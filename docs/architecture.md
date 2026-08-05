# RTI Demo UI Architecture

## 1. Objective

Build a small GUI SDK for local RTI Connext demos with one browser frontend and
two interchangeable state servers:

- Python 3.11+ using native `asyncio` and `aiohttp`.
- C++17 using pinned `cpp-httplib`, acquired with CMake `FetchContent`.
- SDK-owned `index.html`, `runtime.js`, and `theme.css` shared byte-for-byte by
  both backends.

The browser owns DOM, SVG, and animation. Each backend owns the authoritative
component model and exposes the same JSON snapshot. This gives SDK components
identical markup, appearance, and behavior without Wt, NiceGUI, GTK, Qt, or
duplicated frontends.

The initial component set is deliberately small:

- `DemoUiApp`: model ownership and local HTTP lifecycle.
- `Card`: titled grouping.
- `Scene2DViewport`: entities and directed links in a bounded 2D scene.

## 2. Scope Guardrails

V1 targets single-process, single-developer demos viewed through a normal
browser, VS Code Simple Browser, or a forwarded Codespaces port.

Out of scope:

- Authentication, TLS termination, public deployment, and multi-user sessions.
- A general-purpose widget framework or arbitrary server-side widget handles.
- DDS-specific types or behavior in the SDK library.
- WebSocket/SSE transport, deltas, and command routes before measurements
  require them.
- 3D, charting, graph layout, and high-volume canvas rendering.
- Automatic browser launch and fixed assumptions about repository-relative
  runtime paths.

The SDK sends semantic state, never pre-rendered SVG, DOM fragments, animation
frames, or DDS objects.

## 3. Architecture

### 3.1 Runtime Flow

The demo executable is also the local web server; users start exactly one Python
or C++ process. Python `await app.run()` starts the embedded aiohttp server and
waits, while C++ `app.run()` starts its blocking server. Both print the URL
after binding. There is no Node.js process, frontend build/watch command, or
separately managed web server. Stopping the app stops its HTTP server; only
C++ also owns SDK timers.

1. Application code creates `DemoUiApp`, cards, and scenes.
2. Python application coroutines mutate the model on the owner event loop;
   C++ application or DDS worker threads use the thread-safe SDK methods.
3. Every successful mutation increments one application-wide `revision`.
4. `GET /api/state` copies a consistent snapshot before serializing it.
5. The browser polls every 200 ms and skips reconciliation when `revision` is
   unchanged.
6. `runtime.js` reconciles SDK-owned DOM/SVG and uses `requestAnimationFrame()`
   to interpolate entity movement between snapshots.

Start with full snapshots. Add bounded revision history and `?since=<revision>`
only after profiling demonstrates a real payload or latency problem. A
missing/expired revision must fall back to a full snapshot.

### 3.2 Ownership

- `DemoUiApp` exclusively owns cards and scenes.
- Python returns ordinary object references.
- C++ stores `std::unique_ptr<Card>` and each card stores
  `std::unique_ptr<Scene2DViewport>`; factory methods return non-owning pointers
  valid until `DemoUiApp` destruction.
- Python model state is owned by the event loop and owner thread captured by
  `run()`; foreign threads must use `loop.call_soon_threadsafe`.
- C++ uses one model mutex to protect the complete model and revision.
- HTTP handlers never retain pointers/references into mutable model storage
  after taking a snapshot.
- Browser state is disposable; refreshing reconstructs it from the next
  snapshot.

### 3.3 Extension Boundary

Tier 1 is the server/runtime infrastructure. Tier 2 is the shared component
model (`Card`, `Scene2DViewport`). Tier 3 is application-owned browser markup
using documented CSS classes.

A new Tier 2 component is justified only when all are true:

1. At least two independent demos need it.
2. Shared state semantics or rendering code are required.
3. HTML plus a documented CSS class is insufficient.
4. The state can be represented generically without a Connext dependency.

Consuming projects may serve their own assets or pages. Those pages are outside
SDK API parity and must not alter the fixed SDK routes.

## 4. Repository Layout

