"""Rules that must hold whatever the estimator or the motion generator decide."""

from lampkit.types import APP_REQUEST, INTERVENE, VETO

from conftest import simulate


def test_exam_mode_never_moves_the_body():
    rt, _, body = simulate("exam", ["personalize.enabled=false"])
    exam_start = next(e.t for e in rt.bus.history if e.kind == "state.enter" and e.data["state"] == "exam")
    settle = exam_start + 1.0
    frames = [f for f in body.frames if f["t"] > settle]
    for ch in ("yaw", "low", "up", "nod", "turn"):
        span = max(f[ch] for f in frames) - min(f[ch] for f in frames)
        assert span < 0.5, (ch, span)
    assert not [e for e in rt.bus.history if e.kind == APP_REQUEST and e.t > exam_start]


def test_hourly_budget_caps_nudges():
    rt, _, _ = simulate("demo", ["personalize.enabled=false", "policy.budget_per_hour=1"])
    budgeted = {k for k, v in rt.cfg["intents"].items() if v.get("budget")}
    fired = [e for e in rt.bus.history if e.kind == INTERVENE and e.data["intent"] in budgeted]
    assert len(fired) == 1


def test_app_only_condition_keeps_the_lamp_still_but_still_asks_margin():
    rt, _, body = simulate("stuck", ["personalize.enabled=false", "experiment.condition=app_only"])
    assert body.frames == []
    assert [e.data["action"] for e in rt.bus.history if e.kind == APP_REQUEST] == ["show_hint"]
    assert all(not e.data["motion"] for e in rt.bus.history if e.kind == INTERVENE)
    assert any(e.kind == VETO for e in rt.bus.history)


def test_static_condition_lights_but_never_moves():
    rt, _, body = simulate("stuck", ["personalize.enabled=false", "experiment.condition=static"])
    ivs = [e for e in rt.bus.history if e.kind == INTERVENE]
    assert ivs and all(not e.data["motion"] for e in ivs)
    span = max(f["nod"] for f in body.frames[50:]) - min(f["nod"] for f in body.frames[50:])
    assert span < 0.5
    assert max(f["glow"] for f in body.frames) > 1.1


def test_light_stays_dim_and_cool_while_the_phone_is_out():
    _, _, body = simulate("phone", ["personalize.enabled=false"])
    during = [f for f in body.frames if 23.0 < f["t"] < 45.0]
    after = [f for f in body.frames if f["t"] > 50.0]
    assert max(f["glow"] for f in during) < 0.85
    assert max(f["warmth"] for f in during) < 0.4
    assert min(f["glow"] for f in after) > 0.9


def test_an_empty_seat_has_no_study_state():
    rt, _, _ = simulate("away", ["personalize.enabled=false"])
    absent = [e for e in rt.bus.history if e.kind == "evidence" and 33.0 < e.t < 140.0]
    assert absent and all(v == 0.0 for e in absent for k, v in e.data.items() if k != "phone")


def test_body_stays_inside_joint_limits():
    rt, _, body = simulate("demo")
    lim = rt.cfg["kinematics"]["limits"]
    for f in body.frames:
        for ch, (lo, hi) in lim.items():
            assert lo - 1.0 <= f[ch] <= hi + 1.0, (f["t"], ch, f[ch])


def test_body_motion_respects_speed_limits():
    rt, _, body = simulate("demo")
    vmax = rt.cfg["motion"]["spring"]["vmax"]
    for a, b in zip(body.frames, body.frames[1:]):
        dt = b["t"] - a["t"]
        for ch in ("yaw", "low", "up", "nod", "turn"):
            v = abs(b[ch] - a[ch]) / dt
            assert v <= vmax.get(ch, vmax["default"]) * 1.05, (a["t"], ch, v)


def test_pat_dismisses_and_counts_as_failure():
    from lampkit.infra import ManualClock
    from lampkit.config import load_profile
    from lampkit.runtime import Runtime
    from lampkit.sensors import ScriptedSensor, ReplaySensor
    from lampkit.types import Event, OUTCOME
    from conftest import SCENARIOS

    sc = ScriptedSensor(SCENARIOS / "phone.json")
    pat = ReplaySensor([Event(22.0, "user.pat", {}, "test")])
    rt = Runtime(load_profile("sim", ["personalize.enabled=false"]), ManualClock(0.0), [sc, pat])
    rt.simulate(sc.duration)
    outs = [e.data for e in rt.bus.history if e.kind == OUTCOME]
    assert outs and outs[0]["dismissed"] and not outs[0]["success"]
