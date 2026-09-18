# Windows and macOS Native Webview Qualification Plan

## Status

Windows and macOS Python/C++ have passed hosted compilation, real-engine,
lifecycle, and shared frontend conformance. They remain release candidates
pending the manual gates below.

The final implementation intentionally follows a thin-shell contract:
pywebview 6.2.1 supplies GTK, Edge Chromium, and Cocoa for Python, while
webview 0.12.0 supplies the corresponding C++ engines. Browser storage and
frontend navigation use backend defaults rather than SDK-owned policy layers.

This work is intentionally separate from the Linux implementation pull request.
It targets the RTI development-host architectures that are relevant to recent
Connext releases:

| RTI architecture | Combination | Qualification status |
| --- | --- | --- |
| `arm64Darwin23clang16.0` | C++17 / Apple Silicon macOS 14+ / current compatible Xcode | Automated gates passed; manual acceptance pending |
| `arm64Darwin23clang16.0` | Python 3.11+ / Apple Silicon macOS 14+ | Automated gates passed; manual acceptance pending |
| `x64Linux4gcc8.3.0` | Python 3.11+ and C++17 / Ubuntu 22.04+ / GCC 11+ or Clang 14+ | Supported |
| `x64Win64VS2017` | Python 3.11+ and C++17 / Windows 10/11 / VS2022 | Automated gates passed; manual acceptance pending |

The compiler encoded in an RTI architecture name describes the toolchain used
to build the RTI binaries. It is not a requirement to build the consuming
application with that legacy compiler. Qualification uses a modern compatible
application toolchain and separately verifies linking to the applicable RTI
binary architecture.

`armv8Linux` and all other operating-system/CPU combinations are outside this
effort.

## Inherited Contract

The additional platforms must preserve the completed Linux contract:

- Browser mode remains the default and core packages have no native GUI
  dependency, import, or platform probe.
- Python uses the separate `rti-demo-ui-native` distribution and synchronous
  `run_native()` API on the main thread.
- C++ uses the separate `rti_demo_ui_native::native_webview` target and
  synchronous `native::run()` API on the main thread.
- The state server binds a dynamic literal-loopback port and is accepting
  requests before the window is created.
- Window close, programmatic stop, server failure, and process control requests
  converge on one idempotent joined cleanup path.
- The SDK exposes no application JavaScript-native API.
- Browser storage persistence and frontend navigation are backend-owned.
  Applications needing deterministic storage or navigation restrictions
  implement them in application state and frontend behavior.
- Built-in, custom, and adapter-provided frontends use the same HTTP, snapshot,
  SSE, command, theme, Canvas, WebGL, focus, and resize contracts.

The latest stable pywebview release remains 6.2.1 and is used on all three
Python platforms. C++ retains webview 0.12.0.

## Application Identity, Storage, and Navigation

Python retains the optional reverse-DNS `application_id` for source
compatibility. It does not select a browser profile.

Python and C++ use the default persistent-storage behavior of the selected
backend. The exact directory, persistence lifetime, and sharing boundary are
platform/library details and are not SDK guarantees. In particular, dynamic
loopback ports make origin-scoped `localStorage` and IndexedDB unsuitable for
portable application state.

Custom frontends are trusted application code. The SDK does not intercept
top-level navigation or popup requests and does not claim to be a browser
security boundary. Applications must keep their native-mode frontend within
the navigation model they intend to support.

## Windows Direction

### Python

- Select pywebview's Edge Chromium backend explicitly.
- Disable private mode while leaving the user-data directory and navigation
  behavior to pywebview/WebView2 defaults.
- Translate missing pythonnet, WebView2 Runtime, and initialization failures
  into `NativeWebviewError` with a concrete installation action.
- Use a Windows console control handler that only sets a Win32 event. A managed
  watcher dispatches window close outside callback context and unregisters the
  handler on exit.

### C++

- Build the pinned webview backend with Visual Studio 2022 and the current
  Windows SDK.
- Use pinned webview's stock WebView2 user-data and navigation behavior.
- Keep COM initialization, window creation, and the Win32 message loop on the
  calling main thread.
- Use `SetConsoleCtrlHandler` only to signal a Win32 event; a managed watcher
  dispatches close. Restore the previous process behavior on exit.
- Treat a missing Evergreen WebView2 Runtime as a startup failure, not a browser
  fallback or bootstrap request.

## macOS Direction

### Python

- Select pywebview's Cocoa backend explicitly and disable private mode.
- Use its default `WKWebsiteDataStore`, delegates, navigation behavior, and
  AppKit main-thread loop.
- Expose no application JavaScript API.
- Translate missing pywebview Cocoa dependencies and initialization failures
  into actionable `NativeWebviewError`.
- POSIX handlers only set an event; the managed watcher schedules close on the
  AppKit main queue and restores prior handlers.

Do not use pywebview private `BrowserView` state or replace its private
delegates.

### C++

- Compile the platform host as Objective-C++ and link AppKit and WebKit.
- Keep `NSApplication`, `NSWindow`, and `WKWebView` creation and execution on
  the calling main thread.
- Use pinned webview's stock default `WKWebsiteDataStore`, navigation behavior,
  and application identity.
- Dispatch termination onto the AppKit main queue. POSIX handlers retain the
  common event-only contract.

## Host-Independent Preparation

The following may be completed without Windows or macOS development hosts:

1. Isolate lifecycle and control-watcher seams from native engine calls.
2. Select platform sources and dependencies in CMake without changing the core
   graph.
3. Add Python platform configuration and dependency markers without eager
   pywebview imports.
4. Add deterministic tests for backend selection, lifecycle races, and handler
   restoration.
5. Add compile/fake-lifecycle CI jobs where hosted architecture and toolchains
   exist. Such jobs are preparation evidence and do not advertise support.
6. Reuse the production conformance page and structured result schema for
   eventual real-engine jobs.

Platform code that cannot be compiled or exercised on the current host must be
clearly marked unqualified. A source skeleton or cross-compilation result is
not a support result.

## Fixed Qualification Gates

Each Python/C++ and platform combination is classified independently. Support
requires all of:

1. Native compilation and dependency installation on the exact OS/CPU family.
2. Real window startup on the required main thread.
3. Built-in, custom, and adapter-provided frontend conformance.
4. Snapshot, idle/active SSE, commands with exact Origin, dynamic imports,
   workers, themes/layouts, Canvas known pixels, WebGL known pixels, focus, and
   narrow resizing.
5. Startup failure before/after bind, normal close, programmatic stop,
   simultaneous close, server failure, signal/console control, active command,
   and active SSE teardown.
6. Released bound port and joined server, watcher, event-loop, and GUI-owned
   work on every exit.
7. Required hosted or maintained self-hosted real-engine CI with retained
   diagnostics.
8. Interactive validation of native chrome, keyboard input, accessibility,
   standard/high DPI, multi-monitor movement, hardware GPU rendering, close,
   control handling, and application-owned link behavior.

## Required Hosts

Completion requires:

- An Apple Silicon macOS 14 runner with Xcode/Apple Clang and a WindowServer
  session. A GitHub-hosted arm64 runner is acceptable if available; otherwise
  use a maintained self-hosted Mac.
- A Windows 10/11 x64 runner with Visual Studio 2022, a current Windows SDK,
  Evergreen WebView2 Runtime, and an interactive desktop. If GitHub-hosted
  Windows cannot reliably run the real window, use a maintained self-hosted
  runner.
- Interactive access to each platform for the manual release checklist.

Signing, notarization, installers, auto-update, and bundling the WebView2
Runtime remain outside qualification. A later packaging phase may add them
after the native runners pass.

## Prepared-Work Exit

The no-host preparation checkpoint is complete when:

- Shared behavior has deterministic Linux-runnable tests.
- Platform dependency and source selection is explicit.
- Windows and macOS implementation seams are documented or implemented without
  claiming runtime success.
- CI scaffolding distinguishes compile/fake checks from required real-engine
  qualification.
- The exact commands, unverified assumptions, and required host actions are
  recorded.
- Existing Linux and browser behavior remains fully green.

## Preparation CI Evidence

GitHub Actions run
[`33563348799`](https://github.com/wcoleman-rti/rti-demo-ui/actions/runs/33563348799)
validated the initial host-independent checkpoint on 2026-09-01:

- `windows-2022` reported Windows Server 2022-compatible build
  `10.0.20348`, AMD64, and completed 27 tests with five intentional
  platform-specific skips.
- `macos-14` reported macOS 14.8.7, arm64, and completed 27 tests with five
  intentional platform-specific skips. This confirms that the hosted label
  matches the `arm64Darwin23clang16.0` host architecture needed for subsequent
  compile and engine work.
- Existing Python, C++, browser, and Linux real-engine jobs also passed.

The initial preparation jobs omitted the repository's pinned `pytest-asyncio`
dependency, causing warnings for its configured pytest options. The job now
installs that existing pin; this was a test-environment issue rather than a
runner behavior failure.

## Automated Native Qualification Evidence

GitHub Actions run
[`35356444290`](https://github.com/wcoleman-rti/rti-demo-ui/actions/runs/35356444290)
passed on 2026-09-18:

- Windows Server 2022 / AMD64: Python and C++ compilation, fake lifecycle,
  real-window smoke, shared conformance, dynamic-port persistence, and
  application/executable identity isolation.
- macOS 14 / arm64: C++ compilation, fake lifecycle, real-window smoke, shared
  conformance, dynamic-port persistence, and executable identity isolation.
- Linux native, core Python/C++, browser, and documentation regression jobs.

These historical results exceeded the current thin-shell contract by also
testing profile isolation and navigation denial. They do not replace interactive
Windows 10/11 and Apple Silicon macOS checks for accessibility, native chrome,
hardware GPU behavior, DPI/multi-monitor behavior, and user-driven close and
control handling.

GitHub Actions run
[`35361628970`](https://github.com/wcoleman-rti/rti-demo-ui/actions/runs/35361628970)
extended that evidence on 2026-09-18:

- The former direct macOS Python/PyObjC host passed fake lifecycle/profile
  tests, real-window smoke, shared conformance, dynamic-port persistence, and
  application-ID isolation on macOS 14 / arm64.
- The Windows Python/C++ job passed the same established gates after waiting
  for transient WebView2 BrowserMetrics handles during test-workspace cleanup.
- Every Linux native, core Python/C++, browser, and documentation regression
  job passed.

That direct-host result is retained as historical evidence. The subsequent
thin-shell revision replaced it with pywebview Cocoa and removed profile
isolation and navigation denial from the production contract.
