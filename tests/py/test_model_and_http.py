import asyncio
import json
import socket
import threading

import pytest
from aiohttp import ClientSession

from rti_demo_ui import DemoUiApp, Severity


def make_app(port):
    return DemoUiApp(title="Test App", port=port, host="127.0.0.1")


def configure_scene(app):
    card = app.add_card("Fleet")
    scene = card.add_scene_2d(600, 400, (-100.0, 100.0, -100.0, 100.0))
    return card, scene


async def start_app(app):
    task = asyncio.create_task(app.run())
    await app._wait_until_ready()
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
    assert snapshot["links"] == []
    assert [entity["id"] for entity in snapshot["entities"]] == ["v2"]


def test_insertion_order_stable():
    app = make_app(19083)
    _card, scene = configure_scene(app)
    scene.add_entity("v3", 0.0, 0.0)
    scene.add_entity("v1", 0.0, 0.0)
    scene.add_entity("v2", 0.0, 0.0)
    assert [entity["id"] for entity in scene.to_dict()["entities"]] == [
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
    app = make_app(19086)
    run_task = await start_app(app)
    try:
        async with ClientSession() as session:
            for path, content_type in [
                ("/", "text/html; charset=utf-8"),
                ("/sdk/runtime.js", "application/javascript; charset=utf-8"),
                ("/sdk/theme.css", "text/css; charset=utf-8"),
            ]:
                response = await session.get(f"http://127.0.0.1:19086{path}")
                assert response.status == 200
                assert response.headers["Content-Type"] == content_type
                assert response.headers["X-Content-Type-Options"] == "nosniff"

            health = await session.get("http://127.0.0.1:19086/api/health")
            assert json.loads(await health.read()) == {"status": "ok"}

            state = await session.get("http://127.0.0.1:19086/api/state")
            payload = json.loads(await state.read())
            assert payload["schema_version"] == 1
            assert payload["title"] == "Test App"

            missing = await session.get("http://127.0.0.1:19086/does-not-exist")
            assert missing.status == 404
            assert json.loads(await missing.read()) == {"error": "not found"}
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
