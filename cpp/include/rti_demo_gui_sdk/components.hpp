// Pre-built C++ widgets, Card and Scene2DViewport (see
// docs/architecture.md §7.2-§7.4).
#pragma once

#include <map>
#include <memory>
#include <optional>
#include <string>
#include <vector>

#include "rti_demo_gui_sdk/types.hpp"

namespace rti_demo_gui_sdk {

namespace detail {
class Model;
}  // namespace detail

class Scene2DViewport {
   public:
    Scene2DViewport(detail::Model& model, std::string id, int width, int height,
                    GridBounds bounds);

    void add_entity(const std::string& id, double x, double y,
                    double heading = 0.0,
                    std::string color = "var(--sdk-accent)",
                    Severity status = Severity::success,
                    Freshness freshness = Freshness::fresh);
    void update_entity(const std::string& id,
                       std::optional<double> x = std::nullopt,
                       std::optional<double> y = std::nullopt,
                       std::optional<double> heading = std::nullopt,
                       std::optional<Severity> status = std::nullopt,
                       std::optional<Freshness> freshness = std::nullopt);
    void remove_entity(const std::string& id);
    void add_link(const std::string& source_id, const std::string& target_id,
                  Severity status = Severity::success);
    void remove_link(const std::string& source_id,
                     const std::string& target_id);

    // Not thread-safe; caller must hold the model lock.
    std::string to_json_locked() const;

    const std::string& id() const { return id_; }

   private:
    struct Entity {
        std::string id;
        double x;
        double y;
        double heading;
        std::string color;
        Severity status;
        Freshness freshness;
    };
    struct Link {
        std::string source_id;
        std::string target_id;
        Severity status;
    };

    detail::Model& model_;
    std::string id_;
    int width_;
    int height_;
    GridBounds bounds_;
    std::vector<Entity> entities_;
    std::vector<Link> links_;

    Entity* find_entity(const std::string& id);
};

class Card {
   public:
    Card(detail::Model& model, std::string id, std::string title);

    Scene2DViewport* add_scene_2d(int width, int height, GridBounds bounds);

    // Not thread-safe; caller must hold the model lock.
    std::string to_json_locked() const;

    const std::string& id() const { return id_; }

   private:
    detail::Model& model_;
    std::string id_;
    std::string title_;
    std::vector<std::unique_ptr<Scene2DViewport>> components_;
};

}  // namespace rti_demo_gui_sdk
