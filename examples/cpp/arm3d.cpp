// Application-owned arm3d pilot with deterministic mock joint targets.
#include <cmath>
#include <filesystem>
#include <rti_demo_ui/gui_sdk.hpp>

#include "console_control.hpp"

int main() {
    using namespace rti::demo::ui;
    rti_demo_ui_examples::ConsoleControl control;
    DemoUiApp app("Surgical Arm", 0, "127.0.0.1",
                  std::filesystem::path(RTI_DEMO_ARM3D_ROOT));
    Json camera = {{"mode", "orbit"},
                   {"position", {4.0, 4.45, 5.0}},
                   {"target", {0.0, 1.45, 0.0}},
                   {"min_distance", 0.1},
                   {"max_distance", 1000.0}};
    auto* scene = app.add_card("Arm monitor")
                      ->add_scene_3d("/models/scene3d-fixture.glb", camera);
    const char* paths[] = {"Arm/Base", "Arm/Shoulder", "Arm/Elbow", "Arm/Wrist",
                           "Arm/Tool"};
    for (int index = 0; index < 5; ++index)
        scene->add_node("joint-" + std::to_string(index), paths[index],
                        std::vector<double>{0.0, 0.25 + index * 0.6, 0.0});
    double cycle = 0.0;
    control.start([&app]() { app.stop(); });
    app.add_timer(200, [&scene, &cycle]() {
        for (int index = 0; index < 5; ++index) {
            const double angle = std::sin(cycle * 0.12 + index * 0.7) * 0.25;
            scene->update_node(
                "joint-" + std::to_string(index), std::nullopt,
                std::vector<double>{0.0, std::sin(angle / 2.0), 0.0,
                                    std::cos(angle / 2.0)},
                std::nullopt, std::nullopt,
                std::abs(angle) > 0.2
                    ? std::optional<Severity>(Severity::warning)
                    : std::optional<Severity>(Severity::success));
        }
        cycle += 1.0;
    });
    app.run();
    control.finish();
    return 0;
}
