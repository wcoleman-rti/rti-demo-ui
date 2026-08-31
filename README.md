# RTI Demo UI

A small UI SDK designed for local RTI Connext DDS demos, without linking to or
depending on Connext itself. It has one shared browser frontend and two
interchangeable state servers: Python 3.11+ with native
`asyncio`/`aiohttp`, and C++17 (pinned `cpp-httplib` + `nlohmann/json` via
CMake `FetchContent`). See [docs/architecture.md](docs/architecture.md)
for the full design. Direct third-party dependencies and licenses are listed
in [docs/third-party.md](docs/third-party.md).

Each backend owns the authoritative component model (`DemoUiApp`, `Card`,
`Scene2DViewport`, `Scene3DViewport`, generic state components, and custom
components) and serves
an identical v2 JSON snapshot; the browser owns DOM/SVG rendering via the
supported `/sdk/client.js` transport and shared `runtime.js`. Scene3D is an
opt-in dynamic import of the bundled `/sdk/runtime3d.js`; ordinary pages never
load Three.js. There is no Node.js process or DDS dependency at runtime.

## Quick usage

Python:

```python
import asyncio

from rti_demo_ui import DemoUiApp


async def main() -> None:
  app = DemoUiApp(title="Fleet Telemetry")
  scene = app.add_card("Vehicles").add_scene_2d(
    width=600, height=400, bounds=(-100.0, 100.0, -100.0, 100.0)
  )
  scene.add_entity("vehicle-1", x=0.0, y=0.0, heading=0.0)

  try:
    await app.run()
  finally:
    await app.stop()


asyncio.run(main())
```

The built-in page supports governed `dark`/`light` themes and `auto`, `grid-2`,
`grid-3`, and `sidebar-main` layouts. See the language API guides for
constructor and live mutation examples.

C++:

```cpp
#include <rti_demo_ui/rti_demo_ui.hpp>

int main() {
  using namespace rti::demo::ui;

  DemoUiApp app("Fleet Telemetry");
  auto* scene = app.add_card("Vehicles")->add_scene_2d(
    600, 400, {-100.0, 100.0, -100.0, 100.0});
  scene->add_entity("vehicle-1", 0.0, 0.0, 0.0);

  app.run();
}
```

See [examples/py/simple.py](examples/py/simple.py) and
[examples/cpp/simple.cpp](examples/cpp/simple.cpp) for animation and graceful
interactive shutdown.

Run the application-owned gallery in any governed presentation:

```bash
PYTHONPATH=python python examples/py/gallery.py --theme light --layout grid-3
./build/cpp/examples/rti_demo_ui_gallery --theme dark --layout sidebar-main
```

## Arm 3D pilot

The application-owned arm pilot serves a deterministic GLB and updates five
mock joint targets without DDS or a Node.js development server:

```bash
PYTHONPATH=python python examples/py/arm3d.py
./build/cpp/examples/rti_demo_ui_arm3d
```

Open the printed URL. The model, stable node paths, coordinate conventions,
fallback behavior, and replacement guidance are documented in
[examples/web/arm3d/README.md](examples/web/arm3d/README.md).

## Repository layout

```text
assets/       canonical index.html, runtime.js, runtime3d.js, client.js, theme.css
cpp/          C++17 SDK core (rti_demo_ui::core)
python/       Python 3.11+ SDK source (rti_demo_ui)
examples/     simple, gallery, and guarded Connext examples per language
tests/        cpp (CTest), py (pytest model/HTTP), browser (Playwright)
docs/         architecture, API, frontend, lifecycle, and contributor guides
```

## Python

```bash
pip install -e .                  # editable install
pip install -e '.[dev]'           # + test, browser, and commit tooling
# Pins: pytest 8.4.2, pytest-asyncio 1.4.0
pre-commit install --install-hooks # install and provision checks before commits
# One-time browser binary download, needed for tests/browser.
playwright install chromium
python examples/py/simple.py      # runs the asyncio app and prints its URL
```

## C++

```bash
cmake -S . -B build -DBUILD_TESTING=ON
cmake --build build
ctest --test-dir build
./build/cpp/examples/rti_demo_ui_simple
```

`cmake -S . -B build -DBUILD_TESTING=ON` fetches pinned, MIT-licensed
dependencies on first configure (network required only when the `FetchContent`
cache is empty):

