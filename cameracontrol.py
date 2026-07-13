import serial
import serial.tools.list_ports
import matplotlib.pyplot as plt
from matplotlib.widgets import TextBox
import numpy as np
import tkinter as tk
from tkinter import ttk, filedialog
import csv
import time
from datetime import datetime

BAUDRATE = 115200

# Limits
EXPOSURE_MIN = 1
EXPOSURE_MAX = 2000
GAIN_MIN = 0.1
GAIN_MAX = 10.0

INTEGRATION_TIME_MIN = 0.5
INTEGRATION_TIME_MAX = 300.0


# Single persistent Tk root, reused for the port dialog and every save prompt.
# Creating a fresh tk.Tk() each time (and calling mainloop() on it) is what caused
# the app to freeze after saving a capture, since it left the Tcl interpreter in a
# bad state. Now we only ever create ONE root, and use Toplevel + wait_window for
# each subsequent dialog.
root = tk.Tk()
root.withdraw()  # the root window itself is never shown directly


def select_port():
    """Show a small window listing available serial ports and let the user pick one."""
    ports = list(serial.tools.list_ports.comports())
    port_names = [p.device for p in ports]

    selected_port = {"value": None}

    root.deiconify()
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
            root.withdraw()
            for widget in root.winfo_children():
                widget.destroy()
            root.quit()

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
current_integration_time = 1.0  # seconds, used by Integration Capture

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


def update_integration_time(text):
    global current_integration_time
    try:
        new_value = float(text.strip())
    except ValueError:
        return
    new_value = max(INTEGRATION_TIME_MIN, min(INTEGRATION_TIME_MAX, new_value))  # clamp to range
    current_integration_time = new_value


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


