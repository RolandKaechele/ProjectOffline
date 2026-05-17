# gantt_view.py

Renders the Gantt chart panel — the right-hand side of the Gantt Chart tab.

## Layout Constants

| Constant | Default | Description |
| - | - | - |
| `ROW_HEIGHT` | 36 px | Height of each task row |
| `DAY_WIDTH_DEF` | 22 px | Default pixel width of one calendar day |
| `DAY_WIDTH_MIN` | 4 px | Minimum zoom level |
| `DAY_WIDTH_MAX` | 80 px | Maximum zoom level |
| `HEADER_MONTH_H` | 22 px | Height of the top (month) calendar row |
| `HEADER_WEEK_H` | 20 px | Height of the bottom (day-numbers) calendar row |
| `HEADER_HEIGHT` | 42 px | `HEADER_MONTH_H + HEADER_WEEK_H` |
| `NAV_BAR_HEIGHT` | 24 px | Navigation buttons bar above the calendar header |
| `BASELINE_THICK` | 3 px | Thickness of the baseline strip drawn below each task bar |

## Class: `GanttView`

`GanttView` is a `QWidget` that hosts a navigation bar, a fixed `GanttHeader`, and a scrollable `GanttCanvas`.

### Signals

| Signal | Arguments | Description |
| - | - | - |
| `zoom_changed` | `int` — new day width | Emitted after `set_day_width()` changes the zoom (forwarded from canvas) |
| `task_moved` | `task (object), delta_days (int)` | Emitted when the user drag-moves a task bar (forwarded from canvas) |
| `task_edited` | — | Emitted after a task is edited via the Task Information dialog (forwarded from canvas) |

### Public Methods

| Method | Description |
| - | - |
| `load_project(project, recompute_critical=False)` | Load an MPXJ `ProjectFile` and repaint; auto-scrolls to today |
| `set_day_width(px)` | Set zoom level (clamps to `DAY_WIDTH_MIN`…`DAY_WIDTH_MAX`) |
| `zoom_in()` | Increase day width by 4 px |
| `zoom_out()` | Decrease day width by 4 px |
| `set_show_resource_units(show)` | Toggle resource unit % labels on task bars |
| `set_show_sundays(show)` | Show or hide Sunday columns |
| `set_zero_float_critical(value)` | When `True`, tasks with zero total float are marked critical |
| `set_collapsed_ids(ids)` | Pass the set of collapsed summary task IDs to the canvas |
| `scroll_to_date(qdate, margin_days=7)` | Scroll horizontally so `qdate` is visible. **Day mode**: scrolls to `qdate − margin_days` calendar days. **Hourly mode**: `margin_days` is ignored; instead lands 2 hour-slot widths before `qdate` (or at the exact position when `margin_days=0`, used by zoom-preserve calls). |
| `verticalScrollBar()` | Return the canvas scroll area's vertical scrollbar for external sync |

### Navigation Bar

A thin bar (`NAV_BAR_HEIGHT = 24 px`) above the calendar header with three buttons:

| Button | Action |
| - | - |
| ◀◀ First | Scroll to 1 week before the first task's start |
| ◀ Today | Scroll to 1 week before today |
| Last ▶▶ | Scroll to 1 week before the last task's finish |


## Class: `GanttHeader`

Fixed two-row calendar header (`QWidget`) that scrolls horizontally in sync with the canvas but never scrolls vertically.

### `configure(project_start, total_days, day_width, show_sundays=True, non_working_dates=None)`

Reconfigures the header and resizes the widget.  Called by `GanttView._sync_header()` after every load or zoom change.

### Rendering

`paintEvent` draws:

1. **Month band** (top row) — alternating light/dark blue bands; month name label where there is enough space (`"MMM yyyy"` when ≥ 64 px wide, otherwise `"MMM"`).
2. **Day numbers** (bottom row) — Saturdays and public holidays in light grey; Sundays in blue-tint; Mondays with a slight highlight; other days in the default background.  When `day_width < 14` only week numbers (`"Wnn"`) are shown on Mondays.
3. **Today indicator** — bold green vertical line with a downward-pointing triangle at the bottom of the header.


## Class: `GanttCanvas`

The actual drawing widget (`QWidget`) inside `GanttView`.

