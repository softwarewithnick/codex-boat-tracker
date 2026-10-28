"""Render deterministic demo/unknown profiles for visual review, without network."""
import os
from pathlib import Path
import sys
import time

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pygame
from main import load_config
from tracker.cards import save_card
from tracker.feeds import DemoFeed
from tracker.model import VesselStore
from tracker.ui import TrackerUI


def main():
    folder = ROOT / "previews"
    folder.mkdir(exist_ok=True)
    pygame.display.init()
    pygame.font.init()
    config, bounds = load_config(ROOT / "config.example.json")
    config["capture_directory"] = str(folder)
    store, feed = VesselStore(bounds), DemoFeed(bounds)
    feed.drain(store)
    ui = TrackerUI(pygame.display.set_mode((1280, 800)), config, bounds, store, feed)
    ui.draw()
    pygame.image.save(ui.canvas, str(folder / "map.png"))
    ui.activate("open_details")
    ui.draw()
    pygame.image.save(ui.canvas, str(folder / "vessel-overview.png"))
    # Also verify the actual 1280x800 letterboxed frame.
    pygame.image.save(ui.display, str(folder / "touchscreen-1280x800.png"))
    ui.activate("details_voyage")
    ui.draw()
    pygame.image.save(ui.canvas, str(folder / "vessel-voyage.png"))
    saved = save_card(ui, store.vessels[ui.selected], time.monotonic())
    saved.replace(folder / "sample-sighting-card.png")
    ui.selected = "900000002"
    ui.draw()
    pygame.image.save(ui.canvas, str(folder / "class-b-voyage.png"))
    vessel = store.vessels[ui.selected]
    vessel.length_m = vessel.beam_m = None
    vessel.last_position = time.monotonic() - 240
    ui.activate("details_overview")
    ui.draw()
    pygame.image.save(ui.canvas, str(folder / "unknown-dimensions.png"))
    ui.activate("details_voyage")
    ui.draw()
    pygame.image.save(ui.canvas, str(folder / "stale-voyage.png"))
    pygame.quit()
    print("Rendered 8 preview images")


if __name__ == "__main__":
    main()
