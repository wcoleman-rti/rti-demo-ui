#
# (c) 2026 Copyright, Real-Time Innovations, Inc.  All rights reserved.
#
# RTI grants Licensee a license to use, modify, compile, and create derivative
# works of the Software.  Licensee has the right to distribute object form
# only for use with RTI products.  The Software is provided "as is", with no
# warranty of any type, including any warranty for fitness for any purpose.
# RTI is under no obligation to maintain or support the Software.  RTI shall
# not be liable for any incidental or consequential damages arising out of the
# use or inability to use the software.
#

"""Shared Severity/Freshness model and validation helpers.

See docs/architecture.md §7.1 and §7.4.
"""

from __future__ import annotations

import math
import json
import re
from enum import Enum
from copy import deepcopy
from typing import Any, Tuple

GridBounds = Tuple[float, float, float, float]

_COLOR_PATTERN = re.compile(r"^(#[0-9A-Fa-f]{6}|var\(--[A-Za-z0-9-]+\))$")


class Severity(str, Enum):
    success = "success"
    warning = "warning"
    danger = "danger"


class Freshness(str, Enum):
    fresh = "fresh"
    aging = "aging"
    stale = "stale"


class Theme(str, Enum):
    dark = "dark"
    light = "light"


class Layout(str, Enum):
    auto = "auto"
    grid_2 = "grid-2"
    grid_3 = "grid-3"
    sidebar_main = "sidebar-main"


class CardArea(str, Enum):
    main = "main"
    sidebar = "sidebar"


FRESHNESS_OPACITY = {
    Freshness.fresh: 1.0,
    Freshness.aging: 0.65,
    Freshness.stale: 0.35,
}


def require_non_empty(value: str, name: str, error_prefix: str) -> None:
    if not value:
        raise ValueError(f"{error_prefix}{name} must not be empty")


def require_positive_int(value: int, name: str, error_prefix: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{error_prefix}{name} must be a positive integer")


def require_finite(value: float, name: str, error_prefix: str) -> None:
    if (
        not isinstance(value, (int, float))
        or isinstance(value, bool)
        or not math.isfinite(value)
    ):
        raise ValueError(f"{error_prefix}{name} must be finite")


def require_valid_bounds(bounds: GridBounds, error_prefix: str) -> None:
    if len(bounds) != 4:
        raise ValueError(f"{error_prefix}grid_bounds must have exactly 4 values")
    x_min, x_max, y_min, y_max = bounds
    for name, value in (
        ("x_min", x_min),
        ("x_max", x_max),
        ("y_min", y_min),
        ("y_max", y_max),
    ):
        require_finite(value, name, error_prefix)
    if x_min >= x_max:
        raise ValueError(f"{error_prefix}x_min must be less than x_max")
    if y_min >= y_max:
        raise ValueError(f"{error_prefix}y_min must be less than y_max")


def require_valid_color(color: str, error_prefix: str) -> None:
    if not _COLOR_PATTERN.match(color):
        raise ValueError(
            f"{error_prefix}color must match #RRGGBB or var(--name), got {color!r}"
        )


def coerce_severity(value) -> Severity:
    return value if isinstance(value, Severity) else Severity(value)


def coerce_freshness(value) -> Freshness:
    return value if isinstance(value, Freshness) else Freshness(value)


def coerce_theme(value) -> Theme:
    if isinstance(value, Theme):
        return value
    if not isinstance(value, str):
        raise ValueError("DemoUiApp: invalid theme")
    return Theme(value)


def coerce_layout(value) -> Layout:
    if isinstance(value, Layout):
        return value
    if not isinstance(value, str):
        raise ValueError("DemoUiApp: invalid layout")
    return Layout(value)


def coerce_card_area(value) -> CardArea:
    if isinstance(value, CardArea):
        return value
    if not isinstance(value, str):
        raise ValueError("Card: invalid area")
    return CardArea(value)


def require_card_span(value) -> None:
    if type(value) is not int or value not in (1, 2, 3):
        raise ValueError("Card: span must be an integer from 1 to 3")


def copy_json_value(value: Any, error_prefix: str = "") -> Any:
    try:
        json.dumps(value, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{error_prefix}data must be JSON-compatible") from error
    return deepcopy(value)
