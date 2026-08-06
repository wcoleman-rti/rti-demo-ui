# Scene3D Web Visualization

## Status

Proposed implementation plan for `feature/scene3d-web-visualization`.

## Objective

Add a web-native 3D visualization path for applications such as the MedTech
surgical arm demo, using Three.js and application-owned GLB assets, while
keeping DDS, business logic, and domain-specific rendering decisions outside
the SDK core.

The first target is not a 1:1 port of the PySide6 arm widget. It is a better
browser experience: an interactive 3D arm with application-owned joint state,
status highlighting, camera controls, and ordinary HTML controls/readouts
around the canvas.

## Product Boundary

The SDK provides:

- A JSON-compatible, language-neutral scene state contract.
- Python and C++ component APIs with matching validation and serialization.
- Optional browser rendering for the generic scene contract.
- Static asset serving for application-owned JavaScript, Three.js bundles, and
  GLB files.
- Existing command and snapshot transport integration.

The application provides:

- DDS entities, QoS, subscriptions, commands, and business logic.
- The model asset and its stable node names or paths.
- Conversion from domain values such as motor angles to node transforms.
- The semantic meaning of each joint, status, alarm, and interaction.
- The surrounding application layout, labels, metrics, logs, and fallback UI.

The SDK must not add Connext, WIS, DDS types, arm-specific semantics, model
loading from remote services, or safety-critical control behavior.

## Current Foundation

The existing implementation already supports the pilot:

- `DemoUiApp` can serve an application-owned `static_root`.
- `/sdk/client.js` can consume the existing v2 snapshot API without using the
  built-in renderer.
- Custom components can carry arbitrary JSON data.
- GLB files are already served by the static-root path.
- The browser runtime already interpolates moving 2D poses between snapshots.
- A 200 ms snapshot cadence is sufficient for the arm's small set of joint
  targets when the browser interpolates locally.

The current built-in `runtime.js` intentionally renders unknown custom types as
unsupported components. The pilot should therefore use an application-owned
frontend before extending the shared renderer.

## Existing SDK Prerequisites

This plan consumes the following SDK capabilities that are already implemented;
they are prerequisites, not additional scene3d work:

- Application-owned static roots with traversal-safe asset serving and
  namespaced `/sdk/...` assets.
- Python's native asyncio/aiohttp lifecycle, owner-loop mutation rules, and
  port-zero readiness APIs. C++ retains its blocking, thread-safe lifecycle.
- The v2 snapshot envelope, application and component revisions, generic
  application state, typed components, opaque custom components, and matching
  command APIs.
- The framework-independent `/sdk/client.js` polling client with revision
  short-circuiting, retry handling, and command invocation.

Scene3D implementation should extend these contracts rather than duplicate
transport, readiness, command, or generic state infrastructure. WebSocket and
SSE transports remain deferred; the initial scene3d path uses the existing
snapshot polling contract.

## Proposed Scene Contract

The eventual generic component should be named `scene3d`, not `arm3d`.
Static scene configuration and dynamic pose state should remain JSON data so
both language backends can produce identical snapshots.

Canonical shape:

```json
{
  "id": "scene-3d-1",
  "type": "scene3d",
  "revision": 12,
  "data": {
    "asset": "/models/surgical-arm.glb",
    "nodes": [
      {
        "id": "shoulder",
        "path": "Arm/Shoulder",
        "position": [0, 0, 0],
        "rotation": [0, 0, 0.564642, 0.825336],
        "scale": [1, 1, 1],
        "visible": true,
        "status": "success"
      }
    ],
    "camera": {
      "mode": "orbit",
      "position": [4, 3, 5],
      "target": [0, 0, 0],
      "min_distance": 0.1,
      "max_distance": 1000.0
    },
    "background": "#0a0e17",
    "grid": false
  }
}
```

Every field shown in this canonical shape is serialized; defaults are applied
by construction and are never omitted from snapshots. `asset`, `nodes`,
`camera`, `background`, and `grid` are required scene data fields. Each node
always contains `id`, `path`, `position`, `rotation`, `scale`, `visible`, and
`status`; each camera always contains `mode`, `position`, `target`,
`min_distance`, and `max_distance`. `nodes` may be empty. Partial updates
change only the supplied node fields and serialize the complete resulting node.
An accepted no-op produces byte-identical scene data and does not change either
revision.

