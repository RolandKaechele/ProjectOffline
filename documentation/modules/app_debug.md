# app_debug.py

Central debug flag and project-state dump utility.  All debug features are
**disabled by default** and activate only when `--debug` (or `-v`) is passed on
the command line.


## Debug Flag

```python
def set_debug(enabled: bool) -> None: ...
def is_debug() -> bool: ...
```

`set_debug(True)` is called by `main.py` when `--debug` / `-v` is present.
`is_debug()` is queried by any module that wants to guard verbose output or
debug-only features (e.g. `MainWindow._debug_dump()`).


## Function: `dump_project_state`

```python
def dump_project_state(project, ui_state: dict | None = None) -> str:
```

Serialises the current project and optional UI state to a JSON file and returns
the absolute path of the written file.

### Parameters

| Parameter | Type | Description |
| - | - | - |
| `project` | MPXJ `ProjectFile` (JPype) | The loaded project object |
| `ui_state` | `dict \| None` | Additional UI context collected by the caller; placed verbatim under the `"ui"` top-level key |

### Output File

Written to `os.getcwd()` with the name pattern:

```
debug_project_dump_YYYYMMDD_HHMMSS.json
```

For example: `debug_project_dump_20250523_143012.json`

### JSON Structure

```json
{
  "ui": {
    "file_path": "...",
    "unsaved_changes": false,
    "active_tab_index": 0,
    "active_tab_name": "Gantt Chart",
    "ribbon_tab_index": 0,
    "ribbon_tab_name": "Task",
    "zoom_day_width": 22,
    "hourly_mode": false,
    "gantt_scroll_x": 0,
    "gantt_scroll_y": 0,
    "work_hour_start": 8,
    "work_hour_end": 17,
    "clock_day_span": 9,
    "show_off_hours": false,
    "show_resource_units": false,
    "zero_float_critical": false,
    "project_start": "2025-01-06",
    "project_total_days": 120,
    "critical_task_ids": [3, 7, 12],
    "baseline_view": {
      "delegate_type": "_CellColorDelegate",
      "baseline_slot": 0,
      "comparison_slot": -1,
      "show_start_diff": true,
      "show_finish_diff": true,
      "show_duration_diff": true,
      "row_count": 13,
      "colored_cells_count": 5,
      "uncolored_delta_count": 0,
      "colored_cells": [
        {"task": "Development", "col": "Start_\u0394", "rgb": "(255,210,120)"}
      ]
    }
  },
  "confluence_calendar_props": {
    "base_url_set": true,
    "base_url": "https://confluence.corp",
    "space_key_set": true,
    "space_key": "TEAM",
    "timezone": "Europe/Berlin",
    "days_ahead": 365
  },
  "ad_sync_result": {
    "available": true,
    "sync": {
      "total": 12,
      "updated": 3,
      "skipped": 9,
      "errors": []
    },
    "lookups": [
      {"fn": "lookup_by_name", "input": "Smith, John",
       "result": {"display_name": "John Smith", "email": "j.smith@corp",
                  "department": "Engineering", "username": "jsmith"}},
      {"fn": "lookup_by_email", "input": "unknown@corp", "result": null}
    ]
  },
  "project": {
    "name": "My Project",
    "start": "2025-01-06",
    "finish": "2025-05-31",
    "author": "...",
    "company": "...",
    "baseline_dates": {
      "0": "2025-01-05",
      "1": "2025-03-10"
    },
    "tasks": [
      {
        "id": 1,
        "name": "Design phase",
        "start": "2025-01-06T08:00",
        "finish": "2025-01-17T17:00",
        "duration": "10.0 d",
        "pct_complete": 100.0,
        "critical": false,
        "milestone": false,
        "summary": false,
        "constraint_type": null,
        "constraint_date": null,
        "baseline_start": "2025-01-06T08:00",
        "baseline_finish": "2025-01-17T17:00",
        "baselines": {
          "0": {
            "start": "2025-01-06T08:00",
            "finish": "2025-01-17T17:00",
            "duration": "10.0 d",
            "start_days": 0,
            "finish_days": 0,
            "duration_pct": 0.0
          }
        },
        "predecessors": [
          {"id": 0, "type": "FS", "lag": "0.0 d"}
        ],
        "assignments": [
          {"resource_id": 1, "resource_name": "Alice", "units": 1.0}
        ]
      }
    ],
    "resources": [
      {
        "id": 1,
        "name": "Alice",
        "max_units": 1.0,
        "type": "Work",
        "email": "alice@example.com"
      }
    ]
  }
}
```

