"""Tests for views/gantt_view.py — GanttView widget and helper functions.

Pure helper functions (_to_qdate, _add_working_days, _snap_to_workday,
_get_visible_tasks) are tested without a QApplication.

GanttView widget tests require the session-scoped 'qapp' fixture.
_get_non_working_dates is patched out to avoid JPype imports.
"""

import sys
import os

import pytest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'src')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'src', 'views')))
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from conftest import make_mock_task, make_mock_ldt, make_mock_project


# ---------------------------------------------------------------------------
# _to_qdate helper
# ---------------------------------------------------------------------------

class TestToQdate:
    def setup_method(self):
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

    def test_none_returns_none(self):
        from gantt_view import _to_qdate
        assert _to_qdate(None) is None

    def test_iso_date_string(self):
        from gantt_view import _to_qdate
        from PyQt5.QtCore import QDate
        mock_dt = MagicMock()
        mock_dt.__str__ = MagicMock(return_value="2025-06-15")
        result = _to_qdate(mock_dt)
        assert result == QDate(2025, 6, 15)

    def test_datetime_string_truncated_to_date(self):
        from gantt_view import _to_qdate
        from PyQt5.QtCore import QDate
        mock_dt = MagicMock()
        mock_dt.__str__ = MagicMock(return_value="2025-12-01T08:00:00")
        result = _to_qdate(mock_dt)
        assert result == QDate(2025, 12, 1)

    def test_invalid_string_returns_none(self):
        from gantt_view import _to_qdate
        mock_dt = MagicMock()
        mock_dt.__str__ = MagicMock(return_value="not-a-date")
        result = _to_qdate(mock_dt)
        assert result is None

    def test_empty_string_returns_none(self):
        from gantt_view import _to_qdate
        mock_dt = MagicMock()
        mock_dt.__str__ = MagicMock(return_value="")
        result = _to_qdate(mock_dt)
        assert result is None


# ---------------------------------------------------------------------------
# _add_working_days helper
# ---------------------------------------------------------------------------

class TestAddWorkingDays:
    def test_add_zero_days_returns_start_unchanged(self):
        """_add_working_days with 0 days returns the start date unchanged.
        n = max(0, 0-1) = 0 — no advancement."""
        from gantt_view import _add_working_days
        from PyQt5.QtCore import QDate
        monday = QDate(2025, 1, 6)   # a Monday
        result = _add_working_days(monday, 0)
        assert result == monday

    def test_add_five_days_from_monday(self):
        """A 5-day task starting Monday finishes Friday (Mon–Fri).
        n = max(0, 5-1) = 4 working-day advances."""
        from gantt_view import _add_working_days
        from PyQt5.QtCore import QDate
        monday = QDate(2025, 1, 6)   # Monday 2025-01-06
        result = _add_working_days(monday, 5)
        assert result == QDate(2025, 1, 10)  # Friday

    def test_one_day_task_on_friday_stays_friday(self):
        """A 1-day task placed on Friday finishes Friday (same day).
        n = max(0, 1-1) = 0 — no advancement."""
        from gantt_view import _add_working_days
        from PyQt5.QtCore import QDate
        friday = QDate(2025, 1, 10)   # Friday 2025-01-10
        result = _add_working_days(friday, 1)
        assert result == friday

    def test_two_day_task_from_friday_skips_weekend(self):
        """A 2-day task starting Friday finishes Monday (skips Sat/Sun).
        n = max(0, 2-1) = 1 working-day advance."""
        from gantt_view import _add_working_days
        from PyQt5.QtCore import QDate
        friday = QDate(2025, 1, 10)   # Friday 2025-01-10
        result = _add_working_days(friday, 2)
        assert result == QDate(2025, 1, 13)  # Monday 2025-01-13

    def test_result_is_never_a_weekend(self):
        from gantt_view import _add_working_days
        from PyQt5.QtCore import QDate
        start = QDate(2025, 1, 6)
        for days in range(1, 15):
            result = _add_working_days(start, days)
            assert result.dayOfWeek() not in (6, 7), \
                f"Got weekend for days={days}: {result.toString()}"


# ---------------------------------------------------------------------------
# _snap_to_workday helper
# ---------------------------------------------------------------------------

class TestSnapToWorkday:
    def test_workday_unchanged(self):
        from gantt_view import _snap_to_workday
        from PyQt5.QtCore import QDate
        monday = QDate(2025, 1, 6)
        assert _snap_to_workday(monday) == monday

    def test_saturday_snaps_to_monday(self):
        from gantt_view import _snap_to_workday
        from PyQt5.QtCore import QDate
        saturday = QDate(2025, 1, 11)
        result = _snap_to_workday(saturday)
        assert result == QDate(2025, 1, 13)

    def test_sunday_snaps_to_monday(self):
        from gantt_view import _snap_to_workday
        from PyQt5.QtCore import QDate
        sunday = QDate(2025, 1, 12)
        result = _snap_to_workday(sunday)
        assert result == QDate(2025, 1, 13)

    def test_holiday_in_non_working_set_snaps_forward(self):
        from gantt_view import _snap_to_workday
        from PyQt5.QtCore import QDate
        monday = QDate(2025, 1, 6)
        non_working = {"2025-01-06", "2025-01-07"}   # Mon + Tue blocked
        result = _snap_to_workday(monday, non_working)
        assert result == QDate(2025, 1, 8)


