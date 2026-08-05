# Generic State, Commands, and Browser Client Plan

## Objective

Extend RTI Demo UI so application-owned operational dashboards can migrate to
the SDK without reproducing its state transport, lifecycle, or command
plumbing. Preserve the existing local, framework-agnostic, full-snapshot
architecture and parity between the Python and C++ backends.

The first delivery adds generic state components, a local opt-in command API,
and a supported browser client. It does not add a general-purpose server-side
widget framework, application-defined HTTP routes, remote deployment support,
or a push transport.

This plan depends on `custom_frontend_and_lifecycle.md` for completed
static-root and bind-before-listen work. That plan owns the existing lifecycle
refactor; this plan owns only the follow-on public port-zero and readiness API.
Implement overlapping host-default and readiness changes once in this plan after
the dependency is merged. Do not run the two plans as independent edits to
`DemoUiApp` lifecycle code.

## Product Decisions

### Compatibility Boundary

Continue serving full snapshots from `GET /api/state`, with one
application-wide monotonic `revision`. This is the first SDK consumer, so ship
the v2 snapshot as the next major SDK release rather than maintaining a v1
compatibility endpoint. The release notes and custom frontend guide must state
that v1 scene fields moved under `component.data`, show a before/after example,
and require frontend authors to upgrade their snapshot parsing before upgrading
the SDK. The browser client must reject unsupported major schema versions
visibly and preserve the existing revision short-circuit behavior.

The v2 snapshot shape is:

