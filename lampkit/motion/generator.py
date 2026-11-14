"""Lightweight ELEGNT: pick the movement that maximises F(tau) + gamma * E(tau).

For one intervention we build a few dozen candidate trajectories: the purely functional move
(reach the gaze/light target by a minimum-jerk path), and the same move with expressive
primitives layered on, at a few amplitudes, with or without an anticipatory head-first lead.
Each candidate is scored:

  F = w_reach * reach - w_time * duration - w_effort * effort - w_noise * noise
  E = sum_dim want[dim] * min(1, have[dim]) - w_exaggerate * excess^2 - w_idle * lively * (1 - want[emotion])

gamma is set per state in the profile and multiplied by the personalised `gamma_mult`, so
gamma ~ 0 (focused study, exam) always returns the plain functional move, while comfort or
celebration gets the expressive one. Planning a candidate is a few ms of pure Python.
"""
from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field

from ..types import ATTENTION, EMOTION, INTENTION, Intervention
from .kinematics import CHANNELS, Rig
from .primitives import LIBRARY

EXTRA = ("hop", "squash", "glow", "warmth")
ALL_CH = CHANNELS + EXTRA


@dataclass
class Plan:
    intent: str
    intervention: int
    priority: int
    gamma: float
    primitives: list
    anticipate: bool
    dt: float
    frames: list = field(default_factory=list)      # list[dict channel -> value]
    score: dict = field(default_factory=dict)

    @property
    def duration(self) -> float:
        return len(self.frames) * self.dt

    def summary(self) -> dict:
        return {"intent": self.intent, "intervention": self.intervention, "gamma": round(self.gamma, 3),
                "primitives": self.primitives, "anticipate": self.anticipate,
                "duration": round(self.duration, 2), "score": {k: round(v, 3) for k, v in self.score.items()}}


def min_jerk(u: float) -> float:
    return u * u * u * (10 - 15 * u + 6 * u * u)


class Generator:
    def __init__(self, cfg: dict, rig: Rig):
        self.cfg = cfg
        self.m = cfg["motion"]
        self.intents = cfg["intents"]
        self.rig = rig
        self.dt = 1.0 / self.m["plan_hz"]

    # ---- targets ----------------------------------------------------------------------------
    def target_point(self, name: str, world: dict):
        if name == "user":
            return tuple(world.get("face") or self.m["targets"]["seat_face"])
        if name == "hint":
            return tuple(world.get("hint") or self.m["targets"]["work"])
        if name == "seat":
            return tuple(self.m["targets"]["seat_face"])
        if name in self.m["targets"]:
            return tuple(self.m["targets"][name])
        return None

    def goal_pose(self, iv: Intervention, spec: dict, q0: dict, world: dict) -> dict:
        if spec.get("pose"):
            return self.rig.clamp(dict(self.m["poses"][spec["pose"]], turn=0.0))
        posture = spec.get("posture") or self.m["posture"]
        p = self.target_point(iv.target, world)
        if p is None:
            return dict(q0)
        return self.rig.clamp(self.rig.look_at(p, posture, start=q0))

    def work_pose(self, q0: dict, world: dict) -> dict:
        p = self.target_point("work", world)
        return self.rig.clamp(self.rig.look_at(p, self.m["posture"], start=q0))

    # ---- trajectory building ----------------------------------------------------------------
    def _move(self, frames: list, a: dict, b: dict, anticipate: bool) -> None:
        vmax = self.m["vmax"]
        span = max(abs(b[c] - a[c]) / vmax[c] for c in CHANNELS)
        dur = max(self.m["min_move"], span * 1.875)          # min-jerk peak speed = 1.875 * mean
        n = max(2, int(round(dur / self.dt)))
        lead = self.m["lead"] if anticipate else 0.0
        for i in range(1, n + 1):
            u = i / n
            f = {}
            for c in CHANNELS:
                # head channels lead the body: they run on a compressed clock
                k = (1 + lead) if c in ("nod", "turn") else 1.0
                f[c] = a[c] + (b[c] - a[c]) * min_jerk(min(1.0, u * k))
            frames.append(f)

    def _hold(self, frames: list, q: dict, seconds: float) -> None:
        for _ in range(int(round(seconds / self.dt))):
            frames.append(dict(q))

    def _primitive(self, frames: list, q: dict, name: str, amp: float, speed: float) -> None:
        p = LIBRARY[name]
        dur = p.duration / speed
        n = max(2, int(round(dur / self.dt)))
        keys = p.keys
        for i in range(1, n + 1):
            u = i / n
            j = next(k for k in range(1, len(keys)) if keys[k][0] >= u - 1e-9)
            (u0, k0), (u1, k1) = keys[j - 1], keys[j]
            w = min_jerk((u - u0) / (u1 - u0)) if u1 > u0 else 1.0
            f = dict(q)
            for c in set(k0) | set(k1):
                f[c] = f.get(c, 0.0) + amp * (k0.get(c, 0.0) + (k1.get(c, 0.0) - k0.get(c, 0.0)) * w)
            frames.append(f)

    def _build(self, iv, spec, q0, goal, end, prims, anticipate):
        frames: list[dict] = []
        returns = end is not goal
        # trajectory frames carry joints only; light and squash/hop are offsets added on top
        joints = lambda q: {c: q.get(c, 0.0) for c in CHANNELS}  # noqa: E731
        start, goal, end = joints(q0), joints(goal), joints(end)
        if anticipate:
            self._hold(frames, start, LIBRARY["pause"].duration * 0.5)
        self._move(frames, start, goal, anticipate)
        for name, amp, speed in prims:
            self._primitive(frames, goal, name, amp, speed)
        self._hold(frames, goal, spec.get("hold", self.m["hold"]))
        if returns:
            self._move(frames, goal, end, False)
        light_curve(frames, iv, spec, q0, self.m, self.dt)
        for f in frames:
            for c in CHANNELS:
                f.setdefault(c, 0.0)
        return frames

    # ---- scoring ----------------------------------------------------------------------------
    def _score(self, frames, prims, anticipate, want, gamma, aim_err):
        s = self.m["score"]
        dur = len(frames) * self.dt
        effort, peak = 0.0, 0.0
        for a, b in zip(frames, frames[1:]):
            for c in CHANNELS:
                d = abs(b[c] - a[c])
                effort += d
                peak = max(peak, d / self.dt)
        noise = max(0.0, peak - self.m["v_quiet"]) / self.m["v_quiet"]
        reach = max(0.0, 1.0 - aim_err * 50.0)
        F = s["reach"] * reach - s["time"] * dur - s["effort"] * effort / 100.0 - s["noise"] * noise
        have: dict[str, float] = {}
        excess, lively = 0.0, 0.0
        for name, amp, _ in prims:
            p = LIBRARY[name]
            for dim, w in p.tags.items():
                have[dim] = have.get(dim, 0.0) + w * amp
            excess += max(0.0, amp - 1.0) ** 2
            lively += p.lively * amp
        if anticipate:
            have[INTENTION] = have.get(INTENTION, 0.0) + 0.4
            have[ATTENTION] = have.get(ATTENTION, 0.0) + 0.2
        E = sum(w * min(1.0, have.get(dim, 0.0)) for dim, w in want.items())
        E -= s["exaggerate"] * excess + s["idle"] * lively * (1.0 - want.get(EMOTION, 0.0))
        return {"F": F, "E": E, "total": F + gamma * E, "duration": dur, "peak_speed": peak}

    def candidates(self, spec: dict):
        allowed = [p for p in spec.get("primitives", []) if p in LIBRARY]
        amps = self.m["amps"]
        sets = [[]]
        sets += [[(p, a, 1.0)] for p in allowed for a in amps]
        sets += [[(p, 1.0, 1.0), (q, 1.0, 1.0)] for p, q in itertools.combinations(allowed, 2)]
        for prims in sets:
            for anticipate in (False, True):
                yield prims, anticipate

    def plan(self, iv: Intervention, q0: dict, world: dict, gamma: float) -> Plan:
        spec = self.intents[iv.intent]
        want = iv.express
        q0 = dict(q0)
        for c in CHANNELS:
            q0.setdefault(c, 0.0)
        goal = self.goal_pose(iv, spec, q0, world)
        end = goal
        if spec.get("return", True) and iv.target != "work" and not spec.get("pose"):
            end = self.work_pose(goal, world)
        p = self.target_point(iv.target, world)
        err = 0.0 if p is None or spec.get("pose") else self.rig.aim_error(goal, p)
        best = None
        for prims, anticipate in self.candidates(spec):
            frames = self._build(iv, spec, q0, goal, end, prims, anticipate)
            sc = self._score(frames, prims, anticipate, want, gamma, err)
            if best is None or sc["total"] > best[0]["total"] + 1e-9:
                best = (sc, frames, prims, anticipate)
        sc, frames, prims, anticipate = best
        return Plan(iv.intent, iv.id, spec.get("priority", 1), gamma, [list(x) for x in prims],
                    anticipate, self.dt, frames, sc)


