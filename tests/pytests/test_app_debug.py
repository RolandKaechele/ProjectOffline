"""Tests for app_debug.py — Debug flag, build version, and dump helpers."""

import json
import sys
import os
from unittest.mock import MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

import app_debug


class TestSetDebug:
    def test_set_debug_true(self):
        app_debug.set_debug(True)
        assert app_debug.is_debug() is True

    def test_set_debug_false(self):
        app_debug.set_debug(False)
        assert app_debug.is_debug() is False

    def test_set_debug_toggles(self):
        app_debug.set_debug(True)
        assert app_debug.is_debug() is True
        app_debug.set_debug(False)
        assert app_debug.is_debug() is False
        app_debug.set_debug(True)
        assert app_debug.is_debug() is True


class TestIsDebug:
    def test_initial_state_is_false(self):
        # Reset to default state
        app_debug.set_debug(False)
        assert app_debug.is_debug() is False

    def test_persists_after_multiple_calls(self):
        app_debug.set_debug(True)
        assert app_debug.is_debug() is True
        assert app_debug.is_debug() is True
        assert app_debug.is_debug() is True


class TestBuildVersion:
    def test_build_version_is_exported(self):
        assert hasattr(app_debug, '_BUILD_VERSION')

    def test_build_version_is_string(self):
        assert isinstance(app_debug._BUILD_VERSION, str)

    def test_build_version_is_non_empty(self):
        assert app_debug._BUILD_VERSION != ""


