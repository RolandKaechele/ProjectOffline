"""Tests for integrations/secondary_calendar_integration.py.

All MPXJ / JPype calls are mocked; no Java runtime is needed.
"""

import json
import sys
import os

import pytest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_project(custom_props_map=None, calendars=None):
    """Return a mock MPXJ ProjectFile with controllable custom properties."""
    project = MagicMock()
    props   = MagicMock()
    cp      = MagicMock()

    stored = {} if custom_props_map is None else dict(custom_props_map)
    cp.get.side_effect     = lambda key: stored.get(key)
    cp.put.side_effect     = lambda key, val: stored.update({key: val})

    props.getCustomProperties.return_value = cp
    props.setCustomProperties.side_effect  = lambda _: None
    project.getProjectProperties.return_value = props

    cals = [] if calendars is None else list(calendars)
    project.getCalendars.return_value = cals
    return project


def _make_calendar(name, uid=1, exception_count=0):
    cal = MagicMock()
    cal.getName.return_value       = name
    cal.getUniqueID.return_value   = uid
    exs = [MagicMock() for _ in range(exception_count)]
    cal.getCalendarExceptions.return_value = exs
    return cal


def _make_resource(uid=42):
    res = MagicMock()
    res.getUniqueID.return_value = uid
    return res


# ---------------------------------------------------------------------------
# _parse_map
# ---------------------------------------------------------------------------

class TestParseMap:
    def _call(self, raw):
        from integrations.secondary_calendar_integration import _parse_map
        return _parse_map(raw)

    def test_none_returns_empty(self):
        assert self._call(None) == {}

    def test_empty_string_returns_empty(self):
        assert self._call("") == {}

    def test_valid_json_dict_parsed(self):
        raw = json.dumps({"42": {"calendar_name": "Bayern", "calendar_uid": "7", "source": "ad"}})
        result = self._call(raw)
        assert "42" in result
        assert result["42"]["calendar_name"] == "Bayern"

    def test_entry_without_calendar_name_skipped(self):
        raw = json.dumps({"1": {"calendar_uid": "5", "source": "ad"}})
        assert self._call(raw) == {}

    def test_entry_with_blank_calendar_name_skipped(self):
        raw = json.dumps({"1": {"calendar_name": "  ", "calendar_uid": "5"}})
        assert self._call(raw) == {}

    def test_non_dict_value_skipped(self):
        raw = json.dumps({"1": "not-a-dict"})
        assert self._call(raw) == {}

    def test_invalid_json_returns_empty(self):
        assert self._call("{broken json") == {}

    def test_non_integer_key_skipped(self):
        raw = json.dumps({"abc": {"calendar_name": "Bayern"}})
        assert self._call(raw) == {}

    def test_source_defaults_to_ad_when_missing(self):
        raw = json.dumps({"5": {"calendar_name": "NRW"}})
        result = self._call(raw)
        assert result["5"]["source"] == "ad"


# ---------------------------------------------------------------------------
# get_secondary_calendar_map
# ---------------------------------------------------------------------------

class TestGetSecondaryCalendarMap:
    def test_empty_project_returns_empty_dict(self):
        from integrations.secondary_calendar_integration import get_secondary_calendar_map
        project = _make_project()
        assert get_secondary_calendar_map(project) == {}

    def test_none_project_returns_empty_dict(self):
        from integrations.secondary_calendar_integration import get_secondary_calendar_map
        assert get_secondary_calendar_map(None) == {}

    def test_persisted_entry_is_returned(self):
        from integrations.secondary_calendar_integration import get_secondary_calendar_map
        raw = json.dumps({"42": {"calendar_name": "Bayern", "calendar_uid": "7", "source": "ad"}})
        project = _make_project({"AD Secondary Calendars": raw})
        result  = get_secondary_calendar_map(project)
        assert "42" in result
        assert result["42"]["calendar_name"] == "Bayern"


# ---------------------------------------------------------------------------
# set_secondary_calendar_for_resource
# ---------------------------------------------------------------------------

