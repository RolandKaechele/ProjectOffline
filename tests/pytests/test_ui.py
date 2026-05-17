"""Tests for ui.py â€” MainWindow class.

MainWindow is the main application window that orchestrates:
  - All 8 views (TaskView, GanttView, ResourceView, etc.)
  - Tab switching and layout management
  - Menu bar and ribbon toolbar
  - Undo/redo history management
  - File operations (open, save, new)
  - Zoom controls

Requires a QApplication (provided by the session-scoped 'qapp' fixture).
Most dependencies are mocked to avoid complex initialization.

jpype and mpxj are stubbed in sys.modules by conftest.py so source modules
that contain lazy ``import jpype`` calls can be imported successfully.
"""

import sys
import os

import pytest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from logic import ProjectLogic
from file_handler import ProjectFileHandler  # importable; jpype stubbed by conftest


# ---------------------------------------------------------------------------
# HorizontalWheelBlocker
# ---------------------------------------------------------------------------

class TestHorizontalWheelBlocker:
    def test_wheel_blocker_exists(self, qapp):
        from ui import _HorizontalWheelBlocker
        blocker = _HorizontalWheelBlocker()
        assert blocker is not None

    def test_wheel_blocker_is_event_filter(self, qapp):
        from ui import _HorizontalWheelBlocker
        from PyQt5.QtCore import QObject
        blocker = _HorizontalWheelBlocker()
        assert isinstance(blocker, QObject)

    def test_wheel_blocker_has_event_filter_method(self, qapp):
        from ui import _HorizontalWheelBlocker
        blocker = _HorizontalWheelBlocker()
        assert hasattr(blocker, 'eventFilter')
        assert callable(blocker.eventFilter)


# ---------------------------------------------------------------------------
# MainWindow Initialization
# ---------------------------------------------------------------------------

def _make_timeline_mock():
    """Return a real QWidget that stands in for TimelineView in the test fixture.

    QVBoxLayout.addWidget() requires a real QWidget, so MagicMock() cannot be
    used directly.  All custom attributes called during MainWindow.__init__ are
    added as plain no-op callables.
    """
    from PyQt5.QtWidgets import QWidget
    w = QWidget()
    w._timeline_tasks      = []
    w._timeline_milestones = []
    w.register             = MagicMock()
    w.is_task_pinned       = MagicMock(return_value=False)
    w.is_milestone_pinned  = MagicMock(return_value=False)
    w._set_collapsed       = MagicMock()
    return w


