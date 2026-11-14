"""The console must not turn labels into evidence or bypass runtime constraints."""
import json
import threading
import time
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from lampkit.config import load_profile
from lampkit.infra import ManualClock
from lampkit.lab import Lab, LabInbox, make_handler
from lampkit.runtime import Runtime
from lampkit.bodies import NullBody
from lampkit.types import Event


def test_labels_cannot_inject_evidence_and_exam_still_vetoes():
    inbox = LabInbox(20)
    cfg = load_profile('sim', ['personalize.enabled=false', 'personalize.state_file=null'])
    clock = ManualClock()
    rt = Runtime(cfg, clock, [inbox], body=NullBody())
    for i in range(140):
        rt.bus.emit(Event(clock.now(), 'obs.face', {'present': True}, 'test-camera'))
        rt.tick()
        clock.advance(.05)
    before = rt.fsm.study
    inbox.submit({'kind':'lab.annotation','data':{'label':'confused'}})
    rt.tick()
    assert rt.fsm.study == before
    assert rt.est.stuck_conf == 0
    assert rt.bus.history[-1].kind != 'obs.vlm'
    with pytest.raises(ValueError):
        inbox.submit({'kind':'obs.face','data':{'present':True}})
    with pytest.raises(ValueError):
        inbox.submit({'kind':'intervene','data':{'intent':'celebrate'}})
    inbox.submit({'kind':'app.exam','data':{'active':True}})
    inbox.submit({'kind':'app.correct','data':{}})
    start=len(rt.bus.history)
    rt.tick()
    assert rt.est.exam
    assert not any(e.kind=='intervene' and e.data['motion'] for e in rt.bus.history[start:])
    assert any(e.kind=='lab.annotation' and e.src=='self-report' for e in rt.bus.history)
    assert any(e.kind=='app.exam' and e.src=='mock-margin' for e in rt.bus.history)
    rt.close()


def test_local_server_guards_camera_and_never_serves_project_files(tmp_path):
    (tmp_path/'index.html').write_text('lab')
    lab=Lab(load_profile('sim'))
    server=ThreadingHTTPServer(('127.0.0.1',0),make_handler(lab,tmp_path))
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    url=f'http://127.0.0.1:{server.server_port}'
    def request(path, data=None, headers=None):
        return urllib.request.urlopen(urllib.request.Request(url+path, data=data, headers=headers or {}))
    try:
        assert json.load(request('/api/state'))['status']=='stopped'
        assert request('/api/frame.jpg').status==204
        for path,data,headers,code in [
            ('/api/start',b'{}',{},403),
            ('/api/start',b'{}',{'X-Lamp-Lab':'1','Origin':'https://example.org'},403),
            ('/api/state',None,{'Host':'evil.test'},403),
            ('/../profiles/base.json',None,{},404),
            ('/api/event',b'{"kind":"app.correct"}',{'X-Lamp-Lab':'1'},400),
        ]:
            with pytest.raises(urllib.error.HTTPError) as err:
                request(path,data,headers)
            assert err.value.code==code
        assert lab.thread is None
    finally:
        server.shutdown();server.server_close();thread.join()


def test_automatic_timeout_releases_camera_and_restart_has_fresh_inbox():
    cameras=[]
    class FakeCamera:
        def __init__(self,cfg,clock):
            self.thread=threading.current_thread()
            self.closed=False
            cameras.append(self)
        def frame(self): return None
        def poll(self,t): return [Event(t,'obs.face',{'present':False},'test-camera')]
        def close(self): self.closed=True
    cfg=load_profile('sim',['lab.max_seconds=0.08','bridge.enabled=false'])
    lab=Lab(cfg,camera_factory=FakeCamera)
    lab.start()
    lab.thread.join(timeout=3)
    assert not lab.thread.is_alive()
    assert lab.snapshot()['status']=='stopped'
    assert cameras[0].closed
    first=lab.inbox
    first.submit({'kind':'app.exam','data':{'active':True}})
    lab.start()
    lab.thread.join(timeout=3)
    assert not lab.thread.is_alive()
    assert lab.inbox is not first
    assert cameras[1].closed
    assert lab.snapshot()['exam'] is False
    assert lab.jpeg is None
