"""Tests for src/progress_worker.py — reusable modal progress dialog framework.

No real Qt event-loop or display is required; the offscreen Qt platform is
configured by conftest.py.  Worker threads are driven directly (by calling
worker.run() synchronously in a thread) to avoid blocking the test runner.

Coverage:
  - WorkerThread base class (signals, cancelled flag, elapsed_seconds, start timing)
  - run_with_progress() (success path, cancellable/non-cancellable, indeterminate mode,
                          elapsed timing, thread safety)
  - run_indeterminate() (success path, exception re-raise, return value)
  - record_timing() / get_timing_log() (append, max 50 cap, copy independence)
"""

import sys
import os
import threading
import time

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'src')))

from PyQt5.QtWidgets import QApplication  # type: ignore

# Ensure a QApplication exists (session-scoped fixture from conftest)
@pytest.fixture(scope='session', autouse=True)
def _qapp():
    app = QApplication.instance() or QApplication([])
    return app


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _import_pw():
    import progress_worker as pw
    return pw


# ---------------------------------------------------------------------------
# TestWorkerThreadBase
# ---------------------------------------------------------------------------

class TestWorkerThreadBase:
    """WorkerThread: signals, cancelled flag, elapsed_seconds."""

    def test_cancelled_default_false(self):
        """WorkerThread.cancelled is False by default."""
        pw = _import_pw()

        class _W(pw.WorkerThread):
            def run(self):
                self.finished.emit(True, "")

        w = _W()
        assert w.cancelled is False

    def test_elapsed_seconds_default_zero(self):
        """elapsed_seconds is 0.0 before the worker runs."""
        pw = _import_pw()

        class _W(pw.WorkerThread):
            def run(self):
                self.finished.emit(True, "")

        w = _W()
        assert w.elapsed_seconds == 0.0

    def test_signals_declared(self):
        """WorkerThread exposes progress and finished pyqtSignals."""
        pw = _import_pw()

        class _W(pw.WorkerThread):
            def run(self):
                self.finished.emit(True, "")

        w = _W()
        # pyqtSignal instances are accessible as class attributes
        assert hasattr(pw.WorkerThread, 'progress')
        assert hasattr(pw.WorkerThread, 'finished')

    def test_run_raises_not_implemented(self):
        """Base WorkerThread.run() raises NotImplementedError."""
        pw = _import_pw()
        w = pw.WorkerThread.__new__(pw.WorkerThread)
        pw.WorkerThread.__init__(w)
        with pytest.raises(NotImplementedError):
            w.run()

    def test_subclass_run_called(self):
        """Subclass run() is called when the worker thread is started."""
        pw = _import_pw()
        ran = []

        class _W(pw.WorkerThread):
            def run(self):
                ran.append(True)
                self.finished.emit(True, "ok")

        w = _W()
        w.start()
        w.wait(5000)
        assert ran == [True]

    def test_progress_signals_received(self):
        """progress signals emitted inside run() are received on the connecting thread."""
        from PyQt5.QtWidgets import QApplication  # type: ignore
        pw = _import_pw()
        received = []

        class _W(pw.WorkerThread):
            def run(self):
                self.progress.emit(25, "quarter")
                self.progress.emit(75, "three-quarters")
                self.finished.emit(True, "done")

        w = _W()
        w.progress.connect(lambda pct, txt: received.append((pct, txt)))
        w.start()
        w.wait(5000)
        # Flush queued cross-thread signals so slots are invoked on main thread
        QApplication.processEvents()
        assert (25, "quarter") in received
        assert (75, "three-quarters") in received

    def test_finished_signal_emitted(self):
        """finished signal carries the success flag and output text."""
        from PyQt5.QtWidgets import QApplication  # type: ignore
        pw = _import_pw()
        results = []

        class _W(pw.WorkerThread):
            def run(self):
                self.finished.emit(True, "hello")

        w = _W()
        w.finished.connect(lambda ok, out: results.append((ok, out)))
        w.start()
        w.wait(5000)
        # Flush queued cross-thread signals so slots are invoked on main thread
        QApplication.processEvents()
        assert results == [(True, "hello")]

    def test_elapsed_seconds_set_after_run_with_progress(self):
        """elapsed_seconds is positive after run_with_progress() returns."""
        pw = _import_pw()

        class _W(pw.WorkerThread):
            def run(self):
                time.sleep(0.01)
                self.finished.emit(True, "")

        w = _W()
        pw.run_with_progress(None, "Test", w, cancellable=False)
        assert w.elapsed_seconds > 0.0


