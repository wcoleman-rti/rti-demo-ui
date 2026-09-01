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

"""Card and SDK-owned state components."""

from __future__ import annotations

import math
import re
from typing import Dict, List, Optional

from .types import (
    CardArea,
    Freshness,
    GridBounds,
    Layout,
    Severity,
    coerce_card_area,
    coerce_freshness,
    coerce_severity,
    copy_json_value,
    require_card_span,
    require_finite,
    require_non_empty,
    require_positive_int,
    require_valid_bounds,
    require_valid_color,
)


class _Component:
    def __init__(self, model, component_id: str, component_type: str) -> None:
        self._model = model
        self.id = component_id
        self.type = component_type
        self.revision = 0
        self._card_id = None

    def _mutated(self) -> None:
        if self._card_id is None:
            raise RuntimeError("Component: component is not attached to a card")
        self._model.commit_component_locked(self._card_id, self.id)
        self.revision = self._model.revision

    def _envelope(self, data: dict) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "revision": self.revision,
            "data": data,
        }


class Card:
    """Titled grouping of components. Owned exclusively by DemoUiApp."""

    def __init__(
        self,
        model,
        card_id: str,
        title: str,
        area=CardArea.main,
        span: int = 1,
    ) -> None:
        require_non_empty(title, "title", "Card: ")
        area = coerce_card_area(area)
        require_card_span(span)
        self._model = model
        self.id = card_id
        self.title = title
        self.area = area
        self.span = span
        self._components: List[_Component] = []

    def set_area(self, area) -> None:
        area = coerce_card_area(area)
        self._model.check_owner()
        self._model.ensure_running()
        if area == self.area:
            return
        if area == CardArea.sidebar and any(
            card is not self and card.area == CardArea.sidebar
            for card in self._model.cards
        ):
            raise ValueError("DemoUiApp: at most one sidebar card is permitted")
        if (
            self.area == CardArea.sidebar
            and area == CardArea.main
            and self._model.layout == Layout.sidebar_main
        ):
            raise ValueError(
                "DemoUiApp: sidebar-main requires exactly one sidebar card"
            )
        self.area = area
        self._model.commit_card_locked(self.id)

    def set_span(self, span: int) -> None:
        require_card_span(span)
        self._model.check_owner()
        self._model.ensure_running()
        if span == self.span:
            return
        self.span = span
        self._model.commit_card_locked(self.id)

    def _add_component(self, component: _Component) -> _Component:
        self._components.append(component)
        component._card_id = self.id
        self._model.commit_card_locked(self.id)
        component.revision = self._model.revision
        return component

    def add_scene_2d(
        self, width: int, height: int, bounds: GridBounds
    ) -> "Scene2DViewport":
        require_positive_int(width, "width", "Scene2DViewport: ")
        require_positive_int(height, "height", "Scene2DViewport: ")
        require_valid_bounds(bounds, "Scene2DViewport: ")
        self._model.check_owner()
        self._model.ensure_running()
        scene = Scene2DViewport(
            self._model,
            self._model.next_component_id("scene"),
            width,
            height,
            bounds,
        )
        return self._add_component(scene)

    def add_scene_3d(
        self,
        asset: str,
        camera: Optional[dict] = None,
        background: str = "#0a0e17",
        grid: bool = False,
    ) -> "Scene3DViewport":
        self._model.check_owner()
        self._model.ensure_running()
        scene = Scene3DViewport(
            self._model,
            self._model.next_component_id("scene3d"),
            asset,
            camera,
            background,
            grid,
        )
        return self._add_component(scene)

    def add_table(self, columns, rows, empty_state: str = "") -> "Table":
        self._model.check_owner()
        self._model.ensure_running()
        table = Table(
            self._model,
            self._model.next_component_id("table"),
            columns,
            rows,
            empty_state,
        )
        return self._add_component(table)

    def add_metric(self, label: str, value, severity=None) -> "Metric":
        self._model.check_owner()
        self._model.ensure_running()
        metric = Metric(
            self._model,
            self._model.next_component_id("metric"),
            label,
            value,
            severity,
        )
        return self._add_component(metric)

    def add_text(self, text: str, severity=None) -> "Text":
        self._model.check_owner()
        self._model.ensure_running()
        component = Text(
            self._model,
            self._model.next_component_id("text"),
            text,
            severity,
        )
        return self._add_component(component)

    def add_badge(self, text: str, severity=Severity.success) -> "Badge":
        self._model.check_owner()
        self._model.ensure_running()
        component = Badge(
            self._model,
            self._model.next_component_id("badge"),
            text,
            severity,
        )
        return self._add_component(component)

    def add_log(self, entries, empty_state: str = "", max_entries: int = 100) -> "Log":
        self._model.check_owner()
        self._model.ensure_running()
        component = Log(
            self._model,
            self._model.next_component_id("log"),
            entries,
            empty_state,
            max_entries,
        )
        return self._add_component(component)

    def add_custom_component(
        self, type: str, data, id: Optional[str] = None
    ) -> "CustomComponent":
        self._model.check_owner()
        self._model.ensure_running()
        component_id = id or self._model.next_component_id("component")
        component = CustomComponent(self._model, component_id, type, data)
        return self._add_component(component)

    def to_dict(self) -> dict:
        self._model.check_owner()
        self._model.ensure_running()
        return {
            "id": self.id,
            "title": self.title,
            "area": self.area.value,
            "span": self.span,
            "components": [component.to_dict() for component in self._components],
        }