class TestDumpProjectState:

    def _make_project(self):
        """Return a minimal MagicMock shaped like an MPXJ ProjectFile."""
        project = MagicMock()
        props = MagicMock()
        props.getName.return_value = "Test Project"
        props.getStartDate.return_value = None
        props.getFinishDate.return_value = None
        props.getAuthor.return_value = None
        props.getCompany.return_value = None
        props.getStatusDate.return_value = None
        props.getCurrencySymbol.return_value = None
        project.getProjectProperties.return_value = props
        project.getCustomFields.return_value = []
        project.getTasks.return_value = []
        project.getResources.return_value = []
        project.getDefaultCalendar.return_value = None
        return project

    def test_returns_empty_string_for_none_project(self):
        assert app_debug.dump_project_state(None) == ""

    def test_returns_file_path(self, tmp_path, monkeypatch):
        monkeypatch.setattr(app_debug, '__file__', str(tmp_path / 'app_debug.py'))
        result = app_debug.dump_project_state(self._make_project())
        assert os.path.isfile(result)

    def test_output_in_dump_subdirectory(self, tmp_path, monkeypatch):
        monkeypatch.setattr(app_debug, '__file__', str(tmp_path / 'app_debug.py'))
        result = app_debug.dump_project_state(self._make_project())
        assert os.path.basename(os.path.dirname(result)) == "dump"

    def test_dump_directory_is_created(self, tmp_path, monkeypatch):
        monkeypatch.setattr(app_debug, '__file__', str(tmp_path / 'app_debug.py'))
        dump_dir = tmp_path / "dump"
        assert not dump_dir.exists()
        app_debug.dump_project_state(self._make_project())
        assert dump_dir.is_dir()

    def test_json_build_version_is_first_key(self, tmp_path, monkeypatch):
        monkeypatch.setattr(app_debug, '__file__', str(tmp_path / 'app_debug.py'))
        result = app_debug.dump_project_state(self._make_project())
        with open(result, encoding='utf-8') as fh:
            data = json.load(fh)
        assert list(data.keys())[0] == 'build_version'

    def test_json_build_version_matches_module(self, tmp_path, monkeypatch):
        monkeypatch.setattr(app_debug, '__file__', str(tmp_path / 'app_debug.py'))
        result = app_debug.dump_project_state(self._make_project())
        with open(result, encoding='utf-8') as fh:
            data = json.load(fh)
        assert data['build_version'] == app_debug._BUILD_VERSION

    def test_json_contains_dump_timestamp(self, tmp_path, monkeypatch):
        monkeypatch.setattr(app_debug, '__file__', str(tmp_path / 'app_debug.py'))
        result = app_debug.dump_project_state(self._make_project())
        with open(result, encoding='utf-8') as fh:
            data = json.load(fh)
        assert 'dump_timestamp' in data
        assert isinstance(data['dump_timestamp'], str)

    def test_json_contains_project_block(self, tmp_path, monkeypatch):
        monkeypatch.setattr(app_debug, '__file__', str(tmp_path / 'app_debug.py'))
        result = app_debug.dump_project_state(self._make_project())
        with open(result, encoding='utf-8') as fh:
            data = json.load(fh)
        assert 'project' in data
        assert isinstance(data['project'], dict)

    def test_json_filename_contains_timestamp(self, tmp_path, monkeypatch):
        monkeypatch.setattr(app_debug, '__file__', str(tmp_path / 'app_debug.py'))
        result = app_debug.dump_project_state(self._make_project())
        assert os.path.basename(result).startswith('debug_project_dump_')
        assert result.endswith('.json')

    def test_bundled_dump_next_to_executable(self, tmp_path, monkeypatch):
        """In a PyInstaller bundle (sys.frozen=True) the dump lands next to the exe."""
        import app_debug as _ad
        exe_path = tmp_path / 'ProjectOffline.exe'
        monkeypatch.setattr(_ad.sys, 'frozen', True, raising=False)
        monkeypatch.setattr(_ad.sys, 'executable', str(exe_path))
        result = _ad.dump_project_state(self._make_project())
        assert os.path.dirname(os.path.dirname(result)) == str(tmp_path)
        assert os.path.basename(os.path.dirname(result)) == 'dump'

    def test_json_contains_confluence_calendar_props_block(self, tmp_path, monkeypatch):
        """dump_project_state() always writes a 'confluence_calendar_props' key."""
        monkeypatch.setattr(app_debug, '__file__', str(tmp_path / 'app_debug.py'))
        result = app_debug.dump_project_state(self._make_project())
        with open(result, encoding='utf-8') as fh:
            data = json.load(fh)
        assert 'confluence_calendar_props' in data

    def test_json_confluence_calendar_props_empty_for_mock_project(self, tmp_path, monkeypatch):
        """confluence_calendar_props is an empty dict when CALENDAR fields are absent."""
        monkeypatch.setattr(app_debug, '__file__', str(tmp_path / 'app_debug.py'))
        result = app_debug.dump_project_state(self._make_project())
        with open(result, encoding='utf-8') as fh:
            data = json.load(fh)
        # The block may be empty (no real MPXJ project), but must be a dict
        assert isinstance(data['confluence_calendar_props'], dict)

    def test_json_contains_jira_project_props_block(self, tmp_path, monkeypatch):
        """dump_project_state() always writes a 'jira_project_props' key."""
        monkeypatch.setattr(app_debug, '__file__', str(tmp_path / 'app_debug.py'))
        result = app_debug.dump_project_state(self._make_project())
        with open(result, encoding='utf-8') as fh:
            data = json.load(fh)
        assert 'jira_project_props' in data

    def test_json_jira_project_props_empty_for_mock_project(self, tmp_path, monkeypatch):
        """jira_project_props is an empty dict when JIRA fields are absent."""
        monkeypatch.setattr(app_debug, '__file__', str(tmp_path / 'app_debug.py'))
        result = app_debug.dump_project_state(self._make_project())
        with open(result, encoding='utf-8') as fh:
            data = json.load(fh)
        # The block may be empty (no real MPXJ project), but must be a dict
        assert isinstance(data['jira_project_props'], dict)

    def test_json_jira_project_props_contains_field_checkboxes(self, tmp_path, monkeypatch):
        """jira_project_props contains field_checkboxes dict when jira2project container is set."""
        monkeypatch.setattr(app_debug, '__file__', str(tmp_path / 'app_debug.py'))

        project = self._make_project()
        mock_cp = MagicMock()
        mock_cp.get.side_effect = lambda k: {
            "jira2project": json.dumps({
                "fields": {"jira_status": True, "jira_assignee": False, "jira_priority": True}
            }),
        }.get(k)
        mock_cp.keySet.return_value = []
        project.getProjectProperties.return_value.getCustomProperties.return_value = mock_cp

        result = app_debug.dump_project_state(project)
        with open(result, encoding='utf-8') as fh:
            data = json.load(fh)

        assert 'field_checkboxes' in data['jira_project_props']
        assert isinstance(data['jira_project_props']['field_checkboxes'], dict)

    def test_json_jira_field_checkboxes_parses_true_false_strings(self, tmp_path, monkeypatch):
        """Field checkbox boolean values are correctly extracted from jira2project container."""
        monkeypatch.setattr(app_debug, '__file__', str(tmp_path / 'app_debug.py'))

        project = self._make_project()
        mock_cp = MagicMock()
        mock_cp.get.side_effect = lambda k: {
            "jira2project": json.dumps({
                "fields": {
                    "jira_status": True,
                    "jira_assignee": False,
                    "jira_priority": True,
                    # jira_description absent (tests None/unset case)
                }
            }),
        }.get(k)
        mock_cp.keySet.return_value = []
        project.getProjectProperties.return_value.getCustomProperties.return_value = mock_cp

        result = app_debug.dump_project_state(project)
        with open(result, encoding='utf-8') as fh:
            data = json.load(fh)

        checkboxes = data['jira_project_props']['field_checkboxes']
        assert checkboxes['jira_status'] is True
        assert checkboxes['jira_priority'] is True
        assert checkboxes['jira_assignee'] is False
        # absent field defaults to False
        assert checkboxes['jira_description'] is False

    def test_json_jira_field_checkboxes_contains_all_36_fields(self, tmp_path, monkeypatch):
        """Field checkboxes dict contains all 36 expected field names."""
        monkeypatch.setattr(app_debug, '__file__', str(tmp_path / 'app_debug.py'))
        
        project = self._make_project()
        mock_cp = MagicMock()
        mock_cp.get.return_value = None  # All fields unset
        mock_cp.keySet.return_value = []
        project.getProjectProperties.return_value.getCustomProperties.return_value = mock_cp
        
        result = app_debug.dump_project_state(project)
        with open(result, encoding='utf-8') as fh:
            data = json.load(fh)
        
        checkboxes = data['jira_project_props']['field_checkboxes']
        # Verify all 36 field names are present
        expected_fields = [
            "jira_project_name", "jira_description",
            "jira_status", "jira_status_percent", "jira_resolution", "jira_resolution_date", "jira_security_level",
            "jira_assignee", "jira_assignee_display_name", "jira_reporter", "jira_reporter_display_name",
            "jira_priority", "jira_due_date", "jira_created_date", "jira_updated_date",
            "jira_components", "jira_fix_versions", "jira_affects_versions",
            "jira_fix_version_description", "jira_fix_version_released", "jira_fix_version_start_date", "jira_fix_version_release_date",
            "jira_labels", "jira_environment", "jira_votes", "jira_comments",
            "jira_time_spent", "jira_remaining_estimate", "jira_original_estimate", "jira_time_spent_seconds", "jira_worklog_entries",
            "jira_parent_key", "jira_epic_link", "jira_parent_link", "jira_subtask_parent", "jira_issue_links",
        ]
        assert len(checkboxes) == 36
        for field_name in expected_fields:
            assert field_name in checkboxes

    def test_json_jira_field_checkboxes_all_false_by_default(self, tmp_path, monkeypatch):
        """All field checkboxes default to False when not explicitly set in project."""
        monkeypatch.setattr(app_debug, '__file__', str(tmp_path / 'app_debug.py'))
        
        project = self._make_project()
        mock_cp = MagicMock()
        mock_cp.get.return_value = None  # All fields unset
        mock_cp.keySet.return_value = []
        project.getProjectProperties.return_value.getCustomProperties.return_value = mock_cp
        
        result = app_debug.dump_project_state(project)
        with open(result, encoding='utf-8') as fh:
            data = json.load(fh)
        
        checkboxes = data['jira_project_props']['field_checkboxes']
        # All fields should default to False
        for field_name, enabled in checkboxes.items():
            assert enabled is False, f"Field {field_name} should default to False"

    def test_json_jira_project_props_includes_filter_and_filter_type(self, tmp_path, monkeypatch):
        """jira_project_props includes filter and filter_type from the jira2project container."""
        monkeypatch.setattr(app_debug, '__file__', str(tmp_path / 'app_debug.py'))

        project = self._make_project()
        mock_cp = MagicMock()
        mock_cp.get.side_effect = lambda k: {
            "jira2project": json.dumps({
                "filter": "project = MYPROJ",
                "filter_type": "jql",
            }),
        }.get(k)
        mock_cp.keySet.return_value = []
        project.getProjectProperties.return_value.getCustomProperties.return_value = mock_cp

        result = app_debug.dump_project_state(project)
        with open(result, encoding='utf-8') as fh:
            data = json.load(fh)

        jira_props = data['jira_project_props']
        assert jira_props['filter'] == "project = MYPROJ"
        assert jira_props['filter_type'] == "jql"
        assert jira_props['filter_set'] is True

    def test_json_project_to_jira_props_contains_export_settings(self, tmp_path, monkeypatch):
        """dump_project_state() writes a dedicated Project -> Jira config block."""
        monkeypatch.setattr(app_debug, '__file__', str(tmp_path / 'app_debug.py'))

        project = self._make_project()
        mock_cp = MagicMock()
        mock_cp.get.side_effect = lambda k: {
            "project2jira": json.dumps({
                "export_scope": "full_project",
                "create_update_mode": "create_only",
                "conflict_policy": "prefer_jira",
                "dry_run": False,
                "fields": {
                    "jira_status": {"enabled": True, "jira_field": "status"},
                },
                "issue_type_map": {"Task": "Task"},
                "transition_map": {"Done": "31"},
            }),
        }.get(k)
        mock_cp.keySet.return_value = []
        project.getProjectProperties.return_value.getCustomProperties.return_value = mock_cp

        result = app_debug.dump_project_state(project)
        with open(result, encoding='utf-8') as fh:
            data = json.load(fh)

        props = data['jira_project_to_jira_props']
        assert props['export_scope'] == 'full_project'
        assert props['create_update_mode'] == 'create_only'
        assert props['conflict_policy'] == 'prefer_jira'
        assert props['dry_run'] is False
        assert props['fields']['jira_status']['enabled'] is True
        assert props['fields']['jira_status']['jira_field'] == 'status'
        assert props['issue_type_map'] == {'Task': 'Task'}
        assert props['transition_map'] == {'Done': '31'}

    def test_json_project_to_jira_props_redacts_sensitive_keys(self, tmp_path, monkeypatch):
        """Sensitive-looking keys inside Project -> Jira config are redacted in the dump."""
        monkeypatch.setattr(app_debug, '__file__', str(tmp_path / 'app_debug.py'))

        project = self._make_project()
        mock_cp = MagicMock()
        mock_cp.get.side_effect = lambda k: {
            "project2jira": json.dumps({
                "api_token": "secret-token",
                "fields": {"jira_status": {"enabled": True, "jira_field": "status"}},
            }),
        }.get(k)
        mock_cp.keySet.return_value = []
        project.getProjectProperties.return_value.getCustomProperties.return_value = mock_cp

        result = app_debug.dump_project_state(project)
        with open(result, encoding='utf-8') as fh:
            data = json.load(fh)

        props = data['jira_project_to_jira_props']
        assert props['api_token'] == '<redacted>'


