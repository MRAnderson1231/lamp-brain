"""Wires the layers together and runs the loop.

    sensors / iPad bridge --obs.*, app.*--> Estimator --evidence--> StateMachine --state.enter-->
    Policy --intervene--> [interceptors: exam mode, experiment condition] --> Generator --plan-->
    Player --pose--> Body

Everything passes through one Bus and lands in one append-only log, so `lampkit replay`
can rebuild any session from its input events.
"""
from __future__ import annotations

import copy
import signal
import time

from .bodies import make_body
from .estimate import Estimator
from .fsm import StateMachine
from .infra import Bus, Clock, EventLog, ManualClock
from .motion.generator import Generator, gamma_for, light_only
from .motion.kinematics import Rig
from .motion.player import Player
from .personalize import Personalizer
from .policy import Policy, install_interceptors
from .types import (APP_CORRECT, APP_REQUEST, APP_WRONG, CTX_EXAM, CTX_STUDYING, EVIDENCE,
                    INTERVENE, MOMENT, PLAN, STATE_ENTER, USER_PAT, Event, Intervention)


class Runtime:
    def __init__(self, cfg: dict, clock: Clock | None = None, sensors=None, body=None, bridge=None,
                 log_path=None, seed: int = 0):
        self.cfg = cfg
        self.clock = clock or Clock()
        self.sensors = list(sensors or [])
        self.body = body or make_body(cfg)
        self.bridge = bridge
        self.bus = Bus(EventLog(log_path), history_limit=None if isinstance(self.clock, ManualClock) else cfg["log"]["history_limit"])
        self.est = Estimator(cfg)
        self.fsm = StateMachine(cfg, self.bus.emit)
        self.pz = Personalizer(cfg, seed=seed)
        self.policy = Policy(cfg, self.bus.emit, self.pz)
        install_interceptors(self.bus, cfg, lambda: CTX_EXAM if self.est.exam else self.fsm.context)
        k = cfg["kinematics"]
        self.rig = Rig(k["scale"], k["head_scale"], limits={c: tuple(v) for c, v in k["limits"].items()})
        self.gen = Generator(cfg, self.rig)
        start = dict(cfg["motion"]["poses"]["sleep"], turn=0.0)
        start.update(glow=cfg["intents"]["sleep"]["light"]["glow"], warmth=cfg["intents"]["sleep"]["light"]["warmth"])
        self.player = Player(cfg, start)
        self.condition = cfg.get("experiment", {}).get("condition", "expressive")
        self.last_t: float | None = None
        self.next_evidence = 0.0

        self.bus.on("obs.", self.est.observe)
        self.bus.on("app.", self._on_app)
        self.bus.on(USER_PAT, self.est.observe)
        self.bus.on(USER_PAT, self.policy.on_event)
        self.bus.on(STATE_ENTER, self.policy.on_event)
        self.bus.on(MOMENT, self.policy.on_event)
        self.bus.on(INTERVENE, self._on_intervene)
        if bridge is not None:
            self.bus.on(APP_REQUEST, bridge.send)
        self.bus.emit(Event(self.clock.now(), "meta", {"seed": seed, "condition": self.condition,
                                                       "profile": cfg.get("name", ""), "format": 2,
                                                       "config": copy.deepcopy(cfg), "posterior": copy.deepcopy(self.pz.post)}, "runtime"))

    # ---- listeners ---------------------------------------------------------------------------
    def _on_app(self, ev: Event) -> None:
        was_exam = self.est.exam
        self.est.observe(ev)
        if self.est.exam and not was_exam:
            self.player.freeze()
        if ev.kind in (APP_CORRECT, APP_WRONG) and self.fsm.context in (CTX_STUDYING, CTX_EXAM):
            self.bus.emit(Event(ev.t, MOMENT, {"name": "correct" if ev.kind == APP_CORRECT else "wrong"}, "runtime"))

    def world(self) -> dict:
        w = {"face": self.est.face_pos}
        r = self.est.stuck_region
        if r and self.est.stuck_conf > 0.1:
            w["hint"] = self.screen_point(r[0] + r[2] / 2, r[1] + r[3] / 2)
        return w

    def screen_point(self, u: float, v: float):
        """Screen coordinates (0..1, origin top-left) -> desk coordinates."""
        import math
        s = self.cfg["motion"]["screen"]
        dx, dy = (u - 0.5) * s["size"][0], (0.5 - v) * s["size"][1]
        a = math.radians(s["yaw_deg"])
        cx, cy, cz = s["center"]
        return (cx + dx * math.cos(a) - dy * math.sin(a), cy + dx * math.sin(a) + dy * math.cos(a), cz)

    def _on_intervene(self, ev: Event) -> None:
        iv = Intervention(**ev.data)
        if not iv.motion and not iv.light:
            return
        gamma = gamma_for(self.cfg, iv, self.policy.arm[1].get("gamma_mult", 1.0))
        t0 = time.perf_counter()
        if iv.motion:
            plan = self.gen.plan(iv, self.player.pose, self.world(), gamma)
        else:
            plan = light_only(iv, self.player.pose, self.cfg, self.gen.dt)
        ms = (time.perf_counter() - t0) * 1000.0
        accepted = self.player.play(plan, ev.t)
        self.bus.emit(Event(ev.t, PLAN, dict(plan.summary(), accepted=accepted, plan_ms=round(ms, 1)), "motion"))

    # ---- loop --------------------------------------------------------------------------------
    def tick(self) -> None:
        t = self.clock.now()
        dt = 0.0 if self.last_t is None else t - self.last_t
        self.last_t = t
        self.bus.emit(Event(t, "tick", {}, "runtime"))
        incoming = []
        for s in self.sensors:
            incoming += s.poll(t)
        if self.bridge is not None:
            incoming += self.bridge.poll(t)
        for ev in sorted(incoming, key=lambda e: e.t):
            self.bus.emit(ev)
        evidence, why, feats = self.est.evidence(t)
        self.fsm.tick(t, evidence, why, feats, self.est.exam, self.est.on_break)
        self.policy.tick(t)
        if t >= self.next_evidence:
            self.next_evidence = t + self.cfg["log"]["evidence_every"]
            self.bus.emit(Event(t, EVIDENCE, {k: round(v, 3) for k, v in evidence.items()}, "estimate"))
        self.player.breathing = self.condition == "expressive" and not self.est.exam and self.fsm.context != CTX_EXAM
        if self.condition != "app_only" and dt > 0:
            self.body.apply(t, self.player.step(t, dt, freeze_motion=self.est.exam or self.fsm.context == CTX_EXAM or self.condition == "static"))

    def simulate(self, until: float, dt: float = 0.05, realtime: bool = False) -> None:
        assert isinstance(self.clock, ManualClock)
        while self.clock.now() <= until + 1e-9:
            self.tick()
            if realtime:
                time.sleep(dt)
            self.clock.advance(dt)
        self.bus.log.flush()

    def run(self, hz: float = 30.0, duration: float | None = None) -> None:
        period = 1.0 / hz

        def _stop(signum, frame):
            raise KeyboardInterrupt
        signal.signal(signal.SIGTERM, _stop)
        deadline = None if duration is None else time.monotonic() + duration
        try:
            while deadline is None or time.monotonic() < deadline:
                t0 = time.monotonic()
                self.tick()
                time.sleep(max(0.0, period - (time.monotonic() - t0)))
        except KeyboardInterrupt:
            pass
        finally:
            self.close()

    def close(self) -> None:
        self.bus.log.close()
        for resource in [*self.sensors, self.bridge, self.body]:
            if resource is not None and hasattr(resource, "close"):
                resource.close()
