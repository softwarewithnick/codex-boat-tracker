"""Real local WebSocket tests; no AISstream key or external service required."""
import asyncio
import json
import unittest
from websockets.asyncio.server import serve
from tracker.feeds import AISStreamFeed
from tracker.model import Bounds, VesselStore

BOUNDS = Bounds(-80.16, 26.0, -79.7, 26.25)


async def eventually(predicate, timeout=5):
    deadline = asyncio.get_running_loop().time() + timeout
    while not predicate():
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError("Timed out waiting for feed state")
        await asyncio.sleep(.03)


class FeedTests(unittest.IsolatedAsyncioTestCase):
    async def test_binary_reports_subscription_and_reconnect(self):
        subscriptions = []

        async def handler(socket):
            subscriptions.append(json.loads(await socket.recv()))
            await socket.send(json.dumps({"MessageType": "SubscriptionConfirmation",
                                          "Message": {"CompressionEnabled": True}}).encode())
            await socket.send(b"malformed json")
            await socket.send(json.dumps({
                "MessageType": "StandardClassBPositionReport",
                "MetaData": {"MMSI": 123456789, "ShipName": "LOCAL TEST"},
                "Message": {"StandardClassBPositionReport": {
                    "Latitude": 26.12, "Longitude": -80.01, "Sog": 3.4, "Cog": 80}}
            }).encode())
            if len(subscriptions) == 1:
                await socket.close()
            else:
                await socket.wait_closed()

        async with serve(handler, "127.0.0.1", 0, compression="deflate") as server:
            port = server.sockets[0].getsockname()[1]
            feed = AISStreamFeed(BOUNDS, "local-test-key", endpoint=f"ws://127.0.0.1:{port}")
            feed.start()
            try:
                await eventually(lambda: len(subscriptions) >= 2 and feed.status == "CONNECTED")
                store = VesselStore(BOUNDS)
                feed.drain(store)
                self.assertEqual(store.positioned()[0].name, "LOCAL TEST")
                self.assertEqual(subscriptions[0], BOUNDS.subscription("local-test-key"))
                self.assertIsNotNone(feed.last_received)
            finally:
                await asyncio.to_thread(feed.close)
            self.assertFalse(feed.thread.is_alive())

    async def test_rejection_stops_without_exposing_server_message(self):
        async def handler(socket):
            await socket.recv()
            await socket.send(json.dumps({"error": "invalid key: private-test-key"}))
            await socket.wait_closed()

        async with serve(handler, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            feed = AISStreamFeed(BOUNDS, "private-test-key", endpoint=f"ws://127.0.0.1:{port}")
            feed.start()
            try:
                await eventually(lambda: feed.status == "REJECTED")
                self.assertNotIn("private-test-key", feed.detail)
            finally:
                await asyncio.to_thread(feed.close)
            self.assertFalse(feed.thread.is_alive())


if __name__ == "__main__":
    unittest.main()

