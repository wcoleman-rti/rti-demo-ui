"""Basic RTI Connext DDS pub/sub wired in via the §10 polling pattern (see
docs/implementation_plan.md §10.2). Requires rti.connext, installed
separately (not an SDK runtime dependency).
"""

import math
import threading
import time

import rti.connextdds as dds
import rti.types as idl

from rti_demo_gui_sdk import CoreApp


@idl.struct
class VehicleState:
    vehicle_id: str = ""
    x: float = 0.0
    y: float = 0.0
    heading: float = 0.0


def main() -> None:
    app = CoreApp(title="Connext Demo")
    card = app.add_card("Fleet Telemetry")
    scene = card.add_scene_2d(
        width=600, height=400, bounds=(-100.0, 100.0, -100.0, 100.0)
    )
    scene.add_entity("vehicle-1", x=0.0, y=0.0)

    participant = dds.DomainParticipant(domain_id=0)
    topic = dds.Topic(participant, "VehicleStateTopic", VehicleState)
    writer = dds.DataWriter(participant.implicit_publisher, topic)
    reader = dds.DataReader(participant.implicit_subscriber, topic)

    stop_event = threading.Event()

    def writer_worker() -> None:
        angle = 0.0
        while not stop_event.is_set():
            angle += 0.05
            sample = VehicleState(
                vehicle_id="vehicle-1",
                x=40.0 * math.cos(angle),
                y=40.0 * math.sin(angle),
                heading=math.degrees(angle) % 360,
            )
            writer.write(sample)
            time.sleep(0.1)

    def reader_worker() -> None:
        while not stop_event.is_set():
            for data, info in reader.take():
                if not info.valid:
                    continue
                scene.update_entity(
                    data.vehicle_id, x=data.x, y=data.y, heading=data.heading
                )
            time.sleep(0.05)

    writer_thread = threading.Thread(target=writer_worker, daemon=True)
    reader_thread = threading.Thread(target=reader_worker, daemon=True)
    writer_thread.start()
    reader_thread.start()

    try:
        app.run()
    finally:
        stop_event.set()
        writer_thread.join()
        reader_thread.join()


if __name__ == "__main__":
    main()
