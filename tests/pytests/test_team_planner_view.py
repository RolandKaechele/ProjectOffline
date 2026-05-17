"""Tests for views/team_planner_view.py — TeamPlannerView widget and helpers.

Pure helper functions (_chip_dur_str, _compute_lane_layout, _row_height_for_lanes,
_x_to_date) are tested without a QApplication.

TeamPlannerView / TeamPlannerCanvas widget tests require the session-scoped 'qapp'
fixture.  _get_non_working_dates and JPype are patched out to avoid JVM imports.
"""

import sys
import os

import pytest 
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'src')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'src', 'views')))
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from conftest import make_mock_task, make_mock_resource, make_mock_project


# ---------------------------------------------------------------------------
# _chip_dur_str helper
# ---------------------------------------------------------------------------

class TestChipDurStr:
    """_chip_dur_str converts MPXJ duration to a human-readable 'Xd' / 'Xw' label."""

    def test_five_day_task_returns_1w(self):
        from team_planner_view import _chip_dur_str
        task = make_mock_task(duration_days=5)
        assert _chip_dur_str(task) == "1w"

    def test_one_day_task_returns_1d(self):
        from team_planner_view import _chip_dur_str
        task = make_mock_task(duration_days=1)
        assert _chip_dur_str(task) == "1d"

    def test_three_day_task_returns_3d(self):
        from team_planner_view import _chip_dur_str
        task = make_mock_task(duration_days=3)
        assert _chip_dur_str(task) == "3d"

    def test_six_day_task_returns_1w_1d(self):
        from team_planner_view import _chip_dur_str
        task = make_mock_task(duration_days=6)
        assert _chip_dur_str(task) == "1w 1d"

    def test_ten_day_task_returns_2w(self):
        from team_planner_view import _chip_dur_str
        task = make_mock_task(duration_days=10)
        assert _chip_dur_str(task) == "2w"

    def test_hour_units_converted_to_days(self):
        from team_planner_view import _chip_dur_str
        task = MagicMock()
        dur = MagicMock()
        unit = MagicMock(); unit.__str__ = MagicMock(return_value="HOURS")
        dur.getDuration.return_value = 40.0   # 40 h == 5 d
        dur.getUnits.return_value    = unit
        task.getDuration.return_value = dur
        assert _chip_dur_str(task) == "1w"

    def test_week_units_converted_to_days(self):
        from team_planner_view import _chip_dur_str
        task = MagicMock()
        dur = MagicMock()
        unit = MagicMock(); unit.__str__ = MagicMock(return_value="WEEKS")
        dur.getDuration.return_value = 2.0   # 2 w == 10 d
        dur.getUnits.return_value    = unit
        task.getDuration.return_value = dur
        assert _chip_dur_str(task) == "2w"

    def test_none_duration_returns_empty(self):
        from team_planner_view import _chip_dur_str
        task = MagicMock()
        task.getDuration.return_value = None
        assert _chip_dur_str(task) == ""

    def test_exception_returns_empty(self):
        from team_planner_view import _chip_dur_str
        task = MagicMock()
        task.getDuration.side_effect = Exception("boom")
        assert _chip_dur_str(task) == ""


# ---------------------------------------------------------------------------
# _compute_lane_layout helper
# ---------------------------------------------------------------------------

class TestComputeLaneLayout:
    """_compute_lane_layout assigns overlapping tasks to separate lanes."""

    def test_empty_list_returns_empty(self):
        from team_planner_view import _compute_lane_layout
        assert _compute_lane_layout([]) == []

    def test_single_task_uses_lane_0(self):
        from team_planner_view import _compute_lane_layout
        task = make_mock_task(
            start_year=2025, start_month=1, start_day=6,
            finish_year=2025, finish_month=1, finish_day=10,
        )
        result = _compute_lane_layout([task])
        assert len(result) == 1
        assert result[0]['lane'] == 0
        assert result[0]['task'] is task

    def test_non_overlapping_tasks_share_lane_0(self):
        """Two tasks that do not overlap should both fit in lane 0."""
        from team_planner_view import _compute_lane_layout
        t1 = make_mock_task(
            task_id=1, uid=1,
            start_year=2025, start_month=1, start_day=6,
            finish_year=2025, finish_month=1, finish_day=8,
        )
        t2 = make_mock_task(
            task_id=2, uid=2,
            start_year=2025, start_month=1, start_day=13,
            finish_year=2025, finish_month=1, finish_day=17,
        )
        result = _compute_lane_layout([t1, t2])
        lanes = {e['task'].getID(): e['lane'] for e in result}
        assert lanes[1] == 0
        assert lanes[2] == 0

    def test_overlapping_tasks_use_different_lanes(self):
        """Two tasks whose date ranges overlap must be placed in different lanes."""
        from team_planner_view import _compute_lane_layout
        t1 = make_mock_task(
            task_id=1, uid=1,
            start_year=2025, start_month=1, start_day=6,
            finish_year=2025, finish_month=1, finish_day=15,
        )
        t2 = make_mock_task(
            task_id=2, uid=2,
            start_year=2025, start_month=1, start_day=8,
            finish_year=2025, finish_month=1, finish_day=17,
        )
        result = _compute_lane_layout([t1, t2])
        lanes = {e['task'].getID(): e['lane'] for e in result}
        assert lanes[1] != lanes[2]

    def test_three_overlapping_tasks_use_three_lanes(self):
        from team_planner_view import _compute_lane_layout
        tasks = [
            make_mock_task(task_id=i, uid=i,
                           start_year=2025, start_month=1, start_day=6,
                           finish_year=2025, finish_month=1, finish_day=20)
            for i in range(1, 4)
        ]
        result = _compute_lane_layout(tasks)
        used_lanes = {e['lane'] for e in result}
        assert len(used_lanes) == 3

    def test_result_sorted_by_start(self):
        """Output is sorted by start date (earliest first)."""
        from team_planner_view import _compute_lane_layout
        t1 = make_mock_task(task_id=1, uid=1,
                            start_year=2025, start_month=1, start_day=13,
                            finish_year=2025, finish_month=1, finish_day=17)
        t2 = make_mock_task(task_id=2, uid=2,
                            start_year=2025, start_month=1, start_day=6,
                            finish_year=2025, finish_month=1, finish_day=10)
        result = _compute_lane_layout([t1, t2])
        # t2 (earlier start) should appear first
        assert result[0]['task'].getID() == 2
        assert result[1]['task'].getID() == 1


# ---------------------------------------------------------------------------
# _row_height_for_lanes helper
# ---------------------------------------------------------------------------

