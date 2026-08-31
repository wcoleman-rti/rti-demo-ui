#include <httplib.h>
#include <rti_demo_ui/rti_demo_ui.hpp>

#include <arpa/inet.h>
#include <sys/socket.h>
#include <unistd.h>

#include <chrono>
#include <condition_variable>
#include <cstdio>
#include <cstring>
#include <memory>
#include <mutex>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

using namespace rti::demo::ui;

namespace rti::demo::ui::detail {
class SseTestAccess {
   public:
    static SseManager& manager(DemoUiApp& app) {
        return *app.sse_manager_;
    }

    static void set_heartbeat(DemoUiApp& app,
                              std::chrono::milliseconds interval) {
        auto& manager = *app.sse_manager_;
        std::lock_guard<std::mutex> guard(manager.mutex_);
        manager.heartbeat_interval_ = interval;
        manager.cv_.notify_all();
    }

    static size_t subscriber_count(DemoUiApp& app) {
        auto& manager = *app.sse_manager_;
        std::lock_guard<std::mutex> guard(manager.mutex_);
        return manager.subscribers_.size();
    }

    static void delay_next_publication(
        DemoUiApp& app, std::chrono::milliseconds interval) {
        auto& manager = *app.sse_manager_;
        std::lock_guard<std::mutex> guard(manager.mutex_);
        manager.publication_interval_ = interval;
        manager.previous_flush_ = SseManager::Clock::now();
    }

    static bool wait_for_pending(
        DemoUiApp& app, const std::shared_ptr<SseManager::Subscriber>& subscriber,
        bool snapshot) {
        auto& manager = *app.sse_manager_;
        std::unique_lock<std::mutex> lock(manager.mutex_);
        const bool ready = manager.cv_.wait_for(
            lock, std::chrono::seconds(1), [&]() {
                return subscriber->closed ||
                       (subscriber->pending &&
                        subscriber->pending->snapshot == snapshot);
            });
        return ready && !subscriber->closed && subscriber->pending &&
               subscriber->pending->snapshot == snapshot;
    }

    static bool reset_pending(
        DemoUiApp& app, const std::shared_ptr<SseManager::Subscriber>& subscriber) {
        auto& manager = *app.sse_manager_;
        std::lock_guard<std::mutex> guard(manager.mutex_);
        return subscriber->reset_pending;
    }

    static bool wait_for_close(
        DemoUiApp& app, const std::shared_ptr<SseManager::Subscriber>& subscriber) {
        auto& manager = *app.sse_manager_;
        std::unique_lock<std::mutex> lock(manager.mutex_);
        return manager.cv_.wait_for(lock, std::chrono::seconds(1),
                                    [&]() { return subscriber->closed; });
    }

    static void set_tail_revision(
        DemoUiApp& app, const std::shared_ptr<SseManager::Subscriber>& subscriber,
        long revision) {
        auto& manager = *app.sse_manager_;
        std::lock_guard<std::mutex> guard(manager.mutex_);
        subscriber->tail_revision = revision;
    }

    static size_t pending_slot_count(
        DemoUiApp& app,
        const std::shared_ptr<SseManager::Subscriber>& subscriber) {
        auto& manager = *app.sse_manager_;
        std::lock_guard<std::mutex> guard(manager.mutex_);
        return subscriber->pending ? 1 : 0;
    }

    static long model_revision(DemoUiApp& app) {
        std::lock_guard<std::mutex> guard(app.model_.lock());
        return app.model_.revision_;
    }
};
}  // namespace rti::demo::ui::detail

static int g_failures = 0;

