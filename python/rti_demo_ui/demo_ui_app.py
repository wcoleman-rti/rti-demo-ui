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
from .types import (
    CardArea,
    Layout,
    Theme,
    coerce_card_area,
    coerce_layout,
    coerce_theme,
    copy_json_value,
    require_card_span,
    require_non_empty,
)

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
    """Connection details published after :meth:`DemoUiApp.run` binds a socket.

    Attributes:
        host: Bound host string passed to the server.
        port: Actual bound TCP port. This may differ from the requested port
            when the app was created with ``port=0``.
        url: Base origin URL without a trailing slash.
    """

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
    _UPSERT = "upsert"
    _REMOVE = "remove"

    def __init__(self) -> None:
        self.active = False
        self.base_revision = 0
        self.app_data = False
        self.presentation = False
        self.cards = {}
        self.components = {}
        self.removed_cards = set()
        self.removed_components = set()

    def start(self, revision: int) -> None:
        self.active = True
        self.base_revision = revision
        self.app_data = False
        self.presentation = False
        self.cards.clear()
        self.components.clear()

    def empty(self) -> bool:
        return not (self.app_data or self.presentation or self.cards or self.components)

    def mark_app_data(self) -> bool:
        was_empty = self.empty()
        if not self.active:
            return False
        self.app_data = True
        return was_empty

    def mark_presentation(self) -> bool:
        was_empty = self.empty()
        if not self.active:
            return False
        self.presentation = True
        return was_empty

    def mark_card(self, card_id: str) -> bool:
        was_empty = self.empty()
        if not self.active:
            return False
        if card_id in self.removed_cards:
            raise RuntimeError(f"cannot upsert removed card target: {card_id}")
        self.cards[card_id] = self._UPSERT
        self.components = {
            target: operation
            for target, operation in self.components.items()
            if target[0] != card_id
        }
        return was_empty

    def mark_card_removed(self, card_id: str) -> bool:
        was_empty = self.empty()
        self.removed_cards.add(card_id)
        if not self.active:
            return False
        self.cards[card_id] = self._REMOVE
        self.components = {
            target: operation
            for target, operation in self.components.items()
            if target[0] != card_id
        }
        return was_empty

    def mark_component(self, card_id: str, component_id: str) -> bool:
        was_empty = self.empty()
        if not self.active:
            return False
        if card_id in self.removed_cards:
            raise RuntimeError(
                f"cannot upsert component in removed card target: {card_id}"
            )
        target = (card_id, component_id)
        if target in self.removed_components:
            raise RuntimeError(
                f"cannot upsert removed component target: {card_id}:{component_id}"
            )
        if card_id not in self.cards:
            self.components[target] = self._UPSERT
        return self.active and was_empty and not self.empty()

    def mark_component_removed(self, card_id: str, component_id: str) -> bool:
        was_empty = self.empty()
        self.removed_components.add((card_id, component_id))
        if not self.active:
            return False
        if card_id not in self.cards:
            self.components[(card_id, component_id)] = self._REMOVE
        return was_empty and not self.empty()

    def flush(self, model) -> Optional[dict]:
        if not self.active or not (
            self.app_data or self.presentation or self.cards or self.components
        ):
            return None
        changes = []
        if self.app_data:
            changes.append(
                {
                    "op": "replace-app-data",
                    "value": copy_json_value(model.data, "DemoUiApp: "),
                }
            )
        if self.presentation:
            changes.append(
                {
                    "op": "replace-presentation",
                    "theme": model.theme.value,
                    "layout": model.layout.value,
                }
            )
        cards_by_id = {card.id: card for card in model.cards}
        for card_id, operation in sorted(self.cards.items()):
            if operation == self._REMOVE:
                changes.append({"op": "remove-card", "card_id": card_id})
            else:
                changes.append(
                    {
                        "op": "upsert-card",
                        "value": cards_by_id[card_id].to_dict(),
                    }
                )
        for (card_id, component_id), operation in sorted(self.components.items()):
            if operation == self._REMOVE:
                changes.append(
                    {
                        "op": "remove-component",
                        "card_id": card_id,
                        "component_id": component_id,
                    }
                )
                continue
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

    def __init__(
        self,
        title: str,
        static_root: Optional[Path] = None,
        theme=Theme.dark,
        layout=Layout.auto,
    ) -> None:
        self.title = title
        self.static_root = static_root
        self.theme = theme
        self.layout = layout
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

    def commit_presentation_locked(self) -> None:
        self.revision += 1
        if self._dirty_targets.mark_presentation() and self._dirty_callback is not None:
            self._dirty_callback()

    def commit_card_locked(self, card_id: str) -> None:
        if card_id in self._dirty_targets.removed_cards:
            raise RuntimeError(f"cannot upsert removed card target: {card_id}")
        self.revision += 1
        if self._dirty_targets.mark_card(card_id) and self._dirty_callback is not None:
            self._dirty_callback()

    def commit_card_removal_locked(self, card_id: str) -> None:
        self.revision += 1
        if (
            self._dirty_targets.mark_card_removed(card_id)
            and self._dirty_callback is not None
        ):
            self._dirty_callback()

    def commit_component_locked(self, card_id: str, component_id: str) -> None:
        if (
            card_id in self._dirty_targets.removed_cards
            or (
                card_id,
                component_id,
            )
            in self._dirty_targets.removed_components
        ):
            raise RuntimeError(
                f"cannot upsert removed component target: {card_id}:{component_id}"
            )
        self.revision += 1
        if (
            self._dirty_targets.mark_component(card_id, component_id)
            and self._dirty_callback is not None
        ):
            self._dirty_callback()

    def commit_component_removal_locked(self, card_id: str, component_id: str) -> None:
        self.revision += 1
        if (
            self._dirty_targets.mark_component_removed(card_id, component_id)
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
            "theme": self.theme.value,
            "layout": self.layout.value,
            "data": copy_json_value(self.data, "DemoUiApp: "),
            "cards": [card.to_dict() for card in self.cards],
        }


