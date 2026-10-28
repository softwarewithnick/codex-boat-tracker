"""Network I/O lives off the render thread. Demo never mixes with live data."""
import asyncio
import json
import math
import queue
import random
import threading
import time
from datetime import datetime, timedelta, timezone

from .model import POSITION_TYPES


class AISStreamFeed:
    def __init__(self, bounds, key, *, endpoint="wss://stream.aisstream.io/v0/stream"):
        self.bounds, self.key, self.endpoint = bounds, key, endpoint
        self.messages = queue.Queue(maxsize=800)
        self.status = "CONNECTING"
        self.detail = "Opening AISstream connection"
        self.dropped = 0
        self.last_received = None
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True, name="aisstream")

    def start(self):
        self.thread.start()

    def close(self):
        self.stop_event.set()
        if self.thread.is_alive():
            self.thread.join(timeout=3)

    def _run(self):
        asyncio.run(self._connect())

    async def _pause(self, seconds):
        deadline = time.monotonic() + seconds
        while not self.stop_event.is_set() and time.monotonic() < deadline:
            await asyncio.sleep(0.1)

    async def _connect(self):
        from websockets.asyncio.client import connect
        from websockets.exceptions import ConnectionClosed
        delay = 1
        while not self.stop_event.is_set():
            try:
                self.status, self.detail = "CONNECTING", "Opening AISstream connection"
                async with connect(self.endpoint, compression="deflate", open_timeout=8,
                                   ping_interval=20, ping_timeout=20, close_timeout=1,
                                   max_size=262144, max_queue=16) as socket:
                    await socket.send(json.dumps(self.bounds.subscription(self.key)))
                    self.status, self.detail = "SUBSCRIBING", "Waiting for subscription confirmation"
                    subscribed_at = time.monotonic()
                    while not self.stop_event.is_set():
                        try:
                            raw = await asyncio.wait_for(socket.recv(), timeout=1)
                        except asyncio.TimeoutError:
                            if self.status == "SUBSCRIBING" and time.monotonic() - subscribed_at > 15:
                                raise TimeoutError("Subscription confirmation timed out")
                            continue
                        try:
                            message = json.loads(raw)
                        except (ValueError, UnicodeDecodeError, TypeError):
                            continue
                        if not isinstance(message, dict):
                            continue
                        # Never echo server payloads, which might include credentials.
                        if "error" in message or "Error" in message or message.get("MessageType") == "Error":
                            self.status = "REJECTED"
                            self.detail = "Check API key, subscription and account connection limits"
                            return
                        if message.get("MessageType") == "SubscriptionConfirmation":
                            payload = message.get("Message", {})
                            compressed = isinstance(payload, dict) and payload.get("CompressionEnabled")
                            self.status = "CONNECTED"
                            self.detail = "Waiting for vessel reports" if compressed else "Connected; compression unconfirmed"
                            delay = 1
                            continue
                        if message.get("MessageType") in POSITION_TYPES:
                            self.last_received = time.monotonic()
                            self.status, self.detail = "CONNECTED", "Receiving AIS position reports"
                            delay = 1
                        try:
                            self.messages.put_nowait(message)
                        except queue.Full:
                            try:
                                self.messages.get_nowait()
                            except queue.Empty:
                                pass
                            self.dropped += 1
                            self.messages.put_nowait(message)
            except (OSError, TimeoutError, ConnectionClosed):
                self.status, self.detail = "RECONNECTING", f"Connection interrupted; retry in {delay}s"
            except Exception as error:
                self.status = "RECONNECTING"
                self.detail = f"Stream unavailable ({type(error).__name__}); retry in {delay}s"
            if not self.stop_event.is_set():
                await self._pause(delay + random.uniform(0, 0.5))
                delay = min(delay * 2, 60)

    def drain(self, store, limit=200):
        for _ in range(limit):
            try:
                store.ingest(self.messages.get_nowait())
            except queue.Empty:
                break


