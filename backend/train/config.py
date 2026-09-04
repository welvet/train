from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TrainConfig:
    train_id: str
    ble_address: str
    tag_id: str


TRAINS = (
    TrainConfig(
        train_id="arctic_express",
        ble_address="FFE0916A-B323-1AA5-1083-0DE85F7DCB8D",
        tag_id=os.environ.get("ARCTIC_EXPRESS_TAG_ID", ""),
    ),
)
