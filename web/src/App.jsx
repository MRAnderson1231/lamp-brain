import React, {useEffect, useState} from 'react';
import LampView from './LampView';
import CameraView from './CameraView';
import {command,name,describe} from './api';

function Meter({label,value,detail}){return <div className="meter"><span>{label}</span><div className="meter-track"><div style={{width:`${Math.max(0,Math.min(1,value||0))*100}%`}}/></div><span className="numeric">{value==null?'—':value.toFixed(2)}</span>{detail&&<small>{detail}</small>}</div>;}
const actions=[['开始学习','app.session',{active:true}],['答对','app.correct',{}],['答错','app.wrong',{}],['卡住了','app.stuck',{conf:1,region:[.2,.3,.25,.1]}],['考试模式','app.exam',{active:true}],['结束考试','app.exam',{active:false}],['继续书写','app.pencil',{strokes:1,erases:0}],['接受休息','app.break',{active:true}],['结束休息','app.break',{active:false}],['暂不打扰','user.pat',{}]];
export default function App(){
  const [state,setState]=useState({status:'stopped'}),[error,setError]=useState(''),[busy,setBusy]=useState(false),[connected,setConnected]=useState(false),[label,setLabel]=useState('');
  useEffect(()=>{
    let done=false,timer,controller=new AbortController();
    async function poll(){try{const r=await fetch('/api/state',{signal:controller.signal});if(!r.ok)throw Error('服务连接中断');const s=await r.json();if(!done){setState(s);setConnected(true);}}
      catch(e){if(!done){setConnected(false);setError('本地服务连接中断；摄像头将在无人连接后自动停止。');}}
      if(!done)timer=setTimeout(poll,100);
    }poll();return()=>{done=true;clearTimeout(timer);controller.abort();};
  },[]);
  const running=connected&&state.status==='running', starting=state.status==='starting'||state.status==='stopping';
  async function act(path,data){setBusy(true);setError('');try{await command(path,data);return true;}catch(e){setError(e.message);return false;}finally{setBusy(false);}}
  async function annotate(value){if(await act('event',{kind:'lab.annotation',data:{label:value}}))setLabel(value);}
  async function message(kind,data){
    if(kind==='app.session'&&!(await act('event',{kind:'app.break',data:{active:false}})))return;
    if(kind==='app.session'&&!(await act('event',{kind:'user.study_intent',data:{value:'ready'}})))return;
    await act('event',{kind,data});
  }
  const standalone=(state.profile||'companion')==='companion';
  const control=state.control, mode=control?.world.mode||state.context, offer=control?.hint_offer;
  async function hint(accepted){const data={accepted,intervention:offer.intervention};if(offer.task_id)data.task_id=offer.task_id;await act('event',{kind:'app.hint_feedback',data});}
  const face=state.face||{}, plan=state.plan, action=state.action;
  const why=(state.why?.[state.study]||[]).map(([key,v])=>`${name(key)} ${v.toFixed(2)}`).join(' + ');
  return <main>
    <header><div><h1>台灯 · 感知实验室</h1><p>观察、判断与动作，同屏验证</p></div><div className="header-actions"><button className="primary" disabled={busy||running||starting||!connected} onClick={()=>act('start')}>{state.status==='starting'?'启动中…':running?'摄像头运行中':'开始摄像头'}</button><button disabled={busy||(!running&&!starting)} onClick={()=>act('stop')}>停止</button></div></header>
    {(error||state.error)&&<p className="error" role="alert">{error||state.error}</p>}
    <section className="main-grid">
      <article className="panel"><h2>台灯 · 实时姿态</h2><LampView pose={state.pose}/><dl className="status"><div><dt>当前状态</dt><dd>{state.status==='stopped'?'已停止':name(mode)}{running&&mode==='studying'?` · ${name(state.study)}`:''}</dd></div><div><dt>{running?'动作':'上次动作'}</dt><dd>{state.exam?'考试模式：动作已冻结':action?name(action.intent):'等待输入'}</dd></div><div><dt>原因</dt><dd>{state.exam?'考试约束优先，不发送题目提示':why||action?.reason||'尚未开始'}</dd></div></dl></article>
      <article className="panel"><h2>摄像头 · 本机画面</h2><CameraView running={running} faceFresh={state.face_fresh}/><div className="sensor-grid">{[['眉部变化',face.blend?.browDown],['眨眼',face.blend?.eyeBlink],['头部偏转',face.yaw,'°'],['画面亮度',state.brightness]].map(([text,value,suffix])=><div key={text}><span>{text}</span><strong>{running&&value!=null?`${value.toFixed(suffix?1:2)}${suffix||''}`:'—'}</strong></div>)}</div><p className="note">MediaPipe Face Landmarker · FastVLM / Jev 未启用<br/>画面亮度受自动曝光影响，不是桌面照度。</p></article>
    </section>
    {control&&<p className="control-status">输入融合：{name(control.world.mode)} · 照明：{name(control.lighting.mode)} · 手势：{name(control.gesture.mode)} · 跟随：{name(control.attention?.source)} · 实体硬件未连接</p>}
    <section className="tools-grid">
      <article className="panel"><h2>状态证据</h2>{standalone?<><Meter label="闭眼线索" value={running?face.blend?.eyeBlink:null}/><Meter label="持续线索触发" value={running?(control?.service?.fatigue_cue?1:0):null}/></>:<><Meter label="困惑" value={running?state.evidence?.confused:null}/><Meter label="疲劳" value={running?state.evidence?.fatigued:null}/></>}<Meter label="头部偏离" value={running?state.features?.off_task:null}/><p className="note">规则分数，不是情绪概率。独立陪伴模式只用可观察线索触发关怀，不启用学习提示。</p></article>
      <article className="panel"><h2>{standalone?'独立陪伴控制':'模拟 Margin 消息'}</h2>{standalone?<><div className="buttons"><button disabled={!running||busy} onClick={()=>message('user.pat',{})}>暂不打扰</button><button disabled={!running||busy} onClick={()=>message('user.light',{glow:1,kelvin:3500})}>舒适照明</button><button disabled={!running||busy} onClick={()=>message('user.light',{auto:true})}>自动照明</button></div><p className="note">在桌前：{Math.floor(control?.service?.desk_seconds||0)} 秒 · 已观察到坐姿：{Math.floor(control?.service?.seated_seconds||0)} 秒<br/>人脸位置是估计；目前未接入坐姿、手部与桌面目标检测器。</p></>:<><div className="buttons messages">{actions.map(([text,kind,data])=><button key={text} disabled={!running||busy} aria-pressed={kind==='app.exam'?state.exam===data.active:undefined} onClick={()=>message(kind,data)}>{text}</button>)}</div>{offer&&running&&<div className="hint-offer"><p>台灯询问：需要提示吗？</p><button disabled={busy} onClick={()=>hint(true)}>接受提示</button> <button disabled={busy} onClick={()=>hint(false)}>暂时不用</button></div>}</>}</article>
      <article className="panel"><h2>人工标注</h2><div className="buttons">{[['平静','neutral'],['困惑','confused'],['疲劳','tired'],['不想学习','reluctant']].map(([text,value])=><button key={value} disabled={!running||busy} aria-pressed={label===value} onClick={()=>annotate(value)}>{text}</button>)}</div><p className="note">标注用于对照，不改变系统判断。<br/>默认测试最长 10 分钟；关闭页面后约 20 秒停止。</p></article>
    </section>
    <section className="panel records"><div className="record-heading"><h2>判断记录</h2><span>{running?`已运行 ${Math.floor(state.elapsed||0)} 秒`:'等待测试'}</span></div>{plan&&<p className="plan">最近规划：{name(plan.intent)} · {plan.primitives.map(p=>`${p[0]} × ${p[1]}`).join(' + ')||'功能轨迹'} · γ {plan.gamma} · {plan.duration}s · {plan.plan_ms}ms</p>}<div className="table-scroll"><table><thead><tr><th>时间</th><th>来源</th><th>发生了什么</th></tr></thead><tbody>{state.events?.length?[...state.events].reverse().map(e=><tr key={e.id}><td>{e.t.toFixed(1)}s</td><td>{name(e.src)}</td><td><details><summary>{describe(e)}</summary><pre>{JSON.stringify(e.data,null,2)}</pre></details></td></tr>):<tr><td className="empty" colSpan="3">开始测试后显示真实事件</td></tr>}</tbody></table></div></section>
    <footer>本机原型 · 摄像头画面不落盘 · 日志仅保存观测数值、事件与标注 · 照明与手势控制已接框架，真实照度及手部传感器待接入</footer>
  </main>;
}