class TestRowHeightForLanes:
    def test_single_lane_returns_at_least_row_h(self):
        from team_planner_view import _row_height_for_lanes, ROW_H
        assert _row_height_for_lanes(1) >= ROW_H

    def test_more_lanes_increases_height(self):
        from team_planner_view import _row_height_for_lanes
        assert _row_height_for_lanes(2) > _row_height_for_lanes(1)

    def test_three_lanes_more_than_two(self):
        from team_planner_view import _row_height_for_lanes
        assert _row_height_for_lanes(3) > _row_height_for_lanes(2)


# ---------------------------------------------------------------------------
# Layout / colour constants
# ---------------------------------------------------------------------------

class TestLayoutConstants:
    def test_resource_col_width_positive(self):
        from team_planner_view import RESOURCE_COL_W
        assert RESOURCE_COL_W > 0

    def test_row_h_positive(self):
        from team_planner_view import ROW_H
        assert ROW_H > 0

    def test_task_bar_h_less_than_row_h(self):
        from team_planner_view import TASK_BAR_H, ROW_H
        assert TASK_BAR_H < ROW_H

    def test_chip_dimensions_positive(self):
        from team_planner_view import CHIP_H, CHIP_W
        assert CHIP_H > 0
        assert CHIP_W > 0

    def test_ua_section_height_positive(self):
        from team_planner_view import UA_SECTION_H
        assert UA_SECTION_H > 0

    def test_day_width_range_consistent(self):
        from gantt_view import DAY_WIDTH_DEF, DAY_WIDTH_MIN, DAY_WIDTH_MAX
        assert DAY_WIDTH_MIN <= DAY_WIDTH_DEF <= DAY_WIDTH_MAX


# ---------------------------------------------------------------------------
# TeamPlannerCanvas — unit tests (with qapp)
# ---------------------------------------------------------------------------

class TestTeamPlannerCanvas:
    @pytest.fixture
    def canvas(self, qapp):
        with patch('team_planner_view._get_non_working_dates', return_value=set()):
            from team_planner_view import TeamPlannerCanvas
            return TeamPlannerCanvas()

    def test_widget_created(self, qapp):
        from team_planner_view import TeamPlannerCanvas
        assert TeamPlannerCanvas() is not None

    def test_load_none_does_not_raise(self, canvas):
        canvas.load_project(None)   # must not raise

    def test_load_none_clears_resources(self, canvas):
        canvas.load_project(None)
        assert canvas._resources == []

    def test_load_none_clears_unassigned(self, canvas):
        canvas.load_project(None)
        assert canvas._unassigned == []

    def test_load_project_populates_resources(self, qapp):
        res = make_mock_resource(res_id=1, name="Alice")
        project = make_mock_project(tasks=[], resources=[res])
        with patch('team_planner_view._get_non_working_dates', return_value=set()):
            from team_planner_view import TeamPlannerCanvas
            canvas = TeamPlannerCanvas()
            canvas.load_project(project)
        assert len(canvas._resources) == 1
        assert canvas._res_names == ["Alice"]

    def test_load_project_null_resource_excluded(self, qapp):
        """Resources whose getName() returns None must be filtered out."""
        res_null = MagicMock()
        res_null.getName.return_value = None
        project = make_mock_project(tasks=[], resources=[res_null])
        with patch('team_planner_view._get_non_working_dates', return_value=set()):
            from team_planner_view import TeamPlannerCanvas
            canvas = TeamPlannerCanvas()
            canvas.load_project(project)
        assert canvas._resources == []

    def test_assigned_task_not_in_unassigned(self, qapp):
        """A task that has a resource assignment must not appear in _unassigned."""
        res  = make_mock_resource(res_id=1, name="Bob")
        task = make_mock_task(task_id=1, uid=1)
        # Build assignment mock linking task → resource
        asgn = MagicMock()
        asgn.getResource.return_value = res
        res.getUniqueID.return_value = 1
        task.getResourceAssignments.return_value = [asgn]
        project = make_mock_project(tasks=[task], resources=[res])
        with patch('team_planner_view._get_non_working_dates', return_value=set()):
            from team_planner_view import TeamPlannerCanvas
            canvas = TeamPlannerCanvas()
            canvas.load_project(project)
        assert task not in canvas._unassigned

    def test_unassigned_task_appears_in_unassigned(self, qapp):
        """A non-summary leaf task with no assignment must land in _unassigned."""
        res  = make_mock_resource(res_id=1, name="Carol")
        task = make_mock_task(task_id=2, uid=2)
        task.getResourceAssignments.return_value = []
        task.getSummary.return_value = False
        project = make_mock_project(tasks=[task], resources=[res])
        with patch('team_planner_view._get_non_working_dates', return_value=set()):
            from team_planner_view import TeamPlannerCanvas
            canvas = TeamPlannerCanvas()
            canvas.load_project(project)
        assert task in canvas._unassigned

    def test_summary_task_excluded_from_unassigned(self, qapp):
        """Summary (parent) tasks must not appear in _unassigned even when unassigned."""
        res  = make_mock_resource(res_id=1, name="Dave")
        task = make_mock_task(task_id=3, uid=3, is_summary=True)
        task.getResourceAssignments.return_value = []
        task.getSummary.return_value = True
        project = make_mock_project(tasks=[task], resources=[res])
        with patch('team_planner_view._get_non_working_dates', return_value=set()):
            from team_planner_view import TeamPlannerCanvas
            canvas = TeamPlannerCanvas()
            canvas.load_project(project)
        assert task not in canvas._unassigned

    def test_set_day_width_clamps_to_min(self, canvas):
        from gantt_view import DAY_WIDTH_MIN
        canvas.set_day_width(0)
        assert canvas.day_width >= DAY_WIDTH_MIN

    def test_set_day_width_clamps_to_max(self, canvas):
        from gantt_view import DAY_WIDTH_MAX
        canvas.set_day_width(9999)
        assert canvas.day_width <= DAY_WIDTH_MAX

    def test_set_show_sundays_stores_value(self, canvas):
        canvas.set_show_sundays(False)
        assert canvas.show_sundays is False
        canvas.set_show_sundays(True)
        assert canvas.show_sundays is True

    def test_task_rescheduled_signal_exists(self, canvas):
        from PyQt5.QtCore import pyqtSignal
        assert hasattr(canvas, 'task_rescheduled')

    def test_task_reassigned_signal_exists(self, canvas):
        assert hasattr(canvas, 'task_reassigned')

    def test_layout_changed_signal_exists(self, canvas):
        assert hasattr(canvas, 'layout_changed')

    def test_unassigned_changed_signal_exists(self, canvas):
        assert hasattr(canvas, 'unassigned_changed')

    def test_y_to_row_returns_minus_one_below_all_rows(self, canvas):
        """_y_to_row should return -1 when y is beyond the resource rows area."""
        canvas._resources = []
        canvas._row_y_off = []
        canvas._row_heights = []
        canvas._ua_y = 0
        assert canvas._y_to_row(500) == -1

    def test_y_to_row_returns_zero_when_above_canvas(self, canvas):
        """Negative y should clamp to row 0."""
        canvas._resources = [MagicMock()]
        canvas._row_y_off = [0]
        canvas._row_heights = [44]
        canvas._ua_y = 44
        assert canvas._y_to_row(-5) == 0


