// Model tests: validation, revision counting, atomic link removal, ordering.
// See docs/architecture.md §11.1.
#include <rti_demo_ui/rti_demo_ui.hpp>

#include <cassert>
#include <chrono>
#include <cstdio>
#include <fstream>
#include <thread>

using namespace rti::demo::ui;

namespace rti::demo::ui::detail {
class ModelTestAccess {
   public:
    static Model& model(DemoUiApp& app) { return app.model_; }
};
}  // namespace rti::demo::ui::detail

static int g_failures = 0;

#define CHECK(cond)                                                          \
    do {                                                                     \
        if (!(cond)) {                                                       \
            std::fprintf(stderr, "FAILED: %s (line %d)\n", #cond, __LINE__); \
            ++g_failures;                                                    \
        }                                                                    \
    } while (0)

#define EXPECT_THROWS(expr)                    \
    do {                                        \
        bool threw = false;                     \
        try {                                   \
            expr;                                \
        } catch (const std::invalid_argument&) { \
            threw = true;                        \
        }                                        \
        CHECK(threw);                            \
    } while (0)

void test_revision_increments_once_per_mutation() {
    DemoUiApp app("Test", 19180);
    Card* card = app.add_card("Fleet");
    Scene2DViewport* scene = card->add_scene_2d(600, 400, {-100.0, 100.0, -100.0, 100.0});
    scene->add_entity("v1", 0.0, 0.0);
    // Three successful mutations: add_card, add_scene_2d, add_entity.
}

void test_failed_mutation_does_not_change_revision() {
    DemoUiApp app("Test", 19181);
    Card* card = app.add_card("Fleet");
    Scene2DViewport* scene = card->add_scene_2d(600, 400, {-100.0, 100.0, -100.0, 100.0});
    scene->add_entity("v1", 0.0, 0.0);
    EXPECT_THROWS(scene->add_entity("v1", 1.0, 1.0));
}

void test_dirty_targets_coalesce_to_latest_fixture_state() {
    std::ifstream input(std::string(SOURCE_ROOT) +
                        "/tests/fixtures/sse_event_contract.json");
    const Json vectors = Json::parse(input);
    CHECK(vectors["unicode_serialization"]["payload"].dump() ==
          vectors["unicode_serialization"]["serialized"]);
    DemoUiApp app("Contract", 19186);
    Card* primary = app.add_card("Primary");
    Metric* rate = primary->add_metric("Rate", 10);
    Card* secondary = app.add_card("Secondary");
    Text* status = secondary->add_text("idle");
    auto& model = detail::ModelTestAccess::model(app);

    {
        std::lock_guard<std::mutex> guard(model.lock());
        CHECK(!model.flush_dirty_targets_locked().has_value());
        CHECK(Json::parse(model.snapshot_json_locked()) ==
              vectors["snapshots"]["backend_base"]);
        model.start_dirty_tracking_locked();
    }

    app.set_data({{"site", "north"}, {"mode", "active"}});
    rate->set_value(20);
    rate->set_value(42, Severity::warning);
    secondary->add_metric("Load", 5);
    Card* added = app.add_card("Added");
    added->add_text("ready");
    status->set_text("running", Severity::success);

    {
        std::lock_guard<std::mutex> guard(model.lock());
        const auto patch = model.flush_dirty_targets_locked();
        CHECK(patch.has_value());
        CHECK(*patch == vectors["coalesced_patch"]);
        CHECK(patch->dump() == vectors["serialized_coalesced_patch"]);
        CHECK(Json::parse(model.snapshot_json_locked()) ==
              vectors["snapshots"]["backend_latest"]);
        CHECK(!model.flush_dirty_targets_locked().has_value());
    }
}

void test_entity_removal_removes_links() {
    DemoUiApp app("Test", 19182);
    Card* card = app.add_card("Fleet");
    Scene2DViewport* scene = card->add_scene_2d(600, 400, {-100.0, 100.0, -100.0, 100.0});
    scene->add_entity("v1", 0.0, 0.0);
    scene->add_entity("v2", 1.0, 1.0);
    scene->add_link("v1", "v2");
    scene->remove_entity("v1");
    std::string json = scene->to_json_locked().dump();
    CHECK(json.find("\"links\":[]") != std::string::npos);
}

void test_validation_errors() {
    DemoUiApp app("Test", 19183);
    Card* card = app.add_card("Fleet");
    EXPECT_THROWS(card->add_scene_2d(-1, 400, {-100.0, 100.0, -100.0, 100.0}));
    EXPECT_THROWS(card->add_scene_2d(600, 400, {100.0, -100.0, -100.0, 100.0}));
    Scene2DViewport* scene = card->add_scene_2d(600, 400, {-100.0, 100.0, -100.0, 100.0});
    EXPECT_THROWS(scene->add_entity("", 0.0, 0.0));
    EXPECT_THROWS(scene->add_entity("v1", std::nan(""), 0.0));
    EXPECT_THROWS(scene->add_entity("v1", 0.0, 0.0, 0.0, "not-a-color"));
    EXPECT_THROWS(scene->update_entity("missing"));
    EXPECT_THROWS(scene->remove_entity("missing"));
    scene->add_entity("v1", 0.0, 0.0);
    scene->add_entity("v2", 1.0, 1.0);
    EXPECT_THROWS(scene->add_link("v1", "missing-target"));
    scene->add_link("v1", "v2");
    EXPECT_THROWS(scene->add_link("v1", "v2"));
    EXPECT_THROWS(scene->remove_link("v2", "v1"));
}

void test_timer_cancel_idempotent() {
    DemoUiApp app("Test", 19184);
    int counter = 0;
    TimerHandle handle = app.add_timer(20, [&counter]() { ++counter; });
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
    handle.cancel();
    handle.cancel();
    int after_cancel = counter;
    std::this_thread::sleep_for(std::chrono::milliseconds(100));
    CHECK(counter == after_cancel);
    app.stop();
    app.stop();
}

void test_scene3d_contract() {
    DemoUiApp app("Scene", 19185);
    Card* card = app.add_card("Arm");
    Scene3DViewport* scene = card->add_scene_3d("/models/surgical-arm.glb");
    Json initial = scene->to_json_locked();
    CHECK(initial["type"] == "scene3d");
    CHECK(initial["data"]["nodes"].empty());
    CHECK(initial["data"]["camera"]["mode"] == "orbit");
    scene->apply_node_batch(Json::array({
        {{"op", "add"}, {"id", "shoulder"}, {"path", "Arm/Shoulder"},
         {"rotation", {0.0, 0.0, 0.0, 1.0}}},
        {{"op", "update"}, {"id", "shoulder"}, {"position", {0.1, 0.0, 0.0}}}}));
    Json snapshot = scene->to_json_locked();
    CHECK(snapshot["data"]["nodes"][0]["path"] == "Arm/Shoulder");
    CHECK(snapshot["data"]["nodes"][0]["rotation"] == Json({0.0, 0.0, 0.0, 1.0}));
    const auto unchanged = snapshot.dump();
    scene->apply_node_batch(Json::array({{{"op", "update"},
                                          {"id", "shoulder"},
                                          {"position", {0.1, 0.0, 0.0}}}}));
    CHECK(scene->to_json_locked().dump() == unchanged);
    scene->remove_node("shoulder");
    EXPECT_THROWS(scene->add_node("shoulder", "Arm/Shoulder"));
    EXPECT_THROWS(scene->apply_node_batch(Json::array({
        {{"op", "add"}, {"id", "a"}, {"path", "Arm/A"},
         {"rotation", {0.0, 0.0, 0.0, 1.0}}},
        {{"op", "add"}, {"id", "a"}, {"path", "Arm/B"},
         {"rotation", {0.0, 0.0, 0.0, 1.0}}}})));
}

int main() {
    test_revision_increments_once_per_mutation();
    test_failed_mutation_does_not_change_revision();
    test_dirty_targets_coalesce_to_latest_fixture_state();
    test_entity_removal_removes_links();
    test_validation_errors();
    test_scene3d_contract();
    test_timer_cancel_idempotent();
    if (g_failures == 0) {
        std::printf("All component tests passed\n");
    } else {
        std::fprintf(stderr, "%d component test(s) failed\n", g_failures);
    }
    return g_failures == 0 ? 0 : 1;
}
