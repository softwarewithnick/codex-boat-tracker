"""A fixed 800 x 480 canvas, letterboxed into the actual display."""
from functools import lru_cache
import math
import time
import pygame

from .model import local_nm
from .land import LandLayer, LAND
from .cards import draw_profile, save_card

BG = "#09141c"
PANEL = "#10232e"
WATER = "#0c1c27"
LINE = "#233e4c"
MUTED = "#8ba5b5"
WHITE = "#ecf3f5"
MINT = "#63dfbf"
AMBER = "#ffbf72"
BLUE = "#76b9ed"
SIZE = (800, 480)


class TrackerUI:
    def __init__(self, display, config, bounds, store, feed):
        self.display, self.config = display, config
        self.bounds, self.store, self.feed = bounds, store, feed
        self.canvas = pygame.Surface(SIZE).convert()
        self.chart = pygame.Rect(16, 82, 500, 350)
        self.land = LandLayer()
        self.center = list(bounds.center)
        east, north = local_nm(bounds.north, bounds.east, bounds.center)
        self.home_range = max(north, east / (500 / 258)) * 1.18
        self.range_nm = self.home_range
        self.selected = None
        self.details_open = False
        self.details_page = 0
        self.card_notice = ""
        self.card_notice_until = 0
        self.page = 0
        self.trails = True
        self.buttons = []
        self.targets = []
        self.pointer = None
        self.running = True
        self.fonts = {size: pygame.font.SysFont("segoeui,dejavusans", size)
                      for size in (11, 12, 13, 14, 16, 18, 20, 24, 28)}
        self.viewport = pygame.Rect(0, 0, *SIZE)

    @lru_cache(maxsize=256)
    def rendered(self, value, size, color):
        return self.fonts[size].render(value, True, color)

    def text(self, value, xy, size=14, color=WHITE, max_width=None):
        value = str(value)
        if max_width:
            while value and self.fonts[size].size(value)[0] > max_width:
                value = value[:-4] + "..." if len(value) > 3 else ""
        surface = self.rendered(value, size, color)
        self.canvas.blit(surface, xy)

    def button(self, rect, label, action, active=False, enabled=True, size=16):
        rect = pygame.Rect(rect)
        fill = "#20483f" if active else "#19323f"
        pygame.draw.rect(self.canvas, fill if enabled else PANEL, rect, border_radius=10)
        pygame.draw.rect(self.canvas, "#3b7868" if active else LINE, rect, 1, border_radius=10)
        surface = self.rendered(label, size, MINT if active else WHITE if enabled else MUTED)
        self.canvas.blit(surface, surface.get_rect(center=rect.center))
        if enabled:
            self.buttons.append((rect, action))

    @property
    def scale(self):
        return (self.chart.height - 92) / 2 / self.range_nm

    def project(self, lat, lon):
        east, north = local_nm(lat, lon, self.center)
        return (round(self.chart.centerx + east * self.scale),
                round(self.chart.centery - 14 - north * self.scale))

    def color(self, vessel, now):
        if now - vessel.last_position > self.config["stale_seconds"]:
            return MUTED
        return AMBER if vessel.category == "Passenger" else BLUE if vessel.category in ("Cargo", "Tanker") else MINT

    def draw_chart(self, vessels, now):
        self.land.draw(self.canvas, self.chart, self.project, (tuple(self.center), self.range_nm))
        self.canvas.set_clip(self.chart.inflate(-2, -2))
        origin = self.project(*self.bounds.center)
        # Fixed geographic grid and range rings around the configured area center.
        step = 1 if self.range_nm <= 5 else 2 if self.range_nm <= 10 else 5
        for n in range(-20, 21, step):
            x = round(origin[0] + n * self.scale)
            y = round(origin[1] + n * self.scale)
            pygame.draw.line(self.canvas, "#142b37", (x, self.chart.top), (x, self.chart.bottom))
            pygame.draw.line(self.canvas, "#142b37", (self.chart.left, y), (self.chart.right, y))
        for n in range(step, 21, step):
            radius = round(n * self.scale)
            if radius > 1500:
                break
            pygame.draw.circle(self.canvas, LINE, origin, radius, 1)
            if self.chart.top + 50 < origin[1] - radius < self.chart.bottom - 70:
                self.text(f"{n} NM", (origin[0] + 6, origin[1] - radius + 2), 11, MUTED)
        top_left = self.project(self.bounds.north, self.bounds.west)
        bottom_right = self.project(self.bounds.south, self.bounds.east)
        box = pygame.Rect(top_left, (bottom_right[0] - top_left[0], bottom_right[1] - top_left[1]))
        pygame.draw.rect(self.canvas, "#3a6878", box, 1)
        for dx, dy in ((-6, 0), (0, -6)):
            pygame.draw.line(self.canvas, MUTED, (origin[0] + dx, origin[1] + dy),
                             (origin[0] - dx, origin[1] - dy), 1)
        self.targets = []
        for vessel in vessels:
            color = self.color(vessel, now)
            point = self.project(vessel.lat, vessel.lon)
            selected = vessel.mmsi == self.selected
            if self.trails and len(vessel.trail) > 1:
                points = [self.project(*p) for p in vessel.trail]
                pygame.draw.lines(self.canvas, "#375d6b" if not selected else "#4c9688", False, points, 1)
            if not self.chart.inflate(-30, -30).collidepoint(point):
                continue
            angle_value = vessel.heading if vessel.heading is not None else vessel.course
            if angle_value is None:
                pygame.draw.circle(self.canvas, color, point, 6)
            else:
                angle = math.radians(angle_value)
                # AIS angles are clockwise from north.
                shape = [(0, -11), (7, 8), (0, 4), (-7, 8)]
                rotated = [(point[0] + x * math.cos(angle) - y * math.sin(angle),
                            point[1] + x * math.sin(angle) + y * math.cos(angle)) for x, y in shape]
                pygame.draw.polygon(self.canvas, color, rotated)
            if selected:
                pygame.draw.circle(self.canvas, WHITE, point, 19, 1)
                name = vessel.label
                text_width = min(180, self.fonts[12].size(name)[0] + 12)
                label_rect = pygame.Rect(min(point[0] + 22, self.chart.right - text_width - 8),
                                         point[1] - 11, text_width, 24)
                pygame.draw.rect(self.canvas, PANEL, label_rect, border_radius=5)
                self.text(name, (label_rect.x + 6, label_rect.y + 3), 12, WHITE, text_width - 12)
            self.targets.append((point, vessel.mmsi))
        self.canvas.set_clip(None)
        pygame.draw.rect(self.canvas, LINE, self.chart, 1, border_radius=14)
        pygame.draw.rect(self.canvas, WATER, (28, 92, 286, 25), border_radius=6)
        self.text("POSITION VIEW", (32, 96), 12, MINT)
        self.text("/  COASTLINE", (138, 96), 12, MUTED)
        pygame.draw.rect(self.canvas, LAND, (32, 126, 9, 9), border_radius=2)
        self.text("LAND / APPROXIMATE", (47, 122), 11, MUTED)
        self.text("N", (484, 98), 14, WHITE)
        pygame.draw.line(self.canvas, MINT, (488, 130), (488, 120), 2)
        pygame.draw.polygon(self.canvas, MINT, [(488, 115), (484, 121), (492, 121)])
        if not vessels:
            self.text("Waiting for vessel positions", (140, 211), 18, WHITE)
            self.text("Reports appear as AISstream receives them", (108, 239), 13, MUTED)
        scale_nm = min((.05, .1, .2, .5, 1, 2, 5, 10), key=lambda nm: abs(nm * self.scale - 80))
        scale_end = 32 + round(scale_nm * self.scale)
        self.text(f"{scale_nm:g} NM", (32, 327), 11, WHITE)
        pygame.draw.line(self.canvas, WHITE, (32, 348), (scale_end, 348), 2)
        for x in (32, scale_end):
            pygame.draw.line(self.canvas, WHITE, (x, 344), (x, 352), 2)
        if not self.land.covers(*self.center):
            self.text("OUTSIDE LOCAL MAP COVERAGE", (310, 347), 11, AMBER)
        self.button((28, 372, 48, 48), "+", "zoom_in", size=24)
        self.button((82, 372, 48, 48), "-", "zoom_out", size=24)
        self.button((136, 372, 78, 48), "Home", "home")
        self.button((220, 372, 84, 48), "Trails", "trails", active=self.trails)
        self.text("VIEW RADIUS", (369, 378), 11, MUTED)
        self.text(f"{self.range_nm:.1f} NM", (369, 394), 18, WHITE)

    def draw_panel(self, vessels, now):
        pygame.draw.rect(self.canvas, PANEL, (532, 82, 252, 350), border_radius=14)
        vessel = self.store.vessels.get(self.selected)
        self.text("SELECTED VESSEL", (548, 95), 11, MINT)
        if vessel and vessel.last_position is not None:
            self.text(vessel.label, (548, 113), 18, WHITE, 220)
            self.text(f"{vessel.category}  /  {vessel.mmsi}", (548, 139), 12, MUTED, 220)
            self.text("--" if vessel.speed is None else f"{vessel.speed:.1f}", (548, 162), 28)
            self.text("--" if vessel.course is None else f"{vessel.course:.0f}°", (668, 162), 28)
            self.text("SPEED / KN", (548, 196), 11, MUTED)
            self.text("COURSE", (668, 196), 11, MUTED)
        else:
            self.text("Tap a vessel", (548, 123), 20)
            self.text("Explore its size, flag", (548, 157), 14, MUTED)
            self.text("and reported voyage.", (548, 178), 14, MUTED)
        self.button((548, 214, 220, 44), "Vessel details >", "open_details",
                    enabled=vessel is not None and vessel.last_position is not None)
        pygame.draw.line(self.canvas, LINE, (548, 267), (768, 267))
        pages = max(1, math.ceil(len(vessels) / 2))
        self.page = min(self.page, pages - 1)
        self.text(f"VESSELS / {len(vessels):02}", (548, 285), 12, MUTED)
        self.button((676, 273, 44, 44), "<", "prev", enabled=self.page > 0)
        self.button((726, 273, 44, 44), ">", "next", enabled=self.page + 1 < pages)
        for index, v in enumerate(vessels[self.page * 2:self.page * 2 + 2]):
            rect = pygame.Rect(542, 320 + index * 52, 232, 48)
            active = v.mmsi == self.selected
            pygame.draw.rect(self.canvas, "#1a3b40" if active else "#142d39", rect, border_radius=8)
            pygame.draw.circle(self.canvas, self.color(v, now), (555, rect.y + 16), 3)
            self.text(v.label, (566, rect.y + 5), 13, WHITE, 197)
            speed = "--" if v.speed is None else f"{v.speed:.1f}"
            self.text(f"{v.category} / {speed} kn", (566, rect.y + 25), 11, MUTED, 197)
            self.buttons.append((rect, ("select", v.mmsi)))

    def draw(self):
        now = time.monotonic()
        vessels = sorted(self.store.positioned(), key=lambda v: v.mmsi)
        if not self.details_open and self.selected not in {v.mmsi for v in vessels}:
            self.selected = vessels[0].mmsi if vessels else None
        self.buttons = []
        if self.details_open:
            self.targets = []
            draw_profile(self, self.store.vessels.get(self.selected), self.details_page, now)
            self.present()
            return
        self.canvas.fill(BG)
        # Compact radar mark.
        for radius in (7, 15):
            pygame.draw.circle(self.canvas, MINT, (34, 32), radius, 1)
        pygame.draw.line(self.canvas, MINT, (34, 32), (45, 20), 2)
        pygame.draw.circle(self.canvas, MINT, (29, 36), 2)
        self.text("HARBOR", (60, 12), 24)
        self.text(self.config["area_name"].upper() + " / LOCAL WATERS", (61, 43), 11, MUTED, 400)
        demo = self.feed.status == "DEMO"
        color = AMBER if demo or self.feed.status != "CONNECTED" else MINT
        status = "DEMO / SIMULATED" if demo else "AIS / " + self.feed.status
        pygame.draw.circle(self.canvas, color, (524, 29), 4)
        self.text(status, (536, 19), 13, color, 190)
        self.text("HARBOR v0.2.1 / DETAILS", (536, 42), 11, MUTED)
        self.button((736, 10, 48, 48), "X", "quit", size=18)
        pygame.draw.line(self.canvas, LINE, (16, 68), (784, 68))
        self.draw_chart(vessels, now)
        self.draw_panel(vessels, now)
        detail = self.feed.detail
        if self.feed.last_received is not None and not demo:
            detail += f" / last report {int(now - self.feed.last_received)}s ago"
        if self.feed.dropped:
            detail += f" / queue drops {self.feed.dropped}"
        self.text(detail, (18, 444), 12, MUTED, 585)
        self.text("PROTOTYPE / NOT A CHART", (607, 445), 11, MUTED)
        self.present()

    def present(self):
        w, h = self.display.get_size()
        ratio = min(w / SIZE[0], h / SIZE[1])
        target = (max(1, round(SIZE[0] * ratio)), max(1, round(SIZE[1] * ratio)))
        self.viewport = pygame.Rect((w - target[0]) // 2, (h - target[1]) // 2, *target)
        self.display.fill(BG)
        frame = self.canvas if target == SIZE else pygame.transform.scale(self.canvas, target)
        self.display.blit(frame, self.viewport)
        pygame.display.flip()

    def logical(self, pos):
        return ((pos[0] - self.viewport.x) * 800 / self.viewport.width,
                (pos[1] - self.viewport.y) * 480 / self.viewport.height)

    def activate(self, action):
        if action == "close_details":
            self.details_open = False
            self.pointer = None
        elif action == "open_details":
            if self.selected in self.store.vessels:
                self.details_open = True
                self.details_page = 0
                self.pointer = None
        elif action in ("details_overview", "details_voyage"):
            self.details_page = 0 if action == "details_overview" else 1
        elif action == "save_card":
            vessel = self.store.vessels.get(self.selected)
            if vessel and vessel.last_position is not None:
                try:
                    save_card(self, vessel, time.monotonic())
                    self.card_notice = "Saved to captures/"
                except (OSError, pygame.error):
                    self.card_notice = "Save failed - check folder"
                self.card_notice_until = time.monotonic() + 4
        elif self.details_open:
            if action == "quit":
                self.details_open = False
            return
        elif isinstance(action, tuple):
            self.selected = action[1]
            v = self.store.vessels[self.selected]
            self.center = [v.lat, v.lon]
        elif action == "quit":
            self.running = False
        elif action == "zoom_in":
            self.range_nm = max(.25, self.range_nm / 1.4)
        elif action == "zoom_out":
            self.range_nm = min(20, self.range_nm * 1.4)
        elif action == "home":
            self.center, self.range_nm = list(self.bounds.center), self.home_range
        elif action == "trails":
            self.trails = not self.trails
        elif action == "prev":
            self.page = max(0, self.page - 1)
        elif action == "next":
            self.page += 1

    def pointer_down(self, pos):
        for rect, action in reversed(self.buttons):
            if rect.collidepoint(pos):
                self.activate(action)
                return
        if not self.details_open and self.chart.collidepoint(pos):
            self.pointer = (pos, list(self.center))

    def pointer_move(self, pos):
        if not self.pointer:
            return
        start, center = self.pointer
        dx, dy = pos[0] - start[0], pos[1] - start[1]
        self.center[0] = max(-85, min(85, center[0] + dy / self.scale / 60))
        self.center[1] = max(-180, min(180, center[1] - dx / self.scale / 60 /
                                     math.cos(math.radians(center[0]))))

    def pointer_up(self, pos):
        if not self.pointer:
            return
        start, _ = self.pointer
        self.pointer = None
        if math.dist(start, pos) <= 10 and self.targets:
            point, mmsi = min(self.targets, key=lambda item: math.dist(pos, item[0]))
            if math.dist(point, pos) <= 26:
                self.selected = mmsi

    def event(self, event):
        if event.type == pygame.QUIT:
            self.running = False
        elif event.type == pygame.KEYDOWN:
            actions = {pygame.K_ESCAPE: "quit", pygame.K_q: "quit",
                       pygame.K_HOME: "home", pygame.K_h: "home", pygame.K_t: "trails",
                       pygame.K_EQUALS: "zoom_in", pygame.K_PLUS: "zoom_in",
                       pygame.K_MINUS: "zoom_out"}
            if event.key in actions:
                self.activate(actions[event.key])
        elif event.type in (pygame.FINGERDOWN, pygame.FINGERMOTION, pygame.FINGERUP):
            pos = self.logical((event.x * self.display.get_width(), event.y * self.display.get_height()))
            {pygame.FINGERDOWN: self.pointer_down, pygame.FINGERMOTION: self.pointer_move,
             pygame.FINGERUP: self.pointer_up}[event.type](pos)
        elif event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEMOTION):
            if getattr(event, "touch", False):
                return  # SDL synthesizes mouse events for fingers; avoid double activation.
            pos = self.logical(event.pos)
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                self.pointer_down(pos)
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
                self.pointer_up(pos)
            elif event.type == pygame.MOUSEMOTION:
                self.pointer_move(pos)
        elif event.type == pygame.MOUSEWHEEL:
            self.activate("zoom_in" if event.y > 0 else "zoom_out")