```json
{
  "schema_version": 2,
  "revision": 42,
  "title": "Fleet Demo",
  "data": {"fleet": {"connected": true}},
  "cards": [
    {
      "id": "card-1",
      "title": "Operations",
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

Every component uses the stable envelope `id`, `type`, `revision`, and `data`.
Existing `scene2d` fields move inside `data` in v2. IDs remain stable for the
application lifetime. `revision` on a component records the application
revision at its most recent mutation; it does not create an independent
revision counter.

`data` is JSON-compatible: objects, arrays, strings, booleans, finite numbers,
and null. Reject non-finite numbers and values that cannot serialize to JSON.
Application state uses `set_data(value)` and `update_data(path, value)` rather
than exposing a mutable backing dictionary/map. The path API uses non-empty
string segments and creates intermediate objects only when requested.

### Generic Components

Add these SDK-owned components to `Card`:

- `add_table(columns, rows, empty_state="")`
- `add_metric(label, value, severity=None)`
- `add_text(text, severity=None)`
- `add_badge(text, severity=success)`
- `add_log(entries, empty_state="")`

Tables require non-empty unique column IDs and stable non-empty unique row IDs.
Rows carry cell values plus optional `severity` and `status` fields. The
built-in frontend owns presentation-only sorting, sort direction, and empty
state rendering. It must preserve sort state by table ID across polling and
never mutate the server model merely to sort a view.

Returned component handles support live updates. `Table.set_rows(rows)`
atomically replaces rows after validation, `Table.upsert_row(row)` inserts or
replaces one row by stable ID, and `Table.remove_row(id)` rejects an unknown
ID. `Metric.set_value(value, severity=None)`, `Text.set_text(text,
severity=None)`, and `Badge.set_text(text, severity=None)` update their
respective models. Every successful call validates the complete resulting
component state, preserves its component ID, updates its component revision,
and increments the global revision exactly once. Failed calls leave all state
and revisions unchanged.

Logs use stable entry IDs, ISO-8601 timestamp strings, message text, and an
optional severity. Retention is explicit: `add_log` accepts a bounded maximum
entry count and drops oldest entries as part of one revision-changing mutation.
`Log.append(entry)` validates a new unique entry ID, appends it, applies
retention, and increments the global revision exactly once. `Log.clear()` is
an explicit mutation with the same revision rule.

Use existing `Severity` values. Do not add Connext-specific severity, lifecycle,
or QoS types.

### Opaque Custom Components

Expose `Card.add_custom_component(type, data, id=None)` for application-owned
frontends. `type` must be non-empty and must not use SDK-reserved component
type names. The SDK validates JSON-compatible `data`, assigns a stable ID when
omitted, serializes the standard component envelope, and preserves it during
polling.

The built-in renderer displays an isolated unsupported-component diagnostic.
The browser client exposes opaque components without interpreting their data.
Application frontends may render these types themselves. Custom components do
not receive a server-side rendering or event lifecycle in this release.
`CustomComponent.set_data(data)` atomically replaces JSON-compatible data, and
`update_data(path, value)` applies the same validated path behavior as
application state. Both preserve ID and increment the global revision exactly
once.

### Commands

Commands are opt-in, application-local actions:

```text
POST /api/commands/{name}
Content-Type: application/json
Origin: <bound SDK origin>
X-RTI-Demo-Command-Capability: <process-random capability>
```

Applications register a name, a JSON Schema subset for the request payload,
an optional confirmation descriptor, and an async-capable handler. The schema
subset is deliberately small and implemented identically in both languages:
`type`, `properties`, `required`, `items`, `enum`, `minimum`, `maximum`,
`minLength`, `maxLength`, and `additionalProperties`.

Schema semantics are deliberately narrower than JSON Schema: `type` is exactly
one string; `properties` is an object whose values recursively use this same
subset; `items` is one recursive schema, not a tuple of schemas;
`additionalProperties` is exactly a boolean; `required` names direct object
properties; and every listed keyword is ignored when it does not apply to the
instance type. Reject unsupported keywords when a command is registered.
Shared fixtures must cover nested objects, arrays, the rejected tuple-form
`items`, rejected non-boolean `additionalProperties`, and unsupported keywords.

Command names match `^[a-z][a-z0-9-]{0,62}$`, are URL-decoded exactly once as
UTF-8, and reject malformed encodings, decoded slashes, and duplicate
registration. Registration after `run()` begins fails with a language-native
runtime error because the registry is immutable.

The server accepts only JSON objects. It reads command bodies from the request
stream in bounded chunks, rejects more than 64 KiB before JSON parsing, and
does not rely on aiohttp's `client_max_size` default error response. In Python,
set `client_max_size` above the command limit and perform the 64 KiB gate in
the command dispatcher so oversize responses use the standard envelope. In
C++, set the cpp-httplib payload limit and map its command-route oversize error
to that same envelope; also check the accepted request body length defensively.
It validates payloads before invoking a handler. Responses always use one
envelope:

```json
{"ok": true, "result": {}}
```

```json
{
   "ok": false,
   "error": {"code": "validation_error", "message": "...", "details": []}
}
```

Use `400` for malformed JSON or schema failures, `413` for an oversized body,
`403` for an absent/invalid capability or untrusted origin, `404` for unknown
commands, `405` for unsupported methods, `409` for a rejected command during
shutdown or while the same command is busy, and `500` with a generic message
for handler failures. Log handler exceptions server-side without serializing
stack traces.

The command registry is immutable after server startup. Python command
handlers run on the owner event loop. C++ handlers run outside the model mutex
on a request thread; handler documentation requires applications to marshal
thread-affine work themselves. A handler can mutate SDK state using the
existing language-specific rules. The command handler receives validated input
only; it must return JSON-compatible output.

At most one invocation of a command name runs at a time; a concurrent request
for that name fails immediately with `409` and `command_busy` rather than
occupying an unbounded queue. Different commands may overlap. Python tracks
active commands on the owner loop without awaiting a lock. C++ uses a
per-command atomic admission flag and releases it with RAII after invoking the
handler, so httplib request workers never block waiting for another invocation
of the same command. Once shutdown begins, reject new commands with `409` and
`command_stopping`; let already-running handlers complete, then wait for them
before HTTP cleanup returns. If a completed handler cannot serialize a result
because shutdown has already closed its response, discard that result without a
second mutation or retry.

Confirmation metadata is declarative only. The browser client exposes it so a
frontend can request user confirmation before invocation.

Commands are only registered when the application calls the registration API.
Default host changes from `0.0.0.0` to `127.0.0.1`; LAN binding remains an
explicit constructor option for state and static assets, but command
registration fails unless the configured host is the literal loopback address
`127.0.0.1` or `::1`. This avoids ambiguous origins for wildcard/LAN binds.
Registering the first command generates a process-random, high-entropy
capability. `GET /api/command-capability` returns it only to an exact Origin of
`http://127.0.0.1:<bound-port>` or `http://[::1]:<bound-port>`, matching the
configured loopback host; the endpoint is otherwise `404` and always
`no-store`. Commands require the same Origin and capability header. The
browser client obtains and holds the capability only in memory. No CORS headers
are emitted. This is an opt-in local browser capability, not authentication or
a public-hosting security model.

