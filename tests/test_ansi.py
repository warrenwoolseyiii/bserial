"""Tests for the GUI-free ANSI SGR parser (src/bserial/ansi.py)."""


from bserial.ansi import BRIGHT_COLORS, AnsiParser, SgrState


def spans_text(spans):
    return [s.text for s in spans]


def test_plain_text_passthrough():
    parser = AnsiParser()
    spans = parser.feed("hello world")
    assert len(spans) == 1
    assert spans[0].text == "hello world"
    assert spans[0].state == SgrState()


def test_reset_code():
    parser = AnsiParser()
    spans = parser.feed("\x1b[31mred\x1b[0mplain")
    assert spans_text(spans) == ["red", "plain"]
    assert spans[0].state.fg == "#cd0000"
    assert spans[1].state == SgrState()


def test_multi_color_single_line_mid_line_switch():
    parser = AnsiParser()
    spans = parser.feed("a\x1b[32mb\x1b[34mc")
    assert len(spans) == 3
    assert spans[0].text == "a"
    assert spans[0].state.fg is None
    assert spans[1].text == "b"
    assert spans[1].state.fg == "#00cd00"  # green
    assert spans[2].text == "c"
    assert spans[2].state.fg == "#0000ee"  # blue


def test_bright_color_maps_to_valid_hex():
    parser = AnsiParser()
    spans = parser.feed("\x1b[91mx")
    assert len(spans) == 1
    assert spans[0].state.fg == BRIGHT_COLORS[91]
    assert spans[0].state.fg.startswith("#")
    assert len(spans[0].state.fg) == 7


def test_state_persists_across_parse_calls():
    parser = AnsiParser()
    parser.feed("\x1b[35mmagenta text")
    spans = parser.feed(" continues")
    assert len(spans) == 1
    assert spans[0].text == " continues"
    assert spans[0].state.fg == "#cd00cd"


def test_state_resets_after_reset_code_across_calls():
    parser = AnsiParser()
    parser.feed("\x1b[31m")
    parser.feed("red text\x1b[0m")
    spans = parser.feed("plain again")
    assert spans[0].state == SgrState()


def test_escape_sequence_split_across_chunks():
    parser = AnsiParser()
    spans1 = parser.feed("\x1b[")
    assert spans1 == []  # buffered, no output yet
    spans2 = parser.feed("31mfoo")
    assert len(spans2) == 1
    assert spans2[0].text == "foo"
    assert spans2[0].state.fg == "#cd0000"


def test_escape_sequence_split_mid_params():
    parser = AnsiParser()
    spans1 = parser.feed("text\x1b[3")
    assert spans_text(spans1) == ["text"]
    assert spans1[0].state == SgrState()

    spans2 = parser.feed("1mmore")
    assert spans_text(spans2) == ["more"]
    assert spans2[0].state.fg == "#cd0000"


def test_256_color_foreground():
    parser = AnsiParser()
    spans = parser.feed("\x1b[38;5;208morange")
    assert len(spans) == 1
    assert spans[0].state.fg is not None
    assert spans[0].state.fg.startswith("#")


def test_256_color_background():
    parser = AnsiParser()
    spans = parser.feed("\x1b[48;5;27mblue_bg")
    assert spans[0].state.bg is not None
    assert spans[0].state.bg.startswith("#")


def test_truecolor_foreground():
    parser = AnsiParser()
    spans = parser.feed("\x1b[38;2;255;105;180mpink")
    assert spans[0].state.fg == "#ff69b4"


def test_truecolor_background():
    parser = AnsiParser()
    spans = parser.feed("\x1b[48;2;10;20;30mbg")
    assert spans[0].state.bg == "#0a141e"


def test_non_sgr_csi_stripped():
    parser = AnsiParser()
    spans = parser.feed("\x1b[2Kfoo")
    assert spans_text(spans) == ["foo"]


def test_malformed_sgr_ignored_no_exception():
    parser = AnsiParser()
    spans = parser.feed("\x1b[999mstill here")
    # No exception raised; text passes through with unmodified state
    assert "still here" in spans_text(spans)


def test_bold_underline_reverse_flags():
    parser = AnsiParser()
    spans = parser.feed("\x1b[1mbold\x1b[4munderline\x1b[7mreverse")
    assert spans[0].state.bold is True
    assert spans[1].state.bold is True
    assert spans[1].state.underline is True
    assert spans[2].state.reverse is True


def test_background_colors():
    parser = AnsiParser()
    spans = parser.feed("\x1b[41mred_bg\x1b[49mdefault_bg")
    assert spans[0].state.bg == "#cd0000"
    assert spans[1].state.bg is None


def test_reset_clears_all_flags():
    parser = AnsiParser()
    parser.feed("\x1b[1;4;7;31;41m")
    spans = parser.feed("styled\x1b[0mplain")
    assert spans[0].state.bold
    assert spans[0].state.underline
    assert spans[0].state.reverse
    assert spans[0].state.fg is not None
    assert spans[1].state == SgrState()


def test_empty_feed_returns_no_spans():
    parser = AnsiParser()
    spans = parser.feed("")
    assert spans == []


def test_tag_name_stable_and_distinct():
    s1 = SgrState(fg="#ff0000")
    s2 = SgrState(fg="#ff0000")
    s3 = SgrState(fg="#00ff00")
    assert s1.tag_name() == s2.tag_name()
    assert s1.tag_name() != s3.tag_name()


def test_reset_via_parser_reset_method():
    parser = AnsiParser()
    parser.feed("\x1b[31m")
    parser.reset()
    spans = parser.feed("plain")
    assert spans[0].state == SgrState()


