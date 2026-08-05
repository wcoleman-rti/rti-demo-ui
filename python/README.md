# RTI Demo UI (Python)

RTI Demo UI for Python with a native `asyncio`/`aiohttp` backend.
Provides the shared `DemoUiApp`, generic state components, and `Scene2DViewport`
components described in the top-level repository README.

## API and Frontends

```python
from pathlib import Path
from rti_demo_ui import DemoUiApp

app = DemoUiApp(
    "Fleet monitor",
    static_root=Path(__file__).parent / "web",
)
import asyncio

asyncio.run(app.run())
```

`static_root` accepts a string or `os.PathLike[str]` directory containing
`index.html`. The SDK reserves `/sdk/` and `/api/`, serves `/sdk/theme.css`,
`/sdk/runtime.js`, and the framework-independent `/sdk/client.js`, and resolves
other paths beneath the validated root. Port `0` selects an available loopback
port; use `await app.wait_until_ready()` and `app.ready_info` to retrieve it.
Wheel and source-distribution installs load built-in assets from package
resources; application-owned frontend files are deployed separately.

See [../docs/api/python.md](../docs/api/python.md),
[../docs/custom-frontends.md](../docs/custom-frontends.md), and
[../docs/lifecycle.md](../docs/lifecycle.md) for the public API, route
contract, security checks, and shutdown responsibilities.

## Installation

Install the package from the repository root:

```bash
pip install -e .
```

For contributor tooling (`pytest`, `playwright`):

```bash
pip install -e '.[dev]'
```
