"""Try different write modes and command variations to find what moves the motor."""

import asyncio
import struct

from bleak import BleakClient

HUB_CHAR = "00001624-1212-efde-1623-785feabcd123"
ADDRESS = "FB81D51D-F808-C900-5C30-00076EBA9465"
PORT = 0x01  # hub_info confirmed motor is on port 1


def speed_cmd(port: int, speed: int) -> bytes:
    speed = max(-100, min(100, speed))
    return bytes([0x08, 0x00, 0x81, port, 0x11, 0x07]) + struct.pack("b", speed) + bytes([0x64, 0x00])


def on_notification(sender: object, data: bytearray) -> None:
    print(f"  Hub says: {data.hex()}")
    if len(data) >= 3 and data[2] == 0x82:
        port = data[3]
        msg = data[4]
        flags = {0x01: "IN_PROGRESS", 0x02: "COMPLETED", 0x04: "DISCARDED",
                 0x08: "IDLE", 0x10: "BUSY/FULL"}
        desc = flags.get(msg, f"0x{msg:02x}")
        print(f"    -> Port Output Feedback: port={port} status={desc}")


async def main() -> None:
    async with BleakClient(ADDRESS) as client:
        print(f"Connected: {client.is_connected}")
        await client.start_notify(HUB_CHAR, on_notification)
        await asyncio.sleep(1)

        cmd = speed_cmd(PORT, 80)
        print(f"\n--- Write WITHOUT response: {cmd.hex()}")
        await client.write_gatt_char(HUB_CHAR, cmd, response=False)
        await asyncio.sleep(3)

        await client.write_gatt_char(HUB_CHAR, speed_cmd(PORT, 0), response=False)
        await asyncio.sleep(1)

        print(f"\n--- Write WITH response: {cmd.hex()}")
        await client.write_gatt_char(HUB_CHAR, cmd, response=True)
        await asyncio.sleep(3)

        await client.write_gatt_char(HUB_CHAR, speed_cmd(PORT, 0), response=True)
        await asyncio.sleep(1)

        # Try StartPower instead of StartSpeed (sub-command 0x51 on port mode)
        # Direct power command: set power directly
        power_cmd = bytes([0x06, 0x00, 0x81, PORT, 0x11, 0x51, 0x00, 0x64])
        print(f"\n--- StartPower (0x51): {power_cmd.hex()}")
        await client.write_gatt_char(HUB_CHAR, power_cmd, response=False)
        await asyncio.sleep(3)

        stop_power = bytes([0x06, 0x00, 0x81, PORT, 0x11, 0x51, 0x00, 0x00])
        await client.write_gatt_char(HUB_CHAR, stop_power, response=False)
        await asyncio.sleep(1)

        # Try Port Output sub-command 0x01: StartPower(Power)
        direct = bytes([0x07, 0x00, 0x81, PORT, 0x11, 0x01, 0x64, 0x64])
        print(f"\n--- DirectStartPower (0x01): {direct.hex()}")
        await client.write_gatt_char(HUB_CHAR, direct, response=False)
        await asyncio.sleep(3)

        stop_direct = bytes([0x07, 0x00, 0x81, PORT, 0x11, 0x01, 0x00, 0x64])
        await client.write_gatt_char(HUB_CHAR, stop_direct, response=False)
        await asyncio.sleep(1)

        await client.stop_notify(HUB_CHAR)
        print("\nDone. Did any of those make the motor spin?")


if __name__ == "__main__":
    asyncio.run(main())
