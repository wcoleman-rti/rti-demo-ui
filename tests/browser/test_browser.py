"""Playwright browser tests run against the Python backend (shared assets mean
the same assertions apply to the C++ backend — see docs/architecture.md
§11.3). Run explicitly: `pytest tests/py/test_browser.py`.
"""

import threading
import time
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

from rti_demo_ui import DemoUiApp


@pytest.fixture
def running_app():
    app = DemoUiApp(title="Browser Test", port=19380)
    card = app.add_card("Fleet Telemetry")
    scene = card.add_scene_2d(600, 400, (-100.0, 100.0, -100.0, 100.0))
    scene.add_entity("vehicle-1", 0.0, 0.0, status="warning")
    scene.add_entity("vehicle-2", 50.0, 50.0)
    scene.add_link("vehicle-1", "vehicle-2")
    thread = threading.Thread(target=app.run, daemon=True)
    thread.start()
    time.sleep(0.3)
    yield app, "http://127.0.0.1:19380"
    app.stop()


@pytest.fixture
def running_gallery_app():
    static_root = Path(__file__).parents[2] / "examples" / "web" / "gallery"
    app = DemoUiApp(title="Gallery", port=19381, static_root=static_root)
    thread = threading.Thread(target=app.run, daemon=True)
    thread.start()
    time.sleep(0.3)
    yield app, "http://127.0.0.1:19381"
    app.stop()
    thread.join(2)
    assert not thread.is_alive()


def test_scene_renders_without_console_errors(running_app):
    app, base_url = running_app
    errors = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.on("console", lambda msg: errors.append(msg.text) if msg.type == "error" else None)
        page.goto(base_url + "/")
        page.wait_for_selector("svg.sdk-scene2d circle")
        title = page.inner_text("#sdk-app-title")
        assert title == "Browser Test"
        circles = page.query_selector_all("svg.sdk-scene2d circle")
        assert len(circles) == 2
        lines = page.query_selector_all("svg.sdk-scene2d line")
        assert len(lines) >= 1
        browser.close()
    assert errors == []


def test_gallery_page_controls(running_gallery_app):
    app, base_url = running_gallery_app
    del app
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.goto(base_url + "/")
        assert page.locator("#gallery-button").is_visible()
        page.click("#gallery-button")
        assert page.inner_text("#gallery-metric") == "43"
        browser.close()
