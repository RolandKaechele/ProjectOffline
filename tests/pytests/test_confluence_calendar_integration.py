"""Tests for integrations/confluence_calendar_integration.py — Confluence Team Calendar integration.

All network I/O (requests, Playwright), Qt widgets, and JPype/MPXJ Java classes are
replaced with MagicMock objects so the full suite runs offline without a browser,
a JVM, or a Confluence server.

Coverage:
  - Module location (importable from integrations.confluence_calendar_integration)
  - Module constants
  - _flatten_calendars
  - _filter_relevant
  - _parse_date
  - _get_custom_prop / get_project_* helpers
  - _apply_to_project (holidays and vacations, resource matching, calendar creation,
    stale-entry removal in the sync window, expired-entry pruning via prune_before,
    fallback from end-date to start-date when getToDate() is unavailable,
    mixed expired+future exceptions, combined prune+window-removal)
  - ConfluenceCalendarSync.run — all early-exit branches, happy path,
    history_manager.push_all() call ordering, pruned-count in summary
  - clear_saved_session
"""

import sys
import os
import types
from datetime import date
from unittest.mock import MagicMock, patch, call
import pytest

# -- make src/ importable ----------------------------------------------------
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

# ---------------------------------------------------------------------------
# Stub out optional heavy dependencies before the module is imported so that
# the module-level import guards (_REQUESTS_OK, _PLAYWRIGHT_OK) are True.
# ---------------------------------------------------------------------------
_mock_requests = MagicMock()
_mock_playwright = MagicMock()

sys.modules.setdefault('requests', _mock_requests)
sys.modules.setdefault('playwright', _mock_playwright)
sys.modules.setdefault('playwright.sync_api', _mock_playwright)

# Provide a proper TimeoutError class so the `except _PlaywrightTimeout` handler
# in confluence_calendar.py works correctly.
class _FakePlaywrightTimeout(Exception):
    pass

_mock_playwright.sync_api = types.SimpleNamespace(
    sync_playwright=MagicMock(),
    TimeoutError=_FakePlaywrightTimeout,
)
sys.modules['playwright.sync_api'] = types.ModuleType('playwright.sync_api')
sys.modules['playwright.sync_api'].sync_playwright = MagicMock()
sys.modules['playwright.sync_api'].TimeoutError = _FakePlaywrightTimeout

# jpype is only imported inside _apply_to_project(), not at module level in
# confluence_calendar.py, so no global stub is needed.  Tests that exercise
# _apply_to_project patch it locally via patch.dict / patch.

from integrations import confluence_calendar_integration as cc  # noqa: E402  (after sys.modules setup)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_project_with_prop(key: str, value: str):
    """Helper that creates a mock project and patches _get_enterprise_prop for it."""
    project = MagicMock()
    original_func = cc._get_enterprise_prop
    
    def mock_prop(proj, prop_key):
        if proj is project and prop_key == key:
            return value
        return None
    
    return project, mock_prop


# ===========================================================================
# 1. Module constants
# ===========================================================================

class TestConstants:
    def test_base_url_prop(self):
        assert cc.CONFLUENCE_BASE_URL_PROP == "CALENDAR Base URL"

    def test_space_key_prop(self):
        assert cc.CONFLUENCE_SPACE_KEY_PROP == "CALENDAR Space Key"

    def test_timezone_prop(self):
        assert cc.CONFLUENCE_TIMEZONE_PROP == "CALENDAR Timezone"

    def test_days_ahead_prop(self):
        assert cc.CONFLUENCE_DAYS_AHEAD_PROP == "CALENDAR Days Ahead"

    def test_default_timezone_is_europe_berlin(self):
        assert cc._DEFAULT_TIMEZONE == "Europe/Berlin"

    def test_default_days_ahead_is_365(self):
        assert cc._DEFAULT_DAYS_AHEAD == 365


# ===========================================================================
# 2. _flatten_calendars
# ===========================================================================

class TestFlattenCalendars:
    def test_empty_list(self):
        assert cc._flatten_calendars([]) == []

    def test_single_non_parent_subcalendar(self):
        raw = [{"subCalendar": {"id": "a", "type": "custom", "name": "Holidays"}, "childSubCalendars": []}]
        result = cc._flatten_calendars(raw)
        assert len(result) == 1
        assert result[0]["id"] == "a"

    def test_parent_type_subcalendar_is_excluded(self):
        raw = [{"subCalendar": {"id": "p", "type": "parent", "name": "Root"}, "childSubCalendars": []}]
        assert cc._flatten_calendars(raw) == []

    def test_child_subcalendars_are_included(self):
        raw = [
            {
                "subCalendar": {"id": "p", "type": "parent"},
                "childSubCalendars": [
                    {"subCalendar": {"id": "c1", "type": "leaves", "name": "Leave"}},
                    {"subCalendar": {"id": "c2", "type": "custom", "name": "Holidays"}},
                ],
            }
        ]
        result = cc._flatten_calendars(raw)
        ids = {r["id"] for r in result}
        assert ids == {"c1", "c2"}

    def test_child_parent_type_excluded(self):
        raw = [
            {
                "subCalendar": {"id": "a", "type": "custom"},
                "childSubCalendars": [
                    {"subCalendar": {"id": "cp", "type": "parent"}},
                ],
            }
        ]
        result = cc._flatten_calendars(raw)
        ids = {r["id"] for r in result}
        assert ids == {"a"}

    def test_no_child_subcalendars_key(self):
        raw = [{"subCalendar": {"id": "x", "type": "custom"}}]
        result = cc._flatten_calendars(raw)
        assert len(result) == 1

    def test_multiple_items_all_collected(self):
        raw = [
            {"subCalendar": {"id": "a", "type": "custom"}, "childSubCalendars": []},
            {"subCalendar": {"id": "b", "type": "leaves"}, "childSubCalendars": []},
        ]
        result = cc._flatten_calendars(raw)
        assert len(result) == 2

    def test_missing_subcalendar_key_skipped(self):
        raw = [{"childSubCalendars": []}]
        # subCalendar key missing ? sub is {}, type check: {} type is "", not "parent"
        result = cc._flatten_calendars(raw)
        assert result == []  # empty sub dict is falsy ? skipped

    def test_preserves_all_fields(self):
        raw = [{"subCalendar": {"id": "x", "type": "custom", "name": "Test", "extra": 42}, "childSubCalendars": []}]
        result = cc._flatten_calendars(raw)
        assert result[0]["extra"] == 42


# ===========================================================================
# 3. _filter_relevant
# ===========================================================================

class TestFilterRelevant:
    def _cal(self, cal_type="", name=""):
        return {"type": cal_type, "name": name}

    def test_leaves_type_included(self):
        result = cc._filter_relevant([self._cal("leaves", "Some Leave")])
        assert len(result) == 1

    def test_custom_type_included(self):
        result = cc._filter_relevant([self._cal("custom", "Generic")])
        assert len(result) == 1

    def test_unknown_type_excluded_without_keyword(self):
        result = cc._filter_relevant([self._cal("meeting", "Sprint Planning")])
        assert result == []

    def test_holiday_keyword_in_name(self):
        result = cc._filter_relevant([self._cal("meeting", "Public Holiday")])
        assert len(result) == 1

    def test_vacation_keyword_in_name(self):
        result = cc._filter_relevant([self._cal("other", "Vacation Calendar")])
        assert len(result) == 1

    def test_leave_keyword_in_name(self):
        result = cc._filter_relevant([self._cal("other", "Annual Leave")])
        assert len(result) == 1

    def test_feiertag_keyword_in_name(self):
        result = cc._filter_relevant([self._cal("other", "Gesetzliche Feiertage")])
        assert len(result) == 1

    def test_urlaub_keyword_in_name(self):
        result = cc._filter_relevant([self._cal("other", "Urlaub DE")])
        assert len(result) == 1

    def test_case_insensitive_name_match(self):
        result = cc._filter_relevant([self._cal("other", "HOLIDAY CALENDAR")])
        assert len(result) == 1

    def test_empty_input(self):
        assert cc._filter_relevant([]) == []

    def test_multiple_mixed(self):
        cals = [
            self._cal("leaves", ""),
            self._cal("meeting", "Sprint"),
            self._cal("custom", ""),
            self._cal("other", "Vacation"),
        ]
        result = cc._filter_relevant(cals)
        assert len(result) == 3

    def test_missing_type_and_name_keys(self):
        result = cc._filter_relevant([{}])
        assert result == []


# ===========================================================================
# 4. _parse_date
# ===========================================================================

class TestParseDate:
    def test_valid_iso_date(self):
        assert cc._parse_date("2025-06-15") == date(2025, 6, 15)

    def test_datetime_string_uses_first_10_chars(self):
        assert cc._parse_date("2025-06-15T09:00:00") == date(2025, 6, 15)

    def test_none_input_returns_none(self):
        assert cc._parse_date(None) is None

    def test_empty_string_returns_none(self):
        assert cc._parse_date("") is None

    def test_invalid_date_returns_none(self):
        assert cc._parse_date("not-a-date") is None

    def test_partial_invalid_returns_none(self):
        assert cc._parse_date("2025-13-01") is None

    def test_leap_year_date(self):
        assert cc._parse_date("2024-02-29") == date(2024, 2, 29)

    def test_non_leap_year_invalid(self):
        assert cc._parse_date("2023-02-29") is None

    def test_year_boundary(self):
        assert cc._parse_date("2000-01-01") == date(2000, 1, 1)


# ===========================================================================
# 5. _get_enterprise_prop and public getter helpers
# ===========================================================================

