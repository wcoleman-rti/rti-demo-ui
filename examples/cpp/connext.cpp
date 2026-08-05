// Basic RTI Connext DDS pub/sub wired in via the §10 polling pattern (see
// docs/architecture.md §10.3). Built only when BUILD_CONNEXT_EXAMPLE=ON.
#include <atomic>
#include <chrono>
#include <cmath>
#include <dds/dds.hpp>
#include <rti_demo_gui_sdk/gui_sdk.hpp>
#include <thread>

#include "VehicleState.hpp"

int main() {
    using namespace rti_demo_gui_sdk;

    CoreApp app("Connext Demo");
    Card* card = app.add_card("Fleet Telemetry");
    Scene2DViewport* scene =
        card->add_scene_2d(600, 400, {-100.0, 100.0, -100.0, 100.0});
    scene->add_entity("vehicle-1", 0.0, 0.0);

    // Declared in parent-to-child order so reverse destruction is safe.
    dds::domain::DomainParticipant participant(0);
    dds::topic::Topic<VehicleState> topic(participant, "VehicleStateTopic");
    dds::pub::Publisher publisher(participant);
    dds::pub::DataWriter<VehicleState> writer(publisher, topic);
    dds::sub::Subscriber subscriber(participant);
    dds::sub::DataReader<VehicleState> reader(subscriber, topic);

    std::atomic<bool> stop_writer{false};
    std::thread writer_thread([&writer, &stop_writer]() {
        double angle = 0.0;
        while (!stop_writer.load()) {
            VehicleState sample;
            sample.vehicle_id = "vehicle-1";
            angle += 0.05;
            sample.x = 40.0 * std::cos(angle);
            sample.y = 40.0 * std::sin(angle);
            sample.heading = angle * 180.0 / M_PI;
            writer.write(sample);
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
        }
    });

    std::atomic<bool> stop_reader{false};
    std::thread reader_thread([&reader, scene, &stop_reader]() {
        while (!stop_reader.load()) {
            auto samples = reader.take();
            for (const auto& sample : samples) {
                if (!sample.info().valid()) continue;
                const auto& data = sample.data();
                scene->update_entity(data.vehicle_id, data.x, data.y,
                                     data.heading);
            }
            std::this_thread::sleep_for(std::chrono::milliseconds(50));
        }
    });

    app.run();

    stop_writer.store(true);
    stop_reader.store(true);
    writer_thread.join();
    reader_thread.join();
    return 0;
}
