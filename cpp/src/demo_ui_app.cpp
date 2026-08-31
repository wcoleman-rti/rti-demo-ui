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
constexpr size_t kMaxSseStreams = 16;
constexpr size_t kServerWorkers = 20;
constexpr auto kSseHeartbeatInterval = std::chrono::seconds(15);
constexpr auto kSsePublicationInterval =
    std::chrono::duration<double>(1.0 / 30.0);
constexpr char kSseHeartbeat[] = ": heartbeat\n\n";
constexpr char kSseRetry[] = "retry: 1000\n\n";

std::string sse_event(const char* event, long revision,
                      const std::string& data) {
    return "event: " + std::string(event) +
           "\nid: " + std::to_string(revision) + "\ndata: " + data + "\n\n";
}

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
                {"theme", to_string(theme_)},
                {"layout", to_string(layout_)},
                {"data", data_},
                {"cards", std::move(cards)}}
        .dump();
}

void Model::start_dirty_tracking_locked() {
    dirty_tracking_ = true;
    published_revision_ = revision_;
    app_data_dirty_ = false;
    presentation_dirty_ = false;
    dirty_cards_.clear();
    dirty_components_.clear();
}

void Model::commit_app_data_locked() {
    const bool schedule = dirty_tracking_ && !app_data_dirty_ &&
                          !presentation_dirty_ && dirty_cards_.empty() &&
                          dirty_components_.empty();
    ++revision_;
    if (dirty_tracking_) app_data_dirty_ = true;
    if (schedule && sse_manager_) sse_manager_->mark_dirty_locked();
}

void Model::commit_presentation_locked() {
    const bool schedule = dirty_tracking_ && !app_data_dirty_ &&
                          !presentation_dirty_ && dirty_cards_.empty() &&
                          dirty_components_.empty();
    ++revision_;
    if (dirty_tracking_) presentation_dirty_ = true;
    if (schedule && sse_manager_) sse_manager_->mark_dirty_locked();
}

void Model::commit_card_locked(const std::string& card_id) {
    if (removed_card_ids_.count(card_id) != 0) {
        throw std::runtime_error("cannot upsert removed card target: " +
                                 card_id);
    }
    const bool schedule = dirty_tracking_ && !app_data_dirty_ &&
                          !presentation_dirty_ && dirty_cards_.empty() &&
                          dirty_components_.empty();
    ++revision_;
    if (!dirty_tracking_) return;
    dirty_cards_[card_id] = DirtyOperation::upsert;
    for (auto target = dirty_components_.begin();
         target != dirty_components_.end();) {
        if (target->first.first == card_id) {
            target = dirty_components_.erase(target);
        } else {
            ++target;
        }
    }
    if (schedule && sse_manager_) sse_manager_->mark_dirty_locked();
}

void Model::commit_card_removal_locked(const std::string& card_id) {
    const bool schedule = dirty_tracking_ && !app_data_dirty_ &&
                          !presentation_dirty_ && dirty_cards_.empty() &&
                          dirty_components_.empty();
    ++revision_;
    removed_card_ids_.insert(card_id);
    if (!dirty_tracking_) return;
    dirty_cards_[card_id] = DirtyOperation::remove;
    for (auto target = dirty_components_.begin();
         target != dirty_components_.end();) {
        if (target->first.first == card_id) {
            target = dirty_components_.erase(target);
        } else {
            ++target;
        }
    }
    if (schedule && sse_manager_) sse_manager_->mark_dirty_locked();
}

