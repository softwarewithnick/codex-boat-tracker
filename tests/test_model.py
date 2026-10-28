import unittest
from tracker.model import Bounds, VesselStore, POSITION_TYPES


BOUNDS = Bounds(-80.16, 26.0, -79.7, 26.25)


def report(kind="PositionReport", mmsi=123456789, **fields):
    body = {"Latitude": 26.12, "Longitude": -80.01, "Sog": 12.4,
            "Cog": 80.0, "TrueHeading": 81, "Valid": True}
    body.update(fields)
    return {"MessageType": kind, "MetaData": {"MMSI": mmsi, "ShipName": " TEST BOAT@@ "},
            "Message": {kind: body}}


class ModelTests(unittest.TestCase):
    def test_exact_subscription_uses_lat_lon(self):
        subscription = BOUNDS.subscription("test-only")
        self.assertEqual(subscription["BoundingBoxes"],
                         [[[26.0, -80.16], [26.25, -79.7]]])
        self.assertIn("StandardClassBPositionReport", subscription["FilterMessageTypes"])

    def test_class_a_and_b_positions(self):
        for kind in POSITION_TYPES:
            with self.subTest(kind=kind):
                store = VesselStore(BOUNDS)
                self.assertTrue(store.ingest(report(kind), now=0))
                self.assertEqual(store.positioned()[0].name, "TEST BOAT")
                self.assertEqual(store.positioned()[0].speed, 12.4)

    def test_metadata_coordinates_and_ais_sentinels(self):
        msg = report(Sog=102.3, Cog=360, TrueHeading=511)
        del msg["Message"]["PositionReport"]["Latitude"]
        del msg["Message"]["PositionReport"]["Longitude"]
        msg["MetaData"].update(latitude=26.12, longitude=-80.01)
        store = VesselStore(BOUNDS)
        self.assertTrue(store.ingest(msg, now=1))
        vessel = store.positioned()[0]
        self.assertEqual((vessel.speed, vessel.course, vessel.heading), (None, None, None))

    def test_bad_positions_do_not_become_targets(self):
        store = VesselStore(BOUNDS)
        for fields in ({"Latitude": 91}, {"Longitude": 181}, {"Latitude": float("nan")},
                       {"Longitude": "bad"}, {"Valid": False}, {"Latitude": 20}):
            self.assertFalse(store.ingest(report(**fields), now=1))
        self.assertFalse(store.positioned())
        for msg in (None, [], {}, {"MessageType": "PositionReport", "Message": None}):
            self.assertFalse(store.ingest(msg))

    def test_static_reports_do_not_refresh_position_age(self):
        store = VesselStore(BOUNDS, expire_seconds=10)
        store.ingest(report(), now=0)
        store.ingest({"MessageType": "ShipStaticData", "MetaData": {"MMSI": 123456789},
                      "Message": {"ShipStaticData": {"Name": "NEW NAME", "Type": 70,
                                                      "Destination": "PORT"}}}, now=9)
        self.assertEqual(store.positioned()[0].category, "Cargo")
        self.assertEqual(store.positioned()[0].last_position, 0)
        store.expire(now=11)
        self.assertFalse(store.vessels)

    def test_static_before_position_merges(self):
        store = VesselStore(BOUNDS)
        store.ingest({"MessageType": "StaticDataReport", "MetaData": {"MMSI": 123456789},
                      "Message": {"StaticDataReport": {"ReportA": {"Name": "SAILOR"},
                                                       "ReportB": {"ShipType": 36}}}}, now=1)
        self.assertFalse(store.positioned())
        msg = report()
        msg["MetaData"]["ShipName"] = ""
        store.ingest(msg, now=2)
        self.assertEqual(store.positioned()[0].name, "SAILOR")
        self.assertEqual(store.positioned()[0].category, "Sailing")

    def test_memory_caps_and_leaving_area(self):
        store = VesselStore(BOUNDS, max_vessels=2, trail_points=3)
        for index in range(10):
            store.ingest(report(Latitude=26.1 + index * .001), now=index)
        self.assertEqual(len(store.positioned()[0].trail), 3)
        store.ingest(report(mmsi=223456789), now=11)
        store.ingest(report(mmsi=323456789), now=12)
        self.assertEqual(len(store.vessels), 2)
        self.assertNotIn("123456789", store.vessels)
        store.ingest(report(mmsi=323456789, Latitude=20), now=13)
        self.assertNotIn("323456789", store.vessels)


if __name__ == "__main__":
    unittest.main()