def gamma_for(cfg: dict, iv: Intervention, gamma_mult: float) -> float:
    g = cfg["motion"]["gamma"]
    base = g["by_intent"].get(iv.intent, g["by_state"].get(iv.state, g["default"]))
    return max(0.0, base * gamma_mult)


def light_curve(frames: list, iv: Intervention, spec: dict, q0: dict, m: dict, dt: float) -> None:
    """Ramps from the lamp's current light to the intent's light, then (unless the intent keeps
    it) back to the working light. Primitive light offsets already in the frames ride on top."""
    base = m["light"]
    want = {k: iv.light.get(k, base[k]) for k in ("glow", "warmth")}
    now = {k: q0.get(k, base[k]) for k in ("glow", "warmth")}
    ramp = max(1, int(round(m["light_ramp"] / dt)))
    restore = spec.get("restore_light", True)
    n = len(frames)
    for i, f in enumerate(frames):
        for k in ("glow", "warmth"):
            if i < ramp:
                v = now[k] + (want[k] - now[k]) * min_jerk((i + 1) / ramp)
            elif restore and i >= n - ramp:
                v = want[k] + (base[k] - want[k]) * min_jerk((i - (n - ramp) + 1) / ramp)
            else:
                v = want[k]
            f[k] = v + f.get(k, 0.0)
        f.setdefault("hop", 0.0)
        f.setdefault("squash", 0.0)


def light_only(iv: Intervention, q0: dict, cfg: dict, dt: float) -> Plan:
    """Static-lamp plan: keep the pose, change only the light."""
    m = cfg["motion"]
    n = int(round(max(1.0, cfg["intents"][iv.intent].get("hold", m["hold"])) / dt))
    frames = [{c: q0.get(c, 0.0) for c in CHANNELS} for _ in range(n)]
    light_curve(frames, iv, cfg["intents"][iv.intent], q0, m, dt)
    return Plan(iv.intent, iv.id, cfg["intents"][iv.intent].get("priority", 1), 0.0, [], False, dt, frames,
                {"F": 0.0, "E": 0.0, "total": 0.0})
