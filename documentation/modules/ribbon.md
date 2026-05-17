# ribbon.py

Implements the MS Project-style tab ribbon toolbar used in the main window.

## Helper Classes

### `_SplitToolButton`

Subclass of `QToolButton` that overrides `mousePressEvent` to intercept clicks
on the arrow sub-control (`SC_ToolButtonMenu`) before Qt's popup-grab machinery
activates.  When the arrow is hit (or the whole button in `InstantPopup` mode),
it emits `popup_requested` instead of invoking `showMenu()`.  This ensures no
OS-level mouse grab is ever set, so a single click on any other widget (tab or
button) is sufficient to close the popup.

| Signal | Description |
| - | - |
| `popup_requested` | Emitted when the ▾ arrow (or whole button in InstantPopup) is clicked |

### `_RibbonListDelegate`

`QStyledItemDelegate` for the popup list.  Each row shows:

- An **icon** recoloured from ribbon white-on-transparent to `#2e75b6` (or
  highlighted text colour when selected) via `CompositionMode_DestinationIn`.
- A **bold title** line.
- An optional **smaller subtitle** line in grey (`#666666`).
- A **left accent bar** in `#2e75b6` when the row is selected.

### `_RibbonListPopup`

A plain child `QFrame` (no separate OS window) that acts as a floating listview
popup anchored below a ribbon button.  Constructed with an `actions` list of
`(label, callback[, icon[, subtitle]])` tuples.

**Key design points:**

| Aspect | Implementation |
| - | - |
| No OS window | `QFrame(parent)` — child widget, not `Qt.Popup` or `Qt.Tool` |
| Close on outside click | App-level `eventFilter` installed on `showEvent`, removed on `hideEvent`; maps global click pos to local coords and hides without consuming the event |
| Close on tab/button | `_close_active_ribbon_popup()` called from `_on_tab_clicked` and the main-area click handler of each split-button |
| Toggle | `show_below()` hides immediately if already visible |
| Lazy reparent | On first show, reparented to `anchor.window()` so it overlays the full window rather than being clipped by the ribbon group |
| Icon recolouring | Done in `_RibbonListDelegate.paint()` |

## Class: `ProjectRibbon`

Extends `QWidget`.  Emits action signals instead of calling the parent window
directly; `_call(method)` walks up the parent chain to find the first object
that has the named method and invokes it.

### Signals

| Signal | Arguments | Description |
| - | - | - |
| `ribbon_tab_changed` | `int` — tab index | Emitted when the user clicks a ribbon tab |

### Ribbon Tabs

| Index | Label | Panel content |
| - | - | - |
| 0 | TASK | Sheet (Task Sheet), View (Gantt Chart, Dependencies), Clipboard (Paste / Cut / Copy), Jira (Jira Sync Config, Sync from Jira▾, Sync to Jira▾) |
| 1 | RESOURCE | View (Team Planner, Resource Sheet, Resource Usage), Insert (Add Resource▾)\*, Editing (Delete Resource)\*, Confluence (Calendar Config, Sync Calendar)\*, Jira\* |
| 2 | REPORT | Export (Gantt Export▾, Resource SVG), Timeline (Timeline Export▾), Email (Email Accounts, Email Config) |
| 3 | BASELINE | Reference (Set Baseline▾, Clear Baseline▾, Ref: combo, vs.: combo), Gantt Diff (Show Bars, Duration %, Start Δ, Finish Δ), View (Baseline Table) |
| 4 | VERSION CONTROL | Setup (VCS Config, Register with VCS), Operations (Commit▾, Log, Revert, Branches), Git (Pull▾, Push), SVN (SVN Update▾) |

▾ = split-button (`_SplitToolButton`) — click main area for default action,
click ▾ arrow to open the `_RibbonListPopup` with additional options.

\* These groups are hidden when Resource Usage Graph (app tab 6) is the active view — see **Button-Group Visibility** below.

### Split-Button Popup Entries

