# Opt-In Native Webview Mode Plan

## Status

All implementation phases completed on 2026-08-31 for the supported Linux
Python and C++ combinations. The independently packaged runners provide
managed lifecycle, supported-platform integration, release artifacts,
consumer examples, and documented operations. macOS and Windows remain
unsupported.

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
- Does a persistent profile retain browser-owned preferences for the same
  application while keeping distinct application identities isolated?
- How do a dynamic loopback port and browser origin rules constrain durable
  `localStorage`, IndexedDB, and cookie use?
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
3. Wait for public `ReadyInfo`, which guarantees that the listener is accepting
   requests, and use its canonical URL.
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

run_native(
    app,
    application_id="com.example.factory-dashboard",
    async_main=run_demo,
    width=1280,
    height=800,
    devtools=False,
)
```

`run_native` validates a reverse-DNS-style `application_id`, positive bounded
dimensions, loopback hosting, and app lifecycle state. The identifier selects
a stable Python profile namespace; changing it intentionally creates a separate
profile. The runner starts `app.run()` on a dedicated asyncio loop/thread, waits
for `app.wait_until_ready()`, creates the window on the main thread, and
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

rti::demo::ui::native::NativeWindowOptions options;
options.width = 1280;
options.height = 800;
rti::demo::ui::native::run(app, options);
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
- Use a persistent browser profile scoped to the native application's stable
  identity. Repeated executions of the same application may reuse that profile;
  distinct application identities must not share it.
- Python uses the explicit `application_id` to select its profile namespace.
  For the first C++ release, the packaged executable identity is the profile
  identity supplied to the selected platform backend. Same-executable
  invocations may intentionally share browser state.
- The SDK does not intentionally place snapshots, SSE payloads, command
  capabilities, command results, credentials, or other operational state in
  persistent browser storage. API and command responses remain `no-store`; SSE
  and static assets retain their existing explicit cache policies.
- A persistent profile does not provide a stable web origin. Applications using
  port `0` receive a new origin when the selected port changes, so
  origin-scoped `localStorage` and IndexedDB are not guaranteed to carry across
  runs. Application-scoped persistent cookies work across those loopback ports
  and are the bounded first-release browser preference mechanism. Larger or
  sensitive configuration remains application-owned; a stable virtual-origin
  or SDK preferences feature requires a separate future design. The SDK itself
  does not set localhost cookies.
- Private or per-run ephemeral execution may be added later as an explicit
  option, but it is not a first-release support gate.

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
4. Run the same application profile twice on different dynamic ports and verify
   a persistent cookie sentinel survives. Run a distinct application identity
   and verify the sentinel is absent. Record the platform identity and profile
   location or namespace used by the selected backend.
5. Capture a window or webview image where the selected host API supports it
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

#### Phase 1 Result (2026-08-31)

Phase 1 is complete for the supported Linux combinations:

- `native/python/` is an independently versioned `rti-demo-ui-native`
  distribution. It pins the compatible core `0.4.x` line and pywebview 6.2.1,
  imports pywebview only when `run_native()` is called, validates its options
  and app state, creates an application-ID-scoped profile, and keeps the core
  package manifest unchanged.
- `run_native()` owns the app's asyncio loop on a joined worker thread while
  pywebview creation and execution remain on the calling main thread.
  `async_main` runs on the owner loop; normal return, exception, window
  initialization failure, window close, independent server stop, and bind
  failure all converge on app stop and owner-thread join. Application exceptions
  are re-raised after cleanup and native/lifecycle failures use
  `NativeWebviewError`.
- `native/cpp/` is an independently versioned opt-in CMake project exporting
  `rti_demo_ui_native::native_webview`. It fetches pinned webview 0.12.0 only
  when configured, requires an existing or source-provided core target, retains
  C++17, and leaves the root/core CMake graph free of GTK and WebKitGTK probes.
- C++ `native::run()` starts `DemoUiApp::run()` on one joined server thread,
  races readiness against early server completion so bind failure cannot hang,
  creates and runs webview on the calling thread, closes the window when the
  server ends independently, and stops and joins the server after every window
  exit or initialization failure.
- Fake-host suites cover validation, early bind failure, after-bind window
  failure, normal close, independent server stop, `async_main` completion,
  exception and cancellation, single-use app enforcement, released ports, and
  joined execution contexts. Real Python and C++ production API smoke tests pass
  under Xvfb/D-Bus/WebKitGTK. The Ubuntu 22.04 native job passed both suites in
  GitHub Actions run `33440092333`.

The C++ host uses the public Linux native window handle for initial resizable
dimensions because webview 0.12.0 performs the GTK resize but incorrectly
returns `WEBVIEW_ERROR_INVALID_ARGUMENT` from `set_size()`. This bounded
adapter avoids ignoring a reported error or patching the dependency.

Navigation restriction, C++ persistent-cookie configuration, signal
coordination, examples, and full frontend conformance remain Phase 2 work.
Installation and release documentation remain Phase 3 work.

Phase 1 verification commands:

```bash
PYTHONPATH=python:native/python/src \
  /tmp/rti-demo-ui-native-spike-venv/bin/python \
  -m pytest native/python/tests -q

