"""Minimal asyncio example with an application-owned animation task."""

import asyncio
import math

from rti_demo_ui import DemoUiApp


async def main() -> None:
    app = DemoUiApp(title="Simple Demo")
    card = app.add_card("Fleet Telemetry")
    scene = card.add_scene_2d(
        width=600, height=400, bounds=(-100.0, 100.0, -100.0, 100.0)
    )
    scene.add_entity("vehicle-1", x=0.0, y=0.0, heading=0.0)
    scene.add_entity("vehicle-2", x=50.0, y=50.0, heading=180.0)
    scene.add_link("vehicle-1", "vehicle-2")

    async def animate() -> None:
        angle = 0.0
        while True:
            angle += 0.05
            scene.update_entity(
                "vehicle-1",
                x=40.0 * math.cos(angle),
                y=40.0 * math.sin(angle),
                heading=math.degrees(angle) % 360,
            )
            await asyncio.sleep(0.1)

    try:
        async with asyncio.TaskGroup() as tasks:
            tasks.create_task(app.run())
            tasks.create_task(animate())
    except asyncio.CancelledError:
        pass
    finally:
        await app.stop()


if __name__ == "__main__":
    asyncio.run(main())
