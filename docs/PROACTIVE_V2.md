# 主动式台灯 V2：架构与接线契约

**当前默认已改为独立陪伴 `companion`，详见 [COMPANION.md](COMPANION.md)。** 下文的学习模式与 Margin 契约保留在可选 `proactive` 配置；独立模式拒绝 app.*，不会暗中依赖学习消息。

2026-11-14。按用户要求先完成架构，再集中做真实测试。配置中的数值是工程初值，不是实验结论。

## 已接齐的执行链

```text
CameraSensor / PeripheralSensor / 可选 VLM       Margin TCP / 明确用户指令
                obs.*                                  app.* / user.*
                  └──────────────────┬───────────────────────┘
                                     ↓
                   World：来源、时效、质量、去重、题目作用域
                     ↓                              ↓
            学习证据 Estimator/FSM           手势控制状态机 Gestures
                     ↓                       桌面调光 / 灯头引导
               学习干预 Policy                         ↓
                     └───────────→ ControlStack 仲裁 ←─┘
                                   ↓            ↓
                  表达候选轨迹 Generator     Tracking 连续位置 IK
                                   └─────┬──────┘
                       Lighting 独立工作照明目标
                                         ↓
                         Player 平滑、速度/加速度限制
                                         ↓
                        NullBody / Blender UDP / Web 同步显示
                                         ↓
                         日志、拒绝理由、精确回放
```

| 模块 | 已完成架构 | 真实接入或验证尚缺 |
|---|---|---|
| `control/world.py` | 输入过期、质量门槛、去重、乱序拒绝、任务隔离、明确模式指令 | 跨设备时钟对齐、真实 iPad 确认和重连 |
| `control/gestures.py` | 稳定进入、桌面亮度增量、近灯头退让/相对跟随、失去输入退出 | 手部检测、距离估计、桌面和运动相机标定 |
| `control/lighting.py` | lux 与画面亮度分离、PI 与渐变限速、手动覆盖、色温目标 | 标定照度硬件、真实灯具响应与调参 |
| `control/tracking.py` | 连续位置 IK、工作区约束、可达性误差、定频重规划 | 自碰撞/外物碰撞、动力学、真实机构标定 |
| `control/__init__.py` | 模式/手动/学习优先级；提示先征询 | 长期行为体验、实际 Margin 提示 UI |
| `runtime.py`、`motion/player.py` | 统一执行与平滑，V2 控制状态也可回放 | 实体执行器回读 |
| `sensors/peripheral.py` | 有界生产者队列，外设驱动可发布手/光观测 | 不包含手部识别器或照度硬件驱动 |
| `lab.py`、`web/` | 左灯右摄像头、模式、来源、控制状态与日志 | 真人验证待后续进行 |

## 权威模式与主观状态

World 区分 idle（无人无会话）、present（人在场但未开始学习）、studying（明确开始且人在场）、away（会话中离开）、break（明确休息/暂不学习）、exam（最高场景限制）。

原学习 FSM 仍计算学习证据，其默认 engaged 不代表已确认专注。网页优先显示 V2 模式。人工标注 `lab.annotation` 只记录；明确指令 `user.study_intent` 才改变交互许可。相机看到脸可以问候，但不会仅凭此获得学习干预权限。

输入带来源和有效期；task_id 确立后，旧题或缺少匹配 task_id 的笔迹/对错/卡住消息会被拒绝。换题清除卡住、笔迹计时和提示阶梯；旧干预标为未评分，不继续训练个性化。

## 手势与照明的实际控制路径

**桌面调光：** `zone=table` 且 engaged 稳定一段时间后，按桌面坐标中的向上/向下位移输出亮度增减。采用位移门槛和冷却，不改变灯位。上层手部检测器必须区分控制手势与写字/翻页。

**灯头引导：** `zone=head` 稳定进入后建立相对操作点；手过近则给出退让目标，在跟随范围内按相对位移引导灯头。目标由 Tracking 持续求位置 IK，经 Player 平滑。手丢失、越界、目标不可达则停止跟随，不续播被打断的表达动作。用户括号中的绝对上下映射有歧义，实际方向需机位标定后确认；不能直接用图像 y 轴。

该控制律是本项目初版，不是 Apple 未公开代码。现在是位置控制，没有真实力矩反馈，不能称为实体柔顺/阻抗控制。灯头摄像头会随灯运动，必须把手位置变换到固定桌面坐标；单个 Mac 前置摄像头未必同时覆盖脸和桌面，实际传感器布置仍待验证。

