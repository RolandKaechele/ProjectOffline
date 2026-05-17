"""Tests for the three critical-path fixes in gantt_view.

Fixes covered
─────────────
1. _add_working_days off-by-one  (n = max(0, days-1))
   A 1-day task starts and finishes on the same calendar day.

2. Zero-float always critical  (flt <= _ZERO, was flt < _ZERO)
   Tasks whose finish equals the project deadline have zero float and
   must be marked critical regardless of the zero_float_critical flag.

3. SNET / SNLT / MSO constraint override
   When a task's stored start is *before* the constraint date the
   constraint is skipped by the CPM so that dragging a task earlier
   than its original SNET does not inflate net_ef back to the
   constraint date and produce a false zero-float / critical result.
"""

import sys
import os

import pytest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'src')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'src', 'views')))


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _dt_mock(iso_str: str):
    """MagicMock whose str() returns an ISO datetime string."""
    m = MagicMock()
    m.__str__ = MagicMock(return_value=iso_str)
    return m


def _make_cpm_task(tid, start_iso, finish_iso, preds=None,
                   constraint_type=None, constraint_date_iso=None,
                   is_summary=False, children=None):
    """Minimal MPXJ task mock accepted by _compute_critical_ids.

    Parameters
    ----------
    tid               : int  — task ID
    start_iso         : str  — ISO datetime, e.g. "2026-05-07T08:00"
    finish_iso        : str  — ISO datetime
    preds             : list — predecessor relation mocks (use _make_fs_rel)
    constraint_type   : str  — e.g. "START_NO_EARLIER_THAN", or None
    constraint_date_iso: str — ISO datetime for the constraint, or None
    is_summary        : bool — True → getChildTasks() returns children list
    children          : list — child task mocks (only used when is_summary)
    """
    t = MagicMock()
    t.getID.return_value = tid
    t.getStart.return_value = _dt_mock(start_iso)
    t.getFinish.return_value = _dt_mock(finish_iso)
    t.getPredecessors.return_value = preds or []
    t.getConstraintType.return_value = (
        _dt_mock(constraint_type) if constraint_type is not None else None
    )
    t.getConstraintDate.return_value = (
        _dt_mock(constraint_date_iso) if constraint_date_iso is not None else None
    )
    t.getChildTasks.return_value = (children or []) if is_summary else None
    return t


def _make_fs_rel(pred_task):
    """FS predecessor relation mock pointing at pred_task."""
    rel = MagicMock()
    rel.getType.return_value = _dt_mock("FINISH_START")
    rel.getPredecessorTask.return_value = pred_task
    return rel


def _make_project(deadline_iso=None):
    """MPXJ ProjectFile mock with an optional project finish date."""
    proj = MagicMock()
    if deadline_iso:
        proj.getProjectProperties.return_value.getFinishDate.return_value = (
            _dt_mock(deadline_iso)
        )
    else:
        proj.getProjectProperties.return_value.getFinishDate.return_value = None
    return proj


# ---------------------------------------------------------------------------
# Fix 1 — _add_working_days: 1-day task finishes on its start day
# ---------------------------------------------------------------------------

class TestAddWorkingDaysNewSemantics:
    """_add_working_days(start, working_days) after the off-by-one fix.

    Semantics: working_days is the task *duration*.
      1 day  → finish on the same day as start  (n = max(0, 1-1) = 0)
      2 days → finish one working day after start  (n = 1)
      5 days → finish four working days after start  (n = 4)
    """

    def test_one_day_task_finishes_on_start_day(self):
        from gantt_view import _add_working_days
        from PyQt5.QtCore import QDate
        monday = QDate(2025, 1, 6)
        assert _add_working_days(monday, 1) == monday

    def test_one_day_task_on_friday_stays_friday(self):
        """A 1-day task placed on Friday still finishes Friday."""
        from gantt_view import _add_working_days
        from PyQt5.QtCore import QDate
        friday = QDate(2025, 1, 10)
        assert _add_working_days(friday, 1) == friday

    def test_two_day_task_from_monday_finishes_tuesday(self):
        from gantt_view import _add_working_days
        from PyQt5.QtCore import QDate
        monday = QDate(2025, 1, 6)
        assert _add_working_days(monday, 2) == QDate(2025, 1, 7)  # Tuesday

    def test_two_day_task_from_friday_finishes_monday(self):
        """A 2-day task starting Friday spans the weekend → finishes Monday."""
        from gantt_view import _add_working_days
        from PyQt5.QtCore import QDate
        friday = QDate(2025, 1, 10)
        assert _add_working_days(friday, 2) == QDate(2025, 1, 13)  # Monday

    def test_five_day_task_from_monday_finishes_friday(self):
        """Mon–Fri: a 5-day task starting Monday should finish Friday."""
        from gantt_view import _add_working_days
        from PyQt5.QtCore import QDate
        monday = QDate(2025, 1, 6)
        assert _add_working_days(monday, 5) == QDate(2025, 1, 10)  # Friday

    def test_zero_days_returns_start_unchanged(self):
        """Edge case: 0-day duration → n = max(0, -1) = 0 → no advance."""
        from gantt_view import _add_working_days
        from PyQt5.QtCore import QDate
        monday = QDate(2025, 1, 6)
        assert _add_working_days(monday, 0) == monday

    def test_result_is_never_a_weekend(self):
        """For any duration 1–14 starting from Monday the result is a weekday."""
        from gantt_view import _add_working_days
        from PyQt5.QtCore import QDate
        start = QDate(2025, 1, 6)
        for days in range(1, 15):
            result = _add_working_days(start, days)
            assert result.dayOfWeek() not in (6, 7), (
                f"Weekend result for days={days}: {result.toString()}"
            )