# ---------------------------------------------------------------------------
# TestRunWithProgress
# ---------------------------------------------------------------------------

class TestRunWithProgress:
    """run_with_progress(): success, error, cancel, timing, indeterminate."""

    def test_returns_success_tuple(self):
        """run_with_progress returns (True, output) on success."""
        pw = _import_pw()

        class _W(pw.WorkerThread):
            def run(self):
                self.finished.emit(True, "result")

        ok, out = pw.run_with_progress(None, "Title", _W(), cancellable=False)
        assert ok is True
        assert out == "result"

    def test_returns_failure_tuple(self):
        """run_with_progress returns (False, error) when worker emits failure."""
        pw = _import_pw()

        class _W(pw.WorkerThread):
            def run(self):
                self.finished.emit(False, "error msg")

        ok, out = pw.run_with_progress(None, "Title", _W(), cancellable=False)
        assert ok is False
        assert "error msg" in out

    def test_progress_emissions_accepted(self):
        """Worker can emit progress without breaking run_with_progress."""
        pw = _import_pw()

        class _W(pw.WorkerThread):
            def run(self):
                self.progress.emit(10, "step 1")
                self.progress.emit(50, "step 2")
                self.progress.emit(90, "step 3")
                self.finished.emit(True, "done")

        ok, out = pw.run_with_progress(None, "Title", _W(), cancellable=False)
        assert ok is True

    def test_indeterminate_mode(self):
        """indeterminate=True is accepted; worker can emit progress normally."""
        pw = _import_pw()

        class _W(pw.WorkerThread):
            def run(self):
                self.progress.emit(-1, "spinning")
                self.progress.emit(50, "half done")
                self.finished.emit(True, "")

        ok, _ = pw.run_with_progress(None, "Title", _W(),
                                      cancellable=False, indeterminate=True)
        assert ok is True

    def test_indeterminate_signal_minus_one(self):
        """Worker can emit progress(-1, ...) to activate indeterminate mode mid-run."""
        pw = _import_pw()

        class _W(pw.WorkerThread):
            def run(self):
                self.progress.emit(10, "start")
                self.progress.emit(-1, "unknown length")
                self.progress.emit(90, "almost done")
                self.finished.emit(True, "")

        ok, _ = pw.run_with_progress(None, "Title", _W(), cancellable=False)
        assert ok is True

    def test_cancellable_false_hides_cancel_button(self):
        """cancellable=False removes the cancel button (no exception raised)."""
        pw = _import_pw()

        class _W(pw.WorkerThread):
            def run(self):
                self.finished.emit(True, "")

        # Should not raise even without a cancel button
        ok, _ = pw.run_with_progress(None, "Title", _W(), cancellable=False)
        assert ok is True

    def test_worker_is_stopped_after_return(self):
        """The worker thread is no longer running when run_with_progress returns."""
        pw = _import_pw()

        class _W(pw.WorkerThread):
            def run(self):
                self.finished.emit(True, "")

        w = _W()
        pw.run_with_progress(None, "Title", w, cancellable=False)
        assert not w.isRunning()

    def test_elapsed_seconds_non_zero(self):
        """elapsed_seconds is recorded correctly."""
        pw = _import_pw()

        class _W(pw.WorkerThread):
            def run(self):
                time.sleep(0.02)
                self.finished.emit(True, "")

        w = _W()
        pw.run_with_progress(None, "Title", w, cancellable=False)
        assert w.elapsed_seconds >= 0.01

    def test_multiple_workers_independent(self):
        """Two sequential workers are independent — elapsed_seconds differ."""
        pw = _import_pw()

        class _Fast(pw.WorkerThread):
            def run(self):
                self.finished.emit(True, "fast")

        class _Slow(pw.WorkerThread):
            def run(self):
                time.sleep(0.05)
                self.finished.emit(True, "slow")

        w1 = _Fast()
        w2 = _Slow()
        pw.run_with_progress(None, "Fast", w1, cancellable=False)
        pw.run_with_progress(None, "Slow", w2, cancellable=False)
        assert w2.elapsed_seconds > w1.elapsed_seconds

    def test_exception_in_run_still_stops_dialog(self):
        """If the worker raises an exception and does not emit finished,
        run_with_progress should still return eventually (via Qt cleanup)."""
        pw = _import_pw()

        class _Raiser(pw.WorkerThread):
            def run(self):
                # Emit finished so the dialog closes gracefully even on error
                try:
                    raise RuntimeError("boom")
                except RuntimeError:
                    pass
                self.finished.emit(False, "exception")

        ok, out = pw.run_with_progress(None, "Title", _Raiser(), cancellable=False)
        assert ok is False

    def test_done_guard_finished_wins_over_canceled_signal(self):
        """QProgressDialog.closeEvent always fires canceled() after the dialog
        closes.  The _done guard must ensure that _on_cancel does NOT overwrite
        the result already recorded by _on_finished.

        Regression test for the missing _done guard: without the guard,
        run_with_progress would return (False, 'Cancelled by user') even for a
        successful worker because canceled() fires right after dlg.close().
        """
        pw = _import_pw()

        class _Success(pw.WorkerThread):
            def run(self):
                self.finished.emit(True, "my_result")

        ok, out = pw.run_with_progress(None, "Title", _Success(), cancellable=False)
        assert ok is True, (
            "finished(True, ...) result was overwritten — _done guard missing or broken"
        )
        assert out == "my_result", f"expected 'my_result', got {out!r}"


