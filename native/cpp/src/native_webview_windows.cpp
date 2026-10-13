#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <webview/webview.h>
#include <windows.h>

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
    ~WebviewHost() override {
        window_.reset();
        if (large_icon_ != nullptr) {
            DestroyIcon(large_icon_);
        }
        if (small_icon_ != nullptr) {
            DestroyIcon(small_icon_);
        }
    }

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
        if (!options.icon.empty()) {
            const auto icon_path = options.icon.wstring();
            large_icon_ = static_cast<HICON>(
                LoadImageW(nullptr, icon_path.c_str(), IMAGE_ICON,
                           GetSystemMetrics(SM_CXICON),
                           GetSystemMetrics(SM_CYICON), LR_LOADFROMFILE));
            if (large_icon_ == nullptr) {
                throw NativeWebviewError(
                    "failed to load native window icon; Windows requires an "
                    "ICO image");
            }
            small_icon_ = static_cast<HICON>(
                LoadImageW(nullptr, icon_path.c_str(), IMAGE_ICON,
                           GetSystemMetrics(SM_CXSMICON),
                           GetSystemMetrics(SM_CYSMICON), LR_LOADFROMFILE));
            if (small_icon_ == nullptr) {
                DestroyIcon(large_icon_);
                large_icon_ = nullptr;
                throw NativeWebviewError(
                    "failed to load small native window icon; Windows "
                    "requires an ICO image");
            }
            SendMessageW(native_window_, WM_SETICON, ICON_BIG,
                         reinterpret_cast<LPARAM>(large_icon_));
            SendMessageW(native_window_, WM_SETICON, ICON_SMALL,
                         reinterpret_cast<LPARAM>(small_icon_));
        }
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
    HICON large_icon_ = nullptr;
    HICON small_icon_ = nullptr;
    std::atomic<bool> close_requested_{false};
    std::exception_ptr close_error_;
};

}  // namespace

void run(DemoUiApp& app, NativeWindowOptions options) {
    WebviewHost host;
    detail::run_with_signals(app, options, host);
}

}  // namespace rti::demo::ui::native
