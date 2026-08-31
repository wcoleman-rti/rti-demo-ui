import asyncio
import socket
import threading
import time
import unittest

from rti_demo_ui import DemoUiApp

from python_runner_prototype import NativeSpikeError, run_with_host


class FakeWindowHost:
    def __init__(
        self,
        *,
        close_immediately: bool = False,
        create_error: BaseException | None = None,
    ):
        self.close_immediately = close_immediately
        self.create_error = create_error
        self.close_requested = threading.Event()
        self.create_thread = None
        self.run_thread = None
        self.url = None

    def create(self, url: str) -> None:
        self.create_thread = threading.get_ident()
        self.url = url
        if self.create_error is not None:
            raise self.create_error
        if self.close_immediately:
            self.request_close()

    def run(self) -> None:
        self.run_thread = threading.get_ident()
        if not self.close_requested.wait(2):
            raise TimeoutError("fake window did not receive close request")

    def request_close(self) -> None:
        self.close_requested.set()


def assert_port_released(test: unittest.TestCase, url: str) -> None:
    port = int(url.rstrip("/").rsplit(":", 1)[1])
    with socket.socket() as probe:
        probe.settimeout(0.2)
        test.assertNotEqual(probe.connect_ex(("127.0.0.1", port)), 0)


class PythonRunnerPrototypeTests(unittest.TestCase):
    def test_window_close_joins_owner_and_releases_port(self):
        host = FakeWindowHost(close_immediately=True)
        trace = run_with_host(DemoUiApp("close"), host)

        self.assertTrue(trace["owner_loop_off_main_thread"])
        self.assertTrue(trace["server_joined"])
        self.assertEqual(host.create_thread, threading.main_thread().ident)
        self.assertEqual(host.run_thread, threading.main_thread().ident)
        assert_port_released(self, host.url)

    def test_window_initialization_failure_still_releases_port(self):
        host = FakeWindowHost(create_error=RuntimeError("window init failed"))

        with self.assertRaisesRegex(RuntimeError, "window init failed"):
            run_with_host(DemoUiApp("init failure"), host)

        assert_port_released(self, host.url)

    def test_bind_failure_surfaces_without_creating_window(self):
        with socket.socket() as blocker:
            blocker.bind(("127.0.0.1", 0))
            blocker.listen()
            port = blocker.getsockname()[1]
            host = FakeWindowHost()
            with self.assertRaisesRegex(
                NativeSpikeError, "server failed before readiness"
            ):
                run_with_host(DemoUiApp("bind failure", port=port), host)

        self.assertIsNone(host.url)

    def test_async_main_return_requests_window_close(self):
        host = FakeWindowHost()
        mutation_thread = []

        async def async_main(app):
            mutation_thread.append(threading.get_ident())
            app.set_data({"status": "complete"})

        trace = run_with_host(DemoUiApp("async return"), host, async_main=async_main)

        self.assertEqual(mutation_thread, [trace["owner_thread"]])
        self.assertTrue(host.close_requested.is_set())
        assert_port_released(self, host.url)

    def test_async_main_exception_is_raised_after_cleanup(self):
        host = FakeWindowHost()

        async def async_main(_app):
            raise ValueError("application failed")

        with self.assertRaisesRegex(ValueError, "application failed"):
            run_with_host(DemoUiApp("async failure"), host, async_main=async_main)

        assert_port_released(self, host.url)

    def test_window_close_cancels_and_awaits_async_main(self):
        host = FakeWindowHost(close_immediately=True)
        cleanup_complete = threading.Event()

        async def async_main(_app):
            try:
                await asyncio.Event().wait()
            finally:
                await asyncio.sleep(0)
                cleanup_complete.set()

        trace = run_with_host(
            DemoUiApp("async cancellation"), host, async_main=async_main
        )

        self.assertTrue(trace["server_joined"])
        self.assertTrue(cleanup_complete.is_set())
        assert_port_released(self, host.url)

    def test_simultaneous_close_and_async_return_is_idempotent(self):
        host = FakeWindowHost(close_immediately=True)

        async def async_main(_app):
            await asyncio.sleep(0)

        trace = run_with_host(DemoUiApp("simultaneous"), host, async_main=async_main)

        self.assertTrue(trace["server_joined"])
        assert_port_released(self, host.url)

    def test_server_stop_dispatches_window_close(self):
        host = FakeWindowHost()

        async def async_main(app):
            await asyncio.sleep(0.01)
            await app.stop()
            await asyncio.sleep(0.01)

        started = time.monotonic()
        trace = run_with_host(DemoUiApp("server stop"), host, async_main=async_main)

        self.assertLess(time.monotonic() - started, 2)
        self.assertTrue(trace["server_joined"])
        assert_port_released(self, host.url)


if __name__ == "__main__":
    unittest.main()
