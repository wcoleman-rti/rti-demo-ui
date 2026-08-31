// Base C++ application class: model ownership and local HTTP lifecycle (see
// docs/architecture.md §3, §7.2, §8).
#pragma once

#include <atomic>
#include <chrono>
#include <condition_variable>
#include <filesystem>
#include <functional>
#include <map>
#include <memory>
#include <mutex>
#include <optional>
#include <set>
#include <stdexcept>
#include <string>
#include <thread>
#include <unordered_map>
#include <vector>

#include "rti_demo_ui/components.hpp"

namespace httplib {
class Server;
}  // namespace httplib

namespace rti::demo::ui {

namespace detail {

class SseManager;

// Internal model state shared by DemoUiApp, Card, and Scene2DViewport.
class Model {
   public:
    explicit Model(std::string title, std::filesystem::path static_root = {})
        : title_(std::move(title)), static_root_(std::move(static_root)) {}

    std::mutex& lock() { return mutex_; }
    const std::filesystem::path& static_root() const { return static_root_; }
    void set_static_root(std::filesystem::path root) {
        static_root_ = std::move(root);
    }

    void ensure_running() const {
        if (!running_) {
            throw std::runtime_error("DemoUiApp: model is stopped");
        }
    }

    void stop() {
        std::lock_guard<std::mutex> guard(mutex_);
        running_ = false;
    }

    void start_dirty_tracking_locked();
    void commit_app_data_locked();
    void commit_card_locked(const std::string& card_id);
    void commit_card_removal_locked(const std::string& card_id);
    void commit_component_locked(const std::string& card_id,
                                 const std::string& component_id);
    void commit_component_removal_locked(const std::string& card_id,
                                         const std::string& component_id);
    std::optional<Json> flush_dirty_targets_locked();

    std::string next_card_id() {
        return "card-" + std::to_string(next_card_id_++);
    }
    std::string next_component_id(const std::string& type) {
        int& next_id = next_component_ids_[type];
        if (next_id == 0) next_id = 1;
        return type + "-" + std::to_string(next_id++);
    }

    Json update_value(const Json& current, const std::vector<std::string>& path,
                      Json value, bool create_missing) const;

    std::string snapshot_json_locked() const;

    std::string title_;
    std::filesystem::path static_root_;
    long revision_ = 0;
    std::vector<std::unique_ptr<Card>> cards_;
    Json data_ = Json::object();

   private:
    friend class SseManager;

    enum class DirtyOperation { upsert, remove };

    std::mutex mutex_;
    bool running_ = true;
    int next_card_id_ = 1;
    std::unordered_map<std::string, int> next_component_ids_;
    bool dirty_tracking_ = false;
    long published_revision_ = 0;
    bool app_data_dirty_ = false;
    std::map<std::string, DirtyOperation> dirty_cards_;
    std::map<std::pair<std::string, std::string>, DirtyOperation>
        dirty_components_;
    std::set<std::string> removed_card_ids_;
    std::set<std::pair<std::string, std::string>> removed_component_ids_;
    SseManager* sse_manager_ = nullptr;
};

class ModelTestAccess;
class SseTestAccess;

class SseManager {
   public:
    struct StateEvent {
        std::shared_ptr<const std::string> body;
        long revision;
        bool snapshot;
    };

    struct Subscriber {
        std::optional<StateEvent> pending;
        long tail_revision = 0;
        bool reset_pending = false;
        bool closed = false;
    };

    enum class DeliveryKind { state, heartbeat, stopped };

    struct Delivery {
        DeliveryKind kind;
        std::optional<StateEvent> event;
        bool reset = false;
    };

    explicit SseManager(Model& model);
    ~SseManager();

    void start();
    void stop() noexcept;
    void mark_dirty_locked();
    std::shared_ptr<Subscriber> subscribe();
    void unsubscribe(const std::shared_ptr<Subscriber>& subscriber);
    Delivery next(const std::shared_ptr<Subscriber>& subscriber);
    void delivered(const std::shared_ptr<Subscriber>& subscriber,
                   const Delivery& delivery, bool success);