class TestSetSecondaryCalendarForResource:
    def test_set_stores_mapping(self):
        from integrations.secondary_calendar_integration import (
            set_secondary_calendar_for_resource,
            get_secondary_calendar_map,
        )
        project = _make_project()
        set_secondary_calendar_for_resource(project, 42, "Bayern", calendar_uid=7)
        mapping = get_secondary_calendar_map(project)
        assert "42" in mapping
        assert mapping["42"]["calendar_name"] == "Bayern"

    def test_set_with_blank_name_removes_entry(self):
        from integrations.secondary_calendar_integration import (
            set_secondary_calendar_for_resource,
            get_secondary_calendar_map,
        )
        raw = json.dumps({"42": {"calendar_name": "Bayern", "calendar_uid": "7", "source": "ad"}})
        project = _make_project({"AD Secondary Calendars": raw})
        set_secondary_calendar_for_resource(project, 42, "")
        mapping = get_secondary_calendar_map(project)
        assert "42" not in mapping

    def test_set_with_none_name_removes_entry(self):
        from integrations.secondary_calendar_integration import (
            set_secondary_calendar_for_resource,
            get_secondary_calendar_map,
        )
        raw = json.dumps({"42": {"calendar_name": "Bayern", "calendar_uid": "7", "source": "ad"}})
        project = _make_project({"AD Secondary Calendars": raw})
        set_secondary_calendar_for_resource(project, 42, None)
        mapping = get_secondary_calendar_map(project)
        assert "42" not in mapping

    def test_none_uid_is_a_noop(self):
        from integrations.secondary_calendar_integration import (
            set_secondary_calendar_for_resource,
            get_secondary_calendar_map,
        )
        project = _make_project()
        set_secondary_calendar_for_resource(project, None, "Bayern")
        assert get_secondary_calendar_map(project) == {}

    def test_source_stored_correctly(self):
        from integrations.secondary_calendar_integration import (
            set_secondary_calendar_for_resource,
            get_secondary_calendar_map,
        )
        project = _make_project()
        set_secondary_calendar_for_resource(project, 5, "NRW", source="manual")
        mapping = get_secondary_calendar_map(project)
        assert mapping["5"]["source"] == "manual"


# ---------------------------------------------------------------------------
# resolve_secondary_calendar
# ---------------------------------------------------------------------------

class TestResolveSecondaryCalendar:
    def test_no_mapping_returns_none(self):
        from integrations.secondary_calendar_integration import resolve_secondary_calendar
        project  = _make_project()
        resource = _make_resource(99)
        assert resolve_secondary_calendar(project, resource) is None

    def test_returns_none_when_calendar_not_found(self):
        from integrations.secondary_calendar_integration import resolve_secondary_calendar
        raw = json.dumps({"42": {"calendar_name": "Bayern", "calendar_uid": "7", "source": "ad"}})
        project  = _make_project({"AD Secondary Calendars": raw})
        resource = _make_resource(42)
        result   = resolve_secondary_calendar(project, resource)
        # Calendar object is None (not in project calendars) but entry is returned
        assert result is not None
        assert result["calendar"] is None
        assert result["calendar_name"] == "Bayern"

    def test_returns_calendar_when_found_by_name(self):
        from integrations.secondary_calendar_integration import resolve_secondary_calendar
        cal = _make_calendar("Bayern", uid=7)
        raw = json.dumps({"42": {"calendar_name": "Bayern", "calendar_uid": None, "source": "ad"}})
        project  = _make_project({"AD Secondary Calendars": raw}, calendars=[cal])
        resource = _make_resource(42)
        result   = resolve_secondary_calendar(project, resource)
        assert result is not None
        assert result["calendar"] is cal
        assert result["calendar_name"] == "Bayern"

    def test_returns_calendar_when_found_by_uid(self):
        from integrations.secondary_calendar_integration import resolve_secondary_calendar
        cal = _make_calendar("Bayern", uid=7)
        raw = json.dumps({"42": {"calendar_name": "OtherName", "calendar_uid": "7", "source": "ad"}})
        project  = _make_project({"AD Secondary Calendars": raw}, calendars=[cal])
        resource = _make_resource(42)
        result   = resolve_secondary_calendar(project, resource)
        assert result["calendar"] is cal

    def test_none_resource_returns_none(self):
        from integrations.secondary_calendar_integration import resolve_secondary_calendar
        project = _make_project()
        assert resolve_secondary_calendar(project, None) is None


