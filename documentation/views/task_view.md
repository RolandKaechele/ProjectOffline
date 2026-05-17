# task_view.py

Provides the editable task grid on the left side of the Gantt Chart tab.

## Class: `TaskView`

Extends `QTableWidget`.

### Columns

| # | Header | Editable | Notes |
| - | - | - | - |
| 0 | *(indicator)* | No | Status icons drawn by `_make_combined_icon` / `_IndicatorDelegate` |
| 1 | ID | No | Task sequence number |
| 2 | Task Name | Yes | Indented by outline level; summary tasks shown in bold |
| 3 | Duration | Yes | String value from MPXJ (e.g. `5.0d`) |
| 4 | Start | No | `YYYY-MM-DD` |
| 5 | Finish | No | `YYYY-MM-DD` |
| 6 | Predecessors | No | Predecessor entries in `"ID – Task Name"` format (e.g. `6 – Component design`), joined with `,  `; width 220 px |
| 7 | % Done | Yes | Visual progress bar (rendered by `_ProgressDelegate`); values above 100% shown in red |
| 8 | Resources | No | Comma-separated assigned resource names with optional unit % |

`EDITABLE_COLS = {2, 3, 7}` — Task Name, Duration, and % Done.

### Signals

| Signal | Arguments | Description |
| - | - | - |
| `data_changed` | — | Any task field was edited |
| `task_reordered` | — | A task row was moved via drag-and-drop |
| `selection_changed` | `bool` — `True` when ≥ 1 row is selected | The selection changed |
| `show_in_gantt` | `task (object)` | Emitted when the user chooses **Show in Gantt Chart** from the context menu; carries the Java task object so `ui.py` can scroll `GanttView` to the task's start date |
| `split_task_requested` | `task (object)` | Emitted when the user chooses **Split Task…** from the context menu on a non-summary, non-milestone task; `ui.py` opens the split-date dialog |
| `merge_task_requested` | `task (object)` | Emitted when the user chooses **Merge Task Segments** from the context menu; only shown when the task already has splits (`_has_splits_fn` returns `True`) |

> **`_has_splits_fn`** — an optional callable set by `ui.py` after construction:
> `task_view._has_splits_fn = gantt_canvas.get_splits`.
> Returns the list of split segments for a task (truthy when splits exist).
> When not set, the **Merge Task Segments** item is never shown.

### Frozen Indicator Column

Column 0 is mirrored into a `_frozen` `QTableWidget` overlay that stays visually fixed at the left edge while the main table scrolls horizontally.  The overlay uses `Qt.ScrollBarAlwaysOff` and is kept in sync with the main table's vertical scroll bar.

#### Horizontal Scroll Lock

`TaskView` deliberately prevents any horizontal scrolling of the main table:

| Mechanism | Where | Purpose |
| - | - | - |
| `setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)` | `ui.py` — wired after construction | Hides the scrollbar so the user cannot drag it |
| `scrollContentsBy(dx, dy)` override | `task_view.py` | Calls `super().scrollContentsBy(0, dy)` — suppresses any horizontal shift regardless of input source (wheel, keyboard, programmatic) |
| `_HorizontalWheelBlocker` event filter | `ui.py` — installed on `task_view.viewport()` | Swallows wheel events with `angleDelta().x() != 0` before Qt can act on them |

This ensures the task-column grid never drifts relative to the Gantt chart, regardless of trackpad diagonal gestures or programmatic scroll calls.

#### Frozen Column Wheel Forwarding

The `_frozen` overlay has its own viewport that would silently consume wheel events, preventing vertical scroll when the cursor is over the status-icon column.  `_FrozenWheelForwarder` (a `QObject` event filter installed on `_frozen.viewport()`) forwards every `QEvent.Wheel` event to the main table's viewport and returns `True` to suppress the overlay's own handling.

### Row Status Icons (Column 0)

Icons are 32 × 32 `QPixmap` shapes drawn by `_make_icon`.  Multiple icons can appear simultaneously (combined side by side by `_make_combined_icon`), with one exception:

| Icon | Colour | Condition |
| - | - | - |
| Diamond ◆ | Purple | `isMilestone() == true` — shown **alone**, overrides all others |
| Page | Blue | Task has notes |
| Triangle ⚠ | Amber | `% complete > 100` |
| Exclamation circle | Orange | Past finish date and not 100% complete (overdue — `actualFinish` state is intentionally ignored since MPXJ auto-sets it when a task reaches 100% and does not always clear it when the percentage is reverted) |
| Filled circle | Red | Task is on the critical path (only shown when `% complete < 100`) |

