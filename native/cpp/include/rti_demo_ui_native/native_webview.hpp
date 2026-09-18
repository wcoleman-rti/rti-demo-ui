#pragma once

#include <rti_demo_ui/demo_ui_app.hpp>
#include <stdexcept>

namespace rti::demo::ui::native {

/**
 * @brief Reports invalid native options or a native host lifecycle failure.
 */
class NativeWebviewError : public std::runtime_error {
   public:
    using std::runtime_error::runtime_error;
};

/**
 * @brief Initial native window configuration.
 */
struct NativeWindowOptions {
    /** Initial window width in pixels, from 1 through 16384. */
    int width = 1280;
    /** Initial window height in pixels, from 1 through 16384. */
    int height = 800;
    /** Whether to enable the embedded browser's developer tools. */
    bool devtools = false;
};

/**
 * @brief Runs an application in a Linux native webview.
 *
 * This synchronous main-thread entry point owns the native window loop and a
 * joined server thread. Closing the window, stopping the application, or
 * receiving SIGINT or SIGTERM initiates cleanup. The application must be
 * configured for a literal loopback host and must not have been run previously.
 *
 * @param app Configured, single-use application to host.
 * @param options Initial window configuration.
 * @throws NativeWebviewError If validation, server startup, or native window
 * lifecycle handling fails.
 */
void run(DemoUiApp& app, NativeWindowOptions options = {});

}  // namespace rti::demo::ui::native
