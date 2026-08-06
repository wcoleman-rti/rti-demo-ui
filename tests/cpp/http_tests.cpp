// HTTP contract tests against the C++ backend. See
// docs/architecture.md §11.2.
#include <httplib.h>
#include <rti_demo_ui/gui_sdk.hpp>

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

int main() {
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

    std::ifstream runtime3d_file(SOURCE_ROOT "/assets/runtime3d.js",
                                 std::ios::binary);
    std::ostringstream runtime3d_contents;
    runtime3d_contents << runtime3d_file.rdbuf();
    auto runtime3d_response = client.Get("/sdk/runtime3d.js");
    CHECK(runtime3d_response != nullptr);
    if (runtime3d_response)
        CHECK(runtime3d_response->body == runtime3d_contents.str());

    app.stop();
    server_thread.join();

    if (g_failures == 0) {
        std::printf("All HTTP contract tests passed\n");
    } else {
        std::fprintf(stderr, "%d HTTP contract test(s) failed\n", g_failures);
    }
    return g_failures == 0 ? 0 : 1;
}