/tmp/rti-demo-ui-native-spike-venv/bin/python -m pip wheel \
  --no-deps --wheel-dir /tmp/rti-native-phase1-wheel native/python

cmake -S native/cpp -B build/native-phase1 \
  -DBUILD_TESTING=ON \
  -DRTI_DEMO_NATIVE_REAL_ENGINE_TESTS=ON
cmake --build build/native-phase1 --parallel
ctest --test-dir build/native-phase1 --output-on-failure -LE real_engine

LIBGL_ALWAYS_SOFTWARE=1 dbus-run-session -- \
  xvfb-run -a -s "-screen 0 1440x900x24" \
  ctest --test-dir build/native-phase1 --output-on-failure -L real_engine
```

### Phase 2: Platform Integration

- Implement navigation restriction, title/size/resizing, close dispatch, and
  signal coordination for each supported platform.
- Add examples using the same application model in browser and native modes.
- Verify built-in, custom, and adapter-provided frontends.

#### Phase 2 Result (2026-08-31)

Phase 2 is complete for the supported Linux Python and C++ combinations.
Production runners now block top-level navigation and new-window actions
outside the exact dynamically bound loopback origin. Python installs the
WebKitGTK policy synchronously during pywebview's `before_show`; C++ installs
the WebKitGTK `decide-policy` handler through webview's public browser
controller before initial navigation. Neither runner exposes a privileged
JavaScript-native bridge.

Both runners coordinate `SIGINT` and `SIGTERM` without performing window or
server operations in the signal handler. Python handlers only set a
`threading.Event`; C++ handlers only update `volatile std::sig_atomic_t`.
Managed watcher threads request window closure, all server/owner contexts are
joined, and previous handlers are restored on exit. Fake-host and real-engine
SIGINT tests pass.

The C++ production adapter now configures WebKitGTK's supported SQLite cookie
store under
`$XDG_DATA_HOME/rti-demo-ui-native/<executable-filename>/cookies.sqlite`, or
the corresponding GLib user-data directory when `XDG_DATA_HOME` is unset.
The executable filename is the packaged application identity. Moving an
executable without renaming it retains the profile; renaming it selects a new
profile. Packagers must therefore assign distinct executable filenames to
applications that require isolated state. Python continues to use the
required reverse-DNS `application_id` under its documented user-data root.

The shared custom conformance frontend now obtains storage probe settings from
application data when URL parameters are absent, allowing the unmodified
production runner APIs to test dynamic-port persistence. Production Python
and C++ hosts passed snapshot/SSE, command Origin, dynamic adapter and runtime
imports, module workers, themes, Canvas, WebGL, keyboard focus, resize
observation, external-navigation blocking, and cookie storage. Two sequential
runs under one identity reused a cookie across different dynamic ports; a
distinct Python application ID and a distinctly named C++ executable remained
isolated. Existing built-in frontend real-engine smoke tests also pass.

Dual-mode Python and C++ examples construct one model and select browser or
native execution. Browser mode remains the Python default; the C++ native
example is excluded unless `RTI_DEMO_NATIVE_BUILD_EXAMPLES=ON`, so the core
example graph performs no native dependency discovery.

Hosted run `33442500677` passed the production native job on Ubuntu 22.04. Its
first browser job encountered the pre-existing C++ Arm3D selection timing
flake; rerunning that failed job passed all 33 browser tests, making the
overall run green without a source change.

Phase 2 verification commands:

```bash
PYTHONPATH=python:native/python/src \
  /tmp/rti-demo-ui-native-spike-venv/bin/python \
  -m pytest tests/py native/python/tests -q