# ---------------------------------------------------------------------------
# _get_visible_tasks helper
# ---------------------------------------------------------------------------

class TestGetVisibleTasks:
    def test_empty_collapsed_returns_all(self):
        from gantt_view import _get_visible_tasks
        tasks = [make_mock_task(task_id=i, uid=i) for i in range(1, 4)]
        result = _get_visible_tasks(tasks, set())
        assert result == tasks

    def test_empty_task_list_returns_empty(self):
        from gantt_view import _get_visible_tasks
        assert _get_visible_tasks([], set()) == []

    def test_non_summary_task_always_visible(self):
        from gantt_view import _get_visible_tasks
        task = make_mock_task(task_id=1, uid=1, is_summary=False)
        result = _get_visible_tasks([task], {"1"})
        assert task in result

    def test_collapsed_summary_hides_children(self):
        """A summary task with id '1' and a child at outline level 2 should hide the child."""
        from gantt_view import _get_visible_tasks

        summary = make_mock_task(task_id=1, uid=1, outline_level=1, is_summary=True)
        summary.getSummary.return_value = True

        child = make_mock_task(task_id=2, uid=2, outline_level=2, is_summary=False)
        child.getSummary.return_value = False

        result = _get_visible_tasks([summary, child], {"1"})
        assert summary in result
        assert child not in result

    def test_uncollapsed_summary_shows_children(self):
        from gantt_view import _get_visible_tasks

        summary = make_mock_task(task_id=1, uid=1, outline_level=1, is_summary=True)
        summary.getSummary.return_value = True

        child = make_mock_task(task_id=2, uid=2, outline_level=2, is_summary=False)

        result = _get_visible_tasks([summary, child], set())
        assert summary in result
        assert child in result


# ---------------------------------------------------------------------------
# Layout constants
# ---------------------------------------------------------------------------

class TestLayoutConstants:
    def test_day_width_def_between_min_and_max(self):
        from gantt_view import DAY_WIDTH_DEF, DAY_WIDTH_MIN, DAY_WIDTH_MAX
        assert DAY_WIDTH_MIN <= DAY_WIDTH_DEF <= DAY_WIDTH_MAX

    def test_header_height_is_sum_of_rows(self):
        from gantt_view import HEADER_HEIGHT, HEADER_MONTH_H, HEADER_WEEK_H
        assert HEADER_HEIGHT == HEADER_MONTH_H + HEADER_WEEK_H

    def test_row_height_positive(self):
        from gantt_view import ROW_HEIGHT
        assert ROW_HEIGHT > 0

    def test_nav_bar_height_positive(self):
        from gantt_view import NAV_BAR_HEIGHT
        assert NAV_BAR_HEIGHT > 0


# ---------------------------------------------------------------------------
# GanttView widget
# ---------------------------------------------------------------------------

