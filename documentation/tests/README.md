# Test Documentation

This directory contains documentation about the automated test suite for the
Project Offline application.

## Test Specification

The human-readable test specification is maintained as a set of HTML files in
[`tests/pytests/documentation/`](../../tests/pytests/documentation/).

### Quick Access

| Spec File | Modules covered |
| --------- | --------------- |
| [index.html](../../tests/pytests/documentation/index.html) | **Start here** — overview of all groups with links to each spec file |
| [test_spec_app_debug.html](../../tests/pytests/documentation/test_spec_app_debug.html) | `app_debug` |
| [test_spec_history_manager.html](../../tests/pytests/documentation/test_spec_history_manager.html) | `history_manager` |
| [test_spec_logic.html](../../tests/pytests/documentation/test_spec_logic.html) | `logic`, `main` |
| [test_spec_settings_manager.html](../../tests/pytests/documentation/test_spec_settings_manager.html) | `settings_manager` |
| [test_spec_core_misc.html](../../tests/pytests/documentation/test_spec_core_misc.html) | `stylesheet`, `toolbar`, `progress_worker` |
| [test_spec_holidays.html](../../tests/pytests/documentation/test_spec_holidays.html) | `holidays` |
| [test_spec_file_handler.html](../../tests/pytests/documentation/test_spec_file_handler.html) | `export_gantt`, `file_handler`, `icons`, `import_plantuml` |
| [test_spec_integrations_ad.html](../../tests/pytests/documentation/test_spec_integrations_ad.html) | `ad_integration` |
| [test_spec_integrations_confluence_calendar.html](../../tests/pytests/documentation/test_spec_integrations_confluence_calendar.html) | `confluence_calendar` |
| [test_spec_integrations_secondary_calendar.html](../../tests/pytests/documentation/test_spec_integrations_secondary_calendar.html) | `secondary_calendar_integration` |
| [test_spec_integrations_jira_integration.html](../../tests/pytests/documentation/test_spec_integrations_jira_integration.html) | `jira_integration` |
| [test_spec_integrations_jira_sync.html](../../tests/pytests/documentation/test_spec_integrations_jira_sync.html) | `jira_sync`, `jira_sync_push` |
| [test_spec_integrations_email.html](../../tests/pytests/documentation/test_spec_integrations_email.html) | `email_integration` |
| [test_spec_integrations_keepass.html](../../tests/pytests/documentation/test_spec_integrations_keepass.html) | `keepass_integration` |
| [test_spec_integrations_vcs.html](../../tests/pytests/documentation/test_spec_integrations_vcs.html) | `version_control_integration` |
| [test_spec_dialogs.html](../../tests/pytests/documentation/test_spec_dialogs.html) | `dialogs` |
| [test_spec_menu.html](../../tests/pytests/documentation/test_spec_menu.html) | `menu`, `cpm_results_view` |
| [test_spec_ribbon.html](../../tests/pytests/documentation/test_spec_ribbon.html) | `ribbon` |
| [test_spec_settings_dialogs.html](../../tests/pytests/documentation/test_spec_settings_dialogs.html) | `settings_dialogs` |
| [test_spec_ui.html](../../tests/pytests/documentation/test_spec_ui.html) | `ui` |
| [test_spec_views_baseline.html](../../tests/pytests/documentation/test_spec_views_baseline.html) | `baseline_view` |
| [test_spec_views_critical_path.html](../../tests/pytests/documentation/test_spec_views_critical_path.html) | `critical_path`, `dependency_view` |
| [test_spec_views_gantt.html](../../tests/pytests/documentation/test_spec_views_gantt.html) | `gantt_view` |
| [test_spec_views_timeline.html](../../tests/pytests/documentation/test_spec_views_timeline.html) | `timeline_view` |
| [test_spec_views_hour_mode.html](../../tests/pytests/documentation/test_spec_views_hour_mode.html) | `hour_mode` |
| [test_spec_views_resource_usage_graph.html](../../tests/pytests/documentation/test_spec_views_resource_usage_graph.html) | `resource_usage_graph_view` |
| [test_spec_views_resource_view.html](../../tests/pytests/documentation/test_spec_views_resource_view.html) | `resource_view` |
| [test_spec_views_task_sheet.html](../../tests/pytests/documentation/test_spec_views_task_sheet.html) | `task_sheet_view` |
| [test_spec_views_task_view.html](../../tests/pytests/documentation/test_spec_views_task_view.html) | `task_view` |
| [test_spec_views_team_planner.html](../../tests/pytests/documentation/test_spec_views_team_planner.html) | `team_planner_view` |
| [test_spec_views_resource_usage_histogram.html](../../tests/pytests/documentation/test_spec_views_resource_usage_histogram.html) | `resource_usage_histogram_view` |