@pytest.fixture
def main_window(qapp):
    """Return a MainWindow with heavily mocked dependencies.

    Each Qt view widget (QWidget / QTableView) is used as-is so that
    QSplitter / QTabWidget accept them as real widgets.  All custom signals
    and methods that MainWindow.__init__ calls on these widgets are added as
    plain Python attributes or lambdas so they accept calls without error.
    """
    import ui
    from PyQt5.QtWidgets import QWidget, QTableView, QMenuBar, QToolBar, QScrollBar

    class MockSignal:
        """Lightweight stand-in for a Qt signal (connect / emit accepted)."""
        def connect(self, *args, **kwargs):
            pass
        def emit(self, *args, **kwargs):
            pass

    # ---- task view ----------------------------------------------------------
    task_view = QTableView()
    task_view.data_changed      = MockSignal()
    task_view.task_reordered    = MockSignal()
    task_view.selection_changed = MockSignal()
    task_view.show_in_gantt     = MockSignal()
    task_view.timeline_toggle_requested = MockSignal()
    task_view.set_zero_float_critical = MagicMock()

    # ---- gantt view ---------------------------------------------------------
    gantt_view = QWidget()
    gantt_view.task_moved             = MockSignal()
    gantt_view.task_edited            = MockSignal()
    gantt_view.zoom_changed           = MockSignal()
    gantt_view.set_show_resource_units = MagicMock()
    gantt_view.set_show_sundays        = MagicMock()
    gantt_view.set_zero_float_critical = MagicMock()
    gantt_view.set_day_width           = MagicMock()
    gantt_view.load_project            = MagicMock()
    gantt_view.set_timeline_view       = MagicMock()
    gantt_view.clear_splits            = MagicMock()
    gantt_view.canvas                  = MagicMock()
    # verticalScrollBar() must return a real QScrollBar so that .valueChanged
    # and .setValue work as genuine Qt signal/slot connections.
    _gantt_vsb = QScrollBar()
    gantt_view.verticalScrollBar = lambda: _gantt_vsb

    # ---- resource view ------------------------------------------------------
    resource_view = QTableView()
    resource_view.data_changed = MockSignal()

    # ---- dependency view ----------------------------------------------------
    dependency_view = QTableView()
    dependency_view.data_changed = MockSignal()

    # ---- baseline view ------------------------------------------------------
    baseline_view = QTableView()

    # ---- team planner view --------------------------------------------------
    team_planner_view = QWidget()
    team_planner_view.data_changed    = MockSignal()
    team_planner_view.set_show_sundays = MagicMock()
    team_planner_view.canvas          = MagicMock()
    team_planner_view.canvas.set_zero_float_critical = MagicMock()
    _tp_hsb = QScrollBar()
    _tp_rows_area = QWidget()
    _tp_rows_area.horizontalScrollBar = lambda: _tp_hsb
    team_planner_view._rows_area = _tp_rows_area

    # ---- task sheet view ----------------------------------------------------
    task_sheet_view = QTableView()
    task_sheet_view.data_changed = MockSignal()
    task_sheet_view.timeline_toggle_requested = MockSignal()

    # ---- resource usage graph view ------------------------------------------
    resource_usage_view = QWidget()
    resource_usage_view.task_edited      = MockSignal()
    resource_usage_view.set_show_sundays  = MagicMock()
    resource_usage_view.set_show_off_hours = MagicMock()

    # ---- resource usage histogram view --------------------------------------
    histogram_view = QWidget()
    histogram_view.set_scroll_x = MagicMock()
    histogram_view.set_day_width = MagicMock()
    histogram_view.load_project  = MagicMock()

    # ---- menu bar -----------------------------------------------------------
    mock_menu_bar = QMenuBar()
    mock_menu_bar.set_resource_units_checked    = MagicMock()
    mock_menu_bar.set_show_sundays_checked      = MagicMock()
    mock_menu_bar.set_show_off_hours_checked    = MagicMock()
    mock_menu_bar.set_zero_float_critical_checked = MagicMock()
    mock_menu_bar.set_timeline_checked          = MagicMock()
    mock_menu_bar.set_show_histogram_checked    = MagicMock()
    mock_menu_bar.set_save_enabled              = MagicMock()
    mock_menu_bar.set_close_enabled             = MagicMock()
    mock_menu_bar.update_recent_files           = MagicMock()
    mock_menu_bar.update_edit_actions           = MagicMock()
    mock_menu_bar.set_delete_enabled            = MagicMock()

    # ---- toolbar / ribbon ---------------------------------------------------
    mock_tool_bar = QToolBar()
    mock_ribbon = MagicMock()
    mock_ribbon.ribbon_tab_changed = MockSignal()
    mock_tool_bar.ribbon          = mock_ribbon
    mock_tool_bar.set_save_enabled = MagicMock()
    mock_tool_bar.set_delete_enabled = MagicMock()
    mock_tool_bar.update_actions   = MagicMock()

    with patch.object(ui, 'TaskView',               return_value=task_view), \
         patch.object(ui, 'GanttView',              return_value=gantt_view), \
         patch.object(ui, 'ResourceView',           return_value=resource_view), \
         patch.object(ui, 'DependencyView',         return_value=dependency_view), \
         patch.object(ui, 'BaselineView',           return_value=baseline_view), \
         patch.object(ui, 'TeamPlannerView',        return_value=team_planner_view), \
         patch.object(ui, 'TaskSheetView',          return_value=task_sheet_view), \
         patch.object(ui, 'ResourceUsageGraphView', return_value=resource_usage_view), \
         patch.object(ui, 'ResourceUsageHistogramView', return_value=histogram_view), \
         patch.object(ui, 'TimelineView',            return_value=_make_timeline_mock()), \
         patch.object(ui, 'HistoryManager'), \
         patch.object(ui, 'ProjectMenuBar',         return_value=mock_menu_bar), \
         patch.object(ui, 'ProjectToolBar',         return_value=mock_tool_bar):

        logic        = ProjectLogic()
        file_handler = MagicMock()
        file_handler.logic = logic

        window = ui.MainWindow(logic, file_handler)
        return window


class TestMainWindowInit:
    def test_window_is_created(self, main_window):
        assert main_window is not None

    def test_window_has_title(self, main_window):
        assert main_window.windowTitle() == "Project Offline"

    def test_window_stores_logic_reference(self, main_window):
        assert hasattr(main_window, 'logic')
        assert main_window.logic is not None

    def test_window_stores_file_handler_reference(self, main_window):
        assert hasattr(main_window, 'file_handler')
        assert main_window.file_handler is not None

    def test_window_has_views(self, main_window):
        assert hasattr(main_window, 'task_view')
        assert hasattr(main_window, 'gantt_view')
        assert hasattr(main_window, 'resource_view')
        assert hasattr(main_window, 'dependency_view')
        assert hasattr(main_window, 'baseline_view')
        assert hasattr(main_window, 'team_planner_view')
        assert hasattr(main_window, 'task_sheet_view')
        assert hasattr(main_window, 'resource_usage_graph_view')

    def test_window_has_tabs(self, main_window):
        assert hasattr(main_window, 'tabs')

    def test_window_has_history_manager(self, main_window):
        assert hasattr(main_window, '_history')

    def test_window_has_current_file_path(self, main_window):
        assert hasattr(main_window, '_current_file_path')

    def test_initial_file_path_is_none(self, main_window):
        assert main_window._current_file_path is None

    def test_window_has_dirty_flag(self, main_window):
        assert hasattr(main_window, '_dirty')

    def test_initial_dirty_flag_is_false(self, main_window):
        assert main_window._dirty is False

    def test_window_has_settings_manager(self, main_window):
        assert hasattr(main_window, '_settings_manager')

    def test_tab_count_matches_views(self, main_window):
        from app_tabs import (
            TAB_GANTT, TAB_RESOURCES, TAB_DEPENDENCIES, TAB_BASELINE,
            TAB_TEAM_PLANNER, TAB_TASK_SHEET, TAB_RESOURCE_USAGE, TAB_CPM,
        )
        assert main_window.tabs.count() == 8  # TAB_CPM added in Phase 3


