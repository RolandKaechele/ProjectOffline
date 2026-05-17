# toolbar.py - Ribbon-style toolbar wrapper for the Project Offline app
#
# Wraps the ProjectRibbon widget in a QToolBar so that it can be added to
# the main window with addToolBar().  All public methods delegate to the
# embedded ribbon so that ui.py does not need to know the implementation.

from PyQt5.QtWidgets import QToolBar, QWidget  # type: ignore
from PyQt5.QtCore import pyqtSignal            # type: ignore
from ribbon import ProjectRibbon               # type: ignore


class ProjectToolBar(QToolBar):
    def __init__(self, parent, logic, file_handler):
        super().__init__("Main Toolbar", parent)
        self.logic = logic
        self.file_handler = file_handler
        self.setMovable(False)
        self.setFloatable(False)

        self._ribbon = ProjectRibbon(self)
        # QToolBar needs a widget action to embed an arbitrary widget
        self.addWidget(self._ribbon)

    # ------------------------------------------------------------------
    # Public API – delegated to the ribbon
    # ------------------------------------------------------------------

    @property
    def ribbon(self) -> ProjectRibbon:
        return self._ribbon

    def set_save_enabled(self, enabled: bool):
        self._ribbon.set_save_enabled(enabled)

    def set_delete_enabled(self, enabled: bool):
        self._ribbon.set_delete_enabled(enabled)

    def update_actions(self, add_label: str, del_label: str,
                       enabled: bool = True, zoom_enabled: bool = True):
        self._ribbon.update_actions(add_label, del_label, enabled, zoom_enabled)
