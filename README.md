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

## Start with Python

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
python examples/py/simple.py
```

Open the URL printed by the example. Python 3.11 or newer is required.

## Start with C++

```bash
cmake -B build
cmake --build build
./build/cpp/examples/rti_demo_ui_simple
```

C++17 and a network connection for the first dependency fetch are required.

## Start with Python native webview

Native mode is optional. These Python commands target Ubuntu 26.04 with Python
3.13+, using the distro's PyGObject binding. The virtual environment includes
system packages so it can import `gi`:

```bash
sudo apt install python3-gi gir1.2-gtk-3.0 gir1.2-webkit2-4.1
python -m venv --system-site-packages .venv
source .venv/bin/activate
pip install -e . -e native/python
python native/python/examples/dual_mode.py --native
```

Use `--browser` instead of `--native` to run either dual-mode example in a
browser.

## Start with C++ native webview

The C++ native companion builds against the host's GTK and WebKitGTK
development libraries:

```bash
sudo apt install \
  build-essential cmake pkg-config \
  gir1.2-gtk-3.0 gir1.2-webkit2-4.1 \
  libgtk-3-dev libwebkit2gtk-4.1-dev
cmake -B build \
  -DRTI_DEMO_BUILD_NATIVE_WEBVIEW=ON \
  -DRTI_DEMO_BUILD_EXAMPLES=ON
cmake --build build --parallel
./build/native/examples/rti_demo_ui_native_dual_mode --native
```

For Python 3.11/3.12, other supported platforms, and detailed troubleshooting,
see the [native webview guide](docs/native-webview.md).
Set `listening_message_prefix` on `DemoUiApp` to customize the startup URL
announcement, or to `None` in Python / `std::nullopt` in C++ to suppress it;
see the [Python](docs/api/python.md) and [C++](docs/api/cpp.md) guides.

Install both local projects from this checkout with
`pip install -e . -e native/python`. Python package extras declare dependencies;
they do not include a sibling local project in the distribution. The companion
also depends on the core package, so making the core package depend back on it
would create a dependency cycle. Keeping the companion separate lets
browser-only users avoid native dependencies.

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