class TestGetEnterpriseProp:
    def test_returns_none_when_key_absent(self):
        summary_task = MagicMock()
        summary_task.getUniqueID.return_value = 0
        
        UserDefinedField = MagicMock()
        field_type = MagicMock()
        field_type.__class__ = UserDefinedField
        field_type.getFieldTypeClass.return_value = 'TASK'
        
        custom_field = MagicMock()
        custom_field.getAlias.return_value = "DIFFERENT_KEY"
        custom_field.getFieldType.return_value = field_type
        
        project = MagicMock()
        project.getTasks.return_value = [summary_task]
        project.getCustomFields.return_value = [custom_field]
        
        original_isinstance = __builtins__['isinstance'] if hasattr(__builtins__, 'isinstance') else isinstance
        def mock_isinstance(obj, cls):
            if obj is field_type and cls is UserDefinedField:
                return True
            return original_isinstance(obj, cls)
        
        with patch.dict('sys.modules', {'org.mpxj': MagicMock(UserDefinedField=UserDefinedField)}), \
             patch('builtins.isinstance', side_effect=mock_isinstance):
            assert cc._get_enterprise_prop(project, "CALENDAR Base URL") is None

    def test_blank_string_returns_none(self):
        summary_task = MagicMock()
        summary_task.getUniqueID.return_value = 0
        
        UserDefinedField = MagicMock()
        field_type = MagicMock()
        field_type.__class__ = UserDefinedField
        field_type.getFieldTypeClass.return_value = 'TASK'
        
        custom_field = MagicMock()
        custom_field.getAlias.return_value = "CALENDAR Timezone"
        custom_field.getFieldType.return_value = field_type
        
        summary_task.getCachedValue.return_value = "   "
        
        project = MagicMock()
        project.getTasks.return_value = [summary_task]
        project.getCustomFields.return_value = [custom_field]
        
        original_isinstance = __builtins__['isinstance'] if hasattr(__builtins__, 'isinstance') else isinstance
        def mock_isinstance(obj, cls):
            if obj is field_type and cls is UserDefinedField:
                return True
            return original_isinstance(obj, cls)
        
        with patch.dict('sys.modules', {'org.mpxj': MagicMock(UserDefinedField=UserDefinedField)}), \
             patch('builtins.isinstance', side_effect=mock_isinstance):
            assert cc._get_enterprise_prop(project, "CALENDAR Timezone") is None

    def test_exception_returns_none(self):
        project = MagicMock()
        # Make both lookup paths fail: custom-properties returns None so
        # the function falls through to the enterprise-field path, and
        # getTasks() then raises so the whole function returns None.
        project.getProjectProperties.return_value.getCustomProperties.return_value.get.return_value = None
        project.getTasks.side_effect = RuntimeError("boom")
        assert cc._get_enterprise_prop(project, "CALENDAR Base URL") is None


class TestGetProjectBaseUrl:
    def test_returns_url_without_trailing_slash(self):
        project = MagicMock()
        with patch.object(cc, '_get_enterprise_prop', return_value="https://conf.example.com/"):
            assert cc.get_project_base_url(project) == "https://conf.example.com"

    def test_url_without_slash_unchanged(self):
        project = MagicMock()
        with patch.object(cc, '_get_enterprise_prop', return_value="https://conf.example.com"):
            assert cc.get_project_base_url(project) == "https://conf.example.com"

    def test_returns_none_when_absent(self):
        project = MagicMock()
        with patch.object(cc, '_get_enterprise_prop', return_value=None):
            assert cc.get_project_base_url(project) is None


class TestGetProjectSpaceKey:
    def test_returns_space_key(self):
        project = MagicMock()
        with patch.object(cc, '_get_enterprise_prop', return_value="MYSPACE"):
            assert cc.get_project_space_key(project) == "MYSPACE"

    def test_returns_none_when_absent(self):
        project = MagicMock()
        with patch.object(cc, '_get_enterprise_prop', return_value=None):
            assert cc.get_project_space_key(project) is None


class TestGetProjectTimezone:
    def test_returns_stored_timezone(self):
        project = MagicMock()
        with patch.object(cc, '_get_enterprise_prop', return_value="America/New_York"):
            assert cc.get_project_timezone(project) == "America/New_York"

    def test_falls_back_to_default_when_absent(self):
        project = MagicMock()
        with patch.object(cc, '_get_enterprise_prop', return_value=None):
            assert cc.get_project_timezone(project) == "Europe/Berlin"

    def test_falls_back_when_blank(self):
        project = MagicMock()
        with patch.object(cc, '_get_enterprise_prop', return_value=""):
            assert cc.get_project_timezone(project) == "Europe/Berlin"


class TestGetProjectDaysAhead:
    def test_returns_stored_value(self):
        project = MagicMock()
        with patch.object(cc, '_get_enterprise_prop', return_value="180"):
            assert cc.get_project_days_ahead(project) == 180

    def test_falls_back_when_absent(self):
        project = MagicMock()
        with patch.object(cc, '_get_enterprise_prop', return_value=None):
            assert cc.get_project_days_ahead(project) == 365

    def test_falls_back_on_non_numeric(self):
        project = MagicMock()
        with patch.object(cc, '_get_enterprise_prop', return_value="lots"):
            assert cc.get_project_days_ahead(project) == 365

    def test_falls_back_when_zero(self):
        project = MagicMock()
        with patch.object(cc, '_get_enterprise_prop', return_value="0"):
            assert cc.get_project_days_ahead(project) == 365

    def test_falls_back_when_too_large(self):
        project = MagicMock()
        with patch.object(cc, '_get_enterprise_prop', return_value="9999"):
            assert cc.get_project_days_ahead(project) == 365

    def test_boundary_value_1(self):
        project = MagicMock()
        with patch.object(cc, '_get_enterprise_prop', return_value="1"):
            assert cc.get_project_days_ahead(project) == 1

    def test_boundary_value_3650(self):
        project = MagicMock()
        with patch.object(cc, '_get_enterprise_prop', return_value="3650"):
            assert cc.get_project_days_ahead(project) == 3650

    def test_negative_value_falls_back(self):
        project = MagicMock()
        with patch.object(cc, '_get_enterprise_prop', return_value="-10"):
            assert cc.get_project_days_ahead(project) == 365


# ===========================================================================
# 6. _apply_to_project
# ===========================================================================

def _make_local_date_class():
    """Return a mock LocalDate Java class."""
    LocalDate = MagicMock()
    LocalDate.of = MagicMock(side_effect=lambda y, m, d: f"{y:04d}-{m:02d}-{d:02d}")
    return LocalDate


