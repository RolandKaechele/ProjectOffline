# Architecture Overview

This document describes the high-level architecture of Project Offline and how the major modules interact.

## Module Map

```
main.py
  ├── _find_and_configure_jdk()  — bundled-first: searches <exe_dir>/jdk then tools/java;
  │                                 sets JAVA_HOME + prepends bin/ to PATH;
  │                                 falls back to system Java only when no bundled JDK found
  ├── _find_and_configure_git()  — bundled-first: searches <exe_dir>/git/cmd then tools/git/cmd;
  │                                 prepends to PATH; falls back to shutil.which("git.exe")
  ├── _find_and_configure_svn()  — bundled-first: searches <exe_dir>/svn then tools/svn;
  │                                 prepends to PATH; falls back to shutil.which("svn.exe")
  └── creates ProjectLogic, ProjectFileHandler, MainWindow

ui.py  (MainWindow)
  ├── logic.py          (ProjectLogic)
  ├── file_handler.py   (ProjectFileHandler)
  ├── app_debug.py      (debug flag + project-state dump — enabled by --debug)
  ├── app_tabs.py       (TAB_* and RIBBON_* named constants for tab indices)
  ├── menu.py           (ProjectMenuBar)
  ├── toolbar.py        (ProjectToolBar)
  │     └── ribbon.py       (ProjectRibbon — tab ribbon with button groups;
  │           │               tabs: TASK / RESOURCE / REPORT / BASELINE / VERSION CONTROL;
  │           │               VERSION CONTROL tab hidden by default, shown only when a VCS
  │           │               repository is detected for the open project)
  │           └── icons.py      (runtime icon factory — glyphs on QPixmap)
  ├── stylesheet.py     (MS_PROJECT_STYLE QSS string)
  ├── views/
  │   ├── hour_mode.py          (shared hourly-zoom infrastructure — constants, calendar reader,
  │   │                          coordinate helpers, HourModeHeader widget)
  │   ├── task_view.py          (TaskView)
  │   ├── gantt_view.py         (GanttView)
  │   ├── resource_view.py      (ResourceView — load/add/delete resources;
  │   │                          add_resource: assigns next resource ID + creates personal
  │   │                          calendar before opening Resource Information dialog; cancel
  │   │                          rollback removes both resource and newly created calendar;
  │   │                          add_resource_from_ad: single-user AD search flow;
  │   │                          add_resources_from_ad_group: group search + member preview +
  │   │                          bulk add with duplicate-name skip summary;
  │   │                          _create_resource_calendar is shared by all add paths and
  │   │                          links personal calendars to the project default calendar
  │   │                          via setParent() when available;
  │   │                          auto-UID: new resources are assigned the smallest positive
  │   │                          integer UID not already in use by any project resource;
  │   │                          delete_selected_resources: removes personal calendar from
  │   │                          project calendar list before deleting the resource so no
  │   │                          orphaned calendars accumulate in the project)
  │   ├── dependency_view.py    (DependencyView)
  │   ├── baseline_view.py      (BaselineView)
  │   ├── team_planner_view.py  (TeamPlannerView — set_splits_ref links its canvas to GanttCanvas._task_splits;
  │   │                          _compute_conflict_data: wraps getUniqueID() in try/except so resources
  │   │                          with unavailable UIDs still get a swimlane and never crash the view;
  │   │                          _get_resource_vacation_blocks: secondary calendar exceptions are
  │   │                          filtered against parent calendar dates to exclude national holidays
  │   │                          already present in the base calendar; only NAMED exceptions (getName()
  │   │                          non-empty and non-whitespace) are added to the parent_dates suppression
  │   │                          set — anonymous entries such as Schulferien blocks are excluded so
  │   │                          that state-specific secondary-calendar holidays sharing the same start
  │   │                          date are not incorrectly hidden; empty exception names fall back to
  │   │                          the secondary calendar name for block labels)
  │   ├── task_sheet_view.py    (TaskSheetView — full-width hierarchical task sheet, default view)
  │   ├── resource_usage_graph_view.py  (ResourceUsageGraphView — day-by-day resource hour grid)
  │   ├── resource_usage_histogram_view.py  (ResourceUsageHistogramView — aggregate histogram strip below the
  │   │                          Team Planner; _HistogramLabel (frozen 160 px label), _HistogramCanvas
  │   │                          (scrollable bar chart); compute_histogram_data() aggregates capacity and
  │   │                          allocation per calendar day across all resources, excluding weekends,
  │   │                          public holidays, and per-resource vacation exceptions; three-tier colour
  │   │                          coding: green ≤ 80 %, amber 80–100 %, red > 100 %; toggled via
  │   │                          Options → Show Resource Usage Histogram; visibility persisted in
  │   │                          QSettings key "histogram/visible")
  │   └── timeline_view.py      (TimelineView — MS-Project-style milestone strip above the tab area)
  │
  │   Note: gantt_view.py owns split/merge logic (split_task, merge_task, get_splits;
  │         SPLIT_GAP_DAYS constant; _task_splits sidecar shared via set_splits_ref;
  │         sidecar file <basename>.splits.json managed by MainWindow)
  │
  ├── holidays.py       (pure-Python holiday engine — german_national_holidays, german_state_extra_holidays,
  │                     france/india/romania/china/japan holiday functions; add_holidays_to_calendar()
  │                     MPXJ helper; internal helpers _easter, _orthodox_easter, _buss_und_bettag,
  │                     _nth_weekday; default_holiday_years() → range(cy−2, cy+13);
  │                     movable dates hardcoded 2018–2040)
  ├── dialogs.py        (TaskDialog — task editing; ResourceDialog — resource editing:
  │                      avatar widget (64 px circular) shown in the General tab: AD thumbnail
  │                      bytes from _resource_thumbnail_store if available, otherwise a
  │                      type-specific fallback emoji rendered via Segoe UI Emoji
  │                      (👷 WORK/blue, 📦 MATERIAL/green, 💰 COST/orange; plain-text
  │                      "WK"/"MT"/"CO" fallback if font missing); avatar redraws when the
  │                      Type combobox changes (if no AD photo is stored);
  │                      _update_ad_btn_visibility() toggles E-Mail label+field,
  │                      Department label+field, and "Look up in AD…" button: visible only
  │                      when Type = WORK, hidden for MATERIAL and COST; called on dialog
  │                      open and on every Type combobox change;
  │                      E-Mail field pre-populated from MPXJ getEmailAddress(), Department
  │                      field from getDepartment(); "Look up in AD…" button placed inline
  │                      next to the email field: calls _do_ad_lookup() via run_indeterminate,
  │                      single result auto-fills both fields, multiple results open
  │                      ADUserSelectDialog, blank name shows an information dialog;
  │                      apply_to_resource() persists email via setEmailAddress(),
  │                      department via setDepartment() (empty string stored as None), and
  │                      resource type via setType(ResourceType.WORK/MATERIAL/COST);
  │                      duplicate-name guard: after dialog is accepted the proposed name is
  │                      checked against all other resources by UID exclusion; if a duplicate
  │                      is found the new resource and its personal calendar are rolled back
  │                      and a warning dialog is shown;
  │                      DependencyDialog, …
  │                      NewProjectCalendarsDialog — optional calendar picker shown after new project
  │                      creation; state/country checkboxes for German federal states and 5 other
  │                      countries; get_selected() → list of (kind, name) tuples;
  │                      ProjectInformationDialog Calendars tab: Base Calendar field is an
  │                      editable QComboBox (default calendar shown first with "★",
  │                      current calendar excluded, saved via setParent());
  │                      _cal_add_holidays: null-safe UID handling — if MPXJ returns a calendar with
  │                      getUniqueID()==None the next available integer UID is derived from existing
  │                      calendars and assigned via setUniqueID() before use)
  ├── progress_worker.py  (WorkerThread(QThread) base; run_with_progress() / run_indeterminate()
  │                        modal-dialog helpers; record_timing() / get_timing_log() — 50-entry
  │                        timing deque; _done guard prevents double-fire from QProgressDialog
  │                        closeEvent)
  ├── baseline_manager.py (set_baseline, clear_baseline, get_active_baselines,
  │                        get_variance, get_variance_between — 11 baseline slots)
  ├── export_gantt.py   (export_gantt_svg, export_resource_gantt_svg, export_gantt_plantuml)
  ├── import_plantuml.py (import_plantuml)
  ├── history_manager.py (HistoryManager — per-view undo/redo snapshot stacks)
  ├── settings_manager.py  (SettingsManager)
  ├── settings_dialogs.py  (KeePassConfigDialog, KeePassNewEntryDialog,
  │                         JiraSyncConfigDialog — two-tab dialog: "Jira → Project" tab
  │                         (server selection, JQL/saved-filter config, field-selection
  │                         checkboxes; _JIRA2PROJECT_FIELD_DEPENDENCIES module-level dict
  │                         wires dependent checkboxes so e.g. jira_status_percent is
  │                         auto-disabled when jira_status is unchecked) + "Project → Jira"
  │                         tab (tab label uses Unicode arrow U+2192; 36 outbound field-map
  │                         rows where the Jira-field input is an editable QComboBox pre-
  │                         populated from _P2J_JIRA_FIELD_SUGGESTIONS; export scope /
  │                         create-update mode / conflict policy / unlinked-task behaviour
  │                         are QComboBox selectors — default export scope is "Changed since
  │                         last sync"; dry-run QCheckBox; issue-type map table, transition
  │                         map table; persisted under "project2jira" sidecar container;
  │                         _validate_project_to_jira_settings enforces required-field rules
  │                         and performs best-effort Jira server capability checks for issue
  │                         types and transitions);
  │                         each tab is wrapped in a QScrollArea (setWidgetResizable=True,
  │                         QFrame.NoFrame) so content scrolls within the tab and the
  │                         dialog height is always constrained to
  │                         availableGeometry().height() − 40 px (chrome buffer), keeping
  │                         the OK/Cancel button row visible on any screen size;
  │                         _center_on_screen() uses min(sizeHint, maximumHeight) to
  │                         position the dialog correctly without it going off-screen,
  │                         JiraServerEditDialog, JiraServersDialog,
  │                         ConfluenceCalendarConfigDialog — auth mode + timezone QComboBox,
  │                         EmailConfigDialog — project-aware dialog: KeePass entry selector
  │                         + account QComboBox (all named SMTP accounts) + "Manage Accounts…"
  │                         button + "Sender (Per-Project)" group: Sender Address QLineEdit +
  │                         "From KeePass…" button (AD lookup of sender address) + Sender Name
  │                         QLineEdit; active account name, sender address, and sender display name
  │                         stored in project sidecar JSON under "Email Active Account" /
  │                         "Email Sender Address" / "Email Sender Name" custom props;
  │                         opened with project=logic.get_data() so _mark_dirty() fires on accept,
  │                         EmailServerEditDialog — add/edit one named SMTP account; fields:
  │                         Name / SMTP Server / SMTP Port / Use TLS only; no Sender Address
  │                         field, no "From KeePass…" button, no Test Connection button;
  │                         sender address is per-project (sidecar), not per account,
  │                         EmailServersDialog — manage list of named SMTP accounts; Add/Edit/Delete/
  │                         Set Active/Move Up/Move Down; list shows "name ★ — server",
  │                         VcsConfigDialog — KeePass entry selector (3-state stack: not configured /
  │                         locked / unlocked), auto-commit enable/template/scope, git.exe/svn.exe
  │                         path overrides with Browse buttons,
  │                         VcsLogDialog — commit log list, diff preview panel, Restore button,
  │                         VcsBranchDialog — Git branch list, new branch creation, branch switch,
  │                         VcsConflictDialog — conflicting files list with Revert Selected action)
  ├── integrations/
  │   ├── keepass_integration.py  (KeePassManager — runtime KeePass session singleton;
  │   │                            unlock/lock/auto-unlock, entry CRUD, key-file generation)
  │   ├── jira_integration.py  (test_connection, get_jira_client, record_filter_test, get_config_summary,
  │   │                         _extract_filter_id, resolve_filter_to_jql;
  │   │                         supports API Token/Password/PAT auth; basic_auth + token_auth;
  │   │                         credential stripping; _last_connection_test and _last_filter_test tracking
  │   │                         for debug dumps; filter value, filter type, and field-checkbox states stored
  │   │                         per-project inside a single "jira2project" JSON container in custom properties;
  │   │                         filter type is "jql" or "filter"; resolve_filter_to_jql fetches JQL
  │   │                         for saved filters via jira.filter(id).jql)
  │   ├── jira_sync.py  (Jira↔Project sync engine — two directions:
  │   │                  ── Jira→Project (run_sync): fetches all issues matching configured filter
  │   │                  via paginated search_issues calls (pages of 100, specific fields only —
  │   │                  no *all to avoid HTTP 504 on large result sets); creates/updates MPXJ tasks
  │   │                  with bare Jira summary as task name (no bracket type prefix); epics become
  │   │                  summary+rollup container tasks; sub-tickets wired via setParentTask;
  │   │                  load_sidecar_task_data / save_sidecar_task_data — persists jira_key→UID
  │   │                  mapping in .custom-props.json sidecar under "task_jira" key;
  │   │                  _issue_type_label, _status_to_percent, _build_jira_key_lookup helpers;
  │   │                  get_last_result() — module-level result dict;
  │   │                  invoked by MainWindow.run_jira_sync() which pushes tasks+resources undo
  │   │                  snapshots after sync so the entire operation is undoable with Ctrl+Z;
  │   │                  ── Project→Jira (run_push_to_jira): reads project2jira config container
  │   │                  from project custom properties; maps MPXJ tasks to Jira field payloads
  │   │                  via _task_to_jira_payload(); creates new Jira issues for unlinked tasks
  │   │                  or updates existing linked issues; applies workflow transitions via
  │   │                  transition_map config; supports conflict detection (prefer_project /
  │   │                  prefer_jira / manual_review policies); sets parent links for hierarchy
  │   │                  export when hierarchy_export.enabled=True; persists push metadata in
  │   │                  sidecar under task_p2j and jira_push_meta; optional auditability sessions
  │   │                  (capped at 20) stored in jira_push_meta.audit_sessions; dry-run mode
  │   │                  collects preview_actions without calling any write API;
  │   │                  _with_retry() helper: exponential backoff on transient errors (429/5xx/
  │   │                  timeout/connection), immediate re-raise on non-transient errors;
  │   │                  get_last_push_result() — module-level result dict with created/updated/
  │   │                  transitioned/skipped/errors/log/preview_actions/dry_run;
  │   │                  invoked by MainWindow.run_jira_push() which shows JiraPushPreviewDialog
  │   │                  when dry_run=True and passes included_task_uids from user selection;
  │   │                  KeePass unlock prompt in both handlers when auth_mode=keepass)
  │   ├── confluence_calendar_integration.py  (ConfluenceCalendarSync — Playwright SSO,
  │   │                                        holiday/vacation import, stale-entry pruning;
  │   │                                        _apply_to_project: multi-day holiday spans
  │   │                                        (end != start) are skipped — only single-day
  │   │                                        events are written to the project default calendar
  │   │                                        to prevent Schulferien blocks from greying out
  │   │                                        entire weeks in the Team Planner)
  │   ├── secondary_calendar_integration.py  (per-resource secondary holiday calendar
  │   │                                       assignments persisted as JSON in project custom
  │   │                                       property "AD Secondary Calendars";
  │   │                                       get_secondary_calendar_map — return full uid→entry dict;
  │   │                                       set_secondary_calendar_for_resource — set/clear entry;
  │   │                                       resolve_secondary_calendar — look up MPXJ calendar object
  │   │                                       by UID then by name; returns None when no mapping, or
  │   │                                       result dict with calendar=None when calendar not found;
  │   │                                       infer_secondary_calendar_from_ad — score installed calendars
  │   │                                       against AD user location fields (city/state/country) and
  │   │                                       return best match; skips personal resource calendars;
  │   │                                       assign_secondary_calendar_from_ad — infer + persist)
  │   ├── ad_integration.py  (is_ad_available, lookup_by_name/email/username,
  │   │                       search_groups, get_group_members,
  │   │                       lookup_by_email_all/lookup_by_username_all — fast-path
  │                       exact-match (mail -eq / Get-ADUser -Identity) with
  │                       wildcard fallback (mail -like / SamAccountName -like),
  │   │                       sync_resources, lookup history ring-buffer;
  │   │                       add_resource_from_ad — ribbon "Add from AD": AD search dialog
  │   │                       (multi-result list), duplicate-name guard (case-insensitive,
  │   │                       hard block), resource ID assigned immediately via setID(),
  │   │                       personal calendar created through shared
  │   │                       _create_resource_calendar path;
  │   │                       ADGroupSearchDialog + group-member preview used by
  │   │                       add_resources_from_ad_group() for bulk resource creation;
  │   │                       result dicts include city (l), state (st), country (co) LDAP fields;
  │   │                       add_resource_from_ad calls assign_secondary_calendar_from_ad() after
  │   │                       creating the resource to auto-assign a regional holiday calendar;
  │   │                       PowerShell Get-ADUser — no LDAP dependency)
  │   └── email_integration.py  (send_email, test_connection, is_configured — all accept optional
  │                              config: dict parameter so a caller can target a specific account;
  │                              _resolve_config: falls back to get_active_email_config() then legacy
  │                              QSettings single-config keys for backward compat;  │                          _get_sender_address(config): returns plain address or "Name <address>"
  │                          (RFC 2822, via email.utils.formataddr) when config["sender_name"] is set;  │                              get_config_summary: returns legacy keys AND multi-config keys
  │                              num_configs/active_config_name/active_configured/configs list;
  │                              SMTP with KeePass credential retrieval; email config summary
  │                              for debug dumps without exposing passwords)
  │   └── version_control_integration.py  (detect_repo — walks upward for .git/.svn;
  │                              init(project_file_path) / reset() — called on project open/close;
  │                              commit, get_log, branch_list/create/switch, pull — Git operations;
  │                              svn_update, svn_cleanup, svn_revert — SVN operations;
  │                              restore_revision — creates safety snapshot then restores;
  │                              diff_revision — returns unified diff for log preview;
  │                              schedule_auto_commit — 3-second debounced auto-commit on save;
  │                              VcsWorker(QThread) — non-blocking background subprocess runner
  │                              with finished(bool, str) signal and configurable timeout;
  │                              _run_svn: --non-interactive always passed; --no-auth-cache and
  │                              --username/--password only when KeePass credentials available
  │                              so OS credential cache is usable without KeePass configured;
  │                              _askpass_script() — generates GIT_ASKPASS .bat to temp file at
  │                              runtime (cached, regenerated on deletion) so credentials never
  │                              appear in process args; _sanitise_output strips live credentials
  │                              from subprocess stdout/stderr before logging;
  │                              get_config_summary() — non-sensitive dict for debug dump;
  │                              settings: vcs/keepass_entry, vcs/auto_commit_enabled,
  │                              vcs/auto_commit_template, vcs/auto_commit_scope,
  │                              vcs/git_path, vcs/svn_path)
```

