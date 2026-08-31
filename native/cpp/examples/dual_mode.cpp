#include <rti_demo_ui_native/native_webview.hpp>

#include <cmath>
#include <cstring>
#include <iostream>
#include <memory>

int main(int argc, char** argv) {
    bool native_mode = false;
    if (argc == 2 && std::strcmp(argv[1], "--native") == 0) {
        native_mode = true;
    } else if (argc != 1 && !(argc == 2 &&
                              std::strcmp(argv[1], "--browser") == 0)) {
        std::cerr << "usage: rti_demo_ui_native_dual_mode "
                     "[--browser|--native]\n";
        return 2;
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
                             40.0 * std::sin(*angle),
                             (*angle) * 180.0 / M_PI);
    });

    if (native_mode) {
        rti::demo::ui::native::run(app);
    } else {
        app.run();
    }
    return 0;
}
