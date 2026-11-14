"""Bounded newline-JSON Margin transport. Loopback by default; LAN use is explicit.

The prototype has no pairing or encryption: use only on a trusted local network.
All timestamps are assigned on arrival; clients cannot inject internal events.
"""
from __future__ import annotations
import json
import math
import socket
import socketserver
import threading
import time
from .types import Event

APP_KINDS = {"app.session", "app.exam", "app.break", "app.pencil", "app.stuck",
             "app.correct", "app.wrong", "user.pat", "app.task", "app.context",
             "user.study_intent", "user.light", "app.hint_feedback"}


def validate_message(msg: object) -> tuple[str, dict]:
    if not isinstance(msg, dict) or msg.get("kind") not in APP_KINDS:
        raise ValueError("unknown Margin event")
    kind, data = msg["kind"], msg.get("data", {})
    if not isinstance(data, dict):
        raise ValueError("data must be an object")
    def number(v, lo=0, hi=float("inf")):
        return type(v) in (int, float) and math.isfinite(v) and lo <= v <= hi
    if kind in {"app.session", "app.exam", "app.break"}:
        if type(data.get("active")) is not bool:
            raise ValueError("active must be a boolean")
    if "elapsed_min" in data and not number(data["elapsed_min"]):
        raise ValueError("elapsed_min must be finite and nonnegative")
    if 'task_id' in data and (not isinstance(data['task_id'],str) or not 0<len(data['task_id'])<=128):
        raise ValueError('task_id must be a short nonempty string')
    if kind == 'app.task' and 'task_id' not in data:
        raise ValueError('task_id is required')
    if kind == 'app.context' and not number(data.get('local_hour'),0,24):
        raise ValueError('local_hour must be in [0,24]')
    if kind == 'app.hint_feedback' and (type(data.get('accepted')) is not bool or type(data.get('intervention')) is not int):
        raise ValueError('hint feedback requires accepted and intervention id')
    if kind == 'user.study_intent' and data.get('value') not in ('ready','not_now'):
        raise ValueError('study intent must be ready or not_now')
    if kind == 'user.light':
        if not data or not set(data).issubset({'auto','glow','kelvin'}):
            raise ValueError('unknown light command')
        if 'auto' in data and type(data['auto']) is not bool:
            raise ValueError('auto must be boolean')
        if 'glow' in data and not number(data['glow']):
            raise ValueError('brightness must be nonnegative and finite')
        if 'kelvin' in data and not number(data['kelvin']):
            raise ValueError('kelvin must be nonnegative and finite')
    if kind == "app.pencil":
        if any(type(data.get(k, 0)) is not int or data.get(k, 0) < 0 for k in ("strokes", "erases")):
            raise ValueError("pencil counts must be nonnegative integers")
    if kind == "app.stuck":
        if not number(data.get("conf"), 0, 1):
            raise ValueError("conf must be in [0,1]")
        r = data.get("region")
        if r is not None and (not isinstance(r, list) or len(r) != 4 or
                             not all(number(v, 0, 1) for v in r) or
                             r[0] + r[2] > 1 or r[1] + r[3] > 1):
            raise ValueError("region must fit inside normalized screen bounds")
    return kind, data


class IPadBridge:
    def __init__(self, clock, host="127.0.0.1", port=7788, max_line_bytes=16384,
                 max_pending=512, socket_timeout=1.0):
        self.clock, self.max_pending = clock, max_pending
        self.inbox, self.outbox, self.clients = [], [], []
        self.lock = threading.Lock()
        self.stopping = threading.Event()
        bridge = self
        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                self.connection.settimeout(socket_timeout)
                with bridge.lock:
                    bridge.clients.append(self.connection)
                try:
                    # Idle connections are allowed. recv buffering survives timeouts.
                    buf = b""
                    while not bridge.stopping.is_set():
                        try:
                            chunk = self.connection.recv(max_line_bytes)
                        except socket.timeout:
                            continue
                        if not chunk:
                            break
                        buf += chunk
                        while b"\n" in buf:
                            raw, buf = buf.split(b"\n", 1)
                            if len(raw) > max_line_bytes:
                                return
                            try:
                                kind, data = validate_message(json.loads(raw))
                            except (ValueError, TypeError, UnicodeDecodeError):
                                continue
                            with bridge.lock:
                                if len(bridge.inbox) >= max_pending:
                                    return  # overload disconnect, never silently drop exam commands
                                bridge.inbox.append(Event(bridge.clock.now(), kind, data, "ipad"))
                        if len(buf) > max_line_bytes:
                            return
                except OSError:
                    pass
                finally:
                    with bridge.lock:
                        if self.connection in bridge.clients:
                            bridge.clients.remove(self.connection)
        class Server(socketserver.ThreadingMixIn, socketserver.TCPServer):
            allow_reuse_address = True
            daemon_threads = True
        self.server = Server((host, port), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.sender = threading.Thread(target=self._send_loop, daemon=True)
        self.sender.start()

    def poll(self, t):
        with self.lock:
            out, self.inbox = self.inbox, []
        return out

    def send(self, ev):
        # Network writes never block the motion loop.
        with self.lock:
            if len(self.outbox) < self.max_pending:
                self.outbox.append((json.dumps({"kind": ev.kind, "data": ev.data}) + "\n").encode())

    def _send_loop(self):
        while not self.stopping.wait(0.01):
            with self.lock:
                lines, self.outbox = self.outbox, []
                clients = list(self.clients)
            for line in lines:
                for client in clients:
                    try:
                        client.sendall(line)
                    except OSError:
                        with self.lock:
                            if client in self.clients:
                                self.clients.remove(client)
                        client.close()

    def close(self):
        self.stopping.set()
        with self.lock:
            clients, self.clients = self.clients, []
        for client in clients:
            try:
                client.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            client.close()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.sender.join()


def send_events(host, port, events, listen=0.0):
    with socket.create_connection((host, port), timeout=3) as s:
        for e in events:
            validate_message(e)
            s.sendall((json.dumps(e) + "\n").encode())
        buf = b""
        deadline = time.monotonic() + listen
        while time.monotonic() < deadline:
            s.settimeout(max(0.001, deadline - time.monotonic()))
            try:
                chunk = s.recv(4096)
            except socket.timeout:
                break
            if not chunk:
                break
            buf += chunk
        # Only complete frames; a partial final packet is not a JSON document.
        return [json.loads(x) for x in buf.split(b"\n")[:-1] if x.strip()]
