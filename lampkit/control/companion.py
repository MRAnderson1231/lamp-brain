"""Standalone service lifecycle. Face visibility is not proof of sitting or sleeping.

All timers use runtime time. Missing sensor data is distinct from observed absence;
model judgments may corroborate cues, never issue a motion command.
"""
from __future__ import annotations

from .world import finite


class Companion:
    def __init__(self, cfg):
        self.c = cfg['control'].get('companion', {'enabled': False})
        self.enabled = self.c['enabled']
        self.active = False
        self.mode = 'idle'
        self.reason = 'waiting for presence'
        self.previous_observation = None
        self.present_since = self.absent_since = self.unknown_since = None
        self.closed_since = self.yawn_since = None
        self.desk_seconds = self.seated_seconds = self.standing_seconds = 0.0
        self.fatigue_cue = False
        self.reminder_basis = 'desk_presence_proxy'

    def step(self, t, world):
        c = self.c
        face = world.fresh('obs.face', t)
        occupancy = world.fresh('obs.occupancy', t)
        sample = occupancy or face
        present = sample.data['present'] if sample else None
        stamp = sample.observed if sample else t
        # A frozen last frame must not count as multiple new observations.
        observed_dt = 0 if self.previous_observation is None else min(c['max_evidence_step'], max(0, stamp-self.previous_observation))
        self.previous_observation = stamp if sample else None
        intents = []
        if present is True:
            self.absent_since = self.unknown_since = None
            self.present_since = stamp if self.present_since is None else self.present_since
            if not self.active and stamp-self.present_since >= c['arrive_after']:
                self.active = True
                intents.append(('hello', 'sustained person presence'))
            self.mode = 'active' if self.active else 'arriving'
            self.reason = 'person visible' if occupancy else 'face visibility proxy'
            self.desk_seconds += observed_dt
            posture = occupancy.data.get('posture', 'unknown') if occupancy else 'unknown'
            if posture == 'seated':
                self.seated_seconds += observed_dt
                self.standing_seconds = 0
            elif posture == 'standing':
                self.standing_seconds += observed_dt
                if self.standing_seconds >= c['standing_reset_after']:
                    self.seated_seconds = self.desk_seconds = 0
            else:
                self.standing_seconds = 0
                # Missing posture cannot be counted as verified seated time.
                self.seated_seconds = 0
            self.reminder_basis = 'observed_seated' if posture == 'seated' else 'desk_presence_proxy'
            if self.active and (self.seated_seconds >= c['seated_after'] or
                                c['allow_desk_proxy'] and self.desk_seconds >= c['desk_after']):
                intents.append(('stretch_reminder', self.reminder_basis))
        elif present is False:
            self.present_since = self.unknown_since = None
            self.absent_since = t if self.absent_since is None else self.absent_since
            if t-self.absent_since >= c['absence_reset_after']:
                self.desk_seconds = self.seated_seconds = self.standing_seconds = 0
            if self.active and t-self.absent_since >= c['off_after']:
                self.active = False
                intents.append(('sleep', 'sustained observed absence'))
            self.mode = 'away' if self.active else 'idle'
            self.reason = 'observed absence; grace period' if self.active else 'absence timeout'
        else:
            self.present_since = self.absent_since = None
            self.unknown_since = t if self.unknown_since is None else self.unknown_since
            self.mode, self.reason = 'sensor_unknown', 'presence sensor unavailable; no absence inference'
            if t-self.unknown_since >= c['sensor_timeout']:
                self.active = False
                self.reason = 'sensor timeout; light off without autonomous body motion'

        blend = face.data.get('blend', {}) if face and face.data.get('present') else {}
        face_stamp = face.observed if face else t
        closed = blend.get('eyeBlink', 0)
        jaw = blend.get('jawOpen', 0)
        self.closed_since = (face_stamp if self.closed_since is None else self.closed_since) if finite(closed, c['eye_closed'], 1) else None
        self.yawn_since = (face_stamp if self.yawn_since is None else self.yawn_since) if finite(jaw, c['jaw_open'], 1) else None
        self.fatigue_cue = any(start is not None and face_stamp-start >= dwell for start, dwell in
                               ((self.closed_since, c['closed_dwell']), (self.yawn_since, c['yawn_dwell'])))
        if present is True and self.active and self.fatigue_cue:
            judgment = world.fresh('obs.judgment', t)
            interruptible = not judgment or (judgment.data['interruptible'] >= c['interruptible_threshold'] and
                                            judgment.data['fatigue_cues'] >= c['judgment_cue_threshold'])
            if interruptible:
                intents.append(('care_check', 'sustained eye closure or mouth opening; not an emotion diagnosis'))
        world.companion_mode = self.mode
        return intents

    def snapshot(self):
        return {'enabled': self.enabled, 'active': self.active, 'mode': self.mode,
                'reason': self.reason, 'desk_seconds': round(self.desk_seconds, 2),
                'seated_seconds': round(self.seated_seconds, 2), 'reminder_basis': self.reminder_basis,
                'fatigue_cue': self.fatigue_cue}
