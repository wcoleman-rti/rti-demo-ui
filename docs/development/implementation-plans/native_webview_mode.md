# Opt-In Native Webview Mode Plan

## Status

Technology spike proposed for `spike/native-webview`. Promote to
`feature/native-webview` only after the spike exit criteria are met.

This is a program plan with separate agent-session scopes. Phase 0 is one
spike scope and must update this document with the completed six-combination
support matrix before production implementation begins. Subsequent scopes are
the Python companion runner, C++ companion runner, each supported platform's
integration/CI job, and release documentation. Do not ask one implementation
agent to execute the spike and all production phases together.

## Objective

Provide an optional desktop mode that opens the existing web UI in an
application window backed by the operating system's embedded browser engine,
instead of requiring users to copy or open the local URL in an external
browser.

This is a native window host around the existing HTML/CSS/JavaScript frontend;
it is not a native-widget renderer. The same local HTTP, SSE, snapshot,
command, adapter, theme, and layout contracts must work in external and embedded
browsers.

## Selected Technologies

- Python: pywebview 6.2.1 in a companion Python distribution.
- C++: webview 0.12.0 (`webview.h`) in a companion CMake package and target.
- Linux: Ubuntu 22.04 or newer with GTK 3 and WebKitGTK 4.1.
- macOS: macOS 12 or newer with the system WKWebView.
- Windows: Windows 10 or newer with the Evergreen WebView2 Runtime present.

These pins and platform floors are normative for the spike and first release.
The spike may mark a backend/platform combination unsupported when it fails a
fixed exit gate, but it may not substitute another dependency, engine family,
or lower platform floor without revising this plan first.

## Product Boundary

The native mode provides:

- One resizable application window navigated to the app's bound loopback URL.
- Coordinated server readiness, window creation, window close, signal request,
  and process shutdown.
- The same built-in or application-owned frontend as browser mode.
- Actionable missing-dependency and unsupported-platform errors.
- Opt-in Python installation and C++ linking with no native GUI dependencies
  in core builds.

It does not provide a second rendering engine, native controls mirroring SDK
components, direct JavaScript-to-native model mutation, remote URL browsing,
multiple windows, tray integration, auto-update, application packaging, or a
replacement for the existing browser/server API. One application maps to one
native window permanently; multi-window hosting requires a separate future
product and API design.

## Spike Questions

Before locking implementation APIs, build minimal Python and C++ prototypes
that answer:

- Which thread must create and run each platform's webview event loop?
- Can the current Python asyncio owner loop run on a background thread without
  invalidating application mutation and DDS integration patterns?
- How does C++ move its currently blocking `DemoUiApp::run()` to a managed
  server thread while preserving stop/drain behavior?
- Can window closure be observed before the GUI event loop exits, and can
  server shutdown complete without calling GUI APIs from the wrong thread?
- How are Ctrl-C and normal process signals delivered while the GUI loop owns
  the main thread?
- Do exact HTTP `Origin` headers preserve the current command capability
  contract in all three engines?
- Do EventSource, WebGL/Three.js, canvas, local fonts, MapLibre workers, and
  dynamic adapter imports work without engine-specific changes?
- What system packages are required on Linux, and can CI run under a virtual
  display?
- Does Windows require a WebView2 runtime bootstrap or documented system
  prerequisite?
- What macOS framework/link/signing constraints affect downstream consumers?

The spike must produce a short report with a support matrix, prototype code,
dependency decision, lifecycle traces, and recommendation. Prototype code may
remain under an explicitly experimental tools/examples directory but must not
be exported as public API.

## Proposed Lifecycle Contract

The intended steady-state sequence is:

1. Validate loopback host and native dependency availability.
2. Start the state server on a managed background execution context.
3. Wait for public `ReadyInfo` and use its canonical URL.
4. Create and run the native window on the required GUI thread.
5. Navigate only after successful bind; startup failures never show an empty
   window or stale URL.
6. On window close or signal request, request shutdown on the appropriate
   server/GUI execution contexts.
7. Stop accepting work, close SSE streams, drain active commands, clean up the
   HTTP server, join the server context, destroy the webview, and return.

