from __future__ import annotations

import asyncio
import copy
import json
import math
import os
import tempfile
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from train.config import normalized_trains_document

CONFIGURATION_API_VERSION = 1


class ConfigurationError(ValueError):
    def __init__(self, path: str, message: str) -> None:
        super().__init__(f"{path}: {message}")
        self.path = path
        self.message = message


class ConfigurationConflict(ConfigurationError):
    pass


@dataclass(frozen=True, slots=True)
class ConfigurationDocument:
    path: Path
    normalize: Callable[[dict[str, Any]], dict[str, object]]
    restart_required: bool = True


class ConfigurationStore:
    """Versioned registry for editable workspace documents."""

    def __init__(
        self,
        documents: Mapping[str, ConfigurationDocument],
    ) -> None:
        self._documents = dict(documents)
        self._lock = asyncio.Lock()

    @classmethod
    def for_trains(
        cls,
        path: Path,
        *,
        normalize: Callable[[dict[str, Any]], dict[str, object]] = (
            normalized_trains_document
        ),
    ) -> ConfigurationStore:
        return cls({
            "trains": ConfigurationDocument(
                path=path,
                normalize=normalize,
            )
        })

    def snapshot(self) -> dict[str, object]:
        return {
            "version": CONFIGURATION_API_VERSION,
            "documents": {
                name: self._snapshot_document(name, document)
                for name, document in self._documents.items()
            },
        }

    def document_value(self, name: str) -> dict[str, object]:
        definition = self._documents.get(name)
        if definition is None:
            raise ConfigurationError(f"$.documents.{name}", "is not editable")
        value = self._snapshot_document(name, definition)["value"]
        if not isinstance(value, dict):
            raise RuntimeError(
                "configuration document normalization returned a non-object"
            )
        return copy.deepcopy(value)

    async def replace_json(self, text: str) -> dict[str, object]:
        try:
            value = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ConfigurationError("$", f"invalid JSON: {exc.msg}") from exc
        if not isinstance(value, dict):
            raise ConfigurationError("$", "must be an object")
        if set(value) - {"version", "documents"}:
            raise ConfigurationError("$", "contains unsupported fields")
        if value.get("version") != CONFIGURATION_API_VERSION:
            raise ConfigurationError(
                "$.version", f"must be {CONFIGURATION_API_VERSION}"
            )
        raw_documents = value.get("documents")
        if not isinstance(raw_documents, dict) or not raw_documents:
            raise ConfigurationError("$.documents", "must be a non-empty object")
        if len(raw_documents) != 1:
            raise ConfigurationError(
                "$.documents", "must contain exactly one document"
            )

        replacements: dict[
            str,
            tuple[ConfigurationDocument, float, float | None, dict[str, object]],
        ] = {}
        for name, raw_document in raw_documents.items():
            definition = self._documents.get(name)
            path = f"$.documents.{name}"
            if definition is None:
                raise ConfigurationError(path, "is not editable")
            if not isinstance(raw_document, dict):
                raise ConfigurationError(path, "must be an object")
            if set(raw_document) - {"base_modified_at", "modified_at", "value"}:
                raise ConfigurationError(path, "contains unsupported fields")
            base_modified_at = raw_document.get("base_modified_at")
            modified_at = raw_document.get("modified_at")
            for field, timestamp in (("base_modified_at", base_modified_at),):
                if (
                    not isinstance(timestamp, (int, float))
                    or isinstance(timestamp, bool)
                    or not math.isfinite(timestamp)
                    or timestamp <= 0
                ):
                    raise ConfigurationError(
                        f"{path}.{field}", "must be a positive finite timestamp"
                    )
            if modified_at is not None and (
                not isinstance(modified_at, (int, float))
                or isinstance(modified_at, bool)
                or not math.isfinite(modified_at)
                or modified_at <= 0
            ):
                raise ConfigurationError(
                    f"{path}.modified_at", "must be a positive finite timestamp"
                )
            document_value = raw_document.get("value")
            if not isinstance(document_value, dict):
                raise ConfigurationError(f"{path}.value", "must be an object")
            try:
                normalized = definition.normalize(document_value)
            except ValueError as exc:
                raise ConfigurationError(f"{path}.value", str(exc)) from exc
            replacements[name] = (
                definition,
                float(base_modified_at),
                float(modified_at) if modified_at is not None else None,
                normalized,
            )

        async with self._lock:
            for name, (
                definition,
                base_modified_at,
                modified_at,
                normalized,
            ) in replacements.items():
                current = self._snapshot_document(name, definition)
                if current["value"] != normalized:
                    if base_modified_at != current["modified_at"]:
                        raise ConfigurationConflict(
                            f"$.documents.{name}.base_modified_at",
                            "does not match the stored document",
                        )
                    resolved_modified_at = (
                        modified_at
                        if modified_at is not None
                        else max(time.time(), current["modified_at"] + 0.001)
                    )
                    if resolved_modified_at <= current["modified_at"]:
                        raise ConfigurationConflict(
                            f"$.documents.{name}.modified_at",
                            "must be newer than the stored document",
                        )
            for definition, _, modified_at, normalized in replacements.values():
                if self._read_document(definition) != normalized:
                    current_modified_at = definition.path.stat().st_mtime_ns / 1e9
                    resolved_modified_at = (
                        modified_at
                        if modified_at is not None
                        else max(time.time(), current_modified_at + 0.001)
                    )
                    _atomic_write_json(
                        definition.path,
                        normalized,
                        resolved_modified_at,
                    )
            return self.snapshot()

    def _snapshot_document(
        self,
        name: str,
        definition: ConfigurationDocument,
    ) -> dict[str, object]:
        try:
            for _ in range(3):
                before = definition.path.stat()
                value = self._read_document(definition)
                after = definition.path.stat()
                if _file_identity(before) == _file_identity(after):
                    return {
                        "modified_at": after.st_mtime_ns / 1_000_000_000,
                        "restart_required": definition.restart_required,
                        "value": value,
                    }
        except FileNotFoundError as exc:
            raise ConfigurationError(
                f"$.documents.{name}", f"missing {definition.path}"
            ) from exc
        raise ConfigurationError(
            f"$.documents.{name}", "changed repeatedly while being read"
        )

    @staticmethod
    def _read_document(definition: ConfigurationDocument) -> dict[str, object]:
        try:
            value = json.loads(definition.path.read_text())
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            message = (
                exc.msg if isinstance(exc, json.JSONDecodeError) else "invalid UTF-8"
            )
            raise ConfigurationError("$", f"invalid JSON: {message}") from exc
        if not isinstance(value, dict):
            raise ConfigurationError("$", "must be an object")
        try:
            return definition.normalize(value)
        except ValueError as exc:
            raise ConfigurationError("$", str(exc)) from exc


def _atomic_write_json(path: Path, value: dict[str, object], modified_at: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
    )
    staged = Path(name)
    try:
        with os.fdopen(descriptor, "w") as output:
            json.dump(value, output, indent=2)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.utime(staged, ns=(int(modified_at * 1_000_000_000),) * 2)
        os.replace(staged, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        staged.unlink(missing_ok=True)


def _file_identity(value: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        value.st_dev,
        value.st_ino,
        value.st_size,
        value.st_mtime_ns,
        value.st_ctime_ns,
    )
