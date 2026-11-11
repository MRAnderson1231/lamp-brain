"""Author the lamp's animation clips as Blender Actions (run inside Blender).

Each clip is a table of keyframes on a handful of named channels. Angles are
in degrees, relative to the neutral standing pose. A key is (frame, value) or
(frame, value, "V") for a sharp key (ground contacts, snaps). Re-run after
editing to rebuild every `lamp_*` action, then re-run lamp_controller.py.
"""
import math
import bpy

ARM = bpy.data.objects["LampRig"]
FPS = 24

# ---- channels: (bone, property, index) -------------------------------------
YAW = ("swivel", "rotation_euler", 1)   # whole lamp turns (+ = away from camera)
LOW = ("lower", "rotation_euler", 0)    # lower arm, + = lean forward
UP = ("upper", "rotation_euler", 0)     # upper arm, + = fold forward
NOD = ("head", "rotation_euler", 0)     # head pitch, + = look down
TURN = ("head", "rotation_euler", 2)    # head turns on its own, same sense as YAW
HOP = ("root", "location", 1)           # height above the table (metres)
SQ_UP = ("root", "scale", 1)            # squash & stretch, vertical
SQ_A = ("root", "scale", 0)             # squash & stretch, sideways
SQ_B = ("root", "scale", 2)
GLOW = ("head", "glow", 0)              # bulb brightness multiplier
WARM = ("head", "warmth", 0)            # 0 = cold blue, 1 = warm

DEFAULTS = {SQ_UP: 1.0, SQ_A: 1.0, SQ_B: 1.0, GLOW: 1.0, WARM: 1.0}
SIGN = {TURN: -1.0}                     # the head's turn axis points down
ALL = [YAW, LOW, UP, NOD, TURN, HOP, SQ_UP, SQ_A, SQ_B, GLOW, WARM]


def rep(keys, period, n):
    """Repeat a one-period key list n times (last key of each period dropped)."""
    out = []
    for i in range(n):
        out += [(k[0] + i * period,) + tuple(k[1:]) for k in keys[:-1]]
    out.append((n * period,) + tuple(keys[-1][1:]))
    return out


def mirror(keys):
    return [(k[0], -k[1]) + tuple(k[2:]) for k in keys]


def arc(f0, f1, height):
    """Ballistic hop: sharp take-off and landing, parabola in between."""
    keys = [(f0, 0.0, "V")]
    for f in range(f0 + 1, f1):
        u = (f - f0) / (f1 - f0)
        keys.append((f, height * 4 * u * (1 - u)))
    keys.append((f1, 0.0, "V"))
    return keys


def wide(keys):
    """Sideways squash that preserves volume for a vertical squash track."""
    return [(k[0], 1.0 / math.sqrt(k[1])) + tuple(k[2:]) for k in keys]


# head leads the turn, body follows and overshoots, head settles, blink, return
_look_turn = [(0, 0), (5, -4), (16, 24), (34, 8), (62, 9), (74, -7), (100, 0)]
_look_yaw = [(0, 0), (10, -4), (30, 32), (38, 27), (64, 28), (92, -2), (100, 0)]
_look = {
    NOD: [(0, 0), (16, 5), (32, -6), (64, -6), (82, 4), (100, 0)],
    LOW: [(0, 0), (8, 3), (30, -5), (64, -4), (100, 0)],
    GLOW: [(0, 1), (44, 1), (46, 0.2), (49, 1), (100, 1)],
}

_laugh_sq = [(0, 0.88), (3, 1.12), (8, 1.0), (12, 1.07), (14, 0.86), (16, 0.88)]
_happy_sq = [(0, 0.95), (6, 1.04), (12, 0.99), (24, 0.95), (30, 1.04), (36, 0.99), (48, 0.95)]

