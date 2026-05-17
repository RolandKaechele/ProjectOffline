# resource_usage_graph_view.py

Implements the **Resource Usage Graph** tab — a two-pane timeline view that shows
how many hours each resource (and each of their task assignments) is scheduled to
work on every day of the project.  The layout mirrors Microsoft Project's built-in
"Resource Usage" view.


## Layout Overview

```
nav_bar          ← "◀ Today" navigation button
hdr_row
  ├─ _UsageHeaderCorner   (frozen left column header: Resource Name | Work)
  ├─ _DetailsHeaderCell   (narrow "Details" label above the fixed Work body column)
  └─ GanttHeader or _HourModeHeader  (scrollable calendar header; swapped by zoom mode)
body_row
  ├─ _LeftPane            (frozen: resource & task names + total work)
  ├─ _WorkBodyColumn      (fixed 60-px "Work" label column — aligned with _DetailsHeaderCell)
  ├─ _UsageCanvas         (scrollable: hour cells — daily / weekly / monthly / hourly)
  └─ QScrollBar (vsb)     (external vertical scrollbar)
```

**Horizontal scroll** is shared between `_UsageCanvas` and the active header widget
(the canvas drives the header).  **Vertical scroll** uses an external `QScrollBar`
that keeps `_LeftPane`, `_WorkBodyColumn`, and `_UsageCanvas` in lockstep.


## Layout Constants

| Constant | Value | Description |
| - | - | - |
| `LEFT_NAME_W` | 240 px | Width of the "Resource Name" sub-column in the left pane |
| `LEFT_WORK_W` | 80 px | Width of the "Work" sub-column in the left pane |
| `LEFT_W` | 320 px | Total width of the frozen left pane (`LEFT_NAME_W + LEFT_WORK_W`) |
| `ROW_H` | 36 px | Height of each row (matches Task Sheet, Resource Sheet, Gantt) |
| `DETAILS_COL_W` | 60 px | Width of the "Details / Work" label column on the right pane |
| `TRI_W` | 10 px | Width of the collapse/expand triangle on resource rows |
| `INDENT_PX` | 20 px | Left indent for task sub-rows in the left pane |


## Zoom Modes

The view has four zoom levels controlled by the global day-width slider:

| Mode | `day_width` range | Column unit | Header | Hour labels |
| - | - | - | - | - |
| **Monthly** | 4 – 6 px | 1 calendar month (~88–132 px) | `GanttHeader` (month bands only) | Monthly total |
| **Weekly** | 7 – 13 px | 1 ISO week Mon–Sun (49–91 px) | `GanttHeader` ("W17", "W18" …) | Weekly total |
| **Daily** | 14 – 59 px | 1 calendar day (14–59 px) | `GanttHeader` (day numbers) | Per-day hours (≥ 18 px) |
| **Hourly** | 60 – 80 px | 1 work hour 08:00–16:00 (60–80 px) | `_HourModeHeader` (date / hour slots) | Per-hour share (≥ 30 px) |

### Zoom constants

| Constant | Value | Meaning |
| - | - | - |
| `MONTH_MODE_THRESHOLD` | 7 | `day_width < 7` → monthly mode |
| `WEEK_MODE_THRESHOLD` | 14 | `7 ≤ day_width < 14` → weekly mode |
| `HOUR_MODE_THRESHOLD` | 60 | `day_width ≥ 60` → hourly mode |
| `WORK_HOUR_START` | 8 | Default fallback — first work hour slot (08:00) |
| `WORK_HOUR_END` | 17 | Default fallback — exclusive end (last slot = 16:00–17:00) |
| `WORK_DAY_HOURS` | 9 | Default fallback — number of hour columns per working day |

The actual values used at runtime are read from the project's default calendar
by `_read_work_hours()` and stored as `self._work_hour_start`, `self._work_hour_end`,
and `self._work_day_hours` on the main view.  The constants above serve only as the
fallback when the calendar contains no explicit working-time definition.

### Coordinate system

All modes share the same per-day pixel coordinate system: `x = days_from_start × day_width`.
The `_WorkBodyColumn` (60 px, fixed) sits between `_LeftPane` and `_right_scroll` in the
body layout, mirroring `_DetailsHeaderCell` (60 px, fixed) in the header layout.  This
means both `_hdr_area` and `_right_scroll` begin at the same screen x-position, so day
column labels always stay directly above their data cells regardless of scroll position.
`_UsageCanvas` no longer contains any `DETAILS_COL_W` offset — all coordinates within
the canvas start at x = 0.

In **hourly** mode `day_width` is re-interpreted as *pixels per hour*; the canvas skips Saturday/Sunday entirely and draws `self._clock_day_span` sub-columns per working day.  The start and end hours are taken from `self._work_hour_start` / `self._work_hour_end`, which are read from the project calendar by `_read_work_hours()` on every `load_project()` call.

