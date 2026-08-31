"""Synchronous native-window runner with managed asyncio server ownership."""

from __future__ import annotations

import asyncio
import importlib
import os
import queue
import re
import sys
import threading
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable, Protocol

from rti_demo_ui import DemoUiApp

_APPLICATION_ID = re.compile(
    r"[a-z](?:[a-z0-9-]*[a-z0-9])?"
    r"(?:\.[a-z](?:[a-z0-9-]*[a-z0-9])?)+"
)
_MAX_WINDOW_DIMENSION = 16384
_STARTUP_TIMEOUT_SECONDS = 10.0


class NativeWebviewError(RuntimeError):
    """Native runner failure with an actionable correction."""


AsyncMain = Callable[[DemoUiApp], Awaitable[None]]


@dataclass(frozen=True)
class _Options:
    application_id: str
    width: int
    height: int
    devtools: bool
    profile_path: Path


class _WindowHost(Protocol):
    def create(
        self,
        *,
        title: str,
        url: str,
        width: int,
        height: int,
        devtools: bool,
    ) -> None: ...

    def run(self) -> None: ...

    def request_close(self) -> None: ...


class _PyWebviewHost:
    def __init__(self, webview_module, profile_path: Path) -> None:
        self._webview = webview_module
        self._profile_path = profile_path
        self._window = None
        self._started = threading.Event()
        self._close_requested = threading.Event()
        self._close_error: list[BaseException] = []
        self._devtools = False

    def create(
        self,
        *,
        title: str,
        url: str,
        width: int,
        height: int,
        devtools: bool,
    ) -> None:
        self._devtools = devtools
        self._window = self._webview.create_window(
            title,
            url,
            width=width,
            height=height,
            resizable=True,
        )

    def _on_started(self) -> None:
        self._started.set()
        if self._close_requested.is_set():
            self._destroy()

    def _destroy(self) -> None:
        try:
            if self._window is not None:
                self._window.destroy()
        except BaseException as error:
            self._close_error.append(error)

    def request_close(self) -> None:
        self._close_requested.set()
        if self._started.is_set():
            self._destroy()

    def run(self) -> None:
        self._webview.start(
            self._on_started,
            gui="gtk",
            debug=self._devtools,
            private_mode=False,
            storage_path=str(self._profile_path),
        )
        if self._close_error:
            raise self._close_error[0]


def _profile_path(application_id: str) -> Path:
    if sys.platform == "linux":
        data_root = os.environ.get("XDG_DATA_HOME")
        root = (
            Path(data_root).expanduser()
            if data_root
            else Path.home() / ".local" / "share"
        )
        if not root.is_absolute():
            raise NativeWebviewError(
                "XDG_DATA_HOME must be an absolute path for native profile storage"
            )
        return root / "rti-demo-ui-native" / application_id
    raise NativeWebviewError(
        "native webview mode is supported only on Linux in this release"
    )


def _load_pywebview():
    try:
        return importlib.import_module("webview")
    except (ImportError, OSError) as error:
        raise NativeWebviewError(
            "pywebview 6.2.1 with GTK/WebKitGTK is required; install "
            "'rti-demo-ui-native' and the documented Ubuntu GTK 3 and "
            "WebKitGTK 4.1 packages"
        ) from error


def _validate_options(
    app: DemoUiApp,
    application_id: str,
    async_main: AsyncMain | None,
    width: int,
    height: int,
    devtools: bool,
) -> _Options:
    if threading.current_thread() is not threading.main_thread():
        raise NativeWebviewError("run_native() must be called on the main thread")
    if not isinstance(app, DemoUiApp):
        raise NativeWebviewError("app must be an rti_demo_ui.DemoUiApp instance")
    if not isinstance(application_id, str) or not _APPLICATION_ID.fullmatch(
        application_id
    ):
        raise NativeWebviewError(
            "application_id must be a lowercase reverse-DNS identifier such as "
            "'com.example.factory-dashboard'"
        )
    for name, value in (("width", width), ("height", height)):
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or value < 1
            or value > _MAX_WINDOW_DIMENSION
        ):
            raise NativeWebviewError(
                f"{name} must be an integer between 1 and "
                f"{_MAX_WINDOW_DIMENSION}"
            )
    if not isinstance(devtools, bool):
        raise NativeWebviewError("devtools must be a bool")
    if async_main is not None and not callable(async_main):
        raise NativeWebviewError("async_main must be callable or None")
    if app.host not in {"127.0.0.1", "::1"}:
        raise NativeWebviewError(
            "native webview mode requires app.host to be literal loopback "
            "'127.0.0.1' or '::1'"
        )
    if app.run_started or app.ready_info is not None:
        raise NativeWebviewError(
            "DemoUiApp has already started; create a new app for run_native()"
        )
    profile_path = _profile_path(application_id)
    try:
        profile_path.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise NativeWebviewError(
            f"cannot create native profile directory '{profile_path}'; "
            "check application data directory permissions"
        ) from error
    return _Options(application_id, width, height, devtools, profile_path)


