"""Forward and inverse kinematics of the lamp, using the bone frames exported from lamp.blend.

Each channel rotates its bone about one of the bone's own rest axes, pivoting at the bone's
head, exactly like Blender's pose bones (Euler XYZ). Angles are degrees. World space is the
desk scene: lamp base at the origin, z up, scaled by `scale`; the head bone may be scaled
by `head_scale` around its pivot (variant B: shade ~15.5 cm).
"""
from __future__ import annotations

import json
import math
from pathlib import Path

Vec = tuple[float, float, float]
Mat = tuple[Vec, Vec, Vec]          # rows

RIG_FILE = Path(__file__).resolve().parent / "rig.json"
CHANNELS = ("yaw", "low", "up", "nod", "turn")


def v_add(a, b): return (a[0] + b[0], a[1] + b[1], a[2] + b[2])
def v_sub(a, b): return (a[0] - b[0], a[1] - b[1], a[2] - b[2])
def v_scale(a, s): return (a[0] * s, a[1] * s, a[2] * s)
def v_dot(a, b): return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
def v_len(a): return math.sqrt(v_dot(a, a))
def v_norm(a):
    n = v_len(a)
    return (a[0] / n, a[1] / n, a[2] / n) if n > 1e-12 else (0.0, 0.0, 0.0)


def m_mul(a: Mat, b: Mat) -> Mat:
    return tuple(tuple(sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)) for i in range(3))  # type: ignore


def m_vec(a: Mat, v: Vec) -> Vec:
    return (v_dot(a[0], v), v_dot(a[1], v), v_dot(a[2], v))


def m_t(a: Mat) -> Mat:
    return tuple(tuple(a[j][i] for j in range(3)) for i in range(3))  # type: ignore


def rot_axis(axis: int, deg: float) -> Mat:
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    if axis == 0:
        return ((1, 0, 0), (0, c, -s), (0, s, c))
    if axis == 1:
        return ((c, 0, s), (0, 1, 0), (-s, 0, c))
    return ((c, -s, 0), (s, c, 0), (0, 0, 1))


IDENT: Mat = ((1, 0, 0), (0, 1, 0), (0, 0, 1))


class Rig:
    def __init__(self, scale: float = 1.0, head_scale: float = 1.0, rig_file: Path = RIG_FILE, limits: dict | None = None):
        data = json.loads(Path(rig_file).read_text())
        self.chain = data["chain"]
        self.bones = data["bones"]
        self.channels = data["channels"]
        self.spot = data["spot"]
        self.scale = scale
        self.head_scale = head_scale
        self.limits = limits or {}
        # rest frame of every bone: columns are the bone's local axes in armature space
        self.rest = {n: m_t(tuple(tuple(c) for c in b["axes"])) for n, b in self.bones.items()}

    def clamp(self, q: dict) -> dict:
        out = dict(q)
        for ch, (lo, hi) in self.limits.items():
            if ch in out:
                out[ch] = min(hi, max(lo, out[ch]))
        return out

    def _local_rot(self, bone: str, q: dict) -> Mat:
        """Rotation of `bone` in its own frame, Blender Euler XYZ (R = Rz Ry Rx)."""
        ang = [0.0, 0.0, 0.0]
        for ch, spec in self.channels.items():
            if spec["bone"] == bone:
                ang[spec["axis"]] += spec["sign"] * q.get(ch, 0.0)
        r = IDENT
        for axis in (0, 1, 2):
            if ang[axis]:
                r = m_mul(rot_axis(axis, ang[axis]), r)
        return r

    def bone_transforms(self, q: dict) -> dict[str, tuple[Mat, Vec]]:
        """(R, t) per bone so that posed point = R @ rest_point + t, in armature space."""
        out: dict[str, tuple[Mat, Vec]] = {}
        for name in self.chain:
            b = self.bones[name]
            a = self.rest[name]
            local = m_mul(m_mul(a, self._local_rot(name, q)), m_t(a))
            if name == "head" and self.head_scale != 1.0:
                local = tuple(tuple(x * self.head_scale for x in row) for row in local)  # type: ignore
            pivot = tuple(b["head"])
            t_local = v_sub(pivot, m_vec(local, pivot))
            if b["parent"]:
                pr, pt = out[b["parent"]]
                r = m_mul(pr, local)
                t = v_add(m_vec(pr, t_local), pt)
            else:
                r, t = local, t_local
            out[name] = (r, t)
        return out

    def beam(self, q: dict) -> tuple[Vec, Vec]:
        """World position and direction of the light (and the camera next to it)."""
        r, t = self.bone_transforms(q)[self.spot["bone"]]
        pos = v_add(m_vec(r, tuple(self.spot["pos"])), t)
        d = v_norm(m_vec(r, tuple(self.spot["dir"])))
        return v_scale(pos, self.scale), d

    def aim_error(self, q: dict, target: Vec) -> float:
        pos, d = self.beam(q)
        return 1.0 - v_dot(d, v_norm(v_sub(target, pos)))

    def look_at(self, target: Vec, posture: dict, start: dict | None = None) -> dict:
        """Solve yaw and nod so the beam points at `target`, with `low`/`up` given by posture."""
        q = {"yaw": 0.0, "nod": 0.0, "turn": 0.0, "low": posture.get("low", 0.0), "up": posture.get("up", 0.0)}
        if start:
            q["yaw"], q["nod"] = start.get("yaw", 0.0), start.get("nod", 0.0)
        else:
            q["yaw"] = math.degrees(math.atan2(target[1], target[0])) if (target[0] or target[1]) else 0.0
        best = self.aim_error(q, target)
        step = 16.0
        while step > 0.05:
            moved = False
            for ch in ("yaw", "nod"):
                for s in (step, -step):
                    cand = dict(q)
                    cand[ch] += s
                    cand = self.clamp(cand)
                    e = self.aim_error(cand, target)
                    if e < best - 1e-12:
                        q, best, moved = cand, e, True
            if not moved:
                step *= 0.5
        return q
