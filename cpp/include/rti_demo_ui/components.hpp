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

/**
 * Base handle for a component owned by a Card.
 *
 * Handles are owned by DemoUiApp and remain valid until the app is destroyed.
 * Public component mutations are thread-safe and fail after the app is stopped.
 */
class Component {
   public:
    /** @cond INTERNAL */
    Component(detail::Model& model, std::string id, std::string type);
    virtual ~Component() = default;
    virtual Json to_json_locked() const = 0;
    void added_locked(const std::string& card_id);
    /** @endcond */

    /// Return the stable component identifier.
    const std::string& id() const { return id_; }

    /// Return the component type serialized to the browser.
    const std::string& type() const { return type_; }

   protected:
    void mutated_locked();
    detail::Model& model_;
    std::string id_;
    std::string type_;
    std::string card_id_;
    long revision_ = 0;
};

/**
 * A two-dimensional scene containing entities and directed links.
 *
 * Coordinates and headings must be finite. Entity IDs are unique among current
 * entities; removing an entity also removes links connected to it.
 */
class Scene2DViewport final : public Component {
   public:
    /** @cond INTERNAL */
    Scene2DViewport(detail::Model& model, std::string id, int width, int height,
                    GridBounds bounds);
    /** @endcond */

    /**
     * Add an entity to the scene.
     * @param id Non-empty identifier unique within this scene.
     * @param x Horizontal coordinate.
     * @param y Vertical coordinate.
     * @param heading Heading in degrees.
     * @param color A `#RRGGBB` value or `var(--name)` CSS variable.
     * @param status Semantic status.
     * @param freshness Data age indication.
     * @throws std::invalid_argument if a value is invalid or the ID exists.
     * @throws std::runtime_error if the app is stopped.
     */
    void add_entity(const std::string& id, double x, double y,
                    double heading = 0.0,
                    std::string color = "var(--sdk-accent)",
                    Severity status = Severity::success,
                    Freshness freshness = Freshness::fresh);

    /**
     * Update selected fields of an existing entity.
     * @param id Existing entity identifier.
     * @param x Optional replacement horizontal coordinate.
     * @param y Optional replacement vertical coordinate.
     * @param heading Optional replacement heading in degrees.
     * @param status Optional replacement semantic status.
     * @param freshness Optional replacement data age indication.
     * @throws std::invalid_argument if the entity is absent or a coordinate is
     * invalid.
     * @throws std::runtime_error if the app is stopped.
     */
    void update_entity(const std::string& id,
                       std::optional<double> x = std::nullopt,
                       std::optional<double> y = std::nullopt,
                       std::optional<double> heading = std::nullopt,
                       std::optional<Severity> status = std::nullopt,
                       std::optional<Freshness> freshness = std::nullopt);

    /**
     * Remove an entity and all of its links.
     * @throws std::invalid_argument if the entity is absent.
     * @throws std::runtime_error if the app is stopped.
     */
    void remove_entity(const std::string& id);

    /**
     * Add a directed link between existing entities.
     * @param source_id Existing source entity.
     * @param target_id Existing target entity.
     * @param status Initial link status.
     * @throws std::invalid_argument if either entity is absent or the directed
     * link already exists.
     * @throws std::runtime_error if the app is stopped.
     */
    void add_link(const std::string& source_id, const std::string& target_id,
                  Severity status = Severity::success);

    /**
     * Remove a directed link.
     * @throws std::invalid_argument if the link is absent.
     * @throws std::runtime_error if the app is stopped.
     */
    void remove_link(const std::string& source_id,
                     const std::string& target_id);

    /** @cond INTERNAL */
    Json to_json_locked() const override;
    /** @endcond */

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

/**
 * A glTF scene whose imported nodes can be transformed by stable IDs.
 *
 * Transforms use glTF right-handed, Y-up meter coordinates. Positions and
 * scales are three-element vectors; rotations are unit quaternions in
 * `[x, y, z, w]` order. Removed node IDs cannot be reused.
 */
class Scene3DViewport final : public Component {
   public:
    /** @cond INTERNAL */
    Scene3DViewport(detail::Model& model, std::string id, std::string asset,
                    Json camera = Json::object(),
                    std::string background = "#0a0e17", bool grid = false);
    /** @endcond */

