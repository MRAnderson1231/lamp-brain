import bpy, bmesh, math
from mathutils import Vector, Matrix, Quaternion

s = bpy.data.scenes["Margin Luxo"]
bpy.context.window_manager.windows[0].scene = s
rig = s.objects["LampRig"]
pb = rig.pose.bones
for o in [o for o in s.objects if o.name.startswith(("iPad", "Pencil", "Desk Cam", "Close Cam", "Lamp Scale"))]:
    bpy.data.objects.remove(o, do_unlink=True)

K = 0.55            # arms ~21 cm each
HEAD_S, BASE_S = 0.68, 0.7   # shade ~13 cm, base ~14 cm
scaler = bpy.data.objects.new("Lamp Scale", None)
s.collection.objects.link(scaler)
scaler.scale = (K, K, K)
for o in list(s.objects):
    if o.parent is None and o.name not in ("Table", "Fill_Cool", "Rim_Back", "Cam", "Lamp Scale"):
        o.parent = scaler
        o.matrix_parent_inverse = Matrix.Identity(4)
pb["head"].scale = (HEAD_S,) * 3
s.objects["Lamp_Base"].scale = (BASE_S,) * 3
s.objects["Cable"].location.x = (1 - BASE_S) * 0.207
s.view_layers[0].update()


def rrect(w, h, r, seg=12):
    pts = []
    for cx, cy, a0 in ((w/2-r, h/2-r, 0), (-w/2+r, h/2-r, 90), (-w/2+r, -h/2+r, 180), (w/2-r, -h/2+r, 270)):
        for i in range(seg + 1):
            a = math.radians(a0 + 90 * i / seg)
            pts.append((cx + r*math.cos(a), cy + r*math.sin(a)))
    return pts


def slab(name, w, h, r, t, z0=0.0, uv=False):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    vs = [bm.verts.new((x, y, z0)) for x, y in rrect(w, h, r)]
    f = bm.faces.new(vs)
    if t > 0:
        ext = bmesh.ops.extrude_face_region(bm, geom=[f])
        bmesh.ops.translate(bm, verts=[v for v in ext["geom"] if isinstance(v, bmesh.types.BMVert)], vec=(0, 0, t))
        bm.normal_update()
    else:
        f.normal_update()
        if f.normal.z < 0: f.normal_flip()
    if uv:
        lay = bm.loops.layers.uv.new("UVMap")
        for face in bm.faces:
            for l in face.loops:
                l[lay].uv = (l.vert.co.x / w + 0.5, l.vert.co.y / h + 0.5)
    bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me)
    s.collection.objects.link(ob)
    return ob


def mat(name, color, rough, metal=0.0, coat=0.0):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    b.inputs["Coat Weight"].default_value = coat
    return m

# ---------------- iPad mini (195.4 x 134.8 x 6.3 mm), landscape, facing the user (-Y)
IW, IH, IT = 0.1954, 0.1348, 0.0063
ipad = bpy.data.objects.new("iPad mini", None)
s.collection.objects.link(ipad)
ipad.location = (0.34, -0.24, 0.0)
ipad.rotation_euler = (0, 0, math.radians(-6))

body = slab("iPad Body", IW, IH, 0.0108, IT)
bev = body.modifiers.new("soft", "BEVEL"); bev.width = 0.0011; bev.segments = 4; bev.limit_method = "ANGLE"
body.data.materials.append(mat("iPad Space Grey", (0.32, 0.33, 0.35), 0.38, 1.0))
glass = slab("iPad Glass", IW - 0.0016, IH - 0.0016, 0.0100, 0, IT + 0.00005)
glass.data.materials.append(mat("iPad Black Glass", (0.004, 0.004, 0.005), 0.06, 0.0, 1.0))
SW, SH = 0.1766, 0.1159
screen = slab("iPad Screen", SW, SH, 0.0062, 0, IT + 0.0001, uv=True)
sm = mat("iPad Screen", (0.0, 0.0, 0.0), 0.25, 0.0, 0.18)
sm.node_tree.nodes["Principled BSDF"].inputs["Specular IOR Level"].default_value = 0.15
nt = sm.node_tree
tex = nt.nodes.new("ShaderNodeTexImage")
tex.image = bpy.data.images.load("/tmp/bl/margin_ui.png", check_existing=False)
b = nt.nodes["Principled BSDF"]
nt.links.new(tex.outputs["Color"], b.inputs["Emission Color"])
b.inputs["Emission Strength"].default_value = 1.7
b.inputs["Coat Roughness"].default_value = 0.04
screen.data.materials.append(sm)
for o in (body, glass, screen):
    o.parent = ipad
s.view_layers[0].update()

# ---------------- Apple Pencil Pro (166 x 8.9 mm), hovering over the underline
hx, hy = 696, 511
local = Vector(((hx / 2266 - 0.5) * SW, (0.5 - hy / 1488) * SH, IT))
tip = ipad.matrix_world @ local + Vector((0, 0, 0.007))
pen = bpy.data.objects.new("Pencil", None)
s.collection.objects.link(pen)
white = mat("Pencil White", (0.92, 0.92, 0.9), 0.32)
grey = mat("Pencil Nib", (0.55, 0.56, 0.58), 0.5)

