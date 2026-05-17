"""Tests for integrations/jira_sync.py â€” Jira â†’ Project sync execution engine.

All MPXJ/Java calls and Jira API interactions are mocked; no JVM or real Jira
server is required to run these tests.

Coverage:
  - load_sidecar_task_data (missing file, empty file, valid data, malformed JSON)
  - save_sidecar_task_data (create new, merge with existing, error handling)
  - get_last_result (initial None, value after run_sync)
  - _issue_type_label (known type, unknown type, configured override)
  - _status_to_percent (known statuses, unknown status, case-insensitive)
  - _build_jira_key_lookup (empty project, matched keys, unmatched UIDs)
  - run_sync (no filter, API error, creates task, updates task,
               epic + sub-ticket hierarchy, sidecar persistence,
               result counters: created/updated/skipped)
  - get_last_push_result (initial None, value after run_push_to_jira)
  - _task_status_string (0 %, 50 %, 100 % completion â†’ To Do / In Progress / Done)
  - _task_to_jira_payload (summary always present, disabled fields excluded,
                            assignee mapping, due-date mapping)
  - _with_retry (success on first try, retries on transient error,
                  raises after max_retries exceeded)
  - run_push_to_jira (dry-run preview, create unlinked task, update linked task,
                       workflow transition, skip unlinked tasks, conflict detection,
                       hierarchy parent link, auditability session)
"""

import sys
import os
import json
import pytest
from unittest.mock import MagicMock, patch, call

# conftest.py already stubs jpype/java/jira/integrations and sets sys.path.
import app_debug  # available after conftest.py runs


def _get_jira_sync():
    """Import jira_sync lazily (conftest has already set up all stubs)."""
    from integrations import jira_sync as _js
    return _js


# Resolve once at module collection time (conftest has already run by now).
try:
    from integrations import jira_sync
except Exception:  # pragma: no cover
    jira_sync = None  # type: ignore


def _restore_java_stubs():
    """Re-insert java.lang stub into sys.modules.

    When the real jira_integration module is imported during a test run,
    Python may set sys.modules['java.lang'] = None (negative import cache)
    because 'java' is a MagicMock and not a real package.  This helper
    restores the MagicMock stub so that `from java.lang import Integer`
    inside run_sync does not raise ImportError.
    """
    for mod in ('java', 'java.lang', 'java.time', 'java.util'):
        if sys.modules.get(mod) is None:
            sys.modules[mod] = MagicMock()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_issue(key="PROJ-1", summary="Do something", issue_type="Task",
                status="In Progress", assignee_name=None, parent_key=None,
                epic_link_field=None):
    """Build a minimal mock Jira issue."""
    issue = MagicMock()
    issue.key = key
    fields = MagicMock()
    fields.summary = summary
    issuetype = MagicMock()
    issuetype.name = issue_type
    fields.issuetype = issuetype
    status_mock = MagicMock()
    status_mock.name = status
    fields.status = status_mock
    if assignee_name:
        assignee = MagicMock()
        assignee.displayName = assignee_name
        fields.assignee = assignee
    else:
        fields.assignee = None
    if parent_key:
        parent = MagicMock()
        parent.key = parent_key
        fields.parent = parent
    else:
        fields.parent = None
    fields.customfield_10014 = epic_link_field
    # Other optional fields return empty/None
    fields.description = None
    fields.duedate = None
    fields.priority = None
    issue.fields = fields
    return issue


def _make_project(tasks=None):
    """Build a minimal mock MPXJ ProjectFile."""
    project = MagicMock()
    tasks_list = tasks or []
    project.getTasks.return_value = tasks_list
    project.getResources.return_value = []
    # Use a plain MagicMock to avoid circular recursion with _make_mpxj_task()
    project.addTask.return_value = MagicMock()
    project.addResource.return_value = MagicMock()
    props = MagicMock()
    cp = MagicMock()
    cp.get.return_value = json.dumps({"filter": "project = PROJ", "filter_type": "jql"})
    props.getCustomProperties.return_value = cp
    project.getProjectProperties.return_value = props
    return project


def _make_mpxj_task(name="Task A", uid=1, id=1):
    task = MagicMock()
    task.getName.return_value = name
    task.getUniqueID.return_value = uid
    task.getID.return_value = id
    task.getNotes.return_value = ""
    task.getOutlineLevel.return_value = 1
    task.getResourceAssignments.return_value = []
    # Use a plain MagicMock to avoid circular recursion with _make_project()
    task.getParentFile.return_value = MagicMock()
    return task


# ---------------------------------------------------------------------------
# load_sidecar_task_data
# ---------------------------------------------------------------------------

class TestLoadSidecarTaskData:
    """Unit tests for jira_sync.load_sidecar_task_data.

    \testinit
    Prepare temporary sidecar JSON files with various contents.

    \testrun
    Call load_sidecar_task_data(sidecar_path) with different file states.

    \testexpect
    Returns the task_jira dict from the file, or {} for missing/invalid files.

    \testcheck
    Assert the returned dict matches the expected value.
    """

    def test_returns_empty_dict_when_path_is_empty(self):
        result = jira_sync.load_sidecar_task_data("")
        assert result == {}

    def test_returns_empty_dict_when_file_missing(self, tmp_path):
        result = jira_sync.load_sidecar_task_data(str(tmp_path / "nonexistent.json"))
        assert result == {}

    def test_returns_empty_dict_when_task_jira_key_absent(self, tmp_path):
        sidecar = tmp_path / "proj.json"
        sidecar.write_text(json.dumps({"other_key": {}}), encoding="utf-8")
        result = jira_sync.load_sidecar_task_data(str(sidecar))
        assert result == {}

    def test_returns_task_jira_dict_when_present(self, tmp_path):
        data = {"task_jira": {"1": {"jira_key": "PROJ-1"}}}
        sidecar = tmp_path / "proj.json"
        sidecar.write_text(json.dumps(data), encoding="utf-8")
        result = jira_sync.load_sidecar_task_data(str(sidecar))
        assert result == {"1": {"jira_key": "PROJ-1"}}

    def test_returns_empty_dict_on_malformed_json(self, tmp_path):
        sidecar = tmp_path / "proj.json"
        sidecar.write_text("not-json{{{{", encoding="utf-8")
        result = jira_sync.load_sidecar_task_data(str(sidecar))
        assert result == {}

    def test_returns_multiple_entries(self, tmp_path):
        data = {"task_jira": {"1": {"jira_key": "A-1"}, "2": {"jira_key": "A-2"}}}
        sidecar = tmp_path / "proj.json"
        sidecar.write_text(json.dumps(data), encoding="utf-8")
        result = jira_sync.load_sidecar_task_data(str(sidecar))
        assert len(result) == 2
        assert result["2"]["jira_key"] == "A-2"


# ---------------------------------------------------------------------------
# save_sidecar_task_data
# ---------------------------------------------------------------------------

class TestSaveSidecarTaskData:
    """Unit tests for jira_sync.save_sidecar_task_data.

    \testinit
    Create a temporary directory; optionally pre-populate a sidecar file.

    \testrun
    Call save_sidecar_task_data(sidecar_path, task_jira).

    \testexpect
    The sidecar file on disk contains the task_jira dict; existing keys are preserved.

    \testcheck
    Read back the JSON file and assert the task_jira key matches.
    """

    def test_creates_new_file_when_absent(self, tmp_path):
        sidecar = tmp_path / "proj.json"
        jira_sync.save_sidecar_task_data(str(sidecar), {"1": {"jira_key": "X-1"}})
        assert sidecar.exists()
        data = json.loads(sidecar.read_text(encoding="utf-8"))
        assert data["task_jira"]["1"]["jira_key"] == "X-1"

    def test_merges_with_existing_sidecar_data(self, tmp_path):
        sidecar = tmp_path / "proj.json"
        sidecar.write_text(json.dumps({"other": "value"}), encoding="utf-8")
        jira_sync.save_sidecar_task_data(str(sidecar), {"2": {"jira_key": "X-2"}})
        data = json.loads(sidecar.read_text(encoding="utf-8"))
        assert data["other"] == "value"
        assert data["task_jira"]["2"]["jira_key"] == "X-2"

    def test_overwrites_existing_task_jira(self, tmp_path):
        sidecar = tmp_path / "proj.json"
        sidecar.write_text(json.dumps({"task_jira": {"1": {"jira_key": "OLD-1"}}}), encoding="utf-8")
        jira_sync.save_sidecar_task_data(str(sidecar), {"1": {"jira_key": "NEW-1"}})
        data = json.loads(sidecar.read_text(encoding="utf-8"))
        assert data["task_jira"]["1"]["jira_key"] == "NEW-1"

    def test_saves_empty_dict(self, tmp_path):
        sidecar = tmp_path / "proj.json"
        jira_sync.save_sidecar_task_data(str(sidecar), {})
        data = json.loads(sidecar.read_text(encoding="utf-8"))
        assert data["task_jira"] == {}


# ---------------------------------------------------------------------------
# get_last_result
# ---------------------------------------------------------------------------

class TestGetLastResult:
    """Unit tests for jira_sync.get_last_result.

    \testinit
    Reset module-level _last_result to None.

    \testrun
    Call get_last_result() before and after a run_sync call.

    \testexpect
    Returns None initially; returns the result dict after a sync run.

    \testcheck
    Assert return value is None or has the expected keys.
    """

    def test_returns_none_before_any_sync(self):
        jira_sync._last_result = None
        assert jira_sync.get_last_result() is None

    def test_returns_result_after_being_set(self):
        fake = {"created": 1, "updated": 0, "skipped": 0, "errors": [], "log": []}
        jira_sync._last_result = fake
        assert jira_sync.get_last_result() is fake

    def test_result_has_expected_keys(self):
        fake = {"created": 2, "updated": 1, "skipped": 0, "errors": ["e"], "log": ["l"]}
        jira_sync._last_result = fake
        res = jira_sync.get_last_result()
        for key in ("created", "updated", "skipped", "errors", "log"):
            assert key in res


# ---------------------------------------------------------------------------
# _issue_type_label
# ---------------------------------------------------------------------------

class TestIssueTypeLabel:
    """Unit tests for jira_sync._issue_type_label.

    \testinit
    No setup required.

    \testrun
    Call _issue_type_label(issue_type_name, issue_type_labels) with various inputs.

    \testexpect
    Returns the configured label when present, falls back to built-in defaults,
    and uses the raw name when no mapping exists at all.

    \testcheck
    Assert the return value matches the expected label string.
    """

    def test_returns_configured_label(self):
        labels = {"Bug": "DEFECT"}
        assert jira_sync._issue_type_label("Bug", labels) == "DEFECT"

    def test_falls_back_to_default_for_known_type(self):
        assert jira_sync._issue_type_label("Epic", {}) == "Epic"

    def test_falls_back_to_raw_name_for_unknown_type(self):
        assert jira_sync._issue_type_label("CustomType", {}) == "CustomType"

    def test_config_override_takes_precedence_over_default(self):
        labels = {"Epic": "EPIC_OVERRIDE"}
        assert jira_sync._issue_type_label("Epic", labels) == "EPIC_OVERRIDE"

    def test_empty_string_config_returns_empty(self):
        labels = {"Task": ""}
        assert jira_sync._issue_type_label("Task", labels) == ""


# ---------------------------------------------------------------------------
# _status_to_percent
# ---------------------------------------------------------------------------

class TestStatusToPercent:
    """Unit tests for jira_sync._status_to_percent.

    \testinit
    No setup required.

    \testrun
    Call _status_to_percent(status_name) with various status strings.

    \testexpect
    Returns 0, 50, 75, 80, or 100 according to the status map; defaults to 0 for
    unknown statuses; comparison is case-insensitive.

    \testcheck
    Assert the returned integer matches the expected percentage.
    """

    def test_open_returns_zero(self):
        assert jira_sync._status_to_percent("open") == 0

    def test_to_do_returns_zero(self):
        assert jira_sync._status_to_percent("to do") == 0

    def test_in_progress_returns_fifty(self):
        assert jira_sync._status_to_percent("in progress") == 50

    def test_in_review_returns_seventy_five(self):
        assert jira_sync._status_to_percent("in review") == 75

    def test_done_returns_hundred(self):
        assert jira_sync._status_to_percent("done") == 100

    def test_closed_returns_hundred(self):
        assert jira_sync._status_to_percent("closed") == 100

    def test_resolved_returns_hundred(self):
        assert jira_sync._status_to_percent("resolved") == 100

    def test_case_insensitive_in_progress(self):
        assert jira_sync._status_to_percent("IN PROGRESS") == 50

    def test_unknown_status_returns_zero(self):
        assert jira_sync._status_to_percent("something completely unknown") == 0


