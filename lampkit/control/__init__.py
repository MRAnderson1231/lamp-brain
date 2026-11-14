"""Proactive control orchestration: world -> manual goals -> arbitration -> motion/light."""
from __future__ import annotations

from .world import World
from .gestures import Gestures
from .lighting import Lighting
from .tracking import Tracking
from .companion import Companion
from .attention import Attention
from ..types import Event


class ControlStack:
    def __init__(self,cfg,rig):
        self.cfg,self.c,self.rig=cfg,cfg['control'],rig
        self.world=World(cfg)
        self.gestures=Gestures(cfg)
        self.lighting=Lighting(cfg)
        self.tracking=Tracking(cfg,rig)
        self.companion=Companion(cfg)
        if self.companion.enabled:
            self.lighting.glow=0.0
        self.attention=Attention(cfg,rig)
        self.firing_companion=False
        self.manual={'active':False,'glow_delta':0.0,'head_target':None,'mode':'inactive'}
        self.previous_mode=None
        self.was_manual=False
        self.was_quiet=False
        self.next_log=0.0
        self.hint_offer=None

    def observe(self,ev,now,emit):
        accepted,reason=self.world.observe(ev,now)
        if not accepted:
            emit(Event(now,'control.rejected',{'kind':ev.kind,'source':ev.src,'reason':reason},'fusion'))
        return accepted

    def prepare(self,t,player,est,fsm,policy,emit):
        w=self.world
        proposals=self.companion.step(t,w) if self.companion.enabled else []
        mode=w.mode(t)
        if w.task_changed:
            self.reset_task(t,est,fsm,policy,emit)
        if not w.fresh('app.stuck',t):
            est.stuck_conf=0.0;est.stuck_since=None;est.stuck_region=None
        if not w.fresh('obs.phone',t):
            est.docked=True;est.in_hand.value=0.0
        if mode!='studying':
            policy.ladder_next=None
        head,_=self.rig.beam(player.pose)
        self.manual=self.gestures.step(t,w.fresh('obs.hand',t),head,allowed=not w.exam)
        active=self.manual['active']
        quiet=t<w.quiet_until
        if active != self.was_manual or quiet and not self.was_quiet or mode != self.previous_mode and mode in ('exam','break','idle','away','present','sensor_unknown'):
            player.freeze()
            self.tracking.reset()
            self.attention.reset()
        if mode!=self.previous_mode:
            emit(Event(t,'control.mode',{'previous':self.previous_mode,'mode':mode},'fusion'))
            if mode=='studying' and self.previous_mode in ('present','break','away'):
                policy.fire(t,'settle','studying',reason='explicit session active')
        self.was_manual,self.previous_mode=active,mode
        self.was_quiet=quiet
        self.firing_companion=True
        try:
            for intent,reason in proposals:
                policy.fire(t,intent,'companion',reason=reason)
        finally:
            self.firing_companion=False

    def reset_task(self,t,est,fsm,policy,emit):
        est.stuck_conf=0.0;est.stuck_since=None;est.stuck_region=None;est.last_stroke=None;est.erases.clear()
        self.world.samples.pop('app.stuck',None);self.world.samples.pop('app.pencil',None)
        for track in fsm.tracks.values():
            track.reset()
        fsm.last_confused=-1e9
        policy.ladder_next=None
        for old in policy.pending:
            emit(Event(t,'outcome.unscored',{'intervention':old['id'],'intent':old['intent'],'reason':'task changed','evaluated':False},'control'))
        policy.pending.clear()
        self.world.task_changed=False
        self.hint_offer=None

    def guard(self,ev):
        w,d=self.world,ev.data
        if w.exam:
            return None
        if self.manual['active']:
            return None
        mode=w.mode(ev.t)
        if self.companion.enabled:
            if not self.firing_companion or mode=='break' and d['intent'] not in self.c['arbiter']['quiet_allowed']:
                return None
        elif mode!='studying' and d['intent'] not in self.c['arbiter']['nonstudy_intents']:
            return None
        if ev.t<w.quiet_until and d['intent'] not in self.c['arbiter']['quiet_allowed']:
            return None
        return ev

    def request_guard(self,ev):
        if self.companion.enabled:
            return None
        if self.world.mode(ev.t)!='studying' or self.manual['active'] or ev.t<self.world.quiet_until:
            return None
        if ev.data.get('action')=='show_hint' and not ev.data.get('accepted_offer'):
            self.hint_offer={'intervention':ev.data['intervention'],'task_id':self.world.task_id,'t':ev.t}
            return Event(ev.t,ev.kind,dict(ev.data,action='offer_hint',task_id=self.world.task_id),'control')
        return ev

    def hint_feedback(self,ev,emit):
        offer=self.hint_offer
        if not offer or ev.data.get('intervention')!=offer['intervention'] or ev.t-offer['t']>self.c['arbiter']['hint_offer_ttl']:
            emit(Event(ev.t,'control.rejected',{'kind':ev.kind,'reason':'no matching fresh hint offer'},'control'))
            return
        self.hint_offer=None
        if ev.data.get('accepted'):
            emit(Event(ev.t,'lamp.request',{'action':'show_hint','intervention':offer['intervention'],
                       'task_id':offer['task_id'],'accepted_offer':True},'control'))

    def output(self,t,dt,player,condition,emit):
        w=self.world
        target=self.manual['head_target'] if condition=='expressive' and not w.exam else None
        goal=self.tracking.step(t,target,player.pose)
        continuous=condition=='expressive' and self.companion.enabled and w.mode(t)=='active' and not self.manual['active'] and not player.busy and t>=w.quiet_until
        gaze=self.attention.step(t,w,player.pose,continuous)
        override=self.lighting.step(t,dt,w.fresh('obs.ambient',t),w,self.manual['glow_delta'],
                                    self.companion.active if self.companion.enabled else None)
        if goal:
            override.update(goal)
        elif gaze:
            override.update(gaze)
        player.breathing=condition=='expressive' and not w.exam and not self.manual['active'] and w.mode(t)=='studying' and t>=w.quiet_until
        freeze=w.exam or condition=='static' or self.manual['active'] and goal is None
        pose=player.step(t,dt,freeze_motion=freeze,target_override=override)
        if (goal or gaze) and not player.busy:
            # Losing a tracking target should hold the reached pose, not spring back
            # to a stale authored animation endpoint.
            player.hold.update({key:pose[key] for key in self.rig.limits})
        for key,(lo,hi) in self.rig.limits.items():
            clipped=max(lo,min(hi,pose[key]))
            if clipped!=pose[key]:
                player.springs[key].x=clipped;player.springs[key].v=0
                pose[key]=clipped
        if t>=self.next_log:
            emit(Event(t,'control.state',self.snapshot(t),'control'))
            self.next_log=t+self.c['log_every']
        return pose

    def snapshot(self,t):
        return {'world':self.world.snapshot(t),'gesture':dict(self.manual),
                'service':self.companion.snapshot(),'attention':self.attention.snapshot(),
                'hint_offer':self.hint_offer if self.hint_offer and t-self.hint_offer['t']<=self.c['arbiter']['hint_offer_ttl'] else None,
                'lighting':self.lighting.snapshot(),'tracking':{'status':self.tracking.status,'error_m':self.tracking.error},
                'capabilities':{'ambient_sensor':bool(self.world.fresh('obs.ambient',t)),
                                'hand_sensor':bool(self.world.fresh('obs.hand',t)),
                                'physics_validated':False,'hardware_connected':False}}
