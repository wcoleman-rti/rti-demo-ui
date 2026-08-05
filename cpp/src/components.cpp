// Implements Card and Scene2DViewport (see docs/architecture.md
// §7.2-§7.4).
#include "rti_demo_gui_sdk/components.hpp"

#include <algorithm>
#include <sstream>

#include "rti_demo_gui_sdk/app.hpp"

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

}  // namespace

Scene2DViewport::Scene2DViewport(detail::Model& model, std::string id,
                                 int width, int height, GridBounds bounds)
    : model_(model),
      id_(std::move(id)),
      width_(width),
      height_(height),
      bounds_(bounds) {}

Scene2DViewport::Entity* Scene2DViewport::find_entity(const std::string& id) {
    for (auto& entity : entities_) {
        if (entity.id == id) return &entity;
    }
    return nullptr;
}

void Scene2DViewport::add_entity(const std::string& id, double x, double y,
                                 double heading, std::string color,
                                 Severity status, Freshness freshness) {
    static const std::string prefix = "Scene2DViewport: ";
    detail::require_non_empty(id, "id", prefix);
    detail::require_finite(x, "x", prefix);
    detail::require_finite(y, "y", prefix);
    detail::require_finite(heading, "heading", prefix);
    detail::require_valid_color(color, prefix);

    std::lock_guard<std::mutex> guard(model_.lock());
    model_.ensure_running();
    if (find_entity(id) != nullptr) {
        throw std::invalid_argument(prefix + "entity '" + id +
                                    "' already exists");
    }
    entities_.push_back(
        Entity{id, x, y, heading, std::move(color), status, freshness});
    model_.bump_revision_locked();
}

void Scene2DViewport::update_entity(const std::string& id,
                                    std::optional<double> x,
                                    std::optional<double> y,
                                    std::optional<double> heading,
                                    std::optional<Severity> status,
                                    std::optional<Freshness> freshness) {
    static const std::string prefix = "Scene2DViewport: ";
    if (x) detail::require_finite(*x, "x", prefix);
    if (y) detail::require_finite(*y, "y", prefix);
    if (heading) detail::require_finite(*heading, "heading", prefix);

    std::lock_guard<std::mutex> guard(model_.lock());
    model_.ensure_running();
    Entity* entity = find_entity(id);
    if (entity == nullptr) {
        throw std::invalid_argument(prefix + "entity '" + id +
                                    "' does not exist");
    }
    if (x) entity->x = *x;
    if (y) entity->y = *y;
    if (heading) entity->heading = *heading;
    if (status) entity->status = *status;
    if (freshness) entity->freshness = *freshness;
    model_.bump_revision_locked();
}

void Scene2DViewport::remove_entity(const std::string& id) {
    static const std::string prefix = "Scene2DViewport: ";
    std::lock_guard<std::mutex> guard(model_.lock());
    model_.ensure_running();
    auto it =
        std::find_if(entities_.begin(), entities_.end(),
                     [&](const Entity& entity) { return entity.id == id; });
    if (it == entities_.end()) {
        throw std::invalid_argument(prefix + "entity '" + id +
                                    "' does not exist");
    }
    entities_.erase(it);
    links_.erase(std::remove_if(links_.begin(), links_.end(),
                                [&](const Link& link) {
                                    return link.source_id == id ||
                                           link.target_id == id;
                                }),
                 links_.end());
    model_.bump_revision_locked();
}

void Scene2DViewport::add_link(const std::string& source_id,
                               const std::string& target_id, Severity status) {
    static const std::string prefix = "Scene2DViewport: ";
    std::lock_guard<std::mutex> guard(model_.lock());
    model_.ensure_running();
    if (find_entity(source_id) == nullptr) {
        throw std::invalid_argument(prefix + "link source '" + source_id +
                                    "' does not exist");
    }
    if (find_entity(target_id) == nullptr) {
        throw std::invalid_argument(prefix + "link target '" + target_id +
                                    "' does not exist");
    }
    for (const auto& link : links_) {
        if (link.source_id == source_id && link.target_id == target_id) {
            throw std::invalid_argument(prefix + "link (" + source_id + " -> " +
                                        target_id + ") already exists");
        }
    }
    links_.push_back(Link{source_id, target_id, status});
    model_.bump_revision_locked();
}

void Scene2DViewport::remove_link(const std::string& source_id,
                                  const std::string& target_id) {
    static const std::string prefix = "Scene2DViewport: ";
    std::lock_guard<std::mutex> guard(model_.lock());
    model_.ensure_running();
    auto it = std::find_if(links_.begin(), links_.end(), [&](const Link& link) {
        return link.source_id == source_id && link.target_id == target_id;
    });
    if (it == links_.end()) {
        throw std::invalid_argument(prefix + "link (" + source_id + " -> " +
                                    target_id + ") does not exist");
    }
    links_.erase(it);
    model_.bump_revision_locked();
}

std::string Scene2DViewport::to_json_locked() const {
    std::ostringstream out;
    out << "{\"type\":\"scene2d\",\"id\":\"" << json_escape(id_)
        << "\",\"width\":" << width_ << ",\"height\":" << height_
        << ",\"grid_bounds\":[" << bounds_[0] << "," << bounds_[1] << ","
        << bounds_[2] << "," << bounds_[3] << "],\"entities\":[";
    for (size_t i = 0; i < entities_.size(); ++i) {
        const auto& entity = entities_[i];
        if (i > 0) out << ",";
        out << "{\"id\":\"" << json_escape(entity.id) << "\",\"x\":" << entity.x
            << ",\"y\":" << entity.y << ",\"heading\":" << entity.heading
            << ",\"color\":\"" << json_escape(entity.color)
            << "\",\"status\":\"" << to_string(entity.status)
            << "\",\"freshness\":\"" << to_string(entity.freshness) << "\"}";
    }
    out << "],\"links\":[";
    for (size_t i = 0; i < links_.size(); ++i) {
        const auto& link = links_[i];
        if (i > 0) out << ",";
        out << "{\"source_id\":\"" << json_escape(link.source_id)
            << "\",\"target_id\":\"" << json_escape(link.target_id)
            << "\",\"status\":\"" << to_string(link.status) << "\"}";
    }
    out << "]}";
    return out.str();
}

Card::Card(detail::Model& model, std::string id, std::string title)
    : model_(model), id_(std::move(id)), title_(std::move(title)) {
    detail::require_non_empty(title_, "title", "Card: ");
}

Scene2DViewport* Card::add_scene_2d(int width, int height, GridBounds bounds) {
    static const std::string prefix = "Scene2DViewport: ";
    detail::require_positive(width, "width", prefix);
    detail::require_positive(height, "height", prefix);
    detail::require_valid_bounds(bounds, prefix);

    std::lock_guard<std::mutex> guard(model_.lock());
    model_.ensure_running();
    auto scene_id = model_.next_scene_id();
    auto scene = std::make_unique<Scene2DViewport>(model_, scene_id, width,
                                                   height, bounds);
    Scene2DViewport* scene_ptr = scene.get();
    components_.push_back(std::move(scene));
    model_.bump_revision_locked();
    return scene_ptr;
}

std::string Card::to_json_locked() const {
    std::ostringstream out;
    out << "{\"id\":\"" << json_escape(id_) << "\",\"title\":\""
        << json_escape(title_) << "\",\"components\":[";
    for (size_t i = 0; i < components_.size(); ++i) {
        if (i > 0) out << ",";
        out << components_[i]->to_json_locked();
    }
    out << "]}";
    return out.str();
}

}  // namespace rti_demo_gui_sdk
