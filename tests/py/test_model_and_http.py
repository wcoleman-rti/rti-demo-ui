import asyncio
import json
import socket
import threading
from pathlib import Path

import pytest
from aiohttp import ClientSession

from rti_demo_ui import DemoUiApp, Severity
from rti_demo_ui.demo_ui_app import _json_bytes

SSE_VECTORS = json.loads(
    (Path(__file__).parents[1] / "fixtures" / "sse_event_contract.json").read_text()
)


def test_canonical_json_serialization_matches_shared_vectors():
    vector = SSE_VECTORS["unicode_serialization"]
    assert _json_bytes(vector["payload"]).decode() == vector["serialized"]


def make_app(port):
    return DemoUiApp(title="Test App", port=port, host="127.0.0.1")


def configure_scene(app):
    card = app.add_card("Fleet")
    scene = card.add_scene_2d(600, 400, (-100.0, 100.0, -100.0, 100.0))
    return card, scene


async def start_app(app):
    task = asyncio.create_task(app.run())
    await app.wait_until_ready()
    return task


async def read_response(session, path):
    response = await session.get(f"http://127.0.0.1:{session.port}{path}")
    body = await response.read()
    return response, body


def test_revision_increments_once_per_mutation():
    app = make_app(19080)
    assert app._model.revision == 0
    card, scene = configure_scene(app)
    assert app._model.revision == 2
    scene.add_entity("v1", 0.0, 0.0)
    assert app._model.revision == 3
    assert card.title == "Fleet"


def test_dirty_targets_coalesce_to_latest_fixture_state():
    app = DemoUiApp(title="Contract")
    primary = app.add_card("Primary")
    rate = primary.add_metric("Rate", 10)
    secondary = app.add_card("Secondary")
    status = secondary.add_text("idle")

    assert app._model.flush_dirty_targets_locked() is None
    assert app._model.snapshot() == SSE_VECTORS["snapshots"]["backend_base"]
    app._model.start_dirty_tracking_locked()

    app.set_data({"site": "north", "mode": "active"})
    rate.set_value(20)
    rate.set_value(42, Severity.warning)
    secondary.add_metric("Load", 5)
    added = app.add_card("Added")
    added.add_text("ready")
    status.set_text("running", Severity.success)

    patch = app._model.flush_dirty_targets_locked()
    assert patch == SSE_VECTORS["coalesced_patch"]
    assert _json_bytes(patch).decode() == SSE_VECTORS["serialized_coalesced_patch"]
    assert app._model.snapshot() == SSE_VECTORS["snapshots"]["backend_latest"]
    assert app._model.flush_dirty_targets_locked() is None


def test_failed_mutation_does_not_change_revision():
    app = make_app(19081)
    _card, scene = configure_scene(app)
    scene.add_entity("v1", 0.0, 0.0)
    revision_before = app._model.revision
    with pytest.raises(ValueError):
        scene.add_entity("v1", 1.0, 1.0)
    assert app._model.revision == revision_before


def test_entity_removal_removes_links():
    app = make_app(19082)
    _card, scene = configure_scene(app)
    scene.add_entity("v1", 0.0, 0.0)
    scene.add_entity("v2", 1.0, 1.0)
    scene.add_link("v1", "v2")
    scene.remove_entity("v1")
    snapshot = scene.to_dict()
    assert snapshot["data"]["links"] == []
    assert [entity["id"] for entity in snapshot["data"]["entities"]] == ["v2"]


def test_insertion_order_stable():
    app = make_app(19083)
    _card, scene = configure_scene(app)
    scene.add_entity("v3", 0.0, 0.0)
    scene.add_entity("v1", 0.0, 0.0)
    scene.add_entity("v2", 0.0, 0.0)
    assert [entity["id"] for entity in scene.to_dict()["data"]["entities"]] == [
        "v3",
        "v1",
        "v2",
    ]


def test_validation_errors():
    app = make_app(19084)
    card, scene = configure_scene(app)
    with pytest.raises(ValueError):
        card.add_scene_2d(-1, 400, (-100.0, 100.0, -100.0, 100.0))
    with pytest.raises(ValueError):
        card.add_scene_2d(600, 400, (100.0, -100.0, -100.0, 100.0))
    with pytest.raises(ValueError):
        scene.add_entity("", 0.0, 0.0)
    with pytest.raises(ValueError):
        scene.add_entity("v1", float("nan"), 0.0)
    with pytest.raises(ValueError):
        scene.add_entity("v1", 0.0, 0.0, color="not-a-color")
    with pytest.raises(ValueError):
        scene.update_entity("missing")
    with pytest.raises(ValueError):
        scene.remove_entity("missing")
    scene.add_entity("v1", 0.0, 0.0)
    scene.add_entity("v2", 1.0, 1.0)
    with pytest.raises(ValueError):
        scene.add_link("v1", "missing")
    scene.add_link("v1", "v2")
    with pytest.raises(ValueError):
        scene.add_link("v1", "v2")
    with pytest.raises(ValueError):
        scene.remove_link("v2", "v1")


@pytest.mark.asyncio
async def test_http_contract_routes():
    app = make_app(0)
    run_task = await start_app(app)
    try:
        base_url = app.ready_info.url
        async with ClientSession() as session:
            for path, content_type in [
                ("/", "text/html; charset=utf-8"),
                ("/sdk/runtime.js", "application/javascript; charset=utf-8"),
                ("/sdk/runtime3d.js", "application/javascript; charset=utf-8"),
                ("/sdk/client.js", "application/javascript; charset=utf-8"),
                ("/sdk/theme.css", "text/css; charset=utf-8"),
            ]:
                response = await session.get(f"{base_url}{path}")
                assert response.status == 200
                assert response.headers["Content-Type"] == content_type
                assert response.headers["X-Content-Type-Options"] == "nosniff"

            health = await session.get(f"{base_url}/api/health")
            assert json.loads(await health.read()) == {"status": "ok"}

            state = await session.get(f"{base_url}/api/state")
            payload = json.loads(await state.read())
            assert payload["schema_version"] == 2
            assert payload["title"] == "Test App"
            assert payload["data"] == {}

            missing = await session.get(f"{base_url}/does-not-exist")
            assert missing.status == 404
            assert json.loads(await missing.read()) == {"error": "not found"}
    finally:
        await app.stop()
        await run_task


