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

"""Check the interactive frontend used by the manual native release guide."""

import asyncio
import importlib.util
import threading
from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).parents[2]
SPEC = importlib.util.spec_from_file_location(
    "manual_release", ROOT / "native/python/tests/manual_release.py"
)
assert SPEC is not None and SPEC.loader is not None
manual_release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(manual_release)


@pytest.fixture
def manual_app():
    app = manual_release.create_app()
    loop = asyncio.new_event_loop()

    def run_app():
        asyncio.set_event_loop(loop)
        loop.run_until_complete(app.run())

    thread = threading.Thread(target=run_app, daemon=True)
    thread.start()
    asyncio.run_coroutine_threadsafe(app.wait_until_ready(), loop).result(5)
    try:
        yield app.ready_info.url
    finally:
        asyncio.run_coroutine_threadsafe(app.stop(), loop).result(5)
        thread.join(5)
        assert not thread.is_alive()
        loop.close()


def test_manual_frontend_exercises_commands_and_live_selection(manual_app):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 390, "height": 844})
        page.goto(manual_app)

        page.get_by_label("Name").fill("Reviewer")
        page.get_by_role("button", name="Greet").click()
        expect(page.locator("#result")).to_have_text("Hello, Reviewer!")
        option = page.locator("#scene [data-node-id=tool]")
        expect(option).to_be_visible()
        option.click(delay=350)
        expect(page.locator("#selection")).to_have_text("tool: selected")
        option.click(delay=350)
        expect(page.locator("#selection")).to_have_text("tool: deselected")
        assert page.evaluate(
            "document.documentElement.scrollWidth <= window.innerWidth"
        )

        page.get_by_role("link", name="Open local page").click()
        expect(
            page.get_by_role("heading", name="Local navigation test")
        ).to_be_visible()
        page.get_by_role("link", name="Return to manual test").click()
        expect(
            page.get_by_role("heading", name="Native release manual test")
        ).to_be_visible()
        browser.close()
