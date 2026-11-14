# Mac camera → lampkit → Blender

This test uses real camera frames and MediaPipe Face Landmarker. It does not use scripted
presence, a VLM, a microphone, or an iPad. It verifies the transport and motion chain, not
emotion recognition or educational effectiveness. Images are processed in memory locally;
the JSONL log records derived face observations and decisions, not raw video.

## Prepare once

```sh
uv venv .venv-live --python 3.12
uv pip install --python .venv-live/bin/python -r requirements-live.txt
mkdir -p models
curl -fL https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task -o models/face_landmarker.task
```

Open `design/blender/margin_lamp_behaviours.blend`. Save any other unsaved scene first.
In Blender's Scripting workspace, open and run the repository's `blender_live.py`.
It starts a UDP receiver on localhost:9877 and disconnects baked rig animation so live
poses can take effect. Re-running it safely replaces the previous registered receiver.

## Run

```sh
./live_test.sh       # real webcam, fixed policy, stops after 5 minutes
./live_test.sh 90    # shorter run; Ctrl-C also stops it
```

Allow the camera permission if macOS asks. Look into the Mac's front camera. Presence should
trigger a greeting, then a return to the working pose. Move fully out of the image for about
10 seconds: the lamp should search. Returning should trigger another greeting, subject to
its cooldown. Looking away alone does not necessarily mean absent. Fatigue and other states
need sustained evidence and are not guaranteed to trigger from a single exaggerated gesture.

When finished, the runtime releases the camera. Blender's idle receiver can be stopped by
running `bpy.app.driver_namespace["lampkit_live_stop"]()` in its Python console.

Replay the printed log path with `python3 -m lampkit replay logs/<file>.jsonl`.
The source logs and camera-derived data stay in ignored `logs/`; do not upload them as part
of the public repository. Mac camera placement is not the lamp's eventual camera placement,
so the default coordinate mapping is illustrative, not calibrated physical pointing.
