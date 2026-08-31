#include "rti_demo_ui/components.hpp"

#include <algorithm>
#include <cmath>
#include <filesystem>
#include <regex>
#include <set>
#include <sstream>

#include "rti_demo_ui/demo_ui_app.hpp"

namespace rti::demo::ui {
namespace {

void require_string(const Json& value, const char* name,
                    const std::string& prefix) {
    if (!value.is_string() || value.get<std::string>().empty()) {
        throw std::invalid_argument(prefix + name +
                                    " must be a non-empty string");
    }
}

void validate_columns(const Json& columns) {
    if (!columns.is_array() || columns.empty())
        throw std::invalid_argument("Table: columns must be a non-empty array");
    std::set<std::string> ids;
    for (const auto& column : columns) {
        if (!column.is_object())
            throw std::invalid_argument("Table: columns must contain objects");
        require_string(column.value("id", Json()), "id", "Table: ");
        require_string(column.value("label", Json()), "label", "Table: ");
        if (!ids.insert(column["id"].get<std::string>()).second)
            throw std::invalid_argument("Table: column IDs must be unique");
    }
}

void validate_rows(const Json& rows, const Json& columns) {
    if (!rows.is_array())
        throw std::invalid_argument("Table: rows must be an array");
    std::set<std::string> column_ids;
    for (const auto& column : columns)
        column_ids.insert(column["id"].get<std::string>());
    std::set<std::string> row_ids;
    for (const auto& row : rows) {
        if (!row.is_object())
            throw std::invalid_argument("Table: rows must contain objects");
        require_string(row.value("id", Json()), "id", "Table: ");
        if (!row["cells"].is_object())
            throw std::invalid_argument("Table: row cells must be an object");
        for (const auto& cell : row["cells"].items())
            if (!column_ids.count(cell.key()))
                throw std::invalid_argument(
                    "Table: row cells must reference declared columns");
        if (!row_ids.insert(row["id"].get<std::string>()).second)
            throw std::invalid_argument("Table: row IDs must be unique");
    }
}

void validate_log_entries(const Json& entries) {
    if (!entries.is_array())
        throw std::invalid_argument("Log: entries must be an array");
    std::set<std::string> ids;
    for (const auto& entry : entries) {
        if (!entry.is_object())
            throw std::invalid_argument("Log: entries must contain objects");
        require_string(entry.value("id", Json()), "id", "Log: ");
        require_string(entry.value("timestamp", Json()), "timestamp", "Log: ");
        if (!entry.value("message", Json()).is_string())
            throw std::invalid_argument("Log: message must be a string");
        if (!ids.insert(entry["id"].get<std::string>()).second)
            throw std::invalid_argument("Log: entry IDs must be unique");
    }
}

Json component_json(const std::string& id, const std::string& type,
                    long revision, Json data) {
    return Json{{"id", id},
                {"type", type},
                {"revision", revision},
                {"data", std::move(data)}};
}

}  // namespace

Component::Component(detail::Model& model, std::string id, std::string type)
    : model_(model), id_(std::move(id)), type_(std::move(type)) {}

void Component::mutated_locked() {
    if (card_id_.empty()) {
        throw std::runtime_error(
            "Component: component is not attached to a card");
    }
    model_.commit_component_locked(card_id_, id_);
    revision_ = model_.revision_;
}

void Component::added_locked(const std::string& card_id) {
    card_id_ = card_id;
    model_.commit_card_locked(card_id_);
    revision_ = model_.revision_;
}

Scene2DViewport::Scene2DViewport(detail::Model& model, std::string id,
                                 int width, int height, GridBounds bounds)
    : Component(model, std::move(id), "scene2d"),
      width_(width),
      height_(height),
      bounds_(bounds) {}

Scene2DViewport::Entity* Scene2DViewport::find_entity(const std::string& id) {
    for (auto& entity : entities_)
        if (entity.id == id) return &entity;
    return nullptr;
}

void Scene2DViewport::add_entity(const std::string& id, double x, double y,
                                 double heading, std::string color,
                                 Severity status, Freshness freshness) {
    const std::string prefix = "Scene2DViewport: ";
    detail::require_non_empty(id, "id", prefix);
    detail::require_finite(x, "x", prefix);
    detail::require_finite(y, "y", prefix);
    detail::require_finite(heading, "heading", prefix);
    detail::require_valid_color(color, prefix);
    std::lock_guard<std::mutex> guard(model_.lock());
    model_.ensure_running();
    if (find_entity(id))
        throw std::invalid_argument(prefix + "entity '" + id +
                                    "' already exists");
    entities_.push_back(
        {id, x, y, heading, std::move(color), status, freshness});
    mutated_locked();
}

void Scene2DViewport::update_entity(const std::string& id,
                                    std::optional<double> x,
                                    std::optional<double> y,
                                    std::optional<double> heading,
                                    std::optional<Severity> status,
                                    std::optional<Freshness> freshness) {
    const std::string prefix = "Scene2DViewport: ";
    if (x) detail::require_finite(*x, "x", prefix);
    if (y) detail::require_finite(*y, "y", prefix);
    if (heading) detail::require_finite(*heading, "heading", prefix);
    std::lock_guard<std::mutex> guard(model_.lock());
    model_.ensure_running();
    Entity* entity = find_entity(id);
    if (!entity)
        throw std::invalid_argument(prefix + "entity '" + id +
                                    "' does not exist");
    if (x) entity->x = *x;
    if (y) entity->y = *y;
    if (heading) entity->heading = *heading;
    if (status) entity->status = *status;
    if (freshness) entity->freshness = *freshness;
    mutated_locked();
}

void Scene2DViewport::remove_entity(const std::string& id) {
    const std::string prefix = "Scene2DViewport: ";
    std::lock_guard<std::mutex> guard(model_.lock());
    model_.ensure_running();
    auto it =
        std::find_if(entities_.begin(), entities_.end(),
                     [&](const Entity& entity) { return entity.id == id; });
    if (it == entities_.end())
        throw std::invalid_argument(prefix + "entity '" + id +
                                    "' does not exist");
    entities_.erase(it);
    links_.erase(std::remove_if(links_.begin(), links_.end(),
                                [&](const Link& link) {
                                    return link.source_id == id ||
                                           link.target_id == id;
                                }),
                 links_.end());
    mutated_locked();
}

void Scene2DViewport::add_link(const std::string& source_id,
                               const std::string& target_id, Severity status) {
    const std::string prefix = "Scene2DViewport: ";
    std::lock_guard<std::mutex> guard(model_.lock());
    model_.ensure_running();
    if (!find_entity(source_id))
        throw std::invalid_argument(prefix + "link source '" + source_id +
                                    "' does not exist");
    if (!find_entity(target_id))
        throw std::invalid_argument(prefix + "link target '" + target_id +
                                    "' does not exist");
    for (const auto& link : links_)
        if (link.source_id == source_id && link.target_id == target_id)
            throw std::invalid_argument(prefix + "link already exists");
    links_.push_back({source_id, target_id, status});
    mutated_locked();
}

void Scene2DViewport::remove_link(const std::string& source_id,
                                  const std::string& target_id) {
    std::lock_guard<std::mutex> guard(model_.lock());
    model_.ensure_running();
    auto it = std::find_if(links_.begin(), links_.end(), [&](const Link& link) {
        return link.source_id == source_id && link.target_id == target_id;
    });
    if (it == links_.end())
        throw std::invalid_argument("Scene2DViewport: link does not exist");
    links_.erase(it);
    mutated_locked();
}

Json Scene2DViewport::to_json_locked() const {
    Json data{{"width", width_},
              {"height", height_},
              {"grid_bounds", bounds_},
              {"entities", Json::array()},
              {"links", Json::array()}};
    for (const auto& entity : entities_)
        data["entities"].push_back(
            {{"id", entity.id},
             {"x", entity.x},
             {"y", entity.y},
             {"heading", entity.heading},
             {"color", entity.color},
             {"status", to_string(entity.status)},
             {"freshness", to_string(entity.freshness)}});
    for (const auto& link : links_)
        data["links"].push_back({{"source_id", link.source_id},
                                 {"target_id", link.target_id},
                                 {"status", to_string(link.status)}});
    return component_json(id_, type_, revision_, std::move(data));
}

Scene3DViewport::Scene3DViewport(detail::Model& model, std::string id,
                                 std::string asset, Json camera,
                                 std::string background, bool grid)
    : Component(model, std::move(id), "scene3d"),
      asset_(std::move(asset)),
      camera_(camera_config(std::move(camera))),
      background_(std::move(background)),
      grid_(grid) {
    validate_asset(asset_, model_.static_root());
    if (!std::regex_match(background_, std::regex("^#[0-9A-Fa-f]{6}$")))
        throw std::invalid_argument(
            "Scene3DViewport: camera configuration is invalid");
}

void Scene3DViewport::validate_asset(const std::string& asset,
                                     const std::filesystem::path& static_root) {
    const bool lexical = asset.size() > 4 && asset.front() == '/' &&
                         asset.rfind("//", 0) != 0 &&
                         asset.rfind("/sdk/", 0) != 0 &&
                         asset.compare(asset.size() - 4, 4, ".glb") == 0 &&
                         asset.find("?") == std::string::npos &&
                         asset.find("#") == std::string::npos &&
                         asset.find('\0') == std::string::npos &&
                         asset.find("://") == std::string::npos;
    if (!lexical) {
        throw std::invalid_argument(
            "Scene3DViewport: asset must be an absolute same-origin .glb path "
            "under static_root");
    }
    std::stringstream stream(asset.substr(1));
    std::string segment;
    while (std::getline(stream, segment, '/')) {
        if (segment == "..") {
            throw std::invalid_argument(
                "Scene3DViewport: asset must be an absolute same-origin .glb "
                "path under static_root");
        }
    }
    if (!static_root.empty()) {
        std::error_code error;
        const auto candidate = std::filesystem::weakly_canonical(
            static_root / asset.substr(1), error);
        const auto relative =
            std::filesystem::relative(candidate, static_root, error);
        if (error || relative.is_absolute() ||
            !std::filesystem::is_regular_file(candidate, error) || error) {
            throw std::invalid_argument(
                "Scene3DViewport: asset must be an absolute same-origin .glb "
                "path under static_root");
        }
        for (const auto& part : relative)
            if (part == "..") {
                throw std::invalid_argument(
                    "Scene3DViewport: asset must be an absolute same-origin "
                    ".glb path under static_root");
            }
    }
}

std::vector<double> Scene3DViewport::validate_vector(const Json& value,
                                                     size_t size,
                                                     const char* kind) {
    const std::string prefix = "Scene3DViewport: ";
    if (!value.is_array() || value.size() != size) {
        if (std::string(kind) == "rotation")
            throw std::invalid_argument(
                prefix +
                "rotation must be a unit quaternion in [x, y, z, w] order");
        if (std::string(kind) == "scale")
            throw std::invalid_argument(
                prefix + "scale values must be finite and greater than zero");
        throw std::invalid_argument(
            prefix +
            "transform arrays must have exactly 3, 4, and 3 finite values");
    }
    std::vector<double> result;
    for (const auto& item : value) {
        if (!item.is_number() || !std::isfinite(item.get<double>())) {
            if (std::string(kind) == "rotation")
                throw std::invalid_argument(
                    prefix +
                    "rotation must be a unit quaternion in [x, y, z, w] order");
            if (std::string(kind) == "scale")
                throw std::invalid_argument(
                    prefix +
                    "scale values must be finite and greater than zero");
            throw std::invalid_argument(
                prefix +
                "transform arrays must have exactly 3, 4, and 3 finite values");
        }
        result.push_back(item.get<double>());
    }
    if (std::string(kind) == "rotation") {
        double norm = 0.0;
        for (double item : result) norm += item * item;
        if (std::abs(norm - 1.0) > 1e-6)
            throw std::invalid_argument(
                prefix +
                "rotation must be a unit quaternion in [x, y, z, w] order");
    }
    if (std::string(kind) == "scale" &&
        std::any_of(result.begin(), result.end(),
                    [](double item) { return item <= 0; }))
        throw std::invalid_argument(
            prefix + "scale values must be finite and greater than zero");
    return result;
}

void Scene3DViewport::validate_path(const Json& value) {
    if (!value.is_string() || value.get<std::string>().empty())
        throw std::invalid_argument("Scene3DViewport: node path is invalid");
    std::stringstream stream(value.get<std::string>());
    std::string segment;
    while (std::getline(stream, segment, '/')) {
        if (segment.empty() || segment.find('~') != std::string::npos) {
            for (size_t index = 0; index < segment.size(); ++index)
                if (segment[index] == '~' &&
                    (index + 1 >= segment.size() ||
                     (segment[index + 1] != '0' && segment[index + 1] != '1')))
                    throw std::invalid_argument(
                        "Scene3DViewport: node path is invalid");
        }
    }
}

Json Scene3DViewport::camera_config(Json camera) {
    Json result = {{"mode", "orbit"},
                   {"position", {4.0, 3.0, 5.0}},
                   {"target", {0.0, 0.0, 0.0}},
                   {"min_distance", 0.1},
                   {"max_distance", 1000.0}};
    if (!camera.is_null()) {
        if (!camera.is_object())
            throw std::invalid_argument(
                "Scene3DViewport: camera configuration is invalid");
        for (const auto& item : camera.items())
            result[item.key()] = item.value();
    }
    try {
        if (result["mode"] != "orbit") throw std::invalid_argument("invalid");
        const auto position =
            validate_vector(result["position"], 3, "position");
        const auto target = validate_vector(result["target"], 3, "target");
        if (position == target || !result["min_distance"].is_number() ||
            !result["max_distance"].is_number() ||
            !std::isfinite(result["min_distance"].get<double>()) ||
            !std::isfinite(result["max_distance"].get<double>()) ||
            result["min_distance"].get<double>() <= 0 ||
            result["min_distance"].get<double>() >=
                result["max_distance"].get<double>())
            throw std::invalid_argument("invalid");
        result["position"] = position;
        result["target"] = target;
        result["min_distance"] = result["min_distance"].get<double>();
        result["max_distance"] = result["max_distance"].get<double>();
    } catch (...) {
        throw std::invalid_argument(
            "Scene3DViewport: camera configuration is invalid");
    }
    return result;
}

Scene3DViewport::Node Scene3DViewport::node_from_operation(
    const Json& operation, const Node* current) {
    if (!operation.is_object() || !operation.value("id", Json()).is_string() ||
        operation["id"].get<std::string>().empty())
        throw std::invalid_argument(
            "Scene3DViewport: node ID must be non-empty");
    Node result =
        current ? *current : Node{operation["id"],  "",
                                  {0.0, 0.0, 0.0},  {0.0, 0.0, 0.0, 1.0},
                                  {1.0, 1.0, 1.0},  true,
                                  Severity::success};
    if (operation.contains("path")) {
        validate_path(operation["path"]);
        if (current && operation["path"].get<std::string>() != result.path)
            throw std::invalid_argument(
                "Scene3DViewport: node path is invalid");
        result.path = operation["path"].get<std::string>();
    } else if (!current) {
        throw std::invalid_argument("Scene3DViewport: node path is invalid");
    }
    if (operation.contains("position"))
        result.position = validate_vector(operation["position"], 3, "position");
    if (operation.contains("rotation"))
        result.rotation = validate_vector(operation["rotation"], 4, "rotation");
    if (operation.contains("scale"))
        result.scale = validate_vector(operation["scale"], 3, "scale");
    if (operation.contains("visible")) {
        if (!operation["visible"].is_boolean())
            throw std::invalid_argument(
                "Scene3DViewport: transform arrays must have exactly 3, 4, and "
                "3 finite values");
        result.visible = operation["visible"].get<bool>();
    }
    if (operation.contains("status")) {
        const auto status = operation["status"].get<std::string>();
        if (status == "success")
            result.status = Severity::success;
        else if (status == "warning")
            result.status = Severity::warning;
        else if (status == "danger")
            result.status = Severity::danger;
        else
            throw std::invalid_argument("Scene3DViewport: invalid status");
    }
    return result;
}

Json Scene3DViewport::nodes_json(const std::vector<Node>& nodes) {
    Json result = Json::array();
    for (const auto& node : nodes)
        result.push_back({{"id", node.id},
                          {"path", node.path},
                          {"position", node.position},
                          {"rotation", node.rotation},
                          {"scale", node.scale},
                          {"visible", node.visible},
                          {"status", to_string(node.status)}});
    return result;
}

Scene3DViewport::Node* Scene3DViewport::find_node(std::vector<Node>& nodes,
                                                  const std::string& id) {
    const auto found =
        std::find_if(nodes.begin(), nodes.end(),
                     [&](const Node& node) { return node.id == id; });
    return found == nodes.end() ? nullptr : &*found;
}

void Scene3DViewport::add_node(const std::string& id, const std::string& path,
                               std::vector<double> position,
                               std::vector<double> rotation,
                               std::vector<double> scale, bool visible,
                               Severity status) {
    apply_node_batch(Json::array({{{"op", "add"},
                                   {"id", id},
                                   {"path", path},
                                   {"position", position},
                                   {"rotation", rotation},
                                   {"scale", scale},
                                   {"visible", visible},
                                   {"status", to_string(status)}}}));
}

void Scene3DViewport::update_node(const std::string& id,
                                  std::optional<std::vector<double>> position,
                                  std::optional<std::vector<double>> rotation,
                                  std::optional<std::vector<double>> scale,
                                  std::optional<bool> visible,
                                  std::optional<Severity> status) {
    Json operation = {{"op", "update"}, {"id", id}};
    if (position) operation["position"] = *position;
    if (rotation) operation["rotation"] = *rotation;
    if (scale) operation["scale"] = *scale;
    if (visible) operation["visible"] = *visible;
    if (status) operation["status"] = to_string(*status);
    apply_node_batch(Json::array({operation}));
}

void Scene3DViewport::remove_node(const std::string& id) {
    apply_node_batch(Json::array({{{"op", "remove"}, {"id", id}}}));
}

void Scene3DViewport::apply_node_batch(const Json& operations) {
    if (!operations.is_array())
        throw std::invalid_argument(
            "Scene3DViewport: batch contains a duplicate operation");
    apply_node_batch(operations.get<std::vector<Json>>());
}

void Scene3DViewport::apply_node_batch(const std::vector<Json>& operations) {
    if (operations.empty() || operations.size() > 1000)
        throw std::invalid_argument(
            "Scene3DViewport: batch contains a duplicate operation");
    std::lock_guard<std::mutex> guard(model_.lock());
    model_.ensure_running();
    auto candidate = nodes_;
    auto used = used_ids_;
    std::set<std::string> operation_keys;
    for (const auto& operation : operations) {
        if (!operation.is_object() ||
            !operation.value("id", Json()).is_string())
            throw std::invalid_argument(
                "Scene3DViewport: node ID must be non-empty");
        const std::string id = operation["id"].get<std::string>();
        const std::string op = operation.value("op", "");
        if (!operation_keys.insert(op + "\n" + id).second)
            throw std::invalid_argument(
                "Scene3DViewport: batch contains a duplicate operation");
        if (op == "add") {
            if (find_node(candidate, id))
                throw std::invalid_argument(
                    "Scene3DViewport: node ID is already in use");
            if (used.count(id))
                throw std::invalid_argument(
                    "Scene3DViewport: node ID is stale");
            candidate.push_back(node_from_operation(operation));
            used.insert(id);
        } else if (op == "update") {
            Node* node = find_node(candidate, id);
            if (!node)
                throw std::invalid_argument(
                    "Scene3DViewport: node ID is stale");
            *node = node_from_operation(operation, node);
        } else if (op == "remove") {
            const auto found =
                std::find_if(candidate.begin(), candidate.end(),
                             [&](const Node& node) { return node.id == id; });
            if (found == candidate.end())
                throw std::invalid_argument(
                    "Scene3DViewport: node ID is stale");
            candidate.erase(found);
            used.insert(id);
        } else {
            throw std::invalid_argument(
                "Scene3DViewport: batch contains a duplicate operation");
        }
    }
    if (nodes_json(candidate) != nodes_json(nodes_)) {
        nodes_ = std::move(candidate);
        used_ids_ = std::move(used);
        mutated_locked();
    }
}

void Scene3DViewport::set_config(const std::string& asset, Json camera,
                                 std::string background, bool grid) {
    validate_asset(asset, model_.static_root());
    const Json replacement_camera = camera_config(std::move(camera));
    if (!std::regex_match(background, std::regex("^#[0-9A-Fa-f]{6}$")))
        throw std::invalid_argument(
            "Scene3DViewport: camera configuration is invalid");
    std::lock_guard<std::mutex> guard(model_.lock());
    model_.ensure_running();
    if (asset != asset_ || replacement_camera != camera_ ||
        background != background_ || grid != grid_) {
        asset_ = asset;
        camera_ = replacement_camera;
        background_ = std::move(background);
        grid_ = grid;
        mutated_locked();
    }
}

Json Scene3DViewport::to_json_locked() const {
    Json data = {{"asset", asset_},
                 {"nodes", nodes_json(nodes_)},
                 {"camera", camera_},
                 {"background", background_},
                 {"grid", grid_}};
    return component_json(id_, type_, revision_, std::move(data));
}

Table::Table(detail::Model& model, std::string id, Json columns, Json rows,
             std::string empty_state)
    : Component(model, std::move(id), "table"),
      columns_(std::move(columns)),
      rows_(std::move(rows)),
      empty_state_(std::move(empty_state)) {
    detail::require_json_compatible(columns_, "Table: ");
    detail::require_json_compatible(rows_, "Table: ");
    validate_columns(columns_);
    validate_rows(rows_, columns_);
}
void Table::set_rows(Json rows) {
    detail::require_json_compatible(rows, "Table: ");
    validate_rows(rows, columns_);
    std::lock_guard<std::mutex> guard(model_.lock());
    model_.ensure_running();
    rows_ = std::move(rows);
    mutated_locked();
}
void Table::upsert_row(Json row) {
    detail::require_json_compatible(row, "Table: ");
    validate_rows(Json::array({row}), columns_);
    std::lock_guard<std::mutex> guard(model_.lock());
    model_.ensure_running();
    for (auto& existing : rows_)
        if (existing["id"] == row["id"]) {
            existing = std::move(row);
            mutated_locked();
            return;
        }
    rows_.push_back(std::move(row));
    mutated_locked();
}
void Table::remove_row(const std::string& id) {
    std::lock_guard<std::mutex> guard(model_.lock());
    model_.ensure_running();
    for (auto it = rows_.begin(); it != rows_.end(); ++it)
        if ((*it)["id"] == id) {
            rows_.erase(it);
            mutated_locked();
            return;
        }
    throw std::invalid_argument("Table: row does not exist");
}
Json Table::to_json_locked() const {
    return component_json(id_, type_, revision_,
                          Json{{"columns", columns_},
                               {"rows", rows_},
                               {"empty_state", empty_state_}});
}

Metric::Metric(detail::Model& model, std::string id, std::string label,
               Json value, std::optional<Severity> severity)
    : Component(model, std::move(id), "metric"),
      label_(std::move(label)),
      value_(std::move(value)),
      severity_(severity) {
    detail::require_non_empty(label_, "label", "Metric: ");
    detail::require_json_compatible(value_, "Metric: ");
}
void Metric::set_value(Json value, std::optional<Severity> severity) {
    detail::require_json_compatible(value, "Metric: ");
    std::lock_guard<std::mutex> guard(model_.lock());
    model_.ensure_running();
    value_ = std::move(value);
    severity_ = severity;
    mutated_locked();
}
Json Metric::to_json_locked() const {
    return component_json(
        id_, type_, revision_,
        Json{{"label", label_},
             {"value", value_},
             {"severity",
              severity_ ? Json(to_string(*severity_)) : Json(nullptr)}});
}

Text::Text(detail::Model& model, std::string id, std::string text,
           std::optional<Severity> severity)
    : Component(model, std::move(id), "text"),
      text_(std::move(text)),
      severity_(severity) {
    detail::require_non_empty(text_, "text", "Text: ");
}
void Text::set_text(std::string text, std::optional<Severity> severity) {
    detail::require_non_empty(text, "text", "Text: ");
    std::lock_guard<std::mutex> guard(model_.lock());
    model_.ensure_running();
    text_ = std::move(text);
    severity_ = severity;
    mutated_locked();
}
Json Text::to_json_locked() const {
    return component_json(
        id_, type_, revision_,
        Json{{"text", text_},
             {"severity",
              severity_ ? Json(to_string(*severity_)) : Json(nullptr)}});
}
Badge::Badge(detail::Model& model, std::string id, std::string text,
             Severity severity)
    : Text(model, std::move(id), std::move(text), severity) {
    type_ = "badge";
}

Log::Log(detail::Model& model, std::string id, Json entries,
         std::string empty_state, int max_entries)
    : Component(model, std::move(id), "log"),
      entries_(std::move(entries)),
      empty_state_(std::move(empty_state)),
      max_entries_(max_entries) {
    detail::require_positive(max_entries_, "max_entries", "Log: ");
    detail::require_json_compatible(entries_, "Log: ");
    validate_log_entries(entries_);
    while (static_cast<int>(entries_.size()) > max_entries_)
        entries_.erase(entries_.begin());
}
void Log::append(Json entry) {
    detail::require_json_compatible(entry, "Log: ");
    validate_log_entries(Json::array({entry}));
    std::lock_guard<std::mutex> guard(model_.lock());
    model_.ensure_running();
    for (const auto& old : entries_)
        if (old["id"] == entry["id"])
            throw std::invalid_argument("Log: entry ID must be unique");
    entries_.push_back(std::move(entry));
    while (static_cast<int>(entries_.size()) > max_entries_)
        entries_.erase(entries_.begin());
    mutated_locked();
}
void Log::clear() {
    std::lock_guard<std::mutex> guard(model_.lock());
    model_.ensure_running();
    entries_.clear();
    mutated_locked();
}
Json Log::to_json_locked() const {
    return component_json(id_, type_, revision_,
                          Json{{"entries", entries_},
                               {"empty_state", empty_state_},
                               {"max_entries", max_entries_}});
}

CustomComponent::CustomComponent(detail::Model& model, std::string id,
                                 std::string type, Json data)
    : Component(model, std::move(id), std::move(type)), data_(std::move(data)) {
    detail::require_non_empty(id_, "id", "CustomComponent: ");
    detail::require_non_empty(type_, "type", "CustomComponent: ");
    if (type_ == "scene2d" || type_ == "table" || type_ == "metric" ||
        type_ == "text" || type_ == "badge" || type_ == "log")
        throw std::invalid_argument("CustomComponent: type is reserved");
    detail::require_json_compatible(data_, "CustomComponent: ");
}
void CustomComponent::set_data(Json data) {
    detail::require_json_compatible(data, "CustomComponent: ");
    std::lock_guard<std::mutex> guard(model_.lock());
    model_.ensure_running();
    data_ = std::move(data);
    mutated_locked();
}
void CustomComponent::update_data(const std::vector<std::string>& path,
                                  Json value, bool create_missing) {
    detail::require_json_compatible(value, "CustomComponent: ");
    std::lock_guard<std::mutex> guard(model_.lock());
    model_.ensure_running();
    data_ = model_.update_value(data_, path, std::move(value), create_missing);
    mutated_locked();
}
Json CustomComponent::to_json_locked() const {
    return component_json(id_, type_, revision_, data_);
}

Card::Card(detail::Model& model, std::string id, std::string title,
           CardArea area, int span)
    : model_(model),
      id_(std::move(id)),
      title_(std::move(title)),
      area_(area),
      span_(span) {
    detail::require_non_empty(title_, "title", "Card: ");
    to_string(area_);
    detail::require_card_span(span_);
}
void Card::set_area(CardArea area) {
    to_string(area);
    std::lock_guard<std::mutex> guard(model_.lock());
    model_.ensure_running();
    if (area == area_) return;
    if (area == CardArea::sidebar) {
        for (const auto& card : model_.cards_) {
            if (card.get() != this && card->area() == CardArea::sidebar) {
                throw std::invalid_argument(
                    "DemoUiApp: at most one sidebar card is permitted");
            }
        }
    }
    if (area_ == CardArea::sidebar && area == CardArea::main &&
        model_.layout_ == Layout::sidebar_main) {
        throw std::invalid_argument(
            "DemoUiApp: sidebar-main requires exactly one sidebar card");
    }
    area_ = area;
    model_.commit_card_locked(id_);
}
void Card::set_span(int span) {
    detail::require_card_span(span);
    std::lock_guard<std::mutex> guard(model_.lock());
    model_.ensure_running();
    if (span == span_) return;
    span_ = span;
    model_.commit_card_locked(id_);
}
Scene2DViewport* Card::add_scene_2d(int width, int height, GridBounds bounds) {
    detail::require_positive(width, "width", "Scene2DViewport: ");
    detail::require_positive(height, "height", "Scene2DViewport: ");
    detail::require_valid_bounds(bounds, "Scene2DViewport: ");
    std::lock_guard<std::mutex> guard(model_.lock());
    model_.ensure_running();
    auto component = std::make_unique<Scene2DViewport>(
        model_, model_.next_component_id("scene"), width, height, bounds);
    auto* result = component.get();
    components_.push_back(std::move(component));
    result->added_locked(id_);
    return result;
}
Scene3DViewport* Card::add_scene_3d(const std::string& asset, Json camera,
                                    std::string background, bool grid) {
    std::lock_guard<std::mutex> guard(model_.lock());
    model_.ensure_running();
    auto component = std::make_unique<Scene3DViewport>(
        model_, model_.next_component_id("scene3d"), asset, std::move(camera),
        std::move(background), grid);
    auto* result = component.get();
    components_.push_back(std::move(component));
    result->added_locked(id_);
    return result;
}
Table* Card::add_table(Json columns, Json rows, std::string empty_state) {
    std::lock_guard<std::mutex> guard(model_.lock());
    model_.ensure_running();
    auto component = std::make_unique<Table>(
        model_, model_.next_component_id("table"), std::move(columns),
        std::move(rows), std::move(empty_state));
    auto* result = component.get();
    components_.push_back(std::move(component));
    result->added_locked(id_);
    return result;
}
Metric* Card::add_metric(const std::string& label, Json value,
                         std::optional<Severity> severity) {
    std::lock_guard<std::mutex> guard(model_.lock());
    model_.ensure_running();
    auto component =
        std::make_unique<Metric>(model_, model_.next_component_id("metric"),
                                 label, std::move(value), severity);
    auto* result = component.get();
    components_.push_back(std::move(component));
    result->added_locked(id_);
    return result;
}
Text* Card::add_text(const std::string& text,
                     std::optional<Severity> severity) {
    std::lock_guard<std::mutex> guard(model_.lock());
    model_.ensure_running();
    auto component = std::make_unique<Text>(
        model_, model_.next_component_id("text"), text, severity);
    auto* result = component.get();
    components_.push_back(std::move(component));
    result->added_locked(id_);
    return result;
}
Badge* Card::add_badge(const std::string& text, Severity severity) {
    std::lock_guard<std::mutex> guard(model_.lock());
    model_.ensure_running();
    auto component = std::make_unique<Badge>(
        model_, model_.next_component_id("badge"), text, severity);
    auto* result = component.get();
    components_.push_back(std::move(component));
    result->added_locked(id_);
    return result;
}
Log* Card::add_log(Json entries, std::string empty_state, int max_entries) {
    std::lock_guard<std::mutex> guard(model_.lock());
    model_.ensure_running();
    auto component = std::make_unique<Log>(
        model_, model_.next_component_id("log"), std::move(entries),
        std::move(empty_state), max_entries);
    auto* result = component.get();
    components_.push_back(std::move(component));
    result->added_locked(id_);
    return result;
}
CustomComponent* Card::add_custom_component(const std::string& type, Json data,
                                            std::string id) {
    std::lock_guard<std::mutex> guard(model_.lock());
    model_.ensure_running();
    if (id.empty()) id = model_.next_component_id("component");
    auto component = std::make_unique<CustomComponent>(model_, std::move(id),
                                                       type, std::move(data));
    auto* result = component.get();
    components_.push_back(std::move(component));
    result->added_locked(id_);
    return result;
}
Json Card::to_json_locked() const {
    Json components = Json::array();
    for (const auto& component : components_)
        components.push_back(component->to_json_locked());
    return Json{{"id", id_},
                {"title", title_},
                {"area", to_string(area_)},
                {"span", span_},
                {"components", std::move(components)}};
}

}  // namespace rti::demo::ui