```text
assets/
  index.html
  runtime.js
  theme.css
cpp/
  CMakeLists.txt
  include/rti_demo_ui/
    demo_ui_app.hpp
    components.hpp
    types.hpp
    gui_sdk.hpp
  src/
    app.cpp
    components.cpp
    web_assets.hpp.in
python/
  README.md
  rti_demo_ui/
    __init__.py
    demo_ui_app.py
    components.py
    types.py
examples/
  web/gallery/index.html
  cpp/{CMakeLists.txt,simple.cpp,connext.cpp,gallery.cpp,VehicleState.idl}
  py/{simple.py,connext.py,gallery.py}
tests/
  cpp/
  py/
  browser/
docs/
  architecture.md
  custom-frontends.md
  lifecycle.md
  api/{cpp.md,python.md}
  development/
    contributing.md
    implementation-plans/
      custom_frontend_and_lifecycle.md
README.md
.pre-commit-config.yaml
```

## 5. Shared Browser Contract

### 5.1 Routes

In built-in UI mode, both backends implement exactly:

| Request | Response | Cache policy |
| --- | --- | --- |
| `GET /` | canonical `index.html` | `no-cache` |
| `GET /sdk/index.html` | canonical HTML | `no-cache` |
| `GET /sdk/runtime.js` | canonical JavaScript | `no-cache` |
| `GET /sdk/theme.css` | canonical CSS | `no-cache` |
| `GET /api/health` | `{"status":"ok"}` | `no-store` |
| `GET /api/state` | snapshot below | `no-store` |

With an application-owned static root, `/` and non-reserved file paths resolve
under that root. The `/api/` and `/sdk/` prefixes remain reserved; SDK assets
are available at `/sdk/index.html`, `/sdk/runtime.js`, and `/sdk/theme.css`.

Unknown routes return JSON error `{"error":"not found"}` with HTTP 404.
Unsupported methods return HTTP 405. API failures return JSON; asset failures
are startup errors, not request-time fallbacks. Add `Content-Type`,
`Content-Length`, and `X-Content-Type-Options: nosniff` to every response. V1
does not implement conditional requests or return 304.

Servers bind to `0.0.0.0:8080` by default. Constructor validation rejects an
empty host and ports outside 1-65535. Port conflicts fail loudly. No permissive
CORS header is needed because assets and API are same-origin.

### 5.2 Asset Delivery

Python loads canonical SDK assets from package resources during `DemoUiApp`
construction and raises a path-specific `RuntimeError` if any is missing.

CMake reads the same files at configure time and generates private
`web_assets.hpp`. The executable performs no runtime asset lookup. Use one fixed
raw-string delimiter per asset and fail configuration if source text contains
its delimiter. Tests compare bytes returned by both servers with the canonical
source files.

Static-root resolution decodes and validates paths, rejects traversal and
root-escaping symlinks, serves regular files only, and uses an explicit MIME
map. Unknown static files return a plain 404; unknown reserved API paths return
the JSON 404 above.

### 5.3 Snapshot Schema

The authoritative JSON shape is:

```json
{
  "schema_version": 1,
  "revision": 42,
  "title": "Fleet Demo",
  "cards": [
    {
      "id": "card-1",
      "title": "Fleet Telemetry",
      "components": [
        {
          "type": "scene2d",
          "id": "scene-1",
          "width": 600,
          "height": 400,
          "grid_bounds": [-100.0, 100.0, -100.0, 100.0],
          "entities": [
            {
              "id": "vehicle-1",
              "x": 12.0,
              "y": -4.0,
              "heading": 90.0,
              "color": "#59C2FF",
              "status": "success",
              "freshness": "fresh"
            }
          ],
          "links": [
            {"source_id": "vehicle-1", "target_id": "vehicle-2", "status": "warning"}
          ]
        }
      ]
    }
  ]
}
```

Rules:

- `schema_version` is integer `1`; incompatible versions fail visibly in the
  browser.
- IDs are generated as `card-<monotonic integer>` and
  `scene-<monotonic integer>` and remain stable for the process lifetime.
- Arrays preserve creation order; entities preserve insertion order; links
  preserve insertion order.
- JSON contains finite numbers only. Serialization must never emit NaN or
  infinity.
