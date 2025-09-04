#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Subscribe BLE (12 x float32, 48B) and stream to Foxglove via WebSocket (no ROS).
- One aggregated channel:  /load_cells/raw  (json: {t, data[12]})
- Twelve scalar channels:  /load_cells/ch1..ch12  (json: {t, value})

Foxglove: Connect to ws://localhost:8765, add Plot panel -> pick channels' 'value'.
"""

import asyncio
import time
import struct
from typing import List
import json  # ADDED: Import the standard json module

import numpy as np
from bleak import BleakScanner, BleakClient

import foxglove
from foxglove import Channel, Schema

# ---------- BLE settings (match your Arduino sketch) ----------
DEVICE_NAME = "GIGA-LoadCell"  # 广播名
SVC_UUID = "12345678-1234-5678-9abc-def012345678"  # Service UUID
CHR_UUID = "abcdefff-1234-5678-9abc-def012345678"  # Characteristic UUID (Notify)
N_CH = 12  # 通道数（12 路 load cell）
# --------------------------------------------------------------

# JSON Schema：汇总话题（raw）：{ t:number, data:number[12] }
RAW_SCHEMA = {
    "type": "object",
    "properties": {
        "t": {"type": "number"},
        "data": {
            "type": "array",
            "items": {"type": "number"},
            "minItems": N_CH,
            "maxItems": N_CH,
        },
    },
    "required": ["t", "data"],
}

# JSON Schema：标量话题（每路）：{ t:number, value:number }
SCALAR_SCHEMA = {
    "type": "object",
    "properties": {
        "t": {"type": "number"},
        "value": {"type": "number"},
    },
    "required": ["t", "value"],
}

class FoxgloveBridge:
    """Wrap foxglove SDK server & channels."""
    def __init__(self, host: str = "127.0.0.1", port: int = 8765):
        foxglove.set_log_level("INFO")
        # 启动 Foxglove WebSocket 服务器（默认 127.0.0.1:8765）
        self.server = foxglove.start_server(host=host, port=port)
        # 一个汇总通道（数组）
        self.raw_chan = Channel(
            topic="/load_cells/raw",
            message_encoding="json",
            # CORRECTED: Use standard json.dumps
            schema=Schema(name="loadcells_raw", encoding="jsonschema",
                          data=json.dumps(RAW_SCHEMA).encode("utf-8")),
        )
        # 12 个标量通道（每路一个）
        self.scalar_chans: List[Channel] = []
        for i in range(N_CH):
            ch = Channel(
                topic=f"/load_cells/ch{i+1}",
                message_encoding="json",
                schema=Schema(name="loadcells_scalar", encoding="jsonschema",
                              # CORRECTED: Use standard json.dumps
                              data=json.dumps(SCALAR_SCHEMA).encode("utf-8")),
            )
            self.scalar_chans.append(ch)

    def log_frame(self, values: List[float]):
        """Log one BLE frame to Foxglove."""
        now = time.time()
        # 汇总
        self.raw_chan.log({"t": now, "data": list(values)})
        # 每路标量
        for i, v in enumerate(values):
            self.scalar_chans[i].log({"t": now, "value": float(v)})

    def stop(self):
        self.server.stop()

async def connect_ble_and_stream():
    print(f"Scanning BLE for device named '{DEVICE_NAME}' ...")
    devices = await BleakScanner.discover(timeout=6.0)
    target = None
    for d in devices:
        if d.name == DEVICE_NAME:
            target = d
            break
    if target is None:
        raise RuntimeError("BLE device not found. Check advertising, name, and that no other app is connected.")

    print(f"Found {target.address} ({target.name}). Connecting...")
    bridge = FoxgloveBridge(host="127.0.0.1", port=8765)
    unpacker = struct.Struct("<" + "f"*N_CH)  # little-endian 12 x float32

    async def on_notify(_handle, data: bytearray):
        # 48B -> 12 floats
        if len(data) != unpacker.size:
            # 尝试容错：若不是 48B，可忽略或自行适配（如 int16 24B）
            return
        vals = unpacker.unpack(data)
        bridge.log_frame(vals)

    async with BleakClient(target) as client:
        if not await client.is_connected():
            raise RuntimeError("BLE connect failed.")
        print("Connected. Subscribing notifications...")
        await client.start_notify(CHR_UUID, on_notify)
        print("Subscribed. Open Foxglove and connect ws://localhost:8765")

        try:
            while True:
                await asyncio.sleep(1.0)  # 只保持事件循环
        except KeyboardInterrupt:
            print("Stopping...")
        finally:
            await client.stop_notify(CHR_UUID)
            bridge.stop()

def main():
    try:
        asyncio.run(connect_ble_and_stream())
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()