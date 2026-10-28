"""Touch-friendly vessel profiles and a local, two-page PNG sighting card."""
from datetime import datetime, timezone
from pathlib import Path
import pygame

from .details import NAVIGATION, age_text, measurement

BG, PANEL, LINE = "#09141c", "#10232e", "#233e4c"
WHITE, MUTED, MINT, AMBER = "#ecf3f5", "#8ba5b5", "#63dfbf", "#ffbf72"


def metric(ui, x, y, width, label, value, size=24):
    pygame.draw.rect(ui.canvas, PANEL, (x, y, width, 72), border_radius=12)
    ui.text(label, (x + 14, y + 10), 11, MUTED, width - 28)
    ui.text(value, (x + 14, y + 31), size, WHITE, width - 28)


def draw_profile(ui, vessel, page, now, *, exporting=False, saved_at=None):
    ui.canvas.fill(BG)
    demo = ui.feed.status == "DEMO"
    ui.text("HARBOR / " + ("DEMO SIGHTING - SIMULATED" if demo else "VESSEL SIGHTING"),
            (24, 14), 12, AMBER if demo else MINT)
    if not vessel or vessel.last_position is None:
        ui.text("Vessel no longer tracked", (24, 100), 24)
        ui.text("Return to the map to choose another vessel.", (24, 142), 16, MUTED)
        if not exporting:
            ui.button((24, 420, 130, 48), "< Map", "close_details")
        return
    ui.text(vessel.label, (24, 38), 28, WHITE, 648)
    if not exporting:
        ui.button((724, 12, 52, 48), "X", "close_details")
    nav = NAVIGATION.get(vessel.navigation_status, "Status not reported")
    ui.text(f"{vessel.category}  /  {nav}", (24, 77), 14, MUTED, 752)
    flag_label = "Flag (demo)" if vessel.demo_country else "Flag inferred from MMSI"
    ui.text(f"{flag_label}: {vessel.flag}", (24, 101), 14, MINT, 752)
    if page == 0:
        metric(ui, 24, 138, 240, "LENGTH", measurement(vessel.length_m, vessel.length_at_least))
        metric(ui, 280, 138, 240, "WIDTH / BEAM", measurement(vessel.beam_m, vessel.beam_at_least))
        metric(ui, 536, 138, 240, "REPORTED DRAFT", measurement(vessel.draught_m, vessel.draught_m == 25.5, 1))
        metric(ui, 24, 222, 240, "SPEED OVER GROUND", "Unknown" if vessel.speed is None else f"{vessel.speed:.1f} kn")
        metric(ui, 280, 222, 240, "COURSE OVER GROUND", "Unknown" if vessel.course is None else f"{vessel.course:.0f}°")
        metric(ui, 536, 222, 240, "HEADING / BOW DIRECTION", "Unknown" if vessel.heading is None else f"{vessel.heading:.0f}°")
        # Stylised side profile: explicitly a comparison, never a vessel photograph.
        pygame.draw.polygon(ui.canvas, "#20483f", [(26, 348), (330, 348), (310, 370), (48, 370)])
        pygame.draw.rect(ui.canvas, "#3b7868", (245, 323, 36, 25), border_radius=3)
        pygame.draw.line(ui.canvas, MINT, (25, 382), (330, 382), 1)
        for x in (25, 330):
            pygame.draw.line(ui.canvas, MINT, (x, 378), (x, 386), 1)
        ui.text("ILLUSTRATION / NOT TO SCALE", (32, 395), 11, MUTED)
        ui.text("HOW BIG IS IT?", (360, 318), 11, MINT)
        if vessel.length_m is not None:
            prefix = "At least" if vessel.length_at_least else "About"
            ui.text(f"{prefix} {vessel.length_m / 12:.1f} city buses long", (360, 340), 20, WHITE, 414)
            ui.text("Compared with a 12 m bus, end to end.", (360, 371), 13, MUTED)
        else:
            ui.text("Waiting for reported dimensions", (360, 342), 18, WHITE, 414)
            ui.text("Static details may take several minutes.", (360, 371), 13, MUTED)
    else:
        metric(ui, 24, 134, 368, "REPORTED DESTINATION", vessel.destination or "Not reported", 20)
        metric(ui, 408, 134, 368, "REPORTED ETA / NO YEAR IN AIS", vessel.eta or "Not reported", 20)
        metric(ui, 24, 214, 240, "RADIO CALL SIGN", vessel.call_sign or "Not reported", 20)
        metric(ui, 280, 214, 240, "IMO NUMBER", vessel.imo or "Not reported / invalid", 18)
        metric(ui, 536, 214, 240, "MMSI / AIS CLASS", f"{vessel.mmsi} / {vessel.ais_class or '?'}", 18)
        ui.text("LAST REPORTED POSITION", (24, 302), 11, MUTED)
        ui.text(f"{vessel.lat:.5f}, {vessel.lon:.5f}", (24, 322), 18, WHITE)
        stale = now - vessel.last_position > ui.config["stale_seconds"]
        ui.text(("STALE / " if stale else "Received / ") + age_text(vessel.last_position, now),
                (24, 350), 13, AMBER if stale else MINT)
        ui.text("DETAILS RECEIVED", (408, 302), 11, MUTED)
        ui.text("Identity / " + age_text(vessel.last_static, now), (408, 322), 14, WHITE)
        ui.text("Voyage / " + age_text(vessel.last_voyage, now), (408, 350), 14, WHITE)
        ui.text("Reported by vessel; may be missing or outdated.", (24, 386), 13, MUTED)
    if exporting:
        ui.text("AISstream / " + ui.config["area_name"] + " / not for navigation", (24, 427), 12, MUTED, 752)
        ui.text(f"Saved {saved_at}  |  Page {page + 1}/2", (24, 449), 12, MUTED)
    else:
        ui.button((24, 420, 120, 48), "< Map", "close_details")
        ui.button((158, 420, 150, 48), "Overview", "details_overview", active=page == 0)
        ui.button((322, 420, 150, 48), "Voyage + ID", "details_voyage", active=page == 1)
        saved = now < ui.card_notice_until
        label = ui.card_notice if saved else "Save card"
        ui.button((486, 420, 290, 48), label, "save_card", size=14 if saved else 16)


def save_card(ui, vessel, now):
    """Export both pages locally. Never upload data or include credentials."""
    folder = Path(ui.config.get("capture_directory", Path(__file__).resolve().parents[1] / "captures")).expanduser()
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc)
    path = folder / f"harbor-{vessel.mmsi}-{stamp:%Y%m%dT%H%M%S%fZ}.png"
    original_canvas, original_buttons = ui.canvas, ui.buttons
    try:
        ui.canvas = pygame.Surface((800, 480))
        ui.buttons = []
        card = pygame.Surface((800, 960))
        for page in range(2):
            draw_profile(ui, vessel, page, now, exporting=True, saved_at=stamp.strftime("%d %b %Y %H:%M UTC"))
            card.blit(ui.canvas, (0, page * 480))
        pygame.image.save(card, str(path))
    finally:
        ui.canvas, ui.buttons = original_canvas, original_buttons
    return path
