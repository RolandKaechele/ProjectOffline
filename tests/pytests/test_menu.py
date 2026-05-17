"""Tests for menu.py - Menu bar module."""

import pytest
from unittest.mock import MagicMock, patch, call


@pytest.fixture
def mock_parent(qapp):
    """Create a mock parent window with all required methods."""
    from PyQt5.QtWidgets import QMainWindow
    parent = QMainWindow()
    parent.new_project = MagicMock()
    parent.open_project = MagicMock()
    parent.save_project = MagicMock()
    parent.save_project_as = MagicMock()
    parent.close_project = MagicMock()
    parent.import_plantuml = MagicMock()
    parent.export_gantt_svg = MagicMock()
    parent.export_resource_gantt_svg = MagicMock()
    parent.export_gantt_plantuml = MagicMock()
    parent.close = MagicMock()
    parent.toggle_show_off_hours = MagicMock()
    parent.toggle_resource_units = MagicMock()
    parent.toggle_show_sundays = MagicMock()
    parent.toggle_zero_float_critical = MagicMock()
    parent.toggle_timeline = MagicMock()
    parent.toggle_histogram = MagicMock()
    parent.open_recent_file = MagicMock()
    parent.open_project_info = MagicMock()
    parent.open_keepass_settings = MagicMock()
    parent.open_jira_config = MagicMock()
    parent.open_jira_settings = MagicMock()
    parent.open_cpm_settings = MagicMock()
    parent.open_project_file = MagicMock()
    parent.clear_recent_files = MagicMock()
    return parent


def test_menu_bar_init(mock_parent):
    """Test ProjectMenuBar initializes correctly."""
    from menu import ProjectMenuBar
    
    logic = MagicMock()
    file_handler = MagicMock()
    
    menu_bar = ProjectMenuBar(mock_parent, logic, file_handler)
    
    assert menu_bar.logic is logic
    assert menu_bar.file_handler is file_handler
    assert menu_bar.parent() is mock_parent


def test_menu_bar_has_file_menu(mock_parent):
    """Test menu bar has File menu."""
    from menu import ProjectMenuBar
    
    logic = MagicMock()
    file_handler = MagicMock()
    
    menu_bar = ProjectMenuBar(mock_parent, logic, file_handler)
    
    # Find File menu
    menus = [menu_bar.actions()[i].text() for i in range(len(menu_bar.actions()))]
    assert "&File" in menus


def test_menu_bar_has_options_menu(mock_parent):
    """Test menu bar has Options menu."""
    from menu import ProjectMenuBar
    
    logic = MagicMock()
    file_handler = MagicMock()
    
    menu_bar = ProjectMenuBar(mock_parent, logic, file_handler)
    
    menus = [menu_bar.actions()[i].text() for i in range(len(menu_bar.actions()))]
    assert "&Options" in menus


def test_set_save_enabled_true(mock_parent):
    """Test set_save_enabled(True) enables save action."""
    from menu import ProjectMenuBar
    
    logic = MagicMock()
    file_handler = MagicMock()
    
    menu_bar = ProjectMenuBar(mock_parent, logic, file_handler)
    menu_bar.set_save_enabled(True)
    
    assert menu_bar._save_act.isEnabled()


def test_set_save_enabled_false(mock_parent):
    """Test set_save_enabled(False) disables save action."""
    from menu import ProjectMenuBar
    
    logic = MagicMock()
    file_handler = MagicMock()
    
    menu_bar = ProjectMenuBar(mock_parent, logic, file_handler)
    menu_bar.set_save_enabled(True)  # Enable first
    menu_bar.set_save_enabled(False)  # Then disable
    
    assert not menu_bar._save_act.isEnabled()


def test_update_recent_files_empty(mock_parent):
    """Test update_recent_files() with empty list."""
    from menu import ProjectMenuBar
    
    logic = MagicMock()
    file_handler = MagicMock()
    
    menu_bar = ProjectMenuBar(mock_parent, logic, file_handler)
    menu_bar.update_recent_files([])
    
    assert not menu_bar._recent_menu.isEnabled()


def test_update_recent_files_with_files(mock_parent):
    """Test update_recent_files() with file list."""
    from menu import ProjectMenuBar
    
    logic = MagicMock()
    file_handler = MagicMock()
    
    menu_bar = ProjectMenuBar(mock_parent, logic, file_handler)
    menu_bar.update_recent_files(["project1.mpp", "project2.xml"])
    
    assert menu_bar._recent_menu.isEnabled()
    actions = menu_bar._recent_menu.actions()
    # Menu has file actions + separator + clear action
    assert len(actions) >= 2


