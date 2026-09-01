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

import asyncio
import os
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from rti_demo_ui import DemoUiApp
from rti_demo_ui_native import NativeWebviewError
from rti_demo_ui_native import runner
from rti_demo_ui_native.runner import (
    _load_pywebview,
    _origin,
    _run_native,
    _same_origin,
)


class FakeWindowHost:
    def __init__(
        self,
        *,
        close_immediately=False,
        create_error=None,
        run_error=None,
    ):
        self.close_immediately = close_immediately
        self.create_error = create_error
        self.run_error = run_error
        self.close_requested = threading.Event()
        self.create_thread = None
        self.run_thread = None
        self.options = None

    def create(self, **options):
        self.create_thread = threading.get_ident()
        self.options = options
        if self.create_error is not None:
            raise self.create_error
        if self.close_immediately:
            self.request_close()

    def run(self):
        self.run_thread = threading.get_ident()
        if self.run_error is not None:
            raise self.run_error
        if not self.close_requested.wait(2):
            raise TimeoutError("fake window did not receive close request")

    def request_close(self):
        self.close_requested.set()


def run_fake(app, host, *, async_main=None, application_id="com.example.demo"):
    return _run_native(
        app,
        application_id=application_id,
        async_main=async_main,
        width=1280,
        height=800,
        devtools=False,
        host_factory=lambda _options: host,
    )


def assert_port_released(url):
    port = int(url.rstrip("/").rsplit(":", 1)[1])
    with socket.socket() as probe:
        probe.settimeout(0.2)
        assert probe.connect_ex(("127.0.0.1", port)) != 0


def test_import_is_lazy_for_pywebview():
    source_root = Path(__file__).parents[1] / "src"
    core_root = Path(__file__).parents[3] / "python"
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import rti_demo_ui_native; "
            "assert 'webview' not in sys.modules",
        ],
        env={"PYTHONPATH": f"{source_root}:{core_root}"},
        check=False,
    )
    assert result.returncode == 0


@pytest.mark.parametrize(
    ("application_id", "message"),
    [
        ("demo", "reverse-DNS"),
        ("Com.Example.Demo", "reverse-DNS"),
        ("com.example.-demo", "reverse-DNS"),
        (None, "reverse-DNS"),
    ],
)
def test_invalid_application_id_is_actionable(application_id, message):
    with pytest.raises(NativeWebviewError, match=message):
        run_fake(
            DemoUiApp("invalid"),
            FakeWindowHost(),
            application_id=application_id,
        )


@pytest.mark.parametrize(
    ("name", "value"),
    [("width", 0), ("width", True), ("height", 16385), ("height", 1.5)],
)
def test_invalid_dimensions_are_actionable(name, value):
    kwargs = {"width": 1280, "height": 800}
    kwargs[name] = value
    with pytest.raises(NativeWebviewError, match=name):
        _run_native(
            DemoUiApp("invalid"),
            application_id="com.example.demo",
            async_main=None,
            devtools=False,
            host_factory=lambda _options: FakeWindowHost(),
            **kwargs,
        )


def test_non_loopback_host_is_rejected():
    with pytest.raises(NativeWebviewError, match="literal loopback"):
        run_fake(DemoUiApp("remote", host="localhost"), FakeWindowHost())


def test_unsupported_platform_is_actionable(monkeypatch):
    monkeypatch.setattr(runner.sys, "platform", "darwin")
    with pytest.raises(NativeWebviewError, match="supported only on Linux"):
        run_fake(DemoUiApp("unsupported"), FakeWindowHost())


def test_missing_pywebview_is_actionable(monkeypatch):
    def missing(_name):
        raise ModuleNotFoundError("webview is absent")

    monkeypatch.setattr(runner.importlib, "import_module", missing)
    with pytest.raises(NativeWebviewError, match="pywebview 6.2.1"):
        _load_pywebview()


def test_run_native_requires_main_thread():
    errors = []

    def invoke():
        try:
            run_fake(DemoUiApp("wrong thread"), FakeWindowHost())
        except BaseException as error:
            errors.append(error)

    thread = threading.Thread(target=invoke)
    thread.start()
    thread.join()
    assert len(errors) == 1
    assert isinstance(errors[0], NativeWebviewError)
    assert "main thread" in str(errors[0])


def test_navigation_origin_is_exact():
    origin = _origin("http://127.0.0.1:42000/")
    assert _same_origin("http://127.0.0.1:42000/dashboard", origin)
    assert _same_origin("http://127.0.0.1:42000/?view=main", origin)
    assert not _same_origin("http://127.0.0.1:42001/", origin)
    assert not _same_origin("http://localhost:42000/", origin)
    assert not _same_origin("https://example.invalid/", origin)
    assert not _same_origin("about:blank", origin)


