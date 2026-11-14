"""Digital twin: drive the Blender lamp from the lampkit runtime in real time.

Run inside Blender (Scripting tab -> open this file -> Run Script, or through blender-mcp),
with the "Margin Luxo" scene open. Then, in a terminal:

    python -m lampkit simulate scenarios/demo.json --profile twin --realtime
    python -m lampkit run --profile desk                       # camera + iPad, live

The runtime streams one JSON pose per tick over UDP 127.0.0.1:9877; a Blender timer applies
the newest one to LampRig. Set RECORD = True to also keyframe every pose, so a live session
can be rendered afterwards. Run `stop()` from the Python console to release the port.
"""

import json
import math
import socket

import bpy

PORT = 9877
SCENE = "Margin Luxo"
RIG = "LampRig"
RECORD = False
FPS = 30

# runtime channel -> (bone, property, index, sign); degrees for rotations
CHANNELS = {
    "yaw": ("swivel", "rotation_euler", 1, 1.0),
    "low": ("lower", "rotation_euler", 0, 1.0),
    "up": ("upper", "rotation_euler", 0, 1.0),
    "nod": ("head", "rotation_euler", 0, 1.0),
    "turn": ("head", "rotation_euler", 2, -1.0),
    "hop": ("root", "location", 1, 1.0),
}

_state = {"sock": None, "t0": None, "frames": 0}


def apply(pose: dict) -> None:
    rig = bpy.data.scenes[SCENE].objects[RIG]
    pb = rig.pose.bones
    for ch, (bone, prop, i, sign) in CHANNELS.items():
        if ch not in pose:
            continue
        v = sign * pose[ch]
        getattr(pb[bone], prop)[i] = math.radians(v) if prop == "rotation_euler" else v
    if "squash" in pose:
        s = 1.0 + pose["squash"]
        pb["root"].scale = (1 / math.sqrt(s), s, 1 / math.sqrt(s))
    for prop in ("glow", "warmth"):
        if prop in pose:
            pb["head"][prop] = float(pose[prop])
    if RECORD and "t" in pose:
        if _state["t0"] is None:
            _state["t0"] = pose["t"]
        frame = 1 + int(round((pose["t"] - _state["t0"]) * FPS))
        for bone, prop, i, _ in CHANNELS.values():
            pb[bone].keyframe_insert(prop, index=i, frame=frame)
        pb["root"].keyframe_insert("scale", frame=frame)
        for prop in ("glow", "warmth"):
            pb["head"].keyframe_insert('["%s"]' % prop, frame=frame)
    rig.update_tag()


def _poll():
    sock = _state["sock"]
    if sock is None:
        return None
    latest = None
    while True:
        try:
            data, _ = sock.recvfrom(65536)
        except BlockingIOError:
            break
        except OSError:
            return None
        latest = data
    if latest is not None:
        try:
            apply(json.loads(latest))
            _state["frames"] += 1
        except (ValueError, KeyError) as e:
            print("blender_live: bad pose:", e)
    return 1.0 / 60.0


def start(port: int = PORT) -> None:
    stop()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", port))
    sock.setblocking(False)
    _state.update(sock=sock, t0=None, frames=0)
    bpy.app.timers.register(_poll, persistent=True)
    print("blender_live: listening on udp %d" % port)


def stop() -> None:
    if _state["sock"] is not None:
        _state["sock"].close()
        _state["sock"] = None
    if bpy.app.timers.is_registered(_poll):
        bpy.app.timers.unregister(_poll)


if __name__ == "__main__":
    start()
