# Product Use Cases and Visual Capabilities

## Use This Brief

Read this before planning a component, adapter, layout, or transport change.
It explains why capabilities belong; `docs/architecture.md` defines shipped
contracts, and `docs/development/implementation-plans/` defines unshipped ones.

- **Available:** shipped in Python and C++ unless stated otherwise.
- **Planned:** designed but not yet a usable API.
- **Candidate:** known need requiring a focused plan and approval.

RTI Demo UI supports local, live, bounded operational demos, often driven by
RTI Connext DDS. Applications own language-neutral semantic state; the browser
owns rendering, interaction, and animation. Connext is optional application
integration, not an SDK runtime dependency. The viewer should be able to scan
health, locate change, inspect an object, and invoke a few deliberate commands.

The SDK is not a general analytics platform, website framework, low-code
builder, or pass-through browser-library wrapper.

## Capability-Driving Uses

| Scenario | Viewer need and visual treatment |
| --- | --- |
| Fleet and mobile assets | Find assets, movement, routes, and unhealthy units using metrics, status, bounded lists, logs, moving entities, and selection. Use maps for geographic coordinates and `scene2d` for local/site coordinates. |
| Industrial, energy, mine, or warehouse | Identify running, stale, blocked, or out-of-limit equipment using metrics, gauges, trends, alarms, task grids, or local schematics with zones and paths. |
| Patient or hospital unit | Scan current vitals and alarms, then drill into one patient using cards, lists, metrics, status, and bounded waveforms. Spatial scenes belong only when position has domain meaning. |
| Robot or machine digital twin | Inspect pose and subsystem health through one interactive GLB, stable node transforms, camera controls, selection, status, and logs. The surgical-arm pilot is the reference. |
| Perception, inspection, or medical imaging | Show the latest bounded JPEG, PNG, or WebP frame with timestamp, dimensions, fit, freshness, and textual fallback. This is latest-frame presentation, not video or archival storage. |
| Operational tasks and events | Scan, sort, filter, select, and act on a bounded set of stable-ID rows using severity and confirmed SDK commands. |

Schemas, APIs, examples, and acceptance tests should serve at least one of
these workflows without exposing a renderer's full configuration surface.

## Graphical Vocabulary

### Available

| Element | Use and boundary |
| --- | --- |
| Card | Group one operational concern; avoid decorative nesting. |
| Metric, text, badge | Current values and semantic status; no arbitrary HTML or historical plotting. |
| Log, table | Bounded stable-ID events and rows; not log exploration, spreadsheets, or data lakes. |
| `scene2d` | Entities, links, heading, status, and freshness in local coordinates; not a geographic map. |
| `scene3d` | One GLB with stable node transforms, camera, and status; not a scene editor or server-side Three.js API. |
| Custom component | Application JSON for a custom frontend; no automatic built-in rendering. |
| Command controls | Explicit validated actions, with confirmation where needed; not arbitrary client messaging. |

### Planned

| Element | Direction |
| --- | --- |
| Bounded time series | Waveforms and recent telemetry via uPlot. |
| Indicator chart | Gauges, dials, and rich status charts via Apache ECharts. |
| Geographic map | Fleets, swarms, routes, and sites via MapLibre GL JS. |
| High-update schematic | Local entities, zones, paths, and selection via PixiJS-backed `scene2d`. |
| Operational grid | Current tasks, events, and row actions via Tabulator. |
| Raster frame | Latest bounded sensor image via browser-native decoding. |
| Themes and layouts | Governed dark/light presentation and responsive organization. |
| Native host | The same browser app in an opt-in webview; no new component model. |

Optional renderers sit behind constrained SDK schemas. They are explicitly
enabled, locally served, reproducibly pinned, and absent when unused.

## Boundaries and Rules

- Model semantic state, not DOM, SVG markup, pixels, animation frames, or
  renderer instances. Keep IDs stable and collections bounded.
- Preserve Python/C++ validation, state, command, and snapshot parity. Keep
  deployed operation local and offline, without a CDN or Node.js process.
- Let the browser interpolate and animate independently of mutation and
  transport frequency. Prefer core controls when graphics add no domain value.
- Represent degraded data with severity, freshness, timestamps, empty states,
  and textual fallbacks. Keep commands separate from passive state updates.
- Load optional runtimes only when enabled and used. Test visual capabilities
  on desktop and mobile in empty, stale, error, and updating states.
- Add a candidate only when a recurring demo cannot use this vocabulary. First
  define its scenario, bounded data, updates, interactions, fallback, and
  cross-language behavior; select a renderer afterward.

Middleware or arbitrary relationship graphs, general business analytics,
unbounded exploration, video streaming, and full image annotation are not
current goals and require separate product decisions.

## References and Agent Handoff

Concrete references are the Python/C++ `simple` and `connext` examples for
`scene2d`, `arm3d` plus `examples/web/arm3d/` for 3D, and `gallery` plus
`examples/web/gallery/` for custom frontends. See `docs/architecture.md` for
shipped invariants, `implementation-plans/sdk_next_wave.md` for sequencing,
and `implementation-plans/ui_renderer_adapters_opt_in.md` for planned adapters.

At session start:

1. Name the workflow and viewer question.
2. Confirm whether the capability is available, planned, or a candidate.
3. Inspect the nearest example, architecture, and one relevant plan.
4. Define bounded data, update rate, interactions, fallback, and shutdown.
5. Reuse the smallest fitting surface; keep Python, C++, browser, fixtures,
   examples, and docs aligned; validate the workflow, not just isolated APIs.

For handoff, provide this file plus the specific workflow, status, plan, and
acceptance scenario the next agent owns.
