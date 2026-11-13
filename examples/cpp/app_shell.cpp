/*
 * (c) 2026 Copyright, Real-Time Innovations, Inc.  All rights reserved.
 *
 * RTI grants Licensee a license to use, modify, compile, and create derivative
 * works of the Software.  Licensee has the right to distribute object form
 * only for use with RTI products.  The Software is provided "as is", with no
 * warranty of any type, including any warranty for fitness for any purpose.
 * RTI is under no obligation to maintain or support the Software.  RTI shall
 * not be liable for any incidental or consequential damages arising out of
 * the use or inability to use the software.
 */

// Responsive custom frontend shell example.
#include <filesystem>
#include <memory>
#include <rti_demo_ui/rti_demo_ui.hpp>
#include <string>
#include <vector>

#include "console_control.hpp"

int main() {
    using namespace rti::demo::ui;

    rti_demo_ui_examples::ConsoleControl control;
    DemoUiApp app("Application workspace", 0, "127.0.0.1",
                  std::filesystem::path(RTI_DEMO_APP_SHELL_ROOT));

    const Json initial_activity = Json::array({Json{
        {"time", "Ready"}, {"message", "Waiting for the first update."}}});
    app.set_data({{"status", "Awaiting updates"},
                  {"sample_count", 0},
                  {"last_updated", "Waiting for first update"},
                  {"activity", initial_activity}});

    auto sample_count = std::make_shared<int>(0);
    auto activity = std::make_shared<std::vector<Json>>();
    activity->push_back(
        Json{{"time", "Ready"}, {"message", "Waiting for the first update."}});
    app.add_timer(2000, [&app, sample_count, activity]() {
        const int count = ++(*sample_count);
        const std::string sequence = "Update " + std::to_string(count);
        activity->insert(activity->begin(),
                         Json{{"time", sequence},
                              {"message", "Application data received."}});
        if (activity->size() > 5) activity->resize(5);

        app.update_data({"status"}, "Live");
        app.update_data({"sample_count"}, count);
        app.update_data({"last_updated"}, sequence);
        app.update_data({"activity"}, Json(*activity));
    });

    control.start([&app]() { app.stop(); });
    app.run();
    control.finish();
    return 0;
}
