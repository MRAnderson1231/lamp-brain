import bpy, math, json
from mathutils import Vector

s = bpy.data.scenes["Margin Luxo"]
rig = s.objects["LampRig"]
pb = rig.pose.bones
spot = s.objects["Lamp_Spot"]
ipad = s.objects["iPad mini"]
HEAD_S = pb["head"].scale[0]
ad = rig.animation_data or rig.animation_data_create()
ad.action = None

# glow 1.0 == normal working light at this scale
def rescale_driver(fc, base):
    fc.driver.expression = "g * %g" % base
for fc in bpy.data.lights["Lamp_Spot"].animation_data.drivers:
    if fc.data_path == "energy": rescale_driver(fc, 20)
for mname, base in (("Lamp_Bulb", 4.0), ("Lamp_Inner", 0.5), ("Lamp_Vent", 1.2)):
    nt = bpy.data.materials[mname].node_tree
    for fc in (nt.animation_data.drivers if nt.animation_data else []):
        if "default_value" in fc.data_path and fc.driver.expression.startswith("g *"):
            rescale_driver(fc, base)

# screen: plain page <-> page with Margin's hint, driven by a keyframed mix
sm = bpy.data.materials["iPad Screen"]
nt = sm.node_tree
bsdf = nt.nodes["Principled BSDF"]
hint_tex = next(n for n in nt.nodes if n.type == "TEX_IMAGE")
plain = nt.nodes.get("Plain") or nt.nodes.new("ShaderNodeTexImage")
plain.name = "Plain"
plain.image = bpy.data.images.load("/tmp/bl/margin_ui_plain.png", check_existing=True)
mix = nt.nodes.get("Hint Mix") or nt.nodes.new("ShaderNodeMix")
mix.name = "Hint Mix"; mix.data_type = "RGBA"
nt.links.new(plain.outputs["Color"], mix.inputs[6])
nt.links.new(hint_tex.outputs["Color"], mix.inputs[7])
nt.links.new(mix.outputs[2], bsdf.inputs["Emission Color"])
mix.inputs[0].default_value = 0.0

CH = {
    "YAW": ("swivel", "rotation_euler", 1), "LOW": ("lower", "rotation_euler", 0),
    "UP": ("upper", "rotation_euler", 0), "NOD": ("head", "rotation_euler", 0),
    "TURN": ("head", "rotation_euler", 2), "HOP": ("root", "location", 1),
    "SQ": ("root", "scale", 1), "GLOW": ("head", "glow", 0), "WARM": ("head", "warmth", 0),
}

def apply(p):
    for bn in pb:
        bn.rotation_euler = (0, 0, 0); bn.location = (0, 0, 0); bn.scale = (1, 1, 1)
    pb["head"].scale = (HEAD_S,) * 3
    pb["swivel"].rotation_euler[1] = math.radians(p[0])
    pb["lower"].rotation_euler[0] = math.radians(p[1])
    pb["upper"].rotation_euler[0] = math.radians(p[2])
    pb["head"].rotation_euler[0] = math.radians(p[3])
    s.view_layers[0].update()

def beam():
    m = spot.matrix_world
    return m.translation.copy(), -(m.to_3x3() @ Vector((0, 0, 1))).normalized()

def solve(target, low, up, yaws=range(-120, 21), nods=range(-50, 81)):
    best = None
    for y in yaws:
        for n in nods:
            apply((y, low, up, n))
            o, d = beam()
            err = d.angle((target - o).normalized())
            if best is None or err < best[0]:
                best = (err, y, n)
    return (best[1], low, up, best[2]), math.degrees(best[0])

page = ipad.matrix_world @ Vector((-0.01, 0.01, 0.0063))
face = Vector((0.36, -0.74, 0.40))          # student sitting in front of the iPad
HOME, e1 = solve(page, 2, 0)
USER, e2 = solve(face, -4, -8)

def head_min_z():
    o = s.objects["Lamp_Head"]
    dg = bpy.context.evaluated_depsgraph_get()
    ev = o.evaluated_get(dg)
    return min((ev.matrix_world @ v.co).z for v in ev.data.vertices)

SLEEP = None
for up in range(34, -1, -2):
    apply((HOME[0] + 10, 6, up, 72))
    if head_min_z() > 0.02:
        SLEEP = (HOME[0] + 10, 6, up, 72); break
print("HOME", HOME, round(e1, 1), "USER", USER, round(e2, 1), "SLEEP", SLEEP)

hy, hl, hu, hn = HOME
uy, ul, uu, un = USER
sy, sl, su, sn = SLEEP
d = 1 if uy > hy else -1
my, mn = (hy + uy) / 2, (hn + un) / 2

