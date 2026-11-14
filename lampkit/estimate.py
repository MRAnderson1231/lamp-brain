"""Observations -> features -> evidence for each study state.

Features are smoothed, normalised signals in 0..1 (plus a few signed ones). Evidence for a
state is a clipped weighted sum of features; the weights live in the profile under
`estimate.weights`, so tuning never needs a code change. `evidence()` also returns the
top contributions, which the state machine logs as the reason for every transition.
"""
from __future__ import annotations

import math
from collections import deque

from .types import (APP_BREAK, APP_EXAM, APP_PENCIL, APP_SESSION, APP_STUCK, OBS_FACE,
                    OBS_PHONE, OBS_POSE, OBS_VLM, PHONE, Event)


def clip01(x: float) -> float:
    return 0.0 if x < 0 else 1.0 if x > 1 else x


class Ema:
    """Exponential moving average with a time constant, robust to irregular sampling."""

    def __init__(self, tau: float, value: float = 0.0):
        self.tau, self.value, self.t = tau, value, None

    def update(self, t: float, x: float) -> float:
        if self.t is None:
            self.value = x
        else:
            a = 1.0 - math.exp(-max(0.0, t - self.t) / self.tau)
            self.value += a * (x - self.value)
        self.t = t
        return self.value


class Estimator:
    def __init__(self, cfg: dict):
        c = cfg["estimate"]
        self.cfg = c
        self.weights: dict[str, dict[str, float]] = c["weights"]
        tau = c["tau"]
        self.brow = Ema(tau["face"])
        self.squint = Ema(tau["face"])
        self.frown = Ema(tau["face"])
        self.smile = Ema(tau["face"])
        self.off_task = Ema(tau["off_task"])
        self.slouch = Ema(tau["posture"])
        self.hand_on_head = Ema(tau["posture"])
        self.in_hand = Ema(tau["phone"])
        self.closed: deque[tuple[float, bool]] = deque()
        self.yawns: deque[float] = deque()
        self.erases: deque[tuple[float, int]] = deque()
        self.jaw_open_since: float | None = None
        self.vlm: dict[str, float] = {}
        self.vlm_t = -1e9
        self.face_t = -1e9
        self.face_present = False
        self.face_pos: list[float] | None = None
        self.docked = True
        self.last_stroke = None
        self.stuck_conf = 0.0
        self.stuck_since: float | None = None
        self.stuck_region: list[float] | None = None
        self.session_start: float | None = None
        self.session_offset_min = 0.0
        self.exam = False
        self.on_break = False

    # ---- inputs ------------------------------------------------------------------------------
    def observe(self, ev: Event) -> None:
        t, d = ev.t, ev.data
        if ev.kind == OBS_FACE:
            self.face_t = t
            self.face_present = bool(d.get("present", True))
            if not self.face_present:
                self.off_task.update(t, 1.0)
                return
            if "x" in d:
                self.face_pos = [d["x"], d["y"], d["z"]]
            b = d.get("blend", {})
            self.brow.update(t, b.get("browDown", 0.0))
            self.squint.update(t, b.get("eyeSquint", 0.0))
            self.frown.update(t, b.get("mouthFrown", 0.0))
            self.smile.update(t, b.get("mouthSmile", 0.0))
            away = abs(d.get("yaw", 0.0)) > self.cfg["off_task_yaw"] or d.get("pitch", 20.0) < self.cfg["off_task_pitch"]
            self.off_task.update(t, 1.0 if away else 0.0)
            self.closed.append((t, b.get("eyeBlink", 0.0) > 0.5))
            if b.get("jawOpen", 0.0) > self.cfg["yawn_jaw"]:
                if self.jaw_open_since is None:
                    self.jaw_open_since = t
                elif t - self.jaw_open_since >= self.cfg["yawn_seconds"] and (not self.yawns or self.yawns[-1] < self.jaw_open_since):
                    self.yawns.append(t)
            else:
                self.jaw_open_since = None
        elif ev.kind == OBS_POSE:
            self.slouch.update(t, d.get("slouch", 0.0))
            self.hand_on_head.update(t, 1.0 if d.get("hand_on_head") else 0.0)
        elif ev.kind == OBS_PHONE:
            if "docked" in d:
                self.docked = bool(d["docked"])
            self.in_hand.update(t, d.get("in_hand", 0.0))
        elif ev.kind == OBS_VLM:
            self.vlm = dict(d.get("probs", {}))
            self.vlm_t = t
        elif ev.kind == APP_PENCIL:
            if d.get("strokes", 0) > 0:
                self.last_stroke = t
                # writing again clears a stuck signal
                self.stuck_conf *= self.cfg["stuck_clear_on_write"]
                if self.stuck_conf < 0.1:
                    self.stuck_since = None
            if d.get("erases", 0) > 0:
                self.erases.append((t, int(d["erases"])))
        elif ev.kind == APP_STUCK:
            self.stuck_conf = float(d.get("conf", 0.8))
            self.stuck_region = d.get("region")
            if self.stuck_since is None:
                self.stuck_since = t
        elif ev.kind == APP_SESSION:
            if d.get("active", True):
                self.session_start = t
                self.session_offset_min = float(d.get("elapsed_min", 0.0))
            else:
                self.session_start = None
        elif ev.kind == APP_EXAM:
            self.exam = bool(d.get("active", True))
        elif ev.kind == APP_BREAK:
            self.on_break = bool(d.get("active", True))
            if not self.on_break:
                # a real break resets tiredness: forget old eye closures and yawns, restart the clock
                self.closed.clear()
                self.yawns.clear()
                if self.session_start is not None:
                    self.session_start, self.session_offset_min = t, 0.0

    # ---- outputs -----------------------------------------------------------------------------
    def present(self, t: float) -> bool:
        return self.face_present and (t - self.face_t) < self.cfg["face_timeout"]

    def features(self, t: float) -> dict[str, float]:
        c = self.cfg
        while self.closed and self.closed[0][0] < t - c["perclos_window"]:
            self.closed.popleft()
        while self.yawns and self.yawns[0] < t - c["yawn_window"]:
            self.yawns.popleft()
        while self.erases and self.erases[0][0] < t - c["erase_window"]:
            self.erases.popleft()
        perclos = sum(1 for _, x in self.closed if x) / len(self.closed) if self.closed else 0.0
        vlm_fresh = (t - self.vlm_t) < c["vlm_stale"]
        v = self.vlm if vlm_fresh else {}
        stuck_age = (t - self.stuck_since) if self.stuck_since is not None else 0.0
        idle = (t - self.last_stroke) if self.last_stroke is not None else 0.0
        study_min = ((t - self.session_start) / 60.0 + self.session_offset_min) if self.session_start is not None else 0.0
        present = self.present(t)
        return {
            "present": 1.0 if present else 0.0,
            "stuck": self.stuck_conf,
            "stuck_age": clip01(stuck_age / c["stuck_age_full"]),
            "idle": clip01(idle / c["idle_full"]),
            "erase_rate": clip01(sum(n for _, n in self.erases) / c["erase_full"]),
            "brow": clip01(self.brow.value),
            "squint": clip01(self.squint.value),
            "frown": clip01(self.frown.value),
            "smile": clip01(self.smile.value),
            "off_task": clip01(self.off_task.value) if present else 1.0,
            "slouch": clip01(self.slouch.value),
            "hand_on_head": clip01(self.hand_on_head.value),
            "perclos": clip01(perclos / c["perclos_full"]),
            "yawns": clip01(len(self.yawns) / c["yawn_full"]),
            "study_time": clip01(study_min / c["study_full_min"]),
            "phone": max(0.0 if self.docked else 1.0, clip01(self.in_hand.value)),
            "vlm_engaged": v.get("engaged", 0.0),
            "vlm_confused": v.get("confused", 0.0),
            "vlm_frustrated": v.get("frustrated", 0.0),
            "vlm_bored": v.get("bored", 0.0),
            "vlm_tired": v.get("tired", 0.0),
            "vlm_sad": v.get("sad", 0.0),
        }

    def evidence(self, t: float) -> tuple[dict[str, float], dict[str, list[tuple[str, float]]], dict[str, float]]:
        f = self.features(t)
        ev, why = {}, {}
        for state, w in self.weights.items():
            if not f["present"] and state != PHONE:
                # an empty seat is the context machine's business, not a study state
                ev[state], why[state] = 0.0, []
                continue
            parts = [(k, wk * f.get(k, 0.0)) for k, wk in w.items()]
            ev[state] = clip01(sum(p for _, p in parts))
            why[state] = sorted([p for p in parts if p[1] > 0.01], key=lambda p: -p[1])[:3]
        return ev, why, f
