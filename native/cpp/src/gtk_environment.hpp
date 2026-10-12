/*
 * (c) 2026 Copyright, Real-Time Innovations, Inc.  All rights reserved.
 *
 * RTI grants Licensee a license to use, modify, compile, and create derivative
 * works of the Software.  Licensee has the right to distribute object form
 * only for use with RTI products.  The Software is provided "as is", with no
 * warranty of any type, including any warranty for fitness for any purpose.
 * RTI is under no obligation to maintain or support the Software.  RTI shall
 * not be liable for any incidental or consequential damages arising out of
 * the use or inability to use the software.
 */

#pragma once

#include <cstdlib>
#include <cstdio>
#include <string>
#include <utility>
#include <vector>

#include <rti_demo_ui_native/native_webview.hpp>

namespace rti::demo::ui::native::detail {
namespace {

bool is_snap_path(const std::string& path,
                  const std::vector<std::string>& roots) {
    for (const auto& root : roots) {
        if (path == root ||
            (path.size() > root.size() &&
             path.compare(0, root.size(), root) == 0 &&
             path[root.size()] == '/')) {
            return true;
        }
    }
    return false;
}

std::string without_snap_paths(const std::string& value,
                               const std::vector<std::string>& roots) {
    std::string filtered;
    std::size_t start = 0;
    while (start <= value.size()) {
        const auto end = value.find(':', start);
        const auto path = value.substr(
            start, end == std::string::npos ? std::string::npos : end - start);
        if (!path.empty() && !is_snap_path(path, roots)) {
            if (!filtered.empty()) {
                filtered += ':';
            }
            filtered += path;
        }
        if (end == std::string::npos) {
            break;
        }
        start = end + 1;
    }
    return filtered;
}

}  // namespace

class ScopedGtkEnvironment final {
   public:
    ScopedGtkEnvironment() {
        std::vector<std::string> roots{"/snap"};
        if (const auto* home = std::getenv("HOME")) {
            roots.emplace_back(std::string(home) + "/snap");
        }
        try {
            for (const auto* name : kPathVariables) {
                sanitize(name, roots);
            }
        } catch (...) {
            restore();
            throw;
        }
    }

    ~ScopedGtkEnvironment() { restore(); }

    ScopedGtkEnvironment(const ScopedGtkEnvironment&) = delete;
    ScopedGtkEnvironment& operator=(const ScopedGtkEnvironment&) = delete;

   private:
    struct Variable {
        std::string name;
        std::string original;
        std::string filtered;
    };

    static constexpr const char* kPathVariables[] = {
        "GSETTINGS_SCHEMA_DIR", "GTK_PATH",          "GTK_EXE_PREFIX",
        "GTK_DATA_PREFIX",      "GDK_PIXBUF_MODULEDIR", "GDK_PIXBUF_MODULE_FILE",
        "GTK_IM_MODULE_FILE",   "GIO_MODULE_DIR",    "GIO_EXTRA_MODULES",
        "GI_TYPELIB_PATH",      "XDG_DATA_DIRS",
    };

    void sanitize(const char* name, const std::vector<std::string>& roots) {
        const auto* value = std::getenv(name);
        if (!value) {
            return;
        }
        const std::string original(value);
        const auto filtered = without_snap_paths(original, roots);
        if (filtered == original) {
            return;
        }
        variables_.push_back({name, original, filtered});
        const auto result =
            filtered.empty() ? unsetenv(name) : setenv(name, filtered.c_str(), 1);
        if (result != 0) {
            throw NativeWebviewError(std::string("failed to isolate GTK path ") +
                                     name);
        }
    }

    void restore() noexcept {
        for (auto variable = variables_.rbegin(); variable != variables_.rend();
             ++variable) {
            const auto* current = std::getenv(variable->name.c_str());
            if ((variable->filtered.empty() && current) ||
                (!variable->filtered.empty() &&
                 (!current || variable->filtered != current))) {
                continue;
            }
            if (setenv(variable->name.c_str(), variable->original.c_str(), 1) !=
                0) {
                std::fprintf(stderr, "failed to restore GTK path %s\n",
                             variable->name.c_str());
            }
        }
        variables_.clear();
    }

    std::vector<Variable> variables_;
};

}  // namespace rti::demo::ui::native::detail
