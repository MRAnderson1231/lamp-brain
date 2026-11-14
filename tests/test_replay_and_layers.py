import ast
from pathlib import Path

from lampkit.config import load_profile
from lampkit.replay import replay

from conftest import simulate

PKG = Path(__file__).resolve().parents[1] / "lampkit"

# A module may only import from its own layer or the layers listed for it.
# The core (estimate -> fsm -> policy) never touches sensors, bodies, motion or the network.
ALLOWED = {
    "types": set(),
    "config": set(),
    "infra": {"types"},
    "expect": {"types"},
    "estimate": {"types"},
    "fsm": {"types", "estimate"},
    "personalize": {"types"},
    "policy": {"types", "personalize"},
    "motion": {"types", "motion"},
    "sensors": {"types", "infra", "sensors"},
    "bodies": {"types"},
    "bridge": {"types"},
    "control": {"control", "types", "motion"},
}


def _layer(path: Path) -> str:
    rel = path.relative_to(PKG)
    return rel.parts[0] if len(rel.parts) > 1 else rel.stem


def test_layers_only_import_downward():
    bad = []
    for path in PKG.rglob("*.py"):
        layer = _layer(path)
        if layer not in ALLOWED:
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ImportFrom) and node.level > 0:
                pkg_parts = list(path.relative_to(PKG).parts[:-1])
                base = pkg_parts[:len(pkg_parts) - (node.level - 1)]
                full = base + (node.module or "").split(".")
                mod = full[0] if full and full[0] else ""
                if not mod:
                    continue
                if mod != layer and mod not in ALLOWED[layer]:
                    bad.append("%s imports %s" % (path.relative_to(PKG), mod))
    assert bad == []


def test_replay_reproduces_every_decision(tmp_path):
    log = tmp_path / "demo.jsonl"
    simulate("demo", seed=7, log_path=log)
    result = replay(str(log), load_profile("sim"))
    assert result["identical"], result.get("diff")
