"""Basic RTI Connext DDS pub/sub wired into an asyncio TaskGroup. Requires
rti.connext, installed separately (not an SDK runtime dependency).
"""

import asyncio
import math

import rti.asyncio  # noqa: F401 - installs Connext's asyncio integration
import rti.connextdds as dds
import rti.types as idl

from rti_demo_ui import DemoUiApp


@idl.struct
class VehicleState:
    vehicle_id: str = ""
    x: float = 0.0
    y: float = 0.0
    heading: float = 0.0


async def main() -> None:
    app = DemoUiApp(title="Connext Demo")
    card = app.add_card("Fleet Telemetry")
    scene = card.add_scene_2d(
        width=600, height=400, bounds=(-100.0, 100.0, -100.0, 100.0)
    )
    scene.add_entity("vehicle-1", x=0.0, y=0.0)

    participant = dds.DomainParticipant(domain_id=0)
    topic = dds.Topic(participant, "VehicleStateTopic", VehicleState)
    writer = dds.DataWriter(topic)
    reader = dds.DataReader(topic)

    async def process_samples() -> None:
        async for data in reader.take_data_async():
            scene.update_entity(
                data.vehicle_id, x=data.x, y=data.y, heading=data.heading
            )

    async def publish_samples() -> None:
        angle = 0.0
        while True:
            angle += 0.05
            sample = VehicleState(
                vehicle_id="vehicle-1",
                x=40.0 * math.cos(angle),
                y=40.0 * math.sin(angle),
                heading=math.degrees(angle) % 360,
            )
            writer.write(sample)
            await asyncio.sleep(0.1)

    try:
        async with asyncio.TaskGroup() as tasks:
            tasks.create_task(app.run())
            tasks.create_task(process_samples())
            tasks.create_task(publish_samples())
    except asyncio.CancelledError:
        pass
    finally:
        await app.stop()


if __name__ == "__main__":
    asyncio.run(main())
