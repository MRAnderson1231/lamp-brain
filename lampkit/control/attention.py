"""Quiet continuous gaze: task lighting first, face attention otherwise.

Coordinates are desk-frame metres; face positions are monocular estimates. This is
orientation control for a simulation, not calibrated collision-aware physical motion.
"""
from __future__ import annotations

from .world import finite


class Attention:
    def __init__(self, cfg, rig):
        self.c = cfg['control'].get('attention', {})
        self.posture = cfg['motion']['posture']
        self.rig = rig
        self.reset()

    def reset(self):
        self.target = self.goal = None
        self.next_plan = -float('inf')
        self.source = None
        self.status = 'inactive'

    def step(self, t, world, pose, allowed):
        face, work = world.fresh('obs.face', t), world.fresh('obs.work_target', t)
        target, source = None, None
        if work:
            target, source = work.data['position'], 'work_target'
        elif face and face.data.get('present'):
            target = [face.data.get(k) for k in ('x', 'y', 'z')]
            source = 'face_estimate'
        if not allowed or target is None or not all(finite(v) for v in target):
            self.reset()
            return None
        if any(not lo <= v <= hi for v, lo, hi in zip(target, self.c['target_min'], self.c['target_max'])):
            self.reset()
            self.status = 'target_out_of_range'
            return None
        changed = self.target is None or source != self.source or sum((a-b)**2 for a,b in zip(target,self.target))**.5 >= self.c['deadband_m']
        if t >= self.next_plan and changed:
            raw = self.rig.look_at(tuple(target), self.posture, start=pose)
            self.goal = self.rig.clamp(raw)
            self.target, self.source = list(target), source
            self.next_plan = t+1/self.c['hz']
        self.status = 'tracking' if self.goal else 'waiting'
        return self.goal

    def snapshot(self):
        return {'status': self.status, 'source': self.source, 'target': self.target}
