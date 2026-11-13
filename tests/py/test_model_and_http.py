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
import json
import socket
import threading
from importlib import resources
from pathlib import Path

import pytest
from aiohttp import ClientSession

from rti_demo_ui import (
    DemoUiApp,
    Severity,
    TimeSeriesSeries,
    TimeSeriesStatus,
)
from rti_demo_ui.demo_ui_app import _json_bytes

SSE_VECTORS = json.loads(
    (Path(__file__).parents[1] / "fixtures" / "sse_event_contract.json").read_text()
)
TIME_SERIES_FIXTURE = json.loads(
    (Path(__file__).parents[1] / "fixtures" / "time_series_contract.json").read_text()
)


def test_canonical_json_serialization_matches_shared_vectors():
    vector = SSE_VECTORS["unicode_serialization"]
    assert _json_bytes(vector["payload"]).decode() == vector["serialized"]


def make_app(port):
    return DemoUiApp(title="Test App", port=port, host="127.0.0.1")


def test_canonical_and_packaged_presentation_assets_match():
    asset_package = resources.files("rti_demo_ui").joinpath("_assets")
    asset_root = Path(__file__).parents[2] / "assets"
    for filename in ("runtime.js", "theme.css", "momentary.js"):
        assert (
            asset_package.joinpath(filename).read_bytes()
            == (asset_root / filename).read_bytes()
        )


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


def enable_test_uplot(app):
    app._register_adapter("uplot", "1", ("timeseries",), b"export {}", b".chart{}")


def test_adapter_registry_rejects_component_collisions_atomically():
    app = DemoUiApp("Adapters")
    enable_test_uplot(app)
    with pytest.raises(ValueError, match="already registered"):
        app._register_adapter("uplot", "2", ("other",), b"runtime")
    with pytest.raises(ValueError, match="colliding"):
        app._register_adapter("another", "1", ("timeseries",), b"runtime")
    with pytest.raises(ValueError, match="colliding"):
        app._register_adapter("reserved", "1", ("table",), b"runtime")
    assert app._adapter_manifest()["adapters"][0]["components"] == ["timeseries"]
    with pytest.raises(ValueError, match="reserved"):
        app.add_card("Custom").add_custom_component("timeseries", {})


def test_time_series_backend_matches_shared_cross_language_fixture():
    app = DemoUiApp("Chart")
    enable_test_uplot(app)
    chart = app.add_card("Trend").add_time_series(
        "Rate",
        [
            TimeSeriesSeries(
                "rate",
                "Rate",
                "Hz",
                samples=[(1, 1), (2, None)],
            )
        ],
        x_label="Time",
    )
    assert app._model.snapshot() == TIME_SERIES_FIXTURE["snapshot"]
    app._model.start_dirty_tracking_locked()
    chart.append("rate", [(3, 2), (4, None)])
    assert (
        app._model.flush_dirty_targets_locked() == TIME_SERIES_FIXTURE["append_patch"]
    )
    assert app._model.snapshot() == TIME_SERIES_FIXTURE["snapshot_after_append"]


def test_time_series_validation_retention_and_atomic_replacement():
    app = make_app(19085)
    card = app.add_card("Trends")
    with pytest.raises(RuntimeError, match="enable the optional uPlot adapter"):
        card.add_time_series("Rate", [TimeSeriesSeries("rate", "Rate")])
    enable_test_uplot(app)
    before_invalid_add = app._model.revision
    with pytest.raises(ValueError, match="1 to 8"):
        card.add_time_series(
            "Too many",
            [
                TimeSeriesSeries(f"series-{index}", f"Series {index}")
                for index in range(9)
            ],
        )
    assert app._model.revision == before_invalid_add
    chart = card.add_time_series(
        "Rate",
        [
            TimeSeriesSeries(
                "rate",
                "Rate",
                "Hz",
                samples=[(1000, 2.0), (2000, None)],
            )
        ],
        status=TimeSeriesStatus.live,
        x_range=(0, 5000),
    )
    baseline = chart.to_dict()
    revision = app._model.revision

    for invalid in (
        [(3000, 3.0), (3000, 4.0)],
        [(3000, float("nan"))],
        [(3000, float("inf"))],
        [(3000, 3.0)] * 1025,
    ):
        with pytest.raises(ValueError):
            chart.append("rate", invalid)
        assert chart.to_dict() == baseline
        assert app._model.revision == revision

    with pytest.raises(ValueError):
        chart.replace_series("rate", [(3000, 3.0), (2000, 4.0)])
    with pytest.raises(ValueError, match="at most 10000"):
        chart.replace_series("rate", [(index, float(index)) for index in range(10_001)])
    assert chart.to_dict() == baseline
    assert app._model.revision == revision

    chart.append("rate", [(3000, 3.0)])
    assert app._model.revision == revision + 1
    assert chart.to_dict()["data"]["series"][0]["samples"][-1] == [3000.0, 3.0]
    chart.set_status("stale")
    assert chart.to_dict()["data"]["status"] == "stale"

    chart.replace_series("rate", [(float(i), float(i)) for i in range(10_000)])
    retained_revision = app._model.revision
    chart.append("rate", [(10_000, 10_000.0), (10_001, None)])
    samples = chart.to_dict()["data"]["series"][0]["samples"]
    assert len(samples) == 10_000
    assert samples[0] == [2.0, 2.0]
    assert samples[-1] == [10_001.0, None]
    assert app._model.revision == retained_revision + 1


