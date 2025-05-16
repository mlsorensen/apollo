import logging
import math
import os.path
import time
import pandas as pd
from datetime import datetime
from enum import Enum
from multiprocessing import Process, Queue
from typing import Optional

from PIL import Image, ImageFont, ImageDraw

from lib.control import TargetMemory

label_font = ImageFont.truetype("lib/font/LiberationMono-Regular.ttf", 16)
label_font_mid = ImageFont.truetype("lib/font/LiberationMono-Regular.ttf", 20)
label_font_lg = ImageFont.truetype("lib/font/LiberationMono-Regular.ttf", 24)
value_font = ImageFont.truetype("lib/font/Quicksand-Regular.ttf", 24)
value_font_lg = ImageFont.truetype("lib/font/Quicksand-Regular.ttf", 36)
value_font_lg_bold = ImageFont.truetype("lib/font/Quicksand-Bold.ttf", 36)

bg_color = "BLACK"
light_bg_color = "DIMGREY"
fg_color = "WHITE"


class FlowGraph:
    def __init__(self, flow_data: list, series_color="BLUE", label_color="#c7c7c7", line_color="#5a5a5a", max_value=8,
                 width_pixels=240, height_pixels=160):
        self.flow_data = flow_data
        self.max_value = max_value
        self.series_color = series_color
        self.label_color = label_color
        self.line_color = line_color
        self.y_pix = height_pixels
        self.x_pix = width_pixels
        self.y_pix_interval = height_pixels / max_value
        if len(flow_data) > 0:
            self.x_pix_interval = width_pixels / len(flow_data)
        else:
            self.x_pix_interval = width_pixels / 1

    def generate_graph(self) -> Image:
        points = list()
        i = 0
        for y in self.flow_data:
            x_coord = i * self.x_pix_interval if i * self.x_pix_interval < self.x_pix else self.x_pix
            y_coord = y * self.y_pix_interval + 2 if y * self.y_pix_interval < self.y_pix else self.y_pix
            # flip Y value because zero is at top of image
            y_coord = abs(y_coord - self.y_pix)
            points.append((x_coord, y_coord))
            i += 1
        img = Image.new("RGBA", (self.x_pix, self.y_pix), "BLACK")
        draw = ImageDraw.Draw(img)

        # 8g line
        self.__draw_y_line(draw, 0, self.label_color)
        # 6g line
        self.__draw_y_line(draw, self.y_pix * .25 - 2, self.line_color)
        # 4g line
        self.__draw_y_line(draw, self.y_pix / 2 - 2, self.line_color)
        # 2g line
        self.__draw_y_line(draw, self.y_pix * .75 - 2, self.line_color)
        # 0g line
        self.__draw_y_line(draw, self.y_pix - 2, self.line_color)

        # data series line
        draw.line(points, fill=self.series_color, width=2)

        # 8g label
        draw.text((2, 0), "8", self.label_color, label_font)
        # 6g label
        draw.text((2, self.y_pix * .25), "6", self.label_color, label_font)
        # 4g label
        draw.text((2, self.y_pix * .5), "4", self.label_color, label_font)
        # 2g label
        draw.text((2, self.y_pix * .75), "2", self.label_color, label_font)

        last_flow_rate = self.flow_data[-1] if len(self.flow_data) > 0 else 0
        fmt_flow = "{:0.1f}".format(last_flow_rate)
        fmt_flow_label = "g/s"
        w = draw.textlength(fmt_flow, value_font)
        wl = draw.textlength(fmt_flow_label, label_font)
        draw.text(((self.x_pix - 4 - w - wl), (self.y_pix * .25) - value_font.size - 4), fmt_flow, fg_color, value_font)
        draw.text(((self.x_pix - wl), (self.y_pix * .25) - label_font.size - 4), fmt_flow_label, fg_color, label_font)
        return img

    def __draw_y_line(self, draw: ImageDraw, y, color):
        draw.line((0, y, self.x_pix, y), fill=color, width=1)


class DisplayData:
    def __init__(self, weight: float, sample_rate: float, memory: TargetMemory, flow_data: list, battery: int,
                 paddle_on: bool, shot_time_elapsed: float, save_image: bool = False,
                 flow_smooth_factor: int = 8):
        self.weight = weight
        self.sample_rate = sample_rate
        self.memory = memory
        self.flow_data = flow_data
        self.battery = battery
        self.paddle_on = paddle_on
        self.shot_time_elapsed = shot_time_elapsed
        self.save_image = save_image
        self.flow_smooth_factor = flow_smooth_factor

    def flow_rate_moving_avg(self) -> list:
        flow_data_series = pd.Series(self.flow_data)
        flow_data_windows = flow_data_series.rolling(self.flow_smooth_factor)
        return flow_data_windows.mean().dropna().to_list()