class TestDumpProjectCalendarsBlock:
    """dump_project_state() always writes a 'project_calendars' block."""

    def _make_project(self):
        project = MagicMock()
        props = MagicMock()
        props.getName.return_value = "Test Project"
        props.getStartDate.return_value = None
        props.getFinishDate.return_value = None
        props.getAuthor.return_value = None
        props.getCompany.return_value = None
        props.getStatusDate.return_value = None
        props.getCurrencySymbol.return_value = None
        project.getProjectProperties.return_value = props
        project.getCustomFields.return_value = []
        project.getTasks.return_value = []
        project.getResources.return_value = []
        project.getDefaultCalendar.return_value = None
        project.getCalendars.return_value = []
        return project

    def test_project_calendars_block_present(self, tmp_path, monkeypatch):
        """dump_project_state() always writes a 'project_calendars' key."""
        monkeypatch.setattr(app_debug, '__file__', str(tmp_path / 'app_debug.py'))
        result = app_debug.dump_project_state(self._make_project())
        with open(result, encoding='utf-8') as fh:
            data = json.load(fh)
        assert 'project_calendars' in data

    def test_project_calendars_block_is_dict(self, tmp_path, monkeypatch):
        """project_calendars block is a dict."""
        monkeypatch.setattr(app_debug, '__file__', str(tmp_path / 'app_debug.py'))
        result = app_debug.dump_project_state(self._make_project())
        with open(result, encoding='utf-8') as fh:
            data = json.load(fh)
        assert isinstance(data['project_calendars'], dict)

    def test_project_calendars_has_installed_calendars_key(self, tmp_path, monkeypatch):
        """project_calendars contains an 'installed_calendars' list."""
        monkeypatch.setattr(app_debug, '__file__', str(tmp_path / 'app_debug.py'))
        result = app_debug.dump_project_state(self._make_project())
        with open(result, encoding='utf-8') as fh:
            data = json.load(fh)
        pc = data['project_calendars']
        assert 'installed_calendars' in pc
        assert isinstance(pc['installed_calendars'], list)