class _Entity:
    __slots__ = ("id", "x", "y", "heading", "color", "status", "freshness")

    def __init__(self, id, x, y, heading, color, status, freshness):
        self.id = id
        self.x = x
        self.y = y
        self.heading = heading
        self.color = color
        self.status = status
        self.freshness = freshness

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "x": self.x,
            "y": self.y,
            "heading": self.heading,
            "color": self.color,
            "status": self.status.value,
            "freshness": self.freshness.value,
        }


class Scene2DViewport(_Component):
    """Entities and directed links in a bounded 2D scene."""

    _ERROR_PREFIX = "Scene2DViewport: "

    def __init__(
        self, model, scene_id: str, width: int, height: int, bounds: GridBounds
    ) -> None:
        super().__init__(model, scene_id, "scene2d")
        self.width = width
        self.height = height
        self.bounds = tuple(bounds)
        self._entities: Dict[str, _Entity] = {}
        self._links: List[tuple] = []

    def add_entity(
        self,
        id: str,
        x: float,
        y: float,
        heading: float = 0.0,
        color: str = "var(--sdk-accent)",
        status: Severity = Severity.success,
        freshness: Freshness = Freshness.fresh,
    ) -> None:
        prefix = self._ERROR_PREFIX
        require_non_empty(id, "id", prefix)
        require_finite(x, "x", prefix)
        require_finite(y, "y", prefix)
        require_finite(heading, "heading", prefix)
        require_valid_color(color, prefix)
        status = coerce_severity(status)
        freshness = coerce_freshness(freshness)
        self._model.check_owner()
        self._model.ensure_running()
        if id in self._entities:
            raise ValueError(f"{prefix}entity '{id}' already exists")
        self._entities[id] = _Entity(id, x, y, heading, color, status, freshness)
        self._mutated()

    def update_entity(
        self,
        id: str,
        x: Optional[float] = None,
        y: Optional[float] = None,
        heading: Optional[float] = None,
        status: Optional[Severity] = None,
        freshness: Optional[Freshness] = None,
    ) -> None:
        prefix = self._ERROR_PREFIX
        if x is not None:
            require_finite(x, "x", prefix)
        if y is not None:
            require_finite(y, "y", prefix)
        if heading is not None:
            require_finite(heading, "heading", prefix)
        self._model.check_owner()
        self._model.ensure_running()
        entity = self._entities.get(id)
        if entity is None:
            raise ValueError(f"{prefix}entity '{id}' does not exist")
        if x is not None:
            entity.x = x
        if y is not None:
            entity.y = y
        if heading is not None:
            entity.heading = heading
        if status is not None:
            entity.status = coerce_severity(status)
        if freshness is not None:
            entity.freshness = coerce_freshness(freshness)
        self._mutated()

    def remove_entity(self, id: str) -> None:
        prefix = self._ERROR_PREFIX
        self._model.check_owner()
        self._model.ensure_running()
        if id not in self._entities:
            raise ValueError(f"{prefix}entity '{id}' does not exist")
        del self._entities[id]
        self._links = [link for link in self._links if link[0] != id and link[1] != id]
        self._mutated()

    def add_link(
        self, source_id: str, target_id: str, status: Severity = Severity.success
    ) -> None:
        prefix = self._ERROR_PREFIX
        status = coerce_severity(status)
        self._model.check_owner()
        self._model.ensure_running()
        if source_id not in self._entities:
            raise ValueError(f"{prefix}link source '{source_id}' does not exist")
        if target_id not in self._entities:
            raise ValueError(f"{prefix}link target '{target_id}' does not exist")
        if any(
            source == source_id and target == target_id
            for source, target, _ in self._links
        ):
            raise ValueError(
                f"{prefix}link ({source_id} -> {target_id}) already exists"
            )
        self._links.append((source_id, target_id, status))
        self._mutated()

    def remove_link(self, source_id: str, target_id: str) -> None:
        prefix = self._ERROR_PREFIX
        self._model.check_owner()
        self._model.ensure_running()
        for index, (source, target, _) in enumerate(self._links):
            if source == source_id and target == target_id:
                del self._links[index]
                self._mutated()
                return
        raise ValueError(f"{prefix}link ({source_id} -> {target_id}) does not exist")

    def to_dict(self) -> dict:
        return self._envelope(
            {
                "width": self.width,
                "height": self.height,
                "grid_bounds": list(self.bounds),
                "entities": [entity.to_dict() for entity in self._entities.values()],
                "links": [
                    {
                        "source_id": source,
                        "target_id": target,
                        "status": status.value,
                    }
                    for source, target, status in self._links
                ],
            }
        )


