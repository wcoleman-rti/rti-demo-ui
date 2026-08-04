import json
import threading
import time
import urllib.error
import urllib.request

import pytest

from rti_demo_gui_sdk import CoreApp, Severity


def make_app(port):
    return CoreApp(title="Test App", port=port)


def test_revision_increments_once_per_mutation():
    app = make_app(19080)
    assert app._model.revision == 0
    card = app.add_card("Fleet")
    assert app._model.revision == 1
    scene = card.add_scene_2d(600, 400, (-100.0, 100.0, -100.0, 100.0))
    assert app._model.revision == 2
    scene.add_entity("v1", 0.0, 0.0)
    assert app._model.revision == 3


def test_failed_mutation_does_not_change_revision():
    app = make_app(19081)
    card = app.add_card("Fleet")
    scene = card.add_scene_2d(600, 400, (-100.0, 100.0, -100.0, 100.0))
    scene.add_entity("v1", 0.0, 0.0)
    revision_before = app._model.revision
    with pytest.raises(ValueError):
        scene.add_entity("v1", 1.0, 1.0)
    assert app._model.revision == revision_before


def test_entity_removal_removes_links():
    app = make_app(19082)
    card = app.add_card("Fleet")
    scene = card.add_scene_2d(600, 400, (-100.0, 100.0, -100.0, 100.0))
    scene.add_entity("v1", 0.0, 0.0)
    scene.add_entity("v2", 1.0, 1.0)
    scene.add_link("v1", "v2")
    scene.remove_entity("v1")
    snapshot = scene.to_dict()
    assert snapshot["links"] == []
    assert [e["id"] for e in snapshot["entities"]] == ["v2"]


def test_insertion_order_stable():
    app = make_app(19083)
    card = app.add_card("Fleet")
    scene = card.add_scene_2d(600, 400, (-100.0, 100.0, -100.0, 100.0))
    scene.add_entity("v3", 0.0, 0.0)
    scene.add_entity("v1", 0.0, 0.0)
    scene.add_entity("v2", 0.0, 0.0)
    assert [e["id"] for e in scene.to_dict()["entities"]] == ["v3", "v1", "v2"]


def test_validation_errors():
    app = make_app(19084)
    card = app.add_card("Fleet")
    with pytest.raises(ValueError):
        card.add_scene_2d(-1, 400, (-100.0, 100.0, -100.0, 100.0))
    with pytest.raises(ValueError):
        card.add_scene_2d(600, 400, (100.0, -100.0, -100.0, 100.0))
    scene = card.add_scene_2d(600, 400, (-100.0, 100.0, -100.0, 100.0))
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


def test_timer_and_stop_idempotent():
    app = make_app(19085)
    counter = {"n": 0}

    def tick():
        counter["n"] += 1

    handle = app.add_timer(20, tick)
    time.sleep(0.1)
    handle.cancel()
    n_after_cancel = counter["n"]
    time.sleep(0.1)
    assert counter["n"] == n_after_cancel
    app.stop()
    app.stop()


def test_http_contract_routes():
    app = make_app(19086)
    thread = threading.Thread(target=app.run, daemon=True)
    thread.start()
    time.sleep(0.3)
    base = "http://127.0.0.1:19086"
    try:
        for path, content_type in [
            ("/", "text/html; charset=utf-8"),
            ("/runtime.js", "application/javascript; charset=utf-8"),
            ("/theme.css", "text/css; charset=utf-8"),
            ("/gallery", "text/html; charset=utf-8"),
        ]:
            response = urllib.request.urlopen(base + path)
            assert response.status == 200
            assert response.headers.get("Content-Type") == content_type
            assert response.headers.get("X-Content-Type-Options") == "nosniff"

        health = urllib.request.urlopen(base + "/api/health")
        assert json.loads(health.read()) == {"status": "ok"}

        state = urllib.request.urlopen(base + "/api/state")
        payload = json.loads(state.read())
        assert payload["schema_version"] == 1
        assert payload["title"] == "Test App"

        with pytest.raises(urllib.error.HTTPError) as excinfo:
            urllib.request.urlopen(base + "/does-not-exist")
        assert excinfo.value.code == 404
        assert json.loads(excinfo.value.read()) == {"error": "not found"}
    finally:
        app.stop()


def test_severity_enum_values():
    assert Severity.success.value == "success"
