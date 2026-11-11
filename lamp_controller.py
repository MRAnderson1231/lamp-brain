"""Realtime lamp controller (run inside Blender, after lamp_clips.py).

Plays the `lamp_*` actions on the rig from a timer, independent of the
timeline, cross-fading whenever the clip changes.

Trigger an emotion in either of two ways:
  * write one word to EMOTION_FILE:  neutral | happy | laughing | sad | surprised
  * from Blender's Python console:   bpy.app.driver_namespace["lamp"].set("happy")

While the emotion is "neutral" the lamp breathes and, every few seconds,
plays a random idle (look left / right, inspect the table, nod at the viewer).
Stop with:  bpy.app.driver_namespace["lamp"].stop()
"""
import os
import random
import re
import time

import bpy

# emotion.txt lives next to the .blend file
EMOTION_FILE = os.path.join(os.path.dirname(bpy.data.filepath), "emotion.txt")
FPS = 24.0
TICK = 1.0 / 30.0
BLEND = 0.35                      # seconds of cross-fade between clips
IDLE_GAP = (2.5, 6.0)             # seconds of plain breathing between idles

BREATHE = "lamp_idle_breathe"
IDLES = ["lamp_idle_look_left", "lamp_idle_look_right", "lamp_idle_curious", "lamp_idle_hello"]
LOOPS = {"happy": "lamp_happy", "laughing": "lamp_laugh", "sad": "lamp_sad"}
ONE_SHOTS = {"surprised": "lamp_surprised"}
EMOTIONS = {"neutral"} | set(LOOPS) | set(ONE_SHOTS)

_BONE_PROP = re.compile(r'pose\.bones\["(\w+)"\]\.(\w+)$')
_BONE_CUSTOM = re.compile(r'pose\.bones\["(\w+)"\]\["(\w+)"\]$')


def _fcurves(action):
    if getattr(action, "layers", None):
        out = []
        for layer in action.layers:
            for strip in layer.strips:
                for bag in strip.channelbags:
                    out.extend(bag.fcurves)
        return out
    return list(action.fcurves)


class Clip:
    def __init__(self, action):
        self.name = action.name
        self.length = action.frame_range[1] / FPS
        self.channels = []            # (key, fcurve)
        for fc in _fcurves(action):
            m = _BONE_PROP.match(fc.data_path)
            if m:
                self.channels.append(((m.group(1), m.group(2), fc.array_index), fc))
                continue
            m = _BONE_CUSTOM.match(fc.data_path)
            if m:
                self.channels.append(((m.group(1), m.group(2), -1), fc))


class LampController:
    def __init__(self):
        self.arm = bpy.data.objects["LampRig"]
        if self.arm.animation_data:
            self.arm.animation_data.action = None      # the timer owns the pose
        self.clips = {a.name: Clip(a) for a in bpy.data.actions if a.name.startswith("lamp_")}
        self.emotion = "neutral"
        self.clip = None
        self.loop = True
        self.clip_start = 0.0
        self.snapshot = {}
        self.blend_start = 0.0
        self.next_idle = time.perf_counter() + random.uniform(*IDLE_GAP)
        self.file_mtime = 0.0
        self.running = False
        self.play(BREATHE, loop=True)

    # ---- pose io ----
    def _read(self, key):
        bone, prop, idx = key
        pb = self.arm.pose.bones[bone]
        return float(pb[prop]) if idx < 0 else float(getattr(pb, prop)[idx])

    def _write(self, key, value):
        bone, prop, idx = key
        pb = self.arm.pose.bones[bone]
        if idx < 0:
            pb[prop] = float(value)
        else:
            getattr(pb, prop)[idx] = value

    def apply(self, clip, seconds, blend=1.0):
        frame = seconds * FPS
        for key, fc in clip.channels:
            v = fc.evaluate(frame)
            if blend < 1.0:
                a = self.snapshot.get(key, v)
                v = a + (v - a) * blend
            self._write(key, v)
        self.arm.update_tag()

    # ---- control ----
    def play(self, name, loop):
        now = time.perf_counter()
        clip = self.clips[name]
        self.snapshot = {key: self._read(key) for key, _ in clip.channels}
        self.clip, self.loop = clip, loop
        self.clip_start = self.blend_start = now

    def set(self, emotion):
        emotion = emotion.strip().lower()
        if emotion not in EMOTIONS or emotion == self.emotion:
            return
        self.emotion = emotion
        if emotion in LOOPS:
            self.play(LOOPS[emotion], loop=True)
        elif emotion in ONE_SHOTS:
            self.play(ONE_SHOTS[emotion], loop=False)
        else:
            self.play(BREATHE, loop=True)
            self.next_idle = time.perf_counter() + random.uniform(*IDLE_GAP)

    def _poll_file(self):
        try:
            mt = os.stat(EMOTION_FILE).st_mtime
        except OSError:
            return
        if mt != self.file_mtime:
            self.file_mtime = mt
            try:
                with open(EMOTION_FILE) as f:
                    self.set(f.read())
            except OSError:
                pass

    def step(self, now):
        self._poll_file()
        t = now - self.clip_start
        if self.loop:
            t %= self.clip.length
        elif t >= self.clip.length:
            # a one-shot finished: fall back to breathing
            self.apply(self.clip, self.clip.length)
            self.play(BREATHE, loop=True)
            self.next_idle = now + random.uniform(*IDLE_GAP)
            t = 0.0
        if self.emotion == "neutral" and self.clip.name == BREATHE and now >= self.next_idle:
            self.play(random.choice(IDLES), loop=False)
            t = 0.0
        u = min(1.0, (now - self.blend_start) / BLEND)
        self.apply(self.clip, t, blend=u * u * (3 - 2 * u))

    def tick(self):
        if not self.running:
            return None
        try:
            self.step(time.perf_counter())
            for win in bpy.context.window_manager.windows:
                for area in win.screen.areas:
                    if area.type == 'VIEW_3D':
                        area.tag_redraw()
        except ReferenceError:        # rig was deleted or file reloaded
            self.running = False
            return None
        return TICK

    def start(self):
        if not self.running:
            self.running = True
            bpy.app.timers.register(self.tick, first_interval=TICK)

    def stop(self):
        self.running = False


_old = bpy.app.driver_namespace.get("lamp")
if _old is not None:
    _old.stop()
lamp = LampController()
bpy.app.driver_namespace["lamp"] = lamp
lamp.start()
print("lamp controller running; clips:", sorted(lamp.clips))
