"""GUI-free ANSI SGR (CSI ... m) parser.

Parses text containing ANSI escape sequences into styled spans, carrying
style state persistently across chunks/lines. Non-SGR CSI/escape sequences
are stripped rather than left in the output. Incomplete escape sequences
split across reads are buffered and completed on the next call.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

# Matches a full CSI sequence: ESC [ params intermediate final
# final byte range 0x40-0x7E ('@'-'~')
_CSI_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")

# Matches a *possibly incomplete* CSI sequence at the end of a string:
# ESC, or ESC [, or ESC [ ...params/intermediates... (no final byte yet)
_PARTIAL_CSI_TAIL_RE = re.compile(r"\x1B(\[[0-?]*[ -/]*)?$")

# --- Optional device-quirk compatibility mode -----------------------------
# Some embedded firmware is built with a C source that uses the GNU-only
# '\e' escape (e.g. printf("\e[0;33m...")). Toolchains that don't support
# that non-standard extension silently emit the literal two characters
# 'e' '[' instead of the real ESC (0x1B) byte. This was confirmed via raw
# byte capture against a real device: raw_capture.log never contained a
# 0x1B byte, only literal ASCII "e[0;33m" / "e[0m" text (see PLAN.md /
# debug session notes). This is OFF by default because 'e[' can
# legitimately appear in normal text (e.g. "the[re]"); it is opt-in so it
# never corrupts output from well-behaved devices/other firmware.
_QUIRK_CSI_RE = re.compile(r"e\[[0-?]*[ -/]*[@-~]")
_QUIRK_PARTIAL_CSI_TAIL_RE = re.compile(r"e(\[[0-?]*[ -/]*)?$")

# The 16 standard/bright ANSI colors as hex (xterm-ish palette).
STANDARD_COLORS = {
    30: "#000000",  # black
    31: "#cd0000",  # red
    32: "#00cd00",  # green
    33: "#cdcd00",  # yellow
    34: "#0000ee",  # blue
    35: "#cd00cd",  # magenta
    36: "#00cdcd",  # cyan
    37: "#e5e5e5",  # white
}

BRIGHT_COLORS = {
    90: "#7f7f7f",  # bright black (gray)
    91: "#ff5555",  # bright red
    92: "#55ff55",  # bright green
    93: "#ffff55",  # bright yellow
    94: "#5555ff",  # bright blue
    95: "#ff55ff",  # bright magenta
    96: "#55ffff",  # bright cyan
    97: "#ffffff",  # bright white
}

# xterm 256-color palette (16 base + 216 cube + 24 grayscale ramp).
_XTERM_256_BASE = [
    "#000000", "#cd0000", "#00cd00", "#cdcd00", "#0000ee", "#cd00cd",
    "#00cdcd", "#e5e5e5", "#7f7f7f", "#ff5555", "#55ff55", "#ffff55",
    "#5555ff", "#ff55ff", "#55ffff", "#ffffff",
]

_CUBE_STEPS = [0, 95, 135, 175, 215, 255]


def _xterm_256_color(n: int) -> str:
    """Convert an xterm 256-color index to a hex color string."""
    if n < 0:
        n = 0
    if n < 16:
        return _XTERM_256_BASE[n]
    if n < 232:
        n -= 16
        r = _CUBE_STEPS[(n // 36) % 6]
        g = _CUBE_STEPS[(n // 6) % 6]
        b = _CUBE_STEPS[n % 6]
        return f"#{r:02x}{g:02x}{b:02x}"
    if n < 256:
        level = 8 + (n - 232) * 10
        level = max(0, min(255, level))
        return f"#{level:02x}{level:02x}{level:02x}"
    return "#ffffff"


@dataclass(frozen=True)
class SgrState:
    """Immutable SGR style state."""

    fg: str | None = None       # hex color string or None (default)
    bg: str | None = None       # hex color string or None (default)
    bold: bool = False
    dim: bool = False
    italic: bool = False
    underline: bool = False
    reverse: bool = False

    def tag_name(self) -> str:
        """Stable tag identifier derived from this state, for widget tag caching."""
        fg = self.fg.lstrip("#") if self.fg else "d"
        bg = self.bg.lstrip("#") if self.bg else "d"
        flags = "".join(
            f"{name}{int(getattr(self, name))}"
            for name in ("bold", "dim", "italic", "underline", "reverse")
        )
        return f"sgr_fg{fg}_bg{bg}_{flags}"

    def is_default(self) -> bool:
        return self == SgrState()


@dataclass(frozen=True)
class Span:
    """A run of text sharing a single SGR style state."""

    text: str
    state: SgrState


def _apply_sgr_params(state: SgrState, params: list[int]) -> SgrState:
    """Apply a list of SGR numeric parameters to a state, returning a new state."""
    if not params:
        params = [0]

    i = 0
    n = len(params)
    while i < n:
        code = params[i]

        if code == 0:
            state = SgrState()
        elif code == 1:
            state = replace(state, bold=True)
        elif code == 2:
            state = replace(state, dim=True)
        elif code == 3:
            state = replace(state, italic=True)
        elif code == 4:
            state = replace(state, underline=True)
        elif code == 7:
            state = replace(state, reverse=True)
        elif code == 21 or code == 22:
            state = replace(state, bold=False, dim=False)
        elif code == 23:
            state = replace(state, italic=False)
        elif code == 24:
            state = replace(state, underline=False)
        elif code == 27:
            state = replace(state, reverse=False)
        elif 30 <= code <= 37:
            state = replace(state, fg=STANDARD_COLORS[code])
        elif code == 38:
            # extended fg: 38;5;n or 38;2;r;g;b
            if i + 1 < n and params[i + 1] == 5 and i + 2 < n:
                state = replace(state, fg=_xterm_256_color(params[i + 2]))
                i += 2
            elif i + 1 < n and params[i + 1] == 2 and i + 4 < n:
                r, g, b = params[i + 2], params[i + 3], params[i + 4]
                r = max(0, min(255, r))
                g = max(0, min(255, g))
                b = max(0, min(255, b))
                state = replace(state, fg=f"#{r:02x}{g:02x}{b:02x}")
                i += 4
            # malformed -> ignore silently
        elif code == 39:
            state = replace(state, fg=None)
        elif 40 <= code <= 47:
            state = replace(state, bg=STANDARD_COLORS[code - 10])
        elif code == 48:
            if i + 1 < n and params[i + 1] == 5 and i + 2 < n:
                state = replace(state, bg=_xterm_256_color(params[i + 2]))
                i += 2
            elif i + 1 < n and params[i + 1] == 2 and i + 4 < n:
                r, g, b = params[i + 2], params[i + 3], params[i + 4]
                r = max(0, min(255, r))
                g = max(0, min(255, g))
                b = max(0, min(255, b))
                state = replace(state, bg=f"#{r:02x}{g:02x}{b:02x}")
                i += 4
        elif code == 49:
            state = replace(state, bg=None)
        elif 90 <= code <= 97:
            state = replace(state, fg=BRIGHT_COLORS[code])
        elif 100 <= code <= 107:
            state = replace(state, bg=BRIGHT_COLORS[code - 10])
        # unknown codes are silently ignored

        i += 1

    return state


class AnsiParser:
    """Stateful ANSI SGR parser.

    Feed text via ``feed()``; state (colors, bold, etc.) persists across
    calls, and incomplete escape sequences at the end of a chunk are
    buffered until more data arrives.
    """

    def __init__(self, literal_e_quirk: bool = False) -> None:
        """
        literal_e_quirk: opt-in workaround for firmware that was built with
        a C source using the GNU-only '\\e' escape and a toolchain that
        doesn't support it, causing the device to send the literal
        characters 'e' '[' instead of a real ESC (0x1B) byte. Confirmed via
        raw byte capture against a real device (see PLAN.md / debug notes).
        Off by default since 'e[' can appear in legitimate text.
        """
        self.state = SgrState()
        self._pending = ""
        self.literal_e_quirk = literal_e_quirk

    def reset(self) -> None:
        """Reset style state and any buffered partial escape sequence."""
        self.state = SgrState()
        self._pending = ""

    def feed(self, text: str) -> list[Span]:
        """Parse a chunk of text, returning a list of styled Spans.

        Style state and any incomplete trailing escape sequence carry over
        to the next call.
        """
        data = self._pending + text
        self._pending = ""

        csi_re = _CSI_RE
        partial_tail_re = _PARTIAL_CSI_TAIL_RE
        if self.literal_e_quirk:
            csi_re = _QUIRK_CSI_RE
            partial_tail_re = _QUIRK_PARTIAL_CSI_TAIL_RE

        # Hold back an incomplete escape sequence at the very end of data.
        partial_match = partial_tail_re.search(data)
        if partial_match:
            self._pending = data[partial_match.start():]
            data = data[: partial_match.start()]

        spans: list[Span] = []
        pos = 0
        for match in csi_re.finditer(data):
            if match.start() > pos:
                literal = data[pos:match.start()]
                if literal:
                    spans.append(Span(literal, self.state))

            seq = match.group(0)
            if seq.endswith("m"):
                param_str = seq[2:-1]  # strip ESC [ ... m
                if param_str == "":
                    params = [0]
                else:
                    try:
                        params = [int(p) if p else 0 for p in param_str.split(";")]
                    except ValueError:
                        params = []
                if params:
                    self.state = _apply_sgr_params(self.state, params)
                # else: malformed, ignore
            # any other CSI final byte -> stripped, no state change

            pos = match.end()

        if pos < len(data):
            literal = data[pos:]
            if literal:
                spans.append(Span(literal, self.state))

        return spans