class Scene3DViewport(_Component):
    """GLB scene configuration and application-owned local node targets."""

    _ERROR_PREFIX = "Scene3DViewport: "
    _PATH_ESCAPE = re.compile(r"^(?:[^~/]|~[01])+$")
    _MAX_BATCH_SIZE = 1000

    def __init__(self, model, scene_id, asset, camera, background, grid):
        super().__init__(model, scene_id, "scene3d")
        self._config = self._make_config(
            asset, camera, background, grid, model.static_root
        )
        self._nodes = {}
        self._used_ids = set()

    @classmethod
    def _invalid_asset(cls):
        raise ValueError(
            cls._ERROR_PREFIX
            + "asset must be an absolute same-origin .glb path under static_root"
        )

    @classmethod
    def _validate_asset(cls, asset, static_root):
        if (
            not isinstance(asset, str)
            or not asset.startswith("/")
            or asset.startswith("//")
            or asset.startswith("/sdk/")
            or not asset.endswith(".glb")
            or "?" in asset
            or "#" in asset
            or "\x00" in asset
            or "://" in asset
            or any(segment == ".." for segment in asset.split("/"))
        ):
            cls._invalid_asset()
        if static_root is not None:
            candidate = (static_root / asset[1:]).resolve(strict=False)
            if (
                candidate != static_root
                and static_root not in candidate.parents
                or not candidate.is_file()
            ):
                cls._invalid_asset()

    @classmethod
    def _vector(cls, value, length, kind):
        valid = (
            isinstance(value, (list, tuple))
            and len(value) == length
            and all(
                isinstance(item, (int, float))
                and not isinstance(item, bool)
                and math.isfinite(item)
                for item in value
            )
        )
        if not valid:
            if kind == "rotation":
                raise ValueError(
                    cls._ERROR_PREFIX
                    + "rotation must be a unit quaternion in [x, y, z, w] order"
                )
            if kind == "scale":
                raise ValueError(
                    cls._ERROR_PREFIX
                    + "scale values must be finite and greater than zero"
                )
            raise ValueError(
                cls._ERROR_PREFIX
                + "transform arrays must have exactly 3, 4, and 3 finite values"
            )
        result = [float(item) for item in value]
        if kind == "rotation" and abs(sum(item * item for item in result) - 1.0) > 1e-6:
            raise ValueError(
                cls._ERROR_PREFIX
                + "rotation must be a unit quaternion in [x, y, z, w] order"
            )
        if kind == "scale" and any(item <= 0 for item in result):
            raise ValueError(
                cls._ERROR_PREFIX + "scale values must be finite and greater than zero"
            )
        return result

    @classmethod
    def _camera(cls, camera):
        result = {
            "mode": "orbit",
            "position": [4.0, 3.0, 5.0],
            "target": [0.0, 0.0, 0.0],
            "min_distance": 0.1,
            "max_distance": 1000.0,
        }
        if camera is not None:
            if not isinstance(camera, dict):
                raise ValueError(cls._ERROR_PREFIX + "camera configuration is invalid")
            result.update(copy_json_value(camera, cls._ERROR_PREFIX))
        try:
            if result["mode"] != "orbit":
                raise ValueError
            position = cls._vector(result["position"], 3, "position")
            target = cls._vector(result["target"], 3, "target")
            minimum = result["min_distance"]
            maximum = result["max_distance"]
            if (
                not isinstance(minimum, (int, float))
                or isinstance(minimum, bool)
                or not isinstance(maximum, (int, float))
                or isinstance(maximum, bool)
                or not math.isfinite(minimum)
                or not math.isfinite(maximum)
                or minimum <= 0
                or minimum >= maximum
                or position == target
            ):
                raise ValueError
        except (KeyError, TypeError, ValueError):
            raise ValueError(cls._ERROR_PREFIX + "camera configuration is invalid")
        return {
            "mode": "orbit",
            "position": position,
            "target": target,
            "min_distance": float(minimum),
            "max_distance": float(maximum),
        }

    @classmethod
    def _make_config(cls, asset, camera, background, grid, static_root):
        cls._validate_asset(asset, static_root)
        if not isinstance(background, str) or not re.fullmatch(
            r"#[0-9A-Fa-f]{6}", background
        ):
            raise ValueError(cls._ERROR_PREFIX + "camera configuration is invalid")
        if not isinstance(grid, bool):
            raise ValueError(cls._ERROR_PREFIX + "camera configuration is invalid")
        return {
            "asset": asset,
            "nodes": [],
            "camera": cls._camera(camera),
            "background": background,
            "grid": grid,
        }

    @classmethod
    def _validate_path(cls, path):
        if (
            not isinstance(path, str)
            or not path
            or any(
                not segment or not cls._PATH_ESCAPE.fullmatch(segment)
                for segment in path.split("/")
            )
        ):
            raise ValueError(cls._ERROR_PREFIX + "node path is invalid")

    @classmethod
    def _node(cls, operation, current=None):
        node_id = operation.get("id") if isinstance(operation, dict) else None
        if not isinstance(node_id, str) or not node_id:
            raise ValueError(cls._ERROR_PREFIX + "node ID must be non-empty")
        result = dict(
            current
            or {
                "id": node_id,
                "path": operation.get("path"),
                "position": [0.0, 0.0, 0.0],
                "rotation": [0.0, 0.0, 0.0, 1.0],
                "scale": [1.0, 1.0, 1.0],
                "visible": True,
                "status": Severity.success.value,
            }
        )
        if "path" in operation:
            cls._validate_path(operation["path"])
            result["path"] = operation["path"]
        elif current is None:
            raise ValueError(cls._ERROR_PREFIX + "node path is invalid")
        for field, length, kind in (
            ("position", 3, "position"),
            ("rotation", 4, "rotation"),
            ("scale", 3, "scale"),
        ):
            if field in operation:
                result[field] = cls._vector(operation[field], length, kind)
        if "visible" in operation:
            if not isinstance(operation["visible"], bool):
                raise ValueError(
                    cls._ERROR_PREFIX
                    + "transform arrays must have exactly 3, 4, and 3 finite values"
                )
            result["visible"] = operation["visible"]
        if "status" in operation:
            result["status"] = coerce_severity(operation["status"]).value
        return result

    def _apply(self, operations):
        if (
            not isinstance(operations, list)
            or not operations
            or len(operations) > self._MAX_BATCH_SIZE
        ):
            raise ValueError(
                self._ERROR_PREFIX + "batch contains a duplicate operation"
            )
        candidate = {key: dict(value) for key, value in self._nodes.items()}
        seen = set()
        for operation in operations:
            if not isinstance(operation, dict):
                raise ValueError(
                    self._ERROR_PREFIX + "batch contains a duplicate operation"
                )
            node_id = operation.get("id")
            operation_type = operation.get("op")
            operation_key = (operation_type, node_id)
            if operation_key in seen:
                raise ValueError(
                    self._ERROR_PREFIX + "batch contains a duplicate operation"
                )
            seen.add(operation_key)
            if operation_type == "add":
                if node_id in self._used_ids:
                    message = (
                        "node ID is stale"
                        if node_id not in self._nodes
                        else "node ID is already in use"
                    )
                    raise ValueError(self._ERROR_PREFIX + message)
                if node_id in candidate:
                    raise ValueError(self._ERROR_PREFIX + "node ID is already in use")
                candidate[node_id] = self._node(operation)
            elif operation_type == "update":
                if node_id not in candidate:
                    raise ValueError(self._ERROR_PREFIX + "node ID is stale")
                candidate[node_id] = self._node(operation, candidate[node_id])
            elif operation_type == "remove":
                if node_id not in candidate:
                    raise ValueError(self._ERROR_PREFIX + "node ID is stale")
                del candidate[node_id]
            else:
                raise ValueError(
                    self._ERROR_PREFIX + "batch contains a duplicate operation"
                )
        changed = list(candidate.values()) != list(self._nodes.values())
        if changed:
            self._nodes = candidate
            self._used_ids.update(operation.get("id") for operation in operations)
            self._mutated()

    def add_node(
        self,
        id,
        path,
        position=(0, 0, 0),
        rotation=(0, 0, 0, 1),
        scale=(1, 1, 1),
        visible=True,
        status=Severity.success,
    ):
        self._model.check_owner()
        self._model.ensure_running()
        self._apply(
            [
                {
                    "op": "add",
                    "id": id,
                    "path": path,
                    "position": position,
                    "rotation": rotation,
                    "scale": scale,
                    "visible": visible,
                    "status": status,
                }
            ]
        )

    def update_node(
        self, id, position=None, rotation=None, scale=None, visible=None, status=None
    ):
        self._model.check_owner()
        self._model.ensure_running()
        operation = {"op": "update", "id": id}
        for name, value in (
            ("position", position),
            ("rotation", rotation),
            ("scale", scale),
            ("visible", visible),
            ("status", status),
        ):
            if value is not None:
                operation[name] = value
        self._apply([operation])

    def remove_node(self, id):
        self._model.check_owner()
        self._model.ensure_running()
        self._apply([{"op": "remove", "id": id}])

    def apply_node_batch(self, batch):
        self._model.check_owner()
        self._model.ensure_running()
        self._apply(batch)

    def set_config(self, asset, camera=None, background="#0a0e17", grid=False):
        self._model.check_owner()
        self._model.ensure_running()
        replacement = self._make_config(
            asset, camera, background, grid, self._model.static_root
        )
        replacement["nodes"] = [dict(node) for node in self._nodes.values()]
        if replacement != self._config:
            self._config = replacement
            self._mutated()

    def to_dict(self):
        data = dict(self._config)
        data["nodes"] = [dict(node) for node in self._nodes.values()]
        return self._envelope(data)