    /**
     * Add an imported node binding and its initial local transform.
     * @param id Non-empty identifier never previously used in this scene.
     * @param path Imported glTF node path.
     * @param position Local `[x, y, z]` position.
     * @param rotation Local unit quaternion in `[x, y, z, w]` order.
     * @param scale Positive local `[x, y, z]` scale.
     * @param visible Initial visibility.
     * @param status Initial semantic status.
     * @throws std::invalid_argument if the ID or path is invalid, the ID was
     * used previously, or a transform is invalid.
     * @throws std::runtime_error if the app is stopped.
     */
    void add_node(const std::string& id, const std::string& path,
                  std::vector<double> position = {0.0, 0.0, 0.0},
                  std::vector<double> rotation = {0.0, 0.0, 0.0, 1.0},
                  std::vector<double> scale = {1.0, 1.0, 1.0},
                  bool visible = true, Severity status = Severity::success);

    /**
     * Update selected local-transform fields of an existing node.
     * @param id Existing node identifier.
     * @param position Optional local `[x, y, z]` position.
     * @param rotation Optional unit quaternion in `[x, y, z, w]` order.
     * @param scale Optional positive local `[x, y, z]` scale.
     * @param visible Optional visibility.
     * @param status Optional semantic status.
     * @throws std::invalid_argument if the node is absent or a transform is
     * invalid.
     * @throws std::runtime_error if the app is stopped.
     */
    void update_node(const std::string& id,
                     std::optional<std::vector<double>> position = std::nullopt,
                     std::optional<std::vector<double>> rotation = std::nullopt,
                     std::optional<std::vector<double>> scale = std::nullopt,
                     std::optional<bool> visible = std::nullopt,
                     std::optional<Severity> status = std::nullopt);

    /**
     * Remove a node while reserving its ID for the scene lifetime.
     * @throws std::invalid_argument if the node is absent.
     * @throws std::runtime_error if the app is stopped.
     */
    void remove_node(const std::string& id);

    /**
     * Atomically apply 1 to 1000 JSON `add`, `update`, or `remove` operations.
     *
     * Validation occurs against a copy; any failure leaves nodes and revisions
     * unchanged. A valid no-op does not increment the revision.
     *
     * @throws std::invalid_argument if the batch or an operation is invalid.
     * @throws std::runtime_error if the app is stopped.
     */
    void apply_node_batch(const Json& operations);

    /// @copydoc apply_node_batch(const Json&)
    void apply_node_batch(const std::vector<Json>& operations);

    /**
     * Atomically replace the asset, camera, background, and grid configuration.
     *
     * `asset` must be an absolute same-origin `.glb` path outside `/sdk/`. When
     * a custom static root is configured, the resolved asset must be a regular
     * file beneath that root. The camera supports orbit mode.
     *
     * @param asset Scene asset path.
     * @param camera Complete or partial orbit-camera configuration.
     * @param background A `#RRGGBB` background color.
     * @param grid Whether to show the ground grid.
     * @throws std::invalid_argument if any configuration value is invalid.
     * @throws std::runtime_error if the app is stopped.
     */
    void set_config(const std::string& asset, Json camera = Json::object(),
                    std::string background = "#0a0e17", bool grid = false);

    /** @cond INTERNAL */
    Json to_json_locked() const override;
    /** @endcond */

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

/**
 * Tabular state with declared columns and rows keyed by stable string IDs.
 *
 * Columns are objects with non-empty unique `id` and `label` strings. Rows are
 * objects with a non-empty unique `id` and a `cells` object whose keys refer to
 * declared columns.
 */
class Table final : public Component {
   public:
    /** @cond INTERNAL */
    Table(detail::Model& model, std::string id, Json columns, Json rows,
          std::string empty_state);
    /** @endcond */

    /**
     * Replace all rows after validating the complete collection.
     * @throws std::invalid_argument if the rows violate the table schema.
     * @throws std::runtime_error if the app is stopped.
     */
    void set_rows(Json rows);

