# Custom Frontend and Lifecycle Plan

## Objective

Extend the SDK so Connext demo applications can either use the existing
SDK-owned browser UI or serve an application-owned static frontend from the
same local server. Keep the default `DemoUiApp` experience unchanged and
minimal. In both modes, serve reusable SDK frontend assets from stable
`/sdk/...` routes. Use the gallery example to validate the custom-frontend
path at `/`.

At the same time, make startup failures explicit, make immediate Python port
reuse more resilient, and document/test a supported Ctrl-C shutdown path.

Rename the public SDK to `rti_demo_ui` and its application host to
`DemoUiApp`. The SDK has no external users yet, so this is a deliberate
breaking rename with no compatibility aliases or deprecated import paths.

## Public Naming

Use one product name and application-host name consistently:

```text
Repository:         rti-demo-ui
C++ namespace:    rti::demo::ui
C++ class:        rti::demo::ui::DemoUiApp
C++ primary header: rti_demo_ui/demo_ui_app.hpp
CMake project:     rti_demo_ui
CMake target:     rti_demo_ui::core

Python distribution: rti-demo-ui
Python package:      rti_demo_ui
Python class:     rti_demo_ui.DemoUiApp

Documentation title: RTI Demo UI
```

Rename repository directories, CMake targets, Python distribution/package
metadata, imports, include paths, examples, tests, documentation, and runtime
error text in the same implementation change. Do not retain `CoreApp`,
`rti_demo_gui_sdk`, or legacy aliases.

Do not rename generated or cache output. Delete `build/`, `*.egg-info/`,
`.ruff_cache/`, and other generated directories before the rename, then let
the renamed build recreate them. As the final rename gate, search all tracked
source, tooling, and documentation files for legacy names, including
`.pre-commit-config.yaml`, `.gitignore`, CI workflows, and task definitions.
Exclude generated/cache directories from that search; they must have been
deleted rather than edited.

Keep structural directories such as `cpp/`, `python/`, `assets/`, `examples/`,
and `tests/`; they describe repository roles rather than the public product
name. Rename the external Git repository and its local checkout directory to
`rti-demo-ui` as a coordinated repository-hosting operation. Source changes
must not assume that directory rename has already occurred.

## Product Boundary

The SDK has two frontend modes:

1. **Built-in UI (default):** SDK-owned `index.html`, `runtime.js`, and
   `theme.css` render the `DemoUiApp` card/scene model through `/api/state`.
2. **Custom static frontend (opt-in):** The application supplies a directory
   containing `index.html` and its browser assets. The SDK serves those assets,
   its reusable `/sdk/...` assets, and its reserved API routes.

The custom frontend owns its markup, JavaScript, rendering libraries, and
domain-specific visualization. It may consume the existing `/api/state`
contract, but the first implementation does not add custom JSON endpoints,
SSE, WebSockets, or browser-to-server command routes.

`/sdk/theme.css` is a supported public styling contract. The SDK documents
stable semantic CSS custom properties and selected component classes, while
leaving internal selectors private. A custom frontend may load
`/sdk/runtime.js` only when it deliberately follows the built-in DOM and
`/api/state` schema; it is not a required dependency for custom pages.

This permits a future Three.js robotic-arm demo without making the SDK a 3D
engine: the demo bundles Three.js/model assets and uses an SDK API extension
added in a later phase to retrieve its arm-specific state.

## Public API

Add an optional static-root parameter, preserving every existing call site:

```cpp
rti::demo::ui::DemoUiApp app("Patient Monitor", 8080, "0.0.0.0", "web");
```

```python
app = DemoUiApp("Patient Monitor", static_root="web")
```

Requirements:

- Empty/omitted `static_root` selects built-in UI mode.
- A supplied root must exist and be a directory at `DemoUiApp` construction.
- The directory must contain a regular `index.html`; reject missing or invalid
  roots with a clear language-native argument error before binding a socket.
- Relative paths are resolved once to an absolute/canonical static root during
  construction. Do not make asset lookup depend on the working directory after
  `run()` begins.
