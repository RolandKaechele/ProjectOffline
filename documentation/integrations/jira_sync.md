# Jira→Project Sync

## Overview

The `src/integrations/jira_sync.py` module is the runtime sync engine that fetches Jira issues matching a configured filter and creates or updates MPXJ tasks in the currently open project.  It is invoked by **Project → Jira → Run Jira Sync** (`MainWindow.run_jira_sync()`).

Key capabilities:

- Fetches issues via a saved Jira filter or a raw JQL query (resolved through `jira_integration.resolve_filter_to_jql`)
- Creates new MPXJ tasks for issues not yet in the project
- Updates existing tasks (name, percent-complete, type label) for issues already tracked
- Builds an epic → sub-task hierarchy using MPXJ `setParentTask`
- Persists a Jira-key → UID mapping in the project sidecar so subsequent syncs update rather than duplicate
- Returns a result dict with counters (`created`, `updated`, `skipped`, `errors`, `log`) accessible via `get_last_result()`
- Integrated with the undo stack — a single Ctrl+Z reverts the entire sync

## Prerequisites

| Requirement | Notes |
| ----------- | ----- |
| Jira server configured | Must be set up in **Settings → Jira Servers** |
| Filter configured | Set in **Project → Jira → Configure Jira Sync** (JQL or saved filter) |
| Authenticated JIRA client | Obtained via `jira_integration.get_jira_client()` |
| KeePass unlocked (if applicable) | If the server uses `auth_mode="keepass"`, the user is prompted to unlock KeePass before the sync starts |
| Open project file | Sync modifies the current in-memory MPXJ project |

## run_sync() Flow

```
MainWindow.run_jira_sync()
  │
  ├── reads server config from QSettings (jira/sync_server)
  ├── reads jira2project container from project custom-properties
  ├── jira_integration.get_jira_client(server_cfg)  →  JIRA client
  ├── jira_sync.run_sync(project, server_cfg, jira_client, sidecar_path)
  │     │
  │     ├── load_sidecar_task_data(sidecar_path)
  │     │     └── reads .custom-props.json → {uid_str → {jira_key, issue_type, status, …}}
  │     ├── _build_jira_key_lookup(project, task_jira)
  │     │     └── {jira_key → MPXJ Task} for all already-synced tasks
  │     ├── resolve_filter_to_jql(server_cfg, jira_client)  [via jira_integration]
  │     ├── paginated loop — jira_client.search_issues(jql, startAt, maxResults=100,
  │     │       fields="summary,issuetype,status,parent,customfield_10014,…")
  │     │       stops when a page returns fewer than 100 results
  │     │
  │     ├── Pass 1 — Epics first:
  │     │     for each Epic issue:
  │     │       lookup existing task or create new MPXJ task
  │     │       task.setSummary(True)
  │     │       task.setRollup(True)
  │     │       task.setName(summary)  ← bare Jira summary, no type prefix
  │     │
  │     ├── Pass 2 — Non-epics:
  │     │     for each non-Epic issue:
  │     │       lookup existing task or create new MPXJ task
  │     │       task.setName(summary)  ← bare Jira summary, no type prefix
  │     │       task.setPercentageComplete(_status_to_percent(status))
  │     │       if parent epic present → task.setParentTask(epic_task)
  │     │
  │     ├── save_sidecar_task_data(sidecar_path, task_jira)
  │     │     └── merges task_jira into .custom-props.json under "task_jira" key
  │     └── returns {created, updated, skipped, errors, log}  →  stored in _last_result
  │
  ├── history_manager.push('tasks')
  ├── history_manager.push('resources')
  ├── _refresh_all_views()
  └── _mark_dirty()
```

### Early-exit conditions

`run_sync()` returns immediately (with zero counters and an explanatory error entry) when:

- No filter is configured in the project's `jira2project` properties
- The JIRA client is `None`
- `search_issues` returns no results

## Sidecar Data Format

Per-task Jira metadata is stored in the project sidecar file (`.custom-props.json`) under the top-level key `"task_jira"`.  The dictionary key is the MPXJ task UID as a string; the value is a plain dict with at minimum a `"jira_key"` entry.

