# ui.py

Implements `MainWindow`, the top-level application window.

## Class: `MainWindow`

Extends `QMainWindow`.

### Construction

```python
MainWindow(logic: ProjectLogic, file_handler: ProjectFileHandler)
```

Sets up every UI component in `__init__`:

1. Creates all six views (`TaskView`, `GanttView`, `ResourceView`, `DependencyView`, `BaselineView`, `TeamPlannerView`, `TaskSheetView`).
2. Connects cross-view signals (see **Signal Wiring** below).
3. Builds the **Gantt Chart** tab as a `QSplitter` (task table left, Gantt right).
4. Wraps all tabs in a `QTabWidget` (tab bar hidden — navigation is via the ribbon).
5. Creates `ProjectMenuBar` and `ProjectToolBar` (with embedded `ProjectRibbon`).
6. Adds the status bar with task/resource counts (left) and a zoom slider (right).
7. Creates `TimelineView`, starts it collapsed (`_set_collapsed(True)`), calls `timeline_view.register(self)`, and wires `gantt_view.set_timeline_view(timeline_view)` and `resource_usage_graph_view.set_timeline_view(timeline_view)`.
8. Assembles the central widget as a `QVBoxLayout` with `TimelineView` above the `QTabWidget`.
9. Restores persistent settings from `QSettings` (`"ProjectOffline" / "ProjectManager"`), including `timeline/visible`.

### Window State Attributes

| Attribute | Type | Description |
| - | - | - |
| `_current_file_path` | `str \| None` | Path of the currently open file |
| `_dirty` | `bool` | `True` when there are unsaved changes |
| `_history` | `HistoryManager` | Per-view undo/redo snapshot manager |
| `_settings` | `QSettings` | Persistent settings store |
| `_settings_manager` | `SettingsManager` | KeePass / Jira credential manager |
| `_last_app_tab_for_ribbon` | `dict[int, int]` | Remembers the last active app tab per ribbon tab index; used to restore the previous view when switching ribbon tabs |
| `_ribbon_driving_tab_switch` | `bool` | Guard flag set to `True` inside `_on_ribbon_tab_changed` while it is programmatically calling `setCurrentIndex()`; prevents `_on_tab_changed` from overriding the ribbon tab or updating `_last_app_tab_for_ribbon` during that call |
| `_active_baseline_number` | `int` | Currently selected reference baseline slot (0–10); updated by `set_active_baseline()` |
| `_comparison_baseline_number` | `int` | Currently selected comparison slot: −1 = current schedule, 0–10 = another baseline slot; updated by `set_comparison_baseline()` |
| `timeline_view` | `TimelineView` | MS-Project-style milestone strip displayed above the `QTabWidget`; collapsed by default |

### Tab Layout

| Index | Tab | Left pane | Right pane |
| - | - | - | - |
| 0 | Gantt Chart | `TaskView` | `GanttView` |
| 1 | Resources | `ResourceView` (full width) | — |
| 2 | Dependencies | `DependencyView` (full width) | — |
| 3 | Baseline | `BaselineView` (full width) | — |
| 4 | Team Planner | `TeamPlannerView` (full width) | — |
| 5 | Task Sheet | `TaskSheetView` (full width) | — |
| 6 | Resource Usage | `ResourceUsageGraphView` (full width) | — |

**Default view on startup:** Tab 5 (Task Sheet) is selected after the toolbar is created.

The central widget uses a `QVBoxLayout`: `TimelineView` is placed **above** the `QTabWidget`. The strip is collapsed to zero height when not in use so it does not consume vertical space.

The tab bar is hidden; navigation uses the ribbon tabs which map as follows:

| Ribbon tab | App tabs managed |
| - | - |
| 0 TASK | 0 Gantt Chart, 2 Dependencies, 3 Baseline, 5 Task Sheet |
| 1 RESOURCE | 1 Resources, 4 Team Planner, 6 Resource Usage Graph |
| 2 REPORT | 0 Gantt Chart |

When the user switches ribbon tabs, `_on_ribbon_tab_changed` restores the last active app tab for that ribbon tab (stored in `_last_app_tab_for_ribbon`).  When the user switches app tabs, `_on_tab_changed` saves the new index into `_last_app_tab_for_ribbon` for the current ribbon tab.