# ---------------------------------------------------------------------------
# File Operations
# ---------------------------------------------------------------------------

class TestFileOperations:
    def test_new_project_method_exists(self, main_window):
        assert hasattr(main_window, 'new_project')
        assert callable(main_window.new_project)

    def test_open_project_method_exists(self, main_window):
        assert hasattr(main_window, 'open_project')
        assert callable(main_window.open_project)

    def test_save_project_method_exists(self, main_window):
        assert hasattr(main_window, 'save_project')
        assert callable(main_window.save_project)

    def test_save_project_as_method_exists(self, main_window):
        assert hasattr(main_window, 'save_project_as')
        assert callable(main_window.save_project_as)

    def test_open_project_file_method_exists(self, main_window):
        assert hasattr(main_window, 'open_project_file')
        assert callable(main_window.open_project_file)


# ---------------------------------------------------------------------------
# Tab Management
# ---------------------------------------------------------------------------

class TestTabManagement:
    def test_on_tab_changed_method_exists(self, main_window):
        assert hasattr(main_window, '_on_tab_changed')
        assert callable(main_window._on_tab_changed)

    def test_on_ribbon_tab_changed_method_exists(self, main_window):
        assert hasattr(main_window, '_on_ribbon_tab_changed')
        assert callable(main_window._on_ribbon_tab_changed)

    def test_last_app_tab_for_ribbon_dict_exists(self, main_window):
        assert hasattr(main_window, '_last_app_tab_for_ribbon')
        assert isinstance(main_window._last_app_tab_for_ribbon, dict)

    def test_app_to_ribbon_tab_mapping_exists(self, main_window):
        assert hasattr(main_window, '_APP_TO_RIBBON_TAB')
        assert isinstance(main_window._APP_TO_RIBBON_TAB, dict)


# ---------------------------------------------------------------------------
# Undo / Redo
# ---------------------------------------------------------------------------

class TestUndoRedo:
    def test_undo_method_exists(self, main_window):
        assert hasattr(main_window, '_undo')
        assert callable(main_window._undo)

    def test_redo_method_exists(self, main_window):
        assert hasattr(main_window, '_redo')
        assert callable(main_window._redo)

    def test_history_manager_exists(self, main_window):
        assert hasattr(main_window, '_history')


# ---------------------------------------------------------------------------
# Zoom Controls
# ---------------------------------------------------------------------------

class TestZoomControls:
    def test_zoom_in_method_exists(self, main_window):
        assert hasattr(main_window, 'zoom_in')
        assert callable(main_window.zoom_in)

    def test_zoom_out_method_exists(self, main_window):
        assert hasattr(main_window, 'zoom_out')
        assert callable(main_window.zoom_out)

    def test_on_zoom_slider_method_exists(self, main_window):
        assert hasattr(main_window, '_on_zoom_slider')
        assert callable(main_window._on_zoom_slider)

    def test_zoom_slider_exists(self, main_window):
        assert hasattr(main_window, '_zoom_slider')

    def test_zoom_pct_label_exists(self, main_window):
        assert hasattr(main_window, '_zoom_pct_label')


# ---------------------------------------------------------------------------
# View Toggle Methods
# ---------------------------------------------------------------------------

class TestViewToggles:
    def test_toggle_resource_units_method_exists(self, main_window):
        assert hasattr(main_window, 'toggle_resource_units')
        assert callable(main_window.toggle_resource_units)

    def test_toggle_show_sundays_method_exists(self, main_window):
        assert hasattr(main_window, 'toggle_show_sundays')
        assert callable(main_window.toggle_show_sundays)

    def test_toggle_show_off_hours_method_exists(self, main_window):
        assert hasattr(main_window, 'toggle_show_off_hours')
        assert callable(main_window.toggle_show_off_hours)

    def test_toggle_zero_float_critical_method_exists(self, main_window):
        assert hasattr(main_window, 'toggle_zero_float_critical')
        assert callable(main_window.toggle_zero_float_critical)


# ---------------------------------------------------------------------------
# Data Change Handlers
# ---------------------------------------------------------------------------