class DemoFeed:
    status = "DEMO"
    detail = "Simulated traffic / no live AIS connection"
    dropped = 0

    def __init__(self, bounds):
        self.bounds = bounds
        self.started = time.monotonic()
        self.last_tick = 0
        self.last_received = None
        self.ships = [
            ("DEMO ATLANTIC", 70, .28, .70, 152, 12.4),
            ("DEMO SEA BREEZE", 37, .66, .74, 218, 5.8),
            ("DEMO COASTAL", 60, .47, .47, 32, 16.2),
            ("DEMO MARINER", 36, .74, .29, 310, 4.1),
            ("DEMO HARBOR TUG", 52, .20, .26, 72, 3.2),
            ("DEMO CORAL", 80, .82, .56, 185, 10.7),
        ]
        self.last_static_tick = float("-inf")

    def start(self):
        pass

    def close(self):
        pass

    def drain(self, store, limit=200):
        now = time.monotonic()
        if now - self.last_tick < 1:
            return
        self.last_tick = self.last_received = now
        elapsed = now - self.started
        send_static = now - self.last_static_tick >= 360
        if send_static:
            self.last_static_tick = now
        eta = datetime.now(timezone.utc) + timedelta(hours=8)
        profiles = [
            (230, 32, 9.4, "PORT EVERGLADES", "Bahamas", "DEMO1"),
            (18, 5, 1.5, "", "United States", "DEMO2"),
            (294, 38, 8.2, "NASSAU", "Malta", "DEMO3"),
            (14, 4, 2.1, "", "United Kingdom", "DEMO4"),
            (32, 11, 4.5, "PORT EVERGLADES", "United States", "DEMO5"),
            (24, 6, 1.9, "", "Cayman Islands", "DEMO6"),
        ]
        for index, (name, ship_type, x, y, course, speed) in enumerate(self.ships):
            angle = math.radians(course)
            lat_span = self.bounds.north - self.bounds.south
            lon_span = self.bounds.east - self.bounds.west
            x += math.sin(angle) * speed * elapsed / 3600 / (60 * math.cos(math.radians(self.bounds.center[0]))) / lon_span
            y += math.cos(angle) * speed * elapsed / 3600 / 60 / lat_span
            lat = self.bounds.south + ((y - .08) % .84 + .08) * lat_span
            lon = self.bounds.west + ((x - .08) % .84 + .08) * lon_span
            mmsi = 900000001 + index
            length, beam, draught, destination, country, callsign = profiles[index]
            class_a = ship_type in (70, 60, 52)
            if send_static:
                static = {"Name": name, "Type": ship_type, "CallSign": callsign,
                          "Dimension": {"A": length - 5, "B": 5, "C": beam // 2, "D": beam - beam // 2}}
                if class_a:
                    prefix = str(900000 + index)
                    checksum = sum(int(d) * w for d, w in zip(prefix, range(7, 1, -1))) % 10
                    static.update(ImoNumber=int(prefix + str(checksum)), Destination=destination,
                                  MaximumStaticDraught=draught,
                                  Eta={"Month": eta.month, "Day": eta.day, "Hour": eta.hour, "Minute": eta.minute})
                    static_kind, payload = "ShipStaticData", static
                else:
                    static["ShipType"] = static.pop("Type")
                    static_kind, payload = "StaticDataReport", {"ReportA": {"Name": name}, "ReportB": static}
                store.ingest({"MessageType": static_kind, "MetaData": {"MMSI": mmsi},
                              "Message": {static_kind: payload}}, now)
            kind = "PositionReport" if class_a else "StandardClassBPositionReport"
            store.ingest({"MessageType": kind,
                          "MetaData": {"MMSI": mmsi, "ShipName": name},
                          "Message": {kind: {
                              "Latitude": lat, "Longitude": lon, "Sog": speed,
                              "Cog": course, "TrueHeading": (int(course) + 3) % 360,
                              "NavigationalStatus": 0}}}, now)
            store.vessels[str(mmsi)].demo_country = country

