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

"""Minimal validated browser command example."""

import asyncio
from pathlib import Path

from rti_demo_ui import DemoUiApp


async def main() -> None:
    static_root = Path(__file__).resolve().parents[1] / "web" / "commands"
    app = DemoUiApp("Commands", static_root=static_root)
    app.register_command(
        "greet",
        {
            "type": "object",
            "properties": {"name": {"type": "string", "minLength": 1}},
            "required": ["name"],
            "additionalProperties": False,
        },
        lambda payload: {"message": f"Hello, {payload['name']}!"},
    )

    try:
        await app.run()
    except asyncio.CancelledError:
        pass
    finally:
        await app.stop()


if __name__ == "__main__":
    asyncio.run(main())