void Model::commit_component_locked(const std::string& card_id,
                                    const std::string& component_id) {
    const auto target = std::make_pair(card_id, component_id);
    if (removed_card_ids_.count(card_id) != 0 ||
        removed_component_ids_.count(target) != 0) {
        throw std::runtime_error("cannot upsert removed component target: " +
                                 card_id + ":" + component_id);
    }
    const bool schedule = dirty_tracking_ && !app_data_dirty_ &&
                          !presentation_dirty_ && dirty_cards_.empty() &&
                          dirty_components_.empty();
    ++revision_;
    if (dirty_tracking_ && dirty_cards_.count(card_id) == 0) {
        dirty_components_[target] = DirtyOperation::upsert;
    }
    if (schedule && sse_manager_) sse_manager_->mark_dirty_locked();
}

void Model::commit_component_removal_locked(const std::string& card_id,
                                            const std::string& component_id) {
    const bool schedule = dirty_tracking_ && !app_data_dirty_ &&
                          !presentation_dirty_ && dirty_cards_.empty() &&
                          dirty_components_.empty();
    ++revision_;
    removed_component_ids_.emplace(card_id, component_id);
    if (dirty_tracking_ && dirty_cards_.count(card_id) == 0) {
        dirty_components_[{card_id, component_id}] = DirtyOperation::remove;
    }
    if (schedule && sse_manager_) sse_manager_->mark_dirty_locked();
}

std::optional<Json> Model::flush_dirty_targets_locked() {
    if (!dirty_tracking_ ||
        (!app_data_dirty_ && !presentation_dirty_ && dirty_cards_.empty() &&
         dirty_components_.empty())) {
        return std::nullopt;
    }

    Json changes = Json::array();
    if (app_data_dirty_) {
        changes.push_back({{"op", "replace-app-data"}, {"value", data_}});
    }
    if (presentation_dirty_) {
        changes.push_back({{"op", "replace-presentation"},
                           {"theme", to_string(theme_)},
                           {"layout", to_string(layout_)}});
    }
    for (const auto& [card_id, operation] : dirty_cards_) {
        if (operation == DirtyOperation::remove) {
            changes.push_back({{"op", "remove-card"}, {"card_id", card_id}});
            continue;
        }
        const auto card = std::find_if(
            cards_.begin(), cards_.end(),
            [&card_id](const auto& item) { return item->id_ == card_id; });
        changes.push_back(
            {{"op", "upsert-card"}, {"value", (*card)->to_json_locked()}});
    }
    for (const auto& [target, operation] : dirty_components_) {
        const auto& [card_id, component_id] = target;
        if (operation == DirtyOperation::remove) {
            changes.push_back({{"op", "remove-component"},
                               {"card_id", card_id},
                               {"component_id", component_id}});
            continue;
        }
        const auto card = std::find_if(
            cards_.begin(), cards_.end(),
            [&card_id](const auto& item) { return item->id_ == card_id; });
        const auto component = std::find_if(
            (*card)->components_.begin(), (*card)->components_.end(),
            [&component_id](const auto& item) {
                return item->id() == component_id;
            });
        changes.push_back({{"op", "upsert-component"},
                           {"card_id", card_id},
                           {"value", (*component)->to_json_locked()}});
    }

    Json patch{{"schema_version", 1},
               {"base_revision", published_revision_},
               {"revision", revision_},
               {"changes", std::move(changes)}};
    start_dirty_tracking_locked();
    return patch;
}

SseManager::SseManager(Model& model)
    : model_(model),
      publication_interval_(
          std::chrono::ceil<Clock::duration>(kSsePublicationInterval)),
      heartbeat_interval_(kSseHeartbeatInterval) {}

SseManager::~SseManager() { stop(); }

void SseManager::start() {
    std::lock_guard<std::mutex> model_guard(model_.lock());
    std::lock_guard<std::mutex> sse_guard(mutex_);
    if (active_) return;
    active_ = true;
    previous_flush_ = Clock::now() - publication_interval_;
    model_.sse_manager_ = this;
    model_.start_dirty_tracking_locked();
    thread_ = std::thread([this]() { run(); });
}

