"""From states to interventions.

The policy decides *what* to communicate (an `Intervention`: intent, target, wanted
expressive dimensions, light, optional request to Margin). The motion generator decides
*how* to move. Rules:

  * every intent has a cooldown; nudging intents also count against an hourly budget;
  * confusion gets a waiting window first (productive struggle), then the hint ladder;
  * each tracked intervention gets an outcome after `outcome_window` seconds: success if
    the student is back to engaged, failure if not or if they tapped the shade.

Exam mode and the experiment conditions are bus interceptors (see `install_interceptors`),
so they apply to every intervention regardless of where it came from.
"""
from __future__ import annotations

import copy
from typing import Callable

from .personalize import Personalizer
from .types import (APP_REQUEST, BORED, CONFUSED, CTX_ARRIVING, CTX_AWAY, CTX_BREAK,
                    CTX_EXAM, CTX_SLEEP, CTX_STUDYING, ENGAGED, FATIGUED, FRUSTRATED,
                    INTERVENE, LOW, MOMENT, OUTCOME, PARAMS, PHONE, STATE_ENTER, USER_PAT,
                    Event, Intervention)

Emit = Callable[[Event], "Event | None"]

STUDY_INTENT = {CONFUSED: "attend", BORED: "nudge", FATIGUED: "suggest_break", LOW: "comfort", PHONE: "phone_look"}
CONTEXT_INTENT = {CTX_ARRIVING: "hello", CTX_AWAY: "search", CTX_SLEEP: "sleep", CTX_BREAK: "rest"}


