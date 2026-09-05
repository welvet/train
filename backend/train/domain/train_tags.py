from __future__ import annotations

from collections.abc import Mapping


class TrainTagRegistry:
    """Resolves hardware tag identifiers to application train identifiers."""

    def __init__(self, train_tag_map: Mapping[str, str] | None = None) -> None:
        self._train_by_tag = {
            self.normalize(tag_id): train_id
            for tag_id, train_id in (train_tag_map or {}).items()
            if tag_id and train_id.strip()
        }

    @staticmethod
    def normalize(tag_id: object) -> str:
        return str(tag_id).strip().upper()

    def resolve(self, tag_id: object) -> str | None:
        return self._train_by_tag.get(self.normalize(tag_id))
