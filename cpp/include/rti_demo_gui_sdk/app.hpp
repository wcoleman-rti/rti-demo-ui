// Base C++ application class: model ownership and local HTTP lifecycle (see
// docs/implementation_plan.md §3, §7.2, §8).
#pragma once

#include <atomic>
#include <condition_variable>
#include <functional>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

#include "rti_demo_gui_sdk/components.hpp"

namespace httplib {
class Server;
}  // namespace httplib

namespace rti_demo_gui_sdk {

namespace detail {

// Internal model state shared by CoreApp, Card, and Scene2DViewport.
class Model {
   public:
    explicit Model(std::string title) : title_(std::move(title)) {}

    std::mutex& lock() { return mutex_; }

    void ensure_running() const {
        if (!running_) {
            throw std::runtime_error("CoreApp: model is stopped");
        }
    }

    void stop() {
        std::lock_guard<std::mutex> guard(mutex_);
        running_ = false;
    }

    void bump_revision_locked() { ++revision_; }

    std::string next_card_id() {
        return "card-" + std::to_string(next_card_id_++);
    }
    std::string next_scene_id() {
        return "scene-" + std::to_string(next_scene_id_++);
    }

    std::string snapshot_json_locked() const;

    std::string title_;
    long revision_ = 0;
    std::vector<std::unique_ptr<Card>> cards_;

   private:
    std::mutex mutex_;
    bool running_ = true;
    int next_card_id_ = 1;
    int next_scene_id_ = 1;
};

// Thread + synchronization state for one SDK-owned periodic timer. Shared
// between CoreApp (which keeps the timer alive/cancels it at stop()) and any
// TimerHandle returned to the caller, so dropping the handle never stops it.
class TimerState {
   public:
    TimerState(std::thread thread, std::shared_ptr<std::atomic<bool>> stop_flag,
               std::shared_ptr<std::condition_variable> cv,
               std::shared_ptr<std::mutex> cv_mutex);
    ~TimerState();

    void cancel();

   private:
    std::thread thread_;
    std::shared_ptr<std::atomic<bool>> stop_flag_;
    std::shared_ptr<std::condition_variable> cv_;
    std::shared_ptr<std::mutex> cv_mutex_;
};

}  // namespace detail

// Cancelable reference to an SDK-owned periodic timer. CoreApp keeps the
// underlying thread running independent of this handle's lifetime; call
// cancel() explicitly to stop it early.
class TimerHandle {
   public:
    TimerHandle() = default;
    explicit TimerHandle(std::shared_ptr<detail::TimerState> state);

    void cancel();

   private:
    std::shared_ptr<detail::TimerState> state_;
};

class CoreApp {
   public:
    explicit CoreApp(std::string title, int port = 8080,
                     std::string host = "0.0.0.0");
    ~CoreApp();

    CoreApp(const CoreApp&) = delete;
    CoreApp& operator=(const CoreApp&) = delete;

    Card* add_card(const std::string& title);
    TimerHandle add_timer(int interval_ms, std::function<void()> callback);
    void run();
    void stop() noexcept;

   private:
    std::string host_;
    int port_;
    detail::Model model_;
    std::unique_ptr<httplib::Server> server_;
    std::vector<std::shared_ptr<detail::TimerState>> timers_;
    bool stopped_ = false;
};

}  // namespace rti_demo_gui_sdk
