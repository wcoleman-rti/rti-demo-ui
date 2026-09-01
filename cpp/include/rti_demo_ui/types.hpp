/*
 * (c) 2026 Copyright, Real-Time Innovations, Inc.  All rights reserved.
 *
 * RTI grants Licensee a license to use, modify, compile, and create derivative
 * works of the Software.  Licensee has the right to distribute object form
 * only for use with RTI products.  The Software is provided "as is", with no
 * warranty of any type, including any warranty for fitness for any purpose.
 * RTI is under no obligation to maintain or support the Software.  RTI shall
 * not be liable for any incidental or consequential damages arising out of the
 * use or inability to use the software.
 */

// Shared telemetry/pose types plus the generic Severity/Freshness model (see
// docs/architecture.md §7.1, §7.4).
#pragma once

#include <array>
#include <cmath>
#include <nlohmann/json.hpp>
#include <regex>
#include <stdexcept>
#include <string>

namespace rti::demo::ui {

using Json = nlohmann::json;

using GridBounds = std::array<double, 4>;

enum class Severity { success, warning, danger };
enum class Freshness { fresh, aging, stale };
enum class Theme { dark, light };
enum class Layout { automatic, grid_2, grid_3, sidebar_main };
enum class CardArea { main, sidebar };

inline const char* to_string(Severity value) {
    switch (value) {
        case Severity::success:
            return "success";
        case Severity::warning:
            return "warning";
        case Severity::danger:
            return "danger";
    }
    return "success";
}

inline const char* to_string(Freshness value) {
    switch (value) {
        case Freshness::fresh:
            return "fresh";
        case Freshness::aging:
            return "aging";
        case Freshness::stale:
            return "stale";
    }
    return "fresh";
}

inline const char* to_string(Theme value) {
    switch (value) {
        case Theme::dark:
            return "dark";
        case Theme::light:
            return "light";
    }
    throw std::invalid_argument("DemoUiApp: invalid theme");
}

inline const char* to_string(Layout value) {
    switch (value) {
        case Layout::automatic:
            return "auto";
        case Layout::grid_2:
            return "grid-2";
        case Layout::grid_3:
            return "grid-3";
        case Layout::sidebar_main:
            return "sidebar-main";
    }
    throw std::invalid_argument("DemoUiApp: invalid layout");
}

inline const char* to_string(CardArea value) {
    switch (value) {
        case CardArea::main:
            return "main";
        case CardArea::sidebar:
            return "sidebar";
    }
    throw std::invalid_argument("Card: invalid area");
}

inline double freshness_opacity(Freshness value) {
    switch (value) {
        case Freshness::fresh:
            return 1.0;
        case Freshness::aging:
            return 0.65;
        case Freshness::stale:
            return 0.35;
    }
    return 1.0;
}

namespace detail {

inline void require_non_empty(const std::string& value, const std::string& name,
                              const std::string& error_prefix) {
    if (value.empty()) {
        throw std::invalid_argument(error_prefix + name + " must not be empty");
    }
}

inline void require_positive(int value, const std::string& name,
                             const std::string& error_prefix) {
    if (value <= 0) {
        throw std::invalid_argument(error_prefix + name +
                                    " must be a positive integer");
    }
}

inline void require_card_span(int value) {
    if (value < 1 || value > 3) {
        throw std::invalid_argument(
            "Card: span must be an integer from 1 to 3");
    }
}

inline void require_finite(double value, const std::string& name,
                           const std::string& error_prefix) {
    if (!std::isfinite(value)) {
        throw std::invalid_argument(error_prefix + name + " must be finite");
    }
}

inline void require_valid_bounds(const GridBounds& bounds,
                                 const std::string& error_prefix) {
    require_finite(bounds[0], "x_min", error_prefix);
    require_finite(bounds[1], "x_max", error_prefix);
    require_finite(bounds[2], "y_min", error_prefix);
    require_finite(bounds[3], "y_max", error_prefix);
    if (bounds[0] >= bounds[1]) {
        throw std::invalid_argument(error_prefix +
                                    "x_min must be less than x_max");
    }
    if (bounds[2] >= bounds[3]) {
        throw std::invalid_argument(error_prefix +
                                    "y_min must be less than y_max");
    }
}

inline bool is_valid_color(const std::string& color) {
    static const std::regex pattern(
        "^(#[0-9A-Fa-f]{6}|var\\(--[A-Za-z0-9-]+\\))$");
    return std::regex_match(color, pattern);
}

inline void require_valid_color(const std::string& color,
                                const std::string& error_prefix) {
    if (!is_valid_color(color)) {
        throw std::invalid_argument(error_prefix +
                                    "color must match #RRGGBB or var(--name)");
    }
}

inline void require_json_compatible(const Json& value,
                                    const std::string& error_prefix) {
    if (value.is_number_float() && !std::isfinite(value.get<double>())) {
        throw std::invalid_argument(error_prefix +
                                    "data must be JSON-compatible");
    }
    if (value.is_array()) {
        for (const auto& item : value)
            require_json_compatible(item, error_prefix);
    } else if (value.is_object()) {
        for (const auto& item : value.items())
            require_json_compatible(item.value(), error_prefix);
    }
}

}  // namespace detail
}  // namespace rti::demo::ui
