# jira_sync.py - Jira → Project sync execution engine.
#
# Fetches Jira issues matching a configured filter and creates or updates
# MPXJ tasks in the in-memory project.  Epic issues are converted to summary
# (rollup) tasks; sub-tickets become child tasks underneath them.
#
# Per-task Jira metadata is persisted in a "task_jira" top-level key inside
# the project's .custom-props.json sidecar:
#   {
#     "task_jira": {
#       "<task_unique_id>": {
#         "jira_key": "PROJ-123",
#         "jira_status": "In Progress",
#         ...
#       }
#     }
#   }
#
# Public API
# ----------
#   run_sync(project, server, jira_client, sidecar_path) -> dict
#   get_last_result()                                     -> dict | None
#   load_sidecar_task_data(sidecar_path)                  -> dict
#   save_sidecar_task_data(sidecar_path, data)            -> None

from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone
from typing import Optional

from app_debug import is_debug as _is_debug  # type: ignore

# ---------------------------------------------------------------------------
# Module-level state (for debug dump)
# ---------------------------------------------------------------------------
_last_result: Optional[dict] = None

# Default issue-type abbreviations used for task name prefixes ([Epic], [Story], …)
_DEFAULT_ISSUE_TYPE_LABELS: dict = {
    "Epic":         "Epic",
    "Story":        "Story",
    "Task":         "Task",
    "Sub-task":     "Sub",
    "Bug":          "Bug",
    "Feature":      "Feature",
    "Improvement":  "Improve",
    "Change":       "Change",
    "Incident":     "Incident",
    "Problem":      "Problem",
    "Service Request": "SR",
    "Risk":         "Risk",
}

# Status → percentage-complete mapping (used when jira_status_percent is enabled)
_STATUS_PERCENT_MAP: dict = {
    "to do":        0,
    "open":         0,
    "new":          0,
    "backlog":      0,
    "selected for development": 0,
    "ready":        0,
    "in progress":  50,
    "in review":    75,
    "in testing":   80,
    "testing":      80,
    "done":         100,
    "closed":       100,
    "resolved":     100,
    "won't do":     0,
    "cancelled":    0,
    "invalid":      0,
}

_J2P_ADVANCED_DEFAULTS: dict = {
    "relink": {
        "enabled": False,
        "behavior": "messagebox",  # skip|relink|messagebox
    },
    "incremental": {
        "enabled": False,
        "mode": "changed_since_last_sync",  # changed_since_last_sync|full_resync
    },
    "conflict": {
        "enabled": False,
        "policy": "messagebox",  # prefer_jira|prefer_local|manual_review|messagebox
        "field_policy": {
            "status": "messagebox",
            "dates": "messagebox",
            "assignee": "messagebox",
            "estimate": "messagebox",
            "labels": "messagebox",
        },
    },
    "orphan": {
        "enabled": False,
        "behavior": "messagebox",  # keep|unlink|close|delete|messagebox
    },
    "normalize": {
        "enabled": False,
    },
    "hierarchy": {
        "enabled": False,
    },
    "dependencies": {
        "enabled": False,
    },
    "reliability": {
        "enabled": False,
        "max_retries": 3,
        "backoff_seconds": 1.0,
    },
    "preview": {
        "enabled": False,
        "include_keys": [],
        "exclude_keys": [],
    },
    "closed_state_completion": {
        "enabled": False,
    },
}


