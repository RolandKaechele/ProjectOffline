# hour_mode.py

Shared hourly-zoom infrastructure used by all three timeline views: **GanttView**,
**TeamPlannerView**, and **ResourceUsageGraphView**.

Centralising the working-hour calendar reader, coordinate helpers, and the two-row
header widget here ensures all views stay pixel-perfectly aligned when the user
switches to hourly zoom.


## Constants

| Constant | Value | Description |
| - | - | - |
| `HOUR_MODE_THRESHOLD` | 60 | `day_width` (px/slot) at or above which hourly mode activates |
| `WORK_HOUR_START` | 8 | Fallback first work hour when no calendar is defined (08:00) |
| `WORK_HOUR_END` | 17 | Fallback exclusive end hour (last slot = 16:00–17:00) |
| `WORK_DAY_HOURS` | 9 | `WORK_HOUR_END − WORK_HOUR_START` — default column count per day |


## Function: `read_work_hours(project)`

```python
def read_work_hours(project) -> tuple[int, int, int, frozenset]:
```

Reads the working-hour window from the project's **default calendar**.  It iterates
the five standard weekdays (Mon–Fri) and collects all time ranges defined for the
first working weekday it finds.

### Returns

| Position | Name | Description |
| - | - | - |
| 0 | `work_hour_start` | First clock hour to display (e.g. `9` for 09:00) |
| 1 | `work_hour_end` | Exclusive last clock hour (e.g. `17` for 17:00) |
| 2 | `work_day_hours` | Actual working hours per day (sum of all working ranges) |
| 3 | `non_working_slots` | `frozenset` of clock hours in `[start, end)` that are not worked (e.g. `{12}` for a 12:00–13:00 lunch break) |

Split schedules (e.g. 09:00–12:00 + 13:00–17:00) are handled correctly — `min_start`
and `max_end` define the outer window; `non_working_slots` marks the gap between ranges
as a break.  Falls back to module-level defaults on any MPXJ or Java exception.


## Function: `working_day_count(project_start, total_days)`

```python
def working_day_count(project_start: QDate, total_days: int) -> int:
```

Returns the number of Mon–Fri days in the half-open interval
`[project_start, project_start + total_days)`.  Used to compute the total canvas width
in hourly mode.


## Function: `date_to_working_day_idx(date, project_start)`

```python
def date_to_working_day_idx(date: QDate, project_start: QDate) -> int:
```

Returns how many Mon–Fri days lie **strictly between** `project_start` (inclusive) and
`date` (exclusive).  Weekend days are not counted.

This is the fundamental coordinate function for hourly mode.  Given a working-day index
`wday`, the left pixel edge of that day is:

```
x = wday × clock_day_span × day_width
```

where `clock_day_span` is the number of visible hour columns per day (from
`read_work_hours`) and `day_width` is pixels-per-hour-slot.

> **Vacation x-positions** in TeamPlannerView and ResourceUsageGraphView must use
> this function rather than the calendar-based `_date_to_x()` helper so that
> Saturday/Sunday gaps are skipped correctly.


## Function: `datetime_to_hourly_x(java_datetime, project_start, day_width, work_hour_start, clock_day_span, show_off_hours)`

```python
def datetime_to_hourly_x(java_datetime,
                          project_start: QDate,
                          day_width: int,
                          work_hour_start: int,
                          clock_day_span: int,
                          show_off_hours: bool) -> float:
```

Converts an MPXJ `java.time.LocalDateTime` to a pixel x-coordinate in hourly mode.

### Parameters

| Parameter | Description |
| - | - |
| `java_datetime` | MPXJ `LocalDateTime` (or `None`) |
| `project_start` | `QDate` — left edge of the canvas |
| `day_width` | Pixels per **hour slot** (re-interpretation of the global `day_width` in hourly mode) |
| `work_hour_start` | First visible clock hour when `show_off_hours=False` |
| `clock_day_span` | Number of hour columns per working day |
| `show_off_hours` | When `True`, full 24-hour clock is shown; clamping is disabled |

Returns `0.0` on any error or `None` input.

> **Important — LABEL_WIDTH not included**: The returned x value is relative to
> the left edge of the scrollable canvas content (x = 0 at `project_start`).
> **Callers must add `LABEL_WIDTH` themselves** before using the value for
> painting or hit-testing.  In `GanttCanvas._draw_task_row` (hourly branch) this
> is done as `x1 = LABEL_WIDTH + int(datetime_to_hourly_x(...))`.