#define CHECK(cond)                                                          \
    do {                                                                     \
        if (!(cond)) {                                                       \
            std::fprintf(stderr, "FAILED: %s (line %d)\n", #cond, __LINE__); \
            ++g_failures;                                                    \
        }                                                                    \
    } while (0)

class RawStream {
   public:
    explicit RawStream(const ReadyInfo& info) {
        socket_ = socket(AF_INET, SOCK_STREAM, 0);
        if (socket_ < 0) throw std::runtime_error("socket failed");
        timeval timeout{5, 0};
        setsockopt(socket_, SOL_SOCKET, SO_RCVTIMEO, &timeout, sizeof(timeout));
        sockaddr_in address{};
        address.sin_family = AF_INET;
        address.sin_port = htons(static_cast<uint16_t>(info.port));
        if (inet_pton(AF_INET, info.host.c_str(), &address.sin_addr) != 1 ||
            connect(socket_, reinterpret_cast<sockaddr*>(&address),
                    sizeof(address)) != 0) {
            close(socket_);
            throw std::runtime_error("connect failed");
        }
        const std::string request =
            "GET /api/events HTTP/1.1\r\nHost: " + info.host + ":" +
            std::to_string(info.port) +
            "\r\nAccept: text/event-stream\r\nLast-Event-ID: 1\r\n\r\n";
        size_t sent = 0;
        while (sent < request.size()) {
            const ssize_t count =
                send(socket_, request.data() + sent, request.size() - sent, 0);
            if (count <= 0) {
                close(socket_);
                throw std::runtime_error("send failed");
            }
            sent += static_cast<size_t>(count);
        }
    }

    RawStream(const RawStream&) = delete;
    RawStream& operator=(const RawStream&) = delete;

    ~RawStream() {
        if (socket_ >= 0) close(socket_);
    }

    std::string read_headers() {
        std::string headers;
        while (headers.find("\r\n\r\n") == std::string::npos) {
            headers += receive();
        }
        const auto end = headers.find("\r\n\r\n") + 4;
        buffer_ = headers.substr(end) + buffer_;
        return headers.substr(0, end);
    }

    std::string read_chunk() {
        const std::string size_line = read_line();
        const size_t size = std::stoul(size_line, nullptr, 16);
        std::string body = read_exact(size);
        CHECK(read_exact(2) == "\r\n");
        return body;
    }

    void close_peer() {
        if (socket_ >= 0) {
            shutdown(socket_, SHUT_RDWR);
            close(socket_);
            socket_ = -1;
        }
    }

   private:
    std::string receive() {
        char data[4096];
        const ssize_t count = recv(socket_, data, sizeof(data), 0);
        if (count <= 0) throw std::runtime_error("receive failed");
        return std::string(data, static_cast<size_t>(count));
    }

    std::string read_line() {
        while (buffer_.find("\r\n") == std::string::npos) {
            buffer_ += receive();
        }
        const auto end = buffer_.find("\r\n");
        std::string line = buffer_.substr(0, end);
        buffer_.erase(0, end + 2);
        return line;
    }

    std::string read_exact(size_t size) {
        while (buffer_.size() < size) buffer_ += receive();
        std::string value = buffer_.substr(0, size);
        buffer_.erase(0, size);
        return value;
    }

    int socket_ = -1;
    std::string buffer_;
};

Json event_data(const std::string& event) {
    const auto start = event.find("data: ");
    if (start == std::string::npos) {
        throw std::runtime_error("event has no data");
    }
    const auto data_start = start + std::strlen("data: ");
    const auto end = event.find("\n\n", data_start);
    return Json::parse(event.substr(data_start, end - data_start));
}

std::string read_event_chunk(RawStream& stream, const std::string& prefix) {
    for (int attempt = 0; attempt < 20; ++attempt) {
        std::string chunk = stream.read_chunk();
        if (chunk.find(prefix) == 0) return chunk;
    }
    throw std::runtime_error("expected event was not received");
}

void test_snapshot_patch_heartbeat_and_disconnect() {
    DemoUiApp app("C++ Events");
    Card* card = app.add_card("Status");
    Metric* metric = card->add_metric("Rate", 1);
    std::thread server([&app]() { app.run(); });
    app.wait_until_ready();
    detail::SseTestAccess::set_heartbeat(app, std::chrono::milliseconds(20));
    RawStream stream(*app.ready_info());

    const std::string headers = stream.read_headers();
    CHECK(headers.find("HTTP/1.1 200") != std::string::npos);
    CHECK(headers.find("Content-Type: text/event-stream") != std::string::npos);
    CHECK(headers.find("Cache-Control: no-cache") != std::string::npos);
    CHECK(headers.find("X-Content-Type-Options: nosniff") != std::string::npos);
    CHECK(headers.find("Content-Length:") == std::string::npos);
    CHECK(headers.find("Access-Control-Allow-Origin:") == std::string::npos);
    CHECK(stream.read_chunk() == "retry: 1000\n\n");

    const std::string snapshot_event = stream.read_chunk();
    CHECK(snapshot_event.find("event: snapshot\nid: 2\n") == 0);
    const Json snapshot = event_data(snapshot_event);
    CHECK(snapshot["revision"] == 2);
    CHECK(snapshot["cards"][0]["components"][0]["data"]["value"] == 1);

    app.set_data(Json{{"mode", "live"}});
    metric->set_value(2);
    metric->set_value(42, Severity::warning);
    const std::string patch_event = stream.read_chunk();
    CHECK(patch_event.find("event: patch\nid: 5\n") == 0);
    const Json patch = event_data(patch_event);
    CHECK(patch["base_revision"] == 2);
    CHECK(patch["revision"] == 5);
    CHECK(patch["changes"][0]["op"] == "replace-app-data");
    CHECK(patch["changes"][1]["op"] == "upsert-component");
    CHECK(patch["changes"][1]["value"]["data"]["value"] == 42);

    app.set_theme(Theme::light);
    app.set_layout(Layout::grid_2);
    card->set_span(2);
    const Json presentation_patch =
        event_data(read_event_chunk(stream, "event: patch"));
    CHECK(presentation_patch["revision"] == 8);
    CHECK(presentation_patch["changes"].size() == 2);
    CHECK((presentation_patch["changes"][0] ==
           Json{{"op", "replace-presentation"},
                {"theme", "light"},
                {"layout", "grid-2"}}));
    CHECK(presentation_patch["changes"][1]["op"] == "upsert-card");
    CHECK(presentation_patch["changes"][1]["value"]["span"] == 2);

    detail::SseTestAccess::delay_next_publication(
        app, std::chrono::milliseconds(100));
    const auto previous_publication = std::chrono::steady_clock::now();
    metric->set_value(43);
    metric->set_value(100);
    const Json next_patch =
        event_data(read_event_chunk(stream, "event: patch"));
    CHECK(next_patch["revision"] == 10);
    CHECK(next_patch["changes"][0]["value"]["data"]["value"] == 100);
    CHECK(std::chrono::steady_clock::now() - previous_publication >=
          std::chrono::milliseconds(80));

    CHECK(stream.read_chunk() == ": heartbeat\n\n");
    stream.close_peer();
    for (int attempt = 0;
         attempt < 100 && detail::SseTestAccess::subscriber_count(app) != 0;
         ++attempt) {
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
    }
    CHECK(detail::SseTestAccess::subscriber_count(app) == 0);

    app.stop();
    server.join();
}

void test_admission_reserves_ordinary_workers() {
    DemoUiApp app("C++ Capacity");
    app.add_card("Status");
    std::thread server([&app]() { app.run(); });
    app.wait_until_ready();
    const ReadyInfo info = *app.ready_info();
    std::vector<std::unique_ptr<RawStream>> streams;
    for (int index = 0; index < 16; ++index) {
        auto stream = std::make_unique<RawStream>(info);
        CHECK(stream->read_headers().find("HTTP/1.1 200") != std::string::npos);
        CHECK(stream->read_chunk() == "retry: 1000\n\n");
        CHECK(stream->read_chunk().find("event: snapshot") == 0);
        streams.push_back(std::move(stream));
    }
    CHECK(detail::SseTestAccess::subscriber_count(app) == 16);

    httplib::Client client(info.host, info.port);
    client.set_read_timeout(2, 0);
    const auto rejected = client.Get("/api/events");
    CHECK(rejected != nullptr && rejected->status == 503);
    if (rejected) {
        CHECK(rejected->body ==
              "{\"error\":\"event stream capacity reached\"}");
    }
    const auto state = client.Get("/api/state");
    CHECK(state != nullptr && state->status == 200);
    const auto method_not_allowed =
        client.Post("/api/events", "", "application/json");
    CHECK(method_not_allowed != nullptr && method_not_allowed->status == 405);

    const auto start = std::chrono::steady_clock::now();
    app.stop();
    server.join();
    CHECK(std::chrono::steady_clock::now() - start < std::chrono::seconds(2));
}

void test_slow_subscriber_snapshot_reset_and_close() {
    DemoUiApp app("C++ Slow");
    std::thread server([&app]() { app.run(); });
    app.wait_until_ready();
    auto& manager = detail::SseTestAccess::manager(app);
    auto subscriber = manager.subscribe();
    CHECK(subscriber != nullptr);
    const auto initial = manager.next(subscriber);
    CHECK(initial.kind == detail::SseManager::DeliveryKind::state);
    CHECK(initial.event->snapshot);

    app.set_data(Json{{"publication", 1}});
    CHECK(detail::SseTestAccess::wait_for_pending(app, subscriber, false));

    app.set_data(Json{{"publication", 2}});
    CHECK(detail::SseTestAccess::wait_for_pending(app, subscriber, true));
    CHECK(detail::SseTestAccess::reset_pending(app, subscriber));

    const auto reset = manager.next(subscriber);
    CHECK(reset.reset);
    app.set_data(Json{{"publication", 3}});
    CHECK(detail::SseTestAccess::wait_for_pending(app, subscriber, false));
    app.set_data(Json{{"publication", 4}});
    CHECK(detail::SseTestAccess::wait_for_close(app, subscriber));
    CHECK(detail::SseTestAccess::subscriber_count(app) == 0);

    app.stop();
    server.join();
}

void test_multi_client_publication_order_and_tail_reset() {
    DemoUiApp app("C++ Ordering");
    Metric* metric = app.add_card("Status")->add_metric("Rate", 0);
    std::thread server([&app]() { app.run(); });
    app.wait_until_ready();
    auto& manager = detail::SseTestAccess::manager(app);
    auto first = manager.subscribe();
    auto second = manager.subscribe();
    auto mismatch = manager.subscribe();
    for (const auto& subscriber : {first, second, mismatch}) {
        const auto initial = manager.next(subscriber);
        CHECK(initial.event->snapshot);
        manager.delivered(subscriber, initial, true);
    }
    detail::SseTestAccess::set_tail_revision(app, mismatch, 99);
    detail::SseTestAccess::delay_next_publication(
        app, std::chrono::milliseconds(50));

    app.set_data(Json{{"mode", "live"}});
    metric->set_value(1);
    metric->set_value(2);
    CHECK(detail::SseTestAccess::wait_for_pending(app, first, false));
    CHECK(detail::SseTestAccess::wait_for_pending(app, second, false));
    CHECK(detail::SseTestAccess::wait_for_pending(app, mismatch, true));
    const auto first_patch = manager.next(first);
    const auto second_patch = manager.next(second);
    const auto reset = manager.next(mismatch);
    CHECK(first_patch.event->body == second_patch.event->body);
    CHECK(first_patch.event->revision == second_patch.event->revision);
    CHECK(reset.event->revision == first_patch.event->revision);
    CHECK(event_data(*first_patch.event->body)["revision"] ==
          first_patch.event->revision);
    CHECK(event_data(*reset.event->body)["revision"] == reset.event->revision);
    manager.delivered(first, first_patch, true);
    manager.delivered(second, second_patch, true);
    manager.delivered(mismatch, reset, true);

    metric->set_value(3);
    CHECK(detail::SseTestAccess::wait_for_pending(app, first, false));
    CHECK(detail::SseTestAccess::wait_for_pending(app, second, false));
    CHECK(detail::SseTestAccess::wait_for_pending(app, mismatch, false));
    const auto next_first = manager.next(first);
    const auto next_second = manager.next(second);
    const auto next_mismatch = manager.next(mismatch);
    CHECK(next_first.event->revision > first_patch.event->revision);
    CHECK(next_first.event->body == next_second.event->body);
    CHECK(next_first.event->body == next_mismatch.event->body);
    manager.delivered(first, next_first, true);
    manager.delivered(second, next_second, true);
    manager.delivered(mismatch, next_mismatch, true);

    manager.unsubscribe(first);
    manager.unsubscribe(second);
    manager.unsubscribe(mismatch);
    app.stop();
    server.join();
}

void test_provider_writer_failure_outcomes_close_subscribers() {
    DemoUiApp app("C++ Writer");
    std::thread server([&app]() { app.run(); });
    app.wait_until_ready();
    auto& manager = detail::SseTestAccess::manager(app);
    const detail::SseManager::WriteResult outcomes[] = {
        detail::SseManager::WriteResult::timed_out,
        detail::SseManager::WriteResult::failed,
        detail::SseManager::WriteResult::unwritable};

    for (const auto outcome : outcomes) {
        auto subscriber = manager.subscribe();
        const auto delivery = manager.next(subscriber);
        bool called = false;
        const bool written = manager.write(
            subscriber, &delivery, delivery.event->body->data(),
            delivery.event->body->size(),
            [&called, outcome](const char*, size_t) {
                called = true;
                return outcome;
            });
        CHECK(called);
        CHECK(!written);
        CHECK(detail::SseTestAccess::subscriber_count(app) == 0);
    }

    app.stop();
    server.join();
}

void test_sustained_burst_is_bounded_and_converges_to_latest_state() {
    DemoUiApp app("C++ Burst");
    Metric* metric = app.add_card("Status")->add_metric("Rate", 0);
    std::thread server([&app]() { app.run(); });
    app.wait_until_ready();
    auto& manager = detail::SseTestAccess::manager(app);
    auto subscriber = manager.subscribe();
    const auto initial = manager.next(subscriber);
    manager.delivered(subscriber, initial, true);

    std::mutex publications_mutex;
    std::condition_variable publications_cv;
    std::vector<std::chrono::steady_clock::time_point> publication_times;
    std::vector<Json> publications;
    std::thread consumer([&]() {
        while (true) {
            const auto delivery = manager.next(subscriber);
            if (delivery.kind == detail::SseManager::DeliveryKind::stopped) {
                return;
            }
            if (delivery.kind == detail::SseManager::DeliveryKind::heartbeat) {
                continue;
            }
            const Json publication = event_data(*delivery.event->body);
            manager.delivered(subscriber, delivery, true);
            {
                std::lock_guard<std::mutex> guard(publications_mutex);
                publication_times.push_back(std::chrono::steady_clock::now());
                publications.push_back(publication);
            }
            publications_cv.notify_all();
        }
    });

    int last_value = 0;
    const auto burst_end =
        std::chrono::steady_clock::now() + std::chrono::milliseconds(1050);
    while (std::chrono::steady_clock::now() < burst_end) {
        metric->set_value(++last_value);
        std::this_thread::sleep_for(std::chrono::milliseconds(1));
    }
    const long final_revision = detail::SseTestAccess::model_revision(app);
    {
        std::unique_lock<std::mutex> lock(publications_mutex);
        CHECK(publications_cv.wait_for(
            lock, std::chrono::milliseconds(250), [&]() {
                return !publications.empty() &&
                       publications.back()["revision"] == final_revision;
            }));
        if (publications.empty()) {
            manager.unsubscribe(subscriber);
            lock.unlock();
            consumer.join();
            app.stop();
            server.join();
            return;
        }
        CHECK(publications.back()["changes"][0]["value"]["data"]["value"] ==
              last_value);
        for (const auto start : publication_times) {
            size_t count = 0;
            for (const auto value : publication_times) {
                if (value >= start && value < start + std::chrono::seconds(1)) {
                    ++count;
                }
            }
            CHECK(count <= 30);
        }
    }
    CHECK(detail::SseTestAccess::pending_slot_count(app, subscriber) <= 1);

    manager.unsubscribe(subscriber);
    consumer.join();
    app.stop();
    server.join();
}

void test_four_workers_remain_available_with_sixteen_streams() {
    DemoUiApp app("C++ Worker Barrier");
    std::mutex barrier_mutex;
    std::condition_variable barrier_cv;
    int entered = 0;
    bool released = false;
    for (const std::string name : {"worker-a", "worker-b", "worker-c",
                                   "worker-d"}) {
        app.register_command(
            name,
            CommandSchema(Json{{"type", "object"},
                               {"additionalProperties", false}}),
            [&](const Json&) {
                std::unique_lock<std::mutex> lock(barrier_mutex);
                ++entered;
                barrier_cv.notify_all();
                barrier_cv.wait(lock, [&]() { return released; });
                return Json::object();
            });
    }
    std::thread server([&app]() { app.run(); });
    app.wait_until_ready();
    const ReadyInfo info = *app.ready_info();
    std::vector<std::unique_ptr<RawStream>> streams;
    for (int index = 0; index < 16; ++index) {
        auto stream = std::make_unique<RawStream>(info);
        stream->read_headers();
        stream->read_chunk();
        stream->read_chunk();
        streams.push_back(std::move(stream));
    }

    httplib::Client capability_client(info.host, info.port);
    httplib::Headers origin{{"Origin", info.url}};
    const auto capability =
        capability_client.Get("/api/command-capability", origin);
    CHECK(capability != nullptr && capability->status == 200);
    if (!capability || capability->status != 200) {
        app.stop();
        server.join();
        return;
    }
    const std::string token =
        Json::parse(capability->body)["capability"].get<std::string>();
    std::vector<int> statuses(4, 0);
    std::vector<std::thread> requests;
    const std::string names[] = {"worker-a", "worker-b", "worker-c",
                                 "worker-d"};
    for (int index = 0; index < 4; ++index) {
        requests.emplace_back([&, index]() {
            httplib::Client client(info.host, info.port);
            client.set_read_timeout(3, 0);
            httplib::Headers headers{
                {"Origin", info.url},
                {"X-RTI-Demo-Command-Capability", token}};
            const auto response = client.Post(
                "/api/commands/" + names[index], headers, "{}",
                "application/json");
            statuses[index] = response ? response->status : 0;
        });
    }
    {
        std::unique_lock<std::mutex> lock(barrier_mutex);
        CHECK(barrier_cv.wait_for(lock, std::chrono::seconds(2),
                                  [&]() { return entered == 4; }));
        released = true;
        barrier_cv.notify_all();
    }
    for (auto& request : requests) request.join();
    for (const int status : statuses) CHECK(status == 200);

    app.stop();
    server.join();
}

void test_concurrent_mutation_and_subscription_lock_order() {
    DemoUiApp app("C++ Lock Order");
    std::thread server([&app]() { app.run(); });
    app.wait_until_ready();
    auto& manager = detail::SseTestAccess::manager(app);

    std::thread mutations([&app]() {
        for (int value = 0; value < 500; ++value) {
            app.set_data(Json{{"value", value}});
        }
    });
    std::thread subscriptions([&manager]() {
        for (int index = 0; index < 100; ++index) {
            auto subscriber = manager.subscribe();
            if (subscriber) {
                manager.next(subscriber);
                manager.unsubscribe(subscriber);
            }
        }
    });
    mutations.join();
    subscriptions.join();

    app.stop();
    server.join();
}

int main() {
    test_snapshot_patch_heartbeat_and_disconnect();
    test_admission_reserves_ordinary_workers();
    test_slow_subscriber_snapshot_reset_and_close();
    test_multi_client_publication_order_and_tail_reset();
    test_provider_writer_failure_outcomes_close_subscribers();
    test_sustained_burst_is_bounded_and_converges_to_latest_state();
    test_four_workers_remain_available_with_sixteen_streams();
    test_concurrent_mutation_and_subscription_lock_order();
    if (g_failures == 0) {
        std::printf("All SSE tests passed\n");
    } else {
        std::fprintf(stderr, "%d SSE test(s) failed\n", g_failures);
    }
    return g_failures == 0 ? 0 : 1;
}