def _now_iso_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_jira_datetime(date_str: str) -> str:
    """Convert a Jira ISO datetime string (e.g. '2024-01-15T10:30:00.000+0200')
    to a UTC ISO-8601 string.  Returns the input string unchanged if parsing fails.
    """
    if not date_str or len(date_str) < 10:
        return date_str
    try:
        import re as _re
        s = date_str.strip()
        # Date-only strings (no time component) need no timezone conversion
        if "T" not in s:
            return date_str
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        # Normalize offset without colon: +0200 → +02:00
        s = _re.sub(r"([+-])(\d{2})(\d{2})$", r"\1\2:\3", s)
        # Strip milliseconds: .123+... → +...
        s = _re.sub(r"\.\d+([+-])", r"\1", s)
        dt = datetime.fromisoformat(s)
        dt_utc = dt.astimezone(timezone.utc)
        return dt_utc.isoformat().replace("+00:00", "Z")
    except Exception:
        return date_str


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge dicts, preserving nested defaults."""
    result = dict(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _get_advanced_config(j2p: dict) -> dict:
    return _deep_merge(_J2P_ADVANCED_DEFAULTS, j2p.get("advanced") or {})


def _sanitize_text(value: str) -> str:
    """Best-effort sanitizer for Jira rich-text/markdown payloads."""
    if not value:
        return ""
    text = str(value)
    text = re.sub(r"\{code(?::[^}]*)?\}", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\{[^{}]+\}", "", text)
    text = re.sub(r"\[(.*?)\|https?://[^\]]+\]", r"\1", text)
    text = re.sub(r"[*_~`#]", "", text)
    return text.strip()


def _safe_issue_field(fields, attr_name: str):
    try:
        return getattr(fields, attr_name, None)
    except Exception:
        return None


def _is_transient_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(token in msg for token in ("429", "too many", "timeout", "timed out", "503", "502", "500", "connection", "temporary"))


# ---------------------------------------------------------------------------
# Public helpers for sidecar task data
# ---------------------------------------------------------------------------

def load_sidecar_task_data(sidecar_path: str) -> dict:
    """Load the task_jira dict from the sidecar JSON.  Returns {} on missing/error."""
    if not sidecar_path or not os.path.exists(sidecar_path):
        return {}
    try:
        with open(sidecar_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("task_jira", {})
    except Exception as exc:
        if _is_debug():
            print(f"[DEBUG] jira_sync: load_sidecar_task_data error: {exc}")
        return {}


def _load_sidecar_dict(sidecar_path: str) -> dict:
    """Load full sidecar JSON dict (empty on missing/error)."""
    if not sidecar_path or not os.path.exists(sidecar_path):
        return {}
    try:
        with open(sidecar_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_sidecar_task_data(sidecar_path: str, task_jira: dict) -> None:
    """Write the task_jira dict into the sidecar JSON (merging with existing data)."""
    try:
        existing: dict = _load_sidecar_dict(sidecar_path)
        existing["task_jira"] = task_jira
        with open(sidecar_path, "w", encoding="utf-8") as f:
            json.dump(existing, f, ensure_ascii=False, indent=2)
    except Exception as exc:
        if _is_debug():
            print(f"[DEBUG] jira_sync: save_sidecar_task_data error: {exc}")


def _save_sidecar_dict(sidecar_path: str, data: dict) -> None:
    """Persist full sidecar dict."""
    if not sidecar_path:
        return
    try:
        with open(sidecar_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as exc:
        if _is_debug():
            print(f"[DEBUG] jira_sync: _save_sidecar_dict error: {exc}")


# ---------------------------------------------------------------------------
# Debug accessor
# ---------------------------------------------------------------------------

def get_last_result() -> Optional[dict]:
    """Return the result dict from the most recent run_sync() call, or None."""
    return _last_result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _read_j2p_config(project) -> dict:
    """Extract the jira2project config dict from MPXJ project custom properties."""
    try:
        cp = project.getProjectProperties().getCustomProperties()
        if cp is None:
            return {}
        raw = cp.get("jira2project")
        if raw is None:
            return {}
        return json.loads(str(raw))
    except Exception:
        return {}


def _get_field_flag(j2p: dict, field: str) -> bool:
    """Return True if field is enabled in jira2project.fields.*."""
    return bool((j2p.get("fields") or {}).get(field, False))


def _safe_str(val) -> str:
    if val is None:
        return ""
    return str(val)


def _issue_type_label(issue_type_name: str, issue_type_labels: dict) -> str:
    """Return the display abbreviation for an issue type."""
    if issue_type_name in issue_type_labels:
        return issue_type_labels[issue_type_name]
    return _DEFAULT_ISSUE_TYPE_LABELS.get(issue_type_name, issue_type_name)


def _status_to_percent(status_name: str) -> int:
    """Map a Jira status name to a 0–100 percentage value."""
    return _STATUS_PERCENT_MAP.get(status_name.lower(), 0)


def _parse_jira_date(date_str: Optional[str], normalize: bool = False):
    """Parse 'YYYY-MM-DD' or ISO datetime string into java.time.LocalDateTime.
    Returns None if parsing fails or jpype is not available.
    When *normalize* is True, timezone-aware datetimes are converted to UTC
    before extracting the date portion.
    """
    if not date_str:
        return None
    try:
        import jpype  # type: ignore
        LDT = jpype.JClass("java.time.LocalDateTime")
        date_part = date_str[:10]
        if normalize and len(date_str) > 10:
            date_part = _normalize_jira_datetime(date_str)[:10]
        parts = date_part.split("-")
        if len(parts) != 3:
            return None
        year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
        return LDT.of(year, month, day, 8, 0, 0)
    except Exception:
        return None


def _build_jira_key_lookup(project, task_jira: dict) -> dict:
    """Return {jira_key: mpxj_task} by scanning task_jira sidecar entries."""
    uid_to_task: dict = {}
    try:
        for t in project.getTasks():
            if t.getName() is None:
                continue
            try:
                uid_to_task[str(t.getUniqueID())] = t
            except Exception:
                pass
    except Exception:
        pass

    key_to_task: dict = {}
    for uid_str, jira_data in task_jira.items():
        jira_key = jira_data.get("jira_key", "")
        if jira_key and uid_str in uid_to_task:
            key_to_task[jira_key] = uid_to_task[uid_str]
    return key_to_task


def _next_task_ids(project) -> tuple[int, int]:
    """Return (next_id, next_uid) for a new task."""
    max_id, max_uid = 0, 0
    try:
        for t in project.getTasks():
            try:
                tid = int(str(t.getID() or 0))
                uid = int(str(t.getUniqueID() or 0))
                if tid > max_id:
                    max_id = tid
                if uid > max_uid:
                    max_uid = uid
            except Exception:
                pass
    except Exception:
        pass
    return max_id + 1, max_uid + 1


def _find_or_create_resource(project, assignee_name: str):
    """Return existing resource by name or create a new one."""
    try:
        from java.lang import Integer as JInteger  # type: ignore
        for res in project.getResources():
            if res.getName() and str(res.getName()) == assignee_name:
                return res
        # Create new resource
        next_uid, next_id = 1, 1
        max_uid, max_id = 0, 0
        for res in project.getResources():
            try:
                u = int(str(res.getUniqueID() or 0))
                i = int(str(res.getID() or 0))
                if u > max_uid:
                    max_uid = u
                if i > max_id:
                    max_id = i
            except Exception:
                pass
        next_uid = max_uid + 1
        next_id = max_id + 1
        res = project.addResource()
        res.setName(assignee_name)
        res.setUniqueID(JInteger(next_uid))
        res.setID(JInteger(next_id))
        return res
    except Exception as exc:
        if _is_debug():
            print(f"[DEBUG] jira_sync: _find_or_create_resource error: {exc}")
        return None


def _apply_fields_to_task(task, issue, j2p: dict, is_new: bool, errors: list,
                           log_lines: list, normalize_enabled: bool = False,
                           skip_fields: Optional[set] = None,
                           closed_state_completion_enabled: bool = False) -> dict:
    """Apply enabled jira2project field flags from a Jira issue to an MPXJ task.

    Returns a dict of {field_name: written_value} for debug logging.
    """
    written: dict = {}

    try:
        fields = issue.fields

        def _f(name):
            if skip_fields and name in skip_fields:
                return False
            return _get_field_flag(j2p, name)

        # --- Dates ---
        if _f("jira_due_date") and getattr(fields, "duedate", None):
            ldt = _parse_jira_date(fields.duedate, normalize=normalize_enabled)
            if ldt is not None:
                try:
                    task.setDeadline(ldt)
                    written["deadline"] = fields.duedate
                except Exception:
                    pass

        if _f("jira_created_date") and getattr(fields, "created", None):
            try:
                raw = str(fields.created or "")
                val = _normalize_jira_datetime(raw) if normalize_enabled else raw
                existing_notes = str(task.getNotes() or "")
                if "Jira Created:" not in existing_notes:
                    task.setNotes(existing_notes + f"\nJira Created: {val[:19]}")
                written["jira_created_date"] = val[:19]
            except Exception:
                pass

        if _f("jira_updated_date") and getattr(fields, "updated", None):
            try:
                raw = str(fields.updated or "")
                val = _normalize_jira_datetime(raw) if normalize_enabled else raw
                existing_notes = str(task.getNotes() or "")
                if "Jira Updated:" not in existing_notes:
                    task.setNotes(existing_notes + f"\nJira Updated: {val[:19]}")
                written["jira_updated_date"] = val[:19]
            except Exception:
                pass

        if _f("jira_resolution_date") and getattr(fields, "resolutiondate", None):
            try:
                raw = str(fields.resolutiondate or "")
                val = _normalize_jira_datetime(raw) if normalize_enabled else raw
                existing_notes = str(task.getNotes() or "")
                if "Jira Resolved:" not in existing_notes:
                    task.setNotes(existing_notes + f"\nJira Resolved: {val[:19]}")
                written["jira_resolution_date"] = val[:19]
            except Exception:
                pass

        # --- Status ---
        status_name = ""
        if getattr(fields, "status", None):
            try:
                status_name = str(fields.status.name)
            except Exception:
                pass
        if _f("jira_status") and status_name:
            try:
                task.setNotes((task.getNotes() or "") + f"\nJira Status: {status_name}")
                written["jira_status_note"] = status_name
            except Exception:
                pass

        if closed_state_completion_enabled and status_name.lower() in ("closed", "resolved", "done"):
            try:
                import jpype  # type: ignore
                task.setPercentageComplete(jpype.JClass("java.lang.Double")(100.0))
                written["pct_complete_closed_state"] = 100
            except Exception:
                pass

        if _f("jira_status_percent") and status_name:
            try:
                pct = _status_to_percent(status_name)
                import jpype  # type: ignore
                Number = jpype.JClass("java.lang.Number")
                from org.mpxj import Duration, TimeUnit  # type: ignore
                task.setPercentageComplete(
                    jpype.JClass("java.lang.Double")(float(pct))
                )
                written["pct_complete"] = pct
            except Exception as exc:
                if _is_debug():
                    print(f"[DEBUG] jira_sync: setPercentageComplete error: {exc}")

        # --- Assignee → resource assignment ---
        if _f("jira_assignee") and getattr(fields, "assignee", None):
            try:
                assignee_name = str(fields.assignee.displayName)
                project = task.getParentFile()
                res = _find_or_create_resource(project, assignee_name)
                if res is not None:
                    # Remove old assignments from this task first to avoid duplicates
                    try:
                        existing_assignments = list(task.getResourceAssignments() or [])
                        for asn in existing_assignments:
                            try:
                                asn_res = asn.getResource()
                                if asn_res is not None and str(asn_res.getName()) == assignee_name:
                                    task.getResourceAssignments().remove(asn)
                            except Exception:
                                pass
                    except Exception:
                        pass
                    task.addResourceAssignment(res)
                    written["assignee"] = assignee_name
            except Exception as exc:
                errors.append(f"assignee for {issue.key}: {exc}")
                if _is_debug():
                    print(f"[DEBUG] jira_sync: assignee error for {issue.key}: {exc}")

        # --- Description → notes ---
        if _f("jira_description") and getattr(fields, "description", None):
            try:
                desc = str(fields.description or "")
                if normalize_enabled:
                    desc = _sanitize_text(desc)
                if desc:
                    task.setNotes(desc[:2000])
                    written["notes_from_description"] = True
            except Exception:
                pass

        # --- Priority ---
        if _f("jira_priority") and getattr(fields, "priority", None):
            try:
                prio = str(fields.priority.name)
                existing_notes = str(task.getNotes() or "")
                if "Jira Priority:" not in existing_notes:
                    task.setNotes(existing_notes + f"\nJira Priority: {prio}")
                written["jira_priority"] = prio
            except Exception:
                pass

    except Exception as exc:
        errors.append(f"field apply for {getattr(issue, 'key', '?')}: {exc}")
        if _is_debug():
            print(f"[DEBUG] jira_sync: _apply_fields_to_task exception: {exc}")

    return written


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_sync(
    project,
    server: dict,
    jira_client,
    sidecar_path: str,
    relink_callback=None,
    conflict_callback=None,
    orphan_callback=None,
    progress_callback=None,
    force_incremental: bool = False,
    force_full_resync: bool = False,
) -> dict:
    """Synchronise Jira issues into the MPXJ project.

    Args:
        project:              MPXJ ProjectFile (modified in-place)
        server:               Server config dict from settings_manager.get_jira_servers()
        jira_client:          Authenticated jira.JIRA instance
        sidecar_path:         Path to the .custom-props.json sidecar file
        relink_callback:      callable(issue_key, stored_id, incoming_id) -> "skip"|"relink"
                              Called when behavior=="messagebox" and an issue ID has changed.
        conflict_callback:    callable(issue_key, task_name) -> "prefer_jira"|"prefer_local"|"skip"
                              Called when policy=="messagebox" and a local conflict is detected.
        orphan_callback:      callable(jira_key, task_name) -> "keep"|"unlink"|"close"|"delete"
                              Called per orphan when behavior=="messagebox".
        force_incremental:    If True, behave as if incremental.enabled=True and
                              mode=changed_since_last_sync, regardless of project config.
        force_full_resync:    If True, bypass the last-sync timestamp so all issues are
                              re-fetched, regardless of project config.
        When a callback is None and the configured behavior is "messagebox", the
        engine falls back to the safe default ("skip" / "keep").

    Returns:
        {"created": int, "updated": int, "skipped": int, "errors": list[str]}
    """
    global _last_result

    result: dict = {
        "created": 0,
        "updated": 0,
        "skipped": 0,
        "errors": [],
        "log":    [],
        "preview_actions": [],
        "processed": 0,
        "orphans": {
            "detected": 0,
            "handled": 0,
            "behavior": None,
        },
    }

    _LOG_PREFIX = "[DEBUG] jira2project_sync.run:"

    def _log(msg: str):
        if _is_debug():
            print(f"{_LOG_PREFIX} {msg}")
        result["log"].append(msg)

    try:
        # ---- Read project config -------------------------------------------
        j2p = _read_j2p_config(project)
        advanced = _get_advanced_config(j2p)
        normalize_enabled = bool((advanced.get("normalize") or {}).get("enabled", False))
        filter_val = j2p.get("filter", "")
        filter_type = j2p.get("filter_type", "jql")
        issue_type_labels: dict = j2p.get("issue_type_labels") or {}

        if not filter_val:
            result["errors"].append("No filter configured — nothing to sync.")
            _last_result = result
            return result

        # ---- Resolve filter to JQL ----------------------------------------
        from integrations.jira_integration import resolve_filter_to_jql  # type: ignore
        jql, err = resolve_filter_to_jql(jira_client, filter_val, filter_type)
        if err:
            result["errors"].append(f"Filter resolution failed: {err}")
            _last_result = result
            return result

        # Sidecar metadata (used for incremental mode and audit trail)
        sidecar_data = _load_sidecar_dict(sidecar_path)
        sync_meta = sidecar_data.get("jira_sync_meta") or {}
        task_jira = sidecar_data.get("task_jira") or {}

        incremental_cfg = advanced.get("incremental") or {}
        # force_incremental / force_full_resync override the project-level config
        if force_full_resync:
            # Treat as if incremental is off — fetch everything
            incremental_cfg = {"enabled": False}
        elif force_incremental:
            # Treat as if incremental is on in changed_since_last_sync mode
            incremental_cfg = {"enabled": True, "mode": "changed_since_last_sync"}
        if incremental_cfg.get("enabled") and incremental_cfg.get("mode") == "changed_since_last_sync":
            since = str(sync_meta.get("last_successful_sync") or "").strip()
            if since:
                safe_since = since.replace("T", " ").replace("+00:00", "")[:16]
                jql = f"({jql}) AND updated >= \"{safe_since}\""

        _log(f"Resolved JQL: {jql}")
        if progress_callback:
            progress_callback(5, "Resolving Jira filter\u2026")

        # ---- Fetch issues ---------------------------------------------------
        # Request only the fields the sync actually uses to avoid 504 timeouts
        # from requesting *all fields for large result sets.
        _SYNC_FIELDS = [
            "summary",          # task name
            "updated",          # conflict / audit
            "issuetype",        # Epic detection
            "status",           # status notes / percent complete
            "parent",           # modern Jira epic-link (parent field)
            "customfield_10014",# legacy Jira epic-link custom field
            "duedate",          # jira_due_date checkbox
            "created",          # jira_created_date checkbox
            "resolutiondate",   # jira_resolution_date checkbox
            "assignee",         # jira_assignee checkbox
            "description",      # jira_description checkbox
            "priority",         # jira_priority checkbox
            "issuelinks",       # dependency mapping
            "labels",           # conflict policy bucket
            "timeoriginalestimate", "timeestimate", "timespent",  # estimate bucket
        ]

        reliability_cfg = advanced.get("reliability") or {}
        retry_enabled = bool(reliability_cfg.get("enabled", False))
        max_retries = int(reliability_cfg.get("max_retries", 3) or 3)
        backoff_seconds = float(reliability_cfg.get("backoff_seconds", 1.0) or 1.0)

        def _search_issues_page(start_at: int, page_size: int):
            attempt = 0
            while True:
                try:
                    return jira_client.search_issues(
                        jql, startAt=start_at, maxResults=page_size,
                        fields=",".join(_SYNC_FIELDS)
                    )
                except Exception as exc:
                    if not retry_enabled or not _is_transient_error(exc) or attempt >= max_retries:
                        raise
                    attempt += 1
                    wait_s = backoff_seconds * (2 ** (attempt - 1))
                    _log(f"Transient Jira error at page {start_at}: {exc}. Retry {attempt}/{max_retries} in {wait_s:.1f}s")
                    time.sleep(wait_s)

        try:
            all_issues = []
            start_at = 0
            page_size = 100
            while True:
                page = _search_issues_page(start_at, page_size)
                if not page:
                    break
                all_issues.extend(page)
                _log(f"Fetched {len(all_issues)} issues so far (page startAt={start_at})")
                if progress_callback:
                    progress_callback(-1, f"Fetching issues\u2026 {len(all_issues)} so far")
                if len(page) < page_size:
                    break
                start_at += len(page)
        except Exception as exc:
            result["errors"].append(f"Jira API error: {exc}")
            _last_result = result
            return result

        _log(f"Fetched {len(all_issues)} issues total")
        if progress_callback:
            progress_callback(30, f"Processing {len(all_issues)} issue(s)\u2026")

        # ---- Sort: Epics first, then the rest --------------------------------
        epics = [i for i in all_issues
                 if _safe_str(getattr(i.fields, "issuetype", None) and
                              i.fields.issuetype.name) == "Epic"
                 or (hasattr(i.fields, "issuetype") and
                     i.fields.issuetype and
                     str(i.fields.issuetype.name) == "Epic")]
        non_epics = [i for i in all_issues if i not in epics]

        # ---- Load sidecar task data ----------------------------------------
        if incremental_cfg.get("enabled") and incremental_cfg.get("mode") == "full_resync":
            _log("Incremental mode requested full_resync: rebuilding links from Jira response.")
            task_jira = {}

        key_to_task = _build_jira_key_lookup(project, task_jira)

        # Build ID lookup to treat Jira ID as canonical identity.
        id_to_task: dict = {}
        try:
            uid_to_task_ref: dict = {}
            for t in project.getTasks():
                try:
                    uid_to_task_ref[str(t.getUniqueID())] = t
                except Exception:
                    pass
            for uid_str, meta in (task_jira or {}).items():
                jira_id = str(meta.get("jira_id") or "").strip()
                if jira_id and uid_str in uid_to_task_ref:
                    id_to_task[jira_id] = uid_to_task_ref[uid_str]
        except Exception:
            pass

        # ---- Build a UID → task map for fast lookup -------------------------
        uid_to_task: dict = {}
        try:
            for t in project.getTasks():
                if t.getName() is None:
                    continue
                try:
                    uid_to_task[int(str(t.getUniqueID()))] = t
                except Exception:
                    pass
        except Exception:
            pass

        # ---- Process issues (Epics first, then sub-tickets) ------------------
        epic_key_to_task: dict = {}  # epic jira_key → mpxj summary task

        from java.lang import Integer as _JInt  # type: ignore

        for issue in (epics + non_epics):
            try:
                issue_key = str(issue.key)
                issue_id = str(getattr(issue, "id", "") or "")
                fields = issue.fields
                result["processed"] += 1
                if progress_callback:
                    _n  = result["processed"]
                    _tot = max(1, len(epics) + len(non_epics))
                    _pct = 30 + int(_n / _tot * 65)
                    progress_callback(_pct, f"Processing issue {_n}/{_tot}\u2026")
                summary = _safe_str(getattr(fields, "summary", ""))
                issue_type_name = _safe_str(
                    getattr(fields, "issuetype", None) and fields.issuetype and
                    fields.issuetype.name
                )
                is_epic = issue_type_name == "Epic"

                task_name = summary

                # Selective apply controls (preview include/exclude lists).
                preview_cfg = advanced.get("preview") or {}
                include_keys = {str(k).strip() for k in (preview_cfg.get("include_keys") or []) if str(k).strip()}
                exclude_keys = {str(k).strip() for k in (preview_cfg.get("exclude_keys") or []) if str(k).strip()}
                if include_keys and issue_key not in include_keys:
                    result["skipped"] += 1
                    _log(f"[SKIP] {issue_key} — not in include list")
                    continue
                if issue_key in exclude_keys:
                    result["skipped"] += 1
                    _log(f"[SKIP] {issue_key} — in exclude list")
                    continue

                # ---- Determine if this is a create or update -----------------
                existing_task = id_to_task.get(issue_id) or key_to_task.get(issue_key)

                # Relink policy: same key points to a different stored ID.
                relink_cfg = advanced.get("relink") or {}
                if existing_task is not None and issue_id:
                    existing_uid = str(existing_task.getUniqueID())
                    existing_meta = task_jira.get(existing_uid) or {}
                    existing_id = str(existing_meta.get("jira_id") or "").strip()
                    if existing_id and existing_id != issue_id:
                        behavior = str(relink_cfg.get("behavior") or "messagebox")
                        if behavior == "messagebox" and relink_callback is not None:
                            behavior = relink_callback(issue_key, existing_id, issue_id) or "skip"
                        allow_relink = bool(relink_cfg.get("enabled", False)) and behavior == "relink"
                        if not allow_relink:
                            result["skipped"] += 1
                            _log(f"[SKIP] {issue_key} — relink blocked (stored id={existing_id}, incoming id={issue_id}, behavior={behavior})")
                            continue

                is_update = existing_task is not None

                preview_enabled = bool((advanced.get("preview") or {}).get("enabled", False))
                action = "update" if is_update else "create"
                if preview_enabled:
                    result["preview_actions"].append({
                        "issue_key": issue_key,
                        "issue_id": issue_id,
                        "action": action,
                        "summary": summary,
                    })
                    result["skipped"] += 1
                    _log(f"[PREVIEW] {issue_key} — {action}")
                    continue

                if is_update:
                    # --- UPDATE existing task ----------------------------------
                    task = existing_task

                    # Conflict detection: compare current task state against the last snapshot.
                    conflict_cfg = advanced.get("conflict") or {}
                    conflict_policy = str(conflict_cfg.get("policy") or "messagebox")
                    skip_fields: set = set()
                    if conflict_cfg.get("enabled"):
                        uid_str = str(task.getUniqueID())
                        existing_meta = task_jira.get(uid_str) or {}
                        snapshot = existing_meta.get("last_sync_snapshot") or {}
                        local_name = _safe_str(task.getName())
                        local_notes = _safe_str(task.getNotes())
                        if snapshot and (
                            _safe_str(snapshot.get("name")) != local_name
                            or _safe_str(snapshot.get("notes")) != local_notes
                        ):
                            effective_policy = conflict_policy
                            if conflict_policy == "messagebox":
                                if conflict_callback is not None:
                                    effective_policy = conflict_callback(
                                        issue_key, local_name
                                    ) or "skip"
                                else:
                                    effective_policy = "skip"
                            if effective_policy == "prefer_local":
                                field_policy = conflict_cfg.get("field_policy") or {}
                                if str(field_policy.get("status", "")) == "prefer_local":
                                    skip_fields.update({"jira_status", "jira_status_percent"})
                                if str(field_policy.get("dates", "")) == "prefer_local":
                                    skip_fields.update({"jira_due_date", "jira_created_date",
                                                        "jira_updated_date", "jira_resolution_date"})
                                if str(field_policy.get("assignee", "")) == "prefer_local":
                                    skip_fields.add("jira_assignee")
                                if str(field_policy.get("estimate", "")) == "prefer_local":
                                    skip_fields.update({"jira_time_spent", "jira_remaining_estimate",
                                                        "jira_original_estimate", "jira_time_spent_seconds"})
                                if str(field_policy.get("labels", "")) == "prefer_local":
                                    skip_fields.add("jira_labels")
                            elif effective_policy not in ("prefer_jira", "manual_review"):
                                # skip / messagebox-without-callback / unrecognized
                                result["skipped"] += 1
                                _log(f"[SKIP] {issue_key} — local conflict detected; policy={effective_policy}")
                                continue
                            elif effective_policy == "manual_review":
                                result["skipped"] += 1
                                _log(f"[SKIP] {issue_key} — local conflict detected; policy=manual_review")
                                continue

                    old_name = _safe_str(task.getName())
                    # Always track summary name
                    task.setName(task_name)

                    # Collect fields written for diff logging
                    old_vals: dict = {"name": old_name}
                    new_vals: dict = {"name": task_name}

                    written = _apply_fields_to_task(
                        task, issue, j2p, is_new=False,
                        errors=result["errors"], log_lines=result["log"],
                        normalize_enabled=normalize_enabled,
                        skip_fields=skip_fields,
                        closed_state_completion_enabled=bool((advanced.get("closed_state_completion") or {}).get("enabled", False)),
                    )
                    new_vals.update(written)

                    diff = {k: (old_vals.get(k), v)
                            for k, v in new_vals.items()
                            if old_vals.get(k) != v}

                    _log(f"[UPDATE] {issue_key} — task uid={task.getUniqueID()}"
                         f"\n  received: {{'summary': {summary!r}, 'status': "
                         f"{_safe_str(getattr(fields, 'status', None) and fields.status and fields.status.name)!r}}}"
                         f"\n  written: {new_vals}"
                         f"\n  diff: {diff}")

                    # Update sidecar
                    uid_str = str(task.getUniqueID())
                    if uid_str not in task_jira:
                        task_jira[uid_str] = {}
                    raw_updated = _safe_str(_safe_issue_field(fields, "updated"))
                    remote_updated = _normalize_jira_datetime(raw_updated) if normalize_enabled else raw_updated
                    task_jira[uid_str]["jira_key"] = issue_key
                    if issue_id:
                        task_jira[uid_str]["jira_id"] = issue_id
                    task_jira[uid_str]["jira_status"] = _safe_str(
                        getattr(fields, "status", None) and fields.status and fields.status.name
                    )
                    task_jira[uid_str]["last_imported_at"] = _now_iso_utc()
                    task_jira[uid_str]["last_remote_updated"] = remote_updated
                    task_jira[uid_str]["last_sync_snapshot"] = {
                        "name": _safe_str(task.getName()),
                        "notes": _safe_str(task.getNotes()),
                    }
                    result["updated"] += 1

                    if is_epic:
                        epic_key_to_task[issue_key] = task

                else:
                    # --- CREATE new task ---------------------------------------
                    next_id, next_uid = _next_task_ids(project)

                    task = project.addTask()
                    task.setName(task_name)
                    task.setID(_JInt(next_id))
                    task.setUniqueID(_JInt(next_uid))

                    if is_epic:
                        # Epic → summary task (Summary=1, Rollup=1)
                        try:
                            task.setSummary(True)
                        except Exception:
                            pass
                        try:
                            task.setRollup(True)
                        except Exception:
                            pass
                        epic_key_to_task[issue_key] = task
                    else:
                        # Check if this issue belongs to an Epic in our set
                        epic_link_key = None
                        try:
                            # Modern Jira: parent field
                            if hasattr(fields, "parent") and fields.parent:
                                epic_link_key = str(fields.parent.key)
                        except Exception:
                            pass
                        if not epic_link_key:
                            try:
                                # Old Jira: customfield_10014 (Epic Link)
                                epic_link = getattr(fields, "customfield_10014", None)
                                if epic_link:
                                    epic_link_key = str(epic_link)
                            except Exception:
                                pass

                        hierarchy_enabled = bool((advanced.get("hierarchy") or {}).get("enabled", False))
                        if "advanced" not in j2p:
                            # Backward compatibility: legacy projects imported hierarchy implicitly.
                            hierarchy_enabled = True
                        if hierarchy_enabled and epic_link_key and epic_link_key in epic_key_to_task:
                            parent_task = epic_key_to_task[epic_link_key]
                            try:
                                task.setParentTask(parent_task)
                                task.setOutlineLevel(_JInt(
                                    int(str(parent_task.getOutlineLevel() or 1)) + 1
                                ))
                            except Exception as exc2:
                                if _is_debug():
                                    print(f"[DEBUG] jira_sync: setParentTask error: {exc2}")

                    # Apply start/finish dates from due date or today as fallback
                    try:
                        import jpype  # type: ignore
                        LDT = jpype.JClass("java.time.LocalDateTime")
                        import datetime as _dt
                        today = _dt.date.today()
                        start_ldt = LDT.of(today.year, today.month, today.day, 8, 0, 0)
                        task.setStart(start_ldt)
                    except Exception:
                        pass

                    written = _apply_fields_to_task(
                        task, issue, j2p, is_new=True,
                        errors=result["errors"], log_lines=result["log"],
                        normalize_enabled=normalize_enabled,
                        closed_state_completion_enabled=bool((advanced.get("closed_state_completion") or {}).get("enabled", False)),
                    )

                    # Optional dependency import from Jira issue links.
                    if bool((advanced.get("dependencies") or {}).get("enabled", False)):
                        try:
                            links = list(_safe_issue_field(fields, "issuelinks") or [])
                            for link in links:
                                try:
                                    linked_issue = getattr(link, "inwardIssue", None) or getattr(link, "outwardIssue", None)
                                    if linked_issue is None:
                                        continue
                                    linked_key = str(getattr(linked_issue, "key", "") or "")
                                    dep_task = key_to_task.get(linked_key)
                                    if dep_task is not None:
                                        try:
                                            task.addPredecessor(dep_task)
                                        except Exception:
                                            pass
                                except Exception:
                                    pass
                        except Exception:
                            pass

                    _log(f"[CREATE] {issue_key} — new task id={next_id}, uid={next_uid}"
                         f"\n  received: {{'summary': {summary!r}, 'issuetype': {issue_type_name!r}, "
                         f"'status': {_safe_str(getattr(fields, 'status', None) and fields.status and fields.status.name)!r}}}"
                         f"\n  written: {{'name': {task_name!r}, **{written}}}")

                    # Record in sidecar
                    uid_str = str(next_uid)
                    task_jira[uid_str] = {
                        "jira_key": issue_key,
                        "jira_id": issue_id,
                        "jira_status": _safe_str(
                            getattr(fields, "status", None) and fields.status and fields.status.name
                        ),
                        "last_imported_at": _now_iso_utc(),
                        "last_remote_updated": (
                            _normalize_jira_datetime(_safe_str(_safe_issue_field(fields, "updated")))
                            if normalize_enabled
                            else _safe_str(_safe_issue_field(fields, "updated"))
                        ),
                        "last_sync_snapshot": {
                            "name": _safe_str(task.getName()),
                            "notes": _safe_str(task.getNotes()),
                        },
                    }
                    # Update lookup for subsequent issues
                    key_to_task[issue_key] = task
                    if issue_id:
                        id_to_task[issue_id] = task
                    uid_to_task[next_uid] = task
                    result["created"] += 1

            except Exception as exc:
                err_msg = f"Issue {getattr(issue, 'key', '?')}: {exc}"
                result["errors"].append(err_msg)
                result["skipped"] += 1
                _log(f"[SKIP] {err_msg}")

        # ---- Handle orphaned linked tasks ----------------------------------
        fetched_keys = {str(i.key) for i in (epics + non_epics)}
        orphan_cfg = advanced.get("orphan") or {}
        orphan_behavior = str(orphan_cfg.get("behavior") or "messagebox")
        result["orphans"]["behavior"] = orphan_behavior
        orphan_uid_entries = [
            (uid, meta)
            for uid, meta in (task_jira or {}).items()
            if str(meta.get("jira_key") or "") and str(meta.get("jira_key")) not in fetched_keys
        ]
        result["orphans"]["detected"] = len(orphan_uid_entries)

        if orphan_cfg.get("enabled") and orphan_uid_entries:
            for uid, meta in orphan_uid_entries:
                task = uid_to_task.get(int(uid)) or uid_to_task.get(uid)
                effective_orphan = orphan_behavior
                if orphan_behavior == "messagebox":
                    if orphan_callback is not None:
                        task_name = _safe_str(task.getName()) if task is not None else str(uid)
                        effective_orphan = orphan_callback(
                            str(meta.get("jira_key") or uid), task_name
                        ) or "keep"
                    else:
                        effective_orphan = "keep"
                if effective_orphan == "keep":
                    continue
                if effective_orphan == "unlink":
                    task_jira.pop(uid, None)
                    result["orphans"]["handled"] += 1
                elif effective_orphan == "close":
                    try:
                        if task is not None:
                            import jpype  # type: ignore
                            task.setPercentageComplete(jpype.JClass("java.lang.Double")(100.0))
                        task_jira.pop(uid, None)
                        result["orphans"]["handled"] += 1
                    except Exception:
                        pass
                elif effective_orphan == "delete":
                    try:
                        if task is not None:
                            project.getTasks().remove(task)
                        task_jira.pop(uid, None)
                        result["orphans"]["handled"] += 1
                    except Exception:
                        pass

        # ---- Persist sidecar + sync metadata -------------------------------
        sync_meta.update({
            "last_run_at": _now_iso_utc(),
            "last_jql": jql,
            "last_result": {
                "created": result["created"],
                "updated": result["updated"],
                "skipped": result["skipped"],
                "errors": list(result.get("errors", []))[:50],
                "processed": result.get("processed", 0),
            },
            "preview_enabled": bool((advanced.get("preview") or {}).get("enabled", False)),
        })

        if not result["errors"]:
            sync_meta["last_successful_sync"] = _now_iso_utc()

        if progress_callback:
            progress_callback(96, "Saving sync metadata\u2026")
        sidecar_data["task_jira"] = task_jira
        sidecar_data["jira_sync_meta"] = sync_meta
        if sidecar_path:
            _save_sidecar_dict(sidecar_path, sidecar_data)

        summary_line = (
            f"Sync complete — created={result['created']}, "
            f"updated={result['updated']}, skipped={result['skipped']}, "
            f"errors={len(result['errors'])}"
        )
        _log(summary_line)
        if progress_callback:
            progress_callback(100, "Sync complete")

    except Exception as exc:
        result["errors"].append(f"Sync aborted: {exc}")
        if _is_debug():
            import traceback
            print(f"[DEBUG] jira_sync: fatal exception:\n{traceback.format_exc()}")

    _last_result = result
    return result


# ---------------------------------------------------------------------------
# Module-level state for Project → Jira push
# ---------------------------------------------------------------------------
_last_push_result: Optional[dict] = None


def get_last_push_result() -> Optional[dict]:
    """Return the result dict from the most recent run_push_to_jira() call, or None."""
    return _last_push_result


# ---------------------------------------------------------------------------
# Helpers: read P2J config
# ---------------------------------------------------------------------------

def _read_p2j_config(project) -> dict:
    """Extract the project2jira config dict from MPXJ project custom properties."""
    try:
        cp = project.getProjectProperties().getCustomProperties()
        if cp is None:
            return {}
        raw = cp.get("project2jira")
        if raw is None:
            return {}
        return json.loads(str(raw))
    except Exception:
        return {}


def _p2j_field_enabled(p2j: dict, field_name: str) -> bool:
    return bool((p2j.get("fields") or {}).get(field_name, {}).get("enabled", False))


def _p2j_jira_field(p2j: dict, field_name: str, default: str = "") -> str:
    entry = (p2j.get("fields") or {}).get(field_name) or {}
    return str(entry.get("jira_field") or default).strip()


# ---------------------------------------------------------------------------
# Helpers: map project task → Jira issue payload
# ---------------------------------------------------------------------------

def _task_to_jira_payload(task, p2j: dict, issue_type: str = "Task") -> dict:
    """Build a dict of Jira field values from an MPXJ task using enabled field mappings.

    Returns a flat dict suitable for jira_client.create_issue(fields=...) or
    jira_client.issue(key).update(fields=...).  Only enabled fields are included.
    """
    payload: dict = {}

    def _set(field_name: str, value):
        jira_field = _p2j_jira_field(p2j, field_name)
        if jira_field and value is not None:
            payload[jira_field] = value

    # summary — always include (Jira requires it for create)
    name = _safe_str(task.getName())
    if name:
        summary_field = _p2j_jira_field(p2j, "jira_summary", "summary")
        payload[summary_field or "summary"] = name

    # description
    if _p2j_field_enabled(p2j, "jira_description"):
        notes = _safe_str(task.getNotes())
        if notes:
            _set("jira_description", notes[:32767])

    # due date
    if _p2j_field_enabled(p2j, "jira_due_date"):
        try:
            deadline = task.getDeadline()
            if deadline is not None:
                # Convert java.time.LocalDate or LocalDateTime to ISO string
                try:
                    date_str = str(deadline)[:10]
                    _set("jira_due_date", date_str)
                except Exception:
                    pass
        except Exception:
            pass

    # assignee — first resource on the task
    if _p2j_field_enabled(p2j, "jira_assignee"):
        try:
            assignments = list(task.getResourceAssignments() or [])
            if assignments:
                res = assignments[0].getResource()
                if res is not None:
                    assignee_name = _safe_str(res.getName())
                    if assignee_name:
                        jira_field = _p2j_jira_field(p2j, "jira_assignee", "assignee")
                        if jira_field:
                            # Jira Cloud expects {"accountId": ...}; Server expects {"name": ...}
                            # We pass the display name and let the caller decide which sub-key to use.
                            payload[jira_field] = {"name": assignee_name}
        except Exception:
            pass

    # priority
    if _p2j_field_enabled(p2j, "jira_priority"):
        try:
            notes = _safe_str(task.getNotes())
            for line in notes.splitlines():
                if line.strip().startswith("Jira Priority:"):
                    prio = line.split(":", 1)[1].strip()
                    if prio:
                        _set("jira_priority", {"name": prio})
                    break
        except Exception:
            pass

    # time tracking — original estimate from duration
    if _p2j_field_enabled(p2j, "jira_original_estimate"):
        try:
            dur = task.getDuration()
            if dur is not None:
                hours = float(str(dur.convertUnits(
                    __import__("net.sf.mpxj", fromlist=["TimeUnit"]).TimeUnit.HOURS,
                    task.getParentFile().getProjectProperties()
                ).getDuration() or 0))
                if hours > 0:
                    _set("jira_original_estimate", f"{int(hours)}h")
        except Exception:
            pass

    return payload


def _task_status_string(task) -> str:
    """Return a human-readable status string for an MPXJ task."""
    try:
        pct = float(str(task.getPercentageComplete() or 0))
    except Exception:
        pct = 0.0
    if pct >= 100.0:
        return "Done"
    if pct > 0.0:
        return "In Progress"
    return "To Do"


# ---------------------------------------------------------------------------
# Helpers: safe API call with retry/backoff
# ---------------------------------------------------------------------------

def _with_retry(fn, max_retries: int, backoff_seconds: float):
    """Call fn(); on transient Jira errors retry with exponential backoff."""
    attempt = 0
    while True:
        try:
            return fn()
        except Exception as exc:
            if not _is_transient_error(exc) or attempt >= max_retries:
                raise
            attempt += 1
            wait_s = backoff_seconds * (2 ** (attempt - 1))
            if _is_debug():
                print(f"[DEBUG] jira_push: transient error: {exc}. Retry {attempt}/{max_retries} in {wait_s:.1f}s")
            time.sleep(wait_s)


# ---------------------------------------------------------------------------
# Main entry point: Project → Jira push
# ---------------------------------------------------------------------------

def run_push_to_jira(project, server: dict, jira_client, sidecar_path: str,
                     included_task_uids: Optional[set] = None) -> dict:
    """Push project task changes to Jira (Project → Jira direction).

    Args:
        project:             MPXJ ProjectFile (read-only during push)
        server:              Server config dict from settings_manager.get_jira_servers()
        jira_client:         Authenticated jira.JIRA instance
        sidecar_path:        Path to .custom-props.json sidecar file
        included_task_uids:  Optional set of task UID strings to process.
                             None = process all eligible tasks (respecting scope).
                             Populated by the dry-run preview dialog for selective apply.

    Returns:
        {
            "created": int, "updated": int, "transitioned": int,
            "skipped": int, "errors": list[str], "log": list[str],
            "preview_actions": list[dict],   # populated during dry-run pass
            "dry_run": bool,
        }
    """
    global _last_push_result

    result: dict = {
        "created": 0,
        "updated": 0,
        "transitioned": 0,
        "skipped": 0,
        "errors": [],
        "log": [],
        "preview_actions": [],
        "dry_run": False,
    }

    _LOG_PREFIX = "[DEBUG] jira_push.run:"

    def _log(msg: str):
        if _is_debug():
            print(f"{_LOG_PREFIX} {msg}")
        result["log"].append(msg)

    try:
        # ---- Read config -------------------------------------------------------
        p2j = _read_p2j_config(project)
        dry_run = bool(p2j.get("dry_run", True))
        result["dry_run"] = dry_run

        export_scope   = str(p2j.get("export_scope") or "selected_tasks")
        create_update  = str(p2j.get("create_update_mode") or "create_update")
        conflict_policy = str(p2j.get("conflict_policy") or "manual_review")
        unlinked_behavior = str(p2j.get("unlinked_task_behavior") or "skip")
        issue_type_map = p2j.get("issue_type_map") or {}    # project_type -> jira_issue_type
        transition_map = p2j.get("transition_map") or {}    # project_status -> jira_transition
        hier_cfg       = p2j.get("hierarchy_export") or {}
        audit_enabled  = bool((p2j.get("auditability") or {}).get("enabled", False))

        hier_enabled        = bool(hier_cfg.get("enabled", False))
        epic_type           = str(hier_cfg.get("epic_type") or "Epic")
        story_type          = str(hier_cfg.get("story_type") or "Story")
        subtask_type        = str(hier_cfg.get("subtask_type") or "Sub-task")
        dep_link_type       = str(hier_cfg.get("dependency_link_type") or "blocks")

        # ---- Fetch Jira project key from issue_type_map or first server project ---
        # We use the server-configured project key (stored in j2p.jira_project_key or
        # inferred from the configured JQL filter).  Fall back to requiring the caller
        # to have "project" in the field map.
        jira_project_key = str(p2j.get("jira_project_key") or "").strip()
        # Also check j2p config for the key used during import
        try:
            j2p_raw = project.getProjectProperties().getCustomProperties().get("jira2project")
            if j2p_raw:
                j2p_import = json.loads(str(j2p_raw))
                if not jira_project_key:
                    # Try to extract from JQL: "project = MYPROJ"
                    import re as _re
                    m = _re.search(r"project\s*=\s*[\"']?(\w+)[\"']?", str(j2p_import.get("filter", "")), _re.IGNORECASE)
                    if m:
                        jira_project_key = m.group(1).strip()
        except Exception:
            pass

        # Reliability
        reliability_cfg = p2j.get("reliability") or {}
        retry_enabled = bool(reliability_cfg.get("enabled", False))
        max_retries   = int(reliability_cfg.get("max_retries", 3) or 3)
        backoff_s     = float(reliability_cfg.get("backoff_seconds", 1.0) or 1.0)

        # ---- Load sidecar metadata -------------------------------------------
        sidecar_data = _load_sidecar_dict(sidecar_path)
        task_jira    = sidecar_data.get("task_jira") or {}    # Jira→Project link data
        task_p2j     = sidecar_data.get("task_p2j") or {}     # Project→Jira push metadata
        push_meta    = sidecar_data.get("jira_push_meta") or {}

        # ---- Build uid→task lookup -------------------------------------------
        uid_to_task: dict = {}
        try:
            for t in project.getTasks():
                if t.getName() is None:
                    continue
                try:
                    uid_to_task[str(t.getUniqueID())] = t
                except Exception:
                    pass
        except Exception:
            pass

        # Determine last successful push time for "changed_since_last_sync" scope.
        last_push_time = str(push_meta.get("last_successful_push") or "").strip()

        # ---- Collect eligible tasks ------------------------------------------
        def _is_eligible(t) -> bool:
            """Return True if this task should be considered for export."""
            try:
                if t.getName() is None:
                    return False
                # Skip the project summary task (UID=0 or ID=0)
                try:
                    if int(str(t.getUniqueID() or 0)) == 0:
                        return False
                except Exception:
                    pass
                # Summary tasks are usually containers; skip unless hierarchy enabled
                try:
                    if t.getSummary() and not hier_enabled:
                        return False
                except Exception:
                    pass
            except Exception:
                return False
            return True

        eligible_tasks = [t for t in project.getTasks() if _is_eligible(t)]

        if export_scope == "changed_since_last_sync" and last_push_time:
            # Filter to tasks changed after last push (based on task_p2j metadata)
            def _changed_since(t) -> bool:
                uid_str = str(t.getUniqueID())
                meta = task_p2j.get(uid_str) or {}
                pushed_at = meta.get("last_pushed_at")
                if not pushed_at:
                    return True  # never pushed — always include
                # Compare by checking if the task has been modified (no direct MPXJ API;
                # we rely on the task having sidecar entries from Jira→Project that updated after push)
                j2p_meta = task_jira.get(uid_str) or {}
                last_imported = str(j2p_meta.get("last_imported_at") or "").strip()
                if last_imported > pushed_at:
                    return True  # re-imported from Jira after last push → may have changed
                return False
            eligible_tasks = [t for t in eligible_tasks if _changed_since(t)]

        # If included_task_uids is provided (from dry-run selection), filter further.
        if included_task_uids is not None:
            eligible_tasks = [t for t in eligible_tasks
                              if str(t.getUniqueID()) in included_task_uids]

        _log(f"Eligible tasks for push: {len(eligible_tasks)} "
             f"(scope={export_scope}, dry_run={dry_run})")

        # ---- Fetch available Jira issue types once for validation -----------
        _available_issue_types: set = set()
        try:
            for it in jira_client.issue_types():
                _available_issue_types.add(str(getattr(it, "name", it)))
        except Exception:
            pass

        # ---- Helper: resolve a Jira transition for an issue -----------------
        def _get_transition_id(issue_key: str, transition_name_or_id: str) -> Optional[str]:
            """Return the numeric transition ID for the given name or ID."""
            try:
                transitions = _with_retry(
                    lambda: jira_client.transitions(issue_key),
                    max_retries if retry_enabled else 0, backoff_s,
                )
                for t in (transitions or []):
                    if isinstance(t, dict):
                        tid  = str(t.get("id", ""))
                        tname = str(t.get("name", ""))
                    else:
                        tid   = str(getattr(t, "id", ""))
                        tname = str(getattr(t, "name", ""))
                    if tid == transition_name_or_id or tname.lower() == transition_name_or_id.lower():
                        return tid
            except Exception as exc:
                _log(f"[WARN] Could not fetch transitions for {issue_key}: {exc}")
            return None

        # ---- Process tasks ---------------------------------------------------
        push_results: list[dict] = []  # for auditability summary

        for task in eligible_tasks:
            uid_str  = str(task.getUniqueID())
            task_name = _safe_str(task.getName())

            try:
                # Determine if this task has an existing Jira link
                j2p_meta = task_jira.get(uid_str) or {}
                p2j_meta = task_p2j.get(uid_str) or {}
                jira_key = str(j2p_meta.get("jira_key") or p2j_meta.get("jira_key") or "").strip()
                jira_id  = str(j2p_meta.get("jira_id")  or p2j_meta.get("jira_id")  or "").strip()

                has_link = bool(jira_key)

                # ---- Determine action ----------------------------------------
                if not has_link:
                    if create_update == "update_only":
                        result["skipped"] += 1
                        _log(f"[SKIP] uid={uid_str} '{task_name}' — update_only mode, no link")
                        continue
                    # Unlinked task behavior
                    if unlinked_behavior == "skip":
                        result["skipped"] += 1
                        _log(f"[SKIP] uid={uid_str} '{task_name}' — unlinked, behavior=skip")
                        continue
                    # "create" or "prompt" — we treat prompt same as create in the push engine
                    # (the dialog already asked before calling this function)
                    action = "create"
                else:
                    if create_update == "create_only":
                        result["skipped"] += 1
                        _log(f"[SKIP] uid={uid_str} '{task_name}' — create_only mode, already linked")
                        continue
                    action = "update"

                # Determine Jira issue type from project task type + mapping
                try:
                    task_type_name = _safe_str(task.getType())
                except Exception:
                    task_type_name = ""
                jira_issue_type = issue_type_map.get(task_type_name, issue_type_map.get("", "Task"))
                if not jira_issue_type:
                    jira_issue_type = "Task"

                # Hierarchy: override issue type for parent/child tasks when enabled
                if hier_enabled:
                    try:
                        parent_task = task.getParentTask()
                        if parent_task is not None and parent_task.getName() is not None:
                            # Child task
                            try:
                                is_subtask = task.getSummary() is False and parent_task.getSummary()
                            except Exception:
                                is_subtask = False
                            jira_issue_type = subtask_type if is_subtask else story_type
                        elif task.getSummary():
                            jira_issue_type = epic_type
                    except Exception:
                        pass

                # Build field payload
                fields_payload = _task_to_jira_payload(task, p2j, jira_issue_type)

                # ---- Conflict detection (update path) ------------------------
                details_str = ""
                if action == "update" and conflict_policy != "prefer_project":
                    try:
                        remote_issue = _with_retry(
                            lambda: jira_client.issue(jira_key, fields="updated,summary"),
                            max_retries if retry_enabled else 0, backoff_s,
                        )
                        remote_updated = str(getattr(remote_issue.fields, "updated", "") or "")
                        last_push_at   = str(p2j_meta.get("last_pushed_at") or "")
                        if remote_updated and last_push_at and remote_updated > last_push_at:
                            # Concurrent remote edit detected
                            if conflict_policy == "prefer_jira":
                                result["skipped"] += 1
                                _log(f"[SKIP] {jira_key} — remote edit detected; conflict_policy=prefer_jira")
                                if not dry_run:
                                    continue
                            elif conflict_policy == "manual_review":
                                result["skipped"] += 1
                                result["errors"].append(
                                    f"{jira_key}: remote concurrent edit detected "
                                    f"(remote_updated={remote_updated[:19]}, "
                                    f"last_pushed={last_push_at[:19]}). "
                                    "Review manually."
                                )
                                _log(f"[CONFLICT] {jira_key} — manual review required")
                                if not dry_run:
                                    continue
                        details_str = f"remote_updated={remote_updated[:10] if remote_updated else 'n/a'}"
                    except Exception as exc:
                        _log(f"[WARN] Conflict check for {jira_key}: {exc}")

                # ---- Dry-run: collect preview action -------------------------
                if dry_run:
                    changed_fields = ", ".join(fields_payload.keys())
                    result["preview_actions"].append({
                        "task_uid":     uid_str,
                        "task_name":    task_name,
                        "jira_key":     jira_key or "NEW",
                        "action":       action,
                        "issue_type":   jira_issue_type,
                        "changed_fields": changed_fields,
                        "details":      details_str,
                    })
                    result["skipped"] += 1
                    _log(f"[DRY-RUN] {action.upper()} uid={uid_str} '{task_name}' "
                         f"→ {jira_key or 'NEW'} fields={changed_fields}")
                    continue

                # ---- Execute action ------------------------------------------
                if action == "create":
                    # Ensure required 'project' field is present
                    if jira_project_key:
                        fields_payload.setdefault("project", {"key": jira_project_key})
                    fields_payload.setdefault("issuetype", {"name": jira_issue_type})
                    fields_payload.setdefault("summary", task_name)

                    try:
                        new_issue = _with_retry(
                            lambda fp=fields_payload: jira_client.create_issue(fields=fp),
                            max_retries if retry_enabled else 0, backoff_s,
                        )
                        new_key = str(new_issue.key)
                        new_id  = str(new_issue.id)
                        _log(f"[CREATE] uid={uid_str} '{task_name}' → {new_key}")
                        result["created"] += 1
                        jira_key = new_key
                        jira_id  = new_id

                        # Record link in task_jira so subsequent imports can match
                        if uid_str not in task_jira:
                            task_jira[uid_str] = {}
                        task_jira[uid_str]["jira_key"] = new_key
                        task_jira[uid_str]["jira_id"]  = new_id

                        push_results.append({
                            "uid": uid_str, "action": "created",
                            "jira_key": new_key, "task_name": task_name,
                        })
                    except Exception as exc:
                        result["errors"].append(f"Create uid={uid_str} '{task_name}': {exc}")
                        _log(f"[ERROR] Create uid={uid_str}: {exc}")
                        continue

                else:  # update
                    try:
                        update_fields = dict(fields_payload)
                        update_fields.pop("summary", None)   # summary update via dedicated field
                        update_fields.pop("issuetype", None)
                        update_fields.pop("project", None)

                        # Update summary separately (always)
                        summary_payload = {"summary": task_name}

                        def _do_update(ik=jira_key, sp=summary_payload, uf=update_fields):
                            issue_obj = jira_client.issue(ik)
                            issue_obj.update(fields={**sp, **uf})
                            return issue_obj

                        _with_retry(_do_update,
                                    max_retries if retry_enabled else 0, backoff_s)
                        _log(f"[UPDATE] uid={uid_str} '{task_name}' → {jira_key}")
                        result["updated"] += 1
                        push_results.append({
                            "uid": uid_str, "action": "updated",
                            "jira_key": jira_key, "task_name": task_name,
                        })
                    except Exception as exc:
                        result["errors"].append(f"Update {jira_key}: {exc}")
                        _log(f"[ERROR] Update {jira_key}: {exc}")
                        continue

                # ---- Workflow transition -------------------------------------
                task_status = _task_status_string(task)
                transition_value = transition_map.get(task_status, "")
                if transition_value and jira_key:
                    try:
                        transition_id = _get_transition_id(jira_key, transition_value)
                        if transition_id:
                            _with_retry(
                                lambda ik=jira_key, tid=transition_id: jira_client.transition_issue(ik, tid),
                                max_retries if retry_enabled else 0, backoff_s,
                            )
                            result["transitioned"] += 1
                            _log(f"[TRANSITION] {jira_key} → '{transition_value}' (id={transition_id})")
                        else:
                            result["errors"].append(
                                f"{jira_key}: transition '{transition_value}' not available "
                                "for this issue. Check transition mapping or issue workflow."
                            )
                            _log(f"[WARN] {jira_key} transition '{transition_value}' not found")
                    except Exception as exc:
                        result["errors"].append(f"{jira_key} transition error: {exc}")
                        _log(f"[ERROR] {jira_key} transition: {exc}")

                # ---- Hierarchy export: Epic link / parent ------------------
                if hier_enabled and jira_key:
                    try:
                        parent_task = task.getParentTask()
                        if parent_task is not None and parent_task.getName() is not None:
                            parent_uid_str = str(parent_task.getUniqueID())
                            parent_jira_key = str(
                                (task_jira.get(parent_uid_str) or {}).get("jira_key") or
                                (task_p2j.get(parent_uid_str) or {}).get("jira_key") or ""
                            ).strip()
                            if parent_jira_key:
                                try:
                                    _with_retry(
                                        lambda ik=jira_key, pk=parent_jira_key: jira_client.issue(ik).update(
                                            fields={"parent": {"key": pk}}
                                        ),
                                        max_retries if retry_enabled else 0, backoff_s,
                                    )
                                    _log(f"[HIERARCHY] {jira_key} parent set to {parent_jira_key}")
                                except Exception as exc:
                                    _log(f"[WARN] hierarchy parent set for {jira_key}: {exc}")
                    except Exception:
                        pass

                # ---- Dependency export: predecessors → Jira issue links -----
                if hier_enabled and jira_key:
                    try:
                        preds = list(task.getPredecessors() or [])
                        for pred_rel in preds:
                            try:
                                pred_task = pred_rel.getSourceTask() or pred_rel.getTargetTask()
                                if pred_task is None:
                                    continue
                                pred_uid_str = str(pred_task.getUniqueID())
                                pred_jira_key = str(
                                    (task_jira.get(pred_uid_str) or {}).get("jira_key") or
                                    (task_p2j.get(pred_uid_str) or {}).get("jira_key") or ""
                                ).strip()
                                if pred_jira_key:
                                    _with_retry(
                                        lambda ik=jira_key, pk=pred_jira_key, ltype=dep_link_type: jira_client.create_issue_link(
                                            ltype, ik, pk
                                        ),
                                        max_retries if retry_enabled else 0, backoff_s,
                                    )
                                    _log(f"[DEPENDENCY] {jira_key} {dep_link_type} {pred_jira_key}")
                            except Exception as exc:
                                _log(f"[WARN] dependency link for {jira_key}: {exc}")
                    except Exception:
                        pass

                # ---- Update per-task push metadata --------------------------
                if uid_str not in task_p2j:
                    task_p2j[uid_str] = {}
                task_p2j[uid_str]["jira_key"]       = jira_key
                if jira_id:
                    task_p2j[uid_str]["jira_id"]    = jira_id
                task_p2j[uid_str]["last_pushed_at"] = _now_iso_utc()
                task_p2j[uid_str]["last_push_result"] = action

            except Exception as exc:
                err_msg = f"Task uid={uid_str} '{task_name}': {exc}"
                result["errors"].append(err_msg)
                result["skipped"] += 1
                _log(f"[SKIP/ERROR] {err_msg}")
                if _is_debug():
                    import traceback
                    print(f"[DEBUG] jira_push task exception:\n{traceback.format_exc()}")

        # ---- Persist sidecar -----------------------------------------------
        push_meta_update = {
            "last_run_at": _now_iso_utc(),
            "last_result": {
                "created":     result["created"],
                "updated":     result["updated"],
                "transitioned": result["transitioned"],
                "skipped":     result["skipped"],
                "errors":      list(result.get("errors", []))[:50],
                "dry_run":     dry_run,
            },
        }
        if not result["errors"] and not dry_run:
            push_meta_update["last_successful_push"] = _now_iso_utc()

        push_meta.update(push_meta_update)

        if audit_enabled and not dry_run:
            existing_sessions = list(push_meta.get("audit_sessions") or [])
            existing_sessions.append({
                "run_at":      push_meta_update["last_run_at"],
                "created":     result["created"],
                "updated":     result["updated"],
                "transitioned": result["transitioned"],
                "skipped":     result["skipped"],
                "failed":      len(result["errors"]),
                "reasons":     list(result["errors"])[:20],
                "details":     push_results[:100],
            })
            # Keep last 20 sessions
            push_meta["audit_sessions"] = existing_sessions[-20:]

        if not dry_run:
            sidecar_data["task_jira"]      = task_jira
            sidecar_data["task_p2j"]       = task_p2j
            sidecar_data["jira_push_meta"] = push_meta
            # Also snapshot the p2j config into sidecar for portability
            sidecar_data["project2jira_config"] = p2j
            if sidecar_path:
                _save_sidecar_dict(sidecar_path, sidecar_data)

        summary_line = (
            f"Push {'(dry-run) ' if dry_run else ''}complete — "
            f"created={result['created']}, updated={result['updated']}, "
            f"transitioned={result['transitioned']}, skipped={result['skipped']}, "
            f"errors={len(result['errors'])}"
        )
        _log(summary_line)

    except Exception as exc:
        result["errors"].append(f"Push aborted: {exc}")
        if _is_debug():
            import traceback
            print(f"[DEBUG] jira_push: fatal exception:\n{traceback.format_exc()}")

    _last_push_result = result
    return result

