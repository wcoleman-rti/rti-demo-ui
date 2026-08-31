# RTI Demo UI Native

Optional Linux native-window runner for `rti-demo-ui`.

The 0.4.x release supports Python 3.11+ on Ubuntu 22.04+ with GTK 3,
WebKitGTK 4.1, and pywebview 6.2.1. Download both wheels from the matching
GitHub release and install their local paths:

```bash
pip install rti_demo_ui-0.4.0-py3-none-any.whl \
  rti_demo_ui_native-0.4.0-py3-none-any.whl
```

```python
from rti_demo_ui import DemoUiApp
from rti_demo_ui_native import run_native

app = DemoUiApp("Fleet demo")
run_native(app, application_id="com.example.fleet-demo")
```

Browser mode remains available through the core package without installing
this companion. See the project's `docs/native-webview.md` for system
prerequisites, lifecycle, profile, security, and troubleshooting details.
