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

Use the built-in frontend for fast demos, provide a custom frontend when needed,
or opt into a native Linux window. The core SDK does not require Connext,
Node.js, or a separate frontend process at runtime.

## Start with Python

```bash
python -m pip install -e .
python examples/py/simple.py
```

Open the URL printed by the example. Python 3.11 or newer is required.

## Start with C++

```bash
cmake -S . -B build
cmake --build build --target rti_demo_ui_simple
./build/cpp/examples/rti_demo_ui_simple
```

C++17 and a network connection for the first dependency fetch are required.

## What you can build

- Dashboards using tables, metrics, text, badges, logs, and governed layouts.
- Live 2D scenes and glTF-based 3D scenes.
- Custom browser frontends using polling or server-sent events.
- Validated browser commands and application-owned JSON state.
- Optional native Linux windows through separate Python and C++ companions.

Explore the [Python examples](examples/py), [C++ examples](examples/cpp), or the
[Arm 3D example](examples/web/arm3d/README.md). Optional Connext examples show
how to connect DDS data without adding Connext to the core SDK.

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
