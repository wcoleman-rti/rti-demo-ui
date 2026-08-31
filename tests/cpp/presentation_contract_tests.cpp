#include <httplib.h>
#include <rti_demo_ui/rti_demo_ui.hpp>

#include <cstdio>
#include <filesystem>
#include <fstream>
#include <set>
#include <string>
#include <thread>

namespace fs = std::filesystem;
using namespace rti::demo::ui;

static int failures = 0;

#define CHECK(condition)                                               \
    do {                                                               \
        if (!(condition)) {                                            \
            std::fprintf(stderr, "FAILED: %s (line %d)\n", #condition, \
                         __LINE__);                                    \
            ++failures;                                                \
        }                                                              \
    } while (0)

#define EXPECT_INVALID(expression)             \
    do {                                       \
        bool threw = false;                    \
        try {                                  \
            expression;                        \
        } catch (const std::invalid_argument&) { \
            threw = true;                      \
        }                                      \
        CHECK(threw);                          \
    } while (0)

#define EXPECT_RUNTIME(expression)          \
    do {                                    \
        bool threw = false;                 \
        try {                               \
            expression;                    \
        } catch (const std::runtime_error&) { \
            threw = true;                   \
        }                                   \
        CHECK(threw);                       \
    } while (0)

bool is_valid(const std::string& field, const Json& value) {
    if (field == "span") {
        return value.is_number_integer() && !value.is_boolean() &&
               value.get<int>() >= 1 && value.get<int>() <= 3;
    }
    if (!value.is_string()) return false;
    const std::string serialized = value.get<std::string>();
    if (field == "theme") return serialized == "dark" || serialized == "light";
    if (field == "layout") {
        return serialized == "auto" || serialized == "grid-2" ||
               serialized == "grid-3" || serialized == "sidebar-main";
    }
    if (field == "area") return serialized == "main" || serialized == "sidebar";
    return false;
}

class RunningApp {
   public:
    explicit RunningApp(DemoUiApp& app) : app_(app), thread_([&app]() { app.run(); }) {
        app_.wait_until_ready();
        const auto ready = app_.ready_info();
        CHECK(ready.has_value());
        if (ready) client_ = std::make_unique<httplib::Client>(ready->host, ready->port);
    }

    ~RunningApp() {
        app_.stop();
        if (thread_.joinable()) thread_.join();
    }

    Json snapshot() {
        auto response = client_->Get("/api/state");
        CHECK(response != nullptr);
        CHECK(response && response->status == 200);
        return response ? Json::parse(response->body) : Json::object();
    }

   private:
    DemoUiApp& app_;
    std::thread thread_;
    std::unique_ptr<httplib::Client> client_;
};

