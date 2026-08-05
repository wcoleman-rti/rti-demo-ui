// No Connext/DDS dependency — DemoUiApp, Card, Scene2DViewport, one synthetic
// timer (see docs/architecture.md §10.1).
#include <cmath>
#include <rti_demo_ui/gui_sdk.hpp>

#include "console_control.hpp"

int main() {
    using namespace rti::demo::ui;

    rti_demo_ui_examples::ConsoleControl control;
    DemoUiApp app("Simple Demo");
    control.start([&app]() { app.stop(); });
    Card* card = app.add_card("Fleet Telemetry");
    Scene2DViewport* scene =
        card->add_scene_2d(600, 400, {-100.0, 100.0, -100.0, 100.0});
    scene->add_entity("vehicle-1", 0.0, 0.0, 0.0);
    scene->add_entity("vehicle-2", 50.0, 50.0, 180.0);
    scene->add_link("vehicle-1", "vehicle-2");

    auto angle = std::make_shared<double>(0.0);
    app.add_timer(100, [scene, angle]() {
        *angle += 0.05;
        scene->update_entity("vehicle-1", 40.0 * std::cos(*angle),
                             40.0 * std::sin(*angle), (*angle) * 180.0 / M_PI);
    });

    app.run();
    control.finish();
    return 0;
}