## Data Flow

```
File on disk (.mpp / .xml / .puml)
     │
     ▼  ProjectFileHandler.open_project()
     │  uses MPXJ UniversalProjectReader via JPype
     ▼
ProjectLogic.project_data   ← in-memory MPXJ ProjectFile (Java object)
     │
     ▼  MainWindow.load_project()
     ├──► TaskView.load_project()
     ├──► GanttView.load_project()
     ├──► ResourceView.load_project()
     ├──► DependencyView.load_project()
     ├──► BaselineView.load_project()
     ├──► TeamPlannerView.load_project()
     ├──► TaskSheetView.load_project()
     ├──► ResourceUsageGraphView.load_project()
     └──► TimelineView.load_project()  (clears pinned items; JSON sidecar re-pinned afterwards)
          │
     └── <basename>.timeline.json  (sidecar — saved on every pin/unpin and on project save)
     └── <basename>.splits.json   (sidecar — task split segments; written on every save;
                                    read back on open to override MPXJ-native getSplits() data;
                                    managed by MainWindow._save_splits_json / _load_splits_json)
```

On **save**, `ProjectFileHandler.save_project()` calls MPXJ's `MSPDIWriter` to write the in-memory Java object back to an XML file.

## Signal Wiring

`MainWindow` connects PyQt5 signals across views to keep the UI consistent:

| Signal | Source | Effect |
| ------ | ------ | ------ |
| `data_changed` | TaskView | Refresh GanttView + TaskSheetView; mark project dirty |
| `task_reordered` | TaskView | Mark project dirty |
| `selection_changed` | TaskView | Highlight selected task bar in GanttView |
| `data_changed` | ResourceView | Refresh resource list; mark dirty |
| `data_changed` | DependencyView | Refresh dependency arrows; mark dirty |
| `task_moved` | GanttView | Update task start/finish via drag; in hourly mode uses work-hour arithmetic (`_shift_ldt` + `_add_working_hours`) to preserve cross-day durations |
| `zoom_changed` | GanttView | Sync status-bar zoom slider, label, and Team Planner / Resource Usage Graph `day_width` |
| `task_reordered` | TaskView | Push `tasks`+`baseline` undo snapshot |
| `data_changed` | TaskView / ResourceView / DependencyView | Push view-specific undo snapshot |
| `show_in_gantt` | TaskView | Scroll `GanttView` horizontally so the selected task's bar is visible (day and hourly modes) — no tab switch |
| `task_edited` | ResourceUsageGraphView | Reload `GanttView`, `TaskView`, `ResourceUsageGraphView`, and `TaskSheetView`; mark dirty; push `tasks`+`baseline` snapshots |
| *(hover)* | `_UsageCanvas` | `QToolTip` shown on mouse-move over any timeline cell — resource/task name, period label (mode-aware), and hours; no signal; handled internally in `_UsageCanvas.mouseMoveEvent` |
| `verticalScrollBar.valueChanged` | TaskView ↔ GanttView | Keep panes scroll-locked |
| `data_changed` | TeamPlannerView | Mark project dirty; push `team_planner` undo snapshot |
| `data_changed` | TaskSheetView | Refresh GanttView + TaskView + TaskSheetView; mark dirty; push `tasks`+`baseline` snapshots |
| `data_changed` | TimelineView | Auto-save `<basename>.timeline.json` sidecar via `_on_timeline_data_changed` |
| `split_task_requested` | TaskView / TaskSheetView | `split_task_for_task(task)` — call `canvas.split_task()` (via `_do_split_interactive`), save `.splits.json` sidecar, repaint Gantt + Team Planner; undo snapshot taken automatically via `task_edited` → `_on_gantt_task_edited` |
| `remove_from_canvas_requested` | TimelineView | Remove the bar/diamond the user right-clicked from the pinned list; triggers `data_changed` |
| `timeline_toggle_requested` | TaskView / TaskSheetView | Add or remove the selected task/milestone to/from the Timeline strip |
| `task_double_clicked` | CpmResultsView | `MainWindow._on_cpm_task_double_clicked(task_id)` opens the **Task Information** dialog for the selected task |

## Menu Actions (File menu)

| Action | Enabled state | Description |
| ------ | ------------- | ----------- |
| **New** | Always | Creates an empty `ProjectFile`; calls `_apply_system_currency_to_project(project)` to initialise currency symbol, code, decimal digits, and symbol position from the OS locale monetary settings (falls back to MPXJ defaults on error); then calls `_setup_new_project_calendars(project)` to install a "Standard (Deutschland)" calendar with German national holidays and optionally additional regional/country calendars via `NewProjectCalendarsDialog`; then opens the **Project Information** dialog so the user sets start/end dates before adding tasks |
| **Open…** | Always | File dialog → `open_project_file()` |
| **Save** | When project is open | Smart save: overwrites XML; opens Save As for MPP/new |
| **Save As…** | Always | Opens Save As dialog |
| **Close** | When project is open | Prompts Save / Discard / Cancel if `_dirty`; clears in-memory project, calls `gantt_view.clear_splits()`, refreshes all views, clears undo history |
| **Recent Files ▶** | When list non-empty | Quick re-open from the last five paths |
| **Import ▶** | Always | PlantUML `@startgantt` import |
| **Export ▶** | When project is open | Complete SVG, Resource SVGs, PlantUML export |
| **Exit** | Always | Quits the application |

**Note:** `add_entry()` and `add_resource()` are **no-ops** when no project is open — the ribbon Insert and Add Resource buttons are disabled by `_refresh_all_views()` in that state, so no accidental auto-creation of a blank project can occur.

`ResourceView` shows a rich **hover tooltip** on mouse-move: `mouseMoveEvent` and `_show_resource_tooltip()` build an HTML `QToolTip` containing a 64 px avatar (AD thumbnail if stored in `_resource_thumbnail_store`, else the same type emoji as the dialog), the resource name, type, and department.  The tooltip is only rebuilt when the hovered row changes; it is hidden on `leaveEvent`.

## Frozen-Pane Scroll Sync

Three views use a frozen left pane that must stay pixel-perfectly aligned with the scrollable canvas.  Each uses a consistent two-part pattern:

### Wheel forwarding (`_WheelForwarder` / `_FrozenWheelForwarder`)

An event filter installed on the frozen pane's viewport forwards every `QEvent.Wheel` event to the canvas scroll area's viewport (or the external scrollbar) and returns `True` to consume the event.  Without this, wheel gestures over the frozen column are silently dropped by the hidden scrollbars.

| View | Filter class | Installed on | Forwarded to |
| - | - | - | - |
| Gantt Chart (task column) | `_FrozenWheelForwarder` (in `task_view.py`) | `_frozen.viewport()` | `TaskView.viewport()` |
| Resource Usage Graph | `_WheelForwarder` (in `resource_usage_graph_view.py`) | `_left_scroll.viewport()` | `_right_scroll.viewport()` |
| Team Planner | `_WheelForwarder` (in `team_planner_view.py`) | `_res_area.viewport()` | `_rows_area.viewport()` |

### Paint-offset alignment (`set_scroll_y`)

Frozen panes that cannot rely on QScrollArea internal scrolling (because `ScrollBarAlwaysOff` silently clamps the internal bar) use a paint-offset approach instead: the widget always fills the QScrollArea viewport (`setWidgetResizable(True)`), and a `set_scroll_y(y)` method stores the current scroll value and calls `update()`.  `paintEvent` subtracts `_scroll_y` from each row's content-space y to produce the viewport-local draw position.

| View | Pane class | `set_scroll_y` driven by |
| - | - | - |
| Resource Usage Graph | `_LeftPane` | `_vsb.valueChanged` |
| Team Planner | `_ResourcePane` | `_rows_vsb.valueChanged` (and explicit call in `_on_rows_area_v_changed`) |

### Horizontal scroll lock (task column)

The task column (`TaskView`) must never scroll horizontally.  Three complementary guards enforce this:

1. `setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)` — hides the horizontal scrollbar.
2. `scrollContentsBy(dx, dy)` override in `TaskView` — calls `super().scrollContentsBy(0, dy)` to suppress any horizontal shift regardless of input source.
3. `_HorizontalWheelBlocker` event filter in `ui.py` — swallows `QEvent.Wheel` events with `angleDelta().x() != 0` on `task_view.viewport()`.

### Ribbon tab guard (`_ribbon_driving_tab_switch`)

When `_on_ribbon_tab_changed` calls `QTabWidget.setCurrentIndex()`, `_on_tab_changed` fires and would normally call `_activate_tab()`, overriding the ribbon selection.  The boolean flag `_ribbon_driving_tab_switch` is set to `True` (via `try/finally`) around that call so `_on_tab_changed` skips its ribbon-activation and `_last_app_tab_for_ribbon` update logic.
| `task_rescheduled` | TeamPlannerCanvas | Update task start/finish via bar drag on same row |
| `task_reassigned` | TeamPlannerCanvas | Move task to a different resource (or unassign) |
| `layout_changed` | TeamPlannerCanvas | Resize `_ResourcePane` to match lane heights |
| `unassigned_changed` | TeamPlannerCanvas | Refresh `_UnassignedPanel` chip list |
| `ribbon_tab_changed` | ProjectRibbon | Restore the last active app-tab for the selected ribbon tab |
| `currentChanged` | QTabWidget | Update ribbon tab highlight, show/hide zoom slider, show/hide ribbon button groups |

## Tab Layout

| Index | Tab | Left pane | Right pane |
| ----- | --- | --------- | ---------- |
| 0 | Gantt Chart | TaskView (splitter) | GanttView (splitter) |
| 1 | Resources | ResourceView (full width) | — |
| 2 | Dependencies | DependencyView (full width) | — |
| 3 | Baseline | BaselineView (full width) | — |
| 4 | Team Planner | TeamPlannerView (full width) | — |
| 5 | Task Sheet | TaskSheetView (full width) | — |
| 6 | Resource Usage | ResourceUsageGraphView (full width) | — |
| 8 (`TAB_CPM`) | CPM Results | CpmResultsView (full width) | — |

**Note:** `TAB_TIMELINE` (constant value 7) is reserved for the Timeline overlay strip; it is not a `QTabWidget` tab.  `TAB_CPM` has constant value 8; the CPM Results panel occupies physical tab index 7 in the `QTabWidget`.

**Default view:** On startup the application selects tab 5 (Task Sheet) automatically.

## Ribbon UX

### Ribbon Tabs and Their Groups

| Ribbon tab | Index | Groups |
| - | - | - |
| TASK | 0 | Sheet, View, Clipboard, Jira |
| RESOURCE | 1 | View, Insert, Editing, Confluence |
| REPORT | 2 | Export (Gantt / Resource SVG / Timeline / CPM Report split-buttons), Views (CPM Results view-switch), Email (Email Accounts, Email Config) |
| BASELINE | 3 | Reference (Set/Clear + combo selectors), Gantt Diff, View |
| VERSION CONTROL | 4 | Setup, Operations, Git, SVN |

### Split-Buttons (`add_listview_button`)

Several ribbon buttons are **split-buttons** — a `_SplitToolButton` (subclass of
`QToolButton`) in `QToolButton.MenuButtonPopup` mode.  Clicking the main face
area triggers the default action; clicking the small drop-down arrow (▾) opens
a `_RibbonListPopup` — a rich floating listview showing each action as a bold
title with an optional subtitle line.

The popup is a plain child `QWidget` (no separate OS window) reparented to the
top-level window on first show, so closing it by clicking a tab or another
button requires only a single click.  `_SplitToolButton` overrides
`mousePressEvent` to intercept the arrow sub-control hit before Qt can start
its popup-grab machinery, then emits `popup_requested`.

| Panel | Button | Default action | Drop-down entries |
| - | - | - | - |
| TASK → Jira | Sync from Jira | `run_jira_sync` (normal sync) | Sync now (normal), Changed since last sync, Full resync |
| TASK → Jira | Sync to Jira | `run_jira_push` (normal push) | Sync to Jira (normal), Dry-run preview |
| RESOURCE → Insert | Add Resource | `add_resource` (manual) | Add Resource (manual), Add from Active Directory, Add from AD Group |
| REPORT → Export | Gantt Export | `export_gantt_svg` | Gantt SVG, Gantt PlantUML |
| REPORT → Timeline | Timeline Export | `export_timeline_svg` | Timeline SVG, Timeline PlantUML |
| BASELINE → Reference | Set Baseline | `set_baseline` (dialog) | Set baseline (dialog), Set into next free slot, Set all slots (bulk) |
| BASELINE → Reference | Clear Baseline | `clear_baseline` (dialog) | Clear baseline (dialog), Clear all baselines |
| VCS → Operations | Commit | `run_vcs_commit` | Commit project file only, Commit all tracked changes |
| VCS → Git | Pull | `run_vcs_pull` (merge) | Pull (merge), Pull (rebase), Fetch only |
| VCS → SVN | SVN Update | `run_vcs_svn_update` | Update to HEAD, Update to revision… |