class TestApplyToProject:
    """Tests for _apply_to_project — exercises both holiday and vacation paths."""

    def _run(self, project, holiday_events, vacation_events):
        """Run _apply_to_project with a mocked jpype.JClass."""
        LocalDate = _make_local_date_class()
        with patch.dict('sys.modules', {'jpype': MagicMock()}):
            import jpype
            jpype.JClass = MagicMock(return_value=LocalDate)
            return cc._apply_to_project(project, holiday_events, vacation_events)

    # ---- holidays ----

    def test_holidays_added_to_default_calendar(self):
        project = MagicMock()
        cal = MagicMock()
        project.getDefaultCalendar.return_value = cal
        project.getResources.return_value = []

        holiday = {"start": "2025-12-25", "end": "2025-12-25"}
        LocalDate = _make_local_date_class()
        with patch.dict('sys.modules', {'jpype': MagicMock()}):
            import jpype
            jpype.JClass = MagicMock(return_value=LocalDate)
            n_h, n_v, *_ = cc._apply_to_project(project, [holiday], [])

        assert n_h == 1
        assert n_v == 0
        cal.addCalendarException.assert_called_once()

    def test_holiday_with_null_default_calendar(self):
        project = MagicMock()
        project.getDefaultCalendar.return_value = None
        project.getResources.return_value = []

        holiday = {"start": "2025-12-25", "end": "2025-12-25"}
        LocalDate = _make_local_date_class()
        with patch.dict('sys.modules', {'jpype': MagicMock()}):
            import jpype
            jpype.JClass = MagicMock(return_value=LocalDate)
            n_h, n_v, *_ = cc._apply_to_project(project, [holiday], [])

        assert n_h == 0

    def test_holiday_with_invalid_start_date_skipped(self):
        project = MagicMock()
        cal = MagicMock()
        project.getDefaultCalendar.return_value = cal
        project.getResources.return_value = []

        holiday = {"start": None}
        LocalDate = _make_local_date_class()
        with patch.dict('sys.modules', {'jpype': MagicMock()}):
            import jpype
            jpype.JClass = MagicMock(return_value=LocalDate)
            n_h, n_v, *_ = cc._apply_to_project(project, [holiday], [])

        assert n_h == 0
        cal.addCalendarException.assert_not_called()

    def test_holiday_missing_end_defaults_to_start(self):
        project = MagicMock()
        cal = MagicMock()
        project.getDefaultCalendar.return_value = cal
        project.getResources.return_value = []

        holiday = {"start": "2025-12-25"}  # no end key
        LocalDate = _make_local_date_class()
        with patch.dict('sys.modules', {'jpype': MagicMock()}):
            import jpype
            jpype.JClass = MagicMock(return_value=LocalDate)
            n_h, n_v, *_ = cc._apply_to_project(project, [holiday], [])

        assert n_h == 1

    def test_multiple_holidays_counted(self):
        project = MagicMock()
        cal = MagicMock()
        project.getDefaultCalendar.return_value = cal
        project.getResources.return_value = []

        # Only single-day events count; multi-day spans are skipped (Schulferien filter).
        holidays = [
            {"start": "2025-01-01", "end": "2025-01-01"},
            {"start": "2025-05-01", "end": "2025-05-01"},
            {"start": "2025-12-25", "end": "2025-12-27"},  # 3-day span → skipped
        ]
        LocalDate = _make_local_date_class()
        with patch.dict('sys.modules', {'jpype': MagicMock()}):
            import jpype
            jpype.JClass = MagicMock(return_value=LocalDate)
            n_h, n_v, *_ = cc._apply_to_project(project, holidays, [])

        assert n_h == 2

    def test_multi_day_holiday_span_is_skipped(self):
        """Multi-day holiday spans (e.g. school holidays / Schulferien) must not
        be written to the default calendar — they grey out entire weeks for all
        resources."""
        project = MagicMock()
        cal = MagicMock()
        project.getDefaultCalendar.return_value = cal
        project.getResources.return_value = []

        # 16-day Schulferien block typical of Confluence school-holiday calendars
        holiday = {"start": "2026-05-06", "end": "2026-05-21"}
        LocalDate = _make_local_date_class()
        with patch.dict('sys.modules', {'jpype': MagicMock()}):
            import jpype
            jpype.JClass = MagicMock(return_value=LocalDate)
            n_h, n_v, *_ = cc._apply_to_project(project, [holiday], [])

        assert n_h == 0
        cal.addCalendarException.assert_not_called()

    def test_two_day_holiday_span_is_skipped(self):
        """A 2-day span (end - start == 1 day) must also be skipped.
        Confluence can produce these for short Schulferien blocks or when
        using exclusive end-date conventions (DTEND = start + 1 day)."""
        project = MagicMock()
        cal = MagicMock()
        project.getDefaultCalendar.return_value = cal
        project.getResources.return_value = []

        # 2026-11-30 → 2026-12-01: a real anonymous block found in the dump
        holiday = {"start": "2026-11-30", "end": "2026-12-01"}
        LocalDate = _make_local_date_class()
        with patch.dict('sys.modules', {'jpype': MagicMock()}):
            import jpype
            jpype.JClass = MagicMock(return_value=LocalDate)
            n_h, n_v, *_ = cc._apply_to_project(project, [holiday], [])

        assert n_h == 0
        cal.addCalendarException.assert_not_called()

    def test_single_day_holiday_still_accepted(self):
        """Single-day events (start == end) continue to be written as before."""
        project = MagicMock()
        cal = MagicMock()
        project.getDefaultCalendar.return_value = cal
        project.getResources.return_value = []

        holiday = {"start": "2026-05-14", "end": "2026-05-14"}  # Christi Himmelfahrt
        LocalDate = _make_local_date_class()
        with patch.dict('sys.modules', {'jpype': MagicMock()}):
            import jpype
            jpype.JClass = MagicMock(return_value=LocalDate)
            n_h, n_v, *_ = cc._apply_to_project(project, [holiday], [])

        assert n_h == 1
        cal.addCalendarException.assert_called_once()

    # ---- vacations ----

    def _make_resource(self, name, has_calendar=True):
        res = MagicMock()
        res.getName.return_value = name
        cal = MagicMock() if has_calendar else None
        res.getCalendar.return_value = cal
        return res

    def test_vacation_added_to_resource_calendar_by_exact_name(self):
        project = MagicMock()
        project.getDefaultCalendar.return_value = MagicMock()
        res = self._make_resource("Alice")
        project.getResources.return_value = [res]

        vacation = {"start": "2025-07-01", "end": "2025-07-14", "userName": "Alice"}
        LocalDate = _make_local_date_class()
        with patch.dict('sys.modules', {'jpype': MagicMock()}):
            import jpype
            jpype.JClass = MagicMock(return_value=LocalDate)
            n_h, n_v, *_ = cc._apply_to_project(project, [], [vacation])

        assert n_v == 1
        res.getCalendar.return_value.addCalendarException.assert_called_once()

    def test_vacation_case_insensitive_match(self):
        project = MagicMock()
        project.getDefaultCalendar.return_value = MagicMock()
        res = self._make_resource("Bob Smith")
        project.getResources.return_value = [res]

        vacation = {"start": "2025-08-01", "end": "2025-08-07", "userName": "BOB SMITH"}
        LocalDate = _make_local_date_class()
        with patch.dict('sys.modules', {'jpype': MagicMock()}):
            import jpype
            jpype.JClass = MagicMock(return_value=LocalDate)
            n_h, n_v, *_ = cc._apply_to_project(project, [], [vacation])

        assert n_v == 1

    def test_vacation_partial_match(self):
        project = MagicMock()
        project.getDefaultCalendar.return_value = MagicMock()
        res = self._make_resource("Carol Johnson")
        project.getResources.return_value = [res]

        vacation = {"start": "2025-08-01", "end": "2025-08-07", "userName": "Carol"}
        LocalDate = _make_local_date_class()
        with patch.dict('sys.modules', {'jpype': MagicMock()}):
            import jpype
            jpype.JClass = MagicMock(return_value=LocalDate)
            n_h, n_v, *_ = cc._apply_to_project(project, [], [vacation])

        assert n_v == 1

    def test_vacation_unmatched_user_creates_resource(self):
        """Unmatched username now auto-creates a resource."""
        project = MagicMock()
        project.getDefaultCalendar.return_value = MagicMock()
        project.getResources.return_value = []
        new_res = MagicMock()
        new_cal = MagicMock()
        new_cal.getCalendarExceptions.return_value = []
        new_res.getCalendar.return_value = new_cal
        project.addResource.return_value = new_res

        vacation = {"start": "2025-08-01", "end": "2025-08-07", "userName": "Unknown"}
        LocalDate = _make_local_date_class()
        with patch.dict('sys.modules', {'jpype': MagicMock()}):
            import jpype
            jpype.JClass = MagicMock(return_value=LocalDate)
            n_h, n_v, n_v_rem, n_pruned, n_res_new = cc._apply_to_project(project, [], [vacation])

        assert n_v == 1  # Vacation was added
        assert n_res_new == 1  # New resource was created
        project.addResource.assert_called_once()
        new_res.setName.assert_called_once_with("Unknown")

    def test_vacation_creates_resource_calendar_when_none(self):
        """When a resource has no calendar, _apply_to_project creates one."""
        project = MagicMock()
        default_cal = MagicMock()
        project.getDefaultCalendar.return_value = default_cal
        new_cal = MagicMock()
        project.addCalendar.return_value = new_cal

        res = self._make_resource("Dave", has_calendar=False)
        res.getCalendar.return_value = None  # explicitly no calendar
        project.getResources.return_value = [res]

        vacation = {"start": "2025-09-01", "end": "2025-09-05", "userName": "Dave"}
        LocalDate = _make_local_date_class()
        with patch.dict('sys.modules', {'jpype': MagicMock()}):
            import jpype
            jpype.JClass = MagicMock(return_value=LocalDate)
            n_h, n_v, *_ = cc._apply_to_project(project, [], [vacation])

        assert n_v == 1
        project.addCalendar.assert_called_once()
        new_cal.setParent.assert_called_once_with(default_cal)
        res.setCalendar.assert_called_once_with(new_cal)

    def test_vacation_end_before_start_defaults_to_start(self):
        project = MagicMock()
        project.getDefaultCalendar.return_value = MagicMock()
        res = self._make_resource("Eve")
        project.getResources.return_value = [res]

        # end before start — should default end to start
        vacation = {"start": "2025-07-10", "end": "2025-07-05", "userName": "Eve"}
        LocalDate = _make_local_date_class()
        with patch.dict('sys.modules', {'jpype': MagicMock()}):
            import jpype
            jpype.JClass = MagicMock(return_value=LocalDate)
            n_h, n_v, *_ = cc._apply_to_project(project, [], [vacation])

        assert n_v == 1

    def test_vacation_invalid_start_skipped(self):
        project = MagicMock()
        project.getDefaultCalendar.return_value = MagicMock()
        res = self._make_resource("Frank")
        project.getResources.return_value = [res]

        vacation = {"start": None, "end": None, "userName": "Frank"}
        LocalDate = _make_local_date_class()
        with patch.dict('sys.modules', {'jpype': MagicMock()}):
            import jpype
            jpype.JClass = MagicMock(return_value=LocalDate)
            n_h, n_v, *_ = cc._apply_to_project(project, [], [vacation])

        assert n_v == 0

    def test_resource_with_none_name_excluded_from_matching(self):
        """Resources with None name are excluded, but auto-creation still works for valid usernames."""
        project = MagicMock()
        project.getDefaultCalendar.return_value = MagicMock()
        res = MagicMock()
        res.getName.return_value = None  # unnamed resource
        project.getResources.return_value = [res]
        
        # Mock addResource for auto-creation
        new_res = MagicMock()
        new_cal = MagicMock()
        new_cal.getCalendarExceptions.return_value = []
        new_res.getCalendar.return_value = new_cal
        project.addResource.return_value = new_res

        vacation = {"start": "2025-07-01", "end": "2025-07-07", "userName": "Alice"}
        LocalDate = _make_local_date_class()
        with patch.dict('sys.modules', {'jpype': MagicMock()}):
            import jpype
            jpype.JClass = MagicMock(return_value=LocalDate)
            n_h, n_v, n_v_rem, n_pruned, n_res_new = cc._apply_to_project(project, [], [vacation])

        assert n_v == 1  # Vacation added to auto-created resource
        assert n_res_new == 1  # Resource was auto-created

    def test_startdate_enddate_field_names_accepted(self):
        """Alternative field names startDate / endDate are also parsed."""
        project = MagicMock()
        cal = MagicMock()
        project.getDefaultCalendar.return_value = cal
        project.getResources.return_value = []

        holiday = {"startDate": "2025-11-01", "endDate": "2025-11-01"}
        LocalDate = _make_local_date_class()
        with patch.dict('sys.modules', {'jpype': MagicMock()}):
            import jpype
            jpype.JClass = MagicMock(return_value=LocalDate)
            n_h, n_v, *_ = cc._apply_to_project(project, [holiday], [])

        assert n_h == 1


# ===========================================================================
# 7. Stale vacation removal
# ===========================================================================

def _make_exc_mock(start_str: str, end_str: str = None):
    """Return a mock ProjectCalendarException with realistic getFromDate/getToDate."""
    from datetime import date as _date
    s = _date.fromisoformat(start_str)
    e = _date.fromisoformat(end_str or start_str)
    from_ld = MagicMock()
    from_ld.getYear.return_value = s.year
    from_ld.getMonthValue.return_value = s.month
    from_ld.getDayOfMonth.return_value = s.day
    to_ld = MagicMock()
    to_ld.getYear.return_value = e.year
    to_ld.getMonthValue.return_value = e.month
    to_ld.getDayOfMonth.return_value = e.day
    exc = MagicMock()
    exc.getFromDate.return_value = from_ld
    exc.getToDate.return_value = to_ld
    return exc


