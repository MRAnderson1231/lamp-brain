"""Sensors turn the world into input events. A sensor only needs `poll(t) -> list[Event]`.

Implementations: `ScriptedSensor` (scenario files, for tests and demos), `ReplaySensor`
(input events from a recorded log), and in `camera.py` / `vlm.py` the live webcam pipeline
(MediaPipe face/pose/phone) and the FastVLM state scorer.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Protocol

from ..types import Event


class Sensor(Protocol):
    def poll(self, t: float) -> list[Event]: ...


class ReplaySensor:
    def __init__(self, events: Iterable[Event]):
        self.events = sorted((e for e in events if e.is_input), key=lambda e: e.t)
        self.i = 0

    @property
    def end(self) -> float:
        return self.events[-1].t if self.events else 0.0

    def poll(self, t: float) -> list[Event]:
        out = []
        while self.i < len(self.events) and self.events[self.i].t <= t + 1e-9:
            out.append(self.events[self.i])
            self.i += 1
        return out


class ScriptedSensor(ReplaySensor):
    """A scenario is a JSON file:

        {"duration": 120,
         "streams": [{"kind": "obs.face", "every": 0.1, "segments": [
                        {"from": 0, "to": 20, "data": {...}}, ...]}],
         "events":  [{"t": 30, "kind": "app.stuck", "data": {"conf": 0.8}}]}

    Streams repeat their segment's data every `every` seconds; segment data is merged onto
    the stream's `base` data. Events fire once.
    """

    def __init__(self, path: str | Path):
        spec = json.loads(Path(path).read_text())
        self.name = Path(path).stem
        self.profile = spec.get('profile', 'sim')
        self.duration = float(spec["duration"])
        self.expect = spec.get("expect", {})
        evs: list[Event] = []
        for st in spec.get("streams", []):
            base = st.get("base", {})
            for seg in st["segments"]:
                t = float(seg["from"])
                while t < float(seg["to"]) - 1e-9:
                    evs.append(Event(round(t, 4), st["kind"], _merge(base, seg.get("data", {})), "script"))
                    t += float(st["every"])
        for e in spec.get("events", []):
            evs.append(Event(float(e["t"]), e["kind"], e.get("data", {}), "script"))
        super().__init__(evs)


def _merge(a: dict, b: dict) -> dict:
    out = dict(a)
    for k, v in b.items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out
