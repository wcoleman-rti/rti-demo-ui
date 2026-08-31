"""DemoUiApp model ownership and native asyncio HTTP lifecycle."""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import os
import secrets
import threading
from copy import deepcopy
from dataclasses import dataclass
from importlib import resources
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import unquote
from urllib.parse import unquote_to_bytes

from aiohttp import ClientConnectionError, web

from .components import Card
from .commands import COMMAND_NAME, Command, CommandConfirmation, CommandSchema
from .types import copy_json_value, require_non_empty

_COMMAND_BODY_LIMIT = 64 * 1024
_COMMAND_CAPABILITY_HEADER = "X-RTI-Demo-Command-Capability"
_COMMAND_PATH_PREFIX = "/api/commands/"
_SSE_HEARTBEAT_INTERVAL = 15.0
_SSE_MAX_STREAMS = 16
_SSE_PUBLICATION_INTERVAL = 1.0 / 30.0
_SSE_RETRY = b"retry: 1000\n\n"
_SSE_WRITE_TIMEOUT = 5.0
_logger = logging.getLogger(__name__)

_ASSET_ROUTES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/sdk/index.html": ("index.html", "text/html; charset=utf-8"),
    "/sdk/runtime.js": ("runtime.js", "application/javascript; charset=utf-8"),
    "/sdk/runtime3d.js": ("runtime3d.js", "application/javascript; charset=utf-8"),
    "/sdk/client.js": ("client.js", "application/javascript; charset=utf-8"),
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


@dataclass(frozen=True)
class ReadyInfo:
    host: str
    port: int
    url: str


def _json_bytes(payload: Any) -> bytes:
    return json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


@dataclass(frozen=True)
class _StateEvent:
    body: bytes
    revision: int
    snapshot: bool


class _Subscriber:
    def __init__(self, initial: _StateEvent) -> None:
        self.queue = asyncio.Queue(maxsize=1)
        self.queue.put_nowait(initial)
        self.tail_revision = initial.revision
        self.reset_pending = False
        self.closed = False

    def take_pending(self) -> None:
        if not self.queue.empty():
            self.queue.get_nowait()

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        self.take_pending()
        self.queue.put_nowait(None)


class _DirtyTargets:
    def __init__(self) -> None:
        self.active = False
        self.base_revision = 0
        self.app_data = False
        self.cards = set()
        self.components = set()

    def start(self, revision: int) -> None:
        self.active = True
        self.base_revision = revision
        self.app_data = False
        self.cards.clear()
        self.components.clear()

    def empty(self) -> bool:
        return not (self.app_data or self.cards or self.components)

    def mark_app_data(self) -> bool:
        was_empty = self.empty()
        if not self.active:
            return False
        self.app_data = True
        return was_empty

    def mark_card(self, card_id: str) -> bool:
        was_empty = self.empty()
        if not self.active:
            return False
        self.cards.add(card_id)
        self.components = {target for target in self.components if target[0] != card_id}
        return was_empty

    def mark_component(self, card_id: str, component_id: str) -> bool:
        was_empty = self.empty()
        if self.active and card_id not in self.cards:
            self.components.add((card_id, component_id))
        return self.active and was_empty and not self.empty()

    def flush(self, model) -> Optional[dict]:
        if not self.active or not (self.app_data or self.cards or self.components):
            return None
        changes = []
        if self.app_data:
            changes.append(
                {
                    "op": "replace-app-data",
                    "value": copy_json_value(model.data, "DemoUiApp: "),
                }
            )
        cards_by_id = {card.id: card for card in model.cards}
        for card_id in sorted(self.cards):
            changes.append(
                {
                    "op": "upsert-card",
                    "value": cards_by_id[card_id].to_dict(),
                }
            )
        for card_id, component_id in sorted(self.components):
            card = cards_by_id[card_id]
            component = next(
                item for item in card._components if item.id == component_id
            )
            changes.append(
                {
                    "op": "upsert-component",
                    "card_id": card_id,
                    "value": component.to_dict(),
                }
            )
        patch = {
            "schema_version": 1,
            "base_revision": self.base_revision,
            "revision": model.revision,
            "changes": changes,
        }
        self.start(model.revision)
        return patch


