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

import base64
import json
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).parents[2]
VECTORS = json.loads(
    (ROOT / "tests" / "fixtures" / "sse_event_contract.json").read_text()
)
CLIENT_MODULE_URL = (
    "data:text/javascript;base64,"
    + base64.b64encode((ROOT / "assets" / "client.js").read_bytes()).decode("ascii")
)


def test_client_applies_shared_patch_vectors_immutably():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        result = page.evaluate(
            """async ({moduleUrl, vectors}) => {
                const {applyPatch} = await import(moduleUrl);
                const before = JSON.stringify(vectors.snapshots.backend_base);
                const latest = applyPatch(
                    vectors.snapshots.backend_base,
                    vectors.coalesced_patch
                );
                const valid = vectors.operation_vectors.valid.map(
                    ({snapshot, patch, expected}) =>
                        JSON.stringify(applyPatch(snapshot, patch))
                            === JSON.stringify(expected)
                );
                return {
                    latest,
                    inputUnchanged:
                        JSON.stringify(vectors.snapshots.backend_base) === before,
                    frozen: Object.isFrozen(latest)
                        && Object.isFrozen(latest.cards)
                        && Object.isFrozen(latest.cards[0]),
                    valid
                };
            }""",
            {"moduleUrl": CLIENT_MODULE_URL, "vectors": VECTORS},
        )
        browser.close()

    assert result["latest"] == VECTORS["snapshots"]["backend_latest"]
    assert result["inputUnchanged"]
    assert result["frozen"]
    assert all(result["valid"])


def test_client_rejects_revision_gap_and_invalid_operation_vectors():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        rejected = page.evaluate(
            """async ({moduleUrl, vectors}) => {
                const {applyPatch} = await import(moduleUrl);
                const cases = [
                    vectors.revision_gap,
                    ...vectors.operation_vectors.invalid
                ];
                return cases.map(({snapshot, patch}) => {
                    try {
                        applyPatch(snapshot, patch);
                        return false;
                    } catch {
                        return true;
                    }
                });
            }""",
            {"moduleUrl": CLIENT_MODULE_URL, "vectors": VECTORS},
        )
        browser.close()

    assert all(rejected)


def test_client_applies_bounded_time_series_append_delta():
    snapshot = {
        "schema_version": 2,
        "revision": 5,
        "title": "Chart",
        "data": {},
        "cards": [
            {
                "id": "card-1",
                "title": "Trend",
                "components": [
                    {
                        "id": "timeseries-1",
                        "type": "timeseries",
                        "revision": 4,
                        "data": {
                            "title": "Rate",
                            "x_label": "Time",
                            "y_label": "Rate",
                            "status": "live",
                            "x_range": None,
                            "y_range": None,
                            "series": [
                                {
                                    "id": "rate",
                                    "label": "Rate",
                                    "unit": "Hz",
                                    "color": "#0076CE",
                                    "samples": [[1, 1.0], [2, None]],
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }
    patch = {
        "schema_version": 1,
        "base_revision": 5,
        "revision": 7,
        "changes": [
            {
                "op": "append-timeseries",
                "card_id": "card-1",
                "component_id": "timeseries-1",
                "component_revision": 7,
                "series": [{"id": "rate", "samples": [[3, 2.0], [4, None]]}],
            }
        ],
    }
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page()
        result = page.evaluate(
            """async ({moduleUrl, snapshot, patch}) => {
                const {applyPatch} = await import(moduleUrl);
                const next = applyPatch(snapshot, patch);
                const component = next.cards[0].components[0];
                const invalid = JSON.parse(JSON.stringify(patch));
                invalid.changes[0].series[0].samples[0][0] = 2;
                let rejected = false;
                try { applyPatch(snapshot, invalid); } catch { rejected = true; }
                return {
                    samples: component.data.series[0].samples,
                    componentRevision: component.revision,
                    frozen: Object.isFrozen(next)
                        && Object.isFrozen(component.data.series[0].samples),
                    rejected
                };
            }""",
            {"moduleUrl": CLIENT_MODULE_URL, "snapshot": snapshot, "patch": patch},
        )
        browser.close()
    assert result == {
        "samples": [[1, 1.0], [2, None], [3, 2.0], [4, None]],
        "componentRevision": 7,
        "frozen": True,
        "rejected": True,
    }