# ---------------------------------------------------------------------------
# TeamPlannerView — public API and signals
# ---------------------------------------------------------------------------

class TestTeamPlannerView:
    @pytest.fixture
    def tpv(self, qapp):
        with patch('team_planner_view._get_non_working_dates', return_value=set()):
            from team_planner_view import TeamPlannerView
            return TeamPlannerView()

    def test_widget_created(self, qapp):
        from team_planner_view import TeamPlannerView
        assert TeamPlannerView() is not None

    def test_data_changed_signal_exists(self, tpv):
        assert hasattr(tpv, 'data_changed')

    def test_canvas_attribute_exists(self, tpv):
        from team_planner_view import TeamPlannerCanvas
        assert isinstance(tpv.canvas, TeamPlannerCanvas)

    def test_load_none_does_not_raise(self, tpv):
        tpv.load_project(None)

    def test_load_project_updates_canvas_resources(self, qapp):
        res = make_mock_resource(res_id=1, name="Eve")
        project = make_mock_project(tasks=[], resources=[res])
        with patch('team_planner_view._get_non_working_dates', return_value=set()):
            from team_planner_view import TeamPlannerView
            tpv = TeamPlannerView()
            tpv.load_project(project)
        assert len(tpv.canvas._resources) == 1

    def test_load_project_replaces_previous(self, qapp):
        res1 = make_mock_resource(res_id=1, name="Res1")
        res2 = make_mock_resource(res_id=2, name="Res2")
        proj1 = make_mock_project(tasks=[], resources=[res1])
        proj2 = make_mock_project(tasks=[], resources=[res1, res2])
        with patch('team_planner_view._get_non_working_dates', return_value=set()):
            from team_planner_view import TeamPlannerView
            tpv = TeamPlannerView()
            tpv.load_project(proj1)
            assert len(tpv.canvas._resources) == 1
            tpv.load_project(proj2)
            assert len(tpv.canvas._resources) == 2

    def test_set_day_width_propagates_to_canvas(self, tpv):
        from gantt_view import DAY_WIDTH_DEF
        tpv.set_day_width(DAY_WIDTH_DEF + 8)
        assert tpv.canvas.day_width == DAY_WIDTH_DEF + 8

    def test_set_show_sundays_propagates_to_canvas(self, tpv):
        tpv.set_show_sundays(False)
        assert tpv.canvas.show_sundays is False

    def test_unassigned_label_updates_on_load(self, qapp):
        """After loading a project with one unassigned task the counter label shows (1)."""
        res  = make_mock_resource(res_id=1, name="Frank")
        task = make_mock_task(task_id=1, uid=1)
        task.getResourceAssignments.return_value = []
        task.getSummary.return_value = False
        project = make_mock_project(tasks=[task], resources=[res])
        with patch('team_planner_view._get_non_working_dates', return_value=set()):
            from team_planner_view import TeamPlannerView
            tpv = TeamPlannerView()
            tpv.load_project(project)
        assert "(1)" in tpv._ua_col_label.text()

    def test_unassigned_label_zero_on_empty(self, tpv):
        tpv.load_project(None)
        assert "(0)" in tpv._ua_col_label.text()


# ---------------------------------------------------------------------------
# _PlacementDialog
# ---------------------------------------------------------------------------

class TestPlacementDialog:
    def test_default_choice_is_cancel(self, qapp):
        from team_planner_view import _PlacementDialog
        dlg = _PlacementDialog("Task A", "Resource B")
        assert dlg.choice() == _PlacementDialog.CANCEL

    def test_serial_constant(self):
        from team_planner_view import _PlacementDialog
        assert _PlacementDialog.SERIAL == "serial"

    def test_parallel_constant(self):
        from team_planner_view import _PlacementDialog
        assert _PlacementDialog.PARALLEL == "parallel"

    def test_cancel_constant(self):
        from team_planner_view import _PlacementDialog
        assert _PlacementDialog.CANCEL == "cancel"


# ---------------------------------------------------------------------------
# _get_resource_vacation_blocks
# ---------------------------------------------------------------------------

def _make_mock_exception(from_str, to_str, name="Vacation", working=False):
    """Helper: return a mock MPXJ ProjectCalendarException."""
    ex = MagicMock()
    ex.getFromDate.return_value = from_str
    ex.getToDate.return_value   = to_str
    ex.getName.return_value     = name
    ex.getWorking.return_value  = working
    return ex


def _make_resource_with_calendar(exceptions):
    """Helper: resource whose calendar returns the given list of exceptions."""
    res = MagicMock()
    cal = MagicMock()
    cal.getName.return_value = None
    cal.getCalendarExceptions.return_value = exceptions
    res.getCalendar.return_value = cal
    return res


