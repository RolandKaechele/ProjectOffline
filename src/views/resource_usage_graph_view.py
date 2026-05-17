# resource_usage_graph_view.py - Resource Usage Graph view for Project Offline
#
# Displays resource work allocation as a day-by-day timeline grid, mirroring
# MS Project's "Resource Usage" view.
#
# Layout:
#   nav_bar          ← "◀ Today" navigation button
#   hdr_row          ← left corner header + scrollable GanttHeader
#   body_row
#     ├─ left_area   ← _LeftPane (resource / task name + total work)
#     ├─ right_area  ← _UsageCanvas (daily hours cells) inside QScrollArea
#     └─ vsb         ← external QScrollBar keeping both sides in sync
#
# Data model:
#   Each project resource produces one "resource" row (bold, collapsible).
#   Each assignment on that resource produces one "task" sub-row.
#   Daily hours per task row are computed by evenly distributing the
#   assignment work over its working days (Mon–Fri).
#   Resource rows aggregate the daily hours of all their visible task rows.

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from PyQt5.QtWidgets import (  # type: ignore
    QWidget, QScrollArea, QSizePolicy, QHBoxLayout, QVBoxLayout,
    QFrame, QLabel, QPushButton, QScrollBar, QAbstractScrollArea, QApplication,
    QMenu, QToolTip,
)
from PyQt5.QtGui import (  # type: ignore
    QPainter, QColor, QFont, QPen, QBrush, QFontMetrics, QPolygon,
)
from PyQt5.QtCore import Qt, QRect, QDate, QSize, QPoint, QObject, QEvent, pyqtSignal  # type: ignore

from gantt_view import (  # type: ignore
    GanttHeader, _to_qdate, _get_non_working_dates,
    DAY_WIDTH_DEF, DAY_WIDTH_MIN, DAY_WIDTH_MAX,
    HEADER_HEIGHT, HEADER_MONTH_H, HEADER_WEEK_H, NAV_BAR_HEIGHT,
)
from hour_mode import (  # type: ignore
    HOUR_MODE_THRESHOLD, WORK_HOUR_START, WORK_HOUR_END, WORK_DAY_HOURS,
    HourModeHeader, read_work_hours, date_to_working_day_idx,
)

# ---------------------------------------------------------------------------
# Wheel-event forwarder — redirects scroll gestures from the frozen left pane
# to the right canvas so both horizontal and vertical scrolling always moves
# the chart rather than the frozen columns independently.


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


class _WheelForwarder(QObject):
    """Event filter that forwards wheel events from a source viewport to a
    target QScrollArea, keeping the frozen left pane from consuming gestures
    that should scroll the timeline.
    """
    def __init__(self, target_scroll_area, parent=None):
        super().__init__(parent)
        self._target = target_scroll_area

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Wheel:
            QApplication.sendEvent(self._target.viewport(), event)
            return True   # consume from source so it doesn't double-scroll
        return False


# ---------------------------------------------------------------------------
# Layout constants
# ---------------------------------------------------------------------------

LEFT_NAME_W   = 240   # width of the "Resource Name" sub-column
LEFT_WORK_W   = 80    # width of the "Work" sub-column
LEFT_W        = LEFT_NAME_W + LEFT_WORK_W   # total frozen-pane width
ROW_H         = 36    # height of every row (matches other views)
DETAILS_COL_W = 60    # narrow "Details/Work" label column on the right pane
TRI_W         = 10    # width of the collapse/expand triangle
INDENT_PX     = 20    # pixels per outline level in the left pane
MONTH_MODE_THRESHOLD = 7   # day_width (px) below this → monthly columns
                           #   4–6 px/day → ~88–132 px per month column
WEEK_MODE_THRESHOLD  = 14  # day_width (px) below this (but ≥ MONTH_MODE_THRESHOLD) → weekly
                           #   7–13 px/day → 49–91 px per week column
                           # Aligns with GanttHeader: at <14px day numbers are hidden and
                           # week numbers are shown instead.
# HOUR_MODE_THRESHOLD, WORK_HOUR_START, WORK_HOUR_END, WORK_DAY_HOURS imported from hour_mode

# Palette
_C_RES_BG       = QColor(236, 243, 251)   # resource row background (light blue)
_C_RES_BG_ALT   = QColor(225, 235, 248)   # alternate resource row background
_C_TASK_BG_EVEN = QColor(255, 255, 255)
_C_TASK_BG_ODD  = QColor(248, 250, 255)
_C_WORK_CELL    = QColor(70, 130, 200, 60)  # filled hour cell background
_C_GRID         = QColor(210, 220, 235)
_C_WEEKEND      = QColor(222, 222, 222)
_C_TODAY_LINE   = QColor(0, 168, 0)
_C_RES_TEXT     = QColor(26, 63, 122)
_C_TASK_TEXT    = QColor(30, 30, 30)
_C_HEADER_BG    = QColor(210, 228, 252)
_C_SEP             = QColor(140, 175, 215)
_C_VACATION_FILL   = QColor(255, 160, 100, 100)  # semi-transparent orange overlay
_C_VACATION_BORDER = QColor(190, 90, 30, 180)    # darker orange border
_C_VACATION_TEXT   = QColor(130, 50, 10)          # dark-brown label text


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _working_days_in_range(start_qd: QDate, end_qd: QDate) -> int:
    """Count Mon–Fri days between start_qd and end_qd (inclusive)."""
    if not start_qd or not end_qd or end_qd < start_qd:
        return 0
    count = 0
    d = start_qd
    while d <= end_qd:
        if d.dayOfWeek() not in (6, 7):   # 6=Sat, 7=Sun
            count += 1
        d = d.addDays(1)
    return count


def _parse_work_hours(work_obj) -> float:
    """Extract total hours from an MPXJ Duration object.

    MPXJ TimeUnit.toString() returns short abbreviations: 'h', 'm', 'd', 'w', 'mo'.
    We handle both abbreviations and full names (HOURS, MINUTES, …) for safety.
    """
    if work_obj is None:
        return 0.0
    try:
        val = float(str(work_obj.getDuration()))
        raw_unit = str(work_obj.getUnits()) if work_obj.getUnits() else "h"
        u = raw_unit.strip().lower()
        # Short MPXJ abbreviations: h, m, d, w, mo / full names: hours, minutes, days …
        if u in ("h", "eh") or "hour" in u:
            return val
        if u in ("m", "em") or "minute" in u:
            return val / 60.0
        if u in ("d", "ed") or "day" in u:
            return val * 8.0
        if u in ("w", "ew") or "week" in u:
            return val * 40.0
        if u in ("mo", "emo") or "month" in u:
            return val * 160.0
        return val  # unknown unit — return as-is (assume hours)
    except Exception:
        return 0.0


def _build_daily_hours(start_qd: QDate, end_qd: QDate,
                       total_hours: float) -> dict:
    """Return {QDate: hours} distributing total_hours evenly over Mon–Fri days.

    If there are no working days in the range the dict is empty.
    """
    daily: dict = {}
    if not start_qd or not end_qd or total_hours <= 0:
        return daily
    wd = _working_days_in_range(start_qd, end_qd)
    if wd == 0:
        return daily
    h_per_day = total_hours / wd
    d = start_qd
    while d <= end_qd:
        if d.dayOfWeek() not in (6, 7):
            daily[d] = h_per_day
        d = d.addDays(1)
    return daily


