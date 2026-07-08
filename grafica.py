import serial
import matplotlib.pyplot as plt
from matplotlib.widgets import TextBox
import numpy as np

PORT = '/dev/tty.usbmodem1101'
BAUDRATE = 115200

# Limits
EXPOSURE_MIN = 1
EXPOSURE_MAX = 2000
GAIN_MIN = 0.1
GAIN_MAX = 10.0

ser = serial.Serial(PORT, BAUDRATE, timeout=1)

current_exposure = 50
current_gain = 1.0  # 1.0 = no amplification

fig, ax = plt.subplots(figsize=(10, 5))
plt.subplots_adjust(bottom=0.25)

x = np.arange(1, 129)
line, = ax.plot(x, np.zeros(128))

ax.set_xlim(1, 128)
ax.set_ylim(0, 1023)
ax.set_xlabel("Pixel (# 1-128)")
ax.set_ylabel("Intensity (Counts, 0-1023)")
ax.grid(True)
ax.set_title(f"TSL1401 - Exposure: {current_exposure} ms | Gain: {current_gain}x")

axbox_exp = plt.axes([0.2, 0.1, 0.15, 0.05])
text_box_exp = TextBox(axbox_exp, f'Exposure ({EXPOSURE_MIN}-{EXPOSURE_MAX} ms): ', initial=str(current_exposure))

axbox_gain = plt.axes([0.6, 0.1, 0.15, 0.05])
text_box_gain = TextBox(axbox_gain, f'Gain ({GAIN_MIN}-{GAIN_MAX}x): ', initial=str(current_gain))


def update_title():
    ax.set_title(f"TSL1401 - Exposure: {current_exposure} ms | Gain: {current_gain}x")


def update_exposure(text):
    global current_exposure
    if not text.strip().lstrip('-').isdigit():
        return
    new_value = int(text.strip())
    new_value = max(EXPOSURE_MIN, min(EXPOSURE_MAX, new_value))  # clamp to range
    ser.write(f"{new_value}\n".encode())
    current_exposure = new_value
    update_title()


def update_gain(text):
    global current_gain
    try:
        new_value = float(text.strip())
    except ValueError:
        return
    new_value = max(GAIN_MIN, min(GAIN_MAX, new_value))  # clamp to range
    current_gain = new_value
    update_title()


text_box_exp.on_submit(update_exposure)
text_box_gain.on_submit(update_gain)

plt.ion()
plt.show()

try:
    while True:
        serial_line = ser.readline().decode('utf-8', errors='ignore').strip()
        if not serial_line:
            plt.pause(0.01)
            continue

        try:
            values = [int(v) for v in serial_line.split(',')]
        except ValueError:
            continue

        if len(values) != 128:
            continue

        values_with_gain = [min(1023, int(v * current_gain)) for v in values]

        line.set_ydata(values_with_gain)
        fig.canvas.draw_idle()
        plt.pause(0.001)

except KeyboardInterrupt:
    print("Stopped by user")
finally:
    ser.close()