def _severity(value):
    return coerce_severity(value).value if value is not None else None


def _validate_columns(columns):
    if not isinstance(columns, list) or not columns:
        raise ValueError("Table: columns must be a non-empty list")
    result = []
    ids = set()
    for column in columns:
        if not isinstance(column, dict):
            raise ValueError("Table: columns must contain objects")
        column_id = column.get("id")
        if not isinstance(column_id, str) or not column_id or column_id in ids:
            raise ValueError("Table: column IDs must be non-empty and unique")
        if not isinstance(column.get("label"), str) or not column["label"]:
            raise ValueError("Table: column labels must be non-empty strings")
        ids.add(column_id)
        result.append(copy_json_value(column, "Table: "))
    return result


def _validate_rows(rows, columns):
    if not isinstance(rows, list):
        raise ValueError("Table: rows must be a list")
    column_ids = {column["id"] for column in columns}
    result = []
    ids = set()
    for row in rows:
        if (
            not isinstance(row, dict)
            or not isinstance(row.get("id"), str)
            or not row["id"]
            or row["id"] in ids
        ):
            raise ValueError("Table: row IDs must be non-empty and unique")
        if not isinstance(row.get("cells"), dict) or not set(row["cells"]).issubset(
            column_ids
        ):
            raise ValueError("Table: row cells must reference declared columns")
        if "severity" in row:
            _severity(row["severity"])
        ids.add(row["id"])
        result.append(copy_json_value(row, "Table: "))
    return result