   private:
    friend class SseTestAccess;

    using Clock = std::chrono::steady_clock;

    static std::shared_ptr<const std::string> snapshot_event_locked(
        const Model& model);
    static std::shared_ptr<const std::string> patch_event(const Json& patch);
    void run();
    void publish_locked(const Json& patch,
                        std::shared_ptr<const std::string> snapshot);
    void enqueue_locked(const std::shared_ptr<Subscriber>& subscriber,
                        const StateEvent& event, const StateEvent& replacement);
    void close_locked(const std::shared_ptr<Subscriber>& subscriber);

    Model& model_;
    std::mutex mutex_;
    std::condition_variable cv_;
    std::thread thread_;
    bool active_ = false;
    bool flush_scheduled_ = false;
    Clock::time_point flush_deadline_;
    Clock::time_point previous_flush_;
    std::chrono::steady_clock::duration publication_interval_;
    std::chrono::steady_clock::duration heartbeat_interval_;
    std::set<std::shared_ptr<Subscriber>,
             std::owner_less<std::shared_ptr<Subscriber>>>
        subscribers_;
};

// Thread + synchronization state for one SDK-owned periodic timer. Shared
// between DemoUiApp (which keeps the timer alive/cancels it at stop()) and any
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

struct ReadyInfo {
    std::string host;
    int port;
    std::string url;
};

struct CommandConfirmation {
    std::string title;
    std::string message;
};

class CommandSchema {
   public:
    explicit CommandSchema(Json schema);
    const Json& value() const { return schema_; }
    std::vector<Json> validate(const Json& value) const;

   private:
    Json schema_;
};

using CommandHandler = std::function<Json(const Json&)>;

// Cancelable reference to an SDK-owned periodic timer. DemoUiApp keeps the
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

class DemoUiApp {
   public:
    explicit DemoUiApp(std::string title, int port = 0,
                       std::string host = "127.0.0.1",
                       std::filesystem::path static_root = {});
    ~DemoUiApp();

    DemoUiApp(const DemoUiApp&) = delete;
    DemoUiApp& operator=(const DemoUiApp&) = delete;

    Card* add_card(const std::string& title);
    void set_data(Json value);
    void update_data(const std::vector<std::string>& path, Json value,
                     bool create_missing = false);
    void register_command(
        const std::string& name, CommandSchema schema, CommandHandler handler,
        std::optional<CommandConfirmation> confirmation = std::nullopt);
    TimerHandle add_timer(int interval_ms, std::function<void()> callback);
    void run();
    void stop() noexcept;
    void wait_until_ready();
    std::optional<ReadyInfo> ready_info() const;

   private:
    friend class detail::ModelTestAccess;
    friend class detail::SseTestAccess;

    struct RegisteredCommand {
        CommandSchema schema;
        CommandHandler handler;
        std::optional<CommandConfirmation> confirmation;
        std::shared_ptr<std::atomic<bool>> active;
    };

    std::string host_;
    int port_;
    std::filesystem::path static_root_;
    detail::Model model_;
    std::unique_ptr<detail::SseManager> sse_manager_;
    std::unique_ptr<httplib::Server> server_;
    std::vector<std::shared_ptr<detail::TimerState>> timers_;
    std::atomic<bool> stopped_ = false;
    std::atomic<bool> run_started_ = false;
    std::unordered_map<std::string, RegisteredCommand> commands_;
    std::string command_capability_;
    std::mutex command_mutex_;
    std::condition_variable command_cv_;
    int active_commands_ = 0;
    mutable std::mutex readiness_mutex_;
    std::condition_variable readiness_cv_;
    std::optional<ReadyInfo> ready_info_;
};

}  // namespace rti::demo::ui