def cone(name, r1, r2, z0, z1, m, verts=64):
    bpy.ops.mesh.primitive_cone_add(vertices=verts, radius1=r1, radius2=r2, depth=z1 - z0, location=(0, 0, (z0 + z1) / 2))
    o = bpy.context.active_object; o.name = name
    for c in o.users_collection: c.objects.unlink(o)
    s.collection.objects.link(o)
    o.data.materials.append(m)
    bpy.ops.object.shade_smooth() if False else None
    for p in o.data.polygons: p.use_smooth = True
    o.parent = pen
    return o

R = 0.00445
cone("Pencil Nib", 0.0004, 0.0011, 0.0, 0.003, grey)
cone("Pencil Taper", 0.0011, R, 0.003, 0.021, white)
body_p = cone("Pencil Body", R, R, 0.021, 0.166, white)
bp = body_p.modifiers.new("soft", "BEVEL"); bp.width = 0.0012; bp.segments = 4; bp.limit_method = "ANGLE"
elev, head_dir = math.radians(52), Vector((0.88, -0.48, 0)).normalized()
axis = (head_dir * math.cos(elev) + Vector((0, 0, math.sin(elev)))).normalized()
pen.rotation_mode = "QUATERNION"
pen.rotation_quaternion = Vector((0, 0, 1)).rotation_difference(axis) @ Quaternion((0, 0, 1), math.radians(30))
pen.location = tip

# ---------------- pose the lamp so its beam lands on the page
spot = s.objects["Lamp_Spot"]
target = ipad.matrix_world @ Vector((-0.01, 0.01, IT))

def hit():
    s.view_layers[0].update()
    m = spot.matrix_world
    o, d = m.translation, -(m.to_3x3() @ Vector((0, 0, 1))).normalized()
    if d.z >= -0.05: return None, o
    t = -o.z / d.z
    return o + d * t, o

def set_pose(yaw, low, up, nod):
    for bn in pb: bn.rotation_euler = (0, 0, 0)
    pb["head"].scale = (HEAD_S,) * 3
    pb["swivel"].rotation_euler[1] = math.radians(yaw)
    pb["lower"].rotation_euler[0] = math.radians(low)
    pb["upper"].rotation_euler[0] = math.radians(up)
    pb["head"].rotation_euler[0] = math.radians(nod)

best = None
for low, up in ((-6, -12), (-2, -6), (2, 0)):
    for yaw in range(-80, 1, 2):
        for nod in range(0, 81, 2):
            set_pose(yaw, low, up, nod)
            p, o = hit()
            if p is None: continue
            e = (p - target).length
            if best is None or e < best[0]:
                best = (e, yaw, low, up, nod, tuple(round(v, 3) for v in o))
for sign in (1, -1):
    pass
e, yaw, low, up, nod, origin = best
set_pose(yaw, low, up, nod)
s.view_layers[0].update()
print("pose yaw/low/up/nod", yaw, low, up, nod, "err", round(e, 3), "spot at", origin)
if "glow" in pb["head"]: pb["head"]["glow"] = 0.4

# ---------------- cameras
def cam(name, loc, look, lens, focus=None, f=None):
    cd = bpy.data.cameras.new(name); cd.lens = lens
    if focus is not None:
        cd.dof.use_dof = True; cd.dof.focus_distance = (Vector(loc) - focus).length; cd.dof.aperture_fstop = f
    co = bpy.data.objects.new(name, cd); s.collection.objects.link(co)
    co.location = loc
    co.rotation_euler = (Vector(look) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    return co

mid = (Vector((0, 0, 0.2)) + ipad.matrix_world.translation) / 2
desk = cam("Desk Cam", (0.90, -1.06, 0.56), Vector((0.16, -0.12, 0.15)), 40)
close = cam("Close Cam", tip + Vector((0.05, -0.27, 0.15)), tip + Vector((-0.07, 0.10, 0.045)), 30, tip, 2.4)

s.render.resolution_x, s.render.resolution_y = 1600, 900
try:
    s.view_settings.look = "AgX - Medium High Contrast"
except Exception as ex: print("look", ex)
for c, p in ((desk, "/tmp/bl/varB_wide.png"), (close, "/tmp/bl/varB_close.png")):
    s.camera = c
    s.render.filepath = p
    bpy.ops.render.render(write_still=True)
s.camera = desk
for n in ("Lamp_Head", "Lamp_Base", "Lamp_ArmLower", "Lamp_ArmUpper"):
    o = s.objects[n]; bb = [o.matrix_world @ Vector(c) for c in o.bound_box]
    print(n, "size cm", [round((max(v[i] for v in bb) - min(v[i] for v in bb)) * 100, 1) for i in range(3)])
print("top z cm", round(max((o.matrix_world @ Vector(c)).z for o in s.objects if o.type == "MESH" and o.name.startswith("Lamp") for c in o.bound_box) * 100, 1))
print("ok tip", tuple(round(v, 3) for v in tip))
