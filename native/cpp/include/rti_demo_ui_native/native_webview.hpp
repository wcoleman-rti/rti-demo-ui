#pragma once

#include <stdexcept>

#include <rti_demo_ui/demo_ui_app.hpp>

namespace rti::demo::ui::native {

class NativeWebviewError : public std::runtime_error {
   public:
    using std::runtime_error::runtime_error;
};

struct NativeWindowOptions {
    int width = 1280;
    int height = 800;
    bool devtools = false;
};

void run(DemoUiApp& app, NativeWindowOptions options = {});

}  // namespace rti::demo::ui::native