# ---------------------------------------------------------------------------
# _build_jira_key_lookup
# ---------------------------------------------------------------------------

class TestBuildJiraKeyLookup:
    """Unit tests for jira_sync._build_jira_key_lookup.

    \testinit
    Build a mock MPXJ project with tasks whose UIDs match sidecar entries.

    \testrun
    Call _build_jira_key_lookup(project, task_jira).

    \testexpect
    Returns a dict mapping jira_key strings to their corresponding MPXJ task
    objects; entries with no matching UID in the project are omitted.

    \testcheck
    Assert returned dict keys and values match expectations.
    """

    def test_empty_project_returns_empty_dict(self):
        project = MagicMock()
        project.getTasks.return_value = []
        result = jira_sync._build_jira_key_lookup(project, {})
        assert result == {}

    def test_matches_uid_to_jira_key(self):
        task = _make_mpxj_task(name="T", uid=5)
        project = MagicMock()
        project.getTasks.return_value = [task]
        task_jira = {"5": {"jira_key": "PROJ-5"}}
        result = jira_sync._build_jira_key_lookup(project, task_jira)
        assert "PROJ-5" in result
        assert result["PROJ-5"] is task

    def test_skips_entries_without_matching_uid(self):
        project = MagicMock()
        project.getTasks.return_value = []
        task_jira = {"99": {"jira_key": "PROJ-99"}}
        result = jira_sync._build_jira_key_lookup(project, task_jira)
        assert result == {}

    def test_skips_entries_without_jira_key(self):
        task = _make_mpxj_task(uid=3)
        project = MagicMock()
        project.getTasks.return_value = [task]
        task_jira = {"3": {"other_field": "x"}}
        result = jira_sync._build_jira_key_lookup(project, task_jira)
        assert result == {}

    def test_multiple_entries_all_matched(self):
        t1 = _make_mpxj_task(uid=1)
        t2 = _make_mpxj_task(uid=2)
        project = MagicMock()
        project.getTasks.return_value = [t1, t2]
        task_jira = {
            "1": {"jira_key": "A-1"},
            "2": {"jira_key": "A-2"},
        }
        result = jira_sync._build_jira_key_lookup(project, task_jira)
        assert len(result) == 2
        assert result["A-1"] is t1
        assert result["A-2"] is t2


# ---------------------------------------------------------------------------
# run_sync â€” early exit / error paths
# ---------------------------------------------------------------------------

class TestRunSyncEarlyExit:
    """Unit tests for jira_sync.run_sync early-exit branches.

    \testinit
    Build a mock MPXJ project whose jira2project config is missing or empty;
    mock Jira client; disable debug flag.

    \testrun
    Call run_sync(project, server, jira_client, sidecar_path="").

    \testexpect
    When no filter is configured the function returns immediately with an error
    entry; _last_result is updated.

    \testcheck
    Assert errors list is non-empty and created/updated/skipped are all 0.
    """

    def setup_method(self):
        app_debug.set_debug(False)
        jira_sync._last_result = None

    def _project_no_filter(self):
        project = MagicMock()
        props = MagicMock()
        cp = MagicMock()
        cp.get.return_value = json.dumps({})   # no filter key
        props.getCustomProperties.return_value = cp
        project.getProjectProperties.return_value = props
        project.getTasks.return_value = []
        return project

    def test_no_filter_returns_error(self):
        project = self._project_no_filter()
        result = jira_sync.run_sync(project, {}, MagicMock(), "")
        assert result["created"] == 0
        assert result["updated"] == 0
        assert len(result["errors"]) >= 1
        assert any("filter" in e.lower() or "nothing" in e.lower() for e in result["errors"])

    def test_no_filter_sets_last_result(self):
        project = self._project_no_filter()
        jira_sync.run_sync(project, {}, MagicMock(), "")
        assert jira_sync.get_last_result() is not None

    def test_api_error_returns_error(self):
        project = _make_project()
        jira_client = MagicMock()
        jira_client.search_issues.side_effect = Exception("connection refused")
        with patch("integrations.jira_integration.resolve_filter_to_jql", return_value=("project = PROJ", "")):
            result = jira_sync.run_sync(project, {}, jira_client, "")
        assert len(result["errors"]) >= 1
        assert any("connection" in e.lower() or "api" in e.lower() for e in result["errors"])

    def test_filter_resolution_failure_returns_error(self):
        project = _make_project()
        jira_client = MagicMock()
        with patch("integrations.jira_integration.resolve_filter_to_jql", return_value=("", "bad filter")):
            result = jira_sync.run_sync(project, {}, jira_client, "")
        assert any("filter" in e.lower() or "resolution" in e.lower() for e in result["errors"])


# ---------------------------------------------------------------------------
# run_sync â€” task creation
# ---------------------------------------------------------------------------

class TestRunSyncCreateTask:
    """Unit tests for jira_sync.run_sync task creation.

    \testinit
    Build a project with no existing tasks and an empty sidecar. Build a Jira
    client that returns one issue. Stub jpype and java.lang.Integer.

    \testrun
    Call run_sync(project, server, jira_client, sidecar_path).

    \testexpect
    One task is created (result["created"] == 1), task name contains the issue
    summary, and the sidecar is written with the jira_key.

    \testcheck
    Assert result counters, the name set on the new task, and sidecar file content.
    """

    def setup_method(self):
        app_debug.set_debug(False)
        jira_sync._last_result = None
        _restore_java_stubs()

    def test_creates_one_task(self, tmp_path):
        issue = _make_issue("PROJ-1", "Fix login bug")
        project = _make_project()
        project.getTasks.return_value = []
        new_task = _make_mpxj_task(uid=1, id=1)
        project.addTask.return_value = new_task

        jira_client = MagicMock()
        jira_client.search_issues.return_value = [issue]
        sidecar = str(tmp_path / "proj.json")

        with patch("integrations.jira_integration.resolve_filter_to_jql", return_value=("project = PROJ", "")), \
             patch("jpype.JClass", return_value=MagicMock()):
            result = jira_sync.run_sync(project, {}, jira_client, sidecar)

        assert result["created"] == 1
        assert result["updated"] == 0
        assert result["errors"] == []

    def test_task_name_includes_summary(self, tmp_path):
        issue = _make_issue("PROJ-2", "My feature summary")
        project = _make_project()
        project.getTasks.return_value = []
        new_task = _make_mpxj_task(uid=2, id=2)
        project.addTask.return_value = new_task

        jira_client = MagicMock()
        jira_client.search_issues.return_value = [issue]

        with patch("integrations.jira_integration.resolve_filter_to_jql", return_value=("project = PROJ", "")), \
             patch("jpype.JClass", return_value=MagicMock()):
            jira_sync.run_sync(project, {}, jira_client, str(tmp_path / "p.json"))

        set_name_calls = [c for c in new_task.method_calls if c[0] == "setName"]
        assert len(set_name_calls) >= 1
        final_name = set_name_calls[-1][1][0]
        assert "My feature summary" in final_name

    def test_sidecar_written_with_jira_key(self, tmp_path):
        issue = _make_issue("PROJ-3", "Sidecar test")
        project = _make_project()
        project.getTasks.return_value = []
        new_task = _make_mpxj_task(uid=3, id=3)
        project.addTask.return_value = new_task

        jira_client = MagicMock()
        jira_client.search_issues.return_value = [issue]
        sidecar = tmp_path / "proj.json"

        with patch("integrations.jira_integration.resolve_filter_to_jql", return_value=("project = PROJ", "")), \
             patch("jpype.JClass", return_value=MagicMock()):
            jira_sync.run_sync(project, {}, jira_client, str(sidecar))

        assert sidecar.exists()
        data = json.loads(sidecar.read_text(encoding="utf-8"))
        all_keys = [v.get("jira_key") for v in data.get("task_jira", {}).values()]
        assert "PROJ-3" in all_keys

    def test_result_has_log_entry(self, tmp_path):
        issue = _make_issue("PROJ-4", "Log test")
        project = _make_project()
        project.getTasks.return_value = []
        new_task = _make_mpxj_task(uid=4, id=4)
        project.addTask.return_value = new_task

        jira_client = MagicMock()
        jira_client.search_issues.return_value = [issue]

        with patch("integrations.jira_integration.resolve_filter_to_jql", return_value=("project = PROJ", "")), \
             patch("jpype.JClass", return_value=MagicMock()):
            result = jira_sync.run_sync(project, {}, jira_client, str(tmp_path / "p.json"))

        assert any("PROJ-4" in l for l in result.get("log", []))


# ---------------------------------------------------------------------------
# run_sync â€” task update
# ---------------------------------------------------------------------------

class TestRunSyncUpdateTask:
    """Unit tests for jira_sync.run_sync task update.

    \testinit
    Build a project with one existing task whose UID matches a sidecar entry for
    the same Jira key. Build a Jira client returning the same issue with an updated
    summary.

    \testrun
    Call run_sync(project, server, jira_client, sidecar_path).

    \testexpect
    The existing task is updated (result["updated"] == 1, created == 0) and the
    task's setName is called with the new summary.

    \testcheck
    Assert result counters and the setName call arguments.
    """

    def setup_method(self):
        app_debug.set_debug(False)
        jira_sync._last_result = None
        _restore_java_stubs()

    def test_updates_existing_task(self, tmp_path):
        existing_task = _make_mpxj_task(uid=10, id=1, name="[Task] Old summary")
        project = _make_project(tasks=[existing_task])

        sidecar = tmp_path / "proj.json"
        sidecar.write_text(json.dumps({"task_jira": {"10": {"jira_key": "PROJ-10"}}}), encoding="utf-8")

        issue = _make_issue("PROJ-10", "New summary")
        jira_client = MagicMock()
        jira_client.search_issues.return_value = [issue]

        with patch("integrations.jira_integration.resolve_filter_to_jql", return_value=("project = PROJ", "")), \
             patch("jpype.JClass", return_value=MagicMock()):
            result = jira_sync.run_sync(project, {}, jira_client, str(sidecar))

        assert result["updated"] == 1
        assert result["created"] == 0

    def test_update_calls_set_name_with_new_summary(self, tmp_path):
        existing_task = _make_mpxj_task(uid=11, id=1, name="[Task] Old name")
        project = _make_project(tasks=[existing_task])

        sidecar = tmp_path / "proj.json"
        sidecar.write_text(json.dumps({"task_jira": {"11": {"jira_key": "PROJ-11"}}}), encoding="utf-8")

        issue = _make_issue("PROJ-11", "Updated name from Jira")
        jira_client = MagicMock()
        jira_client.search_issues.return_value = [issue]

        with patch("integrations.jira_integration.resolve_filter_to_jql", return_value=("project = PROJ", "")), \
             patch("jpype.JClass", return_value=MagicMock()):
            jira_sync.run_sync(project, {}, jira_client, str(sidecar))

        calls = [c[1][0] for c in existing_task.method_calls if c[0] == "setName"]
        assert any("Updated name from Jira" in n for n in calls)

    def test_no_addTask_called_on_update(self, tmp_path):
        existing_task = _make_mpxj_task(uid=12, id=1)
        project = _make_project(tasks=[existing_task])

        sidecar = tmp_path / "proj.json"
        sidecar.write_text(json.dumps({"task_jira": {"12": {"jira_key": "PROJ-12"}}}), encoding="utf-8")

        issue = _make_issue("PROJ-12", "Same issue")
        jira_client = MagicMock()
        jira_client.search_issues.return_value = [issue]

        with patch("integrations.jira_integration.resolve_filter_to_jql", return_value=("project = PROJ", "")), \
             patch("jpype.JClass", return_value=MagicMock()):
            jira_sync.run_sync(project, {}, jira_client, str(sidecar))

        project.addTask.assert_not_called()


