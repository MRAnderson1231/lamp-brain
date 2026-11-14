import pytest

from lampkit.config import load_profile
from lampkit.control.world import World, Sample
from lampkit.control.lighting import Lighting
from lampkit.control.gestures import Gestures
from lampkit.control.tracking import Tracking
from lampkit.infra import ManualClock
from lampkit.runtime import Runtime
from lampkit.sensors import ScriptedSensor
from lampkit.types import Event
from lampkit.bodies import NullBody
from lampkit.replay import replay
from lampkit.motion.kinematics import Rig


def config():
    return load_profile('proactive',['body.type="null"','bridge.enabled=false','camera.enabled=false'])


def test_fusion_separates_modes_and_rejects_old_task_and_stale_sensors():
    w=World(config())
    assert w.observe(Event(0,'obs.face',{'present':True},'camera'),0)[0]
    assert w.mode(0)=='present'
    w.observe(Event(0,'app.session',{'active':True},'ipad'),0)
    assert w.mode(0)=='studying'
    w.observe(Event(0,'app.task',{'task_id':'new'},'ipad'),0)
    assert not w.observe(Event(.1,'app.correct',{'task_id':'old'},'ipad'),.1)[0]
    assert not w.observe(Event(0,'obs.face',{'present':True},'camera'),10)[0]
    w.observe(Event(.2,'app.exam',{'active':True},'ipad'),.2)
    w.observe(Event(.3,'user.study_intent',{'value':'not_now'},'user'),.3)
    assert w.mode(.3)=='exam'
    w.observe(Event(.4,'app.exam',{'active':False},'ipad'),.4)
    assert w.mode(.4)=='break'


def test_illumination_requires_lux_and_manual_override_has_priority():
    cfg=config();w=World(cfg);light=Lighting(cfg)
    relative=Sample({'measurement':'relative_image','brightness':1},'camera',0,10,1)
    initial=light.glow
    for i in range(10):light.step(i*.1,.1,relative,w)
    assert light.glow==initial
    calibrated=Sample({'measurement':'workplane_total','calibrated':True,'lux':1000},'lux',0,10,1)
    for i in range(10):light.step(1+i*.1,.1,calibrated,w)
    assert light.glow<initial
    assert w.observe(Event(2,'user.light',{'glow':1.3},'user'),2)[0]
    before=light.glow
    light.step(2,.1,calibrated,w)
    assert light.glow>before and light.mode=='manual'
    assert not w.observe(Event(2,'obs.ambient',{'measurement':'workplane_total','calibrated':False,'lux':100},'camera'),2)[0]


def test_table_swipe_requires_engagement_and_lost_tracking_releases():
    g=Gestures(config())
    def sample(y,engaged=True):return Sample({'zone':'table','engaged':engaged,'position':[0,y,0],'hand_id':'a'},'hands',0,10,1)
    assert not g.step(0,sample(0,False),(0,0,.3))['active']
    assert not g.step(.1,sample(0),(0,0,.3))['active']
    out=g.step(.5,sample(.1),(0,0,.3))
    assert out['active'] and out['glow_delta']>0 and out['head_target'] is None
    assert not g.step(.6,None,(0,0,.3))['active']
    assert not g.step(.7,sample(.1),(0,0,.3),allowed=False)['active']


def test_position_tracking_rejects_unreachable_workspace_and_solves_nearby():
    cfg=config();k=cfg['kinematics'];rig=Rig(k['scale'],k['head_scale'],limits=k['limits']);tracker=Tracking(cfg,rig)
    q={c:0.0 for c in k['limits']};p,_=rig.beam(q)
    result,err,status=tracker.solve(p,q)
    assert result is not None and err<.001
    assert tracker.solve((9,9,9),q)[2]=='outside_workspace'


def test_v2_end_to_end_contracts_exam_freeze_and_exact_replay(tmp_path):
    cfg=config();cfg['body']={'type':'null'}
    sc=ScriptedSensor('scenarios/proactive_architecture.json')
    log=tmp_path/'v2.jsonl';body=NullBody(keep=True)
    rt=Runtime(cfg,ManualClock(),[sc],body,log_path=log)
    rt.simulate(sc.duration)
    assert any(e.kind=='control.rejected' and 'active task' in e.data['reason'] for e in rt.bus.history)
    assert not any(e.kind=='intervene' and 15<=e.t<20 for e in rt.bus.history)
    exam_frames=[p for p in body.frames if 15.1<=p['t']<19.9]
    for ch in cfg['kinematics']['limits']:
        assert max(p[ch] for p in exam_frames)==pytest.approx(min(p[ch] for p in exam_frames))
    states=[e for e in rt.bus.history if e.kind=='control.state']
    assert any(e.data['gesture']['mode']=='table' for e in states)
    assert any(e.data['lighting']['mode']=='manual' for e in states)
    rt.close()
    assert replay(str(log))['identical']


def test_task_reset_same_batch_preserves_new_task_stuck_signal():
    cfg=config();cfg['body']={'type':'null'}
    rt=Runtime(cfg,ManualClock(),body=NullBody())
    rt.bus.emit(Event(0,'app.task',{'task_id':'q1'},'ipad'))
    rt.bus.emit(Event(0,'app.stuck',{'task_id':'q1','conf':1},'ipad'))
    rt.tick()
    assert rt.est.stuck_conf==1
    rt.bus.emit(Event(0,'app.task',{'task_id':'q2'},'ipad'))
    rt.tick()
    assert rt.est.stuck_conf==0
    rt.close()


def test_hint_must_be_accepted_and_rechecked_against_exam_mode():
    cfg=config();clock=ManualClock();rt=Runtime(cfg,clock,body=NullBody())
    for kind,data in [('obs.face',{'present':True}),('app.session',{'active':True}),('app.task',{'task_id':'q1'})]:
        rt.bus.emit(Event(0,kind,data,'test'))
    rt.tick()
    rt.policy.fire(0,'show_hint','confused')
    requests=[e for e in rt.bus.history if e.kind=='lamp.request']
    assert [e.data['action'] for e in requests]==['offer_hint']
    token=requests[0].data['intervention']
    rt.bus.emit(Event(0,'app.exam',{'active':True},'ipad'))
    rt.bus.emit(Event(0,'app.hint_feedback',{'task_id':'q1','accepted':True,'intervention':token},'ipad'))
    assert not any(e.kind=='lamp.request' and e.data['action']=='show_hint' for e in rt.bus.history)
    assert rt.control.hint_offer is None
    rt.close()
