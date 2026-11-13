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

// Minimal validated browser command example.
#include <filesystem>
#include <rti_demo_ui/rti_demo_ui.hpp>

#include "console_control.hpp"

int main() {
    using namespace rti::demo::ui;

    rti_demo_ui_examples::ConsoleControl control;
    DemoUiApp app("Commands", 0, "127.0.0.1",
                  std::filesystem::path(RTI_DEMO_COMMANDS_ROOT));
    app.register_command(
        "greet",
        CommandSchema(
            {{"type", "object"},
             {"properties", {{"name", {{"type", "string"}, {"minLength", 1}}}}},
             {"required", Json::array({"name"})},
             {"additionalProperties", false}}),
        [](const Json& payload) {
            return Json{
                {"message",
                 "Hello, " + payload.at("name").get<std::string>() + "!"}};
        });

    control.start([&app]() { app.stop(); });
    app.run();
    control.finish();
    return 0;
}