class TestGanttView:
    @pytest.fixture
    def gv(self, qapp):
        from gantt_view import GanttView
        return GanttView()

    def test_widget_created(self, qapp):
        from gantt_view import GanttView
        assert GanttView() is not None

    def test_zoom_in_increases_day_width(self, gv):
        from gantt_view import DAY_WIDTH_DEF
        initial = gv.canvas.day_width
        gv.zoom_in()
        assert gv.canvas.day_width > initial

    def test_zoom_out_decreases_day_width(self, gv):
        initial = gv.canvas.day_width
        gv.zoom_out()
        assert gv.canvas.day_width < initial

    def test_set_day_width_clamps_to_min(self, gv):
        from gantt_view import DAY_WIDTH_MIN
        gv.set_day_width(0)
        assert gv.canvas.day_width >= DAY_WIDTH_MIN

    def test_set_day_width_clamps_to_max(self, gv):
        from gantt_view import DAY_WIDTH_MAX
        gv.set_day_width(9999)
        assert gv.canvas.day_width <= DAY_WIDTH_MAX

    def test_set_show_resource_units(self, gv):
        gv.set_show_resource_units(True)
        assert gv.canvas.show_resource_units is True
        gv.set_show_resource_units(False)
        assert gv.canvas.show_resource_units is False

    def test_set_show_sundays(self, gv):
        gv.set_show_sundays(False)
        assert gv.canvas.show_sundays is False
        gv.set_show_sundays(True)
        assert gv.canvas.show_sundays is True

    def test_set_zero_float_critical(self, gv):
        gv.set_zero_float_critical(True)
        assert gv.canvas._zero_float_critical is True

    def test_load_none_does_not_raise(self, gv):
        with patch('gantt_view._get_non_working_dates', return_value=set()):
            gv.load_project(None)

    def test_load_project_sets_tasks_on_canvas(self, qapp):
        from gantt_view import GanttView
        gv = GanttView()
        tasks = [make_mock_task(task_id=i, uid=i) for i in range(1, 3)]
        project = make_mock_project(tasks=tasks)
        with patch('gantt_view._get_non_working_dates', return_value=set()), \
             patch('gantt_view._compute_critical_ids', return_value=(set(), {})):
            gv.load_project(project)
        assert len(gv.canvas.tasks) == 2

    def test_load_project_always_calls_compute_critical_ids(self, qapp):
        """load_project must always call _compute_critical_ids, never
        _read_critical_ids, regardless of the recompute_critical flag."""
        from gantt_view import GanttView
        gv = GanttView()
        tasks = [make_mock_task(task_id=1, uid=1)]
        project = make_mock_project(tasks=tasks)
        with patch('gantt_view._get_non_working_dates', return_value=set()), \
             patch('gantt_view._compute_critical_ids', return_value=({1}, {})) as mock_cpm, \
             patch('gantt_view._read_critical_ids') as mock_read:
            gv.load_project(project, recompute_critical=False)
            mock_cpm.assert_called_once()
            mock_read.assert_not_called()

    def test_load_project_cpm_result_used_for_critical_ids(self, qapp):
        """The _critical_ids on the canvas must match the CPM result,
        not the MPXJ-stored getCritical() flag."""
        from gantt_view import GanttView
        gv = GanttView()
        task = make_mock_task(task_id=7, uid=7)
        task.getCritical.return_value = False   # MPXJ says NOT critical
        project = make_mock_project(tasks=[task])
        # CPM says task 7 IS critical
        with patch('gantt_view._get_non_working_dates', return_value=set()), \
             patch('gantt_view._compute_critical_ids', return_value=({7}, {})):
            gv.load_project(project)
        assert 7 in gv.canvas._critical_ids

    def test_signals_defined(self, gv):
        assert hasattr(gv, 'zoom_changed')
        assert hasattr(gv, 'task_moved')
        assert hasattr(gv, 'task_edited')

    # ------------------------------------------------------------------
    # set_timeline_view
    # ------------------------------------------------------------------

    def test_set_timeline_view_stores_on_canvas(self, gv):
        """set_timeline_view() must propagate the reference to the canvas."""
        tv = MagicMock()
        gv.set_timeline_view(tv)
        assert gv.canvas._timeline_view is tv

    def test_set_timeline_view_none_clears_reference(self, gv):
        """Passing None must clear a previously-set reference."""
        tv = MagicMock()
        gv.set_timeline_view(tv)
        gv.set_timeline_view(None)
        assert gv.canvas._timeline_view is None

    def test_canvas_timeline_view_initially_none(self, gv):
        """Canvas must start with _timeline_view == None."""
        assert gv.canvas._timeline_view is None

    def test_set_timeline_view_method_exists(self, gv):
        assert callable(getattr(gv, 'set_timeline_view', None))


# ---------------------------------------------------------------------------
# _task_vacation_blocks helper
# ---------------------------------------------------------------------------

def _make_assignment_with_vacation(from_str, to_str, working=False):
    """Return a mock resource assignment whose resource has one calendar exception."""
    ex = MagicMock()
    ex.getFromDate.return_value = from_str
    ex.getToDate.return_value   = to_str
    ex.getWorking.return_value  = working
    ex.getName.return_value     = "Vacation"
    cal = MagicMock()
    cal.getCalendarExceptions.return_value = [ex]
    res = MagicMock()
    res.getCalendar.return_value = cal
    asgn = MagicMock()
    asgn.getResource.return_value = res
    return asgn