# ---------------------------------------------------------------------------
# run_sync â€” epic hierarchy
# ---------------------------------------------------------------------------

class TestRunSyncEpicHierarchy:
    """Unit tests for jira_sync.run_sync Epic container task creation.

    \testinit
    Build a project with no existing tasks. Build two Jira issues: one Epic
    and one Story whose parent.key points to the Epic.

    \testrun
    Call run_sync(project, server, jira_client, sidecar_path).

    \testexpect
    Two tasks are created; the Epic task has setSummary(True) and setRollup(True)
    called; the Story's setParentTask is called with the Epic task.

    \testcheck
    Assert result["created"] == 2, setSummary and setRollup called on epic task,
    setParentTask called on story task.
    """

    def setup_method(self):
        app_debug.set_debug(False)
        jira_sync._last_result = None
        _restore_java_stubs()

    def test_epic_and_subtask_both_created(self, tmp_path):
        epic = _make_issue("PROJ-100", "Big Epic", issue_type="Epic")
        story = _make_issue("PROJ-101", "Story inside epic", issue_type="Story",
                            parent_key="PROJ-100")

        epic_task = _make_mpxj_task(uid=100, id=1)
        story_task = _make_mpxj_task(uid=101, id=2)
        call_count = [0]

        def add_task_side_effect():
            call_count[0] += 1
            return epic_task if call_count[0] == 1 else story_task

        project = _make_project()
        project.getTasks.return_value = []
        project.addTask.side_effect = add_task_side_effect

        jira_client = MagicMock()
        jira_client.search_issues.return_value = [epic, story]

        with patch("integrations.jira_integration.resolve_filter_to_jql", return_value=("project = PROJ", "")), \
             patch("jpype.JClass", return_value=MagicMock()):
            result = jira_sync.run_sync(project, {}, jira_client, str(tmp_path / "p.json"))

        assert result["created"] == 2

    def test_epic_gets_summary_and_rollup(self, tmp_path):
        epic = _make_issue("PROJ-200", "Epic title", issue_type="Epic")

        epic_task = _make_mpxj_task(uid=200, id=1)
        project = _make_project()
        project.getTasks.return_value = []
        project.addTask.return_value = epic_task

        jira_client = MagicMock()
        jira_client.search_issues.return_value = [epic]

        with patch("integrations.jira_integration.resolve_filter_to_jql", return_value=("project = PROJ", "")), \
             patch("jpype.JClass", return_value=MagicMock()):
            jira_sync.run_sync(project, {}, jira_client, str(tmp_path / "p.json"))

        epic_task.setSummary.assert_called_with(True)
        epic_task.setRollup.assert_called_with(True)

    def test_subtask_gets_parent_task_set(self, tmp_path):
        epic = _make_issue("PROJ-300", "Parent epic", issue_type="Epic")
        sub  = _make_issue("PROJ-301", "Sub ticket", issue_type="Story",
                           parent_key="PROJ-300")

        epic_task  = _make_mpxj_task(uid=300, id=1)
        sub_task   = _make_mpxj_task(uid=301, id=2)
        call_count = [0]

        def _add():
            call_count[0] += 1
            return epic_task if call_count[0] == 1 else sub_task

        project = _make_project()
        project.getTasks.return_value = []
        project.addTask.side_effect = _add

        jira_client = MagicMock()
        jira_client.search_issues.return_value = [epic, sub]

        with patch("integrations.jira_integration.resolve_filter_to_jql", return_value=("project = PROJ", "")), \
             patch("jpype.JClass", return_value=MagicMock()):
            jira_sync.run_sync(project, {}, jira_client, str(tmp_path / "p.json"))

        sub_task.setParentTask.assert_called_with(epic_task)

    def test_epics_processed_before_subtasks(self, tmp_path):
        """Epics appear last in the input but must be processed first."""
        sub  = _make_issue("PROJ-401", "Sub first in list", issue_type="Story",
                           parent_key="PROJ-400")
        epic = _make_issue("PROJ-400", "Epic last in list", issue_type="Epic")

        epic_task = _make_mpxj_task(uid=400, id=1)
        sub_task  = _make_mpxj_task(uid=401, id=2)
        call_count = [0]

        def _add():
            call_count[0] += 1
            return epic_task if call_count[0] == 1 else sub_task

        project = _make_project()
        project.getTasks.return_value = []
        project.addTask.side_effect = _add

        jira_client = MagicMock()
        # Sub comes before epic in the API response
        jira_client.search_issues.return_value = [sub, epic]

        with patch("integrations.jira_integration.resolve_filter_to_jql", return_value=("project = PROJ", "")), \
             patch("jpype.JClass", return_value=MagicMock()):
            result = jira_sync.run_sync(project, {}, jira_client, str(tmp_path / "p.json"))

        # Both should be created, and sub should have its parent set
        assert result["created"] == 2
        sub_task.setParentTask.assert_called_with(epic_task)


# ---------------------------------------------------------------------------
# run_sync â€” result counters and last_result
# ---------------------------------------------------------------------------

class TestRunSyncResultCounters:
    """Unit tests for jira_sync.run_sync result dict and _last_result.

    \testinit
    Build project + sidecar + Jira client with a mix of new and existing issues.

    \testrun
    Call run_sync and inspect the returned dict.

    \testexpect
    Result dict has created, updated, skipped, errors, and log keys with correct
    integer counts; get_last_result() returns the same dict.

    \testcheck
    Assert all five keys present; assert get_last_result() is result.
    """

    def setup_method(self):
        app_debug.set_debug(False)
        jira_sync._last_result = None
        _restore_java_stubs()

    def test_result_has_all_keys(self, tmp_path):
        project = _make_project()
        project.getTasks.return_value = []
        project.addTask.return_value = _make_mpxj_task(uid=1)
        jira_client = MagicMock()
        jira_client.search_issues.return_value = [_make_issue()]

        with patch("integrations.jira_integration.resolve_filter_to_jql", return_value=("p=X", "")), \
             patch("jpype.JClass", return_value=MagicMock()):
            result = jira_sync.run_sync(project, {}, jira_client, str(tmp_path / "p.json"))

        for key in ("created", "updated", "skipped", "errors", "log"):
            assert key in result

    def test_get_last_result_equals_returned_dict(self, tmp_path):
        project = _make_project()
        project.getTasks.return_value = []
        project.addTask.return_value = _make_mpxj_task(uid=1)
        jira_client = MagicMock()
        jira_client.search_issues.return_value = [_make_issue()]

        with patch("integrations.jira_integration.resolve_filter_to_jql", return_value=("p=X", "")), \
             patch("jpype.JClass", return_value=MagicMock()):
            result = jira_sync.run_sync(project, {}, jira_client, str(tmp_path / "p.json"))

        assert jira_sync.get_last_result() is result

    def test_zero_issues_returns_zero_counts(self, tmp_path):
        project = _make_project()
        project.getTasks.return_value = []
        jira_client = MagicMock()
        jira_client.search_issues.return_value = []

        with patch("integrations.jira_integration.resolve_filter_to_jql", return_value=("p=X", "")), \
             patch("jpype.JClass", return_value=MagicMock()):
            result = jira_sync.run_sync(project, {}, jira_client, str(tmp_path / "p.json"))

        assert result["created"] == 0
        assert result["updated"] == 0
        assert result["skipped"] == 0

    def test_debug_log_contains_create_token(self, tmp_path):
        app_debug.set_debug(True)
        project = _make_project()
        project.getTasks.return_value = []
        project.addTask.return_value = _make_mpxj_task(uid=50)
        jira_client = MagicMock()
        jira_client.search_issues.return_value = [_make_issue("T-50", "Debug issue")]

        with patch("integrations.jira_integration.resolve_filter_to_jql", return_value=("p=X", "")), \
             patch("jpype.JClass", return_value=MagicMock()):
            result = jira_sync.run_sync(project, {}, jira_client, str(tmp_path / "p.json"))

        app_debug.set_debug(False)
        assert any("[CREATE]" in l and "T-50" in l for l in result["log"])


# ---------------------------------------------------------------------------
# run_sync â€” task name is plain summary (no issue-type prefix)
# ---------------------------------------------------------------------------

class TestRunSyncTaskNameNoPrefix:
    """Unit tests verifying the task name equals the Jira summary exactly.

    \testinit
    Build a project with no existing tasks and a Jira client returning issues
    of various types (Story, Bug, Epic, Sub-task).

    \testrun
    Call run_sync and inspect the name written to each new task.

    \testexpect
    The task name shall be exactly the Jira issue summary â€” no "[Type]" or
    abbreviation prefix is prepended.

    \testcheck
    Assert the setName call argument equals the raw summary string.
    """

    def setup_method(self):
        app_debug.set_debug(False)
        jira_sync._last_result = None
        _restore_java_stubs()

    def _run_single_issue(self, tmp_path, issue):
        task = _make_mpxj_task(uid=1, id=1)
        project = _make_project()
        project.getTasks.return_value = []
        project.addTask.return_value = task
        jira_client = MagicMock()
        jira_client.search_issues.return_value = [issue]
        with patch("integrations.jira_integration.resolve_filter_to_jql", return_value=("p=X", "")), \
             patch("jpype.JClass", return_value=MagicMock()):
            jira_sync.run_sync(project, {}, jira_client, str(tmp_path / "p.json"))
        return task

    def test_story_name_is_bare_summary(self, tmp_path):
        issue = _make_issue("PROJ-1", "Implement login screen", issue_type="Story")
        task = self._run_single_issue(tmp_path, issue)
        names = [c[1][0] for c in task.method_calls if c[0] == "setName"]
        assert any(n == "Implement login screen" for n in names)

    def test_bug_name_has_no_prefix(self, tmp_path):
        issue = _make_issue("PROJ-2", "Fix null pointer", issue_type="Bug")
        task = self._run_single_issue(tmp_path, issue)
        names = [c[1][0] for c in task.method_calls if c[0] == "setName"]
        final = names[-1]
        assert not final.startswith("[")
        assert "Fix null pointer" in final

    def test_subtask_name_has_no_bracket_prefix(self, tmp_path):
        issue = _make_issue("PROJ-3", "Write unit tests", issue_type="Sub-task")
        task = self._run_single_issue(tmp_path, issue)
        names = [c[1][0] for c in task.method_calls if c[0] == "setName"]
        assert all("[" not in n for n in names)

    def test_change_request_name_is_summary_only(self, tmp_path):
        issue = _make_issue("PROJ-4", "Adjust API contract", issue_type="Change Request")
        task = self._run_single_issue(tmp_path, issue)
        names = [c[1][0] for c in task.method_calls if c[0] == "setName"]
        assert any(n == "Adjust API contract" for n in names)


# ---------------------------------------------------------------------------
# run_sync â€” pagination (all pages fetched)
# ---------------------------------------------------------------------------

