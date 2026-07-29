"""Pure-logic tests for smart autoscroll (PLAN.md 4.x).

GUI scroll behavior itself requires a live Tk widget and is manual-verify
only; this covers the extracted `is_pinned` helper.
"""
from bserial.bserial import is_pinned


def test_is_pinned_exact_bottom():
    assert is_pinned(1.0) is True


def test_is_pinned_within_epsilon():
    assert is_pinned(0.9995, eps=1e-3) is True


def test_is_pinned_scrolled_up():
    assert is_pinned(0.5) is False


def test_is_pinned_just_outside_epsilon():
    assert is_pinned(0.998, eps=1e-3) is False


def test_is_pinned_empty_buffer_default():
    # An empty/short buffer yields yview() == (0.0, 1.0); pinned by default.
    assert is_pinned(1.0) is True


def test_is_pinned_custom_epsilon_wider_tolerance():
    assert is_pinned(0.95, eps=0.1) is True


def test_is_pinned_zero_epsilon_requires_exact():
    assert is_pinned(0.999999, eps=0.0) is False
    assert is_pinned(1.0, eps=0.0) is True
