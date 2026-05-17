"""Tests for views/baseline_view.py — BaselineView widget.

Requires a QApplication (provided by the session-scoped 'qapp' fixture).
MPXJ Java objects are replaced with MagicMock instances.

Coverage:
  - Module constants (_COLUMNS, column indices)
  - BaselineView.__init__
  - load_project (None, single, multiple, replace, none-name filter)
  - set_baseline_number (switch slot, refresh)
  - set_comparison_baseline (initial state, switch, same-slot fallback)
  - set_show_start_diff / set_show_finish_diff / set_show_duration_diff (column visibility)
  - _apply_column_visibility
  - _update_headers (column labels for comparison slot)
  - Variance highlighting via _fmt_days, _fmt_pct, _cell_color_days, _cell_color_pct
  - Row tooltips (only on rows with non-zero variance)
  - color_diagnostics()
  - Colour thresholds (yellow / orange / red for days and %)
  - _on_double_click (row in range, row out of range)
"""

import sys
import os

import pytest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'src')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'src', 'views')))
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from conftest import make_mock_task, make_mock_project


# ---------------------------------------------------------------------------
# Helpers: tasks with baseline data
# ---------------------------------------------------------------------------

def _task_with_baseline(task_id=1, name="Task",
                        baseline_start="2025-01-06", baseline_finish="2025-01-12",
                        baseline_dur="5 days",
                        cur_start="2025-01-06", cur_finish="2025-01-12"):
    """Return a mock task with baseline fields pre-set."""
    task = make_mock_task(task_id=task_id, uid=task_id, name=name,
                          start_year=2025, start_month=1, start_day=6,
                          finish_year=2025, finish_month=1, finish_day=12)
    b_start  = MagicMock(); b_start.__str__  = MagicMock(return_value=baseline_start)
    b_finish = MagicMock(); b_finish.__str__ = MagicMock(return_value=baseline_finish)
    b_dur    = MagicMock(); b_dur.__str__    = MagicMock(return_value=baseline_dur)
    task.getBaselineStart.return_value    = b_start
    task.getBaselineFinish.return_value   = b_finish
    task.getBaselineDuration.return_value = b_dur
    return task


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def view(qapp):
    from baseline_view import BaselineView
    return BaselineView()


# ===========================================================================
# 1. Module constants
# ===========================================================================

class TestModuleConstants:
    def test_columns_list_has_11_entries(self):
        from baseline_view import BaselineView
        assert len(BaselineView.COLUMNS) == 11

    def test_column_names_include_expected_headers(self):
        from baseline_view import BaselineView
        cols = BaselineView.COLUMNS
        assert "ID" in cols
        assert "Name" in cols
        assert any("BL Start" in c for c in cols)
        assert any("BL Finish" in c for c in cols)
        assert any("Duration" in c for c in cols)


# ===========================================================================
# 2. Initialisation
# ===========================================================================

class TestBaselineViewInit:
    def test_widget_created(self, qapp):
        from baseline_view import BaselineView
        assert BaselineView() is not None

    def test_initial_row_count_is_zero(self, view):
        assert view.rowCount() == 0

    def test_column_count_matches_constant(self, view):
        from baseline_view import BaselineView
        assert view.columnCount() == len(BaselineView.COLUMNS)

    def test_column_headers_correct(self, view):
        from baseline_view import BaselineView
        for col, header in enumerate(BaselineView.COLUMNS):
            assert view.horizontalHeaderItem(col).text() == header

    def test_initial_baseline_number_is_zero(self, view):
        assert view._baseline_number == 0

    def test_initial_comparison_number_is_minus_one(self, view):
        assert view._comparison_number == -1

    def test_initial_project_is_none(self, view):
        assert view._project is None

    def test_initial_tasks_list_is_empty(self, view):
        assert view._tasks == []

    def test_diff_flags_all_true_by_default(self, view):
        assert view._show_start_diff is True
        assert view._show_finish_diff is True
        assert view._show_duration_diff is True

    def test_not_editable(self, view):
        from PyQt5.QtWidgets import QAbstractItemView
        assert view.editTriggers() == QAbstractItemView.NoEditTriggers

    def test_row_selection_mode(self, view):
        from PyQt5.QtWidgets import QAbstractItemView
        assert view.selectionBehavior() == QAbstractItemView.SelectRows


