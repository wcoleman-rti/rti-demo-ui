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

import pytest
from aiohttp import ClientSession, TCPConnector

from rti_demo_ui import DemoUiApp, Severity


async def start_app(app):
    task = asyncio.create_task(app.run())
    await app.wait_until_ready()
    return task


async def read_sse_message(response, timeout=1):
    fields = {}
    comments = []
    while True:
        line = await asyncio.wait_for(response.content.readline(), timeout)
        if line == b"":
            raise EOFError("event stream closed")
        if line == b"\n":
            break
        decoded = line.decode("utf-8").rstrip("\n")
        if decoded.startswith(":"):
            comments.append(decoded[1:].strip())
            continue
        name, value = decoded.split(":", 1)
        fields[name] = value.lstrip()
    if "data" in fields:
        fields["data"] = json.loads(fields["data"])
    fields["comments"] = comments
    return fields


@pytest.mark.asyncio
async def test_event_route_sends_retry_and_immediate_snapshot():
    app = DemoUiApp("Events")
    app.set_data({"before": "start"})
    app.add_card("Status").add_metric("Rate", 1)
    run_task = await start_app(app)
    try:
        async with ClientSession() as session:
            response = await session.get(
                f"{app.ready_info.url}/api/events",
                headers={"Accept": "text/event-stream", "Last-Event-ID": "1"},
            )
            assert response.status == 200
            assert response.headers["Content-Type"] == "text/event-stream"
            assert response.headers["Cache-Control"] == "no-cache"
            assert response.headers["X-Content-Type-Options"] == "nosniff"
            assert "Content-Length" not in response.headers
            assert "Access-Control-Allow-Origin" not in response.headers
            assert await read_sse_message(response) == {
                "retry": "1000",
                "comments": [],
            }
            snapshot = await read_sse_message(response)
            assert snapshot["event"] == "snapshot"
            assert snapshot["id"] == str(app._model.revision)
            assert snapshot["data"] == app._model.snapshot()
            response.close()

            rejected = await session.post(f"{app.ready_info.url}/api/events")
            assert rejected.status == 405
            assert await rejected.json() == {"error": "method not allowed"}
    finally:
        await app.stop()
        await run_task


@pytest.mark.asyncio
async def test_event_stream_coalesces_latest_state_for_multiple_subscribers():
    app = DemoUiApp("Events")
    metric = app.add_card("Status").add_metric("Rate", 1)
    run_task = await start_app(app)
    connector = TCPConnector(limit=0)
    try:
        async with ClientSession(connector=connector) as session:
            first = await session.get(f"{app.ready_info.url}/api/events")
            second = await session.get(f"{app.ready_info.url}/api/events")
            for response in (first, second):
                await read_sse_message(response)
                initial = await read_sse_message(response)
                assert initial["event"] == "snapshot"
                assert initial["data"]["revision"] == 2

            app.set_data({"mode": "live"})
            metric.set_value(2)
            metric.set_value(42, Severity.warning)

            publications = [
                await read_sse_message(first),
                await read_sse_message(second),
            ]
            assert publications[0] == publications[1]
            patch = publications[0]
            assert patch["event"] == "patch"
            assert patch["id"] == "5"
            assert patch["data"] == {
                "base_revision": 2,
                "changes": [
                    {"op": "replace-app-data", "value": {"mode": "live"}},
                    {
                        "card_id": "card-1",
                        "op": "upsert-component",
                        "value": {
                            "data": {
                                "label": "Rate",
                                "severity": "warning",
                                "value": 42,
                            },
                            "id": "metric-1",
                            "revision": 5,
                            "type": "metric",
                        },
                    },
                ],
                "revision": 5,
                "schema_version": 1,
            }
            first.close()
            second.close()
    finally:
        await app.stop()
        await run_task


