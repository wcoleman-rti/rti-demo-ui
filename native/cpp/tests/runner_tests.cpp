#include <arpa/inet.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <unistd.h>

#include <atomic>
#include <chrono>
#include <condition_variable>
#include <csignal>
#include <cstdio>
#include <mutex>
#include <rti_demo_ui_native/native_webview.hpp>
#include <stdexcept>
#include <string>
#include <thread>

#include "navigation.hpp"
#include "runner.hpp"

using namespace rti::demo::ui;
using namespace rti::demo::ui::native;
namespace native_detail = rti::demo::ui::native::detail;

namespace {

int failures = 0;

#define CHECK(condition)                                               \
    do {                                                               \
        if (!(condition)) {                                            \
            std::fprintf(stderr, "FAILED: %s (line %d)\n", #condition, \
                         __LINE__);                                    \
            ++failures;                                                \
        }                                                              \
    } while (0)

class FakeWindowHost final : public native_detail::WindowHost {
   public:
    bool close_immediately = false;
    bool fail_create = false;
    std::thread::id create_thread;
    std::thread::id run_thread;
    std::string title;
    std::string url;
    NativeWindowOptions options;

    void create(const std::string& received_title,
                const std::string& received_url,
                const NativeWindowOptions& received_options) override {
        create_thread = std::this_thread::get_id();
        title = received_title;
        url = received_url;
        options = received_options;
        {
            std::lock_guard<std::mutex> guard(mutex_);
            created_ = true;
        }
        cv_.notify_all();
        if (fail_create) {
            throw std::runtime_error("window initialization failed");
        }
        if (close_immediately) {
            request_close();
        }
    }

    void run() override {
        run_thread = std::this_thread::get_id();
        std::unique_lock<std::mutex> lock(mutex_);
        if (!cv_.wait_for(lock, std::chrono::seconds(2),
                          [&]() { return close_requested_; })) {
            throw std::runtime_error("fake window close timed out");
        }
    }

    void request_close() noexcept override {
        {
            std::lock_guard<std::mutex> guard(mutex_);
            close_requested_ = true;
        }
        cv_.notify_all();
    }

    bool wait_until_created() {
        std::unique_lock<std::mutex> lock(mutex_);
        return cv_.wait_for(lock, std::chrono::seconds(2),
                            [&]() { return created_; });
    }

    bool close_requested() const {
        std::lock_guard<std::mutex> guard(mutex_);
        return close_requested_;
    }

