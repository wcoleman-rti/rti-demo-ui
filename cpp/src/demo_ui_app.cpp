// Implements DemoUiApp (see docs/architecture.md §3, §7.2-§7.3, §8).
#include "rti_demo_ui/demo_ui_app.hpp"

#include <httplib.h>

#include <algorithm>
#include <cctype>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <optional>
#include <random>
#include <regex>
#include <set>
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

constexpr size_t kCommandBodyLimit = 64 * 1024;

const std::set<std::string> kSchemaKeywords = {
    "type",    "properties", "required",  "items",     "enum",
    "minimum", "maximum",    "minLength", "maxLength", "additionalProperties"};

void validate_schema_definition(const Json& schema) {
    if (!schema.is_object())
        throw std::invalid_argument("CommandSchema: schema must be an object");
    for (const auto& item : schema.items())
        if (!kSchemaKeywords.count(item.key()))
            throw std::invalid_argument("CommandSchema: unsupported keyword '" +
                                        item.key() + "'");
    if (schema.contains("type") &&
        (!schema["type"].is_string() ||
         !std::set<std::string>{"object", "array", "string", "number",
                                "integer", "boolean", "null"}
              .count(schema["type"].get<std::string>())))
        throw std::invalid_argument(
            "CommandSchema: type must be one schema type string");
    if (schema.contains("properties")) {
        if (!schema["properties"].is_object())
            throw std::invalid_argument(
                "CommandSchema: properties must be an object");
        for (const auto& item : schema["properties"].items())
            validate_schema_definition(item.value());
    }
    if (schema.contains("required")) {
        if (!schema["required"].is_array())
            throw std::invalid_argument(
                "CommandSchema: required must be an array");
        std::set<std::string> names;
        for (const auto& name : schema["required"]) {
            if (!name.is_string() ||
                !names.insert(name.get<std::string>()).second)
                throw std::invalid_argument(
                    "CommandSchema: required names must be unique strings");
            if (schema.contains("properties") &&
                !schema["properties"].contains(name.get<std::string>()))
                throw std::invalid_argument(
                    "CommandSchema: required names must be declared "
                    "properties");
        }
    }
    if (schema.contains("items")) {
        if (!schema["items"].is_object())
            throw std::invalid_argument(
                "CommandSchema: items must be one schema object");
        validate_schema_definition(schema["items"]);
    }
    if (schema.contains("enum") && !schema["enum"].is_array())
        throw std::invalid_argument("CommandSchema: enum must be an array");
    if (schema.contains("additionalProperties") &&
        !schema["additionalProperties"].is_boolean())
        throw std::invalid_argument(
            "CommandSchema: additionalProperties must be boolean");
    for (const char* keyword : {"minimum", "maximum"})
        if (schema.contains(keyword) && !schema[keyword].is_number())
            throw std::invalid_argument(std::string("CommandSchema: ") +
                                        keyword + " must be a number");
    for (const char* keyword : {"minLength", "maxLength"})
        if (schema.contains(keyword) && (!schema[keyword].is_number_integer() ||
                                         schema[keyword].get<int>() < 0))
            throw std::invalid_argument(std::string("CommandSchema: ") +
                                        keyword +
                                        " must be a non-negative integer");
    detail::require_json_compatible(schema, "CommandSchema: ");
}

bool schema_type_matches(const std::string& type, const Json& value) {
    if (type == "object") return value.is_object();
    if (type == "array") return value.is_array();
    if (type == "string") return value.is_string();
    if (type == "boolean") return value.is_boolean();
    if (type == "null") return value.is_null();
    if (type == "integer") return value.is_number_integer();
    if (type == "number") return value.is_number();
    return true;
}

void validate_instance(const Json& schema, const Json& value,
                       const std::string& path, std::vector<Json>& details) {
    if (schema.contains("type") &&
        !schema_type_matches(schema["type"].get<std::string>(), value)) {
        details.push_back({{"path", path}, {"message", "unexpected type"}});
        return;
    }
    if (schema.contains("enum")) {
        bool found = false;
        for (const auto& item : schema["enum"])
            if (item == value) found = true;
        if (!found)
            details.push_back(
                {{"path", path}, {"message", "value is not one of enum"}});
    }
    if (value.is_object()) {
        const auto properties = schema.value("properties", Json::object());
        for (const auto& name : schema.value("required", Json::array()))
            if (!value.contains(name.get<std::string>()))
                details.push_back(
                    {{"path", path + "." + name.get<std::string>()},
                     {"message", "is required"}});
        if (schema.value("additionalProperties", true) == false)
            for (const auto& item : value.items())
                if (!properties.contains(item.key()))
                    details.push_back(
                        {{"path", path + "." + item.key()},
                         {"message", "additional property is not allowed"}});
        for (const auto& item : properties.items())
            if (value.contains(item.key()))
                validate_instance(item.value(), value[item.key()],
                                  path + "." + item.key(), details);
    }
    if (value.is_array() && schema.contains("items"))
        for (size_t index = 0; index < value.size(); ++index)
            validate_instance(schema["items"], value[index],
                              path + "[" + std::to_string(index) + "]",
                              details);
    if (value.is_number() && !value.is_boolean()) {
        if (schema.contains("minimum") && value < schema["minimum"])
            details.push_back(
                {{"path", path}, {"message", "is below minimum"}});
        if (schema.contains("maximum") && value > schema["maximum"])
            details.push_back(
                {{"path", path}, {"message", "is above maximum"}});
    }
    if (value.is_string()) {
        if (schema.contains("minLength") &&
            value.get<std::string>().size() < schema["minLength"].get<size_t>())
            details.push_back(
                {{"path", path}, {"message", "is shorter than minLength"}});
        if (schema.contains("maxLength") &&
            value.get<std::string>().size() > schema["maxLength"].get<size_t>())
            details.push_back(
                {{"path", path}, {"message", "is longer than maxLength"}});
    }
}

