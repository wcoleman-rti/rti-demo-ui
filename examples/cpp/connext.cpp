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

// Basic RTI Connext DDS pub/sub wired in through the application lifecycle
// described in docs/architecture.md. Built only when BUILD_CONNEXT_EXAMPLE=ON.
#include <atomic>
#include <chrono>
#include <cmath>
#include <dds/dds.hpp>
#include <rti/rti.hpp>
#include <rti_demo_ui/rti_demo_ui.hpp>
#include <thread>

#include "VehicleState.hpp"
#include "console_control.hpp"

int main() {
    using namespace rti::demo::ui;

    rti_demo_ui_examples::ConsoleControl control;
    DemoUiApp app("Connext Demo");
    control.start([&app]() { app.stop(); });
    Card* card = app.add_card("Fleet Telemetry");
    Scene2DViewport* scene =
        card->add_scene_2d(600, 400, {-100.0, 100.0, -100.0, 100.0});
    scene->add_entity("vehicle-1", 0.0, 0.0);

    // Declared in parent-to-child order so reverse destruction is safe.
    dds::domain::DomainParticipant participant(0);
    dds::topic::Topic<VehicleState> topic(participant, "VehicleStateTopic");
    dds::pub::DataWriter<VehicleState> writer(topic);
    dds::sub::DataReader<VehicleState> reader(topic);

    rti::sub::SampleProcessor processor;
    processor.attach_reader(
        reader, [&scene](const rti::sub::LoanedSample<VehicleState>& sample) {
            if (!sample.info().valid()) return;
            const auto& data = sample.data();
            scene->update_entity(data.vehicle_id, data.x, data.y, data.heading);
        });

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

    app.run();

    stop_writer.store(true);
    writer_thread.join();
    control.finish();
    return 0;
}
