"""Playwright browser tests run against the Python backend (shared assets mean
the same assertions apply to the C++ backend — see docs/architecture.md.
Run explicitly: `pytest tests/browser/test_browser.py`.
"""

import asyncio
import concurrent.futures
import math
import os
import queue
import re
import signal
import subprocess
import threading
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

from rti_demo_ui import DemoUiApp

_READY_PATTERN = re.compile(
    r"^RTI Demo UI listening on (http://(?:127\.0\.0\.1|\[::1\]):[0-9]+)/$"
)


def _start_app_on_thread(app):
    loop = asyncio.new_event_loop()

    def run_app():
        asyncio.set_event_loop(loop)
        loop.run_until_complete(app.run())

    thread = threading.Thread(target=run_app, daemon=True)
    thread.start()
    asyncio.run_coroutine_threadsafe(app.wait_until_ready(), loop).result(2)
    return loop, thread


@pytest.fixture
def running_app():
    app = DemoUiApp(title="Browser Test")
    card = app.add_card("Fleet Telemetry")
    scene = card.add_scene_2d(600, 400, (-100.0, 100.0, -100.0, 100.0))
    scene.add_entity("vehicle-1", 0.0, 0.0, status="warning")
    scene.add_entity("vehicle-2", 50.0, 50.0)
    scene.add_link("vehicle-1", "vehicle-2")
    loop, thread = _start_app_on_thread(app)
    try:
        yield app, app.ready_info.url
    finally:
        asyncio.run_coroutine_threadsafe(app.stop(), loop).result(2)
        thread.join(2)
        assert not thread.is_alive()
        loop.close()


@pytest.fixture
def running_gallery_app():
    static_root = Path(__file__).parents[2] / "examples" / "web" / "gallery"
    app = DemoUiApp(title="Gallery", static_root=static_root)
    loop, thread = _start_app_on_thread(app)
    try:
        yield app, app.ready_info.url
    finally:
        asyncio.run_coroutine_threadsafe(app.stop(), loop).result(2)
        thread.join(2)
        assert not thread.is_alive()
        loop.close()


@pytest.fixture(params=["python", "cpp"])
def running_arm_server(request):
    static_root = Path(__file__).parents[2] / "examples" / "web" / "arm3d"
    if request.param == "python":
        app = DemoUiApp(title="Surgical Arm", static_root=static_root)
        scene = app.add_card("Arm monitor").add_scene_3d(
            "/models/scene3d-fixture.glb"
        )
        for index, path in enumerate(
            ["Arm/Base", "Arm/Shoulder", "Arm/Elbow", "Arm/Wrist", "Arm/Tool"]
        ):
            scene.add_node(
                f"joint-{index}",
                path,
                position=(0.0, 0.25 + index * 0.6, 0.0),
            )
        loop, thread = _start_app_on_thread(app)

        async def update_scene():
            step = 0
            while True:
                await asyncio.sleep(0.1)
                angle = math.sin(step * 0.12) * 0.25
                scene.update_node(
                    "joint-0",
                    rotation=(
                        0.0,
                        math.sin(angle / 2.0),
                        0.0,
                        math.cos(angle / 2.0),
                    ),
                )
                step += 1

        updates = asyncio.run_coroutine_threadsafe(update_scene(), loop)
        try:
            yield request.param, app.ready_info.url
        finally:
            updates.cancel()
            try:
                updates.result(1)
            except concurrent.futures.CancelledError:
                pass
            asyncio.run_coroutine_threadsafe(app.stop(), loop).result(2)
            thread.join(2)
            assert not thread.is_alive()
            loop.close()
        return

    executable = os.environ.get("RTI_DEMO_CPP_ARM3D")
    if not executable:
        pytest.fail("RTI_DEMO_CPP_ARM3D is required for the C++ arm3d browser backend")
    process = subprocess.Popen(
        [executable],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    lines = queue.Queue()

    def read_stdout():
        for line in process.stdout:
            lines.put(line.rstrip("\n"))

    reader = threading.Thread(target=read_stdout, daemon=True)
    reader.start()
    try:
        try:
            line = lines.get(timeout=10)
        except queue.Empty:
            pytest.fail("C++ arm3d executable did not report readiness within 10 seconds")
        match = _READY_PATTERN.match(line)
        if match is None or process.poll() is not None:
            pytest.fail(f"invalid C++ readiness output: {line!r}")
        yield request.param, match.group(1)
    finally:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGINT)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            pytest.fail("C++ arm3d executable did not stop cleanly after SIGINT")
        reader.join(1)


