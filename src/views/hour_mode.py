# hour_mode.py — Shared hourly-zoom infrastructure for Gantt, Team Planner
#                and Resource Usage Graph views.
#
# Exports
# -------
# Constants
#   HOUR_MODE_THRESHOLD   – day_width (px) at or above which hourly mode activates
#   WORK_HOUR_START       – fallback first work hour (08:00)
#   WORK_HOUR_END         – fallback last work hour exclusive (17:00)
#   WORK_DAY_HOURS        – WORK_HOUR_END - WORK_HOUR_START
#
# Functions
#   read_work_hours(project) → (start, end, work_hours, non_working_slots)
#   working_day_count(project_start, total_days) → int
#   date_to_working_day_idx(date, project_start) → int
#   datetime_to_hourly_x(java_datetime, project_start, day_width,
#                         work_hour_start, clock_day_span, show_off_hours) → float
#
# Widgets
#   HourModeHeader(QWidget) – two-row header: date band / hour slots

from PyQt5.QtWidgets import QWidget  # type: ignore
from PyQt5.QtGui import QPainter, QColor, QFont, QPen  # type: ignore
from PyQt5.QtCore import Qt, QDate, QRect  # type: ignore

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HOUR_MODE_THRESHOLD = 60   # day_width (px) at or above this → hourly columns
WORK_HOUR_START     = 8    # first work hour  (08:00)
WORK_HOUR_END       = 17   # exclusive end    (last slot = 16:00–17:00)
WORK_DAY_HOURS      = WORK_HOUR_END - WORK_HOUR_START   # 9 working hours / day

# ---------------------------------------------------------------------------
# Calendar reader
# ---------------------------------------------------------------------------

def read_work_hours(project) -> tuple:
    """Read the working-hour window from the project's default calendar.

    Returns
    -------
    (work_hour_start, work_hour_end, work_day_hours, non_working_slots)
      work_hour_start   – first clock hour to display        (e.g. 9)
      work_hour_end     – exclusive last clock hour          (e.g. 17)
      work_day_hours    – actual working hours per day       (sum of all ranges)
      non_working_slots – frozenset of clock hours in [start, end) that are
                          not worked (e.g. {12} for a 12:00–13:00 lunch break)

    All ranges for the first working weekday are collected so that a split
    schedule (e.g. 09:00–12:00 + 13:00–17:00) is handled correctly.
    Falls back to module-level defaults on any error.
    """
    try:
        import java.time  # type: ignore
        cal = project.getDefaultCalendar()
        if cal is None:
            return WORK_HOUR_START, WORK_HOUR_END, WORK_DAY_HOURS, frozenset()
        for dow in (
            java.time.DayOfWeek.MONDAY,
            java.time.DayOfWeek.TUESDAY,
            java.time.DayOfWeek.WEDNESDAY,
            java.time.DayOfWeek.THURSDAY,
            java.time.DayOfWeek.FRIDAY,
        ):
            hours = cal.getCalendarHours(dow)
            if not hours:
                continue
            ranges = []
            for rng in hours:
                s, e = rng.getStart(), rng.getEnd()
                if s is not None and e is not None:
                    sh, eh = int(s.getHour()), int(e.getHour())
                    if eh > sh:
                        ranges.append((sh, eh))
            if not ranges:
                continue
            min_start   = min(r[0] for r in ranges)
            max_end     = max(r[1] for r in ranges)
            working_set = set()
            for sh, eh in ranges:
                working_set.update(range(sh, eh))
            non_working = frozenset(range(min_start, max_end)) - working_set
            return min_start, max_end, len(working_set), non_working
    except Exception:
        pass
    return WORK_HOUR_START, WORK_HOUR_END, WORK_DAY_HOURS, frozenset()


# ---------------------------------------------------------------------------
# Working-day helpers
# ---------------------------------------------------------------------------

def working_day_count(project_start: QDate, total_days: int) -> int:
    """Return the number of Mon–Fri days in [project_start, project_start + total_days)."""
    return sum(
        1 for di in range(total_days)
        if project_start.addDays(di).dayOfWeek() not in (6, 7)
    )


def date_to_working_day_idx(date: QDate, project_start: QDate) -> int:
    """Return how many Mon–Fri days lie between project_start (inclusive)
    and *date* (exclusive).  Weekend days are not counted."""
    if date is None or project_start is None:
        return 0
    idx = 0
    d   = project_start
    while d < date:
        if d.dayOfWeek() not in (6, 7):
            idx += 1
        d = d.addDays(1)
    return idx


def datetime_to_hourly_x(java_datetime,
                          project_start: QDate,
                          day_width: int,
                          work_hour_start: int,
                          clock_day_span: int,
                          show_off_hours: bool) -> float:
    """Convert an MPXJ LocalDateTime to a pixel x-coordinate in hourly mode.

    Parameters
    ----------
    java_datetime   : MPXJ java.time.LocalDateTime (or None)
    project_start   : QDate — left edge of the canvas
    day_width       : pixels per *hour* slot in hourly mode
    work_hour_start : first visible clock hour (when show_off_hours=False)
    clock_day_span  : number of hour columns per working day
    show_off_hours  : when True, full 24-hour clock is shown

    Returns 0.0 on failure.
    """
    if java_datetime is None or project_start is None:
        return 0.0
    try:
        yr = int(java_datetime.getYear())
        mo = int(java_datetime.getMonthValue())
        dy = int(java_datetime.getDayOfMonth())
        hr = int(java_datetime.getHour())
        mi = int(java_datetime.getMinute())
    except Exception:
        return 0.0

    date = QDate(yr, mo, dy)
    wday = date_to_working_day_idx(date, project_start)

    if show_off_hours:
        eff_start = 0
        eff_span  = 24
        # No clamping — show full clock
    else:
        eff_start = work_hour_start
        eff_span  = clock_day_span
        # Clamp to the visible working window
        if hr < work_hour_start:
            hr, mi = work_hour_start, 0
        elif hr >= work_hour_start + clock_day_span:
            hr, mi = work_hour_start + clock_day_span - 1, 59

    slot_frac = (hr - eff_start) + mi / 60.0
    return wday * eff_span * day_width + slot_frac * day_width


