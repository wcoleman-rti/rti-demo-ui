# Opt-In UI Renderer Adapters Plan

## Status

Proposed implementation plan for `feature/ui-renderer-adapter-core`, followed
by one feature branch per library adapter.

This is a portfolio program plan, not one agent-session implementation scope.
Hand off exactly one execution unit at a time: Phase 1 adapter core, Phase 2
uPlot, the icon module, one named renderer adapter, raster frames, or Scene3D
migration. ECharts, MapLibre, PixiJS, Tabulator, raster frames, and Scene3D each
require a concise child plan that references this document for shared contracts
and contains only that unit's owning files, dependency pin, generated assets,
tests, and branch exit gate. Do not ask an implementation agent to execute this
entire document in one session.

## Objective

Decouple optional dynamic visualizers and their browser libraries from the SDK
core. Python applications opt in by importing and enabling an adapter package;
C++ applications opt in by including its API and linking its CMake target.
Only enabled adapters expose their component model and browser assets.

The initial portfolio targets industry-facing demo applications: live medical
waveforms, gauges and status indicators, moving assets on geographic or site
maps, interactive 3D equipment views, raster sensor and medical imagery, and
bounded operational task/event grids. The first delivery establishes the
adapter contract and proves it with a small live-data adapter before adding each
independently justified capability.

## Dependencies

This plan begins after the SSE browser-client contract and the theming/layout
snapshot contract are stable. Adapters consume `/sdk/client.js`, theme tokens,
and card layout; they do not implement separate transport or layout systems.

The existing Scene3D implementation is the migration reference. Its current
`scene3d` model and `/sdk/runtime3d.js` asset remain supported until a dedicated
migration phase proves parity.

## Application Use Cases

SDK-owned adapters exist to give RTI Connext DDS demos a consistent API,
interaction model, and visual language across industries. Representative uses
include:

- Patient-monitor waveforms and live physiological indicators.
- Gauges and status panels for vehicle, energy, and industrial telemetry.
- Autonomous taxi fleets, drone swarms, and mine-site assets moving over
  geographic maps.
- Warehouse pickers, vehicle zones, and mine equipment moving through
  schematic 2D scenes or site plans.
- Interactive equipment or vehicle views with selectable zones and subsystem
  health.
- Drill-down operational dashboards such as hospital units, patients, alerts,
  and current vitals.
- Surgical robot and other machine digital twins with selectable subsystems.
- Processed camera, thermal, medical, and other raster sensor frames for
  perception, operative guidance, inspection, and remote operation demos.
- Bounded live task/event grids with selection and SDK command actions.

Middleware topology, relationship graphs, general business analytics, and
unbounded dataset exploration are not initial adapter goals. A library's
popularity alone is insufficient: each adapter needs a recurring demo use
case, a stable language-neutral schema, and behavior that the SDK can make
consistent across Python and C++.

## Product Boundary

The adapter framework provides:

- A closed server-side registration contract for component type, browser
  module asset, version, and optional CSS assets.
- Typed Python and C++ adapter APIs for creating and mutating component state.
- Lazy browser module loading when an enabled component type first appears.
- Renderer `mount`, `update`, and `dispose` lifecycle hooks.
- Separate package/build targets so core consumers do not carry optional
  generated library bundles.
- Pinned, reproducible, locally served browser dependencies and license
  records.

It does not provide runtime installation from npm/CDNs, arbitrary module URLs
from snapshots, untrusted third-party code sandboxing, server-side DOM/widget
handles, framework-specific React/Vue APIs, or automatic conversion between
unrelated chart/map/scene schemas.

## Adapter Categories

Renderer adapters own one or more component types:

- Three.js: interactive `scene3d` equipment, environment, and vehicle views.
- uPlot: compact, high-rate waveforms and bounded time-series telemetry.
- Apache ECharts: gauges, status dials, and broader live charts where uPlot's
  intentionally narrow time-series model is insufficient.
- MapLibre GL JS: GPU-accelerated geographic and site maps with moving assets,
  vector layers, rotation, and pitch.
- PixiJS: high-update `scene2d` schematics with positioned entities, zones,
  paths, labels, selection, and command interaction.
- Tabulator: bounded operational task/event grids with selection, filtering,
  and SDK command actions.
- Browser-native raster frame renderer: bounded JPEG, PNG, or WebP sensor
  frames with timestamps, dimensions, fit mode, stale state, and textual
  fallback. This capability does not initially require a third-party library.

