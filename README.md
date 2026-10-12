<!--
  (c) 2026 Copyright, Real-Time Innovations, Inc.  All rights reserved.

  RTI grants Licensee a license to use, modify, compile, and create derivative
  works of the Software.  Licensee has the right to distribute object form
  only for use with RTI products.  The Software is provided "as is", with no
  warranty of any type, including any warranty for fitness for any purpose.
  RTI is under no obligation to maintain or support the Software.  RTI shall
  not be liable for any incidental or consequential damages arising out of the
  use or inability to use the software.
-->

# RTI Demo UI

Build local browser interfaces for RTI Connext DDS demos from Python or C++.
Applications define cards and stateful components; RTI Demo UI serves the
shared frontend and handles browser updates. Connext integration is optional
and remains application-owned.

Use the built-in frontend for fast demos, provide a custom frontend when
needed, or opt into a native window through separate Python and C++
companions. The core SDK does not require Connext, Node.js, or a separate
frontend process at runtime.

## Prerequisites

- Python 3.11 or newer for Python examples.
- A C++17 compiler and CMake for C++ examples.
- A network connection for the first CMake configure, which fetches pinned
  dependencies.

Browser mode is the default and needs no native webview packages. Native mode
uses the operating system's webview and has additional platform prerequisites,
listed below.

## Start with Python in a browser

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
python examples/py/simple.py
```

On Windows PowerShell, activate the environment with
`.venv\Scripts\Activate.ps1`. Open the URL printed by the example.

## Start with C++ in a browser

```bash
cmake -B build
cmake --build build
./build/cpp/examples/rti_demo_ui_simple
```

## Native webview prerequisites

Install only the native prerequisites for the platform and language you plan
to use. The general compiler and CMake requirements above also apply to C++
native builds.

| Platform | Python native webview | C++ native webview |
| --- | --- | --- |
| Ubuntu 22.04/24.04 | Python 3.11/3.12: install the PyGObject build prerequisites from the [native guide](docs/native-webview.md#linux). | `sudo apt install libwebkit2gtk-4.1-dev` |
| Ubuntu 26.04+ | Install `python3-gi` and `gir1.2-webkit2-4.1`; create the venv with `--system-site-packages` so it can import the distro's `gi` binding. | `sudo apt install libwebkit2gtk-4.1-dev` |
| Windows 10/11 | Install the Evergreen WebView2 Runtime if absent: `winget install --id Microsoft.EdgeWebView2Runtime --exact`. Pip installs pywebview and pythonnet. | Install Visual Studio 2022 with the C++ workload and Windows SDK using Visual Studio Installer. Install the Evergreen WebView2 Runtime if absent: `winget install --id Microsoft.EdgeWebView2Runtime --exact`. |
| macOS 14+ (Apple Silicon) | No separate webview package; pip installs pywebview's Cocoa dependencies. | WebKit and AppKit are built in. Install Apple's C++ command-line tools if needed: `xcode-select --install`. |

Ubuntu 22.04/24.04 Python native setup also requires development headers for
the selected Python. See the [native webview guide](docs/native-webview.md)
for exact prerequisites, supported versions, and troubleshooting.

## Start with Python native webview

On Ubuntu 26.04+, create the environment with
`python -m venv --system-site-packages .venv` so it can import the distro's
PyGObject binding. Use the regular venv command on other platforms.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e . -e native/python
python native/python/examples/dual_mode.py --native
```

On Windows PowerShell, activate the environment with
`.venv\Scripts\Activate.ps1`. The native Python companion is a separate local
project, so install both it and the core package. The Ubuntu `python3-webview`
package currently provides pywebview 6.1, while the companion pins 6.2.1; pip
installs the pinned version. Use `--browser` instead of `--native` to run this
example in a browser.

## Start with C++ native webview

```bash
cmake -B build \
  -DRTI_DEMO_BUILD_NATIVE_WEBVIEW=ON \
  -DRTI_DEMO_BUILD_EXAMPLES=ON
cmake --build build --parallel
./build/native/examples/rti_demo_ui_native_dual_mode --native
```

Set `listening_message_prefix` on `DemoUiApp` to customize the startup URL
announcement, or to `None` in Python / `std::nullopt` in C++ to suppress it;
see the [Python](docs/api/python.md) and [C++](docs/api/cpp.md) guides.

## What you can build

- Dashboards using tables, metrics, text, badges, logs, and governed layouts.
- Live 2D scenes and glTF-based 3D scenes.
- Custom browser frontends using polling or server-sent events.
- Validated browser commands and application-owned JSON state.
- Optional native windows through separate Python and C++ companions. Linux is
  release-supported; see the
  [native support matrix](docs/native-webview.md#support-and-qualification) for
  Windows and macOS qualification status.

Explore the focused [example catalog](examples/README.md) for Python and C++
references covering components, application data, commands, scenes, layouts,
and optional Connext integration.

## Packaging and CMake consumption

For C++, link `rti_demo_ui::core` from `cpp/` with `add_subdirectory()`, or use
the Linux C++ development bundle attached to a matching GitHub Release:

```bash
tar -xzf rti-demo-ui-cpp-0.4.1-linux-x86_64-gcc11.tar.gz
cmake -S . -B build \
  -DCMAKE_PREFIX_PATH="$PWD/rti-demo-ui-cpp-0.4.1-linux-x86_64-gcc11"
```

```cmake
find_package(rti_demo_ui CONFIG REQUIRED)
target_link_libraries(my_app PRIVATE rti_demo_ui::core)
```

The bundle contains the static library, public headers, pinned header-only
dependencies, CMake package metadata, and applicable licenses. It targets
Ubuntu 22.04 x86_64 with GCC 11. Other platforms should build from the tagged
source until they are covered by routine CI and release testing. The optional
native C++ companion remains source-build-only because its GTK/WebKit runtime
ABI is system-specific.

Each stable `vX.Y.Z` tag publishes the two Python wheels and source
distributions, the C++ development bundle, `SHA256SUMS`, and GitHub artifact
attestations for the release artifacts. Packages are not uploaded to PyPI or
another hosted package repository. The release workflow can be run manually
to build and verify the complete artifact set without publishing a release.

## Documentation

- [Documentation home](https://wcoleman-rti.github.io/rti-demo-ui/)
- [Python guide](https://wcoleman-rti.github.io/rti-demo-ui/api/python.html) and
  [API reference](https://wcoleman-rti.github.io/rti-demo-ui/reference/python.html)
- [C++ guide](https://wcoleman-rti.github.io/rti-demo-ui/api/cpp.html) and
  [API reference](https://wcoleman-rti.github.io/rti-demo-ui/reference/cpp.html)
- [Custom frontends](https://wcoleman-rti.github.io/rti-demo-ui/custom-frontends.html)
- [Native webview mode](https://wcoleman-rti.github.io/rti-demo-ui/native-webview.html)
- [Examples](examples) and
  [contributing](https://wcoleman-rti.github.io/rti-demo-ui/development/contributing.html)

See [third-party notices](docs/third-party.md) for dependency and license
details.
