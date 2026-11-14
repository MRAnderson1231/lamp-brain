"""Expressive movement primitives (ELEGNT section 3.2.3: kinesics and proxemics).

A primitive is a short offset curve added on top of the functional pose, plus tags saying
which of ELEGNT's four expressive dimensions it communicates and how strongly. Offsets are in
degrees (channels yaw/low/up/nod/turn), metres (hop), or ratios (squash, glow, warmth).
`keys` are (time fraction, {channel: offset}); amplitude scales offsets, speed scales time.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..types import ATTENTION, ATTITUDE, EMOTION, INTENTION


@dataclass(frozen=True)
class Primitive:
    name: str
    duration: float
    keys: tuple[tuple[float, dict], ...]
    tags: dict = field(default_factory=dict)
    lively: float = 0.0          # how much it reads as "moving for its own sake"


P = Primitive
LIBRARY: dict[str, Primitive] = {p.name: p for p in [
    # kinesics: spatial
    P("nod", 0.8, ((0, {}), (.3, {"nod": 10}), (.6, {"nod": -3}), (1, {})),
      {ATTITUDE: .6, ATTENTION: .2}),
    P("double_nod", 1.1, ((0, {}), (.18, {"nod": -6}), (.32, {"nod": 10}), (.5, {"nod": -5}), (.66, {"nod": 10}), (.85, {"nod": -2}), (1, {})),
      {ATTITUDE: .7, EMOTION: .5}, .3),
    P("shake", 1.0, ((0, {}), (.2, {"turn": 8}), (.45, {"turn": -8}), (.7, {"turn": 5}), (1, {})),
      {ATTITUDE: .8}),
    P("tilt", 1.6, ((0, {}), (.2, {"turn": 12, "nod": -8}), (.7, {"turn": 12, "nod": -8}), (1, {})),
      {ATTITUDE: .5, ATTENTION: .4}),
    P("lean_in", 1.6, ((0, {}), (.35, {"low": 8, "nod": 8}), (.8, {"low": 8, "nod": 8}), (1, {"low": 4, "nod": 4})),
      {ATTENTION: .8, INTENTION: .3}),
    P("stretch", 2.6, ((0, {}), (.12, {"low": 3, "up": 3, "nod": 4}), (.45, {"low": -8, "up": -12, "nod": -22, "squash": .07}),
                       (.7, {"low": -8, "up": -12, "nod": -24, "squash": .07}), (.82, {"low": 4, "up": 4, "nod": 8, "squash": -.04}), (1, {})),
      {EMOTION: .6, INTENTION: .5}, .4),
    P("sway", 2.0, ((0, {}), (.25, {"yaw": 12, "turn": -6}), (.5, {"yaw": -12, "turn": 6}), (.75, {"yaw": 8, "turn": -4}), (1, {})),
      {EMOTION: .5}, .6),
    P("droop", 2.4, ((0, {}), (.6, {"low": 10, "up": 10, "nod": 16, "glow": -.25}), (1, {"low": 10, "up": 10, "nod": 16, "glow": -.25})),
      {EMOTION: .7}),
    P("soft_nods", 3.0, ((0, {}), (.2, {"nod": 4}), (.4, {"nod": -2}), (.65, {"nod": 4}), (.85, {"nod": -2}), (1, {})),
      {EMOTION: .5, ATTENTION: .4}),
    P("bounce", 0.6, ((0, {}), (.15, {"squash": -.05}), (.4, {"hop": .03, "squash": .05}), (.7, {"squash": -.04}), (1, {})),
      {EMOTION: .7}, .5),
    P("search", 2.4, ((0, {}), (.3, {"yaw": 18, "turn": -10}), (.65, {"yaw": -12, "turn": 8}), (1, {})),
      {ATTENTION: .6, INTENTION: .4}, .3),
    # kinesics: temporal, used as a lead-in
    P("pause", 0.5, ((0, {}), (1, {})), {ATTITUDE: .2}),
    # light accents
    P("brighten", 0.9, ((0, {}), (.25, {"glow": .6}), (1, {})), {EMOTION: .4, ATTENTION: .2}),
    P("focus_light", 1.2, ((0, {}), (.4, {"glow": .5}), (1, {"glow": .4})), {INTENTION: .5, ATTENTION: .5}),
    P("breathe_light", 3.0, ((0, {}), (.5, {"glow": .12}), (1, {})), {EMOTION: .3}),
]}
