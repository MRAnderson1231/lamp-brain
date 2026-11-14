"""Wall-clock context enters as recorded input, never as hidden core state."""
from datetime import datetime

from ..types import Event


class LocalContextSensor:
    def __init__(self, cfg):
        self.interval = cfg['local_context']['interval_seconds']
        self.next_emit = -float('inf')

    def poll(self, t):
        if t < self.next_emit:
            return []
        now = datetime.now().astimezone()
        self.next_emit = t+self.interval
        return [Event(t, 'obs.clock', {'local_hour': now.hour+now.minute/60,
                                     'timezone': str(now.tzinfo)}, 'local-clock')]
