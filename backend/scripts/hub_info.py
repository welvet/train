"""Listen to hub notifications to discover attached devices and hub type."""

import asyncio

from bleak import BleakClient

HUB_CHAR = "00001624-1212-efde-1623-785feabcd123"
ADDRESS = "FB81D51D-F808-C900-5C30-00076EBA9465"

DEVICE_TYPES = {
    0x0001: "Motor",
    0x0002: "System Train Motor",
    0x0005: "Button",
    0x0008: "Light",
    0x0014: "Voltage Sensor",
    0x0015: "Current Sensor",
    0x0017: "Piezo Tone",
    0x0022: "RGB Light",
    0x0023: "External Tilt Sensor",
    0x0025: "Motion Sensor",
    0x0026: "Powered Up Medium Motor",
    0x0027: "Powered Up Large Motor",
    0x0028: "Powered Up XL Motor",
    0x002E: "Technic Medium Angular Motor",
    0x002F: "Technic Large Angular Motor",
    0x0030: "Technic Medium Angular Motor (grey)",
    0x0031: "Technic Large Angular Motor (grey)",
    0x0036: "Powered Up Hub IMU Gesture",
    0x0037: "Remote Control Button",
    0x0038: "Remote Control RSSI",
    0x0039: "Powered Up Hub IMU Accelerometer",
    0x003A: "Powered Up Hub IMU Gyro",
    0x003B: "Powered Up Hub IMU Position",
    0x003C: "Powered Up Hub IMU Temperature",
    0x003D: "Color Distance Sensor",
}

MSG_TYPES = {
    0x01: "Hub Properties",
    0x02: "Hub Actions",
    0x03: "Hub Alerts",
    0x04: "Hub Attached I/O",
    0x05: "Generic Error",
    0x08: "HW Network Commands",
    0x10: "FW Update - Go Into Boot Mode",
    0x11: "FW Update Lock Memory",
    0x12: "FW Update Lock Status Request",
    0x13: "FW Lock Status",
    0x41: "Port Input Format Setup (Single)",
    0x42: "Port Input Format Setup (Combined)",
    0x43: "Port Information Request",
    0x44: "Port Mode Information Request",
    0x45: "Port Value (Single)",
    0x46: "Port Value (Combined)",
    0x47: "Port Input Format (Single)",
    0x48: "Port Input Format (Combined)",
    0x61: "Virtual Port Setup",
    0x81: "Port Output Command",
    0x82: "Port Output Command Feedback",
}


def on_notification(sender: object, data: bytearray) -> None:
    if len(data) < 3:
        print(f"  Raw: {data.hex()}")
        return

    msg_type = data[2]
    msg_name = MSG_TYPES.get(msg_type, f"Unknown(0x{msg_type:02x})")
    print(f"  [{msg_name}] {data.hex()}")

    if msg_type == 0x04 and len(data) >= 5:
        port = data[3]
        event = data[4]
        if event == 0x01 and len(data) >= 7:
            dev_type = int.from_bytes(data[5:7], "little")
            dev_name = DEVICE_TYPES.get(dev_type, f"Unknown(0x{dev_type:04x})")
            print(f"    -> Port {port} (0x{port:02x}): ATTACHED {dev_name} (type 0x{dev_type:04x})")
        elif event == 0x00:
            print(f"    -> Port {port} (0x{port:02x}): DETACHED")
        elif event == 0x02 and len(data) >= 9:
            dev_type = int.from_bytes(data[5:7], "little")
            port_a = data[7]
            port_b = data[8]
            dev_name = DEVICE_TYPES.get(dev_type, f"Unknown(0x{dev_type:04x})")
            print(f"    -> Virtual port {port}: {dev_name} (ports {port_a}+{port_b})")


async def main() -> None:
    async with BleakClient(ADDRESS) as client:
        print(f"Connected: {client.is_connected}")
        print("Listening for hub notifications (10s)...\n")

        await client.start_notify(HUB_CHAR, on_notification)
        await asyncio.sleep(10)
        await client.stop_notify(HUB_CHAR)

    print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