int main() {
    std::ifstream fixture_file(fs::path(SOURCE_ROOT) / "tests/fixtures" /
                               "presentation_contract.json");
    CHECK(fixture_file.good());
    Json fixture;
    fixture_file >> fixture;

    const Json expected_values = {
        {"theme", {{"default", "dark"}, {"valid", {"dark", "light"}}}},
        {"layout",
         {{"default", "auto"},
          {"valid", {"auto", "grid-2", "grid-3", "sidebar-main"}}}},
        {"area", {{"default", "main"}, {"valid", {"main", "sidebar"}}}},
        {"span", {{"default", 1}, {"valid", {1, 2, 3}}}},
    };
    for (const auto& [field, expected] : expected_values.items()) {
        const auto& vectors = fixture["values"][field];
        CHECK(vectors["default"] == expected["default"]);
        CHECK(vectors["valid"] == expected["valid"]);
        for (const auto& value : vectors["valid"])
            CHECK(is_valid(field, value));
        for (const auto& value : vectors["invalid"])
            CHECK(!is_valid(field, value));
    }
    CHECK(std::string(to_string(Theme::dark)) == "dark");
    CHECK(std::string(to_string(Theme::light)) == "light");
    CHECK(std::string(to_string(Layout::automatic)) == "auto");
    CHECK(std::string(to_string(Layout::grid_2)) == "grid-2");
    CHECK(std::string(to_string(Layout::grid_3)) == "grid-3");
    CHECK(std::string(to_string(Layout::sidebar_main)) == "sidebar-main");
    CHECK(std::string(to_string(CardArea::main)) == "main");
    CHECK(std::string(to_string(CardArea::sidebar)) == "sidebar");

    const Json expected_defaults = {
        {"schema_version", 2},
        {"revision", 1},
        {"title", "Presentation Defaults"},
        {"theme", "dark"},
        {"layout", "auto"},
        {"data", Json::object()},
        {"cards",
         {{{"id", "card-1"},
           {"title", "Telemetry"},
           {"area", "main"},
           {"span", 1},
           {"components", Json::array()}}}},
    };
    const Json expected_non_default = {
        {"schema_version", 2},
        {"revision", 2},
        {"title", "Presentation Non-Defaults"},
        {"theme", "light"},
        {"layout", "sidebar-main"},
        {"data", Json::object()},
        {"cards",
         {{{"id", "card-1"},
           {"title", "Controls"},
           {"area", "sidebar"},
           {"span", 1},
           {"components", Json::array()}},
          {{"id", "card-2"},
           {"title", "Telemetry"},
           {"area", "main"},
           {"span", 3},
           {"components", Json::array()}}}},
    };
    CHECK(fixture["snapshots"]["defaults"] == expected_defaults);
    CHECK(fixture["snapshots"]["non_default"] == expected_non_default);

    {
        DemoUiApp app("Presentation Defaults");
        app.add_card("Telemetry");
        RunningApp running(app);
        CHECK(running.snapshot() == fixture["snapshots"]["defaults"]);
    }
    {
        DemoUiApp app("Presentation Non-Defaults", 0, "127.0.0.1", {},
                      Theme::light, Layout::sidebar_main);
        app.add_card("Controls", CardArea::sidebar);
        app.add_card("Telemetry", CardArea::main, 3);
        RunningApp running(app);
        CHECK(running.snapshot() == fixture["snapshots"]["non_default"]);
    }

    const Json expected_sidebar_cases =
        Json::array({{{"name", "runtime sidebar-main with one sidebar"},
                      {"operation", "set_layout"},
                      {"validation_point", "mutation_commit"},
                      {"initial_layout", "auto"},
                      {"attempted_layout", "sidebar-main"},
                      {"sidebar_count", 1},
                      {"accepted", true},
                      {"revision_delta", 1}},
                     {{"name", "runtime sidebar-main without sidebar"},
                      {"operation", "set_layout"},
                      {"validation_point", "mutation_commit"},
                      {"initial_layout", "auto"},
                      {"attempted_layout", "sidebar-main"},
                      {"sidebar_count", 0},
                      {"accepted", false},
                      {"revision_delta", 0}},
                     {{"name", "duplicate sidebar assignment"},
                      {"operation", "set_area"},
                      {"validation_point", "mutation_commit"},
                      {"initial_layout", "auto"},
                      {"attempted_area", "sidebar"},
                      {"sidebar_count", 1},
                      {"accepted", false},
                      {"revision_delta", 0}},
                     {{"name", "constructed sidebar-main without sidebar"},
                      {"operation", "run"},
                      {"validation_point", "before_run"},
                      {"initial_layout", "sidebar-main"},
                      {"sidebar_count", 0},
                      {"accepted", false},
                      {"revision_delta", 0}}});
    CHECK(fixture["sidebar_cases"] == expected_sidebar_cases);

    const std::set<std::string> expected_fields = {"theme", "layout", "area",
                                                   "span"};
    std::set<std::string> actual_fields;
    for (const auto& test_case : fixture["revision_cases"])
        actual_fields.insert(test_case["field"].get<std::string>());
    CHECK(actual_fields == expected_fields);

    for (const auto& field : expected_fields) {
        Json field_cases = Json::array();
        for (const auto& test_case : fixture["revision_cases"]) {
            if (test_case["field"] == field) field_cases.push_back(test_case);
        }
        CHECK(field_cases.size() == 3);
        CHECK(field_cases[0]["accepted"] == true);
        CHECK(field_cases[0]["state_changed"] == true);
        CHECK(field_cases[0]["revision_delta"] == 1);
        CHECK(field_cases[1]["accepted"] == true);
        CHECK(field_cases[1]["state_changed"] == false);
        CHECK(field_cases[1]["revision_delta"] == 0);
        CHECK(field_cases[2]["accepted"] == false);
        CHECK(field_cases[2]["state_changed"] == false);
        CHECK(field_cases[2]["revision_delta"] == 0);
        CHECK(field_cases[2]["initial_value"] !=
              field_cases[2]["attempted_value"]);
    }

    {
        DemoUiApp app("Mutations");
        Card* card = app.add_card("Telemetry");
        app.set_theme(Theme::light);
        app.set_theme(Theme::light);
        EXPECT_INVALID(app.set_theme(static_cast<Theme>(99)));
        app.set_layout(Layout::grid_2);
        app.set_layout(Layout::grid_2);
        EXPECT_INVALID(app.set_layout(static_cast<Layout>(99)));
        card->set_area(CardArea::sidebar);
        card->set_area(CardArea::sidebar);
        EXPECT_INVALID(card->set_area(static_cast<CardArea>(99)));
        card->set_span(3);
        card->set_span(3);
        for (const int invalid : {0, 4, -1}) EXPECT_INVALID(card->set_span(invalid));

        RunningApp running(app);
        const Json snapshot = running.snapshot();
        CHECK(snapshot["revision"] == 5);
        CHECK(snapshot["theme"] == "light");
        CHECK(snapshot["layout"] == "grid-2");
        CHECK(snapshot["cards"][0]["area"] == "sidebar");
        CHECK(snapshot["cards"][0]["span"] == 3);

        app.set_layout(Layout::sidebar_main);
        CHECK(running.snapshot()["revision"] == 6);
        EXPECT_INVALID(card->set_area(CardArea::main));
        CHECK(running.snapshot()["revision"] == 6);

        Card* main = app.add_card("Main");
        const auto revision = running.snapshot()["revision"];
        EXPECT_INVALID(main->set_area(CardArea::sidebar));
        EXPECT_INVALID(app.add_card("Duplicate", CardArea::sidebar));
        CHECK(running.snapshot()["revision"] == revision);
    }

    {
        DemoUiApp app("Sidebar", 0, "127.0.0.1", {}, Theme::dark,
                      Layout::sidebar_main);
        EXPECT_INVALID(app.run());
        app.add_card("Controls", CardArea::sidebar);
        RunningApp running(app);
        CHECK(running.snapshot()["layout"] == "sidebar-main");
    }

    {
        DemoUiApp app("Runtime");
        Card* card = app.add_card("Telemetry");
        RunningApp running(app);
        app.set_theme(Theme::light);
        app.set_layout(Layout::grid_3);
        card->set_area(CardArea::sidebar);
        card->set_span(2);
        const Json snapshot = running.snapshot();
        CHECK(snapshot["revision"] == 5);
        CHECK(snapshot["theme"] == "light");
        CHECK(snapshot["layout"] == "grid-3");
        CHECK(snapshot["cards"][0]["area"] == "sidebar");
        CHECK(snapshot["cards"][0]["span"] == 2);
    }

    {
        EXPECT_INVALID(DemoUiApp("Invalid", 0, "127.0.0.1", {},
                                 static_cast<Theme>(99)));
        EXPECT_INVALID(DemoUiApp("Invalid", 0, "127.0.0.1", {}, Theme::dark,
                                 static_cast<Layout>(99)));
        DemoUiApp app("Stopped");
        Card* card = app.add_card("Telemetry");
        const long revision = 1;
        EXPECT_INVALID(app.add_card("Invalid", static_cast<CardArea>(99)));
        EXPECT_INVALID(app.add_card("Invalid", CardArea::main, 0));
        {
            RunningApp running(app);
            CHECK(running.snapshot()["revision"] == revision);
        }
        EXPECT_RUNTIME(app.set_theme(Theme::light));
        EXPECT_RUNTIME(app.set_layout(Layout::grid_2));
        EXPECT_RUNTIME(card->set_area(CardArea::sidebar));
        EXPECT_RUNTIME(card->set_span(2));
    }

    return failures == 0 ? 0 : 1;
}
