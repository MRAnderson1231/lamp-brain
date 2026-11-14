"""Every scenario file states what should happen; the runtime has to deliver it."""

import pytest

from lampkit.expect import check
from lampkit.types import INTERVENE, OUTCOME, PLAN, STATE_ENTER

from conftest import SCENARIOS, simulate

NAMES = sorted(p.stem for p in SCENARIOS.glob("*.json"))
FIXED = ["personalize.enabled=false"]


@pytest.mark.parametrize("name", NAMES)
def test_expectations_with_default_params(name):
    rt, sc, _ = simulate(name, FIXED)
    assert check(sc.expect, rt.bus.history) == []


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("seed", [1, 2, 3])
def test_expectations_hold_for_any_personalized_arm(name, seed):
    if name == "stuck":
        pytest.skip("ladder_start=1 legitimately skips glance_hint")
    rt, sc, _ = simulate(name, seed=seed)
    expect = dict(sc.expect)
    if name == "demo":
        expect.pop("intents")
    assert check(expect, rt.bus.history) == []


def test_frustration_never_steps_down_the_ladder():
    for seed in range(6):
        rt, _, _ = simulate("demo", seed=seed)
        levels = []
        for e in rt.bus.history:
            if e.kind == STATE_ENTER and e.data["layer"] == "study" and e.data["state"] not in ("confused", "frustrated"):
                levels = []
            if e.kind == INTERVENE and e.data["intent"] in ("glance_hint", "show_hint", "voice"):
                levels.append(e.data["level"])
        assert levels == sorted(levels), (seed, levels)


def test_hint_outcomes_reward_the_personalizer():
    rt, _, _ = simulate("stuck", FIXED)
    outs = [e.data for e in rt.bus.history if e.kind == OUTCOME]
    assert outs and all(o["success"] for o in outs)


def test_planning_is_fast_enough_for_the_loop():
    rt, _, _ = simulate("demo")
    ms = [e.data["plan_ms"] for e in rt.bus.history if e.kind == PLAN]
    assert ms and max(ms) < 100, ms