```json
{
  "task_jira": {
    "42": {
      "jira_key": "PROJ-7",
      "issue_type": "Story",
      "status": "In Progress"
    },
    "43": {
      "jira_key": "PROJ-8",
      "issue_type": "Epic",
      "status": "To Do"
    }
  }
}
```

On the next sync, `_build_jira_key_lookup` reads this dict and reconstructs the Jira-key → MPXJ Task map so existing tasks are updated in place rather than duplicated.

### load_sidecar_task_data(path)

Reads the sidecar JSON file and returns the `"task_jira"` sub-dict (or an empty dict if the file does not exist or has no `"task_jira"` key).

### save_sidecar_task_data(path, data)

Reads the existing sidecar JSON (or starts from an empty dict), replaces the `"task_jira"` key with the new `data`, and writes the file back atomically.

## Epic Hierarchy

Epics are processed in a first pass (before all other issue types) so their MPXJ task objects exist before any sub-tickets reference them as parents.

| MPXJ call | Effect |
| --------- | ------ |
| `task.setSummary(True)` | Marks the task as a WBS summary/container row |
| `task.setRollup(True)` | Rolls up duration and dates from child tasks |
| `child.setParentTask(epic_task)` | Nests the child under the epic in the task hierarchy |

Sub-tickets are linked to their parent epic via `issue.fields.parent.key` (Jira Next-Gen) or the `epic_link` custom field (Jira Classic).  If neither field resolves to a known epic, the task is created at the root level.

## Helper Functions

### _issue_type_label(type_name, labels)

Maps a Jira issue type name (`"Epic"`, `"Story"`, `"Bug"`, `"Task"`, `"Sub-task"`) to a configured short label, falling back to the raw `type_name`.  This helper is still used internally (e.g. for sidecar metadata) but is **no longer used to build the task name** — task names are now the bare Jira `summary` string, with no bracket prefix.

### _status_to_percent(status)

Converts a Jira status string to an integer percent-complete value:

| Jira Status | % Complete |
| ----------- | ---------- |
| `"Done"` / `"Closed"` / `"Resolved"` | 100 |
| `"In Progress"` | 50 |
| `"To Do"` / `"Open"` / anything else | 0 |

### _build_jira_key_lookup(project, task_jira)

Iterates all tasks in the MPXJ project, matches each UID against the `task_jira` sidecar dict, and returns a `{jira_key → MPXJ Task}` mapping.

## Result Dict

`run_sync()` returns — and `get_last_result()` exposes — a dictionary with the following keys:

| Key | Type | Description |
| --- | ---- | ----------- |
| `created` | int | Number of new MPXJ tasks created |
| `updated` | int | Number of existing tasks updated |
| `skipped` | int | Number of issues skipped (no change needed) |
| `errors` | list[str] | Error messages for individual issue failures |
| `log` | list[str] | Per-issue log lines starting with `[CREATE]` or `[UPDATE]` |

## Undo Support

`MainWindow.run_jira_sync()` pushes `tasks` and `resources` undo snapshots **after** the sync completes successfully:

```python
self._history.push('tasks')
self._history.push('resources')
```

This follows the same pattern as other mutation operations in `MainWindow`.  A single Ctrl+Z on either the Tasks or Resources view undoes the entire sync — restoring all task names, parent assignments, and percent-complete values — in one step.

## Specific Fields Fetched

To avoid HTTP 504 Gateway Timeout errors on large result sets, `run_sync` requests only the specific fields it needs rather than `fields=*all`:

| Field | Purpose |
| ----- | ------- |
| `summary` | Task name |
| `issuetype` | Epic detection |
| `status` | Percent-complete mapping |
| `parent` | Modern Jira epic-link |
| `customfield_10014` | Legacy Jira epic-link |
| `duedate` | Optional due date (controlled by `jira_duedate` flag) |
| `assignee` | Optional resource assignment |
| `description` | Optional description |
| `priority` | Optional priority |

## KeePass Unlock Prompt

When the configured Jira server uses `auth_mode="keepass"` and KeePass is not yet unlocked, `MainWindow.run_jira_sync()` prompts the user before attempting to connect:

1. A `QMessageBox.question` asks whether to unlock KeePass now.
2. If the user confirms, `settings_manager.auto_unlock_keepass()` is attempted (uses a cached key file if available).
3. If auto-unlock fails, a `QInputDialog` asks for the master password and calls `settings_manager.unlock_keepass(password)`.
4. If the user cancels at any step, the sync is aborted cleanly.

