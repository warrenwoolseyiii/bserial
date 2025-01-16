import sys
import threading
import re
try:
    from serial import Serial, SerialException
except ImportError:
    print("Error: pyserial is not installed. Please install it with 'pip install pyserial'.")
    sys.exit(1)

# Check for Tkinter compatibility
try:
    import tkinter as tk
    from tkinter import ttk, filedialog
except ImportError:
    print("Error: Tkinter is not available in this environment. Please ensure it is installed.")
    sys.exit(1)

class SerialTerminalApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Serial Terminal")
        
        # Serial port and configuration
        self.serial_port = None
        self.connected = False
        self.enable_newline = tk.BooleanVar(value=True)
        self.enable_carriage_return = tk.BooleanVar(value=False)
        
        # UI Elements
        self.create_widgets()
        
    def create_widgets(self):
        # Frame for configuration
        config_frame = ttk.LabelFrame(self.root, text="Configuration")
        config_frame.grid(row=0, column=0, padx=10, pady=10, sticky="ew")

        # Port selection
        ttk.Label(config_frame, text="Port:").grid(row=0, column=0, sticky="w")
        self.port_var = tk.StringVar()
        self.port_entry = ttk.Entry(config_frame, textvariable=self.port_var)
        self.port_entry.grid(row=0, column=1, padx=5)

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

        # Line feed checkbox
        self.newline_checkbox = ttk.Checkbutton(action_frame, text="Enable Newline", variable=self.enable_newline)
        self.newline_checkbox.grid(row=1, column=0, sticky="w")

        # Carriage return checkbox
        self.cr_checkbox = ttk.Checkbutton(action_frame, text="Enable CR", variable=self.enable_carriage_return)
        self.cr_checkbox.grid(row=1, column=1, sticky="w")

        # File logging
        self.log_var = tk.BooleanVar()
        self.log_checkbox = ttk.Checkbutton(action_frame, text="Log to File", variable=self.log_var)
        self.log_checkbox.grid(row=2, column=0, sticky="w")

        self.log_button = ttk.Button(action_frame, text="Select Log File", command=self.select_log_file, state="disabled")
        self.log_button.grid(row=2, column=1, padx=5, sticky="w")

        # Layout adjustments
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)  # Allow console output to scale with the window
        console_frame.columnconfigure(0, weight=1)
        action_frame.columnconfigure(1, weight=1)

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
        cursor = 0
        ansi_escape = re.compile(r'(\x1B\[[0-?]*[ -/]*[@-~])')
        matches = list(ansi_escape.finditer(line))

        for match in matches:
            start, end = match.span()
            if start > cursor:
                self.output_text.config(state="normal")
                self.output_text.insert("end", line[cursor:start])
                self.output_text.config(state="disabled")
            cursor = end  # Move past the ANSI sequence

        # Add remaining text if there's no more ANSI sequence
        if cursor < len(line):
            self.output_text.config(state="normal")
            self.output_text.insert("end", line[cursor:] + "\n")
            self.output_text.config(state="disabled")

    def apply_ansi_codes(self, codes):
        for code in map(int, codes):
            if code == 0:
                self.output_text.tag_configure("default", foreground="white", font=("Courier", 10, "bold"))
                self.output_text.tag_add("default", "end-1c", "end")
            elif code == 30:
                self.output_text.tag_configure("black", foreground="black")
                self.output_text.tag_add("black", "end-1c", "end")
            elif code == 31:
                self.output_text.tag_configure("red", foreground="red")
                self.output_text.tag_add("red", "end-1c", "end")
            elif code == 32:
                self.output_text.tag_configure("green", foreground="green")
                self.output_text.tag_add("green", "end-1c", "end")
            elif code == 33:
                self.output_text.tag_configure("yellow", foreground="yellow")
                self.output_text.tag_add("yellow", "end-1c", "end")
            elif code == 34:
                self.output_text.tag_configure("blue", foreground="blue")
                self.output_text.tag_add("blue", "end-1c", "end")
            elif code == 35:
                self.output_text.tag_configure("magenta", foreground="magenta")
                self.output_text.tag_add("magenta", "end-1c", "end")
            elif code == 36:
                self.output_text.tag_configure("cyan", foreground="cyan")
                self.output_text.tag_add("cyan", "end-1c", "end")
            elif code == 37:
                self.output_text.tag_configure("white", foreground="white")
                self.output_text.tag_add("white", "end-1c", "end")

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

    def select_log_file(self):
        file_path = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text files", "*.txt")])
        if file_path:
            self.log_message(f"Logging to: {file_path}")

if __name__ == "__main__":
    root = tk.Tk()
    app = SerialTerminalApp(root)
    root.mainloop()