### Browser Client

Publish `/sdk/client.js` as a supported ES module independent of the built-in
DOM renderer. It exports:

- `createClient(options)`
- `start()` and `stop()`
- `subscribe(listener)` and `unsubscribe(listener)`
- `getSnapshot()` and `getConnectionState()`
- `invokeCommand(name, payload)`

The client owns one-in-flight full-state polling, schema validation, revision
tracking, retry backoff, connection-state notifications, command capability
bootstrap, command HTTP calls, and structured error parsing. It exposes
snapshots as immutable-by-convention data and never renders markup. `runtime.js`
becomes a consumer of this module, retaining the current built-in DOM/SVG
renderer.

Custom application pages load `/sdk/client.js` and their own renderer. The
client has no framework dependency and does not require SDK CSS.

### Lifecycle and Test APIs

Allow port `0` in both backends. After bind, publish immutable `ReadyInfo`
containing `host`, `port`, and canonical bound `url`. Python exposes
`await app.wait_until_ready()` and `app.ready_info`; C++ exposes
`wait_until_ready()` and `ready_info()`. Do not expose private test-only
readiness mechanisms.

Use `127.0.0.1` in browser and HTTP test helpers. Tests must await readiness
and use the reported port instead of hard-coded ports wherever practical.

## Implementation Steps

### 1. Lock the v2 Contract

1. Update `docs/architecture.md`, `docs/api/python.md`, `docs/api/cpp.md`, and
   `docs/custom-frontends.md` with the v2 snapshot, major-release upgrade
   steps, command capability, browser-client, host, readiness, and command
   concurrency contracts. `api/python.md` and `api/cpp.md` gain dedicated
   sections for application-data mutations; every generic and custom component
   handle; command/schema, capability, and handler APIs; and port-zero
   readiness APIs. The custom frontend guide includes the v1-to-v2 scene
   envelope conversion.
2. Add language-neutral JSON fixtures under `tests/fixtures/` for valid and
   invalid snapshots, JSON data values, table rows, command payloads, and
   command response envelopes.
3. Define equivalent validation error codes and messages in the fixtures so
   Python and C++ parity tests can assert behavior without copying implementation
   details.

### 2. Extend the Backend Model

1. Refactor Python `components.py` and C++ `components.hpp`/
   `components.cpp` around a common internal component serialization contract.
2. Add application data storage and mutation APIs to `DemoUiApp` in both
   languages. Every successful mutation changes the global revision once.
3. Migrate `Scene2DViewport` serialization to the v2 component envelope and
   add a component revision field. Update it on every entity/link mutation in
   Python and C++, alongside generic SDK components, their live mutation APIs,
   custom component data mutations, validation, stable IDs, and serialization.
4. Update the snapshot serializers in Python `demo_ui_app.py` and C++ `app.cpp`
   to emit schema v2 and structured JSON rather than hand-built JSON fragments
   where new arbitrary data is involved.
5. Add focused model tests for validation, ID stability, one revision increment
   per mutation, JSON serialization rejection, log retention, and backend
   snapshot parity.

### 3. Add the Command Registry and Endpoint

1. Define public `Command`, `CommandSchema`, command-name validation,
   confirmation metadata, and command-capability types in Python and C++
   headers/modules with concise, language-native registration APIs on
   `DemoUiApp`.
2. Implement one shared validation algorithm per backend for the documented
   schema subset and test the same fixture vectors in both languages.
3. In Python, reshape `_handle_request` so it dispatches the capability and
   command method/path combinations before its current GET-only rejection, or
   register explicit aiohttp routes that take precedence over the wildcard
   route. In C++, register the capability and command routes before the generic
   POST method-rejection route and static catch-all. Validate exact origin and
   capability before command lookup, retain JSON 404 behavior for other
   `/api/` paths, and return 405 for non-POST command requests.
