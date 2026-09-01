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

#include <httplib.h>
#include <nlohmann/json.hpp>
#include <rti_demo_ui/demo_ui_app.hpp>

#include <chrono>
#include <filesystem>
#include <fstream>
#include <sstream>
#include <string>
#include <thread>

namespace fs = std::filesystem;
using namespace rti::demo::ui;

static int failures = 0;

#define CHECK(condition)                                                     \
    do {                                                                      \
        if (!(condition)) {                                                   \
            std::fprintf(stderr, "FAILED: %s (line %d)\n", #condition,       \
                         __LINE__);                                          \
            ++failures;                                                       \
        }                                                                     \
    } while (0)

int main() {
    const fs::path fixture_root = fs::path(SOURCE_ROOT) / "tests/fixtures";
    const fs::path static_fixture = fixture_root / "static_root";
    const fs::path test_root = fs::temp_directory_path() / "rti_demo_ui_static_root_test";
    std::error_code error;
    fs::remove_all(test_root, error);
    fs::create_directories(test_root, error);
    CHECK(!error);
    const fs::path web_root = test_root / "web";
    fs::copy(static_fixture, web_root, fs::copy_options::recursive, error);
    CHECK(!error);

    fs::create_symlink("symlink-target.txt", web_root / "inside-link.txt", error);
    CHECK(!error);
    fs::create_symlink("missing-target.txt", web_root / "broken-link.txt", error);
    CHECK(!error);
    fs::create_directory_symlink("nested", web_root / "directory-link", error);
    CHECK(!error);
    const fs::path outside = test_root / "outside.txt";
    std::ofstream(outside) << "outside\n";
    fs::create_symlink(outside, web_root / "escape-link.txt", error);
    CHECK(!error);

    std::ifstream vectors_file(fixture_root / "static_route_vectors.json");
    nlohmann::json vectors;
    vectors_file >> vectors;

    DemoUiApp app("Custom fixture", 19391, "127.0.0.1", web_root);
    std::thread server_thread([&app]() { app.run(); });
    std::this_thread::sleep_for(std::chrono::milliseconds(300));
    httplib::Client client("127.0.0.1", 19391);

    for (const auto& vector : vectors) {
        const std::string path = vector.at("path").get<std::string>();
        auto response = client.Get(path);
        CHECK(response != nullptr);
        if (!response) continue;
        CHECK(response->status == vector.at("status").get<int>());
        const auto expected_content_type =
            vector.at("content_type").get<std::string>();
        if (response->get_header_value("Content-Type") != expected_content_type) {
            std::fprintf(stderr, "%s: expected %s, got %s\n",
                         vector.at("name").get<std::string>().c_str(),
                         expected_content_type.c_str(),
                         response->get_header_value("Content-Type").c_str());
            ++failures;
        }
        CHECK(response->get_header_value("X-Content-Type-Options") == "nosniff");
        if (vector.contains("body_contains")) {
            CHECK(response->body.find(vector.at("body_contains").get<std::string>()) !=
                  std::string::npos);
        }
        if (vector.at("response_class") == "api_json") {
            CHECK(nlohmann::json::parse(response->body).is_object());
        }
    }

    app.stop();
    server_thread.join();
    fs::remove_all(test_root, error);
    CHECK(!error);
    return failures == 0 ? 0 : 1;
}
