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

"""Exercise scene-local presentation with real Three.js materials and controls."""

import json
import struct
import zlib
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).parents[2]


def _material_fixture():
    raw = (ROOT / "examples/web/arm3d/models/scene3d-fixture.glb").read_bytes()
    json_length = struct.unpack_from("<I", raw, 12)[0]
    document = json.loads(raw[20 : 20 + json_length])
    binary = raw[28 + json_length :]

    def chunk(kind, payload):
        return (
            struct.pack(">I", len(payload))
            + kind
            + payload
            + struct.pack(">I", zlib.crc32(kind + payload))
        )

    image = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"\0\xff\xff\xff\xff"))
        + chunk(b"IEND", b"")
    )
    document["bufferViews"].append(
        {"buffer": 0, "byteOffset": len(binary), "byteLength": len(image)}
    )
    document["images"] = [{"bufferView": 3, "mimeType": "image/png"}]
    document["textures"] = [{"source": 0}]
    document["materials"][0]["pbrMetallicRoughness"]["baseColorTexture"] = {"index": 0}
    document["materials"][0]["emissiveFactor"] = [0.05, 0.1, 0.2]
    document["buffers"][0]["byteLength"] = len(binary) + len(image)
    binary += image
    binary += b"\0" * (-len(binary) % 4)
    encoded = json.dumps(document).encode()
    encoded += b" " * (-len(encoded) % 4)
    return (
        struct.pack("<III", 0x46546C67, 2, 28 + len(encoded) + len(binary))
        + struct.pack("<II", len(encoded), 0x4E4F534A)
        + encoded
        + struct.pack("<II", len(binary), 0x004E4942)
        + binary
    )


def _page(browser, bundled=False):
    page = browser.new_page()
    three = ROOT / "tools/scene3d/node_modules/three"

    def serve(route):
        path = route.request.url.removeprefix("http://scene.test")
        if path == "/":
            route.fulfill(
                content_type="text/html",
                body="""<!doctype html>
                <script type="importmap">{"imports":{
                  "three":"/three/build/three.module.js",
                  "three/addons/":"/three/examples/jsm/"}}</script>
                <link rel="stylesheet" href="/theme.css">
                <div id="original"></div><div id="status"></div>
                <div id="failure"></div>""",
            )
        elif path == "/model.glb":
            route.fulfill(content_type="model/gltf-binary", body=_material_fixture())
        elif path == "/missing.glb":
            route.fulfill(status=404, body="not found")
        else:
            if path == "/renderer.js":
                file = (
                    ROOT / "assets/runtime3d.js"
                    if bundled
                    else ROOT / "tools/scene3d/src/runtime3d.js"
                )
            elif path == "/theme.css":
                file = ROOT / "assets/theme.css"
            else:
                file = three / path.removeprefix("/three/")
            route.fulfill(
                content_type="text/css" if path.endswith(".css") else "text/javascript",
                body=file.read_bytes(),
            )

    page.route("http://scene.test/**", serve)
    page.goto("http://scene.test/")
    return page


