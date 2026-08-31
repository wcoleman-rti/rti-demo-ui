// Phase 0 webview host; experimental and not a public SDK API.
#include <httplib.h>
#include <webview/webview.h>

#include <atomic>
#include <chrono>
#include <cctype>
#include <condition_variable>
#include <csignal>
#include <filesystem>
#include <iostream>
#include <mutex>
#include <rti_demo_ui/demo_ui_app.hpp>
#include <set>
#include <stdexcept>
#include <string>
#include <thread>

namespace {
volatile std::sig_atomic_t signal_requested = 0;

void on_signal(int) { signal_requested = 1; }

struct Options {
    int port = 0;
    std::string storage_expected = "__absent__";
    std::string storage_key = "rti-demo-ui-native-spike";
    std::filesystem::path storage_path;
    std::string storage_write = "phase-zero";
    bool wait_for_signal = false;
};

bool is_query_value(const std::string& value) {
    if (value.empty()) return false;
    for (const unsigned char character : value) {
        if (!std::isalnum(character) && character != '-' && character != '_' &&
            character != '.') {
            return false;
        }
    }
    return true;
}

Options parse_options(int argc, char** argv) {
    Options options;
    for (int index = 1; index < argc; index += 2) {
        if (index + 1 >= argc) {
            throw std::invalid_argument(std::string(argv[index]) +
                                        " requires a value");
        }
        const std::string name = argv[index];
        const std::string value = argv[index + 1];
        if (name == "--port") {
            options.port = std::stoi(value);
            if (options.port < 0 || options.port > 65535) {
                throw std::invalid_argument("port must be between 0 and 65535");
            }
        } else if (name == "--storage-expected") {
            options.storage_expected = value;
        } else if (name == "--storage-key") {
            options.storage_key = value;
        } else if (name == "--storage-path") {
            options.storage_path = value;
        } else if (name == "--storage-write") {
            options.storage_write = value;
        } else if (name == "--wait-for-signal") {
            if (value != "true" && value != "false") {
                throw std::invalid_argument(
                    "--wait-for-signal must be true or false");
            }
            options.wait_for_signal = value == "true";
        } else {
            throw std::invalid_argument("unknown option: " + name);
        }
    }
    if (!is_query_value(options.storage_expected) ||
        !is_query_value(options.storage_key) ||
        !is_query_value(options.storage_write)) {
        throw std::invalid_argument(
            "storage probe values may contain only letters, numbers, '.', "
            "'-', and '_'");
    }
    if (options.storage_path.empty()) {
        throw std::invalid_argument("--storage-path is required");
    }
    return options;
}

#if defined(__linux__)
struct NavigationPolicy {
    std::string allowed_origin;
    std::atomic<bool> blocked_external{false};
};

gboolean block_external_navigation(WebKitWebView*, WebKitPolicyDecision* decision,
                                   WebKitPolicyDecisionType decision_type,
                                   gpointer user_data) {
    if (decision_type != WEBKIT_POLICY_DECISION_TYPE_NAVIGATION_ACTION &&
        decision_type != WEBKIT_POLICY_DECISION_TYPE_NEW_WINDOW_ACTION) {
        return FALSE;
    }
    auto* navigation = WEBKIT_NAVIGATION_POLICY_DECISION(decision);
    auto* action =
        webkit_navigation_policy_decision_get_navigation_action(navigation);
    const char* uri =
        webkit_uri_request_get_uri(webkit_navigation_action_get_request(action));
    auto* policy = static_cast<NavigationPolicy*>(user_data);
    const std::string target = uri ? uri : "";
    const bool allowed =
        target == policy->allowed_origin ||
        target.rfind(policy->allowed_origin + "/", 0) == 0;
    if (allowed) return FALSE;
    policy->blocked_external = true;
    webkit_policy_decision_ignore(decision);
    return TRUE;
}

void configure_persistent_cookies(webview::webview& window,
                                  const std::filesystem::path& profile) {
    std::filesystem::create_directories(profile);
    auto controller = window.browser_controller();
    controller.ensure_ok();
    auto* view = WEBKIT_WEB_VIEW(controller.value());
    auto* context = webkit_web_view_get_context(view);
    auto* manager = webkit_web_context_get_cookie_manager(context);
    const std::string cookie_path = (profile / "cookies.sqlite").string();
    webkit_cookie_manager_set_persistent_storage(
        manager, cookie_path.c_str(), WEBKIT_COOKIE_PERSISTENT_STORAGE_SQLITE);
}

void configure_navigation_policy(webview::webview& window,
                                 NavigationPolicy& policy) {
    auto controller = window.browser_controller();
    controller.ensure_ok();
    auto* view = WEBKIT_WEB_VIEW(controller.value());
    g_signal_connect(view, "decide-policy",
                     G_CALLBACK(block_external_navigation), &policy);
}
#else
struct NavigationPolicy {
    std::string allowed_origin;
    std::atomic<bool> blocked_external{false};
};

void configure_persistent_cookies(webview::webview&,
                                  const std::filesystem::path&) {}
void configure_navigation_policy(webview::webview&, NavigationPolicy&) {}
#endif

void validate_report(const rti::demo::ui::Json& payload) {
    using rti::demo::ui::Json;
    static const std::set<std::string> expected_checks{
        "canvas",             "command_origin", "dynamic_import",
        "keyboard_focus",     "module_worker",    "navigation_policy",
        "persistent_storage", "resize_observation", "runtime3d_import",
        "snapshot",           "sse",                "theme_asset",
        "webgl",
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

int main(int argc, char** argv) {
    using namespace rti::demo::ui;
    Options options;
    try {
        options = parse_options(argc, argv);
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
    DemoUiApp app("Native webview spike", options.port, "127.0.0.1",
                  SPIKE_STATIC_ROOT);
    std::mutex report_mutex;
    std::condition_variable report_cv;
    Json report;
    bool report_received = false;
    bool server_failed = false;
    bool window_closed = false;
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
    app.register_command(
        "spike-origin", CommandSchema(Json{{"type", "object"}}),
        [](const Json& payload) { return Json{{"origin", payload["origin"]}}; });

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
        configure_persistent_cookies(window, options.storage_path);
        NavigationPolicy navigation_policy{ready.url};
        configure_navigation_policy(window, navigation_policy);
        window.set_title("Native webview spike");
        window.set_size(1280, 800, WEBVIEW_HINT_NONE);
        window.navigate(ready.url + "/?storage_key=" + options.storage_key +
                        "&storage_expected=" + options.storage_expected +
                        "&storage_write=" + options.storage_write);
        std::thread closer([&]() {
            std::unique_lock<std::mutex> lock(report_mutex);
            const auto close_requested = [&]() {
                return (!options.wait_for_signal && report_received) ||
                       signal_requested || server_failed || window_closed;
            };
            if (options.wait_for_signal) {
                while (!close_requested()) {
                    report_cv.wait_for(lock, std::chrono::milliseconds(50));
                }
            } else {
                report_cv.wait_for(lock, std::chrono::seconds(15),
                                   close_requested);
            }
            if (!window_closed) {
                window.dispatch([&window]() { window.terminate(); });
            }
        });
        window.run();
        {
            std::lock_guard<std::mutex> lock(report_mutex);
            window_closed = true;
        }
        report_cv.notify_all();
        closer.join();
        app.stop();
        server.join();
        if (server_error) std::rethrow_exception(server_error);
        bool report_passed = report_received;
        if (report_passed) {
            for (const auto& item : report["results"].items()) {
                report_passed = report_passed && item.value()["passed"].get<bool>();
            }
        }
        std::cout << Json{{"backend", "cpp"},
                          {"close_observed", true},
                          {"report", report},
                          {"server_joined", true},
                          {"signal_observed", signal_requested != 0}}
                         .dump()
                  << '\n';
        if (!report_passed && signal_requested == 0) return 1;
    } catch (const std::exception& error) {
        app.stop();
        if (server.joinable()) server.join();
        std::cerr << error.what() << '\n';
        return 1;
    }
    return 0;
}
