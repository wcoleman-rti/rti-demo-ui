# Server-Sent Events Streaming Plan

## Status

Proposed implementation plan for `feature/sse-streaming`.

## Objective

Add `GET /api/events` as a low-latency state transport using Server-Sent
Events (SSE). Send coalesced, revision-ordered patches during normal operation
while retaining `GET /api/state` as the canonical full snapshot, polling
fallback, and resynchronization mechanism. Optimize for latest-state delivery
to a small number of local browser clients rather than delivery of every
intermediate mutation.

This effort changes transport only. The server remains authoritative for
semantic state, and the browser remains responsible for rendering and
animation.

## Current Foundation

- Every successful logical mutation increments one application-wide monotonic
  revision exactly once.
- `GET /api/state` emits a complete schema-v2 snapshot.
- `/sdk/client.js` owns polling, revision short-circuiting, connection state,
  retry backoff, and immutable-by-convention snapshots.
- Python mutations run on the owner event loop after startup.
- C++ model mutations are serialized by the model mutex.

The current model has no mutation journal and SSE does not add one. Mutation
commit points mark affected application, card, or component targets dirty at
the same point that they advance the revision. A short transport flush then
serializes the latest committed values for those targets.

## Product Boundary

The first release provides:

- One same-origin SSE route for state events.
- An immediate snapshot on a new connection.
- Coalesced incremental patches for committed model changes.
- Snapshot resynchronization after reconnects, revision gaps, and slow-client
  queue replacement.
- Heartbeats, one pending state event per subscriber, and deterministic
  shutdown.
- Explicit `sse` and `poll` browser-client transport modes, with `poll` as the
  compatibility default.

It does not provide WebSockets, client-to-server messages over SSE, public
internet deployment, authentication, cross-origin streams, unbounded event
history, guaranteed observation of every revision, or a general event bus.
Commands continue to use their existing HTTP POST contract.

## HTTP and Event Contract

### Endpoint

```http
GET /api/events HTTP/1.1
Accept: text/event-stream
```

Successful responses use:

```http
HTTP/1.1 200 OK
Content-Type: text/event-stream
Cache-Control: no-cache
X-Content-Type-Options: nosniff
```

The implementation may use HTTP/1.1 chunked transfer encoding. It must not set
`Content-Length`. `Connection` is hop-by-hop and is not part of the normative
application contract. Non-GET requests return the existing JSON 405 response.
Query parameters do not carry resume state. The server ignores
`Last-Event-ID` and starts every connection with its current snapshot.

### Snapshot Event

A snapshot event's data is exactly the canonical schema-v2 `/api/state`
payload:

```text
event: snapshot
id: 104
data: {"schema_version":2,"revision":104,"title":"Fleet","data":{},"cards":[]}

```

The server sends a snapshot immediately on every connection. Receiving a
snapshot atomically replaces the client's local snapshot.

### Patch Event

Patches use domain operations rather than JSON Patch array indexes:

```text
event: patch
id: 105
data: {"schema_version":1,"base_revision":104,"revision":105,"changes":[{"op":"upsert-component","card_id":"card-1","value":{"id":"metric-1","type":"metric","revision":105,"data":{"label":"Rate","value":42,"severity":null}}}]}

```

The patch envelope has:

- `schema_version`: patch schema version `1`, independent of snapshot schema
  version `2`.
- `base_revision`: the exact snapshot revision to which the patch applies.
- `revision`: the latest committed application revision represented by the
  publication and its SSE `id`.
- `changes`: a non-empty ordered list of latest-value operations accumulated
  for one transport publication.

A patch may advance across multiple application revisions. It must transform
the state at `base_revision` directly into the same state represented by
`revision`; the client does not need to observe intermediate revisions.

Initial operations are:

- `replace-app-data`, carrying the complete top-level `data` value.
- `upsert-card`, carrying one complete card and its components.
- `remove-card`, carrying a card ID.
- `upsert-component`, carrying a card ID and complete component envelope.
- `remove-component`, carrying card and component IDs.

The current public API does not remove cards or components, but their
operations are reserved now so future structural APIs do not require another
transport design. Theme/layout work may add a complete `replace-presentation`
operation for top-level presentation metadata. Every new model mutation API
must declare which application, card, or component target it dirties.

The client applies a patch only when `base_revision` equals its current
revision and `revision` is greater. An unknown operation, invalid payload,
revision gap, or application failure triggers a full `/api/state` fetch before
stream consumption resumes. Patch application must build and validate a new
snapshot without mutating the previously published snapshot.

### Publication and Reconnection

The broadcaster has a maximum publication rate of 30 Hz. Define the
publication interval as exactly $1/30$ second. When the accumulator transitions
from empty to non-empty, it schedules a flush for
`max(now, previous_flush + publication_interval)`. Mutations before that
deadline join the same flush. A sustained burst therefore produces one
publication per interval, while the first mutation after an idle period is
eligible for immediate publication and must be published within one interval
unless shutdown has begun.

