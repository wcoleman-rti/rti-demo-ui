"""Run one application model in an external browser or a native window."""

import argparse
import asyncio
import math

from rti_demo_ui import DemoUiApp


def build_application():
    app = DemoUiApp(title="Native Dual-Mode Demo")
    card = app.add_card("Fleet Telemetry")
    scene = card.add_scene_2d(
        width=600, height=400, bounds=(-100.0, 100.0, -100.0, 100.0)
    )
    scene.add_entity("vehicle-1", x=0.0, y=0.0, heading=0.0)
    scene.add_entity("vehicle-2", x=50.0, y=50.0, heading=180.0)
    scene.add_link("vehicle-1", "vehicle-2")

    async def animate(_app):
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

    return app, animate


async def run_browser(app, animate) -> None:
    try:
        async with asyncio.TaskGroup() as tasks:
            tasks.create_task(app.run())
            tasks.create_task(animate(app))
    finally:
        await app.stop()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode", choices=("browser", "native"), default="browser"
    )
    args = parser.parse_args()
    app, animate = build_application()
    if args.mode == "native":
        from rti_demo_ui_native import run_native

        run_native(
            app,
            application_id="org.rti.demo-ui.dual-mode-example",
            async_main=animate,
        )
    else:
        asyncio.run(run_browser(app, animate))


if __name__ == "__main__":
    main()