cmake -S native/cpp -B build/native-phase2 \
  -DBUILD_TESTING=ON \
  -DRTI_DEMO_NATIVE_BUILD_EXAMPLES=ON \
  -DRTI_DEMO_NATIVE_REAL_ENGINE_TESTS=ON
cmake --build build/native-phase2 --parallel
ctest --test-dir build/native-phase2 --output-on-failure -LE real_engine

LIBGL_ALWAYS_SOFTWARE=1 dbus-run-session -- \
  xvfb-run -a -s "-screen 0 1440x900x24" \
  ctest --test-dir build/native-phase2 --output-on-failure -L real_engine

LIBGL_ALWAYS_SOFTWARE=1 dbus-run-session -- \
  xvfb-run -a -s "-screen 0 1440x900x24" \
  bash -euo pipefail <<'SCRIPT'
rm -rf /tmp/rti-demo-ui-phase2-production
mkdir -p /tmp/rti-demo-ui-phase2-production
export XDG_DATA_HOME=/tmp/rti-demo-ui-phase2-production/python-data
PYTHONPATH=python:native/python/src \
  /tmp/rti-demo-ui-native-spike-venv/bin/python \
  native/python/tests/real_conformance.py \
  --application-id org.rti.phase2.same --expected __absent__ --write first \
  --static-root tools/native_webview_spike/conformance
PYTHONPATH=python:native/python/src \
  /tmp/rti-demo-ui-native-spike-venv/bin/python \
  native/python/tests/real_conformance.py \
  --application-id org.rti.phase2.same --expected first --write second \
  --static-root tools/native_webview_spike/conformance
PYTHONPATH=python:native/python/src \
  /tmp/rti-demo-ui-native-spike-venv/bin/python \
  native/python/tests/real_conformance.py \
  --application-id org.rti.phase2.isolated \
  --expected __absent__ --write isolated \
  --static-root tools/native_webview_spike/conformance

export XDG_DATA_HOME=/tmp/rti-demo-ui-phase2-production/cpp-data
production_cpp=./build/native-phase2/tests/rti_demo_ui_native_real_conformance
"$production_cpp" __absent__ first
"$production_cpp" first second
cp "$production_cpp" \
  /tmp/rti-demo-ui-phase2-production/real_conformance_isolated
/tmp/rti-demo-ui-phase2-production/real_conformance_isolated \
  __absent__ isolated
SCRIPT

RTI_DEMO_CPP_ARM3D="$PWD/build/phase2-full/cpp/examples/rti_demo_ui_arm3d" \
  PYTHONPATH=python /tmp/rti-demo-ui-native-spike-venv/bin/python \
  -m pytest tests/browser -q

/tmp/rti-demo-ui-native-spike-venv/bin/python -m pip wheel \
  --no-deps --wheel-dir /tmp/rti-demo-ui-phase2-wheel native/python

