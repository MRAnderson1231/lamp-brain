"""Local observation console. Uses the actual runtime; never invents sensor evidence.

Run: .venv-live/bin/python -m lampkit.lab
Start/stop camera from http://127.0.0.1:8765. Frames are memory-only, never logged.
The HTTP adapter is orchestration like runtime.py, not part of the deterministic core.
"""
from __future__ import annotations

import argparse
import copy
import json
import mimetypes
import queue
import threading
import time
import uuid
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .bridge import IPadBridge, validate_message
from .config import load_profile
from .infra import Clock
from .runtime import Runtime
from .types import Event

ROOT = Path(__file__).resolve().parent.parent
LABELS = {"neutral", "confused", "tired", "reluctant"}


class LabInbox:
    def __init__(self, limit):
        self.q = queue.Queue(maxsize=limit)

    def submit(self, msg):
        if isinstance(msg, dict) and msg.get("kind") == "lab.annotation":
            d = msg.get("data", {})
            if not isinstance(d, dict) or d.get("label") not in LABELS:
                raise ValueError("unknown self-report label")
            kind, data, src = "lab.annotation", {"label": d["label"]}, "self-report"
        else:
            kind, data = validate_message(msg)
            src = "mock-margin"
        self.q.put_nowait((kind, data, src))

    def poll(self, t):
        events = []
        while True:
            try:
                kind, data, src = self.q.get_nowait()
            except queue.Empty:
                return events
            events.append(Event(t, kind, data, src))


class Lab:
    def __init__(self, cfg, camera_factory=None):
        self.cfg = copy.deepcopy(cfg)
        # Observational validation must not update a user's learned preferences.
        self.cfg["personalize"].update(enabled=False, state_file=None)
        self.cfg["vlm"]["enabled"] = False
        self.cfg['decision']['enabled'] = False
        self.camera_factory = camera_factory
        self.lock = threading.Lock()
        self.control = threading.Lock()
        self.halt = threading.Event()
        self.thread = None
        self.inbox = None
        self.jpeg = None
        self.last_seen = time.monotonic()
        self.state = {"status": "stopped", "events": [], "face": {}, "evidence": {},
                      "pose": {}, "context": "sleep", "study": "engaged", "error": None}

    def start(self):
        with self.control:
            if self.thread and self.thread.is_alive():
                return
            self.halt.clear()
            self.last_seen = time.monotonic()
            self.inbox = LabInbox(self.cfg["lab"]["max_pending"])
            with self.lock:
                self.jpeg = None
                self.state = {"status": "starting", "events": [], "face": {}, "evidence": {},
                              "pose": {}, "context": "sleep", "study": "engaged", "error": None}
            self.thread = threading.Thread(target=self._run, daemon=True)
            self.thread.start()

    def stop(self):
        with self.control:
            self.halt.set()
            if self.thread:
                self.thread.join(timeout=self.cfg["lab"]["stop_timeout"])
            with self.lock:
                self.jpeg = None
                if self.thread and self.thread.is_alive():
                    self.state["status"] = "stopping"
                elif self.state["status"] != "error":
                    self.state["status"] = "stopped"

    def submit(self, msg):
        with self.control:
            if self.halt.is_set() or self.state["status"] != "running":
                raise ValueError("先开始摄像头测试，再发送消息或标注")
            self.inbox.submit(msg)

    def snapshot(self):
        with self.lock:
            self.last_seen = time.monotonic()
            return dict(copy.deepcopy(self.state), profile=self.cfg.get('name'))

    def _run(self):
        rt = cam = bridge = None
        cfg, c = self.cfg, self.cfg["lab"]
        clock = Clock()
        started = clock.now()
        events = deque(maxlen=c["history_limit"])
        latest = {}
        counter = 0
        try:
            factory = self.camera_factory
            if factory is None:
                from .sensors.camera import CameraSensor
                factory = CameraSensor
            cam = factory(cfg, clock)
            if self.halt.is_set():
                return
            if cfg["bridge"]["enabled"]:
                bridge = IPadBridge(clock, **{k: v for k, v in cfg["bridge"].items() if k != "enabled"})
            logfile = ROOT / "logs" / ("lab-" + time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6] + ".jsonl")
            sensors = [cam, self.inbox]
            if cfg['local_context']['enabled']:
                from .sensors.local_context import LocalContextSensor
                sensors.append(LocalContextSensor(cfg))
            rt = Runtime(cfg, clock, sensors, bridge=bridge, log_path=logfile)

            def observe(ev):
                nonlocal counter
                if ev.kind == "obs.face":
                    latest["face"] = dict(ev.data, t=ev.t)
                elif ev.kind == "intervene":
                    latest["action"] = ev.data
                elif ev.kind == "motion.plan":
                    latest["plan"] = ev.data
                if ev.kind not in {"tick", "obs.face", "evidence"}:
                    counter += 1
                    events.append({"id": counter, "t": round(ev.t - started, 2),
                                   "kind": ev.kind, "data": ev.data, "src": ev.src})

            rt.bus.on("", observe)
            next_preview = 0.0
            brightness = None
            while not self.halt.is_set():
                t = clock.now()
                if t - started > c["max_seconds"] or t - self.last_seen > c["idle_timeout"]:
                    break
                if not cam.thread.is_alive():
                    raise RuntimeError("摄像头处理线程已停止，请停止后重试")
                rt.tick()
                ev, why, feats = rt.est.evidence(t)
                if t >= next_preview:
                    frame = cam.frame()
                    if frame is not None:
                        cv2 = cam.cv2
                        small = cv2.resize(frame, (c["preview_width"], round(frame.shape[0] * c["preview_width"] / frame.shape[1])))
                        brightness = round(float(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY).mean()) / 255, 3)
                        ok, encoded = cv2.imencode('.jpg', small, [cv2.IMWRITE_JPEG_QUALITY, c["jpeg_quality"]])
                        if ok:
                            with self.lock:
                                self.jpeg = encoded.tobytes()
                    next_preview = t + 1 / c["preview_hz"]
                with self.lock:
                    self.state = {"status": "running", "error": None,
                                  "elapsed": round(t - started, 1), "log": str(logfile),
                                  "context": rt.fsm.context, "study": rt.fsm.study,
                                  "face": latest.get("face", {}), "face_fresh": rt.est.present(t),
                                  "evidence": ev, "why": why, "features": feats,
                                  "scores": {k: v.score.value for k, v in rt.fsm.tracks.items()},
                                  "thresholds": {k: v.enter for k, v in rt.fsm.tracks.items()},
                                  "action": latest.get("action"), "plan": latest.get("plan"),
                                  "pose": dict(rt.body.last), "events": list(events),
                                  "brightness": brightness, "exam": rt.est.exam,
                                  "camera_age": round(t - latest.get("face", {}).get("t", started), 2),
                                  "models": {"face": "MediaPipe Face Landmarker", "vlm": "disabled"}}
                    self.state['control'] = rt.control.snapshot(t) if rt.control else None
                self.halt.wait(max(0, 1 / cfg["loop_hz"] - (clock.now() - t)))
        except (Exception, SystemExit) as exc:
            with self.lock:
                self.state.update(status="error", error=str(exc))
        finally:
            try:
                if rt is not None:
                    rt.close()
                else:
                    if bridge is not None:
                        bridge.close()
                    if cam is not None:
                        cam.close()
            finally:
                with self.lock:
                    self.jpeg = None
                    if self.state["status"] != "error":
                        self.state["status"] = "stopped"