def _hrs_label(h: float, compact: bool = False) -> str:
    """Format hours as compact label, e.g. '8h', '0.67h'.

    Two decimal places are used so that independently-rounded task values
    still sum visually to the resource-row total (rounding error ≤ 0.01 per
    value vs. ≤ 0.1 with one decimal place).  Trailing zeros are stripped so
    exact halves show as '0.5h' rather than '0.50h', and whole numbers show
    as '8h' rather than '8.00h'.

    When *compact* is True (used when the cell is too narrow for two decimal
    places) only one decimal place is rendered, e.g. '5.3h' instead of
    '5.33h'.  This prevents the label from overflowing the cell boundary.
    """
    if h == 0:
        return ""
    if h == int(h):
        return f"{int(h)}h"
    if compact:
        s = f"{h:.1f}".rstrip('0').rstrip('.')
    else:
        s = f"{h:.2f}".rstrip('0')
    return s + "h"


def _get_resource_vacation_blocks(resource) -> list:
    """Return a list of {from_qd, to_qd, name} dicts for every non-working
    calendar exception on the resource's personal calendar (vacations, absences).
    """
    blocks = []
    try:
        cal = resource.getCalendar()
        if cal is None:
            return blocks
        for ex in cal.getCalendarExceptions():
            try:
                if bool(ex.getWorking()):
                    continue
            except Exception:
                pass
            from_str = str(ex.getFromDate() or "")[:10]
            to_str   = str(ex.getToDate()   or "")[:10]
            if not from_str:
                continue
            from_qd = QDate.fromString(from_str, "yyyy-MM-dd")
            to_qd   = QDate.fromString(to_str, "yyyy-MM-dd") if to_str else from_qd
            if not from_qd.isValid():
                continue
            if not to_qd.isValid():
                to_qd = from_qd
            name = str(ex.getName() or "Vacation")
            blocks.append({'from_qd': from_qd, 'to_qd': to_qd, 'name': name})
        blocks.sort(key=lambda b: b['from_qd'].toJulianDay())
    except Exception:
        pass
    return blocks


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

class _Row:
    """Represents one row in the left/right panes."""
    __slots__ = ('kind', 'name', 'total_h', 'daily', 'res_idx',
                 'collapsed', 'visible', 'vacations', 'task')

    def __init__(self, kind: str, name: str, total_h: float,
                 daily: dict, res_idx: int):
        self.kind      = kind        # 'resource' or 'task'
        self.name      = name
        self.total_h   = total_h    # pre-computed; resource rows re-sum on render
        self.daily     = daily      # {QDate: float}
        self.res_idx   = res_idx    # for alternating colour bands
        self.collapsed = False       # only used on 'resource' rows
        self.visible   = True        # set by _build_visible_rows
        self.vacations: list = []    # vacation blocks (resource rows only)
        self.task      = None        # java Task object (task rows only)


# ---------------------------------------------------------------------------
# Left pane — resource/task name + total work
# ---------------------------------------------------------------------------

class _LeftPane(QWidget):
    """Paints the frozen left column: resource name (collapsible) + total work."""

    jump_to_allocation_requested      = pyqtSignal(int)   # vis_idx of resource row
    jump_task_to_allocation_requested = pyqtSignal(int)   # vis_idx of task row
    task_info_requested               = pyqtSignal(object)  # java Task

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: list[_Row] = []
        self._vis:  list[_Row] = []
        self._scroll_y = 0
        self.setFixedWidth(LEFT_W)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

    def set_rows(self, rows: list, vis: list):
        self._rows = rows
        self._vis  = vis
        self.setMinimumHeight(len(vis) * ROW_H)
        self.update()

    def set_scroll_y(self, y: int):
        self._scroll_y = y
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        fm = QFontMetrics(QFont("Segoe UI", 9))

        for i, row in enumerate(self._vis):
            y = i * ROW_H - self._scroll_y
            if y + ROW_H < 0 or y > self.height():
                continue

            # Background
            if row.kind == 'resource':
                bg = _C_RES_BG if row.res_idx % 2 == 0 else _C_RES_BG_ALT
            else:
                bg = _C_TASK_BG_EVEN if i % 2 == 0 else _C_TASK_BG_ODD
            painter.fillRect(0, y, LEFT_W, ROW_H, bg)

            # Horizontal grid line
            painter.setPen(QPen(_C_GRID, 1))
            painter.drawLine(0, y + ROW_H - 1, LEFT_W, y + ROW_H - 1)

            # Vertical separator between Name and Work columns
            painter.drawLine(LEFT_NAME_W, y, LEFT_NAME_W, y + ROW_H)

            # ----- Name column -----
            if row.kind == 'resource':
                # Triangle indicator
                cx = 6
                cy = y + ROW_H // 2
                painter.setBrush(QBrush(_C_RES_TEXT))
                painter.setPen(Qt.NoPen)
                if row.collapsed:
                    pts = QPolygon([QPoint(cx, cy - 5),
                                    QPoint(cx + TRI_W, cy),
                                    QPoint(cx, cy + 5)])
                else:
                    pts = QPolygon([QPoint(cx, cy - 4),
                                    QPoint(cx + TRI_W, cy - 4),
                                    QPoint(cx + 5, cy + 5)])
                painter.drawPolygon(pts)

                font = QFont("Segoe UI", 9)
                font.setBold(True)
                painter.setFont(font)
                painter.setPen(_C_RES_TEXT)
                text_x = TRI_W + 10
            else:
                font = QFont("Segoe UI", 9)
                painter.setFont(font)
                painter.setPen(_C_TASK_TEXT)
                text_x = INDENT_PX + 4

            name_rect = QRect(text_x, y, LEFT_NAME_W - text_x - 4, ROW_H)
            painter.drawText(name_rect, Qt.AlignVCenter | Qt.AlignLeft,
                             fm.elidedText(row.name, Qt.ElideRight,
                                           name_rect.width()))

            # ----- Work column -----
            total_h = row.total_h
            work_rect = QRect(LEFT_NAME_W + 4, y, LEFT_WORK_W - 8, ROW_H)
            font2 = QFont("Segoe UI", 9)
            if row.kind == 'resource':
                font2.setBold(True)
            painter.setFont(font2)
            painter.setPen(_C_RES_TEXT if row.kind == 'resource' else _C_TASK_TEXT)
            painter.drawText(work_rect, Qt.AlignVCenter | Qt.AlignRight,
                             _hrs_label(total_h))

        # Right border
        painter.setPen(QPen(_C_SEP, 2))
        painter.drawLine(LEFT_W - 1, 0, LEFT_W - 1, self.height())

    def mousePressEvent(self, event):
        """Toggle collapse/expand when clicking on a resource row triangle."""
        y_local = event.y() + self._scroll_y
        idx = y_local // ROW_H
        if 0 <= idx < len(self._vis):
            row = self._vis[idx]
            if row.kind == 'resource':
                # Check if click is in the triangle area
                if event.x() <= TRI_W + 10:
                    row.collapsed = not row.collapsed
                    # Notify parent to rebuild visible rows
                    p = self.parent()
                    while p and not hasattr(p, '_rebuild_visible'):
                        p = p.parent() if hasattr(p, 'parent') else None
                    if p:
                        p._rebuild_visible()
        super().mousePressEvent(event)

    def contextMenuEvent(self, event):
        """Show 'Jump to first time allocation' context menu on resource and task rows."""
        y_local = event.y() + self._scroll_y
        idx = y_local // ROW_H
        if not (0 <= idx < len(self._vis)):
            return
        row = self._vis[idx]
        if row.kind == 'resource':
            menu = QMenu(self)
            act_jump = menu.addAction("Jump to first time allocation in chart")
            action = menu.exec_(event.globalPos())
            if action == act_jump:
                self.jump_to_allocation_requested.emit(idx)
        elif row.kind == 'task' and row.daily:
            menu = QMenu(self)
            act_jump = menu.addAction("Jump to first time allocation in chart")
            action = menu.exec_(event.globalPos())
            if action == act_jump:
                self.jump_task_to_allocation_requested.emit(idx)

    def mouseDoubleClickEvent(self, event):
        """Open task info dialog on double-click on a task row."""
        if event.button() == Qt.LeftButton:
            y_local = event.y() + self._scroll_y
            idx = y_local // ROW_H
            if 0 <= idx < len(self._vis):
                row = self._vis[idx]
                if row.kind == 'task' and row.task is not None:
                    self.task_info_requested.emit(row.task)
        super().mouseDoubleClickEvent(event)


