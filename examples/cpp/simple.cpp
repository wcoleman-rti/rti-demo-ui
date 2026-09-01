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

// No Connext/DDS dependency — DemoUiApp, Card, Scene2DViewport, one synthetic
// timer (see docs/architecture.md, Runtime Flow and Ownership).
#include <cmath>
#include <rti_demo_ui/rti_demo_ui.hpp>

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
