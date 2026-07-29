"""Canned ANSI escape sequences used for manual GUI smoke testing.

Shared between the in-app "ANSI Demo" button (`bserial.py`) and the
standalone `tools/ansi_smoke.py` script.
"""

ANSI_DEMO_LINES = [
    "Plain text, no escapes.",
    "\x1b[31mRed\x1b[0m \x1b[32mGreen\x1b[0m \x1b[33mYellow\x1b[0m "
    "\x1b[34mBlue\x1b[0m \x1b[35mMagenta\x1b[0m \x1b[36mCyan\x1b[0m "
    "\x1b[37mWhite\x1b[0m",
    "\x1b[91mBright Red\x1b[0m \x1b[92mBright Green\x1b[0m "
    "\x1b[93mBright Yellow\x1b[0m \x1b[94mBright Blue\x1b[0m "
    "\x1b[95mBright Magenta\x1b[0m \x1b[96mBright Cyan\x1b[0m "
    "\x1b[97mBright White\x1b[0m",
    "\x1b[1mBold\x1b[0m \x1b[4mUnderline\x1b[0m \x1b[7mReverse\x1b[0m "
    "\x1b[3mItalic\x1b[0m",
    "\x1b[41mRed BG\x1b[0m \x1b[42mGreen BG\x1b[0m \x1b[44mBlue BG\x1b[0m",
    "a\x1b[32mb\x1b[34mc\x1b[0md  (mid-line color switches)",
    "\x1b[38;5;208mOrange (256-color)\x1b[0m \x1b[48;5;27mBlue BG (256-color)\x1b[0m",
    "\x1b[38;2;255;105;180mHot Pink (truecolor)\x1b[0m",
    "\x1b[2Kthis CSI is not SGR and should be stripped, only this text remains",
    "\x1b[999mmalformed SGR ignored, plain text remains",
]
