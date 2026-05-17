# Resource Usage Histogram View

> **Screenshot mockup:** [resource_usage_histogram.html](../presentation/screenshots/resource_usage_histogram.html)

## What Is a Resource Usage Histogram?

A **Resource Usage Histogram** is a bar chart strip that visualises the **total
allocated work hours across all resources for each calendar day**.  Each bar's
height is proportional to the combined workload of the entire team on that day.

It answers the question *"Is the team as a whole over- or under-allocated?"* at a
glance, without having to inspect individual resource rows.  Days where the total
exceeds 100 % of available capacity are highlighted in red; everything at or below
capacity is shown in green or amber.

### Typical use-cases

| Use-case | What to look for |
| - | - |
| Capacity planning | Red bars indicate over-allocation that needs re-scheduling or additional resources |
| Sprint / milestone preparation | Flat or low bars before a deadline reveal slack that can absorb scope creep |
| Resource levelling | Spikes show where work is unevenly distributed across the schedule |
| Executive reporting | The histogram gives a one-line load summary below the Team Planner |

### Relation to other views

| View | Shows |
| - | - |
| **Resource Usage Graph** | Per-resource and per-task hours in a spreadsheet-style grid |
| **Team Planner** | Per-resource task bars on a timeline |
| **Resource Usage Histogram** | Aggregate (team total) hours per calendar day — a strip below the Team Planner |


## Implementation

> **Status:** Implemented

### Widget

`ResourceUsageHistogramView` — a `QWidget` in
`src/views/resource_usage_histogram_view.py`, composed of two child widgets:

```
ResourceUsageHistogramView
  ├─ _HistogramLabel   (frozen left column, 160 px — "Resource Usage" label)
  └─ _HistogramCanvas  (scrollable bar chart — shares horizontal scroll with Team Planner)
```

The histogram is embedded **directly below the Team Planner canvas** in `ui.py`
and is synchronised horizontally via the same `QScrollBar` instance that drives
the Team Planner timeline.

### Data Model — `compute_histogram_data()`

The public function `compute_histogram_data(project, start_date, end_date, non_working_dates)` returns a list of dicts, one per calendar day:

```python
{
    'date':            QDate,
    'total_hours':     float,   # allocated hours summed across all resources
    'capacity_hours':  float,   # available hours summed across all resources
    'utilisation_pct': float,   # 0 when capacity_hours == 0
}
```

**Capacity** per day per resource:
- Weekend days (Saturday / Sunday) → 0 h
- Project-level public holidays (passed in `non_working_dates`) → 0 h
- Days covered by a resource's personal calendar vacation exception → 0 h
- All other working days → `work_day_hours` from the project default calendar

**Allocation** per day per resource:
- Summary tasks are excluded
- Each assignment's total work hours are distributed evenly across the working days within the assignment span, respecting the same exclusion rules as capacity

### Colour Coding

| Condition | Bar colour |
| - | - |
| `utilisation ≤ 80 %` | Green (`#348A34`) |
| `80 % < utilisation ≤ 100 %` | Amber (`#FF9A00`) |
| `utilisation > 100 %` | Red (`#CC2222`) |

A dashed blue line marks the 100 % capacity level.

### Settings

| Setting key | Type | Default | Description |
| - | - | - | - |
| `histogram/visible` | `bool` | `false` | Show / hide the histogram strip |

Toggled via **Options → Show Resource Usage Histogram** (checkable menu action).
Persisted via `QSettings`.

### Debug Dump

`src/app_debug.py` includes a `resource_usage_histogram` section:

```json
{
  "resource_usage_histogram": {
    "visible": true,
    "height_px": 120,
    "data": [
      { "date": "2026-05-12", "total_hours": 16.0, "capacity_hours": 16.0, "utilisation_pct": 100.0 },
      { "date": "2026-05-13", "total_hours": 20.0, "capacity_hours": 16.0, "utilisation_pct": 125.0 }
    ]
  }
}
```

### Requirements

| ID | Requirement |
| - | - |
| PO-RES-027 | The system shall provide a Resource Usage Histogram strip below the Team Planner view |
| PO-RES-028 | Bars shall use a three-tier colour scheme: green ≤ 80 %, amber 80–100 %, red > 100 % |
| PO-RES-029 | A dashed horizontal line shall mark the 100 % capacity level |
| PO-RES-030 | Weekends, public holidays, and per-resource vacations shall be excluded from capacity and allocation |
| PO-RES-031 | Summary tasks shall be excluded from allocation calculations |
| PO-RES-032 | Assignment hours shall be distributed evenly across all working days within the assignment span |
| PO-RES-033 | A Format menu toggle shall show / hide the histogram strip; visibility shall be persisted |
| PO-RES-034 | The histogram scroll position and day-width shall be synchronised with the Team Planner |


## File Locations

