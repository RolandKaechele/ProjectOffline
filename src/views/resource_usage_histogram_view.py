# resource_usage_histogram_view.py - Resource Usage Histogram strip
#
# Renders a bar chart below the Team Planner showing total allocated hours per
# day across all resources.  Bars use a three-tier colour scheme:
#   green  ≤ 80 % utilisation
#   amber  80–100 %
#   red    > 100 %
# A dashed line marks the 100 % capacity level.
#
# The widget is composed of two parts aligned to the Team Planner layout:
#   _HistogramLabel (left, fixed 160 px) — static "Resource Usage" label
#   _HistogramCanvas (right, expands)    — the actual bar chart; scrolled in
#                                          sync with the Team Planner via
#                                          set_scroll_x(int)

from PyQt5.QtWidgets import (  # type: ignore
    QWidget, QHBoxLayout, QSizePolicy, QToolTip,
)
from PyQt5.QtCore import Qt, QDate, QRect, QPoint  # type: ignore
from PyQt5.QtGui import (  # type: ignore
    QPainter, QColor, QPen, QFont, QFontMetrics, QBrush,
)

from gantt_view import _to_qdate  # type: ignore

# ---------------------------------------------------------------------------
# Layout constants (must stay in sync with team_planner_view.py)
# ---------------------------------------------------------------------------

RESOURCE_COL_W   = 160   # width of frozen left label column
HISTOGRAM_H      = 120   # default strip height

# ---------------------------------------------------------------------------
# Colour palette
# ---------------------------------------------------------------------------

_C_BAR_GREEN   = QColor(0x34, 0x8A, 0x34)   # ≤ 80 %
_C_BAR_AMBER   = QColor(0xFF, 0x9A, 0x00)   # 80–100 %
_C_BAR_RED     = QColor(0xCC, 0x22, 0x22)   # > 100 %
_C_CAPACITY    = QColor(0x00, 0x4D, 0xCC)   # dashed 100 % line
_C_AXIS_BG     = QColor(0xF2, 0xF5, 0xFA)   # canvas background
_C_GRID        = QColor(0xCC, 0xCC, 0xCC)   # light grid lines
_C_AXIS_TEXT   = QColor(0x44, 0x44, 0x55)   # axis labels
_C_LABEL_BG    = QColor(0xE0, 0xEC, 0xFA)   # left label background
_C_LABEL_TEXT  = QColor(0x1A, 0x3F, 0x7A)
_C_BORDER      = QColor(0xB0, 0xC8, 0xE0)

_DATE_AXIS_H   = 18   # height of the date label row at the bottom


# ---------------------------------------------------------------------------
# Public API: compute_histogram_data()
# ---------------------------------------------------------------------------

