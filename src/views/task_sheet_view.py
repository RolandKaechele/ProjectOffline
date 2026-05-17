# task_sheet_view.py - Standalone hierarchical Task Sheet view
#
# Mirrors the MS Project "Task Sheet" / "Entry Table" layout:
#   Col 0 : #    – row number with status icons (milestone, critical, overdue)
#   Col 1 : Task Name – indented by outline level, bold for summaries,
#                       collapse/expand triangle for summary tasks
#   Col 2 : Duration
#   Col 3 : % Complete – cell with visual progress-bar overlay
#   Col 4 : Start
#   Col 5 : Finish
#   Col 6 : Assigned To
#   Col 7 : Predecessors
#
# Double-clicking any row opens the Task Information dialog.
# Emits data_changed when the dialog is accepted.

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from PyQt5.QtWidgets import (  # type: ignore
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QStyledItemDelegate, QStyleOptionViewItem, QApplication, QStyle,
    QStyleOptionProgressBar, QDialog
)
from PyQt5.QtGui import (  # type: ignore
    QColor, QFont, QPainter, QBrush, QPen, QPolygon, QPixmap, QIcon
)
from PyQt5.QtCore import Qt, QDate, QPoint, QRect, QSize, pyqtSignal  # type: ignore

# Re-use helpers from the other views in this package
from gantt_view import _get_visible_tasks, _compute_critical_ids  # type: ignore
from task_view import (  # type: ignore
    _make_icon, _make_combined_icon, INDENT_PX_PER_LEVEL, TaskView
)

# Spacing constants
_ROW_H          = 36
_NUM_COL_W      = 60   # width of the # column


# ---------------------------------------------------------------------------
# Task Name delegate  (hierarchy indentation + collapse/expand triangle)
# ---------------------------------------------------------------------------


def _load_task_jira_data(view, task) -> dict:
    """Return the sidecar Jira entry for *task*, or {} if not available."""
    try:
        sidecar_path = getattr(view, '_get_sidecar_path', lambda: "")() 
        if not sidecar_path:
            return {}
        from integrations.jira_sync import load_sidecar_task_data  # type: ignore
        all_jira = load_sidecar_task_data(sidecar_path)
        uid_str = str(task.getUniqueID())
        return all_jira.get(uid_str, {})
    except Exception:
        return {}


class _TaskNameDelegate(QStyledItemDelegate):
    """Renders the Task Name cell with pixel indentation and bold summary text.

    UserRole data on the item:
        UserRole   – outline_level (int)
        UserRole+1 – is_summary    (bool)
        UserRole+2 – task_id       (str)
        UserRole+3 – is_collapsed  (bool)
    """
    _TRI_W = 10

    def __init__(self, view, parent=None):
        super().__init__(parent)
        self._view = view   # TaskSheetView reference for collapse toggling

    def paint(self, painter, option, index):
        outline_level = index.data(Qt.UserRole) or 1
        is_summary    = bool(index.data(Qt.UserRole + 1))
        is_collapsed  = bool(index.data(Qt.UserRole + 3))
        indent        = max(0, outline_level - 1) * INDENT_PX_PER_LEVEL

        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ""
        QApplication.style().drawControl(QStyle.CE_ItemViewItem, opt, painter)

        if is_summary:
            tx = option.rect.left() + indent + 2
            cy = option.rect.center().y()
            painter.save()
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setBrush(QBrush(QColor(70, 70, 70)))
            painter.setPen(Qt.NoPen)
            if is_collapsed:
                pts = QPolygon([QPoint(tx, cy - 5),
                                QPoint(tx + self._TRI_W, cy),
                                QPoint(tx, cy + 5)])
            else:
                pts = QPolygon([QPoint(tx, cy - 4),
                                QPoint(tx + self._TRI_W, cy - 4),
                                QPoint(tx + 5, cy + 5)])
            painter.drawPolygon(pts)
            painter.restore()
            indent += self._TRI_W + 4

        text = index.data(Qt.DisplayRole) or ""
        rect = option.rect.adjusted(indent + 4, 0, -4, 0)
        font = QFont(option.font)
        if is_summary:
            font.setBold(True)
        painter.save()
        painter.setFont(font)
        color = (option.palette.highlightedText().color()
                 if option.state & QStyle.State_Selected
                 else option.palette.text().color())
        painter.setPen(color)
        painter.drawText(rect, Qt.AlignVCenter | Qt.AlignLeft, text)
        painter.restore()

    def editorEvent(self, event, model, option, index):
        """Handle mouse clicks on the collapse/expand triangle."""
        from PyQt5.QtCore import QEvent  # type: ignore
        if event.type() == QEvent.MouseButtonPress:
            is_summary   = bool(index.data(Qt.UserRole + 1))
            outline_level = index.data(Qt.UserRole) or 1
            indent        = max(0, outline_level - 1) * INDENT_PX_PER_LEVEL
            if is_summary:
                tri_rect = QRect(
                    option.rect.left() + indent + 2,
                    option.rect.center().y() - 6,
                    self._TRI_W + 2, 14
                )
                if tri_rect.contains(event.pos()):
                    task_id = index.data(Qt.UserRole + 2)
                    self._view._toggle_collapse(task_id)
                    return True
        return False

    def sizeHint(self, option, index):
        return super().sizeHint(option, index)


