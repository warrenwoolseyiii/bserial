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

        # Line feed and carriage return checkbox
        self.newline_checkbox = ttk.Checkbutton(action_frame, text="Enable Newline/CR", variable=self.enable_newline)
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
                        self.log_to_file(line)
            except Exception as e:
                self.log_message(f"Error: {e}")
                break

    def process_ansi_colored_line(self, line):
        cursor = 0
        ansi_escape = re.compile(r'\x1B\[(\d+)(;\d+)*m')
        self.output_text.config(state="normal")

        print(f"Processing line: {line}")

        for match in ansi_escape.finditer(line):
            start, end = match.span()
            print(f"Found ANSI escape sequence from {start} to {end}: {match.group(0)}")

            # Insert plain text before the ANSI sequence
            if start > cursor:
                text_to_insert = line[cursor:start]
                print(f"Inserting plain text: {text_to_insert}")
                self.output_text.insert("end", text_to_insert)

            # Extract the desired parameter (33 in this case)
            parameters = match.group(0).split('[')[1].split('m')[0].split(';')
            if len(parameters) > 1:
                desired_code = parameters[1]
                print(f"Extracted code: {desired_code}")
                # Convert the code to an integer
                try:
                    desired_code = int(desired_code)
                except ValueError:
                    print(f"Invalid code: {desired_code}")
                    continue

            # Apply color to the text "SYS"
            colored_text = line[end:].split('m')[0]
            # Remove the trailing '[' if there is one
            if colored_text.endswith('['):
                colored_text = colored_text[:-1]
            print(f"Applying color to text: {colored_text}")
            # Get the current index of the cursor to pass to the tag_add method
            tag = "yellow"#self.apply_ansi_codes(desired_code)
            current_index = self.output_text.index("end-1c")
            self.output_text.insert("end", colored_text)
            self.output_text.tag_add(colored_text, current_index, "end")
            self.output_text.tag_configure(colored_text, foreground=tag)

            # Remove the ANSI escape sequence and the text inside the brackets
            line = line[end + len(colored_text) + 3:]
            cursor = 0

        # Insert remaining text
        if cursor < len(line):
            remaining_text = line[cursor:]
            print(f"Inserting remaining text: {remaining_text}")
            self.output_text.insert("end", remaining_text)

        self.output_text.insert("end", "\n")
        self.output_text.see("end")
        self.output_text.config(state="disabled")

    def apply_ansi_codes(self, code):
        tag_name = None
        if code == 0:
            tag_name = "white"
            #self.output_text.tag_configure(tag_name, foreground="white", font=("Courier", 10, "bold"))
        elif code == 30:
            tag_name = "black"
            #self.output_text.tag_configure(tag_name, foreground="black")
        elif code == 31:
            tag_name = "red"
            #self.output_text.tag_configure(tag_name, foreground="red")
        elif code == 32:
            tag_name = "green"
            #self.output_text.tag_configure(tag_name, foreground="green")
        elif code == 33:
            tag_name = "yellow"
            #self.output_text.tag_configure("SYS", foreground="yellow")
        elif code == 34:
            tag_name = "blue"
            #self.output_text.tag_configure(tag_name, foreground="blue")
        elif code == 35:
            tag_name = "magenta"
            #self.output_text.tag_configure(tag_name, foreground="magenta")
        elif code == 36:
            tag_name = "cyan"
            #self.output_text.tag_configure(tag_name, foreground="cyan")
        elif code == 37:
            tag_name = "white"
            #self.output_text.tag_configure(tag_name, foreground="white")

        return tag_name

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
        self.log_to_file(message)

    def log_to_file(self, message):
        if self.log_var.get() and self.log_file_path:
            try:
                with open(self.log_file_path, "a") as log_file:
                    log_file.write(message + "\n")
            except Exception as e:
                self.log_message(f"Error writing to log file: {e}")

    def select_log_file(self):
        file_path = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text files", "*.txt")])
        if file_path:
            self.log_file_path = file_path
            self.log_message(f"Logging to: {file_path}")

    def toggle_log_file(self):
        if self.log_var.get() and not self.log_file_path:
            self.select_log_file()

if __name__ == "__main__":
    root = tk.Tk()
    app = SerialTerminalApp(root)
    root.mainloop()
