"""Card and Scene2DViewport components.

See docs/architecture.md §7.2, §7.4, §8.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from .types import (
    Freshness,
    GridBounds,
    Severity,
    coerce_freshness,
    coerce_severity,
    require_finite,
    require_non_empty,
    require_positive_int,
    require_valid_bounds,
    require_valid_color,
)


class Card:
    """Titled grouping of components. Owned exclusively by DemoUiApp."""

    def __init__(self, model, card_id: str, title: str) -> None:
        require_non_empty(title, "title", "Card: ")
        self._model = model
        self.id = card_id
        self.title = title
        self._components: List["Scene2DViewport"] = []

    def add_scene_2d(
        self, width: int, height: int, bounds: GridBounds
    ) -> "Scene2DViewport":
        require_positive_int(width, "width", "Scene2DViewport: ")
        require_positive_int(height, "height", "Scene2DViewport: ")
        require_valid_bounds(bounds, "Scene2DViewport: ")
        with self._model.lock:
            self._model.ensure_running()
            scene_id = self._model.next_scene_id()
            scene = Scene2DViewport(self._model, scene_id, width, height, bounds)
            self._components.append(scene)
            self._model.bump_revision_locked()
        return scene

    def to_dict(self) -> dict:
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


class Scene2DViewport:
    """Entities and directed links in a bounded 2D scene."""

    _ERROR_PREFIX = "Scene2DViewport: "

    def __init__(
        self, model, scene_id: str, width: int, height: int, bounds: GridBounds
    ) -> None:
        self._model = model
        self.id = scene_id
        self.width = width
        self.height = height
        self.bounds = tuple(bounds)
        self._entities: Dict[str, _Entity] = {}
        self._links: List[tuple] = []  # ordered list of (source_id, target_id, status)

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
        with self._model.lock:
            self._model.ensure_running()
            if id in self._entities:
                raise ValueError(f"{prefix}entity '{id}' already exists")
            self._entities[id] = _Entity(id, x, y, heading, color, status, freshness)
            self._model.bump_revision_locked()

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
        with self._model.lock:
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
            self._model.bump_revision_locked()

    def remove_entity(self, id: str) -> None:
        prefix = self._ERROR_PREFIX
        with self._model.lock:
            self._model.ensure_running()
            if id not in self._entities:
                raise ValueError(f"{prefix}entity '{id}' does not exist")
            del self._entities[id]
            self._links = [
                link for link in self._links if link[0] != id and link[1] != id
            ]
            self._model.bump_revision_locked()

    def add_link(
        self, source_id: str, target_id: str, status: Severity = Severity.success
    ) -> None:
        prefix = self._ERROR_PREFIX
        status = coerce_severity(status)
        with self._model.lock:
            self._model.ensure_running()
            if source_id not in self._entities:
                raise ValueError(f"{prefix}link source '{source_id}' does not exist")
            if target_id not in self._entities:
                raise ValueError(f"{prefix}link target '{target_id}' does not exist")
            for existing_source, existing_target, _ in self._links:
                if existing_source == source_id and existing_target == target_id:
                    raise ValueError(
                        f"{prefix}link ({source_id} -> {target_id}) already exists"
                    )
            self._links.append((source_id, target_id, status))
            self._model.bump_revision_locked()

    def remove_link(self, source_id: str, target_id: str) -> None:
        prefix = self._ERROR_PREFIX
        with self._model.lock:
            self._model.ensure_running()
            for index, (existing_source, existing_target, _) in enumerate(self._links):
                if existing_source == source_id and existing_target == target_id:
                    del self._links[index]
                    self._model.bump_revision_locked()
                    return
            raise ValueError(
                f"{prefix}link ({source_id} -> {target_id}) does not exist"
            )

    def to_dict(self) -> dict:
        return {
            "type": "scene2d",
            "id": self.id,
            "width": self.width,
            "height": self.height,
            "grid_bounds": list(self.bounds),
            "entities": [entity.to_dict() for entity in self._entities.values()],
            "links": [
                {"source_id": source, "target_id": target, "status": status.value}
                for source, target, status in self._links
            ],
        }