    /**
     * Insert or replace one row by ID.
     * @throws std::invalid_argument if the row violates the table schema.
     * @throws std::runtime_error if the app is stopped.
     */
    void upsert_row(Json row);

    /**
     * Remove a row by ID.
     * @throws std::invalid_argument if the row is absent.
     * @throws std::runtime_error if the app is stopped.
     */
    void remove_row(const std::string& id);

    /** @cond INTERNAL */
    Json to_json_locked() const override;
    /** @endcond */

   private:
    Json columns_;
    Json rows_;
    std::string empty_state_;
};

/// A labeled JSON value with optional semantic severity.
class Metric final : public Component {
   public:
    /** @cond INTERNAL */
    Metric(detail::Model& model, std::string id, std::string label, Json value,
           std::optional<Severity> severity);
    /** @endcond */

    /**
     * Replace the value and optional severity.
     * @throws std::invalid_argument if `value` is not JSON-compatible.
     * @throws std::runtime_error if the app is stopped.
     */
    void set_value(Json value, std::optional<Severity> severity = std::nullopt);

    /** @cond INTERNAL */
    Json to_json_locked() const override;
    /** @endcond */

   private:
    std::string label_;
    Json value_;
    std::optional<Severity> severity_;
};

/// A non-empty text value with optional semantic severity.
class Text : public Component {
   public:
    /** @cond INTERNAL */
    Text(detail::Model& model, std::string id, std::string text,
         std::optional<Severity> severity);
    /** @endcond */

    /**
     * Replace the text and optional severity.
     * @throws std::invalid_argument if `text` is empty.
     * @throws std::runtime_error if the app is stopped.
     */
    void set_text(std::string text,
                  std::optional<Severity> severity = std::nullopt);

    /** @cond INTERNAL */
    Json to_json_locked() const override;
    /** @endcond */

   protected:
    std::string text_;
    std::optional<Severity> severity_;
};

/// A compact text status initialized with a semantic severity.
class Badge final : public Text {
   public:
    /** @cond INTERNAL */
    Badge(detail::Model& model, std::string id, std::string text,
          Severity severity);
    /** @endcond */
};

/**
 * A bounded insertion-order list of application-defined log entries.
 *
 * Each entry has unique non-empty `id` and `timestamp` strings plus a string
 * `message`. Appending beyond `max_entries` discards the oldest entries.
 */
class Log final : public Component {
   public:
    /** @cond INTERNAL */
    Log(detail::Model& model, std::string id, Json entries,
        std::string empty_state, int max_entries);
    /** @endcond */

    /**
     * Append one entry and enforce the configured entry limit.
     * @throws std::invalid_argument if the entry is invalid or its ID exists.
     * @throws std::runtime_error if the app is stopped.
     */
    void append(Json entry);

    /// Remove all entries. @throws std::runtime_error if the app is stopped.
    void clear();

    /** @cond INTERNAL */
    Json to_json_locked() const override;
    /** @endcond */

   private:
    Json entries_;
    std::string empty_state_;
    int max_entries_;
};

/**
 * Opaque JSON state rendered by an application-owned frontend component.
 *
 * The type must not be `scene2d`, `table`, `metric`, `text`, `badge`, or `log`.
 */
class CustomComponent final : public Component {
   public:
    /** @cond INTERNAL */
    CustomComponent(detail::Model& model, std::string id, std::string type,
                    Json data);
    /** @endcond */

    /**
     * Replace the complete component data value.
     * @throws std::invalid_argument if `data` is not JSON-compatible.
     * @throws std::runtime_error if the app is stopped.
     */
    void set_data(Json data);

    /**
     * Replace a nested value at `path`.
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

    /** @cond INTERNAL */
    Json to_json_locked() const override;
    /** @endcond */

   private:
    Json data_;
};

/**
 * A titled presentation container owned by DemoUiApp.
 *
 * Component factory return values are non-owning pointers that remain valid
 * until the app is destroyed. A card span is an integer from 1 through 3. At
 * most one card may occupy the sidebar.
 */
class Card {
   public:
    /** @cond INTERNAL */
    Card(detail::Model& model, std::string id, std::string title,
         CardArea area = CardArea::main, int span = 1);
    /** @endcond */

