from __future__ import annotations

import copy
import types
from dataclasses import fields, is_dataclass
from typing import Any, get_args, get_origin, get_type_hints

from train.domain.state import SystemState
from train.domain.vocabulary import PUBLIC_EVENTS

STATE_API_VERSION = 4


def openapi_document() -> dict[str, object]:
    schemas = _dataclass_schemas(SystemState)
    schemas["StateEnvelope"] = {
        "type": "object",
        "properties": {
            "version": {"type": "integer", "const": STATE_API_VERSION},
            "snapshot_at": {"type": "number"},
            "state": {"$ref": "#/components/schemas/SystemState"},
            "automation": {"$ref": "#/components/schemas/AutomationSnapshot"},
        },
        "required": ["version", "snapshot_at", "state", "automation"],
        "additionalProperties": False,
    }
    schemas["AutomationDocument"] = {
        "type": "object",
        "description": "Versioned configurable automation tree document",
        "additionalProperties": True,
    }
    schemas["AutomationSnapshot"] = {
        "type": "object",
        "properties": {
            "document": {"$ref": "#/components/schemas/AutomationDocument"},
            "eligible_train_ids": {
                "type": "array",
                "items": {"type": "string"},
            },
            "paused": {"type": "boolean"},
            "statuses": {
                "type": "array",
                "items": {"type": "object", "additionalProperties": True},
            },
        },
        "required": ["document", "eligible_train_ids", "paused", "statuses"],
        "additionalProperties": False,
    }
    schemas["AutomationUpdateResponse"] = {
        "type": "object",
        "properties": {
            "automation": {"$ref": "#/components/schemas/AutomationSnapshot"}
        },
        "required": ["automation"],
        "additionalProperties": False,
    }
    schemas["TrainConfiguration"] = {
        "type": "object",
        "properties": {
            "id": {"type": "string", "minLength": 1},
            "lego_hub_id": {"type": "string", "minLength": 1},
            "ble_address": {"type": "string", "minLength": 1},
            "tag_ids": {
                "type": "array",
                "items": {"type": "string", "minLength": 1},
            },
        },
        "required": ["id", "lego_hub_id", "ble_address", "tag_ids"],
        "additionalProperties": False,
    }
    schemas["TrainsConfiguration"] = {
        "type": "object",
        "properties": {
            "trains": {
                "type": "array",
                "minItems": 1,
                "items": {"$ref": "#/components/schemas/TrainConfiguration"},
            }
        },
        "required": ["trains"],
        "additionalProperties": False,
    }
    schemas["TrainsConfigurationDocument"] = {
        "type": "object",
        "properties": {
            "modified_at": {"type": "number", "exclusiveMinimum": 0},
            "restart_required": {"type": "boolean"},
            "value": {"$ref": "#/components/schemas/TrainsConfiguration"},
        },
        "required": ["modified_at", "restart_required", "value"],
        "additionalProperties": False,
    }
    runtime_id = {
        "type": "string",
        "minLength": 1,
        "maxLength": 16,
        "pattern": "^[A-Za-z0-9_-]+$",
    }
    schemas["ArduinoSwitchConfiguration"] = {
        "type": "object",
        "properties": {
            "id": runtime_id,
            "pin": {"type": "integer", "minimum": 2, "maximum": 10},
            "straight": {"type": "integer", "minimum": 0, "maximum": 180},
            "diverge": {"type": "integer", "minimum": 0, "maximum": 180},
        },
        "required": ["id", "pin", "straight", "diverge"],
        "additionalProperties": False,
    }
    schemas["ArduinoReaderConfiguration"] = {
        "type": "object",
        "properties": {
            "id": runtime_id,
            "ss_pin": {"type": "integer", "minimum": 2, "maximum": 10},
            "read_timeout_ms": {
                "type": "integer",
                "minimum": 1,
                "maximum": 1000,
            },
            "removal_delay_ms": {
                "type": "integer",
                "minimum": 1,
                "maximum": 4294967295,
            },
        },
        "required": ["id", "ss_pin", "read_timeout_ms", "removal_delay_ms"],
        "additionalProperties": False,
    }
    schemas["ArduinoDeviceConfiguration"] = {
        "type": "object",
        "properties": {
            "port": {"type": "string", "minLength": 1},
            "fqbn": {"type": "string", "minLength": 1},
            "baudrate": {
                "type": "integer",
                "minimum": 1,
                "maximum": 4294967295,
            },
            "hub_id": runtime_id,
            "backend_host": {"type": "string", "minLength": 1},
            "backend_port": {"type": "integer", "minimum": 1, "maximum": 65535},
            "servo_settle_ms": {
                "type": "integer",
                "minimum": 1,
                "maximum": 4294967295,
            },
            "reconnect_ms": {
                "type": "integer",
                "minimum": 1,
                "maximum": 4294967295,
            },
            "event_logger_enabled": {"type": "boolean"},
            "switches": {
                "type": "array",
                "maxItems": 8,
                "items": {"$ref": "#/components/schemas/ArduinoSwitchConfiguration"},
            },
            "readers": {
                "type": "array",
                "maxItems": 8,
                "items": {"$ref": "#/components/schemas/ArduinoReaderConfiguration"},
            },
        },
        "required": [
            "port",
            "fqbn",
            "baudrate",
            "hub_id",
            "backend_host",
            "backend_port",
            "servo_settle_ms",
            "reconnect_ms",
            "event_logger_enabled",
            "switches",
            "readers",
        ],
        "additionalProperties": False,
    }
    schemas["ArduinosConfiguration"] = {
        "type": "object",
        "properties": {
            "devices": {
                "type": "object",
                "minProperties": 1,
                "additionalProperties": {
                    "$ref": "#/components/schemas/ArduinoDeviceConfiguration"
                },
            }
        },
        "required": ["devices"],
        "additionalProperties": False,
    }
    schemas["ArduinosConfigurationDocument"] = {
        "type": "object",
        "properties": {
            "modified_at": {"type": "number", "exclusiveMinimum": 0},
            "restart_required": {"type": "boolean"},
            "value": {"$ref": "#/components/schemas/ArduinosConfiguration"},
        },
        "required": ["modified_at", "restart_required", "value"],
        "additionalProperties": False,
    }
    schemas["ConfigurationSnapshot"] = {
        "type": "object",
        "properties": {
            "version": {"type": "integer", "const": 1},
            "documents": {
                "type": "object",
                "properties": {
                    "trains": {
                        "$ref": "#/components/schemas/TrainsConfigurationDocument"
                    },
                    "arduinos": {
                        "$ref": "#/components/schemas/ArduinosConfigurationDocument"
                    },
                },
                "required": ["trains"],
                "additionalProperties": False,
            },
        },
        "required": ["version", "documents"],
        "additionalProperties": False,
    }
    schemas["TrainsConfigurationUpdate"] = {
        "type": "object",
        "properties": {
            "base_modified_at": {"type": "number", "exclusiveMinimum": 0},
            "modified_at": {"type": "number", "exclusiveMinimum": 0},
            "value": {"$ref": "#/components/schemas/TrainsConfiguration"},
        },
        "required": ["base_modified_at", "value"],
        "additionalProperties": False,
    }
    schemas["ArduinosConfigurationUpdate"] = {
        "type": "object",
        "properties": {
            "base_modified_at": {"type": "number", "exclusiveMinimum": 0},
            "modified_at": {"type": "number", "exclusiveMinimum": 0},
            "value": {"$ref": "#/components/schemas/ArduinosConfiguration"},
        },
        "required": ["base_modified_at", "value"],
        "additionalProperties": False,
    }
    schemas["ConfigurationUpdate"] = {
        "type": "object",
        "properties": {
            "version": {"type": "integer", "const": 1},
            "documents": {
                "oneOf": [
                    {
                        "type": "object",
                        "properties": {
                            "trains": {
                                "$ref": "#/components/schemas/TrainsConfigurationUpdate"
                            }
                        },
                        "required": ["trains"],
                        "additionalProperties": False,
                    },
                    {
                        "type": "object",
                        "properties": {
                            "arduinos": {
                                "$ref": "#/components/schemas/ArduinosConfigurationUpdate"
                            }
                        },
                        "required": ["arduinos"],
                        "additionalProperties": False,
                    },
                ]
            },
        },
        "required": ["version", "documents"],
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
            "/api/state/stream": {
                "get": {
                    "operationId": "streamSystemState",
                    "responses": {
                        "200": {
                            "description": "Authoritative state snapshots as server-sent events",
                            "content": {
                                "text/event-stream": {
                                    "schema": {"type": "string"}
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
            "/api/automation": {
                "put": {
                    "operationId": "replaceAutomation",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": "#/components/schemas/AutomationDocument"
                                }
                            }
                        },
                    },
                    "responses": {
                        "200": {
                            "description": "Automation replaced",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "$ref": "#/components/schemas/AutomationUpdateResponse"
                                    }
                                }
                            },
                        },
                        "400": _error_response("Invalid automation document"),
                        "500": _error_response("Automation persistence failed"),
                        "503": _error_response("Automation runtime unavailable"),
                    },
                }
            },
            "/api/configuration": {
                "get": {
                    "operationId": "getConfiguration",
                    "responses": {
                        "200": {
                            "description": "Editable backend configuration",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "$ref": "#/components/schemas/ConfigurationSnapshot"
                                    }
                                }
                            },
                        },
                        "500": _error_response("Configuration read failed"),
                        "503": _error_response("Configuration management unavailable"),
                    },
                },
                "put": {
                    "operationId": "replaceConfiguration",
                    "parameters": [
                        {
                            "name": "X-Train-Restart-After-Save",
                            "in": "header",
                            "required": False,
                            "description": (
                                "Restart the supervised backend after the saved "
                                "response is sent"
                            ),
                            "schema": {"type": "boolean", "default": False},
                        }
                    ],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "$ref": "#/components/schemas/ConfigurationUpdate"
                                }
                            }
                        },
                    },
                    "responses": {
                        "200": {
                            "description": "Configuration persisted",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "$ref": "#/components/schemas/ConfigurationSnapshot"
                                    }
                                }
                            },
                        },
                        "400": _error_response("Invalid configuration"),
                        "409": _error_response("Configuration update is stale"),
                        "500": _error_response("Configuration persistence failed"),
                        "503": _error_response("Configuration management unavailable"),
                    },
                },
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
