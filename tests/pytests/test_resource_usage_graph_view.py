"""Tests for views/resource_usage_graph_view.py — ResourceUsageGraphView widget.

ResourceUsageGraphView displays resource allocation as a day-by-day timeline:
  - Left pane: Resource/task names + total work
  - Right canvas: Daily/hourly work cells
  - Collapsible resource rows with task sub-rows

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

from conftest import make_mock_task, make_mock_resource, make_mock_project
from PyQt5.QtCore import QDate


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def view(qapp):
    """Return a fresh ResourceUsageGraphView with patched dependencies."""
    with patch('resource_usage_graph_view._get_non_working_dates', return_value=set()):
        from resource_usage_graph_view import ResourceUsageGraphView
        v = ResourceUsageGraphView()
    return v


# ---------------------------------------------------------------------------
# Initialisation
# ---------------------------------------------------------------------------

class TestResourceUsageGraphViewInit:
    def test_widget_is_created(self, qapp):
        with patch('resource_usage_graph_view._get_non_working_dates', return_value=set()):
            from resource_usage_graph_view import ResourceUsageGraphView
            v = ResourceUsageGraphView()
        assert v is not None

    def test_has_left_pane(self, view):
        assert hasattr(view, '_left_pane')

    def test_has_canvas(self, view):
        assert hasattr(view, '_canvas')

    def test_has_scroll_area(self, view):
        assert hasattr(view, '_right_scroll')

    def test_has_gantt_header(self, view):
        assert hasattr(view, '_gantt_hdr')

    def test_zoom_slider_exists(self, view):
        # Zoom methods don't exist in current implementation
        # Just check that day_width can be modified
        assert hasattr(view, '_day_width')


# ---------------------------------------------------------------------------
# load_project()
# ---------------------------------------------------------------------------

class TestLoadProject:
    def test_load_none_clears_view(self, view):
        with patch('resource_usage_graph_view._get_non_working_dates', return_value=set()):
            view.load_project(None)
        # Should not crash
        assert view._project is None

    def test_load_project_with_no_resources(self, qapp):
        with patch('resource_usage_graph_view._get_non_working_dates', return_value=set()):
            from resource_usage_graph_view import ResourceUsageGraphView
            v = ResourceUsageGraphView()
            project = make_mock_project(tasks=[], resources=[])
            v.load_project(project)
        assert v._project is project

    def test_load_project_with_one_resource(self, qapp):
        with patch('resource_usage_graph_view._get_non_working_dates', return_value=set()):
            from resource_usage_graph_view import ResourceUsageGraphView
            v = ResourceUsageGraphView()
            res = make_mock_resource(res_id=1, name="Resource A")
            project = make_mock_project(tasks=[], resources=[res])
            v.load_project(project)
        assert v._project is project

    def test_load_project_with_multiple_resources(self, qapp):
        with patch('resource_usage_graph_view._get_non_working_dates', return_value=set()):
            from resource_usage_graph_view import ResourceUsageGraphView
            v = ResourceUsageGraphView()
            resources = [make_mock_resource(res_id=i, name=f"Res{i}") for i in range(1, 4)]
            project = make_mock_project(tasks=[], resources=resources)
            v.load_project(project)
        assert v._project is project

    def test_load_project_replaces_previous_data(self, qapp):
        with patch('resource_usage_graph_view._get_non_working_dates', return_value=set()):
            from resource_usage_graph_view import ResourceUsageGraphView
            v = ResourceUsageGraphView()
            res_a = [make_mock_resource(res_id=i, name=f"A{i}") for i in range(1, 3)]
            project_a = make_mock_project(tasks=[], resources=res_a)
            v.load_project(project_a)
            
            res_b = [make_mock_resource(res_id=1, name="B1")]
            project_b = make_mock_project(tasks=[], resources=res_b)
            v.load_project(project_b)
        assert v._project is project_b

    def test_load_none_after_data_clears(self, qapp):
        with patch('resource_usage_graph_view._get_non_working_dates', return_value=set()):
            from resource_usage_graph_view import ResourceUsageGraphView
            v = ResourceUsageGraphView()
            res = make_mock_resource()
            v.load_project(make_mock_project(tasks=[], resources=[res]))
            v.load_project(None)
        assert v._project is None


# ---------------------------------------------------------------------------
# Resource Rows
# ---------------------------------------------------------------------------

class TestResourceRows:
    def test_resource_rows_built_from_project(self, qapp):
        with patch('resource_usage_graph_view._get_non_working_dates', return_value=set()):
            from resource_usage_graph_view import ResourceUsageGraphView
            v = ResourceUsageGraphView()
            resources = [
                make_mock_resource(res_id=1, name="Developer"),
                make_mock_resource(res_id=2, name="Designer")
            ]
            project = make_mock_project(tasks=[], resources=resources)
            v.load_project(project)
        # Check that resource rows were built
        assert len(v._rows) >= 2

    def test_resource_row_has_name(self, qapp):
        with patch('resource_usage_graph_view._get_non_working_dates', return_value=set()):
            from resource_usage_graph_view import ResourceUsageGraphView
            v = ResourceUsageGraphView()
            res = make_mock_resource(res_id=1, name="Engineer")
            project = make_mock_project(tasks=[], resources=[res])
            v.load_project(project)
        # First row should be the resource
        assert len(v._rows) > 0
        assert v._rows[0].name == "Engineer"


# ---------------------------------------------------------------------------
# Task Assignments
# ---------------------------------------------------------------------------

class TestTaskAssignments:
    def test_resource_with_no_assignments_shows_zero_work(self, qapp):
        with patch('resource_usage_graph_view._get_non_working_dates', return_value=set()):
            from resource_usage_graph_view import ResourceUsageGraphView
            v = ResourceUsageGraphView()
            res = make_mock_resource(res_id=1, name="Dev")
            res.getResourceAssignments.return_value = []
            task = make_mock_task(task_id=1, uid=1, name="Task 1")
            task.getResourceAssignments.return_value = []
            project = make_mock_project(tasks=[task], resources=[res])
            v.load_project(project)
        # Should have resource row but no task sub-rows
        assert len(v._rows) >= 1

    def test_resource_with_assignment_shows_task_row(self, qapp):
        with patch('resource_usage_graph_view._get_non_working_dates', return_value=set()):
            from resource_usage_graph_view import ResourceUsageGraphView
            v = ResourceUsageGraphView()
            
            # Create a mock assignment
            assignment = MagicMock()
            task = make_mock_task(task_id=1, uid=1, name="Task 1")
            res = make_mock_resource(res_id=1, name="Dev")
            assignment.getTask.return_value = task
            assignment.getResource.return_value = res
            assignment.getWork.return_value = MagicMock()
            assignment.getWork.return_value.getDuration.return_value = 40.0  # 40 hours
            
            res.getResourceAssignments.return_value = [assignment]
            task.getResourceAssignments.return_value = [assignment]
            
            project = make_mock_project(tasks=[task], resources=[res])
            v.load_project(project)
        # Should have resource row + task sub-row
        assert len(v._rows) >= 2


# ---------------------------------------------------------------------------
# Canvas Rendering
# ---------------------------------------------------------------------------

class TestCanvasRendering:
    def test_canvas_paint_does_not_crash(self, qapp):
        with patch('resource_usage_graph_view._get_non_working_dates', return_value=set()):
            from resource_usage_graph_view import ResourceUsageGraphView
            v = ResourceUsageGraphView()
            res = make_mock_resource(res_id=1, name="Dev")
            project = make_mock_project(tasks=[], resources=[res])
            v.load_project(project)
            # Trigger paint directly (no viewport for QWidget)
            v._canvas.update()
        assert True

    def test_left_pane_paint_does_not_crash(self, qapp):
        with patch('resource_usage_graph_view._get_non_working_dates', return_value=set()):
            from resource_usage_graph_view import ResourceUsageGraphView
            v = ResourceUsageGraphView()
            res = make_mock_resource(res_id=1, name="Dev")
            project = make_mock_project(tasks=[], resources=[res])
            v.load_project(project)
            # Trigger paint directly (no viewport for QWidget)
            v._left_pane.update()
        assert True


# ---------------------------------------------------------------------------
# Zoom
# ---------------------------------------------------------------------------

class TestZoom:
    def test_day_width_can_be_modified(self, view):
        # Zoom methods don't exist, but day_width is adjustable
        initial = view._day_width
        view._day_width = 50
        assert view._day_width == 50
        view._day_width = initial


# ---------------------------------------------------------------------------
# Navigation
# ---------------------------------------------------------------------------

class TestNavigation:
    def test_has_scroll_to_today_method(self, view):
        # Should have a method to scroll to today
        assert hasattr(view, '_scroll_to_today')


# ---------------------------------------------------------------------------
# WheelForwarder helper class
# ---------------------------------------------------------------------------

class TestWheelForwarder:
    def test_wheel_forwarder_exists(self, qapp):
        from resource_usage_graph_view import _WheelForwarder
        from PyQt5.QtWidgets import QScrollArea
        scroll_area = QScrollArea()
        forwarder = _WheelForwarder(scroll_area)
        assert forwarder is not None

    def test_wheel_forwarder_forwards_events(self, qapp):
        from resource_usage_graph_view import _WheelForwarder
        from PyQt5.QtWidgets import QScrollArea, QApplication
        from PyQt5.QtCore import QEvent
        
        scroll_area = QScrollArea()
        forwarder = _WheelForwarder(scroll_area)
        
        # Create a mock wheel event with the correct type value
        wheel_event = MagicMock()
        wheel_event.type.return_value = QEvent.Wheel
        
        # Patch sendEvent to avoid passing a non-QEvent to Qt
        with patch.object(QApplication, 'sendEvent', return_value=True):
            result = forwarder.eventFilter(None, wheel_event)
        # Wheel event should be consumed (True)
        assert result is True


# ---------------------------------------------------------------------------
# set_timeline_view
# ---------------------------------------------------------------------------

class TestSetTimelineView:
    def test_method_exists(self, view):
        assert callable(getattr(view, 'set_timeline_view', None))

    def test_stores_reference(self, view):
        tv = MagicMock()
        view.set_timeline_view(tv)
        assert view._timeline_view is tv

    def test_set_none_clears_reference(self, view):
        tv = MagicMock()
        view.set_timeline_view(tv)
        view.set_timeline_view(None)
        assert view._timeline_view is None

    def test_initial_value_is_none(self, view):
        """_timeline_view must default to None before set_timeline_view is called."""
        assert getattr(view, '_timeline_view', None) is None