- The C++ API must not introduce ambiguity with existing `(title, port, host)`
  construction. Prefer a final `std::filesystem::path static_root = {}`
  parameter or an options struct only if the resulting overload is clearer.
- Python exposes the same behavior through an optional `PathLike[str]` value.

Do not expose arbitrary route callbacks in this change. That would create a
separate, harder cross-language server API before the static serving contract
is proven.

## Documentation Deliverables

Keep all repository documentation committed. Build the following tree as part
of this work; do not hide implementation plans or design decisions from Git.

```text
docs/
   architecture.md
   custom-frontends.md
   lifecycle.md
   api/
      cpp.md
      python.md
   development/
      contributing.md
      implementation-plans/
         custom_frontend_and_lifecycle.md
```

- `architecture.md` is the durable, cross-language system design and replaces
  the former implementation-plan role.
- `custom-frontends.md` documents built-in versus static-root mode, reserved
  routes, `/sdk/...` reusable assets, CSS compatibility, asset packaging, and
  a complete C++ and Python custom-page example.
- `lifecycle.md` documents `DemoUiApp.run()`, `stop()`, worker ownership, bind
  failures, and supported Ctrl-C handling.
- `api/cpp.md` and `api/python.md` are conceptual usage guides with concise
  examples. Public C++ header comments and Python docstrings/type hints remain
  the source of truth for signatures; generated API reference may be added
  later rather than duplicating every signature by hand.
- `development/contributing.md` describes local setup, build/test commands,
  documentation conventions, and the policy for adding/updating implementation
  plans.
- `development/implementation-plans/` stores committed, decision-bearing
  plans. Temporary private notes belong outside `docs/` and are locally
  ignored.

## Consumer Packaging and Developer Experience

The SDK and the consuming application own different files:

- The SDK packages its built-in `index.html`, `theme.css`, and `runtime.js`.
- It serves its CSS from `/sdk/theme.css`.
- It serves its runtime from `/sdk/runtime.js`.
- Its built-in root page uses those same namespaced routes.
- A consuming application packages its own static root and `index.html`.
- That root can contain app JavaScript/CSS, images, fonts, and GLTF models.
- The application supplies that directory through `static_root`.
- The SDK never copies, embeds, builds, or discovers application assets.
- A consuming CMake project copies its own `web/` directory beside its executable.
- A Python application deployment packages its own `web/` directory as needed.
- Each application passes that deployed directory as `static_root`.

The default experience remains minimal:

```python
app = DemoUiApp("Simple demo")
```

An app that needs custom UX opts in once:

```python
app = DemoUiApp("Robotic Arm", static_root=Path(__file__).parent / "web")
```

Application-owned HTML can share the SDK visual language without copying it:

```html
<link rel="stylesheet" href="/sdk/theme.css">
<link rel="stylesheet" href="/app.css">
<script type="module" src="/app.js"></script>
```

For C++ consumers, the SDK assets remain compiled into the SDK library as they
are today. A consumer-owned `web/` directory is copied by that consumer's
CMake/install rules and passed as an absolute or deployment-relative
`static_root` path.

For Python consumers, this is a required packaging change. The current
repository-relative `assets/` lookup and editable-install-only limitation must
be removed. Package the SDK-owned assets in the wheel and load them with
`importlib.resources`; a normal `pip install` must serve `/sdk/theme.css` and
the built-in UI without the repository checkout being present. Application
assets remain outside the wheel unless the consuming application chooses to
package them.

## Shared Asset Packaging

Maintain one canonical SDK asset source at the repository root:

```text
assets/
   index.html
   runtime.js
   theme.css
```

Do not commit or maintain language-specific source copies of those files.

Add a minimal root `CMakeLists.txt` as the repository developer entry point:

```cmake
cmake_minimum_required(VERSION 3.16)
project(rti_demo_ui LANGUAGES CXX)

include(CTest)
add_subdirectory(cpp)
```

