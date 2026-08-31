#include <webview/webview.h>

#include <atomic>
#include <exception>
#include <memory>
#include <mutex>
#include <utility>

#include "runner.hpp"

namespace rti::demo::ui::native {
namespace {

class WebviewHost final : public detail::WindowHost {
   public:
    void create(const std::string& title, const std::string& url,
                const NativeWindowOptions& options) override {
        std::lock_guard<std::mutex> guard(mutex_);
        window_ = std::make_unique<webview::webview>(options.devtools, nullptr);
        window_->set_title(title).ensure_ok();
        auto native_window = window_->window();
        native_window.ensure_ok();
        gtk_window_set_default_size(GTK_WINDOW(native_window.value()),
                                    options.width, options.height);
        gtk_window_set_resizable(GTK_WINDOW(native_window.value()), TRUE);
        window_->navigate(url).ensure_ok();
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
    std::atomic<bool> close_requested_{false};
    std::exception_ptr close_error_;
};

}  // namespace

void run(DemoUiApp& app, NativeWindowOptions options) {
    WebviewHost host;
    detail::run_with_host(app, options, host);
}

}  // namespace rti::demo::ui::native
