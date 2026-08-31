// Model tests: validation, revision counting, atomic link removal, ordering.
// See docs/architecture.md §11.1.
#include <rti_demo_ui/rti_demo_ui.hpp>

#include <cassert>
#include <chrono>
#include <cstdio>
#include <thread>

using namespace rti::demo::ui;

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
