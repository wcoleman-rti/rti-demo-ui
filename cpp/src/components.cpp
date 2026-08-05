#include "rti_demo_ui/components.hpp"

#include <algorithm>
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
    model_.bump_revision_locked();
    revision_ = model_.revision_;
}

void Component::added_locked() { mutated_locked(); }

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

Card::Card(detail::Model& model, std::string id, std::string title)
    : model_(model), id_(std::move(id)), title_(std::move(title)) {
    detail::require_non_empty(title_, "title", "Card: ");
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
    result->added_locked();
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
    result->added_locked();
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
    result->added_locked();
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
    result->added_locked();
    return result;
}
Badge* Card::add_badge(const std::string& text, Severity severity) {
    std::lock_guard<std::mutex> guard(model_.lock());
    model_.ensure_running();
    auto component = std::make_unique<Badge>(
        model_, model_.next_component_id("badge"), text, severity);
    auto* result = component.get();
    components_.push_back(std::move(component));
    result->added_locked();
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
    result->added_locked();
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
    result->added_locked();
    return result;
}
Json Card::to_json_locked() const {
    Json components = Json::array();
    for (const auto& component : components_)
        components.push_back(component->to_json_locked());
    return Json{
        {"id", id_}, {"title", title_}, {"components", std::move(components)}};
}

}  // namespace rti::demo::ui