class TestGetResourceVacationBlocks:
    def test_no_calendar_returns_empty(self):
        from team_planner_view import _get_resource_vacation_blocks
        res = MagicMock()
        res.getCalendar.return_value = None
        assert _get_resource_vacation_blocks(res) == []

    def test_no_exceptions_returns_empty(self):
        from team_planner_view import _get_resource_vacation_blocks
        res = _make_resource_with_calendar([])
        assert _get_resource_vacation_blocks(res) == []

    def test_non_working_exception_returns_one_block(self):
        from team_planner_view import _get_resource_vacation_blocks
        ex  = _make_mock_exception("2025-07-14", "2025-07-18", "Summer Vacation", working=False)
        res = _make_resource_with_calendar([ex])
        blocks = _get_resource_vacation_blocks(res)
        assert len(blocks) == 1
        assert blocks[0]['name'] == "Summer Vacation"

    def test_working_exception_is_skipped(self):
        from team_planner_view import _get_resource_vacation_blocks
        ex  = _make_mock_exception("2025-08-01", "2025-08-01", "Working Saturday", working=True)
        res = _make_resource_with_calendar([ex])
        assert _get_resource_vacation_blocks(res) == []

    def test_block_has_correct_from_date(self):
        from PyQt5.QtCore import QDate
        from team_planner_view import _get_resource_vacation_blocks
        ex  = _make_mock_exception("2025-03-10", "2025-03-14")
        res = _make_resource_with_calendar([ex])
        blocks = _get_resource_vacation_blocks(res)
        assert blocks[0]['from_qd'] == QDate(2025, 3, 10)

    def test_block_has_correct_to_date(self):
        from PyQt5.QtCore import QDate
        from team_planner_view import _get_resource_vacation_blocks
        ex  = _make_mock_exception("2025-03-10", "2025-03-14")
        res = _make_resource_with_calendar([ex])
        blocks = _get_resource_vacation_blocks(res)
        assert blocks[0]['to_qd'] == QDate(2025, 3, 14)

    def test_missing_to_date_defaults_to_from_date(self):
        from PyQt5.QtCore import QDate
        from team_planner_view import _get_resource_vacation_blocks
        ex  = _make_mock_exception("2025-05-01", "", "Single Day")
        res = _make_resource_with_calendar([ex])
        blocks = _get_resource_vacation_blocks(res)
        assert len(blocks) == 1
        assert blocks[0]['from_qd'] == blocks[0]['to_qd']

    def test_none_name_defaults_to_vacation_string(self):
        from team_planner_view import _get_resource_vacation_blocks
        ex = _make_mock_exception("2025-06-01", "2025-06-05")
        ex.getName.return_value = None
        res = _make_resource_with_calendar([ex])
        blocks = _get_resource_vacation_blocks(res)
        assert blocks[0]['name'] == "Vacation"

    def test_blocks_sorted_by_from_date(self):
        from team_planner_view import _get_resource_vacation_blocks
        ex1 = _make_mock_exception("2025-09-01", "2025-09-05", "Late")
        ex2 = _make_mock_exception("2025-03-01", "2025-03-05", "Early")
        res = _make_resource_with_calendar([ex1, ex2])
        blocks = _get_resource_vacation_blocks(res)
        assert blocks[0]['name'] == "Early"
        assert blocks[1]['name'] == "Late"

    def test_exception_stored_in_block(self):
        from team_planner_view import _get_resource_vacation_blocks
        ex  = _make_mock_exception("2025-12-24", "2025-12-26", "Christmas")
        res = _make_resource_with_calendar([ex])
        blocks = _get_resource_vacation_blocks(res)
        assert blocks[0]['exception'] is ex

    def test_invalid_from_date_skips_block(self):
        from team_planner_view import _get_resource_vacation_blocks
        ex  = _make_mock_exception("not-a-date", "2025-06-01")
        res = _make_resource_with_calendar([ex])
        assert _get_resource_vacation_blocks(res) == []

    def test_calendar_exception_suppressed(self):
        """If the resource raises on getCalendar(), return empty without crashing."""
        from team_planner_view import _get_resource_vacation_blocks
        res = MagicMock()
        res.getCalendar.side_effect = RuntimeError("JVM error")
        assert _get_resource_vacation_blocks(res) == []


# ---------------------------------------------------------------------------
# TeamPlannerCanvas._overlaps_vacation
# ---------------------------------------------------------------------------

class TestOverlapsVacation:
    @pytest.fixture
    def canvas_with_vacation(self, qapp):
        from PyQt5.QtCore import QDate
        with patch('team_planner_view._get_non_working_dates', return_value=set()):
            from team_planner_view import TeamPlannerCanvas
            c = TeamPlannerCanvas()
        # Manually inject one resource and one vacation block
        res = MagicMock()
        res.getUniqueID.return_value = 1
        c._resources = [res]
        c._vacations_by_res = {
            1: [{'from_qd': QDate(2025, 7, 14), 'to_qd': QDate(2025, 7, 18),
                 'name': 'Vacation', 'exception': MagicMock()}]
        }
        return c

    def test_no_vacations_returns_false(self, qapp):
        from PyQt5.QtCore import QDate
        with patch('team_planner_view._get_non_working_dates', return_value=set()):
            from team_planner_view import TeamPlannerCanvas
            c = TeamPlannerCanvas()
        res = MagicMock()
        res.getUniqueID.return_value = 99
        c._resources = [res]
        c._vacations_by_res = {}
        assert c._overlaps_vacation(0, QDate(2025, 7, 14), QDate(2025, 7, 18)) is False

    def test_non_overlapping_before_vacation_returns_false(self, canvas_with_vacation):
        from PyQt5.QtCore import QDate
        assert canvas_with_vacation._overlaps_vacation(
            0, QDate(2025, 7, 1), QDate(2025, 7, 13)
        ) is False

    def test_non_overlapping_after_vacation_returns_false(self, canvas_with_vacation):
        from PyQt5.QtCore import QDate
        assert canvas_with_vacation._overlaps_vacation(
            0, QDate(2025, 7, 19), QDate(2025, 7, 25)
        ) is False

    def test_task_fully_inside_vacation_returns_true(self, canvas_with_vacation):
        from PyQt5.QtCore import QDate
        assert canvas_with_vacation._overlaps_vacation(
            0, QDate(2025, 7, 15), QDate(2025, 7, 17)
        ) is True

    def test_task_starts_before_and_ends_inside_vacation_returns_true(self, canvas_with_vacation):
        from PyQt5.QtCore import QDate
        assert canvas_with_vacation._overlaps_vacation(
            0, QDate(2025, 7, 10), QDate(2025, 7, 16)
        ) is True

    def test_task_starts_inside_and_ends_after_vacation_returns_true(self, canvas_with_vacation):
        from PyQt5.QtCore import QDate
        assert canvas_with_vacation._overlaps_vacation(
            0, QDate(2025, 7, 16), QDate(2025, 7, 22)
        ) is True

    def test_task_spans_entire_vacation_returns_true(self, canvas_with_vacation):
        from PyQt5.QtCore import QDate
        assert canvas_with_vacation._overlaps_vacation(
            0, QDate(2025, 7, 1), QDate(2025, 7, 31)
        ) is True

    def test_invalid_row_index_returns_false(self, canvas_with_vacation):
        from PyQt5.QtCore import QDate
        assert canvas_with_vacation._overlaps_vacation(
            5, QDate(2025, 7, 15), QDate(2025, 7, 17)
        ) is False

    def test_negative_row_index_returns_false(self, canvas_with_vacation):
        from PyQt5.QtCore import QDate
        assert canvas_with_vacation._overlaps_vacation(
            -1, QDate(2025, 7, 15), QDate(2025, 7, 17)
        ) is False

    def test_none_finish_treated_as_start_plus_one_day(self, canvas_with_vacation):
        """When finish_qd is None the method should use start + 1 day."""
        from PyQt5.QtCore import QDate
        # task start is inside the vacation (14–18 July) with no finish
        assert canvas_with_vacation._overlaps_vacation(
            0, QDate(2025, 7, 15), None
        ) is True


# ---------------------------------------------------------------------------
# TeamPlannerCanvas._compute_conflict_data
# ---------------------------------------------------------------------------

