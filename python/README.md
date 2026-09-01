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
The client polls by default; custom frontends can explicitly select
`createClient({transport: "sse"})`. Both `/api/state` and `/api/events` remain
reserved SDK routes.
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