Open any HTML file in a browser.  Each module has its own section; test cases
are organised into collapsible chapters (one per test class).  Every test case
shows four blocks: **Init → Run → Expect → Check**.


## Test Suite Structure

```
tests/
+-- pytests/                           # pytest test files
|   +-- conftest.py                    # Shared fixtures, mocks, JVM stubs
|   +-- test_<module>.py               # One file per src/ module
|   +-- documentation/
|       +-- index.html                 # Spec index (start here)
|       +-- test_spec_app_debug.html  # App Debug
|       +-- test_spec_history_manager.html  # History Manager
|       +-- test_spec_logic.html  # Logic & Main
|       +-- test_spec_settings_manager.html  # Settings Manager
|       +-- test_spec_core_misc.html  # Stylesheet, Toolbar & Progress Worker
|       +-- test_spec_holidays.html  # Holidays
|       +-- test_spec_file_handler.html  # File Handler, Export & Import
|       +-- test_spec_integrations_ad.html  # AD Integration
|       +-- test_spec_integrations_confluence_calendar.html  # Confluence Calendar Integration
|       +-- test_spec_integrations_secondary_calendar.html  # Secondary Calendar Integration
|       +-- test_spec_integrations_jira_integration.html  # Jira Integration (API)
|       +-- test_spec_integrations_jira_sync.html  # Jira Sync (J→P & P→J)
|       +-- test_spec_integrations_email.html  # Email Integration
|       +-- test_spec_integrations_keepass.html  # KeePass Integration
|       +-- test_spec_integrations_vcs.html  # Version Control Integration
|       +-- test_spec_dialogs.html  # Dialogs
|       +-- test_spec_menu.html  # Menu & CPM Results View
|       +-- test_spec_ribbon.html  # Ribbon
|       +-- test_spec_settings_dialogs.html  # Settings Dialogs
|       +-- test_spec_ui.html  # UI (Main Window)
|       +-- test_spec_views_baseline.html  # Baseline View
|       +-- test_spec_views_critical_path.html  # Critical Path & Dependency View
|       +-- test_spec_views_gantt.html  # Gantt View
|       +-- test_spec_views_timeline.html  # Timeline View
|       +-- test_spec_views_hour_mode.html  # Hour Mode Engine
|       +-- test_spec_views_resource_usage_graph.html  # Resource Usage Graph View
|       +-- test_spec_views_resource_view.html  # Resource View
|       +-- test_spec_views_task_sheet.html  # Task Sheet View
|       +-- test_spec_views_task_view.html  # Task View
|       +-- test_spec_views_team_planner.html  # Team Planner View
|       +-- test_spec_views_resource_usage_histogram.html  # Resource Usage Histogram View
+-- project_xml/                       # Sample MPP/XML project files used as fixtures
```


## Running the Tests

Install test dependencies (Python ≥ 3.10 recommended):

```bash
pip install pytest pytest-cov
pip install -r requirements.txt
```

### Full suite

```bash
pytest
```

### Specific module

```bash
pytest tests/pytests/test_history_manager.py -v
pytest tests/pytests/test_gantt_view.py -v
```

### Filter by keyword