**照明：** 只有 `workplane_total + calibrated=true + lux` 进入闭环。`relative_image` 只作观察，避免自动曝光引发误调。PI 带死区、平滑、饱和限制、抗积分饱和与变化率限制；持续过亮可关灯。数据失效保持当前亮度。

桌面滑动或 `user.light` 启动手动覆盖期。色温由明确 Kelvin 设置或应用提供 local_hour 后按配置目标缓变；不把自动白平衡当色温计。当前 warmth 与 Kelvin 是模拟映射，实体冷暖 LED 需另行标定。工作照明在执行层独立输出，表达动作的装饰性 brighten 不能覆盖它。

**仲裁：** 考试限制优先；手动引导期间暂停学习表达；拒绝打扰立即取消当前表达并暂停后续干预。严格考试不运动、不请求题目提示。防手机分心应另设自愿专注模式，不能借手机识别绕过考试限制；手机检测目前未接入，灯也不能物理阻止拿手机。

## Margin 与用户消息契约

现有本机 TCP 换行 JSON 入口继续使用。它只接 app/user 信息，拒绝 obs.* 和电机命令。

```json
{"kind":"app.session","data":{"active":true}}
{"kind":"app.task","data":{"task_id":"math-001"}}
{"kind":"app.pencil","data":{"task_id":"math-001","strokes":8,"erases":2}}
{"kind":"app.stuck","data":{"task_id":"math-001","conf":0.8,"region":[0.2,0.3,0.25,0.1]}}
{"kind":"app.correct","data":{"task_id":"math-001"}}
{"kind":"user.study_intent","data":{"value":"not_now"}}
{"kind":"user.study_intent","data":{"value":"ready"}}
{"kind":"user.light","data":{"glow":0.8,"kelvin":3500}}
{"kind":"user.light","data":{"auto":true}}
{"kind":"app.context","data":{"local_hour":21.5}}
{"kind":"app.exam","data":{"active":true}}
```

设定任务后，stuck/pencil/correct/wrong/hint_feedback 都必须带同一 task_id。尚未设 task_id 时兼容旧消息，便于分步迁移。

提示链：原 show_hint 请求先变成 `lamp.request {action:offer_hint,intervention,task_id}`。Margin 回传 `app.hint_feedback {accepted,intervention,task_id}`；仅同一提示、未过期且当前仍允许干预时，才发真正 show_hint。接受提示不是直接操作电机，仍经过模式/手动/拒绝干预的仲裁。

## 外设适配契约

真实驱动创建 `PeripheralSensor(cfg,clock)`，加入 Runtime.sensors，然后 publish 以下观测之一。队列有界；融合层再次验证新鲜度、质量与单位。

```json
{"kind":"obs.hand","data":{"zone":"table","engaged":true,"hand_id":"right","position":[0.15,0.2,0.02],"frame":"desk_m","calibrated":true,"quality":0.9,"sample_id":"h-103"}}
{"kind":"obs.hand","data":{"zone":"none","engaged":false,"quality":1}}
{"kind":"obs.ambient","data":{"measurement":"workplane_total","calibrated":true,"lux":450,"quality":0.95,"sample_id":"lux-901"}}
{"kind":"obs.ambient","data":{"measurement":"relative_image","calibrated":false,"brightness":0.42,"quality":1}}
```

desk_m：以灯底座为原点，+x 向右，−y 向人，+z 向上，单位米。可选 observed_at 必须转换成 runtime 单调时钟，不是 Unix 时间；未提供则使用本机接收时间。quality 是来源质量，不是情绪概率。calibrated 必须由真实标定支持，不能靠填写 true 代替验证。

当前 MediaPipe 仍只处理脸和头姿；FastVLM 适配代码未验证且关闭。VLM 应提供可观察事实与 unknown，不能直接指定关节或假称理解真实情绪。

## 运行与验证边界

- `desk` 保留原基线；`proactive` 开启本架构，关闭个性化写入。
- `./lab_test.sh` 默认用 proactive，但摄像头仍由用户点击开始。
- 合成输入检查：`python -m lampkit simulate scenarios/proactive_architecture.json --profile proactive --set 'body.type="null"'`。simulate 不开启真实摄像头，不验证模型识别。
- 所有 V2 调参在 `profiles/base.json` 的 control 下；旧配置没有 control 时仍走旧路径。

统一测试阶段按：真实传感器/坐标 → 两类手势和手动优先 → 真 Margin 消息/提示反馈 → 状态误报/介入时机 → MuJoCo/实体机构。当前完成可接线、可解释、可回放的框架；识别准确率、物理稳定性、碰撞安全与学习效果仍待验证。
