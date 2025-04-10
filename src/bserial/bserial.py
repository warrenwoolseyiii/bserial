import sys
import threading
import re
from bserial.version import get_version  # Importing version from version.py
try:
    from serial import Serial, SerialException
except ImportError:
    print("Error: pyserial is not installed. Please install it with 'pip install pyserial'.")
    sys.exit(1)

# Check for Tkinter compatibility
try:
    import tkinter as tk
    from tkinter import ttk, filedialog
    import glob
except ImportError:
    print("Error: Tkinter is not available in this environment. Please ensure it is installed.")
    sys.exit(1)

class SerialTerminalApp:
    def __init__(self, root):
        self.root = root
        title_str = "bserial - Serial Terminal" + " v" + get_version()  # Importing version from version.py
        self.root.title(title_str)
        
        # Serial port and configuration
        self.serial_port = None
        self.connected = False
        self.enable_newline = tk.BooleanVar(value=True)
        self.enable_carriage_return = tk.BooleanVar(value=False)
        self.log_file_path = None
        
        # UI Elements
        self.create_widgets()
        
    def create_widgets(self):
        # Frame for configuration
        config_frame = ttk.LabelFrame(self.root, text="Configuration")
        config_frame.grid(row=0, column=0, padx=10, pady=10, sticky="ew")

        # Port selection
        ttk.Label(config_frame, text="Port:").grid(row=0, column=0, sticky="w")
        self.port_var = tk.StringVar()
        self.port_combobox = ttk.Combobox(config_frame, textvariable=self.port_var)
        self.port_combobox.grid(row=0, column=1, padx=5)
        self.update_ports()

        # Baud rate selection
        ttk.Label(config_frame, text="Baud Rate:").grid(row=0, column=2, sticky="w")
        self.baud_var = tk.StringVar(value="9600")
        self.baud_entry = ttk.Entry(config_frame, textvariable=self.baud_var)
        self.baud_entry.grid(row=0, column=3, padx=5)

        # Connect and Disconnect buttons
        self.connect_button = ttk.Button(config_frame, text="Connect", command=self.connect_serial)
        self.connect_button.grid(row=0, column=4, padx=5)
        self.disconnect_button = ttk.Button(config_frame, text="Disconnect", command=self.disconnect_serial, state="disabled")
        self.disconnect_button.grid(row=0, column=5, padx=5)

        # Frame for console output
        console_frame = ttk.LabelFrame(self.root, text="Console Output")
        console_frame.grid(row=1, column=0, padx=10, pady=10, sticky="nsew")

        self.output_text = tk.Text(console_frame, wrap="word", state="disabled", bg="black", fg="white", font=("Courier", 10, "bold"))
        self.output_text.pack(fill="both", expand=True)

        # Frame for input and actions
        action_frame = ttk.LabelFrame(self.root, text="Actions")
        action_frame.grid(row=2, column=0, padx=10, pady=10, sticky="ew")

        # Input field
        ttk.Label(action_frame, text="Input:").grid(row=0, column=0, sticky="w")
        self.input_var = tk.StringVar()
        self.input_entry = ttk.Entry(action_frame, textvariable=self.input_var)
        self.input_entry.grid(row=0, column=1, padx=5, sticky="ew")
        self.input_entry.bind("<Return>", lambda event: self.send_data_threaded())

        # Send button
        self.send_button = ttk.Button(action_frame, text="Send", command=self.send_data_threaded, state="disabled")
        self.send_button.grid(row=0, column=2, padx=5)

        # Line feed and carriage return checkbox
        self.newline_checkbox = ttk.Checkbutton(action_frame, text="Enable Newline", variable=self.enable_newline)
        self.newline_checkbox.grid(row=1, column=0, sticky="w")

        # Line feed and carriage return checkbox
        self.cr_checkbox = ttk.Checkbutton(action_frame, text="Enable CR", variable=self.enable_carriage_return)
        self.cr_checkbox.grid(row=1, column=1, sticky="w")

        # File logging
        self.log_var = tk.BooleanVar()
        self.log_checkbox = ttk.Checkbutton(action_frame, text="Log to File", variable=self.log_var, command=self.toggle_log_file)
        self.log_checkbox.grid(row=2, column=0, sticky="w")

        self.log_button = ttk.Button(action_frame, text="Select Log File", command=self.select_log_file, state="disabled")
        self.log_button.grid(row=2, column=1, padx=5, sticky="w")

        # Layout adjustments
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)  # Allow console output to scale with the window
        console_frame.columnconfigure(0, weight=1)
        action_frame.columnconfigure(1, weight=1)

        # Button to clear all text that has been stored in the display window
        clear_button = ttk.Button(action_frame, text="Clear", command=self.clear_text)
        clear_button.grid(row=2, column=2, padx=5)

    def update_ports(self):
        """Update the list of available serial ports."""
        try:
            if sys.platform.startswith('win'):
                available_ports = [f'COM{i + 1}' for i in range(256)]
            else:
                available_ports = glob.glob('/dev/tty.[A-Za-z]*')

            self.port_combobox['values'] = available_ports
            if available_ports:
                self.port_combobox.current(0)
        except Exception as e:
            self.log_message(f"Error updating ports: {e}")

    def connect_serial(self):
        port = self.port_var.get()
        baud = self.baud_var.get()
        try:
            self.serial_port = Serial(port, baudrate=int(baud), timeout=1)
            self.connected = True
            self.connect_button.config(state="disabled")
            self.disconnect_button.config(state="normal")
            self.send_button.config(state="normal")
            self.log_button.config(state="normal")
            
            # Start the thread for reading data
            self.read_thread = threading.Thread(target=self.read_serial, daemon=True)
            self.read_thread.start()
            
            self.log_message(f"Connected to {port} at {baud} baud.")
        except SerialException as e:
            self.log_message(f"Error: {e}")
        except ValueError:
            self.log_message("Error: Invalid baud rate. Please enter a valid number.")

    def disconnect_serial(self):
        if self.serial_port and self.serial_port.is_open:
            self.serial_port.close()
        self.connected = False
        self.connect_button.config(state="normal")
        self.disconnect_button.config(state="disabled")
        self.send_button.config(state="disabled")
        self.log_button.config(state="disabled")
        self.log_message("Disconnected.")

    def read_serial(self):
        buffer = ""
        while self.connected:
            try:
                if self.serial_port.in_waiting > 0:
                    buffer += self.serial_port.read(self.serial_port.in_waiting).decode(errors="ignore")
                    while "\n" in buffer:
                        line, buffer = buffer.split("\n", 1)
                        self.process_ansi_colored_line(line)
            except Exception as e:
                self.log_message(f"Error: {e}")
                break

    def process_ansi_colored_line(self, line):
        """Processes a line with ANSI color codes and applies a single color to the whole line."""
        ansi_escape = re.compile(r'\x1B\[[0-9;]*m')  # Regex for all ANSI color codes
        self.output_text.config(state="normal")

        print(f"\n[DEBUG] Processing line: {line}")

        # Find the first ANSI escape sequence in the line
        match = ansi_escape.search(line)
        active_tag = "white"  # Default text color

        if match:
            ansi_code = match.group(0)  # Extract ANSI escape sequence
            print(f"[DEBUG] Found ANSI escape sequence: {ansi_code}")

            color_code = self.extract_color_code(ansi_code)  # Convert to numeric code
            if color_code:
                active_tag = self.apply_ansi_codes(color_code)
                print(f"[DEBUG] Applying color tag: {active_tag} (from ANSI code {color_code})")
            else:
                print("[DEBUG] No valid ANSI color code found, using default white.")

        # Remove all ANSI escape sequences from the text
        clean_line = ansi_escape.sub("", line).strip()
        print(f"[DEBUG] Cleaned line (without ANSI codes): {clean_line}")
        self.log_to_file(clean_line)

        # Ensure the tag exists before applying
        self.ensure_tag_configured(active_tag)

        # Insert the entire cleaned line with the detected color
        print(f"[DEBUG] Inserting line with tag: {active_tag}")
        self.output_text.insert("end", clean_line + "\n", active_tag)

        self.output_text.see("end")
        self.output_text.config(state="disabled")

    def extract_color_code(self, ansi_sequence):
        """Extracts the main ANSI color code from an ANSI escape sequence."""
        print(f"[DEBUG] Extracting color code from ANSI sequence: {ansi_sequence}")
        
        codes = [int(x) for x in re.findall(r'\d+', ansi_sequence)]  # Extract numeric values
        print(f"[DEBUG] Parsed ANSI codes: {codes}")

        # Check for standard and bright colors
        for code in codes:
            if 90 <= code <= 97 or 30 <= code <= 37:
                print(f"[DEBUG] Found valid color code: {code}")
                return code

        print("[DEBUG] No valid ANSI color code found in sequence.")
        return None  # No valid color found

    def apply_ansi_codes(self, code):
        """Maps ANSI color codes to text widget tags."""
        ansi_color_map = {
            0: "white",
            30: "black",
            31: "red",
            32: "green",
            33: "yellow",
            34: "blue",
            35: "magenta",
            36: "cyan",
            37: "white",
            90: "bright_black",
            91: "bright_red",
            92: "bright_green",
            93: "bright_yellow",
            94: "bright_blue",
            95: "bright_magenta",
            96: "bright_cyan",
            97: "bright_white"
        }

        tag = ansi_color_map.get(code, "white")
        print(f"[DEBUG] Mapped ANSI code {code} to tag: {tag}")
        return tag

    def ensure_tag_configured(self, tag):
        """Ensures that the Tkinter Text widget has the necessary color tags configured."""
        if not hasattr(self, "configured_tags"):
            self.configured_tags = set()  # Keep track of configured tags

        if tag not in self.configured_tags:
            print(f"[DEBUG] Configuring new text tag: {tag}")
            self.output_text.tag_configure(tag, foreground=tag)
            self.configured_tags.add(tag)

    def send_data(self):
        try:
            if self.serial_port and self.serial_port.is_open:
                data = self.input_var.get()
                if self.enable_carriage_return.get():
                    data += "\r"
                if self.enable_newline.get():
                    data += "\n"
                self.serial_port.write(data.encode())
                self.log_message(f"Sent: {data}")
                self.log_to_file(f"Sent: {data}")
                self.input_var.set("")
        except Exception as e:
            self.log_message(f"Error sending data: {e}")

    def send_data_threaded(self):
        send_thread = threading.Thread(target=self.send_data)
        send_thread.start()

    def log_message(self, message):
        self.output_text.config(state="normal")
        self.output_text.insert("end", message + "\n")
        self.output_text.config(state="disabled")
        self.output_text.see("end")

    def log_to_file(self, message):
        if self.log_var.get() and self.log_file_path:
            try:
                with open(self.log_file_path, "a") as log_file:
                    # Loop through the message, if you see a null terminator before the end of the message, remove it
                    message = message.replace("\x00", "")
                    log_file.write(message + "\n")
            except Exception as e:
                self.log_message(f"Error writing to log file: {e}")
        else:
            print("Logging is not enabled or no file is selected.")

    def select_log_file(self):
        file_path = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text files", "*.txt")])
        if file_path:
            self.log_file_path = file_path
            self.log_message(f"Logging to: {file_path}")

    def toggle_log_file(self):
        if self.log_var.get() and not self.log_file_path:
            self.select_log_file()

    def clear_text(self):
        self.output_text.config(state="normal")
        self.output_text.delete("1.0", "end")
        self.output_text.config(state="disabled")

if __name__ == "__main__":
    root = tk.Tk()
    app = SerialTerminalApp(root)
    root.mainloop()
