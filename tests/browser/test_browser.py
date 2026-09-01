"""Playwright browser tests run against the Python backend (shared assets mean
the same assertions apply to the C++ backend — see docs/architecture.md.
Run explicitly: `pytest tests/browser/test_browser.py`.
"""

import asyncio
import concurrent.futures
import math
import json
import os
import queue
import re
import signal
import subprocess
import threading
from itertools import combinations, product
from pathlib import Path
from shutil import copy2
from urllib.request import urlopen

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


@pytest.fixture(
    params=list(
        product(
            ("dark", "light"),
            ("auto", "grid-2", "grid-3", "sidebar-main"),
        )
    ),
    ids=lambda value: "-".join(value),
)
def running_gallery_app(request):
    theme, layout = request.param
    static_root = Path(__file__).parents[2] / "examples" / "web" / "gallery"
    app = DemoUiApp(
        title="Gallery",
        static_root=static_root,
        theme=theme,
        layout=layout,
    )
    app.add_card("Presentation", area="sidebar").add_text(f"{theme} / {layout}")
    app.add_card("Telemetry", span=2).add_metric("Connected assets", 12)
    loop, thread = _start_app_on_thread(app)
    try:
        yield app, app.ready_info.url, theme, layout
    finally:
        asyncio.run_coroutine_threadsafe(app.stop(), loop).result(2)
        thread.join(2)
        assert not thread.is_alive()
        loop.close()


@pytest.fixture
def running_builtin_scene3d_app(tmp_path):
    repository_root = Path(__file__).parents[2]
    copy2(repository_root / "assets" / "index.html", tmp_path / "index.html")
    model_root = tmp_path / "models"
    model_root.mkdir()
    copy2(
        repository_root / "examples/web/arm3d/models/scene3d-fixture.glb",
        model_root / "scene3d-fixture.glb",
    )
    app = DemoUiApp(title="Built-In Scene3D", static_root=tmp_path)
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
    page.wait_for_function(
        "document.querySelector('.sdk-scene3d-live').textContent === "
        "'3D model loaded'"
    )
    page.locator("#arm3d-scene [role=option]").first.focus()
    page.keyboard.press("ArrowDown")
    page.keyboard.press("Enter")
    page.wait_for_function(
        "document.querySelectorAll('[role=option][aria-selected=true]').length === 1"
        " && document.querySelector('.sdk-scene3d-live')"
        ".textContent.endsWith('selected')"
    )
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


def _presentation_snapshot(revision=1, theme="dark", layout="auto"):
    return {
        "schema_version": 2,
        "revision": revision,
        "title": "Presentation Browser Test",
        "theme": theme,
        "layout": layout,
        "data": {},
        "cards": [
            {
                "id": "card-a",
                "title": "Controls",
                "area": "sidebar" if layout == "sidebar-main" else "main",
                "span": 1,
                "components": [
                    {
                        "id": "text-a",
                        "type": "text",
                        "revision": revision,
                        "data": {"text": "Controls ready", "severity": "success"},
                    }
                ],
            },
            {
                "id": "card-b",
                "title": "Telemetry",
                "area": "main",
                "span": 1,
                "components": [
                    {
                        "id": "text-b",
                        "type": "text",
                        "revision": revision,
                        "data": {"text": "Telemetry ready", "severity": "warning"},
                    }
                ],
            },
            {
                "id": "card-c",
                "title": "Events",
                "area": "main",
                "span": 1,
                "components": [
                    {
                        "id": "text-c",
                        "type": "text",
                        "revision": revision,
                        "data": {
                            "text": "event-" + ("x" * 500),
                            "severity": "danger",
                        },
                    },
                    {
                        "id": "table-c",
                        "type": "table",
                        "revision": revision,
                        "data": {
                            "columns": [{"key": "event", "label": "Event"}],
                            "rows": [
                                {
                                    "id": "event-1",
                                    "event": "table-" + ("y" * 500),
                                }
                            ],
                            "empty_state": "",
                        },
                    },
                ],
            },
        ],
    }