# ---------------------------------------------------------------------------
# Progress-bar delegate  (% Complete column)
# ---------------------------------------------------------------------------

class _ProgressDelegate(QStyledItemDelegate):
    """Draws a coloured progress bar inside the % Complete cell."""

    def paint(self, painter, option, index):
        # Draw standard background / selection first
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ""
        QApplication.style().drawControl(QStyle.CE_ItemViewItem, opt, painter)

        # Parse the percentage value
        raw = index.data(Qt.DisplayRole) or "0"
        try:
            pct = float(str(raw).replace("%", "").strip())
        except ValueError:
            pct = 0.0
        pct = max(0.0, pct)  # allow > 100 (over-budget tasks)

        r = option.rect.adjusted(4, 6, -4, -6)
        # Background track
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor("#B8CBE4"), 1))
        painter.setBrush(QBrush(QColor("#E8F0FB")))
        painter.drawRoundedRect(r, 2, 2)

        # Fill proportional to pct
        if pct > 0:
            if pct > 100:
                fill_r = QRect(r.left(), r.top(), r.width(), r.height())
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(QColor("#C0392B")))   # red – over 100%
            else:
                fill_w = int(r.width() * pct / 100.0)
                fill_r = QRect(r.left(), r.top(), fill_w, r.height())
                painter.setPen(Qt.NoPen)
                if pct >= 100:
                    painter.setBrush(QBrush(QColor("#217346")))   # green – complete
                elif pct >= 50:
                    painter.setBrush(QBrush(QColor("#2B579A")))   # blue – in progress
                else:
                    painter.setBrush(QBrush(QColor("#70A0D0")))   # light blue – started
            painter.drawRoundedRect(fill_r, 2, 2)

        # Percentage label on top
        label = f"{pct:.0f}%"
        if pct >= 50:
            text_color = (Qt.white if not (option.state & QStyle.State_Selected)
                          else option.palette.highlightedText().color())
        else:
            text_color = (QColor("#1F1F1F") if not (option.state & QStyle.State_Selected)
                          else option.palette.highlightedText().color())
        painter.setPen(text_color)
        painter.setFont(option.font)
        painter.drawText(r, Qt.AlignCenter, label)
        painter.restore()

    def sizeHint(self, option, index):
        sh = super().sizeHint(option, index)
        return QSize(max(sh.width(), 90), sh.height())


# ---------------------------------------------------------------------------
# TaskSheetView widget
# ---------------------------------------------------------------------------

