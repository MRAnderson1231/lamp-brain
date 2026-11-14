"""Continuous, bounded position IK for manual head goals. Not a collision/physics solver."""
from __future__ import annotations

from ..motion.kinematics import CHANNELS


class Tracking:
    def __init__(self, cfg, rig):
        self.c = cfg['control']['tracking']
        self.rig = rig
        self.next_plan = -float('inf')
        self.goal = None
        self.status = 'inactive'
        self.error = None

    def reset(self):
        self.next_plan = -float('inf')
        self.goal = None
        self.status = 'inactive'
        self.error = None

    def solve(self, target, pose):
        c = self.c
        if any(not low <= value <= high for value,low,high in zip(target,c['workspace_min'],c['workspace_max'])):
            return None, None, 'outside_workspace'
        q = self.rig.clamp({key:pose.get(key,0.0) for key in CHANNELS})
        def score(candidate):
            p,_ = self.rig.beam(candidate)
            distance = sum((a-b)**2 for a,b in zip(p,target))
            smooth = sum((candidate[k]-pose.get(k,0.0))**2 for k in CHANNELS)
            return distance+c['posture_weight']*smooth
        best, step = score(q), c['search_step_deg']
        for _ in range(c['iterations']):
            changed = False
            for key in c['channels']:
                for sign in (-1,1):
                    candidate = self.rig.clamp(dict(q, **{key:q[key]+step*sign}))
                    cost = score(candidate)
                    if cost < best-c['cost_epsilon']:
                        q,best,changed = candidate,cost,True
            if not changed:
                step *= c['step_decay']
            if step < c['minimum_step_deg']:
                break
        p,_ = self.rig.beam(q)
        error = sum((a-b)**2 for a,b in zip(p,target))**.5
        return (q if error<=c['tolerance_m'] else None),error,('tracking' if error<=c['tolerance_m'] else 'unreachable')

    def step(self,t,target,pose):
        if target is None:
            self.reset()
            return None
        if t>=self.next_plan:
            self.goal,self.error,self.status=self.solve(target,pose)
            self.next_plan=t+1/self.c['hz']
        return self.goal
