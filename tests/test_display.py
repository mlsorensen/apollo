# test_display.py
import random

from lib import display
from lib.control import TargetMemory
from lib.display import DisplayData


# test_generate_frame should pop up a sample display frame for developing/designing the layout
def test_generate_frame():
    flow_data = []
    for i in range(0, 20):
        flow_data.append(0)
    for i in range(0, 100):
        flow_data.append(random.uniform(1.0, 3.0))
    for i in range(0, 100):
        flow_data.append(random.uniform(3.0, 5.0))
    for i in range(0, 10):
        flow_data.append(0)
    flow_data.append(1.2)
    memory = TargetMemory("F", "orange")
    memory.target = 45
    data = DisplayData(234.1, 0.1, memory, flow_data, 59, True, 22.1, False)
    img = display.draw_frame(240, 320, data)
    img.show()

# test_generate_frame should pop up a sample display frame for developing/designing the layout
def test_generate_frame_wide():
    flow_data = []
    for i in range(0, 20):
        flow_data.append(0)
    for i in range(0, 100):
        flow_data.append(random.uniform(1.0, 3.0))
    for i in range(0, 100):
        flow_data.append(random.uniform(3.0, 5.0))
    for i in range(0, 10):
        flow_data.append(0)
    flow_data.append(1.2)
    memory = TargetMemory("F", "orange")
    memory.target = 45
    data = DisplayData(234.1, 0.1, memory, flow_data, 59, True, 22.1, False)
    img = display.draw_frame_wide(320, 240, data)
    img.show()
