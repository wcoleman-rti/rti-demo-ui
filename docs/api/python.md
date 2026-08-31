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

## Native Window

The separately installed `rti-demo-ui-native` companion provides a synchronous
main-thread runner on supported Linux systems:

```python
from rti_demo_ui_native import run_native

run_native(
    app,
    application_id="com.example.fleet-demo",
    async_main=receive_samples,
    width=1280,
    height=800,
)
```

`async_main(app)` starts on the app owner loop after readiness. A normal return
closes the native window; an exception is re-raised after all managed work is
joined. Browser mode remains the default and does not import pywebview. See
[Native Webview Mode](../native-webview.md) for installation, profiles,
platform support, and troubleshooting.

## Themes and Layouts

`Theme`, `Layout`, and `CardArea` are string enums. Python also accepts their
exact lowercase serialized strings:

```python
from rti_demo_ui import CardArea, DemoUiApp, Layout, Theme

app = DemoUiApp(
    "Operations",
    theme=Theme.light,
    layout=Layout.sidebar_main,
)
controls = app.add_card("Controls", area=CardArea.sidebar)
telemetry = app.add_card("Telemetry", area=CardArea.main, span=2)

app.set_theme("dark")
app.set_layout(Layout.grid_2)
controls.set_area(CardArea.main)
telemetry.set_span(3)
```

Constructor `theme` and `layout` are keyword-only, preserving the positions of
`port`, `host`, and `static_root`. Defaults are `Theme.dark`, `Layout.auto`,
`CardArea.main`, and span `1`. Spans accept only integers `1`, `2`, or `3`;
booleans are rejected. At most one sidebar card is permitted, and
`sidebar-main` requires exactly one before `run()` or when selected at runtime.
Setters return `None`, increment the application revision once when a value
changes, and leave it unchanged for valid no-ops or rejected values. After
startup they follow the normal owner-event-loop rule.

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

Both `GET /api/state` and `GET /api/events` are available in built-in and custom
frontend modes. Browser transport selection is not a `DemoUiApp` constructor
option: custom JavaScript calls `createClient({transport: "sse"})` to opt into
SSE or omits the option to retain polling. See
[Custom Frontends](../custom-frontends.md#browser-transport).

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

## Scene3D

`add_scene_3d` creates the generic scene contract and validates the asset as an
absolute same-origin `.glb` under `static_root`:

```python
from rti_demo_ui import Severity

scene = app.add_card("Arm").add_scene_3d("/models/scene.glb")
scene.add_node(
    "shoulder", "Arm/Shoulder",
    rotation=(0.0, 0.0, 0.564642, 0.825336),
    status=Severity.success,
)
scene.update_node("shoulder", position=(0.1, 0.0, 0.0))
scene.apply_node_batch([
    {"op": "update", "id": "shoulder", "visible": True},
])
```

Nodes use glTF right-handed, Y-up meter coordinates and local transforms. A
node ID is unique for the scene lifetime, including after removal. Mutations
are atomic; changed operations bump the application and component revisions
once, while valid no-ops preserve them. `set_config` replaces the complete
asset/camera/background/grid configuration atomically.
