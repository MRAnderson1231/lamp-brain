import bpy, json, os
cfg = json.load(open("/tmp/bl/render_job.json"))
meta = json.load(open("/tmp/bl/anim_meta.json"))
s = bpy.data.scenes["Margin Luxo"]
rig = s.objects["LampRig"]
ad = rig.animation_data
name = cfg["clip"]
act = bpy.data.actions["margin_" + name]
ad.action = act
if getattr(act, "slots", None) and len(act.slots): ad.action_slot = act.slots[0]

nt = bpy.data.materials["iPad Screen"].node_tree
mix = nt.nodes["Hint Mix"]
if nt.animation_data: nt.animation_data_clear()
for f, v in meta[name]["hint"]:
    mix.inputs[0].default_value = v
    mix.inputs[0].keyframe_insert("default_value", frame=f)

from mathutils import Vector
cam = s.objects.get("Anim Cam")
if cam is None:
    cd = bpy.data.cameras.new("Anim Cam"); cd.lens = 36
    cam = bpy.data.objects.new("Anim Cam", cd); s.collection.objects.link(cam)
cam.location = (1.02, -1.18, 0.62)
cam.rotation_euler = (Vector((0.15, -0.13, 0.19)) - cam.location).to_track_quat("-Z", "Y").to_euler()
s.camera = cam
s.render.resolution_x, s.render.resolution_y = cfg.get("w", 960), cfg.get("h", 540)
s.eevee.taa_render_samples = cfg.get("samples", 32)
s.render.image_settings.file_format = "PNG"
out = "/tmp/bl/anim/%s/" % name
os.makedirs(out, exist_ok=True)
frames = cfg.get("frames") or list(range(0, meta[name]["len"] + 1))
for f in frames:
    s.frame_set(f)
    s.render.filepath = out + "%04d.png" % f
    bpy.ops.render.render(write_still=True)
print("rendered", name, len(frames))
