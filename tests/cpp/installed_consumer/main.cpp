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

#include <rti_demo_ui/rti_demo_ui.hpp>

#ifdef RTI_DEMO_TEST_UPLOT
#include <rti_demo_ui/uplot.hpp>
#endif

int main() {
    rti::demo::ui::DemoUiApp app("Installed package consumer");
#ifdef RTI_DEMO_TEST_UPLOT
    rti::demo::ui::enable_uplot(app);
    app.add_card("Trends")->add_time_series(
        "Rate", {{"rate", "Rate"}});
#endif
    app.add_card("Status")->add_metric("Ready", 1);
    return 0;
}