# ---------------------------------------------------------------------------
# Shared header widget
# ---------------------------------------------------------------------------

class HourModeHeader(QWidget):
    """Two-row header for hourly zoom mode.

    Top row    : date label per working day  (e.g. "Mon 24 Apr")
    Bottom row : hour labels per slot        (8, 9, 10 … 16)

    x=0 is the left edge of the *first hour column* of the first working day
    (plus ``label_width`` if the caller needs a frozen-label-area offset).
    """

    def __init__(self, header_height: int = 42,
                 header_month_h: int = 22,
                 header_week_h: int  = 20,
                 parent=None):
        super().__init__(parent)
        self._header_height  = header_height
        self._header_month_h = header_month_h
        self._header_week_h  = header_week_h

        self._project_start:    QDate | None = None
        self._total_days        = 0
        self._day_width         = HOUR_MODE_THRESHOLD
        self._work_hour_start   = WORK_HOUR_START
        self._clock_day_span    = WORK_DAY_HOURS
        self._non_working_slots: frozenset = frozenset()
        self._label_width       = 0

        self.setFixedHeight(header_height)

    def configure(self, project_start: QDate, total_days: int, day_width: int,
                  work_hour_start: int       = WORK_HOUR_START,
                  clock_day_span: int        = WORK_DAY_HOURS,
                  non_working_slots: frozenset = frozenset(),
                  label_width: int = 0):
        self._project_start    = project_start
        self._total_days       = total_days
        self._day_width        = day_width
        self._work_hour_start  = work_hour_start
        self._clock_day_span   = clock_day_span
        self._non_working_slots = non_working_slots
        self._label_width      = label_width
        wdays  = working_day_count(project_start, total_days)
        total_w = label_width + max(1, wdays * clock_day_span * day_width)
        self.setFixedSize(total_w, self._header_height)
        self.update()

    def paintEvent(self, event):
        if not self._project_start:
            return
        painter    = QPainter(self)
        font_bold  = QFont("Segoe UI", 9, QFont.Bold)
        font_small = QFont("Segoe UI", 7)

        lw  = self._label_width
        mh  = self._header_month_h
        wh  = self._header_week_h
        hh  = self._header_height

        # Label-area placeholder (if any)
        if lw > 0:
            painter.fillRect(0, 0, lw, hh, QColor(236, 243, 251))
            painter.setPen(QPen(QColor(150, 180, 220), 1))
            painter.drawLine(lw, 0, lw, hh)

        day_idx = 0   # counts working days only
        for di in range(self._total_days):
            d   = self._project_start.addDays(di)
            dow = d.dayOfWeek()
            if dow in (6, 7):
                continue

            day_x = lw + day_idx * self._clock_day_span * self._day_width
            day_w = self._clock_day_span * self._day_width

            # Top row — date label
            bg = (QColor(210, 228, 252) if day_idx % 2 == 0
                  else QColor(195, 215, 245))
            painter.fillRect(day_x, 0, day_w, mh, bg)
            painter.setFont(font_bold)
            painter.setPen(QColor(26, 63, 122))
            if day_w > 120:
                label = d.toString("ddd d MMM yyyy")
            elif day_w > 80:
                label = d.toString("ddd d MMM")
            else:
                label = d.toString("d MMM")
            painter.drawText(
                QRect(day_x + 3, 0, day_w - 6, mh),
                Qt.AlignVCenter | Qt.AlignLeft, label,
            )
            painter.setPen(QPen(QColor(140, 175, 215), 1))
            painter.drawLine(day_x, 0, day_x, hh)

            # Bottom row — hour labels; non-working slots are greyed
            painter.setFont(font_small)
            for hi in range(self._clock_day_span):
                hx       = day_x + hi * self._day_width
                hour     = self._work_hour_start + hi
                is_break = hour in self._non_working_slots
                cell_bg  = QColor(210, 215, 225) if is_break else QColor(242, 247, 255)
                painter.fillRect(hx, mh, self._day_width, wh, cell_bg)
                if self._day_width >= 20:
                    text_col = (QColor(150, 155, 165) if is_break
                                else QColor(80, 100, 140))
                    painter.setPen(text_col)
                    painter.drawText(
                        QRect(hx, mh, self._day_width, wh),
                        Qt.AlignCenter, str(hour),
                    )
                painter.setPen(QPen(QColor(215, 225, 240), 1))
                painter.drawLine(hx, mh, hx, hh)

            day_idx += 1

        # Heavy bottom border
        painter.setPen(QPen(QColor(43, 87, 154), 2))
        painter.drawLine(0, hh - 1, self.width(), hh - 1)
        painter.end()