class DisplaySize(Enum):
    SIZE_2_4 = 1
    SIZE_2_0 = 2


class Display:
    def __init__(self, data_queue: Queue, display_size: DisplaySize = DisplaySize.SIZE_2_0, image_save_dir: str = None):
        from lib import LCD_2inch4, LCD_2inch
        if display_size == DisplaySize.SIZE_2_4:
            self.lcd = LCD_2inch4.LCD_2inch4()
        elif display_size == DisplaySize.SIZE_2_0:
            self.lcd = LCD_2inch.LCD_2inch()
        else:
            raise Exception("unknown display size configured: %s" % display_size.name)
        self.lcd.Init()
        self.lcd.clear()
        self.on = True
        self.data_queue: Queue[DisplayData] = data_queue
        self.flow_image = Image.new("RGBA", (0, 0), bg_color)
        self.display_off()
        self.process = None
        self.image_save_dir = image_save_dir

    def start(self):
        self.process = Process(target=self.__update_display)
        self.process.start()

    def stop(self):
        if self.process is not None:
            self.process.kill()
        self.display_off()
        self.lcd.module_exit()

    def display_off(self):
        if self.on:
            self.lcd.clear()
            self.lcd.Off()
            img = Image.new("RGBA", (self.lcd.width, self.lcd.height), bg_color)
            self.lcd.ShowImage(img, 0, 0)
            self.on = False

    def display_on(self):
        if not self.on:
            self.lcd.On()
            self.on = True

    def put_data(self, data: DisplayData):
        self.data_queue.put_nowait(data)

    def save_image(self, img: Image):
        if self.image_save_dir is None:
            logging.info("no directory set to save image")
            return

        if not os.path.exists(self.image_save_dir):
            logging.error("Skipping image save because directory %s does not exist" % self.image_save_dir)
            return

        if not os.path.isdir(self.image_save_dir):
            logging.error("Skipping image save because %s is not a directory" % self.image_save_dir)
            return

        date = datetime.now().strftime("%Y-%m-%d_%I:%M:%S_%p")
        absolute_path = "{basedir}/{date}.png".format(basedir=self.image_save_dir, date=date)
        try:
            img.save(absolute_path)
        except Exception as ex:
            logging.error("Failed to save image: %s", str(ex))

    def __update_display(self):
        while True:
            if self.data_queue.qsize() == 0:
                time.sleep(.1)
                continue

            self.display_on()
            data: Optional[DisplayData] = None
            # always roll forward to latest data
            while self.data_queue.qsize() > 0:
                data = self.data_queue.get()

            if data is None:
                continue

            if data.weight is None:
                logging.error("Skipping display redraw because weight value is missing")
                continue

            if data.battery is None:
                logging.error("Skipping display redraw because battery value is missing")
                continue

            img = None
            if self.lcd.width = 240:
                img = draw_frame(self.lcd.width, self.lcd.height, data)
            else:
                img = draw_frame_wide(self.lcd.width, self.lcd.height, data)

            if data.save_image and img is not None:
                self.save_image(img)
            self.lcd.ShowImage(img, 0, 0)


