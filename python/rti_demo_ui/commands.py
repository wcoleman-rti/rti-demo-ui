"""Opt-in local command registration and the documented schema subset."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional

from .types import copy_json_value

COMMAND_NAME = re.compile(r"^[a-z][a-z0-9-]{0,62}$")
SCHEMA_KEYWORDS = {
    "type",
    "properties",
    "required",
    "items",
    "enum",
    "minimum",
    "maximum",
    "minLength",
    "maxLength",
    "additionalProperties",
}


class CommandSchema:
    def __init__(self, schema: dict):
        self.schema = _validate_schema_definition(schema)

    def validate(self, value: Any) -> list[dict]:
        details: list[dict] = []
        _validate_instance(self.schema, value, "$", details)
        return details


@dataclass(frozen=True)
class CommandConfirmation:
    title: str
    message: str


@dataclass(frozen=True)
class Command:
    name: str
    schema: CommandSchema
    handler: Callable[[Any], Any | Awaitable[Any]]
    confirmation: Optional[CommandConfirmation] = None


def _validate_schema_definition(schema: dict) -> dict:
    if not isinstance(schema, dict):
        raise ValueError("CommandSchema: schema must be an object")
    unsupported = set(schema) - SCHEMA_KEYWORDS
    if unsupported:
        raise ValueError(
            f"CommandSchema: unsupported keyword '{sorted(unsupported)[0]}'"
        )
    if "type" in schema and (
        not isinstance(schema["type"], str)
        or schema["type"]
        not in {"object", "array", "string", "number", "integer", "boolean", "null"}
    ):
        raise ValueError("CommandSchema: type must be one schema type string")
    if "properties" in schema:
        if not isinstance(schema["properties"], dict):
            raise ValueError("CommandSchema: properties must be an object")
        for name, child in schema["properties"].items():
            if not isinstance(name, str):
                raise ValueError("CommandSchema: property names must be strings")
            _validate_schema_definition(child)
    if "required" in schema:
        if not isinstance(schema["required"], list) or any(
            not isinstance(name, str) for name in schema["required"]
        ):
            raise ValueError("CommandSchema: required must be a list of strings")
        if len(set(schema["required"])) != len(schema["required"]):
            raise ValueError("CommandSchema: required names must be unique")
        if "properties" in schema and any(
            name not in schema["properties"] for name in schema["required"]
        ):
            raise ValueError(
                "CommandSchema: required names must be declared properties"
            )
    if "items" in schema:
        if not isinstance(schema["items"], dict):
            raise ValueError("CommandSchema: items must be one schema object")
        _validate_schema_definition(schema["items"])
    if "enum" in schema:
        if not isinstance(schema["enum"], list):
            raise ValueError("CommandSchema: enum must be an array")
        copy_json_value(schema["enum"], "CommandSchema: ")
    if "additionalProperties" in schema and not isinstance(
        schema["additionalProperties"], bool
    ):
        raise ValueError("CommandSchema: additionalProperties must be boolean")
    for keyword in ("minimum", "maximum"):
        if keyword in schema and (
            not isinstance(schema[keyword], (int, float))
            or isinstance(schema[keyword], bool)
        ):
            raise ValueError(f"CommandSchema: {keyword} must be a number")
    for keyword in ("minLength", "maxLength"):
        if keyword in schema and (
            not isinstance(schema[keyword], int)
            or isinstance(schema[keyword], bool)
            or schema[keyword] < 0
        ):
            raise ValueError(f"CommandSchema: {keyword} must be a non-negative integer")
    return copy_json_value(schema, "CommandSchema: ")


def _type_matches(schema_type: str, value: Any) -> bool:
    if schema_type == "null":
        return value is None
    if schema_type == "boolean":
        return isinstance(value, bool)
    if schema_type == "object":
        return isinstance(value, dict)
    if schema_type == "array":
        return isinstance(value, list)
    if schema_type == "string":
        return isinstance(value, str)
    if schema_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if schema_type == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return True


def _validate_instance(
    schema: dict, value: Any, path: str, details: list[dict]
) -> None:
    schema_type = schema.get("type")
    if schema_type is not None and not _type_matches(schema_type, value):
        details.append({"path": path, "message": f"expected {schema_type}"})
        return
    if "enum" in schema and value not in schema["enum"]:
        details.append({"path": path, "message": "value is not one of enum"})
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        for name in schema.get("required", []):
            if name not in value:
                details.append({"path": f"{path}.{name}", "message": "is required"})
        if schema.get("additionalProperties", True) is False:
            for name in value:
                if name not in properties:
                    details.append(
                        {
                            "path": f"{path}.{name}",
                            "message": "additional property is not allowed",
                        }
                    )
        for name, child in properties.items():
            if name in value:
                _validate_instance(child, value[name], f"{path}.{name}", details)
    if isinstance(value, list) and isinstance(schema.get("items"), dict):
        for index, item in enumerate(value):
            _validate_instance(schema["items"], item, f"{path}[{index}]", details)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            details.append({"path": path, "message": "is below minimum"})
        if "maximum" in schema and value > schema["maximum"]:
            details.append({"path": path, "message": "is above maximum"})
    if isinstance(value, str):
        if "minLength" in schema and len(value) < schema["minLength"]:
            details.append({"path": path, "message": "is shorter than minLength"})
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            details.append({"path": path, "message": "is longer than maxLength"})
