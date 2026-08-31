# Opt-In Native Webview Mode Plan

## Status

Technology spike completed on 2026-08-31. Do not promote to
`feature/native-webview`: the fixed SSE and C++ lifecycle gates failed, and no
C++ combination completed a real-engine cycle.

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

## Phase 0 Spike Result (2026-08-31)

### Recommendation

**Do not begin Phase 1.** The spike does not meet the acceptance criteria. The
current baseline has no `/api/events` SSE route, so the shared conformance page
correctly fails SSE in the real Linux Python engine. The C++ lifecycle also has
a readiness/stop race: `ReadyInfo` is published before `listen_after_bind()`,
allowing `stop()` to run before the blocking listen begins. In 100 immediate
readiness/stop iterations, 63 exceeded the two-second watchdog. This API
mismatch must be resolved in the applicable lifecycle/transport plan and this
plan revalidated rather than redesigned silently in Phase 1.

An isolated runner workaround was also validated: after `ReadyInfo`, polling
the public `/api/health` route until it returns 200 produced 100 clean stops in
100 iterations, while the raw `ReadyInfo` path still timed out in 19 of 25
additional iterations. The public runner signature need not change, but the
proposed lifecycle sequence must explicitly require health-confirmed readiness
before window creation.

The selected dependency pins remain appropriate spike candidates:
`pywebview==6.2.1` (BSD-3-Clause) and webview commit
`3ab4b5d722438fc8a13e6ca830c5e2372d19a01d`, tag `0.12.0` (MIT).
No alternative engine, dependency, production API, or lower platform floor was
selected. The prototype and its Python dependency declaration are isolated in
`tools/native_webview_spike/`; core Python and C++ dependency manifests are
unchanged.

### Six-Combination Support Matrix

`Unsupported` is a first-release classification from this spike, not a claim
that the underlying operating-system engine can never be supported.

| Backend | Platform gate | Classification | Reproducible evidence tied to a fixed gate |
| --- | --- | --- | --- |
| Python 3.11+ / pywebview 6.2.1 | Ubuntu 22.04+ / GTK 3 / WebKitGTK 4.1 | Unsupported | A real `gtkwebkit2` cycle ran on Ubuntu 26.04.1 with GTK 3.24.52 and WebKitGTK 2.52.3. Snapshot, exact command Origin, application and runtime3d dynamic imports, module worker, theme asset, Canvas pixel, WebGL pixel, focus, resize, close, signal, ephemeral context/profile cleanup, port teardown, and owner-loop join passed. The strict result schema reported SSE as its only failure because `/api/events` is absent. |
| C++17 / webview 0.12.0 | Ubuntu 22.04+ / GTK 3 / WebKitGTK 4.1 | Unsupported | The isolated host configure failed its required `webkit2gtk-4.1` `pkg-config` development-package check. Raw `ReadyInfo` retains the stop race; public health-confirmed readiness passed 100/100 lifecycle iterations. Pinned webview creates `webkit_web_view_new()` on the default context and exposes no public ephemeral-profile option. The unchanged server also lacks SSE. |
| Python 3.11+ / pywebview 6.2.1 | macOS 12+ / WKWebView | Unsupported | No matching macOS host or real-engine job was available. Pinned pywebview uses `defaultDataStore()` and clears shared website data instead of creating a unique per-run store, which fails the fixed profile gate. The unchanged server lacks SSE. |
| C++17 / webview 0.12.0 | macOS 12+ / WKWebView | Unsupported | No matching macOS host or real-engine job was available. Pinned webview constructs a default `WKWebViewConfiguration` with no public data-store option, which fails the fixed profile gate. The unchanged server lacks SSE. |
| Python 3.11+ / pywebview 6.2.1 | Windows 10+ / Evergreen WebView2 | Unsupported | No matching Windows host or real-engine job was available, so neither runtime-version detection nor the non-skippable startup/render/close gate was executed. The unchanged server lacks SSE. |
| C++17 / webview 0.12.0 | Windows 10+ / Evergreen WebView2 | Unsupported | No matching Windows host or real-engine job was available. Pinned webview hard-codes `%APPDATA%/<executable>` as the WebView2 user-data folder and exposes no public override, which fails the fixed profile gate. The unchanged server lacks SSE. |

At least one Python and one C++ combination must be supported to advance. This
matrix has zero supported combinations, so that criterion fails.

### Prototype and Lifecycle Evidence

The experimental prototype contains:

- one same-origin conformance page and JSON result schema shared by both hosts;
- a Python host that runs the app owner asyncio loop on a background thread and
  pywebview's GTK loop on the main thread;
