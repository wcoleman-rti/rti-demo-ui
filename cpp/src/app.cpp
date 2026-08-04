// Implements CoreApp (see docs/implementation_plan.md §3, §7.2-§7.3, §8).
#include "rti_demo_gui_sdk/app.hpp"

#include <httplib.h>

#include <iostream>
#include <sstream>

#include "web_assets.hpp"

namespace rti_demo_gui_sdk {

namespace {

std::string json_escape(const std::string& value) {
    std::ostringstream out;
    for (char c : value) {
        switch (c) {
            case '"':
                out << "\\\"";
                break;
            case '\\':
                out << "\\\\";
                break;
            case '\n':
                out << "\\n";
                break;
            default:
                out << c;
        }
    }
    return out.str();
}

void send_asset(httplib::Response& res, const char* body,
                const char* content_type) {
    res.status = 200;
    res.set_header("Cache-Control", "no-cache");
    res.set_header("X-Content-Type-Options", "nosniff");
    res.set_content(body, content_type);
}

void send_not_found(httplib::Response& res) {
    res.status = 404;
    res.set_header("Cache-Control", "no-store");
    res.set_header("X-Content-Type-Options", "nosniff");
    res.set_content("{\"error\":\"not found\"}", "application/json");
}

void send_method_not_allowed(httplib::Response& res) {
    res.status = 405;
    res.set_header("Cache-Control", "no-store");
    res.set_header("X-Content-Type-Options", "nosniff");
    res.set_content("{\"error\":\"method not allowed\"}", "application/json");
}

}  // namespace

namespace detail {

std::string Model::snapshot_json_locked() const {
    std::ostringstream out;
    out << "{\"schema_version\":1,\"revision\":" << revision_ << ",\"title\":\""
        << json_escape(title_) << "\",\"cards\":[";
    for (size_t i = 0; i < cards_.size(); ++i) {
        if (i > 0) out << ",";
        out << cards_[i]->to_json_locked();
    }
    out << "]}";
    return out.str();
}

TimerState::TimerState(std::thread thread,
                       std::shared_ptr<std::atomic<bool>> stop_flag,
                       std::shared_ptr<std::condition_variable> cv,
                       std::shared_ptr<std::mutex> cv_mutex)
    : thread_(std::move(thread)),
      stop_flag_(std::move(stop_flag)),
      cv_(std::move(cv)),
      cv_mutex_(std::move(cv_mutex)) {}

TimerState::~TimerState() { cancel(); }

void TimerState::cancel() {
    if (!stop_flag_) return;
    stop_flag_->store(true);
    cv_->notify_all();
    if (thread_.joinable()) thread_.join();
}

}  // namespace detail

TimerHandle::TimerHandle(std::shared_ptr<detail::TimerState> state)
    : state_(std::move(state)) {}

void TimerHandle::cancel() {
    if (state_) state_->cancel();
}

CoreApp::CoreApp(std::string title, int port, std::string host)
    : host_(std::move(host)), port_(port), model_(std::move(title)) {
    if (model_.title_.empty()) {
        throw std::invalid_argument("CoreApp: title must not be empty");
    }
    if (host_.empty()) {
        throw std::invalid_argument("CoreApp: host must not be empty");
    }
    if (port_ < 1 || port_ > 65535) {
        throw std::invalid_argument(
            "CoreApp: port must be between 1 and 65535");
    }
    server_ = std::make_unique<httplib::Server>();
}

CoreApp::~CoreApp() { stop(); }

Card* CoreApp::add_card(const std::string& title) {
    std::lock_guard<std::mutex> guard(model_.lock());
    model_.ensure_running();
    auto card_id = model_.next_card_id();
    auto card = std::make_unique<Card>(model_, card_id, title);
    Card* card_ptr = card.get();
    model_.cards_.push_back(std::move(card));
    model_.bump_revision_locked();
    return card_ptr;
}

TimerHandle CoreApp::add_timer(int interval_ms,
                               std::function<void()> callback) {
    detail::require_positive(interval_ms, "interval_ms", "CoreApp: ");
    {
        std::lock_guard<std::mutex> guard(model_.lock());
        model_.ensure_running();
    }
    auto stop_flag = std::make_shared<std::atomic<bool>>(false);
    auto cv = std::make_shared<std::condition_variable>();
    auto cv_mutex = std::make_shared<std::mutex>();

    std::thread thread([interval_ms, callback = std::move(callback), stop_flag,
                        cv, cv_mutex]() {
        while (!stop_flag->load()) {
            std::unique_lock<std::mutex> lock(*cv_mutex);
            cv->wait_for(lock, std::chrono::milliseconds(interval_ms),
                         [&]() { return stop_flag->load(); });
            if (stop_flag->load()) return;
            lock.unlock();
            try {
                callback();
            } catch (...) {
                return;
            }
        }
    });

    auto state = std::make_shared<detail::TimerState>(std::move(thread),
                                                       stop_flag, cv, cv_mutex);
    // CoreApp retains a reference so the timer keeps running even if the
    // caller discards the returned TimerHandle (matches the Python backend).
    timers_.push_back(state);
    return TimerHandle(state);
}

void CoreApp::run() {
    server_->Get("/", [](const httplib::Request&, httplib::Response& res) {
        send_asset(res, detail::embedded_index_html(),
                   "text/html; charset=utf-8");
    });
    server_->Get("/runtime.js",
                 [](const httplib::Request&, httplib::Response& res) {
                     send_asset(res, detail::embedded_runtime_js(),
                                "application/javascript; charset=utf-8");
                 });
    server_->Get("/theme.css",
                 [](const httplib::Request&, httplib::Response& res) {
                     send_asset(res, detail::embedded_theme_css(),
                                "text/css; charset=utf-8");
                 });
    server_->Get("/gallery",
                 [](const httplib::Request&, httplib::Response& res) {
                     send_asset(res, detail::embedded_gallery_html(),
                                "text/html; charset=utf-8");
                 });
    server_->Get("/api/health",
                 [](const httplib::Request&, httplib::Response& res) {
                     res.status = 200;
                     res.set_header("Cache-Control", "no-store");
                     res.set_header("X-Content-Type-Options", "nosniff");
                     res.set_content("{\"status\":\"ok\"}", "application/json");
                 });
    server_->Get("/api/state",
                 [this](const httplib::Request&, httplib::Response& res) {
                     std::string body;
                     {
                         std::lock_guard<std::mutex> guard(model_.lock());
                         body = model_.snapshot_json_locked();
                     }
                     res.status = 200;
                     res.set_header("Cache-Control", "no-store");
                     res.set_header("X-Content-Type-Options", "nosniff");
                     res.set_content(body, "application/json");
                 });
    server_->set_error_handler(
        [](const httplib::Request&, httplib::Response& res) {
            if (res.status == 404) send_not_found(res);
        });
    server_->set_default_headers({{"X-Content-Type-Options", "nosniff"}});

    server_->Post("/(.*)", [](const httplib::Request&, httplib::Response& res) {
        send_method_not_allowed(res);
    });
    server_->Put("/(.*)", [](const httplib::Request&, httplib::Response& res) {
        send_method_not_allowed(res);
    });
    server_->Delete("/(.*)",
                    [](const httplib::Request&, httplib::Response& res) {
                        send_method_not_allowed(res);
                    });
    server_->Patch("/(.*)",
                   [](const httplib::Request&, httplib::Response& res) {
                       send_method_not_allowed(res);
                   });

    std::cout << "RTI Demo GUI SDK listening on http://" << host_ << ":"
              << port_ << "/" << std::endl;
    server_->listen(host_, port_);
}

void CoreApp::stop() noexcept {
    if (stopped_) return;
    stopped_ = true;
    model_.stop();
    if (server_) server_->stop();
    // Cancel and join before member teardown: timer callbacks may reference
    // Card/Scene2DViewport objects owned by model_.
    for (auto& timer : timers_) {
        timer->cancel();
    }
    timers_.clear();
}

}  // namespace rti_demo_gui_sdk