# HourModeHeader is imported from hour_mode — no local class needed


# ---------------------------------------------------------------------------
# Right canvas — daily hours cells
# ---------------------------------------------------------------------------

class _UsageCanvas(QWidget):
    """Paints the day grid: one column per day, one cell per visible row."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: list[_Row] = []
        self._vis:  list[_Row] = []
        self._project_start: QDate | None = None
        self._total_days     = 0
        self._day_width      = DAY_WIDTH_DEF
        self._show_sundays   = True
        self._non_working:   set = set()
        self._work_hour_start  = WORK_HOUR_START
        self._work_day_hours   = WORK_DAY_HOURS  # actual working hours (excl. breaks)
        self._clock_day_span   = WORK_DAY_HOURS  # total clock columns shown per day
        self._non_working_slots: frozenset = frozenset()
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMouseTracking(True)   # needed for tooltip without click

    def configure(self, rows, vis, project_start: QDate, total_days: int,
                  day_width: int, show_sundays: bool, non_working: set,
                  work_hour_start: int       = WORK_HOUR_START,
                  work_day_hours: int        = WORK_DAY_HOURS,
                  clock_day_span: int        = WORK_DAY_HOURS,
                  non_working_slots: frozenset = frozenset()):
        self._rows            = rows
        self._vis             = vis
        self._project_start   = project_start
        self._total_days      = total_days
        self._day_width       = day_width
        self._show_sundays    = show_sundays
        self._non_working     = non_working
        self._work_hour_start = work_hour_start
        self._work_day_hours  = work_day_hours
        self._clock_day_span  = clock_day_span
        self._non_working_slots = non_working_slots
        self._update_size()
        self.update()

    def _col_x(self, date: QDate) -> int:
        """Return the x-coordinate of the left edge of the column for date."""
        if not self._project_start:
            return 0
        if self._day_width >= HOUR_MODE_THRESHOLD:
            # Hourly mode: each working day (Mon–Fri) spans _clock_day_span * _day_width px
            wday_idx = date_to_working_day_idx(date, self._project_start)
            return wday_idx * self._clock_day_span * self._day_width
        x = 0
        d = self._project_start
        while d < date:
            dow = d.dayOfWeek()
            if self._show_sundays or dow != 7:
                x += self._day_width
            d = d.addDays(1)
        return x

    def _visible_cols(self) -> int:
        count = 0
        for i in range(self._total_days):
            d = self._project_start.addDays(i)
            if self._show_sundays or d.dayOfWeek() != 7:
                count += 1
        return count

    def _update_size(self):
        if not self._project_start:
            return
        if self._day_width >= HOUR_MODE_THRESHOLD:
            # In hourly mode day_width = px-per-hour; count working days × hour slots
            working_days = sum(
                1 for di in range(self._total_days)
                if self._project_start.addDays(di).dayOfWeek() not in (6, 7)
            )
            w = working_days * self._clock_day_span * self._day_width
        else:
            cols = self._visible_cols()
            w = cols * self._day_width
        h = max(400, len(self._vis) * ROW_H)
        self.setFixedSize(w, h)
        self.updateGeometry()
        if self.parent():
            self.parent().updateGeometry()

    # -----------------------------------------------------------------------
    # Tooltip support
    # -----------------------------------------------------------------------

    def _x_to_date_info(self, x: int):
        """Map a canvas x-coordinate to (date, period_label) for the tooltip.

        Returns (QDate or None, str period_label).
        *date* is the representative date (start of the period).
        *period_label* is the human-readable period string, e.g.:
          daily   → 'Mon, 27 Apr 2026'
          weekly  → 'Week 18: 20 Apr – 26 Apr 2026'
          monthly → 'April 2026'
          hourly  → 'Mon, 27 Apr 2026  09:00–10:00'
        """
        if not self._project_start:
            return None, ""

        hourly  = self._day_width >= HOUR_MODE_THRESHOLD
        monthly = (not hourly) and self._day_width < MONTH_MODE_THRESHOLD
        weekly  = (not hourly) and (not monthly) and self._day_width < WEEK_MODE_THRESHOLD

        if hourly:
            slot_w  = self._day_width                          # px per clock-hour column
            day_px  = self._clock_day_span * slot_w           # px per working day
            wday_idx = x // day_px
            hi       = (x % day_px) // slot_w                 # which hour slot in day
            hour     = self._work_hour_start + hi
            # Walk through calendar days to find the wday_idx-th Mon-Fri
            wd = 0
            d = self._project_start
            while wd < wday_idx:
                d = d.addDays(1)
                if d.dayOfWeek() not in (6, 7):
                    wd += 1
                if d > self._project_start.addDays(self._total_days + 14):
                    return None, ""
            # Skip weekends at start
            while d.dayOfWeek() in (6, 7):
                d = d.addDays(1)
            label = f"{d.toString('ddd, d MMM yyyy')}  {hour:02d}:00\u2013{hour+1:02d}:00"
            return d, label

        elif monthly:
            # Find which month the x falls in by scanning month boundaries
            m = QDate(self._project_start.year(), self._project_start.month(), 1)
            last_day = self._project_start.addDays(self._total_days - 1)
            while m <= last_day:
                x_left  = self._col_x(m)
                x_right = self._col_x(m.addMonths(1))
                if x_left <= x < x_right:
                    return m, m.toString('MMMM yyyy')
                m = m.addMonths(1)
            return None, ""

        elif weekly:
            ps_dow   = self._project_start.dayOfWeek()
            week_mon = self._project_start.addDays(-(ps_dow - 1))
            last_day = self._project_start.addDays(self._total_days - 1)
            while week_mon <= last_day:
                x_left  = self._col_x(week_mon)
                x_right = self._col_x(week_mon.addDays(7))
                if x_left <= x < x_right:
                    week_sun = week_mon.addDays(6)
                    wn = week_mon.weekNumber()[0]
                    label = (f"Week {wn}: {week_mon.toString('d MMM')}"
                             f" \u2013 {week_sun.toString('d MMM yyyy')}")
                    return week_mon, label
                week_mon = week_mon.addDays(7)
            return None, ""

        else:  # daily
            col = x // self._day_width
            c = 0
            for di in range(self._total_days):
                d = self._project_start.addDays(di)
                if not self._show_sundays and d.dayOfWeek() == 7:
                    continue
                if c == col:
                    return d, d.toString('ddd, d MMM yyyy')
                c += 1
            return None, ""

    def mouseMoveEvent(self, event):
        """Show a tooltip with date/period and hours when hovering over a cell."""
        if not self._project_start or not self._vis:
            QToolTip.hideText()
            super().mouseMoveEvent(event)
            return

        x = event.x()
        y = event.y()
        row_idx = y // ROW_H
        if not (0 <= row_idx < len(self._vis)):
            QToolTip.hideText()
            super().mouseMoveEvent(event)
            return

        row  = self._vis[row_idx]
        date, period_label = self._x_to_date_info(x)

        if date is None:
            QToolTip.hideText()
            super().mouseMoveEvent(event)
            return

        # ---------- collect the hours value for this cell ----------
        hourly  = self._day_width >= HOUR_MODE_THRESHOLD
        monthly = (not hourly) and self._day_width < MONTH_MODE_THRESHOLD
        weekly  = (not hourly) and (not monthly) and self._day_width < WEEK_MODE_THRESHOLD

        if hourly:
            # Value per hour-slot = daily_h / work_day_hours
            daily_h = row.daily.get(date, 0.0)
            cell_h  = daily_h / self._work_day_hours if self._work_day_hours else 0.0
            day_h   = daily_h
        elif monthly:
            # Sum all days in the month
            next_m = date.addMonths(1)
            d = date
            cell_h = 0.0
            while d < next_m:
                cell_h += row.daily.get(d, 0.0)
                d = d.addDays(1)
            day_h = None
        elif weekly:
            # Sum Mon–Sun
            d = date
            cell_h = 0.0
            for _ in range(7):
                cell_h += row.daily.get(d, 0.0)
                d = d.addDays(1)
            day_h = None
        else:
            cell_h = row.daily.get(date, 0.0)
            day_h = None

        # ---------- build tooltip text ----------
        lines = []
        if row.kind == 'resource':
            lines.append(f"<b>{row.name}</b>")
        else:
            # Find parent resource name
            res_name = ""
            for r in reversed(self._vis[:row_idx]):
                if r.kind == 'resource':
                    res_name = r.name
                    break
            if res_name:
                lines.append(f"<b>{res_name}</b>")
            lines.append(f"Task: {row.name}")

        lines.append(f"Period: {period_label}")

        if cell_h > 0:
            lines.append(f"Hours: <b>{_hrs_label(cell_h)}</b>")
            if hourly and day_h is not None and day_h > 0:
                lines.append(f"Full day: {_hrs_label(day_h)}"
                             f" / {self._work_day_hours}h working")
        else:
            lines.append("Hours: <i>none</i>")

        tip = "<br>".join(lines)
        QToolTip.showText(event.globalPos(), tip, self)
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        QToolTip.hideText()
        super().leaveEvent(event)

    def paintEvent(self, event):
        if not self._project_start or not self._vis:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        today    = QDate.currentDate()
        w        = self.width()
        h        = self.height()
        hourly   = self._day_width >= HOUR_MODE_THRESHOLD
        monthly  = (not hourly) and self._day_width < MONTH_MODE_THRESHOLD
        weekly   = (not hourly) and (not monthly) and self._day_width < WEEK_MODE_THRESHOLD
        last_day = self._project_start.addDays(self._total_days - 1)

        # ── Row backgrounds ──────────────────────────────────────────
        for i, row in enumerate(self._vis):
            y = i * ROW_H
            if row.kind == 'resource':
                bg = _C_RES_BG if row.res_idx % 2 == 0 else _C_RES_BG_ALT
            else:
                bg = _C_TASK_BG_EVEN if i % 2 == 0 else _C_TASK_BG_ODD
            painter.fillRect(0, y, w, ROW_H, bg)
            painter.setPen(QPen(_C_GRID, 1))
            painter.drawLine(0, y + ROW_H - 1, w, y + ROW_H - 1)

        font_sm = QFont("Segoe UI", 8)
        painter.setFont(font_sm)

        def _draw_period_cells(x_left, col_w, row_sums):
            """Fill hour cells and labels for a weekly or monthly period column."""
            for ri, row in enumerate(self._vis):
                hrs = row_sums.get(ri, 0.0)
                if hrs <= 0:
                    continue
                cy = ri * ROW_H
                painter.fillRect(x_left + 1, cy + 3,
                                 col_w - 2, ROW_H - 6, _C_WORK_CELL)
                if col_w >= 20:
                    painter.setPen(_C_RES_TEXT if row.kind == 'resource'
                                   else _C_TASK_TEXT)
                    painter.drawText(QRect(x_left, cy, col_w, ROW_H),
                                     Qt.AlignCenter, _hrs_label(hrs))

        def _sum_period(eff_start, eff_end):
            """Return {row_index: total_hours} and whether today is in this period."""
            sums: dict = {}
            today_here = False
            d = eff_start
            while d <= eff_end:
                if d == today:
                    today_here = True
                for ri, row in enumerate(self._vis):
                    hrs = row.daily.get(d, 0.0)
                    if hrs:
                        sums[ri] = sums.get(ri, 0.0) + hrs
                d = d.addDays(1)
            return sums, today_here

        if hourly:
            # ── HOURLY mode: one column per clock hour in the work-day window ──
            day_idx = 0
            for di in range(self._total_days):
                d   = self._project_start.addDays(di)
                dow = d.dayOfWeek()
                if dow in (6, 7):
                    continue

                day_x  = day_idx * self._clock_day_span * self._day_width
                day_w  = self._clock_day_span * self._day_width
                is_nwd = d.toString("yyyy-MM-dd") in self._non_working

                # Day background shading
                if is_nwd:
                    painter.fillRect(day_x, 0, day_w, h, _C_WEEKEND)
                elif day_idx % 2 == 1:
                    painter.fillRect(day_x, 0, day_w, h, QColor(240, 244, 252, 80))

                # Day-boundary separator
                painter.setPen(QPen(QColor(100, 130, 180), 1))
                painter.drawLine(day_x, 0, day_x, h)

                # Today indicator
                if d == today:
                    painter.setPen(QPen(_C_TODAY_LINE, 2))
                    painter.drawLine(day_x, 0, day_x, h)

                for hi in range(self._clock_day_span):
                    hx       = day_x + hi * self._day_width
                    hour     = self._work_hour_start + hi
                    is_break = hour in self._non_working_slots

                    # Hour-column separator
                    painter.setPen(QPen(_C_GRID, 1))
                    painter.drawLine(hx, 0, hx, h)

                    # Grey out breaks (lunch etc.) with a distinct fill
                    if is_break:
                        painter.fillRect(hx, 0, self._day_width, h, _C_WEEKEND)
                        continue

                    # Holiday day — no work cells, just skip
                    if is_nwd:
                        continue

                    for ri, row in enumerate(self._vis):
                        daily_h = row.daily.get(d, 0.0)
                        if daily_h <= 0:
                            continue
                        # Distribute work over actual working hours (excl. breaks)
                        hour_h = daily_h / self._work_day_hours
                        cy = ri * ROW_H
                        painter.fillRect(hx + 1, cy + 3,
                                         self._day_width - 2, ROW_H - 6,
                                         _C_WORK_CELL)
                        if self._day_width >= 30:
                            painter.setPen(_C_RES_TEXT if row.kind == 'resource'
                                           else _C_TASK_TEXT)
                            painter.drawText(
                                QRect(hx, cy, self._day_width, ROW_H),
                                Qt.AlignCenter, _hrs_label(hour_h),
                            )

                day_idx += 1

        elif monthly:
            # ── MONTHLY mode: one column per calendar month ───────────
            month_start = QDate(self._project_start.year(),
                                self._project_start.month(), 1)
            month_idx = 0
            while month_start <= last_day:
                next_month = month_start.addMonths(1)
                eff_end    = next_month.addDays(-1)
                if eff_end > last_day:
                    eff_end = last_day

                x_left = self._col_x(month_start)
                x_right = self._col_x(next_month)
                col_w  = x_right - x_left

                if col_w > 0:
                    if month_idx % 2 == 1:
                        painter.fillRect(x_left, 0, col_w, h,
                                         QColor(240, 244, 252, 80))

                    sums, today_here = _sum_period(month_start, eff_end)
                    _draw_period_cells(x_left, col_w, sums)

                    painter.setPen(QPen(_C_GRID, 1))
                    painter.drawLine(x_left, 0, x_left, h)

                    if today_here:
                        today_x = self._col_x(today)
                        painter.setPen(QPen(_C_TODAY_LINE, 2))
                        painter.drawLine(today_x, 0, today_x, h)

                month_start = next_month
                month_idx  += 1

        elif weekly:
            # ── WEEKLY mode: one column per ISO week (Mon–Sun) ────────
            ps_dow   = self._project_start.dayOfWeek()   # 1=Mon … 7=Sun
            week_mon = self._project_start.addDays(-(ps_dow - 1))

            week_idx = 0
            while week_mon <= last_day:
                week_sun  = week_mon.addDays(6)
                eff_end   = week_sun if week_sun <= last_day else last_day

                x_left  = self._col_x(week_mon)
                x_right = self._col_x(week_mon.addDays(7))
                col_w   = x_right - x_left

                if col_w > 0:
                    if week_idx % 2 == 1:
                        painter.fillRect(x_left, 0, col_w, h,
                                         QColor(240, 244, 252, 80))

                    sums, today_here = _sum_period(week_mon, eff_end)
                    _draw_period_cells(x_left, col_w, sums)

                    painter.setPen(QPen(_C_GRID, 1))
                    painter.drawLine(x_left, 0, x_left, h)

                    if today_here:
                        today_x = self._col_x(today)
                        painter.setPen(QPen(_C_TODAY_LINE, 2))
                        painter.drawLine(today_x, 0, today_x, h)

                week_mon  = week_mon.addDays(7)
                week_idx += 1

        else:
            # ── DAILY mode: one column per day ────────────────────────
            col = 0
            for di in range(self._total_days):
                d   = self._project_start.addDays(di)
                dow = d.dayOfWeek()
                if not self._show_sundays and dow == 7:
                    continue

                x          = col * self._day_width
                iso        = d.toString("yyyy-MM-dd")
                is_sat_hol = (dow == 6 or iso in self._non_working)

                if is_sat_hol:
                    painter.fillRect(x, 0, self._day_width, h, _C_WEEKEND)
                elif dow == 7:
                    # Sunday: blue-tint, matching Gantt / Team Planner behaviour
                    painter.fillRect(x, 0, self._day_width, h, QColor(205, 215, 235, 140))

                if d == today:
                    painter.setPen(QPen(_C_TODAY_LINE, 2))
                    painter.drawLine(x, 0, x, h)

                painter.setPen(QPen(_C_GRID, 1))
                painter.drawLine(x, 0, x, h)

                for i, row in enumerate(self._vis):
                    if is_sat_hol or dow == 7:
                        break  # no work cells on weekends / public holidays
                    hrs = row.daily.get(d, 0.0)
                    if hrs <= 0:
                        continue
                    cy = i * ROW_H
                    painter.fillRect(x + 1, cy + 3,
                                     self._day_width - 2, ROW_H - 6,
                                     _C_WORK_CELL)
                    if self._day_width >= 18:
                        painter.setPen(_C_RES_TEXT if row.kind == 'resource'
                                       else _C_TASK_TEXT)
                        painter.drawText(
                            QRect(x, cy, self._day_width, ROW_H),
                            Qt.AlignCenter,
                            _hrs_label(hrs, compact=(self._day_width < 32)),
                        )

                col += 1

        # ── Vacation overlays (drawn on top of work cells) ────────────────────
        font_vac = QFont("Segoe UI", 7)
        font_vac.setItalic(True)
        fm_vac = QFontMetrics(font_vac)
        painter.setFont(font_vac)
        end_of_range = self._project_start.addDays(self._total_days)
        for i, row in enumerate(self._vis):
            if row.kind != 'resource' or not row.vacations:
                continue
            ry = i * ROW_H
            for vac in row.vacations:
                from_qd = vac['from_qd']
                to_qd   = vac['to_qd']
                if from_qd > end_of_range or to_qd < self._project_start:
                    continue
                if hourly:
                    # canvas _clock_day_span already reflects show_off_hours
                    eff_span = self._clock_day_span
                    x1 = (date_to_working_day_idx(from_qd, self._project_start)
                          * eff_span * self._day_width)
                    x2 = (date_to_working_day_idx(to_qd.addDays(1), self._project_start)
                          * eff_span * self._day_width)
                else:
                    x1 = self._col_x(from_qd)
                    x2 = self._col_x(to_qd.addDays(1))
                if x2 <= x1:
                    x2 = x1 + self._day_width
                bar_w = x2 - x1
                painter.setBrush(QBrush(_C_VACATION_FILL))
                painter.setPen(QPen(_C_VACATION_BORDER, 1))
                painter.drawRect(x1, ry, bar_w, ROW_H)
                if bar_w >= 20:
                    painter.setPen(_C_VACATION_TEXT)
                    label = fm_vac.elidedText(vac['name'], Qt.ElideRight, bar_w - 6)
                    painter.drawText(QRect(x1 + 3, ry + 2, bar_w - 6, ROW_H - 4),
                                     Qt.AlignTop | Qt.AlignLeft, label)


# ---------------------------------------------------------------------------
# Fixed "Work" body column — sits between left pane and the scrollable canvas
# ---------------------------------------------------------------------------

class _WorkBodyColumn(QWidget):
    """Fixed 60-px column that shows per-row 'Work' labels in the body.

    Mirrors _DetailsHeaderCell in the header so that _right_scroll and
    _hdr_area start at the same screen x-position, keeping day-column labels
    directly above their corresponding data cells regardless of scroll.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._vis: list = []
        self._scroll_y = 0
        self.setFixedWidth(DETAILS_COL_W)

    def set_rows(self, vis: list):
        self._vis = vis
        self.update()

    def set_scroll_y(self, y: int):
        self._scroll_y = y
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        font_sm = QFont("Segoe UI", 8)
        painter.setFont(font_sm)
        h = self.height()

        for i, row in enumerate(self._vis):
            y = i * ROW_H - self._scroll_y
            if y + ROW_H < 0 or y > h:
                continue
            if row.kind == 'resource':
                bg = _C_RES_BG if row.res_idx % 2 == 0 else _C_RES_BG_ALT
            else:
                bg = _C_TASK_BG_EVEN if i % 2 == 0 else _C_TASK_BG_ODD
            painter.fillRect(0, y, DETAILS_COL_W, ROW_H, bg)
            painter.setPen(QPen(_C_GRID, 1))
            painter.drawLine(0, y + ROW_H - 1, DETAILS_COL_W, y + ROW_H - 1)
            painter.setPen(_C_TASK_TEXT)
            painter.drawText(
                QRect(0, y, DETAILS_COL_W - 2, ROW_H),
                Qt.AlignVCenter | Qt.AlignRight, "Work",
            )

        # Right border separating this column from the canvas
        painter.setPen(QPen(_C_SEP, 1))
        painter.drawLine(DETAILS_COL_W - 1, 0, DETAILS_COL_W - 1, h)