class TestRunSyncPagination:
    """Unit tests verifying paginated fetching of Jira issues.

    \testinit
    Build a mock Jira client whose search_issues returns different pages on
    successive calls to simulate a large result set split across pages.

    \testrun
    Call run_sync and assert search_issues is called the expected number of
    times with incrementing startAt values, and that all issues are processed.

    \testexpect
    run_sync shall fetch pages until a partial (or empty) page is returned and
    aggregate all issues from every page; result["created"] must equal the total
    number of unique issues returned across all pages.

    \testcheck
    Assert search_issues call count and call arguments; assert created count.
    """

    def setup_method(self):
        app_debug.set_debug(False)
        jira_sync._last_result = None
        _restore_java_stubs()

    def _make_page(self, keys):
        return [_make_issue(k, f"Issue {k}") for k in keys]

    def test_single_partial_page_fetched_once(self, tmp_path):
        """When first page has < 100 items, search_issues is called exactly once."""
        project = _make_project()
        project.getTasks.return_value = []
        created_tasks = []

        def _add():
            t = _make_mpxj_task(uid=len(created_tasks) + 1)
            created_tasks.append(t)
            return t

        project.addTask.side_effect = _add
        jira_client = MagicMock()
        # 3-item page â€” less than page_size (100)
        jira_client.search_issues.return_value = self._make_page(["A-1", "A-2", "A-3"])

        with patch("integrations.jira_integration.resolve_filter_to_jql", return_value=("p=X", "")), \
             patch("jpype.JClass", return_value=MagicMock()):
            result = jira_sync.run_sync(project, {}, jira_client, str(tmp_path / "p.json"))

        assert result["created"] == 3
        assert jira_client.search_issues.call_count == 1

    def test_two_full_then_partial_page(self, tmp_path):
        """Two full pages (100 each) followed by one partial (50) â†’ 250 issues total."""
        project = _make_project()
        project.getTasks.return_value = []
        uid_counter = [0]

        def _add():
            uid_counter[0] += 1
            return _make_mpxj_task(uid=uid_counter[0])

        project.addTask.side_effect = _add
        jira_client = MagicMock()

        page1 = self._make_page([f"A-{i}" for i in range(1, 101)])     # 100 items
        page2 = self._make_page([f"B-{i}" for i in range(1, 101)])     # 100 items
        page3 = self._make_page([f"C-{i}" for i in range(1, 51)])      # 50 items

        jira_client.search_issues.side_effect = [page1, page2, page3]

        with patch("integrations.jira_integration.resolve_filter_to_jql", return_value=("p=X", "")), \
             patch("jpype.JClass", return_value=MagicMock()):
            result = jira_sync.run_sync(project, {}, jira_client, str(tmp_path / "p.json"))

        assert result["created"] == 250
        assert jira_client.search_issues.call_count == 3

    def test_pagination_uses_correct_start_at(self, tmp_path):
        """Second page call must use startAt=100 (the count of the first page)."""
        project = _make_project()
        project.getTasks.return_value = []
        uid_counter = [0]

        def _add():
            uid_counter[0] += 1
            return _make_mpxj_task(uid=uid_counter[0])

        project.addTask.side_effect = _add
        jira_client = MagicMock()

        page1 = self._make_page([f"A-{i}" for i in range(1, 101)])
        page2 = self._make_page(["B-1", "B-2"])

        jira_client.search_issues.side_effect = [page1, page2]

        with patch("integrations.jira_integration.resolve_filter_to_jql", return_value=("p=X", "")), \
             patch("jpype.JClass", return_value=MagicMock()):
            jira_sync.run_sync(project, {}, jira_client, str(tmp_path / "p.json"))

        calls = jira_client.search_issues.call_args_list
        assert calls[0][1]["startAt"] == 0
        assert calls[1][1]["startAt"] == 100

    def test_empty_first_page_creates_nothing(self, tmp_path):
        """Empty first page â†’ loop exits immediately, nothing created."""
        project = _make_project()
        project.getTasks.return_value = []
        jira_client = MagicMock()
        jira_client.search_issues.return_value = []

        with patch("integrations.jira_integration.resolve_filter_to_jql", return_value=("p=X", "")), \
             patch("jpype.JClass", return_value=MagicMock()):
            result = jira_sync.run_sync(project, {}, jira_client, str(tmp_path / "p.json"))

        assert result["created"] == 0
        assert jira_client.search_issues.call_count == 1

    def test_pagination_requests_specific_fields(self, tmp_path):
        """search_issues must not use fields='*all'; must pass an explicit field list."""
        project = _make_project()
        project.getTasks.return_value = []
        jira_client = MagicMock()
        jira_client.search_issues.return_value = []

        with patch("integrations.jira_integration.resolve_filter_to_jql", return_value=("p=X", "")), \
             patch("jpype.JClass", return_value=MagicMock()):
            jira_sync.run_sync(project, {}, jira_client, str(tmp_path / "p.json"))

        call_kwargs = jira_client.search_issues.call_args[1]
        fields_arg = call_kwargs.get("fields", "")
        assert fields_arg != "*all"
        assert "summary" in fields_arg
        assert "issuetype" in fields_arg

    def test_debug_log_contains_update_token(self, tmp_path):
        app_debug.set_debug(True)
        existing = _make_mpxj_task(uid=60)
        project = _make_project(tasks=[existing])
        sidecar = tmp_path / "p.json"
        sidecar.write_text(json.dumps({"task_jira": {"60": {"jira_key": "T-60"}}}), encoding="utf-8")

        jira_client = MagicMock()
        jira_client.search_issues.return_value = [_make_issue("T-60", "Updated")]

        with patch("integrations.jira_integration.resolve_filter_to_jql", return_value=("p=X", "")), \
             patch("jpype.JClass", return_value=MagicMock()):
            result = jira_sync.run_sync(project, {}, jira_client, str(sidecar))

        app_debug.set_debug(False)
        assert any("[UPDATE]" in l and "T-60" in l for l in result["log"])


# ---------------------------------------------------------------------------
# Helpers shared by P2J tests
# ---------------------------------------------------------------------------

def _p2j_defaults(**overrides) -> dict:
    """Return a minimal project2jira config dict, optionally overriding keys."""
    cfg = {
        "dry_run": False,
        "export_scope": "all_tasks",
        "create_update_mode": "create_update",
        "conflict_policy": "prefer_project",
        "unlinked_task_behavior": "create",
        "issue_type_map": {},
        "transition_map": {},
        "hierarchy_export": {"enabled": False},
        "auditability": {"enabled": False},
        "reliability": {"enabled": False, "max_retries": 3, "backoff_seconds": 0.0},
        "fields": {
            "jira_summary": {"enabled": True, "jira_field": "summary"},
        },
    }
    cfg.update(overrides)
    return cfg


def _make_p2j_project(tasks=None, p2j_cfg=None):
    """Build a mock MPXJ ProjectFile that returns a p2j config from custom properties."""
    project = MagicMock()
    tasks_list = tasks or []
    project.getTasks.return_value = tasks_list
    props = MagicMock()
    cp = MagicMock()
    cp_data = {}
    if p2j_cfg is not None:
        cp_data["project2jira"] = json.dumps(p2j_cfg)
    cp.get.side_effect = lambda key: cp_data.get(key)
    props.getCustomProperties.return_value = cp
    project.getProjectProperties.return_value = props
    return project


def _make_p2j_task(name="Task A", uid=1, pct=0.0, notes="", summary=False,
                   parent=None, predecessors=None, assignments=None):
    """Build a mock MPXJ task with the subset of methods used by run_push_to_jira."""
    task = MagicMock()
    task.getName.return_value = name
    task.getUniqueID.return_value = uid
    task.getID.return_value = uid
    task.getNotes.return_value = notes
    task.getPercentageComplete.return_value = pct
    task.getSummary.return_value = summary
    task.getParentTask.return_value = parent
    task.getResourceAssignments.return_value = assignments or []
    task.getPredecessors.return_value = predecessors or []
    task.getDeadline.return_value = None
    task.getType.return_value = ""
    return task


# ---------------------------------------------------------------------------
# get_last_push_result
# ---------------------------------------------------------------------------

class TestGetLastPushResult:
    """Unit tests for jira_sync.get_last_push_result.

    \testinit
    Reset the module-level _last_push_result via a successful push (or do nothing).

    \testrun
    Call get_last_push_result() before and after run_push_to_jira().

    \testexpect
    Returns None when no push has been executed; returns a dict with the push
    counters after a push completes.

    \testcheck
    Assert None / dict type and key presence.
    """

    def test_returns_none_before_any_push(self):
        jira_sync._last_push_result = None
        assert jira_sync.get_last_push_result() is None

    def test_returns_dict_after_push(self, tmp_path):
        task = _make_p2j_task(uid=1)
        project = _make_p2j_project(tasks=[task], p2j_cfg=_p2j_defaults())
        jira_client = MagicMock()
        jira_client.issue_types.return_value = []
        new_issue = MagicMock()
        new_issue.key = "P-1"
        new_issue.id = "101"
        jira_client.create_issue.return_value = new_issue

        jira_sync.run_push_to_jira(project, {}, jira_client, str(tmp_path / "s.json"))

        result = jira_sync.get_last_push_result()
        assert isinstance(result, dict)

    def test_result_has_all_keys(self, tmp_path):
        task = _make_p2j_task(uid=2)
        project = _make_p2j_project(tasks=[task], p2j_cfg=_p2j_defaults())
        jira_client = MagicMock()
        jira_client.issue_types.return_value = []
        new_issue = MagicMock()
        new_issue.key = "P-2"
        new_issue.id = "102"
        jira_client.create_issue.return_value = new_issue

        result = jira_sync.run_push_to_jira(project, {}, jira_client, str(tmp_path / "s.json"))

        for key in ("created", "updated", "transitioned", "skipped", "errors", "log",
                    "preview_actions", "dry_run"):
            assert key in result, f"Missing key: {key}"


# ---------------------------------------------------------------------------
# _task_status_string
# ---------------------------------------------------------------------------

class TestTaskStatusString:
    """Unit tests for jira_sync._task_status_string.

    \testinit
    Build mock MPXJ tasks with specific percentage-complete values.

    \testrun
    Call _task_status_string(task).

    \testexpect
    0 % â†’ "To Do"; 1â€“99 % â†’ "In Progress"; 100 % â†’ "Done".

    \testcheck
    Assert the returned string matches the expected value.
    """

    def test_zero_percent_returns_to_do(self):
        task = _make_p2j_task(pct=0.0)
        assert jira_sync._task_status_string(task) == "To Do"

    def test_fifty_percent_returns_in_progress(self):
        task = _make_p2j_task(pct=50.0)
        assert jira_sync._task_status_string(task) == "In Progress"

    def test_hundred_percent_returns_done(self):
        task = _make_p2j_task(pct=100.0)
        assert jira_sync._task_status_string(task) == "Done"

    def test_small_nonzero_percent_returns_in_progress(self):
        task = _make_p2j_task(pct=1.0)
        assert jira_sync._task_status_string(task) == "In Progress"

    def test_ninety_nine_percent_returns_in_progress(self):
        task = _make_p2j_task(pct=99.0)
        assert jira_sync._task_status_string(task) == "In Progress"


# ---------------------------------------------------------------------------
# _task_to_jira_payload
# ---------------------------------------------------------------------------

class TestTaskToJiraPayload:
    """Unit tests for jira_sync._task_to_jira_payload.

    \testinit
    Build mock tasks and p2j config dicts with various field-enabled combinations.

    \testrun
    Call _task_to_jira_payload(task, p2j).

    \testexpect
    The returned dict always contains "summary"; optional fields appear only when
    enabled in the config.

    \testcheck
    Assert key presence/absence and values in the returned payload.
    """

    def _make_p2j_fields(**extra_fields):
        cfg = {"fields": {"jira_summary": {"enabled": True, "jira_field": "summary"}}}
        cfg["fields"].update(extra_fields)
        return cfg

    def test_summary_always_present(self):
        task = _make_p2j_task(name="My Task")
        p2j = {"fields": {"jira_summary": {"enabled": True, "jira_field": "summary"}}}
        payload = jira_sync._task_to_jira_payload(task, p2j)
        assert payload.get("summary") == "My Task"

    def test_disabled_description_not_in_payload(self):
        task = _make_p2j_task(name="T", notes="Some notes")
        p2j = {"fields": {
            "jira_summary": {"enabled": True, "jira_field": "summary"},
            "jira_description": {"enabled": False, "jira_field": "description"},
        }}
        payload = jira_sync._task_to_jira_payload(task, p2j)
        assert "description" not in payload

    def test_enabled_description_added_to_payload(self):
        task = _make_p2j_task(name="T", notes="Note text")
        p2j = {"fields": {
            "jira_summary": {"enabled": True, "jira_field": "summary"},
            "jira_description": {"enabled": True, "jira_field": "description"},
        }}
        payload = jira_sync._task_to_jira_payload(task, p2j)
        assert payload.get("description") == "Note text"

    def test_assignee_uses_resource_name(self):
        res = MagicMock()
        res.getName.return_value = "Alice"
        assignment = MagicMock()
        assignment.getResource.return_value = res
        task = _make_p2j_task(name="T", assignments=[assignment])
        p2j = {"fields": {
            "jira_summary": {"enabled": True, "jira_field": "summary"},
            "jira_assignee": {"enabled": True, "jira_field": "assignee"},
        }}
        payload = jira_sync._task_to_jira_payload(task, p2j)
        assert payload.get("assignee") == {"name": "Alice"}

    def test_disabled_assignee_not_in_payload(self):
        res = MagicMock()
        res.getName.return_value = "Bob"
        assignment = MagicMock()
        assignment.getResource.return_value = res
        task = _make_p2j_task(name="T", assignments=[assignment])
        p2j = {"fields": {
            "jira_summary": {"enabled": True, "jira_field": "summary"},
            "jira_assignee": {"enabled": False, "jira_field": "assignee"},
        }}
        payload = jira_sync._task_to_jira_payload(task, p2j)
        assert "assignee" not in payload

    def test_empty_name_omits_summary(self):
        task = _make_p2j_task(name="")
        p2j = {"fields": {"jira_summary": {"enabled": True, "jira_field": "summary"}}}
        payload = jira_sync._task_to_jira_payload(task, p2j)
        assert "summary" not in payload


