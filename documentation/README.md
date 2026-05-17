# Documentation Index

This folder contains documentation for the Project Offline application.

## Sections

### Application

| File | Description |
| - | - |
| [architecture.md](architecture.md) | High-level module map, data flow, signal wiring, and dirty-state tracking |
| [standalone_executable.md](Analyze/standalone_executable.md) | Packaging as a self-contained Windows executable or installer (PyInstaller, SConstruct, build scripts) |
| [jira_sync_configuration.md](Analyze/jira_sync_configuration.md) | Jira synchronization configuration guide — server setup, authentication methods (API Token, Password, PAT), KeePass integration |
| [plugin_system.md](Analyze/plugin_system.md) | Plugin-system index and links to design and implementation planning |
| [plugin_system_design_plan.md](Analyze/plugin_system_design_plan.md) | Detailed plugin-system design and implementation plan |
| [version_control_integration.md](Analyze/version_control_integration.md) | Version-control integration design for Git/SVN workflows, credentials, and operations |
| [ribbon_dropdown_modes.md](Analyze/ribbon_dropdown_modes.md) | Ribbon dropdown-mode analysis and UX/interaction guidance |
| [modal_progress_dialogs.md](Analyze/modal_progress_dialogs.md) | Modal progress-dialog architecture and rollout plan for long-running operations |
| [multi_project_consolidation.md](Analyze/multi_project_consolidation.md) | Multi-project consolidation design plan and implementation notes |
| [gui_customisation.md](Analyze/gui_customisation.md) | GUI customisation index and rollout plan (themes, columns, layout profiles, quick-access toolbar, panel layout) |
| [gui_customisation_themes.md](Analyze/gui_customisation_themes.md) | Detailed design for light/dark/system theme selection and live stylesheet switching |
| [gui_customisation_columns.md](Analyze/gui_customisation_columns.md) | Detailed design for per-view column visibility and order configuration |
| [gui_customisation_layout_profiles.md](Analyze/gui_customisation_layout_profiles.md) | Detailed design for named layout profiles and state restore |
| [gui_customisation_quick_access_toolbar.md](Analyze/gui_customisation_quick_access_toolbar.md) | Detailed design for pinning ribbon actions to quick-access toolbar |
| [gui_customisation_panel_layout.md](Analyze/gui_customisation_panel_layout.md) | Detailed design for splitter persistence and panel reorder/detach strategy |
| [CeptahBridge/](Analyze/CeptahBridge/README.md) | Ceptah Bridge mapping and integration documentation |

### Source Modules (`src/`)

| File | Description |
| - | - |
| [modules/main.md](modules/main.md) | Entry point — argument parsing, object wiring, Qt event loop |
| [modules/app_tabs.md](modules/app_tabs.md) | Named `TAB_*` / `RIBBON_*` constants for `QTabWidget` indices — single source of truth used by `ui.py`, `ribbon.py`, and all views |
| [modules/ui.md](modules/ui.md) | `MainWindow` — tab layout, signal wiring, public actions, drag handling |
| [modules/logic.md](modules/logic.md) | `ProjectLogic` — in-memory `ProjectFile` data store |
| [modules/file_handler.md](modules/file_handler.md) | MPXJ file open/save via JPype |
| [modules/menu.md](modules/menu.md) | `ProjectMenuBar` — File (New, Open, Save, Save As, **Close**, Recent, Import, Export, Exit), Options, and Project menus |
| [modules/toolbar.md](modules/toolbar.md) | `ProjectToolBar` — `QToolBar` wrapper around the ribbon |
| [modules/ribbon.md](modules/ribbon.md) | `ProjectRibbon` — MS Project-style tab ribbon with button groups |
| [modules/icons.md](modules/icons.md) | Runtime icon factory (Unicode glyphs on `QPixmap`) |
| [modules/stylesheet.md](modules/stylesheet.md) | `MS_PROJECT_STYLE` — global QSS string |
| [modules/dialogs.md](modules/dialogs.md) | Task, Resource, Dependency, Baseline, and Project Information dialogs |
| [modules/import_plantuml.md](modules/import_plantuml.md) | PlantUML `@startgantt` import |
| [modules/export_gantt.md](modules/export_gantt.md) | SVG and PlantUML export |
| [modules/history_manager.md](modules/history_manager.md) | Per-view undo/redo snapshot engine (`HistoryManager`) |
| [modules/settings_manager.md](modules/settings_manager.md) | KeePass, Jira (servers + sync server selection), and email persistent settings (`SettingsManager`) |
| [modules/settings_dialogs.md](modules/settings_dialogs.md) | KeePass, Jira (sync config + server list), Confluence, and Email configuration dialogs; `JiraSyncConfigDialog` for selecting sync server, `ConfluenceCalendarConfigDialog` (auth mode, timezone QComboBox with IANA zones) |
| [modules/baseline_manager.md](modules/baseline_manager.md) | Baseline business logic — set, clear, query, and variance helpers for all 11 baseline slots |
| [modules/progress_worker.md](modules/progress_worker.md) | `progress_worker` — `WorkerThread` base class, `run_with_progress()` / `run_indeterminate()` modal-dialog helpers, `_done` guard, timing registry (`record_timing` / `get_timing_log`, 50-entry deque) |

