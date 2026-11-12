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

# Examples

Each example stays focused on one SDK feature and is available in Python and
C++.

| Feature | Python | C++ target |
| --- | --- | --- |
| 2D scene updates | `python examples/py/simple.py` | `rti_demo_ui_simple` |
| Built-in dashboard components | `python examples/py/components.py` | `rti_demo_ui_components` |
| Application-owned JSON state | `python examples/py/app_data.py` | `rti_demo_ui_app_data` |
| Validated browser commands | `python examples/py/commands.py` | `rti_demo_ui_commands` |
| Themes, layouts, and a custom root | `python examples/py/gallery.py` | `rti_demo_ui_gallery` |
| 3D scene updates | `python examples/py/arm3d.py` | `rti_demo_ui_arm3d` |
| Optional Connext DDS integration | `python examples/py/connext.py` | `rti_demo_ui_connext` |

Build any C++ example from the repository root:

```bash
cmake -S . -B build
cmake --build build --target <target>
./build/cpp/examples/<target>
```
