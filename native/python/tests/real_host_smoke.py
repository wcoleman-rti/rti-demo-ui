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

import asyncio

from rti_demo_ui import DemoUiApp
from rti_demo_ui_native import run_native


async def close_after_start(_app):
    await asyncio.sleep(0.5)


run_native(
    DemoUiApp("Native cross-platform smoke"),
    application_id="org.rti.native-cross-platform-smoke",
    async_main=close_after_start,
)
