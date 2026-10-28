import os
os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"

from pathlib import Path
import unittest
import tempfile
import time
import pygame
from main import load_config
from tracker.feeds import DemoFeed
from tracker.model import VesselStore
from tracker.ui import TrackerUI


class TouchTests(unittest.TestCase):
    def setUp(self):
        pygame.display.init()
        pygame.font.init()
        config, bounds = load_config(Path(__file__).resolve().parents[1] / "config.example.json")
        display = pygame.display.set_mode((800, 480))
        self.store = VesselStore(bounds)
        self.feed = DemoFeed(bounds)
        self.feed.drain(self.store)
        self.ui = TrackerUI(display, config, bounds, self.store, self.feed)
        self.ui.draw()

    def tearDown(self):
        pygame.quit()

    def test_touch_zoom_ignores_synthetic_mouse(self):
        original = self.ui.range_nm
        self.ui.event(pygame.event.Event(pygame.FINGERDOWN, x=52/800, y=396/480, finger_id=1))
        zoomed = self.ui.range_nm
        self.assertLess(zoomed, original)
        self.ui.event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=(52, 396), button=1, touch=True))
        self.assertEqual(self.ui.range_nm, zoomed)

    def test_drag_home_selection_and_pagination(self):
        self.ui.pointer_down((400, 150))
        self.ui.pointer_move((450, 180))
        self.ui.pointer_up((450, 180))
        self.assertNotEqual(self.ui.center, list(self.ui.bounds.center))
        self.ui.activate("home")
        self.assertEqual(self.ui.center, list(self.ui.bounds.center))
        self.ui.draw()
        point, mmsi = self.ui.targets[-1]
        self.ui.pointer_down(point)
        self.ui.pointer_up(point)
        self.assertEqual(self.ui.selected, mmsi)
        self.ui.pointer_down((748, 295))
        self.ui.draw()
        self.assertEqual(self.ui.page, 1)

    def test_land_and_water_remain_geographically_aligned(self):
        from tracker.land import LAND, WATER
        for center, radius in ((list(self.ui.bounds.center), self.ui.home_range),
                               ([26.12, -80.08], 3.5)):
            self.ui.center, self.ui.range_nm = center, radius
            self.ui.draw()
            for lat, lon, expected in ((26.12, -80.14, LAND), (26.12, -80.0, WATER)):
                point = self.ui.project(lat, lon)
                local = (point[0] - self.ui.chart.x, point[1] - self.ui.chart.y)
                self.assertEqual(self.ui.land.surface.get_at(local)[:3],
                                 pygame.Color(expected)[:3])
            cached = self.ui.land.surface
            self.ui.draw()
            self.assertIs(self.ui.land.surface, cached)

    def test_empty_view_and_letterboxed_touch(self):
        self.store.vessels.clear()
        self.ui.draw()
        self.assertIsNone(self.ui.selected)
        self.ui.display = pygame.display.set_mode((1000, 700))
        self.ui.present()
        x, y = self.ui.logical(self.ui.viewport.center)
        self.assertAlmostEqual(x, 400)
        self.assertAlmostEqual(y, 240)

    def test_profile_touch_navigation_blocks_map_and_handles_expiry(self):
        self.ui.pointer_down((650, 236))
        self.assertTrue(self.ui.details_open)
        self.ui.draw()
        original_center, original_range = list(self.ui.center), self.ui.range_nm
        self.ui.pointer_down((450, 150))
        self.ui.pointer_move((480, 180))
        self.ui.pointer_up((480, 180))
        self.ui.event(pygame.event.Event(pygame.MOUSEWHEEL, y=1))
        self.assertEqual((self.ui.center, self.ui.range_nm), (original_center, original_range))
        self.ui.event(pygame.event.Event(pygame.FINGERDOWN, x=390/800, y=444/480, finger_id=1))
        self.assertEqual(self.ui.details_page, 1)
        self.ui.draw()
        self.store.vessels.clear()
        self.ui.draw()
        self.ui.pointer_down((80, 440))
        self.assertFalse(self.ui.details_open)
        self.ui.draw()
        self.assertIsNone(self.ui.selected)

    def test_saved_card_contains_two_pages_and_preserves_live_ui(self):
        from tracker.cards import save_card
        self.ui.activate("open_details")
        self.ui.draw()
        canvas, buttons = self.ui.canvas, self.ui.buttons
        with tempfile.TemporaryDirectory() as folder:
            self.ui.config["capture_directory"] = folder
            path = save_card(self.ui, self.store.vessels[self.ui.selected], time.monotonic())
            card = pygame.image.load(str(path))
            self.assertEqual(card.get_size(), (800, 960))
            self.assertGreater(path.stat().st_size, 10000)
            self.assertNotEqual(pygame.image.tobytes(card.subsurface((0, 0, 800, 480)), "RGB"),
                                pygame.image.tobytes(card.subsurface((0, 480, 800, 480)), "RGB"))
        self.assertIs(self.ui.canvas, canvas)
        self.assertIs(self.ui.buttons, buttons)
        self.assertTrue(self.ui.details_open)

    def test_unknown_and_stale_profile_and_letterboxed_close(self):
        vessel = self.store.vessels[self.ui.selected]
        vessel.length_m = vessel.beam_m = vessel.draught_m = None
        vessel.eta = None
        vessel.last_position = time.monotonic() - 250
        self.ui.activate("open_details")
        self.ui.display = pygame.display.set_mode((1280, 800))
        self.ui.draw()
        self.ui.activate("details_voyage")
        self.ui.draw()
        viewport = self.ui.viewport
        x = (viewport.x + 80 * viewport.width / 800) / 1280
        y = (viewport.y + 444 * viewport.height / 480) / 800
        self.ui.event(pygame.event.Event(pygame.FINGERDOWN, x=x, y=y, finger_id=1))
        self.assertFalse(self.ui.details_open)


if __name__ == "__main__":
    unittest.main()