def _make_canvas_with_tasks(tasks_by_uid, vacations_by_uid=None, qapp=None):
    """Helper: build a canvas pre-loaded with lane data and vacation blocks."""
    with patch('team_planner_view._get_non_working_dates', return_value=set()):
        from team_planner_view import TeamPlannerCanvas, _compute_lane_layout
        c = TeamPlannerCanvas()

    resources = []
    for uid, tasks in tasks_by_uid.items():
        res = MagicMock()
        res.getUniqueID.return_value = uid
        res.getName.return_value     = f"Res{uid}"
        res.getCalendar.return_value = None
        resources.append(res)

    c._resources       = resources
    c._tasks_by_res    = {uid: list(tasks) for uid, tasks in tasks_by_uid.items()}
    c._vacations_by_res = vacations_by_uid or {}

    # Build lane data
    from team_planner_view import _compute_lane_layout
    c._lane_data = {uid: _compute_lane_layout(tasks)
                    for uid, tasks in tasks_by_uid.items()}
    return c


class TestComputeConflictData:
    def test_no_resources_returns_empty_lists(self, qapp):
        with patch('team_planner_view._get_non_working_dates', return_value=set()):
            from team_planner_view import TeamPlannerCanvas
            c = TeamPlannerCanvas()
        c._resources       = []
        c._tasks_by_res    = {}
        c._vacations_by_res = {}
        c._lane_data       = {}
        flags, tips = c._compute_conflict_data()
        assert flags == []
        assert tips  == []

    def test_single_task_no_vacation_no_conflict(self, qapp):
        task = make_mock_task(task_id=1, uid=1,
                              start_year=2025, start_month=6, start_day=2,
                              finish_year=2025, finish_month=6, finish_day=6)
        c = _make_canvas_with_tasks({1: [task]})
        flags, tips = c._compute_conflict_data()
        assert flags == [False]
        assert tips  == ['']

    def test_non_overlapping_tasks_no_conflict(self, qapp):
        t1 = make_mock_task(task_id=1, uid=1,
                            start_year=2025, start_month=1, start_day=6,
                            finish_year=2025, finish_month=1, finish_day=10)
        t2 = make_mock_task(task_id=2, uid=2,
                            start_year=2025, start_month=1, start_day=13,
                            finish_year=2025, finish_month=1, finish_day=17)
        # Two tasks on two separate resources — no overlap within same resource
        c = _make_canvas_with_tasks({1: [t1], 2: [t2]})
        flags, tips = c._compute_conflict_data()
        assert flags == [False, False]

    def test_overlapping_tasks_on_same_resource_conflict(self, qapp):
        t1 = make_mock_task(task_id=1, uid=1, name="Task A",
                            start_year=2025, start_month=3, start_day=3,
                            finish_year=2025, finish_month=3, finish_day=10)
        t2 = make_mock_task(task_id=2, uid=2, name="Task B",
                            start_year=2025, start_month=3, start_day=6,
                            finish_year=2025, finish_month=3, finish_day=14)
        # Both tasks belong to resource uid=1
        c = _make_canvas_with_tasks({1: [t1, t2]})
        flags, tips = c._compute_conflict_data()
        assert flags[0] is True

    def test_overlap_tooltip_contains_task_names(self, qapp):
        t1 = make_mock_task(task_id=1, uid=1, name="Alpha",
                            start_year=2025, start_month=3, start_day=3,
                            finish_year=2025, finish_month=3, finish_day=10)
        t2 = make_mock_task(task_id=2, uid=2, name="Beta",
                            start_year=2025, start_month=3, start_day=6,
                            finish_year=2025, finish_month=3, finish_day=14)
        c = _make_canvas_with_tasks({1: [t1, t2]})
        _, tips = c._compute_conflict_data()
        assert "Alpha" in tips[0]
        assert "Beta" in tips[0]

    def test_task_on_vacation_raises_conflict(self, qapp):
        from PyQt5.QtCore import QDate
        task = make_mock_task(task_id=1, uid=1, name="Holiday Task",
                              start_year=2025, start_month=7, start_day=15,
                              finish_year=2025, finish_month=7, finish_day=17)
        vacs = {1: [{'from_qd': QDate(2025, 7, 14), 'to_qd': QDate(2025, 7, 18),
                     'name': 'Summer', 'exception': MagicMock()}]}
        c = _make_canvas_with_tasks({1: [task]}, vacations_by_uid=vacs)
        flags, _ = c._compute_conflict_data()
        assert flags[0] is True

    def test_task_on_vacation_tooltip_contains_vacation_name(self, qapp):
        from PyQt5.QtCore import QDate
        task = make_mock_task(task_id=1, uid=1, name="Meeting",
                              start_year=2025, start_month=7, start_day=15,
                              finish_year=2025, finish_month=7, finish_day=16)
        vacs = {1: [{'from_qd': QDate(2025, 7, 14), 'to_qd': QDate(2025, 7, 18),
                     'name': 'Summer Break', 'exception': MagicMock()}]}
        c = _make_canvas_with_tasks({1: [task]}, vacations_by_uid=vacs)
        _, tips = c._compute_conflict_data()
        assert "Summer Break" in tips[0]

    def test_task_not_on_vacation_no_conflict(self, qapp):
        from PyQt5.QtCore import QDate
        task = make_mock_task(task_id=1, uid=1,
                              start_year=2025, start_month=6, start_day=2,
                              finish_year=2025, finish_month=6, finish_day=6)
        vacs = {1: [{'from_qd': QDate(2025, 7, 14), 'to_qd': QDate(2025, 7, 18),
                     'name': 'Summer', 'exception': MagicMock()}]}
        c = _make_canvas_with_tasks({1: [task]}, vacations_by_uid=vacs)
        flags, _ = c._compute_conflict_data()
        assert flags[0] is False

    def test_tooltip_empty_when_no_conflict(self, qapp):
        task = make_mock_task(task_id=1, uid=1,
                              start_year=2025, start_month=2, start_day=3,
                              finish_year=2025, finish_month=2, finish_day=7)
        c = _make_canvas_with_tasks({1: [task]})
        _, tips = c._compute_conflict_data()
        assert tips[0] == ''

    def test_result_has_same_length_as_resources(self, qapp):
        t1 = make_mock_task(task_id=1, uid=1)
        t2 = make_mock_task(task_id=2, uid=2)
        t3 = make_mock_task(task_id=3, uid=3)
        c = _make_canvas_with_tasks({1: [t1], 2: [t2], 3: [t3]})
        flags, tips = c._compute_conflict_data()
        assert len(flags) == 3
        assert len(tips)  == 3


# ---------------------------------------------------------------------------
# New signals — conflicts_changed and conflict_tooltips_changed
# ---------------------------------------------------------------------------