@pytest.mark.asyncio
async def test_command_contract_and_busy_admission():
    app = make_app(0)
    started = asyncio.Event()
    release = asyncio.Event()

    async def echo(payload):
        started.set()
        await release.wait()
        return payload

    app.register_command(
        "echo",
        {
            "type": "object",
            "properties": {"message": {"type": "string"}},
            "required": ["message"],
            "additionalProperties": False,
        },
        echo,
    )
    run_task = await start_app(app)
    try:
        base_url = app.ready_info.url
        async with ClientSession() as session:
            browser_capability_response = await session.get(
                f"{base_url}/api/command-capability"
            )
            assert browser_capability_response.status == 200
            browser_capability = (await browser_capability_response.json())[
                "capability"
            ]

            mismatched_host_response = await session.get(
                f"{base_url}/api/command-capability",
                headers={"Host": "localhost:1"},
            )
            assert mismatched_host_response.status == 404

            capability_response = await session.get(
                f"{base_url}/api/command-capability",
                headers={"Origin": base_url},
            )
            assert capability_response.status == 200
            capability = (await capability_response.json())["capability"]
            assert browser_capability == capability
            headers = {
                "Origin": base_url,
                "X-RTI-Demo-Command-Capability": capability,
            }
            missing_origin = await session.post(
                f"{base_url}/api/commands/echo",
                headers={"X-RTI-Demo-Command-Capability": browser_capability},
                json={"message": "missing origin"},
            )
            assert missing_origin.status == 403
            first = asyncio.create_task(
                session.post(
                    f"{base_url}/api/commands/echo",
                    headers=headers,
                    json={"message": "hello"},
                )
            )
            await started.wait()
            busy = await session.post(
                f"{base_url}/api/commands/echo",
                headers=headers,
                json={"message": "again"},
            )
            assert busy.status == 409
            assert (await busy.json())["error"]["code"] == "command_busy"
            release.set()
            response = await first
            assert response.status == 200
            assert (await response.json())["result"] == {"message": "hello"}

            invalid = await session.post(
                f"{base_url}/api/commands/echo",
                headers=headers,
                json={},
            )
            assert invalid.status == 400
            assert (await invalid.json())["error"]["code"] == "validation_error"
            oversized = await session.post(
                f"{base_url}/api/commands/echo",
                headers=headers,
                data="x" * (64 * 1024 + 1),
            )
            assert oversized.status == 413
            assert (await oversized.json())["error"]["code"] == "payload_too_large"
    finally:
        await app.stop()
        await run_task


def test_severity_enum_values():
    assert Severity.success.value == "success"


@pytest.mark.asyncio
async def test_stop_before_run_prevents_binding():
    app = make_app(19087)
    await app.stop()
    await app.run()
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 19087))


@pytest.mark.asyncio
async def test_bind_failure_does_not_print_listening_url(capsys):
    blocker = socket.socket()
    blocker.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    blocker.bind(("127.0.0.1", 19088))
    blocker.listen()
    try:
        with pytest.raises(OSError):
            await make_app(19088).run()
        assert "listening" not in capsys.readouterr().out
    finally:
        blocker.close()


@pytest.mark.asyncio
async def test_immediate_restart_after_stop():
    for _ in range(2):
        app = make_app(19089)
        run_task = await start_app(app)
        await app.stop()
        await asyncio.wait_for(run_task, timeout=1)


@pytest.mark.asyncio
async def test_run_is_single_use():
    app = make_app(19090)
    run_task = await start_app(app)
    with pytest.raises(RuntimeError, match="only be called once"):
        await app.run()
    await app.stop()
    await run_task
    with pytest.raises(RuntimeError, match="only be called once"):
        await app.run()


@pytest.mark.asyncio
async def test_run_cancellation_cleans_up_server():
    app = make_app(19091)
    run_task = await start_app(app)
    run_task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(run_task, timeout=1)
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 19091))


@pytest.mark.asyncio
async def test_foreign_thread_model_access_is_rejected():
    app = make_app(19092)
    run_task = await start_app(app)
    errors = []

    def access_model():
        try:
            app.add_card("foreign")
        except RuntimeError as error:
            errors.append(str(error))

    thread = threading.Thread(target=access_model)
    thread.start()
    thread.join()
    assert errors and "owner event loop" in errors[0]
    await app.stop()
    await run_task


@pytest.mark.asyncio
async def test_stop_waits_for_in_flight_request():
    app = make_app(19093)
    request_started = asyncio.Event()
    release_request = asyncio.Event()

    async def slow_handler(request):
        request_started.set()
        await release_request.wait()
        return web.Response(text="done")

    from aiohttp import web

    app._handle_request = slow_handler
    run_task = await start_app(app)
    async with ClientSession() as session:
        request_task = asyncio.create_task(session.get("http://127.0.0.1:19093/"))
        await request_started.wait()
        stop_task = asyncio.create_task(app.stop())
        await asyncio.sleep(0)
        assert not stop_task.done()
        release_request.set()
        response = await request_task
        assert response.status == 200
        assert await response.text() == "done"
        await stop_task
    await run_task
