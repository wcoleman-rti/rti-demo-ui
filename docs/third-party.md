# Third-Party Dependencies

This register covers the SDK's direct dependencies declared in the repository.
It is not a complete inventory of transitive dependencies; release SBOMs will
provide that artifact-level view when package artifacts are published.

## Default SDK Dependencies

| Component | Version or pin | Purpose | License | Source |
| --- | --- | --- | --- | --- |
| aiohttp | `>=3.10,<4` | Python runtime HTTP server | Apache-2.0 | [aio-libs/aiohttp](https://github.com/aio-libs/aiohttp) |
| cpp-httplib | `a7bc00e3307fecdb4d67545e93be7b88cfb1e186` (v0.18.3) | C++ HTTP server | MIT | [yhirose/cpp-httplib](https://github.com/yhirose/cpp-httplib) |
| nlohmann/json | `9cca280a4d0ccf0c08f47a99aa71d1b0e52f8d03` (v3.11.3) | C++ JSON support | MIT | [nlohmann/json](https://github.com/nlohmann/json) |

## Development Dependencies

These packages are installed only with the Python `dev` extra and are not SDK
runtime dependencies.

| Component | Version | Purpose | License | Source |
| --- | --- | --- | --- | --- |
| pytest | 8.4.2 | Python test runner | MIT | [pytest-dev/pytest](https://github.com/pytest-dev/pytest) |
| pytest-asyncio | 1.4.0 | Async Python test support | Apache-2.0 | [pytest-dev/pytest-asyncio](https://github.com/pytest-dev/pytest-asyncio) |
| Playwright | 1.62.0 | Browser test automation | Apache-2.0 | [microsoft/playwright-python](https://github.com/microsoft/playwright-python) |
| clang-format | 18.1.8 | C++ formatting | Apache-2.0 with LLVM Exception | [llvm/llvm-project](https://github.com/llvm/llvm-project) |
| pre-commit | 4.6.1 | Local quality-check orchestration | MIT | [pre-commit/pre-commit](https://github.com/pre-commit/pre-commit) |

## Optional Scene3D Bundle

The opt-in browser renderer is built from exact npm pins in
`tools/scene3d/package-lock.json`. The generated `assets/runtime3d.js` is a
self-contained ES2020 browser module; applications do not contact a CDN or
run Node.js at runtime.

| Component | Version | Purpose | License | Source |
| --- | --- | --- | --- | --- |
| Three.js | 0.173.0 | WebGL scene graph, GLTFLoader, OrbitControls | MIT | [mrdoob/three.js](https://github.com/mrdoob/three.js) |
| esbuild | 0.25.0 | Reproducible browser bundle build tool | MIT | [evanw/esbuild](https://github.com/evanw/esbuild) |

Update the pins with `npm ci --ignore-scripts`, rebuild the artifact, refresh
`assets/runtime3d.sha256`, and review the generated diff and upstream license
notices together.

## Optional Connext Example Dependencies

These components are required only when building or running the guarded Connext
examples. They are not installed, discovered, or fetched by default SDK builds.

| Component | Version or pin | Purpose | License | Source |
| --- | --- | --- | --- | --- |
| RTI Connext Professional | 7.7.0 | DDS runtime and code generation | Commercial; see RTI license terms | [RTI Connext](https://www.rti.com/products/connext-dds-professional) |
| RTI Connext DDS CMake Utilities | `2c4b3efef3ed87135565f5d9493303938a76da31` | CMake integration for C++ Connext example | Apache-2.0 | [rticommunity/rticonnextdds-cmake-utils](https://github.com/rticommunity/rticonnextdds-cmake-utils) |
| rti.connextdds and rti.types | Provided with Connext Professional 7.7.0 | Python Connext example bindings | Commercial; see RTI license terms | [RTI Connext](https://www.rti.com/products/connext-dds-professional) |

## Maintenance

Dependabot monitors the root Python project metadata and GitHub Actions. CMake
`FetchContent` Git commit pins require manual update PRs so that C++ dependency
updates remain explicit and tested. Update this register in the same change as
any direct dependency addition, removal, or version/pin change.
