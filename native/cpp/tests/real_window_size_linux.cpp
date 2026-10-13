#include <gtk/gtk.h>

#include <rti_demo_ui_native/native_webview.hpp>

#include <iostream>

namespace {

constexpr int kExpectedWidth = 641;
constexpr int kExpectedHeight = 437;
constexpr int kMaximumProbeAttempts = 200;
constexpr int kMinimumProbeAttempts = 20;
constexpr char kWindowTitle[] = "Native initial window size";

struct WindowSizeProbe {
    rti::demo::ui::DemoUiApp& app;
    int attempts = 0;
    int width = 0;
    int height = 0;
    bool found = false;
    bool source_active = true;
};

gboolean inspect_window(gpointer data) {
    auto& probe = *static_cast<WindowSizeProbe*>(data);
    ++probe.attempts;
    GList* windows = gtk_window_list_toplevels();
    for (GList* current = windows; current != nullptr; current = current->next) {
        auto* window = GTK_WINDOW(current->data);
        const auto* title = gtk_window_get_title(window);
        if (title != nullptr && title == std::string(kWindowTitle)) {
            gtk_window_get_size(window, &probe.width, &probe.height);
            probe.found = true;
            break;
        }
    }
    g_list_free(windows);
    if (probe.found && probe.attempts >= kMinimumProbeAttempts) {
        probe.source_active = false;
        probe.app.stop();
        return G_SOURCE_REMOVE;
    }
    if (probe.attempts >= kMaximumProbeAttempts) {
        probe.source_active = false;
        probe.app.stop();
        return G_SOURCE_REMOVE;
    }
    return G_SOURCE_CONTINUE;
}

}  // namespace

int main() {
    using rti::demo::ui::DemoUiApp;
    using rti::demo::ui::native::NativeWindowOptions;

    DemoUiApp app(kWindowTitle);
    NativeWindowOptions options;
    options.width = kExpectedWidth;
    options.height = kExpectedHeight;
    WindowSizeProbe probe{app};
    const guint source_id = g_timeout_add(25, inspect_window, &probe);

    try {
        rti::demo::ui::native::run(app, options);
    } catch (const std::exception& error) {
        if (probe.source_active) {
            g_source_remove(source_id);
        }
        std::cerr << error.what() << '\n';
        return 1;
    }
    if (probe.source_active) {
        g_source_remove(source_id);
    }
    if (!probe.found) {
        std::cerr << "timed out waiting for the native GTK window\n";
        return 1;
    }
    if (probe.width != kExpectedWidth || probe.height != kExpectedHeight) {
        std::cerr << "native GTK window size was " << probe.width << 'x'
                  << probe.height << ", expected " << kExpectedWidth << 'x'
                  << kExpectedHeight << '\n';
        return 1;
    }
    return 0;
}
