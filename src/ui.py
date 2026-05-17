# ui.py - Main window for the Qt5 Project Offline app
#
# Layout:
#   - Blue menu bar and toolbar
#   - Gantt Chart tab: left task grid + right gantt chart (splitter)
#   - Additional tabs: Resources, Dependencies, Baseline
#   - Blue status bar with live task/resource counts
#   - Inline task creation and deletion via toolbar, menu, context menu, and keyboard

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'views'))

from PyQt5.QtWidgets import (  # type: ignore
    QMainWindow, QFileDialog, QMessageBox, QTabWidget, QSplitter, QLabel,
    QAbstractItemView, QSlider, QToolButton, QWidget, QHBoxLayout, QVBoxLayout,
    QSpinBox,
)
from PyQt5.QtCore import Qt, QSettings, QObject, QEvent, QDate  # type: ignore
from PyQt5.QtGui import QKeySequence  # type: ignore

from task_view import TaskView # type: ignore
from gantt_view import GanttView, _to_qdate, _add_working_days, _snap_to_workday, DAY_WIDTH_DEF, DAY_WIDTH_MIN, DAY_WIDTH_MAX  # type: ignore
from resource_view import ResourceView # type: ignore
from dependency_view import DependencyView # type: ignore
from baseline_view import BaselineView # type: ignore
from team_planner_view import TeamPlannerView # type: ignore
from resource_usage_histogram_view import ResourceUsageHistogramView  # type: ignore
from task_sheet_view import TaskSheetView # type: ignore
from resource_usage_graph_view import ResourceUsageGraphView # type: ignore
from timeline_view import TimelineView  # type: ignore
from cpm_results_view import CpmResultsView  # type: ignore
from history_manager import HistoryManager
from menu import ProjectMenuBar
from toolbar import ProjectToolBar
from stylesheet import MS_PROJECT_STYLE
from settings_manager import SettingsManager
from app_tabs import (  # type: ignore
    TAB_GANTT, TAB_RESOURCES, TAB_DEPENDENCIES, TAB_BASELINE,
    TAB_TEAM_PLANNER, TAB_TASK_SHEET, TAB_RESOURCE_USAGE, TAB_TIMELINE,
    TAB_CPM,
    RIBBON_TASK, RIBBON_RESOURCE, RIBBON_REPORT, RIBBON_BASELINE, RIBBON_VCS,
)
from progress_worker import WorkerThread, run_with_progress, run_indeterminate, record_timing  # type: ignore


# ---------------------------------------------------------------------------
# Background worker for Jira → Project sync
# ---------------------------------------------------------------------------
import threading as _threading
from PyQt5.QtCore import pyqtSignal as _pyqtSignal  # type: ignore


class _JiraSyncWorker(WorkerThread):
    """Run jira_sync.run_sync() in a background thread.

    Interactive callbacks (relink / conflict / orphan) are dispatched to the
    main thread via signals + a threading.Event rendezvous so the worker
    blocks until the user responds.
    """
    _need_relink   = _pyqtSignal(str, str, str)  # issue_key, stored_id, incoming_id
    _need_conflict = _pyqtSignal(str, str)         # issue_key, task_name
    _need_orphan   = _pyqtSignal(str, str)         # jira_key,  task_name

    def __init__(self, project, server: dict, jira_client, sidecar_path: str,
                 force_incremental: bool = False, force_full_resync: bool = False):
        super().__init__()
        self._project      = project
        self._server       = server
        self._jira_client  = jira_client
        self._sidecar_path = sidecar_path
        self._force_incremental  = force_incremental
        self._force_full_resync  = force_full_resync
        self._event        = _threading.Event()
        self._response     = None
        self.result: dict  = {}

    def _set_response(self, r):
        self._response = r
        self._event.set()

    def _relink_cb(self, issue_key: str, stored_id: str, incoming_id: str) -> str:
        if self.cancelled:
            return "skip"
        self._response = None
        self._event.clear()
        self._need_relink.emit(issue_key, stored_id, incoming_id)
        self._event.wait(timeout=300)
        return self._response or "skip"

    def _conflict_cb(self, issue_key: str, task_name: str) -> str:
        if self.cancelled:
            return "skip"
        self._response = None
        self._event.clear()
        self._need_conflict.emit(issue_key, task_name)
        self._event.wait(timeout=300)
        return self._response or "skip"

    def _orphan_cb(self, jira_key: str, task_name: str) -> str:
        if self.cancelled:
            return "keep"
        self._response = None
        self._event.clear()
        self._need_orphan.emit(jira_key, task_name)
        self._event.wait(timeout=300)
        return self._response or "keep"

    def run(self):
        class _Cancelled(BaseException):
            pass

        def _progress(pct: int, text: str):
            if self.cancelled:
                raise _Cancelled()
            self.progress.emit(pct, text)

        try:
            from integrations import jira_sync as _jira_sync  # type: ignore
            self.result = _jira_sync.run_sync(
                self._project,
                self._server,
                self._jira_client,
                self._sidecar_path,
                relink_callback=self._relink_cb,
                conflict_callback=self._conflict_cb,
                orphan_callback=self._orphan_cb,
                progress_callback=_progress,
                force_incremental=self._force_incremental,
                force_full_resync=self._force_full_resync,
            )
            self.finished.emit(True, "")
        except _Cancelled:
            self.result = {"created": 0, "updated": 0, "skipped": 0,
                           "errors": ["Cancelled by user"]}
            self.finished.emit(False, "Cancelled by user")
        except Exception as exc:
            self.result = {"created": 0, "updated": 0, "skipped": 0,
                           "errors": [str(exc)]}
            self.finished.emit(False, str(exc))


class _HorizontalWheelBlocker(QObject):
    """Event filter that discards horizontal wheel events on the TaskView viewport.
    This prevents the task columns (ID, Name, etc.) from scrolling left/right
    independently of the Gantt chart, which has no matching horizontal offset.
    Vertical wheel events pass through unchanged so the row-sync still works.
    """
    def eventFilter(self, obj, event):
        if event.type() == QEvent.Wheel and event.angleDelta().x() != 0:
            return True   # consume — block horizontal scroll
        return False


# ---------------------------------------------------------------------------
# Background worker for bulk email export
# ---------------------------------------------------------------------------

class _BulkEmailSendWorker(WorkerThread):
    """Export per-resource Gantt SVGs and send one email per resource.

    All filesystem and SMTP work runs in a background thread so the UI stays
    responsive.  Cancellation is checked between sends.
    """

    def __init__(self, included_rows: list, svg_dir: str, email_integration,
                 cfg: dict):
        super().__init__()
        self._rows             = included_rows
        self._svg_dir          = svg_dir
        self._email_integration = email_integration
        self._cfg              = cfg
        self.results: list     = []
        self.skipped: int      = 0

    def run(self):
        import os

        rows  = self._rows
        total = len(rows)

        for idx, row in enumerate(rows, start=1):
            if self.cancelled:
                self.finished.emit(False, "Cancelled by user")
                return

            rname     = row["resource_name"]
            to_addr   = row.get("email", "")
            subj      = row.get("subject", "")
            body_text = row.get("body", "")

            pct = int((idx - 1) / total * 100)
            self.progress.emit(pct, f"Sending to {rname} ({idx}/{total})…")

            if not to_addr:
                self.skipped += 1
                self.results.append({
                    "resource_name": rname,
                    "email":         "",
                    "success":       False,
                    "message":       "Skipped — no email address",
                })
                continue

            # Find the SVG file generated for this resource
            safe_name = "".join(
                c if c.isalnum() or c in (" ", "-", "_") else "_" for c in rname
            ).strip()
            svg_candidates = [
                f for f in os.listdir(self._svg_dir)
                if f.lower().endswith("_gantt.svg")
                and f.lower().startswith(safe_name.lower().replace(" ", "_"))
            ]
            svg_bytes = b""
            attachment_name = f"{safe_name.replace(' ', '_')}_gantt.svg"
            if svg_candidates:
                svg_file = os.path.join(self._svg_dir, svg_candidates[0])
                try:
                    with open(svg_file, "rb") as fh:
                        svg_bytes = fh.read()
                    attachment_name = svg_candidates[0]
                except Exception:
                    svg_bytes = b""

            ok, err = self._email_integration.send_email(
                to=to_addr,
                subject=subj,
                body=body_text,
                attachments=[(attachment_name, svg_bytes)] if svg_bytes else None,
                config=self._cfg,
            )
            self.results.append({
                "resource_name": rname,
                "email":         to_addr,
                "success":       ok,
                "message":       "Sent" if ok else err,
            })

        self.progress.emit(100, "Done")
        self.finished.emit(True, "")