class _EventBroadcaster:
    def __init__(self, model) -> None:
        self._model = model
        self._loop = None
        self._active = False
        self._flush_handle = None
        self._previous_flush = 0.0
        self._subscribers = set()
        self.publication_interval = _SSE_PUBLICATION_INTERVAL
        self.heartbeat_interval = _SSE_HEARTBEAT_INTERVAL
        self.write_timeout = _SSE_WRITE_TIMEOUT

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)

    def start(self, loop) -> None:
        self._loop = loop
        self._active = True
        self._previous_flush = loop.time() - self.publication_interval
        self._model.start_dirty_tracking_locked(self.mark_dirty)

    def mark_dirty(self) -> None:
        if not self._active or self._flush_handle is not None:
            return
        deadline = max(
            self._loop.time(), self._previous_flush + self.publication_interval
        )
        self._flush_handle = self._loop.call_at(deadline, self._flush)

    def _snapshot_event(self) -> _StateEvent:
        snapshot = self._model.snapshot()
        return _StateEvent(_sse_event("snapshot", snapshot), snapshot["revision"], True)

    def subscribe(self) -> Optional[_Subscriber]:
        if not self._active or len(self._subscribers) >= _SSE_MAX_STREAMS:
            return None
        subscriber = _Subscriber(self._snapshot_event())
        self._subscribers.add(subscriber)
        return subscriber

    def unsubscribe(self, subscriber: _Subscriber) -> None:
        self._subscribers.discard(subscriber)
        subscriber.close()

    def _enqueue(
        self, subscriber: _Subscriber, event: _StateEvent, snapshot_event
    ) -> None:
        if subscriber.closed:
            self._subscribers.discard(subscriber)
            return
        if subscriber.queue.full():
            if subscriber.reset_pending:
                self.unsubscribe(subscriber)
                return
            subscriber.take_pending()
            event = snapshot_event()
            subscriber.reset_pending = True
        subscriber.queue.put_nowait(event)
        subscriber.tail_revision = event.revision

    def _publish(self, patch: dict) -> None:
        patch_event = _StateEvent(_sse_event("patch", patch), patch["revision"], False)
        replacement = None

        def snapshot_event():
            nonlocal replacement
            if replacement is None:
                replacement = self._snapshot_event()
            return replacement

        for subscriber in tuple(self._subscribers):
            event = patch_event
            if subscriber.tail_revision != patch["base_revision"]:
                event = snapshot_event()
            self._enqueue(subscriber, event, snapshot_event)

    def _flush(self) -> None:
        self._flush_handle = None
        if not self._active:
            return
        patch = self._model.flush_dirty_targets_locked()
        if patch is None:
            return
        self._previous_flush = self._loop.time()
        self._publish(patch)

    def stop(self) -> None:
        if not self._active:
            return
        self._active = False
        if self._flush_handle is not None:
            self._flush_handle.cancel()
            self._flush_handle = None
        for subscriber in tuple(self._subscribers):
            self.unsubscribe(subscriber)


