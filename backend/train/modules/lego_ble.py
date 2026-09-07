from __future__ import annotations

import asyncio
import json
import logging
import os
import struct
from contextlib import suppress
from typing import Any

from bleak import BleakClient

from train.ble_scan import BleScanUnavailable, HUB_SERVICE_UUID, scan_lego_hubs
from train.core.event_bus import EventBus
from train.core.module import Module
from train.domain import (
    SetTrainSpeed,
    TrainConnected,
    TrainDisconnected,
    TrainSpeedChanged,
    TrainStatus,
)

HUB_CHARACTERISTIC_UUID = "00001624-1212-efde-1623-785feabcd123"

MOTOR_PORT = 0x01
VOLTAGE_PORT = 0x3C
RECONNECT_DELAY = 5.0
POLL_INTERVAL = 1.0
STATUS_INTERVAL = 5.0

BATTERY_REQUEST = bytes([0x05, 0x00, 0x01, 0x06, 0x05])
BATTERY_ENABLE_UPDATES = bytes([0x05, 0x00, 0x01, 0x06, 0x02])
VOLTAGE_MAX_RAW = 3893.0
VOLTAGE_MAX_V = 9.6


def _build_speed_command(port: int, speed: int) -> bytes:
    speed = max(-100, min(100, speed))
    speed_byte = struct.pack("b", speed)
    return bytes([0x06, 0x00, 0x81, port, 0x11, 0x51, 0x00]) + speed_byte


def _build_voltage_subscribe(port: int) -> bytes:
    return bytes([0x0A, 0x00, 0x41, port, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01])