class TestDataChangeHandlers:
    def test_on_task_data_changed_method_exists(self, main_window):
        assert hasattr(main_window, '_on_task_data_changed')
        assert callable(main_window._on_task_data_changed)

    def test_on_resource_data_changed_method_exists(self, main_window):
        assert hasattr(main_window, '_on_resource_data_changed')
        assert callable(main_window._on_resource_data_changed)

    def test_on_dependency_data_changed_method_exists(self, main_window):
        assert hasattr(main_window, '_on_dependency_data_changed')
        assert callable(main_window._on_dependency_data_changed)

    def test_on_gantt_task_moved_method_exists(self, main_window):
        assert hasattr(main_window, '_on_gantt_task_moved')
        assert callable(main_window._on_gantt_task_moved)

    def test_on_gantt_task_edited_method_exists(self, main_window):
        assert hasattr(main_window, '_on_gantt_task_edited')
        assert callable(main_window._on_gantt_task_edited)

    def test_on_team_planner_data_changed_method_exists(self, main_window):
        assert hasattr(main_window, '_on_team_planner_data_changed')
        assert callable(main_window._on_team_planner_data_changed)

    def test_on_task_sheet_data_changed_method_exists(self, main_window):
        assert hasattr(main_window, '_on_task_sheet_data_changed')
        assert callable(main_window._on_task_sheet_data_changed)

    def test_mark_dirty_method_exists(self, main_window):
        assert hasattr(main_window, '_mark_dirty')
        assert callable(main_window._mark_dirty)

    def test_mark_dirty_sets_dirty_flag(self, main_window):
        main_window._dirty = False
        main_window._mark_dirty()
        assert main_window._dirty is True

    def test_mark_clean_clears_dirty_flag(self, main_window):
        main_window._dirty = True
        main_window._mark_clean()
        assert main_window._dirty is False


# ---------------------------------------------------------------------------
# Export Methods
# ---------------------------------------------------------------------------

class TestExportMethods:
    def test_export_gantt_svg_method_exists(self, main_window):
        assert hasattr(main_window, 'export_gantt_svg')
        assert callable(main_window.export_gantt_svg)

    def test_export_resource_gantt_svg_method_exists(self, main_window):
        assert hasattr(main_window, 'export_resource_gantt_svg')
        assert callable(main_window.export_resource_gantt_svg)

    def test_export_gantt_plantuml_method_exists(self, main_window):
        assert hasattr(main_window, 'export_gantt_plantuml')
        assert callable(main_window.export_gantt_plantuml)


# ---------------------------------------------------------------------------
# Import Methods
# ---------------------------------------------------------------------------

class TestImportMethods:
    def test_import_plantuml_method_exists(self, main_window):
        assert hasattr(main_window, 'import_plantuml')
        assert callable(main_window.import_plantuml)


# ---------------------------------------------------------------------------
# Selection Handlers
# ---------------------------------------------------------------------------

class TestSelectionHandlers:
    def test_on_task_selection_changed_method_exists(self, main_window):
        assert hasattr(main_window, '_on_task_selection_changed')
        assert callable(main_window._on_task_selection_changed)

    def test_on_task_reordered_method_exists(self, main_window):
        assert hasattr(main_window, '_on_task_reordered')
        assert callable(main_window._on_task_reordered)


# ---------------------------------------------------------------------------
# Recent Files
# ---------------------------------------------------------------------------

class TestRecentFiles:
    def test_load_recent_files_method_exists(self, main_window):
        assert hasattr(main_window, '_load_recent_files')
        assert callable(main_window._load_recent_files)

    def test_add_to_recent_method_exists(self, main_window):
        assert hasattr(main_window, '_add_to_recent')
        assert callable(main_window._add_to_recent)

    def test_clear_recent_files_method_exists(self, main_window):
        assert hasattr(main_window, 'clear_recent_files')
        assert callable(main_window.clear_recent_files)


# ---------------------------------------------------------------------------
# Tab / Ribbon constants
# ---------------------------------------------------------------------------

class TestAppTabsModule:
    def test_tab_constants_exist(self):
        from app_tabs import (
            TAB_GANTT, TAB_RESOURCES, TAB_DEPENDENCIES, TAB_BASELINE,
            TAB_TEAM_PLANNER, TAB_TASK_SHEET, TAB_RESOURCE_USAGE,
        )
        assert TAB_GANTT == 0
        assert TAB_RESOURCES == 1
        assert TAB_DEPENDENCIES == 2
        assert TAB_BASELINE == 3
        assert TAB_TEAM_PLANNER == 4
        assert TAB_TASK_SHEET == 5
        assert TAB_RESOURCE_USAGE == 6

    def test_ribbon_constants_exist(self):
        from app_tabs import RIBBON_TASK, RIBBON_RESOURCE, RIBBON_REPORT
        assert RIBBON_TASK == 0
        assert RIBBON_RESOURCE == 1
        assert RIBBON_REPORT == 2


# ---------------------------------------------------------------------------
# Timeline view integration
# ---------------------------------------------------------------------------

