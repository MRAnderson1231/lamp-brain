"""Time-bounded world model. Sensor evidence and explicit instructions stay distinct."""
from __future__ import annotations

import math
from dataclasses import dataclass

from ..types import Event


def finite(value, lo=-float('inf'), hi=float('inf')):
    return type(value) in (int, float) and math.isfinite(value) and lo <= value <= hi


@dataclass
class Sample:
    data: dict
    source: str
    observed: float
    expires: float
    quality: float


class World:
    def __init__(self, cfg):
        self.c = cfg['control']['fusion']
        self.samples = {}
        self.seen = {}
        self.session = False
        self.exam = False
        self.rest = False
        self.reluctant = False
        self.task_id = None
        self.quiet_until = 0.0
        self.manual_light = {}
        self.manual_until = 0.0
        self.hour = None
        self.task_changed = False
        self.standalone = cfg['control'].get('companion', {}).get('enabled', False)
        self.companion_mode = 'idle'

    def observe(self, ev: Event, now: float):
        d, k = ev.data, ev.kind
        if not isinstance(d, dict):
            return False, 'data is not an object'
        if self.standalone and k.startswith('app.'):
            return False, 'Margin integration disabled in companion profile'
        observed = d.get('observed_at', ev.t)
        quality = d.get('quality', 1.0)
        ttl = self.c['ttl'].get(k, self.c['default_ttl'])
        if not finite(observed) or observed > now + self.c['future_tolerance']:
            return False, 'invalid or future timestamp'
        if not finite(quality, 0, 1):
            return False, 'invalid observation quality'
        if (k.startswith('obs.') or k in self.c['task_scoped']) and (now - observed > ttl or quality < self.c['min_quality']):
            return False, 'stale or low-quality observation'
        sid = d.get('sample_id')
        if sid is not None:
            if not isinstance(sid, str) or len(sid) > self.c['max_id_length']:
                return False, 'invalid sample id'
            key = (ev.src, sid)
            if key in self.seen:
                return False, 'duplicate sample'
            self.seen[key] = now
            if len(self.seen) > self.c['dedup_limit']:
                del self.seen[next(iter(self.seen))]
        if k in ('obs.face', 'obs.occupancy') and type(d.get('present')) is not bool:
            return False, 'presence must be boolean'
        if k == 'obs.face':
            blend = d.get('blend', {})
            if not isinstance(blend, dict) or not all(finite(v, 0, 1) for v in blend.values()):
                return False, 'invalid face coefficients'
            if any(key in d for key in ('x', 'y', 'z')) and not all(finite(d.get(key)) for key in ('x', 'y', 'z')):
                return False, 'face coordinates must be finite'
            if any(key in d and not finite(d[key]) for key in ('yaw', 'pitch')):
                return False, 'face orientation must be finite'
        if k == 'obs.clock':
            if not finite(d.get('local_hour'), 0, 24):
                return False, 'invalid local clock hour'
            self.hour = d['local_hour']
        if k == 'obs.occupancy' and d.get('posture', 'unknown') not in ('seated', 'standing', 'unknown'):
            return False, 'invalid observed posture'
        if k == 'obs.work_target':
            p = d.get('position')
            if d.get('calibrated') is not True or d.get('frame') != 'desk_m' or not isinstance(p, list) or len(p) != 3 or not all(finite(x) for x in p):
                return False, 'work target requires calibrated desk coordinates'
        if k == 'obs.judgment':
            if not all(finite(d.get(key), 0, 1) for key in ('interruptible', 'fatigue_cues')):
                return False, 'judgment requires bounded probabilities'
            if not isinstance(d.get('model'), str) or not isinstance(d.get('evidence_id'), str):
                return False, 'judgment requires model and evidence provenance'
        if k == 'obs.ambient':
            if d.get('measurement') not in ('relative_image', 'workplane_total'):
                return False, 'ambient measurement requires units and measurement type'
            if d['measurement'] == 'workplane_total':
                if d.get('calibrated') is not True or not finite(d.get('lux'), 0, self.c['max_lux']):
                    return False, 'closed-loop lux must be calibrated'
            elif not finite(d.get('brightness'), 0, 1):
                return False, 'image brightness must be normalized'
        if k == 'obs.hand':
            if d.get('zone') not in ('table', 'head', 'none') or type(d.get('engaged')) is not bool:
                return False, 'hand requires an interaction zone and engagement flag'
            p = d.get('position')
            if d['zone'] != 'none' and (d.get('calibrated') is not True or d.get('frame') != 'desk_m' or not isinstance(p, list) or len(p) != 3 or not all(finite(x) for x in p)):
                return False, 'hand position must be calibrated desk metres'
            if d.get('command', 'follow') not in ('follow', 'beckon', 'away', 'raise', 'lower'):
                return False, 'unknown hand command'
            if d.get('command', 'follow') != 'follow' and not isinstance(d.get('gesture_id'), str):
                return False, 'discrete hand commands require a gesture id'
        if k.startswith('app.') and k in self.c['task_scoped']:
            if self.task_id is not None and d.get('task_id') != self.task_id:
                return False, 'message does not belong to the active task'
        if k.startswith('obs.') or k in ('app.stuck', 'app.pencil'):
            previous = self.samples.get(k)
            if previous and observed < previous.observed:
                return False, 'out-of-order observation'
            self.samples[k] = Sample(dict(d), ev.src, observed, observed + ttl, quality)
        elif k == 'app.session':
            self.session = bool(d.get('active'))
            if not self.session:
                self.task_changed = True
                self.task_id = None
        elif k == 'app.task':
            if not isinstance(d.get('task_id'), str) or not d['task_id']:
                return False, 'task_id is required'
            self.task_changed = self.task_id != d['task_id']
            self.task_id = d['task_id']
        elif k == 'app.exam':
            self.exam = bool(d.get('active'))
        elif k == 'app.break':
            self.rest = bool(d.get('active'))
        elif k == 'user.study_intent':
            if d.get('value') not in ('ready', 'not_now'):
                return False, 'unknown study intent'
            self.reluctant = d['value'] == 'not_now'
        elif k == 'user.pat':
            self.quiet_until = now + self.c['quiet_seconds']
        elif k == 'user.light':
            allowed = {'glow', 'kelvin', 'auto'}
            if not set(d).issubset(allowed) or not d:
                return False, 'unknown light setting'
            if 'auto' in d and type(d['auto']) is not bool:
                return False, 'auto must be boolean'
            if 'glow' in d and not finite(d['glow'], 0, self.c['max_glow']):
                return False, 'invalid brightness'
            if 'kelvin' in d and not finite(d['kelvin'], *self.c['kelvin_range']):
                return False, 'invalid color temperature'
            if d.get('auto'):
                self.manual_light, self.manual_until = {}, now
            else:
                self.manual_light.update({k: v for k, v in d.items() if k != 'auto'})
                self.manual_until = now + self.c['manual_light_seconds']
        elif k == 'app.context':
            if not finite(d.get('local_hour'), 0, 24):
                return False, 'local_hour must be supplied explicitly'
            self.hour = d['local_hour']
        return True, ''

    def fresh(self, kind, t):
        sample = self.samples.get(kind)
        return sample if sample and sample.expires >= t else None

    def mode(self, t):
        if self.exam:
            return 'exam'
        if self.rest or self.reluctant:
            return 'break'
        if self.standalone:
            return self.companion_mode
        face = self.fresh('obs.face', t)
        present = bool(face and face.data.get('present'))
        if self.session:
            return 'studying' if present else 'away'
        return 'present' if present else 'idle'

    def snapshot(self, t):
        return {'mode': self.mode(t), 'session_active': self.session, 'task_id': self.task_id,
                'exam': self.exam, 'reluctant': self.reluctant,
                'sources': {k: {'source': s.source, 'age': round(t-s.observed, 3),
                               'fresh': s.expires >= t, 'quality': s.quality}
                            for k, s in self.samples.items()}}