class TestTaskVacationBlocks:
    def test_no_assignments_returns_empty(self):
        from gantt_view import _task_vacation_blocks
        task = MagicMock()
        task.getResourceAssignments.return_value = []
        assert _task_vacation_blocks(task) == []

    def test_assignment_no_calendar_returns_empty(self):
        from gantt_view import _task_vacation_blocks
        res = MagicMock()
        res.getCalendar.return_value = None
        asgn = MagicMock()
        asgn.getResource.return_value = res
        task = MagicMock()
        task.getResourceAssignments.return_value = [asgn]
        assert _task_vacation_blocks(task) == []

    def test_null_resource_assignment_skipped(self):
        from gantt_view import _task_vacation_blocks
        asgn = MagicMock()
        asgn.getResource.return_value = None
        task = MagicMock()
        task.getResourceAssignments.return_value = [asgn]
        assert _task_vacation_blocks(task) == []

    def test_non_working_exception_returns_one_block(self):
        from PyQt5.QtCore import QDate
        from gantt_view import _task_vacation_blocks
        asgn = _make_assignment_with_vacation("2026-05-21", "2026-06-05", working=False)
        task = MagicMock()
        task.getResourceAssignments.return_value = [asgn]
        blocks = _task_vacation_blocks(task)
        assert len(blocks) == 1
        assert blocks[0][0] == QDate(2026, 5, 21)
        assert blocks[0][1] == QDate(2026, 6, 5)

    def test_working_exception_is_skipped(self):
        from gantt_view import _task_vacation_blocks
        asgn = _make_assignment_with_vacation("2026-05-02", "2026-05-02", working=True)
        task = MagicMock()
        task.getResourceAssignments.return_value = [asgn]
        assert _task_vacation_blocks(task) == []

    def test_invalid_from_date_is_skipped(self):
        from gantt_view import _task_vacation_blocks
        asgn = _make_assignment_with_vacation("not-a-date", "2026-06-01")
        task = MagicMock()
        task.getResourceAssignments.return_value = [asgn]
        assert _task_vacation_blocks(task) == []

    def test_multiple_resources_combined(self):
        from gantt_view import _task_vacation_blocks
        asgn1 = _make_assignment_with_vacation("2026-03-10", "2026-03-14")
        asgn2 = _make_assignment_with_vacation("2026-07-01", "2026-07-05")
        task = MagicMock()
        task.getResourceAssignments.return_value = [asgn1, asgn2]
        blocks = _task_vacation_blocks(task)
        assert len(blocks) == 2

    def test_exception_suppressed_when_get_assignments_raises(self):
        from gantt_view import _task_vacation_blocks
        task = MagicMock()
        task.getResourceAssignments.side_effect = RuntimeError("JVM gone")
        assert _task_vacation_blocks(task) == []


# ---------------------------------------------------------------------------
# GanttCanvas.split_task
# ---------------------------------------------------------------------------

def _make_canvas_for_split(qapp, non_working_dates=None):
    """Return (GanttView, GanttCanvas) with _starts_on_non_working patched.
    The GanttView is returned so callers can keep it alive for the test duration.
    """
    from gantt_view import GanttView
    gv = GanttView()
    nwd = non_working_dates or set()
    from PyQt5.QtCore import QDate
    def _starts_on_nw(d: QDate) -> bool:
        dow = d.dayOfWeek()
        if dow in (6, 7):
            return True
        return d.toString("yyyy-MM-dd") in nwd
    gv.canvas._starts_on_non_working = _starts_on_nw
    gv.canvas.update = MagicMock()  # prevent C++ widget-deleted errors
    return gv, gv.canvas