- Strings are escaped by a structured JSON serializer, not concatenation. Python
  uses `json.dumps(..., allow_nan=False)`. C++ uses `nlohmann/json`, pinned with
  `FetchContent`.
- Unknown future object fields are ignored by the browser. Unknown `type` values
  render a visible unsupported-component error and do not stop other components.

### 5.4 Browser Rendering

`runtime.js` starts after `DOMContentLoaded`, immediately requests state, then
polls every 200 ms with one request in flight at a time. A failed request shows
a connection banner and retries with capped backoff of 0.5, 1, 2, then 5
seconds. Recovery clears the banner.

Reconcile by stable IDs. Do not replace the complete document or scene SVG on
every poll. Preserve the previous and target entity poses; interpolate only `x`,
`y`, and heading over the polling interval. Status, freshness, links, additions,
and removals apply on receipt. Normalize heading interpolation across the
shortest angular path. Respect `prefers-reduced-motion` by applying target poses
immediately.

SVG is the v1 renderer and is expected to support tens to low hundreds of
entities. Re-evaluate Canvas for hundreds of frequently moving entities and
Three.js only for genuine 3D.

## 6. Design System

`assets/theme.css` is the only style source. Define at least:

```css
:root {
  --rti-navy: #172A3A;
  --rti-blue: #0076CE;
  --rti-light-blue: #59C2FF;
  --sdk-bg: #111820;
  --sdk-surface: #1B2631;
  --sdk-card-bg: #22303C;
  --sdk-text: #F4F7F9;
  --sdk-muted: #AAB7C4;
  --sdk-border: #3B4A57;
  --sdk-accent: #59C2FF;
  --sdk-accent-hover: #8BD6FF;
  --sdk-success: #35C58A;
  --sdk-warning: #F4B942;
  --sdk-danger: #EF6262;
}
```

Required classes: `sdk-app`, `sdk-card`, `sdk-card-title`, `sdk-metric`,
`sdk-metric-label`, `sdk-metric-value`, `sdk-status-success`,
`sdk-status-warning`, `sdk-status-danger`, `sdk-table`, `sdk-button`,
`sdk-slider`, `sdk-connection-banner`, and `sdk-scene2d`.

`gallery.html` demonstrates metric/status text, a two-row table, a button, and a
range slider with semantic HTML. It contains no backend-specific code and does
not require command endpoints; controls may update nearby browser-only text.

## 7. Public API

### 7.1 Shared Types

```text
Severity  = success | warning | danger
Freshness = fresh | aging | stale
GridBounds = (x_min, x_max, y_min, y_max)
```

Status and freshness are generic, not DDS lifecycle/QoS types. Severity controls
marker/link color; freshness controls entity opacity: fresh `1.0`, aging `0.65`,
stale `0.35`.

### 7.2 Python

```python
class DemoUiApp:
  def __init__(
    self, title: str, port: int = 8080, host: str = "0.0.0.0",
    static_root: str | os.PathLike[str] | None = None
  ) -> None: ...
  def add_card(self, title: str) -> Card: ...
  async def run(self) -> None: ...
  async def stop(self) -> None: ...

class Card:
  def add_scene_2d(
    self, width: int, height: int, grid_bounds: GridBounds
  ) -> Scene2DViewport: ...

class Scene2DViewport:
    def add_entity(self, id: str, x: float, y: float, heading: float = 0.0,
                   color: str = "var(--sdk-accent)",
                   status: Severity = Severity.success,
                   freshness: Freshness = Freshness.fresh) -> None: ...
    def update_entity(self, id: str, x: float | None = None, y: float | None = None,
                      heading: float | None = None, status: Severity | None = None,
                      freshness: Freshness | None = None) -> None: ...
    def remove_entity(self, id: str) -> None: ...
    def add_link(self, source_id: str, target_id: str,
                 status: Severity = Severity.success) -> None: ...
    def remove_link(self, source_id: str, target_id: str) -> None: ...
```

### 7.3 C++

