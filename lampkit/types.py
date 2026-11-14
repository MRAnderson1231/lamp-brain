"""Shared vocabulary. Every other module may import this one; it imports nothing from lampkit.

Everything that crosses a module boundary is an `Event`: observations from sensors and the
iPad, state changes, interventions, motion plans, outcomes. The event log is the source of
truth: anything the lamp did can be reconstructed by replaying the input events.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

# ---- event kinds -------------------------------------------------------------------------
# inputs: replay feeds exactly these back into the pipeline
OBS_FACE = "obs.face"          # {present, yaw, pitch, x, y, z, blend:{browDown, eyeSquint, eyeBlink, jawOpen, mouthSmile, mouthFrown}}
OBS_POSE = "obs.pose"          # {slouch 0..1, hand_on_head bool}
OBS_PHONE = "obs.phone"        # {docked bool, in_hand 0..1}
OBS_VLM = "obs.vlm"            # {probs:{engaged, confused, frustrated, bored, tired, sad}}
OBS_AMBIENT = "obs.ambient"    # calibrated workplane_total lux OR relative_image brightness; never interchange
OBS_HAND = "obs.hand"          # desk_m position, zone(table/head/none), engaged, quality, observed_at
OBS_OCCUPANCY = "obs.occupancy"  # {present, posture:seated/standing/unknown}; requires a real posture source
OBS_WORK_TARGET = "obs.work_target"  # calibrated desk_m position; not an app message
OBS_JUDGMENT = "obs.judgment"  # bounded cue probabilities, model/evidence_id/observed_at; no actions
OBS_CLOCK = "obs.clock"        # recorded local_hour; no implicit wall time in the core
APP = "app."                   # prefix for Margin events, see APP_* below
USER_PAT = "user.pat"          # the user tapped the shade: "not now"

APP_SESSION = "app.session"    # {active bool}
APP_EXAM = "app.exam"          # {active bool}
APP_PENCIL = "app.pencil"      # {strokes int, erases int}  activity since the last event
APP_STUCK = "app.stuck"        # {conf 0..1, region [x, y, w, h] in screen 0..1}
APP_WRONG = "app.wrong"
APP_CORRECT = "app.correct"
APP_BREAK = "app.break"        # {active bool}  the user accepted a break
APP_TASK = "app.task"          # {task_id}; task-scoped messages must carry the same id
APP_CONTEXT = "app.context"    # {local_hour}; explicit local context for deterministic color scheduling
USER_STUDY_INTENT = "user.study_intent"  # {value:ready/not_now}; distinct from evaluation-only lab.annotation
USER_LIGHT = "user.light"      # {glow?,kelvin?,auto?}; explicit manual override

INPUT_PREFIXES = ("obs.", "app.", "user.")

# derived: produced by the pipeline, compared against during replay
EVIDENCE = "evidence"          # {state: score}
STATE_ENTER = "state.enter"    # {layer, state, prev, reason}
MOMENT = "moment"              # {name}  one-off events: correct, wrong
INTERVENE = "intervene"        # Intervention as dict
VETO = "veto"                  # {intervention, by}
APP_REQUEST = "lamp.request"   # {action, ...} sent to Margin, e.g. show_hint
PLAN = "motion.plan"           # {intent, gamma, primitives, duration, score}
OUTCOME = "outcome"            # {intervention_id, success, dismissed, reward}
PARAMS = "params"              # {context, arm}

# ---- states --------------------------------------------------------------------------------
CTX_SLEEP, CTX_ARRIVING, CTX_STUDYING, CTX_BREAK, CTX_AWAY, CTX_EXAM = (
    "sleep", "arriving", "studying", "break", "away", "exam")
ENGAGED, CONFUSED, FRUSTRATED, BORED, FATIGUED, PHONE, LOW = (
    "engaged", "confused", "frustrated", "bored", "fatigued", "phone", "low")
STUDY_STATES = (ENGAGED, CONFUSED, FRUSTRATED, BORED, FATIGUED, PHONE, LOW)

# ELEGNT's four expressive dimensions
INTENTION, ATTENTION, ATTITUDE, EMOTION = "intention", "attention", "attitude", "emotion"


@dataclass
class Event:
    t: float
    kind: str
    data: dict[str, Any] = field(default_factory=dict)
    src: str = ""

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def from_json(line: str) -> "Event":
        d = json.loads(line)
        return Event(t=float(d["t"]), kind=d["kind"], data=d.get("data") or {}, src=d.get("src", ""))

    @property
    def is_input(self) -> bool:
        return self.kind.startswith(INPUT_PREFIXES)


@dataclass
class Intervention:
    """What the policy wants the lamp to communicate. The motion generator decides how."""
    id: int
    t: float
    intent: str                       # e.g. "attend", "hint", "celebrate"
    state: str                        # the state that caused it
    level: int = 0                    # rung on the intervention ladder
    target: str = "work"              # "user" | "work" | "hint" | "seat" | "rest"
    express: dict[str, float] = field(default_factory=dict)   # wanted ELEGNT dimensions, 0..1
    light: dict[str, float] = field(default_factory=dict)     # {"glow": x, "warmth": y}
    motion: bool = True               # False: light only
    app: dict[str, Any] | None = None  # request for Margin, e.g. {"action": "show_hint"}
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