The canonical mutation fixture is:

```json
{
  "batch": [
    {
      "op": "add",
      "id": "shoulder",
      "path": "Arm/Shoulder",
      "rotation": [0, 0, 0, 1]
    },
    {
      "op": "update",
      "id": "shoulder",
      "position": [0.1, 0, 0]
    }
  ],
  "expected": {
    "revision_delta": 1,
    "node": {
      "id": "shoulder",
      "path": "Arm/Shoulder",
      "position": [0.1, 0, 0],
      "rotation": [0, 0, 0, 1],
      "scale": [1, 1, 1],
      "visible": true,
      "status": "success"
    }
  },
  "no_op": {
    "operation": {
      "op": "update",
      "id": "shoulder",
      "position": [0.1, 0, 0]
    },
    "revision_delta": 0,
    "serialized_data_unchanged": true
  }
}
```

The renderer should support a bounded first version of:

- One GLB asset per scene.
- Unique slash-delimited model node paths.
- Position, quaternion rotation, scale, visibility, and status.
- The model's existing parent-child hierarchy for hierarchical movement.
- Orbit camera configuration.
- Browser-local selection/highlight state.
- Client-side interpolation between target transforms.
- Reduced-motion behavior that applies target transforms immediately.

## Contract Lock Before Implementation

The following rules are normative for the first `scene3d` contract. They must
be captured in shared valid and invalid JSON fixtures before the Python or C++
API is implemented. Python and C++ must raise their language-native validation
exceptions with the same stable message text; browser diagnostics use the
same error codes in the fixture vectors.

- Coordinates use the glTF convention: right-handed, Y-up, with translations
  measured in meters. Node transforms are local transforms relative to the
  addressed node's imported parent. World transforms and SDK-created
  reparenting are out of scope.
- `position` is exactly `[x, y, z]`, with finite numbers and a default of
  `[0, 0, 0]`.
- `rotation` is exactly a finite unit quaternion in `[x, y, z, w]` order. The
  norm must be within `1e-6` of `1.0`; values are rejected rather than silently
  normalized. The default is the identity `[0, 0, 0, 1]`.
- `scale` is exactly `[x, y, z]`, with finite values strictly greater than
  zero. The default is `[1, 1, 1]`.
- `visible` is a boolean defaulting to `true`. `status` uses the existing
  `success`, `warning`, and `danger` values and defaults to `success`.
- Node paths are slash-delimited paths from the GLB scene root. Each segment
  uses JSON Pointer escaping (`~1` for `/` and `~0` for `~`), so duplicate glTF
  node names are allowed when their full paths differ. Empty segments and
  paths that do not resolve to exactly one node are rejected by the renderer
  with `invalid_node_path` or `unresolved_node_path` diagnostics.
- The initial contract addresses imported glTF nodes only. It does not create
  synthetic groups, infer joints, or support reparenting. Parent transforms
  are applied by the model hierarchy before child local transforms.
- The optional orbit camera uses finite meter coordinates. Its defaults are
  `position: [4, 3, 5]`, `target: [0, 0, 0]`, `min_distance: 0.1`, and
  `max_distance: 1000.0`. Position and target must differ, and distance
  bounds must be positive with `min_distance < max_distance`.
- `background` is a six-digit hexadecimal color and `grid` is boolean. The
  browser owns transient camera position after initialization; camera state in
  snapshots is configuration, not a continuously reported interaction state.

The backend fixture error codes are `invalid_asset`, `invalid_transform`,
`invalid_rotation`, `invalid_scale`, `invalid_node_id`, `duplicate_node_id`,
`invalid_node_path`, `invalid_camera`,
`duplicate_operation`, and `stale_node_id`. Each vector includes the exact
  expected message and whether the global/component revision is unchanged.
