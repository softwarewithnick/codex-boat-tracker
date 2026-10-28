import unittest

from tracker.details import dimensions, eta_text, flag_country, imo_number
from tracker.model import Bounds, VesselStore

BOUNDS = Bounds(-81, 25, -79, 27)


def message(kind, body, mmsi=368123456):
    return {"MessageType": kind, "MetaData": {"MMSI": mmsi}, "Message": {kind: body}}


class VesselDetailsTests(unittest.TestCase):
    def setUp(self):
        self.store = VesselStore(BOUNDS)

    def test_static_voyage_merges_with_dynamic_without_refreshing_position(self):
        self.store.ingest(message("PositionReport", {
            "Latitude": 26, "Longitude": -80, "Cog": 90, "TrueHeading": 87,
            "NavigationalStatus": 5}), now=1)
        self.store.ingest(message("ShipStaticData", {
            "Name": "TEST SHIP@@", "Type": 80, "CallSign": " ABC123@ ", "ImoNumber": 9074729,
            "Dimension": {"A": 190, "B": 10, "C": 15, "D": 17},
            "MaximumStaticDraught": 8.4, "Destination": "PORT EVERGLADES",
            "Eta": {"Month": 12, "Day": 31, "Hour": 23, "Minute": 50}}), now=10)
        vessel = self.store.positioned()[0]
        self.assertEqual((vessel.length_m, vessel.beam_m, vessel.draught_m), (200, 32, 8.4))
        self.assertEqual((vessel.category, vessel.call_sign, vessel.imo), ("Tanker", "ABC123", "9074729"))
        self.assertEqual((vessel.heading, vessel.course, vessel.navigation_status), (87, 90, 5))
        self.assertEqual(vessel.eta, "31 Dec 23:50 UTC")
        self.assertEqual(vessel.destination, "PORT EVERGLADES")
        self.assertEqual((vessel.last_position, vessel.last_static, vessel.last_voyage), (1, 10, 10))
        self.assertEqual(vessel.flag, "United States of America")

    def test_unknown_values_clear_previous_reports_but_omitted_fields_do_not(self):
        self.store.ingest(message("ShipStaticData", {
            "CallSign": "ABC", "Destination": "PORT", "ImoNumber": 9074729,
            "Dimension": {"A": 10, "B": 2, "C": 1, "D": 1}, "MaximumStaticDraught": 2,
            "Eta": {"Month": 1, "Day": 2, "Hour": 3, "Minute": 4}}), now=1)
        self.store.ingest(message("ShipStaticData", {"Name": "RENAMED"}), now=2)
        vessel = self.store.vessels["368123456"]
        self.assertEqual(vessel.length_m, 12)
        self.assertEqual(vessel.destination, "PORT")
        self.assertEqual(vessel.last_voyage, 1)
        self.store.ingest(message("ShipStaticData", {
            "Dimension": {"A": 0, "B": 0, "C": 0, "D": 0}, "MaximumStaticDraught": 0,
            "Eta": {"Month": 0, "Day": 0, "Hour": 24, "Minute": 60},
            "ImoNumber": 0, "Destination": "@@@@", "CallSign": ""}), now=3)
        self.assertEqual((vessel.length_m, vessel.beam_m, vessel.draught_m, vessel.eta, vessel.imo), (None,) * 5)
        self.assertEqual((vessel.call_sign, vessel.destination), ("", ""))

    def test_class_b_parts_do_not_overwrite_each_other(self):
        self.store.ingest(message("StaticDataReport", {
            "PartNumber": True, "ReportA": {"Valid": False, "Name": "BAD"},
            "ReportB": {"Valid": True, "ShipType": 36, "CallSign": "SAIL1",
                        "Dimension": {"A": 12, "B": 2, "C": 2, "D": 2}}}), now=1)
        self.store.ingest(message("StaticDataReport", {
            "PartNumber": False, "ReportA": {"Valid": True, "Name": "SAILOR"},
            "ReportB": {"ShipType": 0, "CallSign": "", "Dimension": {"A": 0, "B": 0, "C": 0, "D": 0}}}), now=2)
        vessel = self.store.vessels["368123456"]
        self.assertEqual((vessel.name, vessel.category, vessel.length_m, vessel.call_sign), ("SAILOR", "Sailing", 14, "SAIL1"))
        self.assertIsNone(vessel.eta)
        self.assertIsNone(vessel.last_voyage)

    def test_auxiliary_craft_dimension_bits_are_not_ship_dimensions(self):
        self.store.ingest(message("StaticDataReport", {
            "PartNumber": True, "ReportB": {"ShipType": 37, "Dimension": {"A": 333, "B": 444, "C": 50, "D": 30}}},
            mmsi=983681234), now=1)
        vessel = self.store.vessels["983681234"]
        self.assertIsNone(vessel.length_m)
        self.assertIsNone(vessel.beam_m)
        self.assertEqual(vessel.flag, "Unknown")

    def test_extended_class_b_dimensions_and_class_a_status_unknown(self):
        self.store.ingest(message("ExtendedClassBPositionReport", {
            "Latitude": 26, "Longitude": -80, "Name": "YACHT", "Type": 37,
            "Dimension": {"A": 20, "B": 4, "C": 3, "D": 3}, "TrueHeading": 511}), now=0)
        vessel = self.store.positioned()[0]
        self.assertEqual((vessel.length_m, vessel.beam_m, vessel.ais_class), (24, 6, "B"))
        self.assertIsNone(vessel.navigation_status)
        self.assertIsNone(vessel.heading)
        self.store.ingest(message("PositionReport", {
            "Latitude": 26, "Longitude": -80, "NavigationalStatus": 15}), now=1)
        self.assertIsNone(vessel.navigation_status)

    def test_dimensions_zero_offsets_limits_and_invalid_types(self):
        self.assertEqual(dimensions({"A": 0, "B": 100, "C": 0, "D": 20}), (100, 20, False, False))
        self.assertEqual(dimensions({"A": 511, "B": 10, "C": 63, "D": 1}), (521, 64, True, True))
        for value in (None, [], {}, {"A": True, "B": 1}, {"A": 512, "B": 10}, {"A": 3.5, "B": 1}):
            self.assertIsNone(dimensions(value)[0])

    def test_eta_validates_calendar_without_inventing_year(self):
        self.assertEqual(eta_text({"Month": 2, "Day": 29, "Hour": 0, "Minute": 0}), "29 Feb 00:00 UTC")
        for value in (None, [], {}, {"Month": 2, "Day": 30, "Hour": 1, "Minute": 1},
                      {"Month": 4, "Day": 2, "Hour": 24, "Minute": 60}):
            self.assertIsNone(eta_text(value))
        self.assertEqual(imo_number(9074729), "9074729")
        self.assertIsNone(imo_number(9074728))
        self.assertIsNone(imo_number(True))

    def test_flag_inference_handles_allocations_and_special_identifiers(self):
        self.assertEqual(flag_country("368123456"), "United States of America")
        self.assertIn("Bahamas", flag_country("311123456"))
        self.assertIn("Panama", flag_country("352123456"))
        for mmsi in ("900000001", "970123456", "111368123", "003681234", "983681234", "999999999", "123", "notanMMSI"):
            self.assertEqual(flag_country(mmsi), "Unknown")


if __name__ == "__main__":
    unittest.main()