import datetime as _dt


class TestBuildCpmEntry:
    """Unit tests for the _build_cpm_entry helper (Phase 5 calendar-aware fields)."""

    _ES = _dt.datetime(2026, 1, 5, 8, 0)
    _EF = _dt.datetime(2026, 1, 9, 17, 0)

    def _fd_phase5(self, tf_wh=8.0, ff_wh=4.0, wdh=8.0, critical=False):
        """float_data entry with Phase 5 calendar-aware fields set."""
        return {
            "es": self._ES, "ef": self._EF,
            "ls": self._ES, "lf": self._EF,
            "total_float": _dt.timedelta(hours=tf_wh if tf_wh is not None else 8.0),
            "free_float":  _dt.timedelta(hours=ff_wh if ff_wh is not None else 4.0),
            "total_float_wh": tf_wh,
            "free_float_wh":  ff_wh,
            "work_day_hours": wdh,
            "critical": critical,
        }

    def _fd_legacy(self, total_hours=8.0, free_hours=4.0, critical=False):
        """float_data entry without Phase 5 data (total_float_wh=None)."""
        return {
            "es": self._ES, "ef": self._EF,
            "ls": self._ES, "lf": self._EF,
            "total_float": _dt.timedelta(hours=total_hours),
            "free_float":  _dt.timedelta(hours=free_hours),
            "total_float_wh": None,
            "free_float_wh":  None,
            "work_day_hours": None,
            "critical": critical,
        }

    def test_returns_none_when_no_float_data_for_task(self):
        result = app_debug._build_cpm_entry("99", {"float_data": {}})
        assert result is None

    def test_returns_none_when_ui_state_is_none(self):
        result = app_debug._build_cpm_entry("1", None)
        assert result is None

    def test_returns_dict_with_13_keys(self):
        ui = {"float_data": {1: self._fd_phase5()}}
        result = app_debug._build_cpm_entry("1", ui)
        assert isinstance(result, dict)
        assert len(result) == 13

    def test_calendar_aware_true_when_total_float_wh_set(self):
        ui = {"float_data": {1: self._fd_phase5(tf_wh=8.0)}}
        result = app_debug._build_cpm_entry("1", ui)
        assert result["calendar_aware"] is True

    def test_calendar_aware_false_when_total_float_wh_none(self):
        ui = {"float_data": {1: self._fd_legacy()}}
        result = app_debug._build_cpm_entry("1", ui)
        assert result["calendar_aware"] is False

    def test_total_float_wh_exposed_for_phase5_data(self):
        ui = {"float_data": {1: self._fd_phase5(tf_wh=6.5)}}
        result = app_debug._build_cpm_entry("1", ui)
        assert result["total_float_wh"] == 6.5

    def test_free_float_wh_exposed_for_phase5_data(self):
        ui = {"float_data": {1: self._fd_phase5(ff_wh=3.25)}}
        result = app_debug._build_cpm_entry("1", ui)
        assert result["free_float_wh"] == 3.25

    def test_total_float_wh_none_when_not_phase5(self):
        ui = {"float_data": {1: self._fd_legacy()}}
        result = app_debug._build_cpm_entry("1", ui)
        assert result["total_float_wh"] is None

    def test_total_float_d_uses_work_day_hours(self):
        # 16 wh / 8 wdh = 2.0 working days
        ui = {"float_data": {1: self._fd_phase5(tf_wh=16.0, wdh=8.0)}}
        result = app_debug._build_cpm_entry("1", ui)
        assert result["total_float_d"] == 2.0

    def test_total_float_d_uses_custom_wdh(self):
        # 10 wh / 10 wdh = 1.0 working day
        ui = {"float_data": {1: self._fd_phase5(tf_wh=10.0, wdh=10.0)}}
        result = app_debug._build_cpm_entry("1", ui)
        assert result["total_float_d"] == 1.0

    def test_total_float_d_falls_back_to_8h_when_wdh_none(self):
        # legacy path: total_float timedelta=8h, wdh=None → falls back to 8 → 1.0 day
        ui = {"float_data": {1: self._fd_legacy(total_hours=8.0)}}
        result = app_debug._build_cpm_entry("1", ui)
        assert result["total_float_d"] == 1.0

    def test_legacy_total_float_h_comes_from_timedelta(self):
        # When total_float_wh is None, total_float_h is derived from the timedelta
        ui = {"float_data": {1: self._fd_legacy(total_hours=4.0)}}
        result = app_debug._build_cpm_entry("1", ui)
        assert result["total_float_h"] == 4.0

    def test_critical_flag_preserved(self):
        ui = {"float_data": {1: self._fd_phase5(critical=True)}}
        result = app_debug._build_cpm_entry("1", ui)
        assert result["critical"] is True

    def test_work_day_hours_in_result(self):
        ui = {"float_data": {1: self._fd_phase5(wdh=9.0)}}
        result = app_debug._build_cpm_entry("1", ui)
        assert result["work_day_hours"] == 9.0