# ===========================================================================
# 3. load_project()
# ===========================================================================

class TestLoadProject:
    def test_load_none_clears_rows(self, view):
        view.load_project(None)
        assert view.rowCount() == 0

    def test_load_single_task(self, qapp):
        from baseline_view import BaselineView
        v = BaselineView()
        task = make_mock_task(task_id=1, uid=1, name="Design")
        v.load_project(make_mock_project(tasks=[task]))
        assert v.rowCount() == 1

    def test_load_multiple_tasks(self, qapp):
        from baseline_view import BaselineView
        v = BaselineView()
        tasks = [make_mock_task(task_id=i, uid=i, name=f"T{i}") for i in range(1, 6)]
        v.load_project(make_mock_project(tasks=tasks))
        assert v.rowCount() == 5

    def test_task_name_in_name_column(self, qapp):
        from baseline_view import BaselineView
        v = BaselineView()
        task = make_mock_task(task_id=1, uid=1, name="Development")
        v.load_project(make_mock_project(tasks=[task]))
        item = v.item(0, 1)   # _COL_NAME = 1
        assert item is not None
        assert item.text() == "Development"

    def test_task_id_in_id_column(self, qapp):
        from baseline_view import BaselineView
        v = BaselineView()
        task = make_mock_task(task_id=3, uid=3, name="Testing")
        v.load_project(make_mock_project(tasks=[task]))
        assert v.item(0, 0).text() == "3"   # _COL_ID = 0

    def test_baseline_start_in_baseline_start_column(self, qapp):
        from baseline_view import BaselineView
        v = BaselineView()
        task = _task_with_baseline(task_id=1, name="T", baseline_start="2025-03-10")
        v.load_project(make_mock_project(tasks=[task]))
        item = v.item(0, 2)    # _COL_BL_START = 2
        assert item is not None
        assert "2025-03-10" in item.text()

    def test_none_baseline_shows_empty_string(self, qapp):
        from baseline_view import BaselineView
        v = BaselineView()
        task = make_mock_task(task_id=1, uid=1, name="NoBaseline")
        v.load_project(make_mock_project(tasks=[task]))
        item = v.item(0, 2)   # Baseline Start
        assert item is not None
        assert item.text() == ""

    def test_tasks_with_none_name_excluded(self, qapp):
        from baseline_view import BaselineView
        v = BaselineView()
        valid_task = make_mock_task(task_id=1, uid=1, name="Valid")
        null_task  = make_mock_task(task_id=2, uid=2, name="ShouldBeExcluded")
        null_task.getName.return_value = None
        v.load_project(make_mock_project(tasks=[valid_task, null_task]))
        assert v.rowCount() == 1

    def test_load_replaces_previous_data(self, qapp):
        from baseline_view import BaselineView
        v = BaselineView()
        v.load_project(make_mock_project(tasks=[make_mock_task(task_id=i, uid=i, name=f"A{i}") for i in range(1, 4)]))
        assert v.rowCount() == 3
        v.load_project(make_mock_project(tasks=[make_mock_task(task_id=1, uid=1, name="B1")]))
        assert v.rowCount() == 1

    def test_load_none_after_data_clears(self, qapp):
        from baseline_view import BaselineView
        v = BaselineView()
        v.load_project(make_mock_project(tasks=[make_mock_task()]))
        v.load_project(None)
        assert v.rowCount() == 0

    def test_tasks_stored_in_internal_list(self, qapp):
        from baseline_view import BaselineView
        v = BaselineView()
        tasks = [make_mock_task(task_id=i, uid=i, name=f"T{i}") for i in range(1, 4)]
        v.load_project(make_mock_project(tasks=tasks))
        assert len(v._tasks) == 3

    def test_load_none_clears_internal_task_list(self, view):
        view.load_project(make_mock_project(tasks=[make_mock_task()]))
        view.load_project(None)
        assert view._tasks == []

    def test_project_reference_stored(self, qapp):
        from baseline_view import BaselineView
        v = BaselineView()
        proj = make_mock_project(tasks=[make_mock_task()])
        v.load_project(proj)
        assert v._project is proj

    def test_items_are_not_editable(self, qapp):
        from baseline_view import BaselineView
        from PyQt5.QtCore import Qt
        v = BaselineView()
        v.load_project(make_mock_project(tasks=[make_mock_task(task_id=1, uid=1, name="T")]))
        item = v.item(0, 1)
        assert not (item.flags() & Qt.ItemIsEditable)