# ---------------------------------------------------------------------------
# Header for the right pane (Details column + GanttHeader)
# ---------------------------------------------------------------------------

class _UsageHeaderCorner(QWidget):
    """The corner widget above the left pane — shows column labels."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(LEFT_W, HEADER_HEIGHT + NAV_BAR_HEIGHT)

    def paintEvent(self, event):
        painter = QPainter(self)
        # Nav bar area (blank)
        painter.fillRect(0, 0, LEFT_W, NAV_BAR_HEIGHT, QColor(245, 248, 255))
        # Header area
        y = NAV_BAR_HEIGHT
        painter.fillRect(0, y, LEFT_W, HEADER_HEIGHT, _C_HEADER_BG)

        painter.setPen(QPen(_C_SEP, 1))
        painter.drawLine(0, y, LEFT_W, y)                           # top line
        painter.drawLine(LEFT_NAME_W, y, LEFT_NAME_W, y + HEADER_HEIGHT)  # col sep
        painter.drawLine(LEFT_W - 1, y, LEFT_W - 1, y + HEADER_HEIGHT)    # right border

        font_b = QFont("Segoe UI", 9, QFont.Bold)
        painter.setFont(font_b)
        painter.setPen(_C_RES_TEXT)
        painter.drawText(QRect(4, y, LEFT_NAME_W - 4, HEADER_HEIGHT),
                         Qt.AlignVCenter | Qt.AlignLeft, "Resource Name")
        painter.drawText(QRect(LEFT_NAME_W + 2, y, LEFT_WORK_W - 4, HEADER_HEIGHT),
                         Qt.AlignVCenter | Qt.AlignRight, "Work")


class _DetailsHeaderCell(QWidget):
    """Fixed 'Details' header cell that sits to the left of GanttHeader."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(DETAILS_COL_W, HEADER_HEIGHT)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), _C_HEADER_BG)
        painter.setPen(QPen(_C_SEP, 1))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
        font_b = QFont("Segoe UI", 9, QFont.Bold)
        painter.setFont(font_b)
        painter.setPen(_C_RES_TEXT)
        painter.drawText(self.rect(), Qt.AlignCenter, "Details")


