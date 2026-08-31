import argparse
import asyncio
import json
import threading
from pathlib import Path

from rti_demo_ui import DemoUiApp
from rti_demo_ui_native import run_native


EXPECTED_CHECKS = {
    "snapshot",
    "sse",
    "dynamic_import",
    "runtime3d_import",
    "module_worker",
    "theme_asset",
    "persistent_storage",
    "canvas",
    "webgl",
    "keyboard_focus",
    "resize_observation",
    "navigation_policy",
    "command_origin",
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--application-id", required=True)
    parser.add_argument("--expected", required=True)
    parser.add_argument("--write", required=True)
    parser.add_argument("--static-root", required=True, type=Path)
    args = parser.parse_args()

    report_event = threading.Event()
    report = {}
    app = DemoUiApp("Native Phase 2 conformance", static_root=args.static_root)
    app.set_data(
        {
            "native_storage_key": "phase2-production",
            "native_storage_expected": args.expected,
            "native_storage_write": args.write,
        }
    )

    def record_report(payload):
        report.update(payload)
        report_event.set()
        return {"recorded": True}

    app.register_command("spike-report", {"type": "object"}, record_report)
    app.register_command(
        "spike-origin",
        {"type": "object"},
        lambda payload: {"origin": payload["origin"]},
    )

    async def wait_for_report(_app):
        if not await asyncio.to_thread(report_event.wait, 20):
            raise TimeoutError("production conformance report timed out")

    run_native(
        app,
        application_id=args.application_id,
        async_main=wait_for_report,
    )

    results = report.get("results", {})
    missing = EXPECTED_CHECKS.difference(results)
    failed = {
        name: result
        for name, result in results.items()
        if not result.get("passed", False)
    }
    if missing or failed:
        raise RuntimeError(
            f"production conformance failed: missing={sorted(missing)} failed={failed}"
        )
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