cmake -S cpp -B build/phase2-core-isolation -DBUILD_TESTING=OFF
cmake --build build/phase2-core-isolation --parallel
sha256sum --check assets/runtime3d.sha256
/tmp/rti-demo-ui-native-spike-venv/bin/pre-commit run --all-files
```

### Phase 3: Documentation and Release

- Document installation, system prerequisites, API usage, browser fallback,
  troubleshooting, and platform tier.
- Update lifecycle, architecture, third-party notices, and release packaging.
- Perform automated and manual release smoke tests.

#### Phase 3 Result (2026-08-31)

Phase 3 implementation is complete. `docs/native-webview.md` is the
installation and operations guide for the Linux-first release. It records the
Ubuntu system packages, Python and C++ opt-in setup, synchronous native APIs,
browser fallback, profile identity and storage behavior, exact-origin policy,
shutdown semantics, troubleshooting, support tier, and versioned manual
release checklist. The language API guides, lifecycle, architecture, root
README, and third-party register now agree with that contract.

The Python companion now publishes its own package README and Linux
classifiers. Unsupported platforms no longer install an unused pywebview
dependency, while `run_native()` retains its actionable unsupported-platform
error before lazy engine import. Python 3.11 and 3.12 install the qualified
PyGObject 3.50 pin against the documented Ubuntu development packages; Python
3.13+ uses its matching distro binding through a `--system-site-packages`
environment. The tag release workflow verifies that both distribution versions
match the tag, then builds and attaches wheel and source distributions for
`rti-demo-ui` and `rti-demo-ui-native`. C++ remains a source CMake companion in
the GitHub source archive; a clean downstream consumer configure proves that
adding the native project is opt-in and that the public target links from
outside the repository top-level graph.

Release-artifact smoke tests built both wheels and source distributions,
installed the wheels in a clean environment outside the checkout, served the
built-in packaged frontend in a real pywebview window, and exited cleanly on
SIGINT. The clean C++ consumer configured, built, opened the built-in frontend
through the production runner, and stopped without a leaked server.

Manual release evidence combines the earlier user-accepted Linux checks for
both engines (chrome, resize, rendering, keyboard focus/input, DPI, and blocked
navigation) with the current production runners on the physical display. The
current host reported two 1920x1080 monitors and an Intel Arrow Lake-P display
controller. Production Python conformance on that display passed known-pixel
Canvas/WebGL rendering, focus, commands, imports, and navigation. Both
production release-smoke windows then exited normally from SIGINT. Direct
AT-SPI tree capture and `glxinfo` renderer identification were unavailable
because the inspection-only packages were absent and this session could not
authenticate for system installation. Those tools are diagnostics rather than
runtime gates; semantic browser accessibility coverage passed, and the manual
checklist requires direct accessibility and hardware-renderer inspection again
for each tagged release candidate.

Hosted run `33443952099` passed all jobs for the Phase 3 commit. The Ubuntu
22.04 native job built the downstream CMake consumer, built and installed the
release wheels into a clean environment, ran both installed-artifact native
smokes, and repeated the production and spike conformance gates under
Xvfb/D-Bus/Mesa. The Phase 0 prototype remains as qualification evidence, but
ongoing CI now uses the superseding production Python/C++ lifecycle, signal,
storage, navigation, packaging, and downstream-consumer gates instead of
rebuilding and rerunning both implementations.

Phase 3 verification commands:

```bash
python -m pip install build==1.2.2
python -m build --outdir /tmp/rti-demo-ui-phase3-artifacts/core .
python -m build --outdir /tmp/rti-demo-ui-phase3-artifacts/native native/python

cmake -S native/cpp/tests/consumer -B build/native-consumer \
  -DRTI_DEMO_UI_SOURCE_DIR="$PWD"
cmake --build build/native-consumer --parallel

# From a clean environment outside the checkout, install the two built wheels.
cd /tmp
/tmp/rti-demo-ui-phase3-smoke/bin/python -c \
  'import rti_demo_ui, rti_demo_ui_native'

# Return to the checkout and run both release artifacts on a real or Xvfb
# display. The Python command is sent SIGINT after startup.
XDG_DATA_HOME=/tmp/rti-demo-ui-phase3-profiles/python \
  /tmp/rti-demo-ui-phase3-smoke/bin/python - <<'PY'
import os
import signal
import threading

from rti_demo_ui import DemoUiApp
from rti_demo_ui_native import run_native

