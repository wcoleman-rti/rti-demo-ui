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
    const int port = 19280;
    DemoUiApp app("Test App", port);
    app.add_card("Fleet");

    std::thread server_thread([&app]() { app.run(); });
    std::this_thread::sleep_for(std::chrono::milliseconds(300));

    httplib::Client client("127.0.0.1", port);

    struct Route {
        const char* path;
        const char* content_type;
    };
    Route routes[] = {
        {"/", "text/html; charset=utf-8"},
        {"/sdk/runtime.js", "application/javascript; charset=utf-8"},
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
        CHECK(state->body.find("\"schema_version\":1") != std::string::npos);
        CHECK(state->body.find("\"title\":\"Test App\"") != std::string::npos);
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

    app.stop();
    server_thread.join();

    if (g_failures == 0) {
        std::printf("All HTTP contract tests passed\n");
    } else {
        std::fprintf(stderr, "%d HTTP contract test(s) failed\n", g_failures);
    }
    return g_failures == 0 ? 0 : 1;
}
