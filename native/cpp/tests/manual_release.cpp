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

#include <cstring>
#include <filesystem>
#include <iostream>
#include <rti_demo_ui_native/native_webview.hpp>

int main(int argc, char** argv) {
    rti::demo::ui::native::NativeWindowOptions options;
    options.application_id = "org.rti.demo-ui.manual-release";
    for (int i = 1; i < argc; ++i) {
        if (std::strcmp(argv[i], "--icon") == 0 && i + 1 < argc) {
            options.icon = argv[++i];
        } else if (std::strcmp(argv[i], "--application-id") == 0 &&
                   i + 1 < argc) {
            options.application_id = argv[++i];
        } else {
            std::cerr << "usage: rti_demo_ui_native_manual_release "
                         "[--icon PATH] [--application-id ID]\n";
            return 2;
        }
    }

    using namespace rti::demo::ui;
    DemoUiApp app("Native release manual test", 0, "127.0.0.1",
                  std::filesystem::path(NATIVE_MANUAL_STATIC_ROOT));
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
    rti::demo::ui::native::run(app, options);
    return 0;
}
