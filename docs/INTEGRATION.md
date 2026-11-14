# Margin integration and verified scope

The standard-library core runs without MLX, model downloads, a camera, or Blender.
Use Python 3.12+. Run commands from the repository root.

## Reproducible end-to-end simulation

```sh
python3 -m lampkit simulate scenarios/stuck.json --log /tmp/lamp-stuck.jsonl
python3 -m lampkit replay /tmp/lamp-stuck.jsonl
uv run --no-project --python 3.12 --with pytest pytest -q
```

Use a new log filename for each run. Replay rejects logs containing multiple sessions.
Logs contain input observations, full configuration and initial personalization state; keep
real participant logs private. Runtime in-memory history is bounded; the JSONL file is complete.

## Live TCP integration without a camera

Terminal 1 (synthetic presence, actual network bridge, no model):

```sh
python3 -m lampkit run --profile bridge-demo --scenario scenarios/bridge-presence.json --duration 120 --log /tmp/lamp-bridge.jsonl
```

Terminal 2, after the lamp has greeted the simulated participant:

```sh
python3 -m lampkit mock-ipad app.session '{"active":true}'
python3 -m lampkit mock-ipad app.pencil '{"strokes":1,"erases":0}'
python3 -m lampkit mock-ipad app.stuck '{"conf":1,"region":[0.2,0.3,0.2,0.1]}' --listen 100
```

The final connection receives `lamp.request` with `action: show_hint`, after the configured
waiting window and ladder. This is an actual round-trip TCP test with synthetic perception;
it is not a real iPad demonstration. Use `--set personalize.enabled=false` on terminal 1 for
fixed waiting times. `user.pat` dismisses a pending reminder and suppresses tracked/budgeted
follow-up interventions for `policy.dismiss_quiet_seconds`.

To drive the Blender twin too, add `--set body.type=udp` to terminal 1 and run `blender_live.py`
in the supplied Blender scene. No physical servo driver is included.

## Wire contract (protocol v1)

UTF-8 newline-delimited JSON over TCP, default `127.0.0.1:7788`. Keep one connection open to
receive requests. No WebSocket framing or Bonjour discovery is implemented.

| Kind | Data |
|---|---|
| `app.session` | `active: bool`, optional nonnegative `elapsed_min` |
| `app.exam`, `app.break` | `active: bool` |
| `app.pencil` | nonnegative integer `strokes`, `erases` since last event |
| `app.stuck` | `conf: 0..1`, optional `[x,y,width,height]` fully inside normalized screen |
| `app.correct`, `app.wrong` | `{}` |
| `user.pat` | `{}` |

Outbound: `{"kind":"lamp.request","data":{"action":"show_hint","intervention":5}}`.

The runtime assigns arrival timestamps. Invalid objects, unknown kinds and malformed data are
rejected. Input buffering and line sizes are bounded. Outbound sends run off the control loop.
Exam activation stops current commanded joint motion immediately, including within a batch.
This is software control behavior, not a certification of mechanical stopping safety.

For a physical iPad on a trusted LAN, explicitly set `--set bridge.host=0.0.0.0` and connect to
the Mac's LAN IP. There is no authentication, TLS, pairing, acknowledgment or retry protocol;
do not expose this development endpoint to the Internet. Requests are best-effort, not confirmed
hint displays. No claim of cross-device clock synchronization or automatic calibration is made.

## What remains

- Real Margin client: event production, request acknowledgments and display timing.
- Camera and VLM: install dependencies/model assets, exercise the adapters, measure failures,
  latency and accuracy. Pose/hand/phone perception currently uses scripted inputs only.
- Learned state: rewards are heuristic proxies. Overlapped attempts are unscored; no causal
  efficacy or long-term personalization has been established.
- Screen targeting currently uses configured geometry, not AprilTag localization.
- Motion is a Blender-compatible kinematic prototype with spring smoothing. No validated
  physical collision model, torque limits, MuJoCo or servo firmware exists yet.
- `app.session` controls study-time features; presence still drives the context machine even
  without an active app session. The bridge demo supplies explicitly synthetic presence.

The first real-device milestone is one real iPad stuck event, one synchronized visible hint,
one lamp movement, and a reproducible log. The next is testing perception with a consenting
participant and measuring false interruptions before enabling adaptive behavior by default.
