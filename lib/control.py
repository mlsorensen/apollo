import logging
import time
from collections import deque
from timeit import default_timer as timer
from typing import Optional, Callable

from gpiozero import Button, DigitalOutputDevice

import lib.pyacaia as pyacaia
from lib.pyacaia import AcaiaScale

default_target = 50.0
default_overshoot = 2.0


class TargetMemory:
    def __init__(self, name: str, color="#ff1303"):
        self.name: str = name
        self.target: float = default_target
        self.overshoot: float = default_overshoot
        self.color: str = color

    def target_minus_overshoot(self) -> float:
        return self.target - self.overshoot

    def update_overshoot(self, weight: float):
        new_overshoot = self.overshoot + (weight - self.target)
        if new_overshoot > 10 or new_overshoot < -10:
            logging.error("New overshoot out of safe range, ignoring")
        else:
            self.overshoot = new_overshoot
            logging.debug("set new overshoot to %.2f" % self.overshoot)


class ControlManager:
    TARE_GPIO = 4
    MEM_GPIO = 21
    SCALE_CONNECT_GPIO = 5
    TGT_INC_GPIO = 12
    TGT_DEC_GPIO = 16
    PADDLE_GPIO = 20
    RELAY_GPIO = 26

    def __init__(self, max_flow_points=500):
        self.flow_rate_data = deque([])
        self.flow_rate_max_points = max_flow_points
        self.memories = deque([TargetMemory("A"), TargetMemory("B", "#25a602"), TargetMemory("C", "#376efa")])
        self.relay_off_time = timer()
        self.shot_timer_start: Optional[float] = None
        self.image_needs_save = False

        self.relay = DigitalOutputDevice(ControlManager.RELAY_GPIO)

        self.tgt_inc_button = Button(ControlManager.TGT_INC_GPIO, hold_time=0.5, hold_repeat=True, pull_up=True)
        self.tgt_inc_button.when_pressed = self.__increment_target
        self.tgt_inc_button.when_held = lambda: self.__increment_target(amount=1)

        self.tgt_dec_button = Button(ControlManager.TGT_DEC_GPIO, hold_time=0.5, hold_repeat=True, pull_up=True)
        self.tgt_dec_button.when_pressed = self.__decrement_target
        self.tgt_dec_button.when_held = lambda: self.__decrement_target(amount=1)

        self.paddle_switch = Button(ControlManager.PADDLE_GPIO, pull_up=True, bounce_time=0.1)
        self.paddle_switch.when_pressed = self.__start_shot
        self.paddle_switch.when_released = self.disable_relay

        self.tare_button = Button(ControlManager.TARE_GPIO, pull_up=True)

        self.memory_button = Button(ControlManager.MEM_GPIO, pull_up=True)
        self.memory_button.when_pressed = self.__rotate_memory

        self.scale_connect_button = Button(ControlManager.SCALE_CONNECT_GPIO, pull_up=True)

    def add_tare_handler(self, callback: Callable):
        self.tare_button.when_pressed = callback

    def should_scale_connect(self) -> bool:
        return self.scale_connect_button.value

    def relay_on(self) -> bool:
        return self.relay.value

    def add_flow_rate_data(self, data_point: float):
        if self.relay_on() or self.relay_off_time + 3.0 > timer():
            self.flow_rate_data.append(data_point)
            if len(self.flow_rate_data) > self.flow_rate_max_points:
                self.flow_rate_data.popleft()

    def disable_relay(self):
        logging.info("disable relay")
        if self.relay_on():
            self.relay_off_time = timer()
            self.relay.off()

    def current_memory(self):
        return self.memories[0]

    def shot_time_elapsed(self):
        if self.shot_timer_start is None:
            return 0.0
        elif self.relay_on():
            return timer() - self.shot_timer_start
        else:
            return self.relay_off_time - self.shot_timer_start

    def __increment_target(self, amount=0.1):
        self.memories[0].target += amount

    def __decrement_target(self, amount=0.1):
        self.memories[0].target -= amount

    def __rotate_memory(self):
        self.memories.rotate(-1)

    def __start_shot(self):
        logging.info("Start shot")
        self.flow_rate_data = deque([])
        if self.tare_button.when_pressed is not None:
            self.tare_button.when_pressed()
            logging.info("Sent tare to scale")
            time.sleep(.5)
        self.shot_timer_start = timer()
        self.relay.on()


def try_connect_scale(scale: AcaiaScale, mgr: ControlManager) -> bool:
    try:
        if not scale.connected and mgr.should_scale_connect():
            scale.device = None
            devices = pyacaia.find_acaia_devices(timeout=1)
            if devices:
                scale.mac = devices[0]
                logging.debug("calling connect on mac %s" % scale.mac)
                scale.connect()
                # if scale.weight is None:
                #     logging.error("Connected but no weight, need to reconnect")
                #     scale.disconnect()
                #     time.sleep(1)
                #     return False
                return True
            else:
                logging.debug("no devices found")
                return False
        elif scale.connected and not mgr.should_scale_connect():
            logging.debug("scale connected but should not be")
            scale.disconnect()
            return False
        if scale.connected:
            logging.debug("Connected to scale %s" % scale.mac)
            return True
    except Exception as ex:
        logging.error("Failed to connect to found device:%s" % str(ex))
        return False