def test_materials_selection_camera_and_fallback_are_scene_local():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = _page(browser)
        result = page.evaluate(
            """async () => {
                const THREE = await import('three');
                const {OrbitControls} = await import('three/addons/controls/OrbitControls.js');
                const runtime = await import('/renderer.js');
                const copies = [];
                const meshCopy = THREE.Mesh.prototype.copy;
                THREE.Mesh.prototype.copy = function(...args) {
                    const result = meshCopy.apply(this, args);
                    if (args[0].name === 'Tool' && args[0].parent?.name === 'Arm') {
                        const accent = this.material.clone();
                        accent.color.setHex(0xed8b00);
                        this.material = [this.material, accent];
                    }
                    copies.push(this);
                    return result;
                };
                const controls = [];
                const update = OrbitControls.prototype.update;
                OrbitControls.prototype.update = function(...args) {
                    if (!controls.includes(this)) controls.push(this);
                    return update.apply(this, args);
                };
                const component = (id, asset='/model.glb') => ({
                    id, type: 'scene3d', revision: 1, data: {
                        asset, background: '#0a0e17',
                        camera: {position: [4, 3, 6], target: [0, 1.5, 0],
                                 min_distance: 0.1, max_distance: 100},
                        nodes: [{
                            id: 'base', path: 'Arm/Base', position: [0, 0.25, 0],
                            rotation: [0, 0, 0, 1], scale: [1, 1, 1],
                            status: 'success', visible: true,
                        }, {
                            id: 'tool', path: 'Arm/Tool', position: [0, 2.65, 0],
                            rotation: [0, 0, 0, 1], scale: [0.7, 0.7, 0.7],
                            status: 'success', visible: true,
                        }],
                    },
                });
                const original = component('original');
                const status = component('status');
                const originalHost = document.querySelector('#original');
                const statusHost = document.querySelector('#status');
                const options = {materialMode: 'original', reducedMotion: true};
                await runtime.reconcileScene3d(original, originalHost, options);
                const originalMesh = copies.filter(m => m.name === 'Base').at(-1);
                const appearance = m => ({
                    color: m.color.toArray(), emissive: m.emissive.toArray(),
                    metalness: m.metalness, roughness: m.roughness,
                    map: m.map?.uuid,
                });
                const baseline = appearance(originalMesh.material);
                const toolMesh = copies.filter(m => m.name === 'Tool').at(-1);
                const toolBaseline = toolMesh.material.map(appearance);
                const texture = originalMesh.material.map;
                await runtime.reconcileScene3d(status, statusHost, {reducedMotion: true});
                const statusMesh = copies.filter(m => m.name === 'Base').at(-1);
                const statusColor = statusMesh.material.color.toArray();
                const canvas = originalHost.querySelector('canvas');
                const orbit = controls[0];
                runtime.setScene3dCamera('original', {
                    position: [6, 0, 3], target: [0, 0, 0], up: [0, 0, 1],
                });
                const presetPosition = orbit.object.position.toArray();
                let invalid = false;
                try {
                    runtime.setScene3dCamera('original', {
                        position: [0, 0, 0], target: [0, 0, 0], up: [0, 0, 1],
                    });
                } catch (error) { invalid = error instanceof RangeError; }
                for (let i = 0; i < 8; ++i) {
                    original.revision++;
                    original.data.nodes[0].status = i % 2 ? 'danger' : 'warning';
                    original.data.nodes[0].position[0] = i / 10;
                    await runtime.reconcileScene3d(original, originalHost, {
                        ...options, showNodeList: false,
                    });
                }
                const afterUpdates = appearance(originalMesh.material);
                const sameCanvas = canvas === originalHost.querySelector('canvas');
                const sameControls = controls[0] === orbit && controls.length === 2;
                const cameraPersisted = orbit.object.position.distanceTo(
                    new THREE.Vector3().fromArray(presetPosition)) < 1e-8;
                const upPreserved = orbit.object.up.equals(new THREE.Vector3(0, 0, 1));
                const height = orbit.object.position.clone().sub(orbit.target).dot(orbit.object.up);
                orbit._rotateLeft(0.2);
                orbit.update();
                const orbitFrameUpdated = Math.abs(
                    orbit.object.position.clone().sub(orbit.target).dot(orbit.object.up) - height) < 1e-8;
                originalHost.querySelector('[data-action=reset-camera]').click();
                const resetPreset = orbit.object.position.distanceTo(
                    new THREE.Vector3().fromArray(presetPosition)) < 1e-8;
                const hiddenList = originalHost.querySelector('[role=listbox]').hidden;
                await runtime.reconcileScene3d(original, originalHost, {reducedMotion: true});
                const optionsPersisted = originalHost.querySelector('[role=listbox]').hidden
                    && JSON.stringify(appearance(originalMesh.material)) === JSON.stringify(baseline);
                const option = originalHost.querySelector('[role=option]');
                option.click();
                const selectedEmissive = originalMesh.material.emissive.getHex();
                await runtime.reconcileScene3d(original, originalHost, options);
                const remainsSelected = originalMesh.material.emissive.getHex() === 0xffffff;
                option.click();
                const restored = appearance(originalMesh.material);
                const toolOption = originalHost.querySelectorAll('[role=option]')[1];
                toolOption.click();
                const arrayHighlight = toolMesh.material.every(m => m.emissive.getHex() === 0xffffff);
                toolOption.click();
                const arrayRestored = JSON.stringify(toolBaseline) === JSON.stringify(toolMesh.material.map(appearance));
                const isolated = originalMesh.material !== statusMesh.material
                    && originalMesh.material.map === statusMesh.material.map
                    && originalMesh.material.map === texture;
                let geometryDisposals = 0;
                originalMesh.geometry.addEventListener('dispose', () => geometryDisposals++);
                runtime.disposeScene3d('status');
                const sharedGeometryRetained = geometryDisposals === 0;
                await runtime.reconcileScene3d(original, originalHost, options);
                const preservedAfterOtherDisposal = appearance(originalMesh.material);
                await runtime.reconcileScene3d(component('failure', '/missing.glb'),
                    document.querySelector('#failure'), {showNodeList: false});
                const fallbackVisible = !document.querySelector('#failure [role=listbox]').hidden
                    && !document.querySelector('#failure .sdk-scene3d-fallback-text').hidden;
                runtime.disposeScene3d('original');
                runtime.disposeScene3d('failure');
                return {baseline, afterUpdates, restored, preservedAfterOtherDisposal,
                        statusColor, selectedEmissive, remainsSelected, isolated,
                        sameCanvas, sameControls, cameraPersisted, upPreserved,
                        invalid, hiddenList, fallbackVisible, optionsPersisted,
                        arrayHighlight, arrayRestored, sharedGeometryRetained,
                        orbitFrameUpdated, resetPreset};
            }"""
        )
        browser.close()

    assert result["baseline"] == result["afterUpdates"] == result["restored"]
    assert result["baseline"] == result["preservedAfterOtherDisposal"]
    assert result["baseline"]["map"]
    assert result["baseline"]["metalness"] == 0.15
    assert result["baseline"]["roughness"] == 0.35
    assert result["baseline"]["color"] != result["statusColor"]
    assert result["selectedEmissive"] == 0xFFFFFF
    for field in (
        "remainsSelected",
        "isolated",
        "sameCanvas",
        "sameControls",
        "cameraPersisted",
        "upPreserved",
        "invalid",
        "hiddenList",
        "fallbackVisible",
        "optionsPersisted",
        "arrayHighlight",
        "arrayRestored",
        "sharedGeometryRetained",
        "orbitFrameUpdated",
        "resetPreset",
    ):
        assert result[field], field