# ---------------------------------------------------------------------------
# infer_secondary_calendar_from_ad
# ---------------------------------------------------------------------------

class TestInferSecondaryCalendarFromAd:
    def test_none_project_returns_none(self):
        from integrations.secondary_calendar_integration import infer_secondary_calendar_from_ad
        assert infer_secondary_calendar_from_ad(None, {"state": "Bayern"}) is None

    def test_empty_ad_user_returns_none(self):
        from integrations.secondary_calendar_integration import infer_secondary_calendar_from_ad
        project = _make_project()
        assert infer_secondary_calendar_from_ad(project, {}) is None

    def test_non_dict_ad_user_returns_none(self):
        from integrations.secondary_calendar_integration import infer_secondary_calendar_from_ad
        project = _make_project()
        assert infer_secondary_calendar_from_ad(project, "Bavaria") is None

    def test_matching_state_returns_calendar(self):
        from integrations.secondary_calendar_integration import infer_secondary_calendar_from_ad
        cal = _make_calendar("Bayern", uid=3, exception_count=5)
        project = _make_project(calendars=[cal])
        result = infer_secondary_calendar_from_ad(project, {"state": "Bayern"})
        assert result is not None
        assert result["calendar"] is cal
        assert result["calendar_name"] == "Bayern"

    def test_no_matching_calendar_returns_none(self):
        from integrations.secondary_calendar_integration import infer_secondary_calendar_from_ad
        cal = _make_calendar("NRW", uid=2, exception_count=3)
        project = _make_project(calendars=[cal])
        result = infer_secondary_calendar_from_ad(project, {"state": "Bayern"})
        assert result is None

    def test_country_field_used_for_matching(self):
        from integrations.secondary_calendar_integration import infer_secondary_calendar_from_ad
        cal = _make_calendar("Germany", uid=1, exception_count=4)
        project = _make_project(calendars=[cal])
        result = infer_secondary_calendar_from_ad(project, {"country": "Germany"})
        assert result is not None
        assert result["calendar_name"] == "Germany"

    def test_source_tagged_as_ad_auto_match(self):
        from integrations.secondary_calendar_integration import infer_secondary_calendar_from_ad
        cal = _make_calendar("Bayern", uid=3, exception_count=2)
        project = _make_project(calendars=[cal])
        result = infer_secondary_calendar_from_ad(project, {"state": "Bayern"})
        assert result["source"] == "ad:auto-match"


# ---------------------------------------------------------------------------
# assign_secondary_calendar_from_ad
# ---------------------------------------------------------------------------

class TestAssignSecondaryCalendarFromAd:
    def test_no_matching_calendar_returns_none(self):
        from integrations.secondary_calendar_integration import assign_secondary_calendar_from_ad
        project  = _make_project()
        resource = _make_resource(42)
        result   = assign_secondary_calendar_from_ad(project, resource, {"state": "Bayern"})
        assert result is None

    def test_matching_calendar_is_persisted(self):
        from integrations.secondary_calendar_integration import (
            assign_secondary_calendar_from_ad,
            get_secondary_calendar_map,
        )
        cal = _make_calendar("Bayern", uid=3, exception_count=2)
        project  = _make_project(calendars=[cal])
        resource = _make_resource(42)
        assign_secondary_calendar_from_ad(project, resource, {"state": "Bayern"})
        mapping = get_secondary_calendar_map(project)
        assert "42" in mapping
        assert mapping["42"]["calendar_name"] == "Bayern"

    def test_returns_resolved_dict_after_assign(self):
        from integrations.secondary_calendar_integration import assign_secondary_calendar_from_ad
        cal = _make_calendar("Bayern", uid=3, exception_count=2)
        project  = _make_project(calendars=[cal])
        resource = _make_resource(42)
        result   = assign_secondary_calendar_from_ad(project, resource, {"state": "Bayern"})
        assert result is not None
        assert result["calendar_name"] == "Bayern"
        assert result["calendar"] is cal

    def test_none_resource_uid_returns_none(self):
        from integrations.secondary_calendar_integration import assign_secondary_calendar_from_ad
        resource = MagicMock()
        resource.getUniqueID.side_effect = Exception("no uid")
        project = _make_project()
        result  = assign_secondary_calendar_from_ad(project, resource, {"state": "Bayern"})
        assert result is None


