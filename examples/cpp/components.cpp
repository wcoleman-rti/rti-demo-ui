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

// Minimal built-in dashboard component example.
#include <rti_demo_ui/rti_demo_ui.hpp>

#include "console_control.hpp"

int main() {
    using namespace rti::demo::ui;

    rti_demo_ui_examples::ConsoleControl control;
    DemoUiApp app("Components");
    Card* card = app.add_card("System status");
    card->add_metric("Temperature", 42, Severity::warning);
    card->add_badge("Connected", Severity::success);
    card->add_text("All systems responding");
    card->add_table(
        Json::array({{{"id", "name"}, {"label", "Name"}},
                     {{"id", "value"}, {"label", "Value"}}}),
        Json::array({{{"id", "motor"},
                      {"cells", {{"name", "Motor"}, {"value", "Ready"}}}}}));
    card->add_log(Json::array({{{"id", "startup"},
                                {"timestamp", "12:00:00"},
                                {"message", "Demo started"}}}));

    control.start([&app]() { app.stop(); });
    app.run();
    control.finish();
    return 0;
}