To prevent a feedback loop — where `_on_ribbon_tab_changed` calling `setCurrentIndex()` triggers `_on_tab_changed`, which then calls `_activate_tab()` and overwrites the intended ribbon tab — the `_ribbon_driving_tab_switch` flag is set to `True` with a `try/finally` guard around the `setCurrentIndex()` call.  `_on_tab_changed` skips its ribbon-activation logic and `_last_app_tab_for_ribbon` update while this flag is `True`.

### Task Column Horizontal Scroll Lock

`_HorizontalWheelBlocker` (a `QObject` event filter, defined at module level) is installed on `task_view.viewport()`.  It swallows any `QEvent.Wheel` event whose `angleDelta().x() != 0`, preventing trackpad horizontal gestures from shifting the task-column grid independently of the Gantt chart.

Additionally, `setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)` is applied to `task_view` after construction so the horizontal scrollbar is never visible, and `TaskView.scrollContentsBy()` is overridden to pass `dx=0` to `super()` regardless of what Qt computes.

### Signal Wiring

| Signal | Source | Handler | Effect |
| - | - | - | - |
| `data_changed` | `TaskView` | `_on_task_data_changed` | Reload Gantt, update status bar, push `tasks`+`baseline` snapshots |
| `data_changed` | `TaskView` | `_mark_dirty` | Enable Save |
| `task_reordered` | `TaskView` | `_mark_dirty` | Enable Save |
| `task_reordered` | `TaskView` | `_on_task_reordered` | Push `tasks`+`baseline` snapshots |
| `selection_changed` | `TaskView` | `_on_task_selection_changed` | Enable/disable Delete button |
| `data_changed` | `TaskSheetView` | `_on_task_sheet_data_changed` | Reload GanttView + TaskView + TaskSheetView; update status bar; push `tasks`+`baseline` snapshots |
| `data_changed` | `TaskSheetView` | `_mark_dirty` | Enable Save |
| `data_changed` | `ResourceView` | `_on_resource_data_changed` | Reload resource/gantt/task views |
| `data_changed` | `ResourceView` | `_mark_dirty` | Enable Save |
| `data_changed` | `DependencyView` | `_on_dependency_data_changed` | Reload dependency / Gantt |
| `data_changed` | `DependencyView` | `_mark_dirty` | Enable Save |
| `task_moved` | `GanttView` | `_on_gantt_task_moved` | Shift task dates (work-hour arithmetic in hourly mode, day-snap logic in day mode), push `tasks`+`baseline` snapshots, refresh all |
| `task_edited` | `GanttView` | `_on_gantt_task_edited` | Reload Gantt + task view, push `tasks`+`baseline` snapshots |
| `zoom_changed` | `GanttView` | `_on_gantt_zoom_changed` | Sync zoom label + slider |
| `show_in_gantt` | `TaskView` | `_on_show_task_in_gantt` | Scroll `GanttView` horizontally to the task's start date (all zoom modes; hourly mode uses working-day index to compute pixel offset) |
| `task_edited` | `ResourceUsageGraphView` | `_on_resource_usage_task_edited` | Reload `GanttView`, `TaskView`, `ResourceUsageGraphView`, and `TaskSheetView`; mark project dirty; push `tasks`+`baseline` snapshots |
| `verticalScrollBar.valueChanged` | `TaskView` ↔ `GanttView` | (direct) | Keep panes scroll-locked |
| `data_changed` | `TimelineView` | `_on_timeline_data_changed` | Auto-save `<basename>.timeline.json` sidecar |
| `remove_from_canvas_requested` | `TimelineView` | `_on_timeline_remove_from_canvas` | Remove the bar/diamond the user right-clicked; triggers `data_changed` |
| `timeline_toggle_requested` | `TaskView` / `TaskSheetView` | `_on_timeline_toggle` | Add or remove selected task / milestone from the Timeline strip |
| `split_task_requested` | `TaskView` / `TaskSheetView` | `split_task_for_task` | `canvas.split_task()` (via `_do_split_interactive`) → save `.splits.json` sidecar → repaint |
| `merge_task_requested` | `TaskView` / `TaskSheetView` | `merge_task_for_task` | `gantt_view.merge_task()` → emit `task_edited` → repaint Team Planner |

### Status Bar

The left side shows a live count:

```
Tasks: N  |  Critical: N  |  Resources: N
```

The right side has a zoom control widget (`self._zoom_widget`) that is shown or
hidden automatically depending on the active view:

- Percentage label (`100%`)
- Zoom-out button `−`
- `QSlider` (range `DAY_WIDTH_MIN … DAY_WIDTH_MAX`, default `DAY_WIDTH_DEF`)
- Zoom-in button `+`