def compute_histogram_data(
    project,
    start_date: QDate,
    end_date: QDate,
    non_working_dates: set | None = None,
) -> list:
    """Compute histogram data for *project* over [start_date, end_date).

    Returns a list of dicts, one per calendar day in the range::

        {
            'date':            QDate,
            'total_hours':     float,   # allocated hours (all resources)
            'capacity_hours':  float,   # available hours (all resources)
            'utilisation_pct': float,   # 0 when capacity_hours == 0
        }

    Parameters
    ----------
    project:
        MPXJ ProjectFile.  Pass ``None`` to get an empty list.
    start_date, end_date:
        Inclusive start / exclusive end of the date range (same convention as
        QDate.daysTo).
    non_working_dates:
        Set of "yyyy-MM-dd" strings from the project's default calendar
        (public holidays, etc.).  Obtained from
        ``TeamPlannerCanvas._non_working``.  May be ``None`` (treated as
        empty).
    """
    if project is None or start_date is None or end_date is None:
        return []

    n_days = start_date.daysTo(end_date)
    if n_days <= 0:
        return []

    if non_working_dates is None:
        non_working_dates = set()

    # Working hours per day from the project default calendar
    try:
        from hour_mode import read_work_hours  # type: ignore
        _, _, work_day_hours, _ = read_work_hours(project)
    except Exception:
        work_day_hours = 8

    # Resource list (skip the null/unassigned resource at UID 0)
    try:
        res_list = [r for r in project.getResources() if r.getName() is not None]
    except Exception:
        return []

    def _safe_uid(r):
        try:
            return int(str(r.getUniqueID()))
        except Exception:
            return None

    res_by_uid: dict = {}
    for res in res_list:
        uid = _safe_uid(res)
        if uid is not None:
            res_by_uid[uid] = res

    # Vacation (non-working exception) dates per resource: uid -> set of "yyyy-MM-dd"
    vacation_dates_by_res: dict = {}
    for res in res_list:
        uid = _safe_uid(res)
        if uid is None:
            continue
        vac_dates: set = set()
        try:
            cal = res.getCalendar()
            if cal is not None:
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
                    d = from_qd
                    while d <= to_qd:
                        vac_dates.add(d.toString("yyyy-MM-dd"))
                        d = d.addDays(1)
        except Exception:
            pass
        vacation_dates_by_res[uid] = vac_dates

    # Capacity per day (index = offset from start_date)
    allocated = [0.0] * n_days
    capacity  = [0.0] * n_days

    for i in range(n_days):
        day = start_date.addDays(i)
        day_str = day.toString("yyyy-MM-dd")
        dow = day.dayOfWeek()            # 1=Mon … 7=Sun
        if dow in (6, 7):               # weekend
            continue
        if day_str in non_working_dates:  # project-level non-working day
            continue
        for uid in res_by_uid:
            if day_str in vacation_dates_by_res.get(uid, set()):
                continue
            capacity[i] += work_day_hours

    # Allocation: distribute each assignment's work evenly across its working days
    try:
        all_tasks = list(project.getTasks())
    except Exception:
        all_tasks = []

    for task in all_tasks:
        if task.getName() is None:
            continue
        try:
            if str(task.getID()) == "0":
                continue
        except Exception:
            pass
        try:
            if bool(task.getSummary()):
                continue
        except Exception:
            pass

        task_start  = _to_qdate(task.getStart())
        task_finish = _to_qdate(task.getFinish())
        if not task_start or not task_finish:
            continue
        if task_start > task_finish:
            continue

        try:
            assignments = list(task.getResourceAssignments() or [])
        except Exception:
            continue

        for asgn in assignments:
            try:
                res = asgn.getResource()
                if res is None:
                    continue
                uid = _safe_uid(res)
                if uid not in res_by_uid:
                    continue
            except Exception:
                continue

            # Resolve assignment work in hours
            asgn_hours = 0.0
            try:
                work = asgn.getWork()
                if work is not None:
                    dur_val  = float(str(work.getDuration()))
                    unit_str = str(work.getUnits()).upper() if work.getUnits() is not None else "HOURS"
                    if "HOUR" in unit_str:
                        asgn_hours = dur_val
                    elif "DAY" in unit_str:
                        asgn_hours = dur_val * work_day_hours
                    elif "WEEK" in unit_str:
                        asgn_hours = dur_val * work_day_hours * 5.0
                    elif "MONTH" in unit_str:
                        asgn_hours = dur_val * work_day_hours * 20.0
                    elif "MINUTE" in unit_str:
                        asgn_hours = dur_val / 60.0
                    else:
                        asgn_hours = dur_val
            except Exception:
                pass

            if asgn_hours <= 0.0:
                # Fall back: duration × work_day_hours
                try:
                    dur = task.getDuration()
                    if dur is not None:
                        dur_val  = float(str(dur.getDuration()))
                        unit_str = str(dur.getUnits()).upper() if dur.getUnits() is not None else "DAYS"
                        if "HOUR" in unit_str:
                            asgn_hours = dur_val
                        elif "DAY" in unit_str:
                            asgn_hours = dur_val * work_day_hours
                        elif "WEEK" in unit_str:
                            asgn_hours = dur_val * work_day_hours * 5.0
                        elif "MONTH" in unit_str:
                            asgn_hours = dur_val * work_day_hours * 20.0
                        else:
                            asgn_hours = dur_val * work_day_hours
                except Exception:
                    asgn_hours = float(work_day_hours)

            if asgn_hours <= 0.0:
                continue

            # Count working days in the task span for this resource
            vac_dates = vacation_dates_by_res.get(uid, set())
            working_days_in_span = 0
            d = task_start
            while d <= task_finish:
                d_str = d.toString("yyyy-MM-dd")
                if d.dayOfWeek() not in (6, 7) and d_str not in non_working_dates and d_str not in vac_dates:
                    working_days_in_span += 1
                d = d.addDays(1)

            if working_days_in_span <= 0:
                continue

            daily_hours = asgn_hours / working_days_in_span

            # Distribute to each working day within the histogram range
            d = task_start
            while d <= task_finish:
                d_str  = d.toString("yyyy-MM-dd")
                offset = start_date.daysTo(d)
                if 0 <= offset < n_days:
                    if d.dayOfWeek() not in (6, 7) and d_str not in non_working_dates and d_str not in vac_dates:
                        allocated[offset] += daily_hours
                d = d.addDays(1)

    # Assemble result list
    result = []
    for i in range(n_days):
        day = start_date.addDays(i)
        cap   = capacity[i]
        alloc = allocated[i]
        util_pct = (alloc / cap * 100.0) if cap > 0.0 else 0.0
        result.append({
            'date':            day,
            'total_hours':     alloc,
            'capacity_hours':  cap,
            'utilisation_pct': util_pct,
        })
    return result


