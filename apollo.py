#!/usr/bin/env python3
import logging
import os
import signal
import sys
import time

from concurrent.futures import ThreadPoolExecutor
from logging import handlers
from multiprocessing import Queue
from timeit import default_timer as timer
from typing import Optional

from lib import control
from lib.control import ControlManager
from lib.display import Display, DisplayData, DisplaySize
from lib.pyacaia import AcaiaScale
from lib.webserver import WebServer

WEB_PORT = 80
WEB_DIR = '/opt/apollo/web'
MIN_GOOD_SHOT_DURATION = 10

stop = False
overshoot_update_executor = ThreadPoolExecutor(max_workers=1)

logLevel = os.environ.get('LOGLEVEL', 'INFO').upper()
logPath = os.environ.get('LOGFILE', '/var/log/apollo.log')

refreshRate = float(os.environ.get('REFRESH_RATE', '0.1'))
smoothing = round(1 / refreshRate)

stdout_handler = logging.StreamHandler(stream=sys.stdout)
stdout_handler.setLevel(logging.INFO)
file_handler = handlers.TimedRotatingFileHandler(filename=logPath, when='midnight', backupCount=4)
file_handler.setLevel(logLevel)
handlers = [stdout_handler, file_handler]
logging.basicConfig(
    level=logLevel,
    format='[%(asctime)s] {%(filename)s:%(lineno)d} %(levelname)s - %(message)s',
    handlers=handlers
)


def update_overshoot(scale: AcaiaScale, mgr: ControlManager):
    if mgr.shot_time_elapsed() < MIN_GOOD_SHOT_DURATION:
        logging.info("Declining to consider short shot as a good shot. Not updating overshoot value or saving image")
        return
    time.sleep(3)
    logging.debug("over scale weight is %.2f, target was %.2f" % (scale.weight, mgr.current_memory().target))
    mgr.current_memory().update_overshoot(scale.weight)
    mgr.image_needs_save = True
    logging.info("new overshoot on memory %s is %.2f" %(mgr.current_memory().name, mgr.current_memory().overshoot))


def check_target_disable_relay(scale: AcaiaScale, mgr: ControlManager):
    if mgr.relay_on() and scale.weight > mgr.current_memory().target_minus_overshoot():
        mgr.disable_relay()
        overshoot_update_executor.submit(update_overshoot, scale, mgr)
        logging.debug("Scheduling overshoot check and update")


def main():
    web_server = WebServer(WEB_DIR, WEB_PORT)
    web_server.start()
    logging.info("Started web server")

    display_data_queue: Queue[DisplayData] = Queue()
    display = Display(display_data_queue, display_size=DisplaySize.SIZE_2_0, image_save_dir=WEB_DIR)
    display.start()

    # we need enough data points to capture 60s shot
    mgr = ControlManager(max_flow_points=round(60 / refreshRate))
    scale = AcaiaScale(mac='')

    mgr.add_tare_handler(lambda channel: scale.tare())

    last_sample_time: Optional[float] = None
    last_weight: Optional[float] = None
    while not stop:
        if control.try_connect_scale(scale, mgr):
            check_target_disable_relay(scale, mgr)
        if scale is not None and scale.connected:
            (last_sample_time, last_weight) = update_display(scale, mgr, display, last_sample_time, last_weight)
        else:
            display.display_off()
        time.sleep(refreshRate)
    if scale.connected:
        try:
            scale.disconnect()
        except Exception as ex:
            logging.error("Error during shutdown: %s" % str(ex))
    if display is not None:
        display.stop()
    logging.info("Exiting on stop")


def update_display(scale: AcaiaScale, mgr: ControlManager, display: Display, last_time: float, last_weight: float) -> (float, float):
    now = timer()
    weight = scale.weight
    sample_rate = 0.0
    if last_time is not None and last_weight is not None:
        sample_rate = now - last_time
        changed = weight - last_weight
        g_per_s = round(1 / sample_rate * changed, 1)
        mgr.add_flow_rate_data(g_per_s)
    data = DisplayData(weight, sample_rate, mgr.current_memory(), mgr.flow_rate_data,
                       scale.battery, mgr.relay_on(), mgr.shot_time_elapsed(),
                       mgr.image_needs_save, smoothing)
    display.display_on()
    display.put_data(data)
    mgr.image_needs_save = False
    return now, weight


def shutdown(sig, frame):
    global stop
    stop = True


if __name__ == '__main__':
    signal.signal(signal.SIGINT, shutdown)
    main()
