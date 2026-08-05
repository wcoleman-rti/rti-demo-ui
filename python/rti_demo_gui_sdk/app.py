"""CoreApp: model ownership and local HTTP lifecycle.

See docs/architecture.md §3, §5, §7.2, §8.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable, Dict, Optional

from .components import Card
from .types import require_non_empty, require_positive_int

_ASSETS_DIR = Path(__file__).resolve().parents[2] / "assets"

_ASSET_ROUTES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/runtime.js": ("runtime.js", "application/javascript; charset=utf-8"),
    "/theme.css": ("theme.css", "text/css; charset=utf-8"),
    "/gallery": ("gallery.html", "text/html; charset=utf-8"),
}


def _load_assets() -> Dict[str, bytes]:
    assets = {}
    for route, (filename, _content_type) in _ASSET_ROUTES.items():
        path = _ASSETS_DIR / filename
        if not path.is_file():
            raise RuntimeError(f"CoreApp: missing required asset {path}")
        assets[route] = path.read_bytes()
    return assets


class TimerHandle:
    """Cancelable handle for an SDK-owned periodic timer."""

    def __init__(self, thread: threading.Thread, stop_event: threading.Event) -> None:
        self._thread = thread
        self._stop_event = stop_event

    def cancel(self) -> None:
        self._stop_event.set()
        if threading.current_thread() is not self._thread:
            self._thread.join()


class _Model:
    """Internal model state shared by CoreApp, Card, and Scene2DViewport."""

    def __init__(self, title: str) -> None:
        self.lock = threading.RLock()
        self.title = title
        self.revision = 0
        self.cards = []
        self._running = True
        self._next_card_id = 1
        self._next_scene_id = 1

    def ensure_running(self) -> None:
        if not self._running:
            raise RuntimeError("CoreApp: model is stopped")

    def stop(self) -> None:
        with self.lock:
            self._running = False

    def bump_revision_locked(self) -> None:
        self.revision += 1

    def next_card_id(self) -> str:
        card_id = f"card-{self._next_card_id}"
        self._next_card_id += 1
        return card_id

    def next_scene_id(self) -> str:
        scene_id = f"scene-{self._next_scene_id}"
        self._next_scene_id += 1
        return scene_id

    def snapshot(self) -> dict:
        with self.lock:
            return {
                "schema_version": 1,
                "revision": self.revision,
                "title": self.title,
                "cards": [card.to_dict() for card in self.cards],
            }


class _RequestHandler(BaseHTTPRequestHandler):
    app: "CoreApp"

    def log_message(self, format, *args):  # noqa: A002 - stdlib signature
        pass

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_asset(self, route: str) -> None:
        body = self.app._assets[route]
        content_type = _ASSET_ROUTES[route][1]
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - stdlib signature
        path = self.path.split("?", 1)[0]
        if path in _ASSET_ROUTES:
            self._send_asset(path)
        elif path == "/api/health":
            self._send_json(200, {"status": "ok"})
        elif path == "/api/state":
            self._send_json(200, self.app._model.snapshot())
        else:
            self._send_json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        self._send_json(405, {"error": "method not allowed"})

    do_PUT = do_POST
    do_DELETE = do_POST
    do_PATCH = do_POST


class CoreApp:
    """Model ownership and local HTTP lifecycle for one SDK demo process."""

    def __init__(self, title: str, port: int = 8080, host: str = "0.0.0.0") -> None:
        require_non_empty(title, "title", "CoreApp: ")
        require_non_empty(host, "host", "CoreApp: ")
        if not (1 <= port <= 65535):
            raise ValueError("CoreApp: port must be between 1 and 65535")
        self._model = _Model(title)
        self._assets = _load_assets()
        self._host = host
        self._port = port
        self._server: Optional[ThreadingHTTPServer] = None
        self._timers = []
        self._stopped = False

    def add_card(self, title: str) -> Card:
        with self._model.lock:
            self._model.ensure_running()
            card_id = self._model.next_card_id()
            card = Card(self._model, card_id, title)
            self._model.cards.append(card)
            self._model.bump_revision_locked()
        return card

    def add_timer(self, interval_ms: int, callback: Callable[[], None]) -> TimerHandle:
        require_positive_int(interval_ms, "interval_ms", "CoreApp: ")
        with self._model.lock:
            self._model.ensure_running()
        stop_event = threading.Event()

        def _run() -> None:
            interval_s = interval_ms / 1000.0
            while not stop_event.wait(interval_s):
                try:
                    callback()
                except Exception:
                    return

        thread = threading.Thread(target=_run, daemon=True)
        handle = TimerHandle(thread, stop_event)
        self._timers.append(handle)
        thread.start()
        return handle

    def run(self) -> None:
        handler = type("_BoundHandler", (_RequestHandler,), {"app": self})
        self._server = ThreadingHTTPServer((self._host, self._port), handler)
        actual_port = self._server.server_address[1]
        print(f"RTI Demo GUI SDK listening on http://{self._host}:{actual_port}/")
        try:
            self._server.serve_forever(poll_interval=0.2)
        finally:
            self._server.server_close()

    def stop(self) -> None:
        if self._stopped:
            return
        self._stopped = True
        self._model.stop()
        if self._server is not None:
            self._server.shutdown()
        for handle in self._timers:
            handle.cancel()

    def __del__(self) -> None:
        try:
            self.stop()
        except Exception:
            pass
