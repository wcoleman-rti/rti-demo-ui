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

"""Synchronous native-window runner with managed asyncio server ownership."""

from __future__ import annotations

import asyncio
import importlib
import queue
import re
import signal
import sys
import threading
from contextlib import suppress
from dataclasses import dataclass
from typing import Awaitable, Callable, Protocol

from rti_demo_ui import DemoUiApp

_APPLICATION_ID = re.compile(
    r"[a-z](?:[a-z0-9-]*[a-z0-9])?" r"(?:\.[a-z](?:[a-z0-9-]*[a-z0-9])?)+"
)
_MAX_WINDOW_DIMENSION = 16384
_STARTUP_TIMEOUT_SECONDS = 10.0


class NativeWebviewError(RuntimeError):
    """Report invalid native options or a native host lifecycle failure."""


AsyncMain = Callable[[DemoUiApp], Awaitable[None]]


@dataclass(frozen=True)
class _Options:
    application_id: str | None
    width: int
    height: int
    devtools: bool


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
    def __init__(self, webview_module, gui: str) -> None:
        self._webview = webview_module
        self._gui = gui
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
            gui=self._gui,
            debug=self._devtools,
            private_mode=False,
        )
        if self._close_error:
            raise self._close_error[0]


def _require_supported_production_platform() -> None:
    if sys.platform in {"darwin", "linux", "win32"}:
        return
    raise NativeWebviewError(
        f"native webview mode is not supported on platform '{sys.platform}'"
    )


def _native_prerequisite_hint() -> str:
    if sys.platform == "darwin":
        return "verify pywebview 6.2.1 and macOS WKWebView are available"
    if sys.platform == "win32":
        return "verify pywebview 6.2.1 and the WebView2 Runtime are installed"
    return "verify GTK 3 and WebKitGTK 4.1 are installed"


def _load_pywebview():
    try:
        return importlib.import_module("webview")
    except (ImportError, OSError) as error:
        if sys.platform == "darwin":
            requirement = "pywebview 6.2.1 with its Cocoa dependencies is required"
        elif sys.platform == "win32":
            requirement = (
                "pywebview 6.2.1 with pythonnet and the Evergreen WebView2 "
                "Runtime is required"
            )
        else:
            requirement = (
                "pywebview 6.2.1 with GTK/WebKitGTK is required; install the "
                "documented Ubuntu GTK 3 and WebKitGTK 4.1 packages"
            )
        raise NativeWebviewError(
            f"{requirement}; install 'rti-demo-ui-native'"
        ) from error


def _validate_options(
    app: DemoUiApp,
    application_id: str | None,
    async_main: AsyncMain | None,
    width: int,
    height: int,
    devtools: bool,
) -> _Options:
    if threading.current_thread() is not threading.main_thread():
        raise NativeWebviewError("run_native() must be called on the main thread")
    if not isinstance(app, DemoUiApp):
        raise NativeWebviewError("app must be an rti_demo_ui.DemoUiApp instance")
    if application_id is not None and (
        not isinstance(application_id, str)
        or not _APPLICATION_ID.fullmatch(application_id)
    ):
        raise NativeWebviewError(
            "application_id must be None or a lowercase reverse-DNS identifier "
            "such as 'com.example.factory-dashboard'"
        )
    for name, value in (("width", width), ("height", height)):
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or value < 1
            or value > _MAX_WINDOW_DIMENSION
        ):
            raise NativeWebviewError(
                f"{name} must be an integer between 1 and " f"{_MAX_WINDOW_DIMENSION}"
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
    return _Options(application_id, width, height, devtools)


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
    signal_requested = threading.Event()
    signal_watcher_stop = threading.Event()
    previous_handlers = {}

    def request_signal_shutdown(_signum, _frame) -> None:
        signal_requested.set()

    for signum in (signal.SIGINT, signal.SIGTERM):
        previous_handlers[signum] = signal.signal(signum, request_signal_shutdown)

    def watch_signals() -> None:
        while not signal_watcher_stop.wait(0.05):
            if signal_requested.is_set():
                host.request_close()
                return

    signal_watcher = threading.Thread(
        target=watch_signals, name="rti-demo-ui-native-signal"
    )
    signal_watcher.start()

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
        signal_watcher_stop.set()
        signal_watcher.join(timeout)
        for signum, previous_handler in previous_handlers.items():
            signal.signal(signum, previous_handler)

    if owner_thread.is_alive():
        raise NativeWebviewError(
            "native shutdown timed out while joining the app owner thread"
        )
    if signal_watcher.is_alive():
        raise NativeWebviewError(
            "native shutdown timed out while joining the signal watcher"
        )
    if application_errors:
        raise application_errors[0]
    if owner_errors:
        raise NativeWebviewError("server failed after readiness") from owner_errors[0]
    if window_error is not None:
        if isinstance(window_error, NativeWebviewError):
            raise window_error
        raise NativeWebviewError(
            f"native window failed; {_native_prerequisite_hint()}"
        ) from window_error


def _run_native(
    app: DemoUiApp,
    *,
    application_id: str | None,
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
    application_id: str | None = None,
    async_main: AsyncMain | None = None,
    width: int = 1280,
    height: int = 800,
    devtools: bool = False,
) -> None:
    """Run an application in a native webview.

    This synchronous main-thread entry point owns the native window loop and
    runs the application's asyncio server on a managed background thread.
    Closing the window, stopping the application, or receiving ``SIGINT`` or
    ``SIGTERM`` initiates joined cleanup. The application must not have been
    run previously.

    Args:
        app: Configured, single-use application to host.
        application_id: Optional stable lowercase reverse-DNS identifier kept
            for source compatibility. Native browser storage remains owned by
            the selected platform backend.
        async_main: Optional application coroutine started on the application
            owner loop after the server becomes ready. Returning from it closes
            the window.
        width: Initial window width in pixels, from 1 through 16384.
        height: Initial window height in pixels, from 1 through 16384.
        devtools: Whether to enable the embedded browser's developer tools.

    Raises:
        NativeWebviewError: If options, platform prerequisites, server startup,
            or native window lifecycle handling fail.
        BaseException: Re-raises an exception from ``async_main`` after cleanup.
    """

    def create_host(options: _Options) -> _WindowHost:
        webview_module = _load_pywebview()
        gui = {
            "darwin": "cocoa",
            "linux": "gtk",
            "win32": "edgechromium",
        }[sys.platform]
        return _PyWebviewHost(webview_module, gui)

    _require_supported_production_platform()
    _run_native(
        app,
        application_id=application_id,
        async_main=async_main,
        width=width,
        height=height,
        devtools=devtools,
        host_factory=create_host,
    )
