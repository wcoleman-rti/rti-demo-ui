#pragma once

#include <atomic>
#include <functional>
#include <stdexcept>
#include <thread>

#ifdef _WIN32
#define NOMINMAX
#include <windows.h>
#else
#include <pthread.h>

#include <cerrno>
#include <csignal>
#include <ctime>
#endif

namespace rti_demo_ui_examples {

class ConsoleControl {
   public:
    ConsoleControl() {
#ifdef _WIN32
        event_ = CreateEvent(nullptr, TRUE, FALSE, nullptr);
        if (event_ == nullptr) {
            throw std::runtime_error("failed to create console control event");
        }
#else
        sigemptyset(&signal_set_);
        sigaddset(&signal_set_, SIGINT);
        if (pthread_sigmask(SIG_BLOCK, &signal_set_, nullptr) != 0) {
            throw std::runtime_error("failed to block SIGINT");
        }
#endif
    }

    ~ConsoleControl() { finish(); }

    ConsoleControl(const ConsoleControl&) = delete;
    ConsoleControl& operator=(const ConsoleControl&) = delete;

    void start(std::function<void()> stop_app) {
        stop_app_ = std::move(stop_app);
#ifdef _WIN32
        active_event_ = event_;
        if (!SetConsoleCtrlHandler(&ConsoleControl::handler, TRUE)) {
            active_event_ = nullptr;
            throw std::runtime_error(
                "failed to register console control handler");
        }
#endif
        started_ = true;
        thread_ = std::thread([this]() { wait_for_interrupt(); });
    }

    void finish() noexcept {
        if (!started_) return;
        stopping_.store(true);
#ifdef _WIN32
        SetEvent(event_);
#endif
        if (thread_.joinable()) thread_.join();
#ifdef _WIN32
        SetConsoleCtrlHandler(&ConsoleControl::handler, FALSE);
        active_event_ = nullptr;
#endif
        started_ = false;
    }

   private:
#ifdef _WIN32
    static BOOL WINAPI handler(DWORD event_type) {
        if ((event_type == CTRL_C_EVENT || event_type == CTRL_BREAK_EVENT) &&
            active_event_ != nullptr) {
            SetEvent(active_event_);
            return TRUE;
        }
        return FALSE;
    }
#endif

    void wait_for_interrupt() {
#ifdef _WIN32
        if (WaitForSingleObject(event_, INFINITE) == WAIT_OBJECT_0 &&
            !stopping_.load() && stop_app_) {
            stop_app_();
        }
#else
        while (!stopping_.load()) {
            timespec timeout{};
            timeout.tv_nsec = 100000000;
            const int signal_number =
                sigtimedwait(&signal_set_, nullptr, &timeout);
            if (signal_number == SIGINT) {
                if (stop_app_) stop_app_();
                return;
            }
            if (signal_number < 0 && errno != EAGAIN && errno != EINTR) return;
        }
#endif
    }

    std::function<void()> stop_app_;
    std::thread thread_;
    std::atomic<bool> stopping_{false};
    bool started_ = false;
#ifdef _WIN32
    HANDLE event_ = nullptr;
    inline static HANDLE active_event_ = nullptr;
#else
    sigset_t signal_set_{};
#endif
};

}  // namespace rti_demo_ui_examples