threading.Timer(1, lambda: os.kill(os.getpid(), signal.SIGINT)).start()
run_native(
    DemoUiApp("Installed native wheel smoke"),
    application_id="org.rti.phase3-wheel-smoke",
)
PY
XDG_DATA_HOME=/tmp/rti-demo-ui-phase3-profiles/cpp \
  ./build/native-consumer/rti_demo_ui_native_consumer

xrandr --listmonitors
lspci | grep -Ei 'vga|3d|display'
```

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
- Persistent-profile conformance across dynamic ports: same-application cookie
  reuse, distinct-application isolation, and documented behavior for
  origin-scoped storage, simultaneous instances, and executable relocation.
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
- Developer tools require an explicit option. Native mode uses an
  application-scoped persistent profile; Python identifies it with the required
  `application_id`, while C++ uses the packaged executable identity in the
  first release.
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
- Persistent-profile reuse across dynamic ports for one application identity
  and isolation between distinct identities are verified.
- Optional packaging leaves core installation and linking unaffected.
- Every supported combination has a repeatable build, runtime prerequisites,
  a required real-engine CI smoke test, and a manual release checklist.

The implementation is accepted when supported platforms satisfy those checks
with production runner code and external browser mode remains behaviorally
unchanged.

## Phase 0 Spike Result and Storage Re-evaluation (2026-08-31)

### Recommendation

**Advance to Phase 1 as Linux-first work.** The persistent-profile revision and
installed WebKitGTK development dependencies allowed both selected Linux hosts
to complete the real-engine conformance cycle. The selected dependencies are
viable for a Linux-first release, and the checked-in Ubuntu 22.04 hosted job
passed in GitHub Actions run `33436766073`.

The SSE implementation from `develop` commit `5647f40` passed both embedded
Linux engines. The C++ readiness race was fixed in the core contract rather
than hidden behind runner health polling. `run()` now starts the bound httplib
listener on a managed execution context, waits for its running state, and only
then publishes `ReadyInfo`. `stop()` serializes against readiness publication.
The public API and blocking `run()` behavior are unchanged, while
`wait_until_ready()` now guarantees that the reported URL accepts requests.
All six C++ suites pass, a new 50-iteration immediate-health regression passes,
and the formerly failing raw immediate-stop stress passes 100/100.

The selected dependency pins remain appropriate spike candidates:
`pywebview==6.2.1` (BSD-3-Clause) and webview commit
`3ab4b5d722438fc8a13e6ca830c5e2372d19a01d`, tag `0.12.0` (MIT).
No alternative engine, dependency, production native-host API, or lower
platform floor was selected. The Linux C++ prototype uses webview's public
native browser handle to configure WebKitGTK's supported persistent cookie
store and navigation-policy signal before navigation; no private API or fork is
required. The prototype dependencies remain isolated in
`tools/native_webview_spike/`; core dependency manifests are unchanged.

### Six-Combination Support Matrix

`Unsupported` is a first-release classification from this spike, not a claim
that the underlying operating-system engine can never be supported.

| Backend | Platform gate | Classification | Reproducible evidence tied to a fixed gate |
| --- | --- | --- | --- |
| Python 3.11+ / pywebview 6.2.1 | Ubuntu 22.04+ / GTK 3 / WebKitGTK 4.1 | Supported | Real `gtkwebkit2` cycles passed on Ubuntu 26.04.1 with GTK 3.24.52 and WebKitGTK 2.52.6. Across three dynamic ports, a same-profile persistent cookie survived and a distinct profile remained isolated. Snapshot, SSE, command Origin, imports, worker, theme, Canvas, WebGL, focus, resize, external-navigation blocking, normal close, signal, port teardown, and owner-loop join passed. The identical sequence passed locally and in the Ubuntu 22.04 hosted job under Xvfb/D-Bus/Mesa. Manual chrome, resizing, rendering, focus/input, DPI, and navigation checks passed. |
| C++17 / webview 0.12.0 | Ubuntu 22.04+ / GTK 3 / WebKitGTK 4.1 | Supported | The real pinned webview host built and passed the full cycle on WebKitGTK 2.52.6. A supported native-handle adapter configured a profile cookie database and `decide-policy` callback before navigation. Same-profile reuse, distinct-profile isolation, dynamic ports, SSE, exact Origin, imports, worker, theme, Canvas, WebGL, focus, resize, blocked external navigation, normal close, signal, server join, and fixed readiness passed locally and in the Ubuntu 22.04 hosted job under Xvfb/D-Bus/Mesa. Manual chrome, resizing, rendering, focus/input, DPI, and navigation checks passed. |
| Python 3.11+ / pywebview 6.2.1 | macOS 12+ / WKWebView | Unsupported | No matching macOS host or real-engine job was available. Running pywebview with persistence enabled selects WKWebView's default persistent data store, which is compatible with the revised policy in principle; application identity and isolation remain unverified. |
| C++17 / webview 0.12.0 | macOS 12+ / WKWebView | Unsupported | No matching macOS host or real-engine job was available. Pinned webview's default `WKWebViewConfiguration` selects the persistent data store, which is no longer a failed gate; packaged-application identity and isolation remain unverified. |
| Python 3.11+ / pywebview 6.2.1 | Windows 10+ / Evergreen WebView2 | Unsupported | No matching Windows host or real-engine job was available, so neither runtime-version detection nor the non-skippable startup/render/close gate was executed. |
| C++17 / webview 0.12.0 | Windows 10+ / Evergreen WebView2 | Unsupported | No matching Windows host or real-engine job was available. Pinned webview's persistent `%APPDATA%/<executable>` WebView2 user-data folder aligns with same-executable reuse, but distinct executable identity, collisions, and real-engine behavior remain unverified. |

At least one Python and one C++ combination must be supported to advance. Both
Linux combinations satisfy that rule.

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

The revised Python real-engine sequence used two explicit persistent profile
directories and dynamic ports 45023, 40117, and 45357. Profile A's first run
observed an absent cookie and wrote `app-a-first`; its second run read that value
and wrote `app-a-second`. Profile B observed the cookie as absent. The C++ host
passed the equivalent sequence on dynamic ports 43981, 60241, and 44343 after
configuring WebKitGTK's SQLite cookie store through the public native handle.
Both signal paths passed. All traces reported clean window, server, thread, and
port teardown.

The page reported passes for snapshot schema 2, command capability and exact
browser Origin (the report command was accepted), dynamic adapter import,
runtime3d/Three.js bundle import, a same-origin module worker, applied theme
CSS, Canvas, WebGL, keyboard focus, a 1280x800 resize observation, persistent
cookies across dynamic ports, and blocked external top-level navigation. The
captured JSON passes the checked-in strict result schema. Both engines received
the immediate `snapshot` SSE event with matching event ID and revision. Browser
command acceptance uses a separate structured Origin probe before the final
report; neither prototype adds a production JavaScript-native bridge.

webview 0.12.0 exposes no portable profile configuration. On Linux, its public
native `WebKitWebView` handle is available before navigation, allowing the
companion adapter to assign a supported persistent cookie database and
navigation callback without modifying webview. On macOS it uses the default
persistent `WKWebsiteDataStore`; on Windows it hard-codes an
application-derived WebView2 data directory. The macOS and Windows identity,
collision, relocation, navigation, and simultaneous-instance behavior remain
unverified. Origin-scoped `localStorage` and IndexedDB still vary with a dynamic
port; bounded persistent cookies work across ports, while larger configuration
remains application-owned.

### Exit-Criterion Evaluation

| Exit criterion | Result |
| --- | --- |
| Six combinations complete a leak-free real cycle or receive a failed-gate classification | Pass: all six are classified above; unavailable platforms were not conditionally skipped or claimed supported. |
| At least one Python and one C++ combination supported | Pass: the Linux Python and C++ combinations pass local automation, manual checks, and the hosted Ubuntu 22.04 gate. |
| Main-thread and owner-loop rules documented and represented | Pass for prototype shape: both hosts put the GUI loop on the main thread and server ownership on a managed, joined background context. |
| Origin, SSE, adapter loading, navigation policy, and WebGL verified | **Partial:** all pass in both Linux real engines; macOS and Windows did not run. |
| Same-application persistence and distinct-profile isolation verified | **Partial:** both pass across dynamic ports for Linux Python and C++; macOS, Windows, simultaneous-instance, and relocation behavior remain unverified. |
| Optional packaging leaves core unaffected | Pass for spike scope: core manifests have no native dependency/probe, core CMake tests and Python tests pass, and the native dependency exists only in the spike directory. |
| Every supported combination has repeatable prerequisites, CI smoke, and manual checklist | Pass for the two supported Linux combinations: prerequisites and manual checks pass, and the checked-in Ubuntu 22.04 job passed in GitHub Actions. |

The user manually accepted native chrome, responsive resizing, readable visual
quality, keyboard focus/input, DPI behavior, and absence of unexpected external
navigation in both Linux hosts. The programmatic WebGL probe passed known-pixel
readback and reported renderer `Apple GPU`; the local Xvfb/D-Bus sequence also
passed with Mesa software rendering. Multi-monitor behavior and independent
physical-GPU verification remain unassessed and are documented limitations, not
Linux hosted-CI blockers. No screenshot was captured. Node.js was absent during
the original run, so the Scene3D runtime was checksum-verified but not rebuilt
in that run.

### Phase 0 Conclusion

Phase 0 is complete. Linux Python and C++ satisfy every fixed criterion,
including real rendering, dynamic-port persistence, isolation, navigation
policy, signals, lifecycle, manual acceptance, and Ubuntu 22.04 hosted
execution. The minimum one-Python/one-C++ rule is met and Phase 1 may begin as
Linux-first work; macOS and Windows remain unsupported until separately
qualified.

### Exact Verification Commands and Results

Run from the repository root:

```bash
git merge-base --is-ancestor \
  3525d507d5865a364d8a2cd496fc0b26a7d82ed8 HEAD
