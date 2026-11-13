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

"""Minimal built-in dashboard component example."""

import asyncio

from rti_demo_ui import DemoUiApp, Severity


async def main() -> None:
    app = DemoUiApp("Components")
    card = app.add_card("System status")
    card.add_metric("Temperature", 42, Severity.warning)
    card.add_badge("Connected", Severity.success)
    card.add_text("All systems responding")
    card.add_table(
        [{"id": "name", "label": "Name"}, {"id": "value", "label": "Value"}],
        [{"id": "motor", "cells": {"name": "Motor", "value": "Ready"}}],
    )
    card.add_log(
        [{"id": "startup", "timestamp": "12:00:00", "message": "Demo started"}]
    )

    try:
        await app.run()
    except asyncio.CancelledError:
        pass
    finally:
        await app.stop()


if __name__ == "__main__":
    asyncio.run(main())
