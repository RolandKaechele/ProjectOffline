"""Tests for compute_histogram_data() in views/resource_usage_histogram_view.py.

Tests cover:
  - Single resource basic allocation
  - Multiple resources aggregation
  - Vacation (resource calendar exception) exclusion
  - Public holiday (project non_working_dates) exclusion
  - Over-capacity detection
  - Empty / None project handling
"""

import sys
import os

import pytest
from unittest.mock import MagicMock, patch
from PyQt5.QtCore import QDate

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'src')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'src', 'views')))
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _make_project(tasks, resources):
    """Return a mock MPXJ ProjectFile with the given tasks and resources."""
    project = MagicMock()
    project.getTasks.return_value = tasks
    project.getResources.return_value = resources
    # Default calendar: 8h day, no exceptions
    default_cal = MagicMock()
    default_cal.getCalendarExceptions.return_value = []
    project.getDefaultCalendar.return_value = default_cal
    return project


def _make_resource(uid: int, name: str, vac_dates: list | None = None):
    """Return a mock MPXJ Resource.

    vac_dates: list of (from_str, to_str) "yyyy-MM-dd" pairs for non-working
               calendar exceptions.
    """
    res = MagicMock()
    res.getUniqueID.return_value = uid
    res.getName.return_value = name

    cal = MagicMock()
    exceptions = []
    for (from_str, to_str) in (vac_dates or []):
        ex = MagicMock()
        ex.getWorking.return_value = False
        ex.getFromDate.return_value = from_str
        ex.getToDate.return_value = to_str
        ex.getName.return_value = "Vacation"
        exceptions.append(ex)
    cal.getCalendarExceptions.return_value = exceptions
    res.getCalendar.return_value = cal
    return res


def _make_task(uid: int, name: str, start_str: str, finish_str: str,
               assignments: list | None = None, is_summary: bool = False):
    """Return a mock MPXJ Task with the given dates and resource assignments."""
    task = MagicMock()
    task.getUniqueID.return_value = uid
    task.getID.return_value = uid
    task.getName.return_value = name
    task.getSummary.return_value = is_summary

    # Java Date → str representation (MPXJ returns LocalDateTime-ish objects)
    start_mock = MagicMock()
    start_mock.__str__ = lambda self: start_str + "T08:00:00"
    task.getStart.return_value = start_mock

    finish_mock = MagicMock()
    finish_mock.__str__ = lambda self: finish_str + "T17:00:00"
    task.getFinish.return_value = finish_mock

    # Duration: e.g., 5 DAYS
    dur_days = QDate.fromString(start_str, "yyyy-MM-dd").daysTo(
        QDate.fromString(finish_str, "yyyy-MM-dd")
    ) + 1
    dur_mock = MagicMock()
    dur_mock.getDuration.return_value = float(dur_days)
    dur_mock.getUnits.return_value = "DAYS"
    task.getDuration.return_value = dur_mock

    task.getResourceAssignments.return_value = assignments or []
    return task


def _make_assignment(resource, work_hours: float | None = None):
    """Return a mock MPXJ ResourceAssignment."""
    asgn = MagicMock()
    asgn.getResource.return_value = resource
    if work_hours is not None:
        work = MagicMock()
        work.getDuration.return_value = work_hours
        work.getUnits.return_value = "HOURS"
        asgn.getWork.return_value = work
    else:
        asgn.getWork.return_value = None
    return asgn


# ---------------------------------------------------------------------------
# We need _to_qdate to parse Java-date strings — patch it to parse
# "yyyy-MM-dd" prefixed strings coming from our mock str representation.
# ---------------------------------------------------------------------------

def _to_qdate_patched(java_date):
    """Simplified _to_qdate that works with our mock objects."""
    if java_date is None:
        return None
    s = str(java_date)[:10]
    d = QDate.fromString(s, "yyyy-MM-dd")
    return d if d.isValid() else None


@pytest.fixture(autouse=True)
def patch_to_qdate(monkeypatch):
    import resource_usage_histogram_view as m
    monkeypatch.setattr(m, "_to_qdate", _to_qdate_patched)


