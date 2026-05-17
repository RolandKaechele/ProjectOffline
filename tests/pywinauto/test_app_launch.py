"""
test_app_launch.py — Smoke tests: application starts and the main window is present.

These are the most fundamental system tests.  If any of these fail, all
other system tests are expected to fail as well — investigate the startup
issue first.

Markers
-------
All tests in this module carry the ``systemtest`` marker so they can be
included or excluded via ``pytest -m systemtest`` / ``pytest -m "not systemtest"``.
"""

import pytest


@pytest.mark.systemtest
class TestAppLaunch:
    """Verify that the application starts and the main window is visible."""

    def test_main_window_is_visible(self, main_window):
        """The main window must be visible after launch."""
        assert main_window.is_visible(), "Main window is not visible after launch."

    def test_main_window_title(self, main_window):
        """The main window title must be 'Project Offline'."""
        assert main_window.window_text() == "Project Offline"

    def test_main_window_not_minimized(self, main_window):
        """The main window must not be minimised on startup."""
        assert not main_window.is_minimized(), "Main window is minimised on startup."

    def test_main_window_enabled(self, main_window):
        """The main window must be enabled (not blocked by a modal dialog)."""
        assert main_window.is_enabled(), (
            "Main window is disabled — a modal dialog may have appeared at startup."
        )


@pytest.mark.systemtest
class TestMenuBar:
    """Verify that the main menu bar is present and accessible."""

    def test_menu_bar_exists(self, main_window):
        """A MenuBar control must be a direct child of the main window."""
        control_types = [
            c.element_info.control_type for c in main_window.children()
        ]
        assert "MenuBar" in control_types, (
            f"No MenuBar found among main window children: {control_types}"
        )

    def test_file_menu_accessible(self, main_window):
        """The 'File' top-level menu item must be reachable via pywinauto."""
        # child_window raises if not found; the assertion is implicit.
        file_menu = main_window.child_window(title="File", control_type="MenuItem")
        assert file_menu.exists(timeout=5), "File menu item not found."
