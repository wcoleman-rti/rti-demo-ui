#!/usr/bin/env python3
"""Phase 0 pywebview host; experimental and not a public SDK API."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import queue
import signal
import socket
import threading
import time
from pathlib import Path
from urllib.parse import urlencode

from rti_demo_ui import DemoUiApp

EXPECTED_CHECKS = {
    "canvas",
    "command_origin",
    "dynamic_import",
    "keyboard_focus",
    "module_worker",
    "navigation_policy",
    "persistent_storage",
    "resize_observation",
    "runtime3d_import",
    "snapshot",
    "sse",
    "theme_asset",
    "webgl",
}


def validate_report(payload: dict) -> None:
    if set(payload) != {"results"} or not isinstance(payload["results"], dict):
        raise ValueError("conformance report must contain only an object named results")
    if set(payload["results"]) != EXPECTED_CHECKS:
        raise ValueError("conformance report check set is incomplete")
    for name, result in payload["results"].items():
        if (
            not isinstance(result, dict)
            or set(result) != {"passed", "evidence"}
            or not isinstance(result["passed"], bool)
            or not isinstance(result["evidence"], str)
            or not result["evidence"]
        ):
            raise ValueError(f"conformance result {name!r} is invalid")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=0)
    parser.add_argument("--signal-after", type=float)
    parser.add_argument("--storage-expected", default="__absent__")
    parser.add_argument("--storage-key", default="rti-demo-ui-native-spike")
    parser.add_argument("--storage-path", type=Path, required=True)
    parser.add_argument("--storage-write", default="phase-zero")
    parser.add_argument("--timeout", type=float, default=15.0)
    parser.add_argument("--wait-for-close", action="store_true")
    args = parser.parse_args()

    import webview

    root = Path(__file__).resolve().parent / "conformance"
    report_event = threading.Event()
    signal_event = threading.Event()
    close_event = threading.Event()
    ready_queue: queue.Queue[tuple[asyncio.AbstractEventLoop, str]] = queue.Queue()
    report: dict = {}
    owner_thread_id = None
    app = DemoUiApp("Native webview spike", args.port, static_root=root)

    def record_report(payload: dict) -> dict:
        validate_report(payload)
        report.update(payload)
        report_event.set()
        return {"recorded": True}

    app.register_command("spike-report", {"type": "object"}, record_report)
    app.register_command(
        "spike-origin", {"type": "object"}, lambda payload: {"origin": payload["origin"]}
    )

    async def owner_main() -> None:
        nonlocal owner_thread_id
        run_task = asyncio.create_task(app.run())
        ready = await app.wait_until_ready()
        owner_thread_id = threading.get_ident()
        app.set_data({"owner_thread": owner_thread_id})
        ready_queue.put((asyncio.get_running_loop(), ready.url))
        await run_task

    server_error: list[BaseException] = []

    def run_server() -> None:
        try:
            asyncio.run(owner_main())
        except BaseException as error:
            server_error.append(error)
            report_event.set()

    server_thread = threading.Thread(
        target=run_server, name="native-spike-python-server"
    )
    server_thread.start()
    owner_loop, url = ready_queue.get(timeout=args.timeout)
    port = int(url.rsplit(":", 1)[1])
    profile = args.storage_path.resolve()
    profile.mkdir(parents=True, exist_ok=True)
    query = urlencode(
        {
            "storage_expected": args.storage_expected,
            "storage_key": args.storage_key,
            "storage_write": args.storage_write,
        }
    )
    window = webview.create_window(
        "Native webview spike",
        f"{url}/?{query}",
        width=1280,
        height=800,
        resizable=True,
    )
    window.events.closed += lambda: close_event.set()

    def install_navigation_policy() -> None:
        def find_webview(widget):
            if widget.__gtype__.name == "WebKitWebView":
                return widget
            get_children = getattr(widget, "get_children", None)
            if get_children:
                for child in get_children():
                    found = find_webview(child)
                    if found is not None:
                        return found
            return None

        browser = find_webview(window.native)
        if browser is None:
            raise RuntimeError("WebKitWebView native child was not found")

        def block_external_navigation(_browser, decision, _decision_type):
            get_action = getattr(decision, "get_navigation_action", None)
            if get_action is None:
                return False
            uri = get_action().get_request().get_uri()
            if uri == url or uri.startswith(f"{url}/"):
                return False
            decision.ignore()
            return True

        browser.connect("decide-policy", block_external_navigation)

    window.events.before_show += install_navigation_policy

    previous_sigint = signal.getsignal(signal.SIGINT)
    signal.signal(signal.SIGINT, lambda _signum, _frame: signal_event.set())

    def close_when_done() -> None:
        if args.wait_for_close:
            while (
                not close_event.wait(0.05)
                and not signal_event.is_set()
                and not server_error
            ):
                pass
            if signal_event.is_set() or server_error:
                window.destroy()
            return
        deadline = time.monotonic() + args.timeout
        while time.monotonic() < deadline:
            close_requested = (
                signal_event.is_set()
                if args.signal_after is not None
                else report_event.wait(0.05)
            )
            if close_requested:
                time.sleep(0.1)
                window.destroy()
                return
            time.sleep(0.05)
        window.destroy()

    closer = threading.Thread(target=close_when_done, name="native-spike-closer")
    closer.start()
    if args.signal_after is not None:
        signal_timer = threading.Timer(
            args.signal_after, lambda: os.kill(os.getpid(), signal.SIGINT)
        )
        signal_timer.daemon = True
        signal_timer.start()

    try:
        webview.start(
            gui="gtk", debug=False, private_mode=False, storage_path=str(profile)
        )
    finally:
        signal.signal(signal.SIGINT, previous_sigint)
        stop_future = asyncio.run_coroutine_threadsafe(app.stop(), owner_loop)
        stop_future.result(timeout=args.timeout)
        server_thread.join(timeout=args.timeout)
        closer.join(timeout=args.timeout)

    with socket.socket() as probe:
        probe.settimeout(0.5)
        port_released = probe.connect_ex(("127.0.0.1", port)) != 0

    trace = {
        "backend": "python",
        "close_observed": close_event.is_set(),
        "command_report_received": report_event.is_set() and bool(report),
        "gui_thread": threading.main_thread().ident,
        "owner_thread": owner_thread_id,
        "owner_loop_off_main_thread": owner_thread_id != threading.main_thread().ident,
        "port_released": port_released,
        "profile_path": str(profile),
        "profile_persisted": profile.is_dir(),
        "renderer": webview.renderer,
        "report": report,
        "server_error": repr(server_error[0]) if server_error else None,
        "server_joined": not server_thread.is_alive(),
        "signal_observed": signal_event.is_set(),
    }
    print(json.dumps(trace, sort_keys=True))
    report_passed = bool(report) and all(
        result["passed"] for result in report["results"].values()
    )
    return (
        0
        if trace["close_observed"]
        and trace["server_joined"]
        and trace["port_released"]
        and trace["profile_persisted"]
        and (
            args.signal_after is not None
            or (trace["command_report_received"] and report_passed)
        )
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