def _route_snapshot(page, base_url, state):
    page.route(
        base_url + "/api/state",
        lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(state["snapshot"]),
        ),
    )


def _contrast_ratio(page, foreground_selector, background_selector):
    return page.evaluate(
        """([foregroundSelector, backgroundSelector]) => {
            const parse = value => value.match(/[\\d.]+/g).slice(0, 3).map(Number);
            const luminance = value => {
                const channels = parse(value).map(channel => {
                    const normalized = channel / 255;
                    return normalized <= 0.04045
                        ? normalized / 12.92
                        : Math.pow((normalized + 0.055) / 1.055, 2.4);
                });
                return 0.2126 * channels[0] + 0.7152 * channels[1] +
                    0.0722 * channels[2];
            };
            const foreground = getComputedStyle(
                document.querySelector(foregroundSelector)
            ).color;
            const background = getComputedStyle(
                document.querySelector(backgroundSelector)
            ).backgroundColor;
            const lighter = Math.max(luminance(foreground), luminance(background));
            const darker = Math.min(luminance(foreground), luminance(background));
            return (lighter + 0.05) / (darker + 0.05);
        }""",
        [foreground_selector, background_selector],
    )


def _assert_no_overlaps(boxes):
    for left, right in combinations(boxes, 2):
        separated = (
            left["x"] + left["width"] <= right["x"]
            or right["x"] + right["width"] <= left["x"]
            or left["y"] + left["height"] <= right["y"]
            or right["y"] + right["height"] <= left["y"]
        )
        assert separated


def _capture_viewport_screenshot(page, path, width, height):
    png = page.screenshot(path=path)
    assert path.read_bytes() == png
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    assert int.from_bytes(png[16:20], "big") == width
    assert int.from_bytes(png[20:24], "big") == height


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


def test_presentation_update_preserves_scene3d_selection(
    running_builtin_scene3d_app,
):
    _app, base_url = running_builtin_scene3d_app
    with urlopen(base_url + "/api/state") as response:
        state = {"snapshot": json.load(response)}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        _route_snapshot(page, base_url, state)
        page.goto(base_url + "/")
        page.wait_for_function(
            "document.querySelectorAll('#scene3d-1 [role=option]').length === 5"
        )
        page.locator("#scene3d-1 [role=option]").first.click()
        page.evaluate(
            """window.scenePresentationNodes = {
                card: document.querySelector('#card-1'),
                host: document.querySelector('#scene3d-1'),
                canvas: document.querySelector('#scene3d-1 canvas')
            }"""
        )

        updated = dict(state["snapshot"])
        updated["revision"] += 1
        updated["theme"] = "light"
        updated["layout"] = "grid-2"
        updated["cards"] = [dict(card) for card in updated["cards"]]
        updated["cards"][0]["span"] = 2
        state["snapshot"] = updated
        page.wait_for_function(
            "document.documentElement.dataset.sdkTheme === 'light' && "
            "document.querySelector('#card-1').dataset.sdkSpan === '2'"
        )

        assert page.locator(
            "#scene3d-1 [role=option][aria-selected=true]"
        ).count() == 1
        assert page.evaluate(
            """window.scenePresentationNodes.card ===
                   document.querySelector('#card-1') &&
               window.scenePresentationNodes.host ===
                   document.querySelector('#scene3d-1') &&
               window.scenePresentationNodes.canvas ===
                   document.querySelector('#scene3d-1 canvas')"""
        )
        browser.close()

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
    app, base_url, theme, layout = running_gallery_app
    del app
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.goto(base_url + "/")
        page.wait_for_selector("#card-2")
        assert page.locator("html").get_attribute("data-sdk-theme") == theme
        assert page.locator("#sdk-cards").get_attribute("data-sdk-layout") == layout
        assert page.locator("#card-1").get_attribute("data-sdk-area") == "sidebar"
        assert page.locator("#card-2").get_attribute("data-sdk-span") == "2"
        assert page.locator("#gallery-button").is_visible()
        page.click("#gallery-button")
        assert page.inner_text("#gallery-metric") == "43"
        browser.close()