### Algorithm

```
wday     = date_to_working_day_idx(date, project_start)
eff_span = 24  (off-hours) or clock_day_span (normal)
slot_frac = (hour − eff_start) + minute / 60
x = wday × eff_span × day_width + slot_frac × day_width
```

When `show_off_hours=False` the hour is clamped to the visible working window before
computing `slot_frac`, so task bars that start before work hours snap to the first
visible slot.


## Class: `HourModeHeader`

```python
class HourModeHeader(QWidget):
```

A two-row `QWidget` used as the scrollable header in hourly zoom mode.  Replaces the
standard `GanttHeader` in all three timeline views when `day_width ≥ HOUR_MODE_THRESHOLD`.

### Constructor

```python
HourModeHeader(header_height=42, header_month_h=22, header_week_h=20, parent=None)
```

| Parameter | Default | Description |
| - | - | - |
| `header_height` | 42 px | Total widget height |
| `header_month_h` | 22 px | Height of the top (date label) row |
| `header_week_h` | 20 px | Height of the bottom (hour number) row |

### `configure(project_start, total_days, day_width, work_hour_start, clock_day_span, non_working_slots, label_width)`

Must be called **before** the widget is inserted into a `QScrollArea` so that
`setFixedSize()` is applied to the correct size before Qt computes the scrollbar
range.

| Parameter | Default | Description |
| - | - | - |
| `project_start` | — | `QDate` — first calendar day of the canvas |
| `total_days` | — | Total calendar days (including weekends) |
| `day_width` | — | Pixels per hour slot |
| `work_hour_start` | `WORK_HOUR_START` | First visible clock hour |
| `clock_day_span` | `WORK_DAY_HOURS` | Number of hour columns per working day |
| `non_working_slots` | `frozenset()` | Clock hours that are breaks (shown in grey) |
| `label_width` | `0` | Width of any frozen-label area to the left (used by ResourceUsageGraphView only) |

`configure()` calls `setFixedSize(total_width, header_height)` and triggers a
`repaint()`.

### Rendering (`paintEvent`)

`paintEvent` iterates calendar days, skips Sat/Sun, and for each working day draws:

**Top row (date label)**

- Alternating light/dark blue band per working day.
- Label text adapts to available width:
  - `day_w > 120 px` → `"Mon 24 Apr 2026"`
  - `day_w > 80 px`  → `"Mon 24 Apr"`
  - Otherwise        → `"24 Apr"`
- Blue vertical divider at the left edge of each day.

**Bottom row (hour labels)**

- One cell per `clock_day_span` hour slot.
- Break hours (in `non_working_slots`) are drawn in a grey cell; all other cells use
  a light blue-white background.
- Hour number is painted when `day_width ≥ 20`.
- Light grey vertical divider between each hour slot.

**Heavy border** — 2 px blue line at the bottom of the widget.

### Configure-before-Swap Pattern

All three views that use `HourModeHeader` follow the same scroll-area swap sequence:

```python
# 1. Configure first — sets the correct fixed size
self._hour_hdr.configure(project_start, total_days, day_width, ...)

# 2. Swap into the scroll area (Qt reads the size immediately on setWidget)
if self._hdr_area.widget() is not self._hour_hdr:
    self._hdr_area.takeWidget()
    self._hdr_area.setWidget(self._hour_hdr)

# 3. Re-sync scrollbar position (Qt may reset it to 0 after a widget swap)
self._hdr_area.horizontalScrollBar().setValue(
    self._canvas_scroll.horizontalScrollBar().value()
)
```

Reversing steps 1 and 2 (configure *after* swap) would let Qt compute the scroll range
from the old, stale widget size and clamp the scrollbar value — visually misaligning the
header columns relative to the canvas columns.


## Usage by Views

| View | Header scroll area | Canvas scroll area | Call site |
| - | - | - | - |
| `GanttView` | `_header_area` | `_scroll_area` | `_sync_header()` |
| `TeamPlannerView` | `_header_area` | `_rows_area` | `_sync_header()` |
| `ResourceUsageGraphView` | `_hdr_area` | `_right_scroll` | `_configure_header()` |

All three views import from `hour_mode`:

```python
from hour_mode import (
    HOUR_MODE_THRESHOLD,
    read_work_hours,
    working_day_count,
    date_to_working_day_idx,
    datetime_to_hourly_x,
    HourModeHeader,
)
```
