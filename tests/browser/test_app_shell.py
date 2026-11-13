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

"""Accessibility and responsive-layout check for the custom app-shell example."""

import asyncio
import threading
from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright

from rti_demo_ui import DemoUiApp


ROOT = Path(__file__).parents[2]


@pytest.fixture
def running_app_shell():
    app = DemoUiApp(
        title="Application workspace",
        static_root=ROOT / "examples" / "web" / "app_shell",
    )
    app.set_data(
        {
            "status": "Live",
            "sample_count": 3,
            "last_updated": "Update 3",
            "activity": [
                {"time": "Update 3", "message": "Application data received."},
                {"time": "Ready", "message": "Waiting for the first update."},
            ],
        }
    )
    loop = asyncio.new_event_loop()

    def run_app():
        asyncio.set_event_loop(loop)
        loop.run_until_complete(app.run())

    thread = threading.Thread(target=run_app, daemon=True)
    thread.start()
    asyncio.run_coroutine_threadsafe(app.wait_until_ready(), loop).result(2)
    try:
        yield app.ready_info.url
    finally:
        asyncio.run_coroutine_threadsafe(app.stop(), loop).result(2)
        thread.join(2)
        assert not thread.is_alive()
        loop.close()


def test_app_shell_has_accessible_indicators_and_responsive_layout(running_app_shell):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(running_app_shell)

        expect(
            page.get_by_role("heading", name="Application workspace", level=1)
        ).to_be_visible()
        expect(
            page.get_by_role("status", name="Browser connection status")
        ).to_have_text("Connected")
        expect(page.get_by_role("status", name="Application data status")).to_have_text(
            "Live"
        )
        expect(
            page.get_by_role("complementary", name="Recent activity")
        ).to_be_visible()
        expect(page.locator("#sample-count")).to_have_text("3")
        expect(page.get_by_text("Application data received.")).to_be_visible()

        primary = page.get_by_role("region", name="Overview").bounding_box()
        sidebar = page.get_by_role("complementary", name="Recent activity").bounding_box()
        assert primary is not None and sidebar is not None
        assert sidebar["x"] > primary["x"]

        page.set_viewport_size({"width": 390, "height": 844})
        primary = page.get_by_role("region", name="Overview").bounding_box()
        sidebar = page.get_by_role("complementary", name="Recent activity").bounding_box()
        assert primary is not None and sidebar is not None
        assert sidebar["x"] == pytest.approx(primary["x"])
        assert sidebar["y"] >= primary["y"] + primary["height"]
        assert page.evaluate(
            "document.documentElement.scrollWidth <= window.innerWidth"
        )
        browser.close()
