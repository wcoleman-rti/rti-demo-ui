#pragma once

#include <rti_demo_ui_native/native_webview.hpp>
#include <string>

namespace rti::demo::ui::native::detail {

class WindowHost {
   public:
    virtual ~WindowHost() = default;

    virtual void create(const std::string& title, const std::string& url,
                        const NativeWindowOptions& options) = 0;
    virtual void run() = 0;
    virtual void request_close() noexcept = 0;
};

void run_with_host(DemoUiApp& app, const NativeWindowOptions& options,
                   WindowHost& host);
void run_with_signals(DemoUiApp& app, const NativeWindowOptions& options,
                      WindowHost& host);
const char* native_window_failure_guidance() noexcept;

}  // namespace rti::demo::ui::native::detail
