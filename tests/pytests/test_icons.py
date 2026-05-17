"""Tests for icons.py - Icon generation module."""

import pytest
from PyQt5.QtGui import QIcon


def test_gantt_chart_icon(qapp):
    """Test gantt_chart() returns a QIcon."""
    from icons import gantt_chart
    icon = gantt_chart()
    assert isinstance(icon, QIcon)
    assert not icon.isNull()


def test_resource_sheet_icon(qapp):
    """Test resource_sheet() returns a QIcon."""
    from icons import resource_sheet
    icon = resource_sheet()
    assert isinstance(icon, QIcon)
    assert not icon.isNull()


def test_paste_icon(qapp):
    """Test paste() returns a QIcon."""
    from icons import paste
    icon = paste()
    assert isinstance(icon, QIcon)
    assert not icon.isNull()


def test_cut_icon(qapp):
    """Test cut() returns a QIcon."""
    from icons import cut
    icon = cut()
    assert isinstance(icon, QIcon)
    assert not icon.isNull()


def test_copy_icon(qapp):
    """Test copy() returns a QIcon."""
    from icons import copy
    icon = copy()
    assert isinstance(icon, QIcon)
    assert not icon.isNull()


def test_insert_task_icon(qapp):
    """Test insert_task() returns a QIcon."""
    from icons import insert_task
    icon = insert_task()
    assert isinstance(icon, QIcon)
    assert not icon.isNull()


def test_delete_task_icon(qapp):
    """Test delete_task() returns a QIcon."""
    from icons import delete_task
    icon = delete_task()
    assert isinstance(icon, QIcon)
    assert not icon.isNull()


def test_add_resource_icon(qapp):
    """Test add_resource() returns a QIcon."""
    from icons import add_resource
    icon = add_resource()
    assert isinstance(icon, QIcon)
    assert not icon.isNull()


def test_delete_resource_icon(qapp):
    """Test delete_resource() returns a QIcon."""
    from icons import delete_resource
    icon = delete_resource()
    assert isinstance(icon, QIcon)
    assert not icon.isNull()


def test_export_svg_icon(qapp):
    """Test export_svg() returns a QIcon."""
    from icons import export_svg
    icon = export_svg()
    assert isinstance(icon, QIcon)
    assert not icon.isNull()


def test_export_plantuml_icon(qapp):
    """Test export_plantuml() returns a QIcon."""
    from icons import export_plantuml
    icon = export_plantuml()
    assert isinstance(icon, QIcon)
    assert not icon.isNull()


def test_dependencies_icon(qapp):
    """Test dependencies() returns a QIcon."""
    from icons import dependencies
    icon = dependencies()
    assert isinstance(icon, QIcon)
    assert not icon.isNull()


def test_baseline_icon(qapp):
    """Test baseline() returns a QIcon."""
    from icons import baseline
    icon = baseline()
    assert isinstance(icon, QIcon)
    assert not icon.isNull()


def test_team_planner_icon(qapp):
    """Test team_planner() returns a QIcon."""
    from icons import team_planner
    icon = team_planner()
    assert isinstance(icon, QIcon)
    assert not icon.isNull()


def test_sync_calendar_icon(qapp):
    """Test sync_calendar() returns a QIcon."""
    from icons import sync_calendar
    icon = sync_calendar()
    assert isinstance(icon, QIcon)
    assert not icon.isNull()


def test_confluence_settings_icon(qapp):
    """Test confluence_settings() returns a QIcon."""
    from icons import confluence_settings
    icon = confluence_settings()
    assert isinstance(icon, QIcon)
    assert not icon.isNull()


def test_icon_from_glyph_default(qapp):
    """Test _icon_from_glyph() with default parameters."""
    from icons import _icon_from_glyph
    icon = _icon_from_glyph("✓")
    assert isinstance(icon, QIcon)
    assert not icon.isNull()


def test_icon_from_glyph_custom_color(qapp):
    """Test _icon_from_glyph() with custom color."""
    from icons import _icon_from_glyph
    icon = _icon_from_glyph("★", color="#FF0000")
    assert isinstance(icon, QIcon)
    assert not icon.isNull()


def test_icon_from_glyph_custom_size(qapp):
    """Test _icon_from_glyph() with custom size."""
    from icons import _icon_from_glyph
    icon = _icon_from_glyph("★", size=48)
    assert isinstance(icon, QIcon)
    assert not icon.isNull()


def test_std_icon(qapp):
    """Test _std() returns standard icon."""
    from PyQt5.QtWidgets import QStyle
    from icons import _std
    icon = _std(QStyle.SP_DialogOkButton)
    assert isinstance(icon, QIcon)
    assert not icon.isNull()