void SseManager::mark_dirty_locked() {
    std::lock_guard<std::mutex> guard(mutex_);
    if (!active_ || flush_scheduled_) return;
    const auto now = Clock::now();
    flush_deadline_ = std::max(now, previous_flush_ + publication_interval_);
    flush_scheduled_ = true;
    cv_.notify_all();
}

std::shared_ptr<const std::string> SseManager::snapshot_event_locked(
    const Model& model) {
    return std::make_shared<const std::string>(
        sse_event("snapshot", model.revision_, model.snapshot_json_locked()));
}

std::shared_ptr<const std::string> SseManager::patch_event(const Json& patch) {
    return std::make_shared<const std::string>(
        sse_event("patch", patch["revision"].get<long>(), patch.dump()));
}

std::shared_ptr<SseManager::Subscriber> SseManager::subscribe() {
    std::lock_guard<std::mutex> model_guard(model_.lock());
    std::lock_guard<std::mutex> sse_guard(mutex_);
    if (!active_ || subscribers_.size() >= kMaxSseStreams) return nullptr;
    auto subscriber = std::make_shared<Subscriber>();
    subscriber->pending =
        StateEvent{snapshot_event_locked(model_), model_.revision_, true};
    subscriber->tail_revision = model_.revision_;
    subscribers_.insert(subscriber);
    return subscriber;
}

void SseManager::close_locked(const std::shared_ptr<Subscriber>& subscriber) {
    if (subscriber->closed) return;
    subscriber->closed = true;
    subscriber->pending.reset();
    subscribers_.erase(subscriber);
    cv_.notify_all();
}

void SseManager::unsubscribe(const std::shared_ptr<Subscriber>& subscriber) {
    if (!subscriber) return;
    std::lock_guard<std::mutex> guard(mutex_);
    close_locked(subscriber);
}

void SseManager::enqueue_locked(const std::shared_ptr<Subscriber>& subscriber,
                                const StateEvent& event,
                                const StateEvent& replacement) {
    if (subscriber->closed) return;
    if (subscriber->pending) {
        if (subscriber->reset_pending) {
            close_locked(subscriber);
            return;
        }
        subscriber->pending = replacement;
        subscriber->tail_revision = replacement.revision;
        subscriber->reset_pending = true;
    } else {
        subscriber->pending = event;
        subscriber->tail_revision = event.revision;
    }
}

void SseManager::publish_locked(const Json& patch,
                                std::shared_ptr<const std::string> snapshot) {
    const long base_revision = patch["base_revision"].get<long>();
    const long revision = patch["revision"].get<long>();
    const StateEvent patch_state{patch_event(patch), revision, false};
    const StateEvent snapshot_state{std::move(snapshot), revision, true};
    const std::vector<std::shared_ptr<Subscriber>> subscribers(
        subscribers_.begin(), subscribers_.end());
    for (const auto& subscriber : subscribers) {
        const auto& event = subscriber->tail_revision == base_revision
                                ? patch_state
                                : snapshot_state;
        enqueue_locked(subscriber, event, snapshot_state);
    }
    cv_.notify_all();
}

SseManager::Delivery SseManager::next(
    const std::shared_ptr<Subscriber>& subscriber) {
    std::unique_lock<std::mutex> lock(mutex_);
    const auto deadline = Clock::now() + heartbeat_interval_;
    if (!cv_.wait_until(lock, deadline, [&]() {
            return !active_ || subscriber->closed || subscriber->pending;
        })) {
        return Delivery{DeliveryKind::heartbeat, std::nullopt, false};
    }
    if (!active_ || subscriber->closed) {
        return Delivery{DeliveryKind::stopped, std::nullopt, false};
    }
    Delivery delivery{
        DeliveryKind::state, subscriber->pending,
        subscriber->reset_pending && subscriber->pending->snapshot};
    subscriber->pending.reset();
    return delivery;
}

