"""GPL-2.0-or-later. Pure contact-frame recogniser; no OS calls or wall clock.

Coordinates are normalized to [0, 1]. Time is monotonic seconds supplied by
the host. Actions are requests, never injected here. cancel() releases a drag.
"""

from dataclasses import dataclass
from math import hypot, isfinite


@dataclass(frozen=True)
class Contact:
    id: int
    x: float
    y: float
    tip: bool = True
    confidence: bool = True


@dataclass(frozen=True)
class Frame:
    time: float
    contacts: tuple[Contact, ...]
    device: int = 0
    scan_time: int = 0
    button: bool = False


@dataclass(frozen=True)
class Action:
    kind: str
    dx: float = 0
    dy: float = 0


DEFAULTS = {
    "three_finger_drag": False, "smart_zoom": False, "notification_center": False,
    "launchpad": False, "lookup": False,
    "drag_release_delay": 0.5, "tap_max_movement": 0.025, "tap_max_time": 0.25,
    "edge_width": 0.08, "drag_start_movement": 0.012, "drag_start_time": 0.35,
    "double_tap_time": 0.35, "swipe_distance": 0.12, "pinch_ratio": 0.25,
    "pointer_scale": 1800.0,
}
TOGGLES = tuple(k for k, v in DEFAULTS.items() if type(v) is bool)
RANGES = {
    "drag_release_delay": (0, 1.5), "tap_max_movement": (0.003, 0.1),
    "tap_max_time": (0.08, 0.5), "edge_width": (0.02, 0.25),
    "drag_start_movement": (0.003, 0.08), "drag_start_time": (0.1, 0.7),
    "double_tap_time": (0.15, 0.6), "swipe_distance": (0.05, 0.4),
    "pinch_ratio": (0.1, 0.6), "pointer_scale": (300, 5000),
}


def validate(settings: dict) -> dict:
    if not isinstance(settings, dict) or set(settings) - set(DEFAULTS):
        raise ValueError("Unknown gesture settings.")
    result = {**DEFAULTS, **settings}
    for key in TOGGLES:
        if type(result[key]) is not bool:
            raise ValueError(f"{key} must be true or false.")
    for key, (low, high) in RANGES.items():
        value = result[key]
        if type(value) not in (int, float) or not isfinite(value) or not low <= value <= high:
            raise ValueError(f"{key} must be between {low} and {high}.")
    return result


def centre(points) -> tuple[float, float]:
    return (sum(p.x for p in points) / len(points), sum(p.y for p in points) / len(points))


def radius(points) -> float:
    x, y = centre(points)
    return sum(hypot(p.x - x, p.y - y) for p in points) / len(points)


