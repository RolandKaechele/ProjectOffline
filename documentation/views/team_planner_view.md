# team_planner_view.py

Renders the **Team Planner** tab — a resource-row timeline where each row shows when a team member is busy and allows drag-and-drop rescheduling and reassignment.

## Layout Constants

| Constant | Default | Description |
| - | - | - |
| `RESOURCE_COL_W` | 160 px | Width of the frozen left resource-name column |
| `ROW_H` | 44 px | Default height of each resource row (expands with parallel lanes) |
| `TASK_BAR_H` | 22 px | Height of a scheduled task bar |
| `TASK_BAR_MARGIN_V` | computed | Top/bottom margin inside a row to centre the task bar |
| `LANE_H` | 30 px | Height of one parallel task lane (`TASK_BAR_H + 8`) |
| `LANE_PAD_V` | 5 px | Top/bottom padding within a resource row |
| `UNASSIGNED_AREA_H` | 150 px | Full height of the unassigned tasks panel (legacy; see `UA_SECTION_H`) |
| `CHIP_H` | 40 px | Height of an unassigned-task chip |
| `CHIP_W` | 140 px | Width of an unassigned-task chip |
| `CHIP_PAD_H` | 6 px | Horizontal gap between chips |
| `CHIP_PAD_V` | 5 px | Vertical gap between chips |
| `CHIP_COLS_MIN` | 2 | Minimum chip column count (used before first resize) |
| `UA_SECTION_H` | 120 px | Fixed height of the unassigned section in `TeamPlannerView` |

## Colour Constants

| Constant | Description |
| - | - |
| `_C_ROW_EVEN / _C_ROW_ODD` | Even/odd row background |
| `_C_ROW_DRAG_TARGET` | Row highlight while a bar is dragged over it |
| `_C_TASK_NORMAL / _C_TASK_DRAG` | Task bar fill colours |
| `_C_TASK_GHOST` | Translucent ghost bar during drag |
| `_C_CHIP_NORMAL / _C_CHIP_DRAG` | Unassigned chip fill colours |
| `_C_SAT_EVEN / _C_SAT_ODD` | Saturday/holiday column shading (per-row alternating) |
| `_C_SUN` | Sunday column semi-transparent blue tint |
| `_C_TODAY` | Green today-line |
| `_C_SEPARATOR` | Row separator and right-border line |
| `_C_VACATION_FILL` | Semi-transparent orange fill for vacation blocks |
| `_C_VACATION_BORDER` | Darker orange border on vacation blocks |
| `_C_VACATION_TEXT` | Dark-brown label inside vacation blocks |
| `_C_GHOST_BLOCKED` | Red ghost fill when a drag is blocked by a vacation |
| `_C_GHOST_BLOCKED_PEN` | Red dashed border for a blocked ghost |
| `_C_CONFLICT_ROW_BG` | Light-red row background in `_ResourcePane` for conflicted resources |
| `_C_CONFLICT_ROW_TEXT` | Dark-red resource name text for conflicted rows |
| `_C_CONFLICT_BADGE` | Solid red fill for the `!` conflict badge circle |
| `_C_SECONDARY_FILL` | Semi-transparent yellow fill for secondary calendar exception blocks |
| `_C_SECONDARY_BORDER` | Amber border for secondary calendar exception blocks |
| `_C_SECONDARY_TEXT` | Dark amber label text inside secondary calendar blocks |


## Class: `TeamPlannerView`

Top-level `QWidget` for the Team Planner tab.

### Layout

```
nav_bar
hdr_row:   col_corner  │  hdr_area(GanttHeader)  │  hdr_spacer
body_row:  res_area(_ResourcePane)  │  rows_area(TeamPlannerCanvas)  │  rows_vsb
ua_frame:  ua_col_label  │  ua_scroll(_UnassignedPanel)
```

`hdr_spacer.width == rows_vsb.width` ensures the calendar header viewport is pixel-perfect with the canvas viewport so horizontal scroll is drift-free.

### Signals

| Signal | Arguments | Description |
| - | - | - |
| `data_changed` | — | Emitted after any task reschedule, reassignment or assignment |

### Public Methods

| Method | Description |
| - | - |
| `load_project(project)` | Load an MPXJ `ProjectFile`; rebuilds canvas, resource pane, and calendar header |
| `set_day_width(px)` | Set zoom level on the canvas and sync the header |
| `set_show_sundays(val)` | Show or hide Sunday columns on the canvas and header |

### Scroll Sync