## Jira Tab in Task Information Dialog

When a task has been linked to a Jira issue (i.e. it has a `task_jira` entry in the sidecar), the **Task Information** dialog shows a **Jira** tab with read-only fields:

| Field | Source |
| ----- | ------ |
| Jira Key | `task_jira[uid]["jira_key"]` |
| Status | `task_jira[uid]["jira_status"]` |
| Browse URL | Constructed from `server_url + "/browse/" + jira_key` (clickable link) |

The sidecar data is loaded by a `_load_task_jira_data(view, task)` helper at the point where the dialog is opened (double-click in Task Sheet, Gantt, or Resource Usage Graph).  The helper requires the view to have a `_get_sidecar_path` callable set on it by `MainWindow`.

## Debug Integration

When the `--debug` flag is active, the debug dump (accessible via **Help → Debug Dump**) includes a `jira_sync_result` block:

```json
"jira_sync_result": {
  "created": 3,
  "updated": 12,
  "skipped": 5,
  "errors": [],
  "log": [
    "[CREATE] PROJ-12 → task uid=47",
    "[UPDATE] PROJ-7 → task uid=42"
  ]
}
```

The block is populated from `get_last_result()` and is omitted when no sync has run in the current session (`_last_result` is `None`).


## Project→Jira Push (`run_push_to_jira`)

The **Project→Jira** direction pushes MPXJ task data from the open project back to a Jira server.  It is the counterpart to the Jira→Project import covered above.

### Entry Point

```
run_push_to_jira(project, server, jira_client, sidecar_path,
                 included_task_uids=None, dry_run=False)
```

| Parameter | Type | Description |
| --------- | ---- | ----------- |
| `project` | MPXJ `ProjectFile` | The currently open project |
| `server` | `dict` | Server config entry (name, url, auth\_mode, …) |
| `jira_client` | `jira.JIRA` | Authenticated Jira client |
| `sidecar_path` | `Path` | Path to `<basename>.custom-props.json` |
| `included_task_uids` | `set[int]` or `None` | If provided, only these task UIDs are processed |
| `dry_run` | `bool` | When `True`, no write API calls are made; result contains `preview_actions` |

### Execution Flow

```
run_push_to_jira(project, server, jira_client, sidecar_path)
  │
  ├── _read_p2j_config(project)
  │     └── reads project2jira container from custom properties
  ├── load_sidecar_task_data(sidecar_path) → task_p2j section
  ├── for each task in project.tasks (filtered by included_task_uids):
  │     ├── _task_to_jira_payload(task, config) → Jira fields dict
  │     ├── check task_p2j[uid]: linked? (has real jira_key) or unlinked?
  │     ├── Unlinked task:
  │     │     ├── unlinked_behavior == "skip" → SKIP
  │     │     └── unlinked_behavior == "create" → CREATE
  │     ├── Linked task:
  │     │     ├── conflict detection: remote_updated > last_pushed_at?
  │     │     │     ├── prefer_project → UPDATE (overwrite Jira)
  │     │     │     ├── prefer_jira   → SKIP
  │     │     │     └── manual_review → SKIP (flagged in preview)
  │     │     ├── UPDATE → _with_retry(issue.update, fields=payload)
  │     │     └── TRANSITION → _with_retry(jira_client.transition_issue, …)
  │     └── hierarchy: if hierarchy_export.enabled and task has parent with jira_key
  │                    → add parent link to issue payload
  ├── save_sidecar_task_data(sidecar_path, task_p2j, jira_push_meta)
  └── returns result dict
```

### Result Dictionary

```python
{
    "created":        int,    # issues created in Jira
    "updated":        int,    # issues updated in Jira
    "transitioned":   int,    # workflow transitions applied
    "skipped":        int,    # tasks skipped (unlinked/conflict/filtered)
    "errors":         list,   # error strings (up to 20)
    "log":            list,   # action log strings (up to 50)
    "preview_actions": list,  # populated only when dry_run=True
    "dry_run":        bool,
}
```

`get_last_push_result()` returns the module-level `_last_push_result` from the most recent call.

