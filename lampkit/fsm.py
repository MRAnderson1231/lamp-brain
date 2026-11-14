"""Two-layer state machine.

Context layer: sleep -> arriving -> studying <-> {exam, break, away} -> sleep.
Study layer (only while studying or in exam): engaged, confused, frustrated, bored, fatigued,
phone, low. Each study state keeps a smoothed score of its evidence and becomes active with
hysteresis: score above `enter` for `dwell` seconds, inactive again below `exit`. The current
study state is the active one with the highest priority.

Frustration follows D'Mello & Graesser's confusion -> frustration path: it can only become
active after confusion (within `frustration_memory` seconds), unless its evidence alone is
`strong`.
"""
from __future__ import annotations

from typing import Callable

from .estimate import Ema
from .types import (CONFUSED, CTX_ARRIVING, CTX_AWAY, CTX_BREAK, CTX_EXAM, CTX_SLEEP,
                    CTX_STUDYING, ENGAGED, FRUSTRATED, STATE_ENTER, STUDY_STATES, Event)

Emit = Callable[[Event], object]


class StudyTrack:
    def __init__(self, name: str, c: dict):
        self.name = name
        self.enter, self.exit, self.dwell = c["enter"], c["exit"], c["dwell"]
        self.priority = c["priority"]
        self.score = Ema(c["tau"])
        self.active = False
        self.above_since: float | None = None

    def update(self, t: float, evidence: float, allowed: bool) -> None:
        s = self.score.update(t, evidence)
        if self.active:
            if s < self.exit:
                self.active = False
                self.above_since = None
            return
        if s >= self.enter and allowed:
            if self.above_since is None:
                self.above_since = t
            if t - self.above_since >= self.dwell:
                self.active = True
        else:
            self.above_since = None

    def reset(self) -> None:
        self.active = False
        self.above_since = None
        self.score.value = 0.0


class StateMachine:
    def __init__(self, cfg: dict, emit: Emit):
        c = cfg["fsm"]
        self.c = c
        self.emit = emit
        self.tracks = {s: StudyTrack(s, c["study"][s]) for s in STUDY_STATES if s != ENGAGED}
        self.context = CTX_SLEEP
        self.study = ENGAGED
        self.since = {"context": 0.0, "study": 0.0}
        self.absent_since: float | None = None
        self.present_since: float | None = None
        self.last_confused: float = -1e9

    # ---- helpers ---------------------------------------------------------------------------
    def _set(self, layer: str, state: str, t: float, reason) -> None:
        prev = self.context if layer == "context" else self.study
        if prev == state:
            return
        if layer == "context":
            self.context = state
        else:
            self.study = state
        self.since[layer] = t
        self.emit(Event(t, STATE_ENTER, {"layer": layer, "state": state, "prev": prev, "reason": reason}, "fsm"))

    def time_in(self, layer: str, t: float) -> float:
        return t - self.since[layer]

    # ---- tick --------------------------------------------------------------------------------
    def tick(self, t: float, evidence: dict, why: dict, feats: dict, exam: bool, on_break: bool) -> None:
        present = feats["present"] > 0.5
        if present:
            self.absent_since = None
            self.present_since = self.present_since if self.present_since is not None else t
        else:
            self.present_since = None
            self.absent_since = self.absent_since if self.absent_since is not None else t
        absent_for = (t - self.absent_since) if self.absent_since is not None else 0.0
        present_for = (t - self.present_since) if self.present_since is not None else 0.0
        c = self.c
        ctx = self.context

        if ctx == CTX_SLEEP:
            if present_for >= c["arrive_after"]:
                self._set("context", CTX_ARRIVING, t, "someone sat down")
        elif ctx == CTX_ARRIVING:
            if self.time_in("context", t) >= c["hello_seconds"]:
                self._set("context", CTX_EXAM if exam else CTX_STUDYING, t, "greeted")
        elif ctx in (CTX_STUDYING, CTX_EXAM):
            if absent_for >= c["away_after"]:
                self._set("context", CTX_AWAY, t, "seat empty for %.0fs" % absent_for)
            elif on_break:
                self._set("context", CTX_BREAK, t, "break accepted")
            elif exam and ctx != CTX_EXAM:
                self._set("context", CTX_EXAM, t, "exam mode on")
            elif not exam and ctx == CTX_EXAM:
                self._set("context", CTX_STUDYING, t, "exam mode off")
        elif ctx == CTX_AWAY:
            if present_for >= c["arrive_after"]:
                self._set("context", CTX_ARRIVING, t, "came back")
            elif absent_for >= c["sleep_after"]:
                self._set("context", CTX_SLEEP, t, "nobody for %.0fs" % absent_for)
        elif ctx == CTX_BREAK:
            if not on_break and present:
                self._set("context", CTX_STUDYING, t, "break over")
            elif absent_for >= c["sleep_after"] + c["break_grace"]:
                self._set("context", CTX_SLEEP, t, "long break")

        if self.context not in (CTX_STUDYING, CTX_EXAM):
            for tr in self.tracks.values():
                tr.reset()
            self._set("study", ENGAGED, t, "context %s" % self.context)
            return

        if self.tracks[CONFUSED].active:
            self.last_confused = t
        recent_confusion = (t - self.last_confused) <= c["frustration_memory"]
        for name, tr in self.tracks.items():
            allowed = True
            if name == FRUSTRATED:
                allowed = recent_confusion or evidence.get(name, 0.0) >= c["study"][name]["strong"]
            tr.update(t, evidence.get(name, 0.0), allowed)

        active = [tr for tr in self.tracks.values() if tr.active]
        best = max(active, key=lambda tr: tr.priority).name if active else ENGAGED
        if best != self.study:
            reason = why.get(best) if best != ENGAGED else "no state above threshold"
            self._set("study", best, t, reason)