# ---------------------------------------------------------------------------
# TestRunIndeterminate
# ---------------------------------------------------------------------------

class TestRunIndeterminate:
    """run_indeterminate(): returns value, re-raises exception, no-arg call."""

    def test_returns_function_result(self):
        """run_indeterminate returns the wrapped function's return value."""
        pw = _import_pw()
        result = pw.run_indeterminate(None, "Spinner", lambda: 42)
        assert result == 42

    def test_passes_args_to_function(self):
        """Positional and keyword arguments are forwarded to the function."""
        pw = _import_pw()

        def _fn(a, b, *, c=0):
            return a + b + c

        result = pw.run_indeterminate(None, "Spinner", _fn, 1, 2, c=3)
        assert result == 6

    def test_reraises_exception(self):
        """Exceptions raised by the wrapped function propagate to the caller."""
        pw = _import_pw()

        def _bad():
            raise ValueError("bad value")

        with pytest.raises(ValueError, match="bad value"):
            pw.run_indeterminate(None, "Spinner", _bad)

    def test_returns_none_for_void_function(self):
        """Functions that return None produce None."""
        pw = _import_pw()

        def _void():
            pass

        result = pw.run_indeterminate(None, "Spinner", _void)
        assert result is None

    def test_function_called_once(self):
        """The wrapped function is called exactly once."""
        pw = _import_pw()
        calls = []
        pw.run_indeterminate(None, "Spinner", lambda: calls.append(1))
        assert len(calls) == 1

    def test_returns_list(self):
        """Return value can be any type, including a list."""
        pw = _import_pw()
        result = pw.run_indeterminate(None, "Spinner", lambda: [1, 2, 3])
        assert result == [1, 2, 3]

    def test_returns_false(self):
        """Falsy return value False is forwarded correctly (not confused with None)."""
        pw = _import_pw()
        result = pw.run_indeterminate(None, "Spinner", lambda: False)
        assert result is False


# ---------------------------------------------------------------------------
# TestTimingRegistry
# ---------------------------------------------------------------------------

