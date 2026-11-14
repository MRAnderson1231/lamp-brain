"""Explicitly engaged hand observations -> bounded manual control goals, never motor angles."""
from __future__ import annotations

import math


class Gestures:
    def __init__(self, cfg):
        self.c = cfg['control']['gestures']
        self.key = None
        self.since = None
        self.origin = None
        self.anchor = None
        self.last_swipe = -float('inf')
        self.active = False
        self.mode = 'inactive'
        self.last_command = None
        self.command_target = None

    def reset(self):
        self.key = self.since = self.origin = self.anchor = None
        self.active = False
        self.mode = 'inactive'
        self.command_target = None

    def step(self, t, sample, head, allowed=True):
        out = {'active': False, 'glow_delta': 0.0, 'head_target': None, 'mode': 'inactive'}
        if not allowed or sample is None or not sample.data.get('engaged') or sample.data.get('zone') == 'none':
            self.reset()
            return out
        d = sample.data
        key = (d.get('hand_id', 'primary'), d['zone'])
        position = tuple(d['position'])
        if key != self.key:
            self.key, self.since, self.origin, self.anchor = key, t, position, tuple(head)
        if t - self.since < self.c['engage_seconds']:
            self.mode = 'arming'
            return dict(out, mode='arming')
        self.active = out['active'] = True
        self.mode = out['mode'] = d['zone']
        if d['zone'] == 'table':
            dy = sum((a-b)*axis for a,b,axis in zip(position, self.origin, self.c['table_up_axis']))
            if abs(dy) >= self.c['swipe_metres'] and t-self.last_swipe >= self.c['swipe_cooldown']:
                out['glow_delta'] = math.copysign(self.c['brightness_step'], dy)
                self.origin, self.last_swipe = position, t
        else:
            # Relative virtual handle, with a higher-priority near-hand yielding region.
            separation = [h-p for h,p in zip(head, position)]
            distance = math.sqrt(sum(x*x for x in separation))
            if distance > self.c['max_distance'] or distance < self.c['minimum_tracking_distance']:
                self.reset()
                return out | {'active': False, 'mode': 'out_of_range'}
            if distance < self.c['yield_distance']:
                out['head_target'] = [h + v/distance*(self.c['yield_distance']-distance)*self.c['yield_gain']
                                      for h,v in zip(head,separation)]
            elif d.get('command', 'follow') != 'follow':
                command_key = (key, d['gesture_id'])
                if command_key != self.last_command:
                    direction = self.c['command_axes'][d['command']]
                    self.command_target = [h+v*self.c['command_step_m'] for h,v in zip(head,direction)]
                    self.last_command = command_key
                out['head_target'] = self.command_target
            else:
                out['head_target'] = [a+(p-o)*self.c['follow_gain'] for a,p,o in zip(self.anchor,position,self.origin)]
        return out