def save_integration_csv(columns, data, exposure, gain, total_time, tick_seconds):
    """Save a CSV with Pixel (1-128) as rows and one column per elapsed time tick
    (one tick = the exposure value in ms, used as the reading interval) captured
    during the integration window."""
    filepath = filedialog.asksaveasfilename(
        title="Save integration capture",
        defaultextension=".csv",
        filetypes=[("CSV file", "*.csv"), ("Text file", "*.txt")],
        initialfile=f"integration_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    )

    if not filepath:
        print("Save cancelled.")
        return

    delimiter = "," if filepath.lower().endswith(".csv") else "\t"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with open(filepath, "w", newline="") as f:
        f.write(f"# Exposure_ms: {exposure}\n")
        f.write(f"# Gain: {gain}\n")
        f.write(f"# Integration_time_s: {total_time}\n")
        f.write(f"# Tick_ms: {int(round(tick_seconds * 1000))}\n")
        f.write(f"# Timestamp: {timestamp}\n")

        writer = csv.writer(f, delimiter=delimiter)
        writer.writerow(["Pixel"] + columns)
        for pixel_idx in range(128):
            row = [pixel_idx + 1] + [data[col_idx][pixel_idx] for col_idx in range(len(columns))]
            writer.writerow(row)

    print(f"Integration capture saved to: {filepath}")


def show_save_prompt(values, exposure, gain):
    """Small dialog asking whether to save the snapshot just taken.

    Uses a Toplevel on the single persistent `root` (created once at startup)
    instead of a brand new tk.Tk(). wait_window() blocks only until THIS window
    closes, without starting a second competing mainloop, so matplotlib's loop
    resumes normally afterward.
    """
    prompt = tk.Toplevel(root)
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

    prompt.protocol("WM_DELETE_WINDOW", on_discard)
    root.wait_window(prompt)


def capture_snapshot(event=None):
    if latest_frame["values"] is None:
        print("No data yet, wait for the first reading from the Arduino.")
        return
    # Freeze the current values/params at the moment of capture
    show_save_prompt(list(latest_frame["values"]), current_exposure, current_gain)


axbox_capture = plt.axes([0.08, 0.02, 0.15, 0.06])
btn_capture = plt.Button(axbox_capture, 'Capture')
btn_capture.on_clicked(capture_snapshot)


# --- Integration Capture: take one reading every fixed 500 ms tick until the
# total integration time is reached, then offer to save all of them as columns
# in a single CSV (Pixel 1-128 as rows). Non-blocking: state is advanced from
# inside the main serial-read loop below using time.time() checks. ---
integration_state = {
    "active": False,
    "start_time": None,
    "tick": 0.1,  # seconds, set from current_exposure when the capture starts
    "next_tick": 0.1,
    "columns": [],
    "data": [],
    "total_time": current_integration_time,
}


def show_integration_save_prompt(columns, data, exposure, gain, total_time, tick_seconds):
    """Same Toplevel + wait_window pattern as show_save_prompt, for integration data."""
    prompt = tk.Toplevel(root)
    prompt.title("Integration capture complete")
    prompt.geometry("320x120")
    prompt.attributes("-topmost", True)

    tk.Label(
        prompt,
        text=f"Integration capture complete ({total_time}s, {len(columns)} readings).\nDo you want to save it?",
        font=("Arial", 11),
        justify="center",
    ).pack(pady=15)

    def on_save():
        prompt.destroy()
        save_integration_csv(columns, data, exposure, gain, total_time, tick_seconds)

    def on_discard():
        prompt.destroy()
        print("Integration capture discarded.")

    btn_frame = tk.Frame(prompt)
    btn_frame.pack(pady=5)
    tk.Button(btn_frame, text="Save", width=10, command=on_save).pack(side="left", padx=10)
    tk.Button(btn_frame, text="Discard", width=10, command=on_discard).pack(side="left", padx=10)

    prompt.protocol("WM_DELETE_WINDOW", on_discard)
    root.wait_window(prompt)


def start_integration_capture(event=None):
    if integration_state["active"]:
        print("Integration capture already running.")
        return
    tick = current_exposure / 1000.0  # exposure is in ms; tick is in seconds
    integration_state["active"] = True
    integration_state["start_time"] = time.time()
    integration_state["tick"] = tick
    integration_state["next_tick"] = tick
    integration_state["columns"] = []
    integration_state["data"] = []
    integration_state["total_time"] = current_integration_time
    print(f"Integration capture started: {current_integration_time}s, "
          f"reading every {int(round(tick * 1000))}ms (= current exposure)...")


axbox_integration_capture = plt.axes([0.32, 0.02, 0.18, 0.06])
btn_integration_capture = plt.Button(axbox_integration_capture, 'Integration Capture')
btn_integration_capture.on_clicked(start_integration_capture)

axbox_integration = plt.axes([0.52, 0.025, 0.13, 0.05])
text_box_integration = TextBox(axbox_integration, '', initial=str(current_integration_time))
text_box_integration.on_submit(update_integration_time)

fig.text(0.655, 0.05, 'seconds', fontsize=9, va='center')


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

        if integration_state["active"]:
            elapsed = time.time() - integration_state["start_time"]

            while elapsed >= integration_state["next_tick"] and integration_state["active"]:
                integration_state["data"].append(list(values_with_gain))
                tick_ms = int(round(integration_state["next_tick"] * 1000))
                integration_state["columns"].append(f"{tick_ms}ms")
                integration_state["next_tick"] += integration_state["tick"]

            if elapsed >= integration_state["total_time"]:
                integration_state["active"] = False
                if integration_state["columns"]:
                    show_integration_save_prompt(
                        integration_state["columns"],
                        integration_state["data"],
                        current_exposure,
                        current_gain,
                        integration_state["total_time"],
                        integration_state["tick"],
                    )
                else:
                    print("Integration capture finished with no readings (total time shorter than tick).")

        plt.pause(0.001)
        root.update()  # keep the (hidden) Tk root alive and responsive for Toplevel dialogs

except KeyboardInterrupt:
    print("Stopped by user")
finally:
    ser.close()
    plt.close('all')
    root.destroy()