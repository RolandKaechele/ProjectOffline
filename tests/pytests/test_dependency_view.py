"""Tests for views/dependency_view.py — DependencyView widget.

Requires a QApplication (provided by the session-scoped 'qapp' fixture).
MPXJ Relation objects are replaced with MagicMock instances.
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
# Mock relation builder
# ---------------------------------------------------------------------------

def _make_relation(pred_id=1, pred_name="Predecessor", rel_type="FS", lag="0d"):
    pred_task = MagicMock()
    pred_task.getID.return_value   = pred_id
    pred_task.getName.return_value = pred_name

    relation = MagicMock()
    relation.getPredecessorTask.return_value = pred_task
    rel_type_mock = MagicMock()
    rel_type_mock.__str__ = MagicMock(return_value=rel_type)
    relation.getType.return_value = rel_type_mock
    lag_mock = MagicMock()
    lag_mock.__str__ = MagicMock(return_value=lag)
    relation.getLag.return_value  = lag_mock
    return relation


def _make_project_with_dependency():
    """Project with 2 tasks; task 2 has task 1 as predecessor."""
    task1 = make_mock_task(task_id=1, uid=1, name="Alpha")
    task1.getPredecessors.return_value = []

    rel = _make_relation(pred_id=1, pred_name="Alpha")
    task2 = make_mock_task(task_id=2, uid=2, name="Beta")
    task2.getPredecessors.return_value = [rel]

    return make_mock_project(tasks=[task1, task2]), task1, task2, rel


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def view(qapp):
    from dependency_view import DependencyView
    return DependencyView()


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

class TestDependencyViewInit:
    def test_widget_created(self, qapp):
        from dependency_view import DependencyView
        assert DependencyView() is not None

    def test_initial_row_count_is_zero(self, view):
        assert view.rowCount() == 0

    def test_column_count_matches_constant(self, view):
        from dependency_view import DependencyView
        assert view.columnCount() == len(DependencyView.COLUMNS)

    def test_data_changed_signal_exists(self, view):
        assert hasattr(view, 'data_changed')


# ---------------------------------------------------------------------------
# load_project()
# ---------------------------------------------------------------------------

class TestLoadProject:
    def test_load_none_clears_rows(self, view):
        view.load_project(None)
        assert view.rowCount() == 0

    def test_load_project_with_no_dependencies(self, qapp):
        from dependency_view import DependencyView
        v = DependencyView()
        task = make_mock_task(task_id=1, uid=1)
        task.getPredecessors.return_value = []
        project = make_mock_project(tasks=[task])
        v.load_project(project)
        assert v.rowCount() == 0

    def test_load_project_with_one_dependency(self, qapp):
        from dependency_view import DependencyView
        v = DependencyView()
        project, _, _, _ = _make_project_with_dependency()
        v.load_project(project)
        assert v.rowCount() == 1

    def test_dependency_successor_name_shown(self, qapp):
        from dependency_view import DependencyView
        v = DependencyView()
        project, _, _, _ = _make_project_with_dependency()
        v.load_project(project)
        # Col 1 = Task Name (successor)
        name_item = v.item(0, 1)
        assert name_item is not None
        assert name_item.text() == "Beta"

    def test_dependency_predecessor_name_shown(self, qapp):
        from dependency_view import DependencyView
        v = DependencyView()
        project, _, _, _ = _make_project_with_dependency()
        v.load_project(project)
        # Col 3 = Predecessor Name
        pred_name_item = v.item(0, 3)
        assert pred_name_item is not None
        assert pred_name_item.text() == "Alpha"

    def test_dependency_link_type_shown(self, qapp):
        from dependency_view import DependencyView
        v = DependencyView()
        project, _, _, _ = _make_project_with_dependency()
        v.load_project(project)
        # Col 4 = Link Type
        link_type_item = v.item(0, 4)
        assert link_type_item is not None
        assert "FS" in link_type_item.text()

    def test_multiple_dependencies_all_shown(self, qapp):
        from dependency_view import DependencyView
        v = DependencyView()
        task1 = make_mock_task(task_id=1, uid=1, name="A")
        task1.getPredecessors.return_value = []
        rel2 = _make_relation(pred_id=1, pred_name="A")
        rel3 = _make_relation(pred_id=1, pred_name="A", rel_type="SS")
        task2 = make_mock_task(task_id=2, uid=2, name="B")
        task2.getPredecessors.return_value = [rel2]
        task3 = make_mock_task(task_id=3, uid=3, name="C")
        task3.getPredecessors.return_value = [rel3]
        project = make_mock_project(tasks=[task1, task2, task3])
        v.load_project(project)
        assert v.rowCount() == 2

    def test_tasks_with_none_predecessors_skipped(self, qapp):
        from dependency_view import DependencyView
        v = DependencyView()
        task = make_mock_task(task_id=1, uid=1, name="Solo")
        task.getPredecessors.return_value = None
        project = make_mock_project(tasks=[task])
        v.load_project(project)
        assert v.rowCount() == 0

    def test_load_replaces_previous(self, qapp):
        from dependency_view import DependencyView
        v = DependencyView()
        project, _, _, _ = _make_project_with_dependency()
        v.load_project(project)
        assert v.rowCount() == 1
        v.load_project(None)
        assert v.rowCount() == 0


# ---------------------------------------------------------------------------
# delete_selected_dependencies()
# ---------------------------------------------------------------------------

class TestDeleteDependencies:
    def test_delete_with_no_project_does_not_raise(self, view):
        view.delete_selected_dependencies()

    def test_delete_selected_emits_data_changed(self, qapp):
        from dependency_view import DependencyView
        v = DependencyView()
        project, _, _, rel = _make_project_with_dependency()
        v.load_project(project)
        v.selectRow(0)

        received = []
        v.data_changed.connect(lambda: received.append(1))
        v.delete_selected_dependencies()

        assert len(received) > 0

    def test_delete_removes_row(self, qapp):
        from dependency_view import DependencyView
        v = DependencyView()
        project, _, _, _ = _make_project_with_dependency()
        v.load_project(project)
        assert v.rowCount() == 1
        v.selectRow(0)
        v.delete_selected_dependencies()
        assert v.rowCount() == 0
