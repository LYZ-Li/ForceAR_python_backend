# ble_receive_plot_save.py
import asyncio
import struct
import csv
import time
from bleak import BleakScanner, BleakClient
import numpy as np
import matplotlib.pyplot as plt

DEVICE_NAME = "GIGA-LoadCell"
SVC_UUID = "12345678-1234-5678-9abc-def012345678"
CHR_UUID = "abcdefff-1234-5678-9abc-def012345678"
N_CH = 12
OUT_CSV = "loadcells_ble.csv"

class BLECollector:
    def __init__(self):
        self.rows = []
        self.t0 = time.time()

    def callback(self, _sender, data: bytearray):
        # data = 48B -> 12 x float32, little-endian
        vals = struct.unpack("<" + "f"*N_CH, data)
        t = time.time() - self.t0
        self.rows.append((t,) + vals)

async def main():
    print("Scanning for device:", DEVICE_NAME)
    devices = await BleakScanner.discover(timeout=5.0)
    target = None
    for d in devices:
        if d.name == DEVICE_NAME:
            target = d
            break
    if target is None:
        raise RuntimeError("Device not found. Make sure it's advertising and close other BLE apps.")

    print("Found:", target)

    collector = BLECollector()

    async with BleakClient(target) as client:
        ok = await client.is_connected()
        print("Connected:", ok)

        # 可选：检查服务和特征是否存在
        svcs = await client.get_services()
        if SVC_UUID not in [s.uuid for s in svcs]:
            print("WARNING: Service UUID not found; continue anyway.")

        await client.start_notify(CHR_UUID, collector.callback)
        print("Subscribed. Receiving... (Ctrl+C to stop)")

        # 实时绘图（只画前三路示例）
        plt.ion()
        fig = plt.figure()
        ax = fig.add_subplot(111)
        lines = [ax.plot([], [])[0] for _ in range(3)]
        ax.set_xlabel("Time (s)")
        ax.set_ylabel("Value")

        try:
            while True:
                await asyncio.sleep(0.05)  # ~20Hz 刷新
                if len(collector.rows) == 0:
                    continue
                data = np.array(collector.rows)
                t = data[:, 0]
                for i in range(3):
                    lines[i].set_data(t, data[:, 1 + i])
                ax.relim(); ax.autoscale_view()
                plt.pause(0.001)
        except KeyboardInterrupt:
            print("\nStopping...")
        finally:
            await client.stop_notify(CHR_UUID)

    # 保存 CSV
    header = ["t"] + [f"ch{i+1}" for i in range(N_CH)]
    with open(OUT_CSV, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(collector.rows)
    print("Saved:", OUT_CSV)

if __name__ == "__main__":
    asyncio.run(main())
