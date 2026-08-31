# SDK Next-Wave Implementation Roadmap

## Status

Proposed coordination plan for four independently reviewed implementation
plans. This document owns sequencing and integration boundaries; each feature
plan owns its public contracts and implementation details.

## Objective

Coordinate the next transport, rendering, desktop-hosting, and presentation
capabilities without creating conflicting changes to the shared Python, C++,
and browser runtime surfaces.

The four efforts are:

- Server-Sent Events (SSE) state streaming.
- Opt-in UI renderer adapters with pinned browser libraries.
- An opt-in native desktop webview host.
- Governed dark/light themes and API-driven dashboard layouts.

## Plans

- `sse_event_streaming.md`
- `ui_renderer_adapters_opt_in.md`
- `native_webview_mode.md`
- `theming_and_layouts.md`

## Dependency and Delivery Order

SSE and theming/layouts may be implemented in parallel because their primary
ownership differs: SSE owns backend mutation notification and browser
transport, while theming/layouts owns snapshot presentation metadata and the
built-in renderer's card container.

The adapter core begins after the theming/layout contract is stable and after
the SSE client changes have established the supported transport-facing client
API. Individual library adapters follow the adapter core rather than landing as
independent runtime conventions.

Native webview starts as a technology spike in parallel with SSE and
theming/layouts. Full implementation starts only after the spike resolves GUI
main-thread ownership, dependency packaging, platform support, and coordinated
window/server shutdown. It consumes the existing HTTP client and whichever
transport contract SSE establishes; it does not create another frontend
protocol.

The parallel native spike uses its same-origin conformance fixture to exercise
the required browser primitives before dependent SDK features merge. Passing
that fixture does not satisfy cross-feature integration. Native release remains
blocked on Gate 3 after SSE, theming/layouts, adapter core, and one dynamic
adapter are merged.

```text
SSE streaming -----------+--> UI renderer adapter core --> library adapters
                         |
Themes and layouts ------+

Native webview spike --------> native webview implementation
SSE streaming ---------------^
```

## Git and Worktree Strategy

Keep the plans together on one short-lived planning branch such as
`plan/sdk-next-wave` so their terminology and dependencies can be reviewed as
one change.

After plan approval, use separate worktrees for concurrently active efforts:

```text
feature/sse-streaming
feature/theme-layout
feature/ui-renderer-adapter-core
spike/native-webview
```

Create `feature/ui-renderer-adapter-core` from the integration base after the SSE
client contract and theme/layout schema are stable. Create individual adapter
branches, such as `feature/adapter-uplot`, from the merged adapter core. Promote
the webview spike to `feature/native-webview` only when its acceptance report
selects supported technologies and platforms.

Do not implement all four directly against stale copies of the same base.
SSE and native hosting both affect application lifecycle, while adapters and
layouts both affect `assets/runtime.js`; dependent branches must rebase or be
recreated from the updated integration base before implementation begins.

## Shared Engineering Constraints

- Preserve Python and C++ behavioral parity for public model and HTTP
  contracts.
- Keep operation local and offline; runtime assets must not depend on a CDN.
- Keep `GET /api/state` as the canonical full-snapshot resynchronization path.
- Preserve application-wide monotonic revisions and stable component/card IDs.
- Serve SDK assets under the reserved `/sdk/` prefix.
- Pin, reproducibly bundle, and document third-party browser dependencies and
  licenses.
- Treat custom frontends as supported consumers of `/sdk/client.js`; built-in
  renderer behavior must not be required to use the transport.
- Define startup, cancellation, disconnection, and shutdown behavior before
  implementing long-lived streams or desktop hosts.
- Add shared fixtures before backend implementations when a language-neutral
  schema or wire contract changes.

## Integration Gates

### Gate 1: Contract Review

Each feature plan must have its product boundary, exact API/schema examples,
failure behavior, compatibility policy, and observable acceptance criteria
approved before implementation.

### Gate 2: Focused Feature Validation

Each feature branch must pass its focused Python, C++, and browser tests. A
platform-specific webview branch may use explicit platform test jobs, but must
also test missing-dependency behavior without native packages installed.

### Gate 3: Cross-Feature Integration

Before adapter work begins, verify that the built-in runtime can apply theme
and layout metadata while receiving state through both supported client
transports. Before native webview release, verify the merged SSE,
theme/layout, adapter-manifest, dynamic-import, Canvas, and WebGL paths inside
every supported backend/platform host combination.

### Gate 4: Full Repository Validation

Run the documented CMake/CTest, Python, browser, generated-asset, and
pre-commit checks from `docs/development/contributing.md` before merging each
release milestone.

## Implementation Session Handoff

Give an implementation agent exactly one feature plan or one execution unit
named by a program plan. Include the integration-base commit, which dependency
gates have passed, and any relevant existing worktree changes. The agent reads
that scope, `docs/development/contributing.md`, and nearby owning code/tests; it
does not need the other program plans unless the scoped document links to a
specific cross-feature contract.

The session owns its scope through implementation, focused validation,
documentation updates, and the stated branch exit gate. Later phases and
sibling adapters are out of scope. Any required departure from a resolved
decision stops implementation until the planning document is revised.

## Review Workflow

Review one feature plan at a time in dependency order:

1. SSE event streaming.
2. Theming and layouts.
3. UI renderer adapter core and first adapters.
4. Native webview spike and implementation.

Before each implementation branch begins, perform a read-only review of its
resolved decisions, concurrency, compatibility, security boundaries,
packaging, and corresponding tests for every acceptance criterion.
Implementation must follow the recorded direction; changing a decision
requires an explicit planning-document revision before the code change.

## Completion Criteria

This roadmap is complete when all four plans have been reviewed, their
dependencies are reflected in branch bases, feature-level validation passes,
and the durable resulting contracts are folded into `docs/architecture.md`,
the API guides, lifecycle documentation, custom-frontend documentation, and
third-party notices.