Split-buttons are created by `_RibbonGroup.add_listview_button()`.  The
`default_slot` parameter sets the main-click handler; each
`(label, callback[, icon[, subtitle]])` tuple in `actions` becomes one item in
the `_RibbonListPopup`.  Icons are automatically recoloured from the ribbon's
white-on-transparent format to a blue (`#2e75b6`) tint suitable for the popup's
light background.

### Email Action Disabled State

`ProjectRibbon.set_email_actions_enabled(enabled, tooltip="")` performs two
distinct disable operations:

1. **Popup items** — iterates the three Report-panel popup lists
   (`_gantt_exp_popup`, `_rsvg_popup`, `_tl_exp_popup`) and calls
   `_RibbonListPopup.set_item_enabled()` for the "Email Gantt SVG",
   "Email to All Resources", and "Email Timeline SVG" entries.
   When `enabled=False`, each item has `Qt.ItemIsEnabled | Qt.ItemIsSelectable`
   cleared (rendering it greyed-out and non-interactive) and its
   `Qt.ToolTipRole` set to `tooltip`.  The click guard in `_on_item_clicked`
   returns early for any item whose `flags()` does not include
   `Qt.ItemIsEnabled`.

2. **CPM Report button** — also sets `_cpm_exp_btn.setEnabled(False)` and
   replaces the button's tooltip when `enabled=False`.  When `enabled=True`,
   the button is only re-enabled if a project is already open
   (`self._project_open`); this prevents the button from becoming live when
   email is configured but no project is loaded.  The original tooltip stored
   in `_cpm_exp_btn_tip` is restored on re-enable.  The CPM Report button is
   entirely email-driven (both popup actions send email), so it is disabled as
   a whole rather than per-item.

`MainWindow._update_email_actions_state()` drives this: it checks
`SettingsManager.get_email_configs()` and `get_active_email_config_name()`;
if the list is empty or no active name matches a configured account it calls
`set_email_actions_enabled(False, tooltip)` with a tooltip pointing the user to
**Email Accounts** and **Email Config** in the Report ribbon.  The method is
called at application startup, after `set_project_open()` in `_reload_all_views`,
and whenever `EmailServersDialog` or `EmailConfigDialog` closes.

### Tab Styling

The selected ribbon tab uses the same gradient as the panel below it and has its
bottom border removed, so it visually merges into the panel.  Unselected tabs
use a darker navy background.  A thin `rgba` border-top on `#RibbonPanelContainer`
provides the joining line between tab row and panel.

### Active View Button Highlighting

Every view-switching `QToolButton` is checkable.  On every `QTabWidget.currentChanged`
signal, `ProjectRibbon.highlight_view_button(app_tab_idx)` checks the button
that corresponds to the new tab and unchecks all others.

### Contextual Button-Group Visibility

`ProjectRibbon.update_button_visibility(app_tab_idx)` shows or hides ribbon
groups based on `_hidden_groups_by_app_tab` (configured in `_build_resource_panel`).
Currently, the **Insert**, **Editing**, **Confluence**, and **Jira** groups are
hidden when the Resource Usage Graph (tab 6) is active.

### Zoom Slider Visibility

The status-bar zoom widget (`_zoom_widget`) is shown only for views listed in
`MainWindow._ZOOM_APP_TABS` (currently `{0, 4, 6}`: Gantt Chart, Team Planner,
Resource Usage Graph).

`ResourceUsageGraphView` supports four zoom levels driven by the same global
`day_width` slider that controls the Gantt Chart and Team Planner:

| Mode | `day_width` | Column unit | Active header widget |
| - | - | - | - |
| Monthly | 4 – 6 px | 1 calendar month | `GanttHeader` |
| Weekly | 7 – 13 px | 1 ISO week | `GanttHeader` |
| Daily | 14 – 59 px | 1 calendar day | `GanttHeader` |
| Hourly | 60 – 80 px | 1 work hour (calendar-derived) | `_HourModeHeader` |

In weekly and monthly modes the canvas is configured with `show_sundays=True`
regardless of the user setting so that the per-day coordinate system stays aligned
with `GanttHeader`.  In hourly mode `HourModeHeader` is swapped in via
`QScrollArea.takeWidget()` / `setWidget()`, and `day_width` is re-interpreted as
pixels-per-hour rather than pixels-per-day.  The working-day start and end hours
are read from `project.getDefaultCalendar()` by `read_work_hours()` on every
`load_project()` call, falling back to 08:00–17:00 when no explicit hours are defined.
Break hours (e.g. a 12:00–13:00 lunch break) are returned as a `frozenset` by
`read_work_hours()` and rendered in grey in both the header and the canvas.

The **Show Off-Hours** toggle (Options → Show &Off-Hours, persisted in QSettings under
`"usage/show_off_hours"`) extends the hourly display to cover all 24 clock hours when
enabled.  Off-hour slots are greyed; only the calendar-defined working ranges are
rendered in the normal cell colour.

The **day/header alignment** fix extracts the fixed 60-px "Work" label column
(`_WorkBodyColumn`) from the scrollable canvas into the body layout as a sibling of
`_right_scroll`, mirroring `_DetailsHeaderCell` in the header layout.  This ensures
`_hdr_area` and `_right_scroll` always begin at the same screen x-position, so day
labels remain directly above their data cells regardless of scroll position.

## Shared Hourly-Zoom Infrastructure (`hour_mode.py`)

`GanttView`, `TeamPlannerView`, and `ResourceUsageGraphView` all share the same hourly-zoom
primitives from `hour_mode.py`:

| Export | Purpose |
| - | - |
| `HOUR_MODE_THRESHOLD` | `day_width` threshold (60 px) at which hourly mode activates |
| `read_work_hours(project)` | Read `(start, end, hours, non_working_slots)` from the default calendar |
| `working_day_count(start, days)` | Count Mon–Fri days in a range |
| `date_to_working_day_idx(date, start)` | Convert a `QDate` to a working-day column index |
| `datetime_to_hourly_x(...)` | Convert an MPXJ `LocalDateTime` to a canvas pixel x |
| `HourModeHeader` | Two-row `QWidget` — date label row + hour-slot row |

### Configure-before-Swap Pattern

All three views follow an identical sequence when activating hourly mode to prevent the
header scrollbar from desyncing from the canvas:

```python
# 1. Configure (calls setFixedSize) BEFORE inserting into QScrollArea
self._hour_hdr.configure(project_start, total_days, day_width, ...)

# 2. Swap widget (Qt reads size immediately — must already be correct)
if self._hdr_area.widget() is not self._hour_hdr:
    self._hdr_area.takeWidget()
    self._hdr_area.setWidget(self._hour_hdr)

# 3. Re-sync scrollbar position after the swap
self._hdr_area.horizontalScrollBar().setValue(
    self._canvas_scroll.horizontalScrollBar().value()
)
```

If `configure()` were called *after* `setWidget()`, Qt would compute the scrollbar range
from the old (stale) widget size and clamp the scrollbar value, visually misaligning all
hour-column labels relative to the canvas columns.

### Per-Ribbon Tab Memory

`MainWindow._last_app_tab_for_ribbon` stores the last active app tab for each ribbon tab so switching ribbon tabs and back restores the previous view:

| Ribbon tab | Initial default app tab |
| - | - |
| 0 TASK | 5 Task Sheet |
| 1 RESOURCE | 4 Team Planner |
| 2 REPORT | 0 Gantt Chart |

## Progress Worker

`progress_worker.py` provides a reusable background-thread + modal-dialog framework for all long-running operations.

### Public API

| Symbol | Description |
| - | - |
| `WorkerThread(QThread)` | Abstract base class.  Subclasses override `run()`.  Exposes `progress(int, str)` and `finished(bool, str)` signals; records wall-clock elapsed time via `elapsed_seconds`; sets `cancelled` flag when the dialog's Cancel button is clicked. |
| `run_with_progress(parent, title, worker, *, cancellable, indeterminate, min_duration_ms)` | Blocks the caller until the worker thread finishes.  Opens a `QProgressDialog`, connects signals, and starts the worker.  Returns `(success: bool, result_message: str)`. |
| `run_indeterminate(parent, title, func, *args, **kwargs)` | Convenience wrapper for simple callables that do not need a `WorkerThread` subclass.  Wraps `func` in an anonymous worker, shows a pulsing indeterminate bar, and re-raises any exception thrown by `func`. |
| `record_timing(operation, elapsed, success)` | Appends one entry `{operation, elapsed_seconds, success, timestamp}` to the module-level `_timing_log` deque (capacity 50). |
| `get_timing_log()` | Returns a copy of `_timing_log` as a plain list. |

### _done Guard

`QProgressDialog.closeEvent` always emits `canceled()` even after the dialog closes normally.  Without a guard this would overwrite the `(True, result)` set by `_on_finished` with `(False, "Cancelled by user")`.  Both `_on_finished` and `_on_cancel` check and set a `_done: list = [False]` sentinel before touching the result, making the pattern idempotent.

### Operations Using Progress Worker

All seven priority operations in `MainWindow` (`ui.py`) are wrapped:

| Operation | Worker / Helper | Mode |
| - | - | - |
| Jira→Project Sync | `_JiraSyncWorker` | determinate with progress callback |
| Project→Jira Push | `run_indeterminate` | indeterminate |
| File Open | `run_indeterminate` | indeterminate |
| Confluence Calendar Sync | `run_indeterminate` | indeterminate |
| VCS Commit / Pull / SVN Update | `VcsWorker` (existing `QThread`) | indeterminate |
| File Save | `run_indeterminate` | indeterminate |
| SVG / PlantUML Export | `run_indeterminate` | indeterminate |

`record_timing` is called after every operation.  The timing log is included in the debug dump (`app_debug.py`) under the `long_running_timings` key.

### AD Search Dialog

`ADSearchDialog._do_search` (`dialogs.py`) uses `run_indeterminate` for the AD lookup so the UI stays responsive during the PowerShell call.

### Resource Information Dialog — per-resource AD lookup