class TestApplyToProjectRemoval:
    """Tests for the stale-vacation-removal path of _apply_to_project."""

    def _run(self, project, holiday_events, vacation_events, sync_start=None, sync_end=None, prune_before=None):
        LocalDate = _make_local_date_class()
        with patch.dict('sys.modules', {'jpype': MagicMock()}):
            import jpype
            jpype.JClass = MagicMock(return_value=LocalDate)
            return cc._apply_to_project(
                project, holiday_events, vacation_events, sync_start, sync_end, prune_before
            )

    def _make_resource(self, name, exceptions=None):
        res = MagicMock()
        res.getName.return_value = name
        cal = MagicMock()
        cal.getCalendarExceptions.return_value = list(exceptions or [])
        res.getCalendar.return_value = cal
        return res

    def test_stale_vacation_removed_when_absent_from_new_events(self):
        """An exception in the sync window that has no matching new event is removed."""
        from datetime import date
        stale = _make_exc_mock("2026-07-01", "2026-07-14")
        res = self._make_resource("Alice", exceptions=[stale])
        project = MagicMock()
        project.getDefaultCalendar.return_value = MagicMock()
        project.getResources.return_value = [res]

        # Sync window covers the stale exception; no new vacation for Alice
        _, n_v, n_v_rem, _, _ = self._run(
            project, [], [],
            sync_start=date(2026, 1, 1), sync_end=date(2026, 12, 31),
        )
        assert n_v == 0
        assert n_v_rem == 1
        res.getCalendar.return_value.getCalendarExceptions.return_value  # confirm accessed

    def test_vacation_outside_window_not_removed(self):
        """An exception outside the sync window is never touched."""
        from datetime import date
        old_exc = _make_exc_mock("2025-06-01", "2025-06-05")  # before sync window
        res = self._make_resource("Bob", exceptions=[old_exc])
        project = MagicMock()
        project.getDefaultCalendar.return_value = MagicMock()
        project.getResources.return_value = [res]

        _, n_v, n_v_rem, _, _ = self._run(
            project, [], [],
            sync_start=date(2026, 1, 1), sync_end=date(2026, 12, 31),
        )
        assert n_v_rem == 0  # exception is outside window — untouched

    def test_stale_removed_and_new_added_in_same_sync(self):
        """Old exception removed, new one added when dates changed in Confluence."""
        from datetime import date
        old_exc = _make_exc_mock("2026-08-01", "2026-08-07")
        res = self._make_resource("Carol", exceptions=[old_exc])
        project = MagicMock()
        project.getDefaultCalendar.return_value = MagicMock()
        project.getResources.return_value = [res]

        new_vacation = {"start": "2026-08-05", "end": "2026-08-12", "userName": "Carol"}
        _, n_v, n_v_rem, _, _ = self._run(
            project, [], [new_vacation],
            sync_start=date(2026, 1, 1), sync_end=date(2026, 12, 31),
        )
        assert n_v == 1      # new exception added
        assert n_v_rem == 1  # old exception removed

    def test_no_removal_without_sync_window(self):
        """When sync_start/sync_end are omitted, no exceptions are removed."""
        old_exc = _make_exc_mock("2026-07-01", "2026-07-14")
        res = self._make_resource("Dave", exceptions=[old_exc])
        project = MagicMock()
        project.getDefaultCalendar.return_value = MagicMock()
        project.getResources.return_value = [res]

        _, n_v, n_v_rem, _, _ = self._run(project, [], [])  # no sync window
        assert n_v_rem == 0

    def test_all_vacations_cleared_when_person_has_none_in_confluence(self):
        """Resource with multiple window exceptions and zero new events: all removed."""
        from datetime import date
        exc1 = _make_exc_mock("2026-06-01", "2026-06-05")
        exc2 = _make_exc_mock("2026-09-10", "2026-09-14")
        res = self._make_resource("Eve", exceptions=[exc1, exc2])
        project = MagicMock()
        project.getDefaultCalendar.return_value = MagicMock()
        project.getResources.return_value = [res]

        _, n_v, n_v_rem, _, _ = self._run(
            project, [], [],
            sync_start=date(2026, 1, 1), sync_end=date(2026, 12, 31),
        )
        assert n_v == 0
        assert n_v_rem == 2

    def test_expired_vacation_removed_via_prune_before(self):
        """Exception whose end is before prune_before is pruned regardless of sync window."""
        from datetime import date
        old_exc = _make_exc_mock("2025-03-01", "2025-03-10")  # finished 13 months ago
        res = self._make_resource("Frank", exceptions=[old_exc])
        project = MagicMock()
        project.getDefaultCalendar.return_value = MagicMock()
        project.getResources.return_value = [res]

        _, _, _, n_pruned, _ = self._run(
            project, [], [],
            prune_before=date(2026, 3, 20),
        )
        assert n_pruned == 1

    def test_expired_exception_on_default_calendar_pruned(self):
        """Expired public-holiday exceptions on the default calendar are pruned."""
        from datetime import date
        old_exc = _make_exc_mock("2025-01-01", "2025-01-01")
        default_cal = MagicMock()
        default_cal.getCalendarExceptions.return_value = [old_exc]
        project = MagicMock()
        project.getDefaultCalendar.return_value = default_cal
        project.getResources.return_value = []

        _, _, _, n_pruned, _ = self._run(
            project, [], [],
            prune_before=date(2026, 3, 20),
        )
        assert n_pruned == 1

    def test_non_expired_exception_not_pruned(self):
        """Exception newer than prune_before is never removed."""
        from datetime import date
        recent_exc = _make_exc_mock("2026-04-01", "2026-04-05")
        res = self._make_resource("Grace", exceptions=[recent_exc])
        project = MagicMock()
        project.getDefaultCalendar.return_value = MagicMock()
        project.getResources.return_value = [res]

        _, _, _, n_pruned, _ = self._run(
            project, [], [],
            prune_before=date(2026, 3, 20),
        )
        assert n_pruned == 0

    def test_no_prune_without_prune_before(self):
        """When prune_before is None, no expired entries are removed."""
        old_exc = _make_exc_mock("2024-12-01", "2024-12-31")
        res = self._make_resource("Heidi", exceptions=[old_exc])
        project = MagicMock()
        project.getDefaultCalendar.return_value = MagicMock()
        project.getResources.return_value = [res]

        _, _, _, n_pruned, _ = self._run(project, [], [])  # no prune_before
        assert n_pruned == 0

    def test_exception_without_end_falls_back_to_start_for_pruning(self):
        """When getToDate() returns None/raises, the start date is used for pruning."""
        from datetime import date

        # Build an exception whose getToDate() returns a mock whose _ld_to_date
        # will fail (all methods return None), so the code falls back to getFromDate().
        broken_to = MagicMock()
        broken_to.getYear.side_effect = AttributeError("no year")
        s = date(2025, 2, 1)
        from_ld = MagicMock()
        from_ld.getYear.return_value = s.year
        from_ld.getMonthValue.return_value = s.month
        from_ld.getDayOfMonth.return_value = s.day
        exc = MagicMock()
        exc.getFromDate.return_value = from_ld
        exc.getToDate.return_value = broken_to

        res = self._make_resource("Ivan", exceptions=[exc])
        project = MagicMock()
        project.getDefaultCalendar.return_value = MagicMock()
        project.getResources.return_value = [res]

        # prune_before > start date ? should be pruned using the fallback path
        _, _, _, n_pruned, _ = self._run(
            project, [], [],
            prune_before=date(2026, 3, 20),
        )
        assert n_pruned == 1

    def test_mixed_expired_and_future_only_expired_pruned(self):
        """Only the expired exception is removed; the future one survives."""
        from datetime import date
        expired_exc = _make_exc_mock("2025-01-10", "2025-01-15")  # finished >30 days ago
        future_exc  = _make_exc_mock("2026-07-01", "2026-07-10")  # still in the future
        res = self._make_resource("Judy", exceptions=[expired_exc, future_exc])
        project = MagicMock()
        project.getDefaultCalendar.return_value = MagicMock()
        project.getResources.return_value = [res]

        _, _, _, n_pruned, _ = self._run(
            project, [], [],
            prune_before=date(2026, 3, 20),
        )
        assert n_pruned == 1  # only the one before the cutoff

    def test_prune_and_remove_window_combined(self):
        """Expired pruning and sync-window removal operate independently and both count."""
        from datetime import date
        expired_exc = _make_exc_mock("2025-01-01", "2025-01-05")  # pruned
        stale_exc   = _make_exc_mock("2026-06-10", "2026-06-14")  # in window, no matching event
        res = self._make_resource("Karl", exceptions=[expired_exc, stale_exc])
        project = MagicMock()
        project.getDefaultCalendar.return_value = MagicMock()
        project.getResources.return_value = [res]

        _, _, n_v_rem, n_pruned, _ = self._run(
            project, [], [],
            sync_start=date(2026, 1, 1), sync_end=date(2026, 12, 31),
            prune_before=date(2026, 3, 20),
        )
        assert n_v_rem == 1
        assert n_pruned == 1

    def test_resource_with_no_calendar_and_no_events_skipped(self):
        """Resource with cal=None and no new events produces no new calendar."""
        res = MagicMock()
        res.getName.return_value = "Laura"
        res.getCalendar.return_value = None
        project = MagicMock()
        project.getDefaultCalendar.return_value = MagicMock()
        project.getResources.return_value = [res]

        n_h, n_v, n_v_rem, n_pruned, _ = self._run(project, [], [])
        assert n_v == 0
        # No calendar was created for the resource (no events to apply)
        res.setCalendar.assert_not_called()

    def test_holiday_added_to_default_calendar(self):
        """A single holiday event increments n_holidays and calls addCalendarException."""
        holiday = {"start": "2026-12-25", "end": "2026-12-25"}
        default_cal = MagicMock()
        project = MagicMock()
        project.getDefaultCalendar.return_value = default_cal
        project.getResources.return_value = []

        n_h, n_v, *_ = self._run(project, [holiday], [])
        assert n_h == 1
        default_cal.addCalendarException.assert_called_once()

    def test_vacation_matched_by_partial_username(self):
        """Vacation matched via substring fallback still increments n_vacations."""
        vacation = {"start": "2026-08-01", "end": "2026-08-05", "userName": "mike"}
        res = MagicMock()
        res.getName.return_value = "Mike Smith"  # "mike" is a substring of "mike smith"
        cal = MagicMock()
        cal.getCalendarExceptions.return_value = []
        res.getCalendar.return_value = cal
        project = MagicMock()
        project.getDefaultCalendar.return_value = MagicMock()
        project.getResources.return_value = [res]

        n_h, n_v, *_ = self._run(project, [], [vacation])
        assert n_v == 1

# 7. ConfluenceCalendarSync.run — early-exit branches
# ===========================================================================