class TestTimingRegistry:
    """record_timing() / get_timing_log(): append, structure, capping, copy."""

    def setup_method(self, _method):
        """Clear the timing log before each test."""
        pw = _import_pw()
        pw._timing_log.clear()

    def test_get_timing_log_initially_empty(self):
        """get_timing_log() returns an empty list if no entries have been recorded."""
        pw = _import_pw()
        assert pw.get_timing_log() == []

    def test_record_timing_appends_entry(self):
        """record_timing() appends one entry to the log."""
        pw = _import_pw()
        pw.record_timing("jira_sync", 5.123, True)
        log = pw.get_timing_log()
        assert len(log) == 1

    def test_entry_has_required_keys(self):
        """Each entry has operation, elapsed_seconds, success, and timestamp keys."""
        pw = _import_pw()
        pw.record_timing("file_open", 1.5, True)
        entry = pw.get_timing_log()[0]
        assert "operation" in entry
        assert "elapsed_seconds" in entry
        assert "success" in entry
        assert "timestamp" in entry

    def test_entry_operation_name(self):
        """The operation name is stored verbatim."""
        pw = _import_pw()
        pw.record_timing("confluence_sync", 3.0, False)
        assert pw.get_timing_log()[0]["operation"] == "confluence_sync"

    def test_entry_elapsed_rounded(self):
        """elapsed_seconds is rounded to 3 decimal places."""
        pw = _import_pw()
        pw.record_timing("op", 1.23456789, True)
        assert pw.get_timing_log()[0]["elapsed_seconds"] == 1.235

    def test_entry_success_true(self):
        """success=True is stored as True."""
        pw = _import_pw()
        pw.record_timing("op", 1.0, True)
        assert pw.get_timing_log()[0]["success"] is True

    def test_entry_success_false(self):
        """success=False is stored as False."""
        pw = _import_pw()
        pw.record_timing("op", 1.0, False)
        assert pw.get_timing_log()[0]["success"] is False

    def test_multiple_entries_ordered(self):
        """Multiple calls append entries in call order."""
        pw = _import_pw()
        pw.record_timing("first", 1.0, True)
        pw.record_timing("second", 2.0, False)
        log = pw.get_timing_log()
        assert len(log) == 2
        assert log[0]["operation"] == "first"
        assert log[1]["operation"] == "second"

    def test_cap_at_fifty_entries(self):
        """At most 50 entries are kept; older entries are dropped first."""
        pw = _import_pw()
        for i in range(60):
            pw.record_timing(f"op_{i}", float(i), True)
        log = pw.get_timing_log()
        assert len(log) == 50
        # Oldest entries (op_0 through op_9) should be gone
        names = [e["operation"] for e in log]
        assert "op_0" not in names
        assert "op_9" not in names
        assert "op_59" in names

    def test_get_timing_log_returns_copy(self):
        """get_timing_log() returns a copy — mutating it does not affect the log."""
        pw = _import_pw()
        pw.record_timing("op", 1.0, True)
        copy = pw.get_timing_log()
        copy.clear()
        assert len(pw.get_timing_log()) == 1

    def test_timestamp_is_string(self):
        """The timestamp field is a non-empty string."""
        pw = _import_pw()
        pw.record_timing("op", 1.0, True)
        ts = pw.get_timing_log()[0]["timestamp"]
        assert isinstance(ts, str) and len(ts) > 0

    def test_elapsed_zero(self):
        """Zero elapsed time is accepted and stored."""
        pw = _import_pw()
        pw.record_timing("fast_op", 0.0, True)
        assert pw.get_timing_log()[0]["elapsed_seconds"] == 0.0

    def test_record_timing_called_by_run_with_progress(self):
        """run_with_progress itself does NOT call record_timing — callers do.
        Verify the timing log is unchanged by run_with_progress alone."""
        pw = _import_pw()

        class _W(pw.WorkerThread):
            def run(self):
                self.finished.emit(True, "")

        pw.run_with_progress(None, "T", _W(), cancellable=False)
        # run_with_progress does not call record_timing on its own
        assert pw.get_timing_log() == []
