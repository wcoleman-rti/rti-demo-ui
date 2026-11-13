#include <cmath>
#include <cstring>
#include <iostream>
#include <memory>
#include <rti_demo_ui_native/native_webview.hpp>

int main(int argc, char** argv) {
    bool native_mode = false;
    rti::demo::ui::native::NativeWindowOptions options;
    for (int index = 1; index < argc; ++index) {
        if (std::strcmp(argv[index], "--native") == 0) {
            native_mode = true;
        } else if (std::strcmp(argv[index], "--browser") == 0) {
            native_mode = false;
        } else if (std::strcmp(argv[index], "--icon") == 0 &&
                   index + 1 < argc) {
            options.icon = argv[++index];
        } else if (std::strcmp(argv[index], "--application-id") == 0 &&
                   index + 1 < argc) {
            options.application_id = argv[++index];
        } else {
            std::cerr << "usage: rti_demo_ui_native_dual_mode "
                         "[--browser|--native] [--icon PATH] "
                         "[--application-id ID]\n";
            return 2;
        }
    }

    using namespace rti::demo::ui;
    DemoUiApp app("Native Dual-Mode Demo");
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

    if (native_mode) {
        rti::demo::ui::native::run(app, options);
    } else {
        app.run();
    }
    return 0;
}