### Integrations (`src/integrations/`)

| File | Description |
| - | - |
| [integrations/keepass_integration.md](integrations/keepass_integration.md) | `KeePassManager` — runtime KeePass session, unlock/lock, entry CRUD, module-level façade, QSettings keys, security notes, debug dump fields |
| [integrations/jira_integration.md](integrations/jira_integration.md) | `jira_integration` — Jira API connectivity, server selection, `test_connection`, `get_jira_client`, `get_config_summary`; supports API Token (Jira Cloud), Password, and Personal Access Token (Server/Data Center); basic_auth + token_auth; credential stripping; `JiraSyncConfigDialog` for sync server selection; debug dump |
| [integrations/confluence_calendar_integration.md](integrations/confluence_calendar_integration.md) | `ConfluenceCalendarSync` — Playwright SSO, holiday/vacation import, stale-entry pruning, per-project configuration helpers |
| [integrations/ad_integration.md](integrations/ad_integration.md) | Active Directory lookup via PowerShell `Get-ADUser` — `is_ad_available`, `lookup_by_name/email/username`, `sync_resources`, lookup history, QSettings keys, debug dump |
| [integrations/email_integration.md](integrations/email_integration.md) | `email_integration` — SMTP email with KeePass credentials, `send_email`, `test_connection`, `is_configured`, config summary for debug dumps, QSettings keys, security notes |

### Views (`src/views/`)

| File | Description |
| - | - |
| [modules/hour_mode.md](modules/hour_mode.md) | Shared hourly-zoom infrastructure — constants, calendar reader, coordinate helpers, and `HourModeHeader` widget — used by Gantt, Team Planner, and Resource Usage Graph |
| [views/gantt_view.md](views/gantt_view.md) | Gantt chart rendering, zoom, drag, helper functions |
| [views/task_view.md](views/task_view.md) | Editable task grid, status icons, inline editing, reordering |
| [views/task_sheet_view.md](views/task_sheet_view.md) | Hierarchical task sheet with progress bars, predecessor enrichment, and collapse/expand |
| [views/resource_view.md](views/resource_view.md) | Resource sheet |
| [views/dependency_view.md](views/dependency_view.md) | Task dependency list and relation types |
| [views/baseline_view.md](views/baseline_view.md) | Baseline vs actual comparison with variance highlighting |
| [views/team_planner_view.md](views/team_planner_view.md) | Team Planner — resource-row timeline, drag reschedule/reassign, unassigned chips |
| [views/resource_usage_graph_view.md](views/resource_usage_graph_view.md) | Resource Usage Graph — collapsible resource/task hierarchy, four zoom modes (monthly / weekly / daily / hourly), hour-mode header |
| [views/timeline_view.md](views/timeline_view.md) | Timeline strip — layout constants, visibility management, registration API, signals, public item-management and export API, JSON sidecar format, context menus |
| [views/gantt_view.md](views/gantt_view.md) | *Additional:* Task Splitting &amp; Merging — SPLIT_GAP_DAYS, _task_vacation_blocks, split_task, merge_task, get_splits, sidecar persistence, dashed-gap rendering |

### MPXJ Library

| Folder | Description |
| - | - |
| [mpxj/](Analyze/mpxj/README.md) | MPXJ class reference (Task, Resource, ProjectFile, Calendar, Splits, …) |
