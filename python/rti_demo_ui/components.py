"""Card and SDK-owned state components."""

from __future__ import annotations

from typing import Dict, List, Optional

from .types import (
    Freshness,
    GridBounds,
    Severity,
    coerce_freshness,
    coerce_severity,
    copy_json_value,
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

    def _mutated(self) -> None:
        self._model.bump_revision_locked()
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

    def __init__(self, model, card_id: str, title: str) -> None:
        require_non_empty(title, "title", "Card: ")
        self._model = model
        self.id = card_id
        self.title = title
        self._components: List[_Component] = []

    def _add_component(self, component: _Component) -> _Component:
        self._components.append(component)
        self._model.bump_revision_locked()
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