    /**
     * Move the card to a presentation area.
     * @throws std::invalid_argument if the sidebar constraints would be broken.
     * @throws std::runtime_error if the app is stopped.
     */
    void set_area(CardArea area);

    /**
     * Set the card span from 1 through 3.
     * @throws std::invalid_argument if `span` is outside the supported range.
     * @throws std::runtime_error if the app is stopped.
     */
    void set_span(int span);

    /**
     * Add a 2D scene.
     * @param width Viewport width in pixels; must be positive.
     * @param height Viewport height in pixels; must be positive.
     * @param bounds `{x_min, x_max, y_min, y_max}` with increasing finite axes.
     * @return A non-owning handle owned by this card.
     * @throws std::invalid_argument if dimensions or bounds are invalid.
     * @throws std::runtime_error if the app is stopped.
     */
    Scene2DViewport* add_scene_2d(int width, int height, GridBounds bounds);

    /**
     * Add a 3D scene.
     * @return A non-owning handle owned by this card.
     * @throws std::invalid_argument if its asset or configuration is invalid.
     * @throws std::runtime_error if the app is stopped.
     */
    Scene3DViewport* add_scene_3d(const std::string& asset,
                                  Json camera = Json::object(),
                                  std::string background = "#0a0e17",
                                  bool grid = false);

    /**
     * Add a validated table and return its non-owning handle.
     * @param columns Non-empty column-definition array.
     * @param rows Initial row array.
     * @param empty_state Text shown when no rows exist.
     * @throws std::invalid_argument if columns or rows are invalid.
     * @throws std::runtime_error if the app is stopped.
     */
    Table* add_table(Json columns, Json rows, std::string empty_state = "");

    /**
     * Add a metric and return its non-owning handle.
     * @param label Non-empty display label.
     * @param value JSON-compatible initial value.
     * @param severity Optional initial severity.
     * @throws std::invalid_argument if the label or value is invalid.
     * @throws std::runtime_error if the app is stopped.
     */
    Metric* add_metric(const std::string& label, Json value,
                       std::optional<Severity> severity = std::nullopt);

    /**
     * Add text and return its non-owning handle.
     * @throws std::invalid_argument if `text` is empty.
     * @throws std::runtime_error if the app is stopped.
     */
    Text* add_text(const std::string& text,
                   std::optional<Severity> severity = std::nullopt);

    /**
     * Add a badge and return its non-owning handle.
     * @throws std::invalid_argument if `text` is empty.
     * @throws std::runtime_error if the app is stopped.
     */
    Badge* add_badge(const std::string& text,
                     Severity severity = Severity::success);

    /**
     * Add a bounded log and return its non-owning handle.
     * @param entries Initial entry array; oldest excess entries are discarded.
     * @param empty_state Text shown when no entries exist.
     * @param max_entries Positive retained-entry limit.
     * @throws std::invalid_argument if entries or the limit are invalid.
     * @throws std::runtime_error if the app is stopped.
     */
    Log* add_log(Json entries, std::string empty_state = "",
                 int max_entries = 100);

    /**
     * Add opaque custom component data.
     * @param type Non-empty application-defined renderer type.
     * @param data JSON-compatible initial component data.
     * @param id Optional caller-defined ID; an empty value allocates one.
     * @return A non-owning handle owned by this card.
     * @throws std::invalid_argument if the ID, type, or data is invalid.
     * @throws std::runtime_error if the app is stopped.
     */
    CustomComponent* add_custom_component(const std::string& type, Json data,
                                          std::string id = "");

    /** @cond INTERNAL */
    Json to_json_locked() const;
    /** @endcond */

    /// Return the stable card identifier.
    const std::string& id() const { return id_; }

    /// Return the current presentation area.
    CardArea area() const { return area_; }

   private:
    friend class detail::Model;
    detail::Model& model_;
    std::string id_;
    std::string title_;
    CardArea area_;
    int span_;
    std::vector<std::unique_ptr<Component>> components_;
};

}  // namespace rti::demo::ui
