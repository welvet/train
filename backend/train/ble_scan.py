from __future__ import annotations

from bleak import BleakScanner

BLE_SCAN_TIMEOUT = 10.0
HUB_SERVICE_UUID = "00001623-1212-efde-1623-785feabcd123"


class BleScanUnavailable(RuntimeError):
    """Raised when runtime adapter policy prevents a scan."""


async def scan_lego_hubs() -> list[dict[str, object]]:
    """Discover nearby LEGO Powered Up hubs in a stable display order."""
    results = await BleakScanner.discover(
        timeout=BLE_SCAN_TIMEOUT,
        return_adv=True,
    )
    hubs = [
        {
            "address": device.address,
            "name": advertisement.local_name or device.name,
        }
        for device, advertisement in results.values()
        if HUB_SERVICE_UUID.lower()
        in {uuid.lower() for uuid in advertisement.service_uuids}
    ]
    return sorted(hubs, key=lambda hub: hub["address"])
