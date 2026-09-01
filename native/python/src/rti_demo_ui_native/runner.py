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
import os
import queue
import re
import signal
import sys
import threading
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable, Protocol
from urllib.parse import urlsplit

from rti_demo_ui import DemoUiApp

_APPLICATION_ID = re.compile(
    r"[a-z](?:[a-z0-9-]*[a-z0-9])?" r"(?:\.[a-z](?:[a-z0-9-]*[a-z0-9])?)+"
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
    profile_path: Path | None


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
        self._allowed_origin = ""
        self._gui = "gtk"

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
        self._allowed_origin = _origin(url)
        self._webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] = False
        self._window = self._webview.create_window(
            title,
            url,
            width=width,
            height=height,
            resizable=True,
        )
        policy_event = self._navigation_policy_event()
        policy_event += self._install_navigation_policy

    def _navigation_policy_event(self):
        return self._window.events.before_show

    def _install_navigation_policy(self) -> None:
        def find_webview(widget):
            if widget.__gtype__.name == "WebKitWebView":
                return widget
            get_children = getattr(widget, "get_children", None)
            if get_children is not None:
                for child in get_children():
                    if (found := find_webview(child)) is not None:
                        return found
            return None

        browser = find_webview(self._window.native)
        if browser is None:
            raise NativeWebviewError(
                "WebKitWebView native child was not found; verify pywebview "
                "6.2.1 is using the GTK backend"
            )

        def block_external_navigation(_browser, decision, _decision_type):
            get_action = getattr(decision, "get_navigation_action", None)
            if get_action is None:
                return False
            uri = get_action().get_request().get_uri()
            if _same_origin(uri, self._allowed_origin):
                return False
            decision.ignore()
            return True

        browser.connect("decide-policy", block_external_navigation)

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
            storage_path=str(self._profile_path),
        )
        if self._close_error:
            raise self._close_error[0]


class _WindowsPyWebviewHost(_PyWebviewHost):
    def __init__(self, webview_module, profile_path: Path) -> None:
        super().__init__(webview_module, profile_path)
        self._gui = "edgechromium"
        self._navigation_handler = None
        self._new_window_handler = None

    def _navigation_policy_event(self):
        return self._window.events.before_load

    def _install_navigation_policy(self) -> None:
        native = self._window.native
        webview_control = getattr(native, "webview", None)
        browser = getattr(webview_control, "CoreWebView2", None)
        if browser is None:
            raise NativeWebviewError(
                "WebView2 native controller was not initialized; verify "
                "pywebview 6.2.1 is using the Edge Chromium backend"
            )

        def block_external_navigation(_sender, args):
            if not _same_origin(str(args.Uri), self._allowed_origin):
                args.Cancel = True

        def block_new_window(_sender, args):
            args.Handled = True

        self._navigation_handler = block_external_navigation
        self._new_window_handler = block_new_window
        browser.NavigationStarting += self._navigation_handler
        browser.NewWindowRequested += self._new_window_handler


def _origin(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.scheme != "http" or not parsed.netloc:
        raise NativeWebviewError("native window URL must be an HTTP loopback origin")
    return f"{parsed.scheme}://{parsed.netloc}"


def _same_origin(url: str, allowed_origin: str) -> bool:
    try:
        return _origin(url) == allowed_origin
    except NativeWebviewError:
        return False


def _profile_path(application_id: str) -> Path | None:
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
    elif sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA")
        if not local_app_data:
            raise NativeWebviewError(
                "LOCALAPPDATA is required for native profile storage on Windows"
            )
        root = Path(local_app_data)
        if not root.is_absolute():
            raise NativeWebviewError(
                "LOCALAPPDATA must be an absolute path for native profile storage"
            )
    elif sys.platform == "darwin":
        return None
    else:
        raise NativeWebviewError(
            f"native webview mode is not prepared for platform '{sys.platform}'"
        )
    return root / "rti-demo-ui-native" / application_id


def _require_supported_production_platform() -> None:
    if sys.platform in {"linux", "win32"}:
        return
    raise NativeWebviewError(
        "native webview mode on macOS requires a safe pywebview WKWebView "
        "delegate-composition API that is not available in pywebview 6.2.1"
    )


def _load_pywebview():
    try:
        return importlib.import_module("webview")
    except (ImportError, OSError) as error:
        if sys.platform == "win32":
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
    profile_path = _profile_path(application_id)
    if profile_path is not None:
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
        if options.profile_path is None:
            raise NativeWebviewError(
                "the qualified Linux backend requires a native profile path"
            )
        webview_module = _load_pywebview()
        if sys.platform == "win32":
            return _WindowsPyWebviewHost(webview_module, options.profile_path)
        return _PyWebviewHost(webview_module, options.profile_path)

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
