# Custom Frontends

RTI Demo UI has a built-in frontend and an opt-in application-owned static
frontend. Both modes use the same local server and `/api/state` model contract.

## Modes

The default keeps the SDK page at `/`:

```python
app = DemoUiApp("Simple demo")
```

A custom frontend supplies a directory containing a regular `index.html`:

```python
from pathlib import Path
from rti_demo_ui import DemoUiApp

app = DemoUiApp(
    "Robotic Arm",
    static_root=Path(__file__).parent / "web",
)
```

The C++ form is:

```cpp
rti::demo::ui::DemoUiApp app(
    "Robotic Arm", 8080, "0.0.0.0", "web");
```

Relative roots are resolved during construction. Missing roots, non-directories,
and roots without `index.html` fail before socket binding.

## Routes

SDK routes are reserved in every mode:

| Route | Built-in mode | Custom mode |
| --- | --- | --- |
| `/` | SDK `index.html` | `static_root/index.html` |
| `/sdk/index.html` | SDK HTML | SDK HTML |
| `/sdk/runtime.js` | SDK runtime | SDK runtime |
| `/sdk/theme.css` | SDK theme | SDK theme |
| `/api/health` | health JSON | health JSON |
| `/api/state` | model snapshot | model snapshot |

`/api/` and `/sdk/` are complete reserved prefixes. Unknown API paths return
JSON 404. Unknown SDK paths return a plain static 404. Other custom paths are
looked up under `static_root`; the server serves regular files only and never
lists directories.

Static lookup decodes the URL, rejects NUL bytes, traversal, absolute paths,
broken links, directory links, and symlinks that resolve outside the root. The
explicit MIME map covers HTML, JavaScript, CSS, JSON, SVG, common images, fonts,
GLB, and GLTF. Other regular files use `application/octet-stream`.

## SDK Styling

Load the SDK theme without copying it:

```html
<link rel="stylesheet" href="/sdk/theme.css">
<script type="module" src="/app.js"></script>
```

Stable custom properties include `--sdk-bg`, `--sdk-surface`, `--sdk-card-bg`,
`--sdk-text`, `--sdk-muted`, `--sdk-border`, `--sdk-accent`,
`--sdk-success`, `--sdk-warning`, and `--sdk-danger`. Stable component classes
include `sdk-app`, `sdk-card`, `sdk-card-title`, `sdk-metric`, `sdk-table`,
`sdk-button`, `sdk-slider`, `sdk-connection-banner`, and `sdk-scene2d`.

## Gallery Example

The gallery is an application-owned frontend at
`examples/web/gallery/index.html`. It loads `/sdk/theme.css`, uses semantic
HTML, and serves at `/` when launched through either gallery example. Its
button and slider update browser-only text; no custom server route is needed.

Application assets are not copied into the SDK package. C++ consumers deploy
and pass their own `web/` directory. Python deployments package their own
static root separately and pass that directory to `DemoUiApp`.