The canonical server-side messages are `Scene3DViewport: asset must be an
absolute same-origin .glb path under static_root`, `Scene3DViewport: transform
arrays must have exactly 3, 4, and 3 finite values`, `Scene3DViewport: rotation
must be a unit quaternion in [x, y, z, w] order`, `Scene3DViewport: scale
values must be finite and greater than zero`, `Scene3DViewport: node ID must
be non-empty`, `Scene3DViewport: node ID is already in use`,
`Scene3DViewport: node path is invalid`, `Scene3DViewport: camera
configuration is invalid`, `Scene3DViewport: batch contains a duplicate
operation`, and `Scene3DViewport: node ID is stale`. The backend accepts a
lexically valid path without resolving it against the GLB; browser-only node
resolution uses the separate `unresolved_node_path` diagnostic fixture.

## Implementation Phases

### Phase 0: Contract fixtures and pilot frontend

- Add the shared scene contract fixtures before adding the public component
  APIs. Backend vectors include identity/default transforms, quaternion
  ordering, non-unit and non-finite rotations, wrong array cardinality,
  zero/negative scale, camera bounds, local-transform examples, escaped
  node-path segments, duplicate names with distinct paths, and invalid asset
  URLs. Add separate browser GLB-resolution vectors for valid and unresolved
  paths; unresolved paths are not Python/C++ schema-validation cases.
- Declare the pilot payload private and versioned as
  `scene3d-pilot-v1`; it must not register the public `scene3d` type or become
  an undocumented compatibility contract. Add a fixture that maps the pilot
  payload to the locked `scene3d` shape before the generic API is introduced.
- Add an application-owned arm web example under `examples/web`.
- Make the example layout concrete and runnable:
  `examples/web/arm3d/index.html`, application JavaScript and CSS, a local
  pinned Three.js bundle, and a model asset under the same static root.
- Add `examples/py/arm3d.py` and `examples/cpp/arm3d.cpp` launchers following
  the existing gallery examples. Both use deterministic mock joint updates so
  the visualization can be demonstrated without Connext, DDS, or a Node.js
  development server.
- Bundle or vendor a pinned Three.js build locally; do not require a CDN.
- Add a small GLB fixture or documented model placeholder with stable node
  paths. The fixture must contain a visible, deterministic colored mesh and
  the five paths used by the mock joint updates.
- Load the model with `GLTFLoader` and add `OrbitControls`.
- Consume `/sdk/client.js` and render an application-owned custom component or
  application data object.
- Interpolate joint/node rotations in `requestAnimationFrame`.
- Keep metrics, state badges, logs, and command controls as HTML outside the
  canvas.
- Add a graceful fallback when WebGL or the model cannot be loaded.
- Add `examples/web/arm3d/README.md` with run commands, static-root deployment,
  model preparation, stable node naming, coordinate and unit conventions,
  mock-versus-DDS ownership, and fallback behavior.

Success criterion: the arm moves from application state in a browser at the
existing snapshot cadence, with no DDS dependency in the SDK or frontend
transport.

### Phase 1: Scene3D state contract and API

- Add matching Python and C++ `Scene3DViewport` or equivalent generic
  component APIs on top of the existing component and revision model.
- Add `add_node`, partial `update_node`, `remove_node`, and atomic
  `apply_node_batch` methods. Batch operations are `add`, `update`, or
  `remove`; the complete batch is validated against a copy before commit.
- Use `path` consistently in both APIs and JSON. The Python shape is
  `add_node(id, path, position=(0, 0, 0), rotation=(0, 0, 0, 1),
  scale=(1, 1, 1), visible=True, status=Severity.success)`, with equivalent
  C++ defaults. `update_node(id, position=None, rotation=None, scale=None,
  visible=None, status=None)` is partial; `remove_node(id)` removes one node.
- Encode batch operations as
  `{"op":"add","id":"shoulder","path":"Arm/Shoulder",...}`,
  `{"op":"update","id":"shoulder","rotation":[0,0,0,1]}`, and
  `{"op":"remove","id":"shoulder"}`. Add an explicit fixture for the
  complete scene snapshot, a batch, and a valid no-op.
- Node paths are immutable after `add_node`; changing one requires removal and
  a new node ID. Node IDs are unique for the lifetime of a scene, including
  removed IDs, so stale references cannot silently target a different node.
- A successful operation that changes serialized state increments the global
  and component revision exactly once. A valid no-op does not increment a
  revision. Failed single operations and failed batches leave state and
  revisions unchanged. The API exposes IDs rather than mutable node handles.