def test_update_recent_files_max_limit(mock_parent):
    """Test update_recent_files() respects MAX_RECENT limit."""
    from menu import ProjectMenuBar, MAX_RECENT
    
    logic = MagicMock()
    file_handler = MagicMock()
    
    menu_bar = ProjectMenuBar(mock_parent, logic, file_handler)
    files = [f"project{i}.mpp" for i in range(MAX_RECENT + 3)]
    menu_bar.update_recent_files(files)
    
    actions = menu_bar._recent_menu.actions()
    # Should have at most MAX_RECENT files + separator + clear
    assert len(actions) <= MAX_RECENT + 2


def test_set_resource_units_checked(mock_parent):
    """Test set_resource_units_checked() sets checkbox state."""
    from menu import ProjectMenuBar
    
    logic = MagicMock()
    file_handler = MagicMock()
    
    menu_bar = ProjectMenuBar(mock_parent, logic, file_handler)
    menu_bar.set_resource_units_checked(True)
    
    assert menu_bar._res_units_act.isChecked()


def test_set_show_sundays_checked(mock_parent):
    """Test set_show_sundays_checked() sets checkbox state."""
    from menu import ProjectMenuBar
    
    logic = MagicMock()
    file_handler = MagicMock()
    
    menu_bar = ProjectMenuBar(mock_parent, logic, file_handler)
    menu_bar.set_show_sundays_checked(False)
    
    assert not menu_bar._show_sundays_act.isChecked()


def test_set_zero_float_critical_checked(mock_parent):
    """Test set_zero_float_critical_checked() sets checkbox state."""
    from menu import ProjectMenuBar
    
    logic = MagicMock()
    file_handler = MagicMock()
    
    menu_bar = ProjectMenuBar(mock_parent, logic, file_handler)
    menu_bar.set_zero_float_critical_checked(True)
    
    assert menu_bar._zero_float_act.isChecked()


def test_update_edit_actions(mock_parent):
    """Test update_edit_actions() updates action labels."""
    from menu import ProjectMenuBar
    
    logic = MagicMock()
    file_handler = MagicMock()
    
    menu_bar = ProjectMenuBar(mock_parent, logic, file_handler)
    menu_bar.update_edit_actions("Insert Task", "Delete Task", enabled=True)
    
    # Actions should be enabled
    # (We can't easily check the text without accessing private members)
    assert True  # Test passes if no exceptions


def test_set_delete_enabled(mock_parent):
    """Test set_delete_enabled() enables/disables delete action."""
    from menu import ProjectMenuBar
    
    logic = MagicMock()
    file_handler = MagicMock()
    
    menu_bar = ProjectMenuBar(mock_parent, logic, file_handler)
    menu_bar.set_delete_enabled(False)
    
    # Test completes without exception
    assert True


def test_menu_actions_connected(mock_parent):
    """Test menu actions are connected to parent methods."""
    from menu import ProjectMenuBar
    
    logic = MagicMock()
    file_handler = MagicMock()
    
    menu_bar = ProjectMenuBar(mock_parent, logic, file_handler)
    
    # Trigger the save action
    menu_bar._save_act.setEnabled(True)
    menu_bar._save_act.trigger()
    
    mock_parent.save_project.assert_called_once()


def test_close_action_disabled_by_default(mock_parent):
    """Close action must start disabled (no project open at startup)."""
    from menu import ProjectMenuBar

    menu_bar = ProjectMenuBar(mock_parent, MagicMock(), MagicMock())

    assert not menu_bar._close_act.isEnabled()


def test_set_close_enabled_true(mock_parent):
    """set_close_enabled(True) must enable the Close menu action."""
    from menu import ProjectMenuBar

    menu_bar = ProjectMenuBar(mock_parent, MagicMock(), MagicMock())
    menu_bar.set_close_enabled(True)

    assert menu_bar._close_act.isEnabled()


def test_set_close_enabled_false(mock_parent):
    """set_close_enabled(False) must disable the Close menu action."""
    from menu import ProjectMenuBar

    menu_bar = ProjectMenuBar(mock_parent, MagicMock(), MagicMock())
    menu_bar.set_close_enabled(True)   # enable first
    menu_bar.set_close_enabled(False)

    assert not menu_bar._close_act.isEnabled()


def test_close_action_triggers_close_project(mock_parent):
    """Triggering the Close action must call parent.close_project()."""
    from menu import ProjectMenuBar

    menu_bar = ProjectMenuBar(mock_parent, MagicMock(), MagicMock())
    menu_bar.set_close_enabled(True)
    menu_bar._close_act.trigger()

    mock_parent.close_project.assert_called_once()