class DemoUiApp:
    """Own the presentation model and local aiohttp server for one process.

    A ``DemoUiApp`` is configured synchronously, then started once with
    :meth:`run`. After startup, mutating methods must be called on the event
    loop that owns the running app. The app exposes a local HTTP UI, state
    snapshot route, event stream, and optional validated command endpoints.
    """

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
        *,
        theme=Theme.dark,
        layout=Layout.auto,
    ) -> None:
        """Create an application model and HTTP server wrapper.

        Args:
            title: Non-empty application title.
            port: Requested TCP port in ``[0, 65535]``. Use ``0`` to let the OS
                choose a free port.
            host: Non-empty bind host string. Commands additionally require a
                literal loopback host.
            static_root: Optional existing directory containing ``index.html``
                and any same-origin assets referenced by the UI.
            theme: Initial built-in theme.
            layout: Initial built-in layout.

        Raises:
            ValueError: If any argument is invalid or ``static_root`` is not an
                existing directory containing a regular ``index.html`` file.
        """
        require_non_empty(title, "title", "DemoUiApp: ")
        require_non_empty(host, "host", "DemoUiApp: ")
        theme = coerce_theme(theme)
        layout = coerce_layout(layout)
        if not (0 <= port <= 65535):
            raise ValueError("DemoUiApp: port must be between 0 and 65535")
        self._static_root = self._canonical_static_root(static_root)
        self._model = _Model(title, self._static_root, theme, layout)
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
        """Wait until :meth:`run` binds the server socket successfully.

        Returns:
            The current :class:`ReadyInfo` for the running app.
        """
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

    def add_card(self, title: str, area=CardArea.main, span: int = 1) -> Card:
        """Create and attach a new card.

        Args:
            title: Non-empty card title.
            area: Initial card area as a :class:`CardArea` or matching string.
            span: Initial card span as an integer from 1 to 3.

        Returns:
            The newly attached :class:`Card`. Mutate it in place to add
            components or adjust presentation properties.

        Raises:
            RuntimeError: If called from a non-owner event loop after
                :meth:`run` starts, or after shutdown.
            ValueError: If the arguments are invalid or would create more than
                one sidebar card.
        """
        area = coerce_card_area(area)
        require_card_span(span)
        self._model.check_owner()
        self._model.ensure_running()
        if area == CardArea.sidebar and any(
            card.area == CardArea.sidebar for card in self._model.cards
        ):
            raise ValueError("DemoUiApp: at most one sidebar card is permitted")
        card_id = self._model.next_card_id()
        card = Card(self._model, card_id, title, area, span)
        self._model.cards.append(card)
        self._model.commit_card_locked(card_id)
        return card

    def set_theme(self, theme) -> None:
        """Set the application theme.

        Re-applying the current theme is a no-op and does not bump the model
        revision.

        Args:
            theme: A :class:`Theme` value or matching string.

        Raises:
            RuntimeError: If called from a non-owner event loop after
                :meth:`run` starts, or after shutdown.
            ValueError: If ``theme`` is invalid.
        """
        theme = coerce_theme(theme)
        self._model.check_owner()
        self._model.ensure_running()
        if theme == self._model.theme:
            return
        self._model.theme = theme
        self._model.commit_presentation_locked()

    def set_layout(self, layout) -> None:
        """Set the application card layout.

        Re-applying the current layout is a no-op. ``sidebar-main`` is only
        allowed when exactly one sidebar card exists.

        Args:
            layout: A :class:`Layout` value or matching string.

        Raises:
            RuntimeError: If called from a non-owner event loop after
                :meth:`run` starts, or after shutdown.
            ValueError: If ``layout`` is invalid or violates sidebar-card
                cardinality rules.
        """
        layout = coerce_layout(layout)
        self._model.check_owner()
        self._model.ensure_running()
        if layout == self._model.layout:
            return
        if (
            layout == Layout.sidebar_main
            and sum(card.area == CardArea.sidebar for card in self._model.cards) != 1
        ):
            raise ValueError(
                "DemoUiApp: sidebar-main requires exactly one sidebar card"
            )
        self._model.layout = layout
        self._model.commit_presentation_locked()

    def set_data(self, value) -> None:
        """Replace the application-level JSON payload.

        Args:
            value: Any JSON-compatible value. The SDK stores a defensive deep
                copy, so later caller-side mutations are not observed.

        Raises:
            RuntimeError: If called from a non-owner event loop after
                :meth:`run` starts, or after shutdown.
            ValueError: If ``value`` is not JSON-compatible.
        """
        self._model.check_owner()
        self._model.ensure_running()
        from .types import copy_json_value

        self._model.data = copy_json_value(value, "DemoUiApp: ")
        self._model.commit_app_data_locked()

    def update_data(self, path, value, create_missing=False) -> None:
        """Update a nested field within the application-level data object.

        Args:
            path: Sequence of non-empty string keys. An empty sequence replaces
                the complete application data value.
            value: JSON-compatible value written at the leaf key.
            create_missing: When ``True``, missing intermediate objects are
                created. When ``False``, every segment must already exist.

        Raises:
            RuntimeError: If called from a non-owner event loop after
                :meth:`run` starts, or after shutdown.
            ValueError: If ``path`` is invalid, the current data or an
                intermediate segment is not an object, a required segment is
                missing, or ``value`` is not JSON-compatible.
        """
        self._model.check_owner()
        self._model.ensure_running()
        self._model.data = self._model.update_value(
            self._model.data, path, value, create_missing
        )
        self._model.commit_app_data_locked()

    @property
    def ready_info(self) -> Optional[ReadyInfo]:
        """Current bind information for the running app, if available.

        Returns:
            ``None`` before the server becomes ready and again after cleanup
            completes.
        """
        return self._ready_info

    @property
    def title(self) -> str:
        """Return the application title displayed by the frontend."""
        return self._model.title

    @property
    def host(self) -> str:
        """Return the configured HTTP bind host."""
        return self._host

    @property
    def run_started(self) -> bool:
        """Return whether this single-use application has started running."""
        return self._run_started

    def register_command(
        self,
        name: str,
        schema: dict | CommandSchema,
        handler,
        confirmation: Optional[CommandConfirmation] = None,
    ) -> Command:
        """Register a validated browser-invoked command before startup.

        Args:
            name: Command name matching ``^[a-z][a-z0-9-]{0,62}$``.
            schema: A :class:`CommandSchema` instance or schema dictionary using
                the supported subset.
            handler: Sync or async callable invoked with the validated payload.
                The return value must be JSON-compatible.
            confirmation: Optional browser confirmation metadata shown before the
                command is submitted.

        Returns:
            The registered :class:`Command` definition.

        Raises:
            RuntimeError: If registration is attempted after :meth:`run`
                starts.
            ValueError: If the host is not a literal loopback address, ``name``
                is invalid or already registered, or ``schema`` is invalid.
        """
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
        """Start serving the demo UI until :meth:`stop` or cancellation occurs.

        This coroutine may be called only once. The running loop becomes the
        owner for all subsequent model mutations.

        Raises:
            RuntimeError: If called more than once or if the server does not
                bind exactly one socket.
            ValueError: If the current ``sidebar-main`` layout does not have
                exactly one sidebar card.
            OSError: If the HTTP site fails to bind.
            asyncio.CancelledError: If the task is cancelled while running.
        """
        loop = asyncio.get_running_loop()
        if self._run_started:
            raise RuntimeError("DemoUiApp: run() may only be called once")
        if self._state == self._STOPPED:
            self._run_started = True
            return
        if (
            self._model.layout == Layout.sidebar_main
            and sum(card.area == CardArea.sidebar for card in self._model.cards) != 1
        ):
            raise ValueError(
                "DemoUiApp: sidebar-main requires exactly one sidebar card"
            )
        self._run_started = True
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
        """Stop the server and wait for cleanup to finish.

        ``stop()`` may be awaited before :meth:`run` to prevent any later bind,
        from the owner loop, or from another loop while the app is running. The
        method waits for in-flight requests, active commands, and SSE cleanup.
        Do not directly await ``stop()`` inside a command handler: that handler
        is itself active work that shutdown must drain. Schedule it with
        ``asyncio.create_task(app.stop())`` so the handler can return first.
        """
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
