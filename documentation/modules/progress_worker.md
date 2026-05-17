# progress_worker.py

Reusable background-thread + modal-progress-dialog framework for all
long-running operations.  Every call blocks the caller (modal) while keeping
the UI event loop alive, so the window remains responsive (repaint, resize,
cancel clicks).


## WorkerThread

```python
class WorkerThread(QThread):
    progress  = pyqtSignal(int, str)   # value 0-100, status message
    finished  = pyqtSignal(bool, str)  # success, result / error message
```

| Attribute | Type | Description |
| - | - | - |
| `cancelled` | `bool` | Set to `True` by the framework when Cancel is clicked |
| `elapsed_seconds` | `float` | Wall-clock duration; available after `run()` returns |
| `_start_time` | `float` | `time.monotonic()` snapshot captured in `start()` |

Subclasses override `run()` and may emit `progress` at any time.  Raising
`NotImplementedError` in the base `run()` enforces the override contract.

### Cross-Thread Signal Delivery

Qt delivers signals across threads via the queued connection mechanism.
After calling `worker.wait()` in tests, `QApplication.processEvents()` must
be called once to flush any pending queued signals before asserting on results.


## run_with_progress

```python
def run_with_progress(
    parent: QWidget,
    title: str,
    worker: WorkerThread,
    *,
    cancellable: bool = True,
    indeterminate: bool = False,
    min_duration_ms: int = 0,
) -> tuple[bool, str]:
```

Opens a `QProgressDialog`, connects `worker.progress` → dialog value/label,
starts the worker, and runs a local `QEventLoop` until the worker finishes
or the user cancels.

### Parameters

| Parameter | Default | Description |
| - | - | - |
| `parent` | — | Parent widget for the dialog |
| `title` | — | Dialog window title |
| `worker` | — | Pre-configured `WorkerThread` subclass instance |
| `cancellable` | `True` | If `False` the Cancel button is hidden |
| `indeterminate` | `False` | If `True` sets range `0,0` for a pulsing bar |
| `min_duration_ms` | `0` | Minimum time before the dialog appears (milliseconds) |

### Return Value

`(success: bool, result_message: str)` — mirrors the `finished` signal payload.

### _done Guard

`QProgressDialog.closeEvent` always fires `canceled()` after the dialog
closes, even when it was closed programmatically after a successful finish.
Without a guard this would overwrite `_on_finished`'s `(True, result)` with
`(False, "Cancelled by user")`.

Both `_on_finished` and `_on_cancel` check and set a shared sentinel:

```python
_done: list = [False]   # mutable container so the closures share one reference

def _on_finished(success, msg):
    if _done[0]:
        return
    _done[0] = True
    _result[0] = (success, msg)
    loop.quit()

def _on_cancel():
    if _done[0]:
        return
    _done[0] = True
    worker.cancelled = True
    _result[0] = (False, "Cancelled by user")
    loop.quit()
```


## run_indeterminate

```python
def run_indeterminate(
    parent: QWidget,
    title: str,
    func: Callable,
    *args,
    **kwargs,
) -> Any:
```

Convenience wrapper for simple callables that do not need a custom
`WorkerThread` subclass.  Wraps `func(*args, **kwargs)` in an anonymous
worker, shows a pulsing indeterminate bar (non-cancellable), and returns the
callable's return value.  Any exception raised inside `func` propagates to
the caller.

### Usage Example

```python
project = run_indeterminate(self, "Opening project…", reader.read, file_path)
```


## Timing Registry

```python
def record_timing(operation: str, elapsed: float, success: bool) -> None: ...
def get_timing_log() -> list[dict]: ...
```

`record_timing` appends one entry to a module-level `collections.deque`
(capacity 50, oldest entries discarded):

```json
{
  "operation":       "Jira Sync",
  "elapsed_seconds": 4.231,
  "success":         true,
  "timestamp":       "2026-05-14T10:33:07"
}
```

`get_timing_log()` returns a plain list copy (caller-safe).

The timing log is included in the debug dump (`app_debug.dump_project_state`)
under the top-level key `long_running_timings`.

**Note:** `run_with_progress` and `run_indeterminate` do **not** call
`record_timing` automatically; callers in `ui.py` call it explicitly after
each operation so they can supply the meaningful operation name.


## Operations Using This Module

| Caller | Operation | Mode |
| - | - | - |
| `MainWindow.run_jira_sync` | Jira→Project Sync | determinate (`_JiraSyncWorker`) |
| `MainWindow.run_jira_push` | Project→Jira Push | `run_indeterminate` |
| `MainWindow.open_project_file` | File Open | `run_indeterminate` |
| `MainWindow.sync_confluence_calendar` | Confluence Calendar Sync | `run_indeterminate` |
| `MainWindow._vcs_operation` | VCS Commit / Pull / SVN Update | `VcsWorker` (existing QThread) |
| `MainWindow.save_project_file` | File Save | `run_indeterminate` |
| `MainWindow._export_*` | SVG / PlantUML Export | `run_indeterminate` |
| `ADSearchDialog._do_search` | Active Directory search | `run_indeterminate` |
