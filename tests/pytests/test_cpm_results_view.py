"""Tests for views/cpm_results_view.py — CpmResultsView widget (Phase 3).

CpmResultsView is a read-only QTableWidget that shows CPM schedule results:
Task Name / Duration / Early Start / Early Finish / Late Start / Late Finish /
Total Float / Free Float / Status.

Tests cover: initial state, refresh(), critical/non-critical rows, filter toggle,
status label, column names, Phase 5 calendar-aware wh display, sort order.
"""

import sys
import os

import pytest
from unittest.mock import MagicMock
from datetime import datetime, timedelta

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'src')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'src', 'views')))
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

_ES = datetime(2026, 1, 5, 8, 0)
_EF = datetime(2026, 1, 9, 17, 0)
_LF = datetime(2026, 1, 9, 17, 0)
_LS = datetime(2026, 1, 5, 8, 0)


def _make_fd(crit=False, tf_h=0.0, ff_h=0.0, tf_wh=None, ff_wh=None, wdh=None):
    """Build a float_data entry without Java objects."""
    return {
        "es":             _ES,
        "ef":             _EF,
        "ls":             _LS,
        "lf":             _LF,
        "total_float":    timedelta(hours=tf_h),
        "free_float":     timedelta(hours=ff_h),
        "total_float_wh": tf_wh,
        "free_float_wh":  ff_wh,
        "work_day_hours": wdh,
        "critical":       crit,
    }


def _make_task(tid, name):
    t = MagicMock()
    t.getID.return_value   = tid
    t.getName.return_value = name
    return t


class TestCpmResultsView:
    """Tests for CpmResultsView widget."""

    def test_widget_created(self, qapp):
        from cpm_results_view import CpmResultsView
        v = CpmResultsView()
        assert v is not None

    def test_column_count_is_nine(self, qapp):
        from cpm_results_view import CpmResultsView
        v = CpmResultsView()
        assert v._table.columnCount() == 9

    def test_column_headers_match(self, qapp):
        from cpm_results_view import CpmResultsView, _COL_NAMES
        v = CpmResultsView()
        for col, expected in enumerate(_COL_NAMES):
            assert v._table.horizontalHeaderItem(col).text() == expected

    def test_refresh_empty_data_shows_zero_rows(self, qapp):
        from cpm_results_view import CpmResultsView
        v = CpmResultsView()
        v.refresh({}, [])
        assert v._table.rowCount() == 0

    def test_refresh_populates_rows(self, qapp):
        from cpm_results_view import CpmResultsView
        v = CpmResultsView()
        fd = {1: _make_fd(crit=False, tf_h=8.0), 2: _make_fd(crit=True)}
        tasks = [_make_task(1, "Task A"), _make_task(2, "Task B")]
        v.refresh(fd, tasks)
        assert v._table.rowCount() == 2

    def test_critical_row_shows_critical_status(self, qapp):
        from cpm_results_view import CpmResultsView
        v = CpmResultsView()
        fd = {1: _make_fd(crit=True)}
        tasks = [_make_task(1, "Crit Task")]
        v.refresh(fd, tasks)
        # Status column = col 8
        assert v._table.item(0, 8).text() == "CRITICAL"

    def test_non_critical_row_shows_ok_status(self, qapp):
        from cpm_results_view import CpmResultsView
        v = CpmResultsView()
        fd = {1: _make_fd(crit=False, tf_h=16.0)}
        tasks = [_make_task(1, "Normal Task")]
        v.refresh(fd, tasks)
        assert v._table.item(0, 8).text() == "OK"

    def test_critical_filter_shows_only_critical_rows(self, qapp):
        from cpm_results_view import CpmResultsView
        v = CpmResultsView()
        fd = {1: _make_fd(crit=False, tf_h=16.0), 2: _make_fd(crit=True)}
        tasks = [_make_task(1, "Normal"), _make_task(2, "Critical")]
        v.refresh(fd, tasks)
        v._chk_critical_only.setChecked(True)
        assert v._table.rowCount() == 1
        assert v._table.item(0, 8).text() == "CRITICAL"

    def test_status_label_shows_total_and_critical_count(self, qapp):
        from cpm_results_view import CpmResultsView
        v = CpmResultsView()
        fd = {1: _make_fd(crit=False, tf_h=8.0), 2: _make_fd(crit=True)}
        tasks = [_make_task(1, "A"), _make_task(2, "B")]
        v.refresh(fd, tasks)
        lbl = v._status_lbl.text()
        assert "2" in lbl   # 2 total
        assert "1" in lbl   # 1 critical

    def test_refresh_with_phase5_wh_fields(self, qapp):
        """Phase 5 total_float_wh is preferred over timedelta for Total Float display."""
        from cpm_results_view import CpmResultsView
        v = CpmResultsView()
        fd = {1: _make_fd(crit=False, tf_h=8.0, ff_h=4.0, tf_wh=8.0, ff_wh=4.0, wdh=8.0)}
        tasks = [_make_task(1, "Phase5 Task")]
        v.refresh(fd, tasks)
        # Total Float col = 6: 8.0wh / 8.0wdh = 1.0d
        assert v._table.item(0, 6).text() == "1.0d"

    def test_critical_rows_sorted_first(self, qapp):
        """Critical rows must appear before non-critical rows after refresh."""
        from cpm_results_view import CpmResultsView
        v = CpmResultsView()
        # Task 1 is non-critical (alphabetically first), task 2 is critical
        fd = {1: _make_fd(crit=False, tf_h=8.0), 2: _make_fd(crit=True)}
        tasks = [_make_task(1, "AAAA"), _make_task(2, "BBBB")]
        v.refresh(fd, tasks)
        # Row 0 must be the critical task
        assert v._table.item(0, 8).text() == "CRITICAL"

    def test_double_click_emits_task_double_clicked_signal(self, qapp):
        """Double-clicking a row emits task_double_clicked with the task's int ID."""
        from cpm_results_view import CpmResultsView
        v = CpmResultsView()
        fd = {42: _make_fd(crit=True)}
        tasks = [_make_task(42, "MyTask")]
        v.refresh(fd, tasks)

        received = []
        v.task_double_clicked.connect(received.append)
        # Simulate double-click on the first row
        v._on_double_click(0, 0)
        assert received == [42]

    def test_double_click_on_invalid_row_does_not_emit(self, qapp):
        """Double-clicking on a row with no item does not emit the signal."""
        from cpm_results_view import CpmResultsView
        v = CpmResultsView()
        # Empty table — no rows populated
        received = []
        v.task_double_clicked.connect(received.append)
        v._on_double_click(0, 0)
        assert received == []
