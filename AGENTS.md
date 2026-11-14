# Working on lamp-brain

`lampkit/` is the runtime; read `docs/ARCHITECTURE.md` first. `lamp_brain.py`,
`lamp_controller.py` and `app/` are the older FastVLM mood-mirror demo and are independent of it.

## Commands

```bash
uv run --no-project --python 3.12 --with pytest pytest -q    # all tests, ~5 s, no models needed
python -m lampkit simulate scenarios/<name>.json             # timeline + expectation check
```

## Invariants (tests enforce them; do not weaken a test to pass it)

- No LLM or VLM output may trigger an action directly. Models emit `obs.*` evidence only; the
  estimator → fsm → policy chain decides.
- Layers import downward only (`tests/test_replay_and_layers.py::ALLOWED`).
- The core is deterministic given the event log and the seed: no wall-clock reads, no
  unseeded randomness and no I/O in `estimate`, `fsm`, `policy`, `personalize` or `motion`
  (apart from the personalizer's optional `state_file`).
  Time always comes from `Event.t` or the `t` argument.
- Exam mode never moves the body and never asks Margin for anything.
- Every budgeted intent counts against `policy.budget_per_hour`.
- Every tunable number lives in `profiles/base.json`. Code reads it; code does not hard-code it.
- A behaviour change comes with a scenario in `scenarios/`, including an `expect` block.

## Conventions

- Angles are in degrees, lengths in metres, in the desk frame: lamp base at the origin, +x
  right, −y toward the person, +z up.
- Rig channels: yaw (swivel), low, up, nod, turn (head), hop, squash, glow, warmth.
  `motion/rig.json` is exported from `design/blender/margin_lamp_behaviours.blend`.
- Licences: FastVLM is research-only; use SmolVLM or Moondream before shipping anything.
  Avoid AGPL detectors (Ultralytics).
