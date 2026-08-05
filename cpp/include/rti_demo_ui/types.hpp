// Shared telemetry/pose types plus the generic Severity/Freshness model (see
// docs/architecture.md §7.1, §7.4).
#pragma once

#include <array>
#include <cmath>
#include <regex>
#include <stdexcept>
#include <string>

namespace rti::demo::ui {

using GridBounds = std::array<double, 4>;

enum class Severity { success, warning, danger };
enum class Freshness { fresh, aging, stale };

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

}  // namespace detail
}  // namespace rti::demo::ui
