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
import sys
import tempfile
import threading
from pathlib import Path

from rti_demo_ui import DemoUiApp
from rti_demo_ui_native import run_native


async def close_after_start(_app):
    await asyncio.sleep(0.5)


if sys.platform == "linux":
    import gi

    gi.require_version("Gtk", "3.0")
    gi.require_version("Gdk", "3.0")
    gi.require_version("GdkPixbuf", "2.0")
    from gi.repository import Gdk, GdkPixbuf, GLib, Gtk

    inspected = threading.Event()
    results = {}
    application_id = "org.rti.native-cross-platform-smoke"
    original_name = GLib.get_prgname()
    original_class = Gdk.get_program_class()

    def inspect_window():
        windows = Gtk.Window.list_toplevels()
        window = next(
            (
                item
                for item in windows
                if item.get_title() == "Native cross-platform smoke"
            ),
            None,
        )
        if window is None:
            results["missing_window"] = True
        else:
            icon = window.get_icon()
            results["icon"] = (
                icon is not None
                and icon.get_width() == 256
                and icon.get_height() == 128
            )
            results["identity"] = (
                GLib.get_prgname() == application_id
                and Gdk.get_program_class() == application_id
            )
        inspected.set()
        return GLib.SOURCE_REMOVE

    async def inspect_after_start(_app):
        GLib.idle_add(inspect_window)
        if not await asyncio.to_thread(inspected.wait, 10):
            raise TimeoutError("native icon inspection timed out")

    with tempfile.TemporaryDirectory(prefix="rti-native-icon-test-") as directory:
        path = str(Path(directory) / "oversized.png")
        image = GdkPixbuf.Pixbuf.new(GdkPixbuf.Colorspace.RGB, True, 8, 1024, 512)
        image.fill(0xFF00FFFF)
        image.savev(path, "png", [], [])
        run_native(
            DemoUiApp("Native cross-platform smoke"),
            application_id=application_id,
            icon=path,
            async_main=inspect_after_start,
        )
    assert results == {"icon": True, "identity": True}, results
    assert GLib.get_prgname() == original_name
    assert Gdk.get_program_class() == original_class
else:
    run_native(
        DemoUiApp("Native cross-platform smoke"),
        application_id="org.rti.native-cross-platform-smoke",
        async_main=close_after_start,
    )