- Reuse existing component IDs, component revisions, snapshot envelopes, and
  JSON validation conventions.
- Validate the locked transform, node-path, camera, and asset rules, including
  finite numbers, exact array lengths, stable IDs, and bounded batch sizes.
- Keep asset, camera, background, and grid configuration immutable through
  node updates. Add one atomic `set_config` operation that replaces the full
  configuration and increments the revision once. Asset replacement advances
  the browser asset generation; existing node paths remain logical paths and
  report `unresolved_node_path` if the replacement model does not contain them.
- Add deterministic Python/C++ fixtures proving snapshot parity.

The API should expose generic transforms rather than arm angles. An
application may calculate a transform from five motor angles and submit it to
the scene.

### Asset and URL policy

- The initial contract is GLB-only. GLTF JSON, external buffers, external
  textures, data URLs, remote URLs, protocol-relative URLs, query strings, and
  fragments are out of scope and rejected.
- `asset` is an absolute same-origin application-static path such as
  `/models/surgical-arm.glb`. It must not contain `..`, NUL bytes, a URL scheme,
  or the reserved `/sdk/` prefix. When a `static_root` is configured, the
  backend validates that the path resolves to a regular file below that root;
  otherwise scene3d construction fails with `invalid_asset`.
- The example and shared renderer require `static_root`; SDK assets and model
  assets are never mixed. Static-root traversal and MIME checks remain owned by
  the existing server resolver.

### Phase 2: Shared browser renderer

- Add an optional SDK-owned `/sdk/runtime3d.js` module rather than making the
  existing built-in dashboard load a large 3D dependency for every
  application. `runtime.js` dynamically imports it only after receiving a
  `scene3d` component; non-3D pages never request the module. A failed import
  produces the same textual unsupported/fallback diagnostic as a failed model
  load.
- Define the renderer module interface before implementing the dynamic import:
  `reconcileScene3d(component, host, context)` consumes one complete v2
  component plus the stable DOM host and returns a promise that resolves after
  the current asset/configuration has been applied; `disposeScene3d(componentId)`
  releases the scene, listeners, animation state, and asset reference. The
  context contains `reducedMotion`, `onSelection`, and `onLoadState` callbacks;
  it does not expose SDK internals or browser client state.
- `runtime.js` owns the stable host by component ID. When a `scene3d` component
  is encountered, the existing `renderUnsupported` branch is bypassed; the
  stable host is handed to this lifecycle instead of showing an
  unsupported-component message. On the first `scene3d` component it creates a
  loading host, starts one cached dynamic-import promise, and calls
  `reconcileScene3d` when the module resolves. On later snapshots it calls the
  same method with the new complete component. When a
  component disappears, `runtime.js` calls `disposeScene3d` before removing its
  host. If import or model loading fails, the host switches to the textual
  fallback and `onLoadState` records the failure; a visible Retry control clears
  only the failed import/load generation and retries once on user action.
  Stale promise completions are ignored by component ID and generation.
- Build `runtime3d.js` as one self-contained browser ES module with no bare
  `three` imports, import maps, CDN URLs, or Node.js runtime requirement.
  Use the pinned npm toolchain under `tools/scene3d/`: exact `esbuild` and
  `three` versions in `package.json` and a committed `package-lock.json`.
  `npm ci --ignore-scripts && npm run build:runtime3d` must produce
  `assets/runtime3d.js` from `tools/scene3d/src/runtime3d.js` through
  `tools/scene3d/scripts/build-runtime3d.mjs`. The script must invoke esbuild
  with `bundle: true`, `format: "esm"`, `platform: "browser"`, and a fixed
  ECMAScript target, and `tools/scene3d/package.json` must expose exactly
  `"build:runtime3d": "node scripts/build-runtime3d.mjs"`. Commit the source,
  lockfile, generated artifact, and
  `assets/runtime3d.sha256`; CI reruns the
  build in a clean temporary output and fails if the artifact or checksum
  differs. The update procedure is: change pinned versions, run `npm ci`, run
  the build, update the checksum and `docs/third-party.md`, then review the
  generated diff and license changes. Vendor pinned Three.js,
  `GLTFLoader`, `OrbitControls`, and any required `SkeletonUtils` source under
  the repository's third-party policy, recording exact source revisions and
  license notices.