4. Admit at most one same-name handler without blocking another request worker,
   wait for in-flight work during shutdown, and convert validation, size, origin,
   capability, unknown-command, busy, handler, shutdown, and serialization
   failures to the standard response envelope.
5. Add HTTP tests for success, malformed JSON, schema rejection, invalid names,
   duplicate and late registration, unknown command, unsupported method,
   capability/origin rejection, 64 KiB overflow envelope, handler exception
   containment, same-command busy rejection, shutdown with in-flight work, and
   state mutation from a handler.

### 4. Extract the Browser Client

1. Split transport, retry, schema/revision handling, and command invocation
   from `assets/runtime.js` into `assets/client.js`.
2. Rewrite `runtime.js` to create a client and reconcile only SDK-owned DOM/SVG.
   Preserve existing polling cadence, backoff, reduced-motion behavior, and
   unsupported-component diagnostics.
3. Add browser tests for initial load, reconnect, unchanged revision behavior,
   table sort persistence, live component updates, generic component rendering,
   command capability bootstrap and success/error, and a custom frontend
   consuming `client.js` to render and update an opaque component.
4. Update Python `_ASSET_ROUTES`; CMake's `RTI_DEMO_ASSET_FILES` list, explicit
   `file(READ ...)` variables, and delimiter-check `foreach`; and
   `cpp/src/web_assets.hpp.in` with `embedded_client_js()`. Update package data
   and C++ routing so `client.js` is served byte-identically at
   `/sdk/client.js` by both backends.

### 5. Complete Operational Readiness

1. Change public default hosts to `127.0.0.1` and permit port `0`. In Python,
   retain the existing post-`TCPSite.start()` socket inspection via
   `site._server.sockets`, validate exactly one bound socket, and store its
   `getsockname()` port in immutable `ReadyInfo` before setting readiness. In
   C++, keep `bind_to_port()` for explicit ports and use
   `bind_to_any_port(host_)` for port `0`; store its returned port in
   `ReadyInfo` before `listen_after_bind()`. Print and expose the canonical URL
   from `ReadyInfo`, not the requested port.
2. Replace private Python test readiness access and fixed-port fixtures with
   the public readiness API in `tests/py/test_model_and_http.py`,
   `tests/py/test_static_root.py`, and `tests/browser/test_browser.py`; update
   `tests/cpp/http_tests.cpp` from schema v1 to v2 and add C++ port-zero/
   readiness coverage in `tests/cpp/lifecycle_tests.cpp`. Use each returned
   ready URL rather than fixed ports such as 19072 or 19381.
3. Update README, examples, lifecycle documentation, and custom frontend
   examples to use `client.js` when they consume state or commands. Keep the
   existing gallery as a browser-only static-control smoke demo; do not convert
   it to generic components or commands in this release. Add a separate focused
   browser fixture/example for generic-component and command-client behavior.
4. Run the Python, C++, and browser suites; add explicit byte-parity checks for
   the new browser asset and schema/HTTP parity checks for the new APIs.

## Explicit Deferrals

- SSE and WebSocket transports.
- State deltas, command streaming, cancellation, background jobs, and progress
  events.
- Server-owned forms, button/toggle/slider components, and arbitrary endpoint
  registration.
- Scene layers, static markers, labels, selections, trails, and icon shapes.
- Authentication, TLS, CORS, public hosting, or multi-user sessions.

Reconsider push transport only after measurement shows polling cannot satisfy a
specific dashboard's update rate, payload size, or interaction latency.

## Acceptance Criteria

- Python and C++ emit identical v2 snapshot and command HTTP contracts for the
  shared fixtures.
- Generic and custom components retain stable IDs and support live mutations.
- Each successful mutation increments the global revision exactly once.
- Built-in UI renders generic components while custom pages can render opaque
  components with `/sdk/client.js`.
- Commands are unavailable unless registered and validate names and input.
- Commands require the opt-in loopback same-origin capability.
- A same-command overlap rejects without blocking a worker.
- Commands never disclose handler internals and are loopback-only by default.
- A port-zero app supplies its actual bound URL through public readiness APIs in
  both languages.
- Existing scene behavior, custom static roots, reserved routes, lifecycle
  semantics, and test suites continue to pass.
