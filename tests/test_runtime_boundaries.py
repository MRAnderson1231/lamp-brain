import copy
import json
import socket
import time
import pytest
from lampkit.bridge import IPadBridge, validate_message
from lampkit.config import load_profile
from lampkit.infra import ManualClock
from lampkit.runtime import Runtime
from lampkit.sensors import ReplaySensor
from lampkit.types import Event
from lampkit.replay import replay
from conftest import simulate

@pytest.mark.parametrize('message', [[], {'kind':'intervene'}, {'kind':'app.unknown'},
    {'kind':'app.exam','data':{'active':'false'}},
    {'kind':'app.stuck','data':{'conf':float('nan')}},
    {'kind':'app.stuck','data':{'conf':.9,'region':[.9,0,.2,.1]}},
    {'kind':'app.pencil','data':{'strokes':-1}}])
def test_bridge_rejects_malformed_inputs(message):
    with pytest.raises(ValueError): validate_message(message)

def test_tcp_bridge_roundtrip_and_bad_message_recovery():
    clock = ManualClock(10)
    bridge = IPadBridge(clock, port=0)
    try:
        with socket.create_connection(bridge.server.server_address) as client:
            client.settimeout(2)
            client.sendall(b'[]\n{"kind":"intervene"}\n{"kind":"app.stuck","data":{"conf":0.9}}\n')
            deadline = time.monotonic()+2
            events=[]
            while not events and time.monotonic()<deadline:
                events=bridge.poll(10); time.sleep(.005)
            assert [(e.kind,e.t) for e in events]==[('app.stuck',10)]
            bridge.send(Event(10,'lamp.request',{'action':'show_hint'}))
            reply=client.makefile('rb').readline()
            assert json.loads(reply)['data']['action']=='show_hint'
    finally: bridge.close()
    assert not bridge.thread.is_alive() and not bridge.sender.is_alive()

def test_exam_freezes_mid_animation_and_same_batch_moment():
    cfg=load_profile('sim')
    sensor=ReplaySensor([Event(0,'obs.face',{'present':True}),
        Event(1,'obs.face',{'present':True}), Event(1.1,'app.exam',{'active':True}),
        Event(1.1,'app.correct',{})])
    clock=ManualClock();rt=Runtime(cfg,clock,[sensor])
    for t in [0,1,1.05]:clock.t=t;rt.tick()
    assert rt.player.plan is not None
    before=rt.player.pose
    for t in [1.1,1.2,2,3]:
        clock.t=t;rt.tick()
        for k in ('yaw','low','up','nod','turn','hop','squash'):
            assert rt.player.pose[k]==before[k]
    assert not any(e.kind=='lamp.request' for e in rt.bus.history)

def test_replay_restores_irregular_ticks_delayed_inputs_and_saved_learning(tmp_path):
    cfg=load_profile('sim');state=tmp_path/'personal.json'
    cfg['personalize']['state_file']=str(state)
    state.write_text(json.dumps({'phone':[[2,3]]*18}))
    sensor=ReplaySensor([Event(100,'obs.face',{'present':True}),
        Event(101,'obs.face',{'present':True}), Event(102,'app.exam',{'active':True})])
    clock=ManualClock(100);log=tmp_path/'session.jsonl'
    rt=Runtime(cfg,clock,[sensor],log_path=log,seed=9)
    for t in [100,100.33,101.17,102.2,102.24,104.9]:clock.t=t;rt.tick()
    rt.close()
    state.write_text('{"phone": [[99,1]]}')
    prior=state.read_text()
    assert replay(str(log))['identical']
    assert state.read_text()==prior

def test_pat_suppresses_followup_nag():
    from lampkit.sensors import ScriptedSensor
    from conftest import SCENARIOS
    rt=Runtime(load_profile('sim'),ManualClock(),[ScriptedSensor(SCENARIOS/'phone.json'),
        ReplaySensor([Event(22,'user.pat',{})])])
    rt.simulate(45)
    assert not any(e.kind=='intervene' and e.data['intent']=='phone_nag' for e in rt.bus.history)

def test_learning_does_not_credit_superseded_interventions():
    rt,_,_=simulate('stuck',['personalize.enabled=false'])
    outcomes=[e.data for e in rt.bus.history if e.kind=='outcome.unscored']
    assert outcomes
    assert all(o['reward'] is None and not o['evaluated'] for o in outcomes)
    assert sum(e.kind=='outcome' and e.data['success'] for e in rt.bus.history)==1


def test_margin_tcp_input_reaches_policy_and_request_returns(tmp_path):
    clock=ManualClock()
    bridge=IPadBridge(clock,port=0)
    cfg=load_profile('sim',['personalize.enabled=false'])
    face=ReplaySensor([Event(i/10,'obs.face',{'present':True}) for i in range(2000)])
    rt=Runtime(cfg,clock,[face],bridge=bridge,log_path=tmp_path/'tcp.jsonl')
    try:
        with socket.create_connection(bridge.server.server_address) as client:
            client.settimeout(2)
            messages=[{'kind':'app.session','data':{'active':True}},
                      {'kind':'app.pencil','data':{'strokes':1}},
                      {'kind':'app.stuck','data':{'conf':1,'region':[.2,.3,.2,.1]}}]
            client.sendall(('\n'.join(json.dumps(m) for m in messages)+'\n').encode())
            deadline=time.monotonic()+2
            while time.monotonic()<deadline:
                with bridge.lock: count=len(bridge.inbox)
                if count==len(messages): break
                time.sleep(.005)
            assert count==len(messages)
            rt.simulate(180)
            reply=json.loads(client.makefile('rb').readline())
            assert reply['kind']=='lamp.request' and reply['data']['action']=='show_hint'
        rt.bus.log.flush()
        assert replay(str(tmp_path/'tcp.jsonl'))['identical']
    finally: rt.close()
