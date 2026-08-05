# Contributing

## Setup

Use Python 3.11 or newer and install the contributor tools from the
repository root:

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
pre-commit install --install-hooks
```

The development extra pins `pytest==8.4.2` and `pytest-asyncio==1.4.0`.
These versions support Python 3.11+ and avoid the Python 3.14 event-loop
policy deprecation warnings emitted by older `pytest-asyncio` releases.

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

The C++ and Python HTTP tests load the shared route vectors from
`tests/fixtures/static_route_vectors.json`. Add behavior there first when a
route contract changes, then update both language tests.

## Documentation

`docs/architecture.md` records durable cross-language design and invariants.
`docs/api/` contains conceptual usage guides. `docs/development/` documents
contributor workflow. Decision-bearing implementation plans belong in
`docs/development/implementation-plans/`; temporary notes do not.

Keep public names, route tables, package commands, and examples synchronized.
Do not add compatibility aliases for removed public APIs. Run pre-commit after
editing Markdown, CMake, examples, or source files.
