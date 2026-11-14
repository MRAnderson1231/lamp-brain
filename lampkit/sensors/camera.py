"""Live webcam perception: MediaPipe face landmarks + blendshapes -> `obs.face` at ~15 Hz.

Optional dependencies (`uv sync --extra live`): mediapipe, opencv-python. Model file:
https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task
saved to models/face_landmarker.task.

The camera pose in the desk frame comes from the profile (`camera.position`, `camera.yaw_deg`,
`camera.pitch_deg`, `camera.hfov_deg`); face distance is estimated from the apparent
inter-ocular width (`camera.ipd_m`). Basic capture, face landmarks and presence-driven Blender motion were exercised on a
MacBook Pro on 2026-11-14. Head geometry, affect accuracy and fatigue detection remain
unvalidated.
"""
from __future__ import annotations

import math
import threading
import time
from pathlib import Path

from ..types import OBS_FACE, Event

BLENDS = {"browDown": ("browDownLeft", "browDownRight"), "eyeSquint": ("eyeSquintLeft", "eyeSquintRight"),
          "eyeBlink": ("eyeBlinkLeft", "eyeBlinkRight"), "jawOpen": ("jawOpen",),
          "mouthSmile": ("mouthSmileLeft", "mouthSmileRight"), "mouthFrown": ("mouthFrownLeft", "mouthFrownRight")}


class CameraSensor:
    def __init__(self, cfg: dict, clock):
        import cv2
        import mediapipe as mp
        from mediapipe.tasks.python import BaseOptions
        from mediapipe.tasks.python.vision import FaceLandmarker, FaceLandmarkerOptions, RunningMode

        c = cfg["camera"]
        self.c, self.clock, self.cv2, self.mp = c, clock, cv2, mp
        model = Path(c["face_model"]).expanduser()
        if not model.exists():
            raise SystemExit("missing %s (see lampkit/sensors/camera.py for the download URL)" % model)
        self.landmarker = FaceLandmarker.create_from_options(FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(model)), running_mode=RunningMode.VIDEO,
            output_face_blendshapes=True, output_facial_transformation_matrixes=True, num_faces=1))
        self.cap = cv2.VideoCapture(c.get("index", 0))
        if not self.cap.isOpened():
            raise SystemExit("could not open the camera (System Settings > Privacy & Security > Camera)")
        self.latest_frame = None
        self.out: list[Event] = []
        self.lock = threading.Lock()
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def _loop(self) -> None:
        period = 1.0 / self.c.get("hz", 15)
        while self.running:
            t0 = time.monotonic()
            ok, frame = self.cap.read()
            if ok:
                ev = self._process(frame)
                with self.lock:
                    self.latest_frame = frame
                    self.out.append(ev)
            time.sleep(max(0.0, period - (time.monotonic() - t0)))

    def _process(self, frame) -> Event:
        t = self.clock.now()
        rgb = self.cv2.cvtColor(frame, self.cv2.COLOR_BGR2RGB)
        img = self.mp.Image(image_format=self.mp.ImageFormat.SRGB, data=rgb)
        res = self.landmarker.detect_for_video(img, int(t * 1000))
        if not res.face_landmarks:
            return Event(t, OBS_FACE, {"present": False}, "camera")
        cats = {b.category_name: b.score for b in res.face_blendshapes[0]}
        blend = {k: sum(cats.get(n, 0.0) for n in names) / len(names) for k, names in BLENDS.items()}
        lm = res.face_landmarks[0]
        m = res.facial_transformation_matrixes[0]
        yaw = math.degrees(math.atan2(m[0][2], m[2][2]))
        pitch = math.degrees(math.asin(max(-1.0, min(1.0, -m[1][2]))))
        x, y, z = self._face_xyz(lm, frame.shape[1], frame.shape[0])
        return Event(t, OBS_FACE, {"present": True, "yaw": round(yaw, 1), "pitch": round(pitch, 1),
                                   "x": x, "y": y, "z": z, "blend": {k: round(v, 3) for k, v in blend.items()}}, "camera")

    def _face_xyz(self, lm, w: int, h: int) -> tuple[float, float, float]:
        c = self.c
        f = (w / 2) / math.tan(math.radians(c["hfov_deg"]) / 2)
        left, right = lm[33], lm[263]
        ipd_px = math.hypot((left.x - right.x) * w, (left.y - right.y) * h) or 1.0
        depth = f * c["ipd_m"] / ipd_px
        cx, cy = (left.x + right.x) / 2 * w - w / 2, (left.y + right.y) / 2 * h - h / 2
        # camera frame: forward, left, up
        fwd, left_, up = depth, -cx * depth / f, -cy * depth / f
        yaw, pitch = math.radians(c["yaw_deg"]), math.radians(c["pitch_deg"])
        fx = fwd * math.cos(pitch) - up * math.sin(pitch)
        fz = fwd * math.sin(pitch) + up * math.cos(pitch)
        px, py, pz = c["position"]
        return (round(px + fx * math.cos(yaw) - left_ * math.sin(yaw), 3),
                round(py + fx * math.sin(yaw) + left_ * math.cos(yaw), 3), round(pz + fz, 3))

    def frame(self):
        with self.lock:
            return self.latest_frame

    def poll(self, t: float) -> list[Event]:
        with self.lock:
            out, self.out = self.out, []
        return out

    def close(self):
        self.running = False
        self.thread.join(timeout=2.0)
        if not self.thread.is_alive():
            self.cap.release()
            self.landmarker.close()
