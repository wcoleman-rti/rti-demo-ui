#include <atomic>
#include <chrono>
#include <csignal>
#include <exception>
#include <thread>

#include "runner.hpp"

namespace rti::demo::ui::native::detail {
namespace {

volatile std::sig_atomic_t signal_requested = 0;

void request_signal_shutdown(int) { signal_requested = 1; }

class SignalHandlers {
   public:
    SignalHandlers() {
        signal_requested = 0;
        previous_int_ = std::signal(SIGINT, request_signal_shutdown);
        if (previous_int_ == SIG_ERR) {
            throw NativeWebviewError("failed to install the SIGINT handler");
        }
        previous_term_ = std::signal(SIGTERM, request_signal_shutdown);
        if (previous_term_ == SIG_ERR) {
            std::signal(SIGINT, previous_int_);
            throw NativeWebviewError("failed to install the SIGTERM handler");
        }
    }

    ~SignalHandlers() {
        std::signal(SIGTERM, previous_term_);
        std::signal(SIGINT, previous_int_);
    }

    SignalHandlers(const SignalHandlers&) = delete;
    SignalHandlers& operator=(const SignalHandlers&) = delete;

   private:
    using Handler = void (*)(int);
    Handler previous_int_ = SIG_DFL;
    Handler previous_term_ = SIG_DFL;
};

}  // namespace

void run_with_signals(DemoUiApp& app, const NativeWindowOptions& options,
                      WindowHost& host) {
    SignalHandlers signal_handlers;
    std::atomic<bool> watcher_stop{false};
    std::thread watcher([&]() {
        while (!watcher_stop.load()) {
            if (signal_requested != 0) {
                host.request_close();
                return;
            }
            std::this_thread::sleep_for(std::chrono::milliseconds(10));
        }
    });

    std::exception_ptr error;
    try {
        run_with_host(app, options, host);
    } catch (...) {
        error = std::current_exception();
    }

    watcher_stop = true;
    watcher.join();
    if (error) {
        std::rethrow_exception(error);
    }
}

}  // namespace rti::demo::ui::native::detail
