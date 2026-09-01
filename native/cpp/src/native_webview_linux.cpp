#include <webview/webview.h>

#include <atomic>
#include <exception>
#include <filesystem>
#include <memory>
#include <mutex>
#include <system_error>
#include <utility>

#include "navigation.hpp"
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
    void create(const std::string& title, const std::string& url,
                const NativeWindowOptions& options) override {
        std::lock_guard<std::mutex> guard(mutex_);
        window_ = std::make_unique<webview::webview>(options.devtools, nullptr);
        configure_persistent_cookies();
        allowed_origin_ = detail::origin(url);
        auto controller = window_->browser_controller();
        controller.ensure_ok();
        auto* view = WEBKIT_WEB_VIEW(controller.value());
        g_signal_connect(view, "decide-policy",
                         G_CALLBACK(block_external_navigation), this);
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
    bool same_origin(const std::string& uri) const {
        return detail::same_origin(uri, allowed_origin_);
    }

    static gboolean block_external_navigation(
        WebKitWebView*, WebKitPolicyDecision* decision,
        WebKitPolicyDecisionType decision_type, gpointer user_data) {
        if (decision_type != WEBKIT_POLICY_DECISION_TYPE_NAVIGATION_ACTION &&
            decision_type != WEBKIT_POLICY_DECISION_TYPE_NEW_WINDOW_ACTION) {
            return FALSE;
        }
        auto* navigation = WEBKIT_NAVIGATION_POLICY_DECISION(decision);
        auto* action =
            webkit_navigation_policy_decision_get_navigation_action(navigation);
        const char* uri = webkit_uri_request_get_uri(
            webkit_navigation_action_get_request(action));
        const auto* host = static_cast<WebviewHost*>(user_data);
        if (uri != nullptr && host->same_origin(uri)) {
            return FALSE;
        }
        webkit_policy_decision_ignore(decision);
        return TRUE;
    }

    static std::filesystem::path profile_directory() {
        std::error_code error;
        const auto executable =
            std::filesystem::read_symlink("/proc/self/exe", error);
        if (error || executable.filename().empty()) {
            throw NativeWebviewError(
                "could not determine the executable identity from "
                "/proc/self/exe");
        }
        const char* data_home = g_get_user_data_dir();
        if (data_home == nullptr || data_home[0] == '\0') {
            throw NativeWebviewError(
                "could not determine the Linux user data directory");
        }
        return std::filesystem::path(data_home) / "rti-demo-ui-native" /
               executable.filename();
    }

    void configure_persistent_cookies() {
        const auto directory = profile_directory();
        std::error_code error;
        std::filesystem::create_directories(directory, error);
        if (error) {
            throw NativeWebviewError(
                "could not create native profile directory '" +
                directory.string() + "': " + error.message());
        }

        auto controller = window_->browser_controller();
        controller.ensure_ok();
        auto* view = WEBKIT_WEB_VIEW(controller.value());
        auto* context = webkit_web_view_get_context(view);
        auto* manager = webkit_web_context_get_cookie_manager(context);
        const auto cookie_database = directory / "cookies.sqlite";
        webkit_cookie_manager_set_persistent_storage(
            manager, cookie_database.c_str(),
            WEBKIT_COOKIE_PERSISTENT_STORAGE_SQLITE);
        webkit_cookie_manager_set_accept_policy(
            manager, WEBKIT_COOKIE_POLICY_ACCEPT_NO_THIRD_PARTY);
    }

    void dispatch_close_locked() {
        auto* window = window_.get();
        window->dispatch([window]() { window->terminate().ensure_ok(); })
            .ensure_ok();
    }

    std::mutex mutex_;
    std::unique_ptr<webview::webview> window_;
    std::atomic<bool> close_requested_{false};
    std::exception_ptr close_error_;
    std::string allowed_origin_;
};

}  // namespace

void run(DemoUiApp& app, NativeWindowOptions options) {
    WebviewHost host;
    detail::run_with_signals(app, options, host);
}

}  // namespace rti::demo::ui::native