```cpp
using GridBounds = std::array<double, 4>;
enum class Severity { success, warning, danger };
enum class Freshness { fresh, aging, stale };

class DemoUiApp {
public:
    explicit DemoUiApp(std::string title, int port = 8080,
           std::string host = "0.0.0.0",
           std::filesystem::path static_root = {});
    ~DemoUiApp();
    Card* add_card(const std::string& title);
    TimerHandle add_timer(int interval_ms, std::function<void()> callback);
    void run();
    void stop() noexcept;
};

class Card {
public:
    Scene2DViewport* add_scene_2d(int width, int height, GridBounds bounds);
};

class Scene2DViewport {
public:
    void add_entity(const std::string& id, double x, double y,
                    double heading = 0.0,
                    std::string color = "var(--sdk-accent)",
                    Severity status = Severity::success,
                    Freshness freshness = Freshness::fresh);
    void update_entity(const std::string& id,
                       std::optional<double> x = std::nullopt,
                       std::optional<double> y = std::nullopt,
                       std::optional<double> heading = std::nullopt,
                       std::optional<Severity> status = std::nullopt,
                       std::optional<Freshness> freshness = std::nullopt);
    void remove_entity(const std::string& id);
    void add_link(const std::string& source_id, const std::string& target_id,
                  Severity status = Severity::success);
    void remove_link(const std::string& source_id, const std::string& target_id);
};
```

Both languages use `snake_case` methods and explicit parent factory methods.
There is no `.native`, `.impl()`, `post()`, or framework-specific constructor.

### 7.4 Validation Semantics

- Width/height and timer intervals are positive integers.
- Bounds, coordinates, and headings are finite; each minimum is less than its
  maximum.
- IDs and titles are non-empty.
- Colors match exactly `#[0-9A-Fa-f]{6}` or `var(--[A-Za-z0-9-]+)`.
- Entity IDs are unique within one scene.
- Links are unique directed ordered pairs; reverse links are distinct.
- Both link endpoints must exist.
- No implicit upsert: add duplicate and update/remove unknown IDs fail.
- Removing an entity removes every incoming/outgoing link in the same
  mutation/revision.
- Entity color is immutable after add in v1.

Python raises `ValueError`; C++ throws `std::invalid_argument`. Scene errors
begin `Scene2DViewport:`. Failed operations do not change state or revision.

### 7.5 Scene Geometry

For bounds `(x_min, x_max, y_min, y_max)` and SVG viewport
`(0, 0, width, height)`:

$$
p_x = \frac{x-x_{min}}{x_{max}-x_{min}}\,width, \qquad
p_y = height-\frac{y-y_{min}}{y_{max}-y_{min}}\,height
$$

Heading is finite degrees clockwise from screen-right. Draw links first as 2 px
lines with 6 px arrowheads, then entities as 6 px circles with 10 px heading
lines. Success entities use their supplied color; warning/danger override it.
Success links use `--rti-light-blue`; warning/danger use their status color.
Clip out-of-bounds entities. V1 has no labels, trails, background image, or grid
lines.

## 8. Lifecycle and Threading

### 8.1 Python

Python uses `aiohttp.web.AppRunner` and `web.TCPSite`. The app instance is
single-use and follows `NEW -> STARTING -> RUNNING -> STOPPING -> STOPPED`.
`await app.run()` captures its owner event loop and thread, binds before
printing the URL, waits on a private shutdown signal, and performs aiohttp
cleanup exactly once. `await app.stop()` is idempotent, safe before or during
startup, and schedules its shutdown operation on the owner loop when called
from another event loop. Cancellation performs the same cleanup before
propagating `CancelledError`.

Component methods remain synchronous. Configuration before startup is allowed;
after startup, mutations and snapshots verify the owner event loop and thread.
Foreign threads must schedule application-owned work with
`loop.call_soon_threadsafe`. The SDK owns no Python worker or timer tasks;
applications use `asyncio.TaskGroup` or explicitly retained tasks.

### 8.2 C++

C++ model methods are safe from any application thread; no UI-thread marshaling
exists. Each method validates inputs before acquiring the model mutex where
practical, locks once, performs one logical mutation, and increments revision
once.

`add_timer()` starts an SDK-owned periodic `std::thread` and returns a movable/
cancelable `TimerHandle`. The first callback occurs after one interval.
Exceptions are logged and stop that timer. Callbacks must be short; DDS
blocking reads belong on application-owned workers.