## Frozen Left-Pane Wheel Forwarding

`_WheelForwarder` (a `QObject` event filter) is installed on `_left_scroll.viewport()`.  It forwards every `QEvent.Wheel` event to `_right_scroll.viewport()` and returns `True` to suppress the frozen pane's own scroll handling.  Without this, wheel gestures over the resource/task name column are silently consumed by the hidden scrollbars of `_left_scroll` and do not scroll the canvas.

`_LeftPane` uses the `set_scroll_y(y)` paint-offset approach for vertical alignment: the widget always fills the `_left_scroll` viewport (`setWidgetResizable(True)`), and `_scroll_y` is updated directly from `_vsb.valueChanged` so the painted row positions follow the external scrollbar without depending on QScrollArea internal scrolling.


The `_show_off_hours` flag (toggled by Options → Show Off-Hours, persisted in QSettings under `"usage/show_off_hours"`) extends the hourly view to cover the full 24-hour clock when `True`.  Hours outside the working ranges (pre-work, post-work, and any mid-day breaks) are shown in the grey `_C_WEEKEND` colour.  Both `_HourModeHeader` and `_UsageCanvas` receive the effective `clock_hour_start`, `clock_day_span`, and `non_working_slots` derived from this flag.

In **weekly** and **monthly** modes the canvas is configured with `show_sundays=True` regardless of the user setting, so that `_col_x()` and the `GanttHeader` both count all 7 days per week and stay in sync.  The `show_sundays` user preference only applies in **daily** and **hourly** modes.


## Colour Palette

| Constant | Description |
| - | - |
| `_C_RES_BG / _C_RES_BG_ALT` | Alternating light-blue background for resource header rows |
| `_C_TASK_BG_EVEN / _C_TASK_BG_ODD` | White / off-white alternating task sub-row backgrounds |
| `_C_WORK_CELL` | Semi-transparent blue fill used in hour cells that have non-zero work |
| `_C_GRID` | Light grey horizontal and vertical grid lines |
| `_C_WEEKEND` | Grey weekend column shading (Sat/Sun or calendar holidays) |
| `_C_TODAY_LINE` | Green vertical "today" indicator line |
| `_C_SEP` | Blue-grey separator between the left pane and the canvas |


## Data Model

### `_Row`

Each project resource and each of its task assignments maps to one `_Row` object.

| Attribute | Type | Description |
| - | - | - |
| `kind` | `'resource'` \| `'task'` | Row type |
| `name` | `str` | Display name |
| `total_h` | `float` | Total work in hours |
| `daily` | `dict[QDate, float]` | Hours per working day |
| `res_idx` | `int` | Resource index — used for alternating row colour bands |
| `collapsed` | `bool` | `True` when this resource row is collapsed (task rows hidden) |
| `visible` | `bool` | Set by `_rebuild_visible()` |
| `task` | Java Task \| `None` | The underlying MPXJ task object (set for `kind == 'task'` rows; `None` for resource rows) |

### Daily Hour Distribution

Work is distributed **evenly** over the Mon–Fri working days that fall within the
assignment's start → finish window.  Helper functions:

| Function | Description |
| - | - |
| `_working_days_in_range(start, end)` | Count Mon–Fri days (inclusive) in a date range |
| `_parse_work_hours(work_obj)` | Extract float hours from an MPXJ `Duration` — handles HOURS / DAYS / WEEKS / MONTHS units |
| `_build_daily_hours(start, end, total_h)` | Return `{QDate: h}` with even per-day distribution |
| `_hrs_label(h, compact=False)` | Format hours as a compact string, e.g. `'8h'`, `'7.5h'`. When `compact=True` (used in daily mode for `day_width < 32` px) only one decimal place is rendered (e.g. `'5.3h'` instead of `'5.33h'`) to prevent text overflow in narrow cells. |

Resource rows aggregate their children's `daily` dicts so the resource row's
hour cell shows the **sum** of all assignment hours on that day.


## Classes

### `ResourceUsageGraphView`

Top-level `QWidget` added to the application as tab index **6** ("Resource Usage").

#### Signals

| Signal | Arguments | Description |
| - | - | - |
| `task_edited` | — | Emitted after a task is edited via the double-click Task Information dialog; triggers `ui.py` to reload all affected views |

#### Public Methods

| Method | Description |
| - | - |
| `load_project(project)` | Build the row model from MPXJ `ProjectFile`; configure header and canvas |
| `set_day_width(px)` | Zoom level — propagated from the global zoom slider; triggers mode switch |
| `set_show_sundays(val)` | Show or hide Sunday columns (daily/hourly modes only); propagated from global toggle |
| `set_show_off_hours(val)` | Show or hide hours outside the working window in hourly mode; persisted via `"usage/show_off_hours"` in QSettings |

