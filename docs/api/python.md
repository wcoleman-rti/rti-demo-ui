# Python API

Install from the repository root:

```bash
pip install -e .
```

The public package is `rti_demo_ui`. A minimal application is:

```python
from rti_demo_ui import DemoUiApp

app = DemoUiApp("Fleet demo")
card = app.add_card("Fleet Telemetry")
scene = card.add_scene_2d(600, 400, (-100.0, 100.0, -100.0, 100.0))
scene.add_entity("vehicle-1", 0.0, 0.0)
app.run()
```

`add_card`, scene mutations, and timers are safe from application threads.
`stop()` is idempotent and should be called by application cleanup code.

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
the validated root. See [Custom Frontends](../custom-frontends.md) for the route
and security contract.

For complete signatures and validation semantics, use the Python type hints,
docstrings, and [architecture](../architecture.md) as the source of truth.
