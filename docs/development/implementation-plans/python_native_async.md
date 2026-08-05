# Python Native Async Runtime Plan

## Objective

Replace the Python SDK's `ThreadingHTTPServer` runtime with a native asyncio
runtime. Python applications must compose naturally with asyncio coroutines
without server, request-handler, or SDK-timer threads.

This is a pre-release breaking change. The Python lifecycle intentionally
follows Python async conventions while the C++ SDK retains its blocking,
thread-safe lifecycle. The shared compatibility boundary remains the component
model, snapshot JSON schema, HTTP route/response contract, SDK assets, and
browser behavior.

## Decisions

### Runtime and Supported Python

- Raise the Python minimum version from 3.10 to 3.11.
- Add `aiohttp>=3.10,<4` as a direct runtime dependency.
- Do not make server selection an application concern.
- Apply compatible dependency updates, including security fixes.
- Keep those updates within the selected range.
- Validate a major-version update before changing the bound.
- Add `pytest-asyncio>=0.24,<1` to the development dependencies.
- Configure pytest with `asyncio_mode = "strict"`.
- Use `aiohttp.web.AppRunner` and `aiohttp.web.TCPSite` directly. Do not retain
  `ThreadingHTTPServer`, `BaseHTTPRequestHandler`, or a second Python server
  implementation.
- Keep one local process and the current polling browser transport. This change
  does not introduce WebSockets, SSE, browser command routes, authentication,
  TLS, or public deployment support.

### Public Python API

The Python lifecycle becomes fully awaitable:

```python
app = DemoUiApp("Fleet Demo")
# Configure cards and scenes before serving.
await app.run()
```

`run()` binds the configured socket, prints the actual bound URL only after a
successful bind, and waits until cancellation or `await app.stop()` causes
shutdown. It performs cleanup before returning or propagating cancellation.

```python
await app.stop()
```

`stop()` is idempotent. It marks the model stopped, stops accepting new
requests, waits for in-flight request handlers under aiohttp's normal server
cleanup, and releases server resources. Calling it before `run()` makes a
subsequent `run()` return without binding.

An app instance is single-use. Its private lifecycle state is
`NEW -> STARTING -> RUNNING -> STOPPING -> STOPPED`. `run()` may be called
only once; a concurrent or subsequent call raises `RuntimeError`. `stop()` is
idempotent in every state. `run()` is the only operation that performs server
cleanup; a `stop()` caller waits on a shared completion signal when cleanup is
in progress. When called from a different event loop, `stop()` schedules its
owner-loop shutdown operation with `asyncio.run_coroutine_threadsafe` and
awaits the returned future; it never mutates an asyncio synchronization object
from a foreign thread.

`run()` maintains a private post-bind readiness signal for test fixtures. It
is set only after the listening socket is available and cleared during cleanup.
Tests that host the app on a dedicated loop wait for this signal through
`asyncio.run_coroutine_threadsafe`; they do not use `time.sleep()` to guess
when the server has started.

Remove these Python-only threaded APIs with no aliases or deprecation layer:

- `DemoUiApp.run_async()`
- `DemoUiApp.stop_async()`
- synchronous `DemoUiApp.run()` and `DemoUiApp.stop()`
- `DemoUiApp.add_timer()`
- `TimerHandle`

Do not add an SDK-owned replacement for `add_timer()`. Application coroutines
own periodic work through `asyncio.TaskGroup` or explicitly retained tasks.
This makes application task lifetime visible in application code and avoids an
SDK callback execution policy.

### Model Ownership and Mutation

Component factory and mutation methods remain synchronous:

```python
scene.update_entity("vehicle-1", x=12.0, y=-4.0)
```

They perform short, in-memory validation and mutation only; making every model
call awaitable would add ceremony without awaiting I/O. Once `run()` begins,
the model and all aiohttp handlers are owned by its event loop, so `_Model`
uses no `threading.RLock`.