def test_time_series_appends_publish_delta_batches_and_replace_is_full():
    app = make_app(19086)
    enable_test_uplot(app)
    chart = app.add_card("Trends").add_time_series(
        "Rate",
        [TimeSeriesSeries("rate", "Rate", samples=[(1, 1.0)])],
    )
    app._model.start_dirty_tracking_locked()
    chart.append("rate", [(2, 2.0)])
    chart.append("rate", [(3, None), (4, 4.0)])
    patch = app._model.flush_dirty_targets_locked()
    assert patch["changes"] == [
        {
            "op": "append-timeseries",
            "card_id": "card-1",
            "component_id": "timeseries-1",
            "component_revision": patch["revision"],
            "series": [
                {
                    "id": "rate",
                    "samples": [[2.0, 2.0], [3.0, None], [4.0, 4.0]],
                }
            ],
        }
    ]
    assert "samples" not in patch["changes"][0]

    chart.replace_series("rate", [(5, 5.0)])
    replace_patch = app._model.flush_dirty_targets_locked()
    assert replace_patch["changes"][0]["op"] == "upsert-component"
    assert replace_patch["changes"][0]["value"]["data"]["series"][0]["samples"] == [
        [5.0, 5.0]
    ]


def test_oversized_pending_append_batch_falls_back_to_full_component():
    app = make_app(19087)
    enable_test_uplot(app)
    chart = app.add_card("Trends").add_time_series(
        "Rate",
        [
            TimeSeriesSeries(
                "rate",
                "Rate",
                samples=[(index, float(index)) for index in range(10_000)],
            )
        ],
    )
    app._model.start_dirty_tracking_locked()
    for batch_index in range(10):
        start = 10_000 + batch_index * 1_024
        chart.append(
            "rate",
            [
                (timestamp, float(timestamp))
                for timestamp in range(start, start + 1_024)
            ],
        )
    patch = app._model.flush_dirty_targets_locked()
    assert patch["changes"][0]["op"] == "upsert-component"
    assert len(patch["changes"][0]["value"]["data"]["series"][0]["samples"]) == 10_000


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


def test_dirty_target_removal_precedence_and_id_reuse_rejection():
    vectors = SSE_VECTORS["dirty_target_removal"]

    app = DemoUiApp(title="Contract")
    card = app.add_card("Card")
    app._model.start_dirty_tracking_locked()
    app._model.commit_card_locked(card.id)
    app._model.commit_card_removal_locked(card.id)
    card_patch = app._model.flush_dirty_targets_locked()
    assert card_patch == vectors["card_patch"]
    assert _json_bytes(card_patch).decode() == vectors["serialized_card_patch"]
    revision = app._model.revision
    with pytest.raises(RuntimeError):
        app._model.commit_card_locked(card.id)
    assert app._model.revision == revision

    app = DemoUiApp(title="Contract")
    card = app.add_card("Card")
    metric = card.add_metric("Rate", 1)
    app._model.start_dirty_tracking_locked()
    app._model.commit_component_locked(card.id, metric.id)
    app._model.commit_component_removal_locked(card.id, metric.id)
    component_patch = app._model.flush_dirty_targets_locked()
    assert component_patch == vectors["component_patch"]
    assert (
        _json_bytes(component_patch).decode() == vectors["serialized_component_patch"]
    )
    revision = app._model.revision
    with pytest.raises(RuntimeError):
        app._model.commit_component_locked(card.id, metric.id)
    assert app._model.revision == revision