- [`yhirose/cpp-httplib`](https://github.com/yhirose/cpp-httplib) v0.18.3 (MIT)
- [`nlohmann/json`](https://github.com/nlohmann/json) v3.11.3 (MIT)

`RTI_DEMO_BUILD_EXAMPLES` defaults ON for a top-level build; consuming
projects that `add_subdirectory(cpp)` get it OFF by default and link
`rti_demo_ui::core` directly.

## Opening the SDK app

Both backends bind literal loopback `127.0.0.1` on port `0` by default and print
the actual URL after binding. Use `ReadyInfo` when code needs the selected port.
Open that URL in a normal browser, VS Code Simple Browser, or a forwarded
Codespaces port — no separate frontend process is required. The gallery example
passes its own `examples/web/gallery` directory as `static_root` and serves at
`/`.

## Custom frontends

Pass an application-owned directory containing `index.html` as `static_root`.
The SDK keeps `/sdk/index.html`, `/sdk/runtime.js`, `/sdk/runtime3d.js`,
`/sdk/client.js`, `/sdk/theme.css`,
`/api/health`, and `/api/state` reserved in both modes. Other paths resolve
under the validated static root; traversal, absolute paths, directories, and
symlinks escaping the root are rejected. Unknown `/api/` paths return JSON 404;
unknown `/sdk/` paths return static 404. See
[docs/custom-frontends.md](docs/custom-frontends.md) for the complete route,
MIME, security, and CSS compatibility contract.

The canonical CSS is always available at `/sdk/theme.css`; application pages
should load it rather than copy `assets/theme.css`. The built-in HTML and
gallery use `/sdk/runtime.js` and `/sdk/theme.css`.

## Packaging and CMake consumption

The root `pyproject.toml` maps the `python/` source directory and stages the
canonical root assets into the package at build time. Wheel and source
distribution installs load built-in assets from package resources and do not
need a repository checkout. Editable installs expose the same assets through a
development link. Application-owned frontend directories are not included in
the SDK package.

For C++, link `rti_demo_ui::core` from `cpp/` with `add_subdirectory()` and
pass a deployed frontend directory to the `DemoUiApp` `static_root` argument.
The C++ library embeds all five SDK assets and never uses
`cpp-httplib::set_mount_point()`.

## Optional Connext examples

`examples/py/connext.py` requires `rti.connextdds`/`rti.types` (RTI Connext
Professional 7.7.0), installed separately — it is never an SDK runtime
dependency.

`examples/cpp/connext.cpp` is built only with `BUILD_CONNEXT_EXAMPLE=ON` and
requires an installed RTI Connext Professional 7.7.0 and `CONNEXTDDS_DIR` (or
`$NDDSHOME`) pointing at it:

```bash
cmake -S . -B build-connext \
  -DBUILD_CONNEXT_EXAMPLE=ON \
  -DCONNEXTDDS_DIR=/opt/rti.com/rti_connext_dds-7.7.0
cmake --build build-connext
```

IDL-to-C++ code generation uses
[`rticommunity/rticonnextdds-cmake-utils`](https://github.com/rticommunity/rticonnextdds-cmake-utils)
(pinned commit), not handwritten `rtiddsgen` invocations. Default builds
never discover Connext or fetch this utility.

## Shutdown responsibilities

Python uses `await app.run()` and `await app.stop()`; `stop()` is idempotent,
waits for aiohttp cleanup, and the app instance is single-use. Python model
mutations are synchronous during configuration and must run on the owner event
loop after startup. Foreign threads must schedule work with
`loop.call_soon_threadsafe`. C++ retains its blocking, thread-safe lifecycle
and SDK timer API. Applications that start their own DDS/worker threads must
join those workers themselves before destroying `DemoUiApp`.
The SDK does not install process-global signal handlers. Python examples catch
`asyncio.CancelledError`; C++ examples use an example-local controller, so
terminal Ctrl-C is a normal interactive exit path without a traceback.

See [docs/lifecycle.md](docs/lifecycle.md) for startup, cancellation, worker
ownership, and platform-specific control behavior.

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

For public API examples, see [docs/api/python.md](docs/api/python.md) and
[docs/api/cpp.md](docs/api/cpp.md). Contributor setup and the implementation
plan policy are in [docs/development/contributing.md](docs/development/contributing.md).
