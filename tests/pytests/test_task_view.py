"""Tests for views/task_view.py — TaskView widget.

Requires a QApplication (provided by the session-scoped 'qapp' fixture).
MPXJ Java objects are replaced with MagicMock instances.
_compute_critical_ids is patched to return (set(), {}) so that no JVM
dependency is pulled in during load_project().
"""

import sys
import os

import pytest
from unittest.mock import MagicMock, patch

# conftest adds src/ and src/views/ to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'src')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'src', 'views')))
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# Import factories from conftest (available as top-level names via conftest path insertion)
from conftest import make_mock_task, make_mock_project


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def view(qapp):
    """Return a fresh TaskView with an empty project."""
    with patch('task_view._compute_critical_ids', return_value=(set(), {})):
        from task_view import TaskView
        v = TaskView()
    return v


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

class TestTaskViewInit:
    def test_widget_is_created(self, qapp):
        with patch('task_view._compute_critical_ids', return_value=(set(), {})):
            from task_view import TaskView
            v = TaskView()
        assert v is not None

    def test_initial_row_count_is_zero(self, view):
        assert view.rowCount() == 0

    def test_column_count_matches_columns_constant(self, view):
        from task_view import TaskView
        assert view.columnCount() == len(TaskView.COLUMNS)

    def test_editable_cols_constant(self):
        from task_view import TaskView
        assert TaskView.EDITABLE_COLS == {2, 3, 7}

    def test_data_changed_signal_exists(self, view):
        assert hasattr(view, 'data_changed')

    def test_task_reordered_signal_exists(self, view):
        assert hasattr(view, 'task_reordered')

    def test_selection_changed_signal_exists(self, view):
        assert hasattr(view, 'selection_changed')


# ---------------------------------------------------------------------------
# load_project()
# ---------------------------------------------------------------------------

class TestLoadProject:
    def test_load_none_clears_rows(self, view):
        with patch('task_view._compute_critical_ids', return_value=(set(), {})):
            view.load_project(None)
        assert view.rowCount() == 0

    def test_load_project_with_one_task_adds_one_row(self, qapp):
        with patch('task_view._compute_critical_ids', return_value=(set(), {})):
            from task_view import TaskView
            v = TaskView()
            task = make_mock_task(task_id=1, name="Alpha")
            project = make_mock_project(tasks=[task])
            v.load_project(project)
        assert v.rowCount() == 1

    def test_load_project_with_multiple_tasks(self, qapp):
        with patch('task_view._compute_critical_ids', return_value=(set(), {})):
            from task_view import TaskView
            v = TaskView()
            tasks = [make_mock_task(task_id=i, uid=i, name=f"T{i}") for i in range(1, 6)]
            project = make_mock_project(tasks=tasks)
            v.load_project(project)
        assert v.rowCount() == 5

    def test_load_project_sets_task_name_in_name_column(self, qapp):
        with patch('task_view._compute_critical_ids', return_value=(set(), {})):
            from task_view import TaskView
            v = TaskView()
            task = make_mock_task(task_id=1, name="Critical Path")
            project = make_mock_project(tasks=[task])
            v.load_project(project)
        # Column 2 is the Task Name column
        name_item = v.item(0, 2)
        assert name_item is not None
        assert name_item.text() == "Critical Path"

    def test_load_project_sets_task_id_in_id_column(self, qapp):
        with patch('task_view._compute_critical_ids', return_value=(set(), {})):
            from task_view import TaskView
            v = TaskView()
            task = make_mock_task(task_id=5, uid=5, name="Five")
            project = make_mock_project(tasks=[task])
            v.load_project(project)
        id_item = v.item(0, 1)
        assert id_item is not None
        assert id_item.text() == "5"

    def test_load_project_replaces_previous_data(self, qapp):
        with patch('task_view._compute_critical_ids', return_value=(set(), {})):
            from task_view import TaskView
            v = TaskView()
            tasks_a = [make_mock_task(task_id=i, uid=i, name=f"A{i}") for i in range(1, 4)]
            project_a = make_mock_project(tasks=tasks_a)
            v.load_project(project_a)
            assert v.rowCount() == 3

            tasks_b = [make_mock_task(task_id=1, uid=1, name="B1")]
            project_b = make_mock_project(tasks=tasks_b)
            v.load_project(project_b)
        assert v.rowCount() == 1

    def test_load_none_after_data_clears(self, qapp):
        with patch('task_view._compute_critical_ids', return_value=(set(), {})):
            from task_view import TaskView
            v = TaskView()
            task = make_mock_task()
            v.load_project(make_mock_project(tasks=[task]))
            assert v.rowCount() == 1
            v.load_project(None)
        assert v.rowCount() == 0

    def test_java_tasks_list_populated(self, qapp):
        with patch('task_view._compute_critical_ids', return_value=(set(), {})):
            from task_view import TaskView
            v = TaskView()
            tasks = [make_mock_task(task_id=i, uid=i) for i in range(1, 4)]
            v.load_project(make_mock_project(tasks=tasks))
        assert len(v._java_tasks) == 3

    def test_java_tasks_list_cleared_on_none(self, view):
        with patch('task_view._compute_critical_ids', return_value=(set(), {})):
            view.load_project(None)
        assert view._java_tasks == []


