import json
import math

from lampkit.config import load_profile
from lampkit.motion.generator import Generator
from lampkit.motion.kinematics import RIG_FILE, Rig
from lampkit.types import Intervention

REST = {"yaw": 0.0, "low": 0.0, "up": 0.0, "nod": 0.0, "turn": 0.0}


def test_rest_pose_matches_blender_spot_light():
    rig = Rig(scale=1.0, head_scale=1.0)
    pos, d = rig.beam(REST)
    spot = json.loads(RIG_FILE.read_text())["spot"]
    assert max(abs(a - b) for a, b in zip(pos, spot["pos"])) < 1e-3
    assert max(abs(a - b) for a, b in zip(d, spot["dir"])) < 1e-3


def test_look_at_hits_desk_targets():
    cfg = load_profile("sim")
    k = cfg["kinematics"]
    rig = Rig(k["scale"], k["head_scale"], limits={c: tuple(v) for c, v in k["limits"].items()})
    for target in ([0.33, -0.235, 0.0063], [0.36, -0.74, 0.40], [0.42, -0.20, 0.0063], [0.25, -0.30, 0.0063]):
        q = rig.look_at(target, {"low": 2, "up": 0})
        assert math.degrees(rig.aim_error(q, target)) < 2.0, (target, q)


def test_generator_prefers_function_when_gamma_is_zero():
    cfg = load_profile("sim")
    k = cfg["kinematics"]
    gen = Generator(cfg, Rig(k["scale"], k["head_scale"], limits={c: tuple(v) for c, v in k["limits"].items()}))
    iv = Intervention(id=1, t=0.0, intent="glance_hint", state="confused", level=0, target="hint",
                      express=cfg["intents"]["glance_hint"]["express"], light={}, motion=True, app=None, reason="")
    start = dict(cfg["motion"]["poses"]["relax"], turn=0.0, glow=1.0, warmth=0.75)
    world = {"face": None, "hint": [0.36, -0.22, 0.0063]}
    flat = gen.plan(iv, start, world, gamma=0.0)
    lively = gen.plan(iv, start, world, gamma=1.0)
    assert flat.primitives == []
    assert lively.primitives
    assert lively.score["E"] > flat.score["E"]
