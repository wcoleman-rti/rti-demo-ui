# Lifecycle

`DemoUiApp` owns the local HTTP server, the component model, and SDK timers.
Application code owns DDS workers and other application threads.

## Run and Stop

`run()` binds the configured host and port, prints the URL only after a
successful bind, and blocks in the HTTP loop. `stop()` is idempotent and is the
supported programmatic shutdown API. It marks the model as stopping, wakes the
server, cancels and joins SDK timers, and lets `run()` return. Call it from a
non-signal control path.

Calling `stop()` before or while `run()` starts prevents the server from
entering its listening loop. A failed bind raises an error containing the host
and port and never prints a false listening message. Python enables immediate
address reuse for its private HTTP server subclass.

Application workers must be joined after `run()` returns and before the app is
destroyed. Workers must not retain component pointers beyond app lifetime.

## Python Ctrl-C

Runnable Python examples catch `KeyboardInterrupt`, stop application workers,
and call `app.stop()` in `finally`:

```python
try:
    app.run()
except KeyboardInterrupt:
    pass
finally:
    app.stop()
```

The Connext example joins its writer and reader threads before final app
cleanup. The SDK does not install process-global signal handlers.

## C++ Ctrl-C

The C++ examples block `SIGINT` before creating SDK, timer, DDS, or server
threads. An example-local controller waits with `sigtimedwait()` and calls
`app.stop()` from its control thread, outside a signal handler. Windows uses a
manual-reset event; its console callback handles only `CTRL_C_EVENT` and
`CTRL_BREAK_EVENT` and only calls `SetEvent()`.

`run()` remains on the main thread. After it returns, Connext workers are
signaled and joined, then the controller is joined and released. A terminal
Ctrl-C is therefore a normal interactive exit path with no application traceback.
