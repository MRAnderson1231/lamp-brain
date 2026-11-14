# Lamp lab implementation and visual verification

Date: 2026-11-14. Concept: `lamp-lab-concept.png`. Actual desktop: `lamp-lab-desktop.jpg`. Mobile: `lamp-lab-mobile.jpg`.

V2 follow-up: the user requested completing architecture before further live tests. The
camera remains off. The console now defaults to standalone companion, showing service,
lighting, gesture ownership and target tracking. The optional proactive profile retains Margin.
These controls were covered at the core contract level; no new human gesture/emotion validation is claimed.
The latest code suite reports 94 passed / 3 skipped, and the synthetic V2 scenario and replay pass.

The concept was generated before implementation. The user-specified interface is a functional research console: lamp on the left, real camera on the right. The actual lamp uses the repository's exported Blender geometry; no generated bitmap is used as a working UI or live lamp.

Design tokens: white background, slate text, muted gray secondary text, #087e75 accent, thin #dce0e3 separators, system/PingFang typography, 6–9px control/panel corners. React composition separates API/event formatting, camera preview and the Three.js view from the dashboard shell. All scripts, meshes and model inference are local; no remote font or runtime CDN.

Verification used the IAB browser, with a 1488×1056 desktop viewport matching the concept image dimensions, the normal browser viewport, and 390×844 mobile. The viewport override was reset. Both the concept and saved implementation were opened using view_image for comparison. No external Playwright fallback was required.

| Inspection | Concept evidence | Actual evidence / disposition |
|---|---|---|
| Layout | Lamp left, camera right; three lower sections; log | Same desktop structure; stacked single column at 390px, no horizontal overflow (scrollWidth=390) |
| Copy | Main title, start/stop, three sections, table headings | Preserved; necessary additions listed below; no marketing copy/navigation added |
| Typography | Dark sans-serif headings, restrained captions | Explicit sizes on body, controls, meters, table and caption; readable mobile wrapping |
| Palette | White surfaces, teal primary control, dark camera panel | Preserved; no background gradient, tint or off-white substitution |
| Icons | Outlined camera in the inactive camera panel | Code-native SVG, consistent stroke; not an emoji |
| Media | Articulated lamp; blank camera before start | Real exported rig replaces concept's static lamp; real image only while running; camera hidden before saved screenshots |
| Motion | Working prototype required | Browser consumes runtime pose, updates bone rotations and glow/warmth; no independent canned animation |
| Controls | Message and annotation buttons | Only enabled when runtime is running; selected exam mode visible; stop releases camera |

Intentional deviations: use existing project lamp instead of the generated concept's slightly different proportions; retain last real pose after stopping; add relative image brightness and model identity, unknown-state caveat, extra resume/rest/dismiss controls, and event details/plan scores. These are necessary to distinguish raw sensing, simulated app messages and annotations for the user's requested validation. Extra content makes the desktop page taller than the initial concept. A plain white simulated iPad surface does not imply a live Margin screen integration. Rendering is a diagnostic 3D view, not photorealism or a physics simulator.

Repaired during review: initial light-shadow acne and undersized lamp viewport; resume-study now also clears the break flag; failed annotation requests no longer select a label.

Above-fold copy comparison: original title/subtitle and panel titles retained; intentional new labels are “画面亮度”, “MediaPipe Face Landmarker · FastVLM 未启用”, and the exposure/illuminance clarification. No unrelated content was added. Layout, typography, palette, core labels and control hierarchy were verified against the concept with the functional deviations above; it is not a pixel-identical raster reconstruction.

Observed browser workflow: camera start → actual face and head-angle values → app.correct → runtime celebration with selected double_nod+bounce, F/E/γ and planning latency → exam mode → app.wrong without movement → stop → camera preview removed. Browser error log was empty. Raw face images were not saved to QA files. Frontend production build succeeded; tests cover the same runtime, label isolation, local-origin rejection, idle/timeout cleanup and restart behavior.

Limit: this session did not establish confusion/fatigue classification accuracy, hand tracking, closed-loop illumination or physical hardware safety. Do not conflate a passed UI test with validation of those systems.

## Standalone scope update

Rechecked the companion UI at 1488×1056 and 390×844 with the camera stopped.
No horizontal overflow at 390px; browser error log empty; viewport reset. Updated both
screenshots. Title now 台灯 · 感知实验室; message panel becomes 独立陪伴控制;
MediaPipe, disabled FastVLM/Jev, missing hand/posture/work-target detectors and the
difference between coefficients and emotion probabilities are explicit. This follows
the user's new standalone scope. The layout and visual treatment remain the same.

Synthetic suite: 94 passed, 3 skipped. Companion CLI scenario expectations passed.
Frontend production build passed (Three.js bundle size warning remains).
The architecture is ready for sensor integration, not evidence of validated emotion
recognition, real gestures, physical sitting detection, calibrated light control or motors.