def test_shipped_bundle_preserves_rendered_appearance_and_camera():
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = _page(browser, bundled=True)
        page.evaluate(
            """async () => {
                window.runtime = await import('/renderer.js');
                window.component = {id: 'original', type: 'scene3d', revision: 1, data: {
                    asset: '/model.glb', background: '#0a0e17',
                    camera: {position: [4, 3, 6], target: [0, 1.5, 0],
                             min_distance: 0.1, max_distance: 100},
                    nodes: [{id: 'base', path: 'Arm/Base',
                             position: [0, 0.25, 0], rotation: [0, 0, 0, 1],
                             scale: [1, 1, 1], status: 'success', visible: true}],
                }};
                await runtime.reconcileScene3d(component, document.querySelector('#original'),
                    {materialMode: 'original', reducedMotion: true});
            }"""
        )
        canvas = page.locator("#original canvas")
        original = canvas.screenshot()
        page.evaluate(
            """async () => {
                component.data.nodes[0].status = 'danger';
                component.revision++;
                await runtime.reconcileScene3d(component, document.querySelector('#original'),
                    {reducedMotion: true});
            }"""
        )
        assert canvas.screenshot() == original
        page.evaluate(
            """() => runtime.setScene3dCamera('original', {
                position: [6, 0, 3], target: [0, 0, 0], up: [0, 0, 1],
            })"""
        )
        preset = canvas.screenshot()
        assert preset != original
        page.evaluate(
            """async () => {
                component.data.nodes[0].status = 'warning';
                component.revision++;
                await runtime.reconcileScene3d(component, document.querySelector('#original'),
                    {reducedMotion: true});
            }"""
        )
        assert canvas.screenshot() == preset
        page.evaluate("runtime.disposeScene3d('original')")
        browser.close()