@pytest.mark.asyncio
async def test_publication_is_live_and_limited_to_thirty_hertz():
    app = DemoUiApp("Events")
    metric = app.add_card("Status").add_metric("Rate", 0)
    run_task = await start_app(app)
    subscriber = app._events.subscribe()
    subscriber.queue.get_nowait()
    loop = asyncio.get_running_loop()
    publication_times = []
    original_publish = app._events._publish

    def record_publish(patch):
        publication_times.append(loop.time())
        original_publish(patch)
        subscriber.queue.get_nowait()

    app._events._publish = record_publish
    try:
        deadline = loop.time() + 0.2
        metric.set_value(1)
        while len(publication_times) < 1 and loop.time() < deadline:
            await asyncio.sleep(0.001)
        assert len(publication_times) == 1

        metric.set_value(2)
        metric.set_value(3)
        deadline = loop.time() + 0.2
        while len(publication_times) < 2 and loop.time() < deadline:
            await asyncio.sleep(0.001)
        assert len(publication_times) == 2
        assert publication_times[1] - publication_times[0] >= (
            app._events.publication_interval - 0.002
        )
    finally:
        await app.stop()
        await run_task


@pytest.mark.asyncio
async def test_sustained_burst_is_bounded_and_converges_to_latest_state():
    app = DemoUiApp("Events")
    metric = app.add_card("Status").add_metric("Rate", 0)
    run_task = await start_app(app)
    subscriber = app._events.subscribe()
    subscriber.queue.get_nowait()
    loop = asyncio.get_running_loop()
    publication_times = []
    publications = []
    max_queue_size = 0
    original_publish = app._events._publish

    def record_publish(patch):
        nonlocal max_queue_size
        original_publish(patch)
        publication_times.append(loop.time())
        publications.append(patch)
        max_queue_size = max(max_queue_size, subscriber.queue.qsize())
        subscriber.queue.get_nowait()

    app._events._publish = record_publish
    try:
        last_value = 0
        burst_end = loop.time() + 1.05
        while loop.time() < burst_end:
            last_value += 1
            metric.set_value(last_value)
            await asyncio.sleep(0.001)

        deadline = loop.time() + 0.2
        while (
            not publications or publications[-1]["revision"] != app._model.revision
        ) and loop.time() < deadline:
            await asyncio.sleep(0.001)

        assert publications[-1]["revision"] == app._model.revision
        assert publications[-1]["changes"][0]["value"]["data"]["value"] == last_value
        for start in publication_times:
            assert (
                sum(start <= value < start + 1.0 for value in publication_times) <= 30
            )
        assert subscriber.queue.maxsize == 1
        assert max_queue_size == 1
        assert not subscriber.closed
    finally:
        await app.stop()
        await run_task


@pytest.mark.asyncio
async def test_event_stream_admission_is_bounded_at_sixteen():
    app = DemoUiApp("Events")
    run_task = await start_app(app)
    connector = TCPConnector(limit=0)
    responses = []
    try:
        async with ClientSession(connector=connector) as session:
            for _ in range(16):
                response = await session.get(f"{app.ready_info.url}/api/events")
                responses.append(response)
                assert response.status == 200
                await read_sse_message(response)
                await read_sse_message(response)

            rejected = await session.get(f"{app.ready_info.url}/api/events")
            assert rejected.status == 503
            assert await rejected.json() == {"error": "event stream capacity reached"}
    finally:
        for response in responses:
            response.close()
        await app.stop()
        await run_task


@pytest.mark.asyncio
async def test_event_stream_heartbeat_and_idle_shutdown():
    app = DemoUiApp("Events")
    app._events.heartbeat_interval = 0.01
    run_task = await start_app(app)
    session = ClientSession()
    response = await session.get(f"{app.ready_info.url}/api/events")
    await read_sse_message(response)
    await read_sse_message(response)
    assert await read_sse_message(response) == {
        "comments": ["heartbeat"],
    }

    await asyncio.wait_for(app.stop(), timeout=1)
    await asyncio.wait_for(run_task, timeout=1)
    assert await response.content.read() == b""
    await session.close()