def draw_frame(width: int, height: int, data: DisplayData) -> Image:
    img = Image.new("RGBA", (width, height), bg_color)
    draw = ImageDraw.Draw(img)

    # main boxes are 120 wide x 96 high
    draw.line([(0, 96), (240, 96)], fill=fg_color, width=2)
    draw.line([(120, 0), (120, 96)], fill=fg_color, width=2)
    draw.line([(0, 285), (240, 285)], fill=fg_color, width=2)

    # weight and target labels
    draw.text((16, 16), "weight(g)", fg_color, label_font)
    draw.text((130, 16), "target %s(g)" % data.memory.name, fg_color, label_font)

    # paddle and battery
    paddle_value = "ON" if data.paddle_on else "OFF"
    draw.text((8, 294), "paddle:%s" % paddle_value, fg_color, label_font)
    draw.text((124, 294), "battery:%d%%" % data.battery, fg_color, label_font)

    # weight value
    fmt_weight = "{:0.1f}".format(data.weight)
    w = draw.textlength(fmt_weight, value_font_lg)
    h = value_font_lg.size
    draw.text(((120 - w) / 2, (108 - h) / 2), fmt_weight, fg_color, value_font_lg)

    # target value
    fmt_target = "{:0.1f}".format(data.memory.target)
    target_font = value_font_lg
    w = draw.textlength(fmt_target, target_font)
    h = target_font.size
    draw.text(((120 - w) / 2 + 120, (108 - h) / 2), fmt_target, fg_color, target_font)

    fmt_ready = "Ready"
    w = draw.textlength(fmt_ready, value_font_lg)
    h = value_font_lg.size
    h_pos = 164
    draw.rectangle((116 - w / 2, h_pos, 124 + w / 2, h_pos + h + 4), bg_color, data.memory.color, 4)
    draw.text((120 - w / 2, h_pos), fmt_ready, fg_color, value_font_lg)

    if data.flow_data is not None and len(data.flow_data) > 0:
        flow_rate_data = data.flow_rate_moving_avg()
        flow_image = FlowGraph(flow_rate_data, data.memory.color).generate_graph()
        last_sample_time = data.sample_rate * float(len(data.flow_data))

        draw.text((4, 262), "%ds" % math.ceil(last_sample_time), fg_color, label_font)
        draw.text((218, 262), "0s", fg_color, label_font)

        fmt_shot_time = "timer:{:0.1f}s".format(data.shot_time_elapsed)
        w = draw.textlength(fmt_shot_time, label_font)
        draw.text(((240 - w) / 2, 262), fmt_shot_time, fg_color, label_font)

        img.paste(flow_image, (0, 98))

    return img

def draw_frame_wide(width: int, height: int, data: DisplayData) -> Image:
    background = bg_color
    if data.paddle_on:
        background = light_bg_color
    img = Image.new("RGBA", (width, height), background)

    draw = ImageDraw.Draw(img)

    # main boxes are 106 wide x 72 high
    draw.line([(0, 72), (320, 72)], fill=fg_color, width=2)
    draw.line([(106, 0), (106, 72)], fill=fg_color, width=2)
    draw.line([(212, 0), (212, 72)], fill=fg_color, width=2)
    draw.line([(0, 285), (240, 285)], fill=fg_color, width=2)

    # weight and target labels
    draw.text((10, 8), "weight(g)", fg_color, label_font)
    draw.text((118, 8), "tgt %s (g)" % data.memory.name, fg_color, label_font)
    draw.text((234, 8), "battery", fg_color, label_font)

    # weight value
    fmt_weight = "{:0.1f}".format(data.weight)
    w = draw.textlength(fmt_weight, value_font_lg)
    h = value_font_lg.size
    draw.text(((106 - w) / 2, (88 - h) / 2), fmt_weight, fg_color, value_font_lg)

    # target value
    fmt_target = "{:0.1f}".format(data.memory.target)
    target_font = value_font_lg
    w = draw.textlength(fmt_target, target_font)
    h = target_font.size
    draw.text(((106 - w) / 2 + 106, (88 - h) / 2), fmt_target, fg_color, target_font)

    # battery value
    fmt_batt = "%d%%" % data.battery
    w = draw.textlength(fmt_batt, value_font_lg)
    draw.text(((106 - w)/2 + 214, (88 - h) / 2), fmt_batt, fg_color, value_font_lg)

    fmt_ready = "Ready"
    w = draw.textlength(fmt_ready, value_font_lg)
    h = value_font_lg.size
    h_pos = 120
    draw.rectangle((156 - w / 2, h_pos, 164 + w / 2, h_pos + h + 4), bg_color, data.memory.color, 4)
    draw.text((160 - w / 2, h_pos), fmt_ready, fg_color, value_font_lg)

    if data.flow_data is not None and len(data.flow_data) > 0:
        flow_rate_data = data.flow_rate_moving_avg()
        flow_image = FlowGraph(flow_rate_data, data.memory.color, width_pixels=320, height_pixels=132).generate_graph()
        last_sample_time = data.sample_rate * float(len(data.flow_data))

        draw.text((4, 212), "%ds" % math.ceil(last_sample_time), fg_color, label_font)
        draw.text((298, 212), "0s", fg_color, label_font)

        fmt_shot_time = "timer:{:0.1f}s".format(data.shot_time_elapsed)
        w = draw.textlength(fmt_shot_time, label_font_lg)
        draw.text(((320 - w) / 2, 208), fmt_shot_time, fg_color, label_font_lg)

        img.paste(flow_image, (0, 72))

    return img
