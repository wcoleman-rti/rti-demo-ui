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

# C++ API

A consuming CMake project adds the SDK's `cpp/` directory and links
`rti_demo_ui::core`:

```cmake
add_subdirectory(path/to/rti-demo-ui/cpp)
target_link_libraries(my_demo PRIVATE rti_demo_ui::core)
```

A minimal application is:

```cpp
#include <rti_demo_ui/rti_demo_ui.hpp>

int main() {
    rti::demo::ui::DemoUiApp app("Fleet demo");
    auto* card = app.add_card("Fleet Telemetry");
    auto* scene = card->add_scene_2d(
        600, 400, {-100.0, 100.0, -100.0, 100.0});
    scene->add_entity("vehicle-1", 0.0, 0.0);
    app.run();
}
```

The default host is literal loopback `127.0.0.1` and port `0`; use
`wait_until_ready()` and `ready_info()` when the selected port is needed. The
custom frontend form takes a final filesystem path:

```cpp
rti::demo::ui::DemoUiApp app(
    "Monitor", 0, "127.0.0.1", std::filesystem::path("web"));
```

The SDK embeds its own assets. The consuming project deploys `web/` and passes
that directory as `static_root`; it is never copied into the SDK library.
`stop()` is idempotent and is the programmatic shutdown API. `Card` also owns
table, metric, text, badge, log, and custom component factories. Application
state uses `set_data()` and `update_data()`. Commands use `register_command()`
with the shared schema subset and are available only for literal loopback
hosts.

## Native Window

On supported Linux systems, add the separate `native/cpp` CMake project after
the core target and link `rti_demo_ui_native::native_webview`:

```cpp
#include <rti_demo_ui_native/native_webview.hpp>

rti::demo::ui::native::NativeWindowOptions options;
options.width = 1280;
options.height = 800;
rti::demo::ui::native::run(app, options);
```

The call owns the native main-thread loop and a joined server thread. Browser
targets remain core-only and call `app.run()`. See
[Native Webview Mode](../native-webview.md) for prerequisites, CMake setup,
profiles, platform support, and troubleshooting.

Both `GET /api/state` and `GET /api/events` are served by the C++ backend.
Browser transport selection is not a `DemoUiApp` constructor option: custom
JavaScript calls `createClient({transport: "sse"})` to opt into SSE or omits the
option to retain polling. See
[Custom Frontends](../custom-frontends.md#browser-transport).

For complete signatures and validation semantics, use the public headers and
[architecture](../architecture.md) as the source of truth.

## Themes and Layouts

The scoped `Theme`, `Layout`, and `CardArea` enums serialize to the same values
as Python. `Layout::automatic` serializes as `"auto"`:

```cpp
using namespace rti::demo::ui;

DemoUiApp app("Operations", 0, "127.0.0.1", {},
              Theme::light, Layout::sidebar_main);
auto* controls = app.add_card("Controls", CardArea::sidebar);
auto* telemetry = app.add_card("Telemetry", CardArea::main, 2);

app.set_theme(Theme::dark);
app.set_layout(Layout::grid_2);
controls->set_area(CardArea::main);
telemetry->set_span(3);
```

The new constructor arguments are appended after `static_root`, preserving
existing positional calls. Defaults are `Theme::dark`, `Layout::automatic`,
`CardArea::main`, and span `1`. Spans accept only `1`, `2`, or `3`. At most one
sidebar card is permitted, and `sidebar-main` requires exactly one before
`run()` or when selected at runtime. Changed setters increment the application
revision exactly once; no-ops and rejected values do not.

## Scene3D

The C++ API mirrors Python and serializes the same generic scene contract:

```cpp
auto* scene = app.add_card("Arm")->add_scene_3d("/models/scene.glb");
scene->add_node("shoulder", "Arm/Shoulder",
                {0.0, 0.0, 0.0},
                {0.0, 0.0, 0.564642, 0.825336});
scene->update_node("shoulder", std::vector<double>{0.1, 0.0, 0.0});
scene->apply_node_batch(Json::array({
    Json{{"op", "update"}, {"id", "shoulder"}, {"visible", true}}
}));
```

Transforms are glTF right-handed, Y-up meters and local to the addressed
imported node. Node IDs remain stale after removal. Batch validation is
copy-then-commit, so failures leave state and revisions unchanged.
