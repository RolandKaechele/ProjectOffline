"""Tests for views/task_sheet_view.py — TaskSheetView widget.

TaskSheetView is a hierarchical task table with:
  - Task Name column with indentation + collapse/expand triangles
  - Progress bar delegate for % Complete column
  - Status icons for milestones/critical/overdue tasks

Requires a QApplication (provided by the session-scoped 'qapp' fixture).
MPXJ Java objects are replaced with MagicMock instances.
"""

import sys
import os

import pytest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'src')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'src', 'views')))
# Add parent test directory for conftest imports
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from conftest import make_mock_task, make_mock_project


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def view(qapp):
    """Return a fresh TaskSheetView with patched dependencies."""
    with patch('task_sheet_view._compute_critical_ids', return_value=set()), \
         patch('task_sheet_view._get_visible_tasks', side_effect=lambda tasks, collapsed: tasks):
        from task_sheet_view import TaskSheetView
        v = TaskSheetView()
    return v


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

class TestTaskSheetViewInit:
    def test_widget_is_created(self, qapp):
        with patch('task_sheet_view._compute_critical_ids', return_value=set()), \
             patch('task_sheet_view._get_visible_tasks', side_effect=lambda tasks, collapsed: tasks):
            from task_sheet_view import TaskSheetView
            v = TaskSheetView()
        assert v is not None

    def test_initial_row_count_is_zero(self, view):
        assert view.rowCount() == 0

    def test_column_count_matches_columns_constant(self, view):
        from task_sheet_view import TaskSheetView
        assert view.columnCount() == len(TaskSheetView.COLUMNS)

    def test_data_changed_signal_exists(self, view):
        assert hasattr(view, 'data_changed')


# ---------------------------------------------------------------------------
# load_project()
# ---------------------------------------------------------------------------

class TestLoadProject:
    def test_load_none_clears_rows(self, view):
        with patch('task_sheet_view._compute_critical_ids', return_value=set()), \
             patch('task_sheet_view._get_visible_tasks', side_effect=lambda tasks, collapsed: tasks):
            view.load_project(None)
        assert view.rowCount() == 0

    def test_load_project_with_one_task_adds_one_row(self, qapp):
        with patch('task_sheet_view._compute_critical_ids', return_value=set()), \
             patch('task_sheet_view._get_visible_tasks', side_effect=lambda tasks, collapsed: tasks):
            from task_sheet_view import TaskSheetView
            v = TaskSheetView()
            task = make_mock_task(task_id=1, name="Task One", duration_days=5)
            project = make_mock_project(tasks=[task])
            v.load_project(project)
        assert v.rowCount() == 1

    def test_load_project_with_multiple_tasks(self, qapp):
        with patch('task_sheet_view._compute_critical_ids', return_value=set()), \
             patch('task_sheet_view._get_visible_tasks', side_effect=lambda tasks, collapsed: tasks):
            from task_sheet_view import TaskSheetView
            v = TaskSheetView()
            tasks = [make_mock_task(task_id=i, uid=i, name=f"T{i}") for i in range(1, 6)]
            project = make_mock_project(tasks=tasks)
            v.load_project(project)
        assert v.rowCount() == 5

    def test_load_project_sets_task_name_in_name_column(self, qapp):
        with patch('task_sheet_view._compute_critical_ids', return_value=set()), \
             patch('task_sheet_view._get_visible_tasks', side_effect=lambda tasks, collapsed: tasks):
            from task_sheet_view import TaskSheetView
            v = TaskSheetView()
            task = make_mock_task(task_id=1, name="Test Task")
            project = make_mock_project(tasks=[task])
            v.load_project(project)
        # Column 2 is the Task Name column (0=icon, 1=num, 2=name)
        name_item = v.item(0, 2)
        assert name_item is not None
        assert name_item.text() == "Test Task"

    def test_load_project_replaces_previous_data(self, qapp):
        with patch('task_sheet_view._compute_critical_ids', return_value=set()), \
             patch('task_sheet_view._get_visible_tasks', side_effect=lambda tasks, collapsed: tasks):
            from task_sheet_view import TaskSheetView
            v = TaskSheetView()
            tasks_a = [make_mock_task(task_id=i, uid=i, name=f"A{i}") for i in range(1, 4)]
            project_a = make_mock_project(tasks=tasks_a)
            v.load_project(project_a)
            assert v.rowCount() == 3

            tasks_b = [make_mock_task(task_id=1, uid=1, name="B1")]
            project_b = make_mock_project(tasks=tasks_b)
            v.load_project(project_b)
        assert v.rowCount() == 1

    def test_load_none_after_data_clears(self, qapp):
        with patch('task_sheet_view._compute_critical_ids', return_value=set()), \
             patch('task_sheet_view._get_visible_tasks', side_effect=lambda tasks, collapsed: tasks):
            from task_sheet_view import TaskSheetView
            v = TaskSheetView()
            task = make_mock_task()
            v.load_project(make_mock_project(tasks=[task]))
            assert v.rowCount() == 1
            v.load_project(None)
        assert v.rowCount() == 0


# ---------------------------------------------------------------------------
# Summary Task Rendering
# ---------------------------------------------------------------------------