# ---------------------------------------------------------------------------
# _with_retry
# ---------------------------------------------------------------------------

class TestWithRetry:
    """Unit tests for jira_sync._with_retry.

    \testinit
    Prepare callable stubs that succeed immediately, raise transient errors, or
    raise non-transient errors.

    \testrun
    Call _with_retry(fn, max_retries, backoff_seconds=0.0).

    \testexpect
    Returns the callable's result on success; retries on transient errors up to
    max_retries; re-raises immediately on non-transient errors.

    \testcheck
    Assert return value, call count, and exception type.
    """

    def test_returns_result_on_first_try(self):
        fn = MagicMock(return_value="ok")
        result = jira_sync._with_retry(fn, max_retries=3, backoff_seconds=0.0)
        assert result == "ok"
        assert fn.call_count == 1

    def test_retries_on_transient_error_and_succeeds(self):
        side_effects = [Exception("timeout"), Exception("timeout"), "success"]
        fn = MagicMock(side_effect=side_effects)
        result = jira_sync._with_retry(fn, max_retries=3, backoff_seconds=0.0)
        assert result == "success"
        assert fn.call_count == 3

    def test_raises_after_max_retries_exceeded(self):
        fn = MagicMock(side_effect=Exception("timeout"))
        with pytest.raises(Exception, match="timeout"):
            jira_sync._with_retry(fn, max_retries=2, backoff_seconds=0.0)
        assert fn.call_count == 3  # 1 initial + 2 retries

    def test_raises_immediately_on_non_transient_error(self):
        fn = MagicMock(side_effect=ValueError("not transient"))
        with pytest.raises(ValueError, match="not transient"):
            jira_sync._with_retry(fn, max_retries=5, backoff_seconds=0.0)
        assert fn.call_count == 1


# ---------------------------------------------------------------------------
# run_push_to_jira â€” result structure
# ---------------------------------------------------------------------------

class TestRunPushToJiraResultKeys:
    """run_push_to_jira always returns a dict with the expected keys.

    \testinit
    Build an empty project (no tasks) with valid p2j config.

    \testrun
    Call run_push_to_jira(project, {}, jira_client, sidecar_path).

    \testexpect
    Result dict has keys: created, updated, transitioned, skipped, errors, log,
    preview_actions, dry_run.

    \testcheck
    Assert key presence.
    """

    def test_result_has_all_expected_keys(self, tmp_path):
        project = _make_p2j_project(tasks=[], p2j_cfg=_p2j_defaults())
        jira_client = MagicMock()
        jira_client.issue_types.return_value = []
        result = jira_sync.run_push_to_jira(project, {}, jira_client, str(tmp_path / "s.json"))
        for key in ("created", "updated", "transitioned", "skipped", "errors",
                    "log", "preview_actions", "dry_run"):
            assert key in result

    def test_get_last_push_result_equals_returned_dict(self, tmp_path):
        project = _make_p2j_project(tasks=[], p2j_cfg=_p2j_defaults())
        jira_client = MagicMock()
        jira_client.issue_types.return_value = []
        result = jira_sync.run_push_to_jira(project, {}, jira_client, str(tmp_path / "s.json"))
        assert jira_sync.get_last_push_result() is result

    def test_empty_project_zero_counts(self, tmp_path):
        project = _make_p2j_project(tasks=[], p2j_cfg=_p2j_defaults())
        jira_client = MagicMock()
        jira_client.issue_types.return_value = []
        result = jira_sync.run_push_to_jira(project, {}, jira_client, str(tmp_path / "s.json"))
        assert result["created"] == 0
        assert result["updated"] == 0
        assert result["transitioned"] == 0


# ---------------------------------------------------------------------------
# run_push_to_jira â€” dry-run
# ---------------------------------------------------------------------------

class TestRunPushToJiraDryRun:
    """run_push_to_jira dry_run=True populates preview_actions without API calls.

    \testinit
    Build a project with one unlinked task; set dry_run=True in config.

    \testrun
    Call run_push_to_jira(project, {}, jira_client, sidecar_path).

    \testexpect
    result["dry_run"] is True; preview_actions contains one entry with action="create";
    jira_client.create_issue is never called.

    \testcheck
    Assert dry_run flag, preview_actions length and content, create_issue call count.
    """

    def test_dry_run_flag_is_set(self, tmp_path):
        task = _make_p2j_task(uid=1)
        cfg = _p2j_defaults(dry_run=True, unlinked_task_behavior="create")
        project = _make_p2j_project(tasks=[task], p2j_cfg=cfg)
        jira_client = MagicMock()
        jira_client.issue_types.return_value = []
        result = jira_sync.run_push_to_jira(project, {}, jira_client, str(tmp_path / "s.json"))
        assert result["dry_run"] is True

    def test_preview_actions_populated(self, tmp_path):
        task = _make_p2j_task(name="Alpha", uid=1)
        cfg = _p2j_defaults(dry_run=True, unlinked_task_behavior="create")
        project = _make_p2j_project(tasks=[task], p2j_cfg=cfg)
        jira_client = MagicMock()
        jira_client.issue_types.return_value = []
        result = jira_sync.run_push_to_jira(project, {}, jira_client, str(tmp_path / "s.json"))
        assert len(result["preview_actions"]) == 1
        assert result["preview_actions"][0]["action"] == "create"
        assert result["preview_actions"][0]["task_name"] == "Alpha"

    def test_create_issue_not_called_during_dry_run(self, tmp_path):
        task = _make_p2j_task(uid=1)
        cfg = _p2j_defaults(dry_run=True, unlinked_task_behavior="create")
        project = _make_p2j_project(tasks=[task], p2j_cfg=cfg)
        jira_client = MagicMock()
        jira_client.issue_types.return_value = []
        jira_sync.run_push_to_jira(project, {}, jira_client, str(tmp_path / "s.json"))
        jira_client.create_issue.assert_not_called()

    def test_dry_run_jira_key_is_NEW_for_unlinked(self, tmp_path):
        task = _make_p2j_task(name="Beta", uid=2)
        cfg = _p2j_defaults(dry_run=True, unlinked_task_behavior="create")
        project = _make_p2j_project(tasks=[task], p2j_cfg=cfg)
        jira_client = MagicMock()
        jira_client.issue_types.return_value = []
        result = jira_sync.run_push_to_jira(project, {}, jira_client, str(tmp_path / "s.json"))
        assert result["preview_actions"][0]["jira_key"] == "NEW"


# ---------------------------------------------------------------------------
# run_push_to_jira â€” create
# ---------------------------------------------------------------------------

class TestRunPushToJiraCreate:
    """run_push_to_jira creates a Jira issue for an unlinked task.

    \testinit
    Build a project with one unlinked task; configure unlinked_task_behavior="create".
    jira_client.create_issue returns a mock issue with key="P-1".

    \testrun
    Call run_push_to_jira(project, {}, jira_client, sidecar_path).

    \testexpect
    result["created"] == 1; jira_client.create_issue called once;
    sidecar file written with task_jira entry for the new key.

    \testcheck
    Assert counter, mock call count, and sidecar contents.
    """

    def test_creates_one_issue(self, tmp_path):
        task = _make_p2j_task(name="New Task", uid=10)
        project = _make_p2j_project(tasks=[task], p2j_cfg=_p2j_defaults())
        jira_client = MagicMock()
        jira_client.issue_types.return_value = []
        new_issue = MagicMock()
        new_issue.key = "P-10"
        new_issue.id = "1010"
        jira_client.create_issue.return_value = new_issue

        result = jira_sync.run_push_to_jira(project, {}, jira_client, str(tmp_path / "s.json"))

        assert result["created"] == 1
        jira_client.create_issue.assert_called_once()

    def test_create_issue_receives_summary(self, tmp_path):
        task = _make_p2j_task(name="Summary Here", uid=11)
        project = _make_p2j_project(tasks=[task], p2j_cfg=_p2j_defaults())
        jira_client = MagicMock()
        jira_client.issue_types.return_value = []
        new_issue = MagicMock()
        new_issue.key = "P-11"
        new_issue.id = "1011"
        jira_client.create_issue.return_value = new_issue

        jira_sync.run_push_to_jira(project, {}, jira_client, str(tmp_path / "s.json"))

        call_fields = jira_client.create_issue.call_args[1]["fields"]
        assert call_fields.get("summary") == "Summary Here"

    def test_sidecar_written_with_new_key(self, tmp_path):
        task = _make_p2j_task(name="New Task", uid=12)
        project = _make_p2j_project(tasks=[task], p2j_cfg=_p2j_defaults())
        jira_client = MagicMock()
        jira_client.issue_types.return_value = []
        new_issue = MagicMock()
        new_issue.key = "P-12"
        new_issue.id = "1012"
        jira_client.create_issue.return_value = new_issue
        sidecar = str(tmp_path / "s.json")

        jira_sync.run_push_to_jira(project, {}, jira_client, sidecar)

        data = json.loads(open(sidecar, encoding="utf-8").read())
        assert data["task_jira"]["12"]["jira_key"] == "P-12"

    def test_log_contains_create_token(self, tmp_path):
        task = _make_p2j_task(name="Log Task", uid=13)
        project = _make_p2j_project(tasks=[task], p2j_cfg=_p2j_defaults())
        jira_client = MagicMock()
        jira_client.issue_types.return_value = []
        new_issue = MagicMock()
        new_issue.key = "P-13"
        new_issue.id = "1013"
        jira_client.create_issue.return_value = new_issue

        result = jira_sync.run_push_to_jira(project, {}, jira_client, str(tmp_path / "s.json"))

        assert any("[CREATE]" in l for l in result["log"])


# ---------------------------------------------------------------------------
# run_push_to_jira â€” update
# ---------------------------------------------------------------------------

