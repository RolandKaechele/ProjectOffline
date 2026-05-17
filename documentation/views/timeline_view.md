# timeline_view.py

Implements the **Timeline strip** — a compact, fixed-height bar displayed *above* the
`QTabWidget` in the main window.  The strip mirrors Microsoft Project's Timeline view:
it shows the full project span, pinned task bars and milestone diamonds on a condensed
time axis, providing an executive-friendly overview that fits on a single slide or
printout.


## Layout Overview

```
TimelineView  (QWidget, fixed height = FIXED_HEIGHT px)
  ├─ _header_widget   (GanttHeader — month + day bands, scrolls with canvas)
  └─ _TimelineCanvas  (QPainter-rendered canvas)
        ├─ project span bar   (light blue background bar)
        ├─ task bars          (colour-cycled filled rects, label centred)
        └─ milestone diamonds (rotated squares, label below)
```

Horizontal scroll is shared: the canvas drives the header via
`horizontalScrollBar.valueChanged`.


## Layout Constants

| Constant | Value | Description |
| - | - | - |
| `FIXED_HEIGHT` | 178 px | Total widget height (`HEADER_HEIGHT + TOTAL_CANVAS_H`) |
| `HEADER_HEIGHT` | 42 px | Two-row GanttHeader (month band + day band) |
| `TOTAL_CANVAS_H` | 136 px | Canvas height |
| `ROW_H` | 28 px | Height of a single task/milestone row |
| `PROJECT_BAR_H` | 14 px | Height of the project-span background bar |
| `TASK_AREA_H` | 108 px | Vertical space available for task + milestone rows |
| `TASK_LANE_H` | 24 px | Height of each task lane (bar + vertical padding) |
| `MILESTONE_D` | 14 px | Diameter (diagonal) of a milestone diamond |


## Visibility Management

`TimelineView` is embedded in a `QVBoxLayout` above the `QTabWidget`.  Visibility is
controlled via `_set_collapsed(bool)` rather than `setVisible()` directly, so the
`QVBoxLayout` can collapse to zero height:

```python
def _set_collapsed(self, collapsed: bool):
    if collapsed:
        self.setMaximumHeight(0)
        self.setMinimumHeight(0)
        self.setVisible(False)
    else:
        self.setMinimumHeight(self._fixed_h)
        self.setMaximumHeight(self._fixed_h)
        self.setVisible(True)
```

`MainWindow.changeEvent` defers a call to `_on_window_state_settled` via
`QTimer.singleShot(0, …)` after a maximize / restore event so the layout re-applies
once Qt has fully settled the new window geometry.

### Which tabs show the strip

`_VIEWS_SHOWING_TIMELINE` lists the app-tab indices on which the strip appears when
enabled via **Options → Show Timeline Strip** (default: `{0, 4}` — Gantt Chart and
Team Planner).

`_SOURCE_VIEWS_WITH_CONTEXT_MENU` lists the app-tab indices whose task rows provide
"Show in Timeline" context-menu entries (default: `{0, 5}` — Gantt Chart and Task
Sheet).


## Registration API

```python
TimelineView.register(main_window)
```

Called once during `MainWindow.__init__` after the widget is embedded.  Connects:

- `data_changed` → `MainWindow._on_timeline_data_changed`
- `remove_from_canvas_requested` → `MainWindow._on_timeline_remove_from_canvas`

Also stores `self._main_window = main_window`.


## Signals

| Signal | Signature | Description |
| - | - | - |
| `data_changed` | `()` | Emitted whenever the pinned-item set changes (add, remove, load). |
| `remove_from_canvas_requested` | `(int, bool)` | Emitted when the user right-clicks a bar or diamond and chooses **Remove from Timeline**. Arguments: `task_id`, `is_milestone`. |


## Public API

### Item management

| Method | Description |
| - | - |
| `add_task(task)` | Pin a task bar to the strip. `task` is an MPXJ `Task` object. No-op if already pinned. Emits `data_changed`. |
| `remove_task(task_id)` | Unpin the task with the given integer ID. No-op if not pinned. Emits `data_changed`. |
| `add_milestone(task)` | Pin a milestone diamond. No-op if already pinned. Emits `data_changed`. |
| `remove_milestone(task_id)` | Unpin the milestone. No-op if not pinned. Emits `data_changed`. |
| `is_task_pinned(task_id) → bool` | Returns `True` if a task bar with this integer ID is pinned. |
| `is_milestone_pinned(task_id) → bool` | Returns `True` if a milestone diamond with this integer ID is pinned. |
| `pinned_task_ids() → list[int]` | Returns all currently pinned task IDs. |
| `pinned_milestone_ids() → list[int]` | Returns all currently pinned milestone IDs. |

### Project loading

| Method | Description |
| - | - |
| `load_project(project)` | Clears all pinned items and stores the project reference for date-range calculations. Does **not** re-pin; the caller is responsible for calling `_load_timeline_json()` afterwards. |
| `set_date_range(start, end)` | Sets the visible date range explicitly (e.g. to match the Gantt chart's visible window). |

### Export

| Method | Description |
| - | - |
| `export_svg(path)` | Renders the current strip contents to an SVG file at `path`. |
| `export_plantuml(path)` | Writes a `@startuml … @enduml` PlantUML file with `concise` timeline syntax to `path`. |


## JSON Sidecar

Pinned task and milestone IDs are persisted in a JSON file alongside the project file:

```
<basename>.timeline.json
```

**Format:**

```json
{
    "tasks": [1, 3, 7],
    "milestones": [5]
}
```

The sidecar is written automatically via `MainWindow._save_timeline_json()` every time
`data_changed` is emitted (i.e. on every pin/unpin), and is also saved on every
`File → Save` / `File → Save As…` operation.  It is loaded via
`MainWindow._load_timeline_json()` immediately after `_refresh_all_views()` on project
open.


## Context Menus

### Right-click on a bar or diamond (canvas context menu)

Right-clicking a pinned task bar or milestone diamond on the canvas opens a small
context menu with a single item: **Remove from Timeline**.  Choosing it emits
`remove_from_canvas_requested(task_id, is_milestone)`.

### Source-view context menus

In views listed in `_SOURCE_VIEWS_WITH_CONTEXT_MENU` (Gantt Chart and Task Sheet),
right-clicking a task row shows:

- **Add to Timeline** — if the task is not currently pinned.
- **Remove from Timeline** — if the task is already pinned.

These entries emit `timeline_toggle_requested(task_id, is_milestone)`, which is handled
by `MainWindow._on_timeline_toggle`.

### TaskDialog checkbox

When `TaskDialog` is opened from `GanttView` or `ResourceUsageGraphView`, the
`timeline_view` argument is supplied.  The General tab then shows a **Show in Timeline**
checkbox, pre-checked if the task/milestone is already pinned.  On OK the dialog
pins or unpins accordingly.
