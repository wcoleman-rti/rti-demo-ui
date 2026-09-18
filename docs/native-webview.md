# Native Webview Mode

Native webview mode opens the existing RTI Demo UI browser frontend in a
desktop application window. It does not replace the HTML/CSS/JavaScript
renderer with native widgets. Browser mode remains the default and requires no
native companion package.

## Support and Qualification

| Language | Platform | Automated qualification | Release support |
| --- | --- | --- | --- |
| Python 3.11+ / pywebview 6.2.1 | Ubuntu 22.04+ x86-64 / GTK 3 / WebKitGTK 4.1 | Passed | Supported |
| C++17 / webview 0.12.0 | Ubuntu 22.04+ x86-64 / GTK 3 / WebKitGTK 4.1 | Passed | Supported |
| Python 3.11+ / pywebview 6.2.1 | Windows 10/11 x64 / Evergreen WebView2 | Passed | Pending manual acceptance |
| C++17 / webview 0.12.0 | Windows 10/11 x64 / Evergreen WebView2 | Passed | Pending manual acceptance |
| C++17 / webview 0.12.0 | Apple Silicon macOS 14+ / WKWebView | Passed | Pending manual acceptance |
| Python 3.11+ / PyObjC 12.2.2 | Apple Silicon macOS 14+ / WKWebView | Passed | Pending manual acceptance |

Automated qualification covers compilation, real-window startup, the shared
frontend contract, navigation denial, lifecycle, persistence, and profile
isolation on the target hosted operating systems. Windows and macOS do not
become release-supported until the manual checklist below is recorded.

Python on macOS uses a direct PyObjC Cocoa host so the companion owns the named
data store and delegates without patching or forking pywebview. pywebview
remains pinned to 6.2.1 for Linux and Windows.

## Platform Prerequisites

### Linux

On Ubuntu 22.04 and 24.04 with Python 3.11 or 3.12, install the build
prerequisites for the companion's pinned PyGObject 3.50 dependency:

```bash
sudo apt-get install \
  gcc gir1.2-gtk-3.0 gir1.2-webkit2-4.1 libcairo2-dev \
  libgirepository1.0-dev pkg-config
python3.11 -m venv .venv
```

The selected Python installation must include its matching development
headers. The GitHub Ubuntu 22.04 gate uses setup-python 3.11, builds PyGObject
3.50 against these packages, and runs the real engine.

On newer Ubuntu releases with Python 3.13 or newer, use the matching distro
binding instead:

```bash
sudo apt-get install gir1.2-gtk-3.0 gir1.2-webkit2-4.1 python3-gi
python3 -m venv --system-site-packages .venv
```

The companion's environment marker omits the older PyGObject pin for Python
3.13+, allowing the distro's matching `gi` extension to supply the binding.

C++ builds need:

```bash
sudo apt-get install \
  build-essential cmake libgtk-3-dev libwebkit2gtk-4.1-dev pkg-config
```

The C++ companion fetches the pinned webview 0.12.0 source during its first
CMake configure. A network connection is needed only when that FetchContent
dependency is not already cached.

### Windows

Python requires Python 3.11+, the companion wheel, and the Evergreen WebView2
Runtime. Installing the companion installs pywebview 6.2.1 and pythonnet.

C++ requires Visual Studio 2022 with the current Windows SDK and the Evergreen
WebView2 Runtime. The `x64Win64VS2017` RTI architecture name describes the
Connext binary ABI; applications may use the compatible current MSVC toolchain.

### macOS

C++ requires Apple Silicon macOS 14+, current compatible Xcode/Apple Clang,
AppKit, and WebKit. The `arm64Darwin23clang16.0` RTI architecture remains the
Connext binary architecture even when a newer compatible Xcode builds the
application.

Python requires Python 3.11+ and the companion's pinned PyObjC 12.2.2 Cocoa
and WebKit bindings. Its hosted automated qualification has passed; manual
acceptance remains required.

## Python Installation and Use

Download the core and companion wheels attached to a GitHub release, then
install both local files. The project does not publish them to a package index:

```bash
gh release download v0.4.1 --repo wcoleman-rti/rti-demo-ui \
  --pattern '*.whl' --dir dist
.venv/bin/pip install dist/rti_demo_ui-0.4.1-py3-none-any.whl \
  dist/rti_demo_ui_native-0.4.1-py3-none-any.whl
```

From a source checkout:

```bash
.venv/bin/pip install . ./native/python
```

Build the application model before calling the synchronous native runner on
the main thread:

```python
from rti_demo_ui import DemoUiApp
from rti_demo_ui_native import run_native


async def application_work(app: DemoUiApp) -> None:
    # DDS reads, periodic updates, and post-start model mutations run here.
    ...


app = DemoUiApp("Fleet Telemetry")
app.add_card("Status").add_metric("Vehicles", 12)
run_native(
    app,
    application_id="com.example.fleet-telemetry",
    async_main=application_work,
    width=1280,
    height=800,
    devtools=False,
)
```