| Panel | Button | Default action | Popup entries |
| - | - | - | - |
| TASK → Jira | Sync from Jira | `run_jira_sync` | Sync now (normal), Changed since last sync, Full resync |
| TASK → Jira | Sync to Jira | `run_jira_push` | Sync to Jira (normal), Dry-run preview |
| RESOURCE → Insert | Add Resource | `add_resource` | Add Resource (manual), Add from Active Directory, Add from AD Group |
| REPORT → Export | Gantt Export | `export_gantt_svg` | Gantt SVG, Gantt PlantUML |
| REPORT → Timeline | Timeline Export | `export_timeline_svg` | Timeline SVG, Timeline PlantUML |
| BASELINE → Reference | Set Baseline | `set_baseline` | Set baseline (dialog), Set into next free slot, Set all slots (bulk) |
| BASELINE → Reference | Clear Baseline | `clear_baseline` | Clear baseline (dialog), Clear all baselines |
| VCS → Operations | Commit | `run_vcs_commit` | Commit project file only, Commit all tracked changes |
| VCS → Git | Pull | `run_vcs_pull` | Pull (merge), Pull (rebase), Fetch only |
| VCS → SVN | SVN Update | `run_vcs_svn_update` | Update to HEAD, Update to revision… |

### Tab Visual Style

Ribbon tabs use `QPushButton#RibbonTab` from `stylesheet.py`:

- **Unselected tab**: dark navy background (`#1C3761`), slightly muted white text, with a 2 px bottom accent line in the ribbon-panel gradient colour to anchor it visually.
- **Selected tab**: identical gradient to the ribbon panel below (`#3C71C0 → #2B579A`), border-bottom removed so the tab and panel appear seamlessly connected.
- A `border-top: 1px solid rgba(255,255,255,0.20)` on `#RibbonPanelContainer` provides the thin joining line between the tab row and the panel.

### Active View Button Highlighting

Each view-switching `QToolButton` is `checkable=True`.  When the active app-tab
changes, `highlight_view_button(app_tab_idx)` checks the button for that tab
and unchecks all others.  The checked style (defined in `stylesheet.py`) shows
a light-blue translucent background so the user always knows which view is active.

The mapping is maintained in `_view_btns_by_app_tab` (app-tab index → `QToolButton`):

| App-tab index | View | Ribbon panel |
| - | - | - |
| 0 | Gantt Chart | TASK |
| 1 | Resources | RESOURCE |
| 2 | Dependencies | TASK |
| 3 | Baseline | TASK |
| 4 | Team Planner | RESOURCE |
| 5 | Task Sheet | TASK |
| 6 | Resource Usage Graph | RESOURCE |

### Button-Group Visibility

Some ribbon groups are irrelevant for certain views and are hidden automatically
when that view becomes active.  The mechanism uses two internal collections:

| Collection | Type | Purpose |
| - | - | - |
| `_toggle_groups` | `list[(group, separator)]` | Every group/separator pair that can be toggled.  Populated once at the end of `_build_resource_panel`. |
| `_hidden_groups_by_app_tab` | `dict[int, list]` | Maps an app-tab index to the list of groups that must be **hidden** for that tab.  All other tabs in `_toggle_groups` remain visible. |

**Current rules:**

| App tab | Hidden groups |
| - | - |
| 6 Resource Usage Graph | Insert (Add Resource), Editing (Delete Resource), Confluence (Sync Calendar) |

**How to add a rule** (edit `_build_resource_panel` in `ribbon.py`):

1. Append `(grp, grp.separator_widget())` to `self._toggle_groups` for each new toggleable group.
2. Add `self._hidden_groups_by_app_tab[APP_TAB_IDX] = [grp_a, grp_b, ...]`.

### Button Enable/Disable Logic

| Category | Buttons | Default state | When enabled |
| - | - | - | - |
| `_project_btns` | Task Sheet, Dependencies, Baseline, Insert Task, Delete Task, Team Planner, Resource Sheet, Resource Usage, Add Resource, Delete Resource, all export buttons | Disabled | When a project is open (`set_project_open(True)`) |
| `_selection_btns` | Delete Task, Delete Resource | Disabled | When ≥ 1 row is selected (`set_delete_enabled(True)`) |

