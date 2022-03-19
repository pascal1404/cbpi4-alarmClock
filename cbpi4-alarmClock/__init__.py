# -*- coding: utf-8 -*-
import os
import asyncio
from aiohttp import web
from cbpi.api import parameters, Property, action
from cbpi.api.step import StepResult, CBPiStep
from cbpi.api.timer import Timer
from datetime import datetime
import time
from voluptuous.schema_builder import message
from cbpi.api.dataclasses import NotificationAction, NotificationType
from cbpi.api.dataclasses import Kettle, Props
from cbpi.api import *
import logging

logger = logging.getLogger(__name__)

@parameters([Property.Text(label="Datetime",configurable = True, description = "datestring that represent time to MashIn. Format(dd.mm.yy-HH:MM)"),
             Property.Number(label="Water", description="The volume of the water to be heated to MashIn-temp in l", configurable=True),
             Property.Number(label="Power", description="The power of your heatingelement in W", configurable=True),
             Property.Number(label="Efficient", description="The efficient of your configuration in % (experience start with 80% for induction)", configurable=True),
             Property.Number(label="Temp", description="MashIn temperature", configurable=True),
             Property.Sensor(label="Sensor"),
             Property.Kettle(label="Kettle"),])
class AlarmClockStep(CBPiStep):

    async def on_timer_done(self, timer):
        self.summary = ""
        if self.AutoMode == True:
            await self.setAutoMode(False)
        if self.heating:
            self.cbpi.notify(self.name, 'AlarmClock Time reached. Starting next step', NotificationType.SUCCESS)
        await self.next()

    async def on_timer_update(self, timer, seconds):
        self.summary = Timer.format_time(seconds)
        self.remaining_seconds = seconds
        await self.push_update()

    async def on_start(self):
        self.AutoMode = True
        self.heating = False
        self.remaining_seconds = None
        self.kettle=self.get_kettle(self.props.get("Kettle", None))
        if self.kettle is not None:
            self.kettle.target_temp = 0
        target_datetime = datetime.strptime(self.props.get("Datetime", datetime.now()), '%d.%m.%y-%H:%M')
        now = datetime.now()
        seconds = (target_datetime - now).total_seconds()
        self.timer = Timer(int(seconds), on_update=self.on_timer_update, on_done=self.on_timer_done)
        self.timer.start()

    async def on_stop(self):
        self.heating = False
        await self.timer.stop()
        self.summary = ""
        if self.AutoMode == True:
            await self.setAutoMode(False)
        await self.push_update()

    async def reset(self):
        self.heating = False
        target_datetime = datetime.strptime(self.props.get("Datetime", datetime.now()), '%d.%m.%y-%H:%M')
        now = datetime.now()
        seconds = (target_datetime - now).total_seconds()
        self.timer = Timer(int(seconds), on_update=self.on_timer_update, on_done=self.on_timer_done)

    async def run(self):
        while self.running == True:
            await asyncio.sleep(1)
            sensor_value = self.get_sensor_value(self.props.get("Sensor", None)).get("value")
            heating_time = (int(self.props.get("Water",0)) * ( int(self.props.get("Temp",0)) - sensor_value) * 4186 / int(self.props.get("Power",0))) / (int(self.props.get("Efficient",0)) / 100)
            
            if self.remaining_seconds != None and self.remaining_seconds < heating_time and not self.heating:
                self.heating = True
                if self.kettle is not None:
                    self.kettle.target_temp = int(self.props.get("Temp", 0))
                    await self.setAutoMode(True)
                await self.push_update()
                estimated_completion_time = datetime.fromtimestamp(time.time() + self.remaining_seconds)
                self.cbpi.notify(self.name, 'Heating started. Estimated completion: {}'.format(estimated_completion_time.strftime("%H:%M")), NotificationType.INFO)
        return StepResult.DONE

    async def setAutoMode(self, auto_state):
        try:
            if (self.kettle.instance is None or self.kettle.instance.state == False) and (auto_state is True):
                await self.cbpi.kettle.toggle(self.kettle.id)
            elif (self.kettle.instance.state == True) and (auto_state is False):
                await self.cbpi.kettle.stop(self.kettle.id)
            await self.push_update()

        except Exception as e:
            logging.error("Failed to switch on KettleLogic {} {}".format(self.kettle.id, e))


def setup(cbpi):
    cbpi.plugin.register("AlarmClockStep", AlarmClockStep)
    pass