class TestConfluenceCalendarSyncRun:
    """Tests for every branch of ConfluenceCalendarSync.run()."""

    def _sync(self):
        return cc.ConfluenceCalendarSync()
    
    def _mock_project_with_props(self, base_url, space_key):
        """Create a mock project and patch _get_enterprise_prop to return the given values."""
        project = MagicMock()
        def mock_get_prop(proj, key):
            if proj is project:
                if key == "CALENDAR Base URL":
                    return base_url
                elif key == "CALENDAR Space Key":
                    return space_key
            return None
        return project, mock_get_prop

    def test_missing_requests_shows_critical(self):
        with patch('integrations.confluence_calendar_integration._REQUESTS_OK', False), \
             patch('PyQt5.QtWidgets.QMessageBox') as qmb:
            self._sync().run(MagicMock(), parent_widget=None)
            qmb.critical.assert_called_once()

    def test_missing_playwright_shows_critical(self):
        with patch('integrations.confluence_calendar_integration._PLAYWRIGHT_OK', False), \
             patch('integrations.confluence_calendar_integration._REQUESTS_OK', True), \
             patch('PyQt5.QtWidgets.QMessageBox') as qmb:
            self._sync().run(MagicMock(), parent_widget=None)
            qmb.critical.assert_called_once()

    def test_none_project_shows_warning(self):
        with patch('integrations.confluence_calendar_integration._REQUESTS_OK', True), \
             patch('integrations.confluence_calendar_integration._PLAYWRIGHT_OK', True), \
             patch('PyQt5.QtWidgets.QMessageBox') as qmb:
            self._sync().run(None, parent_widget=None)
            qmb.warning.assert_called_once()

    def test_missing_base_url_shows_information(self):
        project, mock_prop = self._mock_project_with_props(None, "PROJ")
        with patch('integrations.confluence_calendar_integration._REQUESTS_OK', True), \
             patch('integrations.confluence_calendar_integration._PLAYWRIGHT_OK', True), \
             patch.object(cc, '_get_enterprise_prop', side_effect=mock_prop), \
             patch('PyQt5.QtWidgets.QMessageBox') as qmb:
            self._sync().run(project, parent_widget=None)
            qmb.information.assert_called_once()

    def test_missing_space_key_shows_information(self):
        project, mock_prop = self._mock_project_with_props("https://conf.example.com", None)
        with patch('integrations.confluence_calendar_integration._REQUESTS_OK', True), \
             patch('integrations.confluence_calendar_integration._PLAYWRIGHT_OK', True), \
             patch.object(cc, '_get_enterprise_prop', side_effect=mock_prop), \
             patch('PyQt5.QtWidgets.QMessageBox') as qmb:
            self._sync().run(project, parent_widget=None)
            qmb.information.assert_called_once()

    def test_auth_failure_shows_critical(self):
        project, mock_prop = self._mock_project_with_props("https://conf.example.com", "PROJ")
        with patch('integrations.confluence_calendar_integration._REQUESTS_OK', True), \
             patch('integrations.confluence_calendar_integration._PLAYWRIGHT_OK', True), \
             patch.object(cc, '_get_enterprise_prop', side_effect=mock_prop), \
             patch('integrations.confluence_calendar_integration._try_playwright_auth', return_value=None), \
             patch('PyQt5.QtWidgets.QMessageBox') as qmb:
            self._sync().run(project, parent_widget=None)
            qmb.critical.assert_called_once()

    def test_auth_exception_shows_critical(self):
        project, mock_prop = self._mock_project_with_props("https://conf.example.com", "PROJ")
        with patch('integrations.confluence_calendar_integration._REQUESTS_OK', True), \
             patch('integrations.confluence_calendar_integration._PLAYWRIGHT_OK', True), \
             patch.object(cc, '_get_enterprise_prop', side_effect=mock_prop), \
             patch('integrations.confluence_calendar_integration._try_playwright_auth', side_effect=RuntimeError("timeout")), \
             patch('PyQt5.QtWidgets.QMessageBox') as qmb:
            self._sync().run(project, parent_widget=None)
            qmb.critical.assert_called_once()

    def test_no_calendars_found_shows_information(self):
        project, mock_prop = self._mock_project_with_props("https://conf.example.com", "PROJ")
        session = MagicMock()
        with patch('integrations.confluence_calendar_integration._REQUESTS_OK', True), \
             patch('integrations.confluence_calendar_integration._PLAYWRIGHT_OK', True), \
             patch.object(cc, '_get_enterprise_prop', side_effect=mock_prop), \
             patch('integrations.confluence_calendar_integration._try_playwright_auth', return_value=(session, "Test User")), \
             patch('integrations.confluence_calendar_integration._fetch_subcalendars', return_value=[]), \
             patch('integrations.confluence_calendar_integration._filter_relevant', return_value=[]), \
             patch('PyQt5.QtWidgets.QMessageBox') as qmb:
            self._sync().run(project, parent_widget=None)
            qmb.information.assert_called_once()

    def test_happy_path_shows_summary(self):
        project, mock_prop = self._mock_project_with_props("https://conf.example.com", "PROJ")
        cal_entry = {"id": "cal-1", "name": "Holidays", "type": "custom"}
        session = MagicMock()
        with patch('integrations.confluence_calendar_integration._REQUESTS_OK', True), \
             patch('integrations.confluence_calendar_integration._PLAYWRIGHT_OK', True), \
             patch('integrations.confluence_calendar_integration._is_debug', return_value=False), \
             patch.object(cc, '_get_enterprise_prop', side_effect=mock_prop), \
             patch('integrations.confluence_calendar_integration._try_playwright_auth', return_value=(session, "Alice")), \
             patch('integrations.confluence_calendar_integration._fetch_subcalendars', return_value=[cal_entry]), \
             patch('integrations.confluence_calendar_integration._filter_relevant', return_value=[cal_entry]), \
             patch('integrations.confluence_calendar_integration._fetch_events', return_value=[{"start": "2025-12-25", "end": "2025-12-25"}]), \
             patch('integrations.confluence_calendar_integration._apply_to_project', return_value=(1, 0, 0, 0, 0)):
            result = self._sync().run(project, parent_widget=None)
            summary_msg = result
            assert "Alice" in summary_msg
            assert "1" in summary_msg

    def test_calendar_fetch_error_included_in_summary(self):
        project, mock_prop = self._mock_project_with_props("https://conf.example.com", "PROJ")
        cal_entry = {"id": "cal-1", "name": "Holidays", "type": "custom"}
        session = MagicMock()
        with patch('integrations.confluence_calendar_integration._REQUESTS_OK', True), \
             patch('integrations.confluence_calendar_integration._PLAYWRIGHT_OK', True), \
             patch('integrations.confluence_calendar_integration._is_debug', return_value=False), \
             patch.object(cc, '_get_enterprise_prop', side_effect=mock_prop), \
             patch('integrations.confluence_calendar_integration._try_playwright_auth', return_value=(session, "Alice")), \
             patch('integrations.confluence_calendar_integration._fetch_subcalendars', return_value=[cal_entry]), \
             patch('integrations.confluence_calendar_integration._filter_relevant', return_value=[cal_entry]), \
             patch('integrations.confluence_calendar_integration._fetch_events', side_effect=ConnectionError("network error")), \
             patch('integrations.confluence_calendar_integration._apply_to_project', return_value=(0, 0, 0, 0, 0)):
            result = self._sync().run(project, parent_widget=None)
            summary_msg = result
            assert "Holidays" in summary_msg

    def test_fetch_subcalendars_exception_shows_critical(self):
        project, mock_prop = self._mock_project_with_props("https://conf.example.com", "PROJ")
        session = MagicMock()
        with patch('integrations.confluence_calendar_integration._REQUESTS_OK', True), \
             patch('integrations.confluence_calendar_integration._PLAYWRIGHT_OK', True), \
             patch.object(cc, '_get_enterprise_prop', side_effect=mock_prop), \
             patch('integrations.confluence_calendar_integration._try_playwright_auth', return_value=(session, "Alice")), \
             patch('integrations.confluence_calendar_integration._fetch_subcalendars', side_effect=RuntimeError("HTTP 500")), \
             patch('PyQt5.QtWidgets.QMessageBox') as qmb:
            self._sync().run(project, parent_widget=None)
            qmb.critical.assert_called_once()

    def test_history_manager_push_all_called_before_apply(self):
        """history_manager.push_all() is called once before _apply_to_project."""
        project, mock_prop = self._mock_project_with_props("https://conf.example.com", "PROJ")
        cal_entry = {"id": "cal-1", "name": "Holidays", "type": "custom"}
        session = MagicMock()
        history = MagicMock()
        with patch('integrations.confluence_calendar_integration._REQUESTS_OK', True), \
             patch('integrations.confluence_calendar_integration._PLAYWRIGHT_OK', True), \
             patch('integrations.confluence_calendar_integration._is_debug', return_value=False), \
             patch.object(cc, '_get_enterprise_prop', side_effect=mock_prop), \
             patch('integrations.confluence_calendar_integration._try_playwright_auth', return_value=(session, "Alice")), \
             patch('integrations.confluence_calendar_integration._fetch_subcalendars', return_value=[cal_entry]), \
             patch('integrations.confluence_calendar_integration._filter_relevant', return_value=[cal_entry]), \
             patch('integrations.confluence_calendar_integration._fetch_events', return_value=[]), \
             patch('integrations.confluence_calendar_integration._apply_to_project', return_value=(0, 0, 0, 0, 0)), \
             patch('PyQt5.QtWidgets.QMessageBox'):
            self._sync().run(project, parent_widget=None, history_manager=history)
        history.push_all.assert_called_once()

    def test_history_manager_not_called_when_auth_fails(self):
        """push_all() is NOT called when authentication fails (no changes made)."""
        project, mock_prop = self._mock_project_with_props("https://conf.example.com", "PROJ")
        history = MagicMock()
        with patch('integrations.confluence_calendar_integration._REQUESTS_OK', True), \
             patch('integrations.confluence_calendar_integration._PLAYWRIGHT_OK', True), \
             patch.object(cc, '_get_enterprise_prop', side_effect=mock_prop), \
             patch('integrations.confluence_calendar_integration._try_playwright_auth', return_value=None), \
             patch('PyQt5.QtWidgets.QMessageBox'):
            self._sync().run(project, parent_widget=None, history_manager=history)
        history.push_all.assert_not_called()

    def test_history_manager_none_is_safe(self):
        """Passing history_manager=None (default) does not raise."""
        project, mock_prop = self._mock_project_with_props("https://conf.example.com", "PROJ")
        cal_entry = {"id": "cal-1", "name": "Holidays", "type": "custom"}
        session = MagicMock()
        with patch('integrations.confluence_calendar_integration._REQUESTS_OK', True), \
             patch('integrations.confluence_calendar_integration._PLAYWRIGHT_OK', True), \
             patch('integrations.confluence_calendar_integration._is_debug', return_value=False), \
             patch.object(cc, '_get_enterprise_prop', side_effect=mock_prop), \
             patch('integrations.confluence_calendar_integration._try_playwright_auth', return_value=(session, "Alice")), \
             patch('integrations.confluence_calendar_integration._fetch_subcalendars', return_value=[cal_entry]), \
             patch('integrations.confluence_calendar_integration._filter_relevant', return_value=[cal_entry]), \
             patch('integrations.confluence_calendar_integration._fetch_events', return_value=[]), \
             patch('integrations.confluence_calendar_integration._apply_to_project', return_value=(0, 0, 0, 0, 0)), \
             patch('PyQt5.QtWidgets.QMessageBox'):
            # Should not raise
            self._sync().run(project, parent_widget=None, history_manager=None)

    def test_summary_shows_pruned_count_when_nonzero(self):
        """Summary message includes the pruned count line when entries were removed."""
        project, mock_prop = self._mock_project_with_props("https://conf.example.com", "PROJ")
        cal_entry = {"id": "cal-1", "name": "Holidays", "type": "custom"}
        session = MagicMock()
        with patch('integrations.confluence_calendar_integration._REQUESTS_OK', True), \
             patch('integrations.confluence_calendar_integration._PLAYWRIGHT_OK', True), \
             patch('integrations.confluence_calendar_integration._is_debug', return_value=False), \
             patch.object(cc, '_get_enterprise_prop', side_effect=mock_prop), \
             patch('integrations.confluence_calendar_integration._try_playwright_auth', return_value=(session, "Alice")), \
             patch('integrations.confluence_calendar_integration._fetch_subcalendars', return_value=[cal_entry]), \
             patch('integrations.confluence_calendar_integration._filter_relevant', return_value=[cal_entry]), \
             patch('integrations.confluence_calendar_integration._fetch_events', return_value=[]), \
             patch('integrations.confluence_calendar_integration._apply_to_project', return_value=(0, 0, 0, 3, 0)):
            result = self._sync().run(project, parent_widget=None)
        summary_msg = result
        assert "3" in summary_msg
        assert "expired" in summary_msg.lower()


