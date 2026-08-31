# RTI Demo UI Architecture

## 1. Objective

RTI Demo UI is a small local UI SDK designed for RTI Connext DDS demos without
linking to or depending on Connext itself. It has interchangeable Python and
C++ state servers and one shared browser frontend. Python uses Python 3.11+,
asyncio, and aiohttp. C++ uses C++17, cpp-httplib, and nlohmann/json.

The server owns authoritative semantic state. The browser owns DOM, SVG, and
animation. The SDK does not serialize markup, DDS objects, or animation frames.
The supported browser transport is `/sdk/client.js`; it offers compatible
polling and opt-in server-sent events (SSE). `runtime.js` is the built-in
renderer that uses the polling default and consumes complete snapshots through
`subscribe()` without transport-specific handling.

The component model includes `DemoUiApp`, `Card`, `Scene2DViewport`,
`Scene3DViewport`, table, metric, text, badge, log, and opaque custom components.
The SDK is local and single-process. Authentication, TLS termination, public
deployment, and arbitrary server-side widget handles are out of scope.

## 2. Runtime Flow and Ownership

Applications create cards and components before or during the application
lifecycle. Python mutations after startup run on the event loop and thread that
started `run()`; foreign threads must use `loop.call_soon_threadsafe`. C++
model methods are protected by one model mutex and may be called from
application threads. HTTP handlers take a consistent snapshot before
serialization and never retain mutable model references.

Every successful logical mutation increments one application-wide monotonic
`revision` exactly once. Failed mutations leave state and revisions unchanged.
Component `revision` records the application revision at its latest mutation.
Component IDs remain stable for the lifetime of the application.

Python uses `NEW -> STARTING -> RUNNING -> STOPPING -> STOPPED` and an
`aiohttp.web.AppRunner`. C++ uses a blocking httplib server. Both bind before
announcing readiness. The default is literal `127.0.0.1` with port `0`; callers
obtain the selected port through public `ReadyInfo` APIs. `stop()` is
idempotent.
Python waits for aiohttp cleanup. C++ stops accepting requests, closes active
event streams, drains active commands, cancels SDK timers, and joins them before
returning.

## 3. Repository Layout

```text
assets/                 canonical index.html, runtime.js, client.js, theme.css
cpp/                    C++17 library and embedded asset generation
python/                 Python package and package-data build hook
examples/               Python, C++, web, and optional Connext examples
tests/                  Python, C++, browser, and shared fixtures
docs/                   architecture, API, lifecycle, and frontend contracts
```

## 4. HTTP Contract

Both backends expose these SDK-owned routes:

| Request | Response | Cache policy |
| --- | --- | --- |
| `GET /` | built-in or static-root `index.html` | `no-cache` |
| `GET /sdk/index.html` | canonical SDK HTML | `no-cache` |
| `GET /sdk/runtime.js` | canonical renderer | `no-cache` |
| `GET /sdk/runtime3d.js` | optional bundled Three.js renderer | `no-cache` |
| `GET /sdk/client.js` | canonical browser client | `no-cache` |
| `GET /sdk/theme.css` | canonical theme | `no-cache` |
| `GET /api/health` | `{"status":"ok"}` | `no-store` |
| `GET /api/state` | v2 snapshot | `no-store` |
| `GET /api/events` | SSE state stream | `no-cache` |
| `GET /api/command-capability` | opt-in capability | `no-store` |
| `POST /api/commands/{name}` | command envelope | `no-store` |

`/api/` and `/sdk/` are reserved prefixes. Unknown API routes return JSON
`{"error":"not found"}`. Unknown SDK/static assets return a plain 404.
Unsupported methods return 405. Responses include `Content-Type`,
`Content-Length`, and `X-Content-Type-Options: nosniff` where applicable.

Static roots must contain a regular `index.html`. URL decoding, traversal,
absolute paths, NUL bytes, directories, broken links, and symlinks escaping the
root are rejected. The explicit MIME map covers HTML, JavaScript, CSS, JSON,
SVG, common images, fonts, GLB, and GLTF. C++ embeds the canonical assets at
configure time; Python loads them from package resources.

## 5. Snapshot Schema

`GET /api/state` always returns a full v2 snapshot. There is no v1 compatibility
endpoint.

```json
{
  "schema_version": 2,
  "revision": 42,
  "title": "Fleet Demo",
  "theme": "light",
  "layout": "sidebar-main",
  "data": {"fleet": {"connected": true}},
  "cards": [
    {
      "id": "card-1",
      "title": "Operations",
      "area": "sidebar",
      "span": 1,
      "components": [
        {
          "id": "table-1",
          "type": "table",
          "revision": 42,
          "data": {
            "columns": [{"id": "name", "label": "Name", "sortable": true}],
            "rows": [{"id": "vehicle-1", "cells": {"name": "Vehicle 1"}}],
            "empty_state": "No vehicles"
          }
        }
      ]
    }
  ]
}
```