PixiJS is justified by recurring automotive-zone, mine-site, and warehouse
scenarios, but the SDK contract is `scene2d`, not a pass-through PixiJS API.
The adapter must remain useful if its rendering library changes. Prefer normal
SDK layout and controls for hospital/unit/patient drill-down; use `scene2d`
only where spatial position or animated movement conveys domain meaning.

Lucide is a build-time icon source, not an app-enabled adapter or data
component. Generate a versioned SDK-owned icon module or SVG sprite containing
only reviewed icons. SDK controls use stable semantic SDK names rather than
Lucide export names; the generation map records the upstream icon behind each
name. The first release contains exactly 32 reviewed semantic icons in core and
no expanded pack. Names are additive and may not be removed or repurposed
within a major SDK version. Do not accept arbitrary SVG markup in snapshots.

Each adapter gets a separate implementation plan or adapter section after the
core contract lands. Do not place all candidate libraries in one generated
bundle.

### Selection Rationale

- Keep Apache ECharts rather than replacing it with Chart.js or Vega-Lite.
  ECharts' gauges and rich live indicators directly serve operational demos;
  uPlot remains the lighter path for sustained waveform updates.
- Keep MapLibre rather than Leaflet for the primary map adapter. Rotation,
  pitch, GPU vector rendering, and custom layers better fit moving drone,
  vehicle, and mine-site displays. Leaflet remains a possible lightweight
  raster-map adapter only if a later measured use case cannot justify
  MapLibre's bundle and offline-resource complexity.
- Keep PixiJS for schematic spatial scenes that are not latitude/longitude
  maps and do not require a 3D camera. Its retained scene graph, batching, and
  pointer interaction fit many independently updated warehouse, mine, and
  vehicle entities better than repeatedly rebuilding SVG DOM. Three.js remains
  the path for surgical robots, detailed equipment, and other 3D digital
  twins.
- Prefer Tabulator for the operational-grid spike because it is framework
  independent and includes virtualization, selection, sorting, and editing.
  The adapter exposes a constrained SDK schema, not arbitrary Tabulator
  callbacks, HTML formatters, Ajax URLs, or its entire upstream API.
- Omit topology-focused graph libraries unless middleware or relationship
  visualization becomes an explicit product requirement.

### Capability Mapping

| Demo capability | Primary SDK surface | Optional renderer |
| --- | --- | --- |
| Live waveforms | Bounded time-series component | uPlot |
| Gauges, dials, and rich status charts | Indicator/chart component | ECharts |
| Fleet, swarm, and geographic site movement | Map component | MapLibre |
| Warehouse, vehicle-zone, and schematic site movement | `scene2d` component | PixiJS |
| Robot, vehicle, or equipment digital twin | `scene3d` component | Three.js |
| Camera, thermal, and processed medical imagery | Raster-frame component | Browser-native image decoding |
| Unit/patient/status drill-down | Core layout, navigation, and controls | None |
| Current tasks, events, alerts, and row actions | Operational grid | Tabulator |

Avoid substituting a more complex renderer where core HTML controls and layout
communicate the state clearly. Conversely, do not force latitude/longitude
semantics onto floor plans or local machine coordinates merely to reuse the
map adapter.

## Adapter Registration Contract

### Descriptor

An enabled adapter has immutable metadata registered before `run()` begins:

```json
{
  "name": "uplot",
  "version": "1",
  "components": ["timeseries"],
  "module": "/sdk/adapters/uplot/runtime.js",
  "styles": ["/sdk/adapters/uplot/theme.css"]
}
```

Names and component types follow the existing lowercase component-name
restrictions. Routes are generated by the SDK/adapter package, must begin with
`/sdk/adapters/<name>/`, and cannot be supplied by application snapshot data.
Adapter name, component type, and route collisions fail before socket binding.
Registration after `run()` begins fails.

Expose enabled descriptors through `GET /sdk/adapters/manifest.json`. The
manifest is SDK-generated JSON with `no-cache`, `nosniff`, and no application
paths or remote URLs. Unknown and disabled adapter asset routes return the
existing plain SDK 404.

The built-in runtime reads the manifest only after encountering a non-core
component. Custom frontends may read it or import known enabled routes
directly.

### Browser Renderer Lifecycle

Each adapter ES module exports a registration function rather than executing an
unscoped global script:

```javascript
export function registerAdapter(registry) {
    registry.registerComponentRenderer('timeseries', {
        mount(host, component, context) {},
        update(host, previous, component, context) {},
        dispose(host, context) {}
    });
}
```