CLIPS = {
    # ---------------- idle ----------------
    "lamp_idle_breathe": {   # slow breath with one blink
        LOW: [(0, 0), (36, -2.5), (72, 0)],
        UP: [(0, 0), (36, 4), (72, 0)],
        NOD: [(0, 0), (40, -2.5), (72, 0)],
        GLOW: [(0, 1.0), (36, 1.08), (52, 1.03), (54, 0.25), (57, 1.0), (72, 1.0)],
    },
    "lamp_idle_look_left": {
        **_look, YAW: _look_yaw, TURN: _look_turn,
    },
    "lamp_idle_look_right": {
        **_look, YAW: mirror(_look_yaw), TURN: mirror(_look_turn),
    },
    "lamp_idle_curious": {   # head dips first, body leans in, glance both ways, blink
        NOD: [(0, 0), (18, 24), (26, 20), (78, 21), (104, -3), (110, 0)],
        LOW: [(0, 0), (6, -3), (26, 15), (78, 14), (100, 0), (110, 0)],
        UP: [(0, 0), (6, -2), (28, 13), (78, 12), (102, 0), (110, 0)],
        TURN: [(0, 0), (32, 0), (42, 17), (46, 14), (58, -15), (62, -12), (76, 0), (110, 0)],
        GLOW: [(0, 1), (48, 1), (50, 0.25), (53, 1), (110, 1)],
    },
    "lamp_idle_hello": {     # turn to the viewer head-first, nod twice, return
        TURN: [(0, 0), (5, 3), (14, -18), (30, -4), (64, -4), (72, 10), (96, 0)],
        YAW: [(0, 0), (8, 3), (28, -48), (34, -44), (66, -44), (92, 1), (96, 0)],
        NOD: [(0, 0), (30, -8), (37, 10), (44, -8), (51, 10), (58, -5), (66, -5), (96, 0)],
        SQ_UP: [(0, 1), (30, 1), (37, 0.96), (44, 1.02), (51, 0.96), (58, 1), (96, 1)],
        GLOW: [(0, 1.0), (28, 1.35), (66, 1.35), (96, 1.0)],
    },
    # ---------------- emotions ----------------
    "lamp_happy": {          # bouncy sway, head dragging behind the body
        YAW: [(0, 0), (12, 14), (24, 0), (36, -14), (48, 0)],
        TURN: [(0, -4), (4, 0), (16, 8), (28, 0), (40, -8), (48, -4)],
        LOW: [(0, -4), (6, -10), (24, -4), (30, -10), (48, -4)],
        UP: [(0, -4), (6, -10), (24, -4), (30, -10), (48, -4)],
        NOD: [(0, 0), (8, -10), (24, 0), (32, -10), (48, 0)],
        SQ_UP: _happy_sq, SQ_A: wide(_happy_sq), SQ_B: wide(_happy_sq),
        GLOW: [(0, 1.3), (6, 1.55), (24, 1.3), (30, 1.55), (48, 1.3)],
    },
    "lamp_laugh": {          # two ballistic hops, head whipping after the body
        HOP: [(0, 0.0)] + arc(3, 13, 0.20) + [(16, 0.0)] + arc(19, 29, 0.20) + [(32, 0.0)],
        SQ_UP: rep(_laugh_sq, 16, 2),
        SQ_A: rep(wide(_laugh_sq), 16, 2),
        SQ_B: rep(wide(_laugh_sq), 16, 2),
        LOW: rep([(0, 7), (3, -8), (8, -4), (13, -2), (15, 8), (16, 7)], 16, 2),
        UP: rep([(0, 10), (3, -12), (8, -6), (13, -3), (15, 11), (16, 10)], 16, 2),
        NOD: rep([(0, 6), (3, 2), (6, -14), (10, -8), (13, -4), (15, 9), (16, 6)], 16, 2),
        YAW: [(0, -10), (8, 0), (16, 10), (24, 0), (32, -10)],
        TURN: [(0, -4), (4, -8), (12, 4), (20, 8), (28, -4), (32, -4)],
        GLOW: rep([(0, 1.4), (8, 1.9), (16, 1.4)], 16, 2),
    },
    "lamp_sad": {            # sigh: lift a little, slump deeper, slow head shake
        LOW: [(0, 10), (40, 6), (66, 12), (144, 10)],
        UP: [(0, 16), (40, 10), (66, 20), (144, 16)],
        NOD: [(0, 34), (42, 27), (74, 39), (144, 34)],
        YAW: [(0, 0), (80, 0), (96, 5), (112, -5), (128, 3), (144, 0)],
        TURN: [(0, 0), (84, 0), (100, 4), (116, -4), (132, 2), (144, 0)],
        GLOW: [(0, 0.35), (40, 0.45), (70, 0.25), (144, 0.35)],
        WARM: [(0, 0.0), (144, 0.0)],
    },
    "lamp_surprised": {      # one-shot: dip, snap back with overshoot, settle
        LOW: [(0, 0), (3, 7), (6, -18), (10, -11), (14, -13), (36, -12), (56, 0)],
        UP: [(0, 0), (3, 9), (6, -16), (10, -9), (14, -11), (36, -10), (56, 0)],
        NOD: [(0, 0), (3, 6), (8, -18), (12, -5), (16, -9), (36, -8), (56, 0)],
        HOP: [(0, 0.0)] + arc(3, 9, 0.055) + [(56, 0.0)],
        SQ_UP: [(0, 1), (3, 0.9), (6, 1.1), (9, 0.92), (13, 1.03), (17, 1), (56, 1)],
        GLOW: [(0, 1.0), (3, 0.9), (6, 2.3), (12, 1.9), (36, 1.8), (56, 1.0)],
    },
}


