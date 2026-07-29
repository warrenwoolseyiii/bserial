"""Regression test for the live-device ANSI escape corruption bug.

Root cause: read_serial() ran on a background thread and called
process_ansi_chunk() (which mutates the Tk Text widget) directly from
that thread. Tcl/Tk is single-threaded, so cross-thread widget mutation
could corrupt/drop the leading ESC byte of ANSI sequences, causing
literal 'e[0;33m'-style text to appear in the console instead of color.

The fix marshals decoded serial chunks from the background reader
thread onto the main thread via a `queue.Queue`, drained by
`_poll_serial_queue()` (scheduled with `root.after()`), so
`process_ansi_chunk()` and all Text-widget mutation only ever happen on
the main thread.

These tests require a live Tk display; they are skipped if Tk cannot
initialize (e.g. headless CI without a virtual display).
"""

import queue
import threading

import pytest

tk = pytest.importorskip("tkinter")

from bserial.bserial import SerialTerminalApp

USER_SAMPLE_RAW = (
    b"0:00:00:00.127347> \x1b[0;33mRB_APP: LBP_IND: null pointer or payload too short "
    b"(8 bytes, need 10) \xe2\x80\x94 skipping parse\n"
    b"\x1b[0m0:00:00:00.128039> [RBTEST] PASS Lbp_UnsupportedSrcAddrMode !ok\n"
    b"0:00:00:03.008468> \x1b[0;31mG3_MSG:      No HI_HWRESET_CNF, check PE/RTE images, "
    b"connection with ST8500 and if pass-through is active.\n"
    b"\x1b[0m0:00:00:03.009152> Going to sleep...\n"
)


def _make_app():
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no Tk display available")
    app = SerialTerminalApp(root)
    return root, app


def test_serial_queue_exists_and_drains_on_main_thread():
    """process_ansi_chunk() must not be reachable directly from a
    background thread's read loop; chunks must go through the
    thread-safe queue instead."""
    root, app = _make_app()
    try:
        assert isinstance(app._serial_queue, queue.Queue)

        chunk = USER_SAMPLE_RAW.decode(errors="ignore")

        # Simulate what read_serial() does on a background thread: only
        # push to the queue, never touch the widget directly.
        def reader_thread_body():
            app._serial_queue.put(chunk)

        t = threading.Thread(target=reader_thread_body)
        t.start()
        t.join(timeout=5)
        assert not t.is_alive()

        # Drain manually (main thread) as _poll_serial_queue() would via
        # root.after().
        while True:
            try:
                queued_chunk = app._serial_queue.get_nowait()
            except queue.Empty:
                break
            app.process_ansi_chunk(queued_chunk)

        app.output_text.config(state="normal")
        content = app.output_text.get("1.0", "end")
        app.output_text.config(state="disabled")

        assert "\x1b" not in content
        assert "e[0;33m" not in content
        assert "e[0m" not in content
        assert "e[0;31m" not in content
        assert "RB_APP" in content
        assert "G3_MSG" in content
        assert "Going to sleep" in content
    finally:
        root.destroy()


def test_read_serial_never_calls_process_ansi_chunk_directly(monkeypatch):
    """Guard against regressing back to calling process_ansi_chunk()
    straight from the background reader thread. Patches process_ansi_chunk
    to record the calling thread; asserts it is only ever invoked on the
    main thread even when read_serial() is driven from a worker thread."""
    root, app = _make_app()
    try:
        calls = []
        original = app.process_ansi_chunk

        def spy(chunk):
            calls.append(threading.current_thread())
            return original(chunk)

        monkeypatch.setattr(app, "process_ansi_chunk", spy)

        class FakeSerialPort:
            def __init__(self, data):
                self._data = data
                self._sent = False

            @property
            def in_waiting(self):
                return len(self._data) if not self._sent else 0

            def read(self, n):
                self._sent = True
                return self._data

        app.serial_port = FakeSerialPort(USER_SAMPLE_RAW)
        app.connected = True

        def run_once_then_stop():
            app.read_serial()
            app.connected = False

        reader = threading.Thread(target=run_once_then_stop)
        reader.start()
        reader.join(timeout=5)

        # Drive the queue drain on the main thread, exactly like
        # _poll_serial_queue() would via root.after().
        drained = 0
        try:
            while True:
                queued_chunk = app._serial_queue.get_nowait()
                app.process_ansi_chunk(queued_chunk)
                drained += 1
        except queue.Empty:
            pass

        assert drained >= 1
        # Every recorded process_ansi_chunk() invocation must be on the
        # main thread, never on the background reader thread.
        assert all(c is threading.main_thread() for c in calls)
    finally:
        root.destroy()