- Add `runtime3d.js` to Python wheel package data and the build backend staging
  list and `_ASSET_ROUTES`, add it to the CMake asset input list and generated
  `embedded_runtime3d_js()` function, and serve it at `/sdk/runtime3d.js` in
  both backends. Add canonical-byte and route tests before enabling the
  built-in dynamic import. The Phase 0 arm pilot may use an application-owned
  prebundled `arm3d.js`, but it must use the same locked scene contract.
- Render `scene3d` components by stable component and node IDs.
- Cache parsed GLB resources by URL, create an independent object hierarchy per
  scene instance, and reference-count GPU resources. Do not mutate shared
  materials for status highlighting; clone per-instance materials or use
  overlays. Dispose geometries, materials, textures, and the parser resource
  only when the final scene reference is gone. Guard every load completion with
  a component ID and asset generation so removed or replaced scenes cannot
  attach late loader results.
- Interpolate transforms using timestamps or the snapshot cadence, with a
  fallback for irregular updates.
- Implement camera controls, resize handling, reduced motion, load errors,
  and a visible unsupported-feature diagnostic.
- Ensure the canvas is not the only representation of important state. When
  WebGL is unavailable or the model fails to load, render a usable textual
  fallback containing node names, transform/status values, and the failure
  state.
- Make camera reset and zoom controls real focusable buttons with accessible
  names. Render a synchronized semantic node list as a `role="listbox"` with
  one `role="option"` per node, stable `aria-label` text, `aria-selected`, and
  a visible focus ring. Arrow keys/Home/End move focus, Enter/Space selects or
  deselects the focused node, and pointer selection in the canvas updates the
  same list. The list remains present and synchronized in the WebGL and
  textual-fallback states. Provide a polite live region for selection,
  deselection, model-load, and failure changes.
- Keep the ordinary `runtime.js` dependency-free for applications that do not
  use 3D. Built-in scene3d rendering is opted into only by the documented
  dynamic import of `/sdk/runtime3d.js`.

### Phase 3: Interaction and command integration

- Define a browser-only `scene3dselect` `CustomEvent` on the scene host with
  detail `{componentId, nodeId, selected}`. Selection is local to one scene,
  has at most one selected node, and pointer or semantic-list selection emits
  the same event. Selecting the focused selected option with Enter/Space
  deselects it. No selection state is sent in snapshots.
- Applications listen for the event and decide whether to call
  `client.invokeCommand`; the SDK does not infer command names or bind node
  selection to safety actions. Existing command schemas and confirmation
  metadata remain the application boundary.
- Add optional command metadata for confirmation, disabled state, and status
  reporting if the arm pilot demonstrates a need.
- Do not send continuous drag or animation frames to the server by default.
  Use throttled, explicit commands for user actions that need application
  validation.

### Phase 4: Performance path

- Measure the arm with polling before adding a new transport.
- Keep snapshot polling for topology, status, metrics, logs, and low-rate pose
  targets.
- Add a separate streaming transport only for use cases that need it, such as
  patient waveforms or dense telemetry. Do not make 3D scenes depend on a
  WebSocket or SSE implementation unless measurements justify it.
- Define bounded browser buffers, dropped-sample behavior, and reconnect
  semantics before adding streaming.

### Phase 5: CI and developer workflow

- Update `.github/workflows/ci.yml` so the existing `browser` job owns the
  complete scene3d browser prerequisite chain. Keep `needs: python`, then add
  `actions/setup-node@v4` with the exact Node version used by the bundle
  toolchain (initially `22.14.0`). In a clean checkout, run exactly:
  `npm ci --ignore-scripts` from `tools/scene3d`,
  `npm run build:runtime3d`,
  `sha256sum --check assets/runtime3d.sha256`, and
  `git diff --exit-code -- assets/runtime3d.js assets/runtime3d.sha256`.
  The final diff check must fail when the committed artifact or checksum does
  not match a reproducible build; CI must not use `npm install` or a CDN.