class TestSplitTask:
    def _make_task(self, uid=1, start="2026-05-14", finish="2026-05-21",
                   assignments=None, summary=False, milestone=False):
        task = MagicMock()
        task.getUniqueID.return_value = uid
        task.getSummary.return_value  = summary
        task.getMilestone.return_value = milestone
        task.getName.return_value     = "Test Task"
        start_m = MagicMock(); start_m.__str__ = MagicMock(return_value=start)
        finish_m = MagicMock(); finish_m.__str__ = MagicMock(return_value=finish)
        task.getStart.return_value  = start_m
        task.getFinish.return_value = finish_m
        task.getResourceAssignments.return_value = assignments or []
        return task

    def test_split_mid_week_no_vacation(self, qapp):
        """Splitting Mon–Fri task on Wednesday places seg2 on Thursday (gap=1)."""
        from PyQt5.QtCore import QDate
        gv, canvas = _make_canvas_for_split(qapp)
        task   = self._make_task(start="2026-05-18", finish="2026-05-22")  # Mon–Fri
        result = canvas.split_task(task, QDate(2026, 5, 20))  # split on Wed
        assert result is True
        segs = canvas._task_splits[1]
        assert len(segs) == 2
        assert segs[0] == (QDate(2026, 5, 18), QDate(2026, 5, 19))  # seg1 Mon–Tue
        assert segs[1][0] == QDate(2026, 5, 21)                     # seg2 starts Thu

    def test_split_returns_false_for_summary_task(self, qapp):
        from PyQt5.QtCore import QDate
        gv, canvas = _make_canvas_for_split(qapp)
        task   = self._make_task(summary=True)
        assert canvas.split_task(task, QDate(2026, 5, 20)) is False

    def test_split_returns_false_for_milestone(self, qapp):
        from PyQt5.QtCore import QDate
        gv, canvas = _make_canvas_for_split(qapp)
        task   = self._make_task(milestone=True)
        assert canvas.split_task(task, QDate(2026, 5, 20)) is False

    def test_split_out_of_range_returns_false(self, qapp):
        """Split date before task start → False."""
        from PyQt5.QtCore import QDate
        gv, canvas = _make_canvas_for_split(qapp)
        task   = self._make_task(start="2026-05-18", finish="2026-05-22")
        assert canvas.split_task(task, QDate(2026, 5, 10)) is False

    def test_split_seg2_skips_weekend(self, qapp):
        """When seg2_start lands on Saturday, it must advance to Monday."""
        from PyQt5.QtCore import QDate
        gv, canvas = _make_canvas_for_split(qapp)
        # Task Mon May 11 – Mon May 18; split on Fri May 16
        # → seg2_start = Sat May 17 → must advance to Mon May 18
        task   = self._make_task(start="2026-05-11", finish="2026-05-18")
        result = canvas.split_task(task, QDate(2026, 5, 16))
        assert result is True
        segs = canvas._task_splits[1]
        seg2_start = segs[1][0]
        assert seg2_start.dayOfWeek() not in (6, 7)

    def test_split_seg2_skips_into_vacation(self, qapp):
        """When seg2_start lands in a resource vacation the segment is moved past it."""
        from PyQt5.QtCore import QDate
        # Build a mock assignment with vacation May 21 – Jun 5 (Marko scenario)
        asgn = _make_assignment_with_vacation("2026-05-21", "2026-06-05", working=False)
        task = self._make_task(uid=10, start="2026-05-14", finish="2026-05-21",
                               assignments=[asgn])
        gv, canvas = _make_canvas_for_split(qapp)
        # split on May 20 → seg2_start = May 21 (inside vacation)
        result = canvas.split_task(task, QDate(2026, 5, 20))
        assert result is True
        segs = canvas._task_splits[10]
        seg2_start = segs[1][0]
        # Must be after vacation end (Jun 5) and not on a weekend
        assert seg2_start > QDate(2026, 6, 5)
        assert seg2_start.dayOfWeek() not in (6, 7)

    def test_split_seg2_duration_preserved_after_vacation_skip(self, qapp):
        """seg_end must be advanced by the same amount as seg2_start when skipping vacation."""
        from PyQt5.QtCore import QDate
        asgn = _make_assignment_with_vacation("2026-05-21", "2026-06-05", working=False)
        # Task has 5 working days: May 14–21 (end inclusive)
        task = self._make_task(uid=20, start="2026-05-14", finish="2026-05-21",
                               assignments=[asgn])
        gv, canvas = _make_canvas_for_split(qapp)
        canvas.split_task(task, QDate(2026, 5, 20))
        segs = canvas._task_splits[20]
        seg2_s, seg2_e = segs[1]
        # original seg2 duration: seg2_start_orig(May 21) → seg_end(May 21) = 0 days span
        # after advance to Jun 8 (Mon after weekend): span should still be 0 days
        assert seg2_s == seg2_e  # single-day segment

    def test_split_stores_segments_in_task_splits(self, qapp):
        from PyQt5.QtCore import QDate
        gv, canvas = _make_canvas_for_split(qapp)
        task   = self._make_task(uid=5, start="2026-05-11", finish="2026-05-15")
        canvas.split_task(task, QDate(2026, 5, 12))
        assert 5 in canvas._task_splits
        assert len(canvas._task_splits[5]) == 2

    def test_split_existing_split_task(self, qapp):
        """Splitting an already-split task subdivides the correct segment."""
        from PyQt5.QtCore import QDate
        gv, canvas = _make_canvas_for_split(qapp)
        task   = self._make_task(uid=7, start="2026-05-04", finish="2026-05-15")
        # Pre-load two segments
        canvas._task_splits[7] = [
            (QDate(2026, 5, 4), QDate(2026, 5, 7)),
            (QDate(2026, 5, 11), QDate(2026, 5, 15)),
        ]
        result = canvas.split_task(task, QDate(2026, 5, 12))
        assert result is True
        assert len(canvas._task_splits[7]) == 3


# ---------------------------------------------------------------------------
# Split / Merge — history push count (regression tests for double-push bug)
# ---------------------------------------------------------------------------