The set of views that show the zoom widget is controlled by the class-level
`_ZOOM_APP_TABS: frozenset` (default: `{0, 4, 6}` — Gantt Chart, Team Planner,
Resource Usage Graph).  Add or remove app-tab indices there to change which
views expose the zoom control.

### Ribbon Integration

`_on_tab_changed` calls two ribbon methods on every view switch:

| Method | Effect |
| - | - |
| `ribbon.highlight_view_button(idx)` | Checks the active view’s ribbon button; unchecks all others |
| `ribbon.update_button_visibility(idx)` | Hides ribbon groups not applicable to the current view (e.g. Add/Delete Resource and Sync Calendar are hidden for Resource Usage Graph) |

See `ribbon.py` for the configuration dictionaries (`_view_btns_by_app_tab`,
`_toggle_groups`, `_hidden_groups_by_app_tab`).

### Persistent Settings (QSettings keys)

| Key | Type | Description |
| - | - | - |
| `gantt/show_resource_units` | `bool` | Show resource unit % on Gantt bars |
| `gantt/show_sundays` | `bool` | Show Sunday columns |
| `usage/show_off_hours` | `bool` | Show off-hours columns in hourly Resource Usage / Gantt / Team Planner views |
| `timeline/visible` | `bool` | Whether the Timeline strip is currently shown |
| `recentFiles` | `list[str]` | Up to 5 recently opened file paths |

`zero_float_critical` is stored via `SettingsManager.set_zero_float_critical()` /
`get_zero_float_critical()`.

### Keyboard Shortcuts

| Shortcut | Action |
| - | - |
| `Ctrl+Z` | Undo the last action on the active tab's history stack |
| `Ctrl+Y` | Redo the next action on the active tab's history stack |
| `Ctrl+=` / `Ctrl++` | Zoom in |
| `Ctrl+-` | Zoom out |
| `Ctrl+D` | Debug dump — writes a timestamped `debug_project_dump_<ts>.json` to `cwd`; **no-op unless `--debug` was passed at startup** |

### Dirty-state Tracking

`_mark_dirty()` sets `_dirty = True`, enables **Save** in menu and toolbar, and
appends `" *"` to the window title.  `_mark_clean()` reverses this after a
successful save or load.

### Baseline Actions

All baseline actions live in `MainWindow` rather than `dialogs.py` because they need
access to both the live project and the ribbon state.

| Method | Description |
| - | - |
| `set_baseline()` | Opens the **Set Baseline** dialog.  Two radio options: *Create new* (uses the first free slot 0–10) and *Overwrite* (combo of existing slots with capture dates).  Calls `baseline_manager.set_baseline()`, then `_after_baseline_change()`.  Does **not** switch `_active_baseline_number` to the new slot. |
| `clear_baseline()` | Opens the **Clear Baselines** table dialog: a `QTableWidget` with one row per active baseline showing Name, Captured-at date, and a Delete button.  Each delete calls `baseline_manager.clear_baseline()`, repopulates the table, and calls `_after_baseline_change()`.  Dialog stays open until closed manually. |
| `set_active_baseline(number)` | Stores `_active_baseline_number`, updates `GanttView` baseline strip, and refreshes `BaselineView`.  Called by the Ref: ribbon combo. |
| `set_comparison_baseline(number)` | Stores `_comparison_baseline_number` (clamped to −1…10) and calls `baseline_view.set_comparison_baseline()`.  Called by the vs.: ribbon combo. |
| `_after_baseline_change()` | Syncs the Ref: ribbon combo with `_active_baseline_number` (using `blockSignals`), repopulates the vs.: combo via `ribbon.update_baseline_list()`, refreshes `BaselineView`, and calls `gantt_view.canvas.set_baseline_number()`. |
| `toggle_gantt_diff_bars(checked)` | Forwards to `gantt_view.canvas.set_show_baseline(checked)` |
| `toggle_gantt_diff_duration(checked)` | Forwards to `baseline_view.set_show_duration_diff(checked)` |
| `toggle_gantt_diff_start(checked)` | Forwards to `baseline_view.set_show_start_diff(checked)` |
| `toggle_gantt_diff_finish(checked)` | Forwards to `baseline_view.set_show_finish_diff(checked)` |

### Drag Behaviour — `_on_gantt_task_moved`

The handler branches on whether the Gantt canvas is in **hourly mode** (`day_width ≥ HOUR_MODE_THRESHOLD`).

