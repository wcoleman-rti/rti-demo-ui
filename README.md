# RTI Demo GUI SDK Core

A small GUI SDK for local RTI Connext demos with one shared browser frontend
and two interchangeable state servers: Python 3.10+ (`ThreadingHTTPServer`,
standard library only) and C++17 (pinned `cpp-httplib` + `nlohmann/json` via
CMake `FetchContent`). See [docs/architecture.md](docs/architecture.md)
for the full design.

Each backend owns the authoritative component model (`CoreApp`, `Card`,
`Scene2DViewport`) and serves an identical JSON snapshot; the browser owns
DOM/SVG rendering via one shared `runtime.js`. There is no Node.js process,
frontend build step, or DDS dependency in the SDK itself.

## Repository layout

```text
assets/       canonical index.html, runtime.js, theme.css, gallery.html
cpp/          C++17 SDK core (rti_demo_gui_sdk::core)
python/       Python 3.10+ SDK core (rti_demo_gui_sdk)
examples/     simple, gallery, and guarded Connext examples per language
tests/        cpp (CTest), py (pytest model/HTTP), browser (Playwright)
docs/         implementation plan
```

## Python

```bash
pip install -e ./python           # editable install (required in v1)
pip install -e './python[dev]'    # + pytest, playwright, clang-format, pre-commit
pre-commit install --install-hooks # install and provision checks before commits
# One-time browser binary download, needed for tests/browser.
playwright install chromium
python examples/py/simple.py      # prints the URL to open, then blocks
```

Editable install is required because canonical assets are read from
`assets/` at the repository root; wheel/sdist packaging is deferred.

## C++

```bash
cmake -S cpp -B build -DBUILD_TESTING=ON
cmake --build build
ctest --test-dir build
./build/examples/rti_demo_gui_sdk_simple
```

`cmake -S cpp -B build` fetches pinned, MIT-licensed dependencies on first
configure (network required only when the `FetchContent` cache is empty):

- [`yhirose/cpp-httplib`](https://github.com/yhirose/cpp-httplib) v0.18.3 (MIT)
- [`nlohmann/json`](https://github.com/nlohmann/json) v3.11.3 (MIT)

`RTI_DEMO_BUILD_EXAMPLES` defaults ON for a top-level build; consuming
projects that `add_subdirectory(cpp)` get it OFF by default and link
`rti_demo_gui_sdk::core` directly.

## Opening the SDK app

Both backends bind `0.0.0.0:8080` by default and print their URL on `run()`.
Open that URL in a normal browser, VS Code Simple Browser, or a forwarded
Codespaces port — no separate frontend process is required. `/gallery`
demonstrates every shared CSS component.

## Optional Connext examples

`examples/py/connext.py` requires `rti.connextdds`/`rti.types` (RTI Connext
Professional 7.7.0), installed separately — it is never an SDK runtime
dependency.

`examples/cpp/connext.cpp` is built only with `BUILD_CONNEXT_EXAMPLE=ON` and
requires an installed RTI Connext Professional 7.7.0 and `CONNEXTDDS_DIR` (or
`$NDDSHOME`) pointing at it:

```bash
cmake -S cpp -B build-connext \
  -DBUILD_CONNEXT_EXAMPLE=ON \
  -DCONNEXTDDS_DIR=/opt/rti.com/rti_connext_dds-7.7.0
cmake --build build-connext
```

IDL-to-C++ code generation uses
[`rticommunity/rticonnextdds-cmake-utils`](https://github.com/rticommunity/rticonnextdds-cmake-utils)
(pinned commit), not handwritten `rtiddsgen` invocations. Default builds
never discover Connext or fetch this utility.

## Shutdown responsibilities

`CoreApp.stop()` is idempotent: it stops accepting new mutations/timers,
wakes `run()`, cancels and joins SDK-owned timers, and waits for in-flight
HTTP handlers before returning. Destructors call `stop()`. Applications that
start their own DDS/worker threads must join those workers themselves after
`run()` returns and before destroying `CoreApp`.

## Quality gates

```bash
pre-commit run --all-files  # ruff, clang-format, whitespace/YAML checks
PYTHONPATH=python pytest tests/py                       # model + HTTP contract
# Playwright; first run `playwright install chromium`.
PYTHONPATH=python pytest tests/browser
cmake --build build && ctest --test-dir build            # C++ model + HTTP contract
```

`clang-format` and `pre-commit` come from the `dev` extra (no system
package/sudo required); `pre-commit` picks `clang-format` up from the active
virtualenv.