class Table(_Component):
    def __init__(self, model, component_id, columns, rows, empty_state):
        super().__init__(model, component_id, "table")
        self.columns = _validate_columns(columns)
        self.rows = _validate_rows(rows, self.columns)
        self.empty_state = empty_state

    def set_rows(self, rows):
        replacement = _validate_rows(rows, self.columns)
        self._model.check_owner()
        self._model.ensure_running()
        self.rows = replacement
        self._mutated()

    def upsert_row(self, row):
        replacement = _validate_rows([row], self.columns)[0]
        self._model.check_owner()
        self._model.ensure_running()
        for index, existing in enumerate(self.rows):
            if existing["id"] == replacement["id"]:
                self.rows[index] = replacement
                self._mutated()
                return
        self.rows.append(replacement)
        self._mutated()

    def remove_row(self, id: str):
        self._model.check_owner()
        self._model.ensure_running()
        for index, row in enumerate(self.rows):
            if row["id"] == id:
                del self.rows[index]
                self._mutated()
                return
        raise ValueError(f"Table: row '{id}' does not exist")

    def to_dict(self):
        return self._envelope(
            {
                "columns": copy_json_value(self.columns),
                "rows": copy_json_value(self.rows),
                "empty_state": self.empty_state,
            }
        )


class _ScalarComponent(_Component):
    def __init__(self, model, component_id, component_type, data):
        super().__init__(model, component_id, component_type)
        self.data = data

    def to_dict(self):
        return self._envelope(copy_json_value(self.data))


