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

"""Responsive custom frontend shell example."""

import asyncio
from pathlib import Path

from rti_demo_ui import DemoUiApp


async def main() -> None:
    static_root = Path(__file__).resolve().parents[1] / "web" / "app_shell"
    app = DemoUiApp("Application workspace", static_root=static_root)
    app.set_data(
        {
            "status": "Awaiting updates",
            "sample_count": 0,
            "last_updated": "Waiting for first update",
            "activity": [{"time": "Ready", "message": "Waiting for the first update."}],
        }
    )

    async def update_application_data() -> None:
        sample_count = 0
        activity = [{"time": "Ready", "message": "Waiting for the first update."}]
        while True:
            await asyncio.sleep(2)
            sample_count += 1
            sequence = f"Update {sample_count}"
            activity.insert(
                0, {"time": sequence, "message": "Application data received."}
            )
            del activity[5:]
            app.update_data(["status"], "Live")
            app.update_data(["sample_count"], sample_count)
            app.update_data(["last_updated"], sequence)
            app.update_data(["activity"], activity)

    try:
        async with asyncio.TaskGroup() as tasks:
            tasks.create_task(app.run())
            tasks.create_task(update_application_data())
    except asyncio.CancelledError:
        pass
    finally:
        await app.stop()


if __name__ == "__main__":
    asyncio.run(main())
