# Native Webview Mode

Native webview mode opens the existing RTI Demo UI browser frontend in a
desktop application window. It does not replace the HTML/CSS/JavaScript
renderer with native widgets. Browser mode remains the default and requires no
native companion package.

## Support Tier

The first release supports these combinations:

| Language | Companion | Platform |
| --- | --- | --- |
| Python 3.11+ | `rti-demo-ui-native` 0.4.x with pywebview 6.2.1 | Ubuntu 22.04+ with GTK 3 and WebKitGTK 4.1 |
| C++17 | `rti_demo_ui_native::native_webview` 0.4.x with webview 0.12.0 | Ubuntu 22.04+ with GTK 3 and WebKitGTK 4.1 |

The release gates run on x86-64 Ubuntu 22.04 under Xvfb, D-Bus, and Mesa.
Windows and macOS are unsupported in this release because their real engines
have not passed the fixed conformance gates. Use browser mode on unsupported
platforms.

## Linux Prerequisites

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

## Python Installation and Use

Download the core and companion wheels attached to a GitHub release, then
install both local files. The project does not publish them to a package index:

```bash
gh release download v0.4.0 --repo wcoleman-rti/rti-demo-ui \
  --pattern '*.whl' --dir dist
.venv/bin/pip install dist/rti_demo_ui-0.4.0-py3-none-any.whl \
  dist/rti_demo_ui_native-0.4.0-py3-none-any.whl
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
the persistent browser profile. `async_main` runs on the app's owner event
loop after the server is ready. A normal return closes the window; an
exception is re-raised on the calling thread after cleanup.

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

The executable filename is the first-release C++ application identity.
Packagers must give unrelated applications distinct executable filenames.
Moving an executable without renaming it retains its profile; renaming it
selects a new one.

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

Python stores its profile under
`$XDG_DATA_HOME/rti-demo-ui-native/<application-id>`, falling back to the
standard `~/.local/share` data root. C++ stores persistent cookies under
`$XDG_DATA_HOME/rti-demo-ui-native/<executable-filename>/cookies.sqlite`, with
the same standard data-root fallback.

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

Closing the window, stopping the app, or sending `SIGINT`/`SIGTERM` performs
normal cleanup and joins the managed server and watcher contexts. Python
restores the process's previous signal handlers after `run_native` returns;
C++ does the same after `native::run`.

Common failures:

- **Supported only on Linux**: use external browser mode on macOS or Windows.
- **Missing pywebview 6.2.1**: install `rti-demo-ui-native` and the Python
  system prerequisites above in the active environment.
- **GTK/WebKitGTK initialization failure**: install the 4.1 development/runtime
  packages and launch from a graphical session. CI needs both Xvfb and a D-Bus
  session.
- **Invalid application ID**: use a lowercase reverse-DNS value such as
  `com.example.demo`.
- **Literal loopback required**: leave the host at `127.0.0.1` or use `::1`;
  `localhost` and remote bind addresses are intentionally rejected.
- **Profile cannot be created**: verify that `XDG_DATA_HOME`, when set, is an
  absolute writable path.
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
