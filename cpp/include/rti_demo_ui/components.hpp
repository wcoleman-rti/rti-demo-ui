// SDK-owned state components and opaque custom components.
#pragma once

#include <filesystem>
#include <memory>
#include <optional>
#include <set>
#include <string>
#include <vector>

#include "rti_demo_ui/types.hpp"

namespace rti::demo::ui {

namespace detail {
class Model;
}

class Component {
   public:
    Component(detail::Model& model, std::string id, std::string type);
    virtual ~Component() = default;
    virtual Json to_json_locked() const = 0;
    const std::string& id() const { return id_; }
    const std::string& type() const { return type_; }
    void added_locked();

   protected:
    void mutated_locked();
    detail::Model& model_;
    std::string id_;
    std::string type_;
    long revision_ = 0;
};

class Scene2DViewport final : public Component {
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
    Json to_json_locked() const override;

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
    int width_;
    int height_;
    GridBounds bounds_;
    std::vector<Entity> entities_;
    std::vector<Link> links_;
    Entity* find_entity(const std::string& id);
};

class Scene3DViewport final : public Component {
   public:
    Scene3DViewport(detail::Model& model, std::string id, std::string asset,
                    Json camera = Json::object(),
                    std::string background = "#0a0e17", bool grid = false);
    void add_node(const std::string& id, const std::string& path,
                  std::vector<double> position = {0.0, 0.0, 0.0},
                  std::vector<double> rotation = {0.0, 0.0, 0.0, 1.0},
                  std::vector<double> scale = {1.0, 1.0, 1.0},
                  bool visible = true, Severity status = Severity::success);
    void update_node(const std::string& id,
                     std::optional<std::vector<double>> position = std::nullopt,
                     std::optional<std::vector<double>> rotation = std::nullopt,
                     std::optional<std::vector<double>> scale = std::nullopt,
                     std::optional<bool> visible = std::nullopt,
                     std::optional<Severity> status = std::nullopt);
    void remove_node(const std::string& id);
    void apply_node_batch(const Json& operations);
    void apply_node_batch(const std::vector<Json>& operations);
    void set_config(const std::string& asset, Json camera = Json::object(),
                    std::string background = "#0a0e17", bool grid = false);
    Json to_json_locked() const override;

   private:
    struct Node {
        std::string id;
        std::string path;
        std::vector<double> position;
        std::vector<double> rotation;
        std::vector<double> scale;
        bool visible;
        Severity status;
    };
    std::string asset_;
    Json camera_;
    std::string background_;
    bool grid_;
    std::vector<Node> nodes_;
    std::set<std::string> used_ids_;

    static void validate_asset(const std::string& asset,
                               const std::filesystem::path& static_root);
    static std::vector<double> validate_vector(const Json& value, size_t size,
                                               const char* kind);
    static void validate_path(const Json& value);
    static Json camera_config(Json camera);
    static Node node_from_operation(const Json& operation,
                                    const Node* current = nullptr);
    static Json nodes_json(const std::vector<Node>& nodes);
    Node* find_node(std::vector<Node>& nodes, const std::string& id);
};

class Table final : public Component {
   public:
    Table(detail::Model& model, std::string id, Json columns, Json rows,
          std::string empty_state);
    void set_rows(Json rows);
    void upsert_row(Json row);
    void remove_row(const std::string& id);
    Json to_json_locked() const override;

   private:
    Json columns_;
    Json rows_;
    std::string empty_state_;
};

class Metric final : public Component {
   public:
    Metric(detail::Model& model, std::string id, std::string label, Json value,
           std::optional<Severity> severity);
    void set_value(Json value, std::optional<Severity> severity = std::nullopt);
    Json to_json_locked() const override;

   private:
    std::string label_;
    Json value_;
    std::optional<Severity> severity_;
};

class Text : public Component {
   public:
    Text(detail::Model& model, std::string id, std::string text,
         std::optional<Severity> severity);
    void set_text(std::string text,
                  std::optional<Severity> severity = std::nullopt);
    Json to_json_locked() const override;

   protected:
    std::string text_;
    std::optional<Severity> severity_;
};

class Badge final : public Text {
   public:
    Badge(detail::Model& model, std::string id, std::string text,
          Severity severity);
};

class Log final : public Component {
   public:
    Log(detail::Model& model, std::string id, Json entries,
        std::string empty_state, int max_entries);
    void append(Json entry);
    void clear();
    Json to_json_locked() const override;

   private:
    Json entries_;
    std::string empty_state_;
    int max_entries_;
};

class CustomComponent final : public Component {
   public:
    CustomComponent(detail::Model& model, std::string id, std::string type,
                    Json data);
    void set_data(Json data);
    void update_data(const std::vector<std::string>& path, Json value,
                     bool create_missing = false);
    Json to_json_locked() const override;

   private:
    Json data_;
};

class Card {
   public:
    Card(detail::Model& model, std::string id, std::string title);
    Scene2DViewport* add_scene_2d(int width, int height, GridBounds bounds);
    Scene3DViewport* add_scene_3d(const std::string& asset,
                                  Json camera = Json::object(),
                                  std::string background = "#0a0e17",
                                  bool grid = false);
    Table* add_table(Json columns, Json rows, std::string empty_state = "");
    Metric* add_metric(const std::string& label, Json value,
                       std::optional<Severity> severity = std::nullopt);
    Text* add_text(const std::string& text,
                   std::optional<Severity> severity = std::nullopt);
    Badge* add_badge(const std::string& text,
                     Severity severity = Severity::success);
    Log* add_log(Json entries, std::string empty_state = "",
                 int max_entries = 100);
    CustomComponent* add_custom_component(const std::string& type, Json data,
                                          std::string id = "");
    Json to_json_locked() const;
    const std::string& id() const { return id_; }

   private:
    detail::Model& model_;
    std::string id_;
    std::string title_;
    std::vector<std::unique_ptr<Component>> components_;
};

}  // namespace rti::demo::ui
