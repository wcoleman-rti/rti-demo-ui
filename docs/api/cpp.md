# C++ API

A consuming CMake project adds the SDK's `cpp/` directory and links
`rti_demo_ui::core`:

```cmake
add_subdirectory(path/to/rti-demo-ui/cpp)
target_link_libraries(my_demo PRIVATE rti_demo_ui::core)
```

A minimal application is:

```cpp
#include <rti_demo_ui/gui_sdk.hpp>

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

For complete signatures and validation semantics, use the public headers and
[architecture](../architecture.md) as the source of truth.