The SDK does not support direct component mutation from foreign threads. An
application that bridges a blocking integration must schedule its own work on
the loop with `loop.call_soon_threadsafe`; it must not call component methods
from that worker. When `run()` begins, record the owner event loop and thread.
Each component mutation and snapshot access verifies that it is called on the
owner thread after startup, raising a clear `RuntimeError` that directs foreign
callers to `loop.call_soon_threadsafe`. Document this rule prominently in the
Python API and lifecycle documentation.

The synchronous configuration phase before `run()` is allowed. Once stopped,
existing mutation methods continue to raise `RuntimeError` as they do now.

### Lifecycle and Cancellation

`DemoUiApp` owns only the aiohttp server lifecycle. Applications own DDS
readers/writers and all background tasks.

`run()` must:

1. Capture the active event loop and reject attempts to run the same app on a
   different loop.
2. Construct and register the aiohttp routes, bind the configured host/port,
   and report the real port returned by the bound socket.
3. Wait on a private shutdown event.
4. On `asyncio.CancelledError`, run the same shutdown path under cancellation
   protection, then re-raise cancellation.
5. In all exit paths, call aiohttp cleanup exactly once and clear runtime-only
   state.

`stop()` must be safe while startup is in progress. It must set the shutdown
signal without awaiting a lock held by startup, then let `run()` own final
server cleanup. A stop during `STARTING` is checked immediately after binding;
`run()` cleans up without entering its serving wait. It must not install global
signal handlers.

Examples catch `asyncio.CancelledError` in their top-level coroutine, cancel
and await application-owned tasks in `finally`, and let `asyncio.run()` return
normally on Ctrl-C. They must not catch `KeyboardInterrupt` inside the
coroutine or create thread stop events for coroutine work.

The SDK does not own application tasks. Applications use `asyncio.TaskGroup`
to give the UI server and their own tasks one structured-concurrency scope:

```python
async def main() -> None:
   app = DemoUiApp("Fleet Demo")
   # Configure cards and scenes before starting the tasks.

   try:
      async with asyncio.TaskGroup() as tasks:
         tasks.create_task(app.run())
         tasks.create_task(receive_samples())
         tasks.create_task(publish_samples())
   except asyncio.CancelledError:
      pass
   finally:
      await app.stop()


asyncio.run(main())
```

The task group owns application task cancellation and failure propagation.
`DemoUiApp.run()` owns only server cleanup when it is stopped or cancelled.

### HTTP and Browser Contract

Preserve exactly the Python behavior documented in `docs/architecture.md`:

- Built-in and static-root route precedence and reserved `/api/` and `/sdk/`
  prefixes.
- Current response status, content type, cache policy, content length, and
  `X-Content-Type-Options: nosniff` headers.
- JSON error payloads for API failures and plain static-root 404 responses.
- Static-root URL decoding, traversal/root-escape rejection, regular-file
  checks, and explicit MIME mapping.
- Snapshot schema, revision semantics, finite-number serialization, and
  canonical packaged assets.

Do not use `aiohttp`'s directory/static-file helper because it would split
security and MIME behavior from the existing explicit resolver. Refactor the
current resolver into backend-neutral helpers, then have aiohttp handlers turn
its result into responses. Keep packaged SDK assets as byte responses loaded
at construction. Once the resolver has authorized an application static-root
file, return `web.FileResponse` with explicit contract headers so aiohttp can
stream it without blocking the event loop.

### C++ Scope

Do not change the C++ public API, server implementation, or threading model.
C++ remains the blocking/thread-safe implementation. Keep cross-language
contract tests and browser tests as the parity gate; lifecycle signatures need
not match between languages.

## Implementation Sequence

### 1. Freeze the breaking Python contract

1. Update `pyproject.toml` to require Python 3.11+, add
   `aiohttp>=3.10,<4`, add `pytest-asyncio>=0.24,<1` to the development
   dependencies, configure pytest strict asyncio mode, change Ruff's
   `target-version` to `py311`, and update the package description to describe
   the asyncio/aiohttp backend.
   Update both Python versions in `.github/workflows/ci.yml` to `3.11` and the
   Python version requirement in `docs/development/contributing.md`.
