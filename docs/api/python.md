# Python API

Install from the repository root:

```bash
pip install -e .
```

The public package is `rti_demo_ui`. Configure components synchronously, then
own the server lifecycle with `asyncio`:

```python
import asyncio

from rti_demo_ui import DemoUiApp


async def main() -> None:
    app = DemoUiApp("Fleet demo")
    card = app.add_card("Fleet Telemetry")
    scene = card.add_scene_2d(600, 400, (-100.0, 100.0, -100.0, 100.0))
    scene.add_entity("vehicle-1", 0.0, 0.0)
    try:
        await app.run()
    except asyncio.CancelledError:
        pass
    finally:
        await app.stop()


asyncio.run(main())
```

The app instance is single-use. `stop()` is idempotent and waits for aiohttp
cleanup. The default host is `127.0.0.1` and port `0`; call
`await app.wait_until_ready()` and inspect `app.ready_info` for the actual URL.
Component factory and mutation methods remain synchronous, but after
startup they must run on the app's owner event loop and thread. A foreign
thread must schedule its work with `loop.call_soon_threadsafe`.

## Structured Async Applications

Application coroutines own periodic work and DDS integration through a
`TaskGroup` or explicitly retained tasks:

```python
async def main() -> None:
    app = DemoUiApp("Fleet demo")
    try:
        async with asyncio.TaskGroup() as tasks:
            tasks.create_task(app.run())
            tasks.create_task(receive_dds_samples())
            tasks.create_task(publish_dds_samples())
    except asyncio.CancelledError:
        pass
    finally:
        await app.stop()
```

The SDK does not provide Python timer APIs or lifecycle compatibility adapters.

## Custom Frontend

Pass a string or `PathLike[str]` root containing `index.html`:

```python
from pathlib import Path
from rti_demo_ui import DemoUiApp

app = DemoUiApp(
    "Monitor",
    port=8080,
    host="127.0.0.1",
    static_root=Path(__file__).parent / "web",
)
```

The SDK serves `/sdk/...` assets and reserves `/api/...`; other files come from
the validated root. See [Custom Frontends](../custom-frontends.md) for the
route and security contract.

For complete signatures and validation semantics, use the Python type hints,
docstrings, and [architecture](../architecture.md) as the source of truth.

`DemoUiApp.set_data(value)` and `update_data(path, value, create_missing=False)`
manage application-owned JSON state. `Card` also provides `add_table`,
`add_metric`, `add_text`, `add_badge`, `add_log`, and
`add_custom_component`; returned handles expose the live mutation methods
described by their type hints. Register opt-in actions with
`register_command(name, schema, handler, confirmation=None)`. Command schemas
use the shared restricted subset, handlers receive validated objects, and
responses are JSON envelopes.
