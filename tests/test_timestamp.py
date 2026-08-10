"""Unit tests for the OS timestamp prefix feature (chunk-safe, per-line)."""
import re

from bserial.bserial import SerialTerminalApp


class _Stub:
    _timestamp_str = SerialTerminalApp._timestamp_str
    _prefix_lines = SerialTerminalApp._prefix_lines


def test_timestamp_str_format():
    ts = _Stub()._timestamp_str()
    assert re.fullmatch(r"\[\d{2}:\d{2}:\d{2}:\d{3}\] ", ts)


def test_prefix_lines_single_complete_line():
    out, pending = _Stub()._prefix_lines("hello\n", True)
    assert re.match(r"\[\d{2}:\d{2}:\d{2}:\d{3}\] hello\n", out)
    assert pending is True


def test_prefix_lines_no_prefix_when_not_pending():
    out, pending = _Stub()._prefix_lines("hello\n", False)
    assert out == "hello\n"
    assert pending is True


def test_prefix_lines_multi_line_chunk():
    out, pending = _Stub()._prefix_lines("a\nb\nc", True)
    lines = out.splitlines(keepends=True)
    assert len(lines) == 3
    assert lines[0].endswith("a\n") and lines[0].startswith("[")
    assert lines[1].endswith("b\n") and lines[1].startswith("[")
    assert lines[2].endswith("c") and lines[2].startswith("[")  # new line start, stamped
    assert pending is False


def test_prefix_lines_chunked_across_calls():
    # Simulate a line split across two serial reads: only stamped once.
    stub = _Stub()
    out1, pending = stub._prefix_lines("partial", True)
    assert out1.startswith("[") and out1.endswith("partial")
    assert pending is False

    out2, pending = stub._prefix_lines(" line\n", pending)
    assert out2 == " line\n"  # continuation of same line, no new prefix
    assert pending is True

    out3, pending = stub._prefix_lines("next\n", pending)
    assert out3.startswith("[") and out3.endswith("next\n")
    assert pending is True