# ---------------------------------------------------------------------------
# parent_dates filtering in _get_resource_vacation_blocks
# (team_planner_view.py) — unit-tested via the helper logic directly
#
# The fix: anonymous (name=null/empty) exceptions from the parent/default
# calendar must NOT be added to parent_dates, so that secondary-calendar
# holidays which share the same date are not incorrectly suppressed.
# ---------------------------------------------------------------------------

def _make_exception(from_date: str, name=None):
    """Return a mock MPXJ CalendarException with getFromDate() / getName()."""
    ex = MagicMock()
    ex.getFromDate.return_value = from_date   # returned as string; [:10] slicing is tested
    ex.getName.return_value = name
    ex.getWorking.return_value = False
    ex.getToDate.return_value = from_date
    return ex


class TestParentDatesNamedFilter:
    """Verify that building the parent_dates set only includes NAMED exceptions.

    The logic under test lives in team_planner_view._get_resource_vacation_blocks
    but is isolated here to avoid Qt / MPXJ imports.  We replicate the exact
    filtering logic so the test is a direct specification of the fix.
    """

    @staticmethod
    def _build_parent_dates_named_only(exceptions):
        """Replicate the fixed parent_dates construction logic."""
        parent_dates: set = set()
        for pex in exceptions:
            try:
                pname = str(pex.getName() or "").strip()
                if not pname:
                    continue
                pd = str(pex.getFromDate() or "")[:10]
                if pd:
                    parent_dates.add(pd)
            except Exception:
                pass
        return parent_dates

    def test_named_exception_is_included(self):
        ex = _make_exception("2026-05-14", name="Christi Himmelfahrt")
        result = self._build_parent_dates_named_only([ex])
        assert "2026-05-14" in result

    def test_anonymous_exception_is_excluded(self):
        """Anonymous Schulferien block must NOT pollute parent_dates."""
        ex = _make_exception("2026-05-06", name=None)
        result = self._build_parent_dates_named_only([ex])
        assert "2026-05-06" not in result

    def test_empty_string_name_is_excluded(self):
        ex = _make_exception("2026-06-04", name="")
        result = self._build_parent_dates_named_only([ex])
        assert "2026-06-04" not in result

    def test_whitespace_only_name_is_excluded(self):
        ex = _make_exception("2026-06-04", name="   ")
        result = self._build_parent_dates_named_only([ex])
        assert "2026-06-04" not in result

    def test_mixed_named_and_anonymous(self):
        """Named holidays appear in parent_dates; anonymous blocks do not."""
        exs = [
            _make_exception("2026-05-01", name="Tag der Arbeit"),
            _make_exception("2026-05-06", name=None),          # Schulferien start
            _make_exception("2026-05-14", name="Christi Himmelfahrt"),
            _make_exception("2026-05-23", name=None),          # another Schulferien block
        ]
        result = self._build_parent_dates_named_only(exs)
        assert "2026-05-01" in result
        assert "2026-05-14" in result
        assert "2026-05-06" not in result
        assert "2026-05-23" not in result

    def test_secondary_holiday_not_filtered_when_anonymous_block_shares_date(self):
        """Core regression: BW Fronleichnam on 2026-06-04 must NOT be filtered out
        just because an anonymous Schulferien block also starts on that date.
        """
        # Anonymous Schulferien block starting on Fronleichnam
        schulferien = _make_exception("2026-06-04", name=None)
        # Fronleichnam itself is in the secondary (BW) calendar
        fronleichnam = _make_exception("2026-06-04", name="Fronleichnam")

        parent_dates = self._build_parent_dates_named_only([schulferien])

        # The secondary holiday should NOT be in parent_dates → not suppressed
        assert "2026-06-04" not in parent_dates

    def test_empty_exception_list_gives_empty_set(self):
        assert self._build_parent_dates_named_only([]) == set()

    def test_exception_raising_getname_is_skipped(self):
        ex = MagicMock()
        ex.getName.side_effect = Exception("java error")
        result = self._build_parent_dates_named_only([ex])
        assert result == set()


