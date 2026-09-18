#include <webview/webview.h>

#include <atomic>
#include <exception>
#include <memory>
#include <mutex>
#include <string>

#include "runner.hpp"

namespace rti::demo::ui::native {
namespace detail {

const char* native_window_failure_guidance() noexcept {
    return "native window failed; verify the Evergreen WebView2 Runtime is "
           "installed and COM is available on the main STA thread";
}

}  // namespace detail
namespace {

class WebviewHost final : public detail::WindowHost {
   public:
    void create(const std::string& title, const std::string& url,
                const NativeWindowOptions& options) override {
        std::lock_guard<std::mutex> guard(mutex_);
        window_ = std::make_unique<webview::webview>(options.devtools, nullptr);
        window_->set_title(title).ensure_ok();
        window_->set_size(options.width, options.height, WEBVIEW_HINT_NONE)
            .ensure_ok();
        auto native_window = window_->window();
        native_window.ensure_ok();
        native_window_ = static_cast<HWND>(native_window.value());
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
        if (window == nullptr) {
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
        if (native_window_ == nullptr ||
            !PostMessageW(native_window_, WM_CLOSE, 0, 0)) {
            throw NativeWebviewError(
                "failed to post WM_CLOSE to the native window");
        }
    }

    std::mutex mutex_;
    std::unique_ptr<webview::webview> window_;
    HWND native_window_ = nullptr;
    std::atomic<bool> close_requested_{false};
    std::exception_ptr close_error_;
};

}  // namespace

void run(DemoUiApp& app, NativeWindowOptions options) {
    WebviewHost host;
    detail::run_with_signals(app, options, host);
}

}  // namespace rti::demo::ui::native
