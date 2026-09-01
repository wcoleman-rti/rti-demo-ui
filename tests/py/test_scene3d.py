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

import json
from pathlib import Path

import pytest

from rti_demo_ui import DemoUiApp


FIXTURE = json.loads(
    (Path(__file__).parents[1] / "fixtures" / "scene3d_contract.json").read_text()
)


def test_scene3d_defaults_batch_noop_and_stale_id():
    app = DemoUiApp("Scene")
    scene = app.add_card("Arm").add_scene_3d(FIXTURE["defaults"]["asset"])
    assert scene.to_dict()["data"] == FIXTURE["defaults"]["expected_data"]
    revision = app._model.revision
    scene.apply_node_batch(FIXTURE["canonical_batch"]["batch"])
    assert app._model.revision == revision + 1
    assert (
        scene.to_dict()["data"]["nodes"][0]
        == FIXTURE["canonical_batch"]["expected"]["node"]
    )
    snapshot = scene.to_dict()
    scene.apply_node_batch([FIXTURE["canonical_batch"]["no_op"]["operation"]])
    assert scene.to_dict() == snapshot
    assert app._model.revision == revision + 1
    scene.remove_node("shoulder")
    with pytest.raises(ValueError, match="Scene3DViewport: node ID is stale"):
        scene.add_node("shoulder", "Arm/Shoulder")


@pytest.mark.parametrize(
    ("operation", "message"),
    [
        ({"op": "add", "id": "bad", "path": "Arm//Joint"}, "node path is invalid"),
        (
            {"op": "add", "id": "bad", "path": "Arm/Joint", "rotation": [0, 0, 0, 0]},
            "rotation must be a unit quaternion",
        ),
        (
            {"op": "add", "id": "bad", "path": "Arm/Joint", "scale": [1, 0, 1]},
            "scale values must be finite",
        ),
    ],
)
def test_scene3d_failed_batch_does_not_mutate(operation, message):
    app = DemoUiApp("Scene")
    scene = app.add_card("Arm").add_scene_3d("/models/surgical-arm.glb")
    revision = app._model.revision
    with pytest.raises(ValueError, match=message):
        scene.apply_node_batch([operation])
    assert app._model.revision == revision
    assert scene.to_dict()["data"]["nodes"] == []


def test_scene3d_static_root_requires_regular_glb(tmp_path):
    (tmp_path / "index.html").write_text("<html></html>")
    (tmp_path / "model.glb").write_bytes(b"glb")
    app = DemoUiApp("Scene", static_root=tmp_path)
    app.add_card("Arm").add_scene_3d("/model.glb")
    with pytest.raises(ValueError, match="absolute same-origin .glb path"):
        app.add_card("Bad").add_scene_3d("/missing.glb")