```bash
pytest tests/pytests/ -v -k "undo"
pytest tests/pytests/ -v -k "jira"
```

### Quiet summary

```bash
pytest tests/pytests/ -q
```


## Coverage Reports

Coverage is collected automatically on every `pytest` run (configured in
`pyproject.toml`):

| Report | Path |
| ------ | ---- |
| HTML (browsable) | `tests/documentation/htmlcov/index.html` |
| XML (CI tools) | `tests/documentation/coverage.xml` |


## Maintaining the Test Specification

Each HTML spec file corresponds to a logical group of Python test files.
When adding or updating tests:

1. **Run `pytest`** to ensure all tests pass.
2. **Update the relevant spec file** in `tests/pytests/documentation/`
   by adding or editing the corresponding `<div class="test-case">` block.
3. **Update the stats bar** (Total Tests / Passed / Skipped / Failed / Modules)
   at the top of the modified spec file and in `index.html`.
4. **Update `documentation/tests/README.md`** if new test files were created.

### Spec file grouping

| Group | Spec file | Python test files |
| ----- | --------- | ----------------- |
| Core | `test_spec_app_debug.html` | `test_app_debug.py` |
| Core | `test_spec_history_manager.html` | `test_history_manager.py` |
| Core | `test_spec_logic.html` | `test_logic.py`, `test_main.py` |
| Core | `test_spec_settings_manager.html` | `test_settings_manager.py` |
| Core | `test_spec_core_misc.html` | `test_stylesheet.py`, `test_toolbar.py`, `test_progress_worker.py` |
| Core | `test_spec_holidays.html` | `test_holidays.py` |
| Core | `test_spec_file_handler.html` | `test_export_gantt.py`, `test_file_handler.py`, `test_icons.py`, `test_import_plantuml.py` |
| Integrations | `test_spec_integrations_ad.html` | `test_ad_integration.py` |
| Integrations | `test_spec_integrations_confluence_calendar.html` | `test_confluence_calendar_integration.py` |
| Integrations | `test_spec_integrations_secondary_calendar.html` | `test_secondary_calendar_integration.py` |
| Integrations | `test_spec_integrations_jira_integration.html` | `test_jira_integration.py` |
| Integrations | `test_spec_integrations_jira_sync.html` | `test_jira_sync.py` |
| Integrations | `test_spec_integrations_email.html` | `test_email_integration.py` |
| Integrations | `test_spec_integrations_keepass.html` | `test_keepass_integration.py` |
| Integrations | `test_spec_integrations_vcs.html` | `test_version_control_integration.py` |
| UI | `test_spec_dialogs.html` | `test_dialogs.py` |
| UI | `test_spec_menu.html` | `test_menu.py`, `test_cpm_results_view.py` |
| UI | `test_spec_ribbon.html` | `test_ribbon.py` |
| UI | `test_spec_settings_dialogs.html` | `test_settings_dialogs.py` |
| UI | `test_spec_ui.html` | `test_ui.py` |
| Views | `test_spec_views_baseline.html` | `test_baseline_view.py` |
| Views | `test_spec_views_critical_path.html` | `test_critical_path.py`, `test_dependency_view.py` |
| Views | `test_spec_views_gantt.html` | `test_gantt_view.py` |
| Views | `test_spec_views_timeline.html` | `test_timeline_view.py` |
| Views | `test_spec_views_hour_mode.html` | `test_hour_mode.py` |
| Views | `test_spec_views_resource_usage_graph.html` | `test_resource_usage_graph_view.py` |
| Views | `test_spec_views_resource_view.html` | `test_resource_view.py` |
| Views | `test_spec_views_task_sheet.html` | `test_task_sheet_view.py` |
| Views | `test_spec_views_task_view.html` | `test_task_view.py` |
| Views | `test_spec_views_team_planner.html` | `test_team_planner_view.py` |
| Views | `test_spec_views_resource_usage_histogram.html` | `test_histogram_view.py` |
