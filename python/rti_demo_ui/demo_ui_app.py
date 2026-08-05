"""DemoUiApp: model ownership and local HTTP lifecycle.

See docs/architecture.md §3, §5, §7.2, §8.
"""

from __future__ import annotations

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path
from typing import Callable, Dict, Optional
from urllib.parse import unquote

from .components import Card
from .types import require_non_empty, require_positive_int

_ASSET_ROUTES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/sdk/index.html": ("index.html", "text/html; charset=utf-8"),
    "/sdk/runtime.js": ("runtime.js", "application/javascript; charset=utf-8"),
    "/sdk/theme.css": ("theme.css", "text/css; charset=utf-8"),
}

_MIME_TYPES = {
    ".css": "text/css; charset=utf-8",
    ".gif": "image/gif",
    ".glb": "application/octet-stream",
    ".gltf": "application/json; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".ico": "image/x-icon",
    ".jpeg": "image/jpeg",
    ".jpg": "image/jpeg",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".ttf": "font/ttf",
    ".txt": "text/plain; charset=utf-8",
    ".webp": "image/webp",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
}


def _load_assets() -> Dict[str, bytes]:
    assets = {}
    asset_package = resources.files("rti_demo_ui").joinpath("_assets")
    for route, (filename, _content_type) in _ASSET_ROUTES.items():
        resource = asset_package.joinpath(filename)
        try:
            assets[route] = resource.read_bytes()
        except (FileNotFoundError, IsADirectoryError) as error:
            raise RuntimeError(
                f"DemoUiApp: missing required asset rti_demo_ui/_assets/{filename}"
            ) from error
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
    """Internal model state shared by DemoUiApp, Card, and Scene2DViewport."""

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
            raise RuntimeError("DemoUiApp: model is stopped")

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
    app: "DemoUiApp"

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

    def _send_static(self, path: str) -> None:
        asset = self.app._resolve_static_asset(path)
        if asset is None:
            self.app._send_static_not_found(self)
            return
        file_path, content_type = asset
        try:
            body = file_path.read_bytes()
        except OSError:
            self.app._send_static_not_found(self)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - stdlib signature
        path = self.path.split("?", 1)[0]
        if path == "/" and self.app._static_root is not None:
            self._send_static("/index.html")
        elif path in _ASSET_ROUTES:
            self._send_asset(path)
        elif path == "/api/health":
            self._send_json(200, {"status": "ok"})
        elif path == "/api/state":
            self._send_json(200, self.app._model.snapshot())
        elif path == "/api" or path.startswith("/api/"):
            self._send_json(404, {"error": "not found"})
        elif path == "/sdk" or path.startswith("/sdk/"):
            self.app._send_static_not_found(self)
        elif self.app._static_root is not None:
            self._send_static(path)
        else:
            self._send_json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        self._send_json(405, {"error": "method not allowed"})

    do_PUT = do_POST
    do_DELETE = do_POST
    do_PATCH = do_POST


class _ReusableThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True


class DemoUiApp:
    """Model ownership and local HTTP lifecycle for one SDK demo process."""

    def __init__(
        self,
        title: str,
        port: int = 8080,
        host: str = "0.0.0.0",
        static_root: str | os.PathLike[str] | None = None,
    ) -> None:
        require_non_empty(title, "title", "DemoUiApp: ")
        require_non_empty(host, "host", "DemoUiApp: ")
        if not (1 <= port <= 65535):
            raise ValueError("DemoUiApp: port must be between 1 and 65535")
        self._static_root = self._canonical_static_root(static_root)
        self._model = _Model(title)
        self._assets = _load_assets()
        self._host = host
        self._port = port
        self._server: Optional[ThreadingHTTPServer] = None
        self._lifecycle_lock = threading.Lock()
        self._timers = []
        self._stopped = False

    @staticmethod
    def _canonical_static_root(
        static_root: str | os.PathLike[str] | None,
    ) -> Optional[Path]:
        if static_root is None or os.fspath(static_root) == "":
            return None
        try:
            root = Path(static_root).resolve(strict=True)
        except (OSError, RuntimeError) as error:
            raise ValueError(
                "DemoUiApp: static_root must be an existing directory"
            ) from error
        if not root.is_dir():
            raise ValueError("DemoUiApp: static_root must be an existing directory")
        if not (root / "index.html").is_file():
            raise ValueError("DemoUiApp: static_root must contain a regular index.html")
        return root

    def _resolve_static_asset(self, request_path: str) -> Optional[tuple[Path, str]]:
        if self._static_root is None:
            return None
        try:
            decoded = unquote(request_path, encoding="utf-8", errors="strict")
        except UnicodeDecodeError:
            return None
        if "\x00" in decoded or not decoded.startswith("/"):
            return None
        if decoded == "/":
            relative_name = "index.html"
        else:
            relative_name = decoded[1:]
            if relative_name.startswith("/") or relative_name == "":
                return None
        candidate = self._static_root / relative_name
        try:
            resolved = candidate.resolve(strict=False)
        except (OSError, RuntimeError):
            return None
        if resolved != self._static_root and self._static_root not in resolved.parents:
            return None
        if not resolved.is_file():
            return None
        content_type = _MIME_TYPES.get(
            resolved.suffix.lower(), "application/octet-stream"
        )
        return resolved, content_type

    @staticmethod
    def _send_static_not_found(handler: _RequestHandler) -> None:
        body = b"not found"
        handler.send_response(404)
        handler.send_header("Content-Type", "text/plain; charset=utf-8")
        handler.send_header("Content-Length", str(len(body)))
        handler.send_header("X-Content-Type-Options", "nosniff")
        handler.send_header("Cache-Control", "no-cache")
        handler.end_headers()
        handler.wfile.write(body)

    def add_card(self, title: str) -> Card:
        with self._model.lock:
            self._model.ensure_running()
            card_id = self._model.next_card_id()
            card = Card(self._model, card_id, title)
            self._model.cards.append(card)
            self._model.bump_revision_locked()
        return card

    def add_timer(self, interval_ms: int, callback: Callable[[], None]) -> TimerHandle:
        require_positive_int(interval_ms, "interval_ms", "DemoUiApp: ")
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
        with self._lifecycle_lock:
            if self._stopped:
                return
            server = _ReusableThreadingHTTPServer((self._host, self._port), handler)
            self._server = server
        if self._stopped:
            server.server_close()
            with self._lifecycle_lock:
                self._server = None
            return
        actual_port = server.server_address[1]
        print(f"RTI Demo UI listening on http://{self._host}:{actual_port}/")
        try:
            server.serve_forever(poll_interval=0.2)
        finally:
            server.server_close()
            with self._lifecycle_lock:
                self._server = None

    def stop(self) -> None:
        with self._lifecycle_lock:
            if self._stopped:
                return
            self._stopped = True
            server = self._server
        self._model.stop()
        if server is not None:
            server.shutdown()
        for handle in self._timers:
            handle.cancel()

    def __del__(self) -> None:
        try:
            self.stop()
        except Exception:
            pass
