"""Offline AIS field interpretation. Unknown values must never look like facts."""
import calendar
from datetime import datetime
from functools import lru_cache
import json
from pathlib import Path


NAVIGATION = {
    0: "Underway using engine", 1: "At anchor", 2: "Not under command",
    3: "Restricted manoeuvrability", 4: "Constrained by draught", 5: "Moored",
    6: "Aground", 7: "Engaged in fishing", 8: "Underway sailing",
    9: "Reserved (high-speed craft)", 10: "Reserved (wing-in-ground)",
    11: "Towing astern", 12: "Pushing / towing alongside",
    13: "Reserved", 14: "AIS-SART / active alert",
}


def integer(value, low, high):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if not low <= value <= high or int(value) != value:
        return None
    return int(value)


def dimensions(value):
    """Return (length, beam, length_is_lower_bound, beam_is_lower_bound)."""
    if not isinstance(value, dict):
        return None, None, False, False
    a, b = (integer(value.get(k), 0, 511) for k in ("A", "B"))
    c, d = (integer(value.get(k), 0, 63) for k in ("C", "D"))
    length = (a + b or None) if a is not None and b is not None else None
    beam = (c + d or None) if c is not None and d is not None else None
    return length, beam, 511 in (a, b), 63 in (c, d)


def eta_text(value):
    """AIS ETA has no year; do not invent a year or a countdown."""
    if not isinstance(value, dict):
        return None
    month = integer(value.get("Month"), 1, 12)
    day = integer(value.get("Day"), 1, 31)
    hour = integer(value.get("Hour"), 0, 23)
    minute = integer(value.get("Minute"), 0, 59)
    if None in (month, day, hour, minute):
        return None
    try:
        datetime(2000, month, day, hour, minute)
    except ValueError:
        return None
    return f"{day:02} {calendar.month_abbr[month]} {hour:02}:{minute:02} UTC"


def imo_number(value):
    value = integer(value, 1000000, 9999999)
    if value is None:
        return None
    digits = str(value)
    check = sum(int(digit) * weight for digit, weight in zip(digits[:6], range(7, 1, -1))) % 10
    return digits if check == int(digits[-1]) else None


@lru_cache(maxsize=1)
def country_table():
    path = Path(__file__).resolve().parents[1] / "data" / "mid-countries.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))["countries"]
    except (OSError, ValueError, KeyError):
        return {}


def flag_country(mmsi):
    # Ordinary ship stations only. Do not mistake SAR, AtoN, handheld or
    # auxiliary-craft identifiers for an ordinary ship registration.
    if len(mmsi) != 9 or not mmsi.isascii() or not mmsi.isdigit() or mmsi[0] not in "234567":
        return "Unknown"
    return country_table().get(mmsi[:3], "Unknown")


def vessel_type(code):
    groups = {2: "Wing-in-ground craft", 4: "High-speed craft", 6: "Passenger",
              7: "Cargo", 8: "Tanker", 9: "Other vessel"}
    if code // 10 in groups:
        return groups[code // 10]
    return {
        30: "Fishing", 31: "Towing", 32: "Towing (large tow)",
        33: "Dredging / underwater ops", 34: "Diving operations", 35: "Military",
        36: "Sailing", 37: "Pleasure craft", 50: "Pilot vessel", 51: "Search and rescue",
        52: "Tug", 53: "Port tender", 54: "Anti-pollution", 55: "Law enforcement",
        58: "Medical transport", 59: "Noncombatant vessel",
    }.get(code, "Unknown type" if not code else f"Other / AIS type {code}")


def measurement(value, lower_bound=False, decimals=0):
    if value is None:
        return "Unknown"
    return f"{'≥ ' if lower_bound else ''}{value:.{decimals}f} m"


def age_text(timestamp, now):
    if timestamp is None:
        return "Not received"
    seconds = max(0, int(now - timestamp))
    return f"{seconds}s ago" if seconds < 60 else f"{seconds // 60}m ago"
