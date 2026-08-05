// Implements DemoUiApp (see docs/architecture.md §3, §7.2-§7.3, §8).
#include "rti_demo_ui/demo_ui_app.hpp"

#include <httplib.h>

#include <algorithm>
#include <cctype>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <optional>
#include <sstream>

#include "web_assets.hpp"

namespace rti::demo::ui {

namespace {

namespace fs = std::filesystem;

struct ResolvedAsset {
    std::string body;
    std::string content_type;
};

int hex_value(char value) {
    if (value >= '0' && value <= '9') return value - '0';
    if (value >= 'a' && value <= 'f') return value - 'a' + 10;
    if (value >= 'A' && value <= 'F') return value - 'A' + 10;
    return -1;
}

std::optional<std::string> decode_path(const std::string& encoded) {
    std::string decoded;
    decoded.reserve(encoded.size());
    for (size_t index = 0; index < encoded.size(); ++index) {
        if (encoded[index] != '%') {
            decoded.push_back(encoded[index]);
            continue;
        }
        if (index + 2 >= encoded.size()) return std::nullopt;
        const int high = hex_value(encoded[index + 1]);
        const int low = hex_value(encoded[index + 2]);
        if (high < 0 || low < 0) return std::nullopt;
        const char decoded_byte = static_cast<char>((high << 4) | low);
        if (decoded_byte == '\0') return std::nullopt;
        decoded.push_back(decoded_byte);
        index += 2;
    }
    if (decoded.find('\0') != std::string::npos) return std::nullopt;
    return decoded;
}

std::string content_type_for(const fs::path& path) {
    std::string extension = path.extension().string();
    std::transform(extension.begin(), extension.end(), extension.begin(),
                   [](unsigned char value) {
                       return static_cast<char>(std::tolower(value));
                   });
    if (extension == ".css") return "text/css; charset=utf-8";
    if (extension == ".gif") return "image/gif";
    if (extension == ".gltf") return "application/json; charset=utf-8";
    if (extension == ".html") return "text/html; charset=utf-8";
    if (extension == ".ico") return "image/x-icon";
    if (extension == ".jpeg" || extension == ".jpg") return "image/jpeg";
    if (extension == ".js") return "application/javascript; charset=utf-8";
    if (extension == ".json") return "application/json; charset=utf-8";
    if (extension == ".png") return "image/png";
    if (extension == ".svg") return "image/svg+xml";
    if (extension == ".ttf") return "font/ttf";
    if (extension == ".txt") return "text/plain; charset=utf-8";
    if (extension == ".webp") return "image/webp";
    if (extension == ".woff") return "font/woff";
    if (extension == ".woff2") return "font/woff2";
    return "application/octet-stream";
}

std::optional<ResolvedAsset> resolve_static_asset(
    const fs::path& static_root, const std::string& request_path) {
    const auto decoded = decode_path(request_path);
    if (!decoded || decoded->empty() || decoded->front() != '/') {
        return std::nullopt;
    }

    fs::path relative_path;
    if (*decoded == "/") {
        relative_path = "index.html";
    } else {
        const std::string relative_name = decoded->substr(1);
        if (relative_name.empty() || relative_name.front() == '/') {
            return std::nullopt;
        }
        relative_path = fs::path(relative_name);
        if (relative_path.is_absolute()) return std::nullopt;
    }

    std::error_code error;
    const fs::path candidate = static_root / relative_path;
    const fs::path resolved = fs::weakly_canonical(candidate, error);
    if (error) return std::nullopt;
    const fs::path relative_to_root =
        fs::relative(resolved, static_root, error);
    if (error || relative_to_root.is_absolute()) return std::nullopt;
    for (const auto& component : relative_to_root) {
        if (component == "..") return std::nullopt;
    }
    if (!fs::is_regular_file(resolved, error) || error) return std::nullopt;

    std::ifstream file(resolved, std::ios::binary);
    if (!file) return std::nullopt;
    std::ostringstream body;
    body << file.rdbuf();
    return ResolvedAsset{body.str(), content_type_for(resolved)};
}

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

void send_resolved_asset(httplib::Response& res, const ResolvedAsset& asset) {
    res.status = 200;
    res.set_header("Cache-Control", "no-cache");
    res.set_header("X-Content-Type-Options", "nosniff");
    res.set_content(asset.body, asset.content_type);
}

void send_static_not_found(httplib::Response& res) {
    res.status = 404;
    res.set_header("Cache-Control", "no-cache");
    res.set_header("X-Content-Type-Options", "nosniff");
    res.set_content("not found", "text/plain; charset=utf-8");
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

DemoUiApp::DemoUiApp(std::string title, int port, std::string host,
                     std::filesystem::path static_root)
    : host_(std::move(host)), port_(port), model_(std::move(title)) {
    if (model_.title_.empty()) {
        throw std::invalid_argument("DemoUiApp: title must not be empty");
    }
    if (host_.empty()) {
        throw std::invalid_argument("DemoUiApp: host must not be empty");
    }
    if (port_ < 1 || port_ > 65535) {
        throw std::invalid_argument(
            "DemoUiApp: port must be between 1 and 65535");
    }
    if (!static_root.empty()) {
        std::error_code error;
        const auto canonical_root =
            std::filesystem::canonical(static_root, error);
        if (error || !std::filesystem::is_directory(canonical_root, error) ||
            error) {
            throw std::invalid_argument(
                "DemoUiApp: static_root must be an existing directory");
        }
        const auto index_path = canonical_root / "index.html";
        if (!std::filesystem::is_regular_file(index_path, error) || error) {
            throw std::invalid_argument(
                "DemoUiApp: static_root must contain a regular index.html");
        }
        static_root_ = canonical_root;
    }
    server_ = std::make_unique<httplib::Server>();
}

DemoUiApp::~DemoUiApp() { stop(); }

Card* DemoUiApp::add_card(const std::string& title) {
    std::lock_guard<std::mutex> guard(model_.lock());
    model_.ensure_running();
    auto card_id = model_.next_card_id();
    auto card = std::make_unique<Card>(model_, card_id, title);
    Card* card_ptr = card.get();
    model_.cards_.push_back(std::move(card));
    model_.bump_revision_locked();
    return card_ptr;
}

TimerHandle DemoUiApp::add_timer(int interval_ms,
                                 std::function<void()> callback) {
    detail::require_positive(interval_ms, "interval_ms", "DemoUiApp: ");
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
    // DemoUiApp retains a reference so the timer keeps running even if the
    // caller discards the returned TimerHandle (matches the Python backend).
    timers_.push_back(state);
    return TimerHandle(state);
}

void DemoUiApp::run() {
    server_->Get(
        "/", [this](const httplib::Request& req, httplib::Response& res) {
            if (static_root_.empty()) {
                send_asset(res, detail::embedded_index_html(),
                           "text/html; charset=utf-8");
                return;
            }
            const auto asset = resolve_static_asset(static_root_, req.path);
            if (asset) {
                send_resolved_asset(res, *asset);
            } else {
                send_static_not_found(res);
            }
        });
    server_->Get("/sdk/index.html",
                 [](const httplib::Request&, httplib::Response& res) {
                     send_asset(res, detail::embedded_index_html(),
                                "text/html; charset=utf-8");
                 });
    server_->Get("/sdk/runtime.js",
                 [](const httplib::Request&, httplib::Response& res) {
                     send_asset(res, detail::embedded_runtime_js(),
                                "application/javascript; charset=utf-8");
                 });
    server_->Get("/sdk/theme.css",
                 [](const httplib::Request&, httplib::Response& res) {
                     send_asset(res, detail::embedded_theme_css(),
                                "text/css; charset=utf-8");
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
    server_->Get("/api", [](const httplib::Request&, httplib::Response& res) {
        send_not_found(res);
    });
    server_->Get(R"(/api/.*)",
                 [](const httplib::Request&, httplib::Response& res) {
                     send_not_found(res);
                 });
    server_->Get("/sdk", [](const httplib::Request&, httplib::Response& res) {
        send_static_not_found(res);
    });
    server_->Get(R"(/sdk/.*)",
                 [](const httplib::Request&, httplib::Response& res) {
                     send_static_not_found(res);
                 });
    server_->Get(
        R"(/.*)", [this](const httplib::Request& req, httplib::Response& res) {
            if (static_root_.empty()) {
                send_not_found(res);
                return;
            }
            const auto asset = resolve_static_asset(static_root_, req.path);
            if (asset) {
                send_resolved_asset(res, *asset);
            } else {
                send_static_not_found(res);
            }
        });
    server_->set_error_handler(
        [](const httplib::Request&, httplib::Response& res) {
            if (res.status == 404 && res.body.empty()) send_not_found(res);
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

    if (stopped_) return;
    if (!server_->bind_to_port(host_, port_)) {
        throw std::runtime_error("DemoUiApp: failed to bind " + host_ + ":" +
                                 std::to_string(port_));
    }
    if (stopped_) {
        server_->stop();
        return;
    }
    std::cout << "RTI Demo UI listening on http://" << host_ << ":" << port_
              << "/" << std::endl;
    if (!server_->listen_after_bind()) {
        throw std::runtime_error("DemoUiApp: failed to listen on " + host_ +
                                 ":" + std::to_string(port_));
    }
}

void DemoUiApp::stop() noexcept {
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

}  // namespace rti::demo::ui
