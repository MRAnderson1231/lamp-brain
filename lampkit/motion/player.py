"""Plays plans and keeps the lamp alive between them.

Every channel follows its target through a critically damped spring with speed and
acceleration limits, so plan switches never jump and the servos are never asked for more
than they can do quietly. Between plans the lamp holds its last pose with a slow breathing
layer (disabled in exam mode and in the static condition).
"""
from __future__ import annotations

import math

from .generator import ALL_CH, Plan


class Spring:
    def __init__(self, omega: float, vmax: float, amax: float, x: float = 0.0):
        self.omega, self.vmax, self.amax = omega, vmax, amax
        self.x, self.v = x, 0.0

    def step(self, target: float, dt: float) -> float:
        a = self.omega * self.omega * (target - self.x) - 2.0 * self.omega * self.v
        a = max(-self.amax, min(self.amax, a))
        self.v = max(-self.vmax, min(self.vmax, self.v + a * dt))
        self.x += self.v * dt
        return self.x


class Player:
    def __init__(self, cfg: dict, start_pose: dict):
        m = cfg["motion"]
        self.m = m
        sp = m["spring"]
        rest = dict(start_pose)
        for k, v in m["light"].items():
            rest.setdefault(k, v)
        rest.setdefault("hop", 0.0)
        rest.setdefault("squash", 0.0)
        self.springs = {c: Spring(sp["omega"].get(c, sp["omega"]["default"]),
                                  sp["vmax"].get(c, sp["vmax"]["default"]),
                                  sp["amax"].get(c, sp["amax"]["default"]), rest.get(c, 0.0)) for c in ALL_CH}
        self.plan: Plan | None = None
        self.start = 0.0
        self.hold = rest
        self.breathing = True

    @property
    def busy(self) -> bool:
        return self.plan is not None

    def play(self, plan: Plan, t: float) -> bool:
        if self.plan is not None and plan.priority < self.plan.priority:
            return False
        self.plan, self.start = plan, t
        return True

    def target(self, t: float) -> dict:
        if self.plan is not None:
            i = int((t - self.start) / self.plan.dt)
            if i < len(self.plan.frames):
                return self.plan.frames[i]
            self.hold = dict(self.plan.frames[-1])
            self.plan = None
        f = dict(self.hold)
        if self.breathing:
            b = self.m["breathe"]
            s = math.sin(2 * math.pi * t / b["period"])
            f["low"] = f.get("low", 0.0) + b["low"] * s
            f["up"] = f.get("up", 0.0) - b["up"] * s
            f["nod"] = f.get("nod", 0.0) - b["nod"] * s
            f["glow"] = f.get("glow", 1.0) * (1.0 + b["glow"] * s)
        return f

    def freeze(self) -> None:
        """Cancel queued motion and residual velocity at the currently commanded pose."""
        self.plan = None
        self.hold = self.pose
        for spring in self.springs.values():
            spring.v = 0.0

    def step(self, t: float, dt: float, freeze_motion: bool = False) -> dict:
        tgt = self.target(t)
        # Substep long/jittery live ticks so the explicit spring stays stable.
        n = max(1, math.ceil(dt / self.m["max_step"]))
        for _ in range(n):
            for c, spring in self.springs.items():
                if freeze_motion and c not in ("glow", "warmth"):
                    spring.v = 0.0
                else:
                    spring.step(tgt.get(c, spring.x), dt / n)
        return self.pose

    @property
    def pose(self) -> dict:
        return {c: s.x for c, s in self.springs.items()}