# exit 0

git fetch origin develop
git merge --no-edit origin/develop
# merged develop commit 5647f40 as merge commit 2339ec2

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
rm -rf /tmp/rti-demo-ui-native-dynamic-app-a \
  /tmp/rti-demo-ui-native-dynamic-app-b
timeout 40s /tmp/rti-demo-ui-native-spike-venv/bin/python \
  tools/native_webview_spike/python_host.py --timeout 20 \
  --storage-path /tmp/rti-demo-ui-native-dynamic-app-a \
  --storage-key rti-demo-ui-dynamic-python \
  --storage-expected __absent__ --storage-write app-a-first \
  | tee /tmp/native-python-dynamic-a1.log
timeout 40s /tmp/rti-demo-ui-native-spike-venv/bin/python \
  tools/native_webview_spike/python_host.py --timeout 20 \
  --storage-path /tmp/rti-demo-ui-native-dynamic-app-a \
  --storage-key rti-demo-ui-dynamic-python \
  --storage-expected app-a-first --storage-write app-a-second \
  | tee /tmp/native-python-dynamic-a2.log
timeout 40s /tmp/rti-demo-ui-native-spike-venv/bin/python \
  tools/native_webview_spike/python_host.py --timeout 20 \
  --storage-path /tmp/rti-demo-ui-native-dynamic-app-b \
  --storage-key rti-demo-ui-dynamic-python \
  --storage-expected __absent__ --storage-write app-b-first \
  | tee /tmp/native-python-dynamic-b1.log