# ===========================================================================
# 4. set_baseline_number()
# ===========================================================================

class TestSetBaselineNumber:
    def test_set_baseline_number_stores_value(self, view):
        view.set_baseline_number(3)
        assert view._baseline_number == 3

    def test_set_same_number_no_reload(self, qapp):
        """Setting the same baseline number should not trigger a reload."""
        from baseline_view import BaselineView
        v = BaselineView()
        proj = make_mock_project(tasks=[make_mock_task(task_id=1, uid=1, name="T")])
        v.load_project(proj)
        call_count_before = proj.getTasks.call_count
        v.set_baseline_number(0)   # same as initial
        # getTasks should NOT have been called again
        assert proj.getTasks.call_count == call_count_before

    def test_set_different_number_triggers_reload(self, qapp):
        """Switching to a different slot must call getTasks again."""
        from baseline_view import BaselineView
        v = BaselineView()
        proj = make_mock_project(tasks=[make_mock_task(task_id=1, uid=1, name="T")])
        v.load_project(proj)
        call_count_before = proj.getTasks.call_count
        v.set_baseline_number(1)
        assert proj.getTasks.call_count > call_count_before

    def test_set_baseline_number_zero_to_ten_accepted(self, view):
        for n in range(11):
            view.set_baseline_number(n)
            assert view._baseline_number == n


# ===========================================================================
# 5. Column visibility (set_show_*_diff)
# ===========================================================================

class TestColumnVisibility:
    def test_hide_start_diff_hides_three_columns(self, view):
        view.load_project(make_mock_project(tasks=[make_mock_task()]))
        view.set_show_start_diff(False)
        # Columns 2, 3, 4 should be hidden
        for col in (2, 3, 4):
            assert view.isColumnHidden(col), f"col {col} should be hidden"

    def test_show_start_diff_unhides_columns(self, view):
        view.load_project(make_mock_project(tasks=[make_mock_task()]))
        view.set_show_start_diff(False)
        view.set_show_start_diff(True)
        for col in (2, 3, 4):
            assert not view.isColumnHidden(col), f"col {col} should be visible"

    def test_hide_finish_diff_hides_three_columns(self, view):
        view.load_project(make_mock_project(tasks=[make_mock_task()]))
        view.set_show_finish_diff(False)
        for col in (5, 6, 7):
            assert view.isColumnHidden(col)

    def test_show_finish_diff_unhides_columns(self, view):
        view.load_project(make_mock_project(tasks=[make_mock_task()]))
        view.set_show_finish_diff(False)
        view.set_show_finish_diff(True)
        for col in (5, 6, 7):
            assert not view.isColumnHidden(col)

    def test_hide_duration_diff_hides_three_columns(self, view):
        view.load_project(make_mock_project(tasks=[make_mock_task()]))
        view.set_show_duration_diff(False)
        for col in (8, 9, 10):
            assert view.isColumnHidden(col)

    def test_show_duration_diff_unhides_columns(self, view):
        view.load_project(make_mock_project(tasks=[make_mock_task()]))
        view.set_show_duration_diff(False)
        view.set_show_duration_diff(True)
        for col in (8, 9, 10):
            assert not view.isColumnHidden(col)

    def test_flag_stored_after_set_show_start_diff(self, view):
        view.set_show_start_diff(False)
        assert view._show_start_diff is False
        view.set_show_start_diff(True)
        assert view._show_start_diff is True

    def test_all_diff_columns_visible_by_default(self, view):
        view.load_project(make_mock_project(tasks=[make_mock_task()]))
        for col in range(2, 11):
            assert not view.isColumnHidden(col)


