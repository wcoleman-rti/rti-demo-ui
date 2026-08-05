"""Minimal example: one card, one scene, two entities, one link, and a timer
moving one entity. See docs/architecture.md §10.1.
"""

import math

from rti_demo_ui import DemoUiApp


def main() -> None:
    app = DemoUiApp(title="Simple Demo")
    card = app.add_card("Fleet Telemetry")
    scene = card.add_scene_2d(
        width=600, height=400, bounds=(-100.0, 100.0, -100.0, 100.0)
    )
    scene.add_entity("vehicle-1", x=0.0, y=0.0, heading=0.0)
    scene.add_entity("vehicle-2", x=50.0, y=50.0, heading=180.0)
    scene.add_link("vehicle-1", "vehicle-2")

    angle = 0.0

    def tick() -> None:
        nonlocal angle
        angle += 0.05
        scene.update_entity(
            "vehicle-1",
            x=40.0 * math.cos(angle),
            y=40.0 * math.sin(angle),
            heading=math.degrees(angle) % 360,
        )

    app.add_timer(100, tick)
    try:
        app.run()
    except KeyboardInterrupt:
        pass
    finally:
        app.stop()


if __name__ == "__main__":
    main()
