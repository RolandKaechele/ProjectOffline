# app_tabs.py

Centralises all named integer constants for `QTabWidget` (app) tab indices and
ribbon tab indices.  Every module that needs to reference a specific tab imports
the relevant constant from here rather than using magic numbers.

## App Tab Constants

| Constant | Value | View |
| - | - | - |
| `TAB_GANTT` | `0` | Gantt Chart (`TaskView` + `GanttView` splitter) |
| `TAB_RESOURCES` | `1` | Resource Sheet |
| `TAB_DEPENDENCIES` | `2` | Dependencies |
| `TAB_BASELINE` | `3` | Baseline Tracking |
| `TAB_TEAM_PLANNER` | `4` | Team Planner |
| `TAB_TASK_SHEET` | `5` | Task Sheet ← default view on startup |
| `TAB_RESOURCE_USAGE` | `6` | Resource Usage Graph |

The order matches the `QTabWidget.addTab()` calls in `MainWindow.__init__` in
`ui.py`.

## Ribbon Tab Constants

| Constant | Value | Label |
| - | - | - |
| `RIBBON_TASK` | `0` | TASK |
| `RIBBON_RESOURCE` | `1` | RESOURCE |
| `RIBBON_REPORT` | `2` | REPORT |

The order matches `ProjectRibbon.TAB_NAMES` in `ribbon.py`.

## How to Add a New View

1. Add a `TAB_*` constant here (next free integer).
2. Add the corresponding `addTab()` call in `MainWindow.__init__` in `ui.py`.
3. Update the dictionaries in `ui.py`:
   - `_TAB_LABELS`
   - `_ZOOM_APP_TABS` (if the view uses the zoom slider)
   - `_APP_TO_RIBBON_TAB`
   - `_RIBBON_APP_TABS`
   - `_TAB_TO_HISTORY_VIEW`
   - `_last_app_tab_for_ribbon`
4. Update `_view_btns_by_app_tab` and `_hidden_groups_by_app_tab` in `ribbon.py`
   if the view needs a ribbon button or changes button visibility.