# ===========================================================================
# 6. Formatting helpers (_fmt_days, _fmt_pct)
# ===========================================================================

class TestFmtDays:
    def _fmt(self, days):
        from baseline_view import _fmt_days
        return _fmt_days(days)

    def test_none_returns_empty(self):
        assert self._fmt(None) == ""

    def test_zero_returns_zero_string(self):
        assert self._fmt(0) == "0"

    def test_positive_has_plus_sign(self):
        assert self._fmt(3) == "+3"

    def test_negative_has_minus_sign(self):
        assert self._fmt(-2) == "-2"

    def test_large_positive(self):
        assert self._fmt(10) == "+10"


class TestFmtPct:
    def _fmt(self, pct):
        from baseline_view import _fmt_pct
        return _fmt_pct(pct)

    def test_none_returns_empty(self):
        assert self._fmt(None) == ""

    def test_zero_returns_zero_pct(self):
        assert self._fmt(0.0) == "0.0%"

    def test_positive_has_plus_sign(self):
        result = self._fmt(10.0)
        assert result.startswith("+")
        assert "10.0%" in result

    def test_negative_has_minus_sign(self):
        result = self._fmt(-5.0)
        assert result.startswith("-")

    def test_one_decimal_place(self):
        result = self._fmt(7.55)
        # Should be rounded to 1 decimal
        assert "7.6%" in result or "7.5%" in result  # floating point tolerance


# ===========================================================================
# 7. Cell colour helpers
# ===========================================================================

class TestCellColorDays:
    def _color(self, days):
        from baseline_view import _cell_color_days
        return _cell_color_days(days)

    def test_zero_is_none(self):
        assert self._color(0) is None

    def test_one_day_late_is_yellow(self):
        from PyQt5.QtGui import QColor
        assert self._color(1) == QColor(255, 255, 160)

    def test_two_days_late_is_yellow(self):
        from PyQt5.QtGui import QColor
        assert self._color(2) == QColor(255, 255, 160)

    def test_three_days_late_is_orange(self):
        from PyQt5.QtGui import QColor
        assert self._color(3) == QColor(255, 210, 120)

    def test_five_days_late_is_orange(self):
        from PyQt5.QtGui import QColor
        assert self._color(5) == QColor(255, 210, 120)

    def test_six_days_late_is_red(self):
        from PyQt5.QtGui import QColor
        assert self._color(6) == QColor(255, 150, 150)

    def test_negative_one_is_yellow(self):
        from PyQt5.QtGui import QColor
        assert self._color(-1) == QColor(255, 255, 160)

    def test_negative_six_is_red(self):
        from PyQt5.QtGui import QColor
        assert self._color(-6) == QColor(255, 150, 150)


class TestCellColorPct:
    def _color(self, pct):
        from baseline_view import _cell_color_pct
        return _cell_color_pct(pct)

    def test_zero_pct_is_none(self):
        assert self._color(0.0) is None

    def test_small_pct_below_threshold_is_none(self):
        assert self._color(0.04) is None

    def test_5_pct_is_yellow(self):
        from PyQt5.QtGui import QColor
        assert self._color(5.0) == QColor(255, 255, 160)

    def test_10_pct_is_yellow(self):
        from PyQt5.QtGui import QColor
        assert self._color(10.0) == QColor(255, 255, 160)

    def test_11_pct_is_orange(self):
        from PyQt5.QtGui import QColor
        assert self._color(11.0) == QColor(255, 210, 120)

    def test_25_pct_is_orange(self):
        from PyQt5.QtGui import QColor
        assert self._color(25.0) == QColor(255, 210, 120)

    def test_above_25_pct_is_red(self):
        from PyQt5.QtGui import QColor
        assert self._color(25.1) == QColor(255, 150, 150)

    def test_negative_10_pct_is_yellow(self):
        from PyQt5.QtGui import QColor
        assert self._color(-10.0) == QColor(255, 255, 160)


