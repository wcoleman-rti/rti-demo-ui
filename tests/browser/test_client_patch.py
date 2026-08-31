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
