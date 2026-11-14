from concurrent.futures import Future

import pytest

from lampkit.config import load_profile
from lampkit.control.companion import Companion
from lampkit.control.world import World
from lampkit.control.world import Sample
from lampkit.control.gestures import Gestures
from lampkit.infra import ManualClock
from lampkit.runtime import Runtime
from lampkit.bodies import NullBody
from lampkit.sensors import ScriptedSensor
from lampkit.sensors.decision import DecisionSensor
from lampkit.types import Event
from lampkit.replay import replay


def cfg():
    return load_profile('companion', ['body.type="null"', 'camera.enabled=false'])


def test_single_frozen_face_does_not_confirm_arrival_or_fatigue():
    c=cfg();w=World(c);service=Companion(c)
    w.observe(Event(0,'obs.face',{'present':True,'blend':{'eyeBlink':1}},'camera'),0)
    for i in range(20):
        assert service.step(i*.1,w)==[]
    assert not service.active and not service.fatigue_cue
    assert service.mode=='sensor_unknown'


def test_standing_and_missing_posture_do_not_count_as_sitting():
    c=cfg();w=World(c);service=Companion(c)
    for i in range(40):
        t=i*.1
        w.observe(Event(t,'obs.occupancy',{'present':True,'posture':'standing'},'pose'),t)
        service.step(t,w)
    assert service.active and service.seated_seconds==0
    assert service.desk_seconds>0
    assert not w.observe(Event(4,'app.session',{'active':True},'ipad'),4)[0]
    assert not w.session


def test_unknown_sensor_is_not_absence_and_explicit_standing_resets_timer():
    c=cfg();c['control']['companion'].update(standing_reset_after=.3,arrive_after=.1)
    w=World(c);s=Companion(c)
    for i in range(20):
        t=i*.1
        w.observe(Event(t,'obs.occupancy',{'present':True,'posture':'seated' if i<10 else 'standing'},'pose'),t)
        s.step(t,w)
    assert s.seated_seconds==0 and s.desk_seconds==0
    assert not s.step(5,w)
    assert s.mode=='sensor_unknown' and s.active
    assert not s.step(66,w)
    assert not s.active and 'sensor timeout' in s.reason


def test_standalone_lifecycle_motion_and_exact_replay_without_margin(tmp_path):
    c=cfg();sc=ScriptedSensor('scenarios/companion.json')
    body=NullBody(keep=True);log=tmp_path/'companion.jsonl'
    rt=Runtime(c,ManualClock(),[sc],body,log_path=log)
    rt.simulate(sc.duration)
    acts=[e for e in rt.bus.history if e.kind=='intervene']
    assert {'hello','care_check','sleep'} <= {e.data['intent'] for e in acts}
    assert not any(e.kind=='lamp.request' for e in rt.bus.history)
    assert not any(e.kind.startswith('app.') for e in rt.bus.history)
    states=[e.data for e in rt.bus.history if e.kind=='control.state']
    assert any(s['attention']['source']=='face_estimate' for s in states)
    assert any(s['attention']['source']=='work_target' for s in states)
    assert min(p['glow'] for p in body.frames if 49<=p['t']<50)<.02
    assert body.frames[-1]['glow']>.9
    assert all(not p['service']['seated_seconds'] for p in states)
    rt.close()
    assert replay(str(log))['identical']


def test_budgeted_dwell_reminder_and_dismissal():
    c=cfg();c['control']['companion'].update(desk_after=3,arrive_after=.1)
    clock=ManualClock();rt=Runtime(c,clock,body=NullBody())
    for i in range(60):
        t=i*.1;clock.t=t
        rt.bus.emit(Event(t,'obs.face',{'present':True},'camera'))
        rt.tick()
    reminders=[e for e in rt.bus.history if e.kind=='intervene' and e.data['intent']=='stretch_reminder']
    assert len(reminders)==1
    assert rt.policy.budget_log
    assert reminders[0].data['reason']=='desk_presence_proxy'
    clock.t=6
    rt.bus.emit(Event(6,'user.pat',{},'user'))
    rt.tick()
    assert not rt.player.busy
    assert rt.control.world.quiet_until>6
    rt.close()


def test_decision_adapter_never_accepts_commands_or_refreshes_old_evidence():
    sensor=DecisionSensor(cfg(),lambda evidence: {})
    sensor.observed=1; sensor.sequence=1
    sensor.future=Future();sensor.future.set_result({'model':'mock','fatigue_cues':.9,'interruptible':.8,'motor':999})
    ev=sensor.poll(10)[0]
    assert ev.kind=='obs.judgment' and ev.data['observed_at']==1 and 'motor' not in ev.data
    assert not World(cfg()).observe(ev,10)[0]
    sensor.future=Future();sensor.future.set_result({'model':'mock','fatigue_cues':float('nan'),'interruptible':1})
    assert sensor.poll(11)[0].kind=='sensor.error'
    sensor.close()


def test_head_command_is_discrete_and_near_hand_yield_has_priority():
    g=Gestures(cfg())
    data={'zone':'head','engaged':True,'hand_id':'right','position':[0,-.3,.3],
          'command':'raise','gesture_id':'one'}
    hand=Sample(data,'test',0,10,1)
    g.step(0,hand,(0,0,.3))
    first=g.step(.4,hand,(0,0,.3))['head_target']
    assert first[2]>.3
    assert g.step(.5,hand,(0,0,.31))['head_target']==first
    data=dict(data,position=[0,-.1,.3],gesture_id='two')
    near=g.step(.6,Sample(data,'test',.6,10,1),(0,0,.3))['head_target']
    assert near[1]>0 and near[2]==pytest.approx(.3)


def test_no_startup_flash_and_clock_color_temperature_without_app():
    clock=ManualClock();body=NullBody(keep=True);rt=Runtime(cfg(),clock,body=body)
    rt.bus.emit(Event(0,'obs.clock',{'local_hour':22},'local-clock'))
    rt.simulate(2)
    assert max(p['glow'] for p in body.frames)<=.05
    assert rt.control.lighting.kelvin<3500
    assert rt.control.lighting.mode=='occupancy_off'
    rt.close()


def test_model_can_suppress_but_cannot_invent_visible_fatigue():
    c=cfg();c['control']['companion']['arrive_after']=.1
    w=World(c);service=Companion(c)
    for i in range(30):
        t=i*.1
        w.observe(Event(t,'obs.face',{'present':True,'blend':{'eyeBlink':0}},'camera'),t)
        w.observe(Event(t,'obs.judgment',{'fatigue_cues':1,'interruptible':1,'model':'mock','evidence_id':str(i)},'decision'),t)
        assert all(intent!='care_check' for intent,_ in service.step(t,w))
    for i in range(30,60):
        t=i*.1
        w.observe(Event(t,'obs.face',{'present':True,'blend':{'eyeBlink':1}},'camera'),t)
        w.observe(Event(t,'obs.judgment',{'fatigue_cues':1,'interruptible':0,'model':'mock','evidence_id':str(i)},'decision'),t)
        assert all(intent!='care_check' for intent,_ in service.step(t,w))
    assert service.fatigue_cue