def _run_with_host(
    app: DemoUiApp,
    host: _WindowHost,
    options: _Options,
    *,
    async_main: AsyncMain | None,
    timeout: float = _STARTUP_TIMEOUT_SECONDS,
) -> None:
    startup: queue.Queue[tuple[str, object]] = queue.Queue(maxsize=1)
    shutdown_requested = threading.Event()
    owner_errors: list[BaseException] = []
    application_errors: list[BaseException] = []

    async def owner() -> None:
        run_task = asyncio.create_task(app.run())
        ready_task = asyncio.create_task(app.wait_until_ready())
        done, _ = await asyncio.wait(
            {run_task, ready_task}, return_when=asyncio.FIRST_COMPLETED
        )
        if run_task in done:
            ready_task.cancel()
            with suppress(asyncio.CancelledError):
                await ready_task
            try:
                await run_task
            except BaseException as error:
                startup.put(("error", error))
            else:
                startup.put(
                    (
                        "error",
                        NativeWebviewError("server stopped before readiness"),
                    )
                )
            return

        ready = ready_task.result()
        startup.put(("ready", ready.url))
        application_task = (
            asyncio.create_task(async_main(app)) if async_main is not None else None
        )

        if application_task is not None:

            def application_done(task: asyncio.Task) -> None:
                if not task.cancelled() and (error := task.exception()) is not None:
                    application_errors.append(error)
                host.request_close()

            application_task.add_done_callback(application_done)

        shutdown_wait = asyncio.create_task(asyncio.to_thread(shutdown_requested.wait))
        done, _ = await asyncio.wait(
            {run_task, shutdown_wait}, return_when=asyncio.FIRST_COMPLETED
        )
        if run_task in done and not shutdown_requested.is_set():
            try:
                await run_task
            except BaseException as error:
                owner_errors.append(error)
            host.request_close()
            await shutdown_wait
        else:
            await app.stop()
            await run_task

        if application_task is not None and not application_task.done():
            application_task.cancel()
            with suppress(asyncio.CancelledError):
                await application_task

    def run_owner() -> None:
        try:
            asyncio.run(owner())
        except BaseException as error:
            owner_errors.append(error)
            with suppress(queue.Full):
                startup.put_nowait(("error", error))

    owner_thread = threading.Thread(target=run_owner, name="rti-demo-ui-native-owner")
    owner_thread.start()
    window_error: BaseException | None = None
    try:
        try:
            kind, payload = startup.get(timeout=timeout)
        except queue.Empty as error:
            raise NativeWebviewError(
                "server readiness timed out; check the configured loopback port"
            ) from error
        if kind == "error":
            raise NativeWebviewError(
                "server failed before native window creation"
            ) from payload
        host.create(
            title=app.title,
            url=f"{payload}/",
            width=options.width,
            height=options.height,
            devtools=options.devtools,
        )
        host.run()
    except BaseException as error:
        window_error = error
    finally:
        shutdown_requested.set()
        owner_thread.join(timeout)
        if owner_thread.is_alive() and app.run_started:
            try:
                asyncio.run(app.stop())
            except BaseException as error:
                owner_errors.append(error)
            owner_thread.join(timeout)

    if owner_thread.is_alive():
        raise NativeWebviewError(
            "native shutdown timed out while joining the app owner thread"
        )
    if application_errors:
        raise application_errors[0]
    if owner_errors:
        raise NativeWebviewError("server failed after readiness") from owner_errors[0]
    if window_error is not None:
        if isinstance(window_error, NativeWebviewError):
            raise window_error
        raise NativeWebviewError(
            "native window failed; verify GTK 3 and WebKitGTK 4.1 are installed"
        ) from window_error


def _run_native(
    app: DemoUiApp,
    *,
    application_id: str,
    async_main: AsyncMain | None,
    width: int,
    height: int,
    devtools: bool,
    host_factory: Callable[[_Options], _WindowHost],
) -> None:
    options = _validate_options(
        app, application_id, async_main, width, height, devtools
    )
    host = host_factory(options)
    _run_with_host(app, host, options, async_main=async_main)


def run_native(
    app: DemoUiApp,
    *,
    application_id: str,
    async_main: AsyncMain | None = None,
    width: int = 1280,
    height: int = 800,
    devtools: bool = False,
) -> None:
    """Run one app in a Linux native webview until the window or app closes."""

    def create_host(options: _Options) -> _WindowHost:
        return _PyWebviewHost(_load_pywebview(), options.profile_path)

    _run_native(
        app,
        application_id=application_id,
        async_main=async_main,
        width=width,
        height=height,
        devtools=devtools,
        host_factory=create_host,
    )
