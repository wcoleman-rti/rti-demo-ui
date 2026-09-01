/*
 * (c) 2026 Copyright, Real-Time Innovations, Inc.  All rights reserved.
 *
 * RTI grants Licensee a license to use, modify, compile, and create derivative
 * works of the Software.  Licensee has the right to distribute object form
 * only for use with RTI products.  The Software is provided "as is", with no
 * warranty of any type, including any warranty for fitness for any purpose.
 * RTI is under no obligation to maintain or support the Software.  RTI shall
 * not be liable for any incidental or consequential damages arising out of the
 * use or inability to use the software.
 */

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
    explicit Model(std::string title, std::filesystem::path static_root = {},
                   Theme theme = Theme::dark, Layout layout = Layout::automatic)
        : title_(std::move(title)),
          static_root_(std::move(static_root)),
          theme_(theme),
          layout_(layout) {}

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
    void commit_presentation_locked();
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
    Theme theme_;
    Layout layout_;
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
    bool presentation_dirty_ = false;
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
    enum class WriteResult { written, unwritable, failed, timed_out };
    using Writer = std::function<WriteResult(const char*, size_t)>;

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
    bool write(const std::shared_ptr<Subscriber>& subscriber,
               const Delivery* delivery, const char* data, size_t size,
               const Writer& writer);

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

/// Bound server address published after DemoUiApp::run starts listening.
struct ReadyInfo {
    std::string host;  ///< Configured bind host.
    int port;          ///< Selected TCP port.
    std::string url;   ///< HTTP base URL without a trailing slash.
};

/// Browser confirmation text displayed before invoking a command.
struct CommandConfirmation {
    std::string title;    ///< Confirmation dialog title.
    std::string message;  ///< Confirmation dialog message.
};

/**
 * Restricted JSON schema used to validate command request bodies.
 *
 * Supported keywords are `type`, `properties`, `required`, `items`, `enum`,
 * `minimum`, `maximum`, `minLength`, `maxLength`, and
 * `additionalProperties`.
 */
class CommandSchema {
   public:
    /**
     * Validate and retain a schema definition.
     * @throws std::invalid_argument if the definition uses invalid or
     * unsupported schema constructs.
     */
    explicit CommandSchema(Json schema);

    /// Return the validated schema definition.
    const Json& value() const { return schema_; }

    /**
     * Validate one JSON value.
     * @return Validation details; an empty vector means the value is valid.
     */
    std::vector<Json> validate(const Json& value) const;

   private:
    Json schema_;
};

/// Synchronous command callback returning a JSON-compatible result.
using CommandHandler = std::function<Json(const Json&)>;

/**
 * Cancelable handle to an SDK-owned periodic timer.
 *
 * Dropping the handle does not stop the timer because DemoUiApp retains shared
 * ownership. Cancellation is idempotent and joins the timer thread.
 */
class TimerHandle {
   public:
    /// Construct an empty handle whose cancel operation is a no-op.
    TimerHandle() = default;

    /** @cond INTERNAL */
    explicit TimerHandle(std::shared_ptr<detail::TimerState> state);
    /** @endcond */

    /// Stop the timer and join its thread. Safe to call more than once.
    void cancel();

   private:
    std::shared_ptr<detail::TimerState> state_;
};

/**
 * Local HTTP server and authoritative UI component model.
 *
 * Configure cards, components, state, and commands, then call run() to block
 * while serving the browser UI. The app owns every returned Card and Component
 * pointer; those non-owning handles remain valid until app destruction.
 *
 * C++ model operations are thread-safe. The app is single-use: run() can be
 * called only once. stop() is idempotent and may be called from another thread.
 */
class DemoUiApp {
   public:
    /**
     * Construct an application without binding a socket.
     *
     * @param title Non-empty browser title.
     * @param port TCP port from 0 through 65535; 0 selects an available port.
     * @param host Bind host. Literal loopback is required for commands.
     * @param static_root Optional custom-frontend directory containing a
     * regular `index.html`; an empty path selects the built-in frontend.
     * @param theme Initial built-in theme.
     * @param layout Initial card layout.
     * @throws std::invalid_argument if any argument is invalid.
     */
    explicit DemoUiApp(std::string title, int port = 0,
                       std::string host = "127.0.0.1",
                       std::filesystem::path static_root = {},
                       Theme theme = Theme::dark,
                       Layout layout = Layout::automatic);
    ~DemoUiApp();

