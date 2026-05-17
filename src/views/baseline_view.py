# baseline_view.py - Baseline tracking / schedule-comparison view
#
# Displays a comparison table: for each task it shows the baseline
# (planned) dates against the current (scheduled) dates, plus computed
# variance columns:
#   ID | Name | BL Start | Current Start | Start Δ |
#              BL Finish | Current Finish | Finish Δ |
#              BL Duration | Current Duration | Duration %
#
# The active baseline slot (0-10) is controlled via set_baseline_number().
# Rows are colour-coded:
#   orange  — moderate deviation (1-5 days / ±10%)
#   red     — severe deviation   (>5 days  / ±25%)

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from PyQt5.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView, QStyledItemDelegate, QStyle, QStyleOptionViewItem  # type: ignore
from PyQt5.QtGui import QColor, QBrush, QPalette  # type: ignore
from PyQt5.QtCore import Qt  # type: ignore

import baseline_manager  # type: ignore


# Column indices
_COL_ID       = 0
_COL_NAME     = 1
_COL_BL_START = 2
_COL_CUR_START= 3
_COL_START_D  = 4
_COL_BL_FIN   = 5
_COL_CUR_FIN  = 6
_COL_FIN_D    = 7
_COL_BL_DUR   = 8
_COL_CUR_DUR  = 9
_COL_DUR_PCT  = 10

_COLUMNS = [
    "ID", "Name",
    "BL Start", "Current Start", "Start Δ (d)",
    "BL Finish", "Current Finish", "Finish Δ (d)",
    "BL Duration", "Current Duration", "Duration Δ %",
]

_COL_WIDTHS = [40, 200, 120, 120, 80, 120, 120, 80, 110, 110, 90]

# Colour thresholds
_YELLOW = QColor(255, 255, 160)   # any change
_ORANGE = QColor(255, 210, 120)   # moderate deviation
_RED    = QColor(255, 150, 150)   # severe deviation


class _CellColorDelegate(QStyledItemDelegate):
    """Fully custom painter for BaselineView cells.

    ``QStyleSheetStyle`` intercepts the entire ``CE_ItemViewItem`` draw path
    whenever ANY QSS rule matches ``QTableWidget::item`` (even a padding-only
    rule).  All attempts to influence the background via ``backgroundBrush`` or
    palette overrides in ``initStyleOption`` are ignored because the stylesheet
    engine rebuilds those values internally.

    The only reliable fix is to bypass ``super().paint()`` entirely and draw
    the background and text ourselves.
    """

    @staticmethod
    def _bg_color(index):
        """Return the QColor stored as BackgroundRole, or None."""
        bg = index.data(Qt.BackgroundRole)
        if bg is None:
            return None
        if isinstance(bg, QBrush):
            return bg.color()
        if isinstance(bg, QColor):
            return bg
        return None

    def paint(self, painter, option, index):
        # Copy the option and let super fill in Alternate flag, font, etc.
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)

        is_selected = bool(opt.state & QStyle.State_Selected)

        # --- Background ---
        if is_selected:
            bg = opt.palette.brush(QPalette.Active, QPalette.Highlight)
        else:
            custom_color = self._bg_color(index)
            if custom_color is not None and custom_color.isValid():
                bg = QBrush(custom_color)
            elif bool(opt.features & QStyleOptionViewItem.Alternate):
                bg = opt.palette.brush(QPalette.Active, QPalette.AlternateBase)
            else:
                bg = opt.palette.brush(QPalette.Active, QPalette.Base)

        painter.save()
        painter.fillRect(opt.rect, bg)

        # --- Text ---
        text_val = index.data(Qt.DisplayRole)
        if text_val is not None:
            fg_role = QPalette.HighlightedText if is_selected else QPalette.Text
            painter.setPen(opt.palette.color(QPalette.Active, fg_role))
            # padding: 3px vertical, 6px horizontal — matches global QSS rule
            text_rect = opt.rect.adjusted(6, 3, -6, -3)
            raw_align = index.data(Qt.TextAlignmentRole)
            align = int(raw_align) if raw_align is not None else (Qt.AlignLeft | Qt.AlignVCenter)
            painter.drawText(text_rect, align, str(text_val))

        painter.restore()


