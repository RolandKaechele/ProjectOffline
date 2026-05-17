# progress_worker.py - Reusable modal progress dialog + background worker base.
#
# Usage:
#   from progress_worker import WorkerThread, run_with_progress
#
#   class MyWorker(WorkerThread):
#       def run(self):
#           self.progress.emit(10, "Starting…")
#           # ... do work, checking self.cancelled periodically ...
#           self.progress.emit(100, "Done")
#           self.finished.emit(True, "result text")
#
#   ok, output = run_with_progress(parent_widget, "My Operation", MyWorker())
#
# Cancellation:
#   Workers that support cancellation should check ``self.cancelled`` at each
#   safe checkpoint.  Emit ``finished(False, "Cancelled")`` and return when set.
#
# Indeterminate mode:
#   Pass ``indeterminate=True`` to ``run_with_progress()`` or emit
#   ``progress(-1, text)`` from the worker to switch to indeterminate mode.
#   Emit a non-negative percentage to switch back to determinate mode.
#
# Non-cancellable operations:
#   Pass ``cancellable=False`` — the Cancel button is hidden/disabled.

import time
from typing import Optional

from PyQt5.QtCore import Qt, QThread, pyqtSignal  # type: ignore
from PyQt5.QtWidgets import QProgressDialog, QApplication     # type: ignore


class WorkerThread(QThread):
    """Base class for background worker threads used with :func:`run_with_progress`.

    Sub-classes override :meth:`run` and must:
      * Emit ``progress(percent, status_text)`` at meaningful checkpoints.
        Use *percent* = -1 to activate the indeterminate bar.
      * Emit ``finished(success, output_or_error_text)`` exactly once before
        returning from :meth:`run`.
      * Check ``self.cancelled`` before each major step and bail out early
        when it is set (emit ``finished(False, "Cancelled")``).

    Timing:
      * ``elapsed_seconds`` is populated automatically after :meth:`run`
        returns.  It does *not* include time spent in the modal dialog itself
        (e.g. waiting for the user to click Cancel).
    """

    # percent 0-100 (or -1 for indeterminate), status text
    progress  = pyqtSignal(int, str)
    # success flag, summary / error message
    finished  = pyqtSignal(bool, str)

    def __init__(self):
        super().__init__()
        self.cancelled: bool = False
        self.elapsed_seconds: float = 0.0
        self._start_time: Optional[float] = None

    # ------------------------------------------------------------------
    # Internal timing wrapper — do NOT override this.
    # ------------------------------------------------------------------
    def start(self, priority=QThread.InheritPriority):
        self._start_time = time.monotonic()
        super().start(priority)

    # Override QThread.run() to wrap with timing.
    # Sub-classes should override _run() instead, or override run() directly
    # (in which case they are responsible for calling super().run() if they
    # want the elapsed_seconds tracking to work — but it is simpler to just
    # let the framework track it via the finished signal connection set up by
    # run_with_progress).
    def run(self):
        raise NotImplementedError("WorkerThread subclasses must implement run()")


# ---------------------------------------------------------------------------
# Helper: run a WorkerThread with a modal progress dialog
# ---------------------------------------------------------------------------