### Signals

| Signal | Arguments | Description |
| - | - | - |
| `task_moved` | `task (object), delta_days (int)` | Emitted on mouse-release after dragging a bar |
| `zoom_changed` | `int` — new day width | Emitted after every zoom change |
| `task_edited` | — | Emitted when the Task Information dialog commits changes |

### Key Attributes

| Attribute | Type | Default | Description |
| - | - | - | - |
| `show_sundays` | `bool` | `True` | When `False`, Sunday columns are collapsed out of the timeline |
| `show_resource_units` | `bool` | `False` | When `True`, resource labels include `[units%]` |
| `_zero_float_critical` | `bool` | `False` | When `True`, zero-float tasks are coloured critical |
| `_critical_ids` | `set[int]` | `set()` | Int task IDs currently on the critical path |
| `_collapsed_ids` | `set` | `set()` | IDs of collapsed summary tasks |
| `_non_working_dates` | `set[str]` | `set()` | ISO-date strings of public-holiday weekdays |

### Public Methods

| Method | Description |
| - | - |
| `load_project(project, recompute_critical=False)` | Load project; recomputes critical path via CPM |
| `set_day_width(px)` | Clamp and apply zoom, then emit `zoom_changed` |
| `zoom_in()` | Increase day width by 4 px |
| `zoom_out()` | Decrease day width by 4 px |
| `set_show_resource_units(value)` | Toggle resource unit % display |
| `set_show_sundays(value)` | Toggle Sunday columns |
| `set_zero_float_critical(value)` | Toggle zero-float-critical mode |
| `set_collapsed_ids(ids)` | Update the set of collapsed summary IDs and repaint |

### Rendering Pipeline

`paintEvent` draws, top to bottom:

1. **Alternating row backgrounds** — light blue / white per row.
2. **Column shading** — Saturdays and public holidays: opaque grey (alternating shades per row); Sundays: translucent blue-tint.
3. **Task bars** (`_draw_task_row` for each task row):
   - **Summary** — MS Project-style dark bracket: thin horizontal strip with downward wedges at each end.
   - **Milestone** — black diamond.
   - **Critical task** — red bar.
   - **Normal task** — steel-blue bar.
   - Progress: a thin black line across the middle of the completed portion of the bar.
   - **Overallocation** — orange border when any resource assignment's units exceed the resource's max units.  Both values are normalised with the same heuristic (`raw × 100 if raw ≤ 2.0 else raw`) to handle MPXJ's fraction / percentage dual-scale for `getMaxUnits()`.
   - Resource name labels to the right of the bar (hidden when `day_width < 6`).
   - **Warning icon** — yellow ⚠ triangle when `% complete > 100`.
4. **Dependency arrows** (`_draw_dependency_arrows`) — elbow-routed arrows from the predecessor bar's bottom (or top) edge to the successor bar's top (or bottom) edge, with a filled arrowhead.
5. **Drag outline** — dashed orange rectangle shown while dragging a bar.
6. **Summary container finish lines** — dashed vertical line from the right-wedge tip down to the last visible child row.
7. **Today line** — bold green vertical line through all rows.

### Drag Interaction

Left-click and drag on a task bar moves it horizontally.  On mouse-release, `task_moved(task, delta_days)` is emitted and the caller is responsible for updating the MPXJ data.

Double-clicking a bar opens the **Task Information** dialog.  Committing changes emits `task_edited`.


## Helper Functions

### `_to_qdate(java_date) → QDate | None`

Converts an MPXJ `LocalDateTime` or similar Java date object to a Qt `QDate` by parsing the first 10 characters of its `str()` representation (`YYYY-MM-DD`).

### `_add_working_days(start: QDate, working_days: float) → QDate`

Advances `start` by `working_days` business days, skipping Saturdays and Sundays.

### `_snap_to_workday(date: QDate, non_working_dates: set = None) → QDate`

Advances `date` forward day by day until a working day is found, skipping Saturdays, Sundays, and any date present in `non_working_dates` (ISO strings of public holidays).

### `_compute_finish_date(task) → QDate | None`

Returns the task's finish date as a `QDate`.  Uses MPXJ's `getFinish()` as the primary source (which respects the project calendar and holidays).  Falls back to a manual weekend-skipping calculation using `_add_working_days()` when `getFinish()` is unavailable.