class TestSplitMergeHistoryPush:
    """Verify that split / merge operations push history exactly once.

    Before the fix, _do_split_interactive and _do_merge each called
    _push_history() internally (a pre-operation snapshot), and then
    task_edited.emit() triggered a second push via _on_gantt_task_edited.
    This caused a ghost undo step on every split / merge action.

    After the fix, neither method calls _push_history() directly.
    A single history snapshot is taken when task_edited is handled by ui.py.
    """

    def _make_task(self, uid=1, start="2026-05-11", finish="2026-05-22"):
        task = MagicMock()
        task.getUniqueID.return_value = uid
        task.getSummary.return_value  = False
        task.getMilestone.return_value = False
        task.getName.return_value     = "Test Task"
        start_m  = MagicMock(); start_m.__str__  = MagicMock(return_value=start)
        finish_m = MagicMock(); finish_m.__str__ = MagicMock(return_value=finish)
        task.getStart.return_value  = start_m
        task.getFinish.return_value = finish_m
        task.getResourceAssignments.return_value = []
        return task

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _patch_split_dialog(accepted: bool, split_date=None):
        """Return an ExitStack that patches QDialog/QDateEdit in gantt_view.

        When *accepted* is True the dialog simulates the user pressing OK and
        date_edit.date() returns *split_date*.  When False the dialog rejects.
        """
        from contextlib import ExitStack
        from PyQt5.QtWidgets import QDialog as _RealQDialog

        stack = ExitStack()

        mock_dlg = MagicMock()
        mock_dlg.exec_.return_value = (
            _RealQDialog.Accepted if accepted else _RealQDialog.Rejected
        )
        MockQDialog = stack.enter_context(patch('gantt_view.QDialog'))
        MockQDialog.return_value = mock_dlg
        MockQDialog.Accepted     = _RealQDialog.Accepted   # keep the real int constant

        mock_de = MagicMock()
        if split_date is not None:
            mock_de.date.return_value = split_date
        MockQDateEdit = stack.enter_context(patch('gantt_view.QDateEdit'))
        MockQDateEdit.return_value = mock_de

        stack.enter_context(patch('gantt_view._QVBoxLayout'))
        stack.enter_context(patch('gantt_view.QLabel'))
        stack.enter_context(patch('gantt_view.QDialogButtonBox'))
        return stack

    # ------------------------------------------------------------------
    # _do_merge
    # ------------------------------------------------------------------

    def test_do_merge_does_not_call_push_history(self, qapp):
        """_do_merge must NOT call _push_history — history is handled by task_edited."""
        from PyQt5.QtCore import QDate
        gv, canvas = _make_canvas_for_split(qapp)
        task = self._make_task()
        canvas._task_splits[1] = [
            (QDate(2026, 5, 11), QDate(2026, 5, 14)),
            (QDate(2026, 5, 18), QDate(2026, 5, 22)),
        ]
        canvas._push_history = MagicMock()
        canvas._do_merge(task)
        assert canvas._push_history.call_count == 0, \
            "_push_history must not be called from _do_merge"

    def test_do_merge_emits_task_edited_exactly_once(self, qapp):
        """_do_merge must emit task_edited exactly once so history is pushed exactly once."""
        from PyQt5.QtCore import QDate
        gv, canvas = _make_canvas_for_split(qapp)
        task = self._make_task()
        canvas._task_splits[1] = [
            (QDate(2026, 5, 11), QDate(2026, 5, 14)),
            (QDate(2026, 5, 18), QDate(2026, 5, 22)),
        ]
        canvas._push_history = MagicMock()
        emitted = []
        canvas.task_edited.connect(lambda: emitted.append(1))
        canvas._do_merge(task)
        assert len(emitted) == 1, "task_edited must fire exactly once"

    # ------------------------------------------------------------------
    # _do_split_interactive
    # ------------------------------------------------------------------

    def test_do_split_interactive_success_no_push_history(self, qapp):
        """On a successful split, _push_history must NOT be called."""
        from PyQt5.QtCore import QDate
        gv, canvas = _make_canvas_for_split(qapp)
        task = self._make_task()
        canvas._push_history = MagicMock()
        with self._patch_split_dialog(accepted=True, split_date=QDate(2026, 5, 14)):
            canvas._do_split_interactive(task, None)
        assert canvas._push_history.call_count == 0, \
            "_push_history must not be called from _do_split_interactive"

    def test_do_split_interactive_success_emits_task_edited_once(self, qapp):
        """On a successful split, task_edited must be emitted exactly once."""
        from PyQt5.QtCore import QDate
        gv, canvas = _make_canvas_for_split(qapp)
        task = self._make_task()
        canvas._push_history = MagicMock()
        emitted = []
        canvas.task_edited.connect(lambda: emitted.append(1))
        with self._patch_split_dialog(accepted=True, split_date=QDate(2026, 5, 14)):
            canvas._do_split_interactive(task, None)
        assert len(emitted) == 1, "task_edited must fire exactly once on success"

    def test_do_split_interactive_cancel_no_push_no_emit(self, qapp):
        """When the dialog is cancelled, _push_history must not be called and
        task_edited must not be emitted."""
        from PyQt5.QtCore import QDate
        gv, canvas = _make_canvas_for_split(qapp)
        task = self._make_task()
        canvas._push_history = MagicMock()
        emitted = []
        canvas.task_edited.connect(lambda: emitted.append(1))
        with self._patch_split_dialog(accepted=False):
            canvas._do_split_interactive(task, None)
        assert canvas._push_history.call_count == 0, \
            "_push_history must not be called on cancel"
        assert len(emitted) == 0, "task_edited must not fire on cancel"

    def test_do_split_interactive_fail_no_push_no_emit(self, qapp):
        """When split_task() returns False (date out of range), _push_history must
        not be called and task_edited must not be emitted."""
        from PyQt5.QtCore import QDate
        gv, canvas = _make_canvas_for_split(qapp)
        # split date before task start → split_task returns False
        task = self._make_task(start="2026-05-11", finish="2026-05-22")
        canvas._push_history = MagicMock()
        emitted = []
        canvas.task_edited.connect(lambda: emitted.append(1))
        with self._patch_split_dialog(accepted=True, split_date=QDate(2026, 5, 5)), \
             patch('PyQt5.QtWidgets.QMessageBox'):
            canvas._do_split_interactive(task, None)
        assert canvas._push_history.call_count == 0, \
            "_push_history must not be called when split fails"
        assert len(emitted) == 0, "task_edited must not fire when split fails"


