import asyncio
import socket
import threading
import unittest

from rti_demo_ui import DemoUiApp

from python_host import EXPECTED_CHECKS, validate_report


class PythonOwnerLoopSpike(unittest.TestCase):
    def test_background_owner_loop_stops_and_releases_port(self):
        ready = threading.Event()
        state = {}
        app = DemoUiApp("Python native lifecycle spike")

        async def owner_main():
            run_task = asyncio.create_task(app.run())
            info = await app.wait_until_ready()
            app.set_data({"owner_thread": threading.get_ident()})
            state.update(loop=asyncio.get_running_loop(), info=info)
            ready.set()
            await run_task

        thread = threading.Thread(target=lambda: asyncio.run(owner_main()))
        thread.start()
        self.assertTrue(ready.wait(3))
        future = asyncio.run_coroutine_threadsafe(app.stop(), state["loop"])
        future.result(3)
        thread.join(3)
        self.assertFalse(thread.is_alive())

        with socket.socket() as probe:
            probe.bind((state["info"].host, state["info"].port))

    def test_conformance_report_shape_is_strict(self):
        valid = {
            "results": {
                name: {"passed": name != "sse", "evidence": f"{name} evidence"}
                for name in EXPECTED_CHECKS
            }
        }
        validate_report(valid)

        invalid = {"results": dict(valid["results"])}
        invalid["results"].pop("sse")
        with self.assertRaisesRegex(ValueError, "incomplete"):
            validate_report(invalid)


if __name__ == "__main__":
    unittest.main()
