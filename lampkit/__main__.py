"""lampkit command line.

    python -m lampkit simulate scenarios/stuck.json            # print the decision timeline
    python -m lampkit simulate scenarios/demo.json --profile twin --realtime   # drive Blender live
    python -m lampkit replay logs/x.jsonl --set fsm.study.confused.enter=0.6
    python -m lampkit run --profile desk                        # webcam + Margin bridge
    python -m lampkit mock-ipad app.stuck '{"conf": 0.8, "region": [0.2, 0.3, 0.3, 0.05]}'
    python -m lampkit config desk                               # print the merged profile
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from .config import load_profile
from .infra import ManualClock
from .types import (APP_REQUEST, INTERVENE, OUTCOME, PARAMS, PLAN, STATE_ENTER, VETO, Event)

SHOW = {STATE_ENTER, INTERVENE, VETO, PLAN, OUTCOME, APP_REQUEST, "budget", PARAMS, "outcome.unscored"}


def fmt(ev: Event) -> str | None:
    d = ev.data
    if ev.kind == STATE_ENTER:
        r = d["reason"]
        r = ", ".join("%s %.2f" % (k, v) for k, v in r) if isinstance(r, list) else r
        return "%-8s %-9s %s -> %s   (%s)" % ("state", d["layer"], d["prev"], d["state"], r)
    if ev.kind == INTERVENE:
        return "%-8s #%d %s  target=%s level=%d motion=%s  (%s)" % (
            "act", d["id"], d["intent"], d["target"], d["level"], d["motion"], d["reason"])
    if ev.kind == VETO:
        return "%-8s %s blocked by %s" % ("veto", d["data"].get("intent", d["event"]), d["by"])
    if ev.kind == PLAN:
        prims = "+".join("%s×%.1f" % (p[0], p[1]) for p in d["primitives"]) or "functional only"
        return "%-8s %s  γ=%.2f  %s%s  %.1fs  F=%.2f E=%.2f  (%sms)" % (
            "move", d["intent"], d["gamma"], prims, " (head leads)" if d["anticipate"] else "",
            d["duration"], d["score"]["F"], d["score"]["E"], d["plan_ms"])
    if ev.kind == "outcome.unscored":
        return "outcome  #%d %s unscored (%s)" % (d["intervention"], d["intent"], d["reason"])
    if ev.kind == OUTCOME:
        return "%-8s #%d %s %s after %.0fs" % ("outcome", d["intervention"], d["intent"],
                                              "success" if d["success"] else ("dismissed" if d["dismissed"] else "no effect"),
                                              d["latency"])
    if ev.kind == APP_REQUEST:
        return "%-8s -> Margin %s" % ("request", d["action"])
    if ev.kind == "budget":
        return "%-8s %s skipped, %d interventions this hour" % ("budget", d["intent"], d["used"])
    if ev.kind == PARAMS:
        return "%-8s %s  %s" % ("params", d["context"], d["params"])
    return None


def print_timeline(events, t0: float = 0.0) -> None:
    for ev in events:
        if ev.kind in SHOW:
            line = fmt(ev)
            if line:
                print("%7.2fs  %s" % (ev.t - t0, line))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="lampkit", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p, profile):
        p.add_argument("--profile", default=profile)
        p.add_argument("--set", action="append", default=[], metavar="KEY=VALUE", help="override a profile value")

    p = sub.add_parser("simulate", help="run a scenario file through the whole pipeline")
    p.add_argument("scenario")
    common(p, None)
    p.add_argument("--dt", type=float, default=0.05)
    p.add_argument("--log", help="write the event log here")
    p.add_argument("--realtime", action="store_true", help="tick at wall-clock speed (for the Blender twin)")
    p.add_argument("--seed", type=int, default=0)

    p = sub.add_parser("replay", help="rebuild a session from a log and compare decisions")
    p.add_argument("log")
    common(p, None)

    p = sub.add_parser("run", help="live: camera, VLM, Margin bridge, body from the profile")
    common(p, "desk")
    p.add_argument("--log", default=None)
    p.add_argument("--scenario", help="scripted sensor inputs in real time (no real-camera claim)")
    p.add_argument("--duration", type=float, help="stop after this many seconds")

    p = sub.add_parser("mock-ipad", help="send one Margin event to a running lamp")
    p.add_argument("kind")
    p.add_argument("data", nargs="?", default="{}")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=7788)
    p.add_argument("--listen", type=float, default=0.0, help="seconds to wait for lamp requests")

    p = sub.add_parser("config", help="print a merged profile")
    p.add_argument("profile")
    p.add_argument("--set", action="append", default=[])

    a = ap.parse_args(argv)

    if a.cmd == "config":
        print(json.dumps(load_profile(a.profile, a.set), indent=2, ensure_ascii=False))
        return 0

    if a.cmd == "mock-ipad":
        from .bridge import send_events
        replies = send_events(a.host, a.port, [{"kind": a.kind, "data": json.loads(a.data)}], a.listen)
        for r in replies:
            print(json.dumps(r, ensure_ascii=False))
        return 0

    cfg = load_profile(a.profile, a.set) if a.profile else None
    if a.cmd == "replay" and a.set and not a.profile:
        ap.error("--set on replay requires an explicit --profile")

    if a.cmd == "simulate":
        from .runtime import Runtime
        from .sensors import ScriptedSensor
        sc = ScriptedSensor(a.scenario)
        cfg = load_profile(a.profile or sc.profile, a.set)
        rt = Runtime(cfg, ManualClock(0.0), [sc], log_path=a.log, seed=a.seed)
        if a.realtime:
            rt.bus.on("", lambda ev: ev.kind in SHOW and fmt(ev) and print("%7.2fs  %s" % (ev.t, fmt(ev)), flush=True))
            rt.simulate(sc.duration, a.dt, realtime=True)
        else:
            rt.simulate(sc.duration, a.dt)
            print_timeline(rt.bus.history)
        if sc.expect:
            from .expect import check
            fails = check(sc.expect, rt.bus.history)
            print("\nexpectations: " + ("ok" if not fails else "FAILED\n  " + "\n  ".join(fails)))
            return 1 if fails else 0
        return 0

    if a.cmd == "replay":
        from .replay import replay
        res = replay(a.log, cfg)
        print_timeline(res["events"])
        print("\ndecisions identical to the recording:", res["identical"])
        return 0 if res["identical"] else 1

    if a.cmd == "run":
        from .infra import Clock
        from .runtime import Runtime
        clock = Clock()
        sensors = []
        if cfg['local_context']['enabled']:
            from .sensors.local_context import LocalContextSensor
            sensors.append(LocalContextSensor(cfg))
        if cfg['decision']['enabled']:
            from .sensors.decision import DecisionSensor, JevProvider
            sensors.append(DecisionSensor(cfg, JevProvider(cfg)))
        if a.scenario:
            from .sensors import ScriptedSensor
            sc = ScriptedSensor(a.scenario)
            offset = clock.now()
            for event in sc.events:
                event.t += offset
            sensors.append(sc)
            print("SCRIPTED INPUTS:", a.scenario)
        if cfg["camera"].get("enabled"):
            from .sensors.camera import CameraSensor
            cam = CameraSensor(cfg, clock)
            sensors.append(cam)
            if cfg["vlm"].get("enabled"):
                from .sensors.vlm import VlmSensor
                sensors.append(VlmSensor(cfg, clock, cam.frame))
        bridge = None
        if cfg["bridge"].get("enabled"):
            from .bridge import IPadBridge
            bridge = IPadBridge(clock, **{k: v for k, v in cfg["bridge"].items() if k != "enabled"})
            print("waiting for Margin on port %d" % cfg["bridge"]["port"])
        log = a.log or "logs/%s.jsonl" % time.strftime("%Y%m%d-%H%M%S")
        rt = Runtime(cfg, clock, sensors, bridge=bridge, log_path=log)
        rt.bus.on("", lambda ev: ev.kind in SHOW and fmt(ev) and print("%7.2fs  %s" % (ev.t, fmt(ev)), flush=True))
        print("logging to", log)
        rt.run(cfg["loop_hz"], duration=a.duration)
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