### Public Methods

| Method | Description |
| - | - |
| `set_project_open(is_open)` | Enable / disable all project-gated buttons |
| `set_confluence_sync_state(enabled, tooltip)` | Set enabled state and tooltip of the **Sync Calendar** button independently of `set_project_open` (called after loading enterprise custom fields) |
| `set_delete_enabled(enabled)` | Enable / disable the delete button for the active view |
| `update_actions(add_label, del_label, enabled, zoom_enabled)` | Update context-sensitive Insert/Delete button labels and enabled state |
| `highlight_view_button(app_tab_idx)` | Check the view button for the active app tab; uncheck all others |
| `update_button_visibility(app_tab_idx)` | Show/hide ribbon groups according to `_hidden_groups_by_app_tab` |
| `update_baseline_list(active_baselines)` | Repopulate the Ref: and vs.: combos from `{slot: date_str}` dict; preserves current selection where possible |

## Split / Merge Group (reserved)

A `_RibbonGroup("Split")` is built in `_build_task_panel` and stored as
`self._grp_split_task`, but it is **not added to any ribbon panel** — the group
is hidden immediately after creation.  The buttons are still registered in
`_project_btns` so they become enabled/disabled alongside other project-gated
buttons.

| Button | `_call` target | Description |
| - | - | - |
| **Split Task** | `split_task_action` | Open the split-date dialog for the selected task; creates a new segment |
| **Merge Segments** | `merge_task_action` | Remove all splits from the selected task and restore a single bar |

Both actions are accessible via **right-click context menus** in the Gantt Chart
and Team Planner.  The ribbon group is reserved for a future toolbar
customisation feature; when that feature lands, add `grp_split` to the relevant
panel and (if needed) to `_toggle_groups`.

> **Note:** `_grp_split_task` must *not* appear in `_toggle_groups` while it
> remains hidden.  Adding a hidden group to `_toggle_groups` would cause
> `update_button_visibility` to call `setVisible(True)` on it, making it pop up
> as a detached floating window.

## BASELINE Panel

The BASELINE ribbon tab (`RIBBON_BASELINE = 3`) contains three groups:

### Reference group

| Widget | Type | Default action | Drop-down actions |
| - | - | - | - |
| **Set Baseline** ▾ | split-button | `set_baseline` (dialog) | Set baseline (dialog), Set into next free slot, Set all slots (bulk) |
| **Clear Baseline** ▾ | split-button | `clear_baseline` (dialog) | Clear baseline (dialog), Clear all baselines |
| **Ref:** combo | `QComboBox` (min 160 px) | — | Selects the reference baseline slot (index = slot number); calls `set_active_baseline(idx)` on change |
| **vs.:** combo | `QComboBox` (min 160 px) | — | Selects what to compare against: index 0 = `"Current"` (slot −1), index k+1 = slot k; calls `set_comparison_baseline(idx − 1)` on change |

**Set into next free slot** automatically finds the lowest-numbered unoccupied slot (BL-0 through BL-10) and snapshots without showing the dialog.

**Set all slots (bulk)** snapshots the current schedule into all 11 slots simultaneously.

**Clear all baselines** removes all data from all 11 slots simultaneously without showing the dialog.

Both combos are stacked vertically inside a shared container widget (QVBoxLayout with two QHBoxLayout rows, one per combo).  `update_baseline_list()` refreshes them from `baseline_manager.get_active_baselines()` after any set/clear operation.

**Same-slot guard:** when the Ref: combo changes, `_on_baseline_combo_changed` checks if the vs.: combo is set to the same slot.  If so, it silently resets vs.: to index 0 (`"Current"`) and calls `set_comparison_baseline(-1)` to prevent a self-comparison.

### Gantt Diff group

Four checkable `QToolButton` items — all checked by default:

