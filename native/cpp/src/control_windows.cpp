#include <windows.h>

#include <exception>
#include <thread>

#include "runner.hpp"

namespace rti::demo::ui::native::detail {
namespace {

HANDLE control_event = nullptr;

BOOL WINAPI request_control_shutdown(DWORD control_type) {
    switch (control_type) {
        case CTRL_C_EVENT:
        case CTRL_BREAK_EVENT:
        case CTRL_CLOSE_EVENT:
        case CTRL_LOGOFF_EVENT:
        case CTRL_SHUTDOWN_EVENT:
            if (control_event != nullptr) {
                SetEvent(control_event);
            }
            return TRUE;
        default:
            return FALSE;
    }
}

class ControlHandler {
   public:
    ControlHandler() {
        control_event = CreateEventW(nullptr, TRUE, FALSE, nullptr);
        stop_event_ = CreateEventW(nullptr, TRUE, FALSE, nullptr);
        if (control_event == nullptr || stop_event_ == nullptr) {
            cleanup();
            throw NativeWebviewError(
                "failed to create Windows console control events");
        }
        if (!SetConsoleCtrlHandler(request_control_shutdown, TRUE)) {
            cleanup();
            throw NativeWebviewError(
                "failed to install the Windows console control handler");
        }
        installed_ = true;
    }

    ~ControlHandler() {
        if (installed_) {
            SetConsoleCtrlHandler(request_control_shutdown, FALSE);
        }
        cleanup();
    }

    ControlHandler(const ControlHandler&) = delete;
    ControlHandler& operator=(const ControlHandler&) = delete;

    HANDLE control() const noexcept { return control_event; }
    HANDLE stop() const noexcept { return stop_event_; }
    void request_stop() noexcept { SetEvent(stop_event_); }

   private:
    void cleanup() noexcept {
        if (control_event != nullptr) {
            CloseHandle(control_event);
            control_event = nullptr;
        }
        if (stop_event_ != nullptr) {
            CloseHandle(stop_event_);
            stop_event_ = nullptr;
        }
    }

    HANDLE stop_event_ = nullptr;
    bool installed_ = false;
};

}  // namespace

void run_with_signals(DemoUiApp& app, const NativeWindowOptions& options,
                      WindowHost& host) {
    ControlHandler handler;
    std::thread watcher([&]() {
        const HANDLE events[] = {handler.control(), handler.stop()};
        if (WaitForMultipleObjects(2, events, FALSE, INFINITE) ==
            WAIT_OBJECT_0) {
            host.request_close();
        }
    });

    std::exception_ptr error;
    try {
        run_with_host(app, options, host);
    } catch (...) {
        error = std::current_exception();
    }

    handler.request_stop();
    watcher.join();
    if (error) {
        std::rethrow_exception(error);
    }
}

}  // namespace rti::demo::ui::native::detail