| Path | Purpose |
| - | - |
| `src/views/resource_usage_histogram_view.py` | Widget implementation (`ResourceUsageHistogramView`, `compute_histogram_data()`) |
| `src/ui.py` | Instantiation and embedding below Team Planner; `toggle_histogram()` |
| `src/menu.py` | `_show_histogram_act` checkable QAction; `set_show_histogram_checked()` |
| `src/app_debug.py` | Debug dump `resource_usage_histogram` section |
| `tests/pytests/test_histogram_view.py` | Unit tests for `compute_histogram_data()` (15 tests) |


A **Resource Usage Histogram** is a bar chart strip that visualises the **total
allocated work hours across all resources for each time unit** (day, week, month,
or hour).  Each bar's height is proportional to the combined workload of the
entire team at that point in time.

It answers the question *"Is the team as a whole over- or under-allocated?"* at a
glance, without having to inspect individual resource rows.  Days (or weeks, etc.)
where the total exceeds 100 % of available capacity are highlighted in red;
everything at or below capacity is shown in green or a neutral colour.

### Typical use-cases

| Use-case | What to look for |
| - | - |
| Capacity planning | Red bars indicate over-allocation that needs re-scheduling or additional resources |
| Sprint / milestone preparation | Flat or low bars before a deadline reveal slack that can absorb scope creep |
| Resource levelling | Spikes show where work is unevenly distributed across the schedule |
| Executive reporting | The histogram gives a one-line load summary below the Team Planner |

### Relation to other views

| View | Shows |
| - | - |
| **Resource Usage Graph** | Per-resource and per-task hours in a spreadsheet-style grid |
| **Team Planner** | Per-resource task bars on a timeline |
| **Resource Usage Histogram** | Aggregate (team total) hours per time unit — a strip below the Team Planner |


## Planned Implementation

> **Status:** Planned (Phase 3 — Views & UX, not yet implemented)

### Widget

`ResourceUsageHistogramView` — a new `QWidget` in
`src/views/resource_usage_histogram_view.py`.

### Layout

```
TeamPlannerView  (existing)
─────────────────────────────────────────────────
ResourceUsageHistogramView  (new strip below)
  ├─ _HistogramLeftLabel   (frozen left column: "Work" label, same width as resource column)
  └─ _HistogramCanvas      (scrollable bar chart; shares horizontal scroll with Team Planner)
```

The histogram is embedded **directly below the Team Planner canvas** in `ui.py`
and is synchronised horizontally via the same `QScrollBar` instance that drives
the Team Planner timeline.

### Zoom Levels

The histogram inherits the Team Planner's zoom levels and renders one bar per
time unit:

| Zoom | Bar unit |
| ---- | -------- |
| Monthly | 1 calendar month |
| Weekly | 1 ISO week |
| Daily | 1 calendar day |
| Hourly | 1 work hour |

### Capacity Calculation

For each time unit *t*:

```
total_hours(t)  = Σ  allocated_hours(resource, t)   for all resources
capacity(t)     = Σ  available_hours(resource, t)   for all resources
utilisation(t)  = total_hours(t) / capacity(t)
```

`available_hours(resource, t)` accounts for the resource's personal calendar
(working hours, public holidays, vacations).

### Colour Coding

| Condition | Bar colour |
| - | - |
| `utilisation ≤ 80 %` | Green (`#4CAF50`) |
| `80 % < utilisation ≤ 100 %` | Amber (`#FF9800`) |
| `utilisation > 100 %` | Red (`#F44336`) |

### Settings

| Setting key | Type | Default | Description |
| - | - | - | - |
| `histogram/visible` | `bool` | `true` | Show / hide the histogram strip |
| `histogram/height` | `int` | `120` px | Height of the histogram strip |

Persisted via `SettingsManager` / `QSettings`.

### Debug Dump

`src/app_debug.py` will include a `resource_usage_histogram` section:

```json
{
  "resource_usage_histogram": {
    "visible": true,
    "height_px": 120,
    "data": [
      { "date": "2026-05-12", "total_hours": 16.0, "capacity_hours": 16.0, "utilisation_pct": 100.0 },
      { "date": "2026-05-13", "total_hours": 20.0, "capacity_hours": 16.0, "utilisation_pct": 125.0 }
    ]
  }
}
```

### Requirements

| ID | Requirement |
| - | - |
| PO-HIST-001 | The histogram strip shall be rendered directly below the Team Planner canvas |
| PO-HIST-002 | The histogram shall synchronise its horizontal scroll with the Team Planner |
| PO-HIST-003 | The histogram shall support all four zoom levels (monthly / weekly / daily / hourly) |
| PO-HIST-004 | Bars exceeding 100 % capacity shall be highlighted red |
| PO-HIST-005 | The histogram visibility shall be togglable and persisted via QSettings |
| PO-HIST-006 | The debug dump shall include histogram data (date, total hours, capacity, utilisation) |


## File Locations

| Path | Purpose |
| - | - |
| `src/views/resource_usage_histogram_view.py` | Widget implementation (planned) |
| `src/ui.py` | Instantiation and embedding below Team Planner (planned) |
| `src/settings_manager.py` | Persistence of visibility and height settings (planned) |
| `src/app_debug.py` | Debug dump section (planned) |
