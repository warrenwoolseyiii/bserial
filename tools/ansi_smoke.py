"""Manual GUI smoke test for ANSI color rendering.

Launches the bserial GUI (without an actual serial connection) and feeds
canned ANSI escape sequences straight into the console `Text` widget so
colors, bold/underline/reverse, backgrounds, 256-color/truecolor, and
mid-line color switches can be verified visually. Also confirms no
`TclError` is raised (the historical `bright_red` invalid-color bug).

Usage:
    python tools/ansi_smoke.py
"""

import sys
from pathlib import Path

# Allow running directly from a source checkout without installing.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import tkinter as tk

from bserial.ansi_demo_data import ANSI_DEMO_LINES
from bserial.bserial import SerialTerminalApp


def main():
    root = tk.Tk()
    app = SerialTerminalApp(root)

    def feed_demo():
        for line in ANSI_DEMO_LINES:
            app.process_ansi_chunk(line + "\n")

    # Feed once shortly after the window appears.
    root.after(200, feed_demo)

    root.mainloop()


if __name__ == "__main__":
    main()