| Pair | Direction | Notes |
| - | - | - |
| `rows_area` H → `hdr_area` H | Unidirectional | Canvas horizontal → header horizontal |
| `rows_area` V range → `rows_vsb` | Range sync | External scrollbar mirrors internal range |
| `rows_vsb` ↔ `rows_area` V | Bidirectional | `blockSignals` prevents feedback loops |
| `rows_vsb.valueChanged` → `_res_pane.set_scroll_y` | Unidirectional | Paint-offset approach — resource names follow canvas rows without depending on QScrollArea internals |
| `_on_rows_area_v_changed` → `_res_pane.set_scroll_y` | Explicit call | Needed because `_rows_vsb` signals are blocked in that path |

#### Frozen Pane Wheel Forwarding

`_WheelForwarder` (a `QObject` event filter) is installed on `_res_area.viewport()`.  It forwards every `QEvent.Wheel` event to `_rows_area.viewport()` and returns `True` to prevent the frozen pane from consuming the event silently.  This ensures scroll gestures on the resource-name column always move the canvas (both horizontal timeline scroll and vertical row scroll).

### Navigation Bar

A `NAV_BAR_HEIGHT`-tall bar with a **◀ Today** button that scrolls the canvas so the current date is visible.


## Class: `_ResourcePane`

Frozen left widget that paints resource-name labels aligned to canvas row heights.

Uses a **paint-offset** approach rather than QScrollArea internal scrolling:

| Member | Description |
| - | - |
| `_scroll_y` | Current vertical scroll offset in content pixels |
| `set_scroll_y(y)` | Stores `y`, triggers `update()` — called from `_rows_vsb.valueChanged` |
| `paintEvent` | Draws each row at `self._row_y[i] - self._scroll_y`; rows above/below the viewport are still drawn but clipped by Qt |
| `_y_to_row(y)` | Converts a viewport-local y to a row index by adding `_scroll_y` before comparing against `_row_y` offsets |

The widget fills the `_res_area` QScrollArea viewport (`setWidgetResizable(True)`); no fixed content height is set.  `set_layout()` stores row geometry and calls `update()` only — it does **not** call `setFixedSize()`.  Conflict highlighting and tooltips are driven by `set_conflicts()` and `set_tooltips()` signals from `TeamPlannerCanvas`.



Paints resource rows with task bars and handles drag interactions.

### Signals

| Signal | Arguments | Description |
| - | - | - |
| `task_rescheduled` | `task (object), delta_days (int)` | Bar dragged left/right on the same resource row |
| `task_reassigned` | `task, old_res, new_res, placement (str)` | Bar moved to a different resource row; `placement` is `'serial'`, `'parallel'`, or `'unassign'` |
| `layout_changed` | `names, heights, y_offsets, total_h` | Lane layout recomputed; drives `_ResourcePane.set_layout()` |
| `unassigned_changed` | `[task, ...]` | Unassigned task list updated; drives `_UnassignedPanel.set_unassigned()` |
| `conflicts_changed` | `[bool, ...]` | Conflict flags per resource row; drives `_ResourcePane.set_conflicts()` |
| `conflict_tooltips_changed` | `[str, ...]` | Tooltip text per resource row; drives `_ResourcePane.set_tooltips()` |

### Data Loading

`load_project(project)` performs:

1. Collect resources (skip the null resource at uid 0).
2. For each task: find the first matching resource assignment and place the task in `_tasks_by_res[uid]`; tasks with no matching assignment and that are not summary tasks go into `_unassigned`.
3. Compute timeline extents from start/finish dates across all tasks.
4. Call `_get_non_working_dates` to populate `_non_working`.
5. Call `_get_resource_vacation_blocks` per resource to populate `_vacations_by_res`.
6. Call `_rebuild_layout()` to compute lane data, row heights and y-offsets.
7. Emit `layout_changed`, `unassigned_changed`, `conflicts_changed`, and `conflict_tooltips_changed`.

### Lane Layout

`_rebuild_layout()` calls `_compute_lane_layout(tasks)` per resource row.  `_compute_lane_layout` uses a greedy interval-coloring algorithm: each task is assigned to the lowest-index lane that has no temporal overlap with it.  The resulting row height is `_row_height_for_lanes(n_lanes)`.

### Conflict Detection

`_compute_conflict_data()` is called from `_rebuild_layout()` and returns `(list[bool], list[str])` — one entry per resource row.

Two conflict types are detected:

| Conflict | Condition | Tooltip section |
| - | - | - |
| Parallel tasks | `n_lanes > 1` — at least two tasks overlap in time | Lists all overlapping task pairs as `"A" ↔ "B"` |
| Task on vacation | Any `[task.start, task.finish)` intersects a vacation block | Lists task name, vacation name, and date range |