def test_structural_component_order_matches_shared_bytes():
    vector = next(
        item
        for item in SSE_VECTORS["operation_vectors"]["valid"]
        if item["name"] == "whole card upsert preserves component insertion order"
    )
    app = DemoUiApp(title="Contract")
    app._model.start_dirty_tracking_locked()
    card = app.add_card("Card")
    card.add_custom_component("custom-z", {}, id="custom-z")
    card.add_custom_component("custom-a", {}, id="custom-a")

    patch = app._model.flush_dirty_targets_locked()
    assert patch == vector["patch"]
    assert _json_bytes(patch).decode() == vector["serialized"]
    assert app._model.snapshot() == vector["expected"]


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
        with pytest.raises(RuntimeError, match="before run"):
            enable_test_uplot(app)
        async with ClientSession() as session:
            for path, content_type in [
                ("/", "text/html; charset=utf-8"),
                ("/sdk/runtime.js", "application/javascript; charset=utf-8"),
                ("/sdk/runtime3d.js", "application/javascript; charset=utf-8"),
                ("/sdk/client.js", "application/javascript; charset=utf-8"),
                ("/sdk/momentary.js", "application/javascript; charset=utf-8"),
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

            manifest = await session.get(f"{base_url}/sdk/adapters/manifest.json")
            assert manifest.status == 200
            assert manifest.headers["Cache-Control"] == "no-cache"
            assert manifest.headers["X-Content-Type-Options"] == "nosniff"
            assert await manifest.json() == {"schema_version": 1, "adapters": []}
            disabled_asset = await session.get(
                f"{base_url}/sdk/adapters/uplot/runtime.js"
            )
            assert disabled_asset.status == 404

            missing = await session.get(f"{base_url}/does-not-exist")
            assert missing.status == 404
            assert json.loads(await missing.read()) == {"error": "not found"}
    finally:
        await app.stop()
        await run_task


@pytest.mark.asyncio
async def test_enabled_adapter_manifest_and_local_asset_routes():
    app = make_app(0)
    enable_test_uplot(app)
    run_task = await start_app(app)
    try:
        async with ClientSession() as session:
            base = app.ready_info.url
            manifest = await session.get(f"{base}/sdk/adapters/manifest.json")
            assert manifest.headers["Cache-Control"] == "no-cache"
            assert await manifest.json() == {
                "schema_version": 1,
                "adapters": [
                    {
                        "name": "uplot",
                        "version": "1",
                        "components": ["timeseries"],
                        "module": "/sdk/adapters/uplot/runtime.js",
                        "styles": ["/sdk/adapters/uplot/theme.css"],
                    }
                ],
            }
            runtime = await session.get(f"{base}/sdk/adapters/uplot/runtime.js")
            stylesheet = await session.get(f"{base}/sdk/adapters/uplot/theme.css")
            assert runtime.status == stylesheet.status == 200
            assert (
                runtime.headers["Content-Type"]
                == "application/javascript; charset=utf-8"
            )
            assert stylesheet.headers["Content-Type"] == "text/css; charset=utf-8"
            assert await runtime.read() == b"export {}"
            assert await stylesheet.read() == b".chart{}"
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
@pytest.mark.parametrize(
    ("options", "expected_prefix"),
    [
        ({}, "RTI Demo UI listening on"),
        (
            {"listening_message_prefix": "ArmController listening on"},
            "ArmController listening on",
        ),
        ({"listening_message_prefix": ""}, ""),
        ({"listening_message_prefix": None}, None),
    ],
)
async def test_listening_message_prefix(options, expected_prefix, capsys):
    app = DemoUiApp("Listening message", **options)
    run_task = await start_app(app)
    ready_info = app.ready_info
    await app.stop()
    await run_task

    output = capsys.readouterr().out
    if expected_prefix is None:
        assert output == ""
    else:
        prefix = f"{expected_prefix} " if expected_prefix else ""
        assert output == f"{prefix}{ready_info.url}/\n"


def test_invalid_listening_message_prefix():
    with pytest.raises(ValueError, match="listening_message_prefix"):
        DemoUiApp("Invalid announcement", listening_message_prefix=12)


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