# ---------------------------------------------------------------------------
# Main view widget
# ---------------------------------------------------------------------------

class ResourceUsageGraphView(QWidget):
    """Resource Usage Graph — top-level tab widget.

    Displays each resource as a collapsible header row with task assignment
    sub-rows.  The right timeline shows how many hours each resource/task
    consumes per working day.
    """

    task_edited = pyqtSignal()   # emitted after a task is edited via double-click dialog

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project      = None
        self._rows: list[_Row] = []
        self._vis:  list[_Row] = []
        self._project_start: QDate | None = None
        self._total_days      = 0
        self._day_width       = DAY_WIDTH_DEF
        self._show_sundays    = True
        self._non_working:    set = set()
        self._work_hour_start = WORK_HOUR_START
        self._work_hour_end   = WORK_HOUR_END
        self._work_day_hours  = WORK_DAY_HOURS
        self._clock_day_span  = WORK_DAY_HOURS  # clock hours shown per day
        self._day_non_working: frozenset = frozenset()  # hours that are breaks
        self._show_off_hours  = False  # show columns outside the working window

        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Navigation bar ──────────────────────────────────────────
        nav_bar = QWidget()
        nav_bar.setFixedHeight(NAV_BAR_HEIGHT)
        nav_bar.setObjectName("UsageNavBar")
        nav_layout = QHBoxLayout(nav_bar)
        nav_layout.setContentsMargins(4, 2, 4, 2)
        nav_layout.setSpacing(4)

        today_btn = QPushButton("◀ Today")
        today_btn.setFixedHeight(NAV_BAR_HEIGHT - 4)
        today_btn.clicked.connect(self._scroll_to_today)
        nav_layout.addWidget(today_btn)
        nav_layout.addStretch(1)
        root.addWidget(nav_bar)

        # ── Header row ───────────────────────────────────────────────
        hdr_row = QWidget()
        hdr_layout = QHBoxLayout(hdr_row)
        hdr_layout.setContentsMargins(0, 0, 0, 0)
        hdr_layout.setSpacing(0)

        self._corner = _UsageHeaderCorner()
        hdr_layout.addWidget(self._corner)

        # "Details" cell before GanttHeader
        self._details_cell = _DetailsHeaderCell()

        # GanttHeader inside a no-scrollbar scroll area
        self._hdr_area = QScrollArea()
        self._hdr_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._hdr_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._hdr_area.setWidgetResizable(False)
        self._hdr_area.setFrameShape(QFrame.NoFrame)
        self._hdr_area.setFixedHeight(HEADER_HEIGHT)

        self._gantt_hdr = GanttHeader()
        self._hour_hdr  = HourModeHeader(HEADER_HEIGHT, HEADER_MONTH_H, HEADER_WEEK_H)  # shown only in hourly zoom mode
        self._hdr_area.setWidget(self._gantt_hdr)

        # Wrap details cell + header in a single horizontal widget
        hdr_right = QWidget()
        hdr_right_layout = QHBoxLayout(hdr_right)
        hdr_right_layout.setContentsMargins(0, 0, 0, 0)
        hdr_right_layout.setSpacing(0)
        hdr_right_layout.addWidget(self._details_cell)
        hdr_right_layout.addWidget(self._hdr_area)

        hdr_layout.addWidget(hdr_right, 1)

        # Spacer matching scrollbar width
        self._hdr_spacer = QWidget()
        self._hdr_spacer.setFixedWidth(0)   # updated when vsb is visible
        hdr_layout.addWidget(self._hdr_spacer)

        root.addWidget(hdr_row)

        # ── Body row ─────────────────────────────────────────────────
        body_row = QWidget()
        body_layout = QHBoxLayout(body_row)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        # Left pane (frozen resource/task names + work)
        self._left_scroll = QScrollArea()
        self._left_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._left_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._left_scroll.setFrameShape(QFrame.NoFrame)
        self._left_scroll.setWidgetResizable(False)
        self._left_pane = _LeftPane()
        self._left_scroll.setWidget(self._left_pane)
        self._left_scroll.setFixedWidth(LEFT_W)
        body_layout.addWidget(self._left_scroll)

        # Fixed "Work" label column — mirrors _details_cell in the header
        self._work_body_col = _WorkBodyColumn()
        body_layout.addWidget(self._work_body_col)

        # Right canvas
        self._canvas = _UsageCanvas()
        self._right_scroll = QScrollArea()
        self._right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self._right_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._right_scroll.setFrameShape(QFrame.NoFrame)
        self._right_scroll.setWidgetResizable(False)
        self._right_scroll.setWidget(self._canvas)
        body_layout.addWidget(self._right_scroll, 1)

        # Forward wheel events from the frozen left pane to the right canvas so
        # scroll gestures (horizontal or vertical) over the name column move the
        # chart instead of being silently consumed by the left scroll area.
        self._left_wheel_fwd = _WheelForwarder(self._right_scroll, self)
        self._left_scroll.viewport().installEventFilter(self._left_wheel_fwd)

        # External vertical scrollbar
        self._vsb = QScrollBar(Qt.Vertical)
        body_layout.addWidget(self._vsb)
        root.addWidget(body_row, 1)

        # ── Scroll connections ────────────────────────────────────────
        # Horizontal: canvas → header
        self._right_scroll.horizontalScrollBar().valueChanged.connect(
            self._hdr_area.horizontalScrollBar().setValue
        )
        # Vertical range from canvas → vsb
        self._right_scroll.verticalScrollBar().rangeChanged.connect(
            lambda mn, mx: self._vsb.setRange(mn, mx)
        )
        self._right_scroll.verticalScrollBar().valueChanged.connect(
            self._vsb.setValue
        )
        self._vsb.valueChanged.connect(
            self._right_scroll.verticalScrollBar().setValue
        )
        # Sync left pane vertical with canvas vertical
        self._right_scroll.verticalScrollBar().valueChanged.connect(
            self._left_scroll.verticalScrollBar().setValue
        )
        self._vsb.valueChanged.connect(
            self._sync_left_pane_y
        )
        self._vsb.valueChanged.connect(
            self._work_body_col.set_scroll_y
        )

        # Update hdr_spacer width when vsb range/visibility changes
        self._right_scroll.verticalScrollBar().rangeChanged.connect(
            self._sync_hdr_spacer
        )

        # Left pane interaction signals
        self._left_pane.jump_to_allocation_requested.connect(self._on_jump_to_allocation)
        self._left_pane.jump_task_to_allocation_requested.connect(self._on_jump_task_to_allocation)
        self._left_pane.task_info_requested.connect(self._on_task_info)

    def _sync_left_pane_y(self, val: int):
        self._left_scroll.verticalScrollBar().setValue(val)

    def _on_jump_task_to_allocation(self, vis_idx: int):
        """Scroll the right canvas to the first time allocation for the task at vis_idx."""
        if not (0 <= vis_idx < len(self._vis)):
            return
        row = self._vis[vis_idx]
        if not row.daily:
            return
        first_date = min(row.daily.keys())
        x = self._canvas._col_x(first_date)
        margin = max(10, self._canvas._day_width * 3)
        self._right_scroll.horizontalScrollBar().setValue(max(0, x - margin))

    def _on_jump_to_allocation(self, vis_idx: int):
        """Scroll the right canvas to the first time allocation for the resource at vis_idx."""
        if not (0 <= vis_idx < len(self._vis)):
            return
        res_row = self._vis[vis_idx]
        # Gather the earliest date across all task sub-rows that belong to this resource
        first_date = None
        for row in self._vis:
            if row.kind == 'task' and row.res_idx == res_row.res_idx and row.daily:
                d = min(row.daily.keys())
                if first_date is None or d < first_date:
                    first_date = d
        if first_date is None:
            return
        x = self._canvas._col_x(first_date)
        margin = max(10, self._canvas._day_width * 3)
        self._right_scroll.horizontalScrollBar().setValue(max(0, x - margin))

    def set_timeline_view(self, timeline_view):
        """Store a reference to the TimelineView so TaskDialog can show the checkbox."""
        self._timeline_view = timeline_view

    def _on_task_info(self, task):
        """Open TaskDialog for the given task (double-click from left pane)."""
        if self._project is None:
            return
        from dialogs import TaskDialog  # type: ignore
        crit = getattr(self, '_get_critical_ids', lambda: set())()
        fd   = getattr(self, '_get_float_data', lambda: {})()
        task_jira_data = _load_task_jira_data(self, task)
        dlg = TaskDialog(task, self._project, self,
                         timeline_view=getattr(self, '_timeline_view', None),
                         critical_ids=crit,
                         float_data=fd,
                         task_jira_data=task_jira_data)
        if dlg.exec_() == dlg.Accepted:
            dlg.apply_to_task()
            self.task_edited.emit()

    def _sync_hdr_spacer(self, mn, mx):
        visible = mx > mn
        w = self._vsb.sizeHint().width() if visible else 0
        self._hdr_spacer.setFixedWidth(w)

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def load_project(self, project):
        self._project = project
        self._rows.clear()
        self._vis.clear()

        if project is None:
            self._canvas.configure([], [], None, 0,
                                   self._day_width, self._show_sundays, set())
            self._left_pane.set_rows([], [])
            self._work_body_col.set_rows([])
            return

        (self._work_hour_start, self._work_hour_end,
         self._work_day_hours, self._day_non_working) = read_work_hours(project)
        self._clock_day_span = self._work_hour_end - self._work_hour_start
        self._build_rows(project)
        self._compute_date_range(project)
        self._non_working = _get_non_working_dates(
            project, self._project_start, self._total_days
        )
        self._rebuild_visible()
        self._configure_header()

    # _read_work_hours removed — delegated to read_work_hours() from hour_mode

    def _build_rows(self, project):
        """Build the flat row list from project resources and their assignments.

        Strategy: iterate ALL tasks (like TeamPlanner) and collect (task, asgn)
        pairs per resource name.  This avoids relying on resource.getAssignments()
        which can fail silently for some file formats.
        """
        self._rows.clear()

        # ── 1. Build ordered resource list ─────────────────────────────────────
        try:
            resources = [r for r in project.getResources()
                         if r.getName() is not None and str(r.getName()).strip()]
        except Exception:
            resources = []

        res_order: dict = {}   # name → res_idx
        for idx, res in enumerate(resources):
            res_order[str(res.getName())] = idx

        # ── 2. Collect assignments per resource by iterating tasks ─────────────
        from collections import defaultdict
        res_asgns: dict = defaultdict(list)   # name → [(task, asgn), …]

        try:
            all_tasks = list(project.getTasks() or [])
        except Exception:
            all_tasks = []

        for task in all_tasks:
            try:
                if task.getName() is None:
                    continue
                asgn_list = list(task.getResourceAssignments() or [])
            except Exception:
                continue
            for asgn in asgn_list:
                try:
                    res = asgn.getResource()
                    if res is None:
                        continue
                    rname = str(res.getName() or "")
                    if rname and rname in res_order:
                        res_asgns[rname].append((task, asgn))
                except Exception:
                    continue

        # ── 3. Build _Row objects in resource order ────────────────────────────
        for resource in resources:
            rname  = str(resource.getName())
            ridx   = res_order[rname]

            res_row = _Row(kind='resource', name=rname, total_h=0.0,
                           daily={}, res_idx=ridx)
            res_row.vacations = _get_resource_vacation_blocks(resource)
            self._rows.append(res_row)

            for task, asgn in res_asgns.get(rname, []):
                try:
                    task_name = str(task.getName() or "").strip()
                    if not task_name:
                        continue

                    # Work hours — try assignment.getWork() first
                    total_h = 0.0
                    try:
                        total_h = _parse_work_hours(asgn.getWork())
                    except Exception:
                        pass

                    # Fallback: working-days × 8h × allocation-units
                    if total_h <= 0:
                        try:
                            s = _to_qdate(task.getStart())
                            f = _to_qdate(task.getFinish())
                            if s and f:
                                wd = _working_days_in_range(s, f)
                                units_pct = 1.0
                                try:
                                    u = asgn.getUnits()
                                    if u is not None:
                                        units_pct = float(str(u)) / 100.0
                                except Exception:
                                    pass
                                total_h = wd * 8.0 * units_pct
                        except Exception:
                            pass

                    # Dates: prefer assignment-level, fall back to task-level
                    start_qd = (_to_qdate(asgn.getStart())
                                or _to_qdate(task.getStart()))
                    finish_qd = (_to_qdate(asgn.getFinish())
                                 or _to_qdate(task.getFinish()))

                    if start_qd is None or finish_qd is None:
                        continue

                    daily = (_build_daily_hours(start_qd, finish_qd, total_h)
                             if total_h > 0 else {})

                    task_row = _Row(kind='task', name=task_name,
                                   total_h=total_h, daily=daily,
                                   res_idx=ridx)
                    task_row.task = task
                    self._rows.append(task_row)

                    # Accumulate into resource row
                    res_row.total_h += total_h
                    for d, h in daily.items():
                        res_row.daily[d] = res_row.daily.get(d, 0.0) + h

                except Exception:
                    continue

    def _compute_date_range(self, project):
        """Determine project_start and total_days from the loaded rows."""
        all_dates: list[QDate] = []
        for row in self._rows:
            all_dates.extend(row.daily.keys())
            # Include vacation start and end dates so the canvas covers them fully
            for vac in row.vacations:
                all_dates.append(vac['from_qd'])
                all_dates.append(vac['to_qd'])

        # Also include ALL task start dates so project_start matches
        # Gantt / Team Planner (which may have tasks with no assignments).
        try:
            for task in project.getTasks():
                s = _to_qdate(task.getStart())
                if s:
                    all_dates.append(s)
        except Exception:
            pass

        if not all_dates:
            # Fall back to project properties
            try:
                ps = _to_qdate(project.getProjectProperties().getStartDate())
                pf = _to_qdate(project.getProjectProperties().getFinishDate())
                if ps and pf:
                    all_dates = [ps, pf]
            except Exception:
                pass

        if not all_dates:
            self._project_start = QDate.currentDate()
            self._total_days    = 30
            return

        min_d = min(all_dates)
        max_d = max(all_dates)
        # Pad by a few days on each side
        self._project_start = min_d.addDays(-3)
        self._total_days    = self._project_start.daysTo(max_d) + 7

    def _rebuild_visible(self):
        """Rebuild the visible row list (honours collapsed state)."""
        self._vis.clear()
        skip_res_idx: int | None = None

        for row in self._rows:
            if row.kind == 'resource':
                skip_res_idx = row.res_idx if row.collapsed else None
                self._vis.append(row)
            else:
                if skip_res_idx is not None and row.res_idx == skip_res_idx:
                    continue
                self._vis.append(row)

        # Align canvas_start to a clean boundary for weekly/monthly modes.
        if self._project_start and self._day_width < MONTH_MODE_THRESHOLD:
            # Monthly: align to 1st of the month containing project_start
            canvas_start = QDate(self._project_start.year(),
                                 self._project_start.month(), 1)
            last_day     = self._project_start.addDays(self._total_days - 1)
            month_end    = QDate(last_day.year(), last_day.month(),
                                 last_day.daysInMonth())
            canvas_days  = canvas_start.daysTo(month_end) + 1
        elif self._project_start and self._day_width < WEEK_MODE_THRESHOLD:
            # Weekly: align to Monday of the week containing project_start
            ps_dow       = self._project_start.dayOfWeek()   # 1=Mon … 7=Sun
            canvas_start = self._project_start.addDays(-(ps_dow - 1))
            last_day     = self._project_start.addDays(self._total_days - 1)
            last_dow     = last_day.dayOfWeek()
            week_end     = last_day.addDays(7 - last_dow)    # Sunday of last week
            canvas_days  = canvas_start.daysTo(week_end) + 1
        else:
            canvas_start = self._project_start
            canvas_days  = self._total_days

        n = len(self._vis)
        self._left_pane.set_rows(self._rows, self._vis)
        self._left_pane.setMinimumHeight(n * ROW_H)
        self._work_body_col.set_rows(self._vis)

        # Weekly and monthly modes always include Sundays in the day-coordinate
        # system so that _col_x() / _visible_cols() match the GanttHeader (which
        # is also configured with show_sundays=True for those modes).  Daily and
        # hourly modes use the user's actual show_sundays preference.
        if self._project_start and self._day_width < WEEK_MODE_THRESHOLD:
            canvas_show_sundays = True   # weekly or monthly
        else:
            canvas_show_sundays = self._show_sundays   # daily or hourly

        # Compute the clock-hour window to pass to header and canvas.
        # show_off_hours=True: full 24-hour day; all slots outside [start, end) are non-working.
        # show_off_hours=False: only the defined working window, breaks greyed.
        if self._show_off_hours:
            clock_hour_start  = 0
            clock_day_span    = 24
            # All hours outside the working ranges are non-working (off-hours + breaks)
            working_set = frozenset(range(self._work_hour_start, self._work_hour_end)) - self._day_non_working
            off_hours_slots = frozenset(range(24)) - working_set
        else:
            clock_hour_start  = self._work_hour_start
            clock_day_span    = self._clock_day_span  # work_hour_end - work_hour_start
            off_hours_slots   = self._day_non_working  # only lunch/break slots

        self._canvas.configure(
            self._rows, self._vis,
            canvas_start, canvas_days,
            self._day_width, canvas_show_sundays, self._non_working,
            clock_hour_start, self._work_day_hours,
            clock_day_span, off_hours_slots,
        )
        # Force the scroll area to re-evaluate the scrollbar range after the
        # canvas setFixedSize() — required when switching between zoom modes
        # because QScrollArea caches the child size until the widget is "nudged".
        self._right_scroll.setWidget(self._canvas)

    def _configure_header(self):
        """Configure the calendar header to match the current zoom mode.

        Four modes:
          hourly  (day_width ≥ HOUR_MODE_THRESHOLD) → _HourModeHeader
          monthly (day_width < MONTH_MODE_THRESHOLD) → GanttHeader (month bands)
          weekly  (< WEEK_MODE_THRESHOLD)            → GanttHeader (week labels)
          daily   (otherwise)                         → GanttHeader (day numbers)
        """
        if not self._project_start:
            return

        if self._day_width >= HOUR_MODE_THRESHOLD:
            if self._show_off_hours:
                clock_hour_start = 0
                clock_day_span   = 24
                working_set      = frozenset(range(self._work_hour_start, self._work_hour_end)) - self._day_non_working
                off_hours_slots  = frozenset(range(24)) - working_set
            else:
                clock_hour_start = self._work_hour_start
                clock_day_span   = self._clock_day_span
                off_hours_slots  = self._day_non_working
            # Configure BEFORE swapping so the widget has the correct fixed size
            # when it enters the scroll area (prevents scrollbar range mismatch)
            self._hour_hdr.configure(
                self._project_start, self._total_days, self._day_width,
                clock_hour_start, clock_day_span, off_hours_slots,
            )
            if self._hdr_area.widget() is not self._hour_hdr:
                self._hdr_area.takeWidget()
                self._hdr_area.setWidget(self._hour_hdr)
            # Re-sync header scroll to canvas after any widget swap
            self._hdr_area.horizontalScrollBar().setValue(
                self._right_scroll.horizontalScrollBar().value()
            )
            return

        # Ensure the standard GanttHeader is active for all other modes
        if self._day_width < MONTH_MODE_THRESHOLD:
            canvas_start = QDate(self._project_start.year(),
                                 self._project_start.month(), 1)
            last_day     = self._project_start.addDays(self._total_days - 1)
            month_end    = QDate(last_day.year(), last_day.month(),
                                 last_day.daysInMonth())
            canvas_days  = canvas_start.daysTo(month_end) + 1
            self._gantt_hdr.configure(
                canvas_start, canvas_days, self._day_width,
                show_sundays=True, non_working_dates=self._non_working,
            )
        elif self._day_width < WEEK_MODE_THRESHOLD:
            ps_dow      = self._project_start.dayOfWeek()
            week_mon    = self._project_start.addDays(-(ps_dow - 1))
            last_day    = self._project_start.addDays(self._total_days - 1)
            last_dow    = last_day.dayOfWeek()
            week_end    = last_day.addDays(7 - last_dow)
            total_weeks = week_mon.daysTo(week_end) // 7 + 1
            self._gantt_hdr.configure(
                week_mon, total_weeks * 7, self._day_width,
                show_sundays=True, non_working_dates=self._non_working,
            )
        else:
            self._gantt_hdr.configure(
                self._project_start, self._total_days, self._day_width,
                show_sundays=self._show_sundays,
                non_working_dates=self._non_working,
            )
        # Configure BEFORE swapping
        if self._hdr_area.widget() is not self._gantt_hdr:
            self._hdr_area.takeWidget()
            self._hdr_area.setWidget(self._gantt_hdr)
        # Re-sync header scroll to canvas after any widget swap
        self._hdr_area.horizontalScrollBar().setValue(
            self._right_scroll.horizontalScrollBar().value()
        )

    # ------------------------------------------------------------------
    # Public setters (called from MainWindow)
    # ------------------------------------------------------------------

    def set_day_width(self, px: int):
        self._day_width = max(DAY_WIDTH_MIN, min(DAY_WIDTH_MAX, px))
        if self._project_start:
            self._rebuild_visible()
            self._configure_header()

    def set_show_off_hours(self, val: bool):
        self._show_off_hours = val
        if self._project_start:
            self._rebuild_visible()
            self._configure_header()

    def set_show_sundays(self, val: bool):
        self._show_sundays = val
        if self._project_start:
            self._rebuild_visible()
            self._configure_header()

    # ------------------------------------------------------------------
    # Navigation
    # ------------------------------------------------------------------

    def _scroll_to_today(self):
        if not self._project_start:
            return
        today = QDate.currentDate()
        if today < self._project_start:
            self._right_scroll.horizontalScrollBar().setValue(0)
            return
        # Count visible columns from project_start to today
        col = 0
        d = self._project_start
        while d < today and d < self._project_start.addDays(self._total_days):
            if self._show_sundays or d.dayOfWeek() != 7:
                col += 1
            d = d.addDays(1)
        x = col * self._day_width
        # Scroll so today is roughly centred
        vp_w = self._right_scroll.viewport().width()
        target = max(0, x - vp_w // 2)
        self._right_scroll.horizontalScrollBar().setValue(target)