#### Internal Methods

| Method | Description |
| - | - || `_read_work_hours(project)` | Read `(work_hour_start, work_hour_end)` from `project.getDefaultCalendar()` via MPXJ `getCalendarHours(DayOfWeek)`; falls back to `(WORK_HOUR_START, WORK_HOUR_END)` |
| `_build_rows(project)` | Enumerate `project.getResources()` and their `getAssignments()`; create `_Row` objects; set `row.task` on each task row |
| `_compute_date_range(project)` | Derive `project_start` and `total_days` from the outermost assignment dates |
| `_rebuild_visible()` | Recompute `self._vis` from `self._rows` (honours `collapsed` flags); aligns `canvas_start` to month/week boundary; re-seats `_canvas` in scroll area to flush size cache |
| `_configure_header()` | Swap header widget (`GanttHeader` ↔ `_HourModeHeader`) and reconfigure for the current zoom mode |
| `_scroll_to_today()` | Scroll the canvas so today's column is centred in the viewport |
| `_on_jump_to_allocation(vis_idx)` | Scroll `_right_scroll` to the earliest `daily` date across all task sub-rows of the resource row at `vis_idx`; subtracts a 3-day-width margin |
| `_on_jump_task_to_allocation(vis_idx)` | Scroll `_right_scroll` to the earliest key in `row.daily` for the task row at `vis_idx`; subtracts a 3-day-width margin |
| `_on_task_info(task)` | Open `TaskDialog` for `task`; on Accepted call `dlg.apply_to_task()` and emit `task_edited` |

### `_LeftPane`

Custom `QWidget` that paints the frozen name + work column.

- **Resource rows**: bold text, collapse/expand triangle, light-blue background.
- **Task rows**: regular text, indented by `INDENT_PX` pixels.
- `mousePressEvent` checks if the click landed on a resource row's triangle area
  and toggles `row.collapsed`; then calls `_rebuild_visible()` on the parent view.

#### Signals

| Signal | Arguments | Description |
| - | - | - |
| `jump_to_allocation_requested` | `int` — visible row index | Emitted on right-click of a **resource** row; handled by `_on_jump_to_allocation` |
| `jump_task_to_allocation_requested` | `int` — visible row index | Emitted on right-click of a **task** row; handled by `_on_jump_task_to_allocation` |
| `task_info_requested` | `task (object)` | Emitted on double-click of a **task** row; carries the Java task object; handled by `_on_task_info` |

#### Context Menu

Right-click on a visible row shows a context menu whose action depends on row kind:

| Row kind | Action label | Signal emitted |
| - | - | - |
| `'resource'` | Jump to first allocation of '…' in timeline | `jump_to_allocation_requested(vis_idx)` |
| `'task'` (has `daily` data) | Jump to first allocation of '…' in timeline | `jump_task_to_allocation_requested(vis_idx)` |

#### Double-click

Double-clicking a `'task'` row that has a non-`None` `.task` attribute emits `task_info_requested(row.task)`, which opens `TaskDialog` via `_on_task_info`.

### `_UsageCanvas`

Custom `QWidget` that paints the scrollable timeline grid.  Implements four paint
branches selected by `day_width`:

| Branch | Condition | Column unit | Aggregation |
| - | - | - | - |
| Hourly | `day_width ≥ HOUR_MODE_THRESHOLD` | 1 work hour | `daily_hours / self._work_day_hours` per slot |
| Monthly | `day_width < MONTH_MODE_THRESHOLD` | 1 calendar month | Sum all days in month |
| Weekly | `day_width < WEEK_MODE_THRESHOLD` | 1 ISO week (Mon–Sun) | Sum all days in week |
| Daily | otherwise | 1 calendar day | Per-day value directly |

Shared helpers (`_sum_period`, `_draw_period_cells`) are defined as closures inside
`paintEvent` and used by both the weekly and monthly branches.

`_update_size()` recalculates `setFixedSize()` based on the active mode, then calls
`updateGeometry()` on itself and its parent so Qt's layout system re-evaluates the
available scroll range immediately.

#### Label rendering

In **daily mode**, hour labels are shown when `day_width ≥ 18` px.  At narrow widths
(`day_width < 32` px) `_hrs_label` is called with `compact=True` to produce a
1-decimal string (e.g. `'5.3h'`) that fits within the cell.  At wider widths the
full 2-decimal format is used (e.g. `'5.33h'`).

#### Hover tooltip

`_UsageCanvas` has mouse tracking enabled (`setMouseTracking(True)`).  Hovering over
a cell triggers `mouseMoveEvent`, which:

1. Calls `_x_to_date_info(x)` to reverse-map the cursor's x position to a
   `(QDate, period_label)` pair.  The mapping respects the active zoom mode:

   - **Daily** → exact calendar day, label `'Mon, 28 Apr 2026'`
   - **Weekly** → ISO week containing x, label `'Week 18: 20 Apr – 26 Apr 2026'`
   - **Monthly** → calendar month containing x, label `'April 2026'`
   - **Hourly** → working day + hour slot, label `'Mon, 28 Apr 2026  09:00–10:00'`

2. Determines the row under the cursor from `y // ROW_H`.
3. Reads the hours value for that (row, period) combination.
4. Builds an HTML tooltip with:

   - Resource name (bold), or resource + task name for task rows.
   - Period label.
   - Hours for the cell (bold); in hourly mode also shows the full-day total.

5. Calls `QToolTip.showText(event.globalPos(), tip, self)`.

`leaveEvent` calls `QToolTip.hideText()` to dismiss the tooltip when the cursor
leaves the canvas.

### `_HourModeHeader`

Shown **instead of** `GanttHeader` when `day_width ≥ HOUR_MODE_THRESHOLD`.  Two-row
header:

- **Top row**: date label per working day (`"Mon 24 Apr"`, width-adaptive).
- **Bottom row**: hour slot labels (`8`, `9`, `10` … up to `work_hour_end - 1`), one per hour column.

`configure(project_start, total_days, day_width, work_hour_start, clock_day_span, non_working_slots)` accepts the
calendar-derived hour parameters passed through from `ResourceUsageGraphView`.
Break hours (e.g. lunch) receive a grey background and dimmed label in the bottom row;
hours outside the working window are also greyed when `show_off_hours=True`.

`_configure_header()` calls `self._hdr_area.takeWidget()` /
`self._hdr_area.setWidget()` to swap between the two header types.

### `_WorkBodyColumn`

Fixed 60-px `QWidget` sitting between `_LeftPane` and `_right_scroll` in the body layout.
Paints per-row "Work" labels in a column that mirrors `_DetailsHeaderCell` in the header
row.  Scrolls vertically in sync with `_UsageCanvas` via `vsb.valueChanged → set_scroll_y()`.
By extracting this column from the scrollable canvas, `_right_scroll` and `_hdr_area` start
at the same screen x-position, eliminating the previous horizontal misalignment between day
header labels and day data columns.

### `_UsageHeaderCorner`

Fixed `QWidget` that fills the top-left corner above `_LeftPane`.  Paints the
"Resource Name" and "Work" column labels and a blank nav-bar strip.

### `_DetailsHeaderCell`

Fixed `QWidget` that sits between `_UsageHeaderCorner` and the active calendar
header.  Shows the "Details" label above the narrow label column of `_UsageCanvas`.


## Scroll Synchronisation

| Pair | Direction | Mechanism |
| - | - | - |
| Canvas H → header H | Unidirectional | `right_scroll.hBar.valueChanged → hdr_area.hBar.setValue` |
| Canvas V range → vsb | Range sync | `right_scroll.vBar.rangeChanged → vsb.setRange` |
| Canvas V ↔ vsb | Bidirectional | `blockSignals` not needed; Qt skips same-value `setValue` |
| Canvas V → left pane V | Unidirectional | `right_scroll.vBar.valueChanged → left_scroll.vBar.setValue` |
| vsb → work body col | Unidirectional | `vsb.valueChanged → _work_body_col.set_scroll_y` |


## Integration with `ui.py`

| Aspect | Detail |
| - | - |
| Tab index | 6 |
| Tab label | "Resource Usage" |
| Ribbon tab | 1 (RESOURCE) |
| `_APP_TO_RIBBON_TAB` entry | `6: 1` |
| `_RIBBON_APP_TABS` entry | `6` added to `{1: {1, 4, 6}}` |
| `_TAB_TO_HISTORY_VIEW` entry | `6: 'resources'` |
| Zoom slider | `_on_zoom_slider` calls `resource_usage_graph_view.set_day_width(value)` |
| Show Sundays | `toggle_show_sundays` calls `resource_usage_graph_view.set_show_sundays(val)` |
| Show Off-Hours | Options → Show &Off-Hours (checkable); `toggle_show_off_hours` calls `resource_usage_graph_view.set_show_off_hours(val)`; persisted to QSettings `"usage/show_off_hours"` |
| Load project | `_refresh_all_views` calls `resource_usage_graph_view.load_project(project)` |
| Lazy reload | `_on_tab_changed` reloads the view when tab index 6 becomes active |
| Switch action | `MainWindow.switch_to_resource_usage_graph()` → `tabs.setCurrentIndex(6)` |
| Ribbon button | "Resource Usage" button in the RESOURCE ribbon tab (View group) |
