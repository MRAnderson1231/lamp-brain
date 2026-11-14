export async function command(path, data = {}) {
  const response = await fetch(`/api/${path}`, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Lamp-Lab': '1'}, body: JSON.stringify(data)});
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || '操作失败');
  return result;
}
export const names = {
  sleep: '待机', arriving: '发现有人', studying: '陪伴学习', exam: '考试静默', break: '休息', away: '暂时离开',
  engaged: '未触发其他状态', confused: '可能困惑', frustrated: '可能受挫', bored: '可能无聊', fatigued: '可能疲劳', phone: '手机事件', low: '低落线索',
  hello: '打招呼', settle: '回到工作姿态', attend: '关注学习区域', glance_hint: '看向提示区域', show_hint: '请求 Margin 提示',
  celebrate: '庆祝', hmm: '轻微回应', comfort: '安抚', nudge: '轻提醒', suggest_break: '建议休息', phone_look: '看向手机', phone_nag: '提醒放回手机',
  camera: '摄像头', 'mock-margin': '模拟 Margin', ipad: 'Margin 接口', 'self-report': '人工标注', policy: '行为策略', fsm: '状态机', motion: '动作规划', bus: '约束检查',
  brow: '眉部变化', squint: '眯眼', off_task: '头部偏离', stuck: '卡住消息', idle: '停笔', erase_rate: '擦除频率', perclos: '闭眼比例', yawns: '张嘴持续', study_time: '学习时长', frown: '嘴角变化', smile: '微笑线索',
  neutral: '平静', tired: '疲劳', reluctant: '不想学习',
  active:'独立陪伴',sensor_unknown:'感知暂时中断',occupancy_off:'无人熄灯',care_check:'轻声关怀动作',stretch_reminder:'活动提醒',face_estimate:'估计人脸位置',work_target:'工作区目标',
  present:'在场待命', idle:'无人待机', rest:'休息姿态', control:'控制仲裁',fusion:'输入融合',
  hold_no_measurement:'保持亮度，等待标定照度',auto_lux:'自动照度控制',manual:'手动调光',inactive:'未接管',arming:'等待手势稳定',table:'桌面调光',head:'灯头引导',out_of_range:'手超出跟踪范围',
};
export const name = key => names[key] || key || '—';
export function describe(event) {
  const d = event.data;
  if (event.kind === 'state.enter') return `${name(d.prev)} → ${name(d.state)}`;
  if (event.kind === 'intervene') return `${name(d.intent)} · ${d.reason}`;
  if (event.kind === 'motion.plan') return `${name(d.intent)} · 功能 ${d.score.F.toFixed(2)} / 表达 ${d.score.E.toFixed(2)} / 权重 ${d.gamma} · ${d.accepted ? '已执行' : '未抢占当前动作'}`;
  if (event.kind === 'lab.annotation') return `我现在：${name(d.label)}（仅记录）`;
  if (event.kind === 'veto') return `${name(d.data?.intent)} 被 ${d.by} 拦截`;
  if (event.kind.startsWith('app.')) return `${event.kind} · ${JSON.stringify(d)}`;
  return `${event.kind} · ${JSON.stringify(d)}`;
}