def test_presentation_live_updates_preserve_nodes_and_source_order(running_app):
    _app, base_url = running_app
    state = {"snapshot": _presentation_snapshot()}
    warnings = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.on(
            "console",
            lambda message: warnings.append(message.text)
            if message.type == "warning"
            else None,
        )
        _route_snapshot(page, base_url, state)
        page.goto(base_url + "/")
        page.wait_for_selector("#text-c")
        page.evaluate(
            """window.presentationNodes = {
                cardA: document.querySelector('#card-a'),
                cardB: document.querySelector('#card-b'),
                textA: document.querySelector('#text-a'),
                textB: document.querySelector('#text-b')
            }"""
        )

        updated = _presentation_snapshot(2, "light", "grid-3")
        updated["cards"] = [updated["cards"][1], updated["cards"][0]]
        updated["cards"][0]["span"] = 3
        updated["cards"][1]["area"] = "sidebar"
        updated["cards"][1]["span"] = 2
        state["snapshot"] = updated

        page.wait_for_function(
            "document.documentElement.dataset.sdkTheme === 'light' && "
            "document.querySelector('#sdk-cards').dataset.sdkLayout === 'grid-3'"
        )
        assert page.locator("#sdk-cards > .sdk-card").evaluate_all(
            "cards => cards.map(card => card.id)"
        ) == ["card-b", "card-a"]
        assert page.locator("#card-b").get_attribute("data-sdk-span") == "3"
        assert page.locator("#card-a").get_attribute("data-sdk-area") == "sidebar"
        assert page.evaluate(
            """window.presentationNodes.cardA === document.querySelector('#card-a') &&
               window.presentationNodes.cardB === document.querySelector('#card-b') &&
               window.presentationNodes.textA === document.querySelector('#text-a') &&
               window.presentationNodes.textB === document.querySelector('#text-b')"""
        )
        assert warnings == []
        browser.close()


def test_presentation_updates_preserve_table_sort_and_focus_order(running_app):
    _app, base_url = running_app
    snapshot = _presentation_snapshot()
    table = snapshot["cards"][2]["components"][1]
    table["data"]["columns"] = [{"id": "event", "label": "Event"}]
    table["data"]["rows"] = [
        {"id": "event-a", "cells": {"event": "Alpha"}},
        {"id": "event-b", "cells": {"event": "Bravo"}},
    ]
    state = {"snapshot": snapshot}

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        _route_snapshot(page, base_url, state)
        page.goto(base_url + "/")
        page.wait_for_selector("#table-c tr")
        page.evaluate(
            """() => {
                const rows = document.querySelectorAll('#table-c tr');
                document.querySelector('#table-c').append(rows[2], rows[1]);
                window.sortedRows = Array.from(
                    document.querySelectorAll('#table-c tr')
                );
                for (const card of document.querySelectorAll('.sdk-card')) {
                    card.tabIndex = 0;
                }
                const start = document.createElement('button');
                start.id = 'focus-start';
                document.querySelector('#sdk-cards').before(start);
            }"""
        )

        updated = json.loads(json.dumps(snapshot))
        updated["revision"] = 2
        updated["theme"] = "light"
        updated["layout"] = "grid-3"
        updated["cards"] = [
            updated["cards"][1],
            updated["cards"][0],
            updated["cards"][2],
        ]
        updated["cards"][0]["span"] = 2
        state["snapshot"] = updated
        page.wait_for_function(
            "document.documentElement.dataset.sdkTheme === 'light' && "
            "document.querySelector('#sdk-cards').dataset.sdkLayout === 'grid-3'"
        )

        assert page.locator("#table-c tr").evaluate_all(
            "rows => rows.slice(1).map(row => row.textContent)"
        ) == ["Bravo", "Alpha"]
        assert page.evaluate(
            """() => window.sortedRows.every(
                (row, index) => row === document.querySelectorAll('#table-c tr')[index]
            )"""
        )
        page.locator("#focus-start").focus()
        focused_cards = []
        for _ in range(3):
            page.keyboard.press("Tab")
            focused_cards.append(page.evaluate("document.activeElement.id"))
        assert focused_cards == ["card-b", "card-a", "card-c"]
        browser.close()