Window close and stop are idempotent and race-safe. A signal handler must only
set or signal an async-safe primitive; it must not destroy a webview, call
Python, lock a mutex, or stop the server directly from signal context.

If the server stops independently, native mode dispatches a window-close
request onto the GUI thread and surfaces the server failure. If the window
fails to initialize after bind, it stops and joins the server before raising or
returning an error.

## Python Direction

Package native support as the independently versioned
`rti-demo-ui-native` companion distribution:

```toml
[project]
dependencies = [
  "rti-demo-ui==<compatible-core-version>",
  "pywebview==6.2.1",
]
```

Do not add a core extra that imports pywebview. The companion distribution uses
platform markers for pywebview's native Python dependencies and documents the
required system packages. Its compatibility metadata pins the supported core
SDK major/minor line while allowing patch updates.

Prefer a separate synchronous entry point over changing the meaning of the
existing async `DemoUiApp.run()`:

```python
from rti_demo_ui_native import run_native

run_native(app, async_main=run_demo, width=1280, height=800, devtools=False)
```

`run_native` validates positive bounded dimensions, loopback hosting, and app
lifecycle state. It starts `app.run()` on a dedicated asyncio loop/thread,
waits for `app.wait_until_ready()`, creates the window on the main thread, and
marshals stop back to the owner loop. It must not add speculative
`start_background_server()` or `stop_sync()` methods to the core public API.

`async_main` is an optional
`Callable[[DemoUiApp], Awaitable[None]]`. The runner starts it on the app owner
loop after readiness and cancels and awaits it during every shutdown path. A
normal return requests window and server shutdown; an exception does the same
and is re-raised on the calling thread after cleanup. This is the only native
API for application-owned async tasks; applications do not cross threads to
schedule model mutations.

Missing pywebview, missing engine prerequisites, invalid options, and lifecycle
failures raise `NativeWebviewError`, a `RuntimeError` subclass, with an exact
installation or correction action. Reusable SDK code never calls `sys.exit()`.

## C++ Direction

Provide the independently versioned companion CMake package and target:

```cmake
target_link_libraries(my_demo PRIVATE
    rti_demo_ui::rti_demo_ui
  rti_demo_ui_native::native_webview)
```

```cpp
#include <rti_demo_ui_native/native_webview.hpp>

rti::demo::ui::native::run(app, {.width = 1280, .height = 800});
```

The native target contains webview 0.12.0 and platform link flags. Its package
requires a compatible core SDK major/minor line. The core target and headers
must compile without native GUI SDKs.

`run_native` owns a joinable server thread that calls the existing blocking
`app.run()`, waits through `wait_until_ready()`, then navigates the webview to
`ready_info()->url`. It requests `app.stop()` and joins the server on every
exit path. Do not add an unowned detached `start_non_blocking()` API.

`NativeWindowOptions` contains `width=1280`, `height=800`, and
`devtools=false`; the app title supplies the window title and the window is
resizable. `native::run()` returns `void` after normal close and throws
`NativeWebviewError`, derived from `std::runtime_error`, after completing
cleanup on failure. The C++ package keeps this repository's C++17 floor and
requires Visual Studio 2022 on Windows, Apple Clang supplied with Xcode 14 on
macOS, or GCC 11/Clang 14 on Ubuntu.

## Window and Navigation Policy

- Native mode requires the literal `127.0.0.1` or `::1` host so commands and
  origin checks retain their current security boundary.
- Initial navigation is the exact `ReadyInfo.url` plus `/`.
- Block or hand off top-level navigation outside that bound origin. Do not turn
  the app window into a general browser.
- Disable developer tools by default and expose them only through the explicit
  `devtools` runner option.
- Do not add a privileged JavaScript-native bridge in the first release.
- Keep remote subresource policy consistent with the SDK's local/offline asset
  model and adapter-specific rules.
- Create a unique temporary browser profile/cache directory for every run and
  remove it after clean or failed shutdown. Inability to prevent reuse of a
  persistent default profile fails the support gate for that host/platform
  combination.

## Packaging and Platform Support

