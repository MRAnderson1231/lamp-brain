# lampkit architecture

Current default: standalone `companion`; see [COMPANION.md](COMPANION.md).
The study/Margin pipeline below remains optional.

The opt-in `proactive` profile adds world fusion, hand-control arbitration, independent
illumination, and continuous head-position IK. See [PROACTIVE_V2.md](PROACTIVE_V2.md)
for the current V2 architecture and sensor contracts. `desk` retains the baseline below.

lampkit is the brain of the Margin desk lamp. It fuses two sources: what Margin (the iPad
app) knows about the work, and what the lamp's own camera sees of the person. It then decides
when to step in and moves the lamp expressively. The runtime is designed for local execution; live sensors and physical hardware remain unvalidated. No language
model sits in the real-time loop.

```
 camera ─ FaceLandmarker ─┐                      ┌─ Generator: argmax F + γE ─ Player ─ Body
 FastVLM (every 3 s) ─────┤                      │   (look-at IK, primitives)  (springs)  ├ Blender twin (UDP)
 iPad: Margin events ─────┼─ Bus ─ Estimator ─ StateMachine ─ Policy ─┤                   └ servos (later)
   (stuck, wrong, pencil) │  (append-only log)  (evidence) (hysteresis) (ladder, budget,  └─ lamp.request ─▶ Margin
 user.pat ────────────────┘                                              Thompson sampling)
```

## Layers

Dependencies point one way only; `tests/test_replay_and_layers.py` enforces this.

| Layer | Module | Trust | Job |
|---|---|---|---|
| contracts | `types.py` | n/a | Event kinds, states, the `Intervention` record |
| infra | `infra.py`, `config.py` | n/a | Clock, append-only `EventLog`, `Bus` with serial interceptors, layered profiles |
| sensors | `sensors/` | **untrusted** | Turn pixels and models into `obs.*` events. Can be wrong, late or missing |
| bridge | `bridge.py` | **untrusted** | JSON lines from Margin (`app.*`, `user.*`), `lamp.request` back |
| estimate | `estimate.py` | deterministic | Features (EMAs, windows) → evidence per state = clip(Σ weight·feature), with the top reasons |
| fsm | `fsm.py` | deterministic | Context machine (sleep/arriving/studying/exam/break/away) and study tracks with enter/exit thresholds, dwell and priority |
| policy | `policy.py`, `personalize.py` | deterministic | What to do and when: intents, the hint ladder, cooldowns, the hourly budget, outcome tracking, per-user parameters |
| motion | `motion/` | deterministic | How to do it: plan a trajectory, then play it smoothly |
| bodies | `bodies.py` | n/a | Where poses go: nowhere (tests), UDP (Blender twin), servos later |

Models only ever produce **evidence**. Only the deterministic core can produce **actions**.
A misbehaving model can make the lamp read a state wrongly, but it cannot bypass exam mode,
the budget or the cooldowns.

## The loop (30 Hz)

`Runtime.tick()` runs these steps in order:

1. Poll sensors and the bridge, then emit the new events onto the bus in time order.
2. Compute the evidence and update the state machine. A state change emits `state.enter`.
3. The policy reacts to `state.enter` and `moment` events and climbs the ladder on a timer.
   It emits `intervene`.
4. Interceptors may rewrite or veto the intervention. The raw exam flag immediately cancels queued motion and joint velocity, including a plan
   that started before the exam. Exam mode allows light changes only;
   experiment conditions do the same, or let only the app request through.
5. The generator plans the motion and the player starts it (a higher priority can preempt).
6. The player steps its springs and sends the pose to the body.

## State estimation

Two layers, following D'Mello & Graesser's learning-centred affect:

- **Context:** whether anyone is there and what mode they are in, from face presence and Margin.
- **Study:** engaged (default), confused, frustrated, bored, fatigued, low and phone. Each
  state is a weighted sum of features, smoothed by an EMA, and switched with hysteresis. Each
  has enter and exit thresholds, a dwell time and a priority. Frustration is only allowed
  within two minutes of confusion, or on very strong evidence, because confusion turning into
  frustration is when help is useful.