# ===========================================================================
# 7. _validate_base_url
# ===========================================================================

class TestValidateBaseUrl:
    def test_valid_https_url_accepted(self):
        result = cc._validate_base_url("https://confluence.example.com")
        assert result == "https://confluence.example.com"

    def test_https_url_with_path_accepted(self):
        result = cc._validate_base_url("https://confluence.example.com/wiki")
        assert result == "https://confluence.example.com/wiki"

    def test_http_url_rejected(self):
        import pytest
        with pytest.raises(ValueError) as exc:
            cc._validate_base_url("http://confluence.example.com")
        assert "HTTPS" in str(exc.value)

    def test_no_scheme_rejected(self):
        import pytest
        with pytest.raises(ValueError) as exc:
            cc._validate_base_url("confluence.example.com")
        assert "HTTPS" in str(exc.value)

    def test_ftp_scheme_rejected(self):
        import pytest
        with pytest.raises(ValueError) as exc:
            cc._validate_base_url("ftp://confluence.example.com")
        assert "HTTPS" in str(exc.value)

    def test_empty_string_rejected(self):
        import pytest
        with pytest.raises(ValueError):
            cc._validate_base_url("")

    def test_malformed_url_rejected(self):
        import pytest
        with pytest.raises(ValueError):
            cc._validate_base_url("https://")


# ===========================================================================
# 8. _restrict_file_permissions (platform-specific)
# ===========================================================================

class TestRestrictFilePermissions:
    def test_windows_icacls_called(self, tmp_path):
        test_file = tmp_path / "test.json"
        test_file.write_text("{}")
        with patch('sys.platform', 'win32'), \
             patch('subprocess.run') as mock_run, \
             patch('getpass.getuser', return_value='testuser'):
            cc._restrict_file_permissions(test_file)
            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            assert 'icacls' in args
            assert str(test_file) in args

    def test_posix_chmod_called(self, tmp_path):
        test_file = tmp_path / "test.json"
        test_file.write_text("{}")
        with patch('sys.platform', 'linux'), \
             patch('pathlib.Path.chmod') as mock_chmod:
            cc._restrict_file_permissions(test_file)
            mock_chmod.assert_called_once_with(0o600)

    def test_windows_exception_silently_ignored(self, tmp_path):
        test_file = tmp_path / "test.json"
        test_file.write_text("{}")
        with patch('sys.platform', 'win32'), \
             patch('subprocess.run', side_effect=PermissionError("access denied")), \
             patch('getpass.getuser', return_value='testuser'):
            cc._restrict_file_permissions(test_file)  # must not raise

    def test_posix_exception_silently_ignored(self, tmp_path):
        test_file = tmp_path / "test.json"
        test_file.write_text("{}")
        with patch('sys.platform', 'linux'), \
             patch('pathlib.Path.chmod', side_effect=OSError("permission denied")):
            cc._restrict_file_permissions(test_file)  # must not raise


# ===========================================================================
# 9. Resource auto-creation
# ===========================================================================

class TestResourceAutoCreation:
    def _run(self, project, vacation_events):
        LocalDate = _make_local_date_class()
        with patch.dict('sys.modules', {'jpype': MagicMock()}):
            import jpype
            jpype.JClass = MagicMock(return_value=LocalDate)
            return cc._apply_to_project(project, [], vacation_events)

    def test_auto_creates_resource_for_unmatched_username(self):
        """When a vacation userName has no matching resource, one is auto-created."""
        project = MagicMock()
        project.getDefaultCalendar.return_value = MagicMock()
        project.getResources.return_value = []  # no existing resources
        new_res = MagicMock()
        new_cal = MagicMock()
        new_cal.getCalendarExceptions.return_value = []
        new_res.getCalendar.return_value = new_cal
        project.addResource.return_value = new_res

        vacation = {"start": "2026-07-01", "end": "2026-07-07", "userName": "John Doe"}
        n_h, n_v, n_v_rem, n_pruned, n_res_new = self._run(project, [vacation])

        assert n_res_new == 1
        project.addResource.assert_called_once()
        new_res.setName.assert_called_once_with("John Doe")
        assert n_v == 1  # vacation was applied to the new resource

    def test_multiple_vacations_for_new_resource_create_one(self):
        """Multiple vacation events for the same unmatched userName create only one resource."""
        project = MagicMock()
        project.getDefaultCalendar.return_value = MagicMock()
        project.getResources.return_value = []
        new_res = MagicMock()
        new_cal = MagicMock()
        new_cal.getCalendarExceptions.return_value = []
        new_res.getCalendar.return_value = new_cal
        project.addResource.return_value = new_res

        vacations = [
            {"start": "2026-07-01", "end": "2026-07-07", "userName": "Alice"},
            {"start": "2026-08-01", "end": "2026-08-05", "userName": "Alice"},
        ]
        n_h, n_v, n_v_rem, n_pruned, n_res_new = self._run(project, vacations)

        assert n_res_new == 1  # only one resource created
        assert n_v == 2  # both vacations applied

    def test_blank_username_not_auto_created(self):
        """Vacation events with blank/empty userName are skipped; no resource created."""
        project = MagicMock()
        project.getDefaultCalendar.return_value = MagicMock()
        project.getResources.return_value = []

        vacation = {"start": "2026-07-01", "end": "2026-07-07", "userName": "   "}
        n_h, n_v, n_v_rem, n_pruned, n_res_new = self._run(project, [vacation])

        assert n_res_new == 0
        assert n_v == 0
        project.addResource.assert_not_called()

    def test_existing_resource_not_duplicated(self):
        """When a resource already exists, no new resource is created."""
        existing_res = MagicMock()
        existing_res.getName.return_value = "Bob"
        existing_cal = MagicMock()
        existing_cal.getCalendarExceptions.return_value = []
        existing_res.getCalendar.return_value = existing_cal

        project = MagicMock()
        project.getDefaultCalendar.return_value = MagicMock()
        project.getResources.return_value = [existing_res]

        vacation = {"start": "2026-07-01", "end": "2026-07-07", "userName": "Bob"}
        n_h, n_v, n_v_rem, n_pruned, n_res_new = self._run(project, [vacation])

        assert n_res_new == 0  # no new resource created
        assert n_v == 1  # vacation applied to existing resource
        project.addResource.assert_not_called()


# ===========================================================================
# 10. _playwright_session
# ===========================================================================

class TestPlaywrightSession:
    def test_creates_requests_session_with_cookies(self):
        ctx = MagicMock()
        ctx.cookies.return_value = [
            {"name": "JSESSIONID", "value": "abc123"},
            {"name": "auth_token", "value": "xyz789"},
        ]
        base_url = "https://confluence.example.com"

        with patch.object(cc._requests, 'Session') as mock_session_cls:
            mock_session = MagicMock()
            mock_session_cls.return_value = mock_session
            session = cc._playwright_session(ctx, base_url)

            # Verify cookies were set
            assert mock_session.cookies.set.call_count == 2

    def test_sets_user_agent_header(self):
        ctx = MagicMock()
        ctx.cookies.return_value = []
        base_url = "https://confluence.example.com"

        with patch.object(cc._requests, 'Session') as mock_session_cls:
            mock_session = MagicMock()
            mock_session_cls.return_value = mock_session
            session = cc._playwright_session(ctx, base_url)

            # Verify headers were updated
            mock_session.headers.update.assert_called_once()
            headers = mock_session.headers.update.call_args[0][0]
            assert "User-Agent" in headers
            assert "Mozilla" in headers["User-Agent"]


# ===========================================================================
# 11. clear_saved_session
# ===========================================================================

class TestClearSavedSession:
    def test_deletes_state_file_when_present(self, tmp_path):
        fake_state = tmp_path / ".confluence_playwright_state.json"
        fake_state.write_text("{}")
        with patch.object(cc, '_STATE_FILE', fake_state):
            cc.clear_saved_session()
        assert not fake_state.exists()

    def test_no_error_when_file_absent(self, tmp_path):
        fake_state = tmp_path / ".confluence_playwright_state.json"
        with patch.object(cc, '_STATE_FILE', fake_state):
            cc.clear_saved_session()  # must not raise


# ===========================================================================
# 12. Invalid base URL rejection in ConfluenceCalendarSync.run
# ===========================================================================

