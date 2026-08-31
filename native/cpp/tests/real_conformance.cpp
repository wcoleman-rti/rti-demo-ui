#include <rti_demo_ui_native/native_webview.hpp>

#include <chrono>
#include <condition_variable>
#include <exception>
#include <iostream>
#include <mutex>
#include <set>
#include <string>
#include <thread>

namespace {

using rti::demo::ui::CommandSchema;
using rti::demo::ui::DemoUiApp;
using rti::demo::ui::Json;

const std::set<std::string> expected_checks{
    "snapshot",          "sse",             "dynamic_import",
    "runtime3d_import",  "module_worker",   "theme_asset",
    "persistent_storage", "canvas",          "webgl",
    "keyboard_focus",    "resize_observation", "navigation_policy",
    "command_origin",
};

}  // namespace

int main(int argc, char** argv) {
    if (argc != 3) {
        std::cerr << "usage: real_conformance STORAGE_EXPECTED STORAGE_WRITE\n";
        return 2;
    }

    DemoUiApp app("Native Phase 2 conformance", 0, "127.0.0.1",
                  NATIVE_CONFORMANCE_STATIC_ROOT);
    app.set_data(Json{{"native_storage_key", "phase2-production"},
                      {"native_storage_expected", argv[1]},
                      {"native_storage_write", argv[2]}});

    std::mutex mutex;
    std::condition_variable report_cv;
    Json report;
    bool report_received = false;
    app.register_command(
        "spike-report", CommandSchema(Json{{"type", "object"}}),
        [&](const Json& payload) {
            {
                std::lock_guard<std::mutex> guard(mutex);
                report = payload;
                report_received = true;
            }
            report_cv.notify_all();
            return Json{{"recorded", true}};
        });
    app.register_command(
        "spike-origin", CommandSchema(Json{{"type", "object"}}),
        [](const Json& payload) { return Json{{"origin", payload["origin"]}}; });

    std::thread closer([&]() {
        std::unique_lock<std::mutex> lock(mutex);
        report_cv.wait_for(lock, std::chrono::seconds(20),
                           [&]() { return report_received; });
        lock.unlock();
        app.stop();
    });

    try {
        rti::demo::ui::native::run(app);
    } catch (const std::exception& error) {
        app.stop();
        closer.join();
        std::cerr << error.what() << '\n';
        return 1;
    }
    closer.join();

    if (!report_received || !report.contains("results")) {
        std::cerr << "production conformance report timed out\n";
        return 1;
    }
    const auto& results = report["results"];
    for (const auto& name : expected_checks) {
        if (!results.contains(name) || !results[name].value("passed", false)) {
            std::cerr << "failed conformance check: " << name << '\n';
            return 1;
        }
    }
    std::cout << report.dump() << '\n';
    return 0;
}
