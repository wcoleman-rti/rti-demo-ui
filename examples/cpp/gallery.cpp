// Gallery example: serves an application-owned static root.
#include <filesystem>
#include <iostream>
#include <rti_demo_ui/gui_sdk.hpp>

#include "console_control.hpp"

int main() {
    rti_demo_ui_examples::ConsoleControl control;
    rti::demo::ui::DemoUiApp app("Gallery", 0, "127.0.0.1",
                                 std::filesystem::path(RTI_DEMO_GALLERY_ROOT));
    control.start([&app]() { app.stop(); });
    app.run();
    control.finish();
    return 0;
}
