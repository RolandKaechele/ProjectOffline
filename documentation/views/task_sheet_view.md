# task_sheet_view.py

Provides the standalone hierarchical **Task Sheet** view — an MS Project "Entry Table"–style spreadsheet with visual progress bars, predecessor enrichment, and collapse/expand support.  It is displayed on its own full-width tab (tab index 5) and is the **default view** shown on startup.

## Class: `TaskSheetView`

Extends `QTableWidget`.

### Columns

| # | Constant | Header | Width | Policy | Notes |
| - | - | - | - | - | - |
| 0 | `COL_ICON` | *(indicator)* | 36 px | Fixed | Status icons (critical, overdue, note, milestone) |
| 1 | `COL_NUM` | `#` | 46 px | Fixed | Task sequence number |
| 2 | `COL_NAME` | Task Name | 260 px | Interactive | Indented by outline level; collapse/expand triangle for summaries |
| 3 | `COL_DUR` | Duration | 80 px | Interactive | Duration string (e.g. `5.0d`) |
| 4 | `COL_PCT` | % Complete | 110 px | Interactive | Coloured progress bar with % text overlay |
| 5 | `COL_START` | Start | 100 px | Interactive | `YYYY-MM-DD` |
| 6 | `COL_END` | Finish | 100 px | Interactive | `YYYY-MM-DD` |
| 7 | `COL_RES` | Assigned To | 140 px | Interactive | Comma-separated resource names |
| 8 | `COL_PRED` | Predecessors | 220 px | Stretch | `"ID – Task Name"` entries joined with `,  ` |

### Signals

| Signal | Arguments | Description |
| - | - | - |
| `data_changed` | — | Emitted after the user edits a task via the Task Information dialog |
| `split_task_requested` | `task (object)` | Emitted when the user chooses **Split Task…** from the context menu on a non-summary, non-milestone task |
| `merge_task_requested` | `task (object)` | Emitted when the user chooses **Merge Task Segments**; only shown when `_has_splits_fn(task)` returns `True` |

> **`_has_splits_fn`** — optional callable injected by `ui.py`:
> `task_sheet_view._has_splits_fn = gantt_canvas.get_splits`.
> Returns splits for the task; truthy when splits exist.

### Internal State

| Attribute | Type | Description |
| - | - | - |
| `_collapsed` | `set[str]` | Task unique IDs (as strings) whose subtree is currently hidden |
| `_id_to_name` | `dict[int, str]` | Maps numeric task ID → task name; built in `load_project` for predecessor label enrichment |


## Loading Data

```python
task_sheet_view.load_project(project: ProjectFile)
```

1. Iterates all tasks via `_get_visible_tasks(project)` (imported from `gantt_view`).
2. Builds `_id_to_name` from all tasks before populating rows.
3. Determines critical tasks via `_compute_critical_ids(project)` (imported from `gantt_view`).
4. Skips tasks whose parent summary is in `_collapsed`.
5. Populates each row by calling `_fill_row(row, task, critical_ids)`.


## Row Population: `_fill_row`

| Column | Source |
| - | - |
| Icon (0) | `_make_combined_icon` / `_make_icon` from `task_view.py` |
| # (1) | `task.getID()` |
| Task Name (2) | `task.getName()` — with `Qt.UserRole`/`+1`/`+2`/`+3` metadata for delegate |
| Duration (3) | `task.getDuration()` |
| % Complete (4) | `task.getPercentageComplete()` — rendered by `_ProgressDelegate` |
| Start (5) | `task.getStart()` formatted |
| Finish (6) | `task.getFinish()` formatted |
| Assigned To (7) | Comma-separated resource names from `task.getResourceAssignments()` |
| Predecessors (8) | Each predecessor: `f"{pid} – {_id_to_name.get(pid, '')}"` joined with `,  ` |


## Delegates

### `_TaskNameDelegate`

Custom `QStyledItemDelegate` for the **Task Name** column (column 2).

- Reads outline level from `Qt.UserRole` and indents the cell by `outline_level × INDENT_PX_PER_LEVEL` pixels (constant imported from `task_view.py`).
- Renders summary tasks in **bold**.
- Draws a collapse/expand triangle (▶ / ▼) for summary tasks.
- Handles `editorEvent` mouse presses on the triangle area to call `TaskSheetView._toggle_collapse(task_id)`.

#### Data Roles on the Name Column Item

| Role | Type | Content |
| - | - | - |
| `Qt.DisplayRole` | `str` | Task name text |
| `Qt.UserRole` | `int` | Outline level |
| `Qt.UserRole + 1` | `bool` | `is_summary` |
| `Qt.UserRole + 2` | `str` | Task unique ID (as string) |
| `Qt.UserRole + 3` | `bool` | `is_collapsed` |

### `_ProgressDelegate`

Custom `QStyledItemDelegate` for the **% Complete** column (column 4).

- Reads the percentage text from `Qt.DisplayRole`, strips `%`, and converts to float.
- Draws a rounded progress bar with colour-coded fill:

| Range | Fill colour | Text colour |
| - | - | - |
| 0% | Empty track only | Dark |
| 1–49% | Light blue `#70A0D0` (partial) | Dark |
| 50–99% | Blue `#2B579A` (partial) | White |
| 100% | Green `#217346` (full) | White |
| > 100% | Red `#C0392B` (full-width) | White |

- Values above 100% are **not clamped** — the bar fills the full width and turns red to signal an over-budget task.
- Minimum hint width: 90 px.


## Collapse / Expand

`_toggle_collapse(task_id: str)` toggles membership of `task_id` in `_collapsed` and then calls `load_project` again with the currently stored project to re-render the table with hidden rows omitted.

All descendant tasks (any task whose outline path passes through the collapsed summary) are skipped during `load_project`.


## Double-Click → Task Information Dialog

`_on_double_click(row, col)` is connected to `cellDoubleClicked`.

1. Reads the task unique ID from column 2's `Qt.UserRole + 2`.
2. Finds the matching MPXJ task object.
3. Opens `TaskDialog` (from `dialogs.py`) modally.
4. If the user accepts, calls `dlg.apply_to_task()` to write changes back.
5. Emits `data_changed`.


## Predecessor Format

Predecessors are displayed as `"ID – Task Name"` entries, multiple predecessors joined with `,  ` (comma + two spaces).

**Example:** `6 – Component design,  3 – Requirements document`

The lookup table `_id_to_name` is rebuilt each time `load_project` is called.


## Dependencies

| Import | Purpose |
| - | - |
| `gantt_view._get_visible_tasks` | Ordered task iteration respecting WBS hierarchy |
| `gantt_view._compute_critical_ids` | Set of critical task unique IDs |
| `task_view._make_icon`, `_make_combined_icon` | Status icon pixmaps |
| `task_view.INDENT_PX_PER_LEVEL` | Per-level indentation constant |
| `dialogs.TaskDialog` | Full task editing dialog (General / Predecessors / Notes tabs) |