class BaselineView(QTableWidget):

    COLUMNS = _COLUMNS

    def __init__(self, parent=None):
        super().__init__(parent)
        self._baseline_number: int = 0
        self._comparison_number: int = -1   # -1 = current schedule; 0-10 = baseline slot
        self._project = None
        self._tasks: list = []

        self.setColumnCount(len(_COLUMNS))
        self.setHorizontalHeaderLabels(_COLUMNS)
        for col, w in enumerate(_COL_WIDTHS):
            self.setColumnWidth(col, w)
            self.horizontalHeader().setSectionResizeMode(col, QHeaderView.Interactive)
        self.horizontalHeader().setSectionResizeMode(_COL_NAME, QHeaderView.Stretch)

        self.setEditTriggers(QTableWidget.NoEditTriggers)
        self.setSelectionBehavior(QTableWidget.SelectRows)
        self.setAlternatingRowColors(True)
        self.setItemDelegate(_CellColorDelegate(self))
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(22)
        self.cellDoubleClicked.connect(self._on_double_click)

        # Diff-column visibility flags (controlled by Gantt Diff ribbon buttons)
        self._show_start_diff: bool = True
        self._show_finish_diff: bool = True
        self._show_duration_diff: bool = True

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def set_baseline_number(self, number: int) -> None:
        """Switch the active (reference) baseline slot (0-10) and refresh."""
        if number != self._baseline_number:
            self._baseline_number = number
            self._update_headers()
            self.load_project(self._project)

    def set_comparison_baseline(self, number: int) -> None:
        """Set the comparison slot: -1 = current schedule; 0-10 = baseline slot."""
        if number != self._comparison_number:
            self._comparison_number = number
            self._update_headers()
            self.load_project(self._project)

    def set_show_start_diff(self, show: bool) -> None:
        """Show or hide the Start baseline/current/delta columns."""
        self._show_start_diff = bool(show)
        self._apply_column_visibility()

    def set_show_finish_diff(self, show: bool) -> None:
        """Show or hide the Finish baseline/current/delta columns."""
        self._show_finish_diff = bool(show)
        self._apply_column_visibility()

    def set_show_duration_diff(self, show: bool) -> None:
        """Show or hide the Duration baseline/current/delta columns."""
        self._show_duration_diff = bool(show)
        self._apply_column_visibility()

    def load_project(self, project) -> None:
        self._project = project
        self._tasks = []
        self.setRowCount(0)
        if project is None:
            return

        tasks = [t for t in project.getTasks() if t.getName() is not None]
        self._tasks = tasks
        self.setRowCount(len(tasks))

        n = self._baseline_number
        nb = self._comparison_number  # -1 = current schedule
        if nb >= 0 and nb == n:
            nb = -1  # same slot on both sides → fall back to current schedule
        for row, task in enumerate(tasks):
            task_id = str(task.getID()) if task.getID() is not None else ""
            name    = str(task.getName())

            # Reference baseline values
            b_start_raw  = baseline_manager.get_baseline_start(task, n)
            b_finish_raw = baseline_manager.get_baseline_finish(task, n)
            b_dur_raw    = baseline_manager.get_baseline_duration(task, n)
            b_start  = str(b_start_raw)[:10]  if b_start_raw  is not None else ""
            b_finish = str(b_finish_raw)[:10] if b_finish_raw is not None else ""
            try:
                b_dur = str(b_dur_raw) if b_dur_raw is not None else ""
            except Exception:
                b_dur = ""

            # Comparison values (current schedule or another baseline)
            if nb < 0:
                c_start_raw  = task.getStart()
                c_finish_raw = task.getFinish()
                c_dur_raw    = task.getDuration()
                var = baseline_manager.get_variance(task, n)
            else:
                c_start_raw  = baseline_manager.get_baseline_start(task, nb)
                c_finish_raw = baseline_manager.get_baseline_finish(task, nb)
                c_dur_raw    = baseline_manager.get_baseline_duration(task, nb)
                var = baseline_manager.get_variance_between(task, n, nb)

            c_start  = str(c_start_raw)[:10]  if c_start_raw  is not None else ""
            c_finish = str(c_finish_raw)[:10] if c_finish_raw is not None else ""
            try:
                c_dur = str(c_dur_raw) if c_dur_raw is not None else ""
            except Exception:
                c_dur = ""

            # Variance display
            start_d   = _fmt_days(var["start_days"])
            finish_d  = _fmt_days(var["finish_days"])
            dur_pct   = _fmt_pct(var["duration_pct"])

            # Build a tooltip showing variance details — only when there is any difference
            _bl_label  = "Baseline" if n == 0 else f"Baseline {n}"
            _cmp_label = "Current" if nb < 0 else ("Baseline" if nb == 0 else f"Baseline {nb}")
            _tip_lines = []
            if var["start_days"] is not None and var["start_days"] != 0:
                _tip_lines.append(f"Start:    {b_start} → {c_start}  ({start_d} d)")
            if var["finish_days"] is not None and var["finish_days"] != 0:
                _tip_lines.append(f"Finish:   {b_finish} → {c_finish}  ({finish_d} d)")
            if var["duration_pct"] is not None and abs(var["duration_pct"]) >= 0.05:
                _tip_lines.append(f"Duration: {b_dur} → {c_dur}  ({dur_pct})")
            row_tooltip = ""
            if _tip_lines:
                row_tooltip = (
                    f"<b>{name.strip()}</b><br>"
                    f"<small>{_bl_label} vs {_cmp_label}</small><br><br>"
                    + "<br>".join(_tip_lines)
                )

            values = [
                task_id, name,
                b_start, c_start, start_d,
                b_finish, c_finish, finish_d,
                b_dur, c_dur, dur_pct,
            ]

            for col, val in enumerate(values):
                item = QTableWidgetItem(val)
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                if row_tooltip:
                    item.setToolTip(row_tooltip)

                # Delta columns: colour by magnitude of change
                if col == _COL_START_D and var["start_days"] is not None:
                    bg = _cell_color_days(var["start_days"])
                    if bg is not None:
                        item.setBackground(bg)
                elif col == _COL_FIN_D and var["finish_days"] is not None:
                    bg = _cell_color_days(var["finish_days"])
                    if bg is not None:
                        item.setBackground(bg)
                elif col == _COL_DUR_PCT and var["duration_pct"] is not None:
                    bg = _cell_color_pct(var["duration_pct"])
                    if bg is not None:
                        item.setBackground(bg)
                # Data columns: highlight the comparison cell if it differs from reference
                elif col == _COL_CUR_START and c_start and b_start and c_start != b_start:
                    item.setBackground(_YELLOW)
                elif col == _COL_CUR_FIN and c_finish and b_finish and c_finish != b_finish:
                    item.setBackground(_YELLOW)
                elif col == _COL_CUR_DUR and c_dur and b_dur and c_dur != b_dur:
                    item.setBackground(_YELLOW)

                self.setItem(row, col, item)

        self._apply_column_visibility()

    # ------------------------------------------------------------------ #
    # Internal                                                             #
    # ------------------------------------------------------------------ #

    def _update_headers(self) -> None:
        """Refresh the comparison-side column headers based on the current slots."""
        if self._comparison_number < 0:
            comp_label = "Current"
        elif self._comparison_number == 0:
            comp_label = "BL-0"
        else:
            comp_label = f"BL-{self._comparison_number}"
        headers = list(_COLUMNS)
        headers[_COL_CUR_START] = f"{comp_label} Start"
        headers[_COL_CUR_FIN]   = f"{comp_label} Finish"
        headers[_COL_CUR_DUR]   = f"{comp_label} Duration"
        self.setHorizontalHeaderLabels(headers)

    def color_diagnostics(self) -> dict:
        """Return a JSON-serializable dict describing the current cell-colour state.

        Useful for debug dumps: tells us (a) whether setBackground() was actually
        called on items (model-level check), (b) the delegate type in use, and
        (c) the view configuration.  If ``colored_cells`` is empty when we expect
        colours the issue is in load_project(); if it is populated the issue is
        in the delegate / painter.
        """
        _target_cols = {
            _COL_START_D:   "Start_Δ",
            _COL_FIN_D:     "Finish_Δ",
            _COL_DUR_PCT:   "Dur_%",
            _COL_CUR_START: "Cur_Start",
            _COL_CUR_FIN:   "Cur_Finish",
            _COL_CUR_DUR:   "Cur_Dur",
        }
        colored = []
        uncolored_delta_cols = 0
        for row in range(self.rowCount()):
            name_item = self.item(row, _COL_NAME)
            task_name = name_item.text() if name_item else f"row_{row}"
            for col, col_name in _target_cols.items():
                item = self.item(row, col)
                if item is None:
                    continue
                bg = item.data(Qt.BackgroundRole)
                if bg is None:
                    if col in (_COL_START_D, _COL_FIN_D, _COL_DUR_PCT):
                        uncolored_delta_cols += 1
                    continue
                if isinstance(bg, QBrush):
                    if bg.style() == Qt.NoBrush:
                        if col in (_COL_START_D, _COL_FIN_D, _COL_DUR_PCT):
                            uncolored_delta_cols += 1
                        continue
                    color = bg.color()
                elif isinstance(bg, QColor):
                    color = bg
                else:
                    continue
                if not color.isValid():
                    continue
                colored.append({
                    "task": task_name,
                    "col":  col_name,
                    "rgb":  f"({color.red()},{color.green()},{color.blue()})",
                })
        return {
            "delegate_type":       type(self.itemDelegate()).__name__,
            "baseline_slot":       self._baseline_number,
            "comparison_slot":     self._comparison_number,
            "show_start_diff":     self._show_start_diff,
            "show_finish_diff":    self._show_finish_diff,
            "show_duration_diff":  self._show_duration_diff,
            "row_count":           self.rowCount(),
            "colored_cells_count": len(colored),
            "uncolored_delta_count": uncolored_delta_cols,
            "colored_cells":       colored,
        }

    def _apply_column_visibility(self) -> None:
        """Show or hide column groups according to the current diff flags."""
        for col in (_COL_BL_START, _COL_CUR_START, _COL_START_D):
            self.setColumnHidden(col, not self._show_start_diff)
        for col in (_COL_BL_FIN, _COL_CUR_FIN, _COL_FIN_D):
            self.setColumnHidden(col, not self._show_finish_diff)
        for col in (_COL_BL_DUR, _COL_CUR_DUR, _COL_DUR_PCT):
            self.setColumnHidden(col, not self._show_duration_diff)

    def _on_double_click(self, row: int, col: int) -> None:
        if row < 0 or row >= len(self._tasks):
            return
        from dialogs import BaselineEntryDialog  # type: ignore
        BaselineEntryDialog(self._tasks[row], self).exec_()


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _fmt_days(days) -> str:
    if days is None:
        return ""
    return f"{days:+d}" if days != 0 else "0"


def _fmt_pct(pct) -> str:
    if pct is None:
        return ""
    return f"{pct:+.1f}%" if pct != 0.0 else "0.0%"


def _cell_color_days(days: int):
    """Colour for a start/finish delta cell. Returns None if no change."""
    if days == 0:
        return None
    if abs(days) <= 2:
        return _YELLOW
    if abs(days) <= 5:
        return _ORANGE
    return _RED


def _cell_color_pct(pct: float):
    """Colour for a duration-% cell. Returns None if no change."""
    if abs(pct) < 0.05:
        return None
    if abs(pct) <= 10.0:
        return _YELLOW
    if abs(pct) <= 25.0:
        return _ORANGE
    return _RED