void SseManager::delivered(const std::shared_ptr<Subscriber>& subscriber,
                           const Delivery& delivery, bool success) {
    std::lock_guard<std::mutex> guard(mutex_);
    if (!success) {
        close_locked(subscriber);
    } else if (delivery.reset) {
        subscriber->reset_pending = false;
    }
}

bool SseManager::write(const std::shared_ptr<Subscriber>& subscriber,
                       const Delivery* delivery, const char* data, size_t size,
                       const Writer& writer) {
    const bool success = writer(data, size) == WriteResult::written;
    if (delivery) {
        delivered(subscriber, *delivery, success);
    } else if (!success) {
        unsubscribe(subscriber);
    }
    return success;
}

void SseManager::run() {
    std::unique_lock<std::mutex> sse_lock(mutex_);
    while (active_) {
        cv_.wait(sse_lock, [this]() { return !active_ || flush_scheduled_; });
        if (!active_) break;
        if (cv_.wait_until(sse_lock, flush_deadline_,
                           [this]() { return !active_; })) {
            break;
        }
        if (Clock::now() < flush_deadline_) continue;
        flush_scheduled_ = false;
        sse_lock.unlock();

        std::unique_lock<std::mutex> model_lock(model_.lock());
        auto patch = model_.flush_dirty_targets_locked();
        auto snapshot = patch ? snapshot_event_locked(model_) : nullptr;
        sse_lock.lock();
        if (active_ && patch) {
            previous_flush_ = Clock::now();
            publish_locked(*patch, std::move(snapshot));
        }
        sse_lock.unlock();
        model_lock.unlock();
        sse_lock.lock();
    }
}

void SseManager::stop() noexcept {
    {
        std::lock_guard<std::mutex> guard(mutex_);
        if (!active_ && !thread_.joinable()) return;
        active_ = false;
        flush_scheduled_ = false;
        for (const auto& subscriber : subscribers_) {
            subscriber->closed = true;
            subscriber->pending.reset();
        }
        cv_.notify_all();
    }
    if (thread_.joinable()) thread_.join();
    {
        std::lock_guard<std::mutex> model_guard(model_.lock());
        std::lock_guard<std::mutex> sse_guard(mutex_);
        if (model_.sse_manager_ == this) model_.sse_manager_ = nullptr;
        subscribers_.clear();
    }
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
                     std::filesystem::path static_root, Theme theme,
                     Layout layout)
    : host_(std::move(host)),
      port_(port),
      model_(std::move(title), static_root, theme, layout),
      sse_manager_(std::make_unique<detail::SseManager>(model_)) {
    to_string(theme);
    to_string(layout);
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
    server_->new_task_queue = []() {
        return new httplib::ThreadPool(kServerWorkers);
    };
    server_->set_write_timeout(5, 0);
}

DemoUiApp::~DemoUiApp() { stop(); }

Card* DemoUiApp::add_card(const std::string& title, CardArea area, int span) {
    to_string(area);
    detail::require_card_span(span);
    std::lock_guard<std::mutex> guard(model_.lock());
    model_.ensure_running();
    if (area == CardArea::sidebar) {
        for (const auto& card : model_.cards_) {
            if (card->area() == CardArea::sidebar) {
                throw std::invalid_argument(
                    "DemoUiApp: at most one sidebar card is permitted");
            }
        }
    }
    auto card_id = model_.next_card_id();
    auto card = std::make_unique<Card>(model_, card_id, title, area, span);
    Card* card_ptr = card.get();
    model_.cards_.push_back(std::move(card));
    model_.commit_card_locked(card_id);
    return card_ptr;
}

void DemoUiApp::set_theme(Theme theme) {
    to_string(theme);
    std::lock_guard<std::mutex> guard(model_.lock());
    model_.ensure_running();
    if (theme == model_.theme_) return;
    model_.theme_ = theme;
    model_.commit_presentation_locked();
}