@pytest.mark.asyncio
async def test_slow_subscriber_gets_one_snapshot_then_disconnects():
    app = DemoUiApp("Events")
    run_task = await start_app(app)
    try:
        first_subscriber = app._events.subscribe()
        second_subscriber = app._events.subscribe()
        for subscriber in (first_subscriber, second_subscriber):
            initial = subscriber.queue.get_nowait()
            assert initial.snapshot

        app.set_data({"publication": 1})
        first = app._model.flush_dirty_targets_locked()
        app._events._publish(first)
        for subscriber in (first_subscriber, second_subscriber):
            pending = subscriber.queue.get_nowait()
            assert not pending.snapshot
            subscriber.queue.put_nowait(pending)

        app.set_data({"publication": 2})
        second = app._model.flush_dirty_targets_locked()
        app._events._publish(second)
        first_reset = first_subscriber.queue.get_nowait()
        second_reset = second_subscriber.queue.get_nowait()
        assert first_reset is second_reset
        assert first_reset.snapshot
        assert first_reset.revision == 2

        for subscriber in (first_subscriber, second_subscriber):
            subscriber.queue.put_nowait(first_reset)
            subscriber.reset_pending = True
        app.set_data({"publication": 3})
        third = app._model.flush_dirty_targets_locked()
        app._events._publish(third)
        assert first_subscriber.closed
        assert second_subscriber.closed
        assert app._events.subscriber_count == 0
    finally:
        await app.stop()
        await run_task


@pytest.mark.asyncio
async def test_revision_tail_mismatch_gets_current_snapshot():
    app = DemoUiApp("Events")
    run_task = await start_app(app)
    try:
        subscriber = app._events.subscribe()
        subscriber.queue.get_nowait()
        subscriber.tail_revision = 99

        app.set_data({"current": True})
        patch = app._model.flush_dirty_targets_locked()
        app._events._publish(patch)

        replacement = subscriber.queue.get_nowait()
        assert replacement.snapshot
        assert replacement.revision == 1
        assert b'"current":true' in replacement.body
    finally:
        await app.stop()
        await run_task


@pytest.mark.asyncio
async def test_sse_write_timeout_is_reported_as_unwritable():
    class Transport:
        @staticmethod
        def is_closing():
            return False

    class Request:
        transport = Transport()

    class Response:
        async def write(self, _body):
            await asyncio.sleep(1)

    app = DemoUiApp("Events")
    app._events.write_timeout = 0.01
    assert not await app._write_sse(Request(), Response(), b"blocked")


@pytest.mark.asyncio
async def test_peer_disconnect_removes_subscriber():
    app = DemoUiApp("Events")
    app._events.heartbeat_interval = 0.01
    run_task = await start_app(app)
    session = ClientSession()
    try:
        response = await session.get(f"{app.ready_info.url}/api/events")
        await read_sse_message(response)
        await read_sse_message(response)
        assert app._events.subscriber_count == 1
        response.close()
        for _ in range(100):
            if app._events.subscriber_count == 0:
                break
            await asyncio.sleep(0.01)
        assert app._events.subscriber_count == 0
    finally:
        await session.close()
        await app.stop()
        await run_task


@pytest.mark.asyncio
async def test_run_cancellation_closes_idle_event_stream():
    app = DemoUiApp("Events")
    run_task = await start_app(app)
    session = ClientSession()
    try:
        response = await session.get(f"{app.ready_info.url}/api/events")
        await read_sse_message(response)
        await read_sse_message(response)
        assert app._events.subscriber_count == 1

        run_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(run_task, timeout=1)
        assert app._events.subscriber_count == 0
        assert await response.content.read() == b""
    finally:
        await session.close()
        if not run_task.done():
            await app.stop()
            await run_task