class TaskSheetView(QTableWidget):
    """Standalone hierarchical task-sheet view (MS Project "Entry Table" style).

    Signals
    -------
    data_changed : emitted after the user edits a task via the Task dialog.
    """

    data_changed = pyqtSignal()
    # Emitted when the user toggles a task in/out of the timeline via context menu.
    timeline_toggle_requested = pyqtSignal(object)
    split_task_requested  = pyqtSignal(object)
    merge_task_requested  = pyqtSignal(object)

    COLUMNS = ["", "#", "Task Name", "Duration", "% Complete", "Start", "Finish",
               "Assigned To", "Predecessors", "Free Float"]

    # Column indices
    COL_ICON  = 0   # status icon (narrow)
    COL_NUM   = 1   # task ID number (always visible)
    COL_NAME  = 2
    COL_DUR   = 3
    COL_PCT   = 4
    COL_START = 5
    COL_END   = 6
    COL_RES   = 7
    COL_PRED  = 8
    COL_FF    = 9   # Free Float (optional — hidden when not enabled)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project       = None
        self._java_tasks    = []        # visible tasks (respects collapse)
        self._critical_ids  = set()
        self._collapsed_ids = set()
        self._id_to_name    = {}        # int(task_id) -> name, for predecessor labels

        # ---- appearance ----
        self.setColumnCount(len(self.COLUMNS))
        self.setHorizontalHeaderLabels(self.COLUMNS)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(_ROW_H)
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setShowGrid(True)
        self.setGridStyle(Qt.SolidLine)

        # ---- column widths ----
        self.setColumnWidth(self.COL_ICON,  36)
        self.setColumnWidth(self.COL_NUM,   46)
        self.setColumnWidth(self.COL_NAME,  260)
        self.setColumnWidth(self.COL_DUR,   80)
        self.setColumnWidth(self.COL_PCT,   110)
        self.setColumnWidth(self.COL_START, 100)
        self.setColumnWidth(self.COL_END,   100)
        self.setColumnWidth(self.COL_RES,   140)
        self.setColumnWidth(self.COL_PRED,  220)
        self.setColumnWidth(self.COL_FF,    80)
        self.setColumnHidden(self.COL_FF, True)   # hidden until enabled in settings

        hh = self.horizontalHeader()
        hh.setSectionResizeMode(self.COL_ICON,  QHeaderView.Fixed)
        hh.setSectionResizeMode(self.COL_NUM,   QHeaderView.Fixed)
        hh.setSectionResizeMode(self.COL_NAME,  QHeaderView.Interactive)
        hh.setSectionResizeMode(self.COL_DUR,   QHeaderView.Interactive)
        hh.setSectionResizeMode(self.COL_PCT,   QHeaderView.Interactive)
        hh.setSectionResizeMode(self.COL_START, QHeaderView.Interactive)
        hh.setSectionResizeMode(self.COL_END,   QHeaderView.Interactive)
        hh.setSectionResizeMode(self.COL_RES,   QHeaderView.Interactive)
        hh.setSectionResizeMode(self.COL_PRED,  QHeaderView.Interactive)
        hh.setStretchLastSection(True)

        # ---- custom delegates ----
        self._name_delegate = _TaskNameDelegate(self)
        self._pct_delegate  = _ProgressDelegate()
        self.setItemDelegateForColumn(self.COL_NAME, self._name_delegate)
        self.setItemDelegateForColumn(self.COL_PCT,  self._pct_delegate)

        # ---- signals ----
        self.cellDoubleClicked.connect(self._on_double_click)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def load_project(self, project):
        """Populate the table from a MPXJ ProjectFile object (or None to clear)."""
        self.blockSignals(True)
        self._project    = project
        self._java_tasks = []
        self._id_to_name = {}   # int(id) -> name str, for predecessor labels
        self.setRowCount(0)

        if project is not None:
            all_tasks = [t for t in project.getTasks()
                         if t.getName() is not None and str(t.getID()) != "0"]
            # Build lookup used by predecessor column
            for t in all_tasks:
                try:
                    tid = int(str(t.getID()))
                    self._id_to_name[tid] = str(t.getName()) if t.getName() is not None else ""
                except Exception:
                    pass
            self._critical_ids = _compute_critical_ids(all_tasks, project)
            visible = _get_visible_tasks(all_tasks, self._collapsed_ids)
            # Show/hide Free Float column based on settings
            try:
                from settings_manager import SettingsManager as _SM  # type: ignore
                _show_ff = _SM().get_show_free_float_column()
            except Exception:
                _show_ff = False
            self.setColumnHidden(self.COL_FF, not _show_ff)
            self.setRowCount(len(visible))
            for row, task in enumerate(visible):
                self._java_tasks.append(task)
                self._fill_row(row, task)

        self.blockSignals(False)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _fill_row(self, row, task):
        task_id_str = str(task.getID()) if task.getID() is not None else ""
        name_raw    = str(task.getName()) if task.getName() is not None else ""

        # Outline level
        outline_level = 1
        try:
            ol = task.getOutlineLevel()
            if ol is not None:
                outline_level = int(str(ol))
        except Exception:
            pass

        # Summary (has children)
        is_summary = False
        try:
            sv = task.getSummary()
            if sv is not None and str(sv) not in ('null', 'None', '') and bool(sv):
                children = task.getChildTasks()
                is_summary = children is not None and children.size() > 0
        except Exception:
            pass

        duration  = str(task.getDuration())           if task.getDuration()           is not None else ""
        start_str = str(task.getStart())              if task.getStart()              is not None else ""
        finish_str = str(task.getFinish())            if task.getFinish()             is not None else ""
        pct_raw    = str(task.getPercentageComplete()) if task.getPercentageComplete() is not None else "0%"
        pct_display = pct_raw.replace('%', '').strip()

        # Resources / Assigned To
        assigned_to = ""
        try:
            assignments = task.getResourceAssignments()
            if assignments:
                names = []
                for ass in assignments:
                    res = ass.getResource()
                    if res and res.getName() is not None:
                        names.append(str(res.getName()))
                assigned_to = ", ".join(names)
        except Exception:
            pass

        # Predecessors  – "ID - Task Name" format
        pred_str = ""
        try:
            preds = task.getPredecessors()
            if preds:
                parts = []
                for rel in preds:
                    pt = rel.getPredecessorTask()
                    if pt and pt.getID() is not None:
                        pid = int(str(pt.getID()))
                        pname = self._id_to_name.get(pid, "")
                        parts.append(f"{pid} - {pname}" if pname else str(pid))
                pred_str = ",  ".join(parts)
        except Exception:
            pass

        is_critical = int(task_id_str) in self._critical_ids if task_id_str else False

        # --- Col 0 : icon only (narrow status indicator) ---
        indicators = TaskView._get_indicators(task, pct_raw, finish_str, is_critical)
        icon_item = QTableWidgetItem()
        icon_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        icon_item.setTextAlignment(Qt.AlignCenter)
        if indicators:
            icon_item.setIcon(_make_combined_icon([k for k, _ in indicators]))
            icon_item.setToolTip("\n".join(t for _, t in indicators))
        self.setItem(row, self.COL_ICON, icon_item)

        # --- Col 1 : # (task ID — always visible) ---
        num_item = QTableWidgetItem(task_id_str)
        num_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        num_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.setItem(row, self.COL_NUM, num_item)

        # --- Col 2 : Task Name ---
        name_item = QTableWidgetItem(name_raw)
        name_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        name_item.setData(Qt.UserRole,     outline_level)
        name_item.setData(Qt.UserRole + 1, is_summary)
        name_item.setData(Qt.UserRole + 2, task_id_str)
        name_item.setData(Qt.UserRole + 3, task_id_str in self._collapsed_ids)
        self.setItem(row, self.COL_NAME, name_item)

        # --- Col 2 : Duration ---
        self._set_ro(row, self.COL_DUR, duration)

        # --- Col 3 : % Complete  (delegate draws the bar) ---
        pct_item = QTableWidgetItem(pct_display)
        pct_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        pct_item.setTextAlignment(Qt.AlignCenter)
        self.setItem(row, self.COL_PCT, pct_item)

        # --- Col 5-8 ---
        self._set_ro(row, self.COL_START, start_str[:10] if len(start_str) >= 10 else start_str)
        self._set_ro(row, self.COL_END,   finish_str[:10] if len(finish_str) >= 10 else finish_str)
        self._set_ro(row, self.COL_RES,   assigned_to)
        self._set_ro(row, self.COL_PRED,  pred_str)

        # --- Col 9 : Free Float (optional) ---
        ff_str = ""
        try:
            if not self.isColumnHidden(self.COL_FF):
                _fd = getattr(self, '_get_float_data', lambda: {})()
                tid_int = int(task_id_str) if task_id_str else None
                if _fd and tid_int is not None:
                    _entry = _fd.get(tid_int)
                    if _entry is not None:
                        # Phase 5: prefer calendar-aware working hours
                        _ff_wh = _entry.get("free_float_wh")
                        if _ff_wh is not None:
                            _row_wdh = max(_entry.get("work_day_hours") or 8.0, 1.0)
                            ff_str = f"{round(float(_ff_wh) / _row_wdh, 1)}d"
                        elif _entry.get("free_float") is not None:
                            _ff_h = _entry["free_float"].total_seconds() / 3600
                            ff_str = f"{round(_ff_h / 8.0, 1)}d"
        except Exception:
            pass
        self._set_ro(row, self.COL_FF, ff_str)

        # Row background for summary tasks (light blue-grey tint)
        if is_summary:
            for col in range(self.columnCount()):
                item = self.item(row, col)
                if item:
                    item.setBackground(QColor("#EEF3FA"))

    def _set_ro(self, row, col, text):
        """Insert a read-only QTableWidgetItem."""
        item = QTableWidgetItem(text)
        item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        self.setItem(row, col, item)

    # ------------------------------------------------------------------
    # Collapse / expand
    # ------------------------------------------------------------------

    def _toggle_collapse(self, task_id: str):
        if task_id in self._collapsed_ids:
            self._collapsed_ids.discard(task_id)
        else:
            self._collapsed_ids.add(task_id)
        self.load_project(self._project)

    # ------------------------------------------------------------------
    # Context menu
    # ------------------------------------------------------------------

    def _show_context_menu(self, pos):
        rows_sel = sorted(set(i.row() for i in self.selectedIndexes()))
        n_sel    = len(rows_sel)
        from PyQt5.QtWidgets import QMenu  # type: ignore
        menu = QMenu(self)
        # Timeline toggle: only when ui.py has wired _timeline_is_pinned
        tl_act = None
        if (n_sel == 1
                and hasattr(self, '_timeline_is_pinned')
                and self._timeline_is_pinned is not None):
            row = rows_sel[0]
            if 0 <= row < len(self._java_tasks) and self._java_tasks[row] is not None:
                task = self._java_tasks[row]
                try:
                    tid = int(str(task.getID()))
                except Exception:
                    tid = -1
                if tid >= 0:
                    in_tl = self._timeline_is_pinned(tid)
                    tl_act = menu.addAction(
                        "Remove from Timeline" if in_tl else "Add to Timeline"
                    )
        # Split / Merge: single non-summary, non-milestone task
        split_act = merge_act = None
        if n_sel == 1 and rows_sel:
            row = rows_sel[0]
            if 0 <= row < len(self._java_tasks) and self._java_tasks[row] is not None:
                _t = self._java_tasks[row]
                _is_sum = _is_ms = False
                try:
                    _is_sum = bool(_t.getSummary())
                    _is_ms  = bool(_t.getMilestone())
                except Exception:
                    pass
                if not _is_sum and not _is_ms:
                    has_splits = False
                    if hasattr(self, '_has_splits_fn') and self._has_splits_fn is not None:
                        try:
                            has_splits = bool(self._has_splits_fn(_t))
                        except Exception:
                            pass
                    if tl_act is not None:
                        menu.addSeparator()
                    split_act = menu.addAction("Split Task\u2026")
                    merge_act = menu.addAction("Merge Task Segments") if has_splits else None
        if not menu.actions():
            return
        action = menu.exec_(self.mapToGlobal(pos))
        if tl_act and action == tl_act:
            self.timeline_toggle_requested.emit(self._java_tasks[rows_sel[0]])
        elif split_act and action == split_act:
            self.split_task_requested.emit(self._java_tasks[rows_sel[0]])
        elif merge_act and action == merge_act:
            self.merge_task_requested.emit(self._java_tasks[rows_sel[0]])

    # ------------------------------------------------------------------
    # Double-click → Task Information dialog
    # ------------------------------------------------------------------

    def _on_double_click(self, row, col):
        if row < 0 or row >= len(self._java_tasks):
            return
        task = self._java_tasks[row]
        from dialogs import TaskDialog  # type: ignore
        tl = getattr(self, '_timeline_view_ref', None)
        crit = getattr(self, '_get_critical_ids', lambda: set())()
        fd   = getattr(self, '_get_float_data', lambda: {})()
        task_jira_data = _load_task_jira_data(self, task)
        dlg = TaskDialog(task, self._project, self, timeline_view=tl, critical_ids=crit,
                         float_data=fd, task_jira_data=task_jira_data)
        if dlg.exec_() == QDialog.Accepted:
            dlg.apply_to_task()
            self.blockSignals(True)
            self._fill_row(row, task)
            self.blockSignals(False)
            self.data_changed.emit()
