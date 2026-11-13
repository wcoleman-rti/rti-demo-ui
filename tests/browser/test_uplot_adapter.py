#
# (c) 2026 Copyright, Real-Time Innovations, Inc.  All rights reserved.
#
# RTI grants Licensee a license to use, modify, compile, and create derivative
# works of the Software.  Licensee has the right to distribute object form
# only for use with RTI products.  The Software is provided "as is", with no
# warranty of any type, including any warranty for fitness for any purpose.
# RTI is under no obligation to maintain or support the Software.  RTI shall
# not be liable for any incidental or consequential damages arising out of
# the use or inability to use the software.
#

import json
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).parents[2]


def chart_snapshot():
    return {
        "schema_version": 2,
        "revision": 2,
        "title": "Chart Test",
        "theme": "dark",
        "layout": "auto",
        "data": {},
        "cards": [
            {
                "id": "card-1",
                "title": "Trend",
                "area": "main",
                "span": 1,
                "components": [
                    {
                        "id": "timeseries-1",
                        "type": "timeseries",
                        "revision": 2,
                        "data": {
                            "title": "Rate",
                            "x_label": "Time (UTC)",
                            "y_label": "Rate",
                            "status": "live",
                            "x_range": None,
                            "y_range": None,
                            "series": [
                                {
                                    "id": "rate-a",
                                    "label": "Rate A",
                                    "unit": "Hz",
                                    "color": "var(--sdk-accent)",
                                    "samples": [[1760000000000, 1.0], [1760000000100, None]],
                                },
                                {
                                    "id": "rate-b",
                                    "label": "Rate B",
                                    "unit": "Hz",
                                    "color": "#F4B942",
                                    "samples": [[1760000000000, 2.0]],
                                },
                            ],
                        },
                    }
                ],
            }
        ],
    }


def test_opt_in_uplot_adapter_renders_status_theme_and_disposes():
    current = {"snapshot": chart_snapshot()}
    assets = {
        "/sdk/runtime.js": (ROOT / "assets/runtime.js", "application/javascript"),
        "/sdk/client.js": (ROOT / "assets/client.js", "application/javascript"),
        "/sdk/theme.css": (ROOT / "assets/theme.css", "text/css"),
        "/sdk/adapters/uplot/runtime.js": (
            ROOT / "adapters/uplot/assets/runtime.js",
            "application/javascript",
        ),
        "/sdk/adapters/uplot/theme.css": (
            ROOT / "adapters/uplot/assets/theme.css",
            "text/css",
        ),
    }
    manifest = {
        "schema_version": 1,
        "adapters": [
            {
                "name": "uplot",
                "version": "1",
                "components": ["timeseries"],
                "module": "/sdk/adapters/uplot/runtime.js",
                "styles": ["/sdk/adapters/uplot/theme.css"],
            }
        ],
    }

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()

        def route_request(route):
            path = urlparse(route.request.url).path
            if path == "/":
                route.fulfill(
                    status=200,
                    content_type="text/html",
                    body=(
                        "<!doctype html><html><head>"
                        '<link rel="stylesheet" href="/sdk/theme.css">'
                        "</head><body><h1 id='sdk-app-title'></h1>"
                        "<div id='sdk-connection-banner'></div>"
                        "<div id='sdk-cards'></div>"
                        "<script>window.eventSourceCount = 0; window.EventSource = class {"
                        "constructor() { window.eventSourceCount += 1; this.listeners = {}; this.closed = false;"
                        "this.timer = setInterval(() => this.poll(), 50);"
                        "setTimeout(() => { if (this.onopen) this.onopen(); this.poll(); }, 0); }"
                        "addEventListener(name, callback) { this.listeners[name] = callback; }"
                        "async poll() { if (this.closed) return; const response = await fetch('/api/state');"
                        "const snapshot = await response.json();"
                        "if (this.listeners.snapshot) this.listeners.snapshot({data: JSON.stringify(snapshot)}); }"
                        "close() { this.closed = true; clearInterval(this.timer); }"
                        "};</script>"
                        '<script type="module" src="/sdk/runtime.js"></script>'
                        "</body></html>"
                    ),
                )
            elif path in assets:
                asset, content_type = assets[path]
                route.fulfill(
                    status=200, content_type=content_type, body=asset.read_bytes()
                )
            elif path == "/sdk/adapters/manifest.json":
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps(manifest),
                )
            elif path == "/api/state":
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps(current["snapshot"]),
                )
            else:
                route.fulfill(status=404, body="not found")

        page.route("http://uplot.test/**", route_request)
        page.goto("http://uplot.test/")
        page.wait_for_function(
            "() => document.querySelectorAll('.sdk-timeseries-plot canvas').length === 2",
            timeout=5000,
        )
        page.wait_for_function("() => window.eventSourceCount === 1", timeout=5000)
        assert page.locator(".sdk-timeseries-status").inner_text() == "Live data"
        assert page.locator(".sdk-timeseries-values tbody tr").count() == 2

        current["snapshot"]["theme"] = "light"
        current["snapshot"]["revision"] += 1
        component = current["snapshot"]["cards"][0]["components"][0]
        component["revision"] += 1
        component["data"]["status"] = "stale"
        page.wait_for_function(
            "() => document.documentElement.dataset.sdkTheme === 'light'",
            timeout=5000,
        )
        page.wait_for_function(
            "() => document.querySelector('.sdk-timeseries-status')?.textContent.includes('Stale')",
            timeout=5000,
        )

        current["snapshot"]["revision"] += 1
        current["snapshot"]["cards"][0]["components"] = []
        page.wait_for_function(
            "() => document.querySelectorAll('.sdk-timeseries-plot canvas').length === 0",
            timeout=5000,
        )
        assert page.locator("#timeseries-1").count() == 0
        browser.close()
