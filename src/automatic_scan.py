import tkinter as tk
from tkinter import ttk, messagebox
import threading
import time
import serial
import pyvisa

class StageScannerApp:
    def __init__(self, master):
        self.master = master
        self.master.title("Stage Scan Controller")

        # --- Parameter Inputs (units shown in labels) ---
        tk.Label(master, text="X Speed (mm/s)").grid(row=0, column=0, padx=5, pady=2)
        self.x_speed_entry = tk.Entry(master)
        self.x_speed_entry.insert(0, "0.1")
        self.x_speed_entry.grid(row=0, column=1, padx=5, pady=2)

        tk.Label(master, text="Y Speed (mm/s)").grid(row=1, column=0, padx=5, pady=2)
        self.y_speed_entry = tk.Entry(master)
        self.y_speed_entry.insert(0, "0.2")
        self.y_speed_entry.grid(row=1, column=1, padx=5, pady=2)

        tk.Label(master, text="Trigger Frequency (Hz)").grid(row=2, column=0, padx=5, pady=2)
        self.freq_entry = tk.Entry(master)
        self.freq_entry.insert(0, "10")
        self.freq_entry.grid(row=2, column=1, padx=5, pady=2)

        tk.Label(master, text="Y Scan Distance (mm)").grid(row=3, column=0, padx=5, pady=2)
        self.scan_y_entry = tk.Entry(master)
        self.scan_y_entry.insert(0, "8.0")
        self.scan_y_entry.grid(row=3, column=1, padx=5, pady=2)

        tk.Label(master, text="Number of X Tiles").grid(row=4, column=0, padx=5, pady=2)
        self.tile_count_entry = tk.Entry(master)
        self.tile_count_entry.insert(0, "10")
        self.tile_count_entry.grid(row=4, column=1, padx=5, pady=2)

        tk.Label(master, text="X Tile Step (mm)").grid(row=5, column=0, padx=5, pady=2)
        self.tile_step_entry = tk.Entry(master)
        self.tile_step_entry.insert(0, "0.7")
        self.tile_step_entry.grid(row=5, column=1, padx=5, pady=2)

        # --- Control Buttons ---
        self.start_button = tk.Button(master, text="Start Scan", command=self.start_scan)
        self.start_button.grid(row=6, column=0, padx=10, pady=5)

        self.next_button = tk.Button(master, text="Next Scan", command=self.next_scan)
        self.next_button.grid(row=6, column=1, padx=10, pady=5)

        self.return_button = tk.Button(master, text="Return to Start", command=self.return_to_initial)
        self.return_button.grid(row=6, column=2, padx=10, pady=5)

        self.stop_button = tk.Button(master, text="Stop Scan", command=self.stop_scan, bg="red", fg="white")
        self.stop_button.grid(row=6, column=3, padx=10, pady=5)

        # --- Manual Position Control (absolute move) ---
        manual_frame = tk.Frame(master)
        manual_frame.grid(row=7, column=0, columnspan=7, sticky='w', padx=10, pady=5)
        tk.Label(manual_frame, text="X").grid(row=0, column=0)
        self.goto_x = tk.Entry(manual_frame, width=10)
        self.goto_x.grid(row=0, column=1)
        tk.Label(manual_frame, text="Y").grid(row=0, column=2)
        self.goto_y = tk.Entry(manual_frame, width=10)
        self.goto_y.grid(row=0, column=3)
        tk.Label(manual_frame, text="Z").grid(row=0, column=4)
        self.goto_z = tk.Entry(manual_frame, width=10)
        self.goto_z.grid(row=0, column=5)
        self.goto_button = tk.Button(manual_frame, text="Go to XYZ", command=self.goto_xyz)
        self.goto_button.grid(row=0, column=6, padx=10)

        # --- Progress Bar (per-tile progress) ---
        self.progress = ttk.Progressbar(master, orient="horizontal", length=400, mode="determinate")
        self.progress.grid(row=8, column=0, columnspan=7, padx=10, pady=5)

        # --- Text Log (simple log/console) ---
        self.text = tk.Text(master, height=20, width=90)
        self.text.grid(row=9, column=0, columnspan=7)

        # --- Internal state ---
        self.scanning = False
        self.next_event = threading.Event()
        self.init_devices()  # open serial/VISA

    def init_devices(self):
        """Open hardware connections. Edit ports/resources to match your setup."""
        self.stage = serial.Serial('COM8', baudrate=9600, timeout=1)  # stage controller on COM8
        self.rm = pyvisa.ResourceManager()
        # Example Rigol DG800 resource; change for your instrument
        self.dg800 = self.rm.open_resource('USB0::0x1AB1::0x0643::DG8A211800767::INSTR')

    def log_message(self, msg):
        """Append a line to the log window (note: Tk from worker threads is not strictly safe)."""
        self.text.insert(tk.END, msg + "\n")
        self.text.see(tk.END)

    def send_command(self, device, command):
        """
        Send an ASCII command terminated with CR and read one line back.
        This is a simple helper; adapt endlines/echo/timeout to your device protocol.
        """
        device.reset_input_buffer()
        device.write((command + '\r').encode('ascii'))
        time.sleep(0.05)  # naive wait for response; tune per device
        return device.readline().decode('ascii').strip()

    def stop_scan(self):
        """Request stop, disable generator output, and send ESC to stage."""
        self.scanning = False
        self.next_event.set()
        self.log_message("Scan stop requested...")
        try:
            self.dg800.write(":OUTP1 OFF")  # stop DG800 CH1 output
            self.stage.write(b"\x1B\r")     # ESC (device-specific emergency/stop)
            self.log_message("Devices stopped.")
        except Exception as e:
            self.log_message(f"Error while stopping: {e}")

    def start_scan(self):
        """Parse UI parameters and start the scan sequence in a worker thread."""
        try:
            x_speed = float(self.x_speed_entry.get())
            y_speed = float(self.y_speed_entry.get())
            trigger_freq = float(self.freq_entry.get())
            scan_range_y = float(self.scan_y_entry.get()) * 1e4  # device-specific scaling
            tile_count = int(self.tile_count_entry.get())
            tile_step_x = float(self.tile_step_entry.get()) * 1e4  # device-specific scaling
        except ValueError:
            self.log_message("Invalid input values.")
            return

        self.scan_params = (x_speed, y_speed, trigger_freq, scan_range_y, tile_count, tile_step_x)
        threading.Thread(target=self.scan_sequence).start()  # non-blocking GUI

    def next_scan(self):
        """Signal the worker to proceed to the next tile."""
        self.next_event.set()

    def return_to_initial(self):
        """Move back to stored start position after user confirmation (safety for lasers)."""
        if messagebox.askyesno("Confirmation", "Have you turned off the lasers?"):
            try:
                self.send_command(self.stage, f"M X={self.x0} Y={self.y0}")
                self.log_message("Returned to initial position by user request.")
            except Exception as e:
                self.log_message(f"Failed to return to initial position: {e}")

    def goto_xyz(self):
        """Manual absolute move to the specified X/Y/Z."""
        try:
            x = float(self.goto_x.get())
            y = float(self.goto_y.get())
            z = float(self.goto_z.get())
            self.send_command(self.stage, f"M X={x} Y={y} Z={z}")
            self.log_message(f"Moved to position X={x}, Y={y}, Z={z}")
        except ValueError:
            self.log_message("Invalid XYZ input.")

    def scan_sequence(self):
        """Worker thread: run the tiled scan sequence and drive the DG800 during Y moves."""
        self.scanning = True
        x_speed, y_speed, trigger_freq, scan_range_y, tile_count, tile_step_x = self.scan_params
        total_time = scan_range_y / 1e4 / y_speed  # seconds for one Y pass (time-based wait)

        # Initialize progress
        self.progress["maximum"] = tile_count
        self.progress["value"] = 0

        self.log_message(f"Scan started: {tile_count} tiles, Y scan {scan_range_y / 1e4} mm at {y_speed} mm/s")
        self.log_message(f"Trigger frequency: {trigger_freq} Hz, duration: {total_time:.2f} sec")

        # Set stage speeds (device-specific command)
        self.send_command(self.stage, f"S X={x_speed} Y={y_speed}")

        # Read initial position and store as (x0, y0)
        pos = self.send_command(self.stage, "W X Y Z")
        self.log_message("Initial position (X Y Z): " + pos)

        try:
            _, x0, y0, _ = pos.split()
            self.x0 = float(x0)
            self.y0 = float(y0)
        except:
            self.log_message("Failed to parse position.")
            self.scanning = False
            return

        # Main tile loop
        for i in range(tile_count):
            if not self.scanning:
                break

            # Alternate Y direction each tile (serpentine scan)
            target_y = self.y0 + scan_range_y if i % 2 == 0 else self.y0
            self.send_command(self.stage, f"M Y={target_y}")

            # Configure and enable DG800 output for this pass
            self.dg800.write(":SOUR1:FUNC PULSE")
            self.dg800.write(f":SOUR1:FREQ {trigger_freq}")
            self.dg800.write(":SOUR1:VOLT 5")
            self.dg800.write(":SOUR1:VOLT:OFFS 2.5")
            self.dg800.write(":OUTP1 ON")

            # Time-based wait for the Y scan to complete (replace with in-position polling if available)
            t_start = time.time()
            while time.time() - t_start < total_time:
                if not self.scanning:
                    break
                time.sleep(0.1)

            # Stop trigger output at the end of this Y pass
            self.dg800.write(":OUTP1 OFF")

            if not self.scanning:
                break

            # Step X to the next tile origin
            next_x = self.x0 + (i + 1) * tile_step_x
            self.send_command(self.stage, f"M X={next_x}")

            # Update UI/log
            if i + 1 < tile_count:
                self.log_message(f"Tile {i + 1}/{tile_count} complete. Waiting for next scan...")
            elif i + 1 == tile_count:
                self.log_message("All the scans complete. Press 'Return to Start'")
            self.progress["value"] = i + 1

            # Wait for user to press "Next Scan"
            self.next_event.clear()
            self.next_event.wait()

        # Return to start (X0, Y0) and finalize
        self.send_command(self.stage, f"M X={self.x0} Y={self.y0}")
        self.progress["value"] = 0
        self.log_message("Returned to initial position.")
        self.scanning = False
        self.log_message("Scan completed or stopped.")

if __name__ == "__main__":
    root = tk.Tk()
    app = StageScannerApp(root)
    root.mainloop()