### Filtering

Tasks where **all** of `id`, `name`, `start`, and `finish` are `None` or `0` are
skipped to keep the output concise.  Resources with no `id` are similarly omitted.

### Error Handling

All per-task and per-resource attribute reads are wrapped in individual
`try/except` blocks so a single bad value never aborts the entire dump.  If the
file cannot be written the exception propagates to the caller (`MainWindow._debug_dump`
catches it and shows a warning dialog).


## Usage in `MainWindow`

`Ctrl+D` (bound in `ui.py`) calls `MainWindow._debug_dump()`:

1. Returns immediately if `is_debug()` is `False`.
2. Builds `ui_state` from live widget state (scroll positions, zoom level, ribbon
   tab, active view, work-hour settings, critical task IDs, etc.).
3. Calls `dump_project_state(self._logic.project, ui_state)`.
4. Shows a `QMessageBox` with the path of the written file.

## Split Task Data in the Dump

When `ui_state` contains a `"split_tasks"` key, `dump_project_state` appends a
`"split_tasks"` block at the top level of the JSON output.

### Source

`MainWindow._debug_dump` populates `split_tasks` from the Gantt canvas:

```python
ui_state["split_tasks"] = self._gantt_view.canvas.splits_to_dict()
```

`splits_to_dict()` returns `{str(uid): [[iso_start, iso_end], ...]}` — the same
format used by the `.splits.json` sidecar file.

### JSON structure

```json
{
  "split_tasks": [
    {
      "task_uid": 3,
      "task_name": "Backend Coding",
      "segments": [
        {"start": "2026-05-04", "end": "2026-05-14"},
        {"start": "2026-05-18", "end": "2026-05-28"}
      ]
    }
  ]
}
```

### MPXJ-level splits

For each task, the dumper also attempts to read native MPXJ split data via
`task.getSplits()` (available when the project was opened from a `.mpp` or
`.xml` file that already contains split segments).  If present, the data is
stored under `"mpxj_splits"` inside the task's entry in the `"tasks"` array:

```json
{
  "id": 3,
  "name": "Backend Coding",
  ...
  "mpxj_splits": [
    {"start": "2026-05-04T08:00", "finish": "2026-05-14T17:00"},
    {"start": "2026-05-18T08:00", "finish": "2026-05-28T17:00"}
  ]
}
```

If `getSplits()` returns `None` or an empty list, the field is omitted.

## Active Directory Data in the Dump

`dump_project_state` always tries to populate an `"ad_sync_result"` top-level key by
importing `integrations.ad_integration`.  If the module is unavailable the key is an
empty dict.

| Sub-key | Source | Content |
| ------- | ------ | ------- |
| `available` | `is_ad_available()` called at dump time | `true` when PowerShell + RSAT ActiveDirectory module are reachable |
| `sync.total/updated/skipped/errors` | `get_last_sync_result()` | Last result of `sync_resources()`; all `null` when no sync has run |
| `lookups` | `get_last_lookup_results()` | Full list of all individual lookup calls (`lookup_by_name`, `lookup_by_email`, `lookup_by_username`) since process start, each as `{fn, input, result}` |

See [integrations/ad_integration.md](../integrations/ad_integration.md) for the
complete API and field definitions.