# ---------------------------------------------------------------------------
# Fix 2 — zero-float tasks are always critical  (flt <= _ZERO)
# ---------------------------------------------------------------------------

class TestComputeCriticalIdsZeroFloat:
    """Tasks with exactly zero float must be critical.

    Before the fix, flt < _ZERO was required; tasks at exactly the project
    deadline (float = 0) were only critical when zero_float_critical=True.
    """

    def test_task_finishing_at_deadline_is_critical(self):
        """finish == project deadline → float = 0 → critical."""
        from gantt_view import _compute_critical_ids
        t1 = _make_cpm_task(1, "2026-05-07T08:00", "2026-05-07T17:00")
        proj = _make_project("2026-05-07T17:00")
        result = _compute_critical_ids([t1], project=proj, zero_float_critical=False)
        assert 1 in result

    def test_task_finishing_before_deadline_not_critical(self):
        """finish one day before deadline → float = 1 day → not critical."""
        from gantt_view import _compute_critical_ids
        t1 = _make_cpm_task(1, "2026-05-06T08:00", "2026-05-06T17:00")
        proj = _make_project("2026-05-07T17:00")
        result = _compute_critical_ids([t1], project=proj, zero_float_critical=False)
        assert 1 not in result

    def test_task_finishing_past_deadline_is_critical(self):
        """finish > project deadline → always critical (>= check in _is_critical)."""
        from gantt_view import _compute_critical_ids
        t1 = _make_cpm_task(1, "2026-05-08T08:00", "2026-05-08T17:00")
        proj = _make_project("2026-05-07T17:00")
        result = _compute_critical_ids([t1], project=proj, zero_float_critical=False)
        assert 1 in result

    def test_zero_float_without_explicit_deadline(self):
        """Without a stored project deadline the network max becomes the anchor.
        The task that drives the network max has zero float and must be critical.
        """
        from gantt_view import _compute_critical_ids
        t1 = _make_cpm_task(1, "2026-05-07T08:00", "2026-05-07T17:00")
        t2 = _make_cpm_task(2, "2026-05-06T08:00", "2026-05-06T17:00")
        result = _compute_critical_ids([t1, t2], project=None, zero_float_critical=False)
        assert 1 in result      # drives network max → zero float
        assert 2 not in result  # positive float

    def test_deadline_equality_check_is_inclusive(self):
        """Regression guard: the deadline check uses >= so equality is caught
        both by the early_finish >= raw_deadline branch AND the flt <= 0 branch.
        """
        from gantt_view import _compute_critical_ids
        t1 = _make_cpm_task(1, "2026-05-07T08:00", "2026-05-07T17:00")
        proj = _make_project("2026-05-07T17:00")
        # zero_float_critical=False must NOT prevent the task from being critical
        result = _compute_critical_ids([t1], project=proj, zero_float_critical=False)
        assert 1 in result

    def test_two_tasks_on_deadline_both_critical(self):
        """Two independent tasks both finishing exactly at the deadline
        must both be critical."""
        from gantt_view import _compute_critical_ids
        t1 = _make_cpm_task(1, "2026-05-07T08:00", "2026-05-07T17:00")
        t2 = _make_cpm_task(2, "2026-05-06T08:00", "2026-05-07T17:00")
        proj = _make_project("2026-05-07T17:00")
        result = _compute_critical_ids([t1, t2], project=proj, zero_float_critical=False)
        assert 1 in result
        assert 2 in result


