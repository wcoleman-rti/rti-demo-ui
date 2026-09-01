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

# RTI Demo UI Native

Optional Linux native-window runner for `rti-demo-ui`.

The 0.4.x release supports Python 3.11+ on Ubuntu 22.04+ with GTK 3,
WebKitGTK 4.1, and pywebview 6.2.1. Download both wheels from the matching
GitHub release and install their local paths:

```bash
pip install rti_demo_ui-0.4.1-py3-none-any.whl \
  rti_demo_ui_native-0.4.1-py3-none-any.whl
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
