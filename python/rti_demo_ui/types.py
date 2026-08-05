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


def copy_json_value(value: Any, error_prefix: str = "") -> Any:
    try:
        json.dumps(value, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{error_prefix}data must be JSON-compatible") from error
    return deepcopy(value)