# ---------------------------------------------------------------------------
# Fix 3 — SNET / SNLT / MSO constraint override when start < constraint date
# ---------------------------------------------------------------------------

class TestComputeCriticalIdsSnetOverride:
    """When a task's stored start is *before* the constraint date the
    constraint is treated as overridden and the CPM uses the actual
    stored position.  This prevents a dragged task from being falsely
    pushed back to its old SNET and gaining spurious zero float.
    """

    def test_snet_overridden_when_start_before_constraint(self):
        """Task dragged to May 6 with SNET May 7 → constraint skipped →
        float = 1 day → NOT critical.
        """
        from gantt_view import _compute_critical_ids
        t1 = _make_cpm_task(
            1, "2026-05-06T08:00", "2026-05-06T17:00",
            constraint_type="START_NO_EARLIER_THAN",
            constraint_date_iso="2026-05-07T08:00",
        )
        proj = _make_project("2026-05-07T17:00")
        result = _compute_critical_ids([t1], project=proj, zero_float_critical=False)
        assert 1 not in result

    def test_snet_honored_when_start_equals_constraint(self):
        """start == SNET date → constraint NOT overridden (strict <).
        SNET has no additional push effect; task has zero float → critical.
        """
        from gantt_view import _compute_critical_ids
        t1 = _make_cpm_task(
            1, "2026-05-07T08:00", "2026-05-07T17:00",
            constraint_type="START_NO_EARLIER_THAN",
            constraint_date_iso="2026-05-07T08:00",
        )
        proj = _make_project("2026-05-07T17:00")
        result = _compute_critical_ids([t1], project=proj, zero_float_critical=False)
        assert 1 in result

    def test_snet_honored_when_start_after_constraint(self):
        """start > SNET date → constraint not overridden but also has no
        push effect; the task finishes before the deadline → not critical.
        """
        from gantt_view import _compute_critical_ids
        t1 = _make_cpm_task(
            1, "2026-05-08T08:00", "2026-05-08T17:00",
            constraint_type="START_NO_EARLIER_THAN",
            constraint_date_iso="2026-05-07T08:00",
        )
        proj = _make_project("2026-05-09T17:00")
        result = _compute_critical_ids([t1], project=proj, zero_float_critical=False)
        assert 1 not in result  # float = 1 day

    def test_mso_overridden_when_start_before_constraint(self):
        """MUST_START_ON is also skipped when stored start < constraint date."""
        from gantt_view import _compute_critical_ids
        t1 = _make_cpm_task(
            1, "2026-05-05T08:00", "2026-05-05T17:00",
            constraint_type="MUST_START_ON",
            constraint_date_iso="2026-05-07T08:00",
        )
        proj = _make_project("2026-05-07T17:00")
        result = _compute_critical_ids([t1], project=proj, zero_float_critical=False)
        assert 1 not in result  # float = 2 days

    def test_task13_scenario_dragged_before_snet(self):
        """Regression: task 13 dragged from May 7 to May 6 with SNET May 7
        and a predecessor (task 33) finishing Apr 29.
        After the drag the task must NOT be critical (float = 1 day).
        """
        from gantt_view import _compute_critical_ids
        pred = _make_cpm_task(33, "2026-04-27T09:00", "2026-04-29T09:00")
        rel = _make_fs_rel(pred)
        task13 = _make_cpm_task(
            13, "2026-05-06T08:00", "2026-05-06T17:00",
            preds=[rel],
            constraint_type="START_NO_EARLIER_THAN",
            constraint_date_iso="2026-05-07T08:00",
        )
        proj = _make_project("2026-05-07T17:00")
        result = _compute_critical_ids([pred, task13], project=proj,
                                       zero_float_critical=False)
        assert 13 not in result
        assert 33 not in result

    def test_task13_scenario_at_original_position_is_critical(self):
        """Counterpart: task 13 at its original May 7 start (= SNET) has
        zero float and must be critical.
        """
        from gantt_view import _compute_critical_ids
        pred = _make_cpm_task(33, "2026-04-27T09:00", "2026-04-29T09:00")
        rel = _make_fs_rel(pred)
        task13 = _make_cpm_task(
            13, "2026-05-07T08:00", "2026-05-07T17:00",
            preds=[rel],
            constraint_type="START_NO_EARLIER_THAN",
            constraint_date_iso="2026-05-07T08:00",
        )
        proj = _make_project("2026-05-07T17:00")
        result = _compute_critical_ids([pred, task13], project=proj,
                                       zero_float_critical=False)
        assert 13 in result