Every component uses the envelope `id`, `type`, `revision`, and `data`. Scene
fields that were direct v1 component fields now live under `data`. Snapshot
values are JSON-compatible: objects, arrays, strings, booleans, finite numbers,
and null. Unknown component types render an isolated diagnostic.

Application state uses `set_data(value)` and `update_data(path, value,
create_missing=False)`. Paths contain non-empty string segments. Intermediate
objects are created only when requested.

## 6. Event Stream

`GET /api/events` exposes the same read-only state as `GET /api/state` using
`text/event-stream`. It first sends `retry: 1000`, then an atomic current
`snapshot` event. Later `patch` events carry the base and resulting application
revisions. Event IDs are decimal application revisions. A heartbeat comment is
sent after 15 seconds without a state event.

Both backends coalesce changes to at most 30 publications per second and send
latest state rather than replaying every intermediate revision. Each connection
has one pending state-event slot. A lagging client is reset with a current
snapshot and is disconnected if it remains unwritable. Writes have a five-second
deadline, and each backend admits at most 16 active streams. The C++ server uses
20 workers so four remain available for ordinary state, asset, health, and
command requests.

Presentation changes emit a `replace-presentation` patch with the complete
`theme` and `layout`; card presentation changes emit the card's normal
`upsert-card` patch.

The stream emits no CORS headers and accepts no command capability. It uses the
same loopback trust boundary as the snapshot route. Response compression and
proxy buffering must not delay event chunks. Reverse proxies are unsupported
unless they explicitly preserve long-lived, unbuffered SSE responses and use an
idle timeout longer than the 15-second heartbeat interval.

## 7. Presentation

Presentation metadata is authoritative additive schema-v2 state. `theme` is
`dark` or `light`, and `layout` is `auto`, `grid-2`, `grid-3`, or
`sidebar-main`. Cards serialize `area` as `main` or `sidebar` and `span` as the
integer `1`, `2`, or `3`. The compatibility defaults for missing or malformed
fields are `dark`, `auto`, `main`, and `1`. The built-in renderer reports each
malformed field independently and never derives CSS classes or unrestricted
styles from snapshot strings.

`auto` uses responsive 280 px target columns. The fixed grid presets use two or
three equal columns. `sidebar-main` uses one bounded 320 px sidebar and one
flexible main track. Every layout collapses to source-ordered single-column
cards at 720 px or less. CSS caps spans to available columns and keeps card
contents from forcing page overflow. DOM order always follows snapshot order;
presentation changes move existing cards rather than recreate card or component
nodes.

At most one card may have `area=sidebar`. Entering `sidebar-main` at runtime
requires exactly one sidebar at the mutation commit point. Constructing an app
with `sidebar-main` permits cards to be configured before `run()`, which then
requires exactly one sidebar. Failed changes and valid no-ops do not increment
the revision.

The canonical `/sdk/theme.css` defines stable semantic background, surface,
card, text, muted, border, accent/hover, success, warning, and danger tokens for
both palettes. Theme selection uses `data-sdk-theme` on the document element,
preserving application-owned classes. The built-in grid uses `data-sdk-layout`
on `#sdk-cards` and bounded `data-sdk-area` and `data-sdk-span` card attributes.

## 8. Components and Validation

`Card` provides:

- `add_scene_2d(width, height, bounds)`
- `add_scene_3d(asset, camera=None, background="#0a0e17", grid=False)`
- `add_table(columns, rows, empty_state="")`
- `add_metric(label, value, severity=None)`
- `add_text(text, severity=None)`
- `add_badge(text, severity=success)`
- `add_log(entries, empty_state="", max_entries=100)`
- `add_custom_component(type, data, id=None)`

Tables require non-empty unique column IDs and stable non-empty unique row IDs.
Table handles support `set_rows`, `upsert_row`, and `remove_row`. Metrics,
text, and badges support live value/text updates. Logs use stable IDs,
ISO-8601 timestamp strings, message text, and bounded retention; `append` and
`clear` are explicit mutations. Custom component types must be non-empty and
must not use SDK-reserved types. Custom handles support `set_data` and
`update_data`.

`Severity` is `success`, `warning`, or `danger`. `Freshness` is `fresh`,
`aging`, or `stale`. Scene bounds, coordinates, headings, widths, heights, and
intervals are finite/positive as appropriate. Python raises `ValueError` and
C++ throws `std::invalid_argument` for validation failures.