class LegoBleModule(Module):
    def __init__(self, bus: EventBus, *, train_map: dict[str, str] | None = None) -> None:
        super().__init__(bus)
        if train_map is not None:
            self._train_map = train_map
        else:
            raw = os.environ.get("TRAIN_BLE_MAP", "{}")
            self._train_map = json.loads(raw)
        self._clients: dict[str, BleakClient] = {}
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._adapter_condition = asyncio.Condition()
        self._connection_attempts = 0
        self._scan_task: asyncio.Task[list[dict[str, object]]] | None = None
        self._battery: dict[str, int] = {}
        self._voltage: dict[str, float] = {}
        self._log = logging.getLogger("train.ble")

    async def start(self) -> None:
        self.bus.subscribe(SetTrainSpeed, self._on_set_speed)
        for ble_address, train_name in self._train_map.items():
            task = asyncio.create_task(
                self._maintain_connection(train_name, ble_address),
                name=f"ble:{train_name}",
            )
            self._tasks[train_name] = task
        self._log.info("Managing %d train(s): %s", len(self._train_map), list(self._train_map.values()))

    async def stop(self) -> None:
        await self.cancel_scan()
        for task in self._tasks.values():
            task.cancel()
        await asyncio.gather(*self._tasks.values(), return_exceptions=True)
        self._tasks.clear()
        for name, client in self._clients.items():
            with suppress(Exception):
                await client.disconnect()
        self._clients.clear()

    async def cancel_scan(self) -> None:
        task = self._scan_task
        if task is None:
            return
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        if self._scan_task is task:
            self._scan_task = None

    async def scan(self) -> list[dict[str, object]]:
        """Run one shared scan without overlapping a connection attempt."""
        task = self._scan_task
        if task is None or task.done():
            task = asyncio.create_task(self._scan_exclusively(), name="ble:scan")
            self._scan_task = task
            task.add_done_callback(self._scan_finished)
        await asyncio.wait((task,))
        return task.result()

    def _scan_finished(self, task: asyncio.Task[list[dict[str, object]]]) -> None:
        if self._scan_task is task:
            self._scan_task = None
            asyncio.create_task(self._notify_adapter_available())
        if not task.cancelled():
            # A disconnected HTTP caller may leave the shared scan without a waiter.
            task.exception()

    async def _scan_exclusively(self) -> list[dict[str, object]]:
        async with self._adapter_condition:
            if self._clients or self._connection_attempts:
                raise BleScanUnavailable(
                    "Disconnect or power down connected train hubs and wait for "
                    "connection attempts to finish before scanning"
                )
        return await scan_lego_hubs()

    async def _notify_adapter_available(self) -> None:
        async with self._adapter_condition:
            self._adapter_condition.notify_all()

    async def _connect(self, train_name: str, client: BleakClient) -> None:
        async with self._adapter_condition:
            await self._adapter_condition.wait_for(lambda: self._scan_task is None)
            self._connection_attempts += 1
        connected = False
        try:
            await client.connect()
            connected = True
        finally:
            async with self._adapter_condition:
                if connected:
                    self._clients[train_name] = client
                self._connection_attempts -= 1
                self._adapter_condition.notify_all()

    async def _maintain_connection(self, train_name: str, ble_address: str) -> None:
        while True:
            was_connected = False
            client = BleakClient(ble_address)
            try:
                await self._connect(train_name, client)
                was_connected = True
                await self.bus.publish(TrainConnected(train_name=train_name, ble_address=ble_address))
                self._log.info("Connected to %s (%s)", train_name, ble_address)

                await self._setup_notifications(train_name, client)
                await self._poll_while_connected(train_name, client)

            except asyncio.CancelledError:
                if was_connected:
                    self._clients.pop(train_name, None)
                    with suppress(Exception):
                        await client.disconnect()
                raise

            except Exception as exc:
                self._log.warning("Connection to %s (%s) failed: %s", train_name, ble_address, exc)

            if was_connected:
                self._clients.pop(train_name, None)
                self._battery.pop(train_name, None)
                self._voltage.pop(train_name, None)
                await self.bus.publish(TrainDisconnected(train_name=train_name, ble_address=ble_address))
                self._log.info("Disconnected from %s", train_name)

            await asyncio.sleep(RECONNECT_DELAY)

    async def _setup_notifications(self, train_name: str, client: BleakClient) -> None:
        def on_notification(sender: object, data: bytearray) -> None:
            if len(data) < 3:
                return
            msg_type = data[2]
            if msg_type == 0x01 and len(data) >= 6 and data[3] == 0x06:
                self._battery[train_name] = data[5]
            elif msg_type == 0x45 and len(data) >= 6 and data[3] == VOLTAGE_PORT:
                raw = int.from_bytes(data[4:6], "little")
                self._voltage[train_name] = round(raw * VOLTAGE_MAX_V / VOLTAGE_MAX_RAW, 2)

        await client.start_notify(HUB_CHARACTERISTIC_UUID, on_notification)
        await client.write_gatt_char(HUB_CHARACTERISTIC_UUID, _build_voltage_subscribe(VOLTAGE_PORT))
        await client.write_gatt_char(HUB_CHARACTERISTIC_UUID, BATTERY_REQUEST)
        await client.write_gatt_char(HUB_CHARACTERISTIC_UUID, BATTERY_ENABLE_UPDATES)

    async def _poll_while_connected(self, train_name: str, client: BleakClient) -> None:
        elapsed = 0.0
        while client.is_connected:
            await asyncio.sleep(POLL_INTERVAL)
            elapsed += POLL_INTERVAL
            if elapsed >= STATUS_INTERVAL:
                elapsed = 0.0
                await self._publish_status(train_name)

    async def _publish_status(self, train_name: str) -> None:
        await self.bus.publish(TrainStatus(
            train_name=train_name,
            battery_pct=self._battery.get(train_name, 0),
            voltage=self._voltage.get(train_name, 0.0),
        ))

    async def _on_set_speed(self, event: SetTrainSpeed) -> None:
        client = self._clients.get(event.train_name)
        if client is None or not client.is_connected:
            await self.bus.publish(
                TrainSpeedChanged(
                    train_name=event.train_name,
                    speed=event.speed,
                    success=False,
                    request_id=event.request_id,
                )
            )
            return
        try:
            command = _build_speed_command(MOTOR_PORT, event.speed)
            await client.write_gatt_char(HUB_CHARACTERISTIC_UUID, command)
            await self.bus.publish(
                TrainSpeedChanged(
                    train_name=event.train_name,
                    speed=event.speed,
                    success=True,
                    request_id=event.request_id,
                )
            )
        except Exception:
            self._log.error("Failed to set speed for %s", event.train_name, exc_info=True)
            await self.bus.publish(
                TrainSpeedChanged(
                    train_name=event.train_name,
                    speed=event.speed,
                    success=False,
                    request_id=event.request_id,
                )
            )