# ===========================================================================
# 8. Row colour logic (via cell coloring — _row_color removed)
# ===========================================================================

class TestRowColor:
    """_row_color was removed in favour of per-cell colouring.
    These tests verify the cell-level helpers produce the expected severity.
    """

    def test_all_none_returns_none(self):
        from baseline_view import _cell_color_days
        assert _cell_color_days(0) is None

    def test_small_deviation_returns_yellow(self):
        from PyQt5.QtGui import QColor
        from baseline_view import _cell_color_days
        assert _cell_color_days(1) == QColor(255, 255, 160)

    def test_moderate_deviation_returns_orange(self):
        from PyQt5.QtGui import QColor
        from baseline_view import _cell_color_days
        assert _cell_color_days(3) == QColor(255, 210, 120)

    def test_severe_days_returns_red(self):
        from PyQt5.QtGui import QColor
        from baseline_view import _cell_color_days
        assert _cell_color_days(6) == QColor(255, 150, 150)

    def test_severe_pct_returns_red(self):
        from PyQt5.QtGui import QColor
        from baseline_view import _cell_color_pct
        assert _cell_color_pct(26.0) == QColor(255, 150, 150)

    def test_moderate_pct_returns_orange(self):
        from PyQt5.QtGui import QColor
        from baseline_view import _cell_color_pct
        assert _cell_color_pct(11.0) == QColor(255, 210, 120)

    def test_finish_days_also_considered(self):
        from PyQt5.QtGui import QColor
        from baseline_view import _cell_color_days
        assert _cell_color_days(6) == QColor(255, 150, 150)


# ===========================================================================
# 9. Variance highlighting (end-to-end via load_project)
# ===========================================================================

class TestVarianceHighlight:
    def test_no_exception_when_baseline_differs_from_actual(self, qapp):
        """Rows with differing baseline vs actual should be highlighted without error."""
        from baseline_view import BaselineView
        v = BaselineView()
        task = _task_with_baseline(task_id=1, baseline_start="2025-01-06")
        actual_start = MagicMock()
        actual_start.__str__ = MagicMock(return_value="2025-01-08")
        task.getActualStart.return_value = actual_start
        v.load_project(make_mock_project(tasks=[task]))
        assert v.rowCount() == 1

    def test_start_delta_cell_text_matches_fmt_days(self, qapp):
        """The Start Δ column text reflects the variance computed by baseline_manager."""
        from baseline_view import BaselineView
        v = BaselineView()
        task = _task_with_baseline(task_id=1, name="T", baseline_start="2025-01-06")
        proj = make_mock_project(tasks=[task])
        with patch('baseline_manager.get_variance',
                   return_value={"start_days": 3, "finish_days": None, "duration_pct": None}):
            v.load_project(proj)
        delta_item = v.item(0, 4)   # _COL_START_D = 4
        assert delta_item is not None
        assert delta_item.text() == "+3"

    def test_duration_pct_cell_text_matches_fmt_pct(self, qapp):
        """The Duration Δ% column text reflects the variance computed by baseline_manager."""
        from baseline_view import BaselineView
        v = BaselineView()
        task = _task_with_baseline(task_id=1, name="T")
        proj = make_mock_project(tasks=[task])
        with patch('baseline_manager.get_variance',
                   return_value={"start_days": None, "finish_days": None, "duration_pct": 10.0}):
            v.load_project(proj)
        pct_item = v.item(0, 10)   # _COL_DUR_PCT = 10
        assert pct_item is not None
        assert "+10.0%" in pct_item.text()


# ===========================================================================
# 10. _on_double_click
# ===========================================================================

