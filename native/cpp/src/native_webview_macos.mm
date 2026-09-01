#import <AppKit/AppKit.h>
#import <WebKit/WebKit.h>

#include <webview/webview.h>

#include <atomic>
#include <exception>
#include <memory>
#include <mutex>
#include <string>
#include <utility>

#include "navigation.hpp"
#include "runner.hpp"

@interface RTIDemoNavigationDelegate : NSObject <WKNavigationDelegate, WKUIDelegate> {
    std::string _allowedOrigin;
    id<WKUIDelegate> _forwardingUIDelegate;
}
- (instancetype)initWithAllowedOrigin:(std::string)allowedOrigin
                 forwardingUIDelegate:(id<WKUIDelegate>)forwardingUIDelegate;
@end

@implementation RTIDemoNavigationDelegate

- (instancetype)initWithAllowedOrigin:(std::string)allowedOrigin
                 forwardingUIDelegate:(id<WKUIDelegate>)forwardingUIDelegate {
    self = [super init];
    if (self != nil) {
        _allowedOrigin = std::move(allowedOrigin);
        _forwardingUIDelegate = forwardingUIDelegate;
    }
    return self;
}

- (void)webView:(WKWebView*)webView
    decidePolicyForNavigationAction:(WKNavigationAction*)navigationAction
                    decisionHandler:(void (^)(WKNavigationActionPolicy))decisionHandler {
    NSString* absoluteString = navigationAction.request.URL.absoluteString;
    const char* utf8 = absoluteString.UTF8String;
    const bool allowed =
        utf8 != nullptr && rti::demo::ui::native::detail::same_origin(utf8, _allowedOrigin);
    decisionHandler(allowed ? WKNavigationActionPolicyAllow : WKNavigationActionPolicyCancel);
}

- (WKWebView*)webView:(WKWebView*)webView
    createWebViewWithConfiguration:(WKWebViewConfiguration*)configuration
               forNavigationAction:(WKNavigationAction*)navigationAction
                    windowFeatures:(WKWindowFeatures*)windowFeatures {
    return nil;
}

- (id)forwardingTargetForSelector:(SEL)selector {
    if ([_forwardingUIDelegate respondsToSelector:selector]) {
        return _forwardingUIDelegate;
    }
    return [super forwardingTargetForSelector:selector];
}

- (BOOL)respondsToSelector:(SEL)selector {
    return
        [super respondsToSelector:selector] || [_forwardingUIDelegate respondsToSelector:selector];
}

@end

namespace rti::demo::ui::native {
namespace detail {

const char* native_window_failure_guidance() noexcept {
    return "native window failed; verify AppKit and WebKit are available and "
           "native::run() is called on the process main thread";
}

}  // namespace detail
namespace {

class WebviewHost final : public detail::WindowHost {
   public:
    ~WebviewHost() override {
        if (view_ != nil) {
            view_.navigationDelegate = nil;
            view_.UIDelegate = forwarding_ui_delegate_;
        }
    }

    void create(const std::string& title, const std::string& url,
                const NativeWindowOptions& options) override {
        std::lock_guard<std::mutex> guard(mutex_);
        window_ = std::make_unique<webview::webview>(options.devtools, nullptr);
        auto controller = window_->browser_controller();
        controller.ensure_ok();
        view_ = (__bridge WKWebView*)controller.value();
        forwarding_ui_delegate_ = view_.UIDelegate;
        delegate_ =
            [[RTIDemoNavigationDelegate alloc] initWithAllowedOrigin:detail::origin(url)
                                                forwardingUIDelegate:forwarding_ui_delegate_];
        view_.navigationDelegate = delegate_;
        view_.UIDelegate = delegate_;
        window_->set_title(title).ensure_ok();
        window_->set_size(options.width, options.height, WEBVIEW_HINT_NONE).ensure_ok();
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
        auto* window = window_.get();
        window->dispatch([window]() { window->terminate().ensure_ok(); }).ensure_ok();
    }

    std::mutex mutex_;
    std::unique_ptr<webview::webview> window_;
    WKWebView* view_ = nil;
    id<WKUIDelegate> forwarding_ui_delegate_ = nil;
    RTIDemoNavigationDelegate* delegate_ = nil;
    std::atomic<bool> close_requested_{false};
    std::exception_ptr close_error_;
};

}  // namespace

void run(DemoUiApp& app, NativeWindowOptions options) {
    WebviewHost host;
    detail::run_with_signals(app, options, host);
}

}  // namespace rti::demo::ui::native