**UID resilience:** the call to `int(str(res.getUniqueID()))` inside `_compute_conflict_data` is wrapped in `try/except`.  If `getUniqueID()` raises or returns an unusable value, the resource row is still included in the result with `conflict=False` and an empty tooltip — the Team Planner never crashes due to a missing or malformed UID.

### Vacation Blocks

Resource calendars may define non-working `ProjectCalendarException` entries (vacations, absences).  These are loaded by `_get_resource_vacation_blocks(resource)` into `_vacations_by_res` and rendered as coloured overlays on the canvas.

`_get_resource_vacation_blocks()` collects two kinds of blocks for each resource:

1. **Personal calendar exceptions** — from the resource's own `ProjectCalendar`; rendered as semi-transparent **orange** blocks.
2. **Secondary calendar exceptions** — from the calendar resolved by `resolve_secondary_calendar()` in `secondary_calendar_integration.py`; rendered as semi-transparent **yellow** blocks with `source="secondary"` and `calendar_name` set to the secondary calendar's name.

**Parent-date filtering for secondary calendars:**  To avoid double-rendering national public holidays that are already shown via the primary (personal) calendar, `_get_resource_vacation_blocks()` filters secondary calendar exceptions:

- The **reference calendar** is the secondary calendar's parent calendar (the national/base holiday calendar from which it inherits).  If the secondary calendar has no parent, the project default calendar is used as the reference.
- Any exception whose date range is already present in the reference calendar is **excluded** from the secondary blocks.  Only dates unique to the secondary calendar are rendered.

**Named-only parent_dates filter:**  When building the set of reference exception dates (`parent_dates`) used for the suppression above, only exceptions whose `getName()` returns a non-empty, non-whitespace string are included.  Anonymous entries — those with `getName() == None`, `""`, or whitespace — are silently skipped.  This is critical because Confluence sync writes multi-day school-holiday blocks (*Schulferien*) as unnamed exceptions; without this guard, a Schulferien block starting on the same date as a state-specific secondary-calendar holiday (e.g. BW *Fronleichnam* on 2026-06-04) would cause that holiday to be incorrectly suppressed from the yellow blocks rendered in the Team Planner.

**Exception name fallback:**  When a secondary calendar exception has an empty or whitespace-only name, the block label falls back to the secondary calendar name alone (e.g. `"Baden-Württemberg"`).  When the exception name is non-empty, the label is formatted as `"<calendar_name>: <exception_name>"` (e.g. `"Baden-Württemberg: Heilige Drei Könige"`).


**Behaviour of vacation blocks:**

- Painted below task bars so task bars float on top.
- Labels show the exception name (elided if the block is narrow).
- **Hover** — `event()` in `TeamPlannerCanvas` intercepts `QEvent.ToolTip` via `_hit_vacation()`.  For personal blocks the tooltip shows exception name and date range; for secondary blocks it additionally shows the source calendar name (e.g. `"Source: Bayern"`).
- **Double-click** on a vacation block opens `_VacationDialog` (read-only).
- **Drag-and-drop** onto a vacation block is blocked; the ghost turns red and the cursor changes to `ForbiddenCursor`.
- Hovering over a vacation block (without dragging) shows a `PointingHandCursor` hint.

### Drag Interactions

| Gesture | Result |
| - | - |
| Drag bar left/right on same row | Emits `task_rescheduled(task, delta_days)` |
| Drag bar to a different row | Emits `task_reassigned(task, old_res, new_res, placement)` |
| Drag bar off all resource rows | Emits `task_reassigned(task, old_res, None, 'unassign')` |
| Drag chip from Unassigned panel onto a row | Calls `_on_chip_drop` → `_on_task_assigned` → emits `data_changed` |
| Drag onto a vacation block | Blocked silently; ghost turns red, cursor shows `ForbiddenCursor` |

When dropping onto a busy row, `_ask_placement()` is called.  If there is no temporal overlap the placement is `'parallel'` without a dialog.  If there is overlap, `_PlacementDialog` is shown.

### Painting

`paintEvent` renders in order:

1. **Row backgrounds** — even rows `_C_ROW_EVEN` (white), odd rows `_C_ROW_ODD` (near-white blue tint).
2. **Weekend/holiday column shading** — Saturdays/holidays: opaque grey (alternating per row); Sundays: semi-transparent blue-tint.
3. **Vertical grid lines**.
4. **Vacation blocks** per row (`_paint_vacation_blocks_for_row()`).  Personal calendar blocks are painted in orange (`_C_VACATION_FILL`); secondary calendar blocks are painted in yellow (`_C_SECONDARY_FILL`).
5. **Task bars** per lane via `_paint_task_bar()`.
6. **Drag ghost** — translucent bar at the current drag position (`_paint_drag_ghost()`); turns red when blocked by a vacation block.
7. **Today line** — bold green vertical line.

