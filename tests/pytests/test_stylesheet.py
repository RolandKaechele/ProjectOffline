"""Tests for stylesheet.py - QSS stylesheet module."""

import pytest


def test_stylesheet_exists():
    """Test MS_PROJECT_STYLE constant exists."""
    from stylesheet import MS_PROJECT_STYLE
    assert MS_PROJECT_STYLE is not None
    assert isinstance(MS_PROJECT_STYLE, str)
    assert len(MS_PROJECT_STYLE) > 0


def test_stylesheet_contains_qmainwindow():
    """Test stylesheet contains QMainWindow styling."""
    from stylesheet import MS_PROJECT_STYLE
    assert "QMainWindow" in MS_PROJECT_STYLE


def test_stylesheet_contains_qmenubar():
    """Test stylesheet contains QMenuBar styling."""
    from stylesheet import MS_PROJECT_STYLE
    assert "QMenuBar" in MS_PROJECT_STYLE


def test_stylesheet_valid_css_syntax():
    """Test stylesheet has basic CSS-like syntax."""
    from stylesheet import MS_PROJECT_STYLE
    # Should contain CSS-like structure with braces
    assert "{" in MS_PROJECT_STYLE
    assert "}" in MS_PROJECT_STYLE
    assert ":" in MS_PROJECT_STYLE