class Policy:
    def __init__(self, cfg: dict, emit: Emit, personalizer: Personalizer):
        self.cfg = cfg
        self.c = cfg["policy"]
        self.intents = cfg["intents"]
        self.emit = emit
        self.pz = personalizer
        self.next_id = 1
        self.last_fired: dict[str, float] = {}
        self.budget_log: list[float] = []
        self.context = CTX_SLEEP
        self.study = ENGAGED
        self.study_since = 0.0
        self.arm: tuple[int, dict] = (-1, dict(self.pz.default))
        self.ladder_level = -1
        self.ladder_next = None
        self.phone_nagged = False
        self.pending: list[dict] = []
        self.quiet_until = 0.0

    # ---- inputs ------------------------------------------------------------------------------
    def on_event(self, ev: Event) -> None:
        if ev.kind == STATE_ENTER:
            d = ev.data
            if d["layer"] == "context":
                self.context = d["state"]
                if d["state"] in CONTEXT_INTENT:
                    self.fire(ev.t, CONTEXT_INTENT[d["state"]], d["state"], reason="context " + d["state"])
                elif d["state"] == CTX_STUDYING and d["prev"] in (CTX_ARRIVING, CTX_BREAK, CTX_EXAM):
                    self.fire(ev.t, "settle", d["state"], reason="back to work")
            else:
                self._enter_study(ev.t, d["state"], d["prev"])
        elif ev.kind == MOMENT:
            name = ev.data["name"]
            self.fire(ev.t, {"correct": "celebrate", "wrong": "hmm"}[name], self.study, reason=name)
        elif ev.kind == USER_PAT:
            self.quiet_until = ev.t + self.c["dismiss_quiet_seconds"]
            for p in self.pending:
                p["dismissed"] = True
            self.ladder_next = None

    def _enter_study(self, t: float, state: str, prev: str) -> None:
        self.study, self.study_since = state, t
        if not (prev == CONFUSED and state == FRUSTRATED):
            # confusion turning into frustration keeps climbing the same ladder, never back down
            self.ladder_level = -1
        self.ladder_next = None
        if state == ENGAGED:
            if prev in (CONFUSED, FRUSTRATED, BORED, PHONE, FATIGUED, LOW) and self.context in (CTX_STUDYING, CTX_EXAM):
                self.fire(t, "settle", state, reason="back to engaged")
            return
        self.arm = self.pz.choose(state)
        self.emit(Event(t, PARAMS, {"context": state, "arm": self.arm[0], "params": self.arm[1]}, "personalize"))
        if state == CONFUSED:
            self.fire(t, "attend", state, reason="confusion noticed")
            self.ladder_next = t + self.arm[1]["confusion_window"]
        elif state == FRUSTRATED:
            self._climb(t, start=True)
        elif state == PHONE:
            self.phone_nagged = False
            self.fire(t, "phone_look", state, reason="phone left the dock")
        else:
            self.fire(t, STUDY_INTENT[state], state, reason=state)

    def _climb(self, t: float, start: bool = False) -> None:
        ladder = self.c["ladder"]
        if start:
            self.ladder_level = max(self.ladder_level, int(self.arm[1]["ladder_start"]) - 1)
        self.ladder_level += 1
        while self.ladder_level < len(ladder) and not self._enabled(ladder[self.ladder_level]):
            self.ladder_level += 1
        if self.ladder_level >= len(ladder):
            self.ladder_next = None
            if start and self.study == FRUSTRATED:
                self.fire(t, "comfort", self.study, reason="hints exhausted")
            return
        intent = ladder[self.ladder_level]
        self.fire(t, intent, self.study, level=self.ladder_level, reason="ladder %d" % self.ladder_level)
        self.ladder_next = t + self.c["ladder_step"]

    # ---- tick --------------------------------------------------------------------------------
    def tick(self, t: float) -> None:
        if self.ladder_next is not None and t >= self.ladder_next and self.study in (CONFUSED, FRUSTRATED):
            if self.study == CONFUSED and self.ladder_level < 0:
                self._climb(t, start=True)
            else:
                self._climb(t)
        if self.study == PHONE and not self.phone_nagged and t - self.study_since >= self.c["phone_nag_after"]:
            self.phone_nagged = True
            self.fire(t, "phone_nag", PHONE, reason="phone still out")
        for p in list(self.pending):
            done = p["dismissed"] or self.study == ENGAGED and self.context in (CTX_STUDYING, CTX_EXAM) \
                or self.context == CTX_BREAK and p["intent"] == "suggest_break"
            if done or t - p["t"] >= self.c["outcome_window"]:
                success = bool(done and not p["dismissed"])
                reward = 1.0 if success else 0.0
                self.pending.remove(p)
                self.pz.update(p["state"], p["arm"], reward)
                self.emit(Event(t, OUTCOME, {"intervention": p["id"], "intent": p["intent"], "state": p["state"],
                                             "success": success, "dismissed": p["dismissed"],
                                             "latency": round(t - p["t"], 2), "reward": reward}, "policy"))

    # ---- firing ------------------------------------------------------------------------------
    def _enabled(self, intent: str) -> bool:
        return bool(self.intents[intent].get("enabled", True))

    def fire(self, t: float, intent: str, state: str, level: int = 0, reason: str = "") -> bool:
        spec = self.intents[intent]
        if t < self.quiet_until and (spec.get("budget") or spec.get("track")):
            return False
        if not self._enabled(intent):
            return False
        if t - self.last_fired.get(intent, -1e9) < spec.get("cooldown", 0):
            return False
        if spec.get("budget", False):
            self.budget_log = [x for x in self.budget_log if t - x < 3600.0]
            if len(self.budget_log) >= self.c["budget_per_hour"]:
                self.emit(Event(t, "budget", {"intent": intent, "used": len(self.budget_log)}, "policy"))
                return False
        iv = Intervention(
            id=self.next_id, t=t, intent=intent, state=state, level=level,
            target=spec.get("target", "work"), express=dict(spec.get("express", {})),
            light=dict(spec.get("light", {})), motion=spec.get("motion", True),
            app=copy.deepcopy(spec.get("app")), reason=reason if isinstance(reason, str) else str(reason))
        out = self.emit(Event(t, INTERVENE, iv.to_dict(), "policy"))
        if out is None:
            return False
        self.next_id += 1
        self.last_fired[intent] = t
        if spec.get("budget", False):
            self.budget_log.append(t)
        if out.data.get("app"):
            self.emit(Event(t, APP_REQUEST, dict(out.data["app"], intervention=iv.id), "policy"))
        if spec.get("track", False) and (out.data.get("motion") or out.data.get("app")):
            # Overlapping interventions confound attribution. Mark prior attempts unscored,
            # rather than rewarding every pending intervention for one return to work.
            for previous in self.pending:
                self.emit(Event(t, "outcome.unscored", {"intervention": previous["id"], "intent": previous["intent"],
                    "state": previous["state"], "success": False, "dismissed": False,
                    "latency": round(t - previous["t"], 2), "reward": None,
                    "evaluated": False, "reason": "superseded"}, "policy"))
            self.pending.clear()
            self.pending.append({"id": iv.id, "t": t, "intent": intent, "state": state, "arm": self.arm[0], "dismissed": False})
        return True


def install_interceptors(bus, cfg: dict, context_of: Callable[[], str]) -> None:
    """Hard rules that hold for every intervention. Order matters: first match wins."""
    c = cfg["policy"]
    condition = cfg.get("experiment", {}).get("condition", "expressive")

    def exam_mode(ev: Event):
        if context_of() != CTX_EXAM:
            return ev
        if ev.data["intent"] not in c["exam_allowed"]:
            return None
        d = dict(ev.data, motion=False, app=None)
        return Event(ev.t, ev.kind, d, ev.src)

    def experiment(ev: Event):
        if condition == "expressive":
            return ev
        if condition == "static":           # lamp present, light only
            return Event(ev.t, ev.kind, dict(ev.data, motion=False), ev.src)
        if condition == "app_only":          # no lamp at all; Margin requests still go through
            if not ev.data.get("app"):
                return None
            return Event(ev.t, ev.kind, dict(ev.data, motion=False, light={}), ev.src)
        raise ValueError("unknown experiment condition %r" % condition)

    bus.intercept(INTERVENE, exam_mode, "exam_mode")
    bus.intercept(INTERVENE, experiment, "experiment:" + condition)