`ResourceDialog._do_ad_lookup` (`dialogs.py`) provides an inline **"Look up in AD…"** button next to the E-Mail field.  When pressed:

1. If the resource name field is blank an information dialog is shown and the lookup is skipped.
2. Otherwise `ad_integration.lookup_by_name_all(name)` is called inside `run_indeterminate`.
3. A single match writes email and department directly into the dialog fields.
4. Multiple matches open `ADUserSelectDialog`; the chosen entry fills the fields.
5. No match shows an information dialog; the fields remain unchanged.

`apply_to_resource()` writes the final field values back to MPXJ via `setEmailAddress()`, `setDepartment()`, and `setType()`; an empty string is converted to `None` so the attribute is cleared rather than stored as an empty string.

The AD thumbnail (raw bytes fetched via `ad_integration.get_thumbnail()`) is stored in `MainWindow._resource_thumbnail_store` (dict uid→bytes) and persisted in `<project>.thumbnails.json` (sidecar JSON with format `{"resources": {"uid": {"thumbnail": "<base64>", "department": "..."}}}`, backward-compatible with old string-only format).  The store is loaded on project open, cleared on project close / new project, saved after "Look up in AD…" confirmation, and pruned when a resource is deleted.

## Undo / Redo

`HistoryManager` (in `history_manager.py`) maintains one snapshot stack per view across five views: `tasks`, `resources`, `dependencies`, `baseline`, and `team_planner`.  Every
mutating operation serialises the full project to MSPDI XML bytes (`MSPDIWriter` +
`ByteArrayOutputStream`) and pushes the snapshot.  Undo and redo deserialise a stored
snapshot (`UniversalProjectReader` + `ByteArrayInputStream`) and reload all views.

`Ctrl+Z` triggers undo and `Ctrl+Y` triggers redo on the **currently active tab**'s stack.
Changes to one view (e.g. tasks) do not affect the redo history of other views (e.g. resources).

**Exception — Confluence Calendar Sync:** the sync writes directly to the MPXJ project's calendar layer (not through any view's mutation path) but **does push an undo snapshot** via `history_manager.push_all()` before any changes are made, so the entire sync can be undone in a single Undo step on any view.  Expired exceptions (older than 30 days) and stale forward-window exceptions are removed automatically; these removals are also covered by the single pre-sync snapshot.

