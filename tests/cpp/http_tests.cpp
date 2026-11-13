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

// HTTP contract tests against the C++ backend. See
// docs/architecture.md §11.2.
#include <httplib.h>
#include <rti_demo_ui/rti_demo_ui.hpp>
#ifdef RTI_DEMO_HAS_UPLOT
#include <rti_demo_ui/uplot.hpp>
#endif

#include <chrono>
#include <cstdio>
#include <fstream>
#include <sstream>
#include <thread>

using namespace rti::demo::ui;

static int g_failures = 0;

#define CHECK(cond)                                                          \
    do {                                                                     \
        if (!(cond)) {                                                       \
            std::fprintf(stderr, "FAILED: %s (line %d)\n", #cond, __LINE__); \
            ++g_failures;                                                    \
        }                                                                    \
    } while (0)

void test_ready_info_is_listening() {
    for (int iteration = 0; iteration < 50; ++iteration) {
        DemoUiApp app("Readiness");
        std::thread server_thread([&app]() { app.run(); });
        app.wait_until_ready();
        const auto info = app.ready_info();
        CHECK(info.has_value());
        if (info) {
            httplib::Client client(info->host, info->port);
            client.set_connection_timeout(0, 100000);
            const auto health = client.Get("/api/health");
            CHECK(health != nullptr && health->status == 200);
        }
        app.stop();
        server_thread.join();
    }
}

int main() {
    test_ready_info_is_listening();

    DemoUiApp app("Test App");
    app.register_command(
        "echo",
        CommandSchema(Json{{"type", "object"},
                           {"properties", Json{{"message", Json{{"type", "string"}}}}},
                           {"required", Json::array({"message"})},
                           {"additionalProperties", false}}),
        [](const Json& payload) { return payload; });
    app.add_card("Fleet");

    std::thread server_thread([&app]() { app.run(); });
    app.wait_until_ready();
    const auto info = app.ready_info();
    CHECK(info.has_value());
    if (!info) return 1;
#ifdef RTI_DEMO_HAS_UPLOT
    bool late_adapter_rejected = false;
    try {
        enable_uplot(app);
    } catch (const std::runtime_error&) {
        late_adapter_rejected = true;
    }
    CHECK(late_adapter_rejected);
#endif

    httplib::Client client(info->host, info->port);

    struct Route {
        const char* path;
        const char* content_type;
    };
    Route routes[] = {
        {"/", "text/html; charset=utf-8"},
        {"/sdk/runtime.js", "application/javascript; charset=utf-8"},
        {"/sdk/runtime3d.js", "application/javascript; charset=utf-8"},
        {"/sdk/client.js", "application/javascript; charset=utf-8"},
        {"/sdk/momentary.js", "application/javascript; charset=utf-8"},
        {"/sdk/theme.css", "text/css; charset=utf-8"},
    };
    for (const auto& route : routes) {
        auto res = client.Get(route.path);
        CHECK(res != nullptr);
        if (res) {
            CHECK(res->status == 200);
            CHECK(res->get_header_value("Content-Type") == route.content_type);
            CHECK(res->get_header_value("X-Content-Type-Options") == "nosniff");
        }
        auto empty_manifest = client.Get("/sdk/adapters/manifest.json");
        CHECK(empty_manifest != nullptr && empty_manifest->status == 200);
        if (empty_manifest) {
            CHECK(empty_manifest->get_header_value("Cache-Control") == "no-cache");
            const Json expected_manifest{
                {"schema_version", 1}, {"adapters", Json::array()}};
            CHECK(Json::parse(empty_manifest->body) == expected_manifest);
        }
        auto disabled_adapter = client.Get("/sdk/adapters/uplot/runtime.js");
        CHECK(disabled_adapter != nullptr && disabled_adapter->status == 404);
    }

    auto health = client.Get("/api/health");
    CHECK(health != nullptr && health->status == 200);
    if (health) CHECK(health->body == "{\"status\":\"ok\"}");

    auto state = client.Get("/api/state");
    CHECK(state != nullptr && state->status == 200);
    if (state) {
        const auto snapshot = Json::parse(state->body);
        CHECK(snapshot["schema_version"] == 2);
        CHECK(snapshot["title"] == "Test App");
        CHECK(snapshot["data"].is_object());
        CHECK(snapshot["cards"].size() == 1);
    }

    httplib::Headers origin_headers{{"Origin", info->url}};
    auto browser_capability = client.Get("/api/command-capability");
    CHECK(browser_capability != nullptr && browser_capability->status == 200);
    httplib::Headers mismatched_host_headers{{"Host", "localhost:1"}};
    auto mismatched_host = client.Get("/api/command-capability",
                                      mismatched_host_headers);
    CHECK(mismatched_host != nullptr && mismatched_host->status == 404);
    auto capability = client.Get("/api/command-capability", origin_headers);
    CHECK(capability != nullptr && capability->status == 200);
    if (capability) {
        const auto capability_body = Json::parse(capability->body);
        CHECK(capability_body["capability"].is_string());
        CHECK(browser_capability != nullptr);
        if (browser_capability) {
            CHECK(Json::parse(browser_capability->body)["capability"] ==
                  capability_body["capability"]);
        }
        httplib::Headers command_headers = origin_headers;
        command_headers.emplace("X-RTI-Demo-Command-Capability",
                                capability_body["capability"].get<std::string>());
        httplib::Headers missing_origin_headers{
            {"X-RTI-Demo-Command-Capability",
             capability_body["capability"].get<std::string>()}};
        auto missing_origin = client.Post(
            "/api/commands/echo", missing_origin_headers,
            R"({"message":"missing origin"})", "application/json");
        CHECK(missing_origin != nullptr && missing_origin->status == 403);
        auto command = client.Post(
            "/api/commands/echo", command_headers,
            R"({"message":"hello"})", "application/json");
        CHECK(command != nullptr && command->status == 200);
        if (command) {
            const auto command_body = Json::parse(command->body);
            CHECK(command_body["ok"] == true);
            CHECK(command_body["result"]["message"] == "hello");
        }
        auto oversized = client.Post(
            "/api/commands/echo", command_headers,
            std::string(64 * 1024 + 1, 'x'), "application/json");
        CHECK(oversized != nullptr && oversized->status == 413);
        if (oversized) CHECK(Json::parse(oversized->body)["error"]["code"] ==
                             "payload_too_large");
    }

    auto missing = client.Get("/does-not-exist");
    CHECK(missing != nullptr && missing->status == 404);
    if (missing) CHECK(missing->body == "{\"error\":\"not found\"}");

    auto method_not_allowed = client.Post("/api/state", "", "text/plain");
    CHECK(method_not_allowed != nullptr && method_not_allowed->status == 405);

    // Canonical asset-byte equality (see docs/architecture.md §11.2).
    std::ifstream theme_file(SOURCE_ROOT "/assets/theme.css", std::ios::binary);
    std::ostringstream theme_contents;
    theme_contents << theme_file.rdbuf();
    auto theme_response = client.Get("/sdk/theme.css");
    CHECK(theme_response != nullptr);
    if (theme_response) CHECK(theme_response->body == theme_contents.str());

    std::ifstream runtime_file(SOURCE_ROOT "/assets/runtime.js", std::ios::binary);
    std::ostringstream runtime_contents;
    runtime_contents << runtime_file.rdbuf();
    auto runtime_response = client.Get("/sdk/runtime.js");
    CHECK(runtime_response != nullptr);
    if (runtime_response) CHECK(runtime_response->body == runtime_contents.str());

    std::ifstream runtime3d_file(SOURCE_ROOT "/assets/runtime3d.js",
                                 std::ios::binary);
    std::ostringstream runtime3d_contents;
    runtime3d_contents << runtime3d_file.rdbuf();
    auto runtime3d_response = client.Get("/sdk/runtime3d.js");
    CHECK(runtime3d_response != nullptr);
    if (runtime3d_response)
        CHECK(runtime3d_response->body == runtime3d_contents.str());

    std::ifstream momentary_file(SOURCE_ROOT "/assets/momentary.js",
                                 std::ios::binary);
    std::ostringstream momentary_contents;
    momentary_contents << momentary_file.rdbuf();
    auto momentary_response = client.Get("/sdk/momentary.js");
    CHECK(momentary_response != nullptr);
    if (momentary_response)
        CHECK(momentary_response->body == momentary_contents.str());

    app.stop();
    server_thread.join();

#ifdef RTI_DEMO_HAS_UPLOT
    DemoUiApp adapter_app("Adapter Routes");
    enable_uplot(adapter_app);
    bool duplicate_adapter_rejected = false;
    try {
        enable_uplot(adapter_app);
    } catch (const std::invalid_argument&) {
        duplicate_adapter_rejected = true;
    }
    CHECK(duplicate_adapter_rejected);
    std::thread adapter_thread([&adapter_app]() { adapter_app.run(); });
    adapter_app.wait_until_ready();
    const auto adapter_info = adapter_app.ready_info();
    CHECK(adapter_info.has_value());
    if (adapter_info) {
        httplib::Client adapter_client(adapter_info->host, adapter_info->port);
        auto manifest = adapter_client.Get("/sdk/adapters/manifest.json");
        CHECK(manifest != nullptr && manifest->status == 200);
        if (manifest) {
            CHECK(manifest->get_header_value("Cache-Control") == "no-cache");
            const auto body = Json::parse(manifest->body);
            CHECK(body["adapters"].size() == 1);
            CHECK(body["adapters"][0]["name"] == "uplot");
            CHECK(body["adapters"][0]["module"] ==
                  "/sdk/adapters/uplot/runtime.js");
        }
        auto module = adapter_client.Get("/sdk/adapters/uplot/runtime.js");
        CHECK(module != nullptr && module->status == 200);
        if (module) CHECK(module->body.size() > 50000);
        auto style = adapter_client.Get("/sdk/adapters/uplot/theme.css");
        CHECK(style != nullptr && style->status == 200);
        if (style) CHECK(style->body.find(".sdk-timeseries") !=
                         std::string::npos);
        auto unknown = adapter_client.Get("/sdk/adapters/uplot/remote.js");
        CHECK(unknown != nullptr && unknown->status == 404);
    }
    adapter_app.stop();
    adapter_thread.join();
#endif

    if (g_failures == 0) {
        std::printf("All HTTP contract tests passed\n");
    } else {
        std::fprintf(stderr, "%d HTTP contract test(s) failed\n", g_failures);
    }
    return g_failures == 0 ? 0 : 1;
}