class TestNewCanvasSignals:
    def test_conflicts_changed_signal_exists(self, qapp):
        with patch('team_planner_view._get_non_working_dates', return_value=set()):
            from team_planner_view import TeamPlannerCanvas
            c = TeamPlannerCanvas()
        assert hasattr(c, 'conflicts_changed')

    def test_conflict_tooltips_changed_signal_exists(self, qapp):
        with patch('team_planner_view._get_non_working_dates', return_value=set()):
            from team_planner_view import TeamPlannerCanvas
            c = TeamPlannerCanvas()
        assert hasattr(c, 'conflict_tooltips_changed')

    def test_load_project_emits_conflicts_changed(self, qapp):
        received = []
        res = make_mock_resource(res_id=1, name="Alice")
        project = make_mock_project(tasks=[], resources=[res])
        with patch('team_planner_view._get_non_working_dates', return_value=set()):
            from team_planner_view import TeamPlannerCanvas
            c = TeamPlannerCanvas()
        c.conflicts_changed.connect(lambda v: received.append(v))
        c.load_project(project)
        assert len(received) >= 1

    def test_load_project_emits_conflict_tooltips_changed(self, qapp):
        received = []
        res = make_mock_resource(res_id=1, name="Bob")
        project = make_mock_project(tasks=[], resources=[res])
        with patch('team_planner_view._get_non_working_dates', return_value=set()):
            from team_planner_view import TeamPlannerCanvas
            c = TeamPlannerCanvas()
        c.conflict_tooltips_changed.connect(lambda v: received.append(v))
        c.load_project(project)
        assert len(received) >= 1


# ---------------------------------------------------------------------------
# _VacationDialog
# ---------------------------------------------------------------------------

class TestVacationDialog:
    @pytest.fixture
    def vacation_block(self):
        from PyQt5.QtCore import QDate
        return {
            'from_qd': QDate(2025, 8, 4),
            'to_qd':   QDate(2025, 8, 8),
            'name':    'Summer Break',
            'exception': MagicMock(),
        }

    def test_dialog_instantiates(self, qapp, vacation_block):
        from team_planner_view import _VacationDialog
        dlg = _VacationDialog(vacation_block, "Alice")
        assert dlg is not None

    def test_dialog_is_modal(self, qapp, vacation_block):
        from team_planner_view import _VacationDialog
        dlg = _VacationDialog(vacation_block, "Alice")
        assert dlg.isModal()

    def test_dialog_title_contains_vacation(self, qapp, vacation_block):
        from team_planner_view import _VacationDialog
        dlg = _VacationDialog(vacation_block, "Alice")
        assert "Vacation" in dlg.windowTitle() or "Calendar" in dlg.windowTitle()

    def test_dialog_has_no_editable_line_edits(self, qapp, vacation_block):
        """All fields are read-only labels — no QLineEdit should be present."""
        from PyQt5.QtWidgets import QLineEdit
        from team_planner_view import _VacationDialog
        dlg = _VacationDialog(vacation_block, "Alice")
        assert len(dlg.findChildren(QLineEdit)) == 0


# ---------------------------------------------------------------------------
# Segment-drag vacation-overlap guard
# (tests _get_resource_vacation_blocks overlap condition used in mouseReleaseEvent)
# ---------------------------------------------------------------------------

def _make_vac_block(from_str, to_str, name="Vacation"):
    """Helper: return a vacation-block dict as produced by _get_resource_vacation_blocks."""
    from PyQt5.QtCore import QDate
    return {
        'from_qd': QDate.fromString(from_str, "yyyy-MM-dd"),
        'to_qd':   QDate.fromString(to_str,   "yyyy-MM-dd"),
        'name':    name,
        'exception': MagicMock(),
    }


def _vacation_overlaps_segment(vac, seg_s, seg_e):
    """Pure-Python replication of the overlap condition used in team_planner_view."""
    return seg_s <= vac['to_qd'] and seg_e >= vac['from_qd']


class TestSegmentVacationOverlapCondition:
    """Verify the overlap predicate used to decide whether to show a dialog.

    The condition is:  new_seg_s <= vac_to  AND  new_seg_e >= vac_from
    All four overlap geometries must trigger; non-overlapping cases must not.
    """

    def test_segment_fully_before_vacation_no_overlap(self):
        from PyQt5.QtCore import QDate
        vac   = _make_vac_block("2026-05-21", "2026-06-05")
        seg_s = QDate(2026, 5, 11)
        seg_e = QDate(2026, 5, 15)
        assert _vacation_overlaps_segment(vac, seg_s, seg_e) is False

    def test_segment_fully_after_vacation_no_overlap(self):
        from PyQt5.QtCore import QDate
        vac   = _make_vac_block("2026-05-21", "2026-06-05")
        seg_s = QDate(2026, 6, 8)
        seg_e = QDate(2026, 6, 12)
        assert _vacation_overlaps_segment(vac, seg_s, seg_e) is False

    def test_segment_fully_inside_vacation_overlaps(self):
        from PyQt5.QtCore import QDate
        vac   = _make_vac_block("2026-05-21", "2026-06-05")
        seg_s = QDate(2026, 5, 25)
        seg_e = QDate(2026, 5, 29)
        assert _vacation_overlaps_segment(vac, seg_s, seg_e) is True

    def test_segment_starts_before_ends_inside_vacation_overlaps(self):
        """Segment end extends into vacation start — the reported bug scenario."""
        from PyQt5.QtCore import QDate
        vac   = _make_vac_block("2026-05-21", "2026-06-05")
        seg_s = QDate(2026, 5, 19)  # before vacation
        seg_e = QDate(2026, 5, 24)  # inside vacation
        assert _vacation_overlaps_segment(vac, seg_s, seg_e) is True

    def test_segment_starts_inside_ends_after_vacation_overlaps(self):
        from PyQt5.QtCore import QDate
        vac   = _make_vac_block("2026-05-21", "2026-06-05")
        seg_s = QDate(2026, 5, 28)  # inside vacation
        seg_e = QDate(2026, 6, 10)  # after vacation
        assert _vacation_overlaps_segment(vac, seg_s, seg_e) is True

    def test_segment_straddles_entire_vacation_overlaps(self):
        from PyQt5.QtCore import QDate
        vac   = _make_vac_block("2026-05-21", "2026-06-05")
        seg_s = QDate(2026, 5, 14)
        seg_e = QDate(2026, 6, 12)
        assert _vacation_overlaps_segment(vac, seg_s, seg_e) is True

    def test_segment_touches_vacation_start_exactly_overlaps(self):
        """Segment ending exactly on vacation start date counts as overlap."""
        from PyQt5.QtCore import QDate
        vac   = _make_vac_block("2026-05-21", "2026-06-05")
        seg_s = QDate(2026, 5, 18)
        seg_e = QDate(2026, 5, 21)  # = vac_from
        assert _vacation_overlaps_segment(vac, seg_s, seg_e) is True

    def test_segment_touches_vacation_end_exactly_overlaps(self):
        """Segment starting exactly on vacation end date counts as overlap."""
        from PyQt5.QtCore import QDate
        vac   = _make_vac_block("2026-05-21", "2026-06-05")
        seg_s = QDate(2026, 6, 5)   # = vac_to
        seg_e = QDate(2026, 6, 9)
        assert _vacation_overlaps_segment(vac, seg_s, seg_e) is True

    def test_segment_ends_day_before_vacation_no_overlap(self):
        """Segment ending strictly before vacation start — boundary must not fire."""
        from PyQt5.QtCore import QDate
        vac   = _make_vac_block("2026-05-21", "2026-06-05")
        seg_s = QDate(2026, 5, 18)
        seg_e = QDate(2026, 5, 20)  # strictly before vac_from
        assert _vacation_overlaps_segment(vac, seg_s, seg_e) is False

    def test_segment_starts_day_after_vacation_no_overlap(self):
        """Segment starting strictly after vacation end — must not fire."""
        from PyQt5.QtCore import QDate
        vac   = _make_vac_block("2026-05-21", "2026-06-05")
        seg_s = QDate(2026, 6, 6)   # strictly after vac_to
        seg_e = QDate(2026, 6, 10)
        assert _vacation_overlaps_segment(vac, seg_s, seg_e) is False