All weights live in `profiles/base.json`. The system estimates behaviour-based states. It does
not claim to recognise emotions, which matters for the EU AI Act's rules on education
settings.

## Policy

| Study state | Intent | Notes |
|---|---|---|
| confused | `attend` (lean in, quiet) | After `confusion_window`, climbs the ladder |
| frustrated | ladder: `glance_hint` → `show_hint` (asks Margin) → `voice` (off) | Continues from where confusion got to, never back down; offers `comfort` once the hints run out |
| phone | `phone_look` instantly, `phone_nag` after 12 s | The light dims and cools until the phone is docked again |
| fatigued | `suggest_break` | Accepting the break resets the tiredness windows |
| low | `comfort` | |
| bored | `nudge` | |
| moments | `celebrate` / `hmm` | Fired by Margin's `app.correct` / `app.wrong` |

Each tracked intervention gets an outcome within `outcome_window`. It succeeds if the person
is engaged again (or took the break), and fails if they patted the lamp to dismiss it. The
reward updates a Beta posterior per (state, arm), where an arm is `confusion_window` ×
`ladder_start` × `gamma_mult`. The next choice is Thompson sampling over those posteriors.
This is how the lamp learns, per person, how patient and how expressive to be.

## Motion: F + γE (ELEGNT-inspired approximation)

Following Hu et al., *ELEGNT* (Apple, arXiv 2501.12493), each candidate trajectory gets a score:

- **F** (function) = reach the target − time − effort − motor noise
- **E** (expression) = for each wanted dimension (intention, attention, attitude, emotion),
  how well the chosen primitives cover it, minus exaggeration, minus moving without a reason
- The plan is the argmax of **F + γE**. γ comes from the intent, then the state, then the
  default, and is scaled by the user's personalized `gamma_mult`.

The candidates are function-only, each primitive at three amplitudes, and pairs of primitives,
each with and without anticipation (the head leads the body). The goal pose comes from a 3-DoF
look-at IK built on the rig exported from Blender (`motion/rig.json`). Moves follow min-jerk
profiles. The `Player` runs critically damped springs with velocity and acceleration limits,
plus a breathing layer when idle. Planning takes 4–18 ms.

The paper reports stronger preference for expression in social scenarios, with mixed
preferences and potential interference in function-oriented scenarios. It does not establish
that expression universally harms functional tasks. We therefore choose low γ for `settle`
and `attend`, and high γ for `hello`, `celebrate` and `comfort` as a design hypothesis.

This code is our finite candidate search, not Apple's released solver or a trained motion
policy. Primitive keyframes, allowed combinations, expressive tags and weights are authored.
Targets, inverse kinematics, interpolation, candidate selection and spring playback are
computed. The score is a hand-designed proxy for perceived expression, not a validated human
preference model. There is no obstacle-aware continuous replanning yet. Hop/squash are visual
simulation channels, not commands validated on physical hardware.

## Replay

The event log is the source of truth. `python -m lampkit replay LOG` feeds the recorded inputs
back in with the recorded seed, initial posterior, full configuration and exact tick batches. It
checks state transitions, interventions, app requests, vetoes, outcomes, parameters and motion
plans (excluding planning wall time). Replay never writes to the current user state file. A recorded
session can also be re-run against explicit profile overrides; differences then return a nonzero exit code.

## Running

```bash
python -m lampkit simulate scenarios/stuck.json          # prints the timeline and checks `expect`
python -m lampkit simulate scenarios/demo.json --profile twin --realtime   # drives Blender
python -m lampkit run --profile desk                     # camera + iPad bridge, live
python -m lampkit mock-ipad app.stuck '{"conf": 0.8}'    # pretend to be Margin
python -m lampkit replay logs/<session>.jsonl
python -m lampkit config desk --set motion.gamma.default=0.5
```

Profiles stack through `extends`: `base` → `sim`/`twin`/`desk` → `exp-static`/`exp-app-only`.
The last two are study conditions for the same runtime: a lamp that only changes its light,
and a lamp that stays still while Margin shows the hint.