**Hourly mode** (no snap dialog, sub-day precision):

1. `delta` is a work-hour slot count (pixels ÷ `day_width`).
2. `_shift_ldt(java_ldt)` converts the slot delta to a `LocalDateTime` by inverting `datetime_to_hourly_x` — it computes a new working-day index and intra-day hour, then walks the QDate calendar forward/backward by that many Mon–Fri days, skipping weekends.
3. The task finish is derived from `new_start` + the MPXJ working duration via `_add_working_hours()`, which walks forward through working days honouring the work-hour window (e.g. a 1d task starting at 15:00 finishes at 15:00 the next working day, not at midnight).
4. Duration units are read from `getDuration().getUnits()` as a string; `HOUR` stays as-is, `WEEK`/`MONTH` multiply by `5×clock_span` / `20×clock_span`, everything else (including the `"d"` abbreviation) is treated as days and multiplied by `clock_span`.
5. Critical path is recomputed (`recompute_critical=True`) and all views refreshed.

**Day mode**:

1. The new start date is computed as `old_start + delta_days`.
2. If the new start lands on a non-working day (weekend / holiday), a `NonWorkingDayDialog` prompts the user to snap to the next working day or keep the literal date.
3. The task finish is recomputed from the new start + duration (skipping weekends), rather than simply shifting by `delta_days`.
4. Every predecessor `Relation`'s lag is adjusted by `delta_days` so the network gap is preserved.
5. All views are refreshed and the project is marked dirty.

### Public Action Methods

| Method | Trigger | Description |
| - | - | - |
| `new_project()` | File → New | Create an empty `ProjectFile`, refresh all views, then immediately call `open_project_info()` so the user sets mandatory start/end dates before any tasks are added — prevents new tasks being incorrectly flagged as critical on an empty calendar |
| `open_project()` | File → Open… | File dialog → `open_project_file()` |
| `open_project_file(path)` | `--open` arg / Recent Files | Load file, refresh all views |
| `save_project()` | File → Save | Smart save: overwrite XML or open Save As for MPP/new |
| `save_project_as()` | File → Save As… | Always opens Save As dialog |
| `close_project()` | File → Close | If `_dirty`, prompts Save / Discard / Cancel; clears the in-memory project, resets `_current_file_path` to `None`, calls `gantt_view.clear_splits()`, refreshes all views and clears undo history |
| `import_plantuml()` | File → Import → PlantUML Gantt… | Parse `.puml` and open as project |
| `export_gantt_svg()` | File → Export → Complete SVG | Export full Gantt to SVG |
| `export_resource_gantt_svg()` | File → Export → Resource SVGs | One SVG per resource to a folder |
| `export_gantt_plantuml()` | File → Export → PlantUML | Export Gantt as `.puml` |
| `zoom_in()` / `zoom_out()` | Ctrl+= / Ctrl+- | Zoom the Gantt canvas |
| `_undo()` | Ctrl+Z | Undo last action on the active tab's history stack |
| `_redo()` | Ctrl+Y | Redo next action on the active tab's history stack |
| `add_entry()` | Ins key / ribbon | Dispatch insert to the active view; **no-op if no project is open** (ribbon buttons are disabled in that state) |
| `delete_entry()` | Del key / ribbon | Dispatch delete to the active view |
| `switch_to_gantt()` | Ribbon / View | Activate Gantt Chart tab |
| `switch_to_resources()` | Ribbon / View | Activate Resources tab |
| `switch_to_dependencies()` | Ribbon / View | Activate Dependencies tab |
| `switch_to_baseline()` | Ribbon / View | Activate Baseline tab |
| `switch_to_task_sheet()` | Ribbon Sheet group | Activate Task Sheet tab (tab 5) |
| `open_project_info()` | Project → Project Information… | Open `ProjectInfoDialog` |
| `open_keepass_settings()` | Project → KeePass Configuration… | Open `KeePassConfigDialog` |
| `open_jira_settings()` | Project → Jira Servers… | Open `JiraServersDialog` |
| `toggle_resource_units(checked)` | Options menu | Toggle + persist resource units display |
| `toggle_show_sundays(checked)` | Options menu | Toggle + persist Sunday column display |
| `toggle_zero_float_critical(checked)` | Options menu | Toggle zero-float critical mode on Gantt, Task Sheet, and Team Planner; persists via `SettingsManager` |
| `_on_show_task_in_gantt(task)` | `TaskView.show_in_gantt` signal | Reads `task.getStart()`, converts to `QDate`, calls `gantt_view.scroll_to_date(date)` so the task bar becomes visible; no tab switch |
| `_on_resource_usage_task_edited()` | `ResourceUsageGraphView.task_edited` signal | Reloads `GanttView`, `TaskView`, `ResourceUsageGraphView`, and `TaskSheetView` with `preserve_scroll=False`; marks project dirty; pushes `tasks`+`baseline` undo snapshots |
| `_debug_dump()` | `Ctrl+D` | No-op unless `--debug` active; collects UI state + project data and writes `debug_project_dump_<timestamp>.json` via `app_debug.dump_project_state()` |