`run()` binds before entering the HTTP server loop. `stop()` is idempotent and
may be called from another thread or a signal handler's deferred control path.
Shutdown order:

1. Mark stopping; reject new timers and mutations with `std::runtime_error`.
2. Stop accepting HTTP requests and wake `run()`.
3. Cancel and join SDK timers. A timer must not join itself.
4. Wait for in-flight handlers to finish.
5. Return from `run()`; the consuming app then joins its DDS workers before
  `DemoUiApp` destruction.

Destructors call `stop()` and join SDK-owned threads. Application-owned workers
must not retain component pointers beyond app lifetime. Do not hold the model
mutex while serializing JSON, writing sockets, invoking callbacks, or joining
threads.

## 9. Build and Packaging

### 9.1 CMake

`cpp/CMakeLists.txt` exports `rti_demo_ui::core`. Use pinned immutable tags:

```cmake
include(FetchContent)

set(HTTPLIB_USE_OPENSSL_IF_AVAILABLE OFF CACHE BOOL "" FORCE)
set(HTTPLIB_USE_ZLIB_IF_AVAILABLE OFF CACHE BOOL "" FORCE)
set(HTTPLIB_USE_BROTLI_IF_AVAILABLE OFF CACHE BOOL "" FORCE)
set(HTTPLIB_USE_ZSTD_IF_AVAILABLE OFF CACHE BOOL "" FORCE)

FetchContent_Declare(
    cpp_httplib
    GIT_REPOSITORY https://github.com/yhirose/cpp-httplib.git
  GIT_TAG a7bc00e3307fecdb4d67545e93be7b88cfb1e186 # v0.18.3
)
FetchContent_Declare(
    nlohmann_json
    GIT_REPOSITORY https://github.com/nlohmann/json.git
  GIT_TAG 9cca280a4d0ccf0c08f47a99aa71d1b0e52f8d03 # v3.11.3
)
FetchContent_MakeAvailable(cpp_httplib nlohmann_json)

target_link_libraries(rti_demo_ui_core
    PUBLIC httplib::httplib
    PRIVATE nlohmann_json::nlohmann_json
)
```

Record both upstream versions and MIT licenses in README. Network is required
only on an empty dependency cache. `RTI_DEMO_BUILD_EXAMPLES` defaults ON only
for a top-level build; tests are top-level-only. `BUILD_CONNEXT_EXAMPLE`
defaults OFF.

### 9.2 Python

The root `pyproject.toml` requires Python 3.11+, depends directly on
`aiohttp>=3.10,<4`, and configures strict `pytest-asyncio` mode. Setuptools
maps packages from `python/`, stages canonical root assets into wheel package
data, and loads them with `importlib.resources`. `MANIFEST.in` includes the
canonical assets in source distributions. Dev extras include pytest,
pytest-asyncio, and Playwright.

### 9.3 Quality Gates

- Python: Ruff formatting/linting and pytest.
- C++: clang-format, build with warnings enabled, and CTest.
- Browser: Playwright against both server implementations using the same
  assertion module.
- Pre-commit: whitespace, EOF, YAML/TOML checks, Ruff, and clang-format.
- `clang-tidy` remains an optional documented command because it requires a
  configured compile database.

## 10. Examples

### 10.1 Simple Examples

Python and C++ examples create the same model shape: one card, one 600x400
scene, two entities, and one link. The Python example owns a 100 ms animation
coroutine in an `asyncio.TaskGroup`; C++ uses its SDK timer. Python awaits
`app.run()` and C++ blocks in `run()`. No browser is opened automatically.

### 10.2 Connext Python Example

Use Connext Professional 7.7.0 and `rti.connextdds`:

- `import rti.connextdds as dds` and `import rti.types as idl`.
- Define `VehicleState` with `@idl.struct` and typed fields.
- Create `dds.DomainParticipant`, `dds.Topic`, `dds.DataWriter`, and
  `dds.DataReader` in parent-to-child order.
- Use an in-process writer so the example runs independently.
- Use `reader.take_async()` and update the scene on the owner event loop.
- Cancel and await publisher/reader tasks before final app cleanup.

