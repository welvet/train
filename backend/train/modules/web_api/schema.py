from __future__ import annotations

import copy
import types
from dataclasses import fields, is_dataclass
from typing import Any, get_args, get_origin, get_type_hints

from train.domain.state import SystemState
from train.domain.vocabulary import PUBLIC_EVENTS

STATE_API_VERSION = 1


def openapi_document() -> dict[str, object]:
    schemas = _dataclass_schemas(SystemState)
    schemas["StateEnvelope"] = {
        "type": "object",
        "properties": {
            "version": {"type": "integer", "const": STATE_API_VERSION},
            "state": {"$ref": "#/components/schemas/SystemState"},
        },
        "required": ["version", "state"],
        "additionalProperties": False,
    }

    public_event_refs: list[dict[str, str]] = []
    for spec in PUBLIC_EVENTS:
        component_name = _pascal_case(spec.name)
        data_name = f"{component_name}Data"
        schemas[data_name] = copy.deepcopy(dict(spec.data_schema))
        event_schema: dict[str, object] = {
            "type": "object",
            "properties": {
                "type": {"type": "string", "const": spec.name},
                "data": {"$ref": f"#/components/schemas/{data_name}"},
            },
            "required": ["type"],
            "additionalProperties": False,
        }
        if spec.data_schema.get("required"):
            event_schema["required"] = ["type", "data"]
        schemas[component_name] = event_schema
        public_event_refs.append({"$ref": f"#/components/schemas/{component_name}"})

    schemas["PublicEvent"] = {
        "oneOf": public_event_refs,
    }
    schemas["ApiError"] = {
        "type": "object",
        "properties": {"error": {"type": "string"}},
        "required": ["error"],
        "additionalProperties": True,
    }
    schemas["CommandResponse"] = {
        "type": "object",
        "properties": {
            "command": {"type": "object", "additionalProperties": True},
            "completed": {"type": "boolean", "const": True},
        },
        "required": ["command", "completed"],
        "additionalProperties": False,
    }

    return {
        "openapi": "3.1.0",
        "info": {
            "title": "Train Web API",
            "version": str(STATE_API_VERSION),
        },
        "paths": {
            "/api/state": {
                "get": {
                    "operationId": "getSystemState",
                    "responses": {
                        "200": {
                            "description": "Current authoritative system state",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "$ref": "#/components/schemas/StateEnvelope"
                                    }
                                }
                            },
                        }
                    },
                }
            },
            "/api/events": {
                "post": {
                    "operationId": "publishEvent",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": "#/components/schemas/PublicEvent"
                                }
                            }
                        },
                    },
                    "responses": {
                        "200": {
                            "description": "Command completed",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "$ref": "#/components/schemas/CommandResponse"
                                    }
                                }
                            },
                        },
                        "400": _error_response("Invalid public event"),
                        "404": _error_response("Unknown resource"),
                        "409": _error_response("Hardware rejected the command"),
                        "504": _error_response("Command outcome is unknown"),
                    },
                }
            },
        },
        "components": {"schemas": schemas},
    }


def _error_response(description: str) -> dict[str, object]:
    return {
        "description": description,
        "content": {
            "application/json": {
                "schema": {"$ref": "#/components/schemas/ApiError"}
            }
        },
    }


def _dataclass_schemas(root: type[object]) -> dict[str, object]:
    schemas: dict[str, object] = {}

    def schema_for(annotation: object) -> dict[str, object]:
        origin = get_origin(annotation)
        arguments = get_args(annotation)

        if annotation is str:
            return {"type": "string"}
        if annotation is bool:
            return {"type": "boolean"}
        if annotation is int:
            return {"type": "integer"}
        if annotation is float:
            return {"type": "number"}
        if origin is dict:
            return {
                "type": "object",
                "additionalProperties": schema_for(arguments[1]),
            }
        if origin in (types.UnionType, getattr(types, "UnionType", object)):
            return {"anyOf": [schema_for(argument) for argument in arguments]}
        if annotation is type(None):
            return {"type": "null"}
        if isinstance(annotation, type) and is_dataclass(annotation):
            name = annotation.__name__
            if name not in schemas:
                schemas[name] = {}
                hints = get_type_hints(annotation)
                properties = {
                    field.name: schema_for(hints[field.name])
                    for field in fields(annotation)
                }
                schemas[name] = {
                    "type": "object",
                    "properties": properties,
                    "required": list(properties),
                    "additionalProperties": False,
                }
            return {"$ref": f"#/components/schemas/{name}"}
        raise TypeError(f"unsupported public state annotation: {annotation!r}")

    schema_for(root)
    return schemas


def _pascal_case(value: str) -> str:
    return "".join(part.capitalize() for part in value.split("_"))
