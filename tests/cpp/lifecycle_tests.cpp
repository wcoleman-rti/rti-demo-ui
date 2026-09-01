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

#include <rti_demo_ui/demo_ui_app.hpp>

#include <arpa/inet.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <unistd.h>

#include <chrono>
#include <cstdio>
#include <future>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <thread>

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
    {
        DemoUiApp app("Pre-stop", 19281, "127.0.0.1");
        app.stop();
        std::thread thread([&app]() { app.run(); });
        thread.join();
        int probe = socket(AF_INET, SOCK_STREAM, 0);
        CHECK(probe >= 0);
        sockaddr_in address{};
        address.sin_family = AF_INET;
        address.sin_port = htons(19281);
        inet_pton(AF_INET, "127.0.0.1", &address.sin_addr);
        CHECK(bind(probe, reinterpret_cast<sockaddr*>(&address),
                   sizeof(address)) == 0);
        close(probe);
    }

    const int port = 19282;
    int blocker = socket(AF_INET, SOCK_STREAM, 0);
    CHECK(blocker >= 0);
    sockaddr_in address{};
    address.sin_family = AF_INET;
    address.sin_port = htons(port);
    inet_pton(AF_INET, "127.0.0.1", &address.sin_addr);
    CHECK(bind(blocker, reinterpret_cast<sockaddr*>(&address), sizeof(address)) ==
          0);
    CHECK(listen(blocker, 1) == 0);

    DemoUiApp app("Bind failure", port, "127.0.0.1");
    std::ostringstream output;
    auto* old_buffer = std::cout.rdbuf(output.rdbuf());
    bool threw = false;
    std::string message;
    try {
        app.run();
    } catch (const std::runtime_error& error) {
        threw = true;
        message = error.what();
    }
    std::cout.rdbuf(old_buffer);
    CHECK(threw);
    CHECK(message.find("127.0.0.1") != std::string::npos);
    CHECK(message.find("19282") != std::string::npos);
    CHECK(output.str().find("listening") == std::string::npos);
    close(blocker);

    for (int index = 0; index < 2; ++index) {
        DemoUiApp restart("Restart", 19283, "127.0.0.1");
        std::thread thread([&restart]() { restart.run(); });
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
        restart.stop();
        thread.join();
    }

    for (int index = 0; index < 10; ++index) {
        DemoUiApp app("Immediate stop");
        auto runner = std::async(std::launch::async, [&app]() { app.run(); });
        app.stop();
        CHECK(runner.wait_for(std::chrono::seconds(2)) ==
              std::future_status::ready);
        runner.get();
    }

    return failures == 0 ? 0 : 1;
}
