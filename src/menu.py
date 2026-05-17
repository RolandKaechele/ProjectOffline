# menu.py - Menu bar for the Project Offline app
#
# Menus: File | Task | Resource | Report | View | Options | Project
# Structured to mirror the MS Project ribbon tab layout.
# The Task menu is context-sensitive: labels and availability update via
# update_edit_actions(), called by ui._on_tab_changed().

import os
from PyQt5.QtWidgets import QAction, QMenuBar  # type: ignore
from PyQt5.QtGui import QKeySequence           # type: ignore

MAX_RECENT = 5


class ProjectMenuBar(QMenuBar):
    def __init__(self, parent, logic, file_handler):
        super().__init__(parent)
        self.logic = logic
        self.file_handler = file_handler
        self._create_menus()

    def _create_menus(self):
        def act(label, tip, slot, shortcut=None):
            a = QAction(label, self)
            if shortcut:
                a.setShortcut(shortcut)
            a.setStatusTip(tip)
            a.triggered.connect(slot)
            return a

        # ---- File ----
        file_menu = self.addMenu("&File")
        file_menu.addAction(act("&New",      "Create a new project",    self.parent().new_project,  QKeySequence.New))
        file_menu.addAction(act("&Open…",    "Open a project file",     self.parent().open_project, QKeySequence.Open))
        self._save_act = QAction("&Save", self)
        self._save_act.setShortcut(QKeySequence.Save)
        self._save_act.setStatusTip("Save the project file")
        self._save_act.triggered.connect(self.parent().save_project)
        self._save_act.setEnabled(False)
        file_menu.addAction(self._save_act)
        self._save_as_act = QAction("Save &As…", self)
        self._save_as_act.setShortcut(QKeySequence.SaveAs)
        self._save_as_act.setStatusTip("Save the project to a new file")
        self._save_as_act.triggered.connect(self.parent().save_project_as)
        file_menu.addAction(self._save_as_act)
        self._close_act = QAction("&Close", self)
        self._close_act.setStatusTip("Close the current project")
        self._close_act.triggered.connect(self.parent().close_project)
        self._close_act.setEnabled(False)
        file_menu.addAction(self._close_act)
        file_menu.addSeparator()
        # Recent Files submenu
        self._recent_menu = file_menu.addMenu("&Recent Files")
        self._recent_menu.setEnabled(False)
        file_menu.addSeparator()
        import_sub = file_menu.addMenu("&Import")
        import_sub.addAction(act(
            "&PlantUML Gantt…",
            "Import a PlantUML @startgantt file as a new project",
            self.parent().import_plantuml,
        ))
        export_sub = file_menu.addMenu("E&xport")
        export_sub.addAction(act(
            "&Complete Gantt Chart as SVG…",
            "Export the full Gantt chart to an SVG file",
            self.parent().export_gantt_svg,
        ))
        export_sub.addAction(act(
            "&Resource Gantt Charts as SVG…",
            "Export one SVG Gantt chart per work resource to a folder",
            self.parent().export_resource_gantt_svg,
        ))
        export_sub.addAction(act(
            "Complete Gantt Chart as &PlantUML…",
            "Export the full Gantt chart as a PlantUML @startgantt file",
            self.parent().export_gantt_plantuml,
        ))
        file_menu.addSeparator()
        file_menu.addAction(act("E&xit", "Exit the application", self.parent().close, "Alt+F4"))

        # ---- Options ----
        format_menu = self.addMenu("&Options")
        self._res_units_act = QAction("Show Resource &Units on Bars", self)
        self._res_units_act.setCheckable(True)
        self._res_units_act.setStatusTip("Toggle resource unit percentage labels on Gantt bars")
        self._res_units_act.triggered.connect(self.parent().toggle_resource_units)
        format_menu.addAction(self._res_units_act)

        self._show_sundays_act = QAction("Show &Sundays", self)
        self._show_sundays_act.setCheckable(True)
        self._show_sundays_act.setChecked(True)
        self._show_sundays_act.setStatusTip("Show or hide Sunday columns in the Gantt chart")
        self._show_sundays_act.triggered.connect(self.parent().toggle_show_sundays)
        format_menu.addAction(self._show_sundays_act)

        self._show_off_hours_act = QAction("Show &Off-Hours", self)
        self._show_off_hours_act.setCheckable(True)
        self._show_off_hours_act.setChecked(False)
        self._show_off_hours_act.setStatusTip(
            "Show columns before and after working hours in the hourly Resource Usage view"
        )
        self._show_off_hours_act.triggered.connect(self.parent().toggle_show_off_hours)
        format_menu.addAction(self._show_off_hours_act)

        self._zero_float_act = QAction("&Zero Float = Critical", self)
        self._zero_float_act.setCheckable(True)
        self._zero_float_act.setChecked(False)
        self._zero_float_act.setStatusTip("When checked, tasks with exactly zero total float are shown as critical")
        self._zero_float_act.triggered.connect(self.parent().toggle_zero_float_critical)
        format_menu.addAction(self._zero_float_act)

        format_menu.addSeparator()
        self._timeline_act = QAction("Show &Timeline Strip", self)
        self._timeline_act.setCheckable(True)
        self._timeline_act.setChecked(False)
        self._timeline_act.setStatusTip(
            "Show the MS-Project-style timeline strip above the current view"
        )
        self._timeline_act.triggered.connect(self.parent().toggle_timeline)
        format_menu.addAction(self._timeline_act)

        self._show_histogram_act = QAction("Show &Resource Usage Histogram", self)
        self._show_histogram_act.setCheckable(True)
        self._show_histogram_act.setChecked(False)
        self._show_histogram_act.setStatusTip(
            "Show or hide the Resource Usage Histogram strip below the Team Planner"
        )
        self._show_histogram_act.triggered.connect(self.parent().toggle_histogram)
        format_menu.addAction(self._show_histogram_act)

        # ---- Project (last) ----
        project_menu = self.addMenu("&Project")
        project_menu.addAction(act(
            "Project &Information…",
            "View and edit project properties",
            self.parent().open_project_info,
            "Alt+F11",
        ))
        project_menu.addSeparator()
        project_menu.addAction(act(
            "&KeePass Configuration…",
            "Configure the KeePass database used for credential management",
            self.parent().open_keepass_settings,
        ))
        # Jira submenu
        jira_menu = project_menu.addMenu("&Jira")
        jira_menu.addAction(act(
            "Jira Sync &Configuration…",
            "Configure Jira synchronization settings",
            self.parent().open_jira_config,
        ))
        jira_menu.addAction(act(
            "Jira &Servers…",
            "Manage Jira server connections and credentials",
            self.parent().open_jira_settings,
        ))
        project_menu.addSeparator()
        project_menu.addAction(act(
            "&Critical Path Settings…",
            "Configure critical path threshold and dependency types",
            self.parent().open_cpm_settings,
        ))

    def set_save_enabled(self, enabled: bool):
        self._save_act.setEnabled(enabled)

    def set_close_enabled(self, enabled: bool):
        self._close_act.setEnabled(enabled)

    def update_recent_files(self, paths: list):
        """Rebuild the Recent Files submenu from a list of file paths."""
        self._recent_menu.clear()
        if not paths:
            self._recent_menu.setEnabled(False)
            return
        self._recent_menu.setEnabled(True)
        for i, path in enumerate(paths[:MAX_RECENT]):
            label = f"&{i + 1}  {os.path.basename(path)}"
            act = QAction(label, self)
            act.setStatusTip(path)
            act.setData(path)
            act.triggered.connect(lambda checked, p=path: self.parent().open_project_file(p))
            self._recent_menu.addAction(act)
        self._recent_menu.addSeparator()
        clear_act = QAction("&Clear Recent Files", self)
        clear_act.triggered.connect(self.parent().clear_recent_files)
        self._recent_menu.addAction(clear_act)

    def set_resource_units_checked(self, checked: bool):
        self._res_units_act.setChecked(checked)

    def set_show_sundays_checked(self, checked: bool):
        self._show_sundays_act.setChecked(checked)

    def set_show_off_hours_checked(self, checked: bool):
        self._show_off_hours_act.setChecked(checked)

    def set_zero_float_critical_checked(self, checked: bool):
        self._zero_float_act.setChecked(checked)

    def set_timeline_checked(self, checked: bool):
        self._timeline_act.setChecked(checked)

    def set_show_histogram_checked(self, checked: bool):
        self._show_histogram_act.setChecked(checked)

    def update_edit_actions(self, add_label, del_label, enabled=True):
        pass  # Insert/Delete Task are ribbon-only

    def set_delete_enabled(self, enabled: bool):
        pass  # Insert/Delete Task are ribbon-only
