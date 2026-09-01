#include <WebView2.h>
#include <webview/webview.h>
#include <wrl.h>

#include <atomic>
#include <exception>
#include <iomanip>
#include <memory>
#include <mutex>
#include <sstream>
#include <string>

#include "navigation.hpp"
#include "runner.hpp"

namespace rti::demo::ui::native {
namespace detail {

const char* native_window_failure_guidance() noexcept {
    return "native window failed; verify the Evergreen WebView2 Runtime is "
           "installed and COM is available on the main STA thread";
}

}  // namespace detail
namespace {

using Microsoft::WRL::Callback;
using Microsoft::WRL::ComPtr;

void ensure_hresult(HRESULT result, const char* operation) {
    if (SUCCEEDED(result)) {
        return;
    }
    std::ostringstream message;
    message << operation << " failed with HRESULT 0x" << std::hex
            << std::uppercase << static_cast<unsigned long>(result);
    throw NativeWebviewError(message.str());
}

std::string utf8(const wchar_t* value) {
    if (value == nullptr) {
        return {};
    }
    const int size = WideCharToMultiByte(CP_UTF8, 0, value, -1, nullptr, 0,
                                         nullptr, nullptr);
    if (size <= 1) {
        return {};
    }
    std::string result(static_cast<std::size_t>(size), '\0');
    WideCharToMultiByte(CP_UTF8, 0, value, -1, result.data(), size, nullptr,
                        nullptr);
    result.resize(static_cast<std::size_t>(size - 1));
    return result;
}

class WebviewHost final : public detail::WindowHost {
   public:
    ~WebviewHost() override { remove_navigation_policy(); }

    void create(const std::string& title, const std::string& url,
                const NativeWindowOptions& options) override {
        std::lock_guard<std::mutex> guard(mutex_);
        window_ = std::make_unique<webview::webview>(options.devtools, nullptr);
        allowed_origin_ = detail::origin(url);
        install_navigation_policy();
        window_->set_title(title).ensure_ok();
        window_->set_size(options.width, options.height, WEBVIEW_HINT_NONE)
            .ensure_ok();
,         auto native_window = window_->window();
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
    void install_navigation_policy() {
        auto native_controller = window_->browser_controller();
        native_controller.ensure_ok();
        auto* controller =
            static_cast<ICoreWebView2Controller*>(native_controller.value());
        ensure_hresult(controller->get_CoreWebView2(&browser_),
                       "get_CoreWebView2");

        navigation_handler_ =
            Callback<ICoreWebView2NavigationStartingEventHandler>(
                [this](ICoreWebView2*,
                       ICoreWebView2NavigationStartingEventArgs* args) {
                    wchar_t* uri = nullptr;
                    const HRESULT get_result = args->get_Uri(&uri);
                    const std::string value = utf8(uri);
                    CoTaskMemFree(uri);
                    if (FAILED(get_result) ||
                        !detail::same_origin(value, allowed_origin_)) {
                        return args->put_Cancel(TRUE);
                    }
                    return S_OK;
                });
        ensure_hresult(browser_->add_NavigationStarting(
                           navigation_handler_.Get(), &navigation_token_),
                       "add_NavigationStarting");
        navigation_registered_ = true;

        new_window_handler_ =
            Callback<ICoreWebView2NewWindowRequestedEventHandler>(
                [](ICoreWebView2*,
                   ICoreWebView2NewWindowRequestedEventArgs* args) {
                    return args->put_Handled(TRUE);
                });
        ensure_hresult(browser_->add_NewWindowRequested(
                           new_window_handler_.Get(), &new_window_token_),
                       "add_NewWindowRequested");
        new_window_registered_ = true;
    }

    void remove_navigation_policy() noexcept {
        if (browser_ && navigation_registered_) {
            browser_->remove_NavigationStarting(navigation_token_);
        }
        if (browser_ && new_window_registered_) {
            browser_->remove_NewWindowRequested(new_window_token_);
        }
        navigation_registered_ = false;
        new_window_registered_ = false;
    }

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
    ComPtr<ICoreWebView2> browser_;
    ComPtr<ICoreWebView2NavigationStartingEventHandler> navigation_handler_;
    ComPtr<ICoreWebView2NewWindowRequestedEventHandler> new_window_handler_;
    EventRegistrationToken navigation_token_{};
    EventRegistrationToken new_window_token_{};
    bool navigation_registered_ = false;
    bool new_window_registered_ = false;
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