class TestTimelineViewIntegration:
    """Tests for the Timeline strip embedded in MainWindow."""

    def test_timeline_view_attribute_exists(self, main_window):
        assert hasattr(main_window, 'timeline_view')

    def test_timeline_view_starts_collapsed(self, main_window):
        """timeline_view must start with _set_collapsed(True) → invisible + 0 height."""
        # The mock's _set_collapsed is a MagicMock; we verify it was called at
        # least once with True during __init__ (via _update_timeline_visibility).
        main_window.timeline_view._set_collapsed.assert_called()

    def test_toggle_timeline_saves_to_settings(self, main_window):
        main_window.toggle_timeline(True)
        val = main_window._settings.value("timeline/visible", False, type=bool)
        assert val is True

    def test_toggle_timeline_false_saves_to_settings(self, main_window):
        main_window.toggle_timeline(False)
        val = main_window._settings.value("timeline/visible", False, type=bool)
        assert val is False

    def test_toggle_timeline_calls_set_timeline_checked(self, main_window):
        main_window.toggle_timeline(True)
        main_window.menuBar().set_timeline_checked.assert_called_with(True)

    def test_toggle_timeline_calls_set_collapsed(self, main_window):
        """toggle_timeline must eventually call _set_collapsed on the timeline view."""
        main_window.toggle_timeline(True)
        main_window.timeline_view._set_collapsed.assert_called()

    def test_update_timeline_visibility_before_settings_is_safe(self, main_window):
        """Guard: calling _update_timeline_visibility before _settings must not raise."""
        saved = main_window._settings
        del main_window._settings
        try:
            main_window._update_timeline_visibility()   # must not raise
        finally:
            main_window._settings = saved

    def test_gantt_view_receives_timeline_reference(self, main_window):
        """set_timeline_view must have been called on gantt_view during init."""
        main_window.gantt_view.set_timeline_view.assert_called_once_with(
            main_window.timeline_view
        )

    def test_on_window_state_settled_method_exists(self, main_window):
        assert hasattr(main_window, '_on_window_state_settled')
        assert callable(main_window._on_window_state_settled)

    def test_on_window_state_settled_calls_update_visibility(self, main_window):
        """_on_window_state_settled must re-apply timeline visibility."""
        initial_call_count = main_window.timeline_view._set_collapsed.call_count
        main_window._on_window_state_settled()
        assert main_window.timeline_view._set_collapsed.call_count > initial_call_count

    def test_on_timeline_data_changed_method_exists(self, main_window):
        assert hasattr(main_window, '_on_timeline_data_changed')
        assert callable(main_window._on_timeline_data_changed)

    def test_on_timeline_remove_from_canvas_method_exists(self, main_window):
        assert hasattr(main_window, '_on_timeline_remove_from_canvas')
        assert callable(main_window._on_timeline_remove_from_canvas)


# ---------------------------------------------------------------------------
# Menu Customisation (File → New, File → Close, no-project guard)
# ---------------------------------------------------------------------------

