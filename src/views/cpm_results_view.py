# cpm_results_view.py — Read-only CPM results panel
#
# Displays per-task ES / EF / LS / LF / Total Float / Free Float / Status
# in a QTableWidget.  Refreshed by calling refresh(float_data, all_tasks).
#
# CPM data must come from gantt_view._compute_critical_ids(return_float_data=True).

from PyQt5.QtWidgets import (  # type: ignore
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QHeaderView, QCheckBox, QPushButton, QLabel, QFileDialog, QAbstractItemView,
)
from PyQt5.QtCore import Qt, pyqtSignal  # type: ignore
from PyQt5.QtGui import QColor, QFont  # type: ignore
from datetime import datetime, timedelta

_WORK_HOURS_PER_DAY = 8.0

_COL_NAMES = [
    "Task Name", "Duration", "Early Start", "Early Finish",
    "Late Start", "Late Finish", "Total Float", "Free Float", "Status",
]

_COLOR_CRITICAL    = QColor(0xFD, 0xEC, 0xEA)
_COLOR_CRIT_TEXT   = QColor(0xC0, 0x39, 0x2B)
_COLOR_NEAR_CRIT   = QColor(0xFE, 0xF9, 0xE7)


def _fmt_dt(v) -> str:
    """Format a datetime-like value to a short date string."""
    try:
        if v is None:
            return ""
        if isinstance(v, datetime):
            return v.strftime("%d %b %Y")
        return str(v)[:10]
    except Exception:
        return ""


def _fmt_td(v: timedelta | None, wdh: float = _WORK_HOURS_PER_DAY) -> str:
    """Format a timedelta to 'Xd' using working-day hours."""
    try:
        if v is None:
            return ""
        days = round(v.total_seconds() / 3600 / max(wdh, 1), 1)
        return f"{days}d"
    except Exception:
        return ""


def _fmt_wh(working_hours, wdh: float = _WORK_HOURS_PER_DAY) -> str:
    """Format working hours (float) to 'Xd' using *wdh* hours/day.

    Used for Phase 5 calendar-aware float display when ``total_float_wh``
    / ``free_float_wh`` are present in float_data.
    """
    try:
        if working_hours is None:
            return ""
        days = round(float(working_hours) / max(wdh, 1), 1)
        return f"{days}d"
    except Exception:
        return ""


