"""AIS normalization and a bounded vessel store, independent of the display."""
from collections import deque
from dataclasses import dataclass, field
import math
import time

from .details import dimensions, eta_text, flag_country, integer, imo_number, vessel_type

POSITION_TYPES = (
    "PositionReport", "StandardClassBPositionReport", "ExtendedClassBPositionReport"
)
MESSAGE_TYPES = (*POSITION_TYPES, "ShipStaticData", "StaticDataReport")


def number(value, minimum, maximum, *, exclusive=False):
    if isinstance(value, bool):
        return None
    try:
        result = float(value)
        if math.isfinite(result) and minimum <= result and (
            result < maximum if exclusive else result <= maximum
        ):
            return result
    except (TypeError, ValueError, OverflowError):
        pass
    return None


def clean(value):
    if not isinstance(value, str):
        return ""
    return " ".join("".join(c if c.isprintable() else " " for c in value).strip(" @").split())[:80]


@dataclass(frozen=True)
class Bounds:
    west: float
    south: float
    east: float
    north: float

    def __post_init__(self):
        if not (-180 <= self.west < self.east <= 180 and
                -85 <= self.south < self.north <= 85):
            raise ValueError("Bounds require west < east and south < north (latitude -85..85).")

    @property
    def center(self):
        return ((self.south + self.north) / 2, (self.west + self.east) / 2)

    def contains(self, lat, lon):
        return self.south <= lat <= self.north and self.west <= lon <= self.east

    def subscription(self, key):
        # Config is lon/lat; AISstream corners are LATITUDE, LONGITUDE.
        return {"APIKey": key,
                "BoundingBoxes": [[[self.south, self.west], [self.north, self.east]]],
                "FilterMessageTypes": list(MESSAGE_TYPES)}


def local_nm(lat, lon, center):
    """Equirectangular projection for this small, local viewing area."""
    return ((lon - center[1]) * 60 * math.cos(math.radians(center[0])),
            (lat - center[0]) * 60)


@dataclass
class Vessel:
    mmsi: str
    name: str = ""
    lat: float | None = None
    lon: float | None = None
    speed: float | None = None
    course: float | None = None
    heading: float | None = None
    ship_type: int = 0
    destination: str = ""
    length_m: int | None = None
    beam_m: int | None = None
    length_at_least: bool = False
    beam_at_least: bool = False
    draught_m: float | None = None
    call_sign: str = ""
    imo: str | None = None
    eta: str | None = None
    navigation_status: int | None = None
    ais_class: str = ""
    last_static: float | None = None
    last_voyage: float | None = None
    demo_country: str = ""
    last_position: float | None = None
    last_message: float = 0
    trail: deque = field(default_factory=lambda: deque(maxlen=48))

    @property
    def label(self):
        return self.name or self.mmsi

    @property
    def category(self):
        return vessel_type(self.ship_type)

    @property
    def flag(self):
        return self.demo_country or flag_country(self.mmsi)

    def update_static(self, body, now, type_key="Type", allow_dimensions=True):
        self.last_static = now
        if "Name" in body:
            self.name = clean(body["Name"]) or self.name
        if type_key in body:
            self.ship_type = integer(body[type_key], 0, 99) or 0
        if "CallSign" in body:
            self.call_sign = clean(body["CallSign"])
        if "Dimension" in body and allow_dimensions:
            self.length_m, self.beam_m, self.length_at_least, self.beam_at_least = dimensions(body["Dimension"])
        if "ImoNumber" in body:
            self.imo = imo_number(body["ImoNumber"])

    def update_voyage(self, body, now):
        if any(key in body for key in ("Destination", "Eta", "MaximumStaticDraught")):
            self.last_voyage = now
        if "Destination" in body:
            self.destination = clean(body["Destination"])
        if "Eta" in body:
            self.eta = eta_text(body["Eta"])
        if "MaximumStaticDraught" in body:
            value = number(body["MaximumStaticDraught"], 0, 25.5)
            self.draught_m = value if value else None