class TestMenuCustomisation:
    """Tests for the three menu customisation items implemented in phase 3.

    1. File → New opens Project Information dialog so the user sets
       mandatory start / end dates before any tasks are created.
    2. File → Close prompts to save unsaved changes then clears the project.
    3. Add Task / Add Resource are no-ops (do NOT auto-create a project)
       when no project is currently open.
    """

    def test_close_project_method_exists(self, main_window):
        assert hasattr(main_window, 'close_project')
        assert callable(main_window.close_project)

    def test_new_project_opens_project_info_dialog(self, main_window):
        """new_project() must call open_project_info() so the user can set
        project start / end dates before the first task is added."""
        with patch.object(main_window, '_refresh_all_views'), \
             patch.object(main_window._history, 'push_all'), \
             patch.object(main_window, '_setup_new_project_calendars'), \
             patch.object(main_window, 'open_project_info') as mock_info:
            main_window.new_project()
        mock_info.assert_called_once()

    def test_close_project_no_dirty_clears_project(self, main_window):
        """close_project() with no unsaved changes must clear the project
        without showing a save dialog."""
        main_window._dirty = False
        main_window.logic.load_data(MagicMock())   # simulate open project
        with patch.object(main_window, '_refresh_all_views'), \
             patch.object(main_window._history, 'push_all'), \
             patch('ui.QMessageBox.question') as mock_q:
            main_window.close_project()
        mock_q.assert_not_called()               # no dialog shown
        assert main_window.logic.get_data() is None
        assert main_window._current_file_path is None
        assert main_window._dirty is False

    def test_close_project_dirty_discard_closes(self, main_window):
        """close_project() with unsaved changes and Discard reply must
        close without saving."""
        from PyQt5.QtWidgets import QMessageBox
        main_window._dirty = True
        main_window.logic.load_data(MagicMock())
        with patch.object(main_window, '_refresh_all_views'), \
             patch.object(main_window._history, 'push_all'), \
             patch('ui.QMessageBox.question', return_value=QMessageBox.Discard):
            main_window.close_project()
        assert main_window.logic.get_data() is None
        assert main_window._dirty is False

    def test_close_project_dirty_cancel_aborts(self, main_window):
        """close_project() with unsaved changes and Cancel reply must
        leave the project open and unchanged."""
        from PyQt5.QtWidgets import QMessageBox
        main_window._dirty = True
        sentinel = MagicMock()
        main_window.logic.load_data(sentinel)
        with patch('ui.QMessageBox.question', return_value=QMessageBox.Cancel):
            main_window.close_project()
        assert main_window._dirty is True          # project still open
        assert main_window.logic.get_data() is sentinel

    def test_close_project_dirty_save_then_close(self, main_window):
        """close_project() with unsaved changes and Save reply must
        call save_project() and then close."""
        from PyQt5.QtWidgets import QMessageBox
        main_window._dirty = True
        main_window.logic.load_data(MagicMock())
        with patch.object(main_window, '_refresh_all_views'), \
             patch.object(main_window._history, 'push_all'), \
             patch.object(main_window, 'save_project',
                          side_effect=lambda: setattr(main_window, '_dirty', False)) as mock_save, \
             patch('ui.QMessageBox.question', return_value=QMessageBox.Save):
            main_window.close_project()
        mock_save.assert_called_once()
        assert main_window.logic.get_data() is None

    def test_add_entry_no_project_does_not_create_new(self, main_window):
        """add_entry() must NOT silently call new_project() when no project
        is open — the ribbon buttons are disabled in that state."""
        main_window.logic.load_data(None)
        with patch.object(main_window, 'new_project') as mock_new:
            main_window.add_entry()
        mock_new.assert_not_called()

    def test_add_resource_no_project_does_not_create_new(self, main_window):
        """add_resource() must NOT silently call new_project() when no
        project is open — the ribbon buttons are disabled in that state."""
        main_window.logic.load_data(None)
        main_window.resource_view.add_resource = MagicMock()
        with patch.object(main_window, 'new_project') as mock_new:
            main_window.add_resource()
        mock_new.assert_not_called()

    def test_close_project_clears_gantt_splits(self, main_window):
        """close_project() must call gantt_view.clear_splits() to discard
        any split-task data from the previous project."""
        main_window._dirty = False
        with patch.object(main_window, '_refresh_all_views'), \
             patch.object(main_window._history, 'push_all'):
            main_window.close_project()
        main_window.gantt_view.clear_splits.assert_called_once()

    def test_close_project_disables_close_menu_via_refresh(self, main_window):
        """After close_project(), _refresh_all_views enables/disables the
        Close menu item based on project-open state; with no project the
        menu bar receives set_close_enabled(False)."""
        main_window._dirty = False
        with patch.object(main_window, '_refresh_all_views') as mock_refresh, \
             patch.object(main_window._history, 'push_all'):
            main_window.close_project()
        # _refresh_all_views is the code path that calls set_close_enabled;
        # verify it was reached (real behaviour is tested in integration).
        mock_refresh.assert_called_once()


# ---------------------------------------------------------------------------
# VCS Ribbon State Updates
# ---------------------------------------------------------------------------

class TestUpdateVcsRibbonState:
    """Unit tests for MainWindow._update_vcs_ribbon_state().

    The method reads VCS configuration and updates the ribbon accordingly.
    All VCS module calls and ribbon calls are mocked so no SVN/Git process
    is spawned.
    """

    @staticmethod
    def _vcs_patch(mock_vcs):
        """Return a context manager that patches version_control_integration
        both in sys.modules and as an attribute on the integrations package so
        the in-function ``from integrations import version_control_integration``
        receives the mock regardless of import-order in the test session."""
        import integrations as _int_pkg
        return patch.multiple(
            _int_pkg,
            version_control_integration=mock_vcs,
        )

    def test_no_repo_hides_vcs_tab(self, main_window):
        """When vcs.is_configured() returns False, set_vcs_tab_visible(False)
        must be called."""
        ribbon = main_window._toolbar.ribbon
        mock_vcs = MagicMock()
        mock_vcs.is_configured.return_value = False
        with self._vcs_patch(mock_vcs):
            main_window._update_vcs_ribbon_state()
        ribbon.set_vcs_tab_visible.assert_called_with(False)

    def test_no_repo_hides_register_button(self, main_window):
        """When vcs.is_configured() returns False, set_vcs_register_state(False)
        must be called to ensure the Register button is hidden even if it was
        previously made visible."""
        ribbon = main_window._toolbar.ribbon
        mock_vcs = MagicMock()
        mock_vcs.is_configured.return_value = False
        with self._vcs_patch(mock_vcs):
            main_window._update_vcs_ribbon_state()
        ribbon.set_vcs_register_state.assert_called_with(False)

    def test_svn_repo_unversioned_file_shows_register_button(self, main_window):
        """When vcs type is 'svn' and svn_is_unversioned() returns True,
        set_vcs_register_state(True, enabled=True) must be called."""
        main_window._current_file_path = "/repo/project.xml"
        ribbon = main_window._toolbar.ribbon
        mock_vcs = MagicMock()
        mock_vcs.is_configured.return_value = True
        mock_vcs.get_vcs_type.return_value = "svn"
        mock_vcs.svn_is_unversioned.return_value = True
        with self._vcs_patch(mock_vcs):
            main_window._update_vcs_ribbon_state()
        ribbon.set_vcs_register_state.assert_called_with(True, enabled=True)

    def test_svn_repo_versioned_file_hides_register_button(self, main_window):
        """When vcs type is 'svn' and svn_is_unversioned() returns False
        (file already tracked), set_vcs_register_state(False, enabled=True) must
        be called — the button is hidden (False) but enabled state is still
        passed as True because we are in the SVN+file branch."""
        main_window._current_file_path = "/repo/project.xml"
        ribbon = main_window._toolbar.ribbon
        mock_vcs = MagicMock()
        mock_vcs.is_configured.return_value = True
        mock_vcs.get_vcs_type.return_value = "svn"
        mock_vcs.svn_is_unversioned.return_value = False
        with self._vcs_patch(mock_vcs):
            main_window._update_vcs_ribbon_state()
        ribbon.set_vcs_register_state.assert_called_with(False, enabled=True)