class Metric(_ScalarComponent):
    def __init__(self, model, component_id, label, value, severity):
        require_non_empty(label, "label", "Metric: ")
        super().__init__(
            model,
            component_id,
            "metric",
            {
                "label": label,
                "value": copy_json_value(value),
                "severity": _severity(severity),
            },
        )

    def set_value(self, value, severity=None):
        replacement = {
            "label": self.data["label"],
            "value": copy_json_value(value),
            "severity": _severity(severity),
        }
        self._model.check_owner()
        self._model.ensure_running()
        self.data = replacement
        self._mutated()


class Text(_ScalarComponent):
    def __init__(self, model, component_id, text, severity):
        require_non_empty(text, "text", "Text: ")
        super().__init__(
            model,
            component_id,
            "text",
            {"text": text, "severity": _severity(severity)},
        )

    def set_text(self, text, severity=None):
        require_non_empty(text, "text", "Text: ")
        replacement = {"text": text, "severity": _severity(severity)}
        self._model.check_owner()
        self._model.ensure_running()
        self.data = replacement
        self._mutated()


class Badge(Text):
    def __init__(self, model, component_id, text, severity):
        require_non_empty(text, "text", "Badge: ")
        _Component.__init__(self, model, component_id, "badge")
        self.data = {"text": text, "severity": _severity(severity or Severity.success)}

    def set_text(self, text, severity=None):
        require_non_empty(text, "text", "Badge: ")
        replacement = {
            "text": text,
            "severity": _severity(severity or Severity.success),
        }
        self._model.check_owner()
        self._model.ensure_running()
        self.data = replacement
        self._mutated()