# ---------------------------------------------------------------------------
# Resource filter and UID handling in load_project()
# ---------------------------------------------------------------------------

class TestResourceFilterAndUid:
    """Tests for bug fixes in TeamPlannerCanvas.load_project():

    1. Resources with null/unparseable UID are no longer filtered out — they
       still appear as (empty) rows in the Team Planner.
    2. _safe_uid() catches all exceptions (not just ValueError/TypeError), so
       JVM errors during getUniqueID() do not crash the load.
    """

    def test_resource_with_null_uid_included_in_resources(self, qapp):
        """Resource whose getUniqueID() returns None must still appear in
        canvas._resources as long as it has a valid name."""
        with patch('team_planner_view._get_non_working_dates', return_value=set()):
            from team_planner_view import TeamPlannerCanvas
            canvas = TeamPlannerCanvas()
        res = MagicMock()
        res.getName.return_value = "Alice"
        res.getUniqueID.return_value = None
        res.getCalendar.return_value = None
        project = make_mock_project(tasks=[], resources=[res])
        canvas.load_project(project)
        assert res in canvas._resources

    def test_resource_with_null_uid_not_in_tasks_by_res(self, qapp):
        """Resource with None UniqueID must not create a key in _tasks_by_res
        (no task bars shown, but an empty row is still rendered)."""
        with patch('team_planner_view._get_non_working_dates', return_value=set()):
            from team_planner_view import TeamPlannerCanvas
            canvas = TeamPlannerCanvas()
        res = MagicMock()
        res.getName.return_value = "Bob"
        res.getUniqueID.return_value = None
        res.getCalendar.return_value = None
        project = make_mock_project(tasks=[], resources=[res])
        canvas.load_project(project)
        assert len(canvas._tasks_by_res) == 0

    def test_resource_uid_exception_does_not_crash_load(self, qapp):
        """If getUniqueID() raises an arbitrary exception (not just ValueError),
        load_project must catch it silently and complete without propagating."""
        with patch('team_planner_view._get_non_working_dates', return_value=set()):
            from team_planner_view import TeamPlannerCanvas
            canvas = TeamPlannerCanvas()
        res = MagicMock()
        res.getName.return_value = "Carol"
        res.getUniqueID.side_effect = RuntimeError("JVM crash")
        res.getCalendar.return_value = None
        project = make_mock_project(tasks=[], resources=[res])
        # Must not raise
        canvas.load_project(project)

    def test_resource_with_valid_uid_added_to_tasks_by_res(self, qapp):
        """Resource with a parseable integer UID must be keyed in _tasks_by_res."""
        with patch('team_planner_view._get_non_working_dates', return_value=set()):
            from team_planner_view import TeamPlannerCanvas
            canvas = TeamPlannerCanvas()
        res = MagicMock()
        res.getName.return_value = "Dave"
        res.getUniqueID.return_value = 7
        res.getCalendar.return_value = None
        project = make_mock_project(tasks=[], resources=[res])
        canvas.load_project(project)
        assert 7 in canvas._tasks_by_res


# ---------------------------------------------------------------------------
# _get_resource_vacation_blocks — secondary calendar (bug fixes)
# ---------------------------------------------------------------------------