Do not add Connext to SDK runtime dependencies.

### 10.3 Connext C++ Example and IDL Generation

Guard all Connext discovery and code generation behind
`BUILD_CONNEXT_EXAMPLE=OFF`. Use `rticonnextdds-cmake-utils`, not handwritten
`rtiddsgen` commands:

```cmake
include(FetchContent)

set(RTICONNEXT_CMAKE_UTILS_GIT_TAG
  "2c4b3efef3ed87135565f5d9493303938a76da31"
  CACHE STRING ""
)
FetchContent_Declare(
    rticonnextdds_cmake_utils
    GIT_REPOSITORY https://github.com/rticommunity/rticonnextdds-cmake-utils.git
    GIT_TAG ${RTICONNEXT_CMAKE_UTILS_GIT_TAG}
)
FetchContent_MakeAvailable(rticonnextdds_cmake_utils)

find_package(RTIConnextDDS 7.7.0 REQUIRED
    COMPONENTS core
    HINTS "${CONNEXTDDS_DIR}"
)
include(ConnextDdsCodegen)
connextdds_rtiddsgen_run(
    IDL_FILE "${CMAKE_CURRENT_SOURCE_DIR}/VehicleState.idl"
    OUTPUT_DIRECTORY "${CMAKE_CURRENT_BINARY_DIR}/generated"
    LANG C++11
)

add_executable(rti_demo_ui_connext
    connext.cpp
    ${VehicleState_CXX11_SOURCES}
)
target_include_directories(rti_demo_ui_connext PRIVATE
    ${VehicleState_CXX11_INCLUDE_DIRS}
)
target_link_libraries(rti_demo_ui_connext PRIVATE
  rti_demo_ui::core
    RTIConnextDDS::cpp2_api
)
```

Pin the utility to a reviewed immutable commit. Declare DDS members in
parent-to-child order (`participant`, `topic`, `writer`, `reader`) so reverse
destruction is safe. A dedicated worker may use a WaitSet/AsyncWaitSet and
update the scene directly. Stop and join it before those members or `DemoUiApp`
are destroyed.

### 10.4 Gallery

Both `gallery.py` and `gallery.cpp` pass `examples/web/gallery` as an
application-owned static root and serve it at `/`. The page loads SDK assets
from `/sdk/theme.css` and demonstrates browser-only controls. It is not part of
SDK asset packaging or the reserved SDK routes.

## 11. Tests

### 11.1 Model Tests in Both Languages

- Constructor and method validation, including every invalid transition.
- Revision starts at zero and increments exactly once per successful logical
  mutation.
- Failed mutations leave revision and snapshot unchanged.
- Entity removal also removes related links atomically.
- Creation/insertion order is stable.
- Snapshot under concurrent mutation always parses and satisfies invariants.
- C++ stop and timer cancellation are idempotent; Python stop and cancellation
  complete aiohttp cleanup before returning.

### 11.2 HTTP Contract Tests

Run the same black-box suite against Python and C++:

- Status, content type, cache, length, and security headers for every fixed
  route.
- Canonical asset-byte equality.
- Snapshot schema/value equality for a deterministic fixture.
- 404/405 JSON errors and health response.
- Port conflict and clean shutdown behavior.
- Repeated concurrent state requests while a worker mutates the scene.

Use an ephemeral test port selected by the test harness; production default
remains 8080.

### 11.3 Browser Tests

Playwright runs the same tests against both backends at desktop and narrow
mobile viewports:

- Cards/scenes render from the snapshot without console errors.
- Coordinates, status colors, freshness opacity, link ordering, and clipping
  match the contract.
- Unchanged revisions do not rebuild scene nodes.
- Movement updates without layout shift; reduced-motion mode disables
  interpolation.
- Connection failure banner appears and clears after recovery.
- Gallery controls and responsive layout work without overlap.

Screenshot comparison is limited to SDK-owned deterministic fixtures. DOM/state
assertions remain the primary tests.

## 12. Delivery Phases

### 12.1 Existing Scaffold Migration

