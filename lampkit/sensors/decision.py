"""Optional low-rate typed judgments, outside the motor loop.

The provider consumes numeric/text evidence only. Camera images are never uploaded by
this adapter. Default is disabled; no cloud call is needed to run the companion.
"""
from __future__ import annotations

import json
import math
import os
from concurrent.futures import ThreadPoolExecutor
from urllib.request import Request, urlopen

from ..types import Event


class JevProvider:
    def __init__(self, cfg):
        self.c = cfg['decision']
        self.key = os.environ.get(self.c['key_env'])
        if not self.key:
            raise ValueError('Jev configured but TYPESAFE_API_KEY is missing')

    def __call__(self, evidence):
        c = self.c
        body = {'model': c['model'], 'state': evidence,
                'questions': {k: {'type': 'noul', 'instructions': question}
                              for k, question in c['questions'].items()}}
        req = Request('https://api.typesafe.ai/v1/systemone',
                      json.dumps(body, allow_nan=False).encode(),
                      {'Content-Type': 'application/json', 'Authorization': 'Bearer '+self.key})
        with urlopen(req, timeout=c['timeout_seconds']) as response:
            raw = response.read(c['max_response_bytes']+1)
        if len(raw) > c['max_response_bytes']:
            raise ValueError('oversized decision response')
        result = json.loads(raw)
        answers = result['answers']
        return {'model': result['model'], **{k: answers[k]['noul'] for k in c['questions']}}


class DecisionSensor:
    def __init__(self, cfg, provider):
        self.c, self.provider = cfg['decision'], provider
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix='lamp-decision')
        self.future = None
        self.next_request = -float('inf')
        self.observed = None
        self.sequence = 0
        self.closed = False

    def submit_world(self, t, evidence):
        if self.closed or self.future is not None or t < self.next_request:
            return
        # Copy a bounded numerical snapshot; keep original observation time so a slow
        # response cannot become fresh evidence simply because it just arrived.
        self.observed = evidence['observed_at']
        self.sequence += 1
        self.future = self.pool.submit(self.provider, json.loads(json.dumps(evidence)))
        self.next_request = t+self.c['interval_seconds']

    def poll(self, t):
        if self.future is None or not self.future.done():
            return []
        future, self.future = self.future, None
        try:
            result = future.result()
            for key in ('fatigue_cues', 'interruptible'):
                value = result[key]
                if type(value) not in (float, int) or not math.isfinite(value) or not 0 <= value <= 1:
                    raise ValueError('invalid decision probability')
            if not isinstance(result.get('model'), str):
                raise ValueError('missing model provenance')
            data = {key: result[key] for key in ('fatigue_cues', 'interruptible', 'model')}
            data.update(observed_at=self.observed, evidence_id=str(self.sequence), sample_id=str(self.sequence))
            return [Event(t, 'obs.judgment', data, 'decision')]
        except Exception as exc:
            # Never log credentials, payloads or a provider's HTTP error body.
            return [Event(t, 'sensor.error', {'sensor':'decision','error_type':type(exc).__name__}, 'decision')]

    def close(self):
        self.closed = True
        self.pool.shutdown(wait=False, cancel_futures=True)
