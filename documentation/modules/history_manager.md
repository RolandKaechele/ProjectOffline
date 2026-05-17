# history_manager.py

Provides `HistoryManager`, the per-view undo/redo engine for the Project Offline.

Each of the five views (`tasks`, `resources`, `dependencies`, `baseline`, `team_planner`) has its own
independent snapshot stack.  A snapshot is the full project serialised as MSPDI XML bytes
so that every restore produces a perfectly consistent, standalone `ProjectFile` object.

## Design

### Stack Layout

```
stacks[view]['snaps'] : [s0, s1, s2, …]
stacks[view]['idx']   : index of the CURRENT state
```

- `s0` is the state recorded immediately after the file is opened (or a new project is created).
- `undo()` decrements `idx` and restores `snaps[idx]`.
- `redo()` increments `idx` and restores `snaps[idx]`.
- `push()` truncates `snaps[idx+1:]`, appends the new snapshot, and sets `idx = len − 1`.

### Why per-view stacks?

Task edits, resource edits, and dependency edits each affect a different part of the
project.  Keeping separate stacks means undoing a task-name change does not accidentally
roll back a resource addition made in the Resources tab.

### Snapshot format

Snapshots are raw MSPDI XML `bytes` produced by MPXJ's `MSPDIWriter` writing to a Java
`ByteArrayOutputStream` — no temporary files are written to disk.  Restoring a snapshot
reads those bytes with `UniversalProjectReader` from a Java `ByteArrayInputStream`, then
calls `logic.load_data()` with the reconstructed `ProjectFile`.

### Re-entrant protection

The `_restoring` flag is set to `True` while a restore is in progress.  Every `push()` call
is a no-op while restoring, which prevents the view-reload signals triggered by the restore
from creating spurious new history entries.

## Class: `HistoryManager`

```python
hm = HistoryManager(logic)
```

A single instance is created in `MainWindow.__init__` and stored as `self._history`.

### Constants

| Constant | Value | Description |
| - | - | - |
| `VIEWS` | `('tasks', 'resources', 'dependencies', 'baseline', 'team_planner')` | Supported view name literals |

### Constructor

```python
HistoryManager(logic: ProjectLogic)
```

Stores a reference to `logic` and initialises one empty stack dict per view.

### Public Methods

| Method | Signature | Returns | Description |
| - | - | - | - |
| `push` | `(view: str)` | — | Snapshot current state onto *view*'s stack; truncates redo branch.  No-op while restoring or when no project is open. |
| `push_all` | `()` | — | Snapshot into ALL view stacks and reset each to a single entry.  Call after file load, new project, or import so that history from a previous session never leaks into the new one. |
| `undo` | `(view: str)` | `bool` | Step back one state on *view*'s stack.  Returns `True` if a step was taken, `False` if already at the initial state (`idx == 0`). |
| `redo` | `(view: str)` | `bool` | Step forward one state on *view*'s stack.  Returns `True` if a step was taken, `False` if already at the most recent state. |
| `can_undo` | `(view: str)` | `bool` | `True` when `idx > 0` for *view*. |
| `can_redo` | `(view: str)` | `bool` | `True` when `idx < len(snaps) − 1` for *view*. |
| `depth` | `(view: str)` | `(int, int)` | `(undo_steps, redo_steps)` — useful for diagnostics and future UI indicators. |

### Internal Methods

| Method | Signature | Returns | Description |
| - | - | - | - |
| `_serialize` | `()` | `bytes \| None` | Serialise current `ProjectFile` to MSPDI XML bytes via `MSPDIWriter` + `ByteArrayOutputStream`.  Returns `None` when no project is loaded or on serialisation error. |
| `_restore` | `(data: bytes)` | — | Deserialise *data* via `UniversalProjectReader` + `ByteArrayInputStream` and replace the live project in `logic` with the restored `ProjectFile`. |

## Integration with `MainWindow`

`MainWindow` (in `ui.py`) holds `self._history = HistoryManager(logic)` and pushes
snapshots after every mutating operation:

| Operation | View stacks pushed |
| - | - |
| Task field edited (`_on_task_data_changed`) | `tasks`, `baseline` |
| Task row drag-reordered (`_on_task_reordered`) | `tasks`, `baseline` |
| Gantt bar dragged (`_on_gantt_task_moved`) | `tasks`, `baseline` |
| Task edited via dialog, task split, or task merge (`_on_gantt_task_edited`) | `tasks`, `baseline` |
| Resource added / deleted (`_on_resource_data_changed`) | `resources` |
| Dependency added / deleted (`_on_dependency_data_changed`) | `dependencies` |
| File opened / new project / PlantUML import | All views (`push_all`) |

### Keyboard Shortcuts

| Shortcut | Action |
| - | - |
| `Ctrl+Z` | Undo the last action on the **currently active tab's** stack, then refresh all views |
| `Ctrl+Y` | Redo the next action on the **currently active tab's** stack, then refresh all views |

The active tab maps to a history view as follows:

| Tab index | Tab name | History view |
| - | - | - |
| 0 | Gantt Chart | `tasks` |
| 1 | Resources | `resources` |
| 2 | Dependencies | `dependencies` |
| 3 | Baseline | `baseline` |
