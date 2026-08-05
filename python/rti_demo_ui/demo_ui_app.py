"""DemoUiApp model ownership and native asyncio HTTP lifecycle."""

from __future__ import annotations

import asyncio
import json
import os
import threading
from importlib import resources
from pathlib import Path
from typing import Dict, Optional
from urllib.parse import unquote

from aiohttp import web

from .components import Card
from .types import require_non_empty

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


def _json_response(status: int, payload: dict) -> web.Response:
    body = json.dumps(payload, allow_nan=False).encode("utf-8")
    return web.Response(
        status=status,
        body=body,
        headers={
            "Content-Type": "application/json",
            "Content-Length": str(len(body)),
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
    )


def _asset_response(body: bytes, content_type: str) -> web.Response:
    return web.Response(
        status=200,
        body=body,
        headers={
            "Content-Type": content_type,
            "Content-Length": str(len(body)),
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-cache",
        },
    )


def _static_not_found_response() -> web.Response:
    body = b"not found"
    return web.Response(
        status=404,
        body=body,
        headers={
            "Content-Type": "text/plain; charset=utf-8",
            "Content-Length": str(len(body)),
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-cache",
        },
    )


class _Model:
    """Internal model state shared by DemoUiApp, Card, and Scene2DViewport."""

    def __init__(self, title: str) -> None:
        self.title = title
        self.revision = 0
        self.cards = []
        self._running = True
        self._owner_loop = None
        self._owner_thread_id = None
        self._next_card_id = 1
        self._next_scene_id = 1

    def set_owner(self, loop) -> None:
        self._owner_loop = loop
        self._owner_thread_id = threading.get_ident()

    def check_owner(self) -> None:
        if self._owner_thread_id is None:
            return
        if threading.get_ident() != self._owner_thread_id:
            raise RuntimeError(
                "DemoUiApp: model access must run on the owner event loop; "
                "use loop.call_soon_threadsafe"
            )
        try:
            current_loop = asyncio.get_running_loop()
        except RuntimeError:
            current_loop = None
        if current_loop is not self._owner_loop:
            raise RuntimeError(
                "DemoUiApp: model access must run on the owner event loop; "
                "use loop.call_soon_threadsafe"
            )

    def ensure_running(self) -> None:
        if not self._running:
            raise RuntimeError("DemoUiApp: model is stopped")

    def stop(self) -> None:
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
        self.check_owner()
        self.ensure_running()
        return {
            "schema_version": 1,
            "revision": self.revision,
            "title": self.title,
            "cards": [card.to_dict() for card in self.cards],
        }


class DemoUiApp:
    """Model ownership and local asyncio HTTP lifecycle for one SDK process."""

    _NEW = "NEW"
    _STARTING = "STARTING"
    _RUNNING = "RUNNING"
    _STOPPING = "STOPPING"
    _STOPPED = "STOPPED"

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
        self._state = self._NEW
        self._run_started = False
        self._owner_loop = None
        self._owner_thread_id = None
        self._shutdown_event = None
        self._ready_event = asyncio.Event()
        self._cleanup_complete = None
        self._cleanup_task = None
        self._runner = None
        self._site = None

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

    def _application(self) -> web.Application:
        application = web.Application()
        application.router.add_route("*", "/{path:.*}", self._handle_request)
        return application

    async def _handle_request(self, request: web.Request) -> web.StreamResponse:
        if request.method != "GET":
            return _json_response(405, {"error": "method not allowed"})

        path = request.raw_path.split("?", 1)[0]
        if path == "/" and self._static_root is not None:
            return self._static_response("/index.html")
        if path in _ASSET_ROUTES:
            _filename, content_type = _ASSET_ROUTES[path]
            return _asset_response(self._assets[path], content_type)
        if path == "/api/health":
            return _json_response(200, {"status": "ok"})
        if path == "/api/state":
            return _json_response(200, self._model.snapshot())
        if path == "/api" or path.startswith("/api/"):
            return _json_response(404, {"error": "not found"})
        if path == "/sdk" or path.startswith("/sdk/"):
            return _static_not_found_response()
        if self._static_root is not None:
            return self._static_response(path)
        return _json_response(404, {"error": "not found"})

    def _static_response(self, path: str) -> web.StreamResponse:
        asset = self._resolve_static_asset(path)
        if asset is None:
            return _static_not_found_response()
        file_path, content_type = asset
        try:
            content_length = file_path.stat().st_size
        except OSError:
            return _static_not_found_response()
        return web.FileResponse(
            path=file_path,
            headers={
                "Content-Type": content_type,
                "Content-Length": str(content_length),
                "X-Content-Type-Options": "nosniff",
                "Cache-Control": "no-cache",
            },
        )

    async def _wait_until_ready(self) -> None:
        await self._ready_event.wait()

    async def _cleanup_impl(self) -> None:
        try:
            if self._runner is not None:
                await self._runner.cleanup()
        finally:
            self._runner = None
            self._site = None
            self._shutdown_event = None
            if self._ready_event is not None:
                self._ready_event.clear()
            self._model.stop()
            self._state = self._STOPPED
            if self._cleanup_complete is not None:
                self._cleanup_complete.set()

    async def _cleanup(self) -> None:
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_impl())
        await asyncio.shield(self._cleanup_task)

    def _request_stop(self) -> None:
        if self._state == self._NEW:
            self._model.stop()
            self._state = self._STOPPED
        elif self._state in (self._STARTING, self._RUNNING):
            self._model.stop()
            self._state = self._STOPPING
            if self._shutdown_event is not None:
                self._shutdown_event.set()

    async def _stop_on_owner_loop(self) -> None:
        self._request_stop()
        if self._cleanup_complete is not None and self._state != self._STOPPED:
            await self._cleanup_complete.wait()

    def add_card(self, title: str) -> Card:
        self._model.check_owner()
        self._model.ensure_running()
        card_id = self._model.next_card_id()
        card = Card(self._model, card_id, title)
        self._model.cards.append(card)
        self._model.bump_revision_locked()
        return card

    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        if self._run_started:
            raise RuntimeError("DemoUiApp: run() may only be called once")
        self._run_started = True
        if self._state == self._STOPPED:
            return
        self._owner_loop = loop
        self._owner_thread_id = threading.get_ident()
        self._model.set_owner(loop)
        self._state = self._STARTING
        self._shutdown_event = asyncio.Event()
        self._cleanup_complete = asyncio.Event()
        cancelled = False
        try:
            self._runner = web.AppRunner(self._application(), handle_signals=False)
            await self._runner.setup()
            self._site = web.TCPSite(self._runner, self._host, self._port)
            await self._site.start()
            sockets = self._site._server.sockets
            actual_port = sockets[0].getsockname()[1]
            if self._state == self._STOPPING:
                return
            self._state = self._RUNNING
            self._ready_event.set()
            print(f"RTI Demo UI listening on http://{self._host}:{actual_port}/")
            await self._shutdown_event.wait()
        except asyncio.CancelledError:
            cancelled = True
            self._request_stop()
        finally:
            if self._state != self._STOPPED:
                self._state = self._STOPPING
            await self._cleanup()
        if cancelled:
            raise asyncio.CancelledError

    async def stop(self) -> None:
        owner_loop = self._owner_loop
        if owner_loop is None:
            self._request_stop()
            return
        current_loop = asyncio.get_running_loop()
        if current_loop is owner_loop:
            await self._stop_on_owner_loop()
            return
        future = asyncio.run_coroutine_threadsafe(
            self._stop_on_owner_loop(), owner_loop
        )
        await asyncio.shield(asyncio.wrap_future(future))
