"""Per-user tuning with Thompson sampling.

Only parameters are learned, never behaviours: how long to let confusion run before helping,
which rung of the ladder to start on, and a personal multiplier on ELEGNT's expressive weight
gamma. Each context (the study state that triggered an intervention) has its own Beta
posterior per arm. Hard limits (exam mode, interruption budget) live in the policy and the
bus interceptors, out of reach of anything learned here.
"""
from __future__ import annotations

import itertools
import json
import random
from pathlib import Path


class Personalizer:
    def __init__(self, cfg: dict, seed: int | None = None):
        c = cfg["personalize"]
        self.enabled = c.get("enabled", True)
        names = sorted(c["arms"])
        self.names = names
        self.arms = [dict(zip(names, vals)) for vals in itertools.product(*(c["arms"][n] for n in names))]
        self.default = c["default"]
        self.path = Path(c["state_file"]).expanduser() if c.get("state_file") else None
        self.rng = random.Random(seed)
        self.post: dict[str, list[list[float]]] = {}
        if self.path and self.path.exists():
            self.post = json.loads(self.path.read_text())

    def _ab(self, context: str) -> list[list[float]]:
        if context not in self.post or len(self.post[context]) != len(self.arms):
            self.post[context] = [[1.0, 1.0] for _ in self.arms]
        return self.post[context]

    def choose(self, context: str) -> tuple[int, dict]:
        if not self.enabled:
            return -1, dict(self.default)
        ab = self._ab(context)
        draws = [self.rng.betavariate(a, b) for a, b in ab]
        i = max(range(len(draws)), key=draws.__getitem__)
        return i, dict(self.arms[i])

    def update(self, context: str, arm: int, reward: float) -> None:
        if arm < 0 or not self.enabled:
            return
        ab = self._ab(context)
        ab[arm][0] += reward
        ab[arm][1] += 1.0 - reward
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.post))
            tmp.replace(self.path)

    def best(self, context: str) -> dict:
        ab = self._ab(context)
        i = max(range(len(ab)), key=lambda k: ab[k][0] / (ab[k][0] + ab[k][1]))
        return dict(self.arms[i])
