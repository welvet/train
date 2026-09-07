from __future__ import annotations

from types import SimpleNamespace

import pytest

from train.ble_scan import BLE_SCAN_TIMEOUT, scan_lego_hubs
from train.modules.lego_ble import HUB_SERVICE_UUID


async def test_scan_lego_hubs_filters_names_and_sorts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict[str, object]] = []

    async def discover(**kwargs: object) -> dict[str, tuple[object, object]]:
        calls.append(kwargs)
        return {
            "other": (
                SimpleNamespace(address="99:00", name="Other"),
                SimpleNamespace(service_uuids=["not-lego"], local_name=None),
            ),
            "second": (
                SimpleNamespace(address="BB:00", name="Device name"),
                SimpleNamespace(service_uuids=[HUB_SERVICE_UUID.upper()], local_name=None),
            ),
            "first": (
                SimpleNamespace(address="AA:00", name="Ignored name"),
                SimpleNamespace(
                    service_uuids=[HUB_SERVICE_UUID], local_name="Advertisement name"
                ),
            ),
        }

    monkeypatch.setattr("train.ble_scan.BleakScanner.discover", discover)

    assert await scan_lego_hubs() == [
        {"address": "AA:00", "name": "Advertisement name"},
        {"address": "BB:00", "name": "Device name"},
    ]
    assert calls == [{"timeout": BLE_SCAN_TIMEOUT, "return_adv": True}]