class VesselStore:
    def __init__(self, bounds, *, max_vessels=400, trail_points=48, expire_seconds=900):
        self.bounds = bounds
        self.max_vessels = max_vessels
        self.trail_points = trail_points
        self.expire_seconds = expire_seconds
        self.vessels = {}

    def ingest(self, envelope, now=None):
        now = time.monotonic() if now is None else now
        if not isinstance(envelope, dict):
            return False
        kind = envelope.get("MessageType")
        message, meta = envelope.get("Message", {}), envelope.get("MetaData", {})
        if kind not in MESSAGE_TYPES or not isinstance(message, dict) or not isinstance(meta, dict):
            return False
        body = message.get(kind, {})
        if not isinstance(body, dict) or body.get("Valid") is False:
            return False
        raw_id = meta.get("MMSI") or body.get("UserID")
        mmsi = str(raw_id)
        if not mmsi.isdigit() or not 1 <= len(mmsi) <= 9 or int(mmsi) == 0:
            return False
        mmsi = mmsi.zfill(9)
        lat = lon = None
        if kind in POSITION_TYPES:
            lat = number(body.get("Latitude", meta.get("latitude", meta.get("Latitude"))), -90, 90)
            lon = number(body.get("Longitude", meta.get("longitude", meta.get("Longitude"))), -180, 180)
            if lat is None or lon is None:
                return False
            if not self.bounds.contains(lat, lon):
                self.vessels.pop(mmsi, None)
                return False
        vessel = self.vessels.get(mmsi)
        if vessel is None:
            if len(self.vessels) >= self.max_vessels:
                oldest = min(self.vessels, key=lambda key: self.vessels[key].last_message)
                del self.vessels[oldest]
            vessel = Vessel(mmsi, trail=deque(maxlen=self.trail_points))
            self.vessels[mmsi] = vessel
        vessel.last_message = now
        vessel.name = vessel.name or clean(meta.get("ShipName"))
        if kind in POSITION_TYPES:
            vessel.lat, vessel.lon = lat, lon
            vessel.speed = number(body.get("Sog"), 0, 102.3, exclusive=True)
            vessel.course = number(body.get("Cog"), 0, 360, exclusive=True)
            vessel.heading = number(body.get("TrueHeading"), 0, 360, exclusive=True)
            vessel.ais_class = "A" if kind == "PositionReport" else "B"
            if kind == "PositionReport":
                vessel.navigation_status = integer(body.get("NavigationalStatus"), 0, 14)
            else:
                vessel.navigation_status = None
            vessel.last_position = now
            point = (lat, lon)
            if not vessel.trail or vessel.trail[-1] != point:
                vessel.trail.append(point)
        if kind in ("ShipStaticData", "ExtendedClassBPositionReport"):
            vessel.update_static(body, now)
            if kind == "ShipStaticData":
                vessel.update_voyage(body, now)
                vessel.ais_class = "A"
        elif kind == "StaticDataReport":
            report_a, report_b = body.get("ReportA", {}), body.get("ReportB", {})
            part = body.get("PartNumber")
            vessel.ais_class = "B"
            if part in (None, False, 0) and isinstance(report_a, dict) and report_a and report_a.get("Valid") is not False:
                vessel.update_static(report_a, now)
            if part in (None, True, 1) and isinstance(report_b, dict) and report_b and report_b.get("Valid") is not False:
                # On 98-prefixed auxiliary craft the dimension bits encode a mother-ship MMSI.
                vessel.update_static(report_b, now, "ShipType", allow_dimensions=not mmsi.startswith("98"))
        return True

    def expire(self, now=None):
        now = time.monotonic() if now is None else now
        for mmsi, vessel in list(self.vessels.items()):
            seen = vessel.last_position if vessel.last_position is not None else vessel.last_message
            if now - seen > self.expire_seconds:
                del self.vessels[mmsi]

    def positioned(self):
        return [v for v in self.vessels.values() if v.last_position is not None]


