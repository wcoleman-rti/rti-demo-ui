#include <chrono>
#include <csignal>
#include <exception>
#include <iostream>
#include <rti_demo_ui_native/native_webview.hpp>
#include <thread>

namespace {

void print_exception(const std::exception& error, int depth = 0) {
    std::cerr << std::string(static_cast<std::size_t>(depth) * 2, ' ')
              << error.what() << '\n';
    try {
        std::rethrow_if_nested(error);
    } catch (const std::exception& nested) {
        print_exception(nested, depth + 1);
    } catch (...) {
        std::cerr << "  unknown nested exception\n";
    }
}

}  // namespace

int main() {
    rti::demo::ui::DemoUiApp app("Native Phase 1 smoke");
    std::thread stopper([&]() {
        app.wait_until_ready();
        std::this_thread::sleep_for(std::chrono::milliseconds(500));
#ifdef _WIN32
        app.stop();
#else
        std::raise(SIGINT);
#endif
    });
    try {
        rti::demo::ui::native::run(app);
    } catch (const std::exception& error) {
        app.stop();
        stopper.join();
        print_exception(error);
        return 1;
    }
    stopper.join();
    return 0;
}