Keep `cpp/CMakeLists.txt` as the C++ consumer entry point. It must work both
when configured through the repository root and when a consumer calls
`add_subdirectory(path/to/rti-demo-ui/cpp)`. It owns C++ target definitions,
dependencies, tests/examples, and the canonical asset embedding logic.

Do not add `CMakeLists.txt` under `assets/`. Assets are shared source data, not
a CMake component. In `cpp/CMakeLists.txt`, resolve their directory relative
to the current list file:

```cmake
set(RTI_DEMO_UI_ASSETS_DIR "${CMAKE_CURRENT_LIST_DIR}/../assets")
```

Validate and embed the declared canonical files at CMake configure time. The
root file delegates only; it does not enumerate or package asset files.

- C++ reads canonical `assets/` at CMake configure time.
- C++ embeds those bytes in its generated private header.
- The C++ library/executable has no runtime asset-path dependency.
- Python stages canonical `assets/` into `rti_demo_ui/_assets/` in wheel output.
- Python uses `importlib.resources` to read those wheel-internal resources.
- Consumer-owned static roots are independent of SDK asset packaging.
- Each consuming application deploys its own static root.

Move Python build metadata from `python/pyproject.toml` to the repository root
so the canonical root assets are included in both source distributions and
wheels. Preserve the Python source layout with setuptools package mapping:

```toml
[tool.setuptools]
package-dir = { "" = "python" }

[tool.setuptools.packages.find]
where = ["python"]
```

Use a root `MANIFEST.in` to include `assets/**` in the sdist. Implement a
setuptools `build_py` subclass that copies canonical `assets/**` into
`build_lib/rti_demo_ui/_assets/` during wheel construction, then register that
class through `[tool.setuptools.cmdclass]`. Declare the staged destination as
package data. Do not rely on an out-of-package `package-data` glob or a source
copy under `python/`.

Validate the packaging contract in three isolated modes:

1. Editable root install: `pip install -e .`.
2. Wheel build/install: install the built wheel into a fresh environment with
   no repository checkout available.
3. Sdist build/install: install the built sdist into a fresh environment with
   no repository checkout available.

Each mode must serve the built-in root and `/sdk/theme.css` successfully.
Update all README and contributor commands from `pip install -e ./python` to
the root installation form, `pip install -e .`.

## Routing and Security Contract

In built-in UI mode, retain the current routes and byte-identical embedded
SDK assets under their new namespaced contract:

```text
GET /                -> SDK index.html
GET /sdk/index.html  -> SDK index.html
GET /sdk/runtime.js  -> SDK runtime.js
GET /sdk/theme.css   -> SDK theme.css
GET /api/health   -> SDK health response
GET /api/state    -> SDK model snapshot
```

In custom static frontend mode:

```text
GET /                -> <static_root>/index.html
GET /<path>          -> regular file under <static_root>
GET /sdk/index.html  -> SDK index.html
GET /sdk/runtime.js  -> SDK runtime.js
GET /sdk/theme.css   -> SDK theme.css
GET /api/health      -> SDK health response
GET /api/state       -> SDK model snapshot
```

Rules:

- `/api/` and `/sdk/` are complete reserved prefixes, not only known routes.
- Static-file lookup never runs for a request whose path begins with either prefix.
- Files at `static_root/api/state` and `static_root/api/unknown` are unreachable.
- Files at `static_root/sdk/theme.css` and `static_root/sdk/unknown.js` are unreachable.
- Unknown `/api/...` paths return the SDK's JSON 404.
- Unknown `/sdk/...` paths return the SDK's static-asset 404.
- Both outcomes are equivalent between C++ and Python.
- Decode and normalize the URL path before lookup. Reject traversal attempts,
  absolute paths, NUL bytes, and paths resolving outside `static_root` with
  `404`; do not disclose filesystem paths.
