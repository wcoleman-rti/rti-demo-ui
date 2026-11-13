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
import http.client
import json
import shutil
import threading
from pathlib import Path

import pytest

from rti_demo_ui import DemoUiApp


FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures"
VECTORS = json.loads((FIXTURE_ROOT / "static_route_vectors.json").read_text())


def _prepare_static_root(destination: Path) -> Path:
    root = destination / "web"
    shutil.copytree(FIXTURE_ROOT / "static_root", root)
    (root / "inside-link.txt").symlink_to("symlink-target.txt")
    (root / "broken-link.txt").symlink_to("missing-target.txt")
    (root / "directory-link").symlink_to("nested", target_is_directory=True)
    outside = destination / "outside.txt"
    outside.write_text("outside\n")
    (root / "escape-link.txt").symlink_to(outside)
    return root


def _request(port: int, path: str):
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
    connection.request("GET", path)
    response = connection.getresponse()
    body = response.read()
    headers = dict(response.getheaders())
    connection.close()
    return response.status, headers, body


def _start_app_on_thread(app):
    loop = asyncio.new_event_loop()

    def run_app():
        asyncio.set_event_loop(loop)
        loop.run_until_complete(app.run())

    thread = threading.Thread(target=run_app, daemon=True)
    thread.start()
    asyncio.run_coroutine_threadsafe(app.wait_until_ready(), loop).result(2)
    return loop, thread


@pytest.fixture
def custom_app(tmp_path):
    root = _prepare_static_root(tmp_path)
    app = DemoUiApp("Custom fixture", static_root=root)
    loop, thread = _start_app_on_thread(app)
    try:
        yield app, root
    finally:
        asyncio.run_coroutine_threadsafe(app.stop(), loop).result(2)
        thread.join(2)
        assert not thread.is_alive()
        loop.close()


def test_static_root_vectors(custom_app):
    app, _root = custom_app
    port = app.ready_info.port
    for vector in VECTORS:
        status, headers, body = _request(port, vector["path"])
        assert status == vector["status"], vector["name"]
        assert headers["Content-Type"] == vector["content_type"], vector["name"]
        assert headers["X-Content-Type-Options"] == "nosniff", vector["name"]
        if "body_contains" in vector:
            assert vector["body_contains"].encode() in body, vector["name"]
        if vector["response_class"] == "api_json":
            json.loads(body)


def test_static_root_rejected_before_run(tmp_path):
    with pytest.raises(ValueError, match="static_root"):
        DemoUiApp("invalid", static_root=tmp_path / "missing")
    file_path = tmp_path / "not-a-directory"
    file_path.write_text("file")
    with pytest.raises(ValueError, match="static_root"):
        DemoUiApp("invalid", static_root=file_path)
    empty_root = tmp_path / "empty"
    empty_root.mkdir()
    with pytest.raises(ValueError, match="index.html"):
        DemoUiApp("invalid", static_root=empty_root)