CLIPS = {
  "1_phone_pickup": {"len": 140,
    "YAW": [(0, hy), (6, hy), (16, uy - 4 * d), (22, uy), (104, uy), (132, hy), (140, hy)],
    "TURN": [(0, 0), (3, 0), (9, 15 * d), (22, 0), (70, 0), (76, 8), (82, -8), (88, 5), (94, 0), (140, 0)],
    "LOW": [(0, hl), (10, hl), (18, ul + 3), (70, ul + 6), (104, ul + 6), (132, hl), (140, hl)],
    "UP": [(0, hu), (10, hu), (18, uu), (104, uu), (132, hu), (140, hu)],
    "NOD": [(0, hn), (8, hn - 6), (18, un), (70, un - 3), (104, un), (132, hn), (140, hn)],
    "GLOW": [(0, 1), (8, 1), (12, 1.25), (104, 1.2), (132, 1), (140, 1)],
    "WARM": [(0, .75), (8, .75), (14, .15), (104, .15), (132, .75), (140, .75)],
  },
  "2_stuck_hint": {"len": 168, "hint": [(0, 0), (80, 0), (92, 1), (168, 1)],
    "YAW": [(0, hy), (36, hy), (50, my), (62, my), (74, hy), (168, hy)],
    "TURN": [(0, 0), (36, 0), (46, 6 * d), (60, 6 * d), (72, 0), (168, 0)],
    "LOW": [(0, hl), (36, hl + 8), (60, hl + 8), (74, hl + 4), (150, hl + 4), (168, hl)],
    "NOD": [(0, hn), (36, hn + 8), (50, mn), (62, mn), (74, hn + 4), (78, hn + 14), (82, hn + 4),
            (86, hn + 14), (92, hn + 6), (150, hn + 6), (168, hn)],
    "GLOW": [(0, 1), (70, 1), (80, 1.6), (150, 1.4), (168, 1)],
    "WARM": [(0, .75), (80, .88), (168, .75)],
  },
  "3_wrong_answer": {"len": 84,
    "NOD": [(0, hn), (10, hn - 10), (40, hn - 10), (64, hn), (84, hn)],
    "TURN": [(0, 0), (10, 12), (40, 12), (64, 0), (84, 0)],
    "LOW": [(0, hl), (10, hl - 3), (40, hl - 3), (64, hl), (84, hl)],
    "GLOW": [(0, 1), (10, .8), (40, .8), (64, 1), (84, 1)],
    "WARM": [(0, .75), (10, .55), (40, .55), (64, .75), (84, .75)],
  },
  "4_correct": {"len": 72,
    "NOD": [(0, hn), (6, hn - 8), (12, hn + 10), (18, hn - 6), (24, hn + 10), (32, hn - 3), (44, hn), (72, hn)],
    "LOW": [(0, hl), (6, hl - 6), (14, hl), (20, hl - 6), (28, hl), (72, hl)],
    "UP": [(0, hu), (6, hu - 6), (14, hu), (20, hu - 6), (28, hu), (72, hu)],
    "SQ": [(0, 1), (5, 1.06), (12, .95), (18, 1.05), (24, .96), (32, 1), (72, 1)],
    "HOP": [(0, 0), (4, 0, "V"), (9, 0.03), (14, 0, "V"), (72, 0)],
    "GLOW": [(0, 1), (6, 1.8), (20, 1.5), (44, 1.1), (72, 1)],
    "WARM": [(0, .75), (6, .95), (44, .85), (72, .75)],
  },
  "5_fatigue_break": {"len": 192,
    "YAW": [(0, hy), (22, uy), (100, uy), (112, uy + 12), (124, uy - 12), (136, uy + 8), (150, uy), (192, uy)],
    "TURN": [(0, 0), (100, 0), (112, -6), (124, 6), (136, -4), (150, 0), (192, 0)],
    "LOW": [(0, hl), (22, ul), (30, ul + 3), (60, ul - 8), (84, ul - 8), (96, ul + 4), (150, ul + 2), (192, ul)],
    "UP": [(0, hu), (22, uu), (30, uu + 3), (60, uu - 12), (84, uu - 12), (96, uu + 4), (150, uu + 2), (192, uu)],
    "NOD": [(0, hn), (22, un), (30, un + 4), (60, un - 22), (84, un - 24), (96, un + 8), (150, un + 4), (192, un)],
    "SQ": [(0, 1), (30, .97), (60, 1.07), (84, 1.07), (96, .96), (110, 1), (192, 1)],
    "GLOW": [(0, 1), (40, 1), (192, .62)],
    "WARM": [(0, .75), (60, 1.0), (192, 1.0)],
  },
  "6_comfort": {"len": 216,
    "YAW": [(0, hy), (60, uy), (216, uy)],
    "TURN": [(0, 0), (60, 0), (120, 5), (180, -4), (216, 0)],
    "LOW": [(0, hl), (60, ul + 10), (216, ul + 10)],
    "UP": [(0, hu), (60, uu + 10), (216, uu + 10)],
    "NOD": [(0, hn), (60, un + 16), (100, un + 12), (130, un + 20), (160, un + 12), (190, un + 20), (216, un + 16)],
    "GLOW": [(0, 1), (60, .68), (84, .8), (108, .68), (132, .8), (156, .68), (180, .8), (216, .7)],
    "WARM": [(0, .75), (60, 1.0), (216, 1.0)],
  },
  "7_away_sleep": {"len": 156,
    "YAW": [(0, hy), (16, uy), (34, uy), (46, uy + 18 * -d), (60, uy + 10 * d), (72, uy), (120, sy), (156, sy)],
    "TURN": [(0, 0), (34, 0), (42, -10 * d), (56, 8 * d), (70, 0), (156, 0)],
    "LOW": [(0, hl), (16, ul), (72, ul), (116, sl + 2), (126, sl), (156, sl)],
    "UP": [(0, hu), (16, uu), (72, uu), (116, su + 3), (126, su), (156, su)],
    "NOD": [(0, hn), (16, un), (72, un), (112, sn + 6), (124, sn - 2), (156, sn)],
    "SQ": [(0, 1), (96, 1), (108, 1.04), (120, .96), (132, 1), (156, 1)],
    "GLOW": [(0, 1), (72, 1), (104, .45), (136, .05), (156, .05)],
    "WARM": [(0, .75), (156, .95)],
  },
  "8_wake_hello": {"len": 132,
    "YAW": [(0, sy), (14, sy), (30, uy), (70, uy), (110, hy), (132, hy)],
    "LOW": [(0, sl), (14, sl + 2), (28, ul - 4), (34, ul), (70, ul), (110, hl), (132, hl)],
    "UP": [(0, su), (14, su + 2), (28, uu - 4), (34, uu), (70, uu), (110, hu), (132, hu)],
    "NOD": [(0, sn), (14, sn + 4), (28, un - 10), (34, un - 4), (42, un + 10), (48, un - 4), (54, un + 10),
            (62, un), (110, hn), (132, hn)],
    "SQ": [(0, 1), (12, .94), (24, 1.06), (34, 1), (132, 1)],
    "GLOW": [(0, .05), (14, .3), (26, 1.2), (70, 1.2), (110, 1), (132, 1)],
    "WARM": [(0, .95), (26, .8), (110, .75), (132, .75)],
  },
}
BASE = {"YAW": hy, "LOW": hl, "UP": hu, "NOD": hn, "TURN": 0, "HOP": 0, "SQ": 1, "GLOW": 1, "WARM": .75}