- Serve regular files only.
- Permit a symlink only when its fully resolved target remains inside the root.
- A permitted symlink target must be a regular file.
- Reject broken links, loops, directory targets, and root escapes with `404`.
- Do not list directories.
- Map a small explicit MIME set: `.html`, `.js`, `.css`, `.json`, `.svg`,
  `.png`, `.jpg`/`.jpeg`, `.gif`, `.webp`, `.ico`, `.woff`, `.woff2`,
  `.ttf`, `.glb`, and `.gltf`. Use `application/octet-stream` only for
  otherwise allowed files where an explicit type is not required.
- Retain `X-Content-Type-Options: nosniff`. Set static asset cache policy to
  `no-cache` initially; versioned-asset caching can be a later optimization.
- Continue returning JSON `404` for reserved API paths and a small plain/text
  or HTML `404` for missing static assets, chosen consistently across both
  backends.
- Continue rejecting unsupported HTTP methods with `405`.

### C++ Static Resolver

Do not use `cpp-httplib` `set_mount_point()` for application static files.
Route precedence and path-containment behavior must be explicit and identical
to the Python implementation. Register SDK `/api/...` and `/sdk/...` routes
first, reject unknown requests under either reserved prefix, then use one
explicit C++ catch-all `GET` handler for all application static requests.

The catch-all uses a dedicated resolver that URL-decodes, rejects invalid or
absolute paths, canonicalizes candidate paths, verifies containment under the
canonical static root, verifies a regular file, selects MIME type, and reads
the file. It returns the specified static 404 for every resolver failure. Do
not distribute equivalent logic across route lambdas.

### Cross-Language Route Vectors

Create `tests/fixtures/static_route_vectors.json` before implementing either
server. It is the single source of expected request behavior for both C++ and
Python HTTP tests. Each vector specifies a request path, expected status,
response class (`sdk_asset`, `api_json`, `application_asset`, or `static_404`),
and expected MIME type where relevant.

Include vectors for root, nested assets, missing files, each supported MIME
type, API and SDK prefix reservation, unknown paths under both reserved
prefixes, encoded traversal, decoded traversal, absolute paths, NUL bytes,
directory requests, a valid in-root symlink, a broken symlink, a symlink to a
directory, and a symlink escaping the root. Both test suites load the same
vectors; they must not maintain hand-copied case lists.

## Implementation Sequence

### 1. Establish the contract in tests and documentation

1. Rename the public C++ and Python SDK surfaces according to **Public
   Naming**, including CMake `project()`/export names, Python distribution and
   package metadata, generated asset identifiers, documentation titles, and
   all source/test/example references. Delete generated/cache output first,
   then run the final tracked-file legacy-name search described in **Public
   Naming**. Run existing test suites before
   starting the static-root work to isolate rename regressions from functional
   changes.
2. Add the root `CMakeLists.txt` described in **Shared Asset Packaging**.
   Refactor `cpp/CMakeLists.txt` only as needed to support both root builds and
   consumer `add_subdirectory(cpp)` use. Update developer CMake commands to
   `cmake -S . -B build` while retaining documented consumer integration.
3. Convert `docs/architecture.md` from its implementation-plan-oriented form
   into the durable system design. Preserve and reorganize its still-valid
   current architecture, model, schema, component, and testing content; do not
   replace it with a blank rewrite. Then update `README.md`, `python/README.md`,
   and `docs/architecture.md`
   to replace the old `/runtime.js`, `/theme.css`, and `/gallery` route table
   with the final built-in/custom-mode route tables above; document complete
   `/api/` and `/sdk/` prefix reservation and the stable CSS compatibility
   contract.
4. Audit `.pre-commit-config.yaml`, `.github/workflows/`, tracked task files,
   and README/developer commands for assumptions that `pyproject.toml` is in
   `python/`. Update install, Ruff, pytest, packaging, and CI commands to use
   the repository root after relocation. No tracked VS Code task files exist
   today, but include them in this audit if added before implementation.
5. Add the shared route-vector fixture defined in **Cross-Language Route
   Vectors** and an application-owned static fixture containing `index.html`,
   `app.js`, `styles.css`, a nested asset, a symlink test target, and a known
   binary or text asset.