class TestDumpCpmBlocks:
    """Integration tests for cpm_settings and cpm_summary blocks in dump_project_state (Phase 5).

    Note: float_data entries use None for es/ef/total_float/free_float so that the dict
    is JSON-serializable when embedded in payload["ui"].  The CPM block logic reads only
    the scalar fields (total_float_wh, work_day_hours, critical) from float_data for
    calendar-aware calculations, so the datetime/timedelta fields are not needed here.
    """

    def _make_project(self):
        project = MagicMock()
        props = MagicMock()
        props.getName.return_value = "Test"
        props.getStartDate.return_value = None
        props.getFinishDate.return_value = None
        props.getAuthor.return_value = None
        props.getCompany.return_value = None
        props.getStatusDate.return_value = None
        props.getCurrencySymbol.return_value = None
        project.getProjectProperties.return_value = props
        project.getCustomFields.return_value = []
        project.getTasks.return_value = []
        project.getResources.return_value = []
        project.getDefaultCalendar.return_value = None
        project.getCalendars.return_value = []
        return project

    def _run(self, tmp_path, monkeypatch, ui_state):
        monkeypatch.setattr(app_debug, '__file__', str(tmp_path / 'app_debug.py'))
        result = app_debug.dump_project_state(self._make_project(), ui_state=ui_state)
        with open(result, encoding='utf-8') as fh:
            return json.load(fh)

    def _fd_entry(self, tf_wh=8.0, ff_wh=4.0, wdh=8.0, critical=False):
        """Return a float_data entry using only JSON-serializable types.

        es/ef/total_float/free_float are set to None; the CPM block code only
        reads the scalar Phase 5 fields for the calendar-aware code paths.
        """
        return {
            "es": None, "ef": None, "ls": None, "lf": None,
            "total_float": None,
            "free_float": None,
            "total_float_wh": tf_wh,
            "free_float_wh":  ff_wh,
            "work_day_hours": wdh,
            "critical": critical,
        }

    def test_cpm_settings_block_present_in_dump(self, tmp_path, monkeypatch):
        data = self._run(tmp_path, monkeypatch, ui_state=None)
        assert "cpm_settings" in data
        assert isinstance(data["cpm_settings"], dict)

    def test_cpm_summary_block_present_in_dump(self, tmp_path, monkeypatch):
        data = self._run(tmp_path, monkeypatch, ui_state=None)
        assert "cpm_summary" in data
        assert isinstance(data["cpm_summary"], dict)

    def test_calendar_aware_active_true_when_float_data_has_wh(self, tmp_path, monkeypatch):
        ui = {"float_data": {1: self._fd_entry(tf_wh=8.0)}}
        data = self._run(tmp_path, monkeypatch, ui_state=ui)
        assert data["cpm_settings"]["calendar_aware_active"] is True
        assert data["cpm_summary"]["calendar_aware_active"] is True

    def test_calendar_aware_active_false_when_no_wh(self, tmp_path, monkeypatch):
        ui = {"float_data": {1: self._fd_entry(tf_wh=None, ff_wh=None, wdh=None)}}
        data = self._run(tmp_path, monkeypatch, ui_state=ui)
        assert data["cpm_settings"]["calendar_aware_active"] is False
        assert data["cpm_summary"]["calendar_aware_active"] is False

    def test_project_wdh_is_median_of_task_wdh(self, tmp_path, monkeypatch):
        # Tasks with wdh 6, 8, 10 → median = sorted[1] = 8.0
        ui = {"float_data": {
            1: self._fd_entry(wdh=6.0),
            2: self._fd_entry(wdh=8.0),
            3: self._fd_entry(wdh=10.0),
        }}
        data = self._run(tmp_path, monkeypatch, ui_state=ui)
        assert data["cpm_settings"]["project_wdh"] == 8.0

    def test_project_wdh_defaults_to_8_when_no_float_data(self, tmp_path, monkeypatch):
        data = self._run(tmp_path, monkeypatch, ui_state={"float_data": {}})
        assert data["cpm_settings"]["project_wdh"] == 8.0

    def test_critical_count_correct(self, tmp_path, monkeypatch):
        ui = {"float_data": {
            1: self._fd_entry(critical=True),
            2: self._fd_entry(critical=False),
            3: self._fd_entry(critical=True),
        }}
        data = self._run(tmp_path, monkeypatch, ui_state=ui)
        assert data["cpm_summary"]["critical_count"] == 2

    def test_near_critical_count_uses_calendar_aware_wdh(self, tmp_path, monkeypatch):
        # slack=1 day; task 2: 6.0 wh / 8 wdh = 0.75 d ≤ 1 → near-critical
        # task 3: 16.0 wh / 8 wdh = 2.0 d > 1 → not near-critical
        ui = {
            "float_data": {
                1: self._fd_entry(critical=True),
                2: self._fd_entry(tf_wh=6.0, wdh=8.0, critical=False),
                3: self._fd_entry(tf_wh=16.0, wdh=8.0, critical=False),
            },
            "cpm_settings": {"critical_slack_days": 1},
        }
        data = self._run(tmp_path, monkeypatch, ui_state=ui)
        assert data["cpm_summary"]["near_critical_count"] == 1

    def test_project_duration_d_none_when_no_datetime_in_float_data(self, tmp_path, monkeypatch):
        # Without es/ef datetimes in float_data, project_duration_d is None
        ui = {"float_data": {1: self._fd_entry(wdh=8.0)}}
        data = self._run(tmp_path, monkeypatch, ui_state=ui)
        assert data["cpm_summary"]["project_duration_d"] is None

    def test_task_cpm_entry_has_phase5_keys(self, tmp_path, monkeypatch):
        """When a task's float_data has Phase 5 fields, the cpm dict in tasks[] contains them."""
        project = self._make_project()
        task = MagicMock()
        task.getID.return_value = 1
        task.getName.return_value = "Task A"
        task.getStart.return_value = None
        task.getFinish.return_value = None
        task.getDuration.return_value = None
        task.getPercentageComplete.return_value = None
        task.getCritical.return_value = False
        task.getMilestone.return_value = False
        task.getSummary.return_value = False
        task.getConstraintType.return_value = None
        task.getConstraintDate.return_value = None
        task.getBaselineStart.return_value = None
        task.getBaselineFinish.return_value = None
        task.getPredecessors.return_value = []
        task.getResourceAssignments.return_value = []
        task.getSplits.return_value = None
        task.getUniqueID.return_value = 101
        task.getCachedValue = MagicMock(return_value=None)
        project.getTasks.return_value = [task]
        # dump_project_state calls _s(t.getID()) → str(1) → "1", so key must be "1"
        # Use only JSON-serializable types (no datetime/timedelta)
        ui = {"float_data": {1: self._fd_entry(tf_wh=8.0, ff_wh=4.0, wdh=8.0)}}
        monkeypatch.setattr(app_debug, '__file__', str(tmp_path / 'app_debug.py'))
        path = app_debug.dump_project_state(project, ui_state=ui)
        with open(path, encoding='utf-8') as fh:
            data = json.load(fh)
        cpm = data["tasks"][0]["cpm"]
        assert cpm is not None
        assert cpm["calendar_aware"] is True
        assert cpm["total_float_wh"] == 8.0
        assert cpm["free_float_wh"] == 4.0
        assert cpm["work_day_hours"] == 8.0
        assert cpm["total_float_d"] == 1.0
        assert cpm["free_float_d"] == 0.5

