// Model tests: validation, revision counting, atomic link removal, ordering.
// See docs/architecture.md §11.1.
#include <rti_demo_ui/gui_sdk.hpp>

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
    std::string json = scene->to_json_locked();
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

int main() {
    test_revision_increments_once_per_mutation();
    test_failed_mutation_does_not_change_revision();
    test_entity_removal_removes_links();
    test_validation_errors();
    test_timer_cancel_idempotent();
    if (g_failures == 0) {
        std::printf("All component tests passed\n");
    } else {
        std::fprintf(stderr, "%d component test(s) failed\n", g_failures);
    }
    return g_failures == 0 ? 0 : 1;
}