class Recognizer:
    def __init__(self, settings=None, four_swipes=False):
        self.settings = validate(settings or {})
        self.four_swipes = four_swipes
        self.dragging = False
        self.release_at = None
        self.pending_tap = None
        self.device = None
        self.last_time = None
        self.last_frame_time = None
        self._clear_session()

    def _clear_session(self):
        self.start_time = None
        self.origins = {}
        self.peak = 0
        self.movement = 0.0
        self.anchor = None
        self.initial_radius = None
        self.blocked = False
        self.fired = False
        self.previous = {}

    def cancel(self) -> list[Action]:
        actions = [Action("left_up")] if self.dragging else []
        self.dragging = False
        self.release_at = None
        self.pending_tap = None
        self._clear_session()
        return actions

    def tick(self, now: float) -> list[Action]:
        result = []
        if self.dragging and ((self.release_at is not None and now >= self.release_at)
                              or (self.last_frame_time is not None and now - self.last_frame_time > 1.0)):
            result.append(Action("left_up"))
            self.dragging = False
            self.release_at = None
            self.blocked = True
        if self.pending_tap and now > self.pending_tap[0] + self.settings["double_tap_time"]:
            # Smart zoom owns two-finger taps; a single tap still right-clicks.
            result.append(Action("right_click"))
            self.pending_tap = None
        return result

    def feed(self, frame: Frame) -> list[Action]:
        now, s = frame.time, self.settings
        if (self.last_time is not None and now < self.last_time) or (self.device is not None and frame.device != self.device):
            result = self.cancel()
        else:
            result = self.tick(now)
        self.device, self.last_time, self.last_frame_time = frame.device, now, now
        points = tuple(p for p in frame.contacts if p.tip)
        if (frame.button or any(not p.confidence or not isfinite(p.x) or not isfinite(p.y)
                               or not 0 <= p.x <= 1 or not 0 <= p.y <= 1 for p in points)
                or len({p.id for p in points}) != len(points)):
            result += self.cancel()
            self.blocked = True
            return result
        if not points:
            if self.dragging and self.release_at is None:
                self.release_at = now + s["drag_release_delay"]
            if self.start_time is not None and not self.blocked and not self.fired and not self.dragging:
                if now - self.start_time <= s["tap_max_time"] and self.movement <= s["tap_max_movement"]:
                    if self.peak == 2 and s["smart_zoom"]:
                        pos = centre(tuple(self.origins.values()))
                        if self.pending_tap and hypot(pos[0] - self.pending_tap[1][0], pos[1] - self.pending_tap[1][1]) <= 0.08:
                            # The output side tracks zoom per window and picks zoom in or reset.
                            result.append(Action("smart_zoom"))
                            self.pending_tap = None
                        else:
                            if self.pending_tap:
                                result.append(Action("right_click"))
                            self.pending_tap = (now, pos)
                    elif self.peak == 3 and s["lookup"]:
                        result.append(Action("lookup"))
            self._clear_session()
            return result + self.tick(now)
        if self.blocked:
            return result
        if self.start_time is None:
            self.start_time = now
        current = {p.id: p for p in points}
        # Permit staggered landing, but never turn a replacement/lifted finger
        # into a fresh tap or jump the centroid during a drag.
        if set(current) - set(self.origins) and self.origins and (now - self.start_time > 0.12 or len(current) <= self.peak):
            self.blocked = True
        for p in points:
            self.origins.setdefault(p.id, p)
            origin = self.origins[p.id]
            self.movement = max(self.movement, hypot(p.x - origin.x, p.y - origin.y))
        self.peak = max(self.peak, len(points))
        pos = centre(points)
        if self.pending_tap and (self.movement > s["tap_max_movement"] or self.peak > 2):
            # The next touch is not a second tap, so the first one was a plain
            # two-finger tap: deliver its right-click now instead of dropping it.
            result.append(Action("right_click"))
            self.pending_tap = None
        if self.dragging:
            if len(points) == 3 and not self.blocked:
                if self.release_at is not None:
                    self.release_at = None
                    self.previous = current
                if set(current) == set(self.previous):
                    old = centre(tuple(self.previous.values()))
                    result.append(Action("move", pos[0] - old[0], pos[1] - old[1]))
            elif self.release_at is None:
                self.release_at = now + s["drag_release_delay"]
            self.previous = current
            return result
        if self.blocked or self.fired:
            return result
        age = now - self.start_time
        if len(points) == self.peak == 3 and s["three_finger_drag"]:
            origins = tuple(self.origins[p.id] for p in points)
            origin = centre(origins)
            dx, dy = pos[0] - origin[0], pos[1] - origin[1]
            coherent = all((p.x-o.x)*dx + (p.y-o.y)*dy > 0 for p, o in zip(points, origins))
            if age <= s["drag_start_time"] and hypot(dx, dy) >= s["drag_start_movement"] and coherent:
                self.dragging = self.fired = True
                result += [Action("left_down"), Action("move", dx, dy)]
        elif len(points) == self.peak == 2 and s["notification_center"]:
            origins = tuple(self.origins[p.id] for p in points)
            if (age < 0.8 and all(p.x >= 1-s["edge_width"] for p in origins)
                    and all(o.x-p.x >= s["swipe_distance"] and abs(o.y-p.y) < 0.06 for p, o in zip(points, origins))):
                result.append(Action("notifications"))
                self.fired = True
        elif len(points) == self.peak == 4 and s["launchpad"]:
            if self.initial_radius is None:
                self.initial_radius, self.anchor = radius(points), pos
            if (0.04 < age < 0.8 and self.initial_radius > 0.06
                    and hypot(pos[0]-self.anchor[0], pos[1]-self.anchor[1]) < 0.06):
                ratio = radius(points) / self.initial_radius
                if abs(ratio-1) >= s["pinch_ratio"]:
                    result.append(Action("start" if ratio < 1 else "desktop"))
                    self.fired = True
            if not self.fired and self.four_swipes and self.anchor and age < 0.8:
                dx, dy = pos[0]-self.anchor[0], pos[1]-self.anchor[1]
                ratio = radius(points) / self.initial_radius if self.initial_radius else 1
                if abs(ratio-1) < s["pinch_ratio"] * 0.6 and max(abs(dx), abs(dy)) > s["swipe_distance"]:
                    kind = ("desktop_right" if dx < 0 else "desktop_left") if abs(dx) > abs(dy) * 1.3 else ("task_view" if dy < 0 else "desktop")
                    result.append(Action(kind))
                    self.fired = True
        self.previous = current
        return result
