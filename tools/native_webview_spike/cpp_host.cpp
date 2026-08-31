// Phase 0 webview host; experimental and not a public SDK API.
#include <httplib.h>
#include <webview/webview.h>

#include <chrono>
#include <condition_variable>
#include <csignal>
#include <iostream>
#include <mutex>
#include <rti_demo_ui/demo_ui_app.hpp>
#include <set>
#include <string>
#include <thread>

namespace {
volatile std::sig_atomic_t signal_requested = 0;

void on_signal(int) { signal_requested = 1; }

void validate_report(const rti::demo::ui::Json& payload) {
    using rti::demo::ui::Json;
    static const std::set<std::string> expected_checks{
        "canvas",           "command_origin", "dynamic_import",
        "keyboard_focus",   "module_worker",  "resize_observation",
        "runtime3d_import", "snapshot",       "sse",
        "theme_asset",      "webgl",
    };
    if (!payload.is_object() || payload.size() != 1 ||
        !payload.contains("results") || !payload["results"].is_object()) {
        throw std::invalid_argument(
            "conformance report must contain only an object named results");
    }
    std::set<std::string> actual_checks;
    for (const auto& item : payload["results"].items()) {
        actual_checks.insert(item.key());
        const Json& result = item.value();
        if (!result.is_object() || result.size() != 2 ||
            !result.contains("passed") || !result["passed"].is_boolean() ||
            !result.contains("evidence") || !result["evidence"].is_string() ||
            result["evidence"].get_ref<const std::string&>().empty()) {
            throw std::invalid_argument("invalid conformance result: " +
                                        item.key());
        }
    }
    if (actual_checks != expected_checks) {
        throw std::invalid_argument(
            "conformance report check set is incomplete");
    }
}

rti::demo::ui::ReadyInfo wait_for_server(
    rti::demo::ui::DemoUiApp& app, std::mutex& server_mutex,
    std::condition_variable& server_cv, bool& server_failed,
    const std::exception_ptr& server_error) {
    const auto deadline =
        std::chrono::steady_clock::now() + std::chrono::seconds(10);
    while (std::chrono::steady_clock::now() < deadline) {
        if (const auto ready = app.ready_info()) {
            httplib::Client client(ready->host, ready->port);
            client.set_connection_timeout(0, 100000);
            if (const auto response = client.Get("/api/health");
                response && response->status == 200) {
                return *ready;
            }
        }
        std::unique_lock<std::mutex> lock(server_mutex);
        if (server_cv.wait_for(lock, std::chrono::milliseconds(5),
                               [&]() { return server_failed; })) {
            std::rethrow_exception(server_error);
        }
    }
    throw std::runtime_error("server health readiness timed out");
}
}  // namespace

int main() {
    using namespace rti::demo::ui;
    DemoUiApp app("Native webview spike", 0, "127.0.0.1", SPIKE_STATIC_ROOT);
    std::mutex report_mutex;
    std::condition_variable report_cv;
    Json report;
    bool report_received = false;
    bool server_failed = false;
    app.register_command("spike-report",
                         CommandSchema(Json{{"type", "object"}}),
                         [&](const Json& payload) {
                             validate_report(payload);
                             {
                                 std::lock_guard<std::mutex> lock(report_mutex);
                                 report = payload;
                                 report_received = true;
                             }
                             report_cv.notify_all();
                             return Json{{"recorded", true}};
                         });

    std::exception_ptr server_error;
    std::thread server([&]() {
        try {
            app.run();
        } catch (...) {
            {
                std::lock_guard<std::mutex> lock(report_mutex);
                server_error = std::current_exception();
                server_failed = true;
            }
            report_cv.notify_all();
        }
    });

    try {
        const auto ready = wait_for_server(app, report_mutex, report_cv,
                                           server_failed, server_error);
        std::signal(SIGINT, on_signal);

        webview::webview window(false, nullptr);
        window.set_title("Native webview spike");
        window.set_size(1280, 800, WEBVIEW_HINT_NONE);
        window.navigate(ready.url + "/");
        std::thread closer([&]() {
            std::unique_lock<std::mutex> lock(report_mutex);
            report_cv.wait_for(lock, std::chrono::seconds(15), [&]() {
                return report_received || signal_requested || server_failed;
            });
            window.dispatch([&window]() { window.terminate(); });
        });
        window.run();
        closer.join();
        app.stop();
        server.join();
        if (server_error) std::rethrow_exception(server_error);
        std::cout << Json{{"backend", "cpp"},
                          {"close_observed", true},
                          {"report", report},
                          {"server_joined", true},
                          {"signal_observed", signal_requested != 0}}
                         .dump()
                  << '\n';
    } catch (const std::exception& error) {
        app.stop();
        if (server.joinable()) server.join();
        std::cerr << error.what() << '\n';
        return 1;
    }
    return 0;
}