2. Update `docs/architecture.md`, `docs/lifecycle.md`, `docs/api/python.md`,
   `README.md`, and `python/README.md` to define the async Python lifecycle,
   event-loop ownership rule, foreign-thread handoff rule, and C++/Python
   parity boundary. Split `docs/architecture.md` section 8 and
   `docs/lifecycle.md`'s run/stop and Ctrl-C material into distinct Python and
   C++ subsections. The Python sections document the lifecycle states,
   TaskGroup ownership, and cancellation shutdown; retain the C++ lifecycle
   text unchanged except for cross-references. Replace the architecture
   acceptance criterion that requires a standard-library-only Python runtime
   with the explicit asyncio/aiohttp and C++ dependency policy. In `README.md`,
   replace the opening and repository-layout claims that describe Python 3.10+
   `ThreadingHTTPServer`/standard-library-only support with Python 3.11+
   asyncio/aiohttp support.
3. Remove all public documentation of Python `add_timer`, `TimerHandle`,
   synchronous `run`/`stop`, and the interim async adapters. Keep C++ timer
   documentation unchanged.
4. Add contract tests for the final Python lifecycle before deleting the old
   backend: successful bind, failed bind, stop-before-run, explicit stop,
   cancellation, immediate restart, and shutdown with an in-flight request.

### 2. Refactor backend-independent Python behavior

1. Extract asset/static response metadata and static-root resolution from
   `BaseHTTPRequestHandler` methods into private helpers with no HTTP-server
   dependency.
2. Preserve `_Model` validation, IDs, insertion order, snapshot shape, and
   revision behavior while removing its `threading.RLock`. Add owner-loop and
   owner-thread validation to mutations and snapshots after startup.
   In `python/rti_demo_ui/components.py`, replace every `with self._model.lock`
   block in `Card.add_scene_2d` and the five `Scene2DViewport` mutations with
   `_Model.check_owner()` followed by `_Model.ensure_running()` and the current
   mutation/revision sequence. Make the same replacement in
   `DemoUiApp.add_card`. `check_owner()` is a no-op before `run()` starts and
   raises the documented owner-loop error afterward.
3. Remove `TimerHandle`, `add_timer`, timer tracking, and all thread/event
   imports. Remove `TimerHandle` from `python/rti_demo_ui/__init__.py` and
   replace the timer and interim `run_async`/`stop_async` coverage in
   `tests/py/test_model_and_http.py` with the final async lifecycle tests.
   Update simple examples to create and clean up application-owned animation
   coroutines.
4. Add direct tests proving every static resolver and snapshot invariant stays
   unchanged before replacing the HTTP transport.

### 3. Implement the aiohttp server lifecycle

1. Build a private `web.Application` and register explicit handlers for
   built-in assets, `/api/health`, `/api/state`, static-root files, 404s, and
   405s. Preserve reserved-prefix precedence.
2. Bind with `AppRunner` and `TCPSite`; extract the actual socket port before
   printing the listening URL. Implement the `NEW -> STARTING -> RUNNING ->
   STOPPING -> STOPPED` state transitions, rejecting a second `run()` and
   ensuring a startup-time `stop()` cannot enter the serving wait. Translate a
   bind failure only if necessary to preserve clear host/port error information.
3. Implement the private shutdown event and cancellation-safe cleanup path.
   Ensure `stop()` during startup cannot allow the app to enter its serving
   wait after shutdown has been requested.
4. Use explicit byte `web.Response` objects and headers for API and SDK asset
   routes. Use `web.FileResponse` only after the explicit static resolver has
   authorized an application-owned file. Do not rely on implicit static
   serving or default error responses.
5. Remove `ThreadingHTTPServer`, `_RequestHandler`,
   `_ReusableThreadingHTTPServer`, `run_async`, and `stop_async` in the same
   change. The final Python public API has only async `run` and `stop`.

### 4. Convert examples to structured async ownership

1. Make `examples/py/simple.py` an async program. Its movement loop is an
   application task; cancellation stops and awaits it before app cleanup.
2. Keep `examples/py/connext.py` fully coroutine-based with `rti.asyncio`,
   `reader.take_async()`, and `asyncio.sleep()`. Its shutdown path cancels and
   awaits publisher/reader work before leaving `main()`.
