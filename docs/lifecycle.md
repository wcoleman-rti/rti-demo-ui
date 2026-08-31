# Lifecycle

Python `DemoUiApp` owns the local aiohttp server and component model.
Applications own DDS readers/writers and all background tasks. C++ retains its
blocking, thread-safe server and SDK timer ownership.

## Python Run and Stop

`await app.run()` binds the configured host and port, prints the URL only after
a successful bind, and waits for cancellation or `await app.stop()`. The
single-use lifecycle is `NEW -> STARTING -> RUNNING -> STOPPING -> STOPPED`.
Concurrent or subsequent `run()` calls raise `RuntimeError`; `stop()` is
idempotent in every state.

Calling `await app.stop()` before `run()` prevents binding. A failed bind
raises an error and never prints a false listening message. Cancellation runs
the same aiohttp cleanup path before `CancelledError` is propagated. Stop
during startup signals shutdown without allowing the server to enter its wait.
An app stopped from another event loop schedules shutdown on its owner loop.
Shutdown rejects new event subscriptions, wakes connected and idle SSE handlers,
closes their transports, and then completes normal aiohttp cleanup.

Component factory and mutation methods remain synchronous. Configuration before
startup is allowed; after startup, mutations and snapshots must run on the
owner event loop and thread. Foreign threads must use
`loop.call_soon_threadsafe`. Applications use `asyncio.TaskGroup` or retained
tasks for periodic work; the SDK has no Python timer API.

```python
async def main() -> None:
    app = DemoUiApp("Fleet Demo")
    try:
        async with asyncio.TaskGroup() as tasks:
            tasks.create_task(app.run())
            tasks.create_task(receive_samples())
    except asyncio.CancelledError:
        pass
    finally:
        await app.stop()
```

## Python Ctrl-C

`asyncio.run()` cancels the top-level coroutine on Ctrl-C. Runnable Python
examples catch `asyncio.CancelledError`, let their `TaskGroup` cancel and await
application work, and call `await app.stop()` in `finally`. They do not catch
`KeyboardInterrupt` inside the coroutine or create SDK-owned worker threads.
The SDK does not install process-global signal handlers.

## C++ Ctrl-C

The C++ examples block `SIGINT` before creating SDK, timer, DDS, or server
threads. An example-local controller waits with `sigtimedwait()` and calls
`app.stop()` from its control thread, outside a signal handler. Windows uses a
manual-reset event; its console callback handles only `CTRL_C_EVENT` and
`CTRL_BREAK_EVENT` and only calls `SetEvent()`.

`run()` remains on the main thread. `stop()` first prevents new subscriptions
and wakes blocked SSE providers before normal HTTP cleanup. After `run()`
returns, Connext workers are signaled and joined, then the controller is joined
and released. A terminal Ctrl-C is therefore a normal interactive exit path
with no application traceback.

## Browser Client Lifecycle

`createClient()` is stopped initially. `start()` and `stop()` are idempotent.
Polling mode owns at most one request and one retry/poll timer. SSE mode owns one
EventSource and uses the browser's reconnect behavior; recovery from an invalid
or gapped patch temporarily owns one `/api/state` fetch and may own one retry
timer. Calling `stop()` closes the source, clears timers, and invalidates the
connection generation so late events and fetch completions cannot notify
subscribers. Calling `start()` again retains the last immutable snapshot while
creating a new transport generation.