# ---------------------------------------------------------------------------
# parent_dates filtering in _get_resource_vacation_blocks
# (team_planner_view.py) — unit-tested via the helper logic directly
#
# The fix: anonymous (name=null/empty) exceptions from the parent/default
# calendar must NOT be added to parent_dates, so that secondary-calendar
# holidays which share the same date are not incorrectly suppressed.
# ---------------------------------------------------------------------------

def _make_exception(from_date: str, name=None):
    """Return a mock MPXJ CalendarException with getFromDate() / getName()."""
    ex = MagicMock()
    ex.getFromDate.return_value = from_date   # returned as string; [:10] slicing is tested
    ex.getName.return_value = name
    ex.getWorking.return_value = False
    ex.getToDate.return_value = from_date
    return ex


class TestParentDatesNamedFilter:
    """Verify that building the parent_dates set only includes NAMED exceptions.

    The logic under test lives in team_planner_view._get_resource_vacation_blocks
    but is isolated here to avoid Qt / MPXJ imports.  We replicate the exact
    filtering logic so the test is a direct specification of the fix.
    """

    @staticmethod
    def _build_parent_dates_named_only(exceptions):
        """Replicate the fixed parent_dates construction logic."""
        parent_dates: set = set()
        for pex in exceptions:
            try:
                pname = str(pex.getName() or "").strip()
                if not pname:
                    continue
                pd = str(pex.getFromDate() or "")[:10]
                if pd:
                    parent_dates.add(pd)
            except Exception:
                pass
        return parent_dates

    def test_named_exception_is_included(self):
        ex = _make_exception("2026-05-14", name="Christi Himmelfahrt")
        result = self._build_parent_dates_named_only([ex])
        assert "2026-05-14" in result

    def test_anonymous_exception_is_excluded(self):
        """Anonymous Schulferien block must NOT pollute parent_dates."""
        ex = _make_exception("2026-05-06", name=None)
        result = self._build_parent_dates_named_only([ex])
        assert "2026-05-06" not in result

    def test_empty_string_name_is_excluded(self):
        ex = _make_exception("2026-06-04", name="")
        result = self._build_parent_dates_named_only([ex])
        assert "2026-06-04" not in result

    def test_whitespace_only_name_is_excluded(self):
        ex = _make_exception("2026-06-04", name="   ")
        result = self._build_parent_dates_named_only([ex])
        assert "2026-06-04" not in result

    def test_mixed_named_and_anonymous(self):
        """Named holidays appear in parent_dates; anonymous blocks do not."""
        exs = [
            _make_exception("2026-05-01", name="Tag der Arbeit"),
            _make_exception("2026-05-06", name=None),          # Schulferien start
            _make_exception("2026-05-14", name="Christi Himmelfahrt"),
            _make_exception("2026-05-23", name=None),          # another Schulferien block
        ]
        result = self._build_parent_dates_named_only(exs)
        assert "2026-05-01" in result
        assert "2026-05-14" in result
        assert "2026-05-06" not in result
        assert "2026-05-23" not in result

    def test_secondary_holiday_not_filtered_when_anonymous_block_shares_date(self):
        """Core regression: BW Fronleichnam on 2026-06-04 must NOT be filtered out
        just because an anonymous Schulferien block also starts on that date.
        """
        # Anonymous Schulferien block starting on Fronleichnam
        schulferien = _make_exception("2026-06-04", name=None)
        # Fronleichnam itself is in the secondary (BW) calendar
        fronleichnam = _make_exception("2026-06-04", name="Fronleichnam")

        parent_dates = self._build_parent_dates_named_only([schulferien])

        # The secondary holiday should NOT be in parent_dates → not suppressed
        assert "2026-06-04" not in parent_dates

    def test_empty_exception_list_gives_empty_set(self):
        assert self._build_parent_dates_named_only([]) == set()

    def test_exception_raising_getname_is_skipped(self):
        ex = MagicMock()
        ex.getName.side_effect = Exception("java error")
        result = self._build_parent_dates_named_only([ex])
        assert result == set()