class TestOnDoubleClick:
    def test_double_click_out_of_range_does_not_raise(self, view):
        """Row index out of range must be silently ignored."""
        view.load_project(None)
        view._on_double_click(-1, 0)   # no tasks — must not raise

    def test_double_click_in_range_opens_dialog(self, qapp):
        """Double-click on a valid row should open BaselineEntryDialog."""
        from baseline_view import BaselineView
        v = BaselineView()
        task = make_mock_task(task_id=1, uid=1, name="T")
        v.load_project(make_mock_project(tasks=[task]))

        mock_dialogs = MagicMock()
        with patch.dict(sys.modules, {'dialogs': mock_dialogs}):
            v._on_double_click(0, 0)

        mock_dialogs.BaselineEntryDialog.assert_called_once()
        mock_dialogs.BaselineEntryDialog.return_value.exec_.assert_called_once()


# ===========================================================================
# 11. set_comparison_baseline()
# ===========================================================================

class TestComparisonBaseline:
    def test_initial_comparison_number_is_minus_one(self, view):
        assert view._comparison_number == -1

    def test_set_comparison_stores_value(self, view):
        view.set_comparison_baseline(2)
        assert view._comparison_number == 2

    def test_set_comparison_minus_one_stored(self, view):
        view.set_comparison_baseline(2)
        view.set_comparison_baseline(-1)
        assert view._comparison_number == -1

    def test_same_slot_fallback_in_load(self, qapp):
        """If comparison == baseline, load_project falls back to -1 (current)."""
        from baseline_view import BaselineView
        v = BaselineView()
        v.set_baseline_number(1)
        v.set_comparison_baseline(1)    # same → should behave as -1
        task = make_mock_task(task_id=1, uid=1, name="T")
        with patch('baseline_manager.get_variance',
                   return_value={"start_days": 0, "finish_days": 0, "duration_pct": 0.0}) as mock_var:
            v.load_project(make_mock_project(tasks=[task]))
        # get_variance (slot 1, current) should have been called, NOT get_variance_between
        mock_var.assert_called()

    def test_comparison_number_accepted_0_to_10(self, view):
        for n in list(range(11)) + [-1]:
            view.set_comparison_baseline(n)
            assert view._comparison_number == n


# ===========================================================================
# 12. _update_headers()
# ===========================================================================

class TestUpdateHeaders:
    def test_headers_show_current_when_comparison_minus_one(self, view):
        view.set_comparison_baseline(-1)
        view._update_headers()
        hdr_start = view.horizontalHeaderItem(3).text()   # _COL_CUR_START
        assert "Current" in hdr_start

    def test_headers_show_bl0_when_comparison_zero(self, view):
        view.set_comparison_baseline(0)
        view._update_headers()
        hdr = view.horizontalHeaderItem(3).text()
        assert "BL-0" in hdr

    def test_headers_show_bl_n_when_comparison_n(self, view):
        view.set_comparison_baseline(5)
        view._update_headers()
        hdr = view.horizontalHeaderItem(3).text()
        assert "BL-5" in hdr


# ===========================================================================
# 13. Row tooltips
# ===========================================================================

