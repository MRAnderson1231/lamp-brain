"""Driver-side hand/lux adapter. No model or physical driver is claimed by this interface.

An actual calibrated driver calls publish(); Runtime polls the bounded inbox. The control
world validates freshness, quality and units again. Remote Margin clients cannot inject
these sensor events. Relative image brightness is explicitly a different measurement.
"""
from __future__ import annotations

from queue import Empty, Queue

from ..types import Event, OBS_AMBIENT, OBS_HAND


class PeripheralSensor:
    def __init__(self,cfg,clock,source='peripheral'):
        self.clock,self.source=clock,source
        self.inbox=Queue(maxsize=cfg['control']['fusion']['sensor_queue_limit'])

    def publish(self,kind,data):
        if kind not in (OBS_HAND,OBS_AMBIENT,'obs.occupancy','obs.work_target'):
            raise ValueError('unsupported peripheral observation')
        self.inbox.put_nowait(Event(self.clock.now(),kind,dict(data),self.source))

    def poll(self,t):
        result=[]
        while True:
            try:
                result.append(self.inbox.get_nowait())
            except Empty:
                return result