`application_id` is a required lowercase reverse-DNS identifier and selects
the persistent browser profile on Linux and Windows. `async_main` runs on the
app's owner event loop after the server is ready. A normal return closes the
window; an exception is re-raised on the calling thread after cleanup.

## C++ Build and Use

The C++ companion is a source CMake package. Keep it out of the core target
graph unless the application opts in:

```cmake
add_subdirectory(path/to/rti-demo-ui/cpp rti-demo-ui-core)
add_subdirectory(path/to/rti-demo-ui/native/cpp rti-demo-ui-native)

target_link_libraries(my_demo PRIVATE
  rti_demo_ui_native::native_webview
)
```

Then run the existing model in the native window:

```cpp
#include <rti_demo_ui_native/native_webview.hpp>

rti::demo::ui::DemoUiApp app("Fleet Telemetry");
app.add_card("Status")->add_metric("Vehicles", 12);

rti::demo::ui::native::NativeWindowOptions options;
options.width = 1280;
options.height = 800;
rti::demo::ui::native::run(app, options);
```

On Linux and Windows, the executable filename is the C++ application identity.
Packagers must give unrelated applications distinct executable filenames.
On macOS, packaged applications use their bundle identity; an unbundled
development executable falls back to executable identity.

## Browser Fallback

The application model is identical in both modes. Do not import or link the
native companion when selecting browser mode:

```python
if use_native:
    from rti_demo_ui_native import run_native

    run_native(app, application_id="com.example.fleet")
else:
    await app.run()
```

For C++, call `native::run(app)` only in a target linked to the companion.
Core-only targets continue to call `app.run()`. See the dual-mode examples
under `native/python/examples` and `native/cpp/examples`.

## Profiles and Navigation

Python stores its Linux profile under
`$XDG_DATA_HOME/rti-demo-ui-native/<application-id>`, falling back to
`~/.local/share`, and its Windows profile under
`%LOCALAPPDATA%/rti-demo-ui-native/<application-id>`.

C++ stores Linux cookies under
`$XDG_DATA_HOME/rti-demo-ui-native/<executable-filename>/cookies.sqlite`.
Pinned webview stores Windows WebView2 data under
`%APPDATA%/<executable-filename>`. WKWebView uses the packaged application's
default persistent website data store on macOS.

Cookies can preserve browser-owned preferences across the dynamic loopback
ports selected on different runs. `localStorage` and IndexedDB are scoped to
the complete origin, including the port, and therefore are not guaranteed to
survive a port change. Applications remain responsible for larger or
sensitive configuration. The SDK does not intentionally persist snapshots,
SSE payloads, command capabilities or results, credentials, or operational
state.

The embedded window permits top-level navigation only within the exact bound
loopback origin. External and new-window navigation is blocked, developer
tools are disabled by default, and no JavaScript-native bridge is exposed.

## Shutdown and Troubleshooting

Closing the window, stopping the app, or sending `SIGINT`/`SIGTERM` on POSIX
performs normal cleanup and joins the managed server and watcher contexts.
Windows C++ handles console control requests through a registered control
handler and posts `WM_CLOSE` to the owned window. Python and POSIX C++ restore
the process's previous handlers after the native runner returns.

Common failures:

- **Missing PyObjC on macOS**: reinstall the companion so its pinned Cocoa and
  WebKit bindings are present.
- **Missing WebView2 Runtime on Windows**: install the Evergreen WebView2
  Runtime and retry from an interactive desktop session.
- **Missing pywebview 6.2.1**: install `rti-demo-ui-native` and the Python
  platform prerequisites above in the active environment.
- **GTK/WebKitGTK initialization failure**: install the 4.1 development/runtime
  packages and launch from a graphical session. CI needs both Xvfb and a D-Bus
  session.
- **Invalid application ID**: use a lowercase reverse-DNS value such as
  `com.example.demo`.
- **Literal loopback required**: leave the host at `127.0.0.1` or use `::1`;
  `localhost` and remote bind addresses are intentionally rejected.
- **Profile cannot be created**: verify that `XDG_DATA_HOME` on Linux or
  `LOCALAPPDATA` on Windows resolves to an absolute writable path.
- **A reused app cannot run**: each `DemoUiApp` instance is single-use in both
  browser and native modes.

## Manual Release Checklist

For each supported engine and release candidate, record:

1. Launch and native window chrome integration.
2. Narrow and wide resizing without clipped controls.
3. Keyboard traversal, text input, and command interaction.
4. Accessibility-tree inspection with the platform tool.
5. Standard and high-DPI behavior, including moving between monitors.
6. Normal close and Ctrl-C cleanup.
7. Blocked external-link and new-window behavior.
8. Canvas and WebGL rendering on a hardware GPU.

Automated conformance covers snapshot/SSE, commands, imports, themes, Canvas,
WebGL pixel readback, focus, resize observation, navigation policy,
profile reuse/isolation, signal shutdown, joined contexts, and released ports.
The manual record is still required before publishing a release candidate.