class TestRowTooltips:
    def test_tooltip_set_when_start_differs(self, qapp):
        """A row with start_days != 0 should have a tooltip on all its cells."""
        from baseline_view import BaselineView
        v = BaselineView()
        task = _task_with_baseline(task_id=1, name="Design")
        with patch('baseline_manager.get_variance',
                   return_value={"start_days": 5, "finish_days": 0, "duration_pct": 0.0}):
            v.load_project(make_mock_project(tasks=[task]))
        # Tooltip should be set on every cell in the row
        for col in range(v.columnCount()):
            item = v.item(0, col)
            assert item is not None
            assert item.toolTip() != "", f"col {col} expected a tooltip"

    def test_no_tooltip_when_no_variance(self, qapp):
        """A row with all-zero variance must NOT have a tooltip."""
        from baseline_view import BaselineView
        v = BaselineView()
        task = _task_with_baseline(task_id=1, name="Design")
        with patch('baseline_manager.get_variance',
                   return_value={"start_days": 0, "finish_days": 0, "duration_pct": 0.0}):
            v.load_project(make_mock_project(tasks=[task]))
        for col in range(v.columnCount()):
            item = v.item(0, col)
            assert item is not None
            assert item.toolTip() == "", f"col {col} should have no tooltip"

    def test_tooltip_contains_task_name(self, qapp):
        from baseline_view import BaselineView
        v = BaselineView()
        task = _task_with_baseline(task_id=1, name="MyTask")
        with patch('baseline_manager.get_variance',
                   return_value={"start_days": -7, "finish_days": 0, "duration_pct": 0.0}):
            v.load_project(make_mock_project(tasks=[task]))
        assert "MyTask" in v.item(0, 1).toolTip()

    def test_tooltip_contains_start_line_when_start_differs(self, qapp):
        from baseline_view import BaselineView
        v = BaselineView()
        task = _task_with_baseline(task_id=1, name="T",
                                   baseline_start="2025-03-01", cur_start="2025-03-06")
        with patch('baseline_manager.get_variance',
                   return_value={"start_days": 5, "finish_days": 0, "duration_pct": 0.0}):
            v.load_project(make_mock_project(tasks=[task]))
        tip = v.item(0, 0).toolTip()
        assert "Start" in tip

    def test_tooltip_omits_finish_line_when_finish_same(self, qapp):
        from baseline_view import BaselineView
        v = BaselineView()
        task = _task_with_baseline(task_id=1, name="T")
        with patch('baseline_manager.get_variance',
                   return_value={"start_days": 3, "finish_days": 0, "duration_pct": 0.0}):
            v.load_project(make_mock_project(tasks=[task]))
        tip = v.item(0, 0).toolTip()
        assert "Finish" not in tip

    def test_tooltip_only_duration_when_only_duration_differs(self, qapp):
        from baseline_view import BaselineView
        v = BaselineView()
        task = _task_with_baseline(task_id=1, name="T")
        with patch('baseline_manager.get_variance',
                   return_value={"start_days": 0, "finish_days": 0, "duration_pct": 15.0}):
            v.load_project(make_mock_project(tasks=[task]))
        tip = v.item(0, 0).toolTip()
        assert "Duration" in tip
        assert "Start" not in tip
        assert "Finish" not in tip


# ===========================================================================
# 14. color_diagnostics()
# ===========================================================================

class TestColorDiagnostics:
    def test_returns_dict(self, view):
        view.load_project(None)
        diag = view.color_diagnostics()
        assert isinstance(diag, dict)

    def test_keys_present(self, view):
        view.load_project(None)
        diag = view.color_diagnostics()
        for key in ("delegate_type", "baseline_slot", "comparison_slot",
                    "row_count", "colored_cells_count", "colored_cells"):
            assert key in diag

    def test_delegate_type_name(self, view):
        diag = view.color_diagnostics()
        assert diag["delegate_type"] == "_CellColorDelegate"

    def test_zero_rows_on_empty_project(self, view):
        view.load_project(None)
        assert view.color_diagnostics()["row_count"] == 0

    def test_colored_cells_empty_when_no_variance(self, qapp):
        from baseline_view import BaselineView
        v = BaselineView()
        task = _task_with_baseline(task_id=1, name="T")
        with patch('baseline_manager.get_variance',
                   return_value={"start_days": 0, "finish_days": 0, "duration_pct": 0.0}):
            v.load_project(make_mock_project(tasks=[task]))
        diag = v.color_diagnostics()
        assert diag["colored_cells_count"] == 0
        assert diag["colored_cells"] == []

    def test_colored_cells_present_when_variance(self, qapp):
        from baseline_view import BaselineView
        v = BaselineView()
        task = _task_with_baseline(task_id=1, name="T")
        with patch('baseline_manager.get_variance',
                   return_value={"start_days": 6, "finish_days": 0, "duration_pct": 0.0}):
            v.load_project(make_mock_project(tasks=[task]))
        diag = v.color_diagnostics()
        assert diag["colored_cells_count"] >= 1

    def test_baseline_slot_matches(self, view):
        view.set_baseline_number(3)
        assert view.color_diagnostics()["baseline_slot"] == 3

    def test_comparison_slot_matches(self, view):
        view.set_comparison_baseline(2)
        assert view.color_diagnostics()["comparison_slot"] == 2

