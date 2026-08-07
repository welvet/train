"""Test reading battery level and voltage from the hub."""

import asyncio

from bleak import BleakClient

HUB_CHAR = "00001624-1212-efde-1623-785feabcd123"
ADDRESS = "FB81D51D-F808-C900-5C30-00076EBA9465"

VOLTAGE_PORT = 0x3C


def on_notification(sender: object, data: bytearray) -> None:
    if len(data) < 3:
        return
    msg_type = data[2]

    # Hub Property response (battery)
    if msg_type == 0x01 and len(data) >= 5 and data[3] == 0x06:
        battery = data[5]
        print(f"  Battery: {battery}%")

    # Port Value (voltage sensor)
    elif msg_type == 0x45 and len(data) >= 6 and data[3] == VOLTAGE_PORT:
        raw = int.from_bytes(data[4:6], "little")
        voltage = raw / 400.0 * 9.6  # typical LWP3 scaling for voltage
        print(f"  Voltage: {voltage:.2f}V (raw={raw})")


async def main() -> None:
    async with BleakClient(ADDRESS) as client:
        print(f"Connected: {client.is_connected}")
        await client.start_notify(HUB_CHAR, on_notification)
        await asyncio.sleep(1)

        # Request battery level (Hub Property 0x06, operation 0x05 = Request Update)
        print("\nRequesting battery level...")
        await client.write_gatt_char(HUB_CHAR, bytes([0x05, 0x00, 0x01, 0x06, 0x05]))
        await asyncio.sleep(1)

        # Enable battery updates (operation 0x02 = Enable Updates)
        print("Enabling battery updates...")
        await client.write_gatt_char(HUB_CHAR, bytes([0x05, 0x00, 0x01, 0x06, 0x02]))
        await asyncio.sleep(1)

        # Subscribe to voltage sensor on port 0x3C
        # Port Input Format Setup: [len, hub, 0x41, port, mode, delta(4 bytes), notify]
        print("Subscribing to voltage sensor...")
        await client.write_gatt_char(
            HUB_CHAR,
            bytes([0x0A, 0x00, 0x41, VOLTAGE_PORT, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01]),
        )

        print("Listening for 10s...")
        await asyncio.sleep(10)

        await client.stop_notify(HUB_CHAR)
    print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
