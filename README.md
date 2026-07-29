# bserial

bserial is a cross-platform GUI serial terminal built with Python and Tkinter. It lets you pick a serial port and baud rate, connect, view incoming data (with ANSI SGR color support) in a scrolling console, send data back to the device, and optionally log the session to a file.

There is no command-line interface / flags — `bserial` always launches the Tkinter GUI.

## Features

- Serial port list populated automatically (COM1-COM256 candidates on Windows; scans `/dev/tty*` on other platforms)
- Configurable baud rate, optional newline/carriage-return on send
- ANSI SGR color rendering in the console ([`src/bserial/ansi.py`](src/bserial/ansi.py:1)): 16-color and bright foreground/background, bold, italic, underline, reverse video, 256-color and truecolor (`38;5;n` / `38;2;r;g;b`), state persists across chunks/lines
- Smart autoscroll: the view only jumps to the bottom on new data if you were already pinned to the bottom; scrolling up to review history is preserved even while data keeps arriving
- Optional logging of received/sent text to a file
- Bounded console buffer (`MAX_LINES`, default 5000) to avoid unbounded memory growth on long-running sessions

## Requirements

- Python 3.7+ (CI targets 3.11)
- [`pyserial`](https://pypi.org/project/pyserial/) (installed automatically as a dependency)
- Tkinter — ships with the standard python.org installers on Windows/macOS. On Linux it is usually a separate OS package:
  ```bash
  sudo apt-get install -y python3-tk
  ```

## Installation

Clone the repository and install with pip:

```bash
git clone https://github.com/warrenwoolseyiii/bserial.git
cd bserial
pip install .
```

This installs bserial and its runtime dependencies (`pyserial`) and registers the `bserial` console-script entry point.

## Usage

Launch the GUI:

```bash
bserial
```

or, equivalently:

```bash
python -m bserial
```

In the window: pick a **Port** and **Baud Rate**, click **Connect**, type into the **Input** field and press Enter (or click **Send**) to transmit. Use **Log to File** to record the session to disk, **Clear** to wipe the console, and **ANSI Demo** to run a canned smoke test of every supported color/style combination directly in the widget.

> Do not run `python src/bserial/bserial.py` directly — the package uses relative imports and expects to be run via the `bserial` entry point, `python -m bserial`, or after an editable/regular install.

## Development

### Setting up a dev environment

**Windows (PowerShell):**
```powershell
cd c:\Users\WWoolsey\Repos\bserial
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
```
If script execution is blocked: `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`.

**Linux / macOS (bash):**
```bash
sudo apt-get install -y python3-venv python3-tk   # Linux only, for Tkinter
cd ~/Repos/bserial
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev]"
sudo usermod -a -G dialout "$USER"   # Linux only: serial port access, re-login required
```

The `dev` extra installs `pytest`, `pytest-cov`, `ruff`, `build`, and `pyinstaller`.

### Project layout

```
src/bserial/
  bserial.py           # Tkinter app, serial I/O, main() entry point
  ansi.py              # GUI-free ANSI/SGR escape sequence parser
  ansi_demo_data.py     # Canned escape sequences for the ANSI Demo / smoke test
  version.py            # __version__ / get_version()
  __main__.py            # `python -m bserial` entry point
tests/
  test_ansi.py           # ansi.py parser unit tests
  test_autoscroll.py     # is_pinned()/autoscroll logic unit tests
tools/
  ansi_smoke.py          # standalone manual GUI smoke test for ANSI rendering
```

### Running tests

```bash
pytest
```

### Linting

```bash
ruff check .
```

### ANSI rendering smoke test

To manually verify ANSI colors/styles render correctly in a live Tk window without a serial connection:

```bash
python tools/ansi_smoke.py
```

This opens the GUI and feeds a canned stream of ANSI escape sequences (all 16 colors, bright variants, bold/italic/underline/reverse, 256-color, truecolor, and mid-line color switches) directly into the console widget shortly after it appears. The same demo is also available from within the running app via the **ANSI Demo** button.

### Building a standalone executable

```bash
pip install build pyinstaller
python -m build                                                   # wheel + sdist -> dist/
pyinstaller --onefile --windowed --paths src --name bserial src/bserial/__main__.py
```

CI ([`.github/workflows/build.yml`](.github/workflows/build.yml:1)) builds this executable for Windows, macOS, and Linux on every push/PR to `main`.

## License

bserial is intended to be released under the MIT License (no `LICENSE` file is currently present in the repository).

## Contributing

If you find a bug or have an idea for a new feature, please open an issue on GitHub. Pull requests are also welcome!