# ---------------------------------------------------------------------------
# Internal canvas widget
# ---------------------------------------------------------------------------

class _HistogramCanvas(QWidget):
    """Draws the bar chart.  Scroll offset is driven externally via set_scroll_x."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data:          list  = []    # list of dicts from compute_histogram_data
        self._project_start: QDate | None = None
        self._total_days:    int   = 0
        self._day_width:     int   = 20
        self._scroll_x:      int   = 0

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(HISTOGRAM_H)
        self.setMouseTracking(True)

    def load(self, data: list, project_start: QDate, total_days: int, day_width: int):
        self._data          = data
        self._project_start = project_start
        self._total_days    = total_days
        self._day_width     = day_width
        self.update()

    def set_day_width(self, dw: int):
        self._day_width = dw
        self.update()

    def set_scroll_x(self, x: int):
        self._scroll_x = x
        self.update()

    # ------------------------------------------------------------------ #
    # Mouse: tooltip on hover                                             #
    # ------------------------------------------------------------------ #

    def mouseMoveEvent(self, event):
        entry = self._entry_at(event.x())
        if entry:
            alloc = entry['total_hours']
            cap   = entry['capacity_hours']
            util  = entry['utilisation_pct']
            date_str = entry['date'].toString("ddd d MMM yyyy")
            tip = (
                f"<b>{date_str}</b><br>"
                f"Allocated: {alloc:.1f} h<br>"
                f"Capacity: {cap:.1f} h<br>"
                f"Utilisation: {util:.0f} %"
            )
            QToolTip.showText(event.globalPos(), tip, self)
        else:
            QToolTip.hideText()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        QToolTip.hideText()
        super().leaveEvent(event)

    def _entry_at(self, viewport_x: int):
        """Return the data entry for the column under viewport_x, or None."""
        if not self._data or self._day_width <= 0 or self._project_start is None:
            return None
        content_x = viewport_x + self._scroll_x
        day_offset = content_x // self._day_width
        if 0 <= day_offset < len(self._data):
            return self._data[day_offset]
        return None

    # ------------------------------------------------------------------ #
    # Painting                                                            #
    # ------------------------------------------------------------------ #

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setClipRect(event.rect())
        w = self.width()
        h = self.height()

        # Background
        painter.fillRect(0, 0, w, h, _C_AXIS_BG)

        if not self._data or self._day_width <= 0 or self._project_start is None:
            painter.end()
            return

        bar_area_h = h - _DATE_AXIS_H   # usable height for bars + capacity line

        # Find the maximum capacity in the visible range for y-scaling
        max_cap = max((d['capacity_hours'] for d in self._data if d['capacity_hours'] > 0), default=8.0)
        # Scale to 120 % of max capacity so over-capacity bars have headroom
        y_max = max_cap * 1.2

        dw = self._day_width

        # Determine visible column range from scroll offset
        first_col = max(0, self._scroll_x // dw)
        last_col  = min(len(self._data), (self._scroll_x + w) // dw + 2)

        # Draw light grid (every Monday)
        painter.setPen(QPen(_C_GRID, 1, Qt.DotLine))
        for col in range(first_col, last_col):
            entry = self._data[col]
            if entry['date'].dayOfWeek() == 1:  # Monday
                x = col * dw - self._scroll_x
                painter.drawLine(x, 0, x, bar_area_h)

        # Draw bars
        for col in range(first_col, last_col):
            entry  = self._data[col]
            alloc  = entry['total_hours']
            cap    = entry['capacity_hours']
            util   = entry['utilisation_pct']

            if alloc <= 0.0 or cap <= 0.0:
                continue

            x = col * dw - self._scroll_x
            bar_h = int(min(alloc / y_max, 1.0) * bar_area_h)
            bar_y = bar_area_h - bar_h

            # Colour by utilisation tier
            if util > 100.0:
                colour = _C_BAR_RED
            elif util > 80.0:
                colour = _C_BAR_AMBER
            else:
                colour = _C_BAR_GREEN

            bar_w = max(1, dw - 1)
            painter.fillRect(x, bar_y, bar_w, bar_h, colour)

        # Dashed capacity line at 100 %
        if max_cap > 0.0:
            cap_y = int(bar_area_h - (max_cap / y_max) * bar_area_h)
            pen = QPen(_C_CAPACITY, 1, Qt.DashLine)
            painter.setPen(pen)
            painter.drawLine(0, cap_y, w, cap_y)

        # Date axis labels (bottom strip)
        label_y = bar_area_h
        painter.fillRect(0, label_y, w, _DATE_AXIS_H, _C_LABEL_BG)
        painter.setPen(QPen(_C_BORDER, 1))
        painter.drawLine(0, label_y, w, label_y)

        font = QFont("Segoe UI", 7)
        painter.setFont(font)
        painter.setPen(_C_AXIS_TEXT)
        fm = QFontMetrics(font)

        for col in range(first_col, last_col):
            entry = self._data[col]
            date  = entry['date']
            dow   = date.dayOfWeek()
            # Show label on Monday (or 1st of month, etc.) when day_width allows
            if dow == 1:
                label = date.toString("d MMM") if dw >= 14 else date.toString("d/M")
                x = col * dw - self._scroll_x
                painter.drawText(QRect(x + 2, label_y, dw * 7, _DATE_AXIS_H),
                                 Qt.AlignLeft | Qt.AlignVCenter, label)
            elif dw >= 30:
                # Draw individual day numbers when very zoomed in
                label = str(date.day())
                x = col * dw - self._scroll_x
                painter.drawText(QRect(x, label_y, dw, _DATE_AXIS_H),
                                 Qt.AlignCenter | Qt.AlignVCenter, label)

        # Top border
        painter.setPen(QPen(_C_BORDER, 1))
        painter.drawLine(0, 0, w, 0)

        painter.end()


# ---------------------------------------------------------------------------
# Public widget: ResourceUsageHistogramView
# ---------------------------------------------------------------------------

class ResourceUsageHistogramView(QWidget):
    """Horizontal histogram strip intended to sit below the Team Planner.

    Layout::

        | "Resource Usage"  | [_HistogramCanvas — scrolled in sync]  |
        |   (160 px label)  |                                         |

    API
    ---
    load_project(project, non_working_dates)
        Compute histogram data from the MPXJ project.  ``non_working_dates``
        should come from ``TeamPlannerCanvas._non_working``.
    set_day_width(dw)
        Mirror the Team Planner zoom level.
    set_scroll_x(x)
        Drive horizontal scroll from the Team Planner scrollbar value signal.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project       = None
        self._day_width     = 20
        self._non_working   : set = set()

        self.setFixedHeight(HISTOGRAM_H)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Left label (mirrors _ResourcePane / col-header layout)
        self._label = QWidget()
        self._label.setFixedWidth(RESOURCE_COL_W)
        self._label.setFixedHeight(HISTOGRAM_H)
        self._label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self._label.setStyleSheet(
            "background:#d2e4fc; border-right:1px solid #90b4d4;"
            "border-top:2px solid #2b579a;"
        )
        root.addWidget(self._label)

        # Right canvas
        self._canvas = _HistogramCanvas()
        root.addWidget(self._canvas, 1)

    def paintEvent(self, event):
        """Draw the label text (drawn on the parent to simplify the child widget)."""
        painter = QPainter(self)
        font = QFont("Segoe UI", 9, QFont.Bold)
        painter.setFont(font)
        painter.setPen(_C_LABEL_TEXT)
        painter.drawText(
            QRect(4, 0, RESOURCE_COL_W - 8, HISTOGRAM_H),
            Qt.AlignVCenter | Qt.AlignLeft,
            "Resource\nUsage",
        )
        painter.end()

    # ------------------------------------------------------------------ #
    # Data                                                                #
    # ------------------------------------------------------------------ #

    def load_project(self, project, non_working_dates: set | None = None):
        self._project     = project
        self._non_working = non_working_dates or set()
        self._recompute()

    def _recompute(self):
        if self._project is None:
            self._canvas.load([], None, 0, self._day_width)
            return
        canvas_tp = self._find_team_planner_canvas()
        if canvas_tp is not None:
            start_date = canvas_tp.project_start
            total_days = canvas_tp.total_days
        else:
            # Determine from project tasks directly
            from gantt_view import _to_qdate  # type: ignore
            starts = []
            ends   = []
            try:
                for t in self._project.getTasks():
                    s = _to_qdate(t.getStart())
                    f = _to_qdate(t.getFinish())
                    if s:
                        starts.append(s)
                    if f:
                        ends.append(f)
            except Exception:
                pass
            start_date = min(starts) if starts else QDate.currentDate()
            max_f      = max(ends) if ends else start_date
            total_days = max(start_date.daysTo(max_f) + 14, 30)

        end_date = start_date.addDays(total_days)
        data = compute_histogram_data(
            self._project, start_date, end_date, self._non_working
        )
        self._canvas.load(data, start_date, total_days, self._day_width)

    def _find_team_planner_canvas(self):
        """Walk up the widget tree to find the TeamPlannerCanvas sibling."""
        try:
            parent = self.parent()
            # We are placed in a container QWidget that also contains the
            # TeamPlannerView; access its canvas directly.
            if parent is not None:
                for child in parent.children():
                    from team_planner_view import TeamPlannerView  # type: ignore
                    if isinstance(child, TeamPlannerView):
                        return child.canvas
        except Exception:
            pass
        return None

    # ------------------------------------------------------------------ #
    # Zoom / scroll sync                                                  #
    # ------------------------------------------------------------------ #

    def set_day_width(self, dw: int):
        self._day_width = dw
        self._canvas.set_day_width(dw)

    def set_scroll_x(self, x: int):
        self._canvas.set_scroll_x(x)