6. Add identical C++ and Python HTTP-contract assertions by loading the shared
   route vectors. Cover root serving, nested serving, MIME type, missing asset,
   traversal rejection, and reserved-prefix behavior without hand-copied case
   lists.
7. Keep browser coverage small: load the custom root and assert its distinctive
   element appears. Do not add a full second browser matrix.

### 2. Implement Python static serving

1. Move `pyproject.toml` to the repository root and retain `python/` as the
   package source directory through setuptools package mapping. Add the build
   hook described in **Shared Asset Packaging**: a root `MANIFEST.in` plus a
   registered setuptools `build_py` subclass. Canonical root `assets/` must be
   included in sdists and staged into wheel package data without a maintained
   Python source copy.
2. Replace the repository-relative `_ASSETS_DIR` lookup with
   `importlib.resources` reads from the wheel-internal package resources.
   Verify editable, wheel, and sdist installation modes can serve the built-in
   root and `/sdk/theme.css` without a repository checkout for wheel/sdist.
3. Change the SDK asset mapping to `/sdk/index.html`, `/sdk/runtime.js`, and
   `/sdk/theme.css`. Update the built-in HTML to request the namespaced CSS and
   JavaScript routes.
4. Add `static_root` validation and canonical-root storage in
   `python/rti_demo_ui/demo_ui_app.py`. Accept `os.PathLike[str]` as well as
   strings, and reject invalid roots before constructing `ThreadingHTTPServer`.
5. Split request routing so `/api/...` and `/sdk/...` are handled before
   application static-file lookup.
6. Implement a single static-file resolver that performs URL decoding,
   containment checking, regular-file checking, and MIME selection.
7. Reuse `_send_asset` response-header behavior for the static response path
   without loading arbitrary assets until requested.
8. Set `ThreadingHTTPServer.allow_reuse_address = True` through a private
   subclass used only by `DemoUiApp`. This server subclass is independent of
   the dynamically created per-application request-handler subclass that binds
   the handler's `app` attribute. Keep both subclassing points separate.

### 3. Implement C++ static serving

1. Add equivalent `std::filesystem::path` validation/canonicalization in
   `cpp/include/rti_demo_ui/demo_ui_app.hpp` and `cpp/src/demo_ui_app.cpp`.
2. Implement the dedicated manual resolver and explicit catch-all handler
   required by **C++ Static Resolver**; do not use `set_mount_point()` or mix
   path validation into route lambdas.
3. Register `/api/...` and `/sdk/...` before the static catch-all route.
   Explicitly reject every unknown path under either reserved prefix before the
   catch-all can inspect it. Prove this behavior with the shared route vectors.
4. Preserve embedded SDK assets in both modes and update built-in HTML to load
   `/sdk/theme.css` and `/sdk/runtime.js`. The CMake embedding pipeline must
   not attempt to embed consumer-provided files.
5. Bind before entering the blocking loop: call `server_->bind(host_, port_)`
   and throw `std::runtime_error` with host and port if it fails; print the URL
   only after that successful bind; then call `server_->listen_after_bind()`.
   A failed bind must never print a listening URL or return normally. Implement
   the `stopped_` guard in this same run/startup path before bind and again
   before `listen_after_bind()`, so a pre-listen `stop()` cannot later enter
   the listening loop.

### 4. Move the gallery to custom static mode

1. Move the gallery HTML and any gallery-specific CSS/JS out of `assets/` into
   an example-owned directory, such as `examples/web/gallery/`. Its HTML loads
   `/sdk/theme.css` rather than copying SDK theme content.
2. Update both gallery applications to pass that directory as `static_root`.
   The C++ example must receive a build-time source-directory definition rather
   than depending on its launch directory. The Python example can resolve its
   directory from `__file__`.
3. Make the gallery output and documented URL `http://localhost:8080/`.
4. Remove `/gallery` from the SDK's documented routes and HTTP tests after
   migration. Do not retain an undocumented compatibility endpoint.