def run_with_progress(
    parent,
    title: str,
    worker: WorkerThread,
    *,
    cancellable: bool = True,
    indeterminate: bool = False,
    min_duration_ms: int = 400,
) -> tuple:
    """Run *worker* in a background thread while showing a modal progress dialog.

    Parameters
    ----------
    parent:
        Parent QWidget for the dialog.
    title:
        Window / label title shown in the progress dialog.
    worker:
        :class:`WorkerThread` instance (not yet started).
    cancellable:
        If *False* the Cancel button is hidden.
    indeterminate:
        Start in indeterminate (bouncing) mode.  The worker can switch to
        determinate by emitting ``progress(0..100, text)``.
    min_duration_ms:
        The dialog is only shown if the worker is still running after this
        many milliseconds (default 400 ms, same as QProgressDialog default).

    Returns
    -------
    tuple[bool, str]
        ``(success, output)`` forwarded from ``worker.finished``.
    """

    max_val = 0 if indeterminate else 100

    cancel_label = "Cancel" if cancellable else ""
    dlg = QProgressDialog(title, cancel_label, 0, max_val, parent)
    dlg.setWindowTitle(title)
    dlg.setWindowModality(Qt.WindowModal)
    dlg.setMinimumDuration(min_duration_ms)
    dlg.setAutoClose(False)
    dlg.setAutoReset(False)
    dlg.setMinimumWidth(420)

    if not cancellable:
        dlg.setCancelButton(None)

    result: list = [False, ""]
    # Guard flag — QProgressDialog.closeEvent always emits canceled(), so
    # whichever of _on_finished / _on_cancel executes first wins and the
    # second call becomes a no-op.
    _done: list = [False]

    def _on_progress(pct: int, text: str):
        if pct < 0:
            # Switch to indeterminate
            dlg.setMaximum(0)
        else:
            if dlg.maximum() == 0:
                dlg.setMaximum(100)
            dlg.setValue(pct)
        dlg.setLabelText(text)
        QApplication.processEvents()

    def _on_finished(ok: bool, out: str):
        if _done[0]:
            return
        _done[0] = True
        # Record elapsed time on the worker object
        if worker._start_time is not None:
            worker.elapsed_seconds = time.monotonic() - worker._start_time
        result[0], result[1] = ok, out
        if dlg.maximum() == 0:
            dlg.setMaximum(100)
        dlg.setValue(100)
        # Close the dialog — this causes dlg.exec_() to return.
        # Note: QProgressDialog.closeEvent emits canceled(); the _done guard
        # above prevents _on_cancel from overwriting our result.
        dlg.close()

    def _on_cancel():
        if _done[0]:
            return
        _done[0] = True
        worker.cancelled = True
        # Give the worker a chance to exit cleanly before terminating
        if not worker.wait(3000):
            worker.terminate()
            worker.wait(1000)
        result[0], result[1] = False, "Cancelled by user"
        dlg.close()

    worker.progress.connect(_on_progress)
    worker.finished.connect(_on_finished)
    dlg.canceled.connect(_on_cancel)

    worker.start()
    dlg.exec_()  # Returns when dlg.close() is called from _on_finished or _on_cancel

    # Safety: ensure the worker has stopped before returning
    if worker.isRunning():
        worker.cancelled = True
        worker.wait(2000)

    return result[0], result[1]


# ---------------------------------------------------------------------------
# Convenience: simple indeterminate spinner for non-threaded steps
# ---------------------------------------------------------------------------

def run_indeterminate(parent, title: str, func, *args, **kwargs):
    """Run *func(*args, **kwargs)* on the main thread while showing an
    indeterminate progress dialog.

    This is a fallback for operations that cannot easily be moved to a thread
    (e.g. JPype/JVM calls that may not be thread-safe).  It calls
    ``QApplication.processEvents()`` to keep the UI alive during the operation.

    Returns the function's return value.  Any exception raised by *func* is
    re-raised after closing the dialog.
    """
    dlg = QProgressDialog(title, "", 0, 0, parent)
    dlg.setWindowTitle(title)
    dlg.setWindowModality(Qt.WindowModal)
    dlg.setMinimumDuration(400)
    dlg.setAutoClose(True)
    dlg.setAutoReset(True)
    dlg.setCancelButton(None)
    dlg.setMinimumWidth(380)
    dlg.show()
    QApplication.processEvents()

    exc_holder: list = []
    result_holder: list = []
    try:
        result_holder.append(func(*args, **kwargs))
    except Exception as exc:  # noqa: BLE001
        exc_holder.append(exc)
    finally:
        dlg.close()

    if exc_holder:
        raise exc_holder[0]
    return result_holder[0] if result_holder else None


# ---------------------------------------------------------------------------
# Timing registry — used by app_debug.py to report elapsed times
# ---------------------------------------------------------------------------

_timing_log: list[dict] = []


def record_timing(operation: str, elapsed: float, success: bool) -> None:
    """Record the elapsed time for a long-running operation.

    Called automatically by the workers that use ``run_with_progress()``, but
    can also be called manually for non-worker operations that wrap
    ``run_indeterminate()``.
    """
    _timing_log.append({
        "operation": operation,
        "elapsed_seconds": round(elapsed, 3),
        "success": success,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    })
    # Keep only the last 50 entries to avoid unbounded growth
    if len(_timing_log) > 50:
        del _timing_log[:-50]


def get_timing_log() -> list[dict]:
    """Return a copy of the timing log (most recent entries last)."""
    return list(_timing_log)