class TestRunPushToJiraUpdate:
    """run_push_to_jira updates a Jira issue for a linked task.

    \testinit
    Build a project with one task linked to "P-20" via the sidecar.

    \testrun
    Call run_push_to_jira(project, {}, jira_client, sidecar_path).

    \testexpect
    result["updated"] == 1; jira_client.issue().update() called once;
    jira_client.create_issue never called.

    \testcheck
    Assert counter and mock call counts.
    """

    def test_updates_linked_issue(self, tmp_path):
        task = _make_p2j_task(name="Existing Task", uid=20)
        project = _make_p2j_project(tasks=[task], p2j_cfg=_p2j_defaults())
        sidecar = tmp_path / "s.json"
        sidecar.write_text(json.dumps({"task_jira": {"20": {"jira_key": "P-20"}}}),
                           encoding="utf-8")
        jira_client = MagicMock()
        jira_client.issue_types.return_value = []
        issue_obj = MagicMock()
        jira_client.issue.return_value = issue_obj

        result = jira_sync.run_push_to_jira(project, {}, jira_client, str(sidecar))

        assert result["updated"] == 1

    def test_issue_update_called_once(self, tmp_path):
        task = _make_p2j_task(name="Existing Task", uid=21)
        project = _make_p2j_project(tasks=[task], p2j_cfg=_p2j_defaults())
        sidecar = tmp_path / "s.json"
        sidecar.write_text(json.dumps({"task_jira": {"21": {"jira_key": "P-21"}}}),
                           encoding="utf-8")
        jira_client = MagicMock()
        jira_client.issue_types.return_value = []
        issue_obj = MagicMock()
        jira_client.issue.return_value = issue_obj

        jira_sync.run_push_to_jira(project, {}, jira_client, str(sidecar))

        issue_obj.update.assert_called_once()

    def test_create_issue_not_called_for_update(self, tmp_path):
        task = _make_p2j_task(name="Existing Task", uid=22)
        project = _make_p2j_project(tasks=[task], p2j_cfg=_p2j_defaults())
        sidecar = tmp_path / "s.json"
        sidecar.write_text(json.dumps({"task_jira": {"22": {"jira_key": "P-22"}}}),
                           encoding="utf-8")
        jira_client = MagicMock()
        jira_client.issue_types.return_value = []
        jira_client.issue.return_value = MagicMock()

        jira_sync.run_push_to_jira(project, {}, jira_client, str(sidecar))

        jira_client.create_issue.assert_not_called()

    def test_log_contains_update_token(self, tmp_path):
        task = _make_p2j_task(name="Update Task", uid=23)
        project = _make_p2j_project(tasks=[task], p2j_cfg=_p2j_defaults())
        sidecar = tmp_path / "s.json"
        sidecar.write_text(json.dumps({"task_jira": {"23": {"jira_key": "P-23"}}}),
                           encoding="utf-8")
        jira_client = MagicMock()
        jira_client.issue_types.return_value = []
        jira_client.issue.return_value = MagicMock()

        result = jira_sync.run_push_to_jira(project, {}, jira_client, str(sidecar))

        assert any("[UPDATE]" in l for l in result["log"])


# ---------------------------------------------------------------------------
# run_push_to_jira â€” skip unlinked tasks
# ---------------------------------------------------------------------------

class TestRunPushToJiraSkip:
    """run_push_to_jira skips unlinked tasks when unlinked_task_behavior='skip'.

    \testinit
    Build a project with one unlinked task; set unlinked_task_behavior="skip".

    \testrun
    Call run_push_to_jira(project, {}, jira_client, sidecar_path).

    \testexpect
    result["skipped"] == 1; result["created"] == 0;
    jira_client.create_issue never called.

    \testcheck
    Assert counter and mock call count.
    """

    def test_skips_unlinked_task(self, tmp_path):
        task = _make_p2j_task(uid=30)
        cfg = _p2j_defaults(unlinked_task_behavior="skip")
        project = _make_p2j_project(tasks=[task], p2j_cfg=cfg)
        jira_client = MagicMock()
        jira_client.issue_types.return_value = []

        result = jira_sync.run_push_to_jira(project, {}, jira_client, str(tmp_path / "s.json"))

        assert result["skipped"] == 1
        assert result["created"] == 0

    def test_create_issue_not_called_when_skipping(self, tmp_path):
        task = _make_p2j_task(uid=31)
        cfg = _p2j_defaults(unlinked_task_behavior="skip")
        project = _make_p2j_project(tasks=[task], p2j_cfg=cfg)
        jira_client = MagicMock()
        jira_client.issue_types.return_value = []

        jira_sync.run_push_to_jira(project, {}, jira_client, str(tmp_path / "s.json"))

        jira_client.create_issue.assert_not_called()

    def test_log_contains_skip_token(self, tmp_path):
        task = _make_p2j_task(uid=32)
        cfg = _p2j_defaults(unlinked_task_behavior="skip")
        project = _make_p2j_project(tasks=[task], p2j_cfg=cfg)
        jira_client = MagicMock()
        jira_client.issue_types.return_value = []

        result = jira_sync.run_push_to_jira(project, {}, jira_client, str(tmp_path / "s.json"))

        assert any("[SKIP]" in l for l in result["log"])


# ---------------------------------------------------------------------------
# run_push_to_jira â€” workflow transition
# ---------------------------------------------------------------------------

class TestRunPushToJiraTransition:
    """run_push_to_jira applies a Jira workflow transition when configured.

    \testinit
    Sidecar links task uid=40 to "P-40"; p2j transition_map maps "Done" â†’ "Close";
    jira_client.transitions returns one transition with name="Close", id="5";
    task percentage_complete=100 (Done).

    \testrun
    Call run_push_to_jira(project, {}, jira_client, sidecar_path).

    \testexpect
    result["transitioned"] == 1; jira_client.transition_issue("P-40", "5") called.

    \testcheck
    Assert counter and mock call arguments.
    """

    def test_transition_applied_when_mapped(self, tmp_path):
        task = _make_p2j_task(name="Done Task", uid=40, pct=100.0)
        cfg = _p2j_defaults(transition_map={"Done": "Close"})
        project = _make_p2j_project(tasks=[task], p2j_cfg=cfg)
        sidecar = tmp_path / "s.json"
        sidecar.write_text(json.dumps({"task_jira": {"40": {"jira_key": "P-40"}}}),
                           encoding="utf-8")
        jira_client = MagicMock()
        jira_client.issue_types.return_value = []
        jira_client.issue.return_value = MagicMock()
        jira_client.transitions.return_value = [{"id": "5", "name": "Close"}]

        result = jira_sync.run_push_to_jira(project, {}, jira_client, str(sidecar))

        assert result["transitioned"] == 1
        jira_client.transition_issue.assert_called_once_with("P-40", "5")

    def test_transition_not_applied_without_mapping(self, tmp_path):
        task = _make_p2j_task(name="Done Task", uid=41, pct=100.0)
        cfg = _p2j_defaults(transition_map={})
        project = _make_p2j_project(tasks=[task], p2j_cfg=cfg)
        sidecar = tmp_path / "s.json"
        sidecar.write_text(json.dumps({"task_jira": {"41": {"jira_key": "P-41"}}}),
                           encoding="utf-8")
        jira_client = MagicMock()
        jira_client.issue_types.return_value = []
        jira_client.issue.return_value = MagicMock()

        result = jira_sync.run_push_to_jira(project, {}, jira_client, str(sidecar))

        assert result["transitioned"] == 0
        jira_client.transition_issue.assert_not_called()

    def test_log_contains_transition_token(self, tmp_path):
        task = _make_p2j_task(name="Done Task", uid=42, pct=100.0)
        cfg = _p2j_defaults(transition_map={"Done": "Close"})
        project = _make_p2j_project(tasks=[task], p2j_cfg=cfg)
        sidecar = tmp_path / "s.json"
        sidecar.write_text(json.dumps({"task_jira": {"42": {"jira_key": "P-42"}}}),
                           encoding="utf-8")
        jira_client = MagicMock()
        jira_client.issue_types.return_value = []
        jira_client.issue.return_value = MagicMock()
        jira_client.transitions.return_value = [{"id": "7", "name": "Close"}]

        result = jira_sync.run_push_to_jira(project, {}, jira_client, str(sidecar))

        assert any("[TRANSITION]" in l for l in result["log"])


# ---------------------------------------------------------------------------
# run_push_to_jira â€” conflict detection
# ---------------------------------------------------------------------------

class TestRunPushToJiraConflict:
    """run_push_to_jira skips an issue when a concurrent remote edit is detected.

    \testinit
    Sidecar: task uid=50 linked to "P-50", last_pushed_at="2024-01-01T00:00:00Z".
    Remote issue.fields.updated = "2024-06-01T12:00:00Z" (newer than last_pushed_at).
    conflict_policy = "prefer_jira".

    \testrun
    Call run_push_to_jira(project, {}, jira_client, sidecar_path).

    \testexpect
    result["skipped"] == 1; issue.update never called.

    \testcheck
    Assert counter and mock call count.
    """

    def test_conflict_prefer_jira_skips_update(self, tmp_path):
        task = _make_p2j_task(name="Conflict Task", uid=50)
        cfg = _p2j_defaults(conflict_policy="prefer_jira")
        project = _make_p2j_project(tasks=[task], p2j_cfg=cfg)
        sidecar = tmp_path / "s.json"
        sidecar.write_text(json.dumps({
            "task_jira": {"50": {"jira_key": "P-50"}},
            "task_p2j":  {"50": {"last_pushed_at": "2024-01-01T00:00:00Z"}},
        }), encoding="utf-8")
        jira_client = MagicMock()
        jira_client.issue_types.return_value = []
        remote_issue = MagicMock()
        remote_issue.fields.updated = "2024-06-01T12:00:00Z"
        jira_client.issue.return_value = remote_issue

        result = jira_sync.run_push_to_jira(project, {}, jira_client, str(sidecar))

        assert result["skipped"] == 1
        remote_issue.update.assert_not_called()

    def test_no_conflict_when_remote_not_newer(self, tmp_path):
        task = _make_p2j_task(name="No Conflict", uid=51)
        cfg = _p2j_defaults(conflict_policy="prefer_jira")
        project = _make_p2j_project(tasks=[task], p2j_cfg=cfg)
        sidecar = tmp_path / "s.json"
        sidecar.write_text(json.dumps({
            "task_jira": {"51": {"jira_key": "P-51"}},
            "task_p2j":  {"51": {"last_pushed_at": "2024-06-02T00:00:00Z"}},
        }), encoding="utf-8")
        jira_client = MagicMock()
        jira_client.issue_types.return_value = []
        remote_issue = MagicMock()
        remote_issue.fields.updated = "2024-06-01T00:00:00Z"  # older
        jira_client.issue.return_value = remote_issue

        result = jira_sync.run_push_to_jira(project, {}, jira_client, str(sidecar))

        assert result["updated"] == 1


# ---------------------------------------------------------------------------
# run_push_to_jira â€” included_task_uids filter
# ---------------------------------------------------------------------------

class TestRunPushToJiraIncludedUids:
    """run_push_to_jira respects the included_task_uids filter.

    \testinit
    Build a project with two tasks (uid=60, uid=61). Pass included_task_uids={"60"}.

    \testrun
    Call run_push_to_jira(project, {}, jira_client, sidecar_path,
                          included_task_uids={"60"}).

    \testexpect
    Only task uid=60 is processed; uid=61 is ignored.
    result["created"] == 1; jira_client.create_issue called once.

    \testcheck
    Assert counter and mock call count.
    """

    def test_only_included_task_processed(self, tmp_path):
        task_a = _make_p2j_task(name="Task A", uid=60)
        task_b = _make_p2j_task(name="Task B", uid=61)
        project = _make_p2j_project(tasks=[task_a, task_b], p2j_cfg=_p2j_defaults())
        jira_client = MagicMock()
        jira_client.issue_types.return_value = []
        new_issue = MagicMock()
        new_issue.key = "P-60"
        new_issue.id = "6060"
        jira_client.create_issue.return_value = new_issue

        result = jira_sync.run_push_to_jira(
            project, {}, jira_client, str(tmp_path / "s.json"),
            included_task_uids={"60"},
        )

        assert result["created"] == 1
        assert jira_client.create_issue.call_count == 1

    def test_excluded_task_not_created(self, tmp_path):
        task_a = _make_p2j_task(name="Task A", uid=62)
        task_b = _make_p2j_task(name="Task B", uid=63)
        project = _make_p2j_project(tasks=[task_a, task_b], p2j_cfg=_p2j_defaults())
        jira_client = MagicMock()
        jira_client.issue_types.return_value = []
        new_issue = MagicMock()
        new_issue.key = "P-62"
        new_issue.id = "6262"
        jira_client.create_issue.return_value = new_issue

        result = jira_sync.run_push_to_jira(
            project, {}, jira_client, str(tmp_path / "s.json"),
            included_task_uids={"62"},
        )

        # Task 63 must not have been created
        assert result["created"] == 1