### `_normalize_schedule(all_tasks)`

Forward pass through the task network: for every FS predecessor relationship, ensures the successor's start is ≥ the predecessor's computed finish + lag.  Modifies Java task objects in-memory.  Iterates until no further changes occur (bounded by task count + 2 passes).

### `_get_visible_tasks(all_tasks, collapsed_ids) → list`

Filters out tasks that are children of a collapsed summary task.  Walks the list in order, tracking the current ancestor at each outline level; any task whose ancestor is in `collapsed_ids` is excluded.

### `_date_to_col(project_start: QDate, date: QDate, show_sundays: bool) → int`

Returns the zero-based visible-column offset of `date` from `project_start`.  When `show_sundays` is `False`, Sunday columns are removed from the count so every visible column represents one Mon–Sat day.

### `_get_non_working_dates(project, project_start: QDate, total_calendar_days: int) → set`

Returns a set of ISO date strings (`YYYY-MM-DD`) for non-working weekdays (public holidays) as defined by the project's default calendar.  Saturdays and Sundays are excluded — they are handled separately by day-of-week logic.

### `_read_critical_ids(all_tasks) → set`

Reads the critical-path flag directly from MPXJ task objects via `getCritical()`.  Returns a set of int task IDs, or an empty set if the flag is unavailable or unset on all tasks.

### `_compute_critical_ids(all_tasks, project=None, zero_float_critical=False) → set`

CPM backward pass using full `datetime` precision.

- Summary tasks are excluded from CPM leaf calculations; a summary is marked critical when any descendant leaf is critical.
- `project`: when supplied, the project's stored finish date anchors the backward pass deadline.
- `zero_float_critical`: when `True`, tasks with zero total float (within a 30-minute tolerance) are marked critical in addition to those with negative float.

Steps:

0. **Completed task exclusion** — build a `completed_ids` set (tasks where `getPercentageComplete() ≥ 100`).  Any task in this set is immediately excluded from criticality; the CPM passes skip them.
1. **Forward pass** — compute network earliest finish (`net_ef`) for each task, respecting FS links and constraints (SNET, SNLT, MSO, MFO, FNET).
2. **Backward pass** — propagate latest finish (`late_finish`) backward from the project deadline anchor.
3. **Float** = `late_finish − net_ef`.  A task is critical when: stored finish > raw deadline, float < 0, or (float ≤ 0 and `zero_float_critical`).
4. Propagate criticality upward to summary tasks via `_any_critical_descendant`.

### `_normalize_schedule(tasks, project_start: QDate)`

Clamps the start date of every task to be no earlier than `project_start`, shifting the finish date by the same amount to preserve duration.


## Task Splitting & Merging

### Constants

| Constant | Value | Description |
| - | - | - |
| `SPLIT_GAP_DAYS` | 1 | Calendar days of gap inserted between segments when splitting. Imported by `team_planner_view.py`. |

### Helper: `_split_task_views() → list[int]`

Module-level function. Returns the list of `TAB_*` view indices on which Split Task / Merge Task context menu entries are available (Gantt Chart and Team Planner). Centralises the "is this view split-capable?" decision.

### Helper: `_task_vacation_blocks(task) → list[tuple[QDate, QDate]]`

Module-level function. Iterates all resource assignments on `task`, reads each resource's MPXJ calendar exceptions, and returns a list of `(from_qd, to_qd)` tuples for every contiguous non-working block found. Used by `split_task` to skip over resource vacation periods when placing the second segment.

### `GanttCanvas.split_task(task, split_qdate: QDate) → bool`

Splits `task` at `split_qdate`. Returns `False` immediately for summary tasks, milestones, and when `split_qdate` does not fall strictly inside an existing segment.

**Algorithm:**

1. Locate the segment `[seg_start, seg_end]` that contains `split_qdate`.
2. `seg2_start = split_qdate + SPLIT_GAP_DAYS`.
3. Skip project non-working days: advance `seg2_start` while `_starts_on_non_working(seg2_start)`.
4. Skip resource vacation blocks (`_task_vacation_blocks`): iterate in a stable-point loop; for each vacation block that overlaps `seg2_start`, advance **both** `seg2_start` *and* `seg_end` forward by the vacation width (preserving segment duration), then re-skip trailing non-working days. Repeat until no block touches `seg2_start`.
5. Write the two new segments back into `_task_splits[uid]`, replacing the split segment.

