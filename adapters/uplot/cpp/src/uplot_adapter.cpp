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
#include "rti_demo_ui/uplot.hpp"

#include "uplot_assets.hpp"

namespace rti::demo::ui {

void enable_uplot(DemoUiApp& app) {
    std::lock_guard<std::mutex> adapter_guard(app.adapter_mutex_);
    if (app.run_started_.load() || app.stopped_.load()) {
        throw std::runtime_error(
            "DemoUiApp: uPlot must be enabled before run()");
    }
    if (app.adapters_.count("uplot") != 0) {
        throw std::invalid_argument("DemoUiApp: uPlot is already enabled");
    }
    {
        std::lock_guard<std::mutex> model_guard(app.model_.lock());
        if (app.model_.has_adapter_component("timeseries")) {
            throw std::invalid_argument(
                "DemoUiApp: timeseries component type is already registered");
        }
        app.model_.register_adapter_components({"timeseries"});
    }
    const std::string root = "/sdk/adapters/uplot";
    const std::string module = root + "/runtime.js";
    app.adapters_["uplot"] = {
        {"name", "uplot"},
        {"version", "1"},
        {"components", {"timeseries"}},
        {"module", module},
        {"styles", Json::array({root + "/theme.css"})}};
    app.adapter_assets_[module] = {
        detail::embedded_uplot_runtime_js(),
        "application/javascript; charset=utf-8"};
    app.adapter_assets_[root + "/theme.css"] = {
        detail::embedded_uplot_theme_css(), "text/css; charset=utf-8"};
}

}  // namespace rti::demo::ui