@pytest.fixture(autouse=True)
def patch_read_work_hours(monkeypatch):
    """Stub out read_work_hours to return 8-hour days without JVM."""
    import resource_usage_histogram_view as m
    monkeypatch.setattr(
        m,
        "compute_histogram_data",
        m.compute_histogram_data,  # use the real one; stub its internal import below
    )
    # Patch the import inside compute_histogram_data
    import unittest.mock as mock
    original = m.compute_histogram_data
    def _patched_compute(*args, **kwargs):
        # Temporarily stub hour_mode inside the function
        import sys
        import types
        hour_mode_mod = types.ModuleType("hour_mode")
        hour_mode_mod.read_work_hours = lambda project: (8, 17, 8, frozenset())
        old = sys.modules.get("hour_mode")
        sys.modules["hour_mode"] = hour_mode_mod
        try:
            return original(*args, **kwargs)
        finally:
            if old is None:
                del sys.modules["hour_mode"]
            else:
                sys.modules["hour_mode"] = old
    monkeypatch.setattr(m, "compute_histogram_data", _patched_compute)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestComputeHistogramDataEmpty:
    def test_none_project_returns_empty(self):
        from resource_usage_histogram_view import compute_histogram_data
        result = compute_histogram_data(None, QDate(2025, 1, 6), QDate(2025, 1, 13))
        assert result == []

    def test_inverted_range_returns_empty(self):
        from resource_usage_histogram_view import compute_histogram_data
        project = _make_project([], [])
        result = compute_histogram_data(project, QDate(2025, 1, 13), QDate(2025, 1, 6))
        assert result == []

    def test_no_resources_no_allocation(self):
        from resource_usage_histogram_view import compute_histogram_data
        project = _make_project([], [])
        result = compute_histogram_data(project, QDate(2025, 1, 6), QDate(2025, 1, 10))
        assert all(d["total_hours"] == 0.0 for d in result)
        assert all(d["capacity_hours"] == 0.0 for d in result)


class TestComputeHistogramDataSingleResource:
    def test_single_resource_capacity_on_working_days(self):
        """Mon–Fri should accumulate 8 h capacity each; weekends 0."""
        from resource_usage_histogram_view import compute_histogram_data
        res = _make_resource(1, "Alice")
        project = _make_project([], [res])
        # Mon 2025-01-06 … Fri 2025-01-10 (5 days)
        start = QDate(2025, 1, 6)
        end   = QDate(2025, 1, 11)   # exclusive
        result = compute_histogram_data(project, start, end)
        assert len(result) == 5
        for d in result:
            assert d["capacity_hours"] == 8.0
            assert d["total_hours"] == 0.0

    def test_single_resource_allocation_distributed_evenly(self):
        """5-day task with 40 h work → 8 h/day."""
        from resource_usage_histogram_view import compute_histogram_data
        res  = _make_resource(1, "Alice")
        asgn = _make_assignment(res, work_hours=40.0)
        task = _make_task(1, "Task A", "2025-01-06", "2025-01-10", [asgn])
        project = _make_project([task], [res])
        start = QDate(2025, 1, 6)
        end   = QDate(2025, 1, 11)
        result = compute_histogram_data(project, start, end)
        for d in result:
            assert abs(d["total_hours"] - 8.0) < 0.01
            assert abs(d["utilisation_pct"] - 100.0) < 0.1

    def test_utilisation_over_100_when_overallocated(self):
        """80 h over 5 working days → 16 h/day on 8 h capacity → 200%."""
        from resource_usage_histogram_view import compute_histogram_data
        res  = _make_resource(1, "Alice")
        asgn = _make_assignment(res, work_hours=80.0)
        task = _make_task(1, "Big Task", "2025-01-06", "2025-01-10", [asgn])
        project = _make_project([task], [res])
        start = QDate(2025, 1, 6)
        end   = QDate(2025, 1, 11)
        result = compute_histogram_data(project, start, end)
        for d in result:
            assert d["utilisation_pct"] > 100.0

    def test_weekend_days_have_zero_capacity(self):
        """Sat + Sun in range → capacity 0."""
        from resource_usage_histogram_view import compute_histogram_data
        res  = _make_resource(1, "Alice")
        project = _make_project([], [res])
        # Saturday 2025-01-11, Sunday 2025-01-12
        start = QDate(2025, 1, 11)
        end   = QDate(2025, 1, 13)
        result = compute_histogram_data(project, start, end)
        for d in result:
            assert d["capacity_hours"] == 0.0


class TestComputeHistogramDataMultipleResources:
    def test_two_resources_capacity_aggregated(self):
        """Two resources → 16 h/day capacity on working days."""
        from resource_usage_histogram_view import compute_histogram_data
        res_a = _make_resource(1, "Alice")
        res_b = _make_resource(2, "Bob")
        project = _make_project([], [res_a, res_b])
        start = QDate(2025, 1, 6)
        end   = QDate(2025, 1, 8)
        result = compute_histogram_data(project, start, end)
        for d in result:
            assert d["capacity_hours"] == 16.0

    def test_two_resources_allocation_aggregated(self):
        """Two resources each assigned 8 h on the same day → 16 h total."""
        from resource_usage_histogram_view import compute_histogram_data
        res_a  = _make_resource(1, "Alice")
        res_b  = _make_resource(2, "Bob")
        asgn_a = _make_assignment(res_a, work_hours=8.0)
        asgn_b = _make_assignment(res_b, work_hours=8.0)
        task = _make_task(1, "Shared Task", "2025-01-06", "2025-01-06",
                          [asgn_a, asgn_b])
        project = _make_project([task], [res_a, res_b])
        start = QDate(2025, 1, 6)
        end   = QDate(2025, 1, 7)
        result = compute_histogram_data(project, start, end)
        assert len(result) == 1
        assert abs(result[0]["total_hours"] - 16.0) < 0.01
        assert abs(result[0]["capacity_hours"] - 16.0) < 0.01
        assert abs(result[0]["utilisation_pct"] - 100.0) < 0.1