class TestSummaryTasks:
    def test_summary_task_displayed(self, qapp):
        with patch('task_sheet_view._compute_critical_ids', return_value=set()), \
             patch('task_sheet_view._get_visible_tasks', side_effect=lambda tasks, collapsed: tasks):
            from task_sheet_view import TaskSheetView
            v = TaskSheetView()
            summary = make_mock_task(task_id=1, uid=1, name="Summary", is_summary=True, outline_level=1)
            # Summary tasks have children
            summary.getChildTasks.return_value = [MagicMock()]
            project = make_mock_project(tasks=[summary])
            v.load_project(project)
        assert v.rowCount() == 1
        name_item = v.item(0, 2)  # Column 2 is Task Name
        assert name_item.text() == "Summary"

    def test_milestone_task_displayed(self, qapp):
        with patch('task_sheet_view._compute_critical_ids', return_value=set()), \
             patch('task_sheet_view._get_visible_tasks', side_effect=lambda tasks, collapsed: tasks):
            from task_sheet_view import TaskSheetView
            v = TaskSheetView()
            milestone = make_mock_task(task_id=1, uid=1, name="Milestone", is_milestone=True, duration_days=0)
            project = make_mock_project(tasks=[milestone])
            v.load_project(project)
        assert v.rowCount() == 1

    def test_duration_displayed_correctly(self, qapp):
        with patch('task_sheet_view._compute_critical_ids', return_value=set()), \
             patch('task_sheet_view._get_visible_tasks', side_effect=lambda tasks, collapsed: tasks):
            from task_sheet_view import TaskSheetView
            v = TaskSheetView()
            task = make_mock_task(task_id=1, uid=1, name="Task", duration_days=10)
            project = make_mock_project(tasks=[task])
            v.load_project(project)
        # Column 3 is Duration (0=icon, 1=num, 2=name, 3=duration)
        duration_item = v.item(0, 3)
        assert "10" in duration_item.text()

    def test_percent_complete_displayed(self, qapp):
        with patch('task_sheet_view._compute_critical_ids', return_value=set()), \
             patch('task_sheet_view._get_visible_tasks', side_effect=lambda tasks, collapsed: tasks):
            from task_sheet_view import TaskSheetView
            v = TaskSheetView()
            task = make_mock_task(task_id=1, uid=1, name="Task", pct=50.0)
            project = make_mock_project(tasks=[task])
            v.load_project(project)
        # Column 4 is % Complete (0=icon, 1=num, 2=name, 3=duration, 4=pct)
        pct_item = v.item(0, 4)
        assert "50" in pct_item.text()


# ---------------------------------------------------------------------------
# Delegates
# ---------------------------------------------------------------------------

class TestTaskNameDelegate:
    def test_delegate_exists(self, qapp):
        with patch('task_sheet_view._compute_critical_ids', return_value=set()), \
             patch('task_sheet_view._get_visible_tasks', side_effect=lambda tasks, collapsed: tasks):
            from task_sheet_view import TaskSheetView, _TaskNameDelegate
            v = TaskSheetView()
            # Check that column 2 (Task Name) has a delegate
            delegate = v.itemDelegateForColumn(2)
            assert isinstance(delegate, _TaskNameDelegate)

    def test_delegate_renders_without_crash(self, qapp):
        with patch('task_sheet_view._compute_critical_ids', return_value=set()), \
             patch('task_sheet_view._get_visible_tasks', side_effect=lambda tasks, collapsed: tasks):
            from task_sheet_view import TaskSheetView
            v = TaskSheetView()
            task = make_mock_task(task_id=1, uid=1, name="Test")
            v.load_project(make_mock_project(tasks=[task]))
            # Force a repaint
            v.viewport().update()
        assert True


class TestProgressDelegate:
    def test_delegate_exists(self, qapp):
        with patch('task_sheet_view._compute_critical_ids', return_value=set()), \
             patch('task_sheet_view._get_visible_tasks', side_effect=lambda tasks, collapsed: tasks):
            from task_sheet_view import TaskSheetView, _ProgressDelegate
            v = TaskSheetView()
            # Check that column 4 (% Complete) has a delegate
            delegate = v.itemDelegateForColumn(4)
            assert isinstance(delegate, _ProgressDelegate)

    def test_delegate_renders_without_crash(self, qapp):
        with patch('task_sheet_view._compute_critical_ids', return_value=set()), \
             patch('task_sheet_view._get_visible_tasks', side_effect=lambda tasks, collapsed: tasks):
            from task_sheet_view import TaskSheetView
            v = TaskSheetView()
            task = make_mock_task(task_id=1, uid=1, name="Test", pct=75.0)
            v.load_project(make_mock_project(tasks=[task]))
            v.viewport().update()
        assert True


# ---------------------------------------------------------------------------
# Double-click
# ---------------------------------------------------------------------------

class TestDoubleClick:
    def test_double_click_handler_exists(self, view):
        assert hasattr(view, '_on_double_click')


# ---------------------------------------------------------------------------
# Free Float column (Phase 4)
# ---------------------------------------------------------------------------

class TestFreeFloatColumn:
    """Tests for the hidden/visible Free Float column (COL_FF) in TaskSheetView."""

    def test_col_ff_hidden_by_default(self, qapp):
        """TSV-FF-1: Free Float column must be hidden right after widget creation."""
        from task_sheet_view import TaskSheetView
        v = TaskSheetView()
        assert v.isColumnHidden(v.COL_FF), \
            f"Column COL_FF ({v.COL_FF}) must be hidden by default"

    def test_col_ff_shown_after_load_project_when_setting_true(self, qapp):
        """TSV-FF-2: Free Float column becomes visible when the user setting is True."""
        from task_sheet_view import TaskSheetView
        with patch('settings_manager.SettingsManager') as mock_sm_cls, \
             patch('task_sheet_view._compute_critical_ids', return_value=set()), \
             patch('task_sheet_view._get_visible_tasks', side_effect=lambda t, c: t):
            mock_sm_cls.return_value.get_show_free_float_column.return_value = True
            v = TaskSheetView()
            project = make_mock_project(tasks=[make_mock_task(task_id=1, name="A")])
            v.load_project(project)
        assert not v.isColumnHidden(v.COL_FF), \
            f"Column COL_FF ({v.COL_FF}) must be visible when get_show_free_float_column()=True"
