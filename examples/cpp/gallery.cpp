// Gallery example: serves an application-owned static root.
#include <filesystem>
#include <iostream>
#include <rti_demo_ui/rti_demo_ui.hpp>
#include <string>

#include "console_control.hpp"

namespace {

using namespace rti::demo::ui;

Theme parse_theme(const std::string& value) {
    if (value == "dark") return Theme::dark;
    if (value == "light") return Theme::light;
    throw std::invalid_argument("theme must be dark or light");
}

Layout parse_layout(const std::string& value) {
    if (value == "auto") return Layout::automatic;
    if (value == "grid-2") return Layout::grid_2;
    if (value == "grid-3") return Layout::grid_3;
    if (value == "sidebar-main") return Layout::sidebar_main;
    throw std::invalid_argument(
        "layout must be auto, grid-2, grid-3, or sidebar-main");
}

}  // namespace

int main(int argc, char** argv) {
    Theme theme = Theme::dark;
    Layout layout = Layout::automatic;
    try {
        for (int index = 1; index < argc; ++index) {
            const std::string option = argv[index];
            if (option == "--theme" && index + 1 < argc) {
                theme = parse_theme(argv[++index]);
            } else if (option == "--layout" && index + 1 < argc) {
                layout = parse_layout(argv[++index]);
            } else {
                throw std::invalid_argument("invalid arguments");
            }
        }
    } catch (const std::invalid_argument& error) {
        std::cerr << error.what()
                  << "\nUsage: rti_demo_ui_gallery "
                     "[--theme dark|light] "
                     "[--layout auto|grid-2|grid-3|sidebar-main]\n";
        return 2;
    }

    rti_demo_ui_examples::ConsoleControl control;
    DemoUiApp app("Gallery", 0, "127.0.0.1",
                  std::filesystem::path(RTI_DEMO_GALLERY_ROOT), theme, layout);
    app.add_card("Presentation", CardArea::sidebar)
        ->add_text(std::string(to_string(theme)) + " / " + to_string(layout));
    app.add_card("Telemetry", CardArea::main, 2)
        ->add_metric("Connected assets", 12);
    control.start([&app]() { app.stop(); });
    app.run();
    control.finish();
    return 0;
}