def test_user_reported_sample_renders_colors_no_literal_escapes():
    """Regression test for the live-device ANSI bug report: real ESC
    (0x1B) bytes, decoded exactly as read_serial() would decode them
    (utf-8 with errors='ignore'), must produce styled spans with the
    escape sequences fully consumed -- not literal 'e[0;33m' text."""
    raw = (
        b"0:00:00:00.127347> \x1b[0;33mRB_APP: LBP_IND: null pointer or payload too short "
        b"(8 bytes, need 10) \xe2\x80\x94 skipping parse\n"
        b"\x1b[0m0:00:00:00.128039> [RBTEST] PASS Lbp_UnsupportedSrcAddrMode !ok\n"
        b"0:00:00:03.008468> \x1b[0;31mG3_MSG:      No HI_HWRESET_CNF, check PE/RTE images, "
        b"connection with ST8500 and if pass-through is active.\n"
        b"\x1b[0m0:00:00:03.009152> Going to sleep...\n"
    )
    chunk = raw.decode(errors="ignore")

    parser = AnsiParser()
    spans = parser.feed(chunk)

    full_text = "".join(s.text for s in spans)
    # No raw escape byte and no literal 'e[' artifact should remain anywhere.
    assert "\x1b" not in full_text
    assert "e[0;33m" not in full_text
    assert "e[0m" not in full_text
    assert "e[0;31m" not in full_text

    # The yellow warning line must be tagged with the standard yellow color.
    yellow_spans = [s for s in spans if s.state.fg == "#cdcd00"]
    assert yellow_spans, "expected at least one span colored yellow (#cdcd00)"
    assert any("RB_APP" in s.text for s in yellow_spans)

    # The red error line must be tagged with the standard red color.
    red_spans = [s for s in spans if s.state.fg == "#cd0000"]
    assert red_spans, "expected at least one span colored red (#cd0000)"
    assert any("G3_MSG" in s.text for s in red_spans)

    # Lines outside SGR sequences must be default (untagged) style.
    default_spans = [s for s in spans if s.state == SgrState()]
    assert any("PASS Lbp_UnsupportedSrcAddrMode" in s.text for s in default_spans)
    assert any("Going to sleep" in s.text for s in default_spans)


def test_literal_e_quirk_disabled_by_default_leaves_literal_e_text():
    """Root-cause regression: raw byte capture against the real device
    (raw_capture.log) proved the device NEVER sends a real ESC (0x1B)
    byte -- it sends the literal ASCII characters 'e' '[' (classic GNU
    '\\e' escape degraded by a toolchain that doesn't support it). With
    the quirk workaround off (the default), the parser must NOT invent
    escape handling for plain text and must pass 'e[0;33m' through
    literally with no color applied."""
    parser = AnsiParser()  # literal_e_quirk defaults to False
    chunk = (
        "0:00:00:00.127347> e[0;33mRB_APP: LBP_IND: null pointer or payload "
        "too short (8 bytes, need 10) \u2014 skipping parse\n\re[0m"
    )
    spans = parser.feed(chunk)
    full_text = "".join(s.text for s in spans)
    assert "e[0;33m" in full_text
    assert "e[0m" in full_text
    assert all(s.state == SgrState() for s in spans)


def test_literal_e_quirk_enabled_renders_colors_from_device_capture():
    """With the opt-in device-quirk workaround enabled, the exact literal
    byte sequence captured from the real device (raw_capture.log) must be
    interpreted as ANSI SGR codes: 'e[0;33m' -> yellow fg, 'e[0m' -> reset.
    This is the actual fix for the reported bug: the ANSI escapes were
    never garbled in transit/parsing -- the device firmware itself never
    sent a real ESC byte."""
    parser = AnsiParser(literal_e_quirk=True)
    chunk = (
        "0:00:00:00.127347> e[0;33mRB_APP: LBP_IND: null pointer or payload "
        "too short (8 bytes, need 10) \u2014 skipping parse\n\re[0m"
        "0:00:00:00.128039> [RBTEST] PASS Lbp_UnsupportedSrcAddrMode !ok\n"
    )
    spans = parser.feed(chunk)
    full_text = "".join(s.text for s in spans)

    assert "e[0;33m" not in full_text
    assert "e[0m" not in full_text

    yellow_spans = [s for s in spans if s.state.fg == "#cdcd00"]
    assert yellow_spans, "expected at least one span colored yellow (#cdcd00)"
    assert any("RB_APP" in s.text for s in yellow_spans)

    default_spans = [s for s in spans if s.state == SgrState()]
    assert any("PASS Lbp_UnsupportedSrcAddrMode" in s.text for s in default_spans)


def test_literal_e_quirk_split_across_chunks():
    """The device-quirk sequence can be split across two serial reads just
    like a real CSI sequence; the parser must buffer the incomplete tail
    the same way it does for '\\x1b['."""
    parser = AnsiParser(literal_e_quirk=True)
    spans1 = parser.feed("text e")
    assert "".join(s.text for s in spans1) == "text "  # 'e' held back, pending

    spans2 = parser.feed("[0;33mmore")
    assert "".join(s.text for s in spans2) == "mor"
    assert spans2[0].state.fg == "#cdcd00"
    # Trailing 'e' in "more" is itself a potential quirk-sequence start and
    # is buffered pending the next chunk -- a known trade-off of this
    # opt-in workaround (any word ending in 'e' triggers one-call latency).
    spans3 = parser.feed("")
    assert "".join(s.text for s in spans3) == ""
    parser.reset()