    DemoUiApp(const DemoUiApp&) = delete;
    DemoUiApp& operator=(const DemoUiApp&) = delete;

    /**
     * Add a card to the application.
     * @return A non-owning pointer valid until app destruction.
     * @throws std::invalid_argument if the title, area, span, or sidebar
     * constraints are invalid.
     * @throws std::runtime_error if the app is stopped.
     */
    Card* add_card(const std::string& title, CardArea area = CardArea::main,
                   int span = 1);

    /**
     * Change the built-in frontend theme.
     *
     * Setting the current value is a no-op and does not increment the revision.
     *
     * @throws std::invalid_argument if `theme` is invalid.
     * @throws std::runtime_error if the app is stopped.
     */
    void set_theme(Theme theme);

    /**
     * Change the card layout.
     *
     * `sidebar_main` requires exactly one sidebar card. Setting the current
     * value is a no-op and does not increment the revision.
     *
     * @throws std::invalid_argument if the layout or sidebar state is invalid.
     * @throws std::runtime_error if the app is stopped.
     */
    void set_layout(Layout layout);

    /**
     * Replace the complete application-owned JSON state.
     * @throws std::invalid_argument if `value` is not JSON-compatible.
     * @throws std::runtime_error if the app is stopped.
     */
    void set_data(Json value);

    /**
     * Replace a nested application-state value at `path`.
     *
     * An empty path replaces the complete value. Missing object keys are
     * created only when `create_missing` is true; array elements cannot be
     * created.
     *
     * @throws std::invalid_argument if the path or value is invalid.
     * @throws std::runtime_error if the app is stopped.
     */
    void update_data(const std::vector<std::string>& path, Json value,
                     bool create_missing = false);

    /**
     * Register a browser-invokable command before run() begins.
     *
     * Names match `[a-z][a-z0-9-]{0,62}`. Commands are available only when
     * binding literal loopback (`127.0.0.1` or `::1`). Handlers execute
     * synchronously on server worker threads.
     *
     * @throws std::invalid_argument if the name, host, handler, or uniqueness
     * constraint is invalid.
     * @throws std::runtime_error if run() has begun or the app is stopped.
     */
    void register_command(
        const std::string& name, CommandSchema schema, CommandHandler handler,
        std::optional<CommandConfirmation> confirmation = std::nullopt);

    /**
     * Start an SDK-owned periodic callback thread.
     *
     * The first invocation occurs after one interval. An exception escaping the
     * callback stops that timer. Dropping the returned handle does not cancel
     * it; app shutdown cancels and joins every timer.
     *
     * @throws std::invalid_argument if `interval_ms` is not positive.
     * @throws std::runtime_error if the app is stopped.
     */
    TimerHandle add_timer(int interval_ms, std::function<void()> callback);

    /**
     * Bind, publish readiness, and block while serving requests.
     *
     * @throws std::invalid_argument if `sidebar_main` lacks exactly one
     * sidebar.
     * @throws std::runtime_error if called more than once or binding/listening
     * fails.
     */
    void run();

    /**
     * Stop serving and wait for active commands and timer threads.
     *
     * Safe to call before, during, or after run(), and safe to call repeatedly
     * from a non-callback thread. Do not call from a command handler or SDK
     * timer callback because stop waits for those callbacks to finish.
     */
    void stop() noexcept;

    /**
     * Block until the server publishes ReadyInfo.
     * @throws std::runtime_error if the app stops before becoming ready.
     */
    void wait_until_ready();

    /// Return bound address information, or `std::nullopt` before readiness.
    std::optional<ReadyInfo> ready_info() const;
    const std::string& title() const noexcept { return model_.title_; }
    const std::string& host() const noexcept { return host_; }
    bool run_started() const noexcept { return run_started_.load(); }

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