The runtime owns the host element and one lifecycle context per component ID.
The adapter owns descendants, canvas/WebGL resources, observers, timers, and
library objects inside that host. `dispose` must release all of them and be
safe after a partial `mount` failure. `update` receives complete component
envelopes and must not mutate snapshots.

The registry permits one renderer per component type. Loading failure renders
an isolated diagnostic with retry, while other cards/components continue to
update. Concurrent encounters share one dynamic-import promise. Removing the
last component does not unload the module, but it must dispose every instance.

The context exposes only bounded SDK services: semantic theme tokens,
reduced-motion state, resize observation, command invocation, and diagnostic
reporting. It does not expose mutable runtime internals.

## Python API and Packaging

### Package Shape

```text
rti_demo_ui                 core distribution
rti_demo_ui_adapter_uplot    optional adapter distribution
rti_demo_ui_adapter_scene3d  optional adapter distribution after migration
```

Keep adapter sources in this repository and build one Python distribution per
adapter. A Python extra alone does not remove package data from the base wheel;
convenience extras may depend on the separate adapter distributions. Each
adapter distribution has its own versioned generated assets, dependency pins,
license material, and wheel-isolation test.

Usage should be explicit and occur before app startup:

```python
from rti_demo_ui import DemoUiApp
from rti_demo_ui.adapters import uplot

app = DemoUiApp("Robot Telemetry", adapters=[uplot.adapter])
card = app.add_card("History")
chart = uplot.add_timeseries(card, series=[...])
```

Import makes a descriptor available; passing it to `DemoUiApp` enables it for
that application. This avoids process-global import side effects leaking into
other app instances or tests. As syntactic sugar, an adapter may expose a typed
Card extension only if static typing and multi-app isolation remain intact.
Do not monkey-patch `Card` merely to make `card.add_scene_3d()` appear.

Adapter component classes reuse the core component envelope, JSON validation,
stable ID, owner-loop, and revision machinery through a supported internal
adapter SPI. Adapters must not access private model fields directly.

## C++ API and Packaging

Provide one target per adapter:

```cmake
target_link_libraries(my_demo PRIVATE
    rti_demo_ui::rti_demo_ui
    rti_demo_ui::adapter_uplot)
```

Usage includes the adapter API and explicitly enables its descriptor:

```cpp
#include <rti_demo_ui/demo_ui_app.hpp>
#include <rti_demo_ui/adapters/uplot.hpp>

rti::demo::ui::DemoUiApp app("Robot Telemetry");
rti::demo::ui::adapters::uplot::enable(app);
auto* card = app.add_card("History");
auto* chart = rti::demo::ui::adapters::uplot::add_timeseries(*card, series);
```

Do not rely on namespace-scope static registration. Static-library dead
stripping, initialization order, and duplicate registration make include/link
side effects unreliable. Include and link time provide the adapter API/assets;
the explicit `enable(app)` call establishes per-application registration.

Adapter targets embed only their own generated module/CSS assets and link the
core target publicly or privately as appropriate. Core C++ builds must not
compile or embed optional bundles.

## Internal Renderer Adapter SPI

Add a small internal API shared by SDK-owned adapters:

- Register an immutable adapter descriptor and asset byte views on an app.
- Reserve component type names before startup.
- Create an adapter component with validated JSON data and a stable ID.
- Replace or path-update adapter data through normal revision semantics.
- Obtain no direct mutable model, server, route table, or renderer access.

The initial SPI may wrap the existing custom component model. Typed adapter
classes add domain validation before committing complete JSON data. Failed
validation leaves revision and published adapter events unchanged.

Third-party adapter authoring is not supported in the first release. The
adapter SPI carries no external compatibility promise and is not exported in
public Python modules or installed C++ headers. Supporting external adapters
requires a later versioned authoring contract and security review.

## Browser Asset Loading

When `runtime.js` encounters an unknown non-core type:

1. Look up the type in the cached SDK manifest.
2. If absent, render the existing unsupported-component diagnostic.
3. Load declared styles once with SDK-owned `<link>` elements.
4. Dynamically import the fixed same-origin module route.
5. Call `registerAdapter()` against the constrained registry.
6. Verify that the expected type was registered, then mount or update it.

Use dynamic `import()`, not a classic `<script>` tag. Apply `nosniff` and exact
JavaScript/CSS content types. Module and style routes are immutable for the app
lifetime, locally served, and never derived from component `data`.

## Adapter Contracts

Each adapter plan must define:

- A language-neutral component data schema and bounded data limits.
- Matching Python/C++ creation and mutation APIs.
- Update strategy: in-place library update versus instance replacement.
- Resize, reduced-motion, theme-change, and disposal behavior.
- Semantic HTML or textual fallback where canvas/WebGL is primary.
- Browser feature requirements and isolated failure diagnostics.
- Exact upstream pin, license, build inputs, generated outputs, checksum, and
  update procedure.

The first reference adapter is uPlot because its schema and lifecycle exercise
high-rate live updates without the complexity of maps or a scene graph. Its
initial component supports complete-series replacement and bounded append for
at most 8 series of 10,000 samples each. Timestamps are finite and strictly
increasing within a series; values are finite numbers or `null`. Append uses
ring retention and rejects samples older than the retained tail. ECharts,
MapLibre, PixiJS, and Tabulator follow independently. The curated icon module
lands with core controls because it is generated static UI material, not a
renderer registration proof.

### Third-Party Dependency Governance

Candidate libraries named only in this plan are not dependencies yet. The same
change that first pins, vendors, builds, links, or ships a direct runtime or
build dependency must update `docs/third-party.md` with its exact version or
commit, purpose, license, and source. This includes adapter libraries, icon
sources, bundlers, native helper libraries, and other direct build-only tools.

Generated packages must preserve required license/notice material. Review the
resolved dependency tree and release SBOM for transitive obligations; do not
manually present transitive packages as direct dependencies unless the
repository directly pins or distributes them independently. Dependency
removal and pin changes update the register in the same change as well.

## Scene3D Migration

After the adapter core and reference adapter pass, migrate current Scene3D
packaging without changing its `scene3d` JSON contract or rendering behavior.
Move the Three.js source/build target and asset to the scene3d adapter
distribution/target. Remove `Card::add_scene_3d`, Python `Card.add_scene_3d`,
and `/sdk/runtime3d.js` in the same major-version change; applications must use
the namespaced adapter factories and `/sdk/adapters/scene3d/runtime.js`.

The migration must preserve model validation, browser selection events,
fallback UI, generated-asset reproducibility, and Python/C++ parity. Publish a
mechanical migration guide, but do not ship compatibility shims or retain the
old route.

## Security and Trust Boundary

Adapters execute trusted code with the page's privileges. The system is an
opt-in packaging and registration boundary, not a sandbox. Only SDK-owned,
locally installed adapter packages may register modules. Reject remote,
protocol-relative, data, blob, application-static, and path-traversing routes.

Adapter component schemas must bound arrays, strings, and retained history so a
snapshot cannot trigger uncontrolled browser allocations. The first MapLibre
adapter accepts only same-origin packaged styles, sprites, glyphs, workers, and
tiles registered before startup. Remote sources and application-supplied URLs
are rejected. Every source carries required attribution metadata rendered by
the adapter; packaged resource ownership and license notices are part of its
distribution.

The Tabulator adapter must cap retained rows and cell sizes, use stable row
IDs, and distinguish current state from intentionally retained event history.
It is read-only in the first release: selection, sorting, and filtering are
browser-local, while every mutation or removal is an explicit registered SDK
command. Snapshots cannot provide code, HTML, remote data URLs, executable
formatter definitions, or editable-column behavior.

The PixiJS adapter uses either Cartesian x/y coordinates in one application-
named unit or normalized x/y coordinates in the closed range 0 through 1;
geographic coordinates remain MapLibre's responsibility and viewport-pixel
coordinates are not accepted. Its schema supports SDK-defined primitive
shapes, paths, zones, labels, approved local raster icons/images, z-order,
transforms, health/status styles, and stable entity IDs. Updates target
entities by ID without replacing the full scene. Selection and activation
invoke normal SDK events/commands. The renderer targets 60 Hz display updates
through coalescing without promising 60 Hz transport delivery. Snapshots
cannot contain JavaScript, shaders, arbitrary SVG/HTML, remote asset URLs,
filters, or renderer-specific PixiJS objects. The adapter provides fit,
pan/zoom, reduced-motion behavior, bounded textures, deterministic asset
lifetime, and Canvas fallback when WebGL/WebGPU is unavailable.

The raster-frame adapter must keep binary payloads out of component snapshots,
polling responses, and SSE events. The application owns each registered media
source and atomically replaces its latest frame; the browser retains no frame
history. Snapshots carry only a stable SDK media source ID, frame revision,
media type, dimensions, timestamp, fit mode, and status metadata. The browser
retrieves at most 3,840 by 2,160 pixels and 16 MiB of JPEG, PNG, or WebP bytes
from a fixed same-origin, no-store SDK route with no application-supplied URL.
New revisions coalesce while a decode is active, and every replaced object URL
is revoked. Stale-frame and decode-failure states retain metadata but do not
present old bytes as current. Continuous video, audio, WebRTC, codec
negotiation, DICOM parsing, and arbitrary overlays require separate transport
and security designs; compose annotations with approved `scene2d` primitives
rather than adding a dedicated overlay schema.

