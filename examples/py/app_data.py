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

"""Minimal application-owned JSON state example."""

import asyncio
from pathlib import Path

from rti_demo_ui import DemoUiApp


async def main() -> None:
    static_root = Path(__file__).resolve().parents[1] / "web" / "app_data"
    app = DemoUiApp("Application data", static_root=static_root)
    app.set_data({"count": 0})

    async def update_count() -> None:
        count = 0
        while True:
            await asyncio.sleep(1)
            count += 1
            app.update_data(["count"], count)

    try:
        async with asyncio.TaskGroup() as tasks:
            tasks.create_task(app.run())
            tasks.create_task(update_count())
    except asyncio.CancelledError:
        pass
    finally:
        await app.stop()


if __name__ == "__main__":
    asyncio.run(main())