**Exception — Jira→Project Sync:** `run_sync()` in `jira_sync.py` writes tasks and resources directly via MPXJ Java calls (not through any view's mutation path).  `MainWindow.run_jira_sync()` calls `history_manager.push('tasks')` and `history_manager.push('resources')` **after** the sync succeeds, so the entire sync (new tasks, updated tasks, epic container wiring) is undoable with a single Ctrl+Z on the Tasks or Resources view stack.

## Persistence

User preferences (zoom level, show/hide resource units, show/hide Sundays, show/hide off-hours in the Resource Usage Graph hourly view) are persisted across sessions via `QSettings` under the key `"ProjectOffline" / "ProjectManager"`.

Key settings keys:

| QSettings key | Default | Description |
| - | - | - |
| `gantt/show_sundays` | `true` | Show Sunday columns in Gantt / Resource Usage |
| `gantt/show_resource_units` | `false` | Show resource-unit percentages on Gantt bars |
| `usage/show_off_hours` | `false` | Show pre/post-work hours in Resource Usage hourly view |
| `timeline/visible` | `false` | Whether the Timeline strip is currently shown |
| `confluence/keepass_entry` | `""` | `"Group/Title"` path of the KeePass entry used to pre-fill Microsoft AAD SSO credentials during Confluence Calendar Sync |
| `email/smtp_server` | `""` | SMTP server hostname for email integration |
| `email/smtp_port` | `587` | SMTP server port (default 587 for STARTTLS) |
| `email/smtp_use_tls` | `true` | Enable STARTTLS for SMTP connection |
| `email/sender_address` | `""` | Email sender address ("From" field) |
| `email/keepass_entry` | `""` | `"Group/Title"` path of the KeePass entry containing SMTP authentication credentials |

## Timeline View

`TimelineView` (in `views/timeline_view.py`) is a fixed-height strip embedded **above** the `QTabWidget` inside a `QVBoxLayout` in the central widget.  It is hidden by default and activated via **Options → Show Timeline Strip** (persisted in `QSettings` as `timeline/visible`).

### Visibility management

The strip uses `_set_collapsed(bool)` instead of `setVisible()` directly so that the `QVBoxLayout` collapses to 0 height (via `setMinimumHeight(0)` + `setMaximumHeight(0)`) when the strip is hidden.  `MainWindow.changeEvent` listens for `QEvent.WindowStateChange` (maximize / restore) and defers a call to `_on_window_state_settled` via `QTimer.singleShot(0, …)` so the layout is re-applied after Qt has fully settled the new window geometry.

### Which tabs show the strip

`_VIEWS_SHOWING_TIMELINE` (configured at the top of `timeline_view.py`) lists the tab indices on which the strip appears when toggled on (default: Gantt Chart and Team Planner).  `_SOURCE_VIEWS_WITH_CONTEXT_MENU` lists the tabs whose task rows offer "Show in Timeline" context-menu items (default: Gantt Chart and Task Sheet).

### Registration API

```python
TimelineView.register(main_window)
```

Called once during `MainWindow.__init__` after the widget is embedded.  Connects:

- `TimelineView.data_changed` → `MainWindow._on_timeline_data_changed` (auto-saves JSON sidecar)
- `TimelineView.remove_from_canvas_requested` → `MainWindow._on_timeline_remove_from_canvas`

### JSON sidecar

Pinned tasks and milestones are saved to `<basename>.timeline.json` alongside the project file.  The sidecar is written on every pin/unpin and on every project save.  It is loaded immediately after `_refresh_all_views()` on project open.

### Timeline strip height

`FIXED_HEIGHT = HEADER_HEIGHT + TOTAL_CANVAS_H` (≈ 178 px).  The strip has two sub-widgets: a `GanttHeader`-compatible month/day header and a `_TimelineCanvas` that renders the project span bar, task bars (with per-task colour cycling), and milestone diamonds.

## Settings & Credentials

`SettingsManager` owns all KeePass and Jira **persistent** settings.  A single instance is created in `MainWindow.__init__` and passed to every dialog that needs it.  The runtime KeePass session (the live `pykeepass.KeePassFile` object) is owned by `KeePassManager` in `src/integrations/keepass_integration.py`, which is initialised immediately after `SettingsManager` via `keepass_integration.init(settings_manager)`.

```
MainWindow
  ├── _settings_manager : SettingsManager
  │     ├── QSettings (Windows registry)
  │     │     keepass/db_path, keepass/key_file, keepass/password
  │     │     jira/servers  (JSON array)
  │     │     confluence/keepass_entry  ("Group/Title" path for AAD SSO auto-fill)
  │     │     email/smtp_server, email/smtp_port, email/smtp_use_tls  (legacy single-config)
  │     │     email/sender_address  (legacy single-config)
  │     │     email/keepass_entry  (SMTP auth credentials — global, NOT per account)
  │     ├── email_configs.json  (next to .exe / project root in dev mode)
  │     │     { "active_config_name": str,
  │     │       "configs": [ {name, smtp_server, smtp_port, smtp_use_tls, sender_address}, … ] }
  │     └── shim methods (unlock_keepass, lock_keepass, …) → delegate to KeePassManager
  └── keepass_integration.init(sm)  →  KeePassManager singleton
        └── _db : pykeepass.KeePassFile   ← session-only, never persisted
```

`SettingsManager` exposes the same KeePass lock/unlock/entry API that the rest of the codebase used before the refactor; each method delegates to `keepass_integration.get_manager()` so call sites do not need to import the integration module directly.

The **Project** menu exposes:

| Action | Handler | Dialog opened |
| - | - | - |
| Project Information… | `MainWindow.open_project_info` | `ProjectInformationDialog` |
| Confluence Calendar Configuration… | `MainWindow.open_confluence_settings` | `ConfluenceCalendarConfigDialog` |
| Sync Confluence Calendar | `MainWindow.sync_confluence_calendar` | — |
| **Jira** submenu | — | — |
| → Jira Sync Configuration… | `MainWindow.open_jira_config` | `JiraSyncConfigDialog` |
| → Jira Servers… | `MainWindow.open_jira_settings` | `JiraServersDialog` |

The **Settings** menu (between Export and Options in the menu bar) exposes:

| Action | Handler | Dialog opened |
| - | - | - |
| KeePass Configuration… | `MainWindow.open_keepass_settings` | `KeePassConfigDialog` (includes Confluence SSO Auto-fill section when DB is unlocked) |

## Confluence Calendar Sync

> Requirements: [PO_09_confluence_integration.dsf](requirements/dsf/PO_09_confluence_integration.dsf)

`ConfluenceCalendarSync` (in `confluence_calendar.py`) is invoked via **Project → Sync Confluence Calendar**.  It operates directly on the in-memory MPXJ `ProjectFile` that is already loaded in `ProjectLogic`.

```
ConfluenceCalendarSync.run(project, history_manager, settings_manager)
  │
  ├── reads CALENDAR Base URL, CALENDAR Space Key from project custom properties
  ├── validates base URL (HTTPS enforcement via _validate_base_url)
  ├── resolves KeePass credentials (optional)
  │     if settings_manager provided and confluence/keepass_entry configured
  │     and DB is unlocked → keepass_creds = (username, password)
  │     otherwise              → keepass_creds = None
  ├── authenticates via _try_playwright_auth(base_url, keepass_creds)
  │     cached state  → headless, instant
  │     expired/first → opens browser; if keepass_creds present, _autofill_microsoft_sso
  │                     pre-fills AAD email+password; user completes MFA only
  │     state file permissions restricted to owner-only (600 on POSIX, icacls on Windows)
  ├── history_manager.push_all()   ← snapshot before any changes
  ├── computes today, until = today + days_ahead, prune_cutoff = today − 30d
  ├── _fetch_subcalendars()  → Confluence REST API
  ├── _filter_relevant()     → keep holiday / leave / vacation calendars
  ├── _fetch_events()        → events for each calendar in [today, until]
  └── _apply_to_project(sync_start=today, sync_end=until, prune_before=prune_cutoff)
        ├── prune expired exceptions (end < prune_cutoff) from default + resource cals
        ├── remove stale window exceptions (in [today, until] but absent from new events)
        ├── holiday events  → project.getDefaultCalendar().addCalendarException()
        └── vacation events → per-resource calendar.addCalendarException()
              ├── matches by exact or partial username (case-insensitive)
              ├── auto-creates resource when no match found (non-blank usernames only)
              └── creates a derived resource calendar if the resource has none
```

**Undo support:** `run()` calls `history_manager.push_all()` after successful authentication and before modifying any calendar.  This makes the entire sync (additions, removals, and pruning) undoable in one step on any view.

Configuration is stored per-project in MPXJ custom properties (not in `QSettings`):

| Custom field | Default | Description |
| - | - | - |
| `CALENDAR Base URL` | — (required) | Confluence server base URL |
| `CALENDAR Space Key` | — (required) | Space key to query |
| `CALENDAR Timezone` | `Europe/Berlin` | IANA timezone for event fetching |
| `CALENDAR Days Ahead` | `365` | Forward sync window in days (1–3650) |

All QSettings writes call `sync()` immediately so values survive a crash.  The master password is stored base64-encoded; Jira server configs are stored as a JSON string.

## Email Integration

> Requirements: [PO_14_email_integration.dsf](requirements/dsf/PO_14_email_integration.dsf)

`email_integration.py` provides SMTP email functionality with KeePass credential management for sending project exports (SVG Gantt charts, Team Planner snapshots, resource utilisation graphs) as email attachments.

```
email_integration.send_email(to, subject, body, attachments)
  │
  ├── is_configured()  → validates server, sender, keepass_entry are set
  ├── _get_credentials()  → retrieves (username, password) from KeePass
  │     if KeePass unlocked and entry exists → (username, password)
  │     otherwise                            → ("", "")
  ├── smtplib.SMTP(server, port, timeout=30)
  │     ├── ehlo()
  │     ├── has_extn('STARTTLS') → starttls() if available and use_tls=True
  │     ├── login(username, password)
  │     └── sendmail(sender, recipients, message)
  └── returns (success: bool, error_message: str)
```

**Configuration via `EmailConfigDialog`:**

The dialog is accessible from the **Email Config** button in the **Report** ribbon panel (always enabled as email settings are global, not project-gated).  The dialog includes:

- **KeePass Section:** Three-state display (not configured / locked / unlocked with entry selection)
- **SMTP Settings:** Server, port, TLS checkbox, sender address with "From KeePass" button for AD lookup
- **Test Connection:** Validates SMTP connect + auth without sending email
- **Send Test Email:** Opens wider dialog (400px) with "Use My Email" button for recipient AD lookup

**Integration Features:**

| Feature | Implementation |
| - | - |
| Credential Storage | KeePass entry (username/password) retrieved via `keepass_integration.get_credentials()` |
| Active Directory Lookup | "From KeePass" button queries AD via `ad_integration.lookup_by_username()` to auto-fill sender address |
| Test Connection | `test_connection()` — SMTP connect + auth without sending, returns (success, error) tuple |
| Send Email | `send_email()` — supports single/multiple recipients, plain text body, attachments as (filename, bytes) tuples |
| Config Summary | `get_config_summary()` — returns dict for debug dumps without exposing passwords |
| Last Results Tracking | Module-level `_last_send_result` and `_last_test_result` for diagnostic purposes |
| Ribbon Disabled State | `MainWindow._update_email_actions_state()` calls `ribbon.set_email_actions_enabled(False, tooltip)` when no accounts exist or none is active; email popup items greyed-out with explanatory tooltip; re-evaluated at startup and after `EmailServersDialog` / `EmailConfigDialog` close |

**Persistence — email_configs.json (next to .exe):**

SMTP account list and active account name are stored in a plain JSON file next to the
executable (or at project root in dev mode) so the whole installation folder can be
copied between machines to transfer the configuration.

| Key in JSON | Default | Description |
| - | - | - |
| `active_config_name` | `""` | Name of the currently active SMTP account |
| `configs[*].name` | — | Display name for the account |
| `configs[*].smtp_server` | `""` | SMTP server hostname |
| `configs[*].smtp_port` | `587` | SMTP server port |
| `configs[*].smtp_use_tls` | `true` | Enable STARTTLS |
| `configs[*].sender_address` | `""` | Sender email address |

**Persistence — QSettings (Windows registry, machine-local):**

| Key | Default | Description |
| - | - | - |
| `email/keepass_entry` | `""` | KeePass entry path for SMTP credentials (global, shared by all accounts) |
| `email/smtp_server` | `""` | Legacy single-config SMTP server (read during migration only) |
| `email/smtp_port` | `587` | Legacy single-config port |
| `email/smtp_use_tls` | `true` | Legacy single-config TLS flag |
| `email/sender_address` | `""` | Legacy single-config sender address |

**Security:**

- Passwords are never written to QSettings, log files, or debug dumps
- Error messages are user-friendly and do not expose sensitive information
- `get_config_summary()` includes `keepass_entry_set: bool` flag instead of the actual entry name

**Debug Dump Integration:**

When the `--debug` flag is active, the debug dump includes an `email_integration` block with the complete output of `get_config_summary()`, providing configuration visibility without exposing credentials.

## Jira Integration

> Requirements: [PO_15_jira_integration.dsf](requirements/dsf/PO_15_jira_integration.dsf)

`jira_integration.py` provides Jira REST API connectivity for synchronizing project tasks with Jira issues, supporting multiple authentication methods (API Token for Jira Cloud, Password for legacy servers, Personal Access Token for Jira Server/Data Center with disabled basic authentication).

```
jira_integration.get_jira_client(server: dict)
  │
  ├── get_jira_credentials(server)  → retrieves (username, credential) from settings or KeePass
  │     both values are stripped of leading/trailing whitespace
  ├── validates credentials based on credential_type:
  │     PAT mode:            credential required, username optional
  │     API Token/Password:  both username and credential required
  ├── JIRA(server=url, token_auth=credential)       for PAT mode
  │   or
  │   JIRA(server=url, basic_auth=(username, credential))  for API Token/Password mode
  └── returns (JIRA instance | None, error_message: str)
```

**Configuration via Dialogs:**

The integration provides two main dialogs:

1. **JiraSyncConfigDialog** (`open_jira_config()` from TASK ribbon or Project → Jira → Jira Sync Configuration):
   - **Server Selection:** Dropdown of configured servers with Add button
   - **Filter Type Selector:** Two radio buttons — "JQL" (raw JQL string) and "Saved Filter (ID or URL)" (numeric ID or full `?filter=` URL); both disabled when no project is open
   - **Filter Field:** Text input; placeholder and tooltip adapt to the selected filter type
   - **Test Filter Button:** Validates filter, resolves saved filter to JQL via `resolve_filter_to_jql()`, executes `jira.search_issues(jql, maxResults=50)`, displays issue count and preview; if the selected server uses KeePass auth and the database is locked, prompts the user to unlock before connecting
   - **Filter Storage:** Saved per-project in custom properties (`.custom-props.json` sidecar file) inside a single `"jira2project"` JSON container; `filter` and `filter_type` keys within the container hold the filter value and mode; filter and field-checkbox keys are omitted from the container when cleared
   - **Project Requirement:** Filter field and type radios disabled when no project is open (filters are project-specific)

2. **JiraServersDialog** (`open_jira_settings()` from Project → Jira → Jira Servers):
   - Server list management (Add, Edit, Delete)
   - Per-server configuration: name, URL, auth mode (Manual/KeePass), credential type (API Token/Password/PAT)

**Integration Features:**

| Feature | Implementation |
| - | - |
| Connection Testing | `test_connection(server)` — creates JIRA client, calls `myself()`, records result in `_last_connection_test` |
| Filter Testing | `record_filter_test(server_name, filter_text, issue_count, error)` — records test results with timestamp in `_last_filter_test` |
| Client Creation | `get_jira_client(server)` — returns authenticated JIRA instance or error message |
| Config Summary | `get_config_summary()` — returns dict for debug dumps including `last_connection_test` and `last_filter_test` (when available) |
| Credential Stripping | All credentials stripped of whitespace to prevent HTTP header validation errors |
| Authentication Modes | Manual (stored in QSettings) or KeePass (retrieved from database) |
| Credential Types | API Token (Jira Cloud), Password (legacy), Personal Access Token (Server/Data Center) |

**Project Custom Properties (Filter Storage):**

The JQL filter is stored per-project in MPXJ custom properties (not in `QSettings`), making it portable with the project file:

| Custom property key | Storage location | Description |
| - | - | - |
| `JIRA Sync Filter` | `.custom-props.json` sidecar | Filter value — JQL string or saved filter ID/URL depending on type |
| `JIRA Sync Filter Type` | `.custom-props.json` sidecar | `"jql"` (default) or `"filter"` — determines how the filter value is interpreted |

When `JiraSyncConfigDialog` is accepted with a project open:

- Filter saved via `project.getProjectProperties().getCustomProperties()` using `java.util.HashMap`
- `MainWindow._mark_dirty()` called to trigger save
- Filter loaded on next dialog open via `_get_filter_from_project()`

**QSettings Persistence (Server Configuration):**

| Key | Default | Description |
| - | - | - |
| `jira/servers` | `[]` | JSON array of server configurations (name, url, auth_mode, credential_type, username, token, keepass_entry) |
| `jira/sync_server` | `""` | Name of the selected sync server |

**Debug Dump Integration:**

When the `--debug` flag is active, the debug dump includes two Jira-related blocks:

1. **`jira_sync_config`** — Complete output of `get_config_summary()`:
   - `servers`: List of configured servers (name, url, auth_mode, credential_type) without credentials
   - `last_connection_test`: Most recent connection test result (timestamp, success, error)
   - `last_filter_test`: Most recent filter test result (server_name, filter, issue_count, timestamp, success, error)

2. **`jira_project_props`** — Project-specific filter configuration:
   - `filter_set`: Boolean indicating whether a filter is configured
   - `filter`: The JQL filter string from custom properties
   - Returns empty dict for projects without the `JIRA Sync Filter` custom property

**Security:**

- Credentials (API tokens, passwords, PATs, KeePass entries) are never written to debug dumps, log files, or displayed in error messages
- `get_config_summary()` returns sanitized configuration without exposing sensitive data
- Test results track success/failure status and error messages for observability

## Jira→Project Sync

> Requirements: [PO_15_jira_integration.dsf §2](requirements/dsf/PO_15_jira_integration.dsf)

`jira_sync.py` (in `src/integrations/`) is the bidirectional sync engine covering both the Jira→Project import direction (`run_sync`) and the Project→Jira push direction (`run_push_to_jira`).  The import direction is invoked from **Project → Jira → Run Jira Sync** via `MainWindow.run_jira_sync()`; the push direction is invoked from the **TASK ribbon → Sync to Jira** button or **Project → Jira → Sync to Jira** via `MainWindow.run_jira_push()`.  The import engine fetches Jira issues matching the project's configured filter and creates or updates MPXJ tasks in the currently open project.  The push engine reads project task data and writes it back to the Jira server.

```
MainWindow.run_jira_sync()
  │
  ├── reads server + jira2project config from project custom-properties
  ├── gets authenticated JIRA client via jira_integration.get_jira_client()
  ├── jira_sync.run_sync(project, server_cfg, jira_client, sidecar_path)
  │     ├── load_sidecar_task_data(sidecar_path)
  │     │     └── reads .custom-props.json → dict[uid_str → {jira_key: …}]
  │     ├── _build_jira_key_lookup(project, task_jira)
  │     │     └── {jira_key → MPXJ Task} for all already-synced tasks
  │     ├── resolve_filter_to_jql(server, jira_client)  [via jira_integration]
  │     ├── jira_client.search_issues(jql, maxResults=500, startAt=0, …)
  │     ├── Pass 1 — Epics first:
  │     │     for each Epic issue:
  │     │       lookup or create MPXJ task
  │     │       task.setSummary(True); task.setRollup(True)
  │     ├── Pass 2 — Non-epics:
  │     │     for each non-Epic issue:
  │     │       lookup or create MPXJ task
  │     │       task.setName(…); task.setPercentageComplete(_status_to_percent(status))
  │     │       if parent epic exists → task.setParentTask(epic_task)
  │     ├── save_sidecar_task_data(sidecar_path, task_jira)
  │     │     └── merges task_jira into .custom-props.json under "task_jira" key
  │     └── returns {created, updated, skipped, errors, log}  → stored in _last_result
  ├── history_manager.push('tasks')
  ├── history_manager.push('resources')
  ├── _refresh_all_views()
  └── _mark_dirty()
```

**Sidecar format** (`<basename>.custom-props.json`, `task_jira` key):

```json
{
  "task_jira": {
    "42": {"jira_key": "PROJ-7", "issue_type": "Story", "status": "In Progress"},
    "43": {"jira_key": "PROJ-8", "issue_type": "Epic",  "status": "To Do"}
  }
}
```

The dictionary key is the MPXJ task UID as a string; the value contains at minimum `jira_key`.  On the next sync, `_build_jira_key_lookup` reconstructs the Jira-key→task map from this sidecar so existing tasks are updated rather than duplicated.

**Epic hierarchy:**

Epics are processed in a first pass so their MPXJ tasks exist before any sub-tickets reference them as parents.  Sub-tickets whose `parent.key` or `epic_link` field matches a known Epic receive `task.setParentTask(epic_task)`, creating an MPXJ summary hierarchy that renders as collapsible rows in the Gantt and Task Sheet views.

**Undo support:**

`MainWindow.run_jira_sync()` pushes `tasks` and `resources` snapshots **after** the sync succeeds (same pattern as `_on_task_data_changed`).  A single Ctrl+Z on either the Tasks or Resources view undoes the entire sync in one step.

**Debug dump integration:**

When `--debug` is active, the debug dump includes a `jira_sync_result` block containing the last `get_last_result()` dict (created, updated, skipped, first 20 errors, first 50 log entries).  The block is omitted when no sync has run in the current session.

## Project→Jira Push

> Requirements: [PO_15_jira_integration.dsf §3](requirements/dsf/PO_15_jira_integration.dsf)

`run_push_to_jira(project, server, jira_client, sidecar_path, included_task_uids=None)` in `jira_sync.py` is the execution engine for the Project→Jira direction.  It is invoked by `MainWindow.run_jira_push()` which optionally shows a `JiraPushPreviewDialog` dry-run pass first.

```
MainWindow.run_jira_push()
  │
  ├── reads project2jira config container from project custom-properties
  ├── gets authenticated JIRA client via jira_integration.get_jira_client()
  ├── jira_sync.run_push_to_jira(…, dry_run=True)          [preview pass]
  │     ├── _read_p2j_config(project) → config dict
  │     ├── load_sidecar_task_data(sidecar_path) → task_p2j section
  │     ├── for each task (or included_task_uids subset):
  │     │     ├── _task_to_jira_payload(task, config) → field dict
  │     │     ├── decide: CREATE / UPDATE / TRANSITION / SKIP
  │     │     └── dry_run=True: append to preview_actions, no API calls
  │     └── returns {preview_actions, dry_run=True, …zeros…}
  ├── JiraPushPreviewDialog(preview_actions) shown to user
  │     └── user can uncheck rows; dialog returns included_task_uids
  ├── jira_sync.run_push_to_jira(…, dry_run=False,           [live pass]
  │         included_task_uids=…)
  │     ├── for each included task:
  │     │     ├── CREATE: jira_client.create_issue(fields=payload)
  │     │     ├── UPDATE: _with_retry(issue.update, fields=payload)
  │     │     ├── TRANSITION: _with_retry(jira_client.transition_issue)
  │     │     ├── conflict check: remote_updated > task_p2j[uid].last_pushed_at
  │     │     └── hierarchy: issue.update(parent={"key": parent_key})
  │     ├── save_sidecar_task_data(task_p2j, jira_push_meta)
  │     └── returns {created, updated, transitioned, skipped, errors, log, dry_run=False}
  └── _refresh_all_views()
```

**Helper functions:**

- `_read_p2j_config(project)` — extracts the `project2jira` container from project custom properties; returns a normalized config dict.
- `_p2j_field_enabled(config, field_name)` — returns True if a field-map row is enabled for the given project field.
- `_p2j_jira_field(config, field_name)` — returns the target Jira field name for a given project field.
- `_task_status_string(task)` — maps MPXJ percent-complete to a Jira-style status string: 0%→`"To Do"`, 1–99%→`"In Progress"`, 100%→`"Done"`.
- `_task_to_jira_payload(task, config)` — builds the Jira `fields` dict from MPXJ task attributes using the field-map configuration.
- `_with_retry(fn, *args, **kwargs)` — wraps any callable with exponential back-off for transient errors (HTTP 429, 5xx, `ConnectionError`, `Timeout`); non-transient errors are re-raised immediately.
- `get_last_push_result()` — returns the module-level `_last_push_result` dict from the most recent `run_push_to_jira` call.

**Sidecar sections** (`<basename>.custom-props.json`):

`task_p2j` records the last push state for each task:

```json
{
  "task_p2j": {
    "42": {"jira_key": "PROJ-7", "last_pushed_at": "2025-10-01T09:00:00"},
    "99": {"jira_key": "NEW",    "last_pushed_at": null}
  }
}
```

A `jira_key` of `"NEW"` indicates a task that has not yet been pushed (unlinked); the key is replaced with the actual Jira issue key after a successful create.

`jira_push_meta` records run-level metadata:

```json
{
  "jira_push_meta": {
    "last_run_at": "2025-10-01T09:00:00",
    "last_successful_push": "2025-10-01T09:00:00",
    "audit_sessions": [
      {"run_at": "2025-10-01T09:00:00", "created": 1, "updated": 3,
       "transitioned": 2, "skipped": 0, "errors": 0}
    ]
  }
}
```

Audit sessions are capped at 20 entries (oldest dropped first).

**Conflict detection:**

When `conflict_policy` is `prefer_jira` or `manual_review`, the engine compares `issue.fields.updated` (ISO timestamp from Jira) against `task_p2j[uid].last_pushed_at`.  If the remote timestamp is newer the task is skipped (prefer_jira) or flagged for review (manual_review).

**Debug dump integration:**

When `--debug` is active, the debug dump includes `jira_push_result` (last `get_last_push_result()` dict) and `jira_push_meta` (last push meta from sidecar) blocks.  Both are omitted when no push has run in the current session.


## App Debug (`app_debug.py`)

> Requirements: [PO_02_App_Debug.dsf](requirements/dsf/PO_02_App_Debug.dsf)

`app_debug.py` is the central debug flag and project-state dump module, activated by the `--debug` command-line flag.

- `is_debug()` / `set_debug(value)` — global debug flag accessor
- `dump_project_state(logic, ui_state)` — serialises live application state to a timestamped JSON file in the OS temp directory; triggered by `Ctrl+D` in `ui.py`
- The dump payload covers: `build_version`, `dump_timestamp`, `python_version`, `platform`, `frozen`, `ui`, `project`, `active_baselines`, `custom_properties`, `task_fields`, `resource_fields`, `enterprise_fields`, `tasks`, `resources`, `calendar_diagnostics`, `split_tasks`, `keepass_integration`, `confluence_calendar_props`, `ad_sync_result`, `email_integration`, `email_export_status`, `email_templates_status`, `resource_sidecar`, `jira_sync_config`, `jira_sync_result`, `jira_project_props`, `jira_push_result`, `jira_push_meta`, `vcs_integration`, `long_running_timings`, `project_calendars`
- On failure, an error dialog with a **Copy to Clipboard** button is shown
- Sensitive data (passwords, KeePass paths, email addresses, VCS credentials, commit messages) is never written to the dump

## Testing

The project includes a comprehensive automated test suite in the `tests/` directory covering all major modules, views, and integrations. Tests run fully offline without requiring a JVM, Confluence server, or browser.

**Test Structure:**

```
tests/
├── conftest.py                   # Shared fixtures (QApp, mock task/resource/project factories)
├── test_ad_integration.py        # Active Directory PowerShell integration
├── test_app_debug.py             # Debug dump — layout diagnostics, project-state serialisation
├── test_confluence_calendar_integration.py  # Confluence Calendar sync — all public/private functions
├── test_secondary_calendar_integration.py  # Secondary calendar assignments — parse_map, get/set/resolve, infer/assign from AD
├── test_dialogs.py               # TaskDialog, ResourceDialog, DependencyDialog — including Timeline checkbox
├── test_email_integration.py     # Email integration — SMTP, KeePass credentials, configuration
├── test_export_gantt.py          # SVG and PlantUML Gantt export
├── test_file_handler.py          # MPXJ file open/save via JPype
├── test_history_manager.py       # Per-view undo/redo stacks
├── test_icons.py                 # Runtime icon factory
├── test_import_plantuml.py       # PlantUML @startgantt parser
├── test_keepass_integration.py   # KeePass credential management
├── test_logic.py                 # ProjectLogic data store
├── test_main.py                  # Application entry point wiring
├── test_menu.py                  # ProjectMenuBar construction and actions
├── test_ribbon.py                # ProjectRibbon tab/button/group logic
├── test_jira_sync.py             # Jira↔Project sync engine — sidecar I/O, helper functions, run_sync flow (J→P) + run_push_to_jira flow (P→J)
├── test_settings_dialogs.py      # KeePassConfigDialog, JiraSyncConfigDialog, JiraServersDialog, EmailConfigDialog, ConfluenceCalendarConfigDialog
├── test_settings_manager.py      # KeePass, Jira, and email settings persistence
├── test_stylesheet.py            # QSS string sanity checks
├── test_toolbar.py               # ProjectToolBar construction
├── test_ui.py                    # MainWindow construction, tab switching, Timeline integration
└── views/
    ├── test_baseline_view.py     # Baseline tracking widget
    ├── test_critical_path.py     # CPM helpers (float calculation, critical flag)
    ├── test_dependency_view.py   # Dependency list widget
    ├── test_gantt_view.py        # Gantt chart rendering and CPM helpers
    ├── test_hour_mode.py         # Shared hourly-zoom infrastructure
    ├── test_resource_usage_graph_view.py  # Resource Usage Graph widget
    ├── test_resource_view.py     # Resource sheet widget
    ├── test_task_sheet_view.py   # Task Sheet widget
    ├── test_task_view.py         # Task grid widget
    ├── test_team_planner_view.py # Team Planner drag-and-drop widget
    └── test_timeline_view.py     # Timeline strip — pinning, collapsing, registration, signals
```

**Key Coverage Areas:**

- **Active Directory Integration** — PowerShell availability detection, lookup by name/email/username with input sanitisation, injection-char rejection, lookup history recording; `lookup_by_email_all`/`lookup_by_username_all` with fast-path exact-match (`mail -eq`, `Get-ADUser -Identity`) and wildcard fallback (`mail -like`, `SamAccountName -like`)
- **Confluence Calendar** — HTTPS validation, SSO authentication flow, Microsoft AAD form auto-fill (`_autofill_microsoft_sso`), KeePass credentials integration via `settings_manager`, holiday/vacation import, resource auto-creation, stale-entry removal, expired-entry pruning, platform-specific file permissions
- **Email Integration** — SMTP configuration validation, KeePass credential retrieval, test connection (auth without send), send_email with attachments (single/multiple recipients), config summary without password exposure, error message user-friendliness, KeePass integration when locked/unlocked/entry not found
- **Jira Integration** — Connection testing, filter resolution, config summary without password exposure
- **Jira→Project Sync** — Sidecar task-data I/O (`load_sidecar_task_data`, `save_sidecar_task_data`), `_issue_type_label`, `_status_to_percent`, `_build_jira_key_lookup`, `run_sync` early-exit branches, task creation, task update, epic hierarchy wiring, result counters, `[CREATE]`/`[UPDATE]` debug log tokens
- **File Operations** — JVM lifecycle management, MPXJ reader/writer wiring, error handling
- **KeePass Integration** — Singleton lifecycle, lock/unlock/auto-unlock, DB creation with key-file, entry CRUD operations, key-file generation
- **Undo/Redo** — Snapshot serialization, per-view isolation, re-entrant protection, history depth limits
- **Views** — Widget initialization, data loading, inline editing, delete operations, signal emissions, Timeline strip pinning/collapsing/registration
- **Dialogs** — Task/Resource/Dependency information editors, data round-tripping, Timeline checkbox pre-checked state
- **MainWindow** — Tab switching, ribbon integration, Timeline visibility toggling, `_on_window_state_settled`, JSON sidecar wiring

**Mocking Strategy:**

All Java classes (`org.mpxj.*`, `jpype`, `java.time`) are replaced with `MagicMock` objects via `sys.modules` patching or `unittest.mock.patch`.  Network dependencies (`requests`, `playwright`) are stubbed before module import.  Qt widgets run headlessly with `QT_QPA_PLATFORM=offscreen`.

Run the full test suite:

```bash
pytest tests/ -v
```

See [`tests/README.md`](../tests/README.md) for detailed per-module coverage information.

## Dirty-State Tracking

`MainWindow._dirty` is set to `True` whenever a `data_changed`, `task_reordered`, or `task_moved` signal is received.  The **Save** action in both the toolbar and the menu bar is enabled only when `_dirty` is `True`.  On close, if the project is dirty the user is offered a Save / Discard / Cancel prompt.

## Critical Path Method (CPM)

The CPM feature provides a forward+backward pass analysis of the open project, identifying which tasks lie on the critical path (zero or minimal total float) and displaying per-task schedule dates and float values in a dedicated read-only panel.

### CPM Computation (`_compute_critical_ids` in `gantt_view.py`)

```
_compute_critical_ids(all_tasks, project, dep_types, critical_slack_days,
                      return_float_data=True)
  │
  ├── Phase 1 — separate summary tasks from leaf tasks; build parent→children map
  ├── Phase 2 — forward pass: derive early_start / early_finish from MPXJ dates
  │     completed tasks (100 % complete) are collected in completed_ids
  ├── Phase 3 — build dependency graph (FS / SS / FF / SF or FS-only)
  ├── Phase 4 — backward pass: compute late_start / late_finish from project deadline
  │     (uses project.getFinish() when supplied; falls back to max early_finish)
  ├── Phase 5 — compute total_float and free_float per leaf task
  │     total_float  = late_finish − early_finish
  │     free_float   = min(successor early_starts) − own early_finish
  │     tasks in completed_ids are never marked critical
  ├── Phase 6 — propagate critical flag to summary tasks
  │     a summary task is critical when ANY leaf descendant is critical
  │     (matches MS Project behaviour)
  └── returns (set[critical_ids], dict[tid → float_entry]) when return_float_data=True
```

**Configurable parameters:**

| Parameter | Default | Description |
| - | - | - |
| `dep_types` | `"all"` | `"all"` uses FS+SS+FF+SF; `"fs_only"` considers only Finish-to-Start links |
| `critical_slack_days` | `0` | Tasks with total float ≤ this value are marked critical (MS Project default is 0) |
| `return_float_data` | `False` | When `True`, returns `(set, dict)` instead of just `set`; all existing callers pass `False` and are unaffected |

### CPM Settings (`CPMSettingsDialog` in `settings_dialogs.py`)

Opened via **REPORT → CPM Settings** button.  Stores two categories of settings:

**Calculation settings** (per-project, saved in the `.custom-props.json` sidecar under `"cpm_config"`):

| Field | Default | Description |
| - | - | - |
| Critical slack threshold | `0` | Days of total float at or below which a task is critical |
| Dependency types | `all` | Radio: all types (FS/SS/FF/SF) or finish-to-start only |

**Display preferences** (global, persisted via `SettingsManager` to `QSettings`):

| Setting | QSettings key | Default | Description |
| - | - | - | - |
| Show total-float overlay bar | `cpm/show_float_bar` | `false` | Render a light-blue bar on each Gantt task bar proportional to its total float |
| Show Free Float column in Task Sheet | `cpm/show_free_float_col` | `false` | Adds a Free Float column to the Task Sheet view |
| Show CPM Results panel | `cpm/show_results_panel` | `false` | Makes the CPM Results tab visible |

**Restore MS Project Defaults** resets all fields to their defaults (0 days, all dep types, all display prefs off).

### CPM Results View (`CpmResultsView` in `views/cpm_results_view.py`)

A read-only `QWidget` embedded as tab index 7 in the `QTabWidget` (`TAB_CPM` = 8 in `app_tabs.py`).

**Signal:** `task_double_clicked = pyqtSignal(int)` — emitted when the user double-clicks a task row; carries the task's integer unique ID.  Connected in `ui.py` to `MainWindow._on_cpm_task_double_clicked(task_id)`, which looks up the task by UID and opens the **Task Information** dialog.

```
CpmResultsView.refresh(float_data, all_tasks, work_day_hours)
  │
  ├── stores float_data dict  (tid → {es, ef, ls, lf, total_float, free_float, critical})
  ├── _populate()
  │     for each task (filtered by "Critical tasks only" if checkbox checked):
  │       row = [name, duration, ES, EF, LS, LF, total_float, free_float, status]
  │       dates formatted to "DD MMM YYYY" (_fmt_dt)
  │       floats formatted to "Xd" using work_day_hours (_fmt_wh / _fmt_td)
  │       critical rows: background _COLOR_CRITICAL + text _COLOR_CRIT_TEXT (red)
  │       near-critical rows: background _COLOR_NEAR_CRIT (amber)
  └── status label: "N critical task(s) — M near-critical"
```

**Columns:** Task Name | Duration | Early Start | Early Finish | Late Start | Late Finish | Total Float | Free Float | Status

**"Export CSV…"** button opens a `QFileDialog` and saves the currently visible rows (respecting the "Critical tasks only" filter) as UTF-8 CSV.

### CPM Report Ribbon Button (`_cpm_exp_btn` in `ribbon.py`)

The **CPM Report** split-button in the REPORT → Export group sends the CPM analysis by email.  It is the only ribbon button that is gated on **both** a project being open **and** email being configured:

| State | Button |
| - | - |
| No project open | Disabled (part of `_project_btns`) |
| Project open + email configured | Enabled |
| Project open + email not configured | Disabled; tooltip replaced with "Configure an SMTP account first" message |
| Email re-configured while project open | Re-enabled; original tooltip restored |

`set_email_actions_enabled(enabled, tooltip)` in `ribbon.py` enforces this:

- `enabled=False` → `_cpm_exp_btn.setEnabled(False)` + replace tooltip
- `enabled=True`  → re-enable only if `self._project_open is True`; restore `_cpm_exp_btn_tip`

**Drop-down actions:**

| Action | Callback | Description |
| - | - | - |
| Email CPM Report | `email_cpm_report` | Send the CPM results table as an HTML email |
| Email CPM Report + Gantt | `email_cpm_report_with_gantt` | Send results table with the Gantt SVG attached |

### Data Flow

```
GanttView.load_project() / _on_project_changed()
  └── _compute_critical_ids(all_tasks, project, dep_types, critical_slack_days,
                            return_float_data=True)
        └── (critical_ids set, float_data dict)

MainWindow._refresh_cpm_results_view()
  ├── reads _cpm_cfg from project sidecar (dep_types, critical_slack_days)
  ├── calls _compute_critical_ids on gantt_view's task list
  ├── passes (float_data, all_tasks, work_day_hours) to cpm_results_view.refresh()
  └── also drives GanttView critical highlighting via gantt_view._critical_ids
```

`_refresh_cpm_results_view()` is called:

- After every `_reload_all_views()` (project open / close)
- After **CPM Settings** dialog closes (settings changed)
- When the user switches to the CPM Results tab