std::string make_capability() {
    std::random_device random;
    std::ostringstream result;
    for (int index = 0; index < 32; ++index)
        result << std::hex << (random() & 0xff);
    return result.str();
}

std::string command_error_body(const std::string& code,
                               const std::string& message,
                               const Json& details = Json::array()) {
    return Json{
        {"ok", false},
        {"error", {{"code", code}, {"message", message}, {"details", details}}}}
        .dump();
}

void send_command_error(httplib::Response& res, int status,
                        const std::string& code, const std::string& message,
                        const Json& details = Json::array()) {
    res.status = status;
    res.set_header("Cache-Control", "no-store");
    res.set_header("X-Content-Type-Options", "nosniff");
    res.set_content(command_error_body(code, message, details),
                    "application/json");
}

}  // namespace

namespace detail {

Json Model::update_value(const Json& current,
                         const std::vector<std::string>& path, Json value,
                         bool create_missing) const {
    if (path.empty()) {
        throw std::invalid_argument(
            "DemoUiApp: path must contain non-empty string segments");
    }
    Json replacement = current;
    if (!replacement.is_object()) {
        throw std::invalid_argument("DemoUiApp: path requires an object value");
    }
    Json* target = &replacement;
    for (size_t index = 0; index + 1 < path.size(); ++index) {
        if (path[index].empty()) {
            throw std::invalid_argument(
                "DemoUiApp: path must contain non-empty string segments");
        }
        if (!target->contains(path[index])) {
            if (!create_missing) {
                throw std::invalid_argument(
                    "DemoUiApp: path segment does not exist");
            }
            (*target)[path[index]] = Json::object();
        }
        target = &(*target)[path[index]];
        if (!target->is_object()) {
            throw std::invalid_argument(
                "DemoUiApp: path segment is not an object");
        }
    }
    if (path.back().empty()) {
        throw std::invalid_argument(
            "DemoUiApp: path must contain non-empty string segments");
    }
    if (!create_missing && !target->contains(path.back())) {
        throw std::invalid_argument("DemoUiApp: path segment does not exist");
    }
    (*target)[path.back()] = std::move(value);
    require_json_compatible(replacement, "DemoUiApp: ");
    return replacement;
}

std::string Model::snapshot_json_locked() const {
    Json cards = Json::array();
    for (const auto& card : cards_) cards.push_back(card->to_json_locked());
    return Json{{"schema_version", 2},
                {"revision", revision_},
                {"title", title_},
                {"data", data_},
                {"cards", std::move(cards)}}
        .dump();
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

CommandSchema::CommandSchema(Json schema) : schema_(std::move(schema)) {
    validate_schema_definition(schema_);
}

std::vector<Json> CommandSchema::validate(const Json& value) const {
    std::vector<Json> details;
    validate_instance(schema_, value, "$", details);
    return details;
}

DemoUiApp::DemoUiApp(std::string title, int port, std::string host,
                     std::filesystem::path static_root)
    : host_(std::move(host)),
      port_(port),
      model_(std::move(title), static_root) {
    if (model_.title_.empty()) {
        throw std::invalid_argument("DemoUiApp: title must not be empty");
    }
    if (host_.empty()) {
        throw std::invalid_argument("DemoUiApp: host must not be empty");
    }
    if (port_ < 0 || port_ > 65535) {
        throw std::invalid_argument(
            "DemoUiApp: port must be between 0 and 65535");
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
        model_.set_static_root(canonical_root);
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

void DemoUiApp::set_data(Json value) {
    detail::require_json_compatible(value, "DemoUiApp: ");
    std::lock_guard<std::mutex> guard(model_.lock());
    model_.ensure_running();
    model_.data_ = std::move(value);
    model_.bump_revision_locked();
}

void DemoUiApp::update_data(const std::vector<std::string>& path, Json value,
                            bool create_missing) {
    detail::require_json_compatible(value, "DemoUiApp: ");
    std::lock_guard<std::mutex> guard(model_.lock());
    model_.ensure_running();
    model_.data_ = model_.update_value(model_.data_, path, std::move(value),
                                       create_missing);
    model_.bump_revision_locked();
}

void DemoUiApp::register_command(
    const std::string& name, CommandSchema schema, CommandHandler handler,
    std::optional<CommandConfirmation> confirmation) {
    if (stopped_.load() || run_started_.load()) {
        throw std::runtime_error(
            "DemoUiApp: command registration is closed after run() begins");
    }
    static const std::regex name_pattern("^[a-z][a-z0-9-]{0,62}$");
    if (!std::regex_match(name, name_pattern)) {
        throw std::invalid_argument("DemoUiApp: command name is invalid");
    }
    if (host_ != "127.0.0.1" && host_ != "::1") {
        throw std::invalid_argument(
            "DemoUiApp: commands require a literal loopback host");
    }
    if (!handler)
        throw std::invalid_argument("DemoUiApp: command handler is empty");
    std::lock_guard<std::mutex> guard(command_mutex_);
    if (commands_.count(name)) {
        throw std::invalid_argument("DemoUiApp: command is already registered");
    }
    if (command_capability_.empty()) command_capability_ = make_capability();
    commands_.emplace(
        name, RegisteredCommand{std::move(schema), std::move(handler),
                                std::move(confirmation),
                                std::make_shared<std::atomic<bool>>(false)});
}

void DemoUiApp::wait_until_ready() {
    std::unique_lock<std::mutex> lock(readiness_mutex_);
    readiness_cv_.wait(
        lock, [this]() { return ready_info_.has_value() || stopped_.load(); });
    if (!ready_info_)
        throw std::runtime_error("DemoUiApp: server stopped before ready");
}

std::optional<ReadyInfo> DemoUiApp::ready_info() const {
    std::lock_guard<std::mutex> guard(readiness_mutex_);
    return ready_info_;
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
    bool expected = false;
    if (!run_started_.compare_exchange_strong(expected, true)) {
        throw std::runtime_error("DemoUiApp: run() may only be called once");
    }
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
    server_->Get("/sdk/runtime3d.js",
                 [](const httplib::Request&, httplib::Response& res) {
                     send_asset(res, detail::embedded_runtime3d_js(),
                                "application/javascript; charset=utf-8");
                 });
    server_->Get("/sdk/client.js",
                 [](const httplib::Request&, httplib::Response& res) {
                     send_asset(res, detail::embedded_client_js(),
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
    server_->Get("/api/command-capability", [this](const httplib::Request& req,
                                                   httplib::Response& res) {
        const auto info = ready_info();
        const std::string origin = req.get_header_value("Origin");
        const bool trusted_origin =
            req.has_header("Origin") && origin == (info ? info->url : "");
        const bool trusted_local_host =
            !req.has_header("Origin") && info &&
            "http://" + req.get_header_value("Host") == info->url;
        if (commands_.empty() || !info ||
            (!trusted_origin && !trusted_local_host)) {
            send_not_found(res);
            return;
        }
        res.status = 200;
        res.set_header("Cache-Control", "no-store");
        res.set_header("X-Content-Type-Options", "nosniff");
        res.set_content(Json{{"capability", command_capability_}}.dump(),
                        "application/json");
    });
    server_->Post(R"(/api/commands/(.*))", [this](const httplib::Request& req,
                                                  httplib::Response& res) {
        const auto info = ready_info();
        if (!info || req.get_header_value("Origin") != info->url ||
            req.get_header_value("X-RTI-Demo-Command-Capability") !=
                command_capability_) {
            send_command_error(res, 403, "forbidden",
                               "origin or capability rejected");
            return;
        }
        if (req.body.size() > kCommandBodyLimit) {
            send_command_error(res, 413, "payload_too_large",
                               "command body exceeds 64 KiB");
            return;
        }
        const std::string name = req.matches[1].str();
        static const std::regex name_pattern("^[a-z][a-z0-9-]{0,62}$");
        if (name.find('%') != std::string::npos ||
            name.find('/') != std::string::npos ||
            !std::regex_match(name, name_pattern)) {
            send_command_error(res, 400, "validation_error",
                               "invalid command name");
            return;
        }

        RegisteredCommand* command = nullptr;
        {
            std::lock_guard<std::mutex> guard(command_mutex_);
            if (stopped_.load()) {
                send_command_error(res, 409, "command_stopping",
                                   "command service is stopping");
                return;
            }
            const auto found = commands_.find(name);
            if (found == commands_.end()) {
                send_command_error(res, 404, "unknown_command",
                                   "unknown command");
                return;
            }
            command = &found->second;
            bool expected = false;
            if (!command->active->compare_exchange_strong(expected, true)) {
                send_command_error(res, 409, "command_busy",
                                   "command is already running");
                return;
            }
            ++active_commands_;
        }

        auto release = [this, command]() {
            command->active->store(false);
            std::lock_guard<std::mutex> guard(command_mutex_);
            --active_commands_;
            command_cv_.notify_all();
        };
        try {
            const Json payload = Json::parse(req.body, nullptr, false);
            if (payload.is_discarded() || !payload.is_object()) {
                release();
                send_command_error(res, 400, "validation_error",
                                   payload.is_discarded()
                                       ? "request body is not valid JSON"
                                       : "command payload must be an object");
                return;
            }
            const auto details = command->schema.validate(payload);
            if (!details.empty()) {
                release();
                send_command_error(res, 400, "validation_error",
                                   "command payload failed schema validation",
                                   details);
                return;
            }
            const Json result = command->handler(payload);
            detail::require_json_compatible(result, "DemoUiApp: ");
            release();
            res.status = 200;
            res.set_header("Cache-Control", "no-store");
            res.set_header("X-Content-Type-Options", "nosniff");
            res.set_content(Json{{"ok", true}, {"result", result}}.dump(),
                            "application/json");
        } catch (const std::exception& error) {
            std::cerr << "RTI Demo UI command handler failed: " << name << ": "
                      << error.what() << std::endl;
            release();
            send_command_error(res, 500, "handler_error",
                               "command handler failed");
        } catch (...) {
            std::cerr << "RTI Demo UI command handler failed: " << name
                      << std::endl;
            release();
            send_command_error(res, 500, "handler_error",
                               "command handler failed");
        }
    });
    server_->Get(R"(/api/commands/(.*))",
                 [](const httplib::Request&, httplib::Response& res) {
                     send_command_error(res, 405, "method_not_allowed",
                                        "method not allowed");
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
        [](const httplib::Request& req, httplib::Response& res) {
            if (res.status == 413 && req.path.rfind("/api/commands/", 0) == 0) {
                send_command_error(res, 413, "payload_too_large",
                                   "command body exceeds 64 KiB");
            } else if (res.status == 404 && res.body.empty()) {
                send_not_found(res);
            }
        });
    server_->set_default_headers({{"X-Content-Type-Options", "nosniff"}});
    server_->set_payload_max_length(kCommandBodyLimit);

    server_->Put(R"(/api/commands/(.*))",
                 [](const httplib::Request&, httplib::Response& res) {
                     send_command_error(res, 405, "method_not_allowed",
                                        "method not allowed");
                 });
    server_->Delete(R"(/api/commands/(.*))",
                    [](const httplib::Request&, httplib::Response& res) {
                        send_command_error(res, 405, "method_not_allowed",
                                           "method not allowed");
                    });
    server_->Patch(R"(/api/commands/(.*))",
                   [](const httplib::Request&, httplib::Response& res) {
                       send_command_error(res, 405, "method_not_allowed",
                                          "method not allowed");
                   });

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
    const int bound_port =
        port_ == 0 ? server_->bind_to_any_port(host_)
                   : (server_->bind_to_port(host_, port_) ? port_ : -1);
    if (bound_port < 0) {
        throw std::runtime_error("DemoUiApp: failed to bind " + host_ + ":" +
                                 std::to_string(port_));
    }
    if (stopped_) {
        server_->stop();
        return;
    }
    const std::string display_host =
        host_.find(':') == std::string::npos ? host_ : "[" + host_ + "]";
    const ReadyInfo info{
        host_, bound_port,
        "http://" + display_host + ":" + std::to_string(bound_port)};
    {
        std::lock_guard<std::mutex> guard(readiness_mutex_);
        ready_info_ = info;
    }
    readiness_cv_.notify_all();
    std::cout << "RTI Demo UI listening on " << info.url << "/" << std::endl;
    if (!server_->listen_after_bind()) {
        throw std::runtime_error("DemoUiApp: failed to listen on " + host_ +
                                 ":" + std::to_string(bound_port));
    }
}

void DemoUiApp::stop() noexcept {
    if (stopped_) return;
    stopped_ = true;
    readiness_cv_.notify_all();
    model_.stop();
    if (server_) server_->stop();
    {
        std::unique_lock<std::mutex> lock(command_mutex_);
        command_cv_.wait(lock, [this]() { return active_commands_ == 0; });
    }
    // Cancel and join before member teardown: timer callbacks may reference
    // Card/Scene2DViewport objects owned by model_.
    for (auto& timer : timers_) {
        timer->cancel();
    }
    timers_.clear();
}

}  // namespace rti::demo::ui