def fcurves(act):
    if getattr(act, "layers", None):
        return [fc for l in act.layers for st in l.strips for bag in st.channelbags for fc in bag.fcurves]
    return list(act.fcurves)


def set_ch(ch, v):
    bone, prop, i = CH[ch]
    b = pb[bone]
    if prop in ("glow", "warmth"): b[prop] = float(v)
    elif prop == "rotation_euler": b.rotation_euler[i] = math.radians(-v if ch == "TURN" else v)
    elif prop == "scale":
        b.scale[1] = v; b.scale[0] = b.scale[2] = 1 / math.sqrt(v)
    else: getattr(b, prop)[i] = v


def key_ch(ch, f):
    bone, prop, i = CH[ch]
    b = pb[bone]
    if prop in ("glow", "warmth"): b.keyframe_insert('["%s"]' % prop, frame=f)
    elif prop == "scale": b.keyframe_insert("scale", frame=f)
    else: b.keyframe_insert(prop, index=i, frame=f)


meta = {}
for name, clip in CLIPS.items():
    an = "margin_" + name
    old = bpy.data.actions.get(an)
    if old: bpy.data.actions.remove(old)
    act = bpy.data.actions.new(an); act.use_fake_user = True
    ad.action = act
    apply(HOME)
    n = clip["len"]
    sharp = set()
    for ch in CH:
        keys = clip.get(ch) or [(0, BASE[ch]), (n, BASE[ch])]
        for k in keys:
            set_ch(ch, k[1]); key_ch(ch, k[0])
            if len(k) > 2: sharp.add(k[0])
    for fc in fcurves(act):
        for kp in fc.keyframe_points:
            kp.interpolation = "BEZIER"
            h = "VECTOR" if (fc.data_path.endswith("location") and kp.co[0] in sharp) else "AUTO_CLAMPED"
            kp.handle_left_type = kp.handle_right_type = h
        fc.update()
    meta[name] = {"len": n, "hint": clip.get("hint", [(0, 0), (n, 0)])}
ad.action = None
json.dump(meta, open("/tmp/bl/anim_meta.json", "w"))
print("built", list(meta))
