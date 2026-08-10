import logging
import os
import queue
import sys
import threading
from datetime import datetime

from .ansi import AnsiParser
from .version import get_version  # Importing version from version.py

try:
    from serial import Serial, SerialException
except ImportError:
    print("Error: pyserial is not installed. Please install it with 'pip install pyserial'.")
    sys.exit(1)

# Check for Tkinter compatibility
try:
    import glob
    import tkinter as tk
    from tkinter import filedialog, ttk
except ImportError:
    print("Error: Tkinter is not available in this environment. Please ensure it is installed.")
    sys.exit(1)

logger = logging.getLogger(__name__)


def is_pinned(fraction, eps=1e-3):
    """Pure logic (PLAN.md 4.2): True if a Text widget's yview upper bound
    ``fraction`` (0.0..1.0) is close enough to 1.0 to be considered "at the
    bottom". Extracted for unit testing without a Tk widget."""
    return fraction >= 1.0 - eps


class SerialTerminalApp:
    # PLAN.md 4.x smart autoscroll: fraction tolerance for "at bottom".
    PIN_EPSILON = 1e-3
    # PLAN.md 4.4 buffer trimming: max lines retained in the console widget.
    MAX_LINES = 5000

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
        # Opt-in workaround (default OFF) for firmware built with the
        # GNU-only '\e' escape that a toolchain silently degrades to the
        # literal characters 'e' '[' instead of a real ESC (0x1B) byte.
        # Confirmed via raw serial capture against a real device where no
        # 0x1B byte was ever present -- only literal "e[0;33m" text.
        self.literal_e_quirk_var = tk.BooleanVar(value=False)
        # OS timestamp prefix: prepend "[HH:MM:SS:MS]" to each received line.
        self.timestamp_var = tk.BooleanVar(value=False)
        self._ts_line_start = True
        self.ansi_parser = AnsiParser(literal_e_quirk=self.literal_e_quirk_var.get())
        self.configured_tags = set()
        self._last_pinned = True
        self._anchor_seq = 0

        # Thread-safe hand-off (root cause fix): the background read_serial()
        # thread must never touch Tk widgets directly (Tcl/Tk is single
        # threaded). Decoded chunks are pushed onto this queue from the
        # reader thread and drained/rendered only on the main thread via
        # root.after() polling in _poll_serial_queue().
        self._serial_queue: "queue.Queue[str]" = queue.Queue()
        self._queue_poll_ms = 20

        # UI Elements
        self.create_widgets()
        self._poll_serial_queue()
        
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
        # PLAN.md 4.4: on resize, re-pin only if we were pinned before the resize.
        self.output_text.bind("<Configure>", self._on_console_configure)

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

        # Device-quirk workaround: some firmware sends literal 'e[' instead
        # of a real ESC (0x1B) byte for ANSI color codes (GNU '\e' escape
        # not supported by the device's toolchain). Off by default.
        self.literal_e_checkbox = ttk.Checkbutton(
            action_frame,
            text="Treat literal 'e[' as ANSI (device quirk)",
            variable=self.literal_e_quirk_var,
            command=self._on_literal_e_quirk_toggle,
        )
        self.literal_e_checkbox.grid(row=3, column=0, columnspan=2, sticky="w")

        # OS timestamp prefix toggle: affects subsequent lines only.
        self.timestamp_checkbox = ttk.Checkbutton(action_frame, text="Add OS Timestamp", variable=self.timestamp_var)
        self.timestamp_checkbox.grid(row=4, column=0, sticky="w")

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

        # Hidden manual ANSI smoke-test action (see tools/ansi_smoke.py, PLAN.md 3.3)
        demo_button = ttk.Button(action_frame, text="ANSI Demo", command=self.run_ansi_demo)
        demo_button.grid(row=2, column=3, padx=5)

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
        """Runs on a background thread. Must NEVER touch Tk widgets
        directly (Tcl/Tk is single-threaded) -- decoded chunks are handed
        off via a thread-safe queue and rendered on the main thread by
        _poll_serial_queue()/process_ansi_chunk()."""
        while self.connected:
            try:
                if self.serial_port.in_waiting > 0:
                    raw = self.serial_port.read(self.serial_port.in_waiting)
                    logger.debug("Raw bytes from serial: %r", raw)
                    if os.environ.get("BSERIAL_DEBUG_RAW"):
                        try:
                            with open("raw_capture.log", "a", encoding="utf-8") as f:
                                f.write(repr(raw) + "\n")
                        except Exception:
                            pass
                    chunk = raw.decode(errors="ignore")
                    if chunk:
                        self._serial_queue.put(chunk)
            except Exception as e:
                self.log_message(f"Error: {e}")
                break

    def _poll_serial_queue(self):
        """Runs on the main thread via root.after(). Drains any chunks the
        background read_serial() thread has queued and renders them through
        process_ansi_chunk(), keeping all Tk widget mutation on the main
        thread (fix for cross-thread Tk access that corrupted/garbled
        escape sequences in the console output)."""
        try:
            while True:
                chunk = self._serial_queue.get_nowait()
                self.process_ansi_chunk(chunk)
        except queue.Empty:
            pass
        finally:
            self.root.after(self._queue_poll_ms, self._poll_serial_queue)

    def _timestamp_str(self):
        """Local OS time as "[HH:MM:SS:MS] " (MS = 3-digit milliseconds)."""
        now = datetime.now()
        return now.strftime("[%H:%M:%S:") + f"{now.microsecond // 1000:03d}] "

    def _prefix_lines(self, text, pending):
        """Prefixes each line-start in ``text`` with a timestamp, chunk-safe:
        ``pending`` carries "next char starts a new line" across calls so a
        line split across reads is only stamped once, at its true start."""
        if not text:
            return text, pending
        out = []
        for line in text.splitlines(keepends=True):
            if pending:
                line = self._timestamp_str() + line
            out.append(line)
            pending = line.endswith("\n")
        return "".join(out), pending

    def process_ansi_chunk(self, chunk):
        """Parses an incoming chunk of (possibly ANSI-colored) text into
        styled spans and inserts each span with its own Tk tag, preserving
        mid-line color changes and persisting style state across chunks.

        Must only be called on the main thread (see _poll_serial_queue)."""
        logger.debug("Processing chunk: %r", chunk)

        spans = self.ansi_parser.feed(chunk)
        if not spans:
            return

        ts_on = self.timestamp_var.get()

        # Plain text (ANSI stripped) for file logging.
        clean_text = "".join(span.text for span in spans)
        if ts_on:
            log_text, _ = self._prefix_lines(clean_text, self._ts_line_start)
        else:
            log_text = clean_text
        self.log_to_file(log_text.rstrip("\n"))

        pinned = self._is_pinned()
        self.output_text.config(state="normal")
        pending = self._ts_line_start
        for span in spans:
            tag = self.ensure_tag_configured(span.state)
            text = span.text
            if ts_on:
                text, pending = self._prefix_lines(text, pending)
            self.output_text.insert("end", text, tag)
        if ts_on:
            self._ts_line_start = pending
        self._trim_buffer(pinned)
        self.output_text.config(state="disabled")
        self._autoscroll(pinned)

    # ---- Smart autoscroll helpers (PLAN.md 4.x) --------------------------

    def _is_pinned(self):
        """True if the console view is currently pinned to the bottom.

        Read the yview fraction *before* mutating the widget: after an
        insert/delete the fraction has already shifted, so pin state must
        be captured beforehand and threaded through to the post-insert
        autoscroll decision.
        """
        _first, last = self.output_text.yview()
        return is_pinned(last, self.PIN_EPSILON)

    def _autoscroll(self, pinned):
        """Scroll to the end only if the view was pinned prior to the
        mutation that just happened. Never force-scrolls an unpinned user
        back to the bottom."""
        self._last_pinned = pinned
        if pinned:
            self.output_text.see("end")

    def _capture_anchor(self):
        """Marks the first visible line so it can be restored after a
        buffer trim shifts line numbers out from under an unpinned user."""
        self._anchor_seq += 1
        mark = f"_autoscroll_anchor_{self._anchor_seq}"
        self.output_text.mark_set(mark, "@0,0")
        self.output_text.mark_gravity(mark, "left")
        return mark

    def _restore_anchor(self, mark):
        """Restores the view to a previously captured anchor mark. Tk marks
        automatically shift when text before them is deleted, so the mark
        still points at the user's original content after trimming."""
        try:
            self.output_text.see(mark)
        finally:
            self.output_text.mark_unset(mark)

    def _trim_buffer(self, pinned):
        """Caps the console buffer at MAX_LINES, preserving the unpinned
        user's scroll position across the deletion (PLAN.md 4.4)."""
        if self.MAX_LINES <= 0:
            return
        line_count = int(self.output_text.index("end-1c").split(".")[0])
        excess = line_count - self.MAX_LINES
        if excess <= 0:
            return

        anchor = None if pinned else self._capture_anchor()
        self.output_text.delete("1.0", f"{excess + 1}.0")
        if anchor is not None:
            self._restore_anchor(anchor)

    def _on_console_configure(self, _event):
        """Window/pane resize (PLAN.md 4.4): re-pin only if we were pinned
        prior to the resize; never force an unpinned user back down."""
        if self._last_pinned:
            self.output_text.see("end")

    def ensure_tag_configured(self, state):
        """Ensures that the Tkinter Text widget has a tag configured for the
        given SgrState, creating/configuring it lazily and caching by tag
        name. Returns the tag name to apply."""
        tag = state.tag_name()

        if tag not in self.configured_tags:
            logger.debug("Configuring new text tag: %s (state=%s)", tag, state)
            kwargs = {}
            if state.fg is not None:
                kwargs["foreground"] = state.fg
            if state.bg is not None:
                kwargs["background"] = state.bg
            if state.underline:
                kwargs["underline"] = True
            if state.bold and state.italic:
                kwargs["font"] = ("Courier", 10, "bold italic")
            elif state.bold:
                kwargs["font"] = ("Courier", 10, "bold")
            elif state.italic:
                kwargs["font"] = ("Courier", 10, "italic")

            # Reverse video: swap fg/bg using current defaults if unset.
            if state.reverse:
                fg = kwargs.get("foreground", "white")
                bg = kwargs.get("background", "black")
                kwargs["foreground"] = bg
                kwargs["background"] = fg

            self.output_text.tag_configure(tag, **kwargs)
            self.configured_tags.add(tag)

        return tag

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
        pinned = self._is_pinned()
        self.output_text.config(state="normal")
        self.output_text.insert("end", message + "\n")
        self._trim_buffer(pinned)
        self.output_text.config(state="disabled")
        self._autoscroll(pinned)

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
            logger.debug("Logging is not enabled or no file is selected.")

    def select_log_file(self):
        file_path = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text files", "*.txt")])
        if file_path:
            self.log_file_path = file_path
            self.log_message(f"Logging to: {file_path}")

    def toggle_log_file(self):
        if self.log_var.get() and not self.log_file_path:
            self.select_log_file()

    def clear_text(self):
        # Explicit user action (PLAN.md 4.4): always force back to bottom.
        self.output_text.config(state="normal")
        self.output_text.delete("1.0", "end")
        self.output_text.config(state="disabled")
        self._autoscroll(pinned=True)

    def _on_literal_e_quirk_toggle(self):
        """Toggle the opt-in device-quirk workaround (see __init__) on the
        live parser without losing its current SGR state."""
        self.ansi_parser.literal_e_quirk = self.literal_e_quirk_var.get()

    def run_ansi_demo(self):
        """Manual GUI smoke test: feeds canned ANSI escape sequences into the
        console widget so colors/styles/reset/mid-line switches can be
        verified visually (see tools/ansi_smoke.py, PLAN.md 3.3)."""
        from .ansi_demo_data import ANSI_DEMO_LINES

        for line in ANSI_DEMO_LINES:
            self.process_ansi_chunk(line + "\n")


def main():
    logging.basicConfig(level=logging.INFO)
    root = tk.Tk()
    SerialTerminalApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