The accumulator uses these keys:

- one `app-data` key;
- one `presentation` key when presentation metadata exists;
- `card:<card_id>` for a complete card; and
- `component:<card_id>:<component_id>` for a component.

Repeated changes to one key collapse to its latest committed value. Marking a
card removes and supersedes all component keys for that card; later component
changes remain absorbed by the complete card until the flush. A removal
supersedes an upsert for the same key. IDs are not reused, so no later upsert
may follow a removal for that ID. Operations are emitted in this exact order:
`replace-app-data`, `replace-presentation`, cards sorted by `card_id`, then
components sorted by `(card_id, component_id)`. Each keyed card or component
emits either its final upsert or removal operation. Both backends implement
this ordering byte-equivalently.

The 30 Hz coalescing rate is an internal transport policy rather than an
application configuration option. Browser animation remains independent and
may run at a higher frame rate.

Subscriber registration and initial snapshot capture must be atomic with
respect to publication. A generated patch is enqueued for a subscriber only
when its `base_revision` matches the revision at the tail of that subscriber's
stream; otherwise the subscriber receives a current snapshot.

Event IDs are decimal application revisions. The server emits
`retry: 1000\n\n` immediately after preparing the stream, independent of state
events. A heartbeat comment such as `: heartbeat\n\n` is written after 15
seconds without a state event; heartbeats do not have IDs and do not affect
connection state or revision.

### Slow Consumers and Shutdown

Each subscriber has room for one pending serialized state event in addition to
any event currently being written. If a new publication arrives while that
slot is occupied, discard the pending event and replace it with one current
snapshot. If the connection remains unwritable, close it and let the client
reconnect. A slow client must never block a model mutation or accumulate a
sequence of pending events. Serialized snapshots are bounded by the
authoritative model state itself; SSE introduces no separate unbounded
allocation. Serialize each publication or replacement snapshot once and share
that immutable payload among subscriber queues rather than making one copy per
subscriber.

Both backends admit at most 16 active SSE streams and return `503` for an
additional subscription. A state event or heartbeat write must complete
within five seconds. A write timeout, false/closed transport result,
`ConnectionResetError`, or `BrokenPipeError` makes the subscriber unwritable
and closes the stream; no retry is performed by the server handler.

On application stop, prevent new subscriptions, wake all waiting stream
handlers, finish or close active providers, and then continue normal HTTP
cleanup. Subscriber cleanup is idempotent when the peer disconnects during
shutdown.

## Python Implementation

Add an internal event broadcaster owned by `DemoUiApp`. It runs on the owner
event loop after startup and maintains a dirty-target accumulator plus one
single-slot `asyncio.Queue` per connection. Pre-start mutations need no dirty
entries because a new subscriber receives the resulting snapshot.

Refactor model commit handling so component, card, and application mutations
mark their affected target dirty at the same logical commit point as the
revision increment. Flushes serialize current target values only on the owner
event loop; do not serialize arbitrary model state from foreign threads.

Implement `_handle_events()` with `aiohttp.web.StreamResponse`, explicit write
error handling, heartbeat timeout, cancellation cleanup, and broadcaster
unsubscribe in `finally`. Treat `ConnectionResetError`, `BrokenPipeError`,
cancellation, and transport closure as normal disconnects. Enforce the
five-second write deadline around each `StreamResponse.write()` and enforce
the shared 16-stream admission limit before preparing a response.

## C++ Implementation

Add an internal `SseManager` guarded by its own mutex and condition variable.
Keep pending events as serialized immutable strings so stream workers do not
retain mutable model references. While holding the model mutex, a mutation
advances the revision and marks its target dirty. Flush processing acquires
locks only in the documented `model mutex -> SSE mutex` order; the SSE mutex is
never held while acquiring or waiting for the model mutex. This ordering also
prevents concurrent mutation threads from publishing revisions out of order.

Register `/api/events` before generic API fallbacks and use cpp-httplib's
chunked content provider. Each connection may occupy one httplib worker while
open. Configure cpp-httplib's task queue with exactly 20 workers: at most 16
concurrent SSE streams plus four workers reserved for ordinary state, asset,
health, and command requests. Return `503` before occupying a provider when
the SSE admission limit is reached. Configure a five-second socket write
timeout. The provider must observe stop state, condition-variable wakeups,
failed writes, peer writability, and provider completion without leaking a
subscriber.

The C++ implementation must not infer disconnect solely from an empty event,
because an idle stream is valid. Heartbeat deadlines and explicit stop flags
wake the provider.

## Browser Client API

Extend `createClient(options)` with:

```javascript
createClient({
  transport: 'poll', // 'sse' | 'poll'
  pollIntervalMs: 200
});
```

`sse` opens `EventSource`, reports `reconnecting`, and uses the browser's SSE
retry behavior without silently changing transport. `poll` is the default,
preserves current behavior, and never opens an `EventSource`. Applications
choose the transport appropriate to their update rate and deployment path;
there is no `auto` mode or polling fallback from explicit `sse` mode.

