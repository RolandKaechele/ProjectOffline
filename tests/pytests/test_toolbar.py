"""Tests for toolbar.py - Ribbon-style toolbar wrapper."""

import pytest
from unittest.mock import MagicMock, patch


def test_toolbar_init(qapp):
    """Test ProjectToolBar initializes correctly."""
    with patch('toolbar.ProjectRibbon') as mock_ribbon:
        from PyQt5.QtWidgets import QWidget
        mock_ribbon_instance = QWidget()  # Real QWidget to avoid type error
        mock_ribbon_instance.set_save_enabled = MagicMock()
        mock_ribbon_instance.set_delete_enabled = MagicMock()
        mock_ribbon_instance.update_actions = MagicMock()
        mock_ribbon.return_value = mock_ribbon_instance
        
        from toolbar import ProjectToolBar
        from PyQt5.QtWidgets import QMainWindow
        
        parent = QMainWindow()
        logic = MagicMock()
        file_handler = MagicMock()
        
        toolbar = ProjectToolBar(parent, logic, file_handler)
        
        assert toolbar.logic is logic
        assert toolbar.file_handler is file_handler
        assert not toolbar.isMovable()
        assert not toolbar.isFloatable()
        mock_ribbon.assert_called_once_with(toolbar)


def test_toolbar_ribbon_property(qapp):
    """Test ribbon property returns the embedded ribbon."""
    with patch('toolbar.ProjectRibbon') as mock_ribbon:
        from PyQt5.QtWidgets import QWidget
        mock_ribbon_instance = QWidget()
        mock_ribbon.return_value = mock_ribbon_instance
        
        from toolbar import ProjectToolBar
        from PyQt5.QtWidgets import QMainWindow
        
        parent = QMainWindow()
        logic = MagicMock()
        file_handler = MagicMock()
        
        toolbar = ProjectToolBar(parent, logic, file_handler)
        
        assert toolbar.ribbon is mock_ribbon_instance


def test_toolbar_set_save_enabled(qapp):
    """Test set_save_enabled() delegates to ribbon."""
    with patch('toolbar.ProjectRibbon') as mock_ribbon:
        from PyQt5.QtWidgets import QWidget
        mock_ribbon_instance = QWidget()
        mock_ribbon_instance.set_save_enabled = MagicMock()
        mock_ribbon.return_value = mock_ribbon_instance
        
        from toolbar import ProjectToolBar
        from PyQt5.QtWidgets import QMainWindow
        
        parent = QMainWindow()
        logic = MagicMock()
        file_handler = MagicMock()
        
        toolbar = ProjectToolBar(parent, logic, file_handler)
        toolbar.set_save_enabled(True)
        
        mock_ribbon_instance.set_save_enabled.assert_called_once_with(True)


def test_toolbar_set_delete_enabled(qapp):
    """Test set_delete_enabled() delegates to ribbon."""
    with patch('toolbar.ProjectRibbon') as mock_ribbon:
        from PyQt5.QtWidgets import QWidget
        mock_ribbon_instance = QWidget()
        mock_ribbon_instance.set_delete_enabled = MagicMock()
        mock_ribbon.return_value = mock_ribbon_instance
        
        from toolbar import ProjectToolBar
        from PyQt5.QtWidgets import QMainWindow
        
        parent = QMainWindow()
        logic = MagicMock()
        file_handler = MagicMock()
        
        toolbar = ProjectToolBar(parent, logic, file_handler)
        toolbar.set_delete_enabled(False)
        
        mock_ribbon_instance.set_delete_enabled.assert_called_once_with(False)


def test_toolbar_update_actions(qapp):
    """Test update_actions() delegates to ribbon."""
    with patch('toolbar.ProjectRibbon') as mock_ribbon:
        from PyQt5.QtWidgets import QWidget
        mock_ribbon_instance = QWidget()
        mock_ribbon_instance.update_actions = MagicMock()
        mock_ribbon.return_value = mock_ribbon_instance
        
        from toolbar import ProjectToolBar
        from PyQt5.QtWidgets import QMainWindow
        
        parent = QMainWindow()
        logic = MagicMock()
        file_handler = MagicMock()
        
        toolbar = ProjectToolBar(parent, logic, file_handler)
        toolbar.update_actions("Add", "Delete", enabled=True, zoom_enabled=False)
        
        # Check call was made with correct arguments (positional or keyword)
        mock_ribbon_instance.update_actions.assert_called_once()
        call_args = mock_ribbon_instance.update_actions.call_args
        assert call_args[0] == ("Add", "Delete", True, False) or \
               (call_args[0] == ("Add", "Delete") and 
                call_args[1] == {"enabled": True, "zoom_enabled": False})


def test_toolbar_title(qapp):
    """Test toolbar has correct title."""
    with patch('toolbar.ProjectRibbon') as mock_ribbon:
        from PyQt5.QtWidgets import QWidget
        mock_ribbon.return_value = QWidget()
        
        from toolbar import ProjectToolBar
        from PyQt5.QtWidgets import QMainWindow
        
        parent = QMainWindow()
        logic = MagicMock()
        file_handler = MagicMock()
        
        toolbar = ProjectToolBar(parent, logic, file_handler)
        
        assert toolbar.windowTitle() == "Main Toolbar"
