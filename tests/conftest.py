import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lampkit.bodies import NullBody  # noqa: E402
from lampkit.config import load_profile  # noqa: E402
from lampkit.infra import ManualClock  # noqa: E402
from lampkit.runtime import Runtime  # noqa: E402
from lampkit.sensors import ScriptedSensor  # noqa: E402

SCENARIOS = ROOT / "scenarios"


def simulate(name: str, overrides=(), seed: int = 0, log_path=None, dt: float = 0.05):
    """Runs scenarios/<name>.json in simulated time. Returns (runtime, scenario, body)."""
    sc = ScriptedSensor(SCENARIOS / (name + ".json"))
    cfg = load_profile(sc.profile, list(overrides))
    body = NullBody(keep=True)
    rt = Runtime(cfg, ManualClock(0.0), [sc], body=body, log_path=log_path, seed=seed)
    rt.simulate(sc.duration, dt)
    return rt, sc, body


@pytest.fixture
def run():
    return simulate
