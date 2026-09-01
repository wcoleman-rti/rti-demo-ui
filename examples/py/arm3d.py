#
# (c) 2026 Copyright, Real-Time Innovations, Inc.  All rights reserved.
#
# RTI grants Licensee a license to use, modify, compile, and create derivative
# works of the Software.  Licensee has the right to distribute object form
# only for use with RTI products.  The Software is provided "as is", with no
# warranty of any type, including any warranty for fitness for any purpose.
# RTI is under no obligation to maintain or support the Software.  RTI shall
# not be liable for any incidental or consequential damages arising out of the
# use or inability to use the software.
#

"""Application-owned arm3d pilot with deterministic mock joint targets."""

import asyncio
import math
from pathlib import Path

from rti_demo_ui import DemoUiApp, Severity


async def main() -> None:
    static_root = Path(__file__).resolve().parents[1] / "web" / "arm3d"
    app = DemoUiApp("Surgical Arm", static_root=static_root)
    scene = app.add_card("Arm monitor").add_scene_3d(
        "/models/scene3d-fixture.glb",
        camera={
            "mode": "orbit",
            "position": [4.0, 4.45, 5.0],
            "target": [0.0, 1.45, 0.0],
            "min_distance": 0.1,
            "max_distance": 1000.0,
        },
    )
    paths = ["Arm/Base", "Arm/Shoulder", "Arm/Elbow", "Arm/Wrist", "Arm/Tool"]
    for index, path in enumerate(paths):
        scene.add_node(f"joint-{index}", path, position=(0.0, 0.25 + index * 0.6, 0.0))
    run_task = asyncio.create_task(app.run())
    await app.wait_until_ready()
    cycle = 0
    try:
        while True:
            for index in range(len(paths)):
                angle = math.sin(cycle * 0.12 + index * 0.7) * 0.25
                scene.update_node(
                    f"joint-{index}",
                    rotation=(0.0, math.sin(angle / 2), 0.0, math.cos(angle / 2)),
                    status=Severity.warning if abs(angle) > 0.2 else Severity.success,
                )
            cycle += 1
            await asyncio.sleep(0.2)
    except asyncio.CancelledError:
        pass
    finally:
        await app.stop()
        await run_task


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