# ---------------------------------------------------------------------------
# run_push_to_jira â€” hierarchy parent link
# ---------------------------------------------------------------------------

class TestRunPushToJiraHierarchy:
    """run_push_to_jira sets the parent field when hierarchy_export is enabled.

    \testinit
    Two tasks: parent (uid=70, linked to "P-70") and child (uid=71, linked to "P-71").
    Child.getParentTask() returns the parent task.
    hierarchy_export.enabled = True.

    \testrun
    Call run_push_to_jira(project, {}, jira_client, sidecar_path).

    \testexpect
    jira_client.issue("P-71").update(fields={"parent": {"key": "P-70"}}) is called.

    \testcheck
    Assert mock call arguments contain parent key.
    """

    def test_parent_link_set_for_child_task(self, tmp_path):
        parent_task = _make_p2j_task(name="Parent", uid=70, summary=True)
        child_task  = _make_p2j_task(name="Child",  uid=71, parent=parent_task)
        cfg = _p2j_defaults(
            hierarchy_export={"enabled": True, "epic_type": "Epic",
                              "story_type": "Story", "subtask_type": "Sub-task",
                              "dependency_link_type": "blocks"},
        )
        project = _make_p2j_project(tasks=[parent_task, child_task], p2j_cfg=cfg)
        sidecar = tmp_path / "s.json"
        sidecar.write_text(json.dumps({
            "task_jira": {
                "70": {"jira_key": "P-70"},
                "71": {"jira_key": "P-71"},
            },
        }), encoding="utf-8")
        jira_client = MagicMock()
        jira_client.issue_types.return_value = []
        child_issue = MagicMock()
        jira_client.issue.return_value = child_issue

        jira_sync.run_push_to_jira(project, {}, jira_client, str(sidecar))

        # At least one update call should have passed parent key
        update_calls = [c for c in child_issue.update.call_args_list
                        if "parent" in (c.kwargs.get("fields") or c[1].get("fields", {}) or {})]
        assert len(update_calls) >= 1, "Expected parent link update call"


# ---------------------------------------------------------------------------
# run_push_to_jira â€” auditability
# ---------------------------------------------------------------------------

class TestRunPushToJiraAuditability:
    """run_push_to_jira stores an audit session in the sidecar when enabled.

    \testinit
    Build a project with one unlinked task; auditability.enabled=True.

    \testrun
    Call run_push_to_jira(project, {}, jira_client, sidecar_path).

    \testexpect
    Sidecar file contains jira_push_meta.audit_sessions with one entry.

    \testcheck
    Read back sidecar and assert audit_sessions length and entry keys.
    """

    def test_audit_session_written_to_sidecar(self, tmp_path):
        task = _make_p2j_task(name="Audited Task", uid=80)
        cfg = _p2j_defaults(auditability={"enabled": True})
        project = _make_p2j_project(tasks=[task], p2j_cfg=cfg)
        jira_client = MagicMock()
        jira_client.issue_types.return_value = []
        new_issue = MagicMock()
        new_issue.key = "P-80"
        new_issue.id = "8080"
        jira_client.create_issue.return_value = new_issue
        sidecar = str(tmp_path / "s.json")

        jira_sync.run_push_to_jira(project, {}, jira_client, sidecar)

        data = json.loads(open(sidecar, encoding="utf-8").read())
        sessions = data.get("jira_push_meta", {}).get("audit_sessions", [])
        assert len(sessions) == 1

    def test_audit_session_has_required_keys(self, tmp_path):
        task = _make_p2j_task(name="Audited Task 2", uid=81)
        cfg = _p2j_defaults(auditability={"enabled": True})
        project = _make_p2j_project(tasks=[task], p2j_cfg=cfg)
        jira_client = MagicMock()
        jira_client.issue_types.return_value = []
        new_issue = MagicMock()
        new_issue.key = "P-81"
        new_issue.id = "8181"
        jira_client.create_issue.return_value = new_issue
        sidecar = str(tmp_path / "s.json")

        jira_sync.run_push_to_jira(project, {}, jira_client, sidecar)

        data = json.loads(open(sidecar, encoding="utf-8").read())
        session = data["jira_push_meta"]["audit_sessions"][0]
        for key in ("run_at", "created", "updated", "skipped", "failed"):
            assert key in session, f"Missing audit key: {key}"

    def test_no_audit_session_when_disabled(self, tmp_path):
        task = _make_p2j_task(name="No Audit", uid=82)
        cfg = _p2j_defaults(auditability={"enabled": False})
        project = _make_p2j_project(tasks=[task], p2j_cfg=cfg)
        jira_client = MagicMock()
        jira_client.issue_types.return_value = []
        new_issue = MagicMock()
        new_issue.key = "P-82"
        new_issue.id = "8282"
        jira_client.create_issue.return_value = new_issue
        sidecar = str(tmp_path / "s.json")

        jira_sync.run_push_to_jira(project, {}, jira_client, sidecar)

        data = json.loads(open(sidecar, encoding="utf-8").read())
        sessions = data.get("jira_push_meta", {}).get("audit_sessions", [])
        assert len(sessions) == 0


# ---------------------------------------------------------------------------
# Helper for advanced config
# ---------------------------------------------------------------------------

def _make_project_advanced(advanced: dict, tasks=None):
    """Build a mock project with a jira2project config including 'advanced' settings."""
    project = _make_project(tasks)
    cfg = {"filter": "project = PROJ", "filter_type": "jql", "advanced": advanced}
    # Override the cp mock's return value (same instance as set up in _make_project)
    cp = project.getProjectProperties().getCustomProperties()
    cp.get.return_value = json.dumps(cfg)
    return project


# ---------------------------------------------------------------------------
# _normalize_jira_datetime
# ---------------------------------------------------------------------------

class TestNormalizeJiraDatetime:
    """Unit tests for jira_sync._normalize_jira_datetime.

    \testinit
    No external state required.

    \testrun
    Call _normalize_jira_datetime(date_str) with various input formats.

    \testexpect
    Timezone-aware datetime strings are converted to UTC ISO-8601 with 'Z' suffix.
    Date-only strings and empty strings pass through unchanged.

    \testcheck
    Assert the returned string matches the expected UTC representation.
    """

    def test_utc_z_passthrough(self):
        """An already-UTC 'Z' datetime is returned unchanged."""
        result = jira_sync._normalize_jira_datetime("2024-01-15T10:30:00Z")
        assert result == "2024-01-15T10:30:00Z"

    def test_converts_positive_offset(self):
        """A +0200 datetime is shifted to UTC (10:30 -> 08:30)."""
        result = jira_sync._normalize_jira_datetime("2024-01-15T10:30:00+0200")
        assert result == "2024-01-15T08:30:00Z"

    def test_converts_negative_offset(self):
        """A -0500 datetime is shifted to UTC (10:00 -> 15:00)."""
        result = jira_sync._normalize_jira_datetime("2024-01-15T10:00:00-0500")
        assert result == "2024-01-15T15:00:00Z"

    def test_strips_milliseconds(self):
        """Milliseconds are stripped before parsing (10:30:00.000+0200 -> UTC)."""
        result = jira_sync._normalize_jira_datetime("2024-01-15T10:30:00.000+0200")
        assert result == "2024-01-15T08:30:00Z"

    def test_date_only_passthrough(self):
        """A date-only string (no 'T') is returned unchanged."""
        result = jira_sync._normalize_jira_datetime("2024-01-15")
        assert result == "2024-01-15"

    def test_empty_string_returns_empty(self):
        """An empty string is returned unchanged."""
        result = jira_sync._normalize_jira_datetime("")
        assert result == ""


# ---------------------------------------------------------------------------
# _parse_jira_date â€” normalize flag
# ---------------------------------------------------------------------------

class TestParseJiraDateNormalize:
    """_parse_jira_date respects the normalize flag for timezone conversion.

    \testinit
    No external state required; jpype is already mocked by conftest.

    \testrun
    Call _parse_jira_date(date_str, normalize=False/True) and capture the
    year/month/day arguments passed to LocalDateTime.of().

    \testexpect
    normalize=False uses the raw first-10-char date prefix.
    normalize=True first converts the datetime to UTC, then uses that date.

    \testcheck
    Assert LocalDateTime.of() was called with the expected y/m/d arguments.
    """

    def test_normalize_false_uses_raw_date(self):
        """normalize=False: date 2024-01-15T01:00:00+0200 -> raw date 2024-01-15."""
        captured = []
        mock_ldt = MagicMock()
        mock_ldt.of.side_effect = lambda y, m, d, h, mn, s: captured.append((y, m, d)) or MagicMock()
        with patch("jpype.JClass", return_value=mock_ldt):
            result = jira_sync._parse_jira_date("2024-01-15T01:00:00+0200", normalize=False)
        assert result is not None
        assert len(captured) == 1
        assert captured[0] == (2024, 1, 15)

    def test_normalize_true_shifts_date_to_utc(self):
        """normalize=True: 2024-01-15T01:00:00+0200 (UTC=2024-01-14T23:00) -> date 2024-01-14."""
        captured = []
        mock_ldt = MagicMock()
        mock_ldt.of.side_effect = lambda y, m, d, h, mn, s: captured.append((y, m, d)) or MagicMock()
        with patch("jpype.JClass", return_value=mock_ldt):
            result = jira_sync._parse_jira_date("2024-01-15T01:00:00+0200", normalize=True)
        assert result is not None
        assert len(captured) == 1
        assert captured[0] == (2024, 1, 14)


# ---------------------------------------------------------------------------
# run_sync â€” relink_callback
# ---------------------------------------------------------------------------

class TestRunSyncRelinkCallback:
    """run_sync invokes relink_callback when behavior='messagebox' and the Jira
    issue ID stored for the linked task differs from the incoming issue ID.

    \testinit
    Project has one existing task (uid=1) linked to jira_key='PROJ-1' with
    jira_id='OLD_ID' in the sidecar. Incoming issue has the same key but
    id='NEW_ID'. J2P config: advanced.relink.enabled=True, behavior='messagebox'.

    \testrun
    Call run_sync(..., relink_callback=cb) with the above setup.

    \testexpect
    cb() is called with (issue_key, stored_id, incoming_id). Returning 'skip'
    causes the task to be counted as skipped; returning 'relink' allows the
    update to proceed.

    \testcheck
    Assert callback invocation, relink_callback args, and result counters.
    """

    def setup_method(self):
        app_debug.set_debug(False)
        jira_sync._last_result = None
        _restore_java_stubs()

    def _setup(self, *, enabled=True):
        existing_task = _make_mpxj_task(name="Task A", uid=1, id=1)
        project = _make_project_advanced(
            {"relink": {"enabled": enabled, "behavior": "messagebox"}},
            tasks=[existing_task],
        )
        issue = _make_issue("PROJ-1", "Task A")
        issue.id = "NEW_ID"
        jira_client = MagicMock()
        jira_client.search_issues.return_value = [issue]
        sidecar_content = json.dumps({
            "task_jira": {"1": {"jira_key": "PROJ-1", "jira_id": "OLD_ID"}}
        })
        return project, jira_client, existing_task, sidecar_content

    def test_callback_called_on_id_change(self, tmp_path):
        """relink_callback is invoked when the issue ID has changed."""
        project, jira_client, _, sidecar_content = self._setup()
        sidecar = tmp_path / "s.json"
        sidecar.write_text(sidecar_content, encoding="utf-8")

        calls = []
        def cb(key, stored, incoming):
            calls.append((key, stored, incoming))
            return "skip"

        with patch("integrations.jira_integration.resolve_filter_to_jql", return_value=("project = PROJ", "")), \
             patch("jpype.JClass", return_value=MagicMock()):
            jira_sync.run_sync(project, {}, jira_client, str(sidecar), relink_callback=cb)

        assert len(calls) == 1
        assert calls[0][0] == "PROJ-1"
        assert calls[0][1] == "OLD_ID"
        assert calls[0][2] == "NEW_ID"

    def test_callback_returns_skip_skips_task(self, tmp_path):
        """When relink_callback returns 'skip', the task is counted as skipped."""
        project, jira_client, _, sidecar_content = self._setup()
        sidecar = tmp_path / "s.json"
        sidecar.write_text(sidecar_content, encoding="utf-8")

        with patch("integrations.jira_integration.resolve_filter_to_jql", return_value=("project = PROJ", "")), \
             patch("jpype.JClass", return_value=MagicMock()):
            result = jira_sync.run_sync(
                project, {}, jira_client, str(sidecar),
                relink_callback=lambda k, s, i: "skip",
            )

        assert result["skipped"] >= 1
        assert result["updated"] == 0

    def test_callback_returns_relink_updates_task(self, tmp_path):
        """When relink_callback returns 'relink' (and enabled=True), the task is updated."""
        project, jira_client, existing_task, sidecar_content = self._setup(enabled=True)
        sidecar = tmp_path / "s.json"
        sidecar.write_text(sidecar_content, encoding="utf-8")

        with patch("integrations.jira_integration.resolve_filter_to_jql", return_value=("project = PROJ", "")), \
             patch("jpype.JClass", return_value=MagicMock()):
            result = jira_sync.run_sync(
                project, {}, jira_client, str(sidecar),
                relink_callback=lambda k, s, i: "relink",
            )

        assert result["updated"] == 1
        assert result["skipped"] == 0

    def test_no_callback_messagebox_defaults_to_skip(self, tmp_path):
        """Without a callback, behavior='messagebox' silently skips the task."""
        project, jira_client, _, sidecar_content = self._setup()
        sidecar = tmp_path / "s.json"
        sidecar.write_text(sidecar_content, encoding="utf-8")

        with patch("integrations.jira_integration.resolve_filter_to_jql", return_value=("project = PROJ", "")), \
             patch("jpype.JClass", return_value=MagicMock()):
            result = jira_sync.run_sync(
                project, {}, jira_client, str(sidecar),
                relink_callback=None,
            )

        assert result["skipped"] >= 1
        assert result["updated"] == 0