class TestGetResourceVacationBlocksSecondary:
    """Secondary calendar blocks: parent-date filtering and empty-name fallback.

    Bug fix 1: MPXJ child calendar's getCalendarExceptions() returns parent
    (national) exceptions merged in — these must be filtered out so only
    state-specific exceptions appear as yellow blocks.

    Bug fix 2: When the exception name is empty the block label must fall back
    to the calendar name, not show an empty or malformed string.
    """

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    def _sec_result(self, child_cal, cal_name="Baden-Württemberg"):
        return {
            "calendar": child_cal,
            "calendar_name": cal_name,
            "source": "ad:auto-match",
        }

    # ------------------------------------------------------------------
    # parent-date filtering tests
    # ------------------------------------------------------------------

    def test_parent_date_is_excluded_from_secondary_blocks(self):
        """An exception whose date is also present in the parent calendar must
        not appear in the blocks returned for the secondary calendar."""
        from team_planner_view import _get_resource_vacation_blocks

        parent_ex = _make_mock_exception("2025-05-01", "2025-05-01",
                                         "Tag der Arbeit", working=False)
        parent_cal = MagicMock()
        parent_cal.getName.return_value = "Standard (Deutschland)"
        parent_cal.getCalendarExceptions.return_value = [parent_ex]

        # Child has the same date AND one unique state date
        child_ex_shared = _make_mock_exception("2025-05-01", "2025-05-01",
                                               "Tag der Arbeit", working=False)
        child_ex_unique = _make_mock_exception("2025-01-06", "2025-01-06",
                                               "Heilige Drei Könige", working=False)
        child_cal = MagicMock()
        child_cal.getName.return_value = "Baden-Württemberg"
        child_cal.getCalendarExceptions.return_value = [child_ex_shared, child_ex_unique]
        child_cal.getParent.return_value = parent_cal

        res = _make_resource_with_calendar([])
        sec = self._sec_result(child_cal)

        with patch("integrations.secondary_calendar_integration"
                   ".resolve_secondary_calendar", return_value=sec):
            blocks = _get_resource_vacation_blocks(res, project=MagicMock())

        secondary_dates = [
            b["from_qd"].toString("yyyy-MM-dd")
            for b in blocks if b.get("source") == "secondary"
        ]
        assert "2025-05-01" not in secondary_dates
        assert "2025-01-06" in secondary_dates

    def test_state_specific_date_appears_when_not_in_parent(self):
        """An exception whose date is NOT in the parent calendar must appear."""
        from team_planner_view import _get_resource_vacation_blocks

        parent_cal = MagicMock()
        parent_cal.getName.return_value = "Standard"
        parent_cal.getCalendarExceptions.return_value = []

        child_ex = _make_mock_exception("2025-06-19", "2025-06-19",
                                        "Fronleichnam", working=False)
        child_cal = MagicMock()
        child_cal.getName.return_value = "Baden-Württemberg"
        child_cal.getCalendarExceptions.return_value = [child_ex]
        child_cal.getParent.return_value = parent_cal

        res = _make_resource_with_calendar([])
        sec = self._sec_result(child_cal)

        with patch("integrations.secondary_calendar_integration"
                   ".resolve_secondary_calendar", return_value=sec):
            blocks = _get_resource_vacation_blocks(res, project=MagicMock())

        secondary_dates = [
            b["from_qd"].toString("yyyy-MM-dd")
            for b in blocks if b.get("source") == "secondary"
        ]
        assert "2025-06-19" in secondary_dates

    def test_no_parent_calendar_uses_default_calendar_for_filtering(self):
        """When child_cal.getParent() is None the project default calendar is
        used for parent-date filtering.  A date in the default calendar must
        be excluded from secondary blocks."""
        from team_planner_view import _get_resource_vacation_blocks

        default_ex = _make_mock_exception("2025-10-03", "2025-10-03",
                                          "Tag der Deutschen Einheit", working=False)
        default_cal = MagicMock()
        default_cal.getCalendarExceptions.return_value = [default_ex]

        child_ex_same = _make_mock_exception("2025-10-03", "2025-10-03", "", working=False)
        child_ex_diff = _make_mock_exception("2025-11-01", "2025-11-01",
                                             "Allerheiligen", working=False)
        child_cal = MagicMock()
        child_cal.getName.return_value = "Bayern"
        child_cal.getCalendarExceptions.return_value = [child_ex_same, child_ex_diff]
        child_cal.getParent.return_value = None

        res = _make_resource_with_calendar([])
        sec = self._sec_result(child_cal, cal_name="Bayern")

        project = MagicMock()
        project.getDefaultCalendar.return_value = default_cal

        with patch("integrations.secondary_calendar_integration"
                   ".resolve_secondary_calendar", return_value=sec):
            blocks = _get_resource_vacation_blocks(res, project=project)

        secondary_dates = [
            b["from_qd"].toString("yyyy-MM-dd")
            for b in blocks if b.get("source") == "secondary"
        ]
        assert "2025-10-03" not in secondary_dates
        assert "2025-11-01" in secondary_dates

    # ------------------------------------------------------------------
    # empty-name fallback tests
    # ------------------------------------------------------------------

    def test_empty_exception_name_falls_back_to_calendar_name(self):
        """When an exception has an empty name the block name should contain
        the calendar name."""
        from team_planner_view import _get_resource_vacation_blocks

        child_ex = _make_mock_exception("2025-01-06", "2025-01-06", "", working=False)
        child_cal = MagicMock()
        child_cal.getName.return_value = "Baden-Württemberg"
        child_cal.getCalendarExceptions.return_value = [child_ex]
        child_cal.getParent.return_value = None

        res = _make_resource_with_calendar([])
        sec = self._sec_result(child_cal)

        project = MagicMock()
        project.getDefaultCalendar.return_value = None

        with patch("integrations.secondary_calendar_integration"
                   ".resolve_secondary_calendar", return_value=sec):
            blocks = _get_resource_vacation_blocks(res, project=project)

        secondary_blocks = [b for b in blocks if b.get("source") == "secondary"]
        assert len(secondary_blocks) == 1
        assert "Baden-Württemberg" in secondary_blocks[0]["name"]

    def test_non_empty_exception_name_included_in_block_label(self):
        """When the exception name is non-empty it must appear in the block name."""
        from team_planner_view import _get_resource_vacation_blocks

        child_ex = _make_mock_exception("2025-01-06", "2025-01-06",
                                        "Heilige Drei Könige", working=False)
        child_cal = MagicMock()
        child_cal.getName.return_value = "Baden-Württemberg"
        child_cal.getCalendarExceptions.return_value = [child_ex]
        child_cal.getParent.return_value = None

        res = _make_resource_with_calendar([])
        sec = self._sec_result(child_cal)

        project = MagicMock()
        project.getDefaultCalendar.return_value = None

        with patch("integrations.secondary_calendar_integration"
                   ".resolve_secondary_calendar", return_value=sec):
            blocks = _get_resource_vacation_blocks(res, project=project)

        secondary_blocks = [b for b in blocks if b.get("source") == "secondary"]
        assert len(secondary_blocks) == 1
        label = secondary_blocks[0]["name"]
        assert "Baden-Württemberg" in label
        assert "Heilige Drei Könige" in label

    def test_secondary_block_source_is_secondary(self):
        """Every block from the secondary calendar must carry source='secondary'."""
        from team_planner_view import _get_resource_vacation_blocks

        child_ex = _make_mock_exception("2025-06-19", "2025-06-19",
                                        "Fronleichnam", working=False)
        child_cal = MagicMock()
        child_cal.getName.return_value = "Baden-Württemberg"
        child_cal.getCalendarExceptions.return_value = [child_ex]
        child_cal.getParent.return_value = None

        res = _make_resource_with_calendar([])
        sec = self._sec_result(child_cal)

        project = MagicMock()
        project.getDefaultCalendar.return_value = None

        with patch("integrations.secondary_calendar_integration"
                   ".resolve_secondary_calendar", return_value=sec):
            blocks = _get_resource_vacation_blocks(res, project=project)

        secondary_blocks = [b for b in blocks if b.get("source") == "secondary"]
        assert len(secondary_blocks) >= 1
        assert all(b["source"] == "secondary" for b in secondary_blocks)

    def test_no_secondary_calendar_returns_only_personal_blocks(self):
        """When resolve_secondary_calendar returns None only the resource's own
        calendar exceptions are included (no secondary blocks)."""
        from team_planner_view import _get_resource_vacation_blocks

        res = _make_resource_with_calendar([
            _make_mock_exception("2025-08-01", "2025-08-15", "Urlaub", working=False)
        ])

        with patch("integrations.secondary_calendar_integration"
                   ".resolve_secondary_calendar", return_value=None):
            blocks = _get_resource_vacation_blocks(res, project=MagicMock())

        assert not any(b.get("source") == "secondary" for b in blocks)

