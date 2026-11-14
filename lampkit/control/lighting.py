"""Independent working-light controller. Relative camera luminance cannot drive lux control."""
from __future__ import annotations

import math


def clamp(x, low, high):
    return max(low, min(high, x))


def approach(x, target, step):
    return x + clamp(target-x, -step, step)


class Lighting:
    def __init__(self, cfg):
        self.c = cfg['control']['lighting']
        self.glow = self.c['initial_glow']
        self.kelvin = self.c['initial_kelvin']
        self.integral = self.glow
        self.filtered_lux = None
        self.bright_since = None
        self.mode = 'hold_no_measurement'
        self.reason = 'no calibrated workplane sensor'

    def step(self, t, dt, sample, world, gesture_delta=0.0, service_active=None):
        c = self.c
        dt = min(max(0, dt), c['max_step'])
        if gesture_delta:
            world.manual_light['glow'] = clamp(self.glow+gesture_delta, 0, c['max_glow'])
            world.manual_until = t + world.c['manual_light_seconds']
        manual = world.manual_light if t < world.manual_until else {}
        goal = self.glow
        if 'glow' in manual:
            goal = manual['glow']
            self.integral = goal
            self.mode, self.reason = 'manual', 'explicit light control overrides automatic brightness'
        elif sample and sample.data.get('measurement') == 'workplane_total' and sample.data.get('calibrated'):
            lux = sample.data['lux']
            a = 1-math.exp(-dt/c['sensor_tau'])
            self.filtered_lux = lux if self.filtered_lux is None else self.filtered_lux+a*(lux-self.filtered_lux)
            error = c['target_lux']-self.filtered_lux
            if abs(error) <= c['deadband_lux']:
                error = 0
            proposal = self.integral+c['ki']*error*dt
            raw = c['kp']*error+proposal
            if 0 <= raw <= c['max_glow'] or raw < 0 and error > 0 or raw > c['max_glow'] and error < 0:
                self.integral = clamp(proposal, 0, c['max_glow'])
            goal = clamp(c['kp']*error+self.integral, 0, c['max_glow'])
            if self.filtered_lux > c['target_lux']+c['off_margin_lux']:
                if self.bright_since is None:
                    self.bright_since = t
                if t-self.bright_since >= c['off_delay']:
                    goal = 0.0
            else:
                self.bright_since = None
            self.mode, self.reason = 'auto_lux', 'calibrated total workplane illuminance'
        else:
            self.filtered_lux = None
            self.bright_since = None
            self.mode, self.reason = 'hold_no_measurement', 'missing/stale/uncalibrated light input; hold brightness'
        if service_active is False:
            # Occupancy shutdown overrides an earlier manual setting. Do not integrate
            # toward maximum brightness while the room is empty.
            goal = 0.0
            self.integral = c['initial_glow']
            self.mode, self.reason = 'occupancy_off', 'standalone service inactive'
        elif service_active is True and self.mode == 'hold_no_measurement':
            goal = c['initial_glow']
        target_kelvin = manual.get('kelvin', self.kelvin)
        if 'kelvin' not in manual and world.hour is not None:
            target_kelvin = c['day_kelvin'] if c['day_hours'][0] <= world.hour < c['day_hours'][1] else c['night_kelvin']
        self.glow = approach(self.glow, goal, c['glow_per_second']*dt)
        self.kelvin = approach(self.kelvin, target_kelvin, c['kelvin_per_second']*dt)
        warm, cold = c['kelvin_range']
        return {'glow': self.glow, 'warmth': clamp((cold-self.kelvin)/(cold-warm),0,1)}

    def snapshot(self):
        return {'mode':self.mode,'reason':self.reason,'glow':round(self.glow,4),
                'kelvin':round(self.kelvin),'filtered_lux':self.filtered_lux}