# ---------------------------------------------------------------------------
# _lag_to_timedelta helper (Phase 1)
# ---------------------------------------------------------------------------

class TestLagToTimedelta:
    """Tests for _lag_to_timedelta() — MPXJ Duration → Python timedelta conversion."""

    def _mock_dur(self, mag, unit_str):
        from datetime import timedelta
        dur = MagicMock()
        dur.getDuration.return_value = mag
        unit = MagicMock()
        unit.__str__ = MagicMock(return_value=unit_str)
        dur.getUnits.return_value = unit
        return dur

    def test_none_returns_zero(self):
        from gantt_view import _lag_to_timedelta
        from datetime import timedelta
        assert _lag_to_timedelta(None) == timedelta(0)

    def test_minutes_unit(self):
        from gantt_view import _lag_to_timedelta
        from datetime import timedelta
        assert _lag_to_timedelta(self._mock_dur(30.0, "MINUTES")) == timedelta(minutes=30)

    def test_hours_unit(self):
        from gantt_view import _lag_to_timedelta
        from datetime import timedelta
        assert _lag_to_timedelta(self._mock_dur(2.0, "HOURS")) == timedelta(hours=2)

    def test_days_unit_equals_480_minutes(self):
        from gantt_view import _lag_to_timedelta
        from datetime import timedelta
        # 1 DAYS = 480 minutes (8-hour working day)
        assert _lag_to_timedelta(self._mock_dur(1.0, "DAYS")) == timedelta(minutes=480)

    def test_weeks_unit_equals_2400_minutes(self):
        from gantt_view import _lag_to_timedelta
        from datetime import timedelta
        # 1 WEEKS = 2400 minutes (5 × 8h)
        assert _lag_to_timedelta(self._mock_dur(1.0, "WEEKS")) == timedelta(minutes=2400)

    def test_negative_lead(self):
        from gantt_view import _lag_to_timedelta
        from datetime import timedelta
        assert _lag_to_timedelta(self._mock_dur(-1.0, "DAYS")) == timedelta(minutes=-480)

    def test_unknown_unit_defaults_to_days(self):
        from gantt_view import _lag_to_timedelta
        from datetime import timedelta
        # Unknown unit falls back to 480 min/unit (treat as days)
        assert _lag_to_timedelta(self._mock_dur(1.0, "UNKNOWNUNIT")) == timedelta(minutes=480)


# ---------------------------------------------------------------------------
# _compute_critical_ids (Phase 1) — CPM engine
# ---------------------------------------------------------------------------