class MainWindow(QMainWindow):
    def __init__(self, logic, file_handler):
        super().__init__()
        self.logic = logic
        self.file_handler = file_handler
        self.setWindowTitle("Project Offline")
        self.setGeometry(100, 100, 1400, 800)
        self.setStyleSheet(MS_PROJECT_STYLE)

        # Tracks the currently open file path and unsaved-changes state
        self._current_file_path: str | None = None
        self._dirty = False
        self._zoom_widget: QWidget | None = None
        # Active baseline slot for comparison (0 = default Baseline)
        self._active_baseline_number: int = 0
        # Comparison slot: -1 = current schedule, 0-10 = baseline slot
        self._comparison_baseline_number: int = -1

        # Remember last active app-tab for each ribbon tab so switching back
        # restores the view the user was on.
        self._last_app_tab_for_ribbon: dict = {
            RIBBON_TASK:     TAB_TASK_SHEET,
            RIBBON_RESOURCE: TAB_TEAM_PLANNER,
            RIBBON_REPORT:   TAB_CPM,
            RIBBON_BASELINE: TAB_BASELINE,
            RIBBON_VCS:      TAB_TASK_SHEET,  # VCS tab has no dedicated view
        }
        # Guard: True while _on_ribbon_tab_changed is switching tabs so that
        # _on_tab_changed does not override the ribbon back to another tab.
        self._ribbon_driving_tab_switch: bool = False

        # --- CPM per-project configuration (loaded from sidecar on project open) ---
        self._cpm_cfg: dict = {"critical_slack_days": 0, "dep_types": "all"}

        # --- Undo / Redo history (one stack per view) ---
        self._history = HistoryManager(logic)

        # --- Views ---
        self.task_view = TaskView()
        self.gantt_view = GanttView()
        self.resource_view = ResourceView()
        self.dependency_view = DependencyView()
        self.baseline_view = BaselineView()
        self.team_planner_view = TeamPlannerView()
        self.histogram_view = ResourceUsageHistogramView()
        self.histogram_view.setVisible(False)  # shown after settings are loaded
        self.task_sheet_view = TaskSheetView()
        self.resource_usage_graph_view = ResourceUsageGraphView()
        self.timeline_view = TimelineView()
        self.timeline_view.setVisible(False)   # shown after settings are loaded
        self.cpm_results_view = CpmResultsView()

        # Task view scrolls per pixel so its scrollbar values match the gantt canvas
        self.task_view.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        # Disable horizontal scrolling on the task column pane — columns are
        # resizable via the splitter/header, so an independent horizontal
        # scrollbar would just desync the task rows from the Gantt bars.
        self.task_view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        # Also block horizontal wheel/trackpad events on the viewport so that
        # swipe gestures cannot shift the columns even without a visible scrollbar.
        self._task_h_wheel_blocker = _HorizontalWheelBlocker(self)
        self.task_view.viewport().installEventFilter(self._task_h_wheel_blocker)

        # Refresh Gantt whenever task data changes; also mark dirty
        self.task_view.data_changed.connect(self._on_task_data_changed)
        self.task_view.data_changed.connect(self._mark_dirty)
        self.task_view.task_reordered.connect(self._mark_dirty)
        self.task_view.task_reordered.connect(self._on_task_reordered)
        self.task_view.selection_changed.connect(self._on_task_selection_changed)
        self.resource_view.data_changed.connect(self._on_resource_data_changed)
        self.resource_view.data_changed.connect(self._mark_dirty)
        self.dependency_view.data_changed.connect(self._on_dependency_data_changed)
        self.dependency_view.data_changed.connect(self._mark_dirty)
        self.gantt_view.task_moved.connect(self._on_gantt_task_moved)
        self.gantt_view.task_edited.connect(self._on_gantt_task_edited)
        self.task_view.show_in_gantt.connect(self._on_show_task_in_gantt)
        self.cpm_results_view.task_double_clicked.connect(self._on_cpm_task_double_clicked)
        if hasattr(self.task_view, 'split_task_requested'):
            self.task_view.split_task_requested.connect(self.split_task_for_task)
        if hasattr(self.task_view, 'merge_task_requested'):
            self.task_view.merge_task_requested.connect(self.merge_task_for_task)
        # Wire task_sheet_view split/merge signals
        if hasattr(self.task_sheet_view, 'split_task_requested'):
            self.task_sheet_view.split_task_requested.connect(self.split_task_for_task)
        if hasattr(self.task_sheet_view, 'merge_task_requested'):
            self.task_sheet_view.merge_task_requested.connect(self.merge_task_for_task)
        # Provide split-state callback to all context-menu views
        self.task_view._has_splits_fn = self._task_has_splits
        self.task_sheet_view._has_splits_fn = self._task_has_splits
        # Provide CPM critical-IDs accessor so TaskDialog uses computed criticality
        self.task_sheet_view._get_critical_ids = lambda: self.gantt_view.canvas._critical_ids
        self.resource_usage_graph_view._get_critical_ids = lambda: self.gantt_view.canvas._critical_ids
        # Provide CPM float-data accessor for TaskDialog Schedule tab
        self.task_sheet_view._get_float_data = lambda: self.gantt_view.canvas._float_data
        self.resource_usage_graph_view._get_float_data = lambda: self.gantt_view.canvas._float_data
        # Provide sidecar path accessor so TaskDialog can show Jira metadata
        _sidecar = lambda: (self._current_file_path + ".custom-props.json") if self._current_file_path else ""
        self.task_sheet_view._get_sidecar_path = _sidecar
        self.gantt_view._get_sidecar_path = _sidecar
        self.resource_usage_graph_view._get_sidecar_path = _sidecar
        # Share the splits dict reference with the team planner for rendering
        self.team_planner_view.canvas.set_splits_ref(self.gantt_view.canvas._task_splits)
        # Register split flush/reload hooks so undo/redo snapshots include split data
        self._history.set_hooks(
            pre_serialize=self._write_splits_to_project,
            post_restore=self._load_splits,
        )
        self.team_planner_view.data_changed.connect(self._on_team_planner_data_changed)
        self.team_planner_view.data_changed.connect(self._mark_dirty)
        # Sync histogram horizontal scroll with the Team Planner timeline scroll
        self.team_planner_view._rows_area.horizontalScrollBar().valueChanged.connect(
            self.histogram_view.set_scroll_x
        )
        self.resource_usage_graph_view.task_edited.connect(self._on_resource_usage_task_edited)
        self.task_sheet_view.data_changed.connect(self._on_task_sheet_data_changed)
        self.task_sheet_view.data_changed.connect(self._mark_dirty)

        # --- Gantt Chart tab: task table left | gantt chart right ---
        gantt_splitter = QSplitter(Qt.Horizontal)
        gantt_splitter.addWidget(self.task_view)
        gantt_splitter.addWidget(self.gantt_view)
        gantt_splitter.setStretchFactor(0, 2)
        gantt_splitter.setStretchFactor(1, 3)
        gantt_splitter.setSizes([480, 720])

        # --- Tabs ---
        self.tabs = QTabWidget()
        self.tabs.addTab(gantt_splitter, "Gantt Chart")          # TAB_GANTT
        self.tabs.addTab(self.resource_view, "Resources")         # TAB_RESOURCES
        self.tabs.addTab(self.dependency_view, "Dependencies")    # TAB_DEPENDENCIES
        self.tabs.addTab(self.baseline_view, "Baseline")          # TAB_BASELINE
        # Wrap Team Planner + histogram strip in a container so the histogram
        # sits directly below the canvas and both are hidden/shown together as
        # a single tab widget child.
        self._team_planner_container = QWidget()
        _tp_layout = QVBoxLayout(self._team_planner_container)
        _tp_layout.setContentsMargins(0, 0, 0, 0)
        _tp_layout.setSpacing(0)
        _tp_layout.addWidget(self.team_planner_view, 1)
        _tp_layout.addWidget(self.histogram_view)
        self.tabs.addTab(self._team_planner_container, "Team Planner")  # TAB_TEAM_PLANNER
        self.tabs.addTab(self.task_sheet_view, "Task Sheet")      # TAB_TASK_SHEET
        self.tabs.addTab(self.resource_usage_graph_view, "Resource Usage")  # TAB_RESOURCE_USAGE
        self.tabs.addTab(self.cpm_results_view, "CPM Results")              # TAB_CPM
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.tabs.tabBar().setVisible(False)

        # Wrap timeline strip (above) + tabs (below) in a single central widget
        _central = QWidget()
        _central_layout = QVBoxLayout(_central)
        _central_layout.setContentsMargins(0, 0, 0, 0)
        _central_layout.setSpacing(0)
        _central_layout.addWidget(self.timeline_view)
        _central_layout.addWidget(self.tabs, 1)
        self.setCentralWidget(_central)

        # --- Menu and Toolbar ---
        self.setMenuBar(ProjectMenuBar(self, logic, file_handler))
        self._toolbar = ProjectToolBar(self, logic, file_handler)
        self.addToolBar(self._toolbar)
        self._toolbar.ribbon.ribbon_tab_changed.connect(self._on_ribbon_tab_changed)

        # Default view: Task Sheet (set after toolbar exists so _on_tab_changed is safe)
        self.tabs.setCurrentIndex(TAB_TASK_SHEET)

        # --- Status Bar ---
        self._status_label = QLabel("Ready")
        self.statusBar().addWidget(self._status_label, 1)   # stretch=1, pushes zoom to the right
        self.statusBar().setVisible(True)

        # --- Status bar zoom control (MS Project style) ---
        self._zoom_pct_label = QLabel("100%")
        self._zoom_pct_label.setFixedWidth(50)
        self._zoom_pct_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._zoom_pct_label.setStyleSheet("color: #1F1F1F; font-size: 11px;")

        self._zoom_slider = QSlider(Qt.Horizontal)
        self._zoom_slider.setRange(DAY_WIDTH_MIN, DAY_WIDTH_MAX)
        self._zoom_slider.setValue(DAY_WIDTH_DEF)
        self._zoom_slider.setFixedWidth(100)
        self._zoom_slider.setToolTip("Drag to zoom the Gantt chart")
        self._zoom_slider.valueChanged.connect(self._on_zoom_slider)

        btn_zoom_out = QToolButton()
        btn_zoom_out.setText("-")
        btn_zoom_out.setToolTip("Zoom Out (Ctrl+-)")
        btn_zoom_out.setFixedSize(20, 20)
        btn_zoom_out.clicked.connect(self.zoom_out)

        btn_zoom_in = QToolButton()
        btn_zoom_in.setText("+")
        btn_zoom_in.setToolTip("Zoom In  (Ctrl++)")
        btn_zoom_in.setFixedSize(20, 20)
        btn_zoom_in.clicked.connect(self.zoom_in)

        zoom_widget = QWidget()
        zoom_layout = QHBoxLayout(zoom_widget)
        zoom_layout.setContentsMargins(0, 0, 6, 0)
        zoom_layout.setSpacing(3)
        zoom_layout.addWidget(self._zoom_pct_label)
        zoom_layout.addWidget(btn_zoom_out)
        zoom_layout.addWidget(self._zoom_slider)
        zoom_layout.addWidget(btn_zoom_in)
        self._zoom_widget = zoom_widget
        self.statusBar().addPermanentWidget(self._zoom_widget)
        self._zoom_widget.setVisible(False)  # shown only for zoom-supporting views

        # --- Status bar: compact CPM threshold spin + CPM summary label ---
        _cpm_bar = QWidget()
        _cpm_bar_layout = QHBoxLayout(_cpm_bar)
        _cpm_bar_layout.setContentsMargins(4, 0, 6, 0)
        _cpm_bar_layout.setSpacing(4)
        _slack_lbl = QLabel("Slack:")
        _slack_lbl.setStyleSheet("color: #1F1F1F; font-size: 11px;")
        self._cpm_slack_spin = QSpinBox()
        self._cpm_slack_spin.setRange(0, 30)
        self._cpm_slack_spin.setSuffix(" d")
        self._cpm_slack_spin.setValue(self._cpm_cfg.get("critical_slack_days", 0))
        self._cpm_slack_spin.setFixedWidth(56)
        self._cpm_slack_spin.setToolTip(
            "Critical slack threshold — tasks with total float ≤ this value are treated as critical"
        )
        self._cpm_slack_spin.setStyleSheet("font-size: 11px;")
        _sep_lbl = QLabel("|")
        _sep_lbl.setStyleSheet("color: #aaaaaa; font-size: 11px;")
        self._cpm_summary_label = QLabel("Critical: —")
        self._cpm_summary_label.setStyleSheet("color: #1F1F1F; font-size: 11px;")
        _cpm_bar_layout.addWidget(_slack_lbl)
        _cpm_bar_layout.addWidget(self._cpm_slack_spin)
        _cpm_bar_layout.addWidget(_sep_lbl)
        _cpm_bar_layout.addWidget(self._cpm_summary_label)
        self._cpm_slack_spin.valueChanged.connect(self._on_cpm_slack_spin_changed)
        # Insert to the left of the zoom widget in the permanent area
        self.statusBar().insertPermanentWidget(0, _cpm_bar)

        # Update slider/label when canvas zoom changes
        self._zoom_def = DAY_WIDTH_DEF
        self.gantt_view.zoom_changed.connect(self._on_gantt_zoom_changed)

        # --- Keyboard shortcuts for zoom ---
        from PyQt5.QtWidgets import QShortcut  # type: ignore
        QShortcut(QKeySequence("Ctrl+="), self).activated.connect(self.zoom_in)
        QShortcut(QKeySequence("Ctrl++"), self).activated.connect(self.zoom_in)
        QShortcut(QKeySequence("Ctrl+-"), self).activated.connect(self.zoom_out)
        QShortcut(QKeySequence("Ctrl+Z"), self).activated.connect(self._undo)
        QShortcut(QKeySequence("Ctrl+Y"), self).activated.connect(self._redo)
        # Debug dump (only active when --debug flag is set)
        QShortcut(QKeySequence("Ctrl+D"), self).activated.connect(self._debug_dump)

        # --- Sync vertical scroll: both panes drive each other ---
        # Connections are safe from infinite loops because Qt skips valueChanged
        # when setValue is called with the same value already set.
        self.task_view.verticalScrollBar().valueChanged.connect(
            self.gantt_view.verticalScrollBar().setValue
        )
        self.gantt_view.verticalScrollBar().valueChanged.connect(
            self.task_view.verticalScrollBar().setValue
        )

        # --- Persistent settings (KeePass, Jira, display prefs) ---
        self._settings = QSettings("ProjectOffline", "ProjectManager")
        self._settings_manager = SettingsManager(self._settings)
        # Initialise the KeePassManager singleton so other integration modules
        # can resolve credentials without importing SettingsManager directly.
        try:
            from integrations import keepass_integration as _kp_mod
            _kp_mod.init(self._settings_manager)
        except Exception:
            pass
        show_units = self._settings.value("gantt/show_resource_units", False, type=bool)
        self.gantt_view.set_show_resource_units(show_units)
        self.menuBar().set_resource_units_checked(show_units)
        self._toolbar.ribbon.set_resource_units_checked(show_units)
        show_sundays = self._settings.value("gantt/show_sundays", True, type=bool)
        self.gantt_view.set_show_sundays(show_sundays)
        self.team_planner_view.set_show_sundays(show_sundays)
        self.resource_usage_graph_view.set_show_sundays(show_sundays)
        self.menuBar().set_show_sundays_checked(show_sundays)
        self._toolbar.ribbon.set_show_sundays_checked(show_sundays)
        show_off_hours = self._settings.value("usage/show_off_hours", False, type=bool)
        self.resource_usage_graph_view.set_show_off_hours(show_off_hours)
        self.menuBar().set_show_off_hours_checked(show_off_hours)
        show_histogram = self._settings.value("histogram/visible", False, type=bool)
        self.histogram_view.setVisible(show_histogram)
        self.menuBar().set_show_histogram_checked(show_histogram)
        zero_float_critical = self._settings_manager.get_zero_float_critical()
        self.gantt_view.set_zero_float_critical(zero_float_critical)
        self.task_view.set_zero_float_critical(zero_float_critical)
        self.team_planner_view.canvas.set_zero_float_critical(zero_float_critical)
        self.menuBar().set_zero_float_critical_checked(zero_float_critical)
        # No project open at startup — disable project-gated ribbon buttons
        self._toolbar.ribbon.set_project_open(False)
        # Reflect initial email configuration state in export dropdown items
        self._update_email_actions_state()
        # Populate Recent Files menu from persisted settings
        self.menuBar().update_recent_files(self._load_recent_files())
        # Restore CPM results panel preference (navigate to it if it was last visible)
        if self._settings_manager.get_show_cpm_results_panel():
            self._last_app_tab_for_ribbon[RIBBON_REPORT] = TAB_CPM

        # --- Timeline view: registration + source-view context-menu wiring ---
        from views.timeline_view import _SOURCE_VIEWS_WITH_CONTEXT_MENU  # type: ignore
        self.timeline_view.register(self)
        # Give views that open TaskDialog a reference to the timeline view
        self.gantt_view.set_timeline_view(self.timeline_view)
        if hasattr(self.resource_usage_graph_view, 'set_timeline_view'):
            self.resource_usage_graph_view.set_timeline_view(self.timeline_view)
        if TAB_GANTT in _SOURCE_VIEWS_WITH_CONTEXT_MENU:
            self.task_view._timeline_is_pinned = (
                lambda tid: self.timeline_view.is_task_pinned(tid)
                or self.timeline_view.is_milestone_pinned(tid)
            )
            self.task_view._timeline_view_ref = self.timeline_view
            self.task_view.timeline_toggle_requested.connect(self._on_timeline_toggle)
        if TAB_TASK_SHEET in _SOURCE_VIEWS_WITH_CONTEXT_MENU:
            self.task_sheet_view._timeline_is_pinned = (
                lambda tid: self.timeline_view.is_task_pinned(tid)
                or self.timeline_view.is_milestone_pinned(tid)
            )
            self.task_sheet_view._timeline_view_ref = self.timeline_view
            self.task_sheet_view.timeline_toggle_requested.connect(self._on_timeline_toggle)
        # Restore timeline visibility from settings
        tl_visible = self._settings.value("timeline/visible", False, type=bool)
        self.menuBar().set_timeline_checked(tl_visible)
        self._update_timeline_visibility()

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    def _mark_dirty(self):
        """Called whenever the project data changes — enables Save."""
        if not self._dirty:
            self._dirty = True
            self._toolbar.set_save_enabled(True)
            self.menuBar().set_save_enabled(True)
            self._update_title()

    def _mark_clean(self):
        """Called after load or save — disables Save."""
        self._dirty = False
        self._toolbar.set_save_enabled(False)
        self.menuBar().set_save_enabled(False)
        self._update_title()

    def _update_title(self):
        base = "Project Offline"
        if self._current_file_path:
            import os
            base = f"{os.path.basename(self._current_file_path)} — Project Offline"
        self.setWindowTitle(base + (" *" if self._dirty else ""))

    def _debug_dump(self):
        """Ctrl+D: dump in-memory project state + UI variables to a timestamped
        JSON file.  No-op unless the application was started with --debug."""
        from app_debug import is_debug, dump_project_state  # type: ignore
        from integrations import keepass_integration as _kp_debug  # type: ignore
        if not is_debug():
            return
        project = self.logic.get_data()
        if project is None:
            QMessageBox.information(self, "Debug Dump", "No project loaded — nothing to dump.")
            return
        try:
            _TAB_NAMES = {
                TAB_GANTT:          "Gantt Chart",
                TAB_RESOURCES:      "Resources",
                TAB_DEPENDENCIES:   "Dependencies",
                TAB_BASELINE:       "Baseline",
                TAB_TEAM_PLANNER:   "Team Planner",
                TAB_TASK_SHEET:     "Task Sheet",
                TAB_RESOURCE_USAGE: "Resource Usage",
            }
            _RIBBON_NAMES = {
                RIBBON_TASK:     "Task",
                RIBBON_RESOURCE: "Resource",
                RIBBON_REPORT:   "Report",
            }
            active_tab_idx  = self.tabs.currentIndex()
            ribbon_tab_idx  = self._toolbar.ribbon._active_tab
            canvas          = self.gantt_view.canvas
            gc              = self.gantt_view._scroll_area.horizontalScrollBar()
            gv              = self.gantt_view._scroll_area.verticalScrollBar()
            ui_state = {
                # Window / file
                "file_path":            self._current_file_path,
                "unsaved_changes":       self._dirty,
                # Navigation
                "active_tab_index":      active_tab_idx,
                "active_tab_name":       _TAB_NAMES.get(active_tab_idx, str(active_tab_idx)),
                "ribbon_tab_index":      ribbon_tab_idx,
                "ribbon_tab_name":       _RIBBON_NAMES.get(ribbon_tab_idx, str(ribbon_tab_idx)),
                # Zoom / scroll
                "zoom_day_width":        canvas.day_width,
                "hourly_mode":           canvas.is_hourly_mode(),
                "gantt_scroll_x":        gc.value(),
                "gantt_scroll_y":        gv.value(),
                # Working-hour window
                "work_hour_start":       canvas._work_hour_start,
                "work_hour_end":         getattr(canvas, '_work_hour_end', None),
                "clock_day_span":        canvas._clock_day_span,
                "show_off_hours":        canvas._show_off_hours,
                # Options
                "show_resource_units":   canvas.show_resource_units,
                "zero_float_critical":   canvas._zero_float_critical,
                # Project extent
                "project_start":         canvas.project_start.toString("yyyy-MM-dd") if canvas.project_start else None,
                "project_total_days":    canvas.total_days,
                # Critical IDs (leaf task IDs flagged critical by current CPM/read)
                "critical_task_ids":     sorted(canvas._critical_ids),
                # Baseline view colour diagnostics
                "baseline_view":         self.baseline_view.color_diagnostics(),
                # Timeline view data
                "timeline_visible":      self.timeline_view.isVisible(),
                "timeline_pinned_tasks": [
                    {
                        "id":     t.task_id,
                        "name":   t.name,
                        "start":  t.start.toString("yyyy-MM-dd"),
                        "finish": t.finish.toString("yyyy-MM-dd"),
                    }
                    for t in self.timeline_view._timeline_tasks
                ],
                "timeline_pinned_milestones": [
                    {
                        "id":   m.milestone_id,
                        "name": m.name,
                        "date": m.date.toString("yyyy-MM-dd"),
                    }
                    for m in self.timeline_view._timeline_milestones
                ],
                # Split task data
                "split_tasks": self.gantt_view.splits_to_dict(),
                # KeePass integration status (non-sensitive fields only)
                "keepass": {
                    "configured":                  _kp_debug.is_configured(),
                    "unlocked":                    _kp_debug.is_unlocked(),
                    "db_path_set":                 bool(self._settings_manager.get_keepass_db_path()),
                    "key_file_set":                bool(self._settings_manager.get_keepass_key_file()),
                    "password_saved":              bool(self._settings_manager.get_keepass_password()),
                    "entry_count":                 len(_kp_debug.list_entries()) if _kp_debug.is_unlocked() else None,
                    "confluence_entry_configured": bool(self._settings_manager.get_confluence_keepass_entry()),
                },
                # Last vacation-overlap dialog choice in the Team Planner
                "last_vacation_action": self.team_planner_view.canvas._last_vacation_action,
                # Non-working day caches — used to diagnose holiday-dialog issues
                "gantt_non_working_count":  len(self.gantt_view.canvas._non_working_dates),
                "gantt_non_working_dates":  sorted(self.gantt_view.canvas._non_working_dates)[:40],
                "tp_non_working_count":     len(self.team_planner_view.canvas._non_working),
                "tp_non_working_dates":     sorted(self.team_planner_view.canvas._non_working)[:40],
                "tp_project_ref_is_none":   self.team_planner_view.canvas._project is None,
                "tp_project_start":         (self.team_planner_view.canvas.project_start.toString("yyyy-MM-dd")
                                             if self.team_planner_view.canvas.project_start else None),
                "tp_total_days":            self.team_planner_view.canvas.total_days,
                # Resource Usage Histogram
                "histogram_visible":        self.histogram_view.isVisible(),
                "histogram_height_px":      self.histogram_view.height(),
                # CPM float data and settings
                "float_data":               getattr(self.gantt_view.canvas, "_float_data", {}),
                "cpm_settings":             dict(self._cpm_cfg),
            }

            # ----------------------------------------------------------
            # Layout diagnostics — compare maximized vs normal window
            # ----------------------------------------------------------
            def _sz(w):
                """Widget ? {w, h} dict (safe)."""
                try:
                    return {"w": w.width(), "h": w.height()}
                except Exception:
                    return None

            def _hint(w):
                """Widget ? sizeHint {w, h} dict (safe)."""
                try:
                    sh = w.sizeHint()
                    return {"w": sh.width(), "h": sh.height()}
                except Exception:
                    return None

            def _min(w):
                """Widget ? minimumSize {w, h} dict (safe)."""
                try:
                    m = w.minimumSize()
                    return {"w": m.width(), "h": m.height()}
                except Exception:
                    return None

            def _max(w):
                """Widget ? maximumSize {w, h} dict (safe)."""
                try:
                    m = w.maximumSize()
                    return {"w": m.width(), "h": m.height()}
                except Exception:
                    return None

            def _pos(w):
                """Widget ? pos {x, y} dict mapped to parent coords (safe)."""
                try:
                    p = w.pos()
                    return {"x": p.x(), "y": p.y()}
                except Exception:
                    return None

            def _geom(w):
                """Widget ? full geometry dict {x, y, w, h} in parent coords."""
                try:
                    g = w.geometry()
                    return {"x": g.x(), "y": g.y(), "w": g.width(), "h": g.height()}
                except Exception:
                    return None

            from PyQt5.QtCore import Qt as _Qt  # type: ignore
            ws = int(self.windowState())
            tl = self.timeline_view
            sb = self.statusBar()
            cw = self.centralWidget()

            # Central VBox layout metrics
            try:
                cl = cw.layout()
                cl_margins = cl.contentsMargins()
                _cl_info = {
                    "spacing": cl.spacing(),
                    "margins": {
                        "left":   cl_margins.left(),
                        "top":    cl_margins.top(),
                        "right":  cl_margins.right(),
                        "bottom": cl_margins.bottom(),
                    },
                    "item_count": cl.count(),
                }
            except Exception:
                _cl_info = None

            # Screen available geometry
            try:
                from PyQt5.QtWidgets import QDesktopWidget  # type: ignore
                _screen = QDesktopWidget().availableGeometry(self)
                _screen_info = {"w": _screen.width(), "h": _screen.height(),
                                "x": _screen.x(), "y": _screen.y()}
            except Exception:
                _screen_info = None

            ui_state["layout_diagnostics"] = {
                # Window
                "window_state_flags":     ws,
                "window_is_maximized":    bool(ws & _Qt.WindowMaximized),
                "window_is_normal":       ws == _Qt.WindowNoState,
                "window_frame_geom":      _geom(self),           # outer (with frame)
                "window_geom":            _sz(self),             # inner client area
                "screen_available":       _screen_info,
                # Fixed structural chrome
                "menubar_height":         self.menuBar().height(),
                "toolbar_height":         self._toolbar.height(),
                # Central widget
                "central_widget_geom":    _geom(cw),
                "central_widget_size":    _sz(cw),
                "central_layout":         _cl_info,
                # Timeline strip
                "timeline_is_visible":    tl.isVisible(),
                "timeline_geom":          _geom(tl),
                "timeline_size":          _sz(tl),
                "timeline_size_hint":     _hint(tl),
                "timeline_minimum_size":  _min(tl),
                "timeline_maximum_size":  _max(tl),
                "timeline_fixed_h":       getattr(tl, '_fixed_h', None),
                # Tab widget
                "tabs_geom":              _geom(self.tabs),
                "tabs_size":              _sz(self.tabs),
                "tabs_size_hint":         _hint(self.tabs),
                "tabs_minimum_size":      _min(self.tabs),
                # Status bar
                "statusbar_is_visible":   sb.isVisible(),
                "statusbar_geom":         _geom(sb),
                "statusbar_size":         _sz(sb),
                "statusbar_size_hint":    _hint(sb),
                # Sum check: toolbar + central + statusbar should == window height
                "height_sum_check": {
                    "toolbar":        self._toolbar.height(),
                    "central_widget": cw.height() if cw else 0,
                    "statusbar":      sb.height(),
                    "menubar":        self.menuBar().height(),
                    "sum":            (self._toolbar.height()
                                       + (cw.height() if cw else 0)
                                       + sb.height()),
                    "window_height":  self.height(),
                    "diff":           self.height() - (
                                        self._toolbar.height()
                                        + (cw.height() if cw else 0)
                                        + sb.height()
                                      ),
                },
            }
            path = dump_project_state(project, ui_state)
            QMessageBox.information(self, "Debug Dump", f"Project state written to:\n{path}")
        except Exception as exc:  # noqa: BLE001
            from PyQt5.QtWidgets import QApplication  # type: ignore
            msg = QMessageBox(self)
            msg.setWindowTitle("Debug Dump Failed")
            msg.setText(str(exc))
            msg.setIcon(QMessageBox.Warning)
            copy_btn = msg.addButton("Copy to Clipboard", QMessageBox.ActionRole)
            copy_btn.clicked.connect(lambda: QApplication.clipboard().setText(str(exc)))
            msg.addButton(QMessageBox.Ok)
            msg.exec_()

    def closeEvent(self, event):
        if self._dirty:
            reply = QMessageBox.question(
                self, "Unsaved Changes",
                "The project has unsaved changes.\nDo you want to save before closing?",
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                QMessageBox.Save,
            )
            if reply == QMessageBox.Save:
                self.save_project()
                if self._dirty:          # save was cancelled
                    event.ignore()
                    return
            elif reply == QMessageBox.Cancel:
                event.ignore()
                return
        event.accept()
        try:
            from integrations.confluence_calendar_integration import clear_saved_session  # type: ignore
            clear_saved_session()
        except Exception:
            pass

    # Tab labels: (toolbar_add, toolbar_del, entry_enabled, zoom_enabled)
    _TAB_LABELS = [
        ("\u2795 Task",        "\u2716 Delete Task",        True,  True),
        ("\u2795 Resource",    "\u2716 Delete Resource",    True,  False),
        ("\u2795 Dependency",  "\u2716 Delete Dependency",  True,  False),
        ("\u2795",             "\u2716",                    False, False),  # Baseline
        ("\u2795",             "\u2716",                    False, True),   # Team Planner
        ("\u2795",             "\u2716",                    False, False),  # Task Sheet
        ("\u2795",             "\u2716",                    False, True),   # Resource Usage Graph
        ("\u2795",             "\u2716",                    False, False),  # CPM Results
    ]

    # App tabs whose zoom slider is visible.
    # HOW TO CONFIGURE
    # ----------------
    # Add or remove TAB_* constants (defined in app_tabs.py) to control on
    # which views the status-bar zoom slider + percentage label is shown.
    # The slider is hidden for all other views.
    _ZOOM_APP_TABS: frozenset = frozenset({
        TAB_GANTT,
        TAB_TEAM_PLANNER,
        TAB_RESOURCE_USAGE,
    })

    # App tab ? ribbon tab mapping.
    # HOW TO CONFIGURE
    # ----------------
    # Each entry maps a TAB_* index to the RIBBON_* tab that owns it.
    # When the user switches app tabs, the ribbon switches to the matching tab.
    _APP_TO_RIBBON_TAB = {
        TAB_GANTT:          RIBBON_TASK,
        TAB_RESOURCES:      RIBBON_RESOURCE,
        TAB_DEPENDENCIES:   RIBBON_TASK,
        TAB_BASELINE:       RIBBON_BASELINE,
        TAB_TEAM_PLANNER:   RIBBON_RESOURCE,
        TAB_TASK_SHEET:     RIBBON_TASK,
        TAB_RESOURCE_USAGE: RIBBON_RESOURCE,
        TAB_CPM:            RIBBON_REPORT,
    }
    # Reverse map: ribbon tab → set of app tabs it manages (used to track
    # "last active" per ribbon tab so switching back restores the right view).
    _RIBBON_APP_TABS = {
        RIBBON_TASK:     {TAB_GANTT, TAB_DEPENDENCIES, TAB_TASK_SHEET},
        RIBBON_RESOURCE: {TAB_RESOURCES, TAB_TEAM_PLANNER, TAB_RESOURCE_USAGE},
        RIBBON_BASELINE: {TAB_BASELINE},
        RIBBON_REPORT:   {TAB_CPM},
        RIBBON_VCS:      set(),  # no dedicated app tab
    }

    def _on_ribbon_tab_changed(self, ribbon_idx: int):
        app_idx = self._last_app_tab_for_ribbon.get(ribbon_idx, -1)
        if app_idx >= 0:
            self._ribbon_driving_tab_switch = True
            try:
                self.tabs.setCurrentIndex(app_idx)
            finally:
                self._ribbon_driving_tab_switch = False

    def _on_task_selection_changed(self, has_sel: bool):
        if self.tabs.currentIndex() == TAB_GANTT:
            self._toolbar.set_delete_enabled(has_sel)
            self.menuBar().set_delete_enabled(has_sel)

    def _on_tab_changed(self, idx):
        if 0 <= idx < len(self._TAB_LABELS):
            add_lbl, del_lbl, enabled, zoom_ok = self._TAB_LABELS[idx]
            self._toolbar.update_actions(add_lbl, del_lbl, enabled, zoom_ok)
            self.menuBar().update_edit_actions(
                f"&Insert {add_lbl.replace('\u2795 ', '')}",
                f"&Delete {del_lbl.replace('\u2716 ', '')}",
                enabled,
            )
            # Gantt tab: delete follows selection, not just tab-active state
            if idx == TAB_GANTT:
                self._toolbar.set_delete_enabled(bool(self.task_view.selectedIndexes()))
            # Task Sheet tab: reload to pick up any changes made in other views
            if idx == TAB_TASK_SHEET and self.logic.get_data() is not None:
                self.task_sheet_view.load_project(self.logic.get_data())
            # Resource Usage Graph tab: reload to pick up any changes
            if idx == TAB_RESOURCE_USAGE and self.logic.get_data() is not None:
                self.resource_usage_graph_view.load_project(self.logic.get_data())
            # CPM Results tab: refresh with latest float data
            if idx == TAB_CPM and self.logic.get_data() is not None:
                self._refresh_cpm_results_view()
            # Sync active ribbon tab and remember this tab for that ribbon.
            # Skip the ribbon activation when the switch was triggered by the
            # ribbon itself — the correct ribbon tab is already highlighted.
            ribbon_idx = self._APP_TO_RIBBON_TAB.get(idx, 0)
            if not self._ribbon_driving_tab_switch:
                if idx in self._RIBBON_APP_TABS.get(ribbon_idx, set()):
                    self._last_app_tab_for_ribbon[ribbon_idx] = idx
                self._toolbar.ribbon._activate_tab(ribbon_idx)
            self._toolbar.ribbon.highlight_view_button(idx)
            self._toolbar.ribbon.update_button_visibility(idx)
            if self._zoom_widget is not None:
                self._zoom_widget.setVisible(idx in self._ZOOM_APP_TABS)
            self._update_timeline_visibility()

    # ------------------------------------------------------------------ #
    # Undo / Redo                                                         #
    # ------------------------------------------------------------------ #

    # ------------------------------------------------------------------ #
    # Timeline view helpers                                               #
    # ------------------------------------------------------------------ #

    def _update_timeline_visibility(self):
        """Show the timeline strip only when user toggle is on AND the current
        tab is listed in _VIEWS_SHOWING_TIMELINE."""
        if not hasattr(self, '_settings'):
            return   # called before settings are initialised (e.g. during __init__)
        from views.timeline_view import _VIEWS_SHOWING_TIMELINE  # type: ignore
        tl_on = self._settings.value("timeline/visible", False, type=bool)
        idx   = self.tabs.currentIndex()
        self.timeline_view._set_collapsed(not (tl_on and idx in _VIEWS_SHOWING_TIMELINE))

    def changeEvent(self, event):
        """Re-apply timeline visibility after window state changes (maximize / restore).
        Uses a deferred call so the layout has fully settled before we update."""
        super().changeEvent(event)
        from PyQt5.QtCore import QEvent, QTimer  # type: ignore
        if event.type() == QEvent.WindowStateChange:
            # Defer until Qt has processed the resize geometry so that
            # _set_collapsed sets the correct min/max heights on the final size.
            QTimer.singleShot(0, self._on_window_state_settled)

    def _on_window_state_settled(self):
        """Called via QTimer after a window state change has fully settled."""
        self._update_timeline_visibility()
        # Ensure the status bar is on top in the Qt widget stacking order.
        # On Windows, QMainWindow can temporarily bury it during maximize/restore.
        self.statusBar().raise_()

    def toggle_timeline(self, checked: bool):
        """Called from Format > Show Timeline."""
        self._settings.setValue("timeline/visible", checked)
        self.menuBar().set_timeline_checked(checked)
        self._update_timeline_visibility()

    def _on_timeline_data_changed(self):
        """Timeline task list changed — auto-save the JSON sidecar file."""
        self._save_timeline_json()

    def _on_timeline_remove_from_canvas(self, item_id: int, is_milestone: bool):
        """User right-clicked a bar/diamond on the canvas and chose Remove."""
        if is_milestone:
            self.timeline_view.remove_milestone(item_id)
        else:
            self.timeline_view.remove_task(item_id)

    def _on_timeline_toggle(self, task):
        """Add or remove *task* from the timeline (from source-view context menu)."""
        try:
            task_id = int(str(task.getID()))
        except Exception:
            return
        try:
            is_milestone = bool(task.getMilestone())
        except Exception:
            is_milestone = False
        if is_milestone:
            if self.timeline_view.is_milestone_pinned(task_id):
                self.timeline_view.remove_milestone(task_id)
            else:
                self.timeline_view.add_milestone(task)
        else:
            if self.timeline_view.is_task_pinned(task_id):
                self.timeline_view.remove_task(task_id)
            else:
                self.timeline_view.add_task(task)

    def _timeline_json_path(self) -> str | None:
        if not self._current_file_path:
            return None
        base = os.path.splitext(self._current_file_path)[0]
        return base + ".timeline.json"

    def _save_timeline_json(self):
        path = self._timeline_json_path()
        if not path:
            return
        try:
            import json
            data = {
                "tasks": [
                    {
                        "id":     t.task_id,
                        "name":   t.name,
                        "start":  t.start.toString("yyyy-MM-dd"),
                        "finish": t.finish.toString("yyyy-MM-dd"),
                    }
                    for t in self.timeline_view._timeline_tasks
                ],
                "milestones": [
                    {
                        "id":   m.milestone_id,
                        "name": m.name,
                        "date": m.date.toString("yyyy-MM-dd"),
                    }
                    for m in self.timeline_view._timeline_milestones
                ],
            }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as exc:
            print(f"[WARN] timeline JSON save: {exc}")

    def _load_timeline_json(self):
        path = self._timeline_json_path()
        if not path or not os.path.exists(path):
            return
        try:
            import json
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            project = self.logic.get_data()
            if project is None:
                return
            task_map: dict = {}
            for t in project.getTasks():
                if t.getName() is None:
                    continue
                try:
                    task_map[int(str(t.getID()))] = t
                except Exception:
                    pass
            for item in data.get("tasks", []):
                tid = item.get("id")
                if tid is not None and tid in task_map:
                    self.timeline_view.add_task(task_map[tid])
            for item in data.get("milestones", []):
                mid = item.get("id")
                if mid is not None and mid in task_map:
                    self.timeline_view.add_milestone(task_map[mid])
        except Exception as exc:
            print(f"[WARN] timeline JSON load: {exc}")

    def export_timeline_svg(self):
        if self.logic.get_data() is None:
            QMessageBox.information(self, "Export", "No project is open.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Timeline as SVG", "", "SVG Files (*.svg)"
        )
        if not path:
            return
        try:
            self.timeline_view.export_svg(path)
            QMessageBox.information(self, "Export", f"Timeline saved to:\n{path}")
        except Exception as exc:
            QMessageBox.critical(self, "Export Error", str(exc))

    def export_timeline_plantuml(self):
        if self.logic.get_data() is None:
            QMessageBox.information(self, "Export", "No project is open.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Timeline as PlantUML", "",
            "PlantUML Files (*.puml *.plantuml)"
        )
        if not path:
            return
        try:
            self.timeline_view.export_plantuml(path)
            QMessageBox.information(self, "Export", f"Timeline PlantUML saved to:\n{path}")
        except Exception as exc:
            QMessageBox.critical(self, "Export Error", str(exc))

    def email_timeline_svg(self):
        """Send the Timeline strip as an SVG email attachment."""
        if self.logic.get_data() is None:
            QMessageBox.information(self, "Email Export", "No project is open.")
            return
        import tempfile, os
        from integrations import email_integration  # type: ignore
        from dialogs import EmailExportDialog  # type: ignore
        try:
            with tempfile.NamedTemporaryFile(suffix=".svg", delete=False) as tf:
                svg_path = tf.name
            self.timeline_view.export_svg(svg_path)
            with open(svg_path, "rb") as fh:
                svg_bytes = fh.read()
            os.unlink(svg_path)
        except Exception as exc:
            QMessageBox.critical(self, "Email Export", f"Failed to export Timeline to SVG:\n{exc}")
            return
        self._send_svg_bytes_as_email("Timeline", "timeline.svg", svg_bytes)

    # Maps app-tab index ? history view name (see app_tabs.py for TAB_* constants)
    _TAB_TO_HISTORY_VIEW = {
        TAB_GANTT:          'tasks',
        TAB_RESOURCES:      'resources',
        TAB_DEPENDENCIES:   'dependencies',
        TAB_BASELINE:       'baseline',
        TAB_TEAM_PLANNER:   'team_planner',
        TAB_TASK_SHEET:     'tasks',
        TAB_RESOURCE_USAGE: 'resources',
    }

    def _active_history_view(self) -> str:
        return self._TAB_TO_HISTORY_VIEW.get(self.tabs.currentIndex(), 'tasks')

    def _undo(self):
        view = self._active_history_view()
        if self._history.undo(view):
            self._refresh_all_views()
            self._mark_dirty()

    def _redo(self):
        view = self._active_history_view()
        if self._history.redo(view):
            self._refresh_all_views()
            self._mark_dirty()

    def _on_task_reordered(self):
        # History is already pushed by _on_task_data_changed (emitted via _reload
        # inside _do_row_reorder before task_reordered fires). Pushing again here
        # would require two undos to reverse a single move-up/down operation.
        pass

    def _on_task_data_changed(self):
        project = self.logic.get_data()
        self.gantt_view.set_collapsed_ids(self.task_view.get_collapsed_ids())
        self.gantt_view.load_project(project)
        self.task_sheet_view.load_project(project)
        self._update_status_bar()
        self._refresh_cpm_results_view()
        self._history.push('tasks')
        self._history.push('baseline')

    def _on_gantt_task_moved(self, task, delta):
        """User dragged a Gantt bar: shift its start/finish and update relation lags."""
        if delta == 0:
            return
        try:
            old_start  = task.getStart()
            old_finish = task.getFinish()
            import jpype  # type: ignore

            # Hourly mode: shift by work-hour slots (NOT calendar hours).
            # delta is the number of visible hour-slot columns moved; this is
            # NOT the same as calendar hours when the move crosses a day boundary
            # (e.g. -2 slots from 08:00 Mon = 15:00 Fri, not 06:00 Mon).
            if self.gantt_view.canvas.is_hourly_mode():
                canvas           = self.gantt_view.canvas
                wh_start         = canvas._work_hour_start
                clock_span       = canvas._clock_day_span
                proj_start_qd    = canvas.project_start   # QDate
                show_off         = canvas._show_off_hours
                eff_span         = 24 if show_off else clock_span
                eff_start_hr     = 0  if show_off else wh_start

                from views.hour_mode import datetime_to_hourly_x  # noqa: F401
                LDT = jpype.JClass('java.time.LocalDateTime')

                def _shift_ldt(java_ldt):
                    """Shift java_ldt by 'delta' work-hour slots, preserving minutes."""
                    if java_ldt is None:
                        return None
                    # Fractional slot position from project origin (day_width=1)
                    slots = datetime_to_hourly_x(java_ldt, proj_start_qd, 1,
                                                 wh_start, clock_span, show_off)
                    new_slots  = slots + delta
                    wday       = int(new_slots // eff_span)
                    slot_frac  = new_slots % eff_span
                    hr         = eff_start_hr + int(slot_frac)
                    mi         = round((slot_frac % 1) * 60)
                    # Advance 'wday' working days from project origin (skip weekends)
                    d = proj_start_qd
                    if wday > 0:
                        cnt = 0
                        while cnt < wday:
                            d = d.addDays(1)
                            if d.dayOfWeek() not in (6, 7):
                                cnt += 1
                    elif wday < 0:
                        cnt = 0
                        while cnt > wday:
                            d = d.addDays(-1)
                            if d.dayOfWeek() not in (6, 7):
                                cnt -= 1
                    return LDT.of(d.year(), d.month(), d.day(), hr, mi, 0)

                def _add_working_hours(start_ldt, n_hours):
                    """Return a new LDT that is n_hours *working* hours after start_ldt.
                    Skips overnight gaps and weekends so a 1d task starting at 15:00
                    finishes at 15:00 the next working day, not at midnight."""
                    s_hr = int(start_ldt.getHour())
                    s_mi = int(start_ldt.getMinute())
                    wh_end = wh_start + clock_span   # e.g. 17
                    remaining_today = max(0.0, (wh_end * 60 - (s_hr * 60 + s_mi)) / 60.0)
                    d = QDate(int(start_ldt.getYear()),
                              int(start_ldt.getMonthValue()),
                              int(start_ldt.getDayOfMonth()))
                    remaining = float(n_hours)
                    if remaining <= remaining_today:
                        total_min = s_hr * 60 + s_mi + round(remaining * 60)
                        return LDT.of(d.year(), d.month(), d.day(),
                                      total_min // 60, total_min % 60, 0)
                    remaining -= remaining_today
                    work_day_h = clock_span
                    while True:
                        d = d.addDays(1)
                        while d.dayOfWeek() in (6, 7):
                            d = d.addDays(1)
                        if remaining <= work_day_h:
                            break
                        remaining -= work_day_h
                    total_min = wh_start * 60 + round(remaining * 60)
                    return LDT.of(d.year(), d.month(), d.day(),
                                  total_min // 60, total_min % 60, 0)

                if old_start:
                    new_start = _shift_ldt(old_start)
                    task.setStart(new_start)
                    # Derive finish by adding the MPXJ working duration (in hours) to
                    # new_start using working-hour arithmetic. Using calendar hours via
                    # Duration.between was wrong: a task starting at 15:00 with 9 working
                    # hours would finish at midnight instead of 15:00 the next working day.
                    if old_finish and new_start is not None:
                        try:
                            dur_obj   = task.getDuration()
                            dur_val   = float(str(dur_obj.getDuration()))
                            dur_units = str(dur_obj.getUnits()).upper() if dur_obj.getUnits() is not None else "DAYS"
                            # Mirror the unit logic already used in gantt_view._compute_finish_date:
                            # anything not HOUR/WEEK/MONTH is treated as days.
                            if 'HOUR' in dur_units:
                                dur_hours = dur_val
                            elif 'WEEK' in dur_units:
                                dur_hours = dur_val * 5 * clock_span
                            elif 'MONTH' in dur_units:
                                dur_hours = dur_val * 20 * clock_span
                            else:  # DAYS (any abbreviation: "d", "DAYS", "ELAPSED_DAYS", …)
                                dur_hours = dur_val * clock_span
                        except Exception:
                            # Last-resort fallback: use working-slot span of original dates
                            from views.hour_mode import datetime_to_hourly_x  # noqa: F401
                            old_s_slots = datetime_to_hourly_x(old_start, proj_start_qd, 1,
                                                               wh_start, clock_span, show_off)
                            old_f_slots = datetime_to_hourly_x(old_finish, proj_start_qd, 1,
                                                               wh_start, clock_span, show_off)
                            dur_hours = max(old_f_slots - old_s_slots, 1)
                        task.setFinish(_add_working_hours(new_start, dur_hours))
                project = self.logic.get_data()
                self.gantt_view.load_project(project, recompute_critical=True, preserve_scroll=True)
                self.task_view.blockSignals(True)
                self.task_view.load_project(project)
                self.task_view.blockSignals(False)
                self._mark_dirty()
                self._update_status_bar()
                self._history.push('tasks')
                return

            delta_days = delta
            raw_start_qd = _to_qdate(old_start.plusDays(delta_days)) if old_start else None
            non_working   = getattr(getattr(self.gantt_view, 'canvas', None), '_non_working_dates', set())
            snapped_qd    = _snap_to_workday(raw_start_qd, non_working) if raw_start_qd else raw_start_qd

            # If the drag lands on a non-working day, ask the user what to do
            if raw_start_qd and snapped_qd != raw_start_qd:
                from dialogs import NonWorkingDayDialog  # type: ignore
                task_name       = str(task.getName()) if task.getName() else "Task"
                raw_date_str    = raw_start_qd.toString("ddd dd MMM ''yy")
                snapped_date_str = snapped_qd.toString("ddd dd MMM ''yy")
                dlg = NonWorkingDayDialog(task_name, raw_date_str, snapped_date_str, self)
                dlg.exec_()
                if dlg.choice() == NonWorkingDayDialog.CANCEL:
                    return
                if dlg.choice() == NonWorkingDayDialog.SNAP:
                    chosen_qd = snapped_qd
                else:
                    chosen_qd = raw_start_qd
            else:
                chosen_qd = raw_start_qd

            new_start_java = None
            if old_start and chosen_qd:
                _LocalDateTime2 = jpype.JClass('java.time.LocalDateTime')
                new_start_java = _LocalDateTime2.of(
                    chosen_qd.year(), chosen_qd.month(), chosen_qd.day(),
                    old_start.getHour(), old_start.getMinute(), 0
                )
                task.setStart(new_start_java)
            if old_finish:
                # Recompute finish from new start + task duration (skipping weekends)
                # rather than shifting old_finish by delta_days, which preserves the
                # calendar span (including weekends) instead of the working-day span.
                finish_recomputed = False
                if new_start_java is not None:
                    try:
                        dur = task.getDuration()
                        if dur is not None:
                            dur_val = float(str(dur.getDuration()))
                            if dur_val > 0:
                                unit_str = str(dur.getUnits()).upper() if dur.getUnits() is not None else "DAYS"
                                if "HOUR" in unit_str:
                                    dur_val /= 8.0
                                elif "WEEK" in unit_str:
                                    dur_val *= 5.0
                                elif "MONTH" in unit_str:
                                    dur_val *= 20.0
                                new_start_qd = _to_qdate(new_start_java)
                                if new_start_qd:
                                    finish_qd = _add_working_days(new_start_qd, dur_val)
                                    _LocalDateTime = jpype.JClass('java.time.LocalDateTime')
                                    task.setFinish(_LocalDateTime.of(
                                        finish_qd.year(), finish_qd.month(), finish_qd.day(),
                                        old_finish.getHour(), old_finish.getMinute(), 0
                                    ))
                                    finish_recomputed = True
                    except Exception as e:
                        print(f"[WARN] finish recompute on drag: {e}")
                if not finish_recomputed:
                    # Fall back: shift by the actual calendar delta to the chosen start
                    actual_delta = old_start.until(new_start_java,
                        jpype.JClass('java.time.temporal.ChronoUnit').DAYS) if new_start_java else delta_days
                    task.setFinish(old_finish.plusDays(int(actual_delta)))
            # Recalculate lag for every predecessor relation on this task.
            # Moving the task by N days changes the gap by N days for all link types.
            try:
                from org.mpxj import Duration, TimeUnit  # type: ignore
                preds = list(task.getPredecessors() or [])
                for rel in preds:
                    pred_task = rel.getPredecessorTask()
                    if pred_task is None:
                        continue
                    rel_type_java = rel.getType()
                    old_lag = rel.getLag()
                    old_lag_days = 0.0
                    try:
                        if old_lag is not None:
                            old_lag_days = float(str(old_lag.getDuration()))
                            lu = str(old_lag.getUnits()).upper() if old_lag.getUnits() else "DAYS"
                            if "HOUR" in lu:
                                old_lag_days /= 8.0
                            elif "WEEK" in lu:
                                old_lag_days *= 5.0
                            elif "MONTH" in lu:
                                old_lag_days *= 20.0
                    except Exception:
                        old_lag_days = 0.0
                    new_lag_days = old_lag_days + delta_days
                    # Remove old relation and add with updated lag
                    task.getPredecessors().remove(rel)
                    import jpype  # type: ignore
                    lag_dur = Duration.getInstance(new_lag_days, TimeUnit.DAYS)
                    _RelBuilder = jpype.JClass('org.mpxj.Relation$Builder')
                    task.addPredecessor(_RelBuilder().predecessorTask(pred_task).type(rel_type_java).lag(lag_dur))
            except Exception as e:
                print(f"[WARN] lag update on drag: {e}")
        except Exception as e:
            print(f"[WARN] task drag commit: {e}")
        # Refresh all views so task table and Gantt are consistent
        project = self.logic.get_data()
        self.gantt_view.load_project(project, recompute_critical=True, preserve_scroll=True)
        self.task_view.blockSignals(True)
        self.task_view.load_project(project)
        self.task_view.blockSignals(False)
        self._mark_dirty()
        self._update_status_bar()
        self._history.push('tasks')
        self._history.push('baseline')

    def _on_gantt_task_edited(self):
        """A task was edited via the dialog opened from the Gantt chart."""
        project = self.logic.get_data()
        self.gantt_view.load_project(project, recompute_critical=True)
        self.task_view.blockSignals(True)
        self.task_view.load_project(project)
        self.task_view.blockSignals(False)
        self.task_sheet_view.load_project(project)
        self._mark_dirty()
        self._update_status_bar()
        self._history.push('tasks')
        self._history.push('baseline')

    def _on_show_task_in_gantt(self, task):
        """Scroll the Gantt canvas horizontally so the task's start bar is visible."""
        try:
            start_qd = _to_qdate(task.getStart())
        except Exception:
            start_qd = None
        if start_qd:
            self.gantt_view.scroll_to_date(start_qd)

    def _on_resource_usage_task_edited(self):
        """A task was edited via the double-click dialog in the Resource Usage view."""
        project = self.logic.get_data()
        self.gantt_view.load_project(project, recompute_critical=True)
        self.task_view.blockSignals(True)
        self.task_view.load_project(project)
        self.task_view.blockSignals(False)
        self.resource_usage_graph_view.load_project(project)
        self.task_sheet_view.load_project(project)
        self._mark_dirty()
        self._update_status_bar()
        self._history.push('tasks')

    def _on_resource_data_changed(self):
        project = self.logic.get_data()
        self.resource_view.load_project(project)
        self.gantt_view.load_project(project)
        self.team_planner_view.load_project(project)
        self.histogram_view.load_project(project, self.team_planner_view.canvas._non_working)
        self.task_view.blockSignals(True)
        self.task_view.load_project(project)
        self.task_view.blockSignals(False)
        self._update_status_bar()
        self._history.push('resources')

    def _on_dependency_data_changed(self):
        self.dependency_view.load_project(self.logic.get_data())
        self.gantt_view.load_project(self.logic.get_data())
        self._history.push('dependencies')

    def _on_team_planner_data_changed(self):
        """A task was rescheduled or reassigned in the Team Planner."""
        project = self.logic.get_data()
        # Refresh all other views so they stay consistent
        self.gantt_view.load_project(project, recompute_critical=True)
        self.task_view.blockSignals(True)
        self.task_view.load_project(project)
        self.task_view.blockSignals(False)
        self.resource_view.load_project(project)
        self.histogram_view.load_project(project, self.team_planner_view.canvas._non_working)
        self._update_status_bar()
        self._history.push('team_planner')
        self._history.push('tasks')
        self._history.push('baseline')

    def _on_task_sheet_data_changed(self):
        """Task was edited via the Task Sheet dialog — sync all other views."""
        project = self.logic.get_data()
        self.gantt_view.load_project(project, recompute_critical=True)
        self.task_view.blockSignals(True)
        self.task_view.load_project(project)
        self.task_view.blockSignals(False)
        self.task_sheet_view.load_project(project)
        self._update_status_bar()
        self._history.push('tasks')
        self._history.push('baseline')

    def _refresh_all_views(self):
        project = self.logic.get_data()
        self.gantt_view.load_project(project)
        self.task_view.load_project(project)
        self.resource_view.load_project(project)
        self.dependency_view.load_project(project)
        self.baseline_view.load_project(project)
        self.team_planner_view.load_project(project)
        self.histogram_view.load_project(project, self.team_planner_view.canvas._non_working)
        self.task_sheet_view.load_project(project)
        self.resource_usage_graph_view.load_project(project)
        self.timeline_view.load_project(project)
        self._refresh_cpm_results_view()
        self._toolbar.ribbon.set_project_open(project is not None)
        self.menuBar().set_close_enabled(project is not None)
        self._update_confluence_sync_btn()
        self._update_email_actions_state()
        self._update_status_bar()
        # Refresh the baseline combo with current baseline dates
        if project is not None:
            import baseline_manager  # type: ignore
            active = baseline_manager.get_active_baselines(project)
            self._toolbar.ribbon.update_baseline_list(active)

    def _update_status_bar(self):
        project = self.logic.get_data()
        if project is None:
            self._status_label.setText("Ready")
            self._update_cpm_status()
            return
        try:
            total = sum(1 for t in project.getTasks()    if t.getName() is not None)
            res   = sum(1 for r in project.getResources() if r.getName() is not None)
            self._status_label.setText(
                f"Tasks: {total}  |  Resources: {res}"
            )
        except Exception:
            self._status_label.setText("Project loaded")
        self._update_cpm_status()

    def _update_cpm_status(self):
        """Update the compact CPM summary label in the status bar."""
        if not hasattr(self, '_cpm_summary_label'):
            return
        project = self.logic.get_data()
        if project is None:
            self._cpm_summary_label.setText("Critical: —")
            return
        try:
            canvas = self.gantt_view.canvas
            n_critical = len(getattr(canvas, '_critical_ids', set()))
            float_data = getattr(canvas, '_float_data', {}) or {}
            if float_data:
                all_ef = [v.get('ef') for v in float_data.values() if v.get('ef')]
                all_es = [v.get('es') for v in float_data.values() if v.get('es')]
                if all_ef and all_es:
                    span = max(all_ef) - min(all_es)
                    wdh = getattr(canvas, '_work_day_hours', 8) or 8
                    dur_days = round(span.total_seconds() / 3600 / wdh, 1)
                    self._cpm_summary_label.setText(
                        f"Duration: {dur_days}d · Critical: {n_critical}"
                    )
                    return
            self._cpm_summary_label.setText(f"Critical: {n_critical}")
        except Exception:
            self._cpm_summary_label.setText("Critical: —")

    def _on_cpm_task_double_clicked(self, task_id: int):
        """Open TaskDialog for the task double-clicked in the CPM Results panel."""
        project = self.logic.get_data()
        if project is None:
            return
        task = None
        try:
            for t in project.getTasks():
                try:
                    if int(str(t.getID())) == task_id:
                        task = t
                        break
                except Exception:
                    pass
        except Exception:
            return
        if task is None:
            return
        from dialogs import TaskDialog  # type: ignore
        canvas = self.gantt_view.canvas
        sidecar = (self._current_file_path + ".custom-props.json") if self._current_file_path else ""
        dlg = TaskDialog(
            task, project, self,
            timeline_view=getattr(self, 'timeline_view', None),
            critical_ids=getattr(canvas, '_critical_ids', set()),
            float_data=getattr(canvas, '_float_data', {}),
            task_jira_data={},
        )
        if dlg.exec_() == dlg.Accepted:
            dlg.apply_to_task()
            self._on_task_data_changed()
            self._mark_dirty()

    def _refresh_cpm_results_view(self):
        """Push latest CPM float data into the CPM Results panel."""
        if not hasattr(self, 'cpm_results_view'):
            return
        try:
            canvas = self.gantt_view.canvas
            float_data = getattr(canvas, '_float_data', {}) or {}
            tasks      = getattr(canvas, 'tasks', []) or []
            wdh        = getattr(canvas, '_work_day_hours', 8) or 8
            self.cpm_results_view.refresh(float_data, tasks, wdh)
        except Exception:
            pass

    # ------------------------------------------------------------------ #
    # Public actions (called by menu, toolbar, and programmatically)      #
    # ------------------------------------------------------------------ #

    def open_project_info(self):
        """Open the Project Information dialog (Project > Project Information)."""
        project = self.logic.get_data()
        if project is None:
            QMessageBox.information(self, "Project Information", "No project is open.")
            return
        from dialogs import ProjectInfoDialog  # type: ignore
        dlg = ProjectInfoDialog(project, self, file_path=self._current_file_path)
        if dlg.exec_() == dlg.Accepted:
            dlg.apply()
            # Re-sync enterprise custom field values into the in-memory MPXJ
            # project — the dialog writes them to the XML on disk but not to
            # the live project object that _update_confluence_sync_btn reads.
            fp = self._current_file_path
            if fp and fp.lower().endswith('.xml'):
                self.file_handler._patch_load_enterprise_cf_values(project, fp)
            self._refresh_all_views()
            self._update_confluence_sync_btn()

    def open_project_file(self, file_path):
        """Open a project file programmatically (e.g. from --open argument)."""
        import time as _time
        _t0 = _time.monotonic()
        try:
            opened = run_indeterminate(
                self, f"Opening {os.path.basename(file_path)}\u2026",
                self.file_handler.open_project, file_path, self,
            )
        except Exception:
            opened = False
        record_timing("file_open", _time.monotonic() - _t0, bool(opened))
        if opened:
            self._current_file_path = file_path
            self._refresh_all_views()
            self._load_timeline_json()     # load after _refresh_all_views clears it
            self._load_splits()            # load split data from MPXJ (fallback)
            self._load_splits_json()       # override with sidecar JSON if present
            # Load resource thumbnails sidecar and wire into ResourceDialog
            try:
                from dialogs import set_resource_thumbnail_store  # type: ignore
                _thumb_store, _dept_store = self._load_thumbnails_json()
                set_resource_thumbnail_store(
                    _thumb_store,
                    _dept_store,
                    self._thumbnails_json_path(),
                )
            except Exception as _e:
                print(f"[WARN] resource sidecar load: {_e}")
            # Load CPM settings from sidecar and apply to canvas + canvas recompute
            self._cpm_cfg = self.file_handler.load_cpm_settings(file_path)
            self._apply_cpm_settings()
            self._history.push_all()
            self._add_to_recent(file_path)
            # MPP can never be saved back — keep Save enabled so the user can
            # immediately Save As.  For XML (and others), no unsaved changes yet.
            ext = os.path.splitext(file_path)[1].lower()
            if ext == '.mpp':
                self._mark_dirty()
            else:
                self._mark_clean()
            # Detect VCS repository and update ribbon
            try:
                from integrations import version_control_integration as vcs  # type: ignore
                vcs.init(file_path)
                self._update_vcs_ribbon_state()
            except Exception:
                pass
        else:
            QMessageBox.critical(self, "Error", f"Failed to open: {file_path}")

    def zoom_in(self):
        self.gantt_view.zoom_in()

    def zoom_out(self):
        self.gantt_view.zoom_out()

    def _on_zoom_slider(self, value: int):
        """Slider dragged — push the new day_width into all timeline views."""
        self.gantt_view.set_day_width(value)
        self.team_planner_view.set_day_width(value)
        self.histogram_view.set_day_width(value)
        self.resource_usage_graph_view.set_day_width(value)

    def _on_gantt_zoom_changed(self, day_width: int):
        """Canvas zoom changed (keyboard shortcut or slider) — sync label + slider."""
        pct = round(day_width / self._zoom_def * 100)
        self._zoom_pct_label.setText(f"{pct}%")
        self._zoom_slider.blockSignals(True)
        self._zoom_slider.setValue(day_width)
        self._zoom_slider.blockSignals(False)
        # Slider signals are blocked above to prevent feedback, so push directly.
        self.team_planner_view.set_day_width(day_width)
        self.histogram_view.set_day_width(day_width)
        self.resource_usage_graph_view.set_day_width(day_width)

    def open_keepass_settings(self):
        """Open the KeePass configuration dialog (Settings ? KeePass Configuration…)."""
        from settings_dialogs import KeePassConfigDialog  # type: ignore
        dlg = KeePassConfigDialog(self._settings_manager, self)
        dlg.exec_()

    def open_jira_settings(self):
        """Open the Jira servers configuration dialog (Settings → Jira Servers…)."""
        from settings_dialogs import JiraServersDialog  # type: ignore
        dlg = JiraServersDialog(self._settings_manager, self)
        dlg.exec_()

    def open_jira_config(self):
        """Open the Jira sync configuration dialog (ribbon Jira Sync Config button)."""
        from settings_dialogs import JiraSyncConfigDialog  # type: ignore
        project = self.logic.get_data()
        dlg = JiraSyncConfigDialog(self._settings_manager, project, self)
        if dlg.exec_() == dlg.Accepted and project is not None:
            # Filter may have changed — mark dirty so the custom properties are saved
            self._mark_dirty()

    def run_jira_sync(self):
        """Synchronize tasks from Jira issues into the open project (normal mode)."""
        self._run_jira_sync_impl()

    def run_jira_sync_changed_since(self):
        """Sync from Jira using only issues changed since the last sync timestamp."""
        self._run_jira_sync_impl(force_incremental=True)

    def run_jira_sync_full_resync(self):
        """Full resync from Jira: ignore the last-sync timestamp and re-fetch all issues."""
        self._run_jira_sync_impl(force_full_resync=True)

    def _run_jira_sync_impl(self, force_incremental: bool = False,
                             force_full_resync: bool = False) -> None:
        """Core Jira → Project sync implementation shared by all sync modes."""
        import json as _json
        project = self.logic.get_data()
        if project is None:
            QMessageBox.information(self, "Jira Sync", "No project is open.")
            return

        # Read current jira2project config to check whether a filter is set
        j2p: dict = {}
        try:
            cp = project.getProjectProperties().getCustomProperties()
            if cp is not None:
                raw = cp.get("jira2project")
                if raw:
                    j2p = _json.loads(str(raw))
        except Exception:
            pass

        if not j2p.get("filter"):
            # Not configured — open the config dialog first
            reply = QMessageBox.question(
                self, "Jira Sync",
                "No Jira filter is configured for this project.\n"
                "Open the Jira Sync Config dialog to set one?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if reply == QMessageBox.Yes:
                self.open_jira_config()
            return

        server_name = j2p.get("server", "")
        servers = self._settings_manager.get_jira_servers() if hasattr(self._settings_manager, "get_jira_servers") else []
        server = next((s for s in servers if s.get("name") == server_name), None)
        if server is None and servers:
            server = servers[0]
        if server is None:
            QMessageBox.warning(
                self, "Jira Sync",
                "No Jira server is configured.\n"
                "Please add a server in Settings → Jira Servers…",
            )
            return

        # If the server uses KeePass and it is locked, offer to unlock first
        if server.get("auth_mode") == "keepass" and not self._settings_manager.is_keepass_unlocked():
            from PyQt5.QtWidgets import QInputDialog, QLineEdit  # type: ignore
            answer = QMessageBox.question(
                self,
                "KeePass Locked",
                "The KeePass database is locked.\n\nDo you want to unlock it now?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if answer != QMessageBox.Yes:
                return
            ok, _ = self._settings_manager.auto_unlock_keepass()
            if not ok:
                pwd, entered = QInputDialog.getText(
                    self,
                    "KeePass Master Password",
                    "Enter KeePass master password:",
                    QLineEdit.Password,
                )
                if not entered:
                    return
                ok, err = self._settings_manager.unlock_keepass(pwd)
                if not ok:
                    QMessageBox.warning(
                        self, "Unlock Failed",
                        f"Could not open KeePass database:\n{err}",
                    )
                    return

        # Get authenticated client
        from integrations.jira_integration import get_jira_client  # type: ignore
        jira_client, err = get_jira_client(server)
        if jira_client is None:
            QMessageBox.critical(self, "Jira Sync",
                                 f"Could not connect to Jira:\n{err}")
            return

        # Determine sidecar path
        sidecar_path = ""
        if self._current_file_path:
            sidecar_path = self._current_file_path + ".custom-props.json"

        # Build mode label for the title bar
        if force_incremental:
            mode_label = "Jira Sync (Changed since last sync)"
        elif force_full_resync:
            mode_label = "Jira Sync (Full resync)"
        else:
            mode_label = "Jira Sync"

        # Run sync in a background thread with a modal progress dialog
        worker = _JiraSyncWorker(project, server, jira_client, sidecar_path,
                                 force_incremental=force_incremental,
                                 force_full_resync=force_full_resync)

        # Wire interactive callbacks: signal comes from worker thread, slot
        # runs on main thread (QueuedConnection), sets response and unblocks worker.
        worker._need_relink.connect(
            lambda k, si, ii: worker._set_response(self._jira_sync_relink_cb(k, si, ii)))
        worker._need_conflict.connect(
            lambda k, t: worker._set_response(self._jira_sync_conflict_cb(k, t)))
        worker._need_orphan.connect(
            lambda k, t: worker._set_response(self._jira_sync_orphan_cb(k, t)))

        ok, err_text = run_with_progress(
            self, mode_label, worker, cancellable=True, indeterminate=False)

        record_timing("jira_sync", worker.elapsed_seconds, ok)

        if not ok and err_text == "Cancelled by user":
            return

        result = worker.result
        if not ok and not result.get("errors"):
            QMessageBox.critical(self, "Jira Sync", f"Sync failed:\n{err_text}")
            return

        # Push post-sync snapshot so the entire sync is a single undoable step.
        # (Same pattern as _on_task_data_changed: push after the change.)
        if hasattr(self, '_history') and self._history is not None:
            self._history.push('tasks')
            self._history.push('resources')

        # Refresh views and mark dirty
        self._refresh_all_views()
        self._mark_dirty()

        # Show result summary
        errs = result.get("errors", [])
        msg = (
            f"Sync complete.\n\n"
            f"  Created: {result.get('created', 0)}\n"
            f"  Updated: {result.get('updated', 0)}\n"
            f"  Skipped: {result.get('skipped', 0)}\n"
        )
        if errs:
            msg += f"\nWarnings/Errors ({len(errs)}):\n" + "\n".join(f"  • {e}" for e in errs[:10])
            if len(errs) > 10:
                msg += f"\n  … and {len(errs) - 10} more"
            QMessageBox.warning(self, "Jira Sync", msg)
        else:
            QMessageBox.information(self, "Jira Sync", msg)

    # ------------------------------------------------------------------
    # Jira sync interactive callbacks (shown on the main thread)
    # ------------------------------------------------------------------

    def _jira_sync_relink_cb(self, issue_key: str, stored_id: str, incoming_id: str) -> str:
        """Ask whether to skip or relink a Jira issue whose stored ID changed."""
        from PyQt5.QtWidgets import QPushButton  # type: ignore
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Jira Sync \u2014 ID Changed")
        msg_box.setIcon(QMessageBox.Question)
        msg_box.setText(
            f"Jira issue <b>{issue_key}</b> has a different ID than the one stored "
            f"for the linked local task.<br><br>"
            f"Stored ID: <tt>{stored_id}</tt><br>"
            f"Incoming ID: <tt>{incoming_id}</tt><br><br>"
            "Do you want to <b>relink</b> the local task to the new Jira issue?<br>"
            "<i>(Relink will overwrite all mapped fields with the new issue data.)</i>"
        )
        btn_skip = msg_box.addButton("Skip", QMessageBox.RejectRole)
        btn_relink = msg_box.addButton("Relink", QMessageBox.AcceptRole)
        msg_box.setDefaultButton(btn_skip)
        msg_box.exec_()
        return "relink" if msg_box.clickedButton() is btn_relink else "skip"

    def _jira_sync_conflict_cb(self, issue_key: str, task_name: str) -> str:
        """Ask how to resolve a local/remote conflict for a Jira issue."""
        from PyQt5.QtWidgets import QPushButton  # type: ignore
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Jira Sync \u2014 Conflict")
        msg_box.setIcon(QMessageBox.Question)
        msg_box.setText(
            f"Local task <b>{task_name}</b> linked to <b>{issue_key}</b> "
            "has been edited locally since the last sync.<br><br>"
            "How do you want to resolve this conflict?"
        )
        btn_jira = msg_box.addButton("Prefer Jira", QMessageBox.AcceptRole)
        btn_local = msg_box.addButton("Prefer Local", QMessageBox.AcceptRole)
        btn_skip = msg_box.addButton("Skip", QMessageBox.RejectRole)
        msg_box.setDefaultButton(btn_skip)
        msg_box.exec_()
        clicked = msg_box.clickedButton()
        if clicked is btn_jira:
            return "prefer_jira"
        if clicked is btn_local:
            return "prefer_local"
        return "skip"

    def _jira_sync_orphan_cb(self, jira_key: str, task_name: str) -> str:
        """Ask what to do with an orphaned task (no longer in Jira results)."""
        from PyQt5.QtWidgets import QPushButton  # type: ignore
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Jira Sync \u2014 Orphaned Task")
        msg_box.setIcon(QMessageBox.Question)
        msg_box.setText(
            f"Task <b>{task_name}</b> is linked to <b>{jira_key}</b> which is no "
            "longer in the Jira results (deleted, moved, or out of scope).<br><br>"
            "What do you want to do with this orphaned task?"
        )
        btn_keep = msg_box.addButton("Keep", QMessageBox.AcceptRole)
        btn_unlink = msg_box.addButton("Unlink", QMessageBox.AcceptRole)
        btn_close = msg_box.addButton("Close", QMessageBox.AcceptRole)
        btn_delete = msg_box.addButton("Delete", QMessageBox.DestructiveRole)
        msg_box.setDefaultButton(btn_keep)
        msg_box.exec_()
        clicked = msg_box.clickedButton()
        if clicked is btn_unlink:
            return "unlink"
        if clicked is btn_close:
            return "close"
        if clicked is btn_delete:
            return "delete"
        return "keep"

    def run_jira_push(self):
        """Push project task changes to Jira issues (Project → Jira direction)."""
        self._run_jira_push_impl()

    def run_jira_push_dry_run(self):
        """Show a dry-run preview of the Jira push without executing any API calls."""
        self._run_jira_push_impl(force_dry_run=True)

    def _run_jira_push_impl(self, force_dry_run: bool = False) -> None:
        """Core Project → Jira push implementation shared by normal and dry-run modes."""
        import json as _json
        project = self.logic.get_data()
        if project is None:
            QMessageBox.information(self, "Jira Sync", "No project is open.")
            return

        # Read p2j config
        p2j: dict = {}
        try:
            cp = project.getProjectProperties().getCustomProperties()
            if cp is not None:
                raw = cp.get("project2jira")
                if raw:
                    p2j = _json.loads(str(raw))
        except Exception:
            pass

        # If no fields are configured, open the config dialog
        if not p2j.get("fields") and not p2j.get("issue_type_map"):
            reply = QMessageBox.question(
                self, "Jira Sync",
                "No Project \u2192 Jira export is configured for this project.\n"
                "Open the Jira Sync Config dialog to configure it?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if reply == QMessageBox.Yes:
                self.open_jira_config()
            return

        # Determine server (shared with j2p config)
        server_name = p2j.get("server", "")
        j2p: dict = {}
        try:
            cp2 = project.getProjectProperties().getCustomProperties()
            if cp2 is not None:
                raw2 = cp2.get("jira2project")
                if raw2:
                    j2p = _json.loads(str(raw2))
        except Exception:
            pass
        if not server_name:
            server_name = j2p.get("server", "")
        servers = self._settings_manager.get_jira_servers() if hasattr(self._settings_manager, "get_jira_servers") else []
        server = next((s for s in servers if s.get("name") == server_name), None)
        if server is None and servers:
            server = servers[0]
        if server is None:
            QMessageBox.warning(
                self, "Jira Sync",
                "No Jira server is configured.\n"
                "Please add a server in Settings \u2192 Jira Servers\u2026",
            )
            return

        # KeePass unlock if needed
        if server.get("auth_mode") == "keepass" and not self._settings_manager.is_keepass_unlocked():
            from PyQt5.QtWidgets import QInputDialog, QLineEdit  # type: ignore
            answer = QMessageBox.question(
                self, "KeePass Locked",
                "The KeePass database is locked.\n\nDo you want to unlock it now?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if answer != QMessageBox.Yes:
                return
            ok, _ = self._settings_manager.auto_unlock_keepass()
            if not ok:
                pwd, entered = QInputDialog.getText(
                    self, "KeePass Master Password",
                    "Enter KeePass master password:",
                    QLineEdit.Password,
                )
                if not entered:
                    return
                ok, err = self._settings_manager.unlock_keepass(pwd)
                if not ok:
                    QMessageBox.warning(self, "Unlock Failed", f"Could not open KeePass database:\n{err}")
                    return

        # Get authenticated Jira client
        from integrations.jira_integration import get_jira_client  # type: ignore
        jira_client, err = get_jira_client(server)
        if jira_client is None:
            QMessageBox.critical(self, "Jira Sync", f"Could not connect to Jira:\n{err}")
            return

        # Sidecar path
        sidecar_path = ""
        if self._current_file_path:
            sidecar_path = self._current_file_path + ".custom-props.json"

        dry_run = force_dry_run or bool(p2j.get("dry_run", True))

        from integrations import jira_sync as _jira_sync  # type: ignore

        if dry_run:
            # --- Dry-run pass: collect preview actions -----------------------
            try:
                dry_result = _jira_sync.run_push_to_jira(
                    project, server, jira_client, sidecar_path
                )
            except Exception as exc:
                QMessageBox.critical(self, "Jira Sync", f"Preview failed:\n{exc}")
                return

            actions = dry_result.get("preview_actions", [])
            if not actions:
                skipped = dry_result.get("skipped", 0)
                errors  = dry_result.get("errors", [])
                info = (
                    "No tasks qualify for export with the current configuration.\n\n"
                    f"Skipped: {skipped}\n"
                )
                if errors:
                    info += "Errors:\n" + "\n".join(f"\u2022 {e}" for e in errors[:5])
                QMessageBox.information(self, "Jira Sync \u2014 Preview", info)
                return

            from settings_dialogs import JiraPushPreviewDialog  # type: ignore
            dlg = JiraPushPreviewDialog(actions, self)
            if dlg.exec_() != dlg.Accepted:
                return

            included_uids = dlg.get_included_task_uids()
            if not included_uids:
                QMessageBox.information(self, "Jira Sync", "No tasks selected for export.")
                return

            # --- Execute actual push with selected tasks ----------------------
            import java.util  # type: ignore
            from integrations.jira_integration import JIRA2PROJECT_PROP as _J2P_PROP  # type: ignore
            from integrations.jira_integration import PROJECT2JIRA_PROP as _P2J_PROP  # type: ignore
            import json as _json2

            def _write_p2j(config_dict: dict):
                try:
                    props = project.getProjectProperties()
                    cp = props.getCustomProperties()
                    new_cp = java.util.HashMap()
                    if cp is not None:
                        for key in cp.keySet():
                            if str(key) != _P2J_PROP:
                                new_cp.put(key, cp.get(key))
                    new_cp.put(_P2J_PROP, _json2.dumps(config_dict, ensure_ascii=False))
                    props.setCustomProperties(new_cp)
                except Exception:
                    pass

            p2j_live = dict(p2j)
            p2j_live["dry_run"] = False
            _write_p2j(p2j_live)

            try:
                result = _jira_sync.run_push_to_jira(
                    project, server, jira_client, sidecar_path,
                    included_task_uids=included_uids,
                )
            except Exception as exc:
                _write_p2j(p2j)  # restore
                QMessageBox.critical(self, "Jira Sync", f"Push failed:\n{exc}")
                return
            finally:
                _write_p2j(p2j)  # always restore original setting

        else:
            # Dry-run disabled — execute directly
            try:
                result = _jira_sync.run_push_to_jira(
                    project, server, jira_client, sidecar_path
                )
            except Exception as exc:
                QMessageBox.critical(self, "Jira Sync", f"Push failed:\n{exc}")
                return

        # Mark dirty so the sidecar change is preserved
        self._mark_dirty()

        # Show result summary
        errs = result.get("errors", [])
        msg = (
            f"Push complete.\n\n"
            f"  Created:      {result.get('created', 0)}\n"
            f"  Updated:      {result.get('updated', 0)}\n"
            f"  Transitioned: {result.get('transitioned', 0)}\n"
            f"  Skipped:      {result.get('skipped', 0)}\n"
        )
        if errs:
            msg += f"\nWarnings/Errors ({len(errs)}):\n" + "\n".join(f"  \u2022 {e}" for e in errs[:10])
            if len(errs) > 10:
                msg += f"\n  \u2026 and {len(errs) - 10} more"
            QMessageBox.warning(self, "Jira Sync", msg)
        else:
            QMessageBox.information(self, "Jira Sync", msg)

    def open_confluence_calendar_config(self):
        """Open the Confluence Calendar configuration dialog (ribbon Calendar Config button)."""
        from settings_dialogs import ConfluenceCalendarConfigDialog  # type: ignore
        project = self.logic.get_data()
        dlg = ConfluenceCalendarConfigDialog(self._settings_manager, project, self)
        if dlg.exec_() == dlg.Accepted and project is not None:
            # Calendar props may have changed — re-evaluate the sync button state
            self._update_confluence_sync_btn()
            self._mark_dirty()

    def open_email_configs(self):
        """Open the Email Configurations manager dialog (ribbon Email Accounts button)."""
        from settings_dialogs import EmailServersDialog  # type: ignore
        dlg = EmailServersDialog(self._settings_manager, self)
        dlg.exec_()
        self._update_email_actions_state()

    def open_email_config(self):
        """Open the Email configuration dialog (ribbon Email Config button)."""
        from settings_dialogs import EmailConfigDialog  # type: ignore
        project = self.logic.get_data()
        dlg = EmailConfigDialog(self._settings_manager, project=project, parent=self)
        if dlg.exec_() == dlg.Accepted and project is not None:
            self._mark_dirty()
        self._update_email_actions_state()

    # ---------------------------------------------------------------- #
    # Email Export actions                                               #
    # ---------------------------------------------------------------- #

    def _get_view_name_for_export(self) -> str:
        """Return a human-readable name for the currently active view tab."""
        _TAB_NAMES = {
            TAB_GANTT:          "Gantt Chart",
            TAB_RESOURCES:      "Resource Sheet",
            TAB_DEPENDENCIES:   "Dependencies",
            TAB_BASELINE:       "Baseline View",
            TAB_TEAM_PLANNER:   "Team Planner",
            TAB_TASK_SHEET:     "Task Sheet",
            TAB_RESOURCE_USAGE: "Resource Usage Graph",
            TAB_CPM:            "CPM Results",
        }
        return _TAB_NAMES.get(self.tabs.currentIndex(), "Current View")

    def _export_current_view_svg(self, output_path: str) -> None:
        """Render the current view to *output_path* as an SVG file."""
        import os
        idx = self.tabs.currentIndex()

        if idx == TAB_GANTT:
            from export_gantt import export_gantt_svg  # type: ignore
            export_gantt_svg(self.gantt_view.canvas, output_path)

        elif idx == TAB_TEAM_PLANNER:
            from PyQt5.QtSvg import QSvgGenerator  # type: ignore
            from PyQt5.QtCore import QSize, QRect  # type: ignore
            from PyQt5.QtGui import QPainter  # type: ignore
            w = self.team_planner_view.width()
            h = self.team_planner_view.height()
            gen = QSvgGenerator()
            gen.setFileName(output_path)
            gen.setSize(QSize(w, h))
            gen.setViewBox(QRect(0, 0, w, h))
            gen.setTitle("Team Planner")
            painter = QPainter(gen)
            self.team_planner_view.render(painter)
            painter.end()

        elif idx == TAB_RESOURCE_USAGE:
            from PyQt5.QtSvg import QSvgGenerator  # type: ignore
            from PyQt5.QtCore import QSize, QRect  # type: ignore
            from PyQt5.QtGui import QPainter  # type: ignore
            w = self.resource_usage_graph_view.width()
            h = self.resource_usage_graph_view.height()
            gen = QSvgGenerator()
            gen.setFileName(output_path)
            gen.setSize(QSize(w, h))
            gen.setViewBox(QRect(0, 0, w, h))
            gen.setTitle("Resource Usage Graph")
            painter = QPainter(gen)
            self.resource_usage_graph_view.render(painter)
            painter.end()

        elif idx == TAB_TIMELINE:  # TAB_TIMELINE == -1; never a real tab index
            self.timeline_view.export_svg(output_path)

        else:
            # Fallback: render the current tab widget's page
            from PyQt5.QtSvg import QSvgGenerator  # type: ignore
            from PyQt5.QtCore import QSize, QRect  # type: ignore
            from PyQt5.QtGui import QPainter  # type: ignore
            widget = self.tabs.currentWidget()
            if widget is None:
                raise RuntimeError("No view is currently visible.")
            w = widget.width()
            h = widget.height()
            gen = QSvgGenerator()
            gen.setFileName(output_path)
            gen.setSize(QSize(w, h))
            gen.setViewBox(QRect(0, 0, w, h))
            painter = QPainter(gen)
            widget.render(painter)
            painter.end()

    def open_email_export(self):
        """Compose and send the current view as an SVG email attachment."""
        project = self.logic.get_data()
        if project is None:
            QMessageBox.information(self, "Email Export", "No project is open.")
            return

        from integrations import email_integration  # type: ignore
        configs = self._settings_manager.get_email_configs()
        active_name = self._settings_manager.get_active_email_config_name()
        view_name = self._get_view_name_for_export()

        from dialogs import EmailExportDialog  # type: ignore
        dlg = EmailExportDialog(project, configs, active_name, view_name=view_name, parent=self)
        if dlg.exec_() != dlg.Accepted:
            return

        to_addr  = dlg.get_to()
        subject  = dlg.get_subject()
        body     = dlg.get_body()
        cfg      = dlg.get_selected_config()

        if not to_addr:
            QMessageBox.warning(self, "Email Export", "Please enter a recipient email address.")
            return
        if not subject:
            QMessageBox.warning(self, "Email Export", "Please enter a subject.")
            return
        if cfg is None:
            QMessageBox.warning(self, "Email Export",
                                "No email account is configured. Use Email Accounts to add one.")
            return

        # Export view to temp SVG
        import tempfile
        import os
        try:
            with tempfile.NamedTemporaryFile(suffix=".svg", delete=False) as tf:
                svg_path = tf.name
            self._export_current_view_svg(svg_path)
            with open(svg_path, "rb") as fh:
                svg_bytes = fh.read()
            os.unlink(svg_path)
        except Exception as exc:
            QMessageBox.critical(self, "Email Export", f"Failed to export view to SVG:\n{exc}")
            return

        safe_view = "".join(c if c.isalnum() or c in (" ", "-", "_") else "_" for c in view_name)
        attachment_name = f"{safe_view.replace(' ', '_')}.svg"

        ok, err = email_integration.send_email(
            to=to_addr,
            subject=subject,
            body=body,
            attachments=[(attachment_name, svg_bytes)],
            config=cfg,
        )

        # Track for debug dump
        import datetime
        email_integration._last_export_result = {
            "timestamp":    datetime.datetime.now().isoformat(timespec="seconds"),
            "mode":         "single",
            "view":         view_name,
            "config_name":  cfg.get("name", ""),
            "sent":         1 if ok else 0,
            "skipped":      0,
            "failed":       0 if ok else 1,
        }

        if ok:
            QMessageBox.information(self, "Email Export",
                                    f"Email sent successfully to:\n{to_addr}")
        else:
            QMessageBox.critical(self, "Email Export", f"Failed to send email:\n{err}")

    def open_email_export_bulk(self):
        """Send per-resource Gantt SVG emails to all resources with known email addresses."""
        project = self.logic.get_data()
        if project is None:
            QMessageBox.information(self, "Email Export", "No project is open.")
            return

        from integrations import email_integration  # type: ignore
        from dialogs import EmailExportDialog, BulkEmailPreviewDialog, BulkEmailSummaryDialog  # type: ignore
        from dialogs import _load_email_templates, _apply_template_placeholders  # type: ignore

        configs = self._settings_manager.get_email_configs()
        active_name = self._settings_manager.get_active_email_config_name()

        # Step 1: Compose screen (template/account selection, body/subject template)
        compose_dlg = EmailExportDialog(
            project, configs, active_name,
            view_name="Gantt Chart (per-resource)",
            parent=self,
        )
        if compose_dlg.exec_() != compose_dlg.Accepted:
            return

        cfg            = compose_dlg.get_selected_config()
        subject_tmpl   = compose_dlg.get_subject()
        body_tmpl      = compose_dlg.get_body()

        if cfg is None:
            QMessageBox.warning(self, "Email Export",
                                "No email account is configured. Use Email Accounts to add one.")
            return

        # Step 2: Build resource list with emails
        import datetime
        import os
        today = datetime.date.today().isoformat()
        project_name = ""
        project_manager = ""
        try:
            props = project.getProjectProperties()
            project_name    = str(props.getName() or "")
            project_manager = str(props.getAuthor() or "")
        except Exception:
            pass

        preview_rows = []
        try:
            for res in project.getResources():
                try:
                    name = str(res.getName() or "")
                    if not name:
                        continue
                    email_addr = ""
                    try:
                        email_addr = str(res.getEmailAddress() or "")
                    except Exception:
                        pass

                    placeholders = {
                        "resource_name":   name,
                        "project_name":    project_name,
                        "project_manager": project_manager,
                        "date":            today,
                        "view_name":       "Gantt Chart",
                    }
                    resolved_subject = _apply_template_placeholders(subject_tmpl, placeholders)
                    preview_rows.append({
                        "resource_name": name,
                        "email":         email_addr,
                        "subject":       resolved_subject,
                        "body":          _apply_template_placeholders(body_tmpl, placeholders),
                    })
                except Exception:
                    pass
        except Exception as exc:
            QMessageBox.critical(self, "Email Export",
                                 f"Failed to read resources from project:\n{exc}")
            return

        if not preview_rows:
            QMessageBox.information(self, "Email Export",
                                    "No resources found in the project.")
            return

        # Step 3: Preview dialog (checkboxes per resource)
        preview_dlg = BulkEmailPreviewDialog(preview_rows, parent=self)
        if preview_dlg.exec_() != preview_dlg.Accepted:
            return

        included = preview_dlg.get_included_rows()
        if not included:
            QMessageBox.information(self, "Email Export",
                                    "No rows selected — no emails sent.")
            return

        # Step 4: Export per-resource SVG files into a temp directory then send
        import tempfile
        import shutil
        from export_gantt import export_resource_gantt_svg  # type: ignore

        svg_dir = tempfile.mkdtemp(prefix="po_email_export_")
        try:
            # Export all per-resource SVGs in one pass (indeterminate spinner)
            try:
                run_indeterminate(
                    self, "Exporting per-resource Gantt SVGs…",
                    export_resource_gantt_svg, self.gantt_view.canvas, svg_dir,
                )
            except Exception as exc:
                QMessageBox.critical(self, "Email Export",
                                     f"SVG export failed:\n{exc}")
                return

            # Send emails via background worker with a modal progress dialog
            worker = _BulkEmailSendWorker(included, svg_dir, email_integration, cfg)
            ok, _msg = run_with_progress(
                self,
                f"Sending emails — 0/{len(included)}…",
                worker,
                cancellable=True,
            )
            results = worker.results
            skipped = worker.skipped
        finally:
            try:
                shutil.rmtree(svg_dir, ignore_errors=True)
            except Exception:
                pass

        # Track for debug dump
        sent_count   = sum(1 for r in results if r.get("success"))
        failed_count = sum(1 for r in results if not r.get("success") and r.get("email"))
        email_integration._last_export_result = {
            "timestamp":    datetime.datetime.now().isoformat(timespec="seconds"),
            "mode":         "bulk",
            "view":         "Gantt Chart (per-resource)",
            "config_name":  cfg.get("name", ""),
            "sent":         sent_count,
            "skipped":      skipped,
            "failed":       failed_count,
        }

        # Step 5: Summary dialog
        summary_dlg = BulkEmailSummaryDialog(results, parent=self)
        summary_dlg.exec_()

    # ---------------------------------------------------------------- #
    # Version Control Integration actions                              #
    # ---------------------------------------------------------------- #

    def _update_vcs_ribbon_state(self):
        """Show / hide the VCS ribbon tab and update button states."""
        from integrations import version_control_integration as vcs  # type: ignore
        ribbon = self._toolbar.ribbon
        is_repo = vcs.is_configured()
        ribbon.set_vcs_tab_visible(is_repo)
        if is_repo:
            ribbon.set_vcs_repo_type(vcs.get_vcs_type())
            # Show "Register with VCS" only for SVN when the project file is unversioned
            if vcs.get_vcs_type() == "svn" and self._current_file_path:
                try:
                    is_unversioned = vcs.svn_is_unversioned(self._current_file_path)
                    ribbon.set_vcs_register_state(is_unversioned, enabled=True)
                except Exception:
                    ribbon.set_vcs_register_state(False)
            else:
                ribbon.set_vcs_register_state(False)
        else:
            ribbon.set_vcs_register_state(False)

    def run_vcs_svn_register(self):
        """Register the unversioned project file with SVN (``svn add``)."""
        from integrations import version_control_integration as vcs  # type: ignore
        if not vcs.is_configured() or vcs.get_vcs_type() != "svn":
            return
        if not self._current_file_path:
            QMessageBox.information(self, "Register with VCS",
                                    "No project file is open.")
            return
        reply = QMessageBox.question(
            self,
            "Register with VCS",
            f"Register the following file with SVN?\n\n{self._current_file_path}\n\n"
            "This schedules the file for addition. "
            "You still need to Commit to make the addition permanent.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if reply != QMessageBox.Yes:
            return
        worker = vcs.VcsWorker("svn_add", file_path=self._current_file_path)
        worker.finished.connect(
            lambda ok, out: self._on_vcs_svn_register_done(ok, out)
        )
        worker.start()
        self._active_vcs_workers = getattr(self, "_active_vcs_workers", [])
        self._active_vcs_workers.append(worker)

    def _on_vcs_svn_register_done(self, success: bool, output: str):
        """Handle completion of the SVN register (svn add) operation."""
        if success:
            QMessageBox.information(
                self, "Register with VCS",
                f"File successfully registered with SVN.\n\n{output[:500]}\n\n"
                "Use \u2018Commit\u2019 to permanently add it to the repository.",
            )
            # Refresh ribbon — the button should now be hidden (file is scheduled)
            self._update_vcs_ribbon_state()
        else:
            QMessageBox.critical(
                self, "Register with VCS Failed",
                f"Could not register file with SVN:\n\n{output[:800]}",
            )

    def open_vcs_config(self):
        """Open the Version Control configuration dialog."""
        from settings_dialogs import VcsConfigDialog  # type: ignore
        dlg = VcsConfigDialog(self._settings_manager, self)
        dlg.exec_()

    def run_vcs_commit(self):
        """Commit the current project file to version control (project file scope)."""
        self._run_vcs_commit_impl(scope="project")

    def run_vcs_commit_all(self):
        """Commit all tracked changes in the repository to version control."""
        self._run_vcs_commit_impl(scope="all")

    def _run_vcs_commit_impl(self, scope: str = "project") -> None:
        """Shared implementation for VCS commit with configurable scope."""
        from integrations import version_control_integration as vcs  # type: ignore
        project = self.logic.get_data()
        if project is None:
            QMessageBox.information(self, "Version Control", "No project is open.")
            return
        if not vcs.is_configured():
            QMessageBox.information(self, "Version Control",
                                    "No repository detected for this project.")
            return
        # Prompt for commit message
        from PyQt5.QtWidgets import QInputDialog  # type: ignore
        import datetime
        project_name = self._current_file_path or "project"
        scope_label = "all changes" if scope == "all" else "project file"
        default_msg = (
            f"Manual commit ({scope_label}): {project_name.split('/')[-1].split(chr(92))[-1]} "
            f"at {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )
        msg, ok = QInputDialog.getText(
            self, "Commit Message", "Enter commit message:", text=default_msg
        )
        if not ok or not msg.strip():
            return
        # Ensure KeePass unlocked if entry is configured
        if self._settings_manager.get_vcs_keepass_entry() and \
                not self._settings_manager.is_keepass_unlocked():
            self._prompt_unlock_keepass_for_vcs()
            if not self._settings_manager.is_keepass_unlocked():
                return
        worker = vcs.VcsWorker("commit", message=msg.strip(), scope=scope,
                               file_path=self._current_file_path or "")
        ok, out = run_with_progress(
            self, "Committing\u2026", worker, cancellable=False, indeterminate=True)
        record_timing("vcs_commit", worker.elapsed_seconds, ok)
        self._on_vcs_operation_done(ok, out, "Commit")

    def open_vcs_log(self):
        """Open the commit history log dialog."""
        from integrations import version_control_integration as vcs  # type: ignore
        if not vcs.is_configured():
            QMessageBox.information(self, "Version Control",
                                    "No repository detected for this project.")
            return
        ok, entries = vcs.get_log(max_entries=100)
        if not ok or not entries:
            QMessageBox.information(self, "Version Control Log",
                                    "No log entries found or repository is empty.")
            return
        from settings_dialogs import VcsLogDialog  # type: ignore
        dlg = VcsLogDialog(entries, vcs_type=vcs.get_vcs_type(),
                           repo_root=vcs.get_repo_root(), parent=self)
        dlg.exec_()

    def open_vcs_branch_dialog(self):
        """Open the Git branch management dialog."""
        from integrations import version_control_integration as vcs  # type: ignore
        if vcs.get_vcs_type() != "git":
            QMessageBox.information(self, "Branch Management",
                                    "Branch management is only available for Git repositories.")
            return
        from settings_dialogs import VcsBranchDialog  # type: ignore
        dlg = VcsBranchDialog(current_branch=vcs.get_current_branch(), parent=self)
        dlg.exec_()
        # Refresh branch display
        self._update_vcs_ribbon_state()

    def run_vcs_pull(self):
        """Pull latest changes from the remote Git repository (merge strategy)."""
        from integrations import version_control_integration as vcs  # type: ignore
        if not vcs.is_configured():
            QMessageBox.information(self, "Version Control",
                                    "No repository detected for this project.")
            return
        if self._settings_manager.get_vcs_keepass_entry() and \
                not self._settings_manager.is_keepass_unlocked():
            self._prompt_unlock_keepass_for_vcs()
            if not self._settings_manager.is_keepass_unlocked():
                return
        worker = vcs.VcsWorker("pull")
        ok, out = run_with_progress(
            self, "Pulling from remote\u2026", worker, cancellable=False, indeterminate=True)
        record_timing("vcs_pull", worker.elapsed_seconds, ok)
        self._on_vcs_pull_done(ok, out)

    def run_vcs_pull_rebase(self):
        """Pull latest changes from the remote Git repository using rebase strategy."""
        from integrations import version_control_integration as vcs  # type: ignore
        if not vcs.is_configured():
            QMessageBox.information(self, "Version Control",
                                    "No repository detected for this project.")
            return
        if self._settings_manager.get_vcs_keepass_entry() and \
                not self._settings_manager.is_keepass_unlocked():
            self._prompt_unlock_keepass_for_vcs()
            if not self._settings_manager.is_keepass_unlocked():
                return
        worker = vcs.VcsWorker("pull", rebase=True)
        ok, out = run_with_progress(
            self, "Pulling (rebase) from remote\u2026", worker, cancellable=False, indeterminate=True)
        record_timing("vcs_pull_rebase", worker.elapsed_seconds, ok)
        self._on_vcs_pull_done(ok, out)

    def run_vcs_fetch_only(self):
        """Fetch changes from the remote Git repository without merging or rebasing."""
        from integrations import version_control_integration as vcs  # type: ignore
        if not vcs.is_configured():
            QMessageBox.information(self, "Version Control",
                                    "No repository detected for this project.")
            return
        if self._settings_manager.get_vcs_keepass_entry() and \
                not self._settings_manager.is_keepass_unlocked():
            self._prompt_unlock_keepass_for_vcs()
            if not self._settings_manager.is_keepass_unlocked():
                return
        worker = vcs.VcsWorker("fetch")
        ok, out = run_with_progress(
            self, "Fetching from remote\u2026", worker, cancellable=False, indeterminate=True)
        record_timing("vcs_fetch", worker.elapsed_seconds, ok)
        self._on_vcs_operation_done(ok, out, "Git Fetch")

    def run_vcs_svn_update(self):
        """Update the SVN working copy to HEAD."""
        from integrations import version_control_integration as vcs  # type: ignore
        if not vcs.is_configured():
            QMessageBox.information(self, "Version Control",
                                    "No repository detected for this project.")
            return
        if self._settings_manager.get_vcs_keepass_entry() and \
                not self._settings_manager.is_keepass_unlocked():
            self._prompt_unlock_keepass_for_vcs()
            if not self._settings_manager.is_keepass_unlocked():
                return
        worker = vcs.VcsWorker("svn_update")
        ok, out = run_with_progress(
            self, "SVN Update\u2026", worker, cancellable=False, indeterminate=True)
        record_timing("vcs_svn_update", worker.elapsed_seconds, ok)
        self._on_vcs_pull_done(ok, out)

    def run_vcs_svn_update_to_revision(self):
        """Prompt for a revision number then update the SVN working copy to that revision."""
        from integrations import version_control_integration as vcs  # type: ignore
        if not vcs.is_configured():
            QMessageBox.information(self, "Version Control",
                                    "No repository detected for this project.")
            return
        from PyQt5.QtWidgets import QInputDialog  # type: ignore
        rev, ok = QInputDialog.getText(
            self, "SVN Update to Revision",
            "Enter the revision number to update to:",
        )
        if not ok or not rev.strip():
            return
        rev = rev.strip()
        if self._settings_manager.get_vcs_keepass_entry() and \
                not self._settings_manager.is_keepass_unlocked():
            self._prompt_unlock_keepass_for_vcs()
            if not self._settings_manager.is_keepass_unlocked():
                return
        worker = vcs.VcsWorker("svn_update", revision=rev)
        ok2, out = run_with_progress(
            self, f"SVN Update to r{rev}\u2026", worker, cancellable=False, indeterminate=True)
        record_timing("vcs_svn_update", worker.elapsed_seconds, ok2)
        self._on_vcs_pull_done(ok2, out)

    def run_vcs_svn_cleanup(self):
        """Run SVN cleanup to fix a locked working copy."""
        from integrations import version_control_integration as vcs  # type: ignore
        if not vcs.is_configured():
            return
        worker = vcs.VcsWorker("svn_cleanup")
        ok, out = run_with_progress(
            self, "SVN Cleanup\u2026", worker, cancellable=False, indeterminate=True)
        record_timing("vcs_svn_cleanup", worker.elapsed_seconds, ok)
        self._on_vcs_operation_done(ok, out, "SVN Cleanup")

    def _on_vcs_operation_done(self, success: bool, output: str, op_name: str):
        if success:
            QMessageBox.information(self, op_name,
                                    f"{op_name} completed successfully.\n\n{output[:500]}")
        else:
            QMessageBox.critical(self, f"{op_name} Failed",
                                 f"{op_name} failed:\n\n{output[:800]}")

    def _on_vcs_pull_done(self, success: bool, output: str):
        """Handle pull/update completion, showing conflict dialog if needed."""
        from integrations import version_control_integration as vcs  # type: ignore
        if success:
            conflicts = vcs.get_conflicts()
            if conflicts:
                from settings_dialogs import VcsConflictDialog  # type: ignore
                dlg = VcsConflictDialog(conflicts, output=output, parent=self)
                dlg.exec_()
            else:
                QMessageBox.information(self, "Version Control",
                                        f"Update completed.\n\n{output[:500]}")
        else:
            QMessageBox.critical(self, "Update Failed",
                                 f"Update failed:\n\n{output[:800]}")

    def _prompt_unlock_keepass_for_vcs(self):
        """Prompt the user to unlock KeePass for VCS credential retrieval."""
        answer = QMessageBox.question(
            self, "KeePass Locked",
            "KeePass is locked. Unlock it now to provide VCS credentials?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes,
        )
        if answer != QMessageBox.Yes:
            return
        ok, _ = self._settings_manager.auto_unlock_keepass()
        if not ok:
            from PyQt5.QtWidgets import QInputDialog, QLineEdit  # type: ignore
            pwd, entered = QInputDialog.getText(
                self, "KeePass Master Password",
                "Enter KeePass master password:", QLineEdit.Password,
            )
            if entered:
                ok, err = self._settings_manager.unlock_keepass(pwd)
                if not ok:
                    QMessageBox.warning(self, "Unlock Failed",
                                        f"Could not open database:\n{err}")



    def split_task_action(self):
        """Ribbon 'Split Task' button: open date picker for the selected task."""
        if self.logic.get_data() is None:
            return
        idx = self.tabs.currentIndex()
        from app_tabs import TAB_GANTT, TAB_TEAM_PLANNER  # type: ignore
        if idx not in (TAB_GANTT, TAB_TEAM_PLANNER):
            return
        # Resolve the selected task from task_view or team_planner_view
        task = self._selected_task_for_split()
        if task is None:
            from PyQt5.QtWidgets import QMessageBox  # type: ignore
            QMessageBox.information(self, "Split Task",
                                    "Select a task in the task list first.")
            return
        # Delegate to canvas (which shows the date picker)
        self.gantt_view.canvas._do_split_interactive(task, None)

    def merge_task_action(self):
        """Ribbon 'Merge Segments' button: merge all segments of the selected task."""
        if self.logic.get_data() is None:
            return
        task = self._selected_task_for_split()
        if task is None:
            return
        self.gantt_view.merge_task(task)
        self.gantt_view.canvas.task_edited.emit()

    def _selected_task_for_split(self):
        """Return the currently selected Java task (from task_view), or None."""
        try:
            rows = sorted(set(i.row() for i in self.task_view.selectedIndexes()))
            if len(rows) == 1 and rows[0] < len(self.task_view._java_tasks):
                task = self.task_view._java_tasks[rows[0]]
                # Skip summaries and milestones
                try:
                    if bool(task.getSummary()) or bool(task.getMilestone()):
                        return None
                except Exception:
                    pass
                return task
        except Exception:
            pass
        return None

    def split_task_for_task(self, task):
        """Open the split date picker for a specific Java task (called from team planner)."""
        if task is None:
            return
        self.gantt_view.canvas._do_split_interactive(task, None)
        self.team_planner_view.canvas.update()

    def merge_task_for_task(self, task):
        """Merge all segments of a specific Java task (called from team planner)."""
        if task is None:
            return
        self.gantt_view.merge_task(task)
        self.gantt_view.canvas.task_edited.emit()
        self.team_planner_view.canvas.update()

    def _task_has_splits(self, task) -> bool:
        """Return True if *task* has split segments stored."""
        try:
            uid = int(str(task.getUniqueID()))
            segs = self.gantt_view.canvas._task_splits.get(uid)
            return segs is not None and len(segs) >= 2
        except Exception:
            return False

    # ---------------------------------------------------------------- #
    # Splits JSON sidecar persistence                                  #
    # ---------------------------------------------------------------- #

    def _splits_json_path(self) -> str | None:
        if not self._current_file_path:
            return None
        base = os.path.splitext(self._current_file_path)[0]
        return base + ".splits.json"

    # ---------------------------------------------------------------- #
    # Resource thumbnail sidecar persistence                           #
    # ---------------------------------------------------------------- #

    def _thumbnails_json_path(self) -> str | None:
        if not self._current_file_path:
            return None
        base = os.path.splitext(self._current_file_path)[0]
        return base + ".thumbnails.json"

    def _load_thumbnails_json(self) -> tuple:
        """Load resource sidecar JSON.  Returns (thumb_store, dept_store).

        Supports both the new format ``{"uid": {"thumbnail": ..., "department": ...}}``
        and the legacy format ``{"uid": "<base64>"}`` (thumbnail only).
        """
        import base64
        import json
        path = self._thumbnails_json_path()
        thumb_store: dict = {}
        dept_store: dict = {}
        if path and os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as _f:
                    data = json.load(_f)
                for uid, entry in data.get("resources", {}).items():
                    uid = str(uid)
                    if isinstance(entry, str):
                        # Legacy format: plain base64 thumbnail string
                        try:
                            thumb_store[uid] = base64.b64decode(entry)
                        except Exception:
                            pass
                    elif isinstance(entry, dict):
                        if "thumbnail" in entry:
                            try:
                                thumb_store[uid] = base64.b64decode(entry["thumbnail"])
                            except Exception:
                                pass
                        if entry.get("department"):
                            dept_store[uid] = entry["department"]
            except Exception as _e:
                print(f"[WARN] resource sidecar load: {_e}")
        return thumb_store, dept_store

    def _save_splits_json(self):
        path = self._splits_json_path()
        if not path:
            return
        try:
            import json
            data = self.gantt_view.canvas.splits_to_dict()
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as exc:
            print(f"[WARN] splits JSON save: {exc}")

    def _load_splits_json(self):
        """Load splits from the sidecar JSON (takes priority over MPXJ getSplits)."""
        path = self._splits_json_path()
        if not path or not os.path.exists(path):
            return
        try:
            import json
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.gantt_view.canvas.load_splits_from_dict(data)
        except Exception as exc:
            print(f"[WARN] splits JSON load: {exc}")

    def _write_splits_to_project(self) -> None:
        """Write Python-side split data back into MPXJ task objects via setSplits().

        This makes the splits self-contained in the saved XML so that MS Project
        (and this app on re-import without the sidecar JSON) can read them back.
        Tasks with no splits have their splits cleared.
        """
        project = self.logic.get_data()
        if project is None:
            return
        splits_dict = self.gantt_view.canvas._task_splits
        try:
            from org.mpxj import DateRange  # type: ignore
            from java.util import ArrayList  # type: ignore
            import java.time as _jtime       # type: ignore
        except Exception:
            return  # JPype not running (e.g. unit-test environment)
        # Build uid ? task map
        uid_to_task = {}
        try:
            for t in project.getTasks():
                if t.getName() is None:
                    continue
                try:
                    uid_to_task[int(str(t.getUniqueID()))] = t
                except Exception:
                    pass
        except Exception:
            return
        for uid, segs in splits_dict.items():
            task = uid_to_task.get(uid)
            if task is None or len(segs) < 2:
                continue
            try:
                split_list = ArrayList()
                for seg_start, seg_end in segs:
                    # Use 08:00 start / 17:00 end — matches default working hours
                    s_ldt = _jtime.LocalDateTime.of(
                        seg_start.year(), seg_start.month(), seg_start.day(), 8, 0)
                    e_ldt = _jtime.LocalDateTime.of(
                        seg_end.year(), seg_end.month(), seg_end.day(), 17, 0)
                    split_list.add(DateRange(s_ldt, e_ldt))
                task.setSplits(split_list)
            except Exception as exc:
                print(f"[WARN] setSplits for uid {uid}: {exc}")

    def _load_splits(self):
        """Load split data from MPXJ getSplits() after project open."""
        project = self.logic.get_data()
        if project is not None:
            self.gantt_view.load_splits_from_project(project)

    def _update_email_actions_state(self) -> None:
        """Enable/disable email export items based on whether an email account is configured."""
        configs     = self._settings_manager.get_email_configs()
        active_name = self._settings_manager.get_active_email_config_name()
        is_configured = bool(active_name and active_name in configs)
        if is_configured:
            self._toolbar.ribbon.set_email_actions_enabled(True)
        else:
            tip = (
                "No email account configured.\n"
                "Use Email Accounts in the Report ribbon to add an SMTP account,\n"
                "then select it via Email Config."
            )
            self._toolbar.ribbon.set_email_actions_enabled(False, tip)

    def _update_confluence_sync_btn(self):
        """Enable/disable the Sync Calendar button based on project custom fields."""
        from integrations.confluence_calendar_integration import (  # type: ignore
            get_project_base_url, get_project_space_key,
            CONFLUENCE_BASE_URL_PROP, CONFLUENCE_SPACE_KEY_PROP,
            CONFLUENCE_TIMEZONE_PROP, CONFLUENCE_DAYS_AHEAD_PROP,
        )
        project = self.logic.get_data()
        if project is None:
            return  # set_project_open(False) already disabled it
        base_url  = get_project_base_url(project)
        space_key = get_project_space_key(project)
        if base_url and space_key:
            self._toolbar.ribbon.set_confluence_sync_state(
                True,
                "Fetch vacations and public holidays from Confluence Team Calendars\n"
                "and apply them as non-working exceptions to resource / project calendars",
            )
        else:
            missing = []
            if not base_url:
                missing.append(f"‘{CONFLUENCE_BASE_URL_PROP}’")
            if not space_key:
                missing.append(f"‘{CONFLUENCE_SPACE_KEY_PROP}’")
            tip = (
                "Set the following custom property(s) in\n"
                "Project \u2192 Project Information \u2192 Custom Fields \u2192 Properties:\n\n"
                + "\n".join(f"  \u2022 {m}" for m in missing)
            )
            self._toolbar.ribbon.set_confluence_sync_state(False, tip)

    def sync_confluence_calendars(self):
        """Fetch Confluence calendar events and apply them to the open project."""
        import time as _time
        from integrations.confluence_calendar_integration import ConfluenceCalendarSync  # type: ignore
        sync = ConfluenceCalendarSync()
        _t0 = _time.monotonic()
        try:
            run_indeterminate(
                self, "Syncing Confluence Calendars\u2026",
                sync.run,
                self.logic.get_data(), self,
                history_manager=self._history,
                settings_manager=self._settings_manager,
            )
            record_timing("confluence_sync", _time.monotonic() - _t0, True)
        except Exception as exc:
            record_timing("confluence_sync", _time.monotonic() - _t0, False)
            QMessageBox.critical(self, "Confluence Sync", f"Sync failed:\n{exc}")
            return
        project = self.logic.get_data()
        if project is not None:
            # Assign UIDs to any newly created resources so views can display them
            self.file_handler.sanitize_resource_uids(project)
            self._refresh_all_views()
            self._mark_dirty()

    def toggle_resource_units(self, checked: bool):
        self.gantt_view.set_show_resource_units(checked)
        self._settings.setValue("gantt/show_resource_units", checked)
        self.menuBar().set_resource_units_checked(checked)
        self._toolbar.ribbon.set_resource_units_checked(checked)

    def toggle_show_sundays(self, checked: bool):
        self.gantt_view.set_show_sundays(checked)
        self.team_planner_view.set_show_sundays(checked)
        self.resource_usage_graph_view.set_show_sundays(checked)
        self._settings.setValue("gantt/show_sundays", checked)
        self.menuBar().set_show_sundays_checked(checked)
        self._toolbar.ribbon.set_show_sundays_checked(checked)

    def toggle_show_off_hours(self, checked: bool):
        self.resource_usage_graph_view.set_show_off_hours(checked)
        self.gantt_view.set_show_off_hours(checked)
        self.team_planner_view.set_show_off_hours(checked)
        self._settings.setValue("usage/show_off_hours", checked)
        self.menuBar().set_show_off_hours_checked(checked)

    def toggle_histogram(self, checked: bool):
        """Called from Options > Show Resource Usage Histogram."""
        self.histogram_view.setVisible(checked)
        self._settings.setValue("histogram/visible", checked)
        self.menuBar().set_show_histogram_checked(checked)

    def toggle_zero_float_critical(self, checked: bool):
        self._settings_manager.set_zero_float_critical(checked)
        self.gantt_view.set_zero_float_critical(checked)
        self.task_view.set_zero_float_critical(checked)
        self.team_planner_view.set_zero_float_critical(checked)
        self.menuBar().set_zero_float_critical_checked(checked)
        # Reload critical ids for the current project if one is open
        project = self.logic.get_data()
        if project is not None:
            self.gantt_view.load_project(project)
            self.task_view.load_project(project)

    def _apply_cpm_settings(self):
        """Push current _cpm_cfg to the Gantt canvas and trigger a recompute."""
        canvas = self.gantt_view.canvas
        canvas.set_critical_slack_days(self._cpm_cfg.get("critical_slack_days", 0))
        canvas.set_cpm_dep_types(self._cpm_cfg.get("dep_types", "all"))
        show_float = self._settings_manager.get_show_float_bar()
        canvas.set_show_float_bar(show_float)
        # Trigger a reload so _compute_critical_ids re-runs with new params
        project = self.logic.get_data()
        if project is not None:
            self.gantt_view.load_project(project)
        # Sync status-bar spin with current config (block signals to avoid re-entry)
        if hasattr(self, '_cpm_slack_spin'):
            self._cpm_slack_spin.blockSignals(True)
            self._cpm_slack_spin.setValue(self._cpm_cfg.get("critical_slack_days", 0))
            self._cpm_slack_spin.blockSignals(False)
        self._update_cpm_status()
        self._refresh_cpm_results_view()

    def open_cpm_settings(self):
        """Open the CPM Settings dialog and apply changes."""
        try:
            from settings_dialogs import CPMSettingsDialog  # type: ignore
        except ImportError:
            QMessageBox.warning(self, "CPM Settings", "CPM Settings dialog not available yet.")
            return
        dlg = CPMSettingsDialog(self._cpm_cfg, self._settings_manager, self)
        if dlg.exec_():
            self._cpm_cfg = dlg.get_cpm_cfg()
            self._apply_cpm_settings()
            # Persist per-project settings to sidecar
            if self._current_file_path:
                self.file_handler.save_cpm_settings(self._current_file_path, self._cpm_cfg)

    def _on_cpm_slack_spin_changed(self, value: int):
        """Called when the status-bar slack spin value changes."""
        self._cpm_cfg["critical_slack_days"] = value
        self._apply_cpm_settings()
        if self._current_file_path:
            self.file_handler.save_cpm_settings(self._current_file_path, self._cpm_cfg)

    def toggle_cpm_results_panel(self):
        """Switch to the CPM Results tab and persist the choice."""
        self.tabs.setCurrentIndex(TAB_CPM)
        self._settings_manager.set_show_cpm_results_panel(True)

    def new_project(self):
        try:
            from org.mpxj import ProjectFile  # type: ignore
            project = ProjectFile()
            self.logic.load_data(project)
        except Exception:
            self.logic.load_data(None)
        self._current_file_path = None
        self.file_handler._source_xml_path = None
        self.gantt_view.clear_splits()   # clear any previous split data
        self._refresh_all_views()
        self._history.push_all()
        self._mark_dirty()   # new unsaved project
        # Clear the resource thumbnail store for the new (unsaved) project
        try:
            from dialogs import set_resource_thumbnail_store  # type: ignore
            set_resource_thumbnail_store({}, {}, None)
        except Exception:
            pass
        # Create the default German national holiday calendar and ask whether
        # optional regional/country calendars should be installed too.
        project = self.logic.get_data()
        if project is not None:
            self._apply_system_currency_to_project(project)
            self._setup_new_project_calendars(project)
        # Prompt for mandatory project start/end dates so tasks are not
        # incorrectly flagged as critical on an empty calendar.
        self.open_project_info()

    def _apply_system_currency_to_project(self, project):
        """Populate the new project's currency settings from the OS locale.

        Reads the system locale via the standard ``locale`` module.  Falls back
        silently if locale data is unavailable or incomplete.
        """
        try:
            import locale as _locale

            # LC_ALL is not supported by getlocale() on Python 3.12/Windows;
            # use LC_MONETARY for save/restore to avoid TypeError.
            saved = _locale.getlocale(_locale.LC_MONETARY)
            try:
                _locale.setlocale(_locale.LC_MONETARY, "")
                conv = _locale.localeconv()
            finally:
                try:
                    _locale.setlocale(_locale.LC_MONETARY, saved)
                except Exception:
                    pass

            symbol  = conv.get("currency_symbol", "")
            code    = (conv.get("int_curr_symbol") or "").strip()
            digits  = conv.get("frac_digits", 2)
            # Negative sentinel (-1) means locale couldn't determine the value.
            if digits < 0:
                digits = 2

            # Map locale convention to MPXJ CurrencySymbolPosition enum name.
            precedes   = conv.get("p_cs_precedes",  1)
            sep_space  = conv.get("p_sep_by_space", 0)
            if precedes:
                pos_name = "BEFORE_WITH_SPACE" if sep_space else "BEFORE"
            else:
                pos_name = "AFTER_WITH_SPACE" if sep_space else "AFTER"

            props = project.getProjectProperties()
            if symbol:
                props.setCurrencySymbol(symbol)
            if code:
                props.setCurrencyCode(code)
            props.setCurrencyDigits(digits)
            try:
                import jpype  # type: ignore
                CSP = jpype.JClass("org.mpxj.CurrencySymbolPosition")
                props.setSymbolPosition(CSP.valueOf(pos_name))
            except Exception:
                pass  # jpype not available or position not settable
        except Exception as e:
            print(f"[WARN] _apply_system_currency_to_project: {e}")

    def _setup_new_project_calendars(self, project):
        """Create the default German holiday calendar for a new project.

        Shows a dialog that lets the user install optional state and country
        calendars.  German state calendars are derived from the standard
        calendar (they inherit national holidays) and only store their extra
        exceptions.  Country calendars are standalone.
        """
        try:
            from holidays import (  # type: ignore
                german_national_holidays, german_state_extra_holidays,
                france_holidays, india_holidays, romania_holidays,
                china_holidays, japan_holidays,
                add_holidays_to_calendar, default_holiday_years,
            )
            from dialogs import NewProjectCalendarsDialog  # type: ignore

            years = default_holiday_years()

            # ---- Default calendar: German national holidays ----
            default_cal = project.addCalendar()
            default_cal.setName("Standard (Deutschland)")
            default_cal.addDefaultCalendarDays()
            default_cal.addDefaultCalendarHours()
            try:
                project.setDefaultCalendar(default_cal)
            except Exception:
                try:
                    default_cal.setDefault(True)
                except Exception:
                    pass
            add_holidays_to_calendar(default_cal, german_national_holidays(years))

            # ---- Optional calendars dialog ----
            dlg = NewProjectCalendarsDialog(self)
            if dlg.exec_() != dlg.Accepted:
                return

            _COUNTRY_FUNS = {
                "France":   lambda: france_holidays(years),
                "India":    lambda: india_holidays(years),
                "Romania":  lambda: romania_holidays(years),
                "China":    lambda: china_holidays(years),
                "Japan":    lambda: japan_holidays(years),
            }

            for name in dlg.get_selected():
                cal = project.addCalendar()
                cal.setName(name)
                if name in NewProjectCalendarsDialog._GERMAN_STATES:
                    # Derive from the standard calendar – inherits national holidays
                    try:
                        cal.setParent(default_cal)
                    except Exception:
                        cal.addDefaultCalendarDays()
                        cal.addDefaultCalendarHours()
                    add_holidays_to_calendar(
                        cal,
                        german_state_extra_holidays(name, years),
                    )
                elif name in _COUNTRY_FUNS:
                    cal.addDefaultCalendarDays()
                    cal.addDefaultCalendarHours()
                    add_holidays_to_calendar(cal, _COUNTRY_FUNS[name]())

        except Exception as e:
            print(f"[WARN] _setup_new_project_calendars: {e}")

    def close_project(self):
        """File ? Close: prompt to save unsaved changes then close the project."""
        if self._dirty:
            reply = QMessageBox.question(
                self, "Unsaved Changes",
                "The project has unsaved changes.\nDo you want to save before closing?",
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
                QMessageBox.Save,
            )
            if reply == QMessageBox.Save:
                self.save_project()
                if self._dirty:      # save was cancelled
                    return
            elif reply == QMessageBox.Cancel:
                return
        self.logic.load_data(None)
        self._current_file_path = None
        self.file_handler._source_xml_path = None
        self.gantt_view.clear_splits()
        self._refresh_all_views()
        self._history.push_all()  # clears history stacks when project is None
        self._mark_clean()
        # Reset VCS state and hide the ribbon tab
        try:
            from integrations import version_control_integration as vcs  # type: ignore
            vcs.reset()
            self._update_vcs_ribbon_state()
        except Exception:
            pass
        # Clear the resource thumbnail store
        try:
            from dialogs import set_resource_thumbnail_store  # type: ignore
            set_resource_thumbnail_store({}, {}, None)
        except Exception:
            pass

    def add_entry(self):
        """Dispatch Insert action to the active view."""
        if self.logic.get_data() is None:
            return
        idx = self.tabs.currentIndex()
        if idx == TAB_GANTT:
            self.task_view.add_task()
        elif idx == TAB_RESOURCES:
            self.resource_view.add_resource()
        elif idx == TAB_DEPENDENCIES:
            self.dependency_view.add_dependency()

    def delete_entry(self):
        """Dispatch Delete action to the active view."""
        idx = self.tabs.currentIndex()
        if idx == TAB_GANTT:
            self.task_view.delete_selected_tasks()
        elif idx == TAB_RESOURCES:
            self.resource_view.delete_selected_resources()
        elif idx == TAB_DEPENDENCIES:
            self.dependency_view.delete_selected_dependencies()

    # kept for backward-compat (e.g. called from --open flow)
    def add_task(self):
        self.tabs.setCurrentIndex(TAB_GANTT)
        self.add_entry()

    def delete_task(self):
        self.task_view.delete_selected_tasks()

    def open_project(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open Project File", "",
            "MS Project Files (*.mpp *.xml *.mpt *.mpx);;All Files (*)"
        )
        if file_path:
            self.open_project_file(file_path)

    def save_project(self):
        """Smart save:
          - MPP file loaded  ? always open Save As dialog (MPXJ can't write MPP)
          - XML file loaded  ? ask: overwrite in-place or Save As
          - No file yet      ? open Save As dialog
        After a successful save the dirty flag is cleared.
        """
        if self.logic.get_data() is None:
            return

        import os
        ext = os.path.splitext(self._current_file_path or "")[1].lower()

        save_path: str | None = None

        if ext == ".xml" and self._current_file_path:
            reply = QMessageBox.question(
                self, "Save Project",
                f"Overwrite the existing file?\n{self._current_file_path}",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
                QMessageBox.Yes,
            )
            if reply == QMessageBox.Cancel:
                return
            if reply == QMessageBox.Yes:
                save_path = self._current_file_path
            # else: fall through to Save As

        if save_path is None:
            # MPP, new project, or user chose "No" above ? open Save As
            suggest = ""
            if self._current_file_path:
                base = os.path.splitext(self._current_file_path)[0]
                suggest = base + ".xml"
            save_path, _ = QFileDialog.getSaveFileName(
                self, "Save Project File", suggest, "MSPDI XML Files (*.xml)"
            )
            if not save_path:
                return

        self._write_splits_to_project()
        import time as _time
        _t0 = _time.monotonic()
        try:
            saved = run_indeterminate(
                self, f"Saving {os.path.basename(save_path)}\u2026",
                self.file_handler.save_project, save_path,
            )
        except Exception:
            saved = False
        record_timing("file_save", _time.monotonic() - _t0, bool(saved))
        if saved:
            self._current_file_path = save_path
            self._mark_clean()
            self._add_to_recent(save_path)
            self._save_timeline_json()
            self._save_splits_json()
            # Trigger auto-commit (debounced)
            try:
                from integrations import version_control_integration as vcs  # type: ignore
                import os as _os
                project = self.logic.get_data()
                project_name = ""
                if project is not None:
                    try:
                        project_name = str(project.getProjectProperties().getName() or "")
                    except Exception:
                        pass
                if not project_name:
                    project_name = _os.path.splitext(
                        _os.path.basename(save_path))[0]
                vcs.schedule_auto_commit(save_path, project_name)
            except Exception:
                pass
        else:
            QMessageBox.critical(self, "Error", "Failed to save project file.")

    # ------------------------------------------------------------------ #
    # Import actions                                                      #
    # ------------------------------------------------------------------ #

    def import_plantuml(self):
        """Import -> PlantUML Gantt: parse a .puml file and open it as a project."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Import PlantUML Gantt File", "",
            "PlantUML Files (*.puml *.plantuml);;All Files (*)"
        )
        if not path:
            return
        try:
            from import_plantuml import import_plantuml as _import  # type: ignore
            project = _import(path)
            self.logic.load_data(project)
            self._current_file_path = None
            self._refresh_all_views()
            self._history.push_all()
            self._mark_dirty()
        except Exception as exc:
            QMessageBox.critical(self, "Import Error", str(exc))

    # ------------------------------------------------------------------ #
    # Export actions                                                      #
    # ------------------------------------------------------------------ #

    def export_gantt_svg(self):
        """Export -> Complete Gantt Chart as SVG."""
        if self.logic.get_data() is None:
            QMessageBox.information(self, "Export", "No project is open.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Gantt Chart as SVG", "", "SVG Files (*.svg)"
        )
        if not path:
            return
        import time as _time
        _t0 = _time.monotonic()
        try:
            from export_gantt import export_gantt_svg  # type: ignore
            run_indeterminate(
                self, "Exporting Gantt Chart\u2026",
                export_gantt_svg, self.gantt_view.canvas, path,
            )
            record_timing("export_gantt_svg", _time.monotonic() - _t0, True)
            QMessageBox.information(self, "Export", f"Gantt chart saved to:\n{path}")
        except Exception as exc:
            record_timing("export_gantt_svg", _time.monotonic() - _t0, False)
            QMessageBox.critical(self, "Export Error", str(exc))

    def export_resource_gantt_svg(self):
        """Export -> Resource Gantt Charts as SVG (one file per resource)."""
        if self.logic.get_data() is None:
            QMessageBox.information(self, "Export", "No project is open.")
            return
        folder = QFileDialog.getExistingDirectory(
            self, "Select Output Folder for Resource Gantt SVGs"
        )
        if not folder:
            return
        import time as _time
        _t0 = _time.monotonic()
        try:
            from export_gantt import export_resource_gantt_svg  # type: ignore
            count = run_indeterminate(
                self, "Exporting Resource Gantt Charts\u2026",
                export_resource_gantt_svg, self.gantt_view.canvas, folder,
            )
            record_timing("export_resource_gantt_svg", _time.monotonic() - _t0, True)
            if count == 0:
                QMessageBox.information(
                    self, "Export",
                    "No resource assignments found — no files were created."
                )
            else:
                QMessageBox.information(
                    self, "Export",
                    f"{count} SVG file(s) written to:\n{folder}"
                )
        except Exception as exc:
            record_timing("export_resource_gantt_svg", _time.monotonic() - _t0, False)
            QMessageBox.critical(self, "Export Error", str(exc))

    def email_gantt_svg(self):
        """Send the Gantt Chart as an SVG email attachment."""
        if self.logic.get_data() is None:
            QMessageBox.information(self, "Email Export", "No project is open.")
            return
        import tempfile, os
        from export_gantt import export_gantt_svg  # type: ignore
        try:
            with tempfile.NamedTemporaryFile(suffix=".svg", delete=False) as tf:
                svg_path = tf.name
            run_indeterminate(
                self, "Exporting Gantt Chart\u2026",
                export_gantt_svg, self.gantt_view.canvas, svg_path,
            )
            with open(svg_path, "rb") as fh:
                svg_bytes = fh.read()
            os.unlink(svg_path)
        except Exception as exc:
            QMessageBox.critical(self, "Email Export", f"Failed to export Gantt to SVG:\n{exc}")
            return
        self._send_svg_bytes_as_email("Gantt Chart", "gantt_chart.svg", svg_bytes)

    def email_resource_gantt_svg(self):
        """Open bulk email export dialog (per-resource Gantt SVGs)."""
        self.open_email_export_bulk()

    # ------------------------------------------------------------------ #
    # CPM Report email                                                     #
    # ------------------------------------------------------------------ #

    def _build_cpm_html_table(self) -> str:
        """Build an HTML table of CPM results from the current float_data."""
        fd = getattr(self.gantt_view.canvas, "_float_data", {})
        canvas = self.gantt_view.canvas
        wdh = getattr(canvas, "_work_day_hours", 8.0) or 8.0

        def _dt(v):
            try:
                return str(v)[:10] if v else ""
            except Exception:
                return ""

        def _td(v):
            try:
                if v is None:
                    return ""
                days = round(v.total_seconds() / 3600 / wdh, 1)
                return f"{days}d"
            except Exception:
                return ""

        def _td_row(data, key_wh, key_td):
            """Prefer calendar-aware working hours (Phase 5) over timedelta fallback."""
            wh = data.get(key_wh)
            if wh is not None:
                row_wdh = data.get("work_day_hours") or wdh
                return f"{round(float(wh) / max(row_wdh, 1), 1)}d"
            return _td(data.get(key_td))

        name_map: dict = {}
        try:
            for t in canvas.tasks:
                tid = int(str(t.getID()))
                name_map[tid] = str(t.getName()) if t.getName() else "(unnamed)"
        except Exception:
            pass

        header = (
            "<table border='1' cellpadding='4' cellspacing='0' "
            "style='border-collapse:collapse;font-size:12px;'>"
            "<tr style='background:#2B579A;color:white;font-weight:bold;'>"
            "<th>Task Name</th><th>ES</th><th>EF</th><th>LS</th><th>LF</th>"
            "<th>Total Float</th><th>Free Float</th><th>Status</th></tr>"
        )
        rows_html = []
        items = sorted(fd.items(), key=lambda x: (not x[1].get("critical"), name_map.get(x[0], "")))
        for tid, data in items:
            is_crit = data.get("critical")
            bg = "#fdecea" if is_crit else "white"
            fc = "#c0392b" if is_crit else "black"
            fw = "bold"   if is_crit else "normal"
            status = "CRITICAL" if is_crit else "OK"
            rows_html.append(
                f"<tr style='background:{bg};color:{fc};font-weight:{fw};'>"
                f"<td>{name_map.get(tid, f'Task {tid}')}</td>"
                f"<td>{_dt(data.get('es'))}</td><td>{_dt(data.get('ef'))}</td>"
                f"<td>{_dt(data.get('ls'))}</td><td>{_dt(data.get('lf'))}</td>"
                f"<td>{_td_row(data, 'total_float_wh', 'total_float')}</td>"
                f"<td>{_td_row(data, 'free_float_wh', 'free_float')}</td>"
                f"<td>{status}</td></tr>"
            )
        return header + "".join(rows_html) + "</table>"

    def email_cpm_report(self):
        """Send CPM results as an HTML email (no Gantt attachment)."""
        self._send_cpm_report_email(with_gantt=False)

    def email_cpm_report_with_gantt(self):
        """Send CPM results as HTML with Gantt SVG attached."""
        self._send_cpm_report_email(with_gantt=True)

    def _send_cpm_report_email(self, with_gantt: bool = False):
        import datetime
        from integrations import email_integration  # type: ignore

        project = self.logic.get_data()
        if project is None:
            QMessageBox.information(self, "CPM Report", "No project is open.")
            return

        fd = getattr(self.gantt_view.canvas, "_float_data", {})
        if not fd:
            QMessageBox.information(self, "CPM Report",
                                    "No CPM data available. Open a project with tasks and dependencies.")
            return

        # Resolve project name and manager
        proj_name = ""
        proj_mgr  = ""
        try:
            props = project.getProjectProperties()
            proj_name = str(props.getName() or "")
            proj_mgr  = str(props.getManager() or "")
        except Exception:
            pass
        if not proj_name:
            proj_name = "Project"

        html_table = self._build_cpm_html_table()
        today_str  = datetime.date.today().strftime("%d %b %Y")
        subject    = f"Critical Path Report: {proj_name} ({today_str})"
        body_plain = (
            f"Critical Path Method (CPM) analysis for {proj_name} as of {today_str}.\n\n"
            "Critical tasks have zero Total Float and are highlighted in the attached report.\n\n"
            f"Kind regards,\n{proj_mgr}"
        )
        body_html = (
            f"<html><body style='font-family:Arial,sans-serif;font-size:14px;color:#222;'>"
            f"<p>Below is the CPM analysis for <strong>{proj_name}</strong> as of <strong>{today_str}</strong>.</p>"
            f"{html_table}"
            f"<p>Critical tasks (red) have zero Total Float.</p>"
            f"<p>Kind regards,<br/>{proj_mgr}</p>"
            f"</body></html>"
        )

        configs     = self._settings_manager.get_email_configs()
        active_name = self._settings_manager.get_active_email_config_name()
        if not configs:
            QMessageBox.warning(self, "CPM Report",
                                "No email account is configured. Use Email Accounts to add one.")
            return
        cfg = next((c for c in configs if c.get("name") == active_name), configs[0])

        # Build recipient list via EmailExportDialog for consistency
        try:
            from dialogs import EmailExportDialog  # type: ignore
            dlg = EmailExportDialog(project, configs, active_name,
                                    view_name="CPM Report", parent=self)
            if dlg.exec_() != dlg.Accepted:
                return
            to_addr = dlg.get_to()
            subject = dlg.get_subject() or subject
            cfg     = dlg.get_selected_config() or cfg
        except Exception:
            # Fallback: ask for email address
            from PyQt5.QtWidgets import QInputDialog  # type: ignore
            to_addr, ok = QInputDialog.getText(self, "CPM Report", "Recipient email address:")
            if not ok or not to_addr.strip():
                return
            to_addr = to_addr.strip()

        attachments = []
        if with_gantt:
            try:
                import tempfile, os
                from export_gantt import export_gantt_svg  # type: ignore
                with tempfile.NamedTemporaryFile(suffix=".svg", delete=False) as tf:
                    svg_path = tf.name
                export_gantt_svg(self.gantt_view.canvas, svg_path)
                with open(svg_path, "rb") as fh:
                    attachments.append(("gantt.svg", fh.read()))
                os.unlink(svg_path)
            except Exception as exc:
                QMessageBox.warning(self, "CPM Report",
                                    f"Could not export Gantt SVG (email will be sent without it):\n{exc}")

        ok, err = email_integration.send_email(
            to=to_addr, subject=subject, body=body_plain,
            attachments=attachments, config=cfg,
            body_html=body_html,
        )
        if ok:
            QMessageBox.information(self, "CPM Report", "CPM report sent successfully.")
        else:
            QMessageBox.critical(self, "CPM Report", f"Failed to send email:\n{err}")



    def _send_svg_bytes_as_email(self, view_name: str, filename: str, svg_bytes: bytes):
        """Shared helper: open EmailExportDialog and send *svg_bytes* as attachment + inline image.

        When the selected template provides a ``body_html`` field, the SVG is embedded directly
        in the HTML email body via a ``cid:`` URI (multipart/related) **and** also attached as a
        downloadable file.  If no HTML template is active the message falls back to plain text with
        a file attachment only.
        """
        import uuid
        import datetime
        from integrations import email_integration  # type: ignore
        from dialogs import EmailExportDialog  # type: ignore

        project = self.logic.get_data()
        configs = self._settings_manager.get_email_configs()
        active_name = self._settings_manager.get_active_email_config_name()
        dlg = EmailExportDialog(project, configs, active_name, view_name=view_name, parent=self)
        if dlg.exec_() != dlg.Accepted:
            return
        to_addr  = dlg.get_to()
        subject  = dlg.get_subject()
        body     = dlg.get_body()
        body_html_tmpl = dlg.get_body_html()   # may contain {svg_inline} placeholder
        cfg      = dlg.get_selected_config()

        if not to_addr:
            QMessageBox.warning(self, "Email Export", "Please enter a recipient email address.")
            return
        if not subject:
            QMessageBox.warning(self, "Email Export", "Please enter a subject.")
            return
        if cfg is None:
            QMessageBox.warning(self, "Email Export",
                                "No email account is configured. Use Email Accounts to add one.")
            return

        # Build inline-image MIME parts when the template provides an HTML body
        inline_images = None
        body_html     = None
        if body_html_tmpl:
            svg_cid   = f"svg_{uuid.uuid4().hex}@projectoffline"
            img_tag   = (
                f'<img src="cid:{svg_cid}" '
                f'style="max-width:100%;border:none;display:block;" '
                f'alt="{view_name} export" />'
            )
            body_html     = body_html_tmpl.replace("{svg_inline}", img_tag)
            inline_images = [(svg_cid, filename, svg_bytes)]

        ok, err = email_integration.send_email(
            to=to_addr, subject=subject, body=body,
            attachments=[(filename, svg_bytes)], config=cfg,
            body_html=body_html, inline_images=inline_images,
        )
        email_integration._last_export_result = {
            "timestamp":   datetime.datetime.now().isoformat(timespec="seconds"),
            "mode":        "single",
            "view":        view_name,
            "config_name": cfg.get("name", ""),
            "sent":        1 if ok else 0,
            "skipped":     0,
            "failed":      0 if ok else 1,
        }
        if ok:
            QMessageBox.information(self, "Email Export", f"Email sent successfully to:\n{to_addr}")
        else:
            QMessageBox.critical(self, "Email Export", f"Failed to send email:\n{err}")

    def export_gantt_plantuml(self):
        """Export -> Complete Gantt Chart as PlantUML file."""
        if self.logic.get_data() is None:
            QMessageBox.information(self, "Export", "No project is open.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Gantt Chart as PlantUML", "", "PlantUML Files (*.puml *.plantuml)"
        )
        if not path:
            return
        import time as _time
        _t0 = _time.monotonic()
        try:
            from export_gantt import export_gantt_plantuml  # type: ignore
            run_indeterminate(
                self, "Exporting PlantUML\u2026",
                export_gantt_plantuml, self.gantt_view.canvas, path,
            )
            record_timing("export_gantt_plantuml", _time.monotonic() - _t0, True)
            QMessageBox.information(self, "Export", f"PlantUML file saved to:\n{path}")
        except Exception as exc:
            record_timing("export_gantt_plantuml", _time.monotonic() - _t0, False)
            QMessageBox.critical(self, "Export Error", str(exc))

    # ------------------------------------------------------------------ #
    # View switching (called by toolbar / View menu)                      #
    # ------------------------------------------------------------------ #

    def switch_to_gantt(self):                    self.tabs.setCurrentIndex(TAB_GANTT)
    def switch_to_resources(self):                self.tabs.setCurrentIndex(TAB_RESOURCES)
    def switch_to_dependencies(self):             self.tabs.setCurrentIndex(TAB_DEPENDENCIES)
    def switch_to_baseline(self):                 self.tabs.setCurrentIndex(TAB_BASELINE)
    def switch_to_team_planner(self):             self.tabs.setCurrentIndex(TAB_TEAM_PLANNER)
    def switch_to_task_sheet(self):               self.tabs.setCurrentIndex(TAB_TASK_SHEET)
    def switch_to_resource_usage_graph(self):     self.tabs.setCurrentIndex(TAB_RESOURCE_USAGE)
    def switch_to_cpm_results(self):              self.tabs.setCurrentIndex(TAB_CPM)

    # ------------------------------------------------------------------ #
    # Baseline actions                                                     #
    # ------------------------------------------------------------------ #

    def set_baseline(self) -> None:
        """Snapshot the current schedule into a baseline slot."""
        project = self.logic.get_data()
        if project is None:
            return
        import baseline_manager  # type: ignore
        from PyQt5.QtWidgets import (  # type: ignore
            QDialog, QVBoxLayout, QHBoxLayout, QGridLayout,
            QPushButton, QLabel, QRadioButton, QComboBox, QButtonGroup, QFrame,
        )
        from PyQt5.QtCore import Qt  # type: ignore

        active = baseline_manager.get_active_baselines(project)
        # Next free slot (0-10 not yet in active)
        next_free = next((n for n in range(11) if n not in active), None)

        dlg = QDialog(self)
        dlg.setWindowTitle("Set Baseline")
        dlg.setMinimumWidth(400)
        root = QVBoxLayout(dlg)
        root.setSpacing(10)

        # --- Option 1: create new ---
        grp = QButtonGroup(dlg)
        new_radio = QRadioButton()
        grp.addButton(new_radio, 0)
        new_row = QHBoxLayout()
        new_row.setContentsMargins(0, 0, 0, 0)
        new_row.addWidget(new_radio)
        if next_free is not None:
            slot_name = "Baseline" if next_free == 0 else f"Baseline {next_free}"
            new_row.addWidget(QLabel(f"Create new  ?  <b>{slot_name}</b>"))
        else:
            new_row.addWidget(QLabel("Create new  (all 11 slots are in use)"))
            new_radio.setEnabled(False)
        new_row.addStretch()
        root.addLayout(new_row)

        # --- Option 2: overwrite existing ---
        ow_radio = QRadioButton()
        grp.addButton(ow_radio, 1)
        ow_row = QHBoxLayout()
        ow_row.setContentsMargins(0, 0, 0, 0)
        ow_row.addWidget(ow_radio)
        ow_row.addWidget(QLabel("Overwrite:"))
        ow_combo = QComboBox()
        for n in sorted(active.keys()):
            label = "Baseline" if n == 0 else f"Baseline {n}"
            ow_combo.addItem(f"{label}  ({active[n]})", n)
        ow_combo.setMinimumWidth(200)
        ow_row.addWidget(ow_combo)
        ow_row.addStretch()
        root.addLayout(ow_row)

        # Enable / disable combo based on radio
        ow_combo.setEnabled(False)
        ow_radio.toggled.connect(ow_combo.setEnabled)
        if not active:
            ow_radio.setEnabled(False)

        # Pre-select sensible default
        if next_free is not None:
            new_radio.setChecked(True)
        else:
            ow_radio.setChecked(True)

        # --- Separator + buttons ---
        sep = QFrame(); sep.setFrameShape(QFrame.HLine); sep.setFrameShadow(QFrame.Sunken)
        root.addWidget(sep)
        btn_row = QHBoxLayout()
        ok_btn = QPushButton("Set Baseline")
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(dlg.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(dlg.reject)
        btn_row.addStretch()
        btn_row.addWidget(ok_btn)
        btn_row.addWidget(cancel_btn)
        root.addLayout(btn_row)

        if dlg.exec_() != QDialog.Accepted:
            return

        if grp.checkedId() == 0:
            # New slot
            slot = next_free
        else:
            # Overwrite
            slot = ow_combo.currentData()
        if slot is None:
            return

        baseline_manager.set_baseline(project, slot)
        # Do NOT switch the active (viewing) baseline to the captured slot.
        self._after_baseline_change()

    def clear_baseline(self) -> None:
        """Remove baseline data — opens a table dialog with per-row delete buttons."""
        project = self.logic.get_data()
        if project is None:
            return
        import baseline_manager  # type: ignore
        from PyQt5.QtWidgets import (  # type: ignore
            QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
            QTableWidget, QTableWidgetItem, QHeaderView, QFrame,
        )
        from PyQt5.QtCore import Qt  # type: ignore
        from PyQt5.QtGui import QColor  # type: ignore

        active = baseline_manager.get_active_baselines(project)
        if not active:
            QMessageBox.information(self, "Clear Baseline", "No baselines are set.")
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("Clear Baselines")
        dlg.setMinimumWidth(480)
        root = QVBoxLayout(dlg)
        root.addWidget(QLabel("Click the delete button to remove a baseline:"))

        # Table: Name | Captured at | Delete
        tbl = QTableWidget(0, 3)
        tbl.setHorizontalHeaderLabels(["Baseline", "Captured at", ""])
        tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        tbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        tbl.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        tbl.verticalHeader().setVisible(False)
        tbl.setEditTriggers(QTableWidget.NoEditTriggers)
        tbl.setSelectionMode(QTableWidget.NoSelection)
        tbl.setAlternatingRowColors(True)

        def _populate():
            ab = baseline_manager.get_active_baselines(project)
            tbl.setRowCount(0)
            for n in sorted(ab.keys()):
                row = tbl.rowCount()
                tbl.insertRow(row)
                name = "Baseline" if n == 0 else f"Baseline {n}"
                tbl.setItem(row, 0, QTableWidgetItem(name))
                tbl.setItem(row, 1, QTableWidgetItem(ab[n]))
                del_btn = QPushButton("??  Delete")
                del_btn.setToolTip(f"Remove all baseline data for {name}")

                def _make_handler(slot, label):
                    def _handler():
                        reply = QMessageBox.question(
                            dlg, "Delete Baseline",
                            f"Remove all baseline data for '{label}'?\nThis cannot be undone.",
                            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
                        )
                        if reply == QMessageBox.Yes:
                            baseline_manager.clear_baseline(project, slot)
                            _populate()
                            self._after_baseline_change()
                    return _handler

                del_btn.clicked.connect(_make_handler(n, name))
                tbl.setCellWidget(row, 2, del_btn)
            tbl.resizeRowsToContents()

        _populate()
        root.addWidget(tbl)

        sep = QFrame(); sep.setFrameShape(QFrame.HLine); sep.setFrameShadow(QFrame.Sunken)
        root.addWidget(sep)
        btn_row = QHBoxLayout()
        close_btn = QPushButton("Close")
        close_btn.setDefault(True)
        close_btn.clicked.connect(dlg.accept)
        btn_row.addStretch()
        btn_row.addWidget(close_btn)
        root.addLayout(btn_row)
        dlg.exec_()

    def set_active_baseline(self, number: int) -> None:
        """Change the active (reference) baseline slot used for display and comparison."""
        self._active_baseline_number = max(0, min(10, int(number)))
        project = self.logic.get_data()
        # Update all views that use the baseline number
        self.gantt_view.canvas.set_baseline_number(self._active_baseline_number)
        self.baseline_view.set_baseline_number(self._active_baseline_number)
        if project is not None:
            self.baseline_view.load_project(project)
        self._mark_dirty()

    def set_baseline_next_free(self) -> None:
        """Snapshot the current schedule into the next free baseline slot without showing a dialog."""
        project = self.logic.get_data()
        if project is None:
            return
        import baseline_manager  # type: ignore
        active = baseline_manager.get_active_baselines(project)
        next_free = next((n for n in range(11) if n not in active), None)
        if next_free is None:
            QMessageBox.warning(
                self, "Set Baseline",
                "All 11 baseline slots are already in use.\n"
                "Use 'Set baseline (dialog)' to overwrite an existing slot.",
            )
            return
        label = "Baseline" if next_free == 0 else f"Baseline {next_free}"
        reply = QMessageBox.question(
            self, "Set Baseline",
            f"Snapshot the current schedule into <b>{label}</b>?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes,
        )
        if reply != QMessageBox.Yes:
            return
        baseline_manager.set_baseline(project, next_free)
        self._after_baseline_change()

    def set_baseline_all_slots(self) -> None:
        """Snapshot the current schedule into all 11 baseline slots at once (bulk capture)."""
        project = self.logic.get_data()
        if project is None:
            return
        import baseline_manager  # type: ignore
        reply = QMessageBox.question(
            self, "Set All Baselines",
            "This will overwrite all 11 baseline slots (Baseline through Baseline 10) "
            "with a snapshot of the current schedule.\n\nContinue?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        for slot in range(11):
            baseline_manager.set_baseline(project, slot)
        self._after_baseline_change()

    def clear_baseline_all(self) -> None:
        """Remove all baseline data from all slots after confirmation."""
        project = self.logic.get_data()
        if project is None:
            return
        import baseline_manager  # type: ignore
        active = baseline_manager.get_active_baselines(project)
        if not active:
            QMessageBox.information(self, "Clear Baseline", "No baselines are set.")
            return
        reply = QMessageBox.question(
            self, "Clear All Baselines",
            f"Remove all baseline data from {len(active)} slot(s)?\nThis cannot be undone.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        for slot in list(active.keys()):
            baseline_manager.clear_baseline(project, slot)
        self._after_baseline_change()

    def set_comparison_baseline(self, number: int) -> None:
        """Change the comparison slot in the baseline table.

        number = -1 means compare against the current (live) schedule;
        number 0-10 means compare against that baseline slot.
        """
        self._comparison_baseline_number = max(-1, min(10, int(number)))
        self.baseline_view.set_comparison_baseline(self._comparison_baseline_number)
        project = self.logic.get_data()
        if project is not None:
            self.baseline_view.load_project(project)

    def toggle_gantt_diff_bars(self, checked: bool) -> None:
        """Show/hide the baseline reference strip on Gantt bars."""
        self.gantt_view.canvas.set_show_baseline_bars(checked)

    def toggle_gantt_diff_duration(self, checked: bool) -> None:
        """Show/hide Duration variance columns in the Baseline table."""
        self.baseline_view.set_show_duration_diff(checked)

    def toggle_gantt_diff_start(self, checked: bool) -> None:
        """Show/hide Start delta columns in the Baseline table."""
        self.baseline_view.set_show_start_diff(checked)

    def toggle_gantt_diff_finish(self, checked: bool) -> None:
        """Show/hide Finish delta columns in the Baseline table."""
        self.baseline_view.set_show_finish_diff(checked)

    def _after_baseline_change(self) -> None:
        """Refresh all baseline-related UI after a set/clear operation."""
        project = self.logic.get_data()
        import baseline_manager  # type: ignore
        active = baseline_manager.get_active_baselines(project) if project else {}
        self._toolbar.ribbon.update_baseline_list(active)
        # Sync ribbon combo with our internal active number (update_baseline_list
        # preserves the combo's previous index, which may not match after a capture).
        ribbon = self._toolbar.ribbon
        if ribbon._baseline_combo is not None:
            ribbon._baseline_combo.blockSignals(True)
            ribbon._baseline_combo.setCurrentIndex(self._active_baseline_number)
            ribbon._baseline_combo.blockSignals(False)
        self.baseline_view.set_baseline_number(self._active_baseline_number)
        if project is not None:
            self.baseline_view.load_project(project)
        self.gantt_view.canvas.set_baseline_number(self._active_baseline_number)
        self.gantt_view.canvas.update()
        self._mark_dirty()

    def save_project_as(self):
        """Force Save As dialog regardless of current file type."""
        if self.logic.get_data() is None:
            return
        import os
        suggest = ""
        if self._current_file_path:
            base = os.path.splitext(self._current_file_path)[0]
            suggest = base + ".xml"
        save_path, _ = QFileDialog.getSaveFileName(
            self, "Save Project File", suggest, "MSPDI XML Files (*.xml)"
        )
        if not save_path:
            return
        self._write_splits_to_project()
        import time as _time
        _t0 = _time.monotonic()
        try:
            saved = run_indeterminate(
                self, f"Saving {os.path.basename(save_path)}\u2026",
                self.file_handler.save_project, save_path,
            )
        except Exception:
            saved = False
        record_timing("file_save", _time.monotonic() - _t0, bool(saved))
        if saved:
            self._current_file_path = save_path
            self._mark_clean()
            self._add_to_recent(save_path)
            self._save_timeline_json()
            self._save_splits_json()
        else:
            QMessageBox.critical(self, "Error", "Failed to save project file.")

    def add_resource(self):
        """Add resource: switch to Resources tab then add."""
        self.tabs.setCurrentIndex(TAB_RESOURCES)
        self.resource_view.add_resource()

    def add_resource_from_ad(self):
        """Open AD search dialog and add the chosen user as a new resource."""
        self.tabs.setCurrentIndex(TAB_RESOURCES)
        self.resource_view.add_resource_from_ad()

    def add_resources_from_ad_group(self):
        """Open AD group search dialog and bulk-add group members as resources."""
        self.tabs.setCurrentIndex(TAB_RESOURCES)
        self.resource_view.add_resources_from_ad_group()

    def delete_resource(self):
        """Delete the selected resource."""
        self.resource_view.delete_selected_resources()

    # ------------------------------------------------------------------ #
    # Recent files                                                        #
    # ------------------------------------------------------------------ #

    def _load_recent_files(self) -> list:
        paths = self._settings.value("recentFiles", [], type=list)
        return [p for p in paths if os.path.exists(p)]

    def _add_to_recent(self, path: str):
        paths = self._load_recent_files()
        path = os.path.normpath(path)
        if path in paths:
            paths.remove(path)
        paths.insert(0, path)
        paths = paths[:5]
        self._settings.setValue("recentFiles", paths)
        self.menuBar().update_recent_files(paths)

    def clear_recent_files(self):
        self._settings.setValue("recentFiles", [])
        self.menuBar().update_recent_files([])