The spike tests Linux, macOS, and Windows for Python and C++ independently and
assigns `supported` only when every exit criterion and real-engine CI check
passes. A combination that cannot run in hosted CI or fails a conformance gate
is `unsupported` for the first release, not experimental. Do not advertise
cross-platform parity based only on successful compilation.

For each supported combination, record:

- Exact package/library pin and source.
- Native engine and minimum OS/runtime version.
- Build and runtime system dependencies.
- License notices and redistribution obligations.
- Wheel/CMake package behavior when the native feature is disabled.
- Headless CI strategy and manual release smoke-test procedure.

Core Python installation and core C++ configuration must remain unchanged and
must not probe for GTK, WebKit, WebView2, or macOS frameworks.

## Cross-Platform Validation Strategy

Native webviews are testable in hosted CI without visual inspection, but CI
must distinguish functional engine conformance from human assessment of native
window behavior and rendering quality.

### Deterministic Automated Layers

1. Run lifecycle, threading, navigation-policy, and failure-path tests against
   a fake window host on every platform. These tests own most race and cleanup
   coverage and do not require a display server.
2. Run a real-engine smoke executable in an OS-specific job. It starts the
   server, opens a real webview, waits for a test page to report completion,
   closes the window programmatically, and asserts clean thread, event-loop,
   SSE, and port teardown under a watchdog timeout.
3. Serve a test-only same-origin conformance page that exercises snapshot,
   EventSource, commands, dynamic imports, theme/layout changes, keyboard
   focus, resize observation, Canvas 2D, and WebGL. It reports structured
   results to a test-only loopback endpoint that is absent from production
   builds. Canvas and WebGL checks read known rendered pixels so a created but
   blank surface cannot pass.
4. Capture a window or webview image where the selected host API supports it
   reliably. Use screenshots for diagnostics and a few stable bounds/pixel
   assertions, not broad golden-image comparison across different operating
   system engines and font rasterizers.

During the spike, the smoke job fails on missing engine/runtime prerequisites
and no target combination may be conditionally skipped. After classification,
release CI requires every combination marked supported; unsupported
combinations are not advertised or included in release jobs.

### Hosted Runner Setup

- Linux: install the pinned WebKitGTK/runtime packages, run GTK under Xvfb and
  a D-Bus session, and use Mesa software rendering when no GPU is available.
  Record whether WebGL passes under software rendering; do not infer hardware
  GPU support from that result.
- Windows: run against the Evergreen WebView2 Runtime on the hosted Windows
  desktop session. Detect and record the runtime version before testing. The
  runtime is a documented prerequisite and is not bundled or bootstrapped by
  the SDK; a missing runtime is a test failure rather than a browser fallback.
- macOS: create WKWebView on the main thread in a hosted macOS job and use the
  runner's WindowServer session. Avoid making screen-capture permission a
  prerequisite; use the in-page conformance report and pixel readback as the
  primary signal.

Python and C++ runners execute the same conformance page and result schema so
backend differences are visible. Jobs retain engine versions, lifecycle logs,
structured conformance results, and available screenshots as artifacts. Run
at least one job per supported OS/backend combination; add architecture jobs
when released artifacts support more than the hosted runner's default
architecture.

### Manual Release Validation

Headless automation cannot establish native focus feel, DPI scaling, window
chrome integration, accessibility, hardware-accelerated WebGL behavior, or
quality across real display configurations. Before release, execute a short
versioned checklist on physical or interactive virtual machines for every
supported platform: launch, resize, keyboard traversal, command interaction,
multi-monitor/DPI behavior, close, Ctrl-C, external-link handling, and one
representative Canvas/WebGL/MapLibre demo. Store the result with the release
artifacts and treat failures as platform-support decisions, not informal
exceptions.

## Security and Compatibility

The embedded engine receives the same trusted local application content as an
external browser. Native hosting does not weaken command origin/capability
checks or grant JavaScript direct native access. The server still binds before
announcing readiness and uses a process-selected port by default.

Browser mode remains the default and supported fallback. Existing `run()`,
`stop()`, and `ReadyInfo` APIs retain their semantics. Native dependencies are
never imported or linked unless the application opts in.