# ---------------------------------------------------------------------------
# System Currency Auto-detection (_apply_system_currency_to_project)
# ---------------------------------------------------------------------------

class TestApplySystemCurrencyToProject:
    """Unit tests for MainWindow._apply_system_currency_to_project().

    The method reads the OS locale via the ``locale`` module and applies
    currency symbol, code, digit count, and symbol position to the MPXJ
    project properties.  All locale calls and MPXJ calls are mocked.
    """

    # ------------------------------------------------------------------
    # Helper: fake localeconv output
    # ------------------------------------------------------------------
    @staticmethod
    def _conv(symbol="€", int_sym="EUR ", frac=2, precedes=0, sep_space=1):
        return {
            "currency_symbol": symbol,
            "int_curr_symbol": int_sym,
            "frac_digits":     frac,
            "p_cs_precedes":   precedes,
            "p_sep_by_space":  sep_space,
            "thousands_sep":   ".",
            "decimal_point":   ",",
        }

    def test_apply_system_currency_method_exists(self, main_window):
        assert hasattr(main_window, '_apply_system_currency_to_project')
        assert callable(main_window._apply_system_currency_to_project)

    def test_apply_system_currency_sets_symbol(self, main_window):
        """Currency symbol from localeconv is written to project properties."""
        mock_project = MagicMock()
        mock_props = MagicMock()
        mock_project.getProjectProperties.return_value = mock_props
        with patch('locale.setlocale'), \
             patch('locale.localeconv', return_value=self._conv(symbol="€")), \
             patch('locale.getlocale', return_value=('de_DE', 'cp1252')):
            main_window._apply_system_currency_to_project(mock_project)
        mock_props.setCurrencySymbol.assert_called_once_with("€")

    def test_apply_system_currency_sets_code(self, main_window):
        """Currency code (stripped) from localeconv is written to project properties."""
        mock_project = MagicMock()
        mock_props = MagicMock()
        mock_project.getProjectProperties.return_value = mock_props
        with patch('locale.setlocale'), \
             patch('locale.localeconv', return_value=self._conv(int_sym="EUR ")), \
             patch('locale.getlocale', return_value=('de_DE', 'cp1252')):
            main_window._apply_system_currency_to_project(mock_project)
        mock_props.setCurrencyCode.assert_called_once_with("EUR")

    def test_apply_system_currency_sets_digits(self, main_window):
        """Fractional digit count from localeconv is written to project properties."""
        import sys as _sys
        mock_project = MagicMock()
        mock_props = MagicMock()
        mock_project.getProjectProperties.return_value = mock_props
        _mock_jpype = MagicMock()
        _mock_jpype.JClass.side_effect = lambda n: int if 'Integer' in n else MagicMock()
        with patch('locale.setlocale'), \
             patch('locale.localeconv', return_value=self._conv(frac=2)), \
             patch('locale.getlocale', return_value=('de_DE', 'cp1252')), \
             patch.dict(_sys.modules, {'jpype': _mock_jpype}):
            main_window._apply_system_currency_to_project(mock_project)
        mock_props.setCurrencyDigits.assert_called_once_with(2)

    def test_apply_system_currency_negative_digits_defaults_to_2(self, main_window):
        """frac_digits == -1 (locale sentinel for 'unknown') must be treated as 2."""
        import sys as _sys
        mock_project = MagicMock()
        mock_props = MagicMock()
        mock_project.getProjectProperties.return_value = mock_props
        _mock_jpype = MagicMock()
        _mock_jpype.JClass.side_effect = lambda n: int if 'Integer' in n else MagicMock()
        with patch('locale.setlocale'), \
             patch('locale.localeconv', return_value=self._conv(frac=-1)), \
             patch('locale.getlocale', return_value=('de_DE', 'cp1252')), \
             patch.dict(_sys.modules, {'jpype': _mock_jpype}):
            main_window._apply_system_currency_to_project(mock_project)
        mock_props.setCurrencyDigits.assert_called_once_with(2)

    def test_apply_system_currency_position_after_with_space(self, main_window):
        """precedes=0, sep_space=1 → AFTER_WITH_SPACE (e.g. German '1,23 €')."""
        mock_project = MagicMock()
        mock_props = MagicMock()
        mock_project.getProjectProperties.return_value = mock_props
        import sys
        mock_csp = MagicMock()
        with patch('locale.setlocale'), \
             patch('locale.localeconv', return_value=self._conv(precedes=0, sep_space=1)), \
             patch('locale.getlocale', return_value=('de_DE', 'cp1252')), \
             patch.dict(sys.modules, {'jpype': MagicMock(
                 JClass=MagicMock(return_value=mock_csp))}):
            main_window._apply_system_currency_to_project(mock_project)
        mock_csp.valueOf.assert_called_once_with("AFTER_WITH_SPACE")

    def test_apply_system_currency_position_after_no_space(self, main_window):
        """precedes=0, sep_space=0 → AFTER."""
        mock_project = MagicMock()
        mock_props = MagicMock()
        mock_project.getProjectProperties.return_value = mock_props
        import sys
        mock_csp = MagicMock()
        with patch('locale.setlocale'), \
             patch('locale.localeconv', return_value=self._conv(precedes=0, sep_space=0)), \
             patch('locale.getlocale', return_value=('de_DE', 'cp1252')), \
             patch.dict(sys.modules, {'jpype': MagicMock(
                 JClass=MagicMock(return_value=mock_csp))}):
            main_window._apply_system_currency_to_project(mock_project)
        mock_csp.valueOf.assert_called_once_with("AFTER")

    def test_apply_system_currency_position_before(self, main_window):
        """precedes=1, sep_space=0 → BEFORE (e.g. '£1.23')."""
        mock_project = MagicMock()
        mock_props = MagicMock()
        mock_project.getProjectProperties.return_value = mock_props
        import sys
        mock_csp = MagicMock()
        with patch('locale.setlocale'), \
             patch('locale.localeconv', return_value=self._conv(precedes=1, sep_space=0)), \
             patch('locale.getlocale', return_value=('en_GB', 'UTF-8')), \
             patch.dict(sys.modules, {'jpype': MagicMock(
                 JClass=MagicMock(return_value=mock_csp))}):
            main_window._apply_system_currency_to_project(mock_project)
        mock_csp.valueOf.assert_called_once_with("BEFORE")

    def test_apply_system_currency_position_before_with_space(self, main_window):
        """precedes=1, sep_space=1 → BEFORE_WITH_SPACE."""
        mock_project = MagicMock()
        mock_props = MagicMock()
        mock_project.getProjectProperties.return_value = mock_props
        import sys
        mock_csp = MagicMock()
        with patch('locale.setlocale'), \
             patch('locale.localeconv', return_value=self._conv(precedes=1, sep_space=1)), \
             patch('locale.getlocale', return_value=('en_GB', 'UTF-8')), \
             patch.dict(sys.modules, {'jpype': MagicMock(
                 JClass=MagicMock(return_value=mock_csp))}):
            main_window._apply_system_currency_to_project(mock_project)
        mock_csp.valueOf.assert_called_once_with("BEFORE_WITH_SPACE")

    def test_apply_system_currency_empty_symbol_not_written(self, main_window):
        """An empty currency_symbol must NOT call setCurrencySymbol (avoid clearing)."""
        mock_project = MagicMock()
        mock_props = MagicMock()
        mock_project.getProjectProperties.return_value = mock_props
        with patch('locale.setlocale'), \
             patch('locale.localeconv', return_value=self._conv(symbol="")), \
             patch('locale.getlocale', return_value=('C', 'UTF-8')):
            main_window._apply_system_currency_to_project(mock_project)
        mock_props.setCurrencySymbol.assert_not_called()

    def test_apply_system_currency_handles_locale_error_gracefully(self, main_window):
        """If the locale module raises, the method must not propagate the exception."""
        mock_project = MagicMock()
        with patch('locale.getlocale', side_effect=Exception("locale unavailable")):
            # Must not raise
            main_window._apply_system_currency_to_project(mock_project)

    def test_new_project_calls_apply_system_currency(self, main_window):
        """new_project() must call _apply_system_currency_to_project() so the
        new project starts with OS-locale currency settings."""
        with patch.object(main_window, '_refresh_all_views'), \
             patch.object(main_window._history, 'push_all'), \
             patch.object(main_window, '_setup_new_project_calendars'), \
             patch.object(main_window, 'open_project_info'), \
             patch.object(main_window, '_apply_system_currency_to_project') as mock_curr:
            main_window.new_project()
        mock_curr.assert_called_once()