### Dry-Run / Preview Mode

When `dry_run=True`, `run_push_to_jira` builds the complete action plan but makes no write API calls.  Each entry in `preview_actions` is a dict:

```python
{
    "task_uid":   int,
    "task_name":  str,
    "action":     "CREATE" | "UPDATE" | "SKIP" | "TRANSITION",
    "jira_key":   str,        # "NEW" for unlinked create actions
    "reason":     str,        # human-readable explanation
    "payload":    dict,       # Jira fields that would be sent
}
```

`MainWindow.run_jira_push()` runs the dry-run pass first, shows the result in `JiraPushPreviewDialog`, then executes the live pass with only the UIDs the user has kept checked.

### Helper Functions

| Function | Description |
| -------- | ----------- |
| `_read_p2j_config(project)` | Extracts and normalises the `project2jira` config container |
| `_p2j_field_enabled(config, field)` | Returns `True` if the field-map row for `field` is enabled |
| `_p2j_jira_field(config, field)` | Returns the Jira field name mapped to `field` |
| `_task_status_string(task)` | `0%`→`"To Do"`, `1–99%`→`"In Progress"`, `100%`→`"Done"` |
| `_task_to_jira_payload(task, config)` | Builds the Jira `fields` dict from MPXJ task attributes |
| `_with_retry(fn, *args, **kwargs)` | Exponential back-off on transient errors (429/5xx/timeout/connection) |

### Sidecar Sections

Two sections are written to `<basename>.custom-props.json` alongside the existing `task_jira` section:

**`task_p2j`** — per-task push metadata:

```json
{
  "task_p2j": {
    "42": {"jira_key": "PROJ-7", "last_pushed_at": "2025-10-01T09:00:00"},
    "99": {"jira_key": "NEW",    "last_pushed_at": null}
  }
}
```

A `jira_key` of `"NEW"` marks an unlinked task.  After a successful create the key is replaced with the new Jira issue key.

**`jira_push_meta`** — run-level metadata and audit log:

```json
{
  "jira_push_meta": {
    "last_run_at": "2025-10-01T09:00:00",
    "last_successful_push": "2025-10-01T09:00:00",
    "audit_sessions": [
      {
        "run_at": "2025-10-01T09:00:00",
        "created": 1, "updated": 3,
        "transitioned": 2, "skipped": 0, "errors": 0
      }
    ]
  }
}
```

`audit_sessions` is capped at 20 entries; the oldest entry is dropped when the cap is exceeded.

### Conflict Detection

The engine compares `issue.fields.updated` (ISO timestamp returned by the Jira REST API) against `task_p2j[uid].last_pushed_at`:

| `conflict_policy` | Behaviour when remote is newer |
| ----------------- | ------------------------------ |
| `prefer_project` | Always write the project value to Jira (overwrite) |
| `prefer_jira` | Skip the task; increment `skipped` counter |
| `manual_review` | Skip the task; flag in `preview_actions` for user review |

### Hierarchy Export

When `hierarchy_export.enabled` is `True` in the `project2jira` config, the engine looks up the MPXJ parent task's `jira_key` in `task_p2j` and adds it as a `parent` field in the Jira update payload.  The parent task must already be linked (have a real Jira key).

### Auditability

Every completed push run appends an audit record to `jira_push_meta.audit_sessions`.  The record captures `run_at`, `created`, `updated`, `transitioned`, `skipped`, and `errors` counts.  Dry-run passes are **not** recorded.

### Debug Integration

When the `--debug` flag is active, the debug dump includes two additional blocks:

```json
"jira_push_result": {
  "created": 1,
  "updated": 3,
  "transitioned": 2,
  "skipped": 0,
  "errors": [],
  "log": [
    "[CREATE] task uid=99 → PROJ-52",
    "[UPDATE] PROJ-7 ← task uid=42"
  ],
  "dry_run": false
},
"jira_push_meta": {
  "last_run_at": "2025-10-01T09:00:00",
  "last_successful_push": "2025-10-01T09:00:00",
  "audit_sessions": [{ "run_at": "2025-10-01T09:00:00", "created": 1,
                       "updated": 3, "transitioned": 2, "skipped": 0, "errors": 0 }]
}
```

Both blocks are omitted when no push has run in the current session.