Do not clear or revert the repository wholesale. Preserve the directory
structure, `.clang-format`, `.gitignore`, pre-commit configuration,
`assets/theme.css`, `VehicleState.idl`, and the C++ master header as starting
points. Apply these targeted replacements before Phase 1:

- Rewrite `cpp/CMakeLists.txt` to remove Wt and embed all three SDK browser assets
  through the pinned dependencies in §9.1.
- Delete `cpp/src/theme_css.hpp.in`; replace it with
  `cpp/src/web_assets.hpp.in`.
- Configure the root `pyproject.toml` for Python 3.11+ with its aiohttp runtime
  dependency and strict asyncio test mode.
- Rename `examples/{cpp,py}/native_gallery.*` to `gallery.*`.
- Add the three missing shared browser assets and rewrite the comment-only API,
  source, example, and test scaffolds in place.

No existing functional implementation needs behavioral migration: the current
language sources and examples are placeholders. Do not preserve obsolete
Wt/NiceGUI comments or APIs merely because their files already exist.

### 12.2 Phases

1. **Foundation:** assets, shared schema fixture, types, validation helpers,
   CMake dependency pins, and packaging. Gate: asset/schema unit tests pass.
2. **Python backend:** model, fixed-route server, lifecycle, timers, simple
   example. Gate: Python model/HTTP tests and browser smoke test pass.
3. **C++ backend:** equivalent model/server using shared assets and schema.
   Gate: same black-box/browser suites pass against C++.
4. **Scene behavior:** reconciliation, SVG geometry, interpolation, reconnect
   behavior, and gallery. Gate: full browser matrix passes against both
   backends.
5. **Connext examples:** Python typed API and C++ generated types behind
   optional build flag. Gate: examples build/run with Connext 7.7.0; default
   build remains Connext-independent.
6. **Documentation and CI:** README integration instructions, license notices,
   format/lint/test workflows, and Simple Browser/Codespaces notes. Gate: clean
   checkout follows documented commands.

Do not start a later phase with a failed gate. Avoid adding fallback transports
or alternate renderers to bypass a failing contract test; fix the shared
contract.

## 13. Acceptance Criteria

- [ ] No Wt, NiceGUI, GTK, Qt, Boost, TLS, or compression dependency is
  required.
- [ ] Python uses Python 3.11+, `aiohttp>=3.10,<4`, and strict
  `pytest-asyncio`; C++ links pinned MIT `cpp-httplib` plus pinned JSON
  serialization.
- [ ] Both servers return byte-identical SDK assets and schema-compatible
      snapshots.
- [ ] Public model APIs and validation semantics match across languages.
- [ ] C++ model mutations are thread-safe and revisioned exactly once; Python
  mutations are owner-loop constrained and revisioned exactly once.
- [ ] Python cancellation/stop releases aiohttp resources; C++ shutdown joins
  SDK-owned threads and supports application-owned worker cleanup.
- [ ] Browser polling works through VS Code/Codespaces forwarding without
      WebSocket support.
- [ ] `Scene2DViewport` rendering and interpolation pass the same Playwright
      tests against both backends.
- [ ] Default builds do not discover Connext or fetch Connext CMake utilities.
- [ ] Optional Connext examples use Professional 7.7.0 APIs and utility-driven
      C++ IDL generation.
- [ ] Canonical assets are not copied into language-specific frontend trees.
- [ ] README and the contributor guides document dependency caching, URL
  discovery, editable Python installation, CMake consumption, custom
  frontends, packaging, and shutdown responsibilities.

## 14. Deferred Decisions

Revisit only with measured demand:

- Delta snapshots and bounded event history.
- SSE/WebSocket command or push channels.
- Canvas for high entity counts and Three.js for true 3D.
- Packaged Python wheels with embedded package data.
- Install/export CMake packaging beyond `add_subdirectory()`.
- Generic command routes and application-authored frontend modules.
- Additional Tier 2 components such as relationship graphs or time-series plots.

The web architecture is inspired by the polling pattern proven in the
`web-based-tutorial-apps` branch of
`rticonnextdds-medtech-reference-architecture`. Do not copy its source or
assets: that repository has RTI-specific licensing and contains
duplicated/transitional browser implementations that this SDK intentionally
replaces with one shared runtime.