class CpmResultsView(QWidget):
    """Read-only panel showing the CPM analysis results for the open project."""

    #: Emitted when the user double-clicks a row.  Carries the integer task ID.
    task_double_clicked = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._float_data: dict = {}
        self._all_tasks: list  = []
        self._work_day_hours: float = _WORK_HOURS_PER_DAY
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Toolbar
        toolbar = QHBoxLayout()
        self._chk_critical_only = QCheckBox("Critical tasks only")
        self._chk_critical_only.toggled.connect(self._apply_filter)
        toolbar.addWidget(self._chk_critical_only)
        toolbar.addStretch()
        export_btn = QPushButton("Export CSV…")
        export_btn.clicked.connect(self._export_csv)
        toolbar.addWidget(export_btn)
        layout.addLayout(toolbar)

        # Table
        self._table = QTableWidget(0, len(_COL_NAMES))
        self._table.setHorizontalHeaderLabels(_COL_NAMES)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setAlternatingRowColors(False)
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        for c in range(1, len(_COL_NAMES)):
            self._table.horizontalHeader().setSectionResizeMode(c, QHeaderView.ResizeToContents)
        self._table.verticalHeader().setDefaultSectionSize(22)
        self._table.cellDoubleClicked.connect(self._on_double_click)
        layout.addWidget(self._table)

        self._status_lbl = QLabel("")
        layout.addWidget(self._status_lbl)

    def refresh(self, float_data: dict, all_tasks: list, work_day_hours: float = _WORK_HOURS_PER_DAY):
        """Populate the table from float_data and all_tasks.

        float_data: int tid → {es, ef, ls, lf, total_float, free_float, critical}
        all_tasks:  list of MPXJ Task objects (used for task names)
        """
        self._float_data = float_data or {}
        self._all_tasks  = all_tasks  or []
        self._work_day_hours = max(work_day_hours, 1.0)
        self._populate()

    def _populate(self):
        fd   = self._float_data
        only = self._chk_critical_only.isChecked()
        wdh  = self._work_day_hours

        # Build name map from all_tasks
        name_map: dict = {}
        for t in self._all_tasks:
            try:
                tid = int(str(t.getID()))
                name = str(t.getName()) if t.getName() else "(unnamed)"
                name_map[tid] = name
            except Exception:
                pass

        rows = []
        for tid, data in fd.items():
            if only and not data.get("critical"):
                continue
            rows.append((tid, data))

        # Sort: critical first, then by name
        rows.sort(key=lambda r: (not r[1].get("critical"), name_map.get(r[0], "")))

        self._table.setRowCount(len(rows))
        _bold = QFont()
        _bold.setBold(True)

        for row_idx, (tid, data) in enumerate(rows):
            is_crit = bool(data.get("critical"))
            dur_td  = data.get("ef", None) and data.get("es", None)

            # Use per-task calendar wdh when available (Phase 5), else global wdh
            row_wdh = data.get("work_day_hours") or wdh

            # duration = ef - es
            dur_str = ""
            try:
                es = data.get("es")
                ef = data.get("ef")
                if es is not None and ef is not None:
                    dur_td = ef - es
                    dur_str = _fmt_td(dur_td, row_wdh)
            except Exception:
                pass

            # Float columns: prefer calendar-aware working hours (Phase 5)
            tf_wh = data.get("total_float_wh")
            ff_wh = data.get("free_float_wh")
            if tf_wh is not None:
                tf_str = _fmt_wh(tf_wh, row_wdh)
            else:
                tf_str = _fmt_td(data.get("total_float"), row_wdh)
            if ff_wh is not None:
                ff_str = _fmt_wh(ff_wh, row_wdh)
            else:
                ff_str = _fmt_td(data.get("free_float"), row_wdh)

            cells = [
                name_map.get(tid, f"Task {tid}"),
                dur_str,
                _fmt_dt(data.get("es")),
                _fmt_dt(data.get("ef")),
                _fmt_dt(data.get("ls")),
                _fmt_dt(data.get("lf")),
                tf_str,
                ff_str,
                "CRITICAL" if is_crit else "OK",
            ]

            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignVCenter | (Qt.AlignLeft if col == 0 else Qt.AlignCenter))
                if is_crit:
                    item.setBackground(_COLOR_CRITICAL)
                    item.setForeground(_COLOR_CRIT_TEXT)
                    if col == 0:
                        item.setFont(_bold)
                if col == 0:
                    item.setData(Qt.UserRole, tid)  # store task ID for double-click lookup
                self._table.setItem(row_idx, col, item)

        critical_count = sum(1 for _, d in rows if d.get("critical"))
        self._status_lbl.setText(
            f"{len(rows)} task(s) shown — {critical_count} critical"
        )

    def _on_double_click(self, row: int, _col: int):
        """Emit task_double_clicked with the task ID stored in the row."""
        item = self._table.item(row, 0)
        if item is None:
            return
        tid = item.data(Qt.UserRole)
        if tid is not None:
            self.task_double_clicked.emit(int(tid))

    def _apply_filter(self):
        self._populate()

    def _export_csv(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export CPM Results", "", "CSV Files (*.csv)"
        )
        if not path:
            return
        import csv
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(_COL_NAMES)
            for row in range(self._table.rowCount()):
                writer.writerow([
                    (self._table.item(row, col).text() if self._table.item(row, col) else "")
                    for col in range(self._table.columnCount())
                ])