## Implementation Phases

### Phase 1: Core Contract and Test Adapter

- Lock descriptor, manifest, collision, route, and renderer lifecycle fixtures.
- Add per-app adapter registration and asset serving in Python and C++.
- Add the browser registry and an internal dependency-free test adapter.
- Prove disabled assets 404 and core package/build outputs exclude adapter
  bytes.

### Phase 2: uPlot Reference Adapter

- Add separate Python distribution and C++ target with exact npm/esbuild pins.
- Define a bounded time-series schema and matching typed APIs.
- Implement theme, resize, update, disposal, fallback, and browser parity tests.

### Phase 3: Utility and Additional Adapters

- Generate the curated Lucide-derived icon module or sprite used by SDK
  controls, with a stable semantic-name map and license record.
- Plan and implement ECharts, MapLibre, PixiJS, and Tabulator on separate
  branches.
- Use shared semantic status colors, selection behavior, command affordances,
  and icon names across map, 2D scene, 3D scene, chart, and grid adapters.
- Do not merge an adapter without its schema, packaging, license, and failure
  behavior review.

### Phase 3a: Raster Frame Transport and Renderer

- Lock a backend-neutral media source lifecycle and same-origin frame route
  before exposing the raster-frame component API.
- Implement browser-native decoding first; add no media library unless a
  measured format, latency, or annotation requirement justifies it.
- Prove bounded memory, coalescing under faster-than-display updates, stale
  indication, and Python/C++ parity with synthetic camera and medical frames.

### Phase 4: Scene3D Migration

- Move Three.js to the adapter package/target while preserving behavior.
- Execute the chosen public API and route migration policy.
- Verify existing arm examples against both backends.

## Verification

- Core isolation: base Python wheel and core C++ target contain no optional
  adapter bundles; disabled routes return 404.
- Registry tests: duplicate names/types/routes, late registration, malformed
  descriptors, per-app isolation, and missing assets fail deterministically.
- Lifecycle tests: load once, mount/update/dispose ordering, removal, failed
  imports, retry, app shutdown, resize, and live theme changes.
- Backend parity: identical adapter descriptors and component snapshots for
  shared fixtures.
- Browser tests: reference adapter through polling and SSE against both
  backends, desktop/mobile rendering, textual fallback, and no leaked canvas,
  timers, or observers after removal.
- Reproducibility: clean pinned builds regenerate byte-identical assets and
  checksums; `docs/third-party.md`, packaged notices, and release SBOMs agree
  with direct pins and shipped artifacts.
- Adapter scenarios: sustained waveform updates, live gauge updates, moving
  map entities, moving 2D scene entities, raster frame updates, and bounded
  grid row/action updates remain responsive and do not leak retained state
  after component removal.

Run focused and full validation from `docs/development/contributing.md` plus
each adapter's generated-asset check.

## Resolved Decisions

- Adapter sources remain in this repository, with one independently built
  Python distribution and CMake target/package per adapter.
- Only SDK-owned adapters use the private extension API in the first release.
- Scene3D moves immediately to namespaced adapter APIs and routes with no
  compatibility shim.
- Enabled descriptors remain solely on the immutable
  `/sdk/adapters/manifest.json` route and are not duplicated in snapshots.
- uPlot supports bounded replace/append for 8 series by 10,000 samples.
- MapLibre uses packaged same-origin resources only and always renders required
  attribution.
- Tabulator is read-only apart from explicit SDK command actions.
- Scene2D supports application-unit Cartesian and normalized coordinates,
  coalesced toward 60 Hz display updates, with local raster assets only.
- Raster sources expose only their latest JPEG, PNG, or WebP frame, bounded to
  3,840 by 2,160 and 16 MiB; annotations compose with Scene2D.
- Core ships 32 additive, major-version-stable semantic icon names and no
  expanded icon pack.

## Acceptance Criteria

- Enabling one adapter exposes only its declared component types and local
  assets in both backends.
- Core installs/builds have no generated bundle size from disabled adapters.
- Browser modules load lazily once and every mounted instance is disposed.
- No snapshot value can cause an arbitrary script or stylesheet URL to load.
- The uPlot reference adapter renders and updates equivalently through Python
  and C++ state producers before additional adapters begin.