Scene3D uses a complete JSON data object with `asset`, `nodes`, `camera`,
`background`, and `grid`. Nodes contain immutable IDs and paths plus position,
quaternion rotation, positive scale, visibility, and severity. Paths address
imported glTF nodes using JSON Pointer escaping; the backend validates lexical
shape while the browser reports unresolved paths. Coordinates are local glTF
right-handed, Y-up meters. `add_node`, partial `update_node`, `remove_node`,
atomic `apply_node_batch`, and atomic `set_config` preserve the same revision
rules as the other components. Removed IDs remain stale for the scene
lifetime.

## 9. Commands

Commands are opt-in. Registration is immutable once `run()` begins. Names match
`^[a-z][a-z0-9-]{0,62}$`. The supported schema subset is exactly `type`,
`properties`, `required`, `items`, `enum`, `minimum`, `maximum`, `minLength`,
`maxLength`, and `additionalProperties`. Schemas reject unsupported keywords,
tuple-form `items`, and non-boolean `additionalProperties`.

The command request is:

```text
POST /api/commands/{name}
Content-Type: application/json
Origin: http://127.0.0.1:<bound-port>
X-RTI-Demo-Command-Capability: <process-random-capability>
```

Commands are allowed only when the configured host is the literal `127.0.0.1`
or `::1`. The capability route requires the exact bound origin and otherwise
returns 404. Commands require the same origin and capability. No CORS headers
are emitted.

Bodies are limited to 64 KiB and must be JSON objects. Responses use one of:

```json
{"ok": true, "result": {}}
```

```json
{"ok": false, "error": {"code": "validation_error", "message": "...",
 "details": []}}
```

Malformed JSON and schema failures return 400. Missing or invalid capability
returns 403. Unknown commands return 404. Unsupported methods return 405.
Oversized bodies return 413 with `payload_too_large`. Shutdown and concurrent
same-command requests return 409 with `command_stopping` or
`command_busy`.
Handler failures return 500 with a generic message and are logged server-side.
At most one invocation of each command name runs at once; different names may
overlap. Python handlers run on the owner event loop. C++ handlers run outside
the model mutex and must marshal thread-affine work themselves.

## 10. Browser Client

`/sdk/client.js` exports `createClient(options)`. `transport: "poll"` is the
compatibility default and uses one-in-flight full-state polling;
`pollIntervalMs` defaults to 200. `transport: "sse"` opens a same-origin
`EventSource`. There is no `auto` mode and explicit SSE never falls back to
polling. Browser reconnects report `reconnecting` and use native EventSource
retry behavior.

The client validates v2 snapshots and all patch operations. It ignores stale
patch revisions. An invalid payload, unknown operation, revision gap, or patch
application failure closes that source, fetches a complete `/api/state`
snapshot, publishes it, and opens a new EventSource without changing transport.
A connection generation prevents late events or fetch completions from an old
source from publishing state. `start()` and `stop()` are idempotent; stopping
closes the source, clears poll/recovery timers, and suppresses late updates.

The client also owns connection-state notifications, capability bootstrap,
command calls, and structured error parsing. It exposes `start`, `stop`,
`subscribe`, `unsubscribe`, `getSnapshot`, `getConnectionState`, and
`invokeCommand`. Published snapshots are immutable by convention and the client
does not render markup.

`runtime.js` is a client consumer. It reconciles cards/components by stable ID,
keeps presentation-only table sorting local to the browser, and interpolates
scene positions with `requestAnimationFrame`. `prefers-reduced-motion` applies
target positions immediately. For `scene3d`, it dynamically imports the
optional `/sdk/runtime3d.js` module only after receiving a scene component.
That renderer caches GLB parsing by URL, clones per-scene hierarchies and
materials, owns orbit controls and browser-local selection, and always keeps a
semantic node list and textual fallback beside the canvas. Unsupported custom
components show a visible isolated diagnostic.

## 11. Build and Tests

C++ uses pinned cpp-httplib v0.18.3 and nlohmann/json v3.11.3 through CMake
`FetchContent`; nlohmann/json is a public link dependency because it appears in
public C++ APIs. Python requires `aiohttp>=3.10,<4`; development extras include
pytest, pytest-asyncio, and Playwright. The optional runtime3d artifact is built
with Node 22.14.0, Three.js 0.173.0, and esbuild 0.25.0 from
`tools/scene3d/package-lock.json`.

The focused validation gates are:

```bash
PYTHONPATH=python pytest tests/py
PYTHONPATH=python pytest tests/browser
cmake --build build
ctest --test-dir build
```

Python and C++ share deterministic JSON fixtures for snapshot, component, and
command-schema parity. Browser tests run the same renderer assertions against
both backends at desktop and narrow mobile viewports. Contract tests cover
headers, canonical asset bytes, v2 snapshots and patches, SSE recovery and
admission, port-zero readiness, capability checks, schema validation, command
busy admission, shutdown draining, and the 64 KiB limit.