- Before `pytest tests/browser`, configure and build the C++ arm example in
  that same browser job:
  `cmake -S . -B build-browser -DBUILD_TESTING=OFF
  -DRTI_DEMO_BUILD_EXAMPLES=ON`, followed by
  `cmake --build build-browser --target rti_demo_ui_arm3d --parallel`.
  Resolve the resulting target file, require that it is executable, and export
  its absolute path as `RTI_DEMO_CPP_ARM3D` through `GITHUB_ENV`. Update
  `tests/browser/test_browser.py` to require this variable for the arm3d
  backend fixture and launch that exact executable using the readiness and
  process-group protocol above. The browser job then runs the same Python and
  C++ assertions; it must not silently skip the C++ backend when the variable
  is absent.
- Keep the ordinary `cpp` job for unit tests, but do not rely on its separate
  runner's build directory or artifacts. The browser job explicitly builds the
  example it launches, making the executable path and toolchain visible in the
  job log.
- Add the equivalent local command sequence to
  `docs/development/contributing.md`, including the Node version check,
  checksum/diff gate, CMake arm3d build, executable-path export, and browser
  test invocation. The local command must use the repository virtualenv and
  must not require a running Node development server.

## API Shape To Evaluate

Python, illustrative only:

```python
scene = card.add_scene_3d(
    asset="/models/surgical-arm.glb",
    camera={"mode": "orbit", "target": [0.0, 1.0, 0.0]},
)
scene.add_node(
  id="shoulder",
    path="Arm/Shoulder",
    rotation=(0.0, 0.0, 0.564642, 0.825336),
    status=Severity.success,
)
scene.update_node("shoulder", position=(0.1, 0.0, 0.0))
```

`add_node` is the creation API; `update_node` is the partial mutation API and
`apply_node_batch` is the atomic multi-operation API. The complete serialized
node always uses `path`, never `node`.

C++ should provide equivalent operations and serialized output. The public
API must not expose Three.js types, browser handles, DOM nodes, or DDS types.
The final names should follow the existing `Card`, component handle, and
Python/C++ parity conventions.

## Testing Plan

- Python unit tests for scene construction, transform validation, mutation,
  revision behavior, and serialization.
- C++ tests for the same contract and exception behavior.
- Shared JSON fixtures for Python/C++ snapshot parity, including exact
  validation messages, failed batches, no-op batches, and stale node IDs.
- Keep backend vectors under `tests/fixtures/scene3d_contract.json` and
  browser model-resolution vectors under
  `tests/fixtures/scene3d_node_resolution.json`. The former tests Python/C++
  lexical/schema behavior; the latter names fixture-GLB paths that the browser
  must resolve or report as `unresolved_node_path`.
- Static-root tests for the GLB model, bundled JavaScript, textures, rejected
  GLTF/remote/data URI references, traversal attempts, and missing assets.
- Browser tests for model loading, nonblank canvas pixels, camera interaction,
  transform updates, interpolation, resize, reduced motion, and load failure.
- Browser tests with WebGL unavailable or model loading blocked must verify the
  textual fallback, keyboard reachability, focus behavior, and announced
  status. Reduced-motion tests must verify target transforms are applied
  immediately.
- Browser accessibility tests must exercise the semantic listbox with WebGL
  enabled and in fallback mode: Tab reaches the listbox and camera controls,
  Arrow/Home/End move focus, Enter/Space selects and deselects, and the live
  region reports the resulting state.
- A narrow mobile viewport test to ensure the canvas and surrounding controls
  do not overlap.
- An application-level pilot test that updates five joint targets without
  importing DDS into the SDK package.
- A runnable Python and C++ example test or smoke check that serves the arm
  static root and exercises the same browser page against each backend.

The browser test environment must distinguish a real rendered canvas from a
blank WebGL surface. The committed fixture GLB, camera, lighting, background,
and canvas region must be deterministic. At least 100 pixels in that region
must differ from the exact background by a channel distance of at least 10; a
nonblank canvas element or clear color alone is insufficient. Console errors
fail the test.

The fallback suite injects WebGL failure by making
`HTMLCanvasElement.getContext("webgl")` and
`getContext("webgl2")` return `null`, independently of host GPU settings. The
browser fixture starts the Python app directly and launches the C++ arm example
as a subprocess, waits for each reported readiness URL, and runs identical
assertions against both backends. The C++ subprocess terminates through the
example's normal stop path.

