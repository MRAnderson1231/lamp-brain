"""Replay recorded tick batches with a snapshot of configuration and learned state."""
from __future__ import annotations
import copy
import json
from .bodies import NullBody
from .infra import EventLog, ManualClock
from .runtime import Runtime
from .sensors import ReplaySensor
from .types import Event

CHECKED = {"state.enter", "intervene", "lamp.request", "veto", "outcome", "params", "motion.plan", "budget", "outcome.unscored"}

def decisions(events: list[Event]) -> list[tuple]:
    out = []
    for e in events:
        if e.kind in CHECKED:
            data = {k: v for k, v in e.data.items() if k != "plan_ms"}
            out.append((e.t, e.kind, json.loads(json.dumps(data))))
    return out


def replay(log_path: str, cfg: dict | None = None, dt: float = 0.05, tail: float = 2.0) -> dict:
    recorded = list(EventLog.read(log_path))
    metas = [e.data for e in recorded if e.kind == "meta"]
    if len(metas) != 1:
        raise ValueError("Replay expects exactly one session per log")
    meta = metas[0]
    config = copy.deepcopy(cfg if cfg is not None else meta.get("config"))
    if config is None:
        raise ValueError("Legacy log requires an explicit profile")
    config["personalize"]["state_file"] = None  # replay must never read/write current user learning
    ticks = []
    for ev in recorded:
        if ev.kind == "tick":
            ticks.append((ev.t, []))
        elif ev.is_input and ticks:
            ticks[-1][1].append(ev)
    class BatchSensor:
        batch = []
        def poll(self, t):
            batch, self.batch = self.batch, []
            return batch
    sensor = BatchSensor() if ticks else ReplaySensor(recorded)
    clock = ManualClock(recorded[0].t if recorded else 0.0)
    rt = Runtime(config, clock, [sensor], NullBody(), seed=meta.get("seed", 0))
    rt.pz.post = copy.deepcopy(meta.get("posterior", {}))
    if ticks:
        for t, batch in ticks:
            clock.t, sensor.batch = t, batch
            rt.tick()
    else:
        rt.simulate(sensor.end + tail, dt)
    old, new = decisions(recorded), decisions(rt.bus.history)
    return {"recorded": old, "replayed": new, "identical": old == new, "events": rt.bus.history}