### Timeline Methods

| Method | Description |
| - | - |
| `toggle_timeline(checked)` | Called by **Options → Show Timeline Strip**.  Saves `timeline/visible` to `QSettings`, updates the menu checkmark, and calls `_update_timeline_visibility()`. |
| `_update_timeline_visibility()` | Calls `timeline_view._set_collapsed(not (tl_on and idx in _VIEWS_SHOWING_TIMELINE))` to show/hide the strip for the active tab. |
| `changeEvent(event)` | Overrides `QMainWindow.changeEvent`; on `QEvent.WindowStateChange` (maximize / restore) posts `_on_window_state_settled` via `QTimer.singleShot(0, …)` so the layout re-applies after Qt settles the new window geometry. |
| `_on_window_state_settled()` | Calls `_update_timeline_visibility()` and `statusBar().raise_()` to enforce stacking order after a window-state change. |
| `_on_timeline_data_changed()` | Slot wired to `TimelineView.data_changed`; calls `_save_timeline_json()`. |
| `_on_timeline_remove_from_canvas(task_id, is_milestone)` | Slot wired to `TimelineView.remove_from_canvas_requested`; calls `timeline_view.remove_task(task_id)` or `remove_milestone(task_id)`. |
| `_on_timeline_toggle(task_id, is_milestone)` | Slot wired to context-menu signals from `TaskView` / `TaskSheetView`; adds or removes the item from the timeline. |
| `_timeline_json_path()` | Returns `<basename>.timeline.json` for the current file path, or `None` if no file is open. |
| `_save_timeline_json()` | Serialises pinned task/milestone IDs to JSON and writes the sidecar file. |
| `_load_timeline_json()` | Reads the sidecar file and re-pins items after a project load. |

### Split Task Methods

| Method | Description |
| - | - |
| `split_task_for_task(task)` | Top-level split dispatcher. Calls `canvas.split_task(task, split_qdate)` via the interactive split dialog on `GanttCanvas`, saves the `.splits.json` sidecar, and triggers a repaint of both Gantt and Team Planner canvases. The undo snapshot is taken automatically via `task_edited` → `_on_gantt_task_edited` after a successful split. Wired to `split_task_requested` signals from `TaskView` and `TaskSheetView`. |
| `merge_task_for_task(task)` | Top-level merge dispatcher. Calls `gantt_view.merge_task(task)` to remove all splits, emits `task_edited` to reload views (which also pushes the undo snapshot), and updates the Team Planner canvas. Wired to `merge_task_requested` signals from `TaskView` and `TaskSheetView`. |
| `_task_has_splits(task)` | Returns `True` when `task` has ≥ 2 stored split segments in `gantt_canvas._task_splits`. Injected as `_has_splits_fn` into `TaskView` and `TaskSheetView` so context menus can conditionally show **Merge Task Segments**. |
| `_splits_json_path()` | Returns `<basename>.splits.json` for the current file path, or `None` if no file is open. |
| `_save_splits_json()` | Calls `canvas.splits_to_dict()` and writes the result as JSON to the splits sidecar file. Called after every split/merge operation and on every project save. |
| `_load_splits_json()` | Reads the sidecar file (if present) and calls `canvas.load_splits_from_dict()`, overriding any MPXJ-native split data. Called after `_load_splits()` on project open. |
| `_write_splits_to_project()` | `pre_serialize` hook registered with `HistoryManager`; called before each undo snapshot is written so the snapshot sees the latest split state. Calls `_save_splits_json()`. |
| `_load_splits()` | Calls `canvas.load_splits_from_project(project)` to read native MPXJ `task.getSplits()` data. Called immediately after `load_project()`; the result is then overridden by `_load_splits_json()` when a sidecar exists. |