# all exit 0 on different ports; persistence, isolation, and navigation pass

rm -rf /tmp/rti-demo-ui-native-python-signal
timeout 40s /tmp/rti-demo-ui-native-spike-venv/bin/python \
  tools/native_webview_spike/python_host.py --timeout 20 --signal-after 4 \
  --storage-path /tmp/rti-demo-ui-native-python-signal \
  --storage-key rti-demo-ui-python-signal \
  --storage-expected __absent__ --storage-write signal-run \
  | tee /tmp/native-python-signal.log
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
# iterations=100 passes=100 timeouts=0 other_failures=0

/usr/bin/python3 - <<'PY'
import json
from pathlib import Path

import jsonschema

schema = json.loads(
    Path("tools/native_webview_spike/conformance/result-schema.json").read_text()
)
trace = json.loads(
    Path("/tmp/native-python-dynamic-a2.log").read_text().splitlines()[-1]
)
jsonschema.validate({"results": trace["report"]["results"]}, schema)
failed = [
    name
    for name, result in trace["report"]["results"].items()
    if not result["passed"]
]
assert failed == [], failed
PY
# exit 0

rm -rf /tmp/rti-demo-ui-native-dynamic-app-a \
  /tmp/rti-demo-ui-native-dynamic-app-b \
  /tmp/rti-demo-ui-native-python-signal