The client ignores patch events whose revision is less than or equal to its
current revision. On an unknown operation, invalid payload, revision gap, or
patch application failure, it closes the current `EventSource`, fetches
`/api/state`, publishes that snapshot, and opens a new `EventSource`. A
connection-generation token prevents late events or fetch completions from an
older source from changing state. This recovery does not change transport
mode.

Custom `baseUrl` values must produce a same-origin events URL accepted by
`EventSource`. `start()` and `stop()` remain idempotent; `stop()` closes the
source, clears all retry/poll timers, and prevents late events from notifying
subscribers. The public subscription callback and immutable snapshot contract
do not change.

The browser client, not `runtime.js`, parses and applies patches. The built-in
renderer continues to consume complete snapshots through `subscribe()`.

## Security and Compatibility

The event route exposes the same read-only state as `/api/state` and uses the
same local-host trust boundary. It emits no CORS headers and accepts no command
capability. Responses must avoid compression buffering that prevents timely
delivery, and documentation must note that reverse proxies are unsupported
unless configured for streaming.

`GET /api/state` remains supported. Existing clients continue polling without
changes, and `poll` remains the default after SSE ships. Selecting `sse` is an
explicit application decision.

## Implementation Phases

### Phase 1: Lock Fixtures and Dirty-Target Contract

- Add shared snapshot, coalesced-patch, revision-gap, and operation vectors
  under `tests/fixtures/`.
- Define exact patch validation and application behavior in `/sdk/client.js`.
- Add dirty-target accumulation in both backends without an HTTP endpoint, and
  prove that a flush represents the latest state at its published revision.

### Phase 2: Python Stream

- Implement the broadcaster, route, coalescing, heartbeat, slow-consumer reset,
  disconnect cleanup, and shutdown.
- Add focused Python tests with multiple subscribers and mutations before,
  during, and after connection.

### Phase 3: C++ Stream

- Implement equivalent coalescing and subscriber management with a chunked
  provider.
- Add worker-capacity, peer-disconnect, blocked-provider shutdown, and lock
  ordering tests.

### Phase 4: Browser Transport

- Add patch application and explicit `sse`/`poll` modes to the canonical
  client asset.
- Keep `runtime.js` transport-agnostic and update packaged/embedded asset
  parity.
- Add browser coverage against both backends.

### Phase 5: Documentation and Rollout

- Update architecture, API, lifecycle, custom-frontend, and route docs.
- Document fallback controls and proxy limitations.
- Document `poll` as the compatibility default and `sse` as an explicit
  application choice.

## Verification

- Python tests: immediate snapshot, target coalescing, flush liveness,
  multi-client ordering, 16-stream admission, queue replacement with a
  snapshot, five-second write timeout, heartbeat, disconnect, cancellation,
  and stop with an idle stream.
- C++ tests: the same contract plus 20-worker capacity and reservation,
  blocked-provider wakeup, lock ordering, and socket-thread cleanup.
- Shared parity tests: byte-equivalent logical event payloads for fixture
  mutations, exact operation ordering and precedence, and equivalent coalesced
  publications for the same mutation burst.
- Browser tests: patch updates without `/api/state` polling, forced revision
  gap resynchronization, stale-event suppression, SSE reconnection without
  transport switching, stop cleanup, poll-default compatibility, and operation
  against both backends.
- Performance test: a high-rate mutation burst produces at most 30 state
  events per second per healthy subscriber, converges to the latest snapshot,
  and does not cause unbounded memory or require rendering at mutation
  frequency. Animation remains browser-owned.

Run the repository's focused Python, C++, browser, generated-asset, and
pre-commit checks documented in `docs/development/contributing.md`.

## Resolved Decisions

- Browser transport is explicit: `poll` remains the default and applications
  may select `sse`; there is no `auto` mode or cross-transport fallback.
- SSE publishes latest-state changes at most 30 times per second and does not
  retain or replay intermediate revisions.
- Each subscriber has one pending state-event slot. Replacing an occupied slot
  produces one latest complete snapshot; a failed write or one exceeding five
  seconds disconnects the peer.
- Both backends admit at most 16 SSE streams. The C++ backend uses 20 workers
  to reserve four for ordinary requests. These transport policies are fixed
  internal limits in the first release rather than constructor options.

## Acceptance Criteria

- Both backends expose the same snapshot and coalescing behavior and cleanly
  stop with connected idle and slow clients.
- Every accepted patch transforms its `base_revision` into the same complete
  snapshot represented by its `revision`, which may skip intermediate
  revisions.
- Existing polling-only consumers remain supported.
- In `sse` mode, the browser resynchronizes through `GET /api/state` without
  switching to polling or exposing partial or out-of-order snapshots to
  subscribers.
- Memory and active stream counts remain bounded under slow or disconnected
  clients.
- A sustained high-rate mutation source converges to its latest state without
  producing network events at the mutation rate.