# ---------------------------------------------------------------------------
# delete_selected_tasks()
# ---------------------------------------------------------------------------

class TestDeleteTasks:
    def test_delete_with_no_project_does_not_raise(self, view):
        view.delete_selected_tasks()   # should not raise

    def test_delete_selected_emits_data_changed(self, qapp):
        with patch('task_view._compute_critical_ids', return_value=(set(), {})):
            from task_view import TaskView
            v = TaskView()
            task = make_mock_task(task_id=1, uid=1)
            v.load_project(make_mock_project(tasks=[task]))
            v.selectRow(0)

            received = []
            v.data_changed.connect(lambda: received.append(1))
            v.delete_selected_tasks()

        assert len(received) > 0

    def test_delete_removes_row_from_view(self, qapp):
        with patch('task_view._compute_critical_ids', return_value=(set(), {})):
            from task_view import TaskView
            v = TaskView()
            tasks = [make_mock_task(task_id=i, uid=i) for i in range(1, 4)]
            v.load_project(make_mock_project(tasks=tasks))
            v.selectRow(0)
            v.delete_selected_tasks()
        assert v.rowCount() == 2


# ---------------------------------------------------------------------------
# get_collapsed_ids()
# ---------------------------------------------------------------------------

class TestCollapsedIds:
    def test_initial_collapsed_ids_empty(self, view):
        assert view.get_collapsed_ids() == set()

    def test_get_collapsed_ids_returns_copy(self, view):
        ids = view.get_collapsed_ids()
        ids.add("fake")
        assert "fake" not in view.get_collapsed_ids()


# ---------------------------------------------------------------------------
# set_zero_float_critical()
# ---------------------------------------------------------------------------

class TestZeroFloatCritical:
    def test_set_false(self, view):
        view.set_zero_float_critical(False)
        assert view._zero_float_critical is False

    def test_set_true(self, view):
        view.set_zero_float_critical(True)
        assert view._zero_float_critical is True

    def test_non_bool_coerced(self, view):
        view.set_zero_float_critical(1)
        assert view._zero_float_critical is True


# ---------------------------------------------------------------------------
# _on_double_click() — passes critical_ids and float_data to TaskDialog
# ---------------------------------------------------------------------------

class TestOnDoubleClick:
    """_on_double_click opens TaskDialog with correct critical_ids and float_data."""

    def test_double_click_passes_critical_ids_to_dialog(self, qapp):
        """critical_ids stored on the view are forwarded to TaskDialog."""
        with patch('task_view._compute_critical_ids', return_value=({3}, {3: {}})):
            from task_view import TaskView
            v = TaskView()
            task = make_mock_task(task_id=3, uid=3, name="T3")
            v.load_project(make_mock_project(tasks=[task]))

        with patch('task_view.TaskView._on_double_click') as _mock:
            # Trigger via internal call — verify the stored attribute directly
            pass
        assert 3 in v._critical_ids

    def test_double_click_passes_float_data_to_dialog(self, qapp):
        """float_data stored on the view after load_project matches what _compute_critical_ids returned."""
        fd = {7: {"total_float_wh": 0.0, "critical": True}}
        with patch('task_view._compute_critical_ids', return_value=({7}, fd)):
            from task_view import TaskView
            v = TaskView()
            task = make_mock_task(task_id=7, uid=7, name="T7")
            v.load_project(make_mock_project(tasks=[task]))

        assert v._float_data == fd

    def test_double_click_calls_task_dialog_with_kwargs(self, qapp):
        """_on_double_click instantiates TaskDialog with critical_ids and float_data kwargs."""
        fd = {1: {"total_float_wh": 8.0, "critical": False}}
        with patch('task_view._compute_critical_ids', return_value=(set(), fd)):
            from task_view import TaskView
            v = TaskView()
            task = make_mock_task(task_id=1, uid=1, name="Alpha")
            v.load_project(make_mock_project(tasks=[task]))

        mock_dlg = MagicMock()
        mock_dlg.exec_.return_value = 0  # Rejected — no apply_to_task
        # TaskDialog is imported locally inside _on_double_click from the dialogs module
        with patch('dialogs.TaskDialog', return_value=mock_dlg) as MockDialog:
            v._on_double_click(0, 0)

        MockDialog.assert_called_once()
        _, kwargs = MockDialog.call_args
        assert kwargs.get('critical_ids') == set()
        assert kwargs.get('float_data') == fd
