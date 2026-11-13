#include <gtk/gtk.h>

#include <chrono>
#include <filesystem>
#include <iostream>
#include <rti_demo_ui_native/native_webview.hpp>

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
    bool icon_valid = false;
    bool identity_valid = false;
};

gboolean inspect_window(gpointer data) {
    auto& probe = *static_cast<WindowSizeProbe*>(data);
    ++probe.attempts;
    GList* windows = gtk_window_list_toplevels();
    for (GList* current = windows; current != nullptr;
         current = current->next) {
        auto* window = GTK_WINDOW(current->data);
        const auto* title = gtk_window_get_title(window);
        if (title != nullptr && title == std::string(kWindowTitle)) {
            gtk_window_get_size(window, &probe.width, &probe.height);
            auto* icon = gtk_window_get_icon(window);
            probe.icon_valid = icon && gdk_pixbuf_get_width(icon) == 256 &&
                               gdk_pixbuf_get_height(icon) == 128;
            probe.identity_valid =
                std::string(g_get_prgname()) == "org.rti.icon-acceptance" &&
                std::string(gdk_get_program_class()) ==
                    "org.rti.icon-acceptance";
            if (probe.attempts == kMinimumProbeAttempts &&
                (!probe.icon_valid || !probe.identity_valid)) {
                std::cerr << "icon: " << (icon ? gdk_pixbuf_get_width(icon) : 0)
                          << 'x' << (icon ? gdk_pixbuf_get_height(icon) : 0)
                          << "; name: " << g_get_prgname()
                          << "; class: " << gdk_get_program_class() << '\n';
            }
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
    options.application_id = "org.rti.icon-acceptance";
    options.icon =
        std::filesystem::temp_directory_path() /
        ("rti-native-icon-" +
         std::to_string(
             std::chrono::steady_clock::now().time_since_epoch().count()) +
         ".png");
    auto* image = gdk_pixbuf_new(GDK_COLORSPACE_RGB, TRUE, 8, 1024, 512);
    gdk_pixbuf_fill(image, 0xff00ffff);
    GError* error = nullptr;
    const bool saved = gdk_pixbuf_save(image, options.icon.string().c_str(),
                                       "png", &error, nullptr);
    g_object_unref(image);
    if (!saved) {
        std::cerr << "could not create icon fixture: " << error->message
                  << '\n';
        g_error_free(error);
        return 1;
    }
    WindowSizeProbe probe{app};
    const guint source_id = g_timeout_add(25, inspect_window, &probe);

    try {
        rti::demo::ui::native::run(app, options);
    } catch (const std::exception& error) {
        std::filesystem::remove(options.icon);
        if (probe.source_active) {
            g_source_remove(source_id);
        }
        std::filesystem::remove(options.icon);
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
    if (!probe.icon_valid || !probe.identity_valid) {
        std::cerr
            << "native GTK icon dimensions or desktop identity incorrect\n";
        return 1;
    }
    return 0;
}