### Tooltip

`event(ev)` is overridden in `TeamPlannerCanvas` to intercept `QEvent.ToolTip`.  When the mouse is over a vacation or secondary calendar block (detected via `_hit_vacation(x, y)`), a `QToolTip` is shown:

| Block type | Tooltip content |
| ---------- | --------------- |
| Personal vacation | `**name**\nfrom – to` |
| Secondary calendar | `**name**\nfrom – to\n*Source: CalendarName*` |

When the cursor is not over any block the tooltip is hidden and the event is ignored.


## Class: `_ResourcePane`

Frozen left column widget (`QWidget`) that draws resource-name labels aligned to the canvas row heights.  It is placed inside a `QScrollArea` with no scrollbars; its vertical position is driven absolutely by the canvas's vertical scrollbar to avoid drift.

`setMouseTracking(True)` is enabled so `QEvent.ToolTip` events fire when the mouse moves over a row.

### Methods

| Method | Description |
| - | - |
| `set_layout(names, row_heights, row_y_offsets, total_content_h)` | Called via `layout_changed`; resizes widget and resets conflict/tooltip lists |
| `set_conflicts(conflicts: list[bool])` | Receives conflict flags from `conflicts_changed`; triggers repaint |
| `set_tooltips(tooltips: list[str])` | Receives tooltip strings from `conflict_tooltips_changed` |
| `event(ev)` | Intercepts `QEvent.ToolTip`; shows `QToolTip` for the row under the cursor |
| `_y_to_row(y) → int` | Maps a pixel y-coordinate to a resource row index (`-1` if outside) |

### Signals

| Signal | Arguments | Description |
| - | - | - |
| `jump_to_task_requested` | `int` — resource row index | Emitted on right-click when the user chooses **Scroll timeline to first task of '…'**; handled by `TeamPlannerView._on_res_pane_jump_to_task` |

### Context Menu

Right-click on a resource name row shows:

| Action | Effect |
| - | - |
| Scroll timeline to first task of '…' | Emits `jump_to_task_requested(row_idx)`; `TeamPlannerView` finds the earliest task start for that resource across `_tasks_by_res` and calls `_scroll_to_date_exact(first_start.addDays(-3))` to bring it into view |

### Conflict Visual Indicators

When `_conflicts[i]` is `True` for a row:

- Row background is filled with `_C_CONFLICT_ROW_BG` (light red).
- Name text is rendered bold in `_C_CONFLICT_ROW_TEXT` (dark red).
- A small filled red circle badge with `!` is drawn on the right side of the row.

### Tooltip

Hovering over any row shows a `QToolTip` with the pre-built conflict description (empty string = no tooltip).  The tooltip content is produced by `_compute_conflict_data()` and contains structured sections for parallel tasks and tasks-on-vacation.


## Class: `_VacationDialog`

Read-only modal dialog that opens when the user double-clicks a vacation block in the canvas.

| Field shown | Source |
| - | - |
| Exception name | `vac['name']` |
| Resource name | `_res_names[row_idx]` |
| From / To dates | `vac['from_qd']` / `vac['to_qd']` formatted as "weekday, D Month YYYY" |
| Duration | Calendar days from `from_qd.daysTo(to_qd) + 1` |
| Type | `ex.getWorking()` → "Working" or "Non-Working" |

A note at the bottom states that the block cannot be moved or deleted here.


## Class: `_UnassignedPanel`

Draws unassigned task chips in a dynamic grid.  Each chip shows:

- **Line 1**: task name (elided if too long)
- **Line 2**: duration label from `_chip_dur_str()` (e.g. `"3d"`, `"1w 2d"`)

### Signals

| Signal | Arguments | Description |
| - | - | - |
| `chip_drag_started` | `task` | User began dragging a chip |
| `chip_drag_moved` | `global_x, global_y` | Chip ghost position updated |
| `chip_drag_ended` | `task, global_x, global_y` | User released the chip |
| `chip_double_clicked` | `task` | User double-clicked a chip |

Drag uses `grabMouse()` so the chip ghost can follow the cursor outside the panel into the canvas area.


## Class: `_PlacementDialog`

Modal dialog shown when a task is dropped onto a resource row that already has tasks in the same time window.

| Button | `choice()` return value |
| - | - |
| Serial (after last task) | `"serial"` |
| Parallel (at dropped position) | `"parallel"` |
| Cancel | `"cancel"` |


