#include "runner.hpp"

#include <atomic>
#include <csignal>
#include <chrono>
#include <condition_variable>
#include <exception>
#include <mutex>
#include <string>
#include <thread>

namespace rti::demo::ui::native::detail {
namespace {

constexpr int kMaximumWindowDimension = 16384;
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

[[noreturn]] void throw_nested(const std::string& message,
                               const std::exception_ptr& cause) {
    try {
        std::rethrow_exception(cause);
    } catch (...) {
        std::throw_with_nested(NativeWebviewError(message));
    }
}

void validate(DemoUiApp& app, const NativeWindowOptions& options) {
    if (options.width < 1 || options.width > kMaximumWindowDimension) {
        throw NativeWebviewError("width must be between 1 and 16384");
    }
    if (options.height < 1 || options.height > kMaximumWindowDimension) {
        throw NativeWebviewError("height must be between 1 and 16384");
    }
    if (app.host() != "127.0.0.1" && app.host() != "::1") {
        throw NativeWebviewError(
            "native webview mode requires a literal loopback host");
    }
    if (app.run_started() || app.ready_info()) {
        throw NativeWebviewError(
            "DemoUiApp has already started; create a new app for native::run()");
    }
}

}  // namespace

void run_with_host(DemoUiApp& app, const NativeWindowOptions& options,
                   WindowHost& host) {
    validate(app, options);

    std::atomic<bool> shutdown_requested{false};
    std::mutex server_mutex;
    std::condition_variable server_cv;
    bool server_finished = false;
    std::exception_ptr server_error;
    std::thread server([&]() {
        std::exception_ptr error;
        try {
            app.run();
        } catch (...) {
            error = std::current_exception();
        }
        {
            std::lock_guard<std::mutex> guard(server_mutex);
            server_error = error;
            server_finished = true;
        }
        server_cv.notify_all();
        if (!shutdown_requested.load()) {
            host.request_close();
        }
    });

    std::exception_ptr window_error;
    try {
        std::optional<ReadyInfo> ready;
        while (!(ready = app.ready_info())) {
            std::unique_lock<std::mutex> lock(server_mutex);
            if (server_cv.wait_for(
                    lock, std::chrono::milliseconds(1),
                    [&]() { return server_finished; })) {
                if (server_error) {
                    throw_nested("server failed before native window creation",
                                 server_error);
                }
                throw NativeWebviewError(
                    "server stopped before native window creation");
            }
        }
        host.create(app.title(), ready->url + "/", options);
        host.run();
    } catch (...) {
        window_error = std::current_exception();
    }

    shutdown_requested = true;
    app.stop();
    if (server.joinable()) {
        server.join();
    }

    if (server_error) {
        throw_nested("server failed while running the native window",
                     server_error);
    }
    if (window_error) {
        try {
            std::rethrow_exception(window_error);
        } catch (const NativeWebviewError&) {
            throw;
        } catch (...) {
            std::throw_with_nested(NativeWebviewError(
                "native window failed; verify GTK 3 and WebKitGTK 4.1 are "
                "installed"));
        }
    }
}

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