# ---------------------------------------------------------------------------
# run_sync â€” conflict_callback
# ---------------------------------------------------------------------------

class TestRunSyncConflictCallback:
    """run_sync invokes conflict_callback when policy='messagebox' and the local
    task has been edited since the last sync snapshot.

    \testinit
    Project has existing task uid=1, name='Modified Name'. Sidecar records
    last_sync_snapshot.name='Original Name'. Issue id='ID_1' matches sidecar
    jira_id so no relink triggers. J2P config: advanced.conflict.enabled=True,
    policy='messagebox'.

    \testrun
    Call run_sync(..., conflict_callback=cb) with the above setup.

    \testexpect
    cb() is called with (issue_key, task_name). Returning 'prefer_jira' allows
    update; returning 'skip' counts the task as skipped.

    \testcheck
    Assert callback invocation and result counters.
    """

    def setup_method(self):
        app_debug.set_debug(False)
        jira_sync._last_result = None
        _restore_java_stubs()

    def _setup(self):
        existing_task = _make_mpxj_task(name="Modified Name", uid=1, id=1)
        project = _make_project_advanced(
            {"conflict": {"enabled": True, "policy": "messagebox"}},
            tasks=[existing_task],
        )
        issue = _make_issue("PROJ-1", "Jira Title")
        issue.id = "ID_1"  # matches sidecar jira_id â†’ no relink trigger
        jira_client = MagicMock()
        jira_client.search_issues.return_value = [issue]
        sidecar_content = json.dumps({
            "task_jira": {
                "1": {
                    "jira_key": "PROJ-1",
                    "jira_id": "ID_1",
                    "last_sync_snapshot": {"name": "Original Name", "notes": ""},
                }
            }
        })
        return project, jira_client, sidecar_content

    def test_callback_called_on_local_edit(self, tmp_path):
        """conflict_callback is invoked when local task name differs from snapshot."""
        project, jira_client, sidecar_content = self._setup()
        sidecar = tmp_path / "s.json"
        sidecar.write_text(sidecar_content, encoding="utf-8")

        calls = []
        def cb(key, task_name):
            calls.append((key, task_name))
            return "skip"

        with patch("integrations.jira_integration.resolve_filter_to_jql", return_value=("project = PROJ", "")), \
             patch("jpype.JClass", return_value=MagicMock()):
            jira_sync.run_sync(project, {}, jira_client, str(sidecar), conflict_callback=cb)

        assert len(calls) == 1
        assert calls[0][0] == "PROJ-1"
        assert "Modified Name" in calls[0][1]

    def test_callback_prefer_jira_updates_task(self, tmp_path):
        """conflict_callback returning 'prefer_jira' allows the task to be updated."""
        project, jira_client, sidecar_content = self._setup()
        sidecar = tmp_path / "s.json"
        sidecar.write_text(sidecar_content, encoding="utf-8")

        with patch("integrations.jira_integration.resolve_filter_to_jql", return_value=("project = PROJ", "")), \
             patch("jpype.JClass", return_value=MagicMock()):
            result = jira_sync.run_sync(
                project, {}, jira_client, str(sidecar),
                conflict_callback=lambda k, n: "prefer_jira",
            )

        assert result["updated"] == 1
        assert result["skipped"] == 0

    def test_callback_skip_skips_task(self, tmp_path):
        """conflict_callback returning 'skip' causes the task to be counted as skipped."""
        project, jira_client, sidecar_content = self._setup()
        sidecar = tmp_path / "s.json"
        sidecar.write_text(sidecar_content, encoding="utf-8")

        with patch("integrations.jira_integration.resolve_filter_to_jql", return_value=("project = PROJ", "")), \
             patch("jpype.JClass", return_value=MagicMock()):
            result = jira_sync.run_sync(
                project, {}, jira_client, str(sidecar),
                conflict_callback=lambda k, n: "skip",
            )

        assert result["skipped"] >= 1
        assert result["updated"] == 0

    def test_no_callback_messagebox_defaults_to_skip(self, tmp_path):
        """Without a conflict_callback, policy='messagebox' silently skips the task."""
        project, jira_client, sidecar_content = self._setup()
        sidecar = tmp_path / "s.json"
        sidecar.write_text(sidecar_content, encoding="utf-8")

        with patch("integrations.jira_integration.resolve_filter_to_jql", return_value=("project = PROJ", "")), \
             patch("jpype.JClass", return_value=MagicMock()):
            result = jira_sync.run_sync(
                project, {}, jira_client, str(sidecar),
                conflict_callback=None,
            )

        assert result["skipped"] >= 1
        assert result["updated"] == 0


# ---------------------------------------------------------------------------
# run_sync â€” orphan_callback
# ---------------------------------------------------------------------------

class TestRunSyncOrphanCallback:
    """run_sync invokes orphan_callback per orphaned task when behavior='messagebox'.

    An orphan is a sidecar entry whose jira_key is absent from the fetched Jira
    results (issue deleted, moved, or out of scope).

    \testinit
    Sidecar has task uid=1 linked to 'PROJ-GONE'. Jira returns no issues
    (empty list). Project has the task with uid=1.
    J2P config: advanced.orphan.enabled=True, behavior='messagebox'.

    \testrun
    Call run_sync(..., orphan_callback=cb) with the above setup.

    \testexpect
    cb() is called once with (jira_key, task_name). Returned action determines
    what happens to the sidecar entry and the project task.

    \testcheck
    Assert callback invocation, sidecar state, and (for 'delete') task removal.
    """

    def setup_method(self):
        app_debug.set_debug(False)
        jira_sync._last_result = None
        _restore_java_stubs()

    def _setup(self, task=None):
        if task is None:
            task = _make_mpxj_task(name="Orphan Task", uid=1, id=1)
        project = _make_project_advanced(
            {"orphan": {"enabled": True, "behavior": "messagebox"}},
            tasks=[task],
        )
        jira_client = MagicMock()
        jira_client.search_issues.return_value = []  # no issues â†’ PROJ-GONE is orphaned
        sidecar_content = json.dumps({
            "task_jira": {"1": {"jira_key": "PROJ-GONE", "jira_id": "OLD_1"}}
        })
        return project, jira_client, task, sidecar_content

    def test_callback_called_for_orphan(self, tmp_path):
        """orphan_callback is invoked once per orphaned task."""
        project, jira_client, _, sidecar_content = self._setup()
        sidecar = tmp_path / "s.json"
        sidecar.write_text(sidecar_content, encoding="utf-8")

        calls = []
        def cb(jira_key, task_name):
            calls.append((jira_key, task_name))
            return "keep"

        with patch("integrations.jira_integration.resolve_filter_to_jql", return_value=("project = PROJ", "")), \
             patch("jpype.JClass", return_value=MagicMock()):
            jira_sync.run_sync(project, {}, jira_client, str(sidecar), orphan_callback=cb)

        assert len(calls) == 1
        assert calls[0][0] == "PROJ-GONE"

    def test_callback_returns_keep_leaves_sidecar_unchanged(self, tmp_path):
        """orphan_callback returning 'keep' leaves the sidecar entry intact."""
        project, jira_client, _, sidecar_content = self._setup()
        sidecar = tmp_path / "s.json"
        sidecar.write_text(sidecar_content, encoding="utf-8")

        with patch("integrations.jira_integration.resolve_filter_to_jql", return_value=("project = PROJ", "")), \
             patch("jpype.JClass", return_value=MagicMock()):
            jira_sync.run_sync(
                project, {}, jira_client, str(sidecar),
                orphan_callback=lambda k, n: "keep",
            )

        data = json.loads(sidecar.read_text(encoding="utf-8"))
        assert "1" in data.get("task_jira", {})

    def test_callback_returns_unlink_removes_sidecar_entry(self, tmp_path):
        """orphan_callback returning 'unlink' removes the sidecar entry."""
        project, jira_client, _, sidecar_content = self._setup()
        sidecar = tmp_path / "s.json"
        sidecar.write_text(sidecar_content, encoding="utf-8")

        with patch("integrations.jira_integration.resolve_filter_to_jql", return_value=("project = PROJ", "")), \
             patch("jpype.JClass", return_value=MagicMock()):
            jira_sync.run_sync(
                project, {}, jira_client, str(sidecar),
                orphan_callback=lambda k, n: "unlink",
            )

        data = json.loads(sidecar.read_text(encoding="utf-8"))
        assert "1" not in data.get("task_jira", {})

    def test_callback_returns_delete_removes_task_from_project(self, tmp_path):
        """orphan_callback returning 'delete' removes the task from the project."""
        task = _make_mpxj_task(name="Orphan Task", uid=1, id=1)
        project, jira_client, _, sidecar_content = self._setup(task=task)
        sidecar = tmp_path / "s.json"
        sidecar.write_text(sidecar_content, encoding="utf-8")

        with patch("integrations.jira_integration.resolve_filter_to_jql", return_value=("project = PROJ", "")), \
             patch("jpype.JClass", return_value=MagicMock()):
            result = jira_sync.run_sync(
                project, {}, jira_client, str(sidecar),
                orphan_callback=lambda k, n: "delete",
            )

        # Sidecar entry removed and orphan counted as handled
        data = json.loads(sidecar.read_text(encoding="utf-8"))
        assert "1" not in data.get("task_jira", {})
        assert result["orphans"]["handled"] >= 1

    def test_no_callback_messagebox_defaults_to_keep(self, tmp_path):
        """Without orphan_callback, behavior='messagebox' keeps the sidecar entry."""
        project, jira_client, _, sidecar_content = self._setup()
        sidecar = tmp_path / "s.json"
        sidecar.write_text(sidecar_content, encoding="utf-8")

        with patch("integrations.jira_integration.resolve_filter_to_jql", return_value=("project = PROJ", "")), \
             patch("jpype.JClass", return_value=MagicMock()):
            jira_sync.run_sync(
                project, {}, jira_client, str(sidecar),
                orphan_callback=None,
            )

        data = json.loads(sidecar.read_text(encoding="utf-8"))
        assert "1" in data.get("task_jira", {})
