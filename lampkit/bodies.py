"""Bodies execute poses. Same interface for the Blender twin, the SceneKit app, MuJoCo, servos.

Pose channels: yaw/low/up/nod/turn in degrees, hop in metres, squash as a ratio offset,
glow (1 = normal working light) and warmth (0 cold .. 1 warm).
"""
from __future__ import annotations

import json
import socket


class NullBody:
    """Remembers poses; used by tests and replay."""

    def __init__(self, keep: bool = False):
        self.keep = keep
        self.last: dict = {}
        self.frames: list[dict] = []

    def apply(self, t: float, pose: dict) -> None:
        self.last = pose
        if self.keep:
            self.frames.append(dict(pose, t=t))


class UdpBody:
    """Streams poses as JSON over UDP. `blender_live.py` (run inside Blender) and future
    SceneKit / servo bridges listen on the same port."""

    def __init__(self, host: str = "127.0.0.1", port: int = 9877):
        self.addr = (host, port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.last: dict = {}

    def apply(self, t: float, pose: dict) -> None:
        self.last = pose
        msg = {k: round(v, 4) for k, v in pose.items()}
        msg["t"] = round(t, 3)
        try:
            self.sock.sendto(json.dumps(msg).encode(), self.addr)
        except OSError:
            pass


    def close(self):
        self.sock.close()


def make_body(cfg: dict):
    b = cfg.get("body", {"type": "null"})
    if b["type"] == "null":
        return NullBody(keep=b.get("keep", False))
    if b["type"] == "udp":
        return UdpBody(b.get("host", "127.0.0.1"), b.get("port", 9877))
    raise ValueError("unknown body %r" % b["type"])
