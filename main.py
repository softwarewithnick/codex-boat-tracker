"""Run the local boat tracker: python main.py [--live] [--fullscreen]."""
import argparse
import json
import os
from pathlib import Path
import sys

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")


def load_config(path):
    with open(path, encoding="utf-8-sig") as handle:
        config = json.load(handle)
    from tracker.model import Bounds
    bounds = Bounds(**config["bounds"])
    display = config["display"]
    if not (320 <= display["width"] <= 7680 and 240 <= display["height"] <= 4320):
        raise ValueError("Display dimensions are out of range.")
    if not 1 <= display["fps"] <= 60:
        raise ValueError("FPS must be 1..60.")
    if not 0 < config["stale_seconds"] < config["expire_seconds"]:
        raise ValueError("Require 0 < stale_seconds < expire_seconds.")
    if not 1 <= config["max_vessels"] <= 5000 or not 2 <= config["trail_points"] <= 500:
        raise ValueError("Vessel or trail limit is out of range.")
    return config, bounds


def main():
    parser = argparse.ArgumentParser(description="Touch-friendly local AIS vessel viewer.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--live", action="store_true", help="Connect to AISstream using AISSTREAM_API_KEY.")
    mode.add_argument("--demo", action="store_true", help="Simulated traffic (the default).")
    default_config = Path(__file__).with_name("config.json")
    if not default_config.exists():
        default_config = Path(__file__).with_name("config.example.json")
    parser.add_argument("--config", type=Path, default=default_config)
    parser.add_argument("--fullscreen", action="store_true")
    parser.add_argument("--headless", action="store_true", help="Render without a desktop window.")
    parser.add_argument("--frames", type=int, default=0, help="Exit after N frames; 0 means unlimited.")
    parser.add_argument("--screenshot", type=Path, help="Save the final rendered frame as a PNG.")
    args = parser.parse_args()
    if args.frames < 0:
        parser.error("--frames must be nonnegative.")
    key = os.environ.get("AISSTREAM_API_KEY", "").strip()
    if args.live and not key:
        parser.error("Live mode requires AISSTREAM_API_KEY. Set it in your local environment.")
    try:
        config, bounds = load_config(args.config)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.error(f"Invalid configuration: {error}")
    if args.headless:
        os.environ["SDL_VIDEODRIVER"] = "dummy"
    try:
        import pygame
        from tracker.feeds import AISStreamFeed, DemoFeed
        from tracker.model import VesselStore
        from tracker.ui import TrackerUI
        if args.live:
            import websockets  # Fail before opening a window if the live dependency is missing.
    except ImportError as error:
        print(f"Missing dependency: {error.name}. Run: python -m pip install -r requirements.txt", file=sys.stderr)
        return 1
    pygame.display.init()
    pygame.font.init()
    pygame.display.set_caption("Harbor / local boat tracker")
    flags = pygame.FULLSCREEN if args.fullscreen else pygame.RESIZABLE
    size = (config["display"]["width"], config["display"]["height"])
    display = pygame.display.set_mode(size, flags)
    store = VesselStore(bounds, max_vessels=config["max_vessels"],
                        trail_points=config["trail_points"], expire_seconds=config["expire_seconds"])
    feed = AISStreamFeed(bounds, key) if args.live else DemoFeed(bounds)
    ui = TrackerUI(display, config, bounds, store, feed)
    clock = pygame.time.Clock()
    frame = 0
    feed.start()
    try:
        while ui.running:
            feed.drain(store)
            store.expire()
            for event in pygame.event.get():
                ui.event(event)
            ui.draw()
            frame += 1
            if args.frames and frame >= args.frames:
                break
            clock.tick(config["display"]["fps"])
        if args.screenshot:
            args.screenshot.parent.mkdir(parents=True, exist_ok=True)
            pygame.image.save(ui.canvas, args.screenshot)
    except KeyboardInterrupt:
        pass
    finally:
        feed.close()
        pygame.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