## Module-level Helpers

### `_chip_dur_str(task) → str`

Returns a short working-day duration label for a chip second line (e.g. `"5d"`, `"1w"`, `"1w 3d"`).  Uses the same unit-conversion logic as `gantt_view` (hours ÷ 8, weeks × 5, months × 20).  Returns `""` on error or if duration is `None`.

### `_compute_lane_layout(tasks) → list[dict]`

Greedy interval-coloring: assigns each task to the lowest-index lane with no temporal overlap.  Returns a list of `{'task': ..., 'lane': int}` sorted by start date.

### `_row_height_for_lanes(n_lanes) → int`

Returns the pixel height that accommodates `n_lanes` parallel task lanes: `max(ROW_H, LANE_PAD_V * 2 + n_lanes * LANE_H)`.

### `_get_resource_vacation_blocks(resource) → list[dict]`

Reads non-working `ProjectCalendarException` entries for a resource and returns them as a list of dicts.  Two sources are merged:

1. **Personal calendar** — entries from the resource's own `ProjectCalendar`:

   ```python
   {'from_qd': QDate, 'to_qd': QDate, 'name': str, 'exception': <MPXJ object>}
   ```

2. **Secondary calendar** — entries from the calendar resolved by `resolve_secondary_calendar()`:

   ```python
   {'from_qd': QDate, 'to_qd': QDate, 'name': str, 'exception': <MPXJ object>,
    'source': 'secondary', 'calendar_name': str}
   ```

Working-day overrides (e.g. special working Saturdays where `ex.getWorking()` is `True`) are skipped in both sources.  Returns `[]` if the resource has no calendar and no secondary calendar mapping, or on any error.

### `_x_to_date(x, project_start, day_width, show_sundays) → QDate`

Converts a canvas x-pixel coordinate back to a calendar `QDate`.  When `show_sundays=False` the visible column is mapped back through the non-Sunday calendar.

### `_col_to_x(col, day_width) → int`

Converts a visible column index to a canvas x-pixel coordinate.


## Task Splitting & Merging in Team Planner

The Team Planner shares the same `_task_splits` dict owned by `GanttCanvas`, accessed via a shared reference.

### `TeamPlannerCanvas.set_splits_ref(splits_dict: dict) → None`

Stores the shared reference to `GanttCanvas._task_splits` so both canvases render from the same split data. Called from `MainWindow.__init__` after both canvases are constructed.

### Split Rendering

When a task has entries in `_task_splits_ref`, the canvas draws individual sub-bars for each segment (the same bar height and colour as a normal task bar). The gap between segments is drawn as a **dashed horizontal connector** at mid-bar height, identical to the Gantt view rendering.

### Segment Dragging

Individual segments can be dragged left/right within the Team Planner timeline. The drag identifies which segment was clicked via `_task_splits_ref` at `mousePressEvent`, stores `_drag_segment_idx`, and updates only that segment's dates on `mouseReleaseEvent`.

**Vacation-overlap detection** on segment drop: the condition `new_seg_s <= vac['to_qd'] and new_seg_e >= vac['from_qd']` covers all four overlap geometries (fully inside, start-before/end-inside, start-inside/end-after, straddle). When an overlap is detected, `_NonWorkingDayDialog` is shown with three options:

| Choice | Effect |
| - | - |
| Move to next working day | Jumps `seg_start` past the vacation end, skips non-working days, preserves segment duration |
| Move anyway | Keeps the dropped position (segment may overlap a vacation block) |
| Cancel | Discards the drop; segment returns to its original position |

### Vacation-Split Dialog (`_VacationSplitDialog`)

Shown when the user drags a **whole unsplit** task bar onto a vacation block in the Team Planner. Offers three choices:

| Choice | `choice()` | Effect |
| - | - | - |
| Move to next working day | `'next_working'` | Advances the task start past the vacation end |
| Split around vacation | `'split'` | Calls `gantt_canvas.split_task()` at the vacation start boundary |
| Move anyway | `'move_anyway'` | Keeps the bar in the vacation (orange ghost position) |

The "Split around vacation" button is only enabled (`can_split=True`) when the task duration is long enough that a split would leave a non-zero segment on each side.

### Segment Merge Dialog (`_SegmentMergeDialog`)

Shown when a segment is dragged so it overlaps another segment of the same task. Offers two choices:

| Choice | `choice()` | Effect |
| - | - | - |
| Merge segments | `'merge'` | Calls `gantt_canvas.merge_task()` to remove the split and restore a single bar |
| Keep separate | `'keep'` | Discards the drag; segments remain as they were |
