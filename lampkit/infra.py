"""Clock, append-only event log, and the event bus.

The bus has two kinds of hooks:
  * listeners observe events (`on`);
  * interceptors run in registration order before listeners and may rewrite or veto an
    event by returning a new event or None (`intercept`). Exam mode and the experiment
    conditions are interceptors, so they hold no matter which module emitted the event.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Callable, Iterator

from .types import Event, VETO

Listener = Callable[[Event], None]
Interceptor = Callable[[Event], "Event | None"]


class Clock:
    def now(self) -> float:
        return time.monotonic()


class ManualClock(Clock):
    """Used by the simulator and replay: time only moves when told to."""

    def __init__(self, t: float = 0.0):
        self.t = t

    def now(self) -> float:
        return self.t

    def advance(self, dt: float) -> None:
        self.t += dt


class EventLog:
    def __init__(self, path: str | Path | None):
        self.path = Path(path) if path else None
        self._f = None
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            # line-buffered: a killed or crashed session still leaves a replayable log
            self._f = self.path.open("a", encoding="utf-8", buffering=1)

    def append(self, ev: Event) -> None:
        if self._f:
            self._f.write(ev.to_json() + "\n")

    def flush(self) -> None:
        if self._f:
            self._f.flush()

    def close(self) -> None:
        if self._f:
            self._f.close()
            self._f = None

    @staticmethod
    def read(path: str | Path) -> Iterator[Event]:
        with Path(path).open(encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    yield Event.from_json(line)


class Bus:
    def __init__(self, log: EventLog | None = None, keep: bool = True, history_limit: int | None = None):
        self.log = log or EventLog(None)
        self.keep = keep
        self.history_limit = history_limit
        self.history: list[Event] = []
        self._listeners: list[tuple[str, Listener]] = []
        self._interceptors: list[tuple[str, str, Interceptor]] = []

    def on(self, prefix: str, fn: Listener) -> None:
        self._listeners.append((prefix, fn))

    def intercept(self, prefix: str, fn: Interceptor, name: str) -> None:
        self._interceptors.append((prefix, name, fn))

    def emit(self, ev: Event) -> Event | None:
        for prefix, name, fn in self._interceptors:
            if ev.kind.startswith(prefix):
                out = fn(ev)
                if out is None:
                    self._record(Event(ev.t, VETO, {"event": ev.kind, "data": ev.data, "by": name}, "bus"))
                    return None
                ev = out
        self._record(ev)
        for prefix, fn in self._listeners:
            if ev.kind.startswith(prefix):
                fn(ev)
        return ev

    def _record(self, ev: Event) -> None:
        self.log.append(ev)
        if self.keep:
            self.history.append(ev)
            if self.history_limit and len(self.history) > self.history_limit:
                del self.history[:-self.history_limit]
