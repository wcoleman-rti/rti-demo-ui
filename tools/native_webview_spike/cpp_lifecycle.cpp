#include <httplib.h>

#include <chrono>
#include <iostream>
#include <rti_demo_ui/demo_ui_app.hpp>
#include <string_view>
#include <thread>

namespace {
bool wait_for_health(const rti::demo::ui::ReadyInfo& ready) {
    httplib::Client client(ready.host, ready.port);
    client.set_connection_timeout(0, 100000);
    const auto deadline =
        std::chrono::steady_clock::now() + std::chrono::seconds(2);
    while (std::chrono::steady_clock::now() < deadline) {
        const auto response = client.Get("/api/health");
        if (response && response->status == 200) return true;
        std::this_thread::sleep_for(std::chrono::milliseconds(5));
    }
    return false;
}
}  // namespace

int main(int argc, char** argv) {
    const bool immediate_stop =
        argc == 2 && std::string_view(argv[1]) == "--immediate-stop";
    rti::demo::ui::DemoUiApp app("C++ native lifecycle spike");
    std::thread server([&app]() { app.run(); });
    app.wait_until_ready();
    const auto ready = app.ready_info();
    if (!ready || ready->host != "127.0.0.1") {
        app.stop();
        server.join();
        std::cerr << "readiness failed\n";
        return 1;
    }
    if (!immediate_stop && !wait_for_health(*ready)) {
        app.stop();
        server.join();
        std::cerr << "health readiness failed\n";
        return 1;
    }
    app.stop();
    server.join();
    std::cout << "ready=" << ready->url << " server_joined=true\n";
    return 0;
}
