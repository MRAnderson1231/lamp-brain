import bpy, math
from pathlib import Path
if not bpy.app.background:
 raise RuntimeError('Run this exporter in a separate Blender --background process; it prunes the in-memory scene.')
# Run from repo root: Blender --background design/blender/margin_lamp_behaviours.blend --python design/blender/export_web.py
s=bpy.data.scenes['Margin Luxo']
bpy.context.window.scene=s
rig=s.objects['LampRig']
head_scale=rig.pose.bones['head'].scale.copy()
rig.animation_data_clear()
for b in rig.pose.bones:
 b.rotation_euler=(0,0,0); b.location=(0,0,0); b.scale=(1,1,1)
rig.pose.bones['head'].scale=head_scale
for o in bpy.context.view_layer.objects: o.select_set(False)
for o in list(s.objects):
 if o==rig or o==rig.parent or (o.parent==rig and o.type in {'MESH','CURVE'}):
  o.hide_set(False); o.hide_viewport=False; o.select_set(True)
keep={o for o in bpy.data.objects if o.select_get()}
keep={o for o in keep if o==rig or o==rig.parent or o.parent==rig}
for o in list(bpy.data.objects):
 if o not in keep: bpy.data.objects.remove(o,do_unlink=True)
for scene in list(bpy.data.scenes):
 if scene!=s: bpy.data.scenes.remove(scene)
bpy.context.view_layer.objects.active=rig
bpy.context.view_layer.update()
bpy.ops.export_scene.gltf(filepath=str(Path(__file__).resolve().parents[2] / 'web/public/lamp.glb'),export_format='GLB',use_selection=True,export_animations=False,export_lights=False,export_cameras=False,export_extras=True)
print('EXPORTED')