class TestComputeHistogramDataVacationExclusion:
    def test_resource_vacation_reduces_capacity(self):
        """Resource on vacation on Mon → capacity 0 on that day."""
        from resource_usage_histogram_view import compute_histogram_data
        # Alice on vacation Mon 2025-01-06
        res = _make_resource(1, "Alice", vac_dates=[("2025-01-06", "2025-01-06")])
        project = _make_project([], [res])
        start = QDate(2025, 1, 6)
        end   = QDate(2025, 1, 8)
        result = compute_histogram_data(project, start, end)
        # Monday: vacation → capacity 0; Tuesday: working → 8
        assert result[0]["date"] == QDate(2025, 1, 6)
        assert result[0]["capacity_hours"] == 0.0
        assert result[1]["capacity_hours"] == 8.0

    def test_allocation_not_placed_on_vacation_day(self):
        """Task covering vacation day → no hours allocated to vacation day."""
        from resource_usage_histogram_view import compute_histogram_data
        # Alice on vacation Mon 2025-01-06 only; task Mon–Tue (2 working days, 1 available)
        res  = _make_resource(1, "Alice", vac_dates=[("2025-01-06", "2025-01-06")])
        asgn = _make_assignment(res, work_hours=8.0)
        task = _make_task(1, "Task A", "2025-01-06", "2025-01-07", [asgn])
        project = _make_project([task], [res])
        start = QDate(2025, 1, 6)
        end   = QDate(2025, 1, 8)
        result = compute_histogram_data(project, start, end)
        # Monday: vacation → 0 h allocated; Tuesday: all 8 h
        assert result[0]["total_hours"] == 0.0
        assert abs(result[1]["total_hours"] - 8.0) < 0.01


class TestComputeHistogramDataPublicHolidays:
    def test_public_holiday_reduces_capacity(self):
        """Project-level non-working date → capacity 0 on that day."""
        from resource_usage_histogram_view import compute_histogram_data
        res = _make_resource(1, "Alice")
        project = _make_project([], [res])
        non_working = {"2025-01-06"}   # Monday is a public holiday
        start = QDate(2025, 1, 6)
        end   = QDate(2025, 1, 8)
        result = compute_histogram_data(project, start, end, non_working)
        assert result[0]["capacity_hours"] == 0.0
        assert result[1]["capacity_hours"] == 8.0

    def test_allocation_not_placed_on_public_holiday(self):
        """Task covering public holiday → no hours allocated to that day."""
        from resource_usage_histogram_view import compute_histogram_data
        res  = _make_resource(1, "Alice")
        asgn = _make_assignment(res, work_hours=16.0)
        task = _make_task(1, "Task A", "2025-01-06", "2025-01-07", [asgn])
        project = _make_project([task], [res])
        non_working = {"2025-01-06"}   # Monday is public holiday → 1 working day
        start = QDate(2025, 1, 6)
        end   = QDate(2025, 1, 8)
        result = compute_histogram_data(project, start, end, non_working)
        assert result[0]["total_hours"] == 0.0
        # All 16 h placed on Tuesday
        assert abs(result[1]["total_hours"] - 16.0) < 0.01


class TestComputeHistogramDataSummaryTaskExclusion:
    def test_summary_tasks_not_counted(self):
        """Summary (parent) tasks should be excluded from allocation."""
        from resource_usage_histogram_view import compute_histogram_data
        res     = _make_resource(1, "Alice")
        asgn    = _make_assignment(res, work_hours=40.0)
        summary = _make_task(1, "Phase 1", "2025-01-06", "2025-01-10", [asgn],
                             is_summary=True)
        project = _make_project([summary], [res])
        start = QDate(2025, 1, 6)
        end   = QDate(2025, 1, 11)
        result = compute_histogram_data(project, start, end)
        for d in result:
            assert d["total_hours"] == 0.0


class TestComputeHistogramDataOverCapacity:
    def test_over_capacity_flag_via_utilisation_pct(self):
        """At least one day over 100% when over-allocated."""
        from resource_usage_histogram_view import compute_histogram_data
        res  = _make_resource(1, "Alice")
        asgn = _make_assignment(res, work_hours=100.0)
        task = _make_task(1, "Big Task", "2025-01-06", "2025-01-10", [asgn])
        project = _make_project([task], [res])
        start = QDate(2025, 1, 6)
        end   = QDate(2025, 1, 11)
        result = compute_histogram_data(project, start, end)
        over = [d for d in result if d["utilisation_pct"] > 100.0]
        assert len(over) > 0
