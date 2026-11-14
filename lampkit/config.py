"""Profiles: layered JSON configs.

A profile names the profile it `extends`; layers are deep-merged in order, then `--set a.b=c`
overrides are applied on top. `lampkit config <profile>` prints the merged result.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

PROFILE_DIR = Path(__file__).resolve().parent.parent / "profiles"


def deep_merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def _parse_value(text: str) -> Any:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def set_path(cfg: dict, dotted: str, value: Any) -> None:
    keys = dotted.split(".")
    node = cfg
    for k in keys[:-1]:
        node = node.setdefault(k, {})
    node[keys[-1]] = value


def load_profile(name_or_path: str, overrides: list[str] | None = None) -> dict:
    path = Path(name_or_path)
    if not path.suffix:
        path = PROFILE_DIR / (name_or_path + ".json")
    layers, seen = [], set()
    while True:
        if path in seen:
            raise ValueError("profile cycle at %s" % path)
        seen.add(path)
        layer = json.loads(path.read_text())
        layers.append(layer)
        parent = layer.pop("extends", None)
        if not parent:
            break
        path = PROFILE_DIR / (parent + ".json")
    cfg: dict = {}
    for layer in reversed(layers):
        cfg = deep_merge(cfg, layer)
    for item in overrides or []:
        key, _, value = item.partition("=")
        set_path(cfg, key.strip(), _parse_value(value.strip()))
    return cfg