def test_pywebview_external_browser_navigation_is_disabled(tmp_path):
    class EventHook:
        def __iadd__(self, _callback):
            return self

    fake_window = SimpleNamespace(
        events=SimpleNamespace(before_show=EventHook()),
    )
    fake_webview = SimpleNamespace(
        settings={"OPEN_EXTERNAL_LINKS_IN_BROWSER": True},
        create_window=lambda *args, **kwargs: fake_window,
    )
    host = runner._PyWebviewHost(fake_webview, tmp_path)
    host.create(
        title="navigation",
        url="http://127.0.0.1:42000/",
        width=1280,
        height=800,
        devtools=False,
    )
    assert fake_webview.settings["OPEN_EXTERNAL_LINKS_IN_BROWSER"] is False


def test_window_close_joins_owner_and_releases_port():
    host = FakeWindowHost(close_immediately=True)
    app = DemoUiApp("close")
    run_fake(app, host)

    assert host.create_thread == threading.main_thread().ident
    assert host.run_thread == threading.main_thread().ident
    assert host.options["title"] == "close"
    assert host.options["url"].endswith("/")
    assert_port_released(host.options["url"])


def test_window_initialization_failure_still_releases_port():
    host = FakeWindowHost(create_error=RuntimeError("window init failed"))
    with pytest.raises(NativeWebviewError, match="native window failed"):
        run_fake(DemoUiApp("init failure"), host)
    assert_port_released(host.options["url"])


def test_bind_failure_surfaces_without_creating_window():
    with socket.socket() as blocker:
        blocker.bind(("127.0.0.1", 0))
        blocker.listen()
        port = blocker.getsockname()[1]
        host = FakeWindowHost()
        with pytest.raises(NativeWebviewError, match="before native window"):
            run_fake(DemoUiApp("bind failure", port=port), host)
    assert host.options is None


def test_async_main_return_requests_window_close():
    host = FakeWindowHost()
    mutation_thread = []

    async def async_main(app):
        mutation_thread.append(threading.get_ident())
        app.set_data({"status": "complete"})

    app = DemoUiApp("async return")
    run_fake(app, host, async_main=async_main)

    assert mutation_thread
    assert mutation_thread[0] != threading.main_thread().ident
    assert host.close_requested.is_set()
    assert_port_released(host.options["url"])


def test_async_main_exception_is_raised_after_cleanup():
    host = FakeWindowHost()

    async def async_main(_app):
        raise ValueError("application failed")

    with pytest.raises(ValueError, match="application failed"):
        run_fake(DemoUiApp("async failure"), host, async_main=async_main)
    assert_port_released(host.options["url"])


def test_window_close_cancels_and_awaits_async_main():
    host = FakeWindowHost(close_immediately=True)
    cleanup_complete = threading.Event()

    async def async_main(_app):
        try:
            await asyncio.Event().wait()
        finally:
            await asyncio.sleep(0)
            cleanup_complete.set()

    run_fake(DemoUiApp("async cancellation"), host, async_main=async_main)
    assert cleanup_complete.is_set()
    assert_port_released(host.options["url"])


def test_server_stop_dispatches_window_close():
    host = FakeWindowHost()

    async def async_main(app):
        await asyncio.sleep(0.01)
        await app.stop()

    started = time.monotonic()
    run_fake(DemoUiApp("server stop"), host, async_main=async_main)

    assert time.monotonic() - started < 2
    assert host.close_requested.is_set()
    assert_port_released(host.options["url"])


def test_sigint_requests_window_close_and_restores_handler():
    host = FakeWindowHost()
    previous_handler = signal.getsignal(signal.SIGINT)
    timer = threading.Timer(0.05, lambda: os.kill(os.getpid(), signal.SIGINT))
    timer.start()
    try:
        run_fake(DemoUiApp("signal"), host)
    finally:
        timer.join()

    assert host.close_requested.is_set()
    assert signal.getsignal(signal.SIGINT) is previous_handler
    assert_port_released(host.options["url"])


def test_app_instance_cannot_run_twice():
    app = DemoUiApp("single use")
    first_host = FakeWindowHost(close_immediately=True)
    run_fake(app, first_host)
    with pytest.raises(NativeWebviewError, match="already started"):
        run_fake(app, FakeWindowHost(close_immediately=True))


def test_relative_xdg_data_home_is_rejected(monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", "relative")
    with pytest.raises(NativeWebviewError, match="absolute path"):
        run_fake(DemoUiApp("profile"), FakeWindowHost(close_immediately=True))


def test_profile_namespace_uses_application_id(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    captured = []
    host = FakeWindowHost(close_immediately=True)
    _run_native(
        DemoUiApp("profile"),
        application_id="com.example.factory-dashboard",
        async_main=None,
        width=1280,
        height=800,
        devtools=False,
        host_factory=lambda options: captured.append(options) or host,
    )
    assert captured[0].profile_path == (
        tmp_path
        / "rti-demo-ui-native"
        / "com.example.factory-dashboard"
    )
    assert captured[0].profile_path.is_dir()
