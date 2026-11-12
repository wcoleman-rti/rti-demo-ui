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
#pragma once

#include "rti_demo_ui/demo_ui_app.hpp"

namespace rti::demo::ui {

/// Enable the bundled local uPlot renderer before adding time-series charts.
void enable_uplot(DemoUiApp& app);

}  // namespace rti::demo::ui