def _validate_log_entries(entries):
    if not isinstance(entries, list):
        raise ValueError("Log: entries must be a list")
    result = []
    ids = set()
    for entry in entries:
        if (
            not isinstance(entry, dict)
            or not isinstance(entry.get("id"), str)
            or not entry["id"]
            or entry["id"] in ids
        ):
            raise ValueError("Log: entry IDs must be non-empty and unique")
        if not isinstance(entry.get("timestamp"), str) or not entry["timestamp"]:
            raise ValueError("Log: timestamp must be a non-empty string")
        if not isinstance(entry.get("message"), str):
            raise ValueError("Log: message must be a string")
        if "severity" in entry:
            _severity(entry["severity"])
        ids.add(entry["id"])
        result.append(copy_json_value(entry, "Log: "))
    return result


class Log(_Component):
    def __init__(self, model, component_id, entries, empty_state, max_entries):
        super().__init__(model, component_id, "log")
        require_positive_int(max_entries, "max_entries", "Log: ")
        self.entries = _validate_log_entries(entries)
        self.max_entries = max_entries
        self.empty_state = empty_state
        self.entries = self.entries[-max_entries:]

    def append(self, entry):
        replacement = _validate_log_entries([entry])[0]
        self._model.check_owner()
        self._model.ensure_running()
        if any(existing["id"] == replacement["id"] for existing in self.entries):
            raise ValueError("Log: entry ID must be unique")
        self.entries = (self.entries + [replacement])[-self.max_entries :]
        self._mutated()

    def clear(self):
        self._model.check_owner()
        self._model.ensure_running()
        self.entries = []
        self._mutated()

    def to_dict(self):
        return self._envelope(
            {
                "entries": copy_json_value(self.entries),
                "empty_state": self.empty_state,
                "max_entries": self.max_entries,
            }
        )


class CustomComponent(_Component):
    def __init__(self, model, component_id, component_type, data):
        require_non_empty(component_id, "id", "CustomComponent: ")
        require_non_empty(component_type, "type", "CustomComponent: ")
        if component_type in {"scene2d", "table", "metric", "text", "badge", "log"}:
            raise ValueError("CustomComponent: type is reserved")
        super().__init__(model, component_id, component_type)
        self.data = copy_json_value(data, "CustomComponent: ")

    def set_data(self, data):
        replacement = copy_json_value(data, "CustomComponent: ")
        self._model.check_owner()
        self._model.ensure_running()
        self.data = replacement
        self._mutated()

    def update_data(self, path, value, create_missing=False):
        self._model.check_owner()
        self._model.ensure_running()
        self.data = self._model.update_value(self.data, path, value, create_missing)
        self._mutated()

    def to_dict(self):
        return self._envelope(copy_json_value(self.data))