| Button | Calls | Effect |
| - | - | - |
| **Show Bars** | `toggle_gantt_diff_bars(checked)` | Show/hide the baseline reference strip behind Gantt bars |
| **Duration %** | `toggle_gantt_diff_duration(checked)` | Show/hide the three Duration columns in the Baseline table |
| **Start Δ** | `toggle_gantt_diff_start(checked)` | Show/hide the three Start columns in the Baseline table |
| **Finish Δ** | `toggle_gantt_diff_finish(checked)` | Show/hide the three Finish columns in the Baseline table |

### View group

| Button | Description |
| - | - |
| **Baseline Table** | Switches the main content area to `BaselineView` (checkable; highlighted when active) |


## Split-Buttons

Several ribbon buttons are **split-buttons** created by `_RibbonGroup.add_menu_button()`.
Clicking the main face area invokes the `default_slot`; clicking the small ▾
arrow opens a `QMenu` of additional actions.

| Ribbon tab | Group | Button | Default slot | Drop-down entries |
| - | - | - | - | - |
| TASK | Jira | Sync from Jira | `run_jira_sync` | Sync now (normal) · Changed since last sync · Full resync · Open Jira Config |
| TASK | Jira | Sync to Jira | `run_jira_push` | Sync to Jira (normal) · Dry-run preview · Open Jira Config |
| RESOURCE | Insert | Add Resource | `add_resource` | Add Resource (manual) · Add from Active Directory · Add from AD Group |
| REPORT | Export | Gantt Export | `export_gantt_svg` | Gantt SVG · Gantt PlantUML |
| REPORT | Timeline | Timeline Export | `export_timeline_svg` | Timeline SVG · Timeline PlantUML |
| BASELINE | Reference | Set Baseline | `set_baseline` | Set baseline (dialog) · Set into next free slot · Set all slots (bulk) |
| BASELINE | Reference | Clear Baseline | `clear_baseline` | Clear baseline (dialog) · Clear all baselines |
| VERSION CONTROL | Operations | Commit | `run_vcs_commit` | Commit tracked changes · Commit all tracked changes |
| VERSION CONTROL | Git | Pull | `run_vcs_pull` | Pull (merge) · Pull (rebase) · Fetch only |
| VERSION CONTROL | SVN | SVN Update | `run_vcs_svn_update` | SVN Update (normal) · SVN Cleanup + Update |

**"Changed since last sync"** invokes `run_jira_sync_changed_since` → `run_sync(force_incremental=True)`.

**"Full resync"** invokes `run_jira_sync_full_resync` → `run_sync(force_full_resync=True)`.

**"Dry-run preview"** invokes `run_jira_push_dry_run` → `run_push_to_jira(dry_run=True)`, then shows `JiraPushPreviewDialog`.

**"Commit all tracked changes"** overrides `vcs/auto_commit_scope` for that single operation.

**"Fetch only"** calls `git_fetch()` in `VcsWorker` (operation code `"fetch"`) without merging.

## Class: `_RibbonGroup`

Internal helper widget: a `QVBoxLayout` with a row of `QToolButton` items at
the top, a group label at the bottom, and a `QFrame` vertical separator on the
right side.

### `add_button(text, tooltip, slot=None, checkable=False, icon=None) → QToolButton`

Creates and adds a `QToolButton` to the group's button row.  Returns the button
for external enable/disable or checked-state management.

### `add_menu_button(text, tooltip, actions, default_slot=None, icon=None, popup_mode=None) → QToolButton`

Creates and adds a split-button (`QToolButton.MenuButtonPopup` mode).  Each
element of `actions` is a `(label, callback)` or `(label, callback, icon)` tuple
and becomes one `QAction` in the attached `QMenu`.  If `default_slot` is `None`,
the first action's callback is used as the main-click handler.


## Class: `_RibbonPanel`

Internal container for one ribbon tab's content.  Uses a `QHBoxLayout` with a
trailing stretch.

### `add_group(group: _RibbonGroup)`

Inserts the group (and its separator widget) before the trailing stretch.