class TestConfluenceCalendarSyncInvalidUrl:
    def _sync(self):
        return cc.ConfluenceCalendarSync()

    def test_non_https_base_url_shows_critical(self):
        project = MagicMock()
        with patch('integrations.confluence_calendar_integration._REQUESTS_OK', True), \
             patch('integrations.confluence_calendar_integration._PLAYWRIGHT_OK', True), \
             patch.object(cc, '_get_enterprise_prop', side_effect=lambda p, k: "http://confluence.example.com" if k == "CALENDAR Base URL" else "PROJ"), \
             patch('PyQt5.QtWidgets.QMessageBox') as qmb:
            self._sync().run(project, parent_widget=None)
            qmb.critical.assert_called_once()
            msg = qmb.critical.call_args[0][2]
            assert "HTTPS" in msg

    def test_malformed_base_url_shows_critical(self):
        project = MagicMock()
        with patch('integrations.confluence_calendar_integration._REQUESTS_OK', True), \
             patch('integrations.confluence_calendar_integration._PLAYWRIGHT_OK', True), \
             patch.object(cc, '_get_enterprise_prop', side_effect=lambda p, k: "not-a-valid-url" if k == "CALENDAR Base URL" else "PROJ"), \
             patch('PyQt5.QtWidgets.QMessageBox') as qmb:
            self._sync().run(project, parent_widget=None)
            qmb.critical.assert_called_once()
            msg = qmb.critical.call_args[0][2]
            assert "valid URL" in msg or "HTTPS" in msg  # either error message is acceptable


# ===========================================================================
# 13. Partial-match resource rename
# ===========================================================================

class TestPartialMatchRename:
    """Partial matches should rename the short project resource name to the full
    Confluence display name, and later events for the same name should hit exact
    match (no double-rename, no extra resource creation)."""

    def _run(self, project, vacation_events):
        LocalDate = _make_local_date_class()
        with patch.dict('sys.modules', {'jpype': MagicMock()}):
            import jpype
            jpype.JClass = MagicMock(return_value=LocalDate)
            return cc._apply_to_project(project, [], vacation_events)

    def _res(self, name):
        res = MagicMock()
        res.getName.return_value = name
        cal = MagicMock()
        cal.getCalendarExceptions.return_value = []
        res.getCalendar.return_value = cal
        return res

    def test_short_resource_renamed_to_full_confluence_name(self):
        """Resource 'Yassine' is renamed to 'Trabelsi, Yassine' on partial match."""
        res = self._res("Yassine")
        project = MagicMock()
        project.getDefaultCalendar.return_value = MagicMock()
        project.getResources.return_value = [res]

        vacation = {"start": "2026-05-04", "end": "2026-05-15", "userName": "Trabelsi, Yassine"}
        n_h, n_v, *_ = self._run(project, [vacation])

        assert n_v == 1
        res.setName.assert_called_once_with("Trabelsi, Yassine")

    def test_multiple_vacations_for_same_person_no_duplicate_rename(self):
        """Multiple vacation events for the same user trigger setName only once."""
        res = self._res("Yassine")
        project = MagicMock()
        project.getDefaultCalendar.return_value = MagicMock()
        project.getResources.return_value = [res]

        vacations = [
            {"start": "2026-05-04", "end": "2026-05-15", "userName": "Trabelsi, Yassine"},
            {"start": "2026-08-01", "end": "2026-08-07", "userName": "Trabelsi, Yassine"},
        ]
        n_h, n_v, *_ = self._run(project, vacations)

        assert n_v == 2
        # First event triggers rename; subsequent events are exact matches — setName once
        res.setName.assert_called_once_with("Trabelsi, Yassine")

    def test_no_rename_when_full_name_already_exists_as_resource(self):
        """If the full Confluence name already maps to another resource, no rename occurs."""
        res_short = self._res("Yassine")
        res_full  = self._res("Trabelsi, Yassine")
        project = MagicMock()
        project.getDefaultCalendar.return_value = MagicMock()
        project.getResources.return_value = [res_short, res_full]

        # "Trabelsi, Yassine" is an exact match for res_full ? no partial path taken
        vacation = {"start": "2026-05-04", "end": "2026-05-15", "userName": "Trabelsi, Yassine"}
        n_h, n_v, *_ = self._run(project, [vacation])

        assert n_v == 1
        res_short.setName.assert_not_called()
        res_full.setName.assert_not_called()

    def test_ambiguous_partial_no_rename_when_new_name_already_taken(self):
        """When the Confluence full name is already a key in name_to_res, skip rename."""
        # Two resources whose names would both partial-match "Smith"
        res_a = self._res("Smith, Alice")
        res_b = self._res("Smith, Bob")
        project = MagicMock()
        project.getDefaultCalendar.return_value = MagicMock()
        project.getResources.return_value = [res_a, res_b]

        # "Smith, Alice" is already in name_to_res — rename of res_a would collide
        vacation = {"start": "2026-06-01", "end": "2026-06-05", "userName": "Smith, Alice"}
        # This is an exact match, so no rename is triggered at all
        n_h, n_v, *_ = self._run(project, [vacation])

        assert n_v == 1
        res_a.setName.assert_not_called()
        res_b.setName.assert_not_called()


# ===========================================================================
# 14. Semicolon normalisation
# ===========================================================================

class TestSemicolonNormalisation:
    """Usernames with ';' as surname/forename separator are normalised to ',' before
    any matching or resource creation."""

    def _run(self, project, vacation_events):
        LocalDate = _make_local_date_class()
        with patch.dict('sys.modules', {'jpype': MagicMock()}):
            import jpype
            jpype.JClass = MagicMock(return_value=LocalDate)
            return cc._apply_to_project(project, [], vacation_events)

    def test_semicolon_username_matched_against_comma_resource(self):
        """'Smith; John' is normalised to 'Smith, John' and matched exactly."""
        res = MagicMock()
        res.getName.return_value = "Smith, John"
        cal = MagicMock()
        cal.getCalendarExceptions.return_value = []
        res.getCalendar.return_value = cal
        project = MagicMock()
        project.getDefaultCalendar.return_value = MagicMock()
        project.getResources.return_value = [res]

        vacation = {"start": "2026-06-01", "end": "2026-06-05", "userName": "Smith; John"}
        n_h, n_v, n_v_rem, n_pruned, n_res_new = self._run(project, [vacation])

        assert n_v == 1
        assert n_res_new == 0          # no new resource — exact match after normalisation
        project.addResource.assert_not_called()

    def test_semicolon_username_new_resource_stored_with_comma(self):
        """When no match exists, a new resource is created with the normalised name."""
        project = MagicMock()
        project.getDefaultCalendar.return_value = MagicMock()
        project.getResources.return_value = []
        new_res = MagicMock()
        new_cal = MagicMock()
        new_cal.getCalendarExceptions.return_value = []
        new_res.getCalendar.return_value = new_cal
        project.addResource.return_value = new_res

        vacation = {"start": "2026-07-01", "end": "2026-07-07", "userName": "Doe; Jane"}
        n_h, n_v, n_v_rem, n_pruned, n_res_new = self._run(project, [vacation])

        assert n_res_new == 1
        # Resource must be stored with comma, not semicolon
        new_res.setName.assert_called_once_with("Doe, Jane")

    def test_trailing_whitespace_stripped_from_username(self):
        """Leading/trailing whitespace in usernames is stripped before matching."""
        res = MagicMock()
        res.getName.return_value = "Alice"
        cal = MagicMock()
        cal.getCalendarExceptions.return_value = []
        res.getCalendar.return_value = cal
        project = MagicMock()
        project.getDefaultCalendar.return_value = MagicMock()
        project.getResources.return_value = [res]

        vacation = {"start": "2026-06-01", "end": "2026-06-05", "userName": "  Alice  "}
        n_h, n_v, n_v_rem, n_pruned, n_res_new = self._run(project, [vacation])

        assert n_v == 1
        assert n_res_new == 0
        project.addResource.assert_not_called()

    def test_semicolon_with_spaces_normalised(self):
        """'Smith ; John' normalises to 'Smith , John' (spaces preserved around comma)."""
        project = MagicMock()
        project.getDefaultCalendar.return_value = MagicMock()
        project.getResources.return_value = []
        new_res = MagicMock()
        new_cal = MagicMock()
        new_cal.getCalendarExceptions.return_value = []
        new_res.getCalendar.return_value = new_cal
        project.addResource.return_value = new_res

        vacation = {"start": "2026-07-01", "end": "2026-07-07", "userName": "Smith ; John"}
        self._run(project, [vacation])

        call_name = new_res.setName.call_args[0][0]
        assert ";" not in call_name
        assert "," in call_name


# ===========================================================================
# 15. Calendar UID assigned before setCalendar
# ===========================================================================

class TestCalendarUIDBeforeSetCalendar:
    """A newly created calendar must have a non-null UID before res.setCalendar() is
    called, so the resource's CALENDAR_UNIQUE_ID is stored correctly and
    _remove_unassigned_enterprise_resources does not delete the resource at save time."""

    def _run(self, project, vacation_events):
        LocalDate = _make_local_date_class()
        with patch.dict('sys.modules', {'jpype': MagicMock()}):
            import jpype
            jpype.JClass = MagicMock(return_value=LocalDate)
            return cc._apply_to_project(project, [], vacation_events)

    def test_uid_assigned_to_new_calendar_before_setcalendar(self):
        """When the created calendar has getUniqueID() == None, setUniqueID is called."""
        res = MagicMock()
        res.getName.return_value = "New Person"
        res.getCalendarUniqueID.return_value = None
        res.getCalendar.return_value = None

        new_cal = MagicMock()
        new_cal.getUniqueID.return_value = None   # new calendar has no UID yet

        project = MagicMock()
        project.getDefaultCalendar.return_value = MagicMock()
        project.getResources.return_value = [res]
        project.addCalendar.return_value = new_cal
        project.getCalendarByName.return_value = None
        project.getCalendars.return_value = []

        # Stub java.lang.Integer so the UID assignment succeeds
        mock_jint = MagicMock(side_effect=lambda v: v)
        with patch.dict('sys.modules', {'java': MagicMock(), 'java.lang': MagicMock(Integer=mock_jint)}):
            vacation = {"start": "2026-07-01", "end": "2026-07-07", "userName": "New Person"}
            self._run(project, [vacation])

        new_cal.setUniqueID.assert_called_once()
        res.setCalendar.assert_called_once_with(new_cal)

    def test_no_uid_assignment_when_calendar_already_has_uid(self):
        """When the calendar already has a UID (reused orphan), setUniqueID is not called."""
        res = MagicMock()
        res.getName.return_value = "Existing Person"
        res.getCalendarUniqueID.return_value = None
        res.getCalendar.return_value = None

        orphan_cal = MagicMock()
        orphan_cal.getUniqueID.return_value = 42   # already has a UID

        project = MagicMock()
        project.getDefaultCalendar.return_value = MagicMock()
        project.getResources.return_value = [res]
        project.getCalendarByName.return_value = orphan_cal
        project.getCalendars.return_value = []

        vacation = {"start": "2026-07-01", "end": "2026-07-07", "userName": "Existing Person"}
        self._run(project, [vacation])

        orphan_cal.setUniqueID.assert_not_called()
        res.setCalendar.assert_called_once_with(orphan_cal)