- a C++ webview host source pinned to webview 0.12.0 and a GUI-independent C++
  server-thread lifecycle executable; and
- a Python fake-host runner prototype and strict lifecycle suite.

The fake-host suite has ten passing tests covering background owner-loop
operation, main-thread window creation/run, owner-loop mutation, bind failure
before readiness, window initialization failure after bind, window close,
server-driven close, `async_main` normal return, exception propagation after
cleanup, cancellation and await on close, simultaneous close/return,
owner-thread join, and port release.

The Python real-engine programmatic-close trace reported
`renderer=gtkwebkit2`, different GUI/owner thread IDs, `close_observed=true`,
`server_joined=true`, `port_released=true`, and `profile_removed=true`. Known
pixels were Canvas `17,34,51,255` and WebGL `255,0,0,255`. The signal trace also
reported `signal_observed=true` and clean teardown. The signal handler only set
a `threading.Event`; cleanup ran outside signal context.

The page reported passes for snapshot schema 2, command capability and exact
browser Origin (the report command was accepted), dynamic adapter import,
runtime3d/Three.js bundle import, a same-origin module worker, applied theme
CSS, Canvas, WebGL, keyboard focus, and a 1280x800 resize observation. The
captured JSON passes the checked-in strict result schema and reports SSE as its
only failed check. Browser command acceptance is the structured test-only
report path; neither prototype adds a production JavaScript-native bridge.

webview 0.12.0 exposes no public cross-platform per-run profile/cache option.
On Linux it creates a webview on WebKitGTK's default context, on macOS it uses
a default `WKWebViewConfiguration`, and on Windows it hard-codes an application
data directory. Its native-handle access does not allow replacing the browser
data store after creation. No private API was selected. Python's Linux backend
uses WebKitGTK's public ephemeral context in `private_mode=True`; the per-run
directory supplied by the prototype was also removed after both close paths.
Pinned pywebview's macOS backend instead clears `defaultDataStore()`, so it
does not satisfy the unique per-run profile requirement.

### Exit-Criterion Evaluation

| Exit criterion | Result |
| --- | --- |
| Six combinations complete a leak-free real cycle or receive a failed-gate classification | Pass: all six are classified above; unavailable platforms were not conditionally skipped or claimed supported. |
| At least one Python and one C++ combination supported | **Fail:** zero combinations are supported. |
| Main-thread and owner-loop rules documented and represented | Pass for prototype shape: both hosts put the GUI loop on the main thread and server ownership on a managed, joined background context. |
| Origin, SSE, adapter loading, and WebGL verified | **Fail:** Origin, adapter import, and WebGL pass on Linux Python; SSE fails and no other real engine ran. |
| Optional packaging leaves core unaffected | Pass for spike scope: core manifests have no native dependency/probe, core CMake tests and Python tests pass, and the native dependency exists only in the spike directory. |
| Every supported combination has repeatable prerequisites, CI smoke, and manual checklist | Vacuous because none are supported; this does not offset the minimum-support failure. |

Manual focus feel, accessibility, DPI/multi-monitor behavior, native chrome,
hardware-accelerated WebGL, external-link handling, and visual quality remain
unsupported/unassessed. The observed WebGL result is for the current Linux
display environment only and does not establish hardware GPU support. No
hosted Xvfb/D-Bus run was available (`Xvfb` was absent), and no screenshot was
captured. The installed WebKitGTK runtime was usable from Python, but its
development metadata/headers required by the C++ host were absent. Node.js was
also absent, so the Scene3D runtime could be checksum-verified but not rebuilt.

### Waiting Point Before SSE Integration

All locally executable work that does not require the pending SSE transport is
complete. The Linux Python real-engine result is schema-valid and has exactly
one failed browser check: `sse`. Resume this spike only after confirmation that
the SSE implementation has merged into `develop`; then fetch/pull `develop`,
merge it into this branch, and rerun the commands below without weakening the
snapshot-event assertion. A passing SSE result will not by itself promote the
plan: C++ profile isolation and real-engine platform jobs still require a plan
decision and suitable runners.

### Exact Verification Commands and Results

Run from the repository root:

```bash
git merge-base --is-ancestor \
  3525d507d5865a364d8a2cd496fc0b26a7d82ed8 HEAD
# exit 0

python3 -m venv --system-site-packages \
  /tmp/rti-demo-ui-native-spike-venv
/tmp/rti-demo-ui-native-spike-venv/bin/pip install \
  -e . -r tools/native_webview_spike/requirements.txt
/tmp/rti-demo-ui-native-spike-venv/bin/pip install -e '.[dev]'

PYTHONPATH=tools/native_webview_spike \
  /tmp/rti-demo-ui-native-spike-venv/bin/python -m unittest -v \
  tools/native_webview_spike/test_python_lifecycle.py \
  tools/native_webview_spike/test_python_runner_prototype.py
# 10 passed

set -o pipefail
timeout 40s /tmp/rti-demo-ui-native-spike-venv/bin/python \
  tools/native_webview_spike/python_host.py --timeout 20 \
  | tee /tmp/native-python-spike-programmatic.log
# exit 0; strict report has exactly one failed check: SSE

timeout 40s /tmp/rti-demo-ui-native-spike-venv/bin/python \
  tools/native_webview_spike/python_host.py --timeout 20 --signal-after 4 \
  | tee /tmp/native-python-spike-signal.log
# exit 0; signal_observed=true and teardown checks pass

cmake -S tools/native_webview_spike \
  -B build/native-webview-spike-fake \
  -DNATIVE_WEBVIEW_SPIKE_BUILD_REAL_HOST=OFF
cmake --build build/native-webview-spike-fake \
  --target native_webview_cpp_lifecycle --parallel
timeout 10s \
  ./build/native-webview-spike-fake/native_webview_cpp_lifecycle
# exit 0

passes=0; timeouts=0; failures=0
for i in $(seq 1 100); do
  timeout 2s \
    ./build/native-webview-spike-fake/native_webview_cpp_lifecycle \
    --immediate-stop >"/tmp/native-cpp-race-$i.log" 2>&1
  rc=$?
  if [ "$rc" -eq 0 ]; then
    passes=$((passes+1))
  elif [ "$rc" -eq 124 ]; then
    timeouts=$((timeouts+1))
  else
    failures=$((failures+1))
  fi
done
printf 'iterations=100 passes=%s timeouts=%s other_failures=%s\n' \
  "$passes" "$timeouts" "$failures"
# iterations=100 passes=37 timeouts=63 other_failures=0

passes=0; timeouts=0; failures=0
for i in $(seq 1 100); do
  timeout 2s \
    ./build/native-webview-spike-fake/native_webview_cpp_lifecycle \
    >"/tmp/native-cpp-health-$i.log" 2>&1
  rc=$?
  if [ "$rc" -eq 0 ]; then
    passes=$((passes+1))
  elif [ "$rc" -eq 124 ]; then
    timeouts=$((timeouts+1))
  else
    failures=$((failures+1))
  fi
done
printf 'health_gated_iterations=100 passes=%s timeouts=%s other_failures=%s\n' \
  "$passes" "$timeouts" "$failures"
# health_gated_iterations=100 passes=100 timeouts=0 other_failures=0

/usr/bin/python3 - <<'PY'
import json
from pathlib import Path

import jsonschema

schema = json.loads(
    Path("tools/native_webview_spike/conformance/result-schema.json").read_text()
)
trace = json.loads(
    Path("/tmp/native-python-spike-programmatic.log").read_text().splitlines()[-1]
)
jsonschema.validate({"results": trace["report"]["results"]}, schema)
failed = [
    name
    for name, result in trace["report"]["results"].items()
    if not result["passed"]
]
assert failed == ["sse"], failed
PY
# exit 0

cmake -S tools/native_webview_spike \
  -B build/native-webview-spike-real \
  -DNATIVE_WEBVIEW_SPIKE_BUILD_REAL_HOST=ON \
  -DWEBVIEW_WEBKITGTK_API=4.1
# fails: required package webkit2gtk-4.1 not found

cmake -S . -B build -DBUILD_TESTING=ON
cmake --build build --parallel
ctest --test-dir build --output-on-failure
# 4/4 passed

PYTHONPATH=python /tmp/rti-demo-ui-native-spike-venv/bin/python \
  -m pytest tests/py -q
# 22 passed

/tmp/rti-demo-ui-native-spike-venv/bin/playwright install chromium
RTI_DEMO_CPP_ARM3D="$PWD/build/cpp/examples/rti_demo_ui_arm3d" \
  PYTHONPATH=python /tmp/rti-demo-ui-native-spike-venv/bin/python \
  -m pytest tests/browser -q
# 6 passed

sha256sum --check assets/runtime3d.sha256
git diff --exit-code -- assets/runtime3d.js assets/runtime3d.sha256
# checksum passes; no generated diff

node --version
# exit 127: node not found; runtime rebuild unavailable

/tmp/rti-demo-ui-native-spike-venv/bin/pre-commit run --all-files
# all configured hooks passed
```
