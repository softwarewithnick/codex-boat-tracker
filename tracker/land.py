"""Small bundled vector basemap; no network or GIS packages at runtime."""
import json
from pathlib import Path
import pygame

WATER = "#0c1c27"
LAND = "#283f40"
SHORE = "#688d88"


class LandLayer:
    def __init__(self, path=None):
        path = path or Path(__file__).resolve().parents[1] / "data" / "south-florida-land.json"
        self.data = json.loads(Path(path).read_text(encoding="utf-8"))
        self.cache_key = None
        self.surface = None

    def covers(self, lat, lon):
        west, south, east, north = self.data["extent"]
        return west <= lon <= east and south <= lat <= north

    def draw(self, target, rect, project, view_key):
        key = (view_key, tuple(rect))
        if key != self.cache_key:
            surface = pygame.Surface(rect.size, pygame.SRCALPHA)
            surface.fill(WATER)

            def points(ring):
                return [(x - rect.x, y - rect.y) for x, y in
                        (project(lat, lon) for lon, lat in ring)]

            for polygon in self.data["land"]:
                pygame.draw.polygon(surface, LAND, points(polygon["outer"]))
                for hole in polygon["holes"]:
                    pygame.draw.polygon(surface, WATER, points(hole))
            for line in self.data["coastline"]:
                pygame.draw.lines(surface, SHORE, False, points(line), 2)
            mask = pygame.Surface(rect.size, pygame.SRCALPHA)
            pygame.draw.rect(mask, "white", mask.get_rect(), border_radius=14)
            surface.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
            self.surface, self.cache_key = surface, key
        target.blit(self.surface, rect)