def make_handler(lab, directory):
    directory = Path(directory).resolve()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def local_request(self):
            expected = f"127.0.0.1:{self.server.server_address[1]}"
            host = self.headers.get("Host", "")
            origin = self.headers.get("Origin")
            return host == expected and (not origin or origin == "http://" + expected)

        def reply(self, code, body=b"", mime="application/json"):
            self.send_response(code)
            self.send_header("Content-Type", mime)
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def json(self, value, code=200):
            self.reply(code, json.dumps(value, ensure_ascii=False).encode())

        def do_GET(self):
            if not self.local_request():
                return self.json({"error": "local origin required"}, 403)
            path = urlparse(self.path).path
            if path == "/api/state":
                return self.json(lab.snapshot())
            if path == "/api/frame.jpg":
                with lab.lock:
                    frame = lab.jpeg
                return self.reply(200 if frame else 204, frame or b"", "image/jpeg")
            asset = (directory / ("index.html" if path == "/" else path.lstrip("/"))).resolve()
            if not asset.is_relative_to(directory) or not asset.is_file():
                return self.json({"error": "not found; run npm run build in web/"}, 404)
            return self.reply(200, asset.read_bytes(), mimetypes.guess_type(asset.name)[0] or "application/octet-stream")

        def do_POST(self):
            if not self.local_request() or self.headers.get("X-Lamp-Lab") != "1":
                return self.json({"error": "local lab request required"}, 403)
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= lab.cfg["lab"]["max_request_bytes"]:
                    raise ValueError("invalid request length")
                data = json.loads(self.rfile.read(length))
                if self.path == "/api/start":
                    lab.start()
                elif self.path == "/api/stop":
                    lab.stop()
                elif self.path == "/api/event":
                    lab.submit(data)
                else:
                    return self.json({"error": "unknown operation"}, 404)
                return self.json({"ok": True})
            except (ValueError, TypeError, queue.Full) as exc:
                return self.json({"error": str(exc) or "too many pending messages"}, 400)

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int)
    parser.add_argument("--profile", default="companion")
    args = parser.parse_args()
    cfg = load_profile(args.profile)
    lab = Lab(cfg)
    server = ThreadingHTTPServer(("127.0.0.1", args.port or cfg["lab"]["port"]), make_handler(lab, ROOT / "web" / "dist"))
    print(f"Lamp lab: http://127.0.0.1:{server.server_port} (camera starts only on click)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        lab.stop()
        server.server_close()


if __name__ == "__main__":
    main()