void DemoUiApp::set_layout(Layout layout) {
    to_string(layout);
    std::lock_guard<std::mutex> guard(model_.lock());
    model_.ensure_running();
    if (layout == model_.layout_) return;
    if (layout == Layout::sidebar_main) {
        int sidebar_count = 0;
        for (const auto& card : model_.cards_) {
            if (card->area() == CardArea::sidebar) ++sidebar_count;
        }
        if (sidebar_count != 1) {
            throw std::invalid_argument(
                "DemoUiApp: sidebar-main requires exactly one sidebar card");
        }
    }
    model_.layout_ = layout;
    model_.commit_presentation_locked();
}

void DemoUiApp::set_data(Json value) {
    detail::require_json_compatible(value, "DemoUiApp: ");
    std::lock_guard<std::mutex> guard(model_.lock());
    model_.ensure_running();
    model_.data_ = std::move(value);
    model_.commit_app_data_locked();
}

void DemoUiApp::update_data(const std::vector<std::string>& path, Json value,
                            bool create_missing) {
    detail::require_json_compatible(value, "DemoUiApp: ");
    std::lock_guard<std::mutex> guard(model_.lock());
    model_.ensure_running();
    model_.data_ = model_.update_value(model_.data_, path, std::move(value),
                                       create_missing);
    model_.commit_app_data_locked();
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
    if (!stopped_) {
        std::lock_guard<std::mutex> guard(model_.lock());
        if (model_.layout_ == Layout::sidebar_main) {
            int sidebar_count = 0;
            for (const auto& card : model_.cards_) {
                if (card->area() == CardArea::sidebar) ++sidebar_count;
            }
            if (sidebar_count != 1) {
                throw std::invalid_argument(
                    "DemoUiApp: sidebar-main requires exactly one sidebar "
                    "card");
            }
        }
    }
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
    server_->Get("/api/events", [this](const httplib::Request&,
                                       httplib::Response& res) {
        auto subscriber = sse_manager_->subscribe();
        if (!subscriber) {
            res.status = 503;
            res.set_header("Cache-Control", "no-store");
            res.set_header("X-Content-Type-Options", "nosniff");
            res.set_content("{\"error\":\"event stream capacity reached\"}",
                            "application/json");
            return;
        }
        res.status = 200;
        res.set_header("Cache-Control", "no-cache");
        res.set_header("X-Content-Type-Options", "nosniff");
        auto retry_sent = std::make_shared<bool>(false);
        auto* manager = sse_manager_.get();
        res.set_chunked_content_provider(
            "text/event-stream",
            [manager, subscriber, retry_sent](size_t, httplib::DataSink& sink) {
                const detail::SseManager::Writer writer =
                    [&sink](const char* data, size_t size) {
                        if (!sink.is_writable()) {
                            return detail::SseManager::WriteResult::unwritable;
                        }
                        return sink.write(data, size)
                                   ? detail::SseManager::WriteResult::written
                                   : detail::SseManager::WriteResult::failed;
                    };
                if (!*retry_sent) {
                    *retry_sent = true;
                    return manager->write(subscriber, nullptr, kSseRetry,
                                          sizeof(kSseRetry) - 1, writer);
                }
                const auto delivery = manager->next(subscriber);
                if (delivery.kind ==
                    detail::SseManager::DeliveryKind::stopped) {
                    sink.done();
                    return true;
                }
                if (delivery.kind ==
                    detail::SseManager::DeliveryKind::heartbeat) {
                    return manager->write(subscriber, nullptr, kSseHeartbeat,
                                          sizeof(kSseHeartbeat) - 1, writer);
                }
                const auto& body = *delivery.event->body;
                return manager->write(subscriber, &delivery, body.data(),
                                      body.size(), writer);
            },
            [manager, subscriber](bool) { manager->unsubscribe(subscriber); });
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
    sse_manager_->start();
    if (stopped_) {
        sse_manager_->stop();
        server_->stop();
        return;
    }
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
    sse_manager_->stop();
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