def test_malformed_presentation_fields_report_and_use_defaults(running_app):
    _app, base_url = running_app
    state = {"snapshot": _presentation_snapshot(theme="light", layout="grid-3")}
    warnings = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        page.on(
            "console",
            lambda message: warnings.append(message.text)
            if message.type == "warning"
            else None,
        )
        _route_snapshot(page, base_url, state)
        page.goto(base_url + "/")
        page.wait_for_selector("#card-a")
        assert page.locator("html").get_attribute("data-sdk-theme") == "light"
        assert page.locator("#sdk-cards").get_attribute("data-sdk-layout") == "grid-3"

        malformed = _presentation_snapshot(revision=2)
        malformed["title"] = "Malformed Presentation"
        malformed["theme"] = "neon<script>"
        malformed["layout"] = {"columns": "arbitrary"}
        malformed["cards"][0]["area"] = "floating"
        malformed["cards"][0]["span"] = True
        state["snapshot"] = malformed
        page.wait_for_function(
            "document.querySelector('#sdk-app-title').textContent === "
            "'Malformed Presentation'"
        )

        assert page.locator("html").get_attribute("data-sdk-theme") == "dark"
        assert page.locator("#sdk-cards").get_attribute("data-sdk-layout") == "auto"
        assert page.locator("#card-a").get_attribute("data-sdk-area") == "main"
        assert page.locator("#card-a").get_attribute("data-sdk-span") == "1"
        assert len(warnings) == 4
        assert all("invalid presentation" in warning for warning in warnings)
        assert not page.locator("[class*='neon'], [style*='neon']").count()

        compatible = _presentation_snapshot(revision=3)
        compatible["title"] = "Compatible Presentation"
        compatible.pop("theme")
        compatible.pop("layout")
        for card in compatible["cards"]:
            card.pop("area")
            card.pop("span")
        state["snapshot"] = compatible
        page.wait_for_function(
            "document.querySelector('#sdk-app-title').textContent === "
            "'Compatible Presentation'"
        )
        assert page.locator("html").get_attribute("data-sdk-theme") == "dark"
        assert page.locator("#sdk-cards").get_attribute("data-sdk-layout") == "auto"
        assert page.locator("#card-a").get_attribute("data-sdk-area") == "main"
        assert page.locator("#card-a").get_attribute("data-sdk-span") == "1"
        browser.close()