def _sse_event(event: str, payload: dict) -> bytes:
    revision = payload["revision"]
    return (
        f"event: {event}\nid: {revision}\ndata: ".encode("utf-8")
        + _json_bytes(payload)
        + b"\n\n"
    )


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
    body = _json_bytes(payload)
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

    def __init__(self, title: str, static_root: Optional[Path] = None) -> None:
        self.title = title
        self.static_root = static_root
        self.revision = 0
        self.cards = []
        self._running = True
        self._owner_loop = None
        self._owner_thread_id = None
        self._next_card_id = 1
        self._next_component_ids = {}
        self.data: Any = {}
        self._dirty_targets = _DirtyTargets()
        self._dirty_callback = None

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

    def start_dirty_tracking_locked(self, callback=None) -> None:
        self._dirty_targets.start(self.revision)
        self._dirty_callback = callback

    def commit_app_data_locked(self) -> None:
        self.revision += 1
        if self._dirty_targets.mark_app_data() and self._dirty_callback is not None:
            self._dirty_callback()

    def commit_card_locked(self, card_id: str) -> None:
        self.revision += 1
        if self._dirty_targets.mark_card(card_id) and self._dirty_callback is not None:
            self._dirty_callback()

    def commit_component_locked(self, card_id: str, component_id: str) -> None:
        self.revision += 1
        if (
            self._dirty_targets.mark_component(card_id, component_id)
            and self._dirty_callback is not None
        ):
            self._dirty_callback()

    def flush_dirty_targets_locked(self) -> Optional[dict]:
        return self._dirty_targets.flush(self)

    def next_card_id(self) -> str:
        card_id = f"card-{self._next_card_id}"
        self._next_card_id += 1
        return card_id

    def next_component_id(self, component_type: str) -> str:
        next_id = self._next_component_ids.get(component_type, 1)
        self._next_component_ids[component_type] = next_id + 1
        return f"{component_type}-{next_id}"

    def update_value(self, current, path, value, create_missing=False):
        if (
            not isinstance(path, (list, tuple))
            or not path
            or any(not isinstance(segment, str) or not segment for segment in path)
        ):
            raise ValueError("DemoUiApp: path must contain non-empty string segments")
        replacement = deepcopy(current)
        if not isinstance(replacement, dict):
            raise ValueError("DemoUiApp: path requires an object value")
        target = replacement
        for segment in path[:-1]:
            if segment not in target:
                if not create_missing:
                    raise ValueError(
                        f"DemoUiApp: path segment '{segment}' does not exist"
                    )
                target[segment] = {}
            if not isinstance(target[segment], dict):
                raise ValueError(
                    f"DemoUiApp: path segment '{segment}' is not an object"
                )
            target = target[segment]
        leaf = path[-1]
        if not create_missing and leaf not in target:
            raise ValueError(f"DemoUiApp: path segment '{leaf}' does not exist")
        target[leaf] = deepcopy(value)
        from .types import copy_json_value

        return copy_json_value(replacement, "DemoUiApp: ")

    def snapshot(self) -> dict:
        self.check_owner()
        self.ensure_running()
        return {
            "schema_version": 2,
            "revision": self.revision,
            "title": self.title,
            "data": copy_json_value(self.data, "DemoUiApp: "),
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
        port: int = 0,
        host: str = "127.0.0.1",
        static_root: str | os.PathLike[str] | None = None,
    ) -> None:
        require_non_empty(title, "title", "DemoUiApp: ")
        require_non_empty(host, "host", "DemoUiApp: ")
        if not (0 <= port <= 65535):
            raise ValueError("DemoUiApp: port must be between 0 and 65535")
        self._static_root = self._canonical_static_root(static_root)
        self._model = _Model(title, self._static_root)
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
        self._ready_info = None
        self._commands: Dict[str, Command] = {}
        self._command_capability = None
        self._active_commands = set()
        self._commands_done = asyncio.Event()
        self._commands_done.set()
        self._events = _EventBroadcaster(self._model)

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
        application = web.Application(client_max_size=_COMMAND_BODY_LIMIT + 1024)
        application.router.add_route("*", "/{path:.*}", self._handle_request)
        return application

    def _command_error(self, status: int, code: str, message: str, details=None):
        return _json_response(
            status,
            {
                "ok": False,
                "error": {
                    "code": code,
                    "message": message,
                    "details": details or [],
                },
            },
        )

    def _command_origin_is_trusted(self, request: web.Request) -> bool:
        if self._ready_info is None:
            return False
        return request.headers.get("Origin") == self._ready_info.url

    def _command_capability_request_is_trusted(self, request: web.Request) -> bool:
        if self._command_origin_is_trusted(request):
            return True
        if self._ready_info is None or "Origin" in request.headers:
            return False
        return request.scheme == "http" and (
            f"http://{request.host}" == self._ready_info.url
        )

    @staticmethod
    def _decode_command_name(encoded_name: str) -> Optional[str]:
        try:
            decoded_bytes = unquote_to_bytes(encoded_name)
            if b"%" in decoded_bytes:
                return None
            decoded = decoded_bytes.decode("utf-8", "strict")
        except (UnicodeDecodeError, ValueError):
            return None
        if "/" in decoded or not COMMAND_NAME.fullmatch(decoded):
            return None
        return decoded

    async def _handle_command_capability(self, request: web.Request):
        if not self._commands or not self._command_capability_request_is_trusted(
            request
        ):
            return _json_response(404, {"error": "not found"})
        return _json_response(200, {"capability": self._command_capability})

    async def _handle_command_request(self, request: web.Request, path: str):
        if request.method != "POST":
            return self._command_error(405, "method_not_allowed", "method not allowed")
        if not self._command_origin_is_trusted(request):
            return self._command_error(
                403, "forbidden", "origin or capability rejected"
            )
        if request.headers.get(_COMMAND_CAPABILITY_HEADER) != self._command_capability:
            return self._command_error(
                403, "forbidden", "origin or capability rejected"
            )
        command_name = self._decode_command_name(path[len(_COMMAND_PATH_PREFIX) :])
        if command_name is None:
            return self._command_error(400, "validation_error", "invalid command name")
        command = self._commands.get(command_name)
        if command is None:
            return self._command_error(404, "unknown_command", "unknown command")
        if self._state in (self._STOPPING, self._STOPPED):
            return self._command_error(
                409, "command_stopping", "command service is stopping"
            )
        if command_name in self._active_commands:
            return self._command_error(
                409, "command_busy", "command is already running"
            )
        self._active_commands.add(command_name)
        self._commands_done.clear()
        try:
            if (
                request.content_length is not None
                and request.content_length > _COMMAND_BODY_LIMIT
            ):
                return self._command_error(
                    413, "payload_too_large", "command body exceeds 64 KiB"
                )
            body = bytearray()
            try:
                while True:
                    chunk = await request.content.read(8192)
                    if not chunk:
                        break
                    body.extend(chunk)
                    if len(body) > _COMMAND_BODY_LIMIT:
                        return self._command_error(
                            413, "payload_too_large", "command body exceeds 64 KiB"
                        )
            except web.HTTPRequestEntityTooLarge:
                return self._command_error(
                    413, "payload_too_large", "command body exceeds 64 KiB"
                )
            try:
                payload = json.loads(body.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                return self._command_error(
                    400, "validation_error", "request body is not valid JSON"
                )
            if not isinstance(payload, dict):
                return self._command_error(
                    400, "validation_error", "command payload must be an object"
                )
            details = command.schema.validate(payload)
            if details:
                return self._command_error(
                    400,
                    "validation_error",
                    "command payload failed schema validation",
                    details,
                )
            try:
                result = command.handler(payload)
                if inspect.isawaitable(result):
                    result = await result
                result = copy_json_value(result, "DemoUiApp: ")
                return _json_response(200, {"ok": True, "result": result})
            except Exception:
                _logger.exception(
                    "RTI Demo UI command handler failed: %s", command_name
                )
                return self._command_error(
                    500, "handler_error", "command handler failed"
                )
        finally:
            self._active_commands.discard(command_name)
            if not self._active_commands:
                self._commands_done.set()

    async def _handle_request(self, request: web.Request) -> web.StreamResponse:
        path = request.raw_path.split("?", 1)[0]
        if path == "/api/events":
            if request.method != "GET":
                return _json_response(405, {"error": "method not allowed"})
            return await self._handle_events(request)
        if path == "/api/command-capability":
            if request.method != "GET":
                return _json_response(405, {"error": "method not allowed"})
            return await self._handle_command_capability(request)
        if path.startswith(_COMMAND_PATH_PREFIX):
            return await self._handle_command_request(request, path)
        if request.method != "GET":
            return _json_response(405, {"error": "method not allowed"})

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

    async def _write_sse(
        self, request: web.Request, response: web.StreamResponse, body: bytes
    ) -> bool:
        transport = request.transport
        if transport is None or transport.is_closing():
            return False
        try:
            await asyncio.wait_for(
                response.write(body), timeout=self._events.write_timeout
            )
        except (
            ClientConnectionError,
            ConnectionResetError,
            BrokenPipeError,
            asyncio.TimeoutError,
        ):
            return False
        return True

    async def _handle_events(self, request: web.Request) -> web.StreamResponse:
        subscriber = self._events.subscribe()
        if subscriber is None:
            return _json_response(503, {"error": "event stream capacity reached"})
        response = web.StreamResponse(
            status=200,
            headers={
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "X-Content-Type-Options": "nosniff",
            },
        )
        response.enable_chunked_encoding()
        prepared = False
        try:
            await response.prepare(request)
            prepared = True
            if not await self._write_sse(request, response, _SSE_RETRY):
                return response
            while True:
                try:
                    event = await asyncio.wait_for(
                        subscriber.queue.get(),
                        timeout=self._events.heartbeat_interval,
                    )
                except asyncio.TimeoutError:
                    if not await self._write_sse(request, response, b": heartbeat\n\n"):
                        break
                    continue
                if event is None:
                    break
                completing_reset = event.snapshot and subscriber.reset_pending
                if not await self._write_sse(request, response, event.body):
                    break
                if completing_reset:
                    subscriber.reset_pending = False
        except (ClientConnectionError, ConnectionResetError, BrokenPipeError):
            pass
        finally:
            self._events.unsubscribe(subscriber)
            if prepared:
                response.force_close()
        return response

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

    async def wait_until_ready(self) -> ReadyInfo:
        await self._ready_event.wait()
        return self._ready_info

    async def _cleanup_impl(self) -> None:
        try:
            self._events.stop()
            if self._active_commands:
                await self._commands_done.wait()
            if self._runner is not None:
                await self._runner.cleanup()
        finally:
            self._runner = None
            self._site = None
            self._shutdown_event = None
            if self._ready_event is not None:
                self._ready_event.clear()
            self._ready_info = None
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
            self._events.stop()
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
        self._model.commit_card_locked(card_id)
        return card

    def set_data(self, value) -> None:
        self._model.check_owner()
        self._model.ensure_running()
        from .types import copy_json_value

        self._model.data = copy_json_value(value, "DemoUiApp: ")
        self._model.commit_app_data_locked()

    def update_data(self, path, value, create_missing=False) -> None:
        self._model.check_owner()
        self._model.ensure_running()
        self._model.data = self._model.update_value(
            self._model.data, path, value, create_missing
        )
        self._model.commit_app_data_locked()

    @property
    def ready_info(self) -> Optional[ReadyInfo]:
        return self._ready_info

    def register_command(
        self,
        name: str,
        schema: dict | CommandSchema,
        handler,
        confirmation: Optional[CommandConfirmation] = None,
    ) -> Command:
        if self._run_started:
            raise RuntimeError(
                "DemoUiApp: command registration is closed after run() begins"
            )
        if not COMMAND_NAME.fullmatch(name):
            raise ValueError("DemoUiApp: command name is invalid")
        if self._host not in {"127.0.0.1", "::1"}:
            raise ValueError("DemoUiApp: commands require a literal loopback host")
        if name in self._commands:
            raise ValueError(f"DemoUiApp: command '{name}' is already registered")
        command_schema = (
            schema if isinstance(schema, CommandSchema) else CommandSchema(schema)
        )
        command = Command(name, command_schema, handler, confirmation)
        self._commands[name] = command
        if self._command_capability is None:
            self._command_capability = secrets.token_urlsafe(32)
        return command

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
            if sockets is None or len(sockets) != 1:
                raise RuntimeError("DemoUiApp: expected exactly one bound socket")
            actual_port = sockets[0].getsockname()[1]
            if self._state == self._STOPPING:
                return
            display_host = f"[{self._host}]" if ":" in self._host else self._host
            self._ready_info = ReadyInfo(
                self._host, actual_port, f"http://{display_host}:{actual_port}"
            )
            self._events.start(loop)
            self._state = self._RUNNING
            self._ready_event.set()
            print(f"RTI Demo UI listening on {self._ready_info.url}/")
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