The C++ subprocess protocol is fixed and must not depend on scraping arbitrary
logs. The launcher writes the readiness line
`RTI Demo UI listening on http://127.0.0.1:<port>/` to stdout using the
existing `ReadyInfo` output. The harness matches the anchored expression
`^RTI Demo UI listening on (http://(?:127\\.0\\.0\\.1|\\[::1\\]):[0-9]+)/$`,
requires the line within 10 seconds, captures stderr for diagnostics, and
fails if the process exits before the match. On POSIX it starts the child in a
new process group and sends SIGINT to that group; on Windows it starts a new
console process group and sends CTRL_BREAK_EVENT. The harness waits up to 5
seconds for a clean exit and reports retained stdout/stderr on timeout; force
termination is cleanup-only and fails the test. The same protocol is used by
the local example smoke command and CI.

## Documentation

Update the following after the contract stabilizes:

- `docs/architecture.md` for the optional 3D component and renderer boundary.
- `docs/custom-frontends.md` for Three.js asset bundling and model deployment.
- `docs/api/python.md` and `docs/api/cpp.md` for matching scene APIs.
- `README.md` with the arm 3D example and local asset guidance.
- A new example README describing model preparation, node naming, coordinate
  conventions, and browser fallback behavior.
- `docs/third-party.md` for pinned Three.js/addon provenance and license
  notices.
- `.github/workflows/ci.yml` for the pinned Node setup, reproducible runtime
  artifact gate, C++ arm3d build, and `RTI_DEMO_CPP_ARM3D` handoff.
- `docs/development/contributing.md` for the matching local verification
  command.

## Non-Goals

- Recreating Qt layouts or widgets in the browser.
- A general-purpose CAD, simulation, physics, or robotics engine.
- Server-side Three.js rendering.
- Automatic inference of joint hierarchies from arbitrary models.
- DDS or WIS integration in the SDK.
- High-rate waveform transport as part of the initial 3D feature.
- Replacing all application-owned frontend code with SDK-owned markup.

## Risks and Decisions

- **Model quality:** the largest practical risk is incorrect GLB pivots,
  hierarchy, or node names. Validate the model before finalizing the API.
- **Dependency size:** Three.js is opt-in through `runtime3d.js` or
  application-bundled in the pilot; the basic SDK frontend remains small.
- **Browser/GPU variance:** provide a 2D or tabular fallback and test in the
  supported browser matrix.
- **Wire compatibility:** the transform, path, asset, camera, and mutation
  conventions are locked before implementation and shared across Python,
  C++, and JavaScript fixtures.
- **State volume:** send target transforms, not per-frame animation data. The
  browser owns interpolation.
- **Interaction safety:** selection may be continuous in the browser, but
  commands must remain explicit, validated, and application-owned.

## Acceptance Criteria

- The arm demo is viewable in a normal browser from the SDK server with no
  separate Node.js process.
- The application supplies the model and owns all DDS/business logic.
- The arm responds smoothly to joint updates at the existing snapshot cadence.
- Python and C++ produce the same generic scene snapshot contract.
- The built-in renderer bypasses its unsupported-component path for `scene3d`,
  calls the named `reconcileScene3d`/`disposeScene3d` interface, and recovers
  from a failed optional-module load through the documented Retry transition.
- The committed Python and C++ launchers serve the same arm3d page and mock
  five joint targets without Connext, DDS, or a Node.js process.
- A broken model or unavailable WebGL produces an understandable fallback.
- Important node state remains available as accessible text without WebGL, and
  enabled scene interactions are usable from the keyboard.
- Ordinary non-3D pages do not request `/sdk/runtime3d.js`.
- `npm ci --ignore-scripts && npm run build:runtime3d` reproduces the committed
  runtime artifact and checksum in CI.
- Asset loads are same-origin GLB loads under the application static root, and
  shared-resource disposal does not break two scenes using one asset.
- The semantic node list remains keyboard reachable and synchronized in both
  WebGL and fallback modes.
- The C++ browser harness uses the fixed readiness marker, timeout, process
  group, and graceful signal protocol.
- Existing non-3D applications and tests do not load or depend on Three.js.
- No core SDK API contains Connext, WIS, or arm-specific types.
