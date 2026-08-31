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

# Contributing

## Setup

Use Python 3.11 or newer and install the contributor tools from the
repository root:

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
pre-commit install --install-hooks
```

The aggregate development extra includes the focused `test`, `browser`, and
`lint` toolsets used by CI, plus the contributor hooks. It pins
`pytest==8.4.2` and `pytest-asyncio==1.4.0`; these versions support Python
3.11+ and avoid the Python 3.14 event-loop policy deprecation warnings emitted
by older `pytest-asyncio` releases.

The C++ configure step fetches pinned `cpp-httplib` and `nlohmann/json` only
when the local CMake cache does not already contain them.

## Build and Test

```bash
cmake -S . -B build -DBUILD_TESTING=ON
cmake --build build
ctest --test-dir build --output-on-failure
PYTHONPATH=python .venv/bin/python -m pytest tests/py -q
.venv/bin/pre-commit run --all-files
```

Browser tests require the Playwright browser binary:

```bash
.venv/bin/playwright install chromium
PYTHONPATH=python .venv/bin/python -m pytest tests/browser -q
```

The scene3d browser coverage additionally verifies the reproducible bundled
runtime and launches the C++ arm example. Use the pinned Node version from
`tools/scene3d/package.json` and run the same prerequisites locally:

```bash
node --version
(cd tools/scene3d && npm ci --ignore-scripts && npm run build:runtime3d)
sha256sum --check assets/runtime3d.sha256
git diff --exit-code -- assets/runtime3d.js assets/runtime3d.sha256
cmake -S . -B build-browser -DBUILD_TESTING=OFF -DRTI_DEMO_BUILD_EXAMPLES=ON
cmake --build build-browser --target rti_demo_ui_arm3d --parallel
export RTI_DEMO_CPP_ARM3D="$(find build-browser -type f \
	-name rti_demo_ui_arm3d -perm -111 -print -quit)"
[[ -n "$RTI_DEMO_CPP_ARM3D" ]]
RTI_DEMO_CPP_ARM3D="$PWD/$RTI_DEMO_CPP_ARM3D" \
	PYTHONPATH=python .venv/bin/python -m pytest tests/browser -q
```

This builds Node assets only; the browser test launches the C++ executable and
does not require a Node development server. The C++ path must be present, so
the browser suite does not silently skip its cross-language assertions.

The C++ and Python HTTP tests load the shared route vectors from
`tests/fixtures/static_route_vectors.json`. Add behavior there first when a
route contract changes, then update both language tests.

## Documentation

`docs/architecture.md` records durable cross-language design and invariants.
`docs/api/` contains conceptual usage guides. `docs/development/` documents
contributor workflow. Decision-bearing implementation plans belong in
`docs/development/implementation-plans/`; temporary notes do not.

The hosted documentation requires CMake, Doxygen, and the Python documentation
extra. Build the same warning-as-error site produced by CI from the repository
root:

```bash
python -m pip install -e '.[docs]'
cmake -S docs -B build/docs
cmake --build build/docs --target docs
```

Open `build/docs/html/index.html` to inspect the result. The documentation build
generates C++ XML from the public headers before Sphinx renders the Markdown
guides and Python/C++ API references.

Start product-facing implementation and planning sessions with
`docs/development/product-use-cases.md`. It records the representative demo
workflows, graphical vocabulary, capability status, product boundaries, and
agent-session checklist that should drive feature scope and acceptance tests.

Keep public names, route tables, package commands, and examples synchronized.
Do not add compatibility aliases for removed public APIs. Run pre-commit after
editing Markdown, CMake, examples, or source files.