Returns `True` on success. After a successful split the caller emits `task_edited`; `_on_gantt_task_edited` in `MainWindow` then pushes the undo snapshot onto the `tasks` and `baseline` stacks. A failed split (e.g. the date is out of range) returns `False` without emitting anything, so no undo step is created.

### `GanttCanvas.merge_task(task) → bool`

Removes all splits for `task`: deletes the entry from `_task_splits` and triggers a repaint. Returns `False` when the task has no recorded splits.

### `GanttCanvas.get_splits(task) → list[tuple[QDate, QDate]] | None`

Returns a copy of the segment list for `task`, or `None` if the task has no splits.

### `GanttCanvas.load_splits_from_project(project) → None`

Reads existing splits from MPXJ `task.getSplits()` on project open. Populates `_task_splits` so that imported MPP/XML files with splits render correctly from the first paint.

### `GanttCanvas.clear_splits() → None`

Empties `_task_splits` (called on project close / new project).

### `GanttCanvas.load_splits_from_dict(data: dict) → None`

Deserialises the sidecar JSON dict (`{str(uid): [[iso_start, iso_end], …]}`) into `_task_splits`. Called by `MainWindow._load_splits_json()` after a project is opened, overriding any MPXJ-native splits with the more precise sidecar data.

### `GanttCanvas.splits_to_dict() → dict`

Serialises `_task_splits` into a JSON-safe dict. Called by `MainWindow._save_splits_json()` on every save and by `MainWindow._write_splits_to_project()` before undo snapshot serialisation.

### Rendering: `_draw_split_segments()`

When a task has entries in `_task_splits`, `_draw_task_row` delegates bar rendering to `_draw_split_segments`. Each segment is drawn as an individual task bar. The gap between segments is rendered as a **dashed horizontal line** at mid-bar height, visually connecting the two bars across the non-working gap.

### Context Menu

Right-clicking a task bar on the Gantt canvas (and other views in `_split_task_views()`) shows:

| Menu item | Condition | Action |
| - | - | - |
| **Split Task…** | Task is not a summary or milestone | Opens `_do_split_interactive`: a date-picker dialog pre-filled with the clicked date. On confirm, calls `split_task()` and repaints. |
| **Merge Task Segments** | Task has ≥ 2 segments | Calls `_do_merge()` which calls `merge_task()`, emits `task_edited`, and repaints. |

### Interactive Split Dialog (`_do_split_interactive`)

Shown when the user chooses "Split Task…" from the context menu. Allows the user to confirm or adjust the split date. If the proposed `seg2_start` would land on a resource vacation, the vacation-skip algorithm moves it automatically and the dialog shows the adjusted date. The undo snapshot is captured via `task_edited.emit()` **after** the mutation succeeds — a cancelled dialog or a split date that fails validation creates no undo step.

### Sidecar Persistence (`.splits.json`)

Splits are stored in a sidecar file alongside the project file: `<basename>.splits.json`. The sidecar is saved on every project save and reloaded on every project open (after MPXJ-native splits are loaded). This is necessary because `MSPDIWriter` does not serialise task splits into the XML output.

| Method in `MainWindow` | Description |
| - | - |
| `_splits_json_path()` | Returns the sidecar path, or `None` when no project is open. |
| `_save_splits_json()` | Serialises `canvas.splits_to_dict()` to JSON and writes the sidecar. |
| `_load_splits_json()` | Reads the sidecar and calls `canvas.load_splits_from_dict()`. |
| `_write_splits_to_project()` | Called as `pre_serialize` hook in `HistoryManager`; ensures undo snapshots see the latest split data. |

The `split_task_requested` signal on `TaskView`, `TaskSheetView`, and the Gantt context menu all route through `MainWindow.split_task_for_task(task)`, which: calls `canvas.split_task()` (via `_do_split_interactive`), saves the sidecar, and triggers a repaint. The undo snapshot is taken automatically via `task_edited.emit()` → `_on_gantt_task_edited()` after a successful split or merge.