def _assert_arm_page(page, base_url):
    errors = []
    page.on(
        "console",
        lambda msg: errors.append(msg.text) if msg.type == "error" else None,
    )
    page.goto(base_url + "/")
    page.wait_for_function(
        "document.querySelectorAll('#arm3d-scene [role=option]').length === 5"
    )
    page.wait_for_function(
        "document.querySelector('#arm3d-scene canvas') && "
        "document.querySelector('#arm3d-scene canvas').width > 0"
    )
    page.locator("#arm3d-scene [role=option]").first.focus()
    page.keyboard.press("ArrowDown")
    page.keyboard.press("Enter")
    assert page.locator('[role="option"][aria-selected="true"]').count() == 1
    assert page.locator(".sdk-scene3d-live").inner_text().endswith("selected")
    page.get_by_role("button", name="Zoom to model").click()
    varied_pixels = page.locator("#arm3d-scene canvas").evaluate(
        """canvas => {
            const gl = canvas.getContext('webgl2') || canvas.getContext('webgl');
            if (!gl) return 0;
            gl.finish();
            const pixels = new Uint8Array(canvas.width * canvas.height * 4);
            gl.readPixels(0, 0, canvas.width, canvas.height, gl.RGBA,
                gl.UNSIGNED_BYTE, pixels);
            let count = 0;
            for (let index = 0; index < pixels.length; index += 4) {
                if (Math.max(Math.abs(pixels[index] - 10),
                    Math.abs(pixels[index + 1] - 14),
                    Math.abs(pixels[index + 2] - 23)) >= 10) count += 1;
            }
            return count;
        }"""
    )
    assert varied_pixels >= 100
    assert errors == []


def test_arm3d_renders_for_both_backends(running_arm_server):
    _backend, base_url = running_arm_server
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        _assert_arm_page(page, base_url)
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.locator("#arm3d-scene canvas").bounding_box()["width"] < 390
        browser.close()


def test_arm3d_fallback_preserves_accessibility(running_arm_server):
    _backend, base_url = running_arm_server
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.add_init_script(
            """(() => {
                const original = HTMLCanvasElement.prototype.getContext;
                HTMLCanvasElement.prototype.getContext = function(type, ...args) {
                    if (type === 'webgl' || type === 'webgl2') return null;
                    return original.call(this, type, ...args);
                };
            })();"""
        )
        page.goto(base_url + "/")
        page.wait_for_selector(".sdk-scene3d-fallback-text")
        assert page.locator('#arm3d-scene [role="option"]').count() == 5
        page.locator('#arm3d-scene [role="option"]').first.focus()
        page.keyboard.press("Enter")
        assert page.locator('[role="option"][aria-selected="true"]').count() == 1
        assert "unavailable" in page.locator(".sdk-scene3d-fallback-text").inner_text()
        browser.close()


def test_sse_client_streams_updates_for_both_backends(running_arm_server):
    _backend, base_url = running_arm_server
    state_requests = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.on(
            "request",
            lambda request: state_requests.append(request.url)
            if request.url.endswith("/api/state")
            else None,
        )
        page.goto(base_url + "/sdk/client.js")
        result = page.evaluate(
            """async () => {
                const {createClient} = await import('/sdk/client.js');
                const revisions = [];
                const client = createClient({transport: 'sse'});
                client.subscribe((snapshot) => {
                    if (snapshot && revisions.at(-1) !== snapshot.revision) {
                        revisions.push(snapshot.revision);
                    }
                });
                client.start();
                const deadline = performance.now() + 3000;
                while (revisions.length < 2 && performance.now() < deadline) {
                    await new Promise((resolve) => setTimeout(resolve, 20));
                }
                const state = client.getConnectionState();
                client.stop();
                return {revisions, state};
            }"""
        )
        browser.close()

    assert len(result["revisions"]) >= 2
    assert result["revisions"][1] > result["revisions"][0]
    assert result["state"] == "connected"
    assert state_requests == []


def test_scene_renders_without_console_errors(running_app):
    app, base_url = running_app
    errors = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.on(
            "console",
            lambda msg: errors.append(msg.text) if msg.type == "error" else None,
        )
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
