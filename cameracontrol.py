import serial
import serial.tools.list_ports
import matplotlib.pyplot as plt
from matplotlib.widgets import TextBox
import numpy as np
import tkinter as tk
from tkinter import ttk, filedialog
import csv
from datetime import datetime

BAUDRATE = 115200

# Limits
EXPOSURE_MIN = 1
EXPOSURE_MAX = 2000
GAIN_MIN = 0.1
GAIN_MAX = 10.0


def select_port():
    """Show a small window listing available serial ports and let the user pick one."""
    ports = list(serial.tools.list_ports.comports())
    port_names = [p.device for p in ports]

    selected_port = {"value": None}

    root = tk.Tk()
    root.title("Select Serial Port")
    root.geometry("350x150")

    tk.Label(root, text="Select the Arduino serial port:", font=("Arial", 11)).pack(pady=10)

    combo = ttk.Combobox(root, values=port_names, state="readonly", width=35)
    if port_names:
        combo.current(0)
    combo.pack(pady=5)

    def refresh_ports():
        new_ports = [p.device for p in serial.tools.list_ports.comports()]
        combo["values"] = new_ports
        if new_ports:
            combo.current(0)

    def confirm():
        if combo.get():
            selected_port["value"] = combo.get()
            root.destroy()

    btn_frame = tk.Frame(root)
    btn_frame.pack(pady=10)
    tk.Button(btn_frame, text="Refresh", command=refresh_ports).pack(side="left", padx=5)
    tk.Button(btn_frame, text="Connect", command=confirm).pack(side="left", padx=5)

    if not port_names:
        tk.Label(root, text="No ports found. Plug in the Arduino and click Refresh.", fg="red").pack()

    root.mainloop()
    return selected_port["value"]


PORT = select_port()

if not PORT:
    print("No port selected. Exiting.")
    exit()

ser = serial.Serial(PORT, BAUDRATE, timeout=1)

current_exposure = 50
current_gain = 1.0  # 1.0 = no amplification

# Holds the most recent frame of 128 values seen from the live feed
latest_frame = {"values": None}

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

running = {"value": True}


def close_program(event=None):
    running["value"] = False


axbox_exit = plt.axes([0.85, 0.02, 0.1, 0.05])
btn_exit = plt.Button(axbox_exit, 'Exit')
btn_exit.on_clicked(close_program)

fig.canvas.mpl_connect('close_event', close_program)


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


def save_snapshot(values, exposure, gain):
    """Ask where to save and write the CSV/TXT with exposure/gain as header info."""
    filepath = filedialog.asksaveasfilename(
        title="Save capture",
        defaultextension=".csv",
        filetypes=[("CSV file", "*.csv"), ("Text file", "*.txt")],
        initialfile=f"capture_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )

    if not filepath:
        print("Save cancelled.")
        return

    delimiter = "," if filepath.lower().endswith(".csv") else "\t"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with open(filepath, "w", newline="") as f:
        # Header info: exposure, gain, timestamp
        f.write(f"# Exposure_ms: {exposure}\n")
        f.write(f"# Gain: {gain}\n")
        f.write(f"# Timestamp: {timestamp}\n")

        writer = csv.writer(f, delimiter=delimiter)
        writer.writerow(["Pixel", "Value"])
        for pixel_idx, value in enumerate(values, start=1):
            writer.writerow([pixel_idx, value])

    print(f"Capture saved to: {filepath}")


def show_save_prompt(values, exposure, gain):
    """Small dialog asking whether to save the snapshot just taken."""
    prompt = tk.Tk()
    prompt.title("Capture taken")
    prompt.geometry("300x120")
    prompt.attributes("-topmost", True)

    tk.Label(prompt, text="Snapshot captured.\nDo you want to save it?", font=("Arial", 11)).pack(pady=15)

    def on_save():
        prompt.destroy()
        save_snapshot(values, exposure, gain)

    def on_discard():
        prompt.destroy()
        print("Capture discarded.")

    btn_frame = tk.Frame(prompt)
    btn_frame.pack(pady=5)
    tk.Button(btn_frame, text="Save", width=10, command=on_save).pack(side="left", padx=10)
    tk.Button(btn_frame, text="Discard", width=10, command=on_discard).pack(side="left", padx=10)

    prompt.mainloop()


def capture_snapshot(event=None):
    if latest_frame["values"] is None:
        print("No data yet, wait for the first reading from the Arduino.")
        return
    # Freeze the current values/params at the moment of capture
    show_save_prompt(list(latest_frame["values"]), current_exposure, current_gain)


axbox_capture = plt.axes([0.4, 0.02, 0.2, 0.06])
btn_capture = plt.Button(axbox_capture, 'Capture')
btn_capture.on_clicked(capture_snapshot)


plt.ion()
plt.show()

try:
    while running["value"]:
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
        latest_frame["values"] = values_with_gain

        line.set_ydata(values_with_gain)
        fig.canvas.draw_idle()
        plt.pause(0.001)

except KeyboardInterrupt:
    print("Stopped by user")
finally:
    ser.close()
    plt.close('all')