## Implementation Phases

### Phase 0: Technology Spike

- Build minimal Python and C++ hosts for each candidate platform available to
  CI/developers.
- Implement the shared conformance page/result schema and fake-host lifecycle
  suite before relying on screenshots.
- Exercise readiness, command origin, SSE, dynamic imports, WebGL, close, and
  signal paths.
- Publish the support matrix and verify the fixed pins and platform gates.
- Validate the specified runner APIs against real Python asyncio and C++ demo
  lifecycle patterns. A mismatch blocks promotion and requires this plan to be
  revised before implementation; the spike does not redesign the API silently.

### Phase 1: Packaging and Runner Core

- Add optional Python packaging and the native module with lazy dependency
  import.
- Add the C++ native target, generated dependency integration, and platform
  link configuration.
- Implement server-thread ownership and all startup/cleanup guards.

### Phase 2: Platform Integration

- Implement navigation restriction, title/size/resizing, close dispatch, and
  signal coordination for each supported platform.
- Add examples using the same application model in browser and native modes.
- Verify built-in, custom, and adapter-provided frontends.

### Phase 3: Documentation and Release

- Document installation, system prerequisites, API usage, browser fallback,
  troubleshooting, and platform tier.
- Update lifecycle, architecture, third-party notices, and release packaging.
- Perform automated and manual release smoke tests.

## Verification

- Core isolation tests without pywebview, webview headers, or platform GUI
  packages.
- Missing-dependency and unsupported-platform tests with actionable errors.
- Startup failure before/after bind, invalid dimensions/host, and repeated-run
  state tests.
- Window-close, programmatic stop, Ctrl-C, server failure, simultaneous close,
  active command, idle SSE, and active SSE teardown tests.
- Assertions that the bound port is released and all managed threads/event
  loops are joined.
- Browser conformance inside the embedded engine: snapshot/SSE, commands,
  themes/layouts, adapter dynamic import, canvas/WebGL, keyboard focus, and
  narrow resizing.
- Linux CI under Xvfb/D-Bus with WebKitGTK and software rendering;
  Windows CI with a recorded WebView2 runtime; and macOS CI with WKWebView on
  the main thread.
- Test-page structured results, known-pixel Canvas/WebGL assertions,
  watchdog-bounded programmatic close, and retained diagnostic artifacts on
  every advertised platform.
- Documented manual release checks for focus, accessibility, DPI/multi-monitor
  behavior, hardware GPU rendering, native window integration, and visual
  quality where automation is insufficient.

Run the applicable core repository checks in addition to native target tests.

## Resolved Decisions

- Pin pywebview 6.2.1 and webview 0.12.0 in separate Python and CMake companion
  artifacts sourced from this repository; core packages contain no native GUI
  dependency or probe.
- Test all six Python/C++ and Linux/macOS/Windows combinations. Support requires
  all fixed gates to pass on Ubuntu 22.04/WebKitGTK 4.1, Windows 10/Evergreen
  WebView2, or macOS 12/WKWebView; otherwise that combination is unsupported.
- Python application work enters through one structured `async_main` callback
  on the owner loop.
- Developer tools require an explicit option and every run uses an ephemeral
  profile removed at shutdown.
- One application has exactly one native window. Multi-window hosting is
  outside this API permanently.

## Spike Exit and Acceptance Criteria

The spike may advance to implementation only when:

- All six Python/C++ and Linux/macOS/Windows combinations have either passed
  the full startup/render/close cycle without detached work or leaked ports,
  or have a recorded unsupported classification tied to a failed fixed gate.
- At least one Python and one C++ combination is supported; otherwise native
  mode does not advance to production implementation.
- Main-thread and owner-loop rules are documented and represented in the
  proposed APIs.
- Command Origin, SSE, adapter loading, and WebGL behavior are verified in the
  selected engines.
- Optional packaging leaves core installation and linking unaffected.
- Every supported combination has a repeatable build, runtime prerequisites,
  a required real-engine CI smoke test, and a manual release checklist.

The implementation is accepted when supported platforms satisfy those checks
with production runner code and external browser mode remains behaviorally
unchanged.