# ===========================================================================
# 16. _autofill_microsoft_sso
# ===========================================================================

class TestAutofillMicrosoftSso:
    """Tests for the Microsoft AAD login auto-fill helper."""

    def test_returns_false_when_not_microsoft_url(self):
        """Non-Microsoft URLs are ignored immediately."""
        page = MagicMock()
        page.url = "https://confluence.example.com/login"
        result = cc._autofill_microsoft_sso(page, "user@example.com", "password")
        assert result is False

    def test_returns_true_when_fill_succeeds(self):
        """Returns True after successfully filling email and password."""
        page = MagicMock()
        page.url = "https://login.microsoftonline.com/tenant/oauth2/v2.0/authorize"
        result = cc._autofill_microsoft_sso(page, "user@example.com", "password")
        assert result is True

    def test_returns_false_when_email_selector_times_out(self):
        """Returns False gracefully when the email field is not found."""
        page = MagicMock()
        page.url = "https://login.microsoftonline.com/tenant/oauth2"
        page.wait_for_selector.side_effect = Exception("Timeout waiting for selector")
        result = cc._autofill_microsoft_sso(page, "user@example.com", "password")
        assert result is False

    def test_fills_email_field(self):
        """Email address is filled into the email input."""
        page = MagicMock()
        page.url = "https://login.microsoftonline.com/tenant/oauth2"
        cc._autofill_microsoft_sso(page, "user@example.com", "secret")
        page.fill.assert_any_call("input[type='email'], #i0116", "user@example.com")

    def test_fills_password_field(self):
        """Password is filled into the password input."""
        page = MagicMock()
        page.url = "https://login.microsoftonline.com/tenant/oauth2"
        cc._autofill_microsoft_sso(page, "user@example.com", "mysecret")
        page.fill.assert_any_call("input[type='password'], #i0118", "mysecret")


# ===========================================================================
# 17. ConfluenceCalendarSync.run — settings_manager / KeePass auto-fill
# ===========================================================================

class TestSyncRunWithSettingsManager:
    """Tests for the settings_manager param of ConfluenceCalendarSync.run()."""

    def _sync(self):
        return cc.ConfluenceCalendarSync()

    def _mock_project_with_props(self, base_url, space_key):
        project = MagicMock()
        def mock_get_prop(proj, key):
            if proj is project:
                if key == "CALENDAR Base URL":
                    return base_url
                elif key == "CALENDAR Space Key":
                    return space_key
            return None
        return project, mock_get_prop

    def _base_patches(self, mock_prop, session="default"):
        """Context manager stack for a minimal happy-path run."""
        from contextlib import ExitStack
        s = session if session != "default" else MagicMock()
        return s, [
            ('confluence_calendar._REQUESTS_OK', True),
            ('confluence_calendar._PLAYWRIGHT_OK', True),
            ('confluence_calendar._is_debug', False),
        ]

    def test_settings_manager_none_passes_no_creds(self):
        """When settings_manager=None, auth is called with keepass_creds=None."""
        project, mock_prop = self._mock_project_with_props("https://conf.example.com", "PROJ")
        session = MagicMock()
        with patch('integrations.confluence_calendar_integration._REQUESTS_OK', True), \
             patch('integrations.confluence_calendar_integration._PLAYWRIGHT_OK', True), \
             patch('integrations.confluence_calendar_integration._is_debug', return_value=False), \
             patch.object(cc, '_get_enterprise_prop', side_effect=mock_prop), \
             patch('integrations.confluence_calendar_integration._try_playwright_auth', return_value=(session, "Alice")) as mock_auth, \
             patch('integrations.confluence_calendar_integration._fetch_subcalendars', return_value=[]), \
             patch('integrations.confluence_calendar_integration._filter_relevant', return_value=[]), \
             patch('PyQt5.QtWidgets.QMessageBox'):
            self._sync().run(project, parent_widget=None, settings_manager=None)
        mock_auth.assert_called_once_with("https://conf.example.com", keepass_creds=None)

    def test_keepass_creds_passed_when_configured_and_unlocked(self):
        """Username+password from KeePass are forwarded when DB is open and entry exists."""
        project, mock_prop = self._mock_project_with_props("https://conf.example.com", "PROJ")
        session = MagicMock()
        sm = MagicMock()
        sm.get_confluence_keepass_entry.return_value = "Confluence/prod"
        sm.is_keepass_unlocked.return_value = True
        entry = MagicMock(username="user@example.com", password="secret")
        sm.find_keepass_entry.return_value = entry
        with patch('integrations.confluence_calendar_integration._REQUESTS_OK', True), \
             patch('integrations.confluence_calendar_integration._PLAYWRIGHT_OK', True), \
             patch('integrations.confluence_calendar_integration._is_debug', return_value=False), \
             patch.object(cc, '_get_enterprise_prop', side_effect=mock_prop), \
             patch('integrations.confluence_calendar_integration._try_playwright_auth', return_value=(session, "Alice")) as mock_auth, \
             patch('integrations.confluence_calendar_integration._fetch_subcalendars', return_value=[]), \
             patch('integrations.confluence_calendar_integration._filter_relevant', return_value=[]), \
             patch('PyQt5.QtWidgets.QMessageBox'):
            self._sync().run(project, parent_widget=None, settings_manager=sm)
        mock_auth.assert_called_once_with(
            "https://conf.example.com",
            keepass_creds=("user@example.com", "secret"),
        )

    def test_no_creds_when_db_locked(self):
        """No credentials forwarded when KeePass DB is locked."""
        project, mock_prop = self._mock_project_with_props("https://conf.example.com", "PROJ")
        session = MagicMock()
        sm = MagicMock()
        sm.get_confluence_keepass_entry.return_value = "Confluence/prod"
        sm.is_keepass_unlocked.return_value = False
        with patch('integrations.confluence_calendar_integration._REQUESTS_OK', True), \
             patch('integrations.confluence_calendar_integration._PLAYWRIGHT_OK', True), \
             patch('integrations.confluence_calendar_integration._is_debug', return_value=False), \
             patch.object(cc, '_get_enterprise_prop', side_effect=mock_prop), \
             patch('integrations.confluence_calendar_integration._try_playwright_auth', return_value=(session, "Alice")) as mock_auth, \
             patch('integrations.confluence_calendar_integration._fetch_subcalendars', return_value=[]), \
             patch('integrations.confluence_calendar_integration._filter_relevant', return_value=[]), \
             patch('PyQt5.QtWidgets.QMessageBox'):
            self._sync().run(project, parent_widget=None, settings_manager=sm)
        mock_auth.assert_called_once_with("https://conf.example.com", keepass_creds=None)

    def test_no_creds_when_entry_not_found(self):
        """No credentials forwarded when configured entry title has no DB match."""
        project, mock_prop = self._mock_project_with_props("https://conf.example.com", "PROJ")
        session = MagicMock()
        sm = MagicMock()
        sm.get_confluence_keepass_entry.return_value = "Confluence/prod"
        sm.is_keepass_unlocked.return_value = True
        sm.find_keepass_entry.return_value = None
        with patch('integrations.confluence_calendar_integration._REQUESTS_OK', True), \
             patch('integrations.confluence_calendar_integration._PLAYWRIGHT_OK', True), \
             patch('integrations.confluence_calendar_integration._is_debug', return_value=False), \
             patch.object(cc, '_get_enterprise_prop', side_effect=mock_prop), \
             patch('integrations.confluence_calendar_integration._try_playwright_auth', return_value=(session, "Alice")) as mock_auth, \
             patch('integrations.confluence_calendar_integration._fetch_subcalendars', return_value=[]), \
             patch('integrations.confluence_calendar_integration._filter_relevant', return_value=[]), \
             patch('PyQt5.QtWidgets.QMessageBox'):
            self._sync().run(project, parent_widget=None, settings_manager=sm)
        mock_auth.assert_called_once_with("https://conf.example.com", keepass_creds=None)

    def test_no_creds_when_entry_title_empty(self):
        """No credentials forwarded when no entry title is configured."""
        project, mock_prop = self._mock_project_with_props("https://conf.example.com", "PROJ")
        session = MagicMock()
        sm = MagicMock()
        sm.get_confluence_keepass_entry.return_value = ""
        with patch('integrations.confluence_calendar_integration._REQUESTS_OK', True), \
             patch('integrations.confluence_calendar_integration._PLAYWRIGHT_OK', True), \
             patch('integrations.confluence_calendar_integration._is_debug', return_value=False), \
             patch.object(cc, '_get_enterprise_prop', side_effect=mock_prop), \
             patch('integrations.confluence_calendar_integration._try_playwright_auth', return_value=(session, "Alice")) as mock_auth, \
             patch('integrations.confluence_calendar_integration._fetch_subcalendars', return_value=[]), \
             patch('integrations.confluence_calendar_integration._filter_relevant', return_value=[]), \
             patch('PyQt5.QtWidgets.QMessageBox'):
            self._sync().run(project, parent_widget=None, settings_manager=sm)
        mock_auth.assert_called_once_with("https://conf.example.com", keepass_creds=None)


# ===========================================================================
# 17. Module location
# ===========================================================================

class TestModuleLocation:
    """Verify that the module lives in its new location (integrations package)."""

    def test_importable_from_integrations(self):
        """Module is importable via  from integrations import confluence_calendar_integration."""
        from integrations import confluence_calendar_integration as _cc
        assert _cc is not None

    def test_importable_via_full_dotted_path(self):
        """ConfluenceCalendarSync is accessible via the full dotted import path."""
        from integrations.confluence_calendar_integration import ConfluenceCalendarSync
        assert ConfluenceCalendarSync is not None

    def test_public_constants_accessible_via_new_path(self):
        """Key public constants are accessible via integrations.confluence_calendar_integration."""
        from integrations.confluence_calendar_integration import (
            CONFLUENCE_BASE_URL_PROP, CONFLUENCE_SPACE_KEY_PROP,
        )
        assert CONFLUENCE_BASE_URL_PROP == "CALENDAR Base URL"
        assert CONFLUENCE_SPACE_KEY_PROP == "CALENDAR Space Key"