   private:
    mutable std::mutex mutex_;
    std::condition_variable cv_;
    bool close_requested_ = false;
    bool created_ = false;
};

bool port_is_released(const std::string& url) {
    const auto colon = url.rfind(':');
    const auto slash = url.find('/', colon);
    const int port = std::stoi(url.substr(colon + 1, slash - colon - 1));
    int probe = socket(AF_INET, SOCK_STREAM, 0);
    sockaddr_in address{};
    address.sin_family = AF_INET;
    address.sin_port = htons(port);
    inet_pton(AF_INET, "127.0.0.1", &address.sin_addr);
    const bool released = connect(probe, reinterpret_cast<sockaddr*>(&address),
                                  sizeof(address)) != 0;
    close(probe);
    return released;
}

template <typename Function>
bool throws_native(Function&& function, const std::string& expected) {
    try {
        function();
    } catch (const NativeWebviewError& error) {
        return std::string(error.what()).find(expected) != std::string::npos;
    }
    return false;
}

void test_normal_close() {
    DemoUiApp app("Native test");
    FakeWindowHost host;
    host.close_immediately = true;
    native_detail::run_with_host(app, {}, host);

    CHECK(host.create_thread == std::this_thread::get_id());
    CHECK(host.run_thread == std::this_thread::get_id());
    CHECK(host.title == "Native test");
    CHECK(host.url.rfind("http://127.0.0.1:", 0) == 0);
    CHECK(host.url.back() == '/');
    CHECK(port_is_released(host.url));
}

void test_window_failure_cleans_up() {
    DemoUiApp app("Window failure");
    FakeWindowHost host;
    host.fail_create = true;
    CHECK(throws_native([&]() { native_detail::run_with_host(app, {}, host); },
                        "native window failed"));
    CHECK(port_is_released(host.url));
}

void test_bind_failure_does_not_create_window() {
    int blocker = socket(AF_INET, SOCK_STREAM, 0);
    CHECK(blocker >= 0);
    sockaddr_in address{};
    address.sin_family = AF_INET;
    address.sin_port = 0;
    inet_pton(AF_INET, "127.0.0.1", &address.sin_addr);
    CHECK(bind(blocker, reinterpret_cast<sockaddr*>(&address),
               sizeof(address)) == 0);
    CHECK(listen(blocker, 1) == 0);
    socklen_t size = sizeof(address);
    CHECK(getsockname(blocker, reinterpret_cast<sockaddr*>(&address), &size) ==
          0);

    DemoUiApp app("Bind failure", ntohs(address.sin_port));
    FakeWindowHost host;
    CHECK(throws_native([&]() { native_detail::run_with_host(app, {}, host); },
                        "server failed"));
    CHECK(host.url.empty());
    close(blocker);
}

void test_server_stop_closes_window() {
    DemoUiApp app("Server stop");
    FakeWindowHost host;
    std::atomic<bool> window_created{false};
    std::thread stopper([&]() {
        window_created = host.wait_until_created();
        app.stop();
    });
    native_detail::run_with_host(app, {}, host);
    stopper.join();

    CHECK(window_created);
    CHECK(host.close_requested());
    CHECK(port_is_released(host.url));
}

void test_signal_closes_window() {
    DemoUiApp app("Signal close");
    FakeWindowHost host;
    std::thread interrupter([&]() {
        CHECK(host.wait_until_created());
        std::raise(SIGINT);
    });
    native_detail::run_with_signals(app, {}, host);
    interrupter.join();

    CHECK(host.close_requested());
    CHECK(port_is_released(host.url));
}

void test_validation() {
    {
        DemoUiApp app("Width");
        FakeWindowHost host;
        CHECK(throws_native(
            [&]() {
                native_detail::run_with_host(
                    app, NativeWindowOptions{0, 800, false}, host);
            },
            "width"));
    }
    {
        DemoUiApp app("Host", 0, "localhost");
        FakeWindowHost host;
        CHECK(throws_native(
            [&]() { native_detail::run_with_host(app, {}, host); },
            "loopback"));
    }
}

void test_navigation_origin_is_exact() {
    const auto allowed = native_detail::origin("http://127.0.0.1:42000/");
    CHECK(native_detail::same_origin("http://127.0.0.1:42000/dashboard",
                                     allowed));
    CHECK(native_detail::same_origin("http://127.0.0.1:42000/?view=main",
                                     allowed));
    CHECK(!native_detail::same_origin("http://127.0.0.1:42001/", allowed));
    CHECK(!native_detail::same_origin("http://localhost:42000/", allowed));
    CHECK(!native_detail::same_origin("https://example.invalid/", allowed));
    CHECK(!native_detail::same_origin("about:blank", allowed));
}

void test_app_is_single_use() {
    DemoUiApp app("Single use");
    FakeWindowHost first;
    first.close_immediately = true;
    native_detail::run_with_host(app, {}, first);

    FakeWindowHost second;
    CHECK(
        throws_native([&]() { native_detail::run_with_host(app, {}, second); },
                      "already started"));
}

}  // namespace

int main() {
    test_normal_close();
    test_window_failure_cleans_up();
    test_bind_failure_does_not_create_window();
    test_server_stop_closes_window();
    test_signal_closes_window();
    test_validation();
    test_navigation_origin_is_exact();
    test_app_is_single_use();
    return failures == 0 ? 0 : 1;
}