3. Make `examples/py/gallery.py` await the native `app.run()` lifecycle.
4. Ensure Ctrl-C exits each Python example without a traceback and without a
   listener left bound.

### 5. Update and broaden validation

1. Rewrite Python HTTP tests with `pytest-asyncio` in strict mode. Exercise
   real localhost lifecycle and port behavior, using aiohttp test utilities
   only where direct route testing is simpler. Preserve the existing
   cross-language route vectors and browser assertions.
2. Add cancellation tests for `run()` while it is waiting, and verify cleanup
   completes before `CancelledError` reaches the caller.
3. Add a slow/in-flight handler test that calls `await app.stop()` and verifies
   aiohttp cleanup waits safely without deadlock.
4. Add a subprocess Ctrl-C test where supported. Otherwise document a manual
   acceptance check for each runnable Python example.
5. Run unchanged C++ unit, HTTP-contract, and browser tests to prove the shared
   contract did not drift.

### 6. Migrate synchronous browser/static test fixtures

1. Replace the `threading.Thread(target=app.run)` and `time.sleep()` fixtures
   in `tests/py/test_static_root.py` and `tests/browser/test_browser.py`.
   Preserve their synchronous request and Playwright test bodies where useful:
   each fixture creates a dedicated background thread with
   `asyncio.new_event_loop()`, runs `app.run()` with
   `loop.run_until_complete()`, and waits deterministically for the app's
   post-bind readiness signal.
2. Teardown schedules `app.stop()` on that owner loop with
   `asyncio.run_coroutine_threadsafe(app.stop(), loop).result()`, waits for
   `app.run()` and the thread to complete, then closes the test loop. Do not
   call `app.stop()` directly from the fixture's main thread.
3. Keep all new async-first lifecycle tests on one pytest-managed loop. The
   background-loop fixture exists only for synchronous HTTP-client and
   Playwright tests that cannot await the app lifecycle directly.

## Focused Validation

Run after each implementation slice:

```bash
python -m pytest tests/py -q
python -m pytest tests/browser -q
cmake --build build && ctest --test-dir build --output-on-failure
```

Add or retain checks for:

- `await app.run()` binding only once and printing only after success.
- A competing listener producing a visible bind failure without a listening
  message.
- `await app.stop()` before `run()` preventing a listener.
- Immediate reuse of a just-stopped explicit test port.
- Cancellation and explicit stop releasing the server and allowing a new app
  to bind the same port.
- Concurrent or subsequent `run()` calls fail.
- Repeated `stop()` calls share completed cleanup.
- A startup-time stop request does not enter the serving wait.
- Foreign-thread mutations after startup raise an owner-loop error.
- Post-start snapshot access from a foreign thread raises an owner-loop error.
- Static-root and browser fixtures wait for the post-bind readiness signal.
- Those fixtures stop through the owner loop without timing sleeps.
- API, SDK asset, static-root, traversal, MIME, cache, and error behavior
  matching the shared C++ contract vectors.
- `asyncio` Python examples exiting cleanly on Ctrl-C.
- Wheel and editable-install packaging still serving canonical assets.

## Deferred Work

- WebSocket, SSE, deltas, and browser-to-server commands.
- SDK-managed background task or periodic timer APIs.
- Foreign-thread mutation convenience APIs.
- A callback/endpoint extension API for application-defined JSON routes.
- A second Python HTTP runtime or user-selected server backend.
- C++ lifecycle changes to imitate Python asyncio.

## Completion Criteria

- Python has one native asyncio server implementation and no threaded server,
  request handlers, SDK timers, lifecycle adapters, or compatibility aliases.
- Python examples compose directly with asyncio and exit cleanly on cancellation/Ctrl-C.
- Model and HTTP/browser contracts remain compatible with C++ where they are
  shared.
- All Python, browser, and C++ quality gates pass with the new dependency and
  supported Python version.
- Documentation clearly states the intentional Python/C++ lifecycle divergence
  and the event-loop ownership rule.