def _path(ch):
    if ch[1] in ("glow", "warmth"):
        return 'pose.bones["%s"]["%s"]' % (ch[0], ch[1]), 0
    return 'pose.bones["%s"].%s' % (ch[0], ch[1]), ch[2]


def _set(ch, value):
    pb = ARM.pose.bones[ch[0]]
    if ch[1] in ("glow", "warmth"):
        pb[ch[1]] = float(value)
    else:
        getattr(pb, ch[1])[ch[2]] = value


def _key(ch, frame):
    pb = ARM.pose.bones[ch[0]]
    if ch[1] in ("glow", "warmth"):
        pb.keyframe_insert('["%s"]' % ch[1], frame=frame)
    else:
        pb.keyframe_insert(ch[1], index=ch[2], frame=frame)


def action_fcurves(action):
    """F-curves of an action, for both layered (4.4+) and legacy actions."""
    if getattr(action, "layers", None):
        out = []
        for layer in action.layers:
            for strip in layer.strips:
                for bag in strip.channelbags:
                    out.extend(bag.fcurves)
        return out
    return list(action.fcurves)


def setup_props_and_drivers():
    head = ARM.pose.bones["head"]
    for name, hi in (("glow", 3.0), ("warmth", 1.0)):
        if name not in head:
            head[name] = 1.0
        head.id_properties_ui(name).update(min=0.0, max=hi)

    def drive(owner, path, index, expr):
        try:
            owner.driver_remove(path, index)
        except Exception:
            pass
        fc = owner.driver_add(path, index) if index >= 0 else owner.driver_add(path)
        d = fc.driver
        d.type = 'SCRIPTED'
        for vname, prop in (("g", "glow"), ("w", "warmth")):
            v = d.variables.new()
            v.name = vname
            v.type = 'SINGLE_PROP'
            v.targets[0].id = ARM
            v.targets[0].data_path = 'pose.bones["head"]["%s"]' % prop
        d.expression = expr

    color = ("0.50 + 0.50*w", "0.66 + 0.06*w", "1.0 - 0.62*w")
    spot = bpy.data.lights["Lamp_Spot"]
    drive(spot, "energy", -1, "g * 50")
    for i, e in enumerate(color):
        drive(spot, "color", i, e)
    for mat_name, strength in (("Lamp_Bulb", 10.0), ("Lamp_Inner", 1.2), ("Lamp_Vent", 3.0)):
        nt = bpy.data.materials[mat_name].node_tree
        bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
        drive(bsdf.inputs["Emission Strength"], "default_value", -1, "g * %s" % strength)
        for i, e in enumerate(color):
            drive(bsdf.inputs["Emission Color"], "default_value", i, e)


def build_clips():
    if ARM.animation_data is None:
        ARM.animation_data_create()
    for name, table in CLIPS.items():
        old = bpy.data.actions.get(name)
        if old:
            bpy.data.actions.remove(old)
        act = bpy.data.actions.new(name)
        act.use_fake_user = True
        ARM.animation_data.action = act
        last = max(k[0] for keys in table.values() for k in keys)
        sharp = set()
        for ch in ALL:
            keys = table.get(ch)
            if keys is None:
                d = DEFAULTS.get(ch, 0.0)
                keys = [(0, d), (last, d)]
            for k in keys:
                v = k[1] * SIGN.get(ch, 1.0)
                _set(ch, math.radians(v) if ch[1] == "rotation_euler" else v)
                _key(ch, k[0])
                if len(k) > 2:
                    sharp.add(_path(ch) + (float(k[0]),))
        for fc in action_fcurves(act):
            for kp in fc.keyframe_points:
                kp.interpolation = 'BEZIER'
                h = 'VECTOR' if (fc.data_path, fc.array_index, kp.co[0]) in sharp else 'AUTO_CLAMPED'
                kp.handle_left_type = h
                kp.handle_right_type = h
            fc.update()
        print("%-24s %3d frames" % (name, last))
    ARM.animation_data.action = None
    for ch in ALL:
        _set(ch, DEFAULTS.get(ch, 0.0))
    ARM.update_tag()


setup_props_and_drivers()
build_clips()
