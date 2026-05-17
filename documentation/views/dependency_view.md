# dependency_view.py

Displays and manages all task predecessor relationships in the project.

## Class: `DependencyView`

Extends `QTableWidget`.

### Columns

| # | Header | Description |
| - | - | - |
| 0 | Task ID | ID of the successor task |
| 1 | Task Name | Name of the successor task |
| 2 | Predecessor ID | ID of the predecessor task |
| 3 | Predecessor Name | Name of the predecessor task |
| 4 | Link Type | Relation type: `FS`, `FF`, `SS`, or `SF` |
| 5 | Lag | Lag duration (e.g. `0.0d`) |

All cells are read-only in the grid; editing is done through the Dependency dialog.

### Signal

| Signal | Arguments | Description |
| - | - | - |
| `data_changed` | — | A dependency was added or deleted |

### Key Interactions

| Action | How to trigger |
| - | - |
| Open Dependency dialog | Double-click any row |
| Add dependency | Right-click → **Insert Dependency**, or `Insert` key, or Edit / toolbar |
| Delete dependency | Right-click → **Delete Dependency**, or `Delete` key, or Edit / toolbar |

### `load_project(project)`

Iterates over all tasks in the project via `project.getTasks()`.  For each task, it calls `getPredecessors()` and creates one table row per `Relation` object, storing a `(successor_task, Relation)` pair in `self._relations` for later editing.

## Relation Types

| Code | Meaning |
| - | - |
| `FINISH_START` (FS) | Successor starts after predecessor finishes (most common) |
| `FINISH_FINISH` (FF) | Successor finishes no earlier than predecessor finishes |
| `START_START` (SS) | Successor starts no earlier than predecessor starts |
| `START_FINISH` (SF) | Successor finishes no earlier than predecessor starts |
