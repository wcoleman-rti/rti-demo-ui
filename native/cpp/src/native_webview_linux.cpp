#include <webview/webview.h>

#include <atomic>
#include <exception>
#include <memory>
#include <mutex>
#include <optional>

#include "gtk_environment.hpp"
#include "runner.hpp"

namespace rti::demo::ui::native {
namespace detail {

const char* native_window_failure_guidance() noexcept {
    return "native window failed; verify GTK 3 and WebKitGTK 4.1 are installed";
}

}  // namespace detail
namespace {

class WebviewHost final : public detail::WindowHost {
   public:
    ~WebviewHost() override {
        window_.reset();
        if (identity_changed_) {
            g_set_prgname(original_name_ ? original_name_->c_str() : nullptr);
            if (original_class_) {
                gdk_set_program_class(original_class_->c_str());
            }
        }
    }

    void create(const std::string& title, const std::string& url,
                const NativeWindowOptions& options) override {
        std::lock_guard<std::mutex> guard(mutex_);
        if (!options.application_id.empty()) {
            if (const auto* name = g_get_prgname()) {
                original_name_ = name;
            }
            if (const auto* name = gdk_get_program_class()) {
                original_class_ = name;
            }
            identity_changed_ = true;
            if (!gtk_init_check(nullptr, nullptr)) {
                throw NativeWebviewError(
                    "native window failed; could not initialize GTK");
            }
            g_set_prgname(options.application_id.c_str());
            gdk_set_program_class(options.application_id.c_str());
        }
        window_ = std::make_unique<webview::webview>(options.devtools, nullptr);
        window_->set_title(title).ensure_ok();
        auto native_window = window_->window();
        native_window.ensure_ok();
        auto* gtk_window = GTK_WINDOW(native_window.value());
        gtk_window_set_resizable(gtk_window, TRUE);
        if (!options.icon.empty()) {
            GError* error = nullptr;
            auto* icon =
                gdk_pixbuf_new_from_file(options.icon.string().c_str(), &error);
            if (icon && (gdk_pixbuf_get_width(icon) > 256 ||
                         gdk_pixbuf_get_height(icon) > 256)) {
                g_object_unref(icon);
                icon = gdk_pixbuf_new_from_file_at_scale(
                    options.icon.string().c_str(), 256, 256, TRUE, &error);
            }
            if (!icon) {
                const std::string detail =
                    error ? error->message : "unknown image loading error";
                if (error) {
                    g_error_free(error);
                }
                throw NativeWebviewError("failed to load native window icon: " +
                                         detail);
            }
            gtk_window_set_icon(gtk_window, icon);
            g_object_unref(icon);
        }
        window_->navigate(url).ensure_ok();
        window_
            ->dispatch(
                [gtk_window, width = options.width, height = options.height]() {
                    gtk_window_resize(gtk_window, width, height);
                })
            .ensure_ok();
        if (close_requested_) {
            dispatch_close_locked();
        }
    }

    void run() override {
        webview::webview* window = nullptr;
        {
            std::lock_guard<std::mutex> guard(mutex_);
            window = window_.get();
        }
        if (!window) {
            throw NativeWebviewError("native window was not created");
        }
        window->run().ensure_ok();
        std::exception_ptr close_error;
        {
            std::lock_guard<std::mutex> guard(mutex_);
            close_error = close_error_;
        }
        if (close_error) {
            std::rethrow_exception(close_error);
        }
    }

    void request_close() noexcept override {
        std::lock_guard<std::mutex> guard(mutex_);
        close_requested_ = true;
        if (window_) {
            try {
                dispatch_close_locked();
            } catch (...) {
                close_error_ = std::current_exception();
            }
        }
    }

   private:
    void dispatch_close_locked() {
        auto* window = window_.get();
        window->dispatch([window]() { window->terminate().ensure_ok(); })
            .ensure_ok();
    }

    std::mutex mutex_;
    std::unique_ptr<webview::webview> window_;
    std::optional<std::string> original_name_;
    std::optional<std::string> original_class_;
    bool identity_changed_ = false;
    std::atomic<bool> close_requested_{false};
    std::exception_ptr close_error_;
};

}  // namespace

void run(DemoUiApp& app, NativeWindowOptions options) {
    detail::ScopedGtkEnvironment gtk_environment;
    WebviewHost host;
    detail::run_with_signals(app, options, host);
}

}  // namespace rti::demo::ui::native
