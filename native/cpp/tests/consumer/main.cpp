#include <rti_demo_ui_native/native_webview.hpp>

#include <chrono>
#include <thread>

int main() {
    rti::demo::ui::DemoUiApp app("Installed-style native consumer");
    app.add_card("Status")->add_metric("Ready", 1);
    std::thread stopper([&]() {
        app.wait_until_ready();
        std::this_thread::sleep_for(std::chrono::milliseconds(500));
        app.stop();
    });
    rti::demo::ui::native::run(app);
    stopper.join();
    return 0;
}
