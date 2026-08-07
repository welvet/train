"""Debug battery response bytes."""

import asyncio

from bleak import BleakClient

HUB_CHAR = "00001624-1212-efde-1623-785feabcd123"
ADDRESS = "FB81D51D-F808-C900-5C30-00076EBA9465"


def on_notification(sender: object, data: bytearray) -> None:
    if len(data) < 3:
        return
    msg_type = data[2]
    if msg_type == 0x01:
        prop = data[3] if len(data) > 3 else None
        print(f"  Hub Property: prop=0x{prop:02x} full={data.hex()} bytes={list(data)}")


async def main() -> None:
    async with BleakClient(ADDRESS) as client:
        print(f"Connected: {client.is_connected}")
        await client.start_notify(HUB_CHAR, on_notification)
        await asyncio.sleep(1)

        print("\nRequest battery (operation 0x05)...")
        await client.write_gatt_char(HUB_CHAR, bytes([0x05, 0x00, 0x01, 0x06, 0x05]))
        await asyncio.sleep(2)

        print("\nEnable battery updates (operation 0x02)...")
        await client.write_gatt_char(HUB_CHAR, bytes([0x05, 0x00, 0x01, 0x06, 0x02]))
        await asyncio.sleep(5)

        await client.stop_notify(HUB_CHAR)
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