@pytest.mark.parametrize("theme", ["dark", "light"])
@pytest.mark.parametrize("layout", ["auto", "grid-2", "grid-3", "sidebar-main"])
def test_every_presentation_preset_is_responsive_and_readable(
    running_app, tmp_path, theme, layout
):
    _app, base_url = running_app
    state = {"snapshot": _presentation_snapshot(theme=theme, layout=layout)}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        _route_snapshot(page, base_url, state)
        page.goto(base_url + "/")
        page.wait_for_selector("#card-c")

        desktop_boxes = [
            page.locator(f"#card-{suffix}").bounding_box() for suffix in ("a", "b", "c")
        ]
        _assert_no_overlaps(desktop_boxes)
        assert page.evaluate(
            "document.documentElement.scrollWidth <= document.documentElement.clientWidth"
        )
        _capture_viewport_screenshot(
            page,
            tmp_path / f"{theme}-{layout}-desktop.png",
            1280,
            900,
        )
        assert _contrast_ratio(page, "#sdk-app-title", "body") >= 4.5
        assert (
            page.evaluate(
                """() => {
                    const probe = document.createElement('span');
                    document.body.appendChild(probe);
                    const resolve = name => {
                        probe.style.color = `var(${name})`;
                        return getComputedStyle(probe).color;
                    };
                    const parse = value => value.match(/[\\d.]+/g)
                        .slice(0, 3).map(Number);
                    const luminance = value => {
                        const channels = parse(value).map(channel => {
                            const normalized = channel / 255;
                            return normalized <= 0.04045
                                ? normalized / 12.92
                                : Math.pow((normalized + 0.055) / 1.055, 2.4);
                        });
                        return 0.2126 * channels[0] + 0.7152 * channels[1] +
                            0.0722 * channels[2];
                    };
                    const ratio = (left, right) => {
                        const a = luminance(resolve(left));
                        const b = luminance(resolve(right));
                        return (Math.max(a, b) + 0.05) /
                            (Math.min(a, b) + 0.05);
                    };
                    const pairs = [
                        ['--sdk-text', '--sdk-bg'],
                        ['--sdk-text', '--sdk-card-bg'],
                        ['--sdk-muted', '--sdk-card-bg'],
                        ['--sdk-success', '--sdk-card-bg'],
                        ['--sdk-warning', '--sdk-card-bg'],
                        ['--sdk-danger', '--sdk-card-bg'],
                        ['--sdk-bg', '--sdk-accent'],
                        ['--sdk-bg', '--sdk-accent-hover']
                    ];
                    const minimum = Math.min(...pairs.map(pair => ratio(...pair)));
                    probe.remove();
                    return minimum;
                }"""
            )
            >= 4.5
        )
        if layout == "grid-2":
            assert desktop_boxes[0]["x"] != desktop_boxes[1]["x"]
        elif layout in {"grid-3", "auto"}:
            assert len({box["x"] for box in desktop_boxes}) == 3
        else:
            assert desktop_boxes[0]["x"] != desktop_boxes[1]["x"]
            assert desktop_boxes[1]["x"] == desktop_boxes[2]["x"]

        page.set_viewport_size({"width": 680, "height": 844})
        compact_boxes = [
            page.locator(f"#card-{suffix}").bounding_box() for suffix in ("a", "b", "c")
        ]
        _assert_no_overlaps(compact_boxes)
        assert len({box["x"] for box in compact_boxes}) == 1
        assert page.evaluate(
            "document.documentElement.scrollWidth <= document.documentElement.clientWidth"
        )

        page.set_viewport_size({"width": 390, "height": 844})
        mobile_boxes = [
            page.locator(f"#card-{suffix}").bounding_box() for suffix in ("a", "b", "c")
        ]
        _assert_no_overlaps(mobile_boxes)
        assert len({box["x"] for box in mobile_boxes}) == 1
        assert [box["y"] for box in mobile_boxes] == sorted(
            box["y"] for box in mobile_boxes
        )
        assert page.evaluate(
            "document.documentElement.scrollWidth <= document.documentElement.clientWidth"
        )
        _capture_viewport_screenshot(
            page,
            tmp_path / f"{theme}-{layout}-mobile.png",
            390,
            844,
        )
        browser.close()


def test_auto_span_is_capped_to_available_columns(running_app):
    _app, base_url = running_app
    snapshot = _presentation_snapshot(layout="auto")
    snapshot["cards"][0]["span"] = 3
    state = {"snapshot": snapshot}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(viewport={"width": 800, "height": 700})
        _route_snapshot(page, base_url, state)
        page.goto(base_url + "/")
        page.wait_for_selector("#card-c")
        cards_width = page.locator("#sdk-cards").bounding_box()["width"]
        assert page.locator("#card-a").bounding_box()["width"] <= cards_width
        assert page.evaluate(
            "document.documentElement.scrollWidth <= document.documentElement.clientWidth"
        )
        browser.close()


def test_forced_colors_keeps_focus_and_borders_visible(running_app):
    _app, base_url = running_app
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(forced_colors="active")
        page = context.new_page()
        page.goto(base_url + "/")
        page.wait_for_selector("#sdk-cards > .sdk-card")
        page.evaluate(
            """const button = document.createElement('button');
               button.className = 'sdk-button';
               button.textContent = 'Action';
               document.querySelector('.sdk-card-body').appendChild(button);
               button.focus();"""
        )
        assert page.locator(".sdk-button").evaluate(
            "button => getComputedStyle(button).outlineStyle"
        ) != "none"
        assert page.locator(".sdk-card").evaluate(
            "card => getComputedStyle(card).borderStyle"
        ) != "none"
        context.close()
        browser.close()