When a milestone is detected all other icons are suppressed.  In all other cases every applicable icon is rendered together.  Hovering over the indicator cell shows a tooltip for each condition.


## Class: `_TaskNameDelegate`

Custom `QStyledItemDelegate` for the **Name** column (column 2).

### Responsibilities

- Draws indentation based on the task's `outline_level` (stored in `Qt.UserRole`).
- Renders summary tasks in **bold**.
- Draws a collapse/expand triangle (▶/▼) for summary tasks.
- Handles `MouseButtonPress` events on the triangle to toggle the collapsed state via `TaskView._toggle_collapse(task_id)`.

### Data Roles on the Name Column Item

| Role | Type | Content |
| - | - | - |
| `Qt.DisplayRole` | `str` | Task name text |
| `Qt.UserRole` | `int` | Outline level |
| `Qt.UserRole + 1` | `bool` | `is_summary` |
| `Qt.UserRole + 2` | `str` | Task unique ID (as string) |
| `Qt.UserRole + 3` | `bool` | `is_collapsed` |


## Predecessor Enrichment

`load_project` builds `self._id_to_name: dict[int, str]` by iterating all tasks once before populating rows.  This lookup is used in `_fill_row` to format each predecessor as `"ID – Task Name"` instead of a bare ID.

**Example:** task 8 with predecessor 6 ("Component design") displays as `6 – Component design`.

Multiple predecessors are joined with `,  ` (comma + two spaces).


## Class: `_ProgressDelegate`

Custom `QStyledItemDelegate` for the **% Done** column (column 7).

- Parses the cell text (strips `%`, converts to float) from `Qt.DisplayRole`.
- Draws a rounded progress bar with colour-coded fill:

| Range | Fill colour | Text colour |
| - | - | - |
| 0% | Empty track only (`#E8F0FB` outline) | Dark (`#1F1F1F`) |
| 1–49% | Light blue `#70A0D0` (partial fill) | Dark (`#1F1F1F`) |
| 50–99% | Blue `#2B579A` (partial fill) | White |
| 100% | Green `#217346` (full fill) | White |
| > 100% | Red `#C0392B` (full-width fill) | White |

- The default `QStyledItemDelegate` editor is still used for inline editing (column 7 is in `EDITABLE_COLS`) — only `paint` and `sizeHint` are overridden.
- Minimum hint width: 90 px.

Double-clicking any editable column opens the delegate editor directly.  When editing is committed, the corresponding MPXJ Java setter is called:

| Column | Setter |
| - | - |
| Task Name (2) | `task.setName(value)` |
| Duration (3) | `task.setDuration(Duration.getInstance(value, TimeUnit.DAYS))` |
| % Done (7) | `task.setPercentageComplete(Double.valueOf(value))` |

Double-clicking the **indicator** column (0) or the **Task Name** column (2) outside the collapse triangle opens the full **Task Information** dialog.  The view maintains `_critical_ids` (a `set` of critical task UIDs) and `_float_data` (a `dict` mapping task UID → float metrics) computed by `_compute_critical_ids(return_float_data=True)` at load time, and passes both to `TaskDialog` so its **Schedule** tab can display the correct critical status and total/free float values.


## Drag-and-Drop Reordering

Rows can be reordered by dragging.  The drop position is determined by where the mouse is within the target row:

| Zone | Mode | Indicator |
| - | - | - |
| Top or bottom 30% of a row | `between` — insert before/after | Blue horizontal line |
| Middle 40% of a row | `child` — make the dragged task a child of the target | Blue border highlight on target row |

After a drop:

1. The task's `OutlineLevel` is updated to match the new position's level.
2. `_reorder_mpxj_tasks` rewrites the MPXJ `ListWithCallbacks` backing store via Java reflection.
3. `_update_parent_dates` recalculates each summary task's start/finish from its children (using outline-level order rather than `getChildTasks()`).
4. `_renumber_task_ids` assigns sequential IDs (1, 2, 3 …) in the new container iteration order.
5. `task_reordered` is emitted.


## Context Menu

Right-click on a task row shows:

| Action | Shortcut | Condition | Effect |
| - | - | - | - |
| Insert Task | `Ins` | Always | Add a new blank task after the selected row |
| Delete Task | `Del` | Always | Delete selected rows |
| Task Information… | — | Always | Open Task Information dialog |
| Show in Gantt Chart | — | Exactly 1 non-`None` task row selected | Emits `show_in_gantt(task)`; `ui.py` scrolls `GanttView` horizontally so the task bar is visible (works in all zoom modes including hourly) |