5. Keep the gallery as a frontend smoke demo: metric/status text, table,
   button, and slider. Do not add a card or `Scene2DViewport` just to make it
   dynamic.

### 5. Support a clean Ctrl-C lifecycle

`DemoUiApp.stop()` is the supported programmatic shutdown API. It must remain
safe to call from a non-signal application control path and idempotent.

Calling `stop()` before or while `run()` is starting must prevent the server
from entering its listening loop. This closes the interrupt race before a
socket has been bound.

1. Document that terminal Ctrl-C is a normal interactive exit path for demo
   applications.
2. Update Python runnable examples to catch `KeyboardInterrupt`, call
   `app.stop()` in `finally`, and exit without a traceback. Preserve each
   example's application-worker cleanup ordering.
3. Keep SDK signal and console-control registration out of `DemoUiApp`.
   Applications may have their own termination policy, and process-global
   handlers would conflict with embedding applications.
4. For POSIX C++ examples, block `SIGINT` before creating SDK, DDS, timer, or
   server threads. Start an example-local control thread that uses
   `sigtimedwait()` with a short timeout; when it receives `SIGINT`, it calls
   `app.stop()` outside a signal handler. When `run()` returns normally, set a
   shutdown flag and join the control thread.
5. For Windows C++ examples, register a `SetConsoleCtrlHandler` callback and
   create a manual-reset event. The callback handles only `CTRL_C_EVENT` and
   `CTRL_BREAK_EVENT`, calls only `SetEvent()`, and returns `TRUE`. An
   example-local control thread waits on that event with a short timeout, then
   calls `app.stop()` outside the callback. On normal `run()` return, set a
   shutdown flag, join the control thread, unregister the handler, and close
   the event. Leave close, logoff, and shutdown console events to default OS
   behavior in this phase.
6. In both C++ example paths, call `run()` on the main thread. After it
   returns, signal and join application-owned DDS workers, then finish control
   thread cleanup. Do not move the server to a background thread merely for
   Ctrl-C handling.

## Focused Validation

Run after each implementation slice:

```bash
cmake --build build && ctest --test-dir build --output-on-failure
PYTHONPATH=python python -m pytest tests/py -q
PYTHONPATH=python python -m pytest tests/browser -q
```

Add minimal lifecycle checks:

- Start, stop, and immediately restart each backend on the same explicit test
  port.
- Bind a temporary competing listener first.
- C++ `run()` raises `std::runtime_error` containing host and port.
- Python raises its existing address-in-use error.
- No failed bind prints a false success message.
- A pre-listen `stop()` leaves no listener and returns promptly.
- Exercise POSIX Ctrl-C and Windows console-control behavior when CI supports it.
- Otherwise retain platform-specific manual verification.
- Unit-test the non-signal `stop()` path and each controller handoff.

Manual acceptance checks:

1. Run each gallery example and open `/`; the controls are visible and work.
2. Run each simple example and open `/`; the built-in card/scene UI remains
   unchanged.
3. Stop each example with Ctrl-C; it exits without an uncaught Python
   traceback or a lingering listener.
4. Immediately restart on the same port; it succeeds. A real concurrently
   running process instead produces a clear bind failure.

## Deferred Work

- Application-defined JSON endpoints for domain-specific data such as robotic
  arm joint angles.
- SSE, WebSockets, browser command routes, authentication, and TLS.
- Bundling, transpiling, or dependency management for Three.js or other
  application frontend tooling.
- Cache fingerprinting, compression, range requests, and production static
  hosting features.

## Completion Criteria

- Existing applications compile/run without source changes and retain the
  SDK-owned UI by default.
- Both language bindings serve the same custom-root fixture with equivalent
  route, MIME, containment, and reserved-API behavior.
- Gallery is served at `/` through the new public capability in both examples.
- C++ bind failures cannot be silent; Python supports address reuse.
- `DemoUiApp.stop()` remains the documented programmatic lifecycle API and the
  shipped runnable examples handle Ctrl-C cleanly.