class TestComputeCriticalIds:
    """Tests for _compute_critical_ids() — CPM forward/backward pass engine."""

    def _make_task(self, tid, start, finish, preds=None, pct=0.0, children=None):
        """Build a minimal mock MPXJ task for CPM tests.

        start / finish are ISO strings like '2026-01-05T08:00'.
        preds is a list of mock relation objects.
        """
        t = MagicMock()
        t.getID.return_value = tid

        def _ldt(iso):
            m = MagicMock()
            m.__str__ = MagicMock(return_value=iso[:16])
            return m

        t.getStart.return_value  = _ldt(start)
        t.getFinish.return_value = _ldt(finish)
        t.getPredecessors.return_value = preds or []
        t.getPercentageComplete.return_value = pct
        t.getChildTasks.return_value = children  # None is falsy → leaf
        t.getConstraintType.return_value = None
        t.getConstraintDate.return_value = None
        t.getCalendar.return_value = None
        t.getResourceAssignments.return_value = []
        return t

    def _make_rel(self, pred_task, rel_type="FINISH_START"):
        """Build a mock MPXJ Relation (dependency link) with zero lag."""
        rel = MagicMock()
        rt = MagicMock()
        rt.__str__ = MagicMock(return_value=rel_type)
        rel.getType.return_value = rt
        rel.getPredecessorTask.return_value = pred_task
        lag_dur = MagicMock()
        lag_dur.getDuration.return_value = 0.0
        lag_unit = MagicMock()
        lag_unit.__str__ = MagicMock(return_value="DAYS")
        lag_dur.getUnits.return_value = lag_unit
        rel.getLag.return_value = lag_dur
        return rel

    def test_returns_set_by_default(self):
        from gantt_view import _compute_critical_ids
        t = self._make_task(1, "2026-01-05T08:00", "2026-01-09T17:00")
        result = _compute_critical_ids([t])
        assert isinstance(result, set)

    def test_returns_tuple_when_return_float_data(self):
        from gantt_view import _compute_critical_ids
        t = self._make_task(1, "2026-01-05T08:00", "2026-01-09T17:00")
        result = _compute_critical_ids([t], return_float_data=True)
        assert isinstance(result, tuple) and len(result) == 2
        crit_ids, float_data = result
        assert isinstance(crit_ids, set)
        assert isinstance(float_data, dict)

    def test_empty_tasks_returns_empty_set(self):
        from gantt_view import _compute_critical_ids
        assert _compute_critical_ids([]) == set()

    def test_empty_tasks_with_return_float_data_returns_empty_tuple(self):
        from gantt_view import _compute_critical_ids
        assert _compute_critical_ids([], return_float_data=True) == (set(), {})

    def test_single_task_is_critical_by_default(self):
        """A task with no successors has TF=0 → critical (threshold=0)."""
        from gantt_view import _compute_critical_ids
        t = self._make_task(1, "2026-01-05T08:00", "2026-01-09T17:00")
        crit, fd = _compute_critical_ids([t], return_float_data=True)
        assert 1 in crit

    def test_completed_task_not_critical(self):
        """A task at 100% complete must never appear in the critical set."""
        from gantt_view import _compute_critical_ids
        t = self._make_task(1, "2026-01-05T08:00", "2026-01-09T17:00", pct=100.0)
        crit, fd = _compute_critical_ids([t], return_float_data=True)
        assert 1 not in crit

    def test_critical_slack_days_threshold(self):
        """With critical_slack_days=2, a task with 1 day float IS critical."""
        from gantt_view import _compute_critical_ids
        # A finishes 2 days before B → TF(A) = 2 days
        t_A = self._make_task(1, "2026-01-05T08:00", "2026-01-07T17:00")
        t_B = self._make_task(2, "2026-01-05T08:00", "2026-01-09T17:00")
        crit = _compute_critical_ids([t_A, t_B], critical_slack_days=2)
        assert 1 in crit  # TF(A) ≤ 2 days → critical

    def test_float_data_contains_expected_keys(self):
        """Each float_data entry must have es, ef, ls, lf, total_float, free_float, critical."""
        from gantt_view import _compute_critical_ids
        t = self._make_task(1, "2026-01-05T08:00", "2026-01-09T17:00")
        _, fd = _compute_critical_ids([t], return_float_data=True)
        assert 1 in fd
        for key in ("es", "ef", "ls", "lf", "total_float", "free_float", "critical"):
            assert key in fd[1], f"Missing key: {key}"

    def test_free_float_is_non_negative(self):
        """Free float must never be negative."""
        from gantt_view import _compute_critical_ids
        from datetime import timedelta
        t = self._make_task(1, "2026-01-05T08:00", "2026-01-09T17:00")
        _, fd = _compute_critical_ids([t], return_float_data=True)
        assert fd[1]["free_float"] >= timedelta(0)

    def test_dep_types_fs_only_does_not_crash(self):
        """dep_types='fs_only' must filter SS dependencies without raising."""
        from gantt_view import _compute_critical_ids
        t_A = self._make_task(1, "2026-01-05T08:00", "2026-01-07T17:00")
        rel  = self._make_rel(t_A, "START_START")
        t_B  = self._make_task(2, "2026-01-08T08:00", "2026-01-12T17:00", preds=[rel])
        result = _compute_critical_ids([t_A, t_B], dep_types="fs_only")
        assert isinstance(result, set)

    def test_summary_task_critical_when_child_is_critical(self):
        """A summary task must be in the critical set when any child is critical."""
        from gantt_view import _compute_critical_ids
        child  = self._make_task(2, "2026-01-05T08:00", "2026-01-09T17:00")
        parent = self._make_task(1, "2026-01-05T08:00", "2026-01-09T17:00",
                                 children=[child])
        crit = _compute_critical_ids([parent, child])
        assert 2 in crit   # child is critical
        assert 1 in crit   # summary propagated critical

    def test_critical_ids_subset_of_float_data_keys(self):
        """Leaf IDs in the critical set must also appear in float_data."""
        from gantt_view import _compute_critical_ids
        t_A = self._make_task(1, "2026-01-05T08:00", "2026-01-09T17:00")
        t_B = self._make_task(2, "2026-01-05T08:00", "2026-01-12T17:00")
        crit, fd = _compute_critical_ids([t_A, t_B], return_float_data=True)
        # Leaf task critical IDs must be in float_data
        leaf_crits = {tid for tid in crit if tid in fd}
        assert leaf_crits.issubset(set(fd.keys()))