cmake -S tools/native_webview_spike \
  -B build/native-webview-spike-real \
  -DNATIVE_WEBVIEW_SPIKE_BUILD_REAL_HOST=ON \
  -DWEBVIEW_WEBKITGTK_API=4.1
cmake --build build/native-webview-spike-real \
  --target native_webview_cpp_host --parallel
# succeeds with WebKitGTK 4.1 version 2.52.6 and GTK 3.24.52

rm -rf /tmp/rti-demo-ui-native-cpp-app-a \
  /tmp/rti-demo-ui-native-cpp-app-b
cpp_host=./build/native-webview-spike-real/native_webview_cpp_host
timeout 40s "$cpp_host" \
  --storage-path /tmp/rti-demo-ui-native-cpp-app-a \
  --storage-key rti-demo-ui-dynamic-cpp \
  --storage-expected __absent__ --storage-write cpp-a-first \
  | tee /tmp/native-cpp-dynamic-a1.log
timeout 40s "$cpp_host" \
  --storage-path /tmp/rti-demo-ui-native-cpp-app-a \
  --storage-key rti-demo-ui-dynamic-cpp \
  --storage-expected cpp-a-first --storage-write cpp-a-second \
  | tee /tmp/native-cpp-dynamic-a2.log
timeout 40s "$cpp_host" \
  --storage-path /tmp/rti-demo-ui-native-cpp-app-b \
  --storage-key rti-demo-ui-dynamic-cpp \
  --storage-expected __absent__ --storage-write cpp-b-first \
  | tee /tmp/native-cpp-dynamic-b1.log
# all exit 0 on different ports; persistence, isolation, and navigation pass

rm -rf /tmp/rti-demo-ui-native-cpp-signal
timeout --kill-after=5s --preserve-status --signal=INT 4s "$cpp_host" \
  --wait-for-signal true \
  --storage-path /tmp/rti-demo-ui-native-cpp-signal \
  --storage-key rti-demo-ui-cpp-signal \
  --storage-expected __absent__ --storage-write signal \
  | tee /tmp/native-cpp-signal.log
# exit 0; signal_observed=true and teardown checks pass

# The exact Xvfb/D-Bus/Mesa sequence is the
# native-webview-spike job's "Run real native engine conformance" block.
# The complete block exited 0 locally and in GitHub Actions run 33436766073.

cmake -S . -B build -DBUILD_TESTING=ON
cmake --build build --parallel
ctest --test-dir build --output-on-failure
# 6/6 passed

PYTHONPATH=python /tmp/rti-demo-ui-native-spike-venv/bin/python \
  -m pytest tests/py -q
# 72 passed

/tmp/rti-demo-ui-native-spike-venv/bin/playwright install chromium
RTI_DEMO_CPP_ARM3D="$PWD/build/cpp/examples/rti_demo_ui_arm3d" \
  PYTHONPATH=python /tmp/rti-demo-ui-native-spike-venv/bin/python \
  -m pytest tests/browser -q
# 33 passed

sha256sum --check assets/runtime3d.sha256
git diff --exit-code -- assets/runtime3d.js assets/runtime3d.sha256
# checksum passes; no generated diff

node --version
# exit 127: node not found; runtime rebuild unavailable

/tmp/rti-demo-ui-native-spike-venv/bin/pre-commit run --all-files
# all configured hooks passed
```
