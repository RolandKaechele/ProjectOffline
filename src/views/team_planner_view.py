# team_planner_view.py - Team Planner view for Project Offline
#
# Displays all resources (team members) as horizontal rows on a shared timeline.
# Task bars show when each resource is busy.  Drag interactions:
#   • Drag a bar left / right  → reschedule the task (shift start + finish)
#   • Drag a bar to another row → reassign task to that resource
#   • Drag an unassigned chip from the bottom panel → assign + schedule
# On drop, if the target row already has tasks at that time the user is asked
# whether to place the new task serial (after the last existing task) or
# parallel (keep the dropped date).
# The view emits  data_changed  so the main window can push undo snapshots.

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from PyQt5.QtWidgets import (  # type: ignore
    QWidget, QScrollArea, QSizePolicy, QHBoxLayout, QVBoxLayout,
    QFrame, QLabel, QSplitter, QMenu, QDialog, QDialogButtonBox,
    QAbstractScrollArea, QScrollBar, QPushButton, QShortcut, QStyle, QApplication
)
from PyQt5.QtGui import (  # type: ignore
    QPainter, QColor, QFont, QPen, QBrush, QFontMetrics, QCursor, QPolygon
)
from PyQt5.QtWidgets import QToolTip  # type: ignore  (separate import for clarity)
from PyQt5.QtCore import Qt, QRect, QDate, QSize, QPoint, QTime, pyqtSignal, QEvent, QObject  # type: ignore

from gantt_view import (  # type: ignore
    GanttHeader, _to_qdate, _add_working_days, _date_to_col, _col_to_date, _get_non_working_dates,
    _compute_critical_ids, _read_critical_ids, _normalize_schedule,
    DAY_WIDTH_DEF, DAY_WIDTH_MIN, DAY_WIDTH_MAX,
    HEADER_HEIGHT, HEADER_MONTH_H, HEADER_WEEK_H, NAV_BAR_HEIGHT, ROW_HEIGHT as GANTT_ROW_H,
    SPLIT_GAP_DAYS,
)
from hour_mode import (  # type: ignore
    HOUR_MODE_THRESHOLD, HourModeHeader,
    read_work_hours, working_day_count, date_to_working_day_idx, datetime_to_hourly_x,
    WORK_HOUR_START, WORK_HOUR_END, WORK_DAY_HOURS,
)

# ---------------------------------------------------------------------------
# Wheel-event forwarder — redirects scroll gestures from the frozen left pane
# to the main canvas scroll area so the Resource Name column cannot scroll
# independently of the timeline.
# ---------------------------------------------------------------------------

class _WheelForwarder(QObject):
    """Event filter installed on a frozen-pane viewport. Forwards every wheel
    event to the target widget so scroll gestures always move the timeline.
    """
    def __init__(self, target_widget, parent=None):
        super().__init__(parent)
        self._target = target_widget

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Wheel:
            QApplication.sendEvent(self._target, event)
            return True
        return False


# ---------------------------------------------------------------------------
# Layout & colour constants
# ---------------------------------------------------------------------------

RESOURCE_COL_W    = 160   # width of left frozen resource-name column
ROW_H             = 44    # height of each resource row
TASK_BAR_H        = 22    # height of a scheduled task bar
TASK_BAR_MARGIN_V = (ROW_H - TASK_BAR_H) // 2
LANE_H            = TASK_BAR_H + 8  # height of one parallel task lane
LANE_PAD_V        = 5               # top/bottom padding within a resource row
UNASSIGNED_AREA_H = 150   # fixed height of the unassigned tasks panel
CHIP_H            = 40    # height of an unassigned-task chip (2 lines: name + duration)
CHIP_W            = 140   # width  of an unassigned-task chip (fixed)
CHIP_PAD_H        = 6     # horizontal gap between chips
CHIP_PAD_V        = 5     # vertical gap between chips
CHIP_COLS_MIN     = 2     # minimum chip columns (used as fallback before first resize)
UA_SECTION_H      = 120   # fixed height of the unassigned section in TeamPlannerView

_C_ROW_EVEN       = QColor(255, 255, 255)
_C_ROW_ODD        = QColor(248, 250, 255)
_C_ROW_DRAG_TARGET = QColor(220, 235, 255)
_C_TASK_NORMAL    = QColor(70, 130, 200)
_C_TASK_DRAG      = QColor(130, 175, 250)
_C_TASK_GHOST     = QColor(180, 210, 255, 100)
_C_TASK_TEXT      = QColor(255, 255, 255)
_C_TASK_CRITICAL  = QColor(200, 50, 50)    # critical task bar (red)
_C_TASK_CRIT_DRAG = QColor(240, 110, 110)  # critical task bar while dragging
_C_CHIP_NORMAL    = QColor(100, 160, 110)
_C_CHIP_DRAG      = QColor(140, 195, 150)
_C_CHIP_TEXT      = QColor(255, 255, 255)
_C_GRID           = QColor(220, 228, 242)
_C_SAT_EVEN       = QColor(222, 222, 222)   # Saturday/holiday, even row
_C_SAT_ODD        = QColor(232, 232, 232)   # Saturday/holiday, odd row
_C_SUN            = QColor(205, 215, 235, 140)  # Sunday: semi-transparent blue-tint
_C_TODAY          = QColor(0, 168, 0)
_C_SEPARATOR      = QColor(43, 87, 154)
_C_UNASSIGNED_HDR = QColor(220, 235, 220)
_C_UNASSIGNED_BG  = QColor(245, 248, 245)
_C_DROP_HINT      = QColor(50, 120, 255, 50)
_C_VACATION_FILL  = QColor(255, 160, 100, 100)  # semi-transparent orange overlay
_C_VACATION_BORDER = QColor(190, 90, 30, 180)   # darker orange border
_C_VACATION_TEXT  = QColor(130, 50, 10)          # dark-brown label text
_C_SECONDARY_FILL = QColor(255, 230, 120, 120)   # semi-transparent yellow overlay
_C_SECONDARY_BORDER = QColor(200, 160, 20, 190)  # amber border for secondary calendar
_C_SECONDARY_TEXT = QColor(120, 90, 10)          # dark amber text
_C_GHOST_BLOCKED  = QColor(220, 60, 60, 80)      # red ghost when drop is blocked
_C_GHOST_BLOCKED_PEN = QColor(180, 30, 30, 200)  # red dashed border for blocked ghost
_C_CONFLICT_ROW_BG   = QColor(255, 220, 220)      # light red row background for conflicted resources
_C_CONFLICT_ROW_TEXT = QColor(160, 0, 0)          # dark red text for conflicted resources
_C_CONFLICT_BADGE    = QColor(200, 0, 0)          # solid red for the conflict badge circle


# ---------------------------------------------------------------------------
# Helper: extract resource exception blocks from calendar exceptions
# ---------------------------------------------------------------------------

def _get_resource_vacation_blocks(resource, project=None) -> list:
    """Return non-working blocks for this resource.

    Includes:
      1) personal calendar exceptions (orange), and
      2) mapped secondary calendar exceptions (yellow).
    """
    blocks = []

    def _append_blocks_from_calendar(cal, source: str, fallback_name: str,
                                     parent_dates: set | None = None):
        if cal is None:
            return
        cal_name = fallback_name
        try:
            cal_name = str(cal.getName() or fallback_name)
        except Exception:
            pass
        for ex in cal.getCalendarExceptions():
            # Skip working-day overrides (e.g. special working Saturdays)
            try:
                if bool(ex.getWorking()):
                    continue
            except Exception:
                pass
            from_str = str(ex.getFromDate() or "")[:10]
            to_str   = str(ex.getToDate()   or "")[:10]
            if not from_str:
                continue
            # For secondary calendars: skip exceptions inherited from the parent
            # calendar (e.g. national holidays that are already rendered as
            # non-working background).  Only state-specific extra holidays are
            # shown as yellow blocks.
            if parent_dates is not None and from_str in parent_dates:
                continue
            from_qd = QDate.fromString(from_str, "yyyy-MM-dd")
            to_qd   = QDate.fromString(to_str,   "yyyy-MM-dd") if to_str else from_qd
            if not from_qd.isValid():
                continue
            if not to_qd.isValid():
                to_qd = from_qd
            ex_name = str(ex.getName() or "").strip()
            if source == "secondary":
                # ex_name may be empty when the exception was loaded back from
                # XML via a parent-calendar merge; fall back to the calendar name.
                label = ex_name if ex_name else cal_name
                shown_name = f"{cal_name}: {label}"
            else:
                shown_name = ex_name or "Vacation"
            blocks.append({
                'from_qd': from_qd,
                'to_qd': to_qd,
                'name': shown_name,
                'exception': ex,
                'source': source,
                'calendar_name': cal_name,
            })

    try:
        cal = resource.getCalendar()
        _append_blocks_from_calendar(cal, "primary", "Vacation")

        if project is not None:
            try:
                from integrations.secondary_calendar_integration import (  # type: ignore
                    resolve_secondary_calendar,
                )

                sec = resolve_secondary_calendar(project, resource)
                if sec and sec.get('calendar') is not None:
                    sec_cal = sec.get('calendar')
                    # Collect the parent calendar's exception dates so we can
                    # filter them out from the secondary-calendar yellow blocks.
                    # MPXJ's getCalendarExceptions() on a child calendar may
                    # include inherited parent exceptions (without names); we
                    # only want to highlight the state/region-specific extras.
                    #
                    # IMPORTANT: only add NAMED exceptions to parent_dates.
                    # Anonymous entries (name is null/empty) are typically
                    # multi-week school-holiday or Confluence-synced blocks that
                    # do not correspond to any specific public holiday.  Including
                    # their fromDate would incorrectly suppress state-specific
                    # secondary-calendar holidays that happen to share the same
                    # start date (e.g. Fronleichnam on 2026-06-04 being masked by
                    # a Schulferien block that starts on the same day).
                    parent_dates: set = set()
                    try:
                        parent_cal = sec_cal.getParent()
                        if parent_cal is not None:
                            for pex in parent_cal.getCalendarExceptions():
                                try:
                                    pname = str(pex.getName() or "").strip()
                                    if not pname:
                                        continue
                                    pd = str(pex.getFromDate() or "")[:10]
                                    if pd:
                                        parent_dates.add(pd)
                                except Exception:
                                    pass
                    except Exception:
                        pass
                    # Additionally, if the secondary calendar was saved/loaded
                    # without a parent link, fall back to the default calendar.
                    if not parent_dates and project is not None:
                        try:
                            default_cal = project.getDefaultCalendar()
                            if default_cal is not None and default_cal != sec_cal:
                                for dex in default_cal.getCalendarExceptions():
                                    try:
                                        dname = str(dex.getName() or "").strip()
                                        if not dname:
                                            continue
                                        dd = str(dex.getFromDate() or "")[:10]
                                        if dd:
                                            parent_dates.add(dd)
                                    except Exception:
                                        pass
                        except Exception:
                            pass
                    _append_blocks_from_calendar(
                        sec_cal, "secondary",
                        str(sec.get('calendar_name') or "Secondary"),
                        parent_dates=parent_dates,
                    )
            except Exception:
                pass

        # De-duplicate by date range + visible label + source.
        unique = {}
        for b in blocks:
            key = (
                b['from_qd'].toString(Qt.ISODate),
                b['to_qd'].toString(Qt.ISODate),
                b.get('name', ''),
                b.get('source', 'primary'),
            )
            unique[key] = b
        blocks = list(unique.values())

        blocks.sort(key=lambda b: b['from_qd'].toJulianDay())
    except Exception:
        pass
    return blocks


# ---------------------------------------------------------------------------
# Read-only vacation / calendar exception dialog
# ---------------------------------------------------------------------------

class _VacationDialog(QDialog):
    """Read-only info dialog for a vacation / calendar exception block."""

    def __init__(self, vac: dict, res_name: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Vacation / Calendar Exception")
        self.setModal(True)
        self.setFixedWidth(400)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Title label
        title = QLabel(f"<b>{vac['name']}</b>")
        title.setTextFormat(Qt.RichText)
        title.setStyleSheet("font-size:13px; color:#5a2000;")
        layout.addWidget(title)

        # Separator
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color:#c87040;")
        layout.addWidget(sep)

        from PyQt5.QtWidgets import QFormLayout  # type: ignore
        form = QFormLayout()
        form.setSpacing(6)
        form.setLabelAlignment(Qt.AlignRight)

        def _ro(text: str) -> QLabel:
            lbl = QLabel(text)
            lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
            return lbl

        form.addRow("Resource:",  _ro(res_name))
        form.addRow("Exception:", _ro(vac['name']))
        if vac.get('calendar_name'):
            form.addRow("Calendar:", _ro(str(vac.get('calendar_name'))))
        if vac.get('source'):
            src = "Secondary calendar" if vac.get('source') == 'secondary' else "Resource calendar"
            form.addRow("Source:", _ro(src))
        form.addRow("From:",      _ro(vac['from_qd'].toString("dddd, d MMMM yyyy")))
        form.addRow("To:",        _ro(vac['to_qd'].toString("dddd, d MMMM yyyy")))
        days = vac['from_qd'].daysTo(vac['to_qd']) + 1
        form.addRow("Duration:",  _ro(f"{days} calendar day{'s' if days != 1 else ''}"))

        # Extra details from the MPXJ exception object if available
        try:
            ex = vac['exception']
            working_str = "Working" if bool(ex.getWorking()) else "Non-Working"
            form.addRow("Type:", _ro(working_str))
        except Exception:
            pass

        layout.addLayout(form)

        note = QLabel("<i>This block is read-only and cannot be moved or deleted here.</i>")
        note.setTextFormat(Qt.RichText)
        note.setStyleSheet("color:#888; font-size:10px;")
        note.setWordWrap(True)
        layout.addWidget(note)

        btn_box = QDialogButtonBox(QDialogButtonBox.Ok)
        btn_box.accepted.connect(self.accept)
        layout.addWidget(btn_box)


# ---------------------------------------------------------------------------
# Helper: date ↔ x-coordinate conversion (mirrors GanttCanvas)
# ---------------------------------------------------------------------------

def _chip_dur_str(task) -> str:
    """Short duration label for a chip second line using MPXJ working-day duration.
    Uses the same unit-conversion logic as the Gantt view (hours/8, months*20).
    Weeks are 5 working days. E.g. '5d', '2w', '1w 3d'.
    """
    try:
        dur = task.getDuration()
        if dur is not None:
            dur_val  = float(str(dur.getDuration()))
            unit_str = str(dur.getUnits()).upper() if dur.getUnits() is not None else "DAYS"
            if "HOUR" in unit_str:
                dur_val /= 8.0
            elif "WEEK" in unit_str:
                dur_val *= 5.0
            elif "MONTH" in unit_str:
                dur_val *= 20.0
            days = max(1, int(round(dur_val)))
            weeks, rem = divmod(days, 5)   # 5 working days per week
            if weeks == 0:
                return f"{days}d"
            return f"{weeks}w {rem}d" if rem else f"{weeks}w"
    except Exception:
        pass
    return ""


def _col_to_x(col: int, day_width: int) -> int:
    return col * day_width


def _x_to_date(x: int, project_start: QDate, day_width: int, show_sundays: bool) -> QDate:
    """Pixel x → calendar QDate (approximate, weekend-aware when show_sundays=False)."""
    if project_start is None or day_width <= 0:
        return QDate.currentDate()
    col = max(0, x // day_width)
    if show_sundays:
        return project_start.addDays(col)
    # Map visible column back to calendar day
    counted = 0
    d = 0
    while counted < col:
        d += 1
        if project_start.addDays(d).dayOfWeek() != 7:
            counted += 1
    return project_start.addDays(d)


# ---------------------------------------------------------------------------
# Lane-layout helpers
# ---------------------------------------------------------------------------

def _compute_lane_layout(tasks: list) -> list:
    """Greedy interval coloring: assign each task to the lowest-index lane
    that has no temporal overlap with it.
    Returns list of {{'task': ..., 'lane': int}} sorted by start date.
    """
    if not tasks:
        return []

    def _julian(t, finish=False):
        d = _to_qdate(t.getFinish() if finish else t.getStart())
        return d.toJulianDay() if d else 0

    items = sorted(tasks, key=lambda t: _julian(t))
    lane_end: list = []   # latest finish Julian day per lane
    result   = []
    for t in items:
        ts = _julian(t, False)
        tf = _julian(t, True) or ts + 1
        placed = False
        for i, end in enumerate(lane_end):
            if ts >= end:               # fits in this lane without overlap
                lane_end[i] = tf
                result.append({'task': t, 'lane': i})
                placed = True
                break
        if not placed:
            result.append({'task': t, 'lane': len(lane_end)})
            lane_end.append(tf)
    return result


def _row_height_for_lanes(n_lanes: int) -> int:
    """Row pixel height that fits n_lanes sub-lanes."""
    return max(ROW_H, LANE_PAD_V * 2 + n_lanes * LANE_H)


# ---------------------------------------------------------------------------
# Serial/Parallel placement dialog
# ---------------------------------------------------------------------------

class _PlacementDialog(QDialog):
    """Ask the user how to place a dropped task on a busy resource row."""

    SERIAL   = "serial"
    PARALLEL = "parallel"
    CANCEL   = "cancel"

    def __init__(self, task_name: str, res_name: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Task Placement")
        self.setModal(True)
        self._choice = self.CANCEL

        layout = QVBoxLayout(self)
        lbl = QLabel(
            f'Place "<b>{task_name}</b>" on <b>{res_name}</b>:'
        )
        lbl.setTextFormat(Qt.RichText)
        layout.addWidget(lbl)

        btn_box = QDialogButtonBox(Qt.Horizontal)
        btn_serial   = QPushButton("Serial (after last task)")
        btn_parallel = QPushButton("Parallel (at dropped position)")
        btn_cancel   = QPushButton("Cancel")
        btn_box.addButton(btn_serial,   QDialogButtonBox.ActionRole)
        btn_box.addButton(btn_parallel, QDialogButtonBox.ActionRole)
        btn_box.addButton(btn_cancel,   QDialogButtonBox.RejectRole)
        btn_serial.clicked.connect(lambda: self._pick(self.SERIAL))
        btn_parallel.clicked.connect(lambda: self._pick(self.PARALLEL))
        btn_cancel.clicked.connect(self.reject)
        layout.addWidget(btn_box)

    def _pick(self, choice: str):
        self._choice = choice
        self.accept()

    def choice(self) -> str:
        return self._choice


# ---------------------------------------------------------------------------
# Vacation-overlap dialog
# ---------------------------------------------------------------------------

class _VacationSplitDialog(QDialog):
    """Ask the user how to handle a task drag that would land on a vacation block.

    Options:
      • Split around vacation  – only enabled when geometrically possible
      • Shift after vacation   – move entire task to first working day after vac
      • Move anyway            – ignore the overlap
      • Cancel
    """

    SPLIT  = 'split'
    SHIFT  = 'shift'
    MOVE   = 'move'

    def __init__(self, task_name: str, vac_name: str,
                 vac_from: str, vac_to: str,
                 can_split: bool, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Task Overlaps Vacation")
        self.setModal(True)
        self._choice = None

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        lbl = QLabel(
            f'<b>{task_name}</b> would overlap the vacation<br>'
            f'<b>{vac_name}</b> &nbsp;({vac_from} \u2013 {vac_to}).'
        )
        lbl.setTextFormat(Qt.RichText)
        lbl.setWordWrap(True)
        layout.addWidget(lbl)

        def _opt_btn(title: str, subtitle: str, enabled: bool = True) -> QPushButton:
            btn = QPushButton(f'{title}\n{subtitle}')
            btn.setEnabled(enabled)
            btn.setMinimumHeight(46)
            btn.setStyleSheet(
                "QPushButton { text-align:left; padding:5px 10px; }\n"
                "QPushButton:disabled { color:#999; }"
            )
            return btn

        self._btn_split = _opt_btn(
            "\u2702  Split around vacation",
            "Segment 1 ends the day before vacation; segment 2 starts the day after.",
            enabled=can_split,
        )
        self._btn_shift = _opt_btn(
            "\u27a1  Shift after vacation",
            "Move the entire task to start on the first working day after vacation.",
        )
        self._btn_move = _opt_btn(
            "\u2194  Move anyway",
            "Ignore the overlap and place the task as dragged.",
        )
        btn_cancel = QPushButton("Cancel")

        self._btn_split.clicked.connect(lambda: self._pick(self.SPLIT))
        self._btn_shift.clicked.connect(lambda: self._pick(self.SHIFT))
        self._btn_move.clicked.connect(lambda: self._pick(self.MOVE))
        btn_cancel.clicked.connect(self.reject)

        layout.addWidget(self._btn_split)
        layout.addWidget(self._btn_shift)
        layout.addWidget(self._btn_move)
        layout.addWidget(btn_cancel)
        self.setMinimumWidth(440)

    def _pick(self, choice: str):
        self._choice = choice
        self.accept()

    def choice(self) -> str | None:
        return self._choice


# ---------------------------------------------------------------------------
# Non-working-day overlap dialog
# ---------------------------------------------------------------------------

class _NonWorkingDayDialog(QDialog):
    """Ask the user how to handle a task drag that starts on a non-working day
    (weekend or public holiday).

    Options:
      • Move to next working day  – shift start forward to first working day
      • Move anyway               – keep the date as dragged
      • Cancel
    """

    NEXT   = 'next'
    MOVE   = 'move'

    def __init__(self, task_name: str, day_label: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Non-working Day")
        self.setModal(True)
        self._choice = None

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        lbl = QLabel(
            f'<b>{task_name}</b> would start on <b>{day_label}</b>,<br>'
            f'which is a non-working day.'
        )
        lbl.setTextFormat(Qt.RichText)
        lbl.setWordWrap(True)
        layout.addWidget(lbl)

        def _opt_btn(title: str, subtitle: str) -> QPushButton:
            btn = QPushButton(f'{title}\n{subtitle}')
            btn.setMinimumHeight(46)
            btn.setStyleSheet("QPushButton { text-align:left; padding:5px 10px; }")
            return btn

        btn_next   = _opt_btn(
            "⏭  Move to next working day",
            "Shift the start forward to the first available working day.",
        )
        btn_move   = _opt_btn(
            "↔  Move anyway",
            "Keep the task on the non-working day as dragged.",
        )
        btn_cancel = QPushButton("Cancel")

        btn_next.clicked.connect(lambda: self._pick(self.NEXT))
        btn_move.clicked.connect(lambda: self._pick(self.MOVE))
        btn_cancel.clicked.connect(self.reject)

        layout.addWidget(btn_next)
        layout.addWidget(btn_move)
        layout.addWidget(btn_cancel)
        self.setMinimumWidth(400)

    def _pick(self, choice: str):
        self._choice = choice
        self.accept()

    def choice(self) -> str | None:
        return self._choice


# ---------------------------------------------------------------------------
# Segment overlap / merge dialog
# ---------------------------------------------------------------------------

class _SegmentMergeDialog(QDialog):
    """Ask the user how to handle a segment drag that would overlap an adjacent segment.

    Options:
      • Merge segments  – remove the split, task becomes a single bar
      • Cancel
    """

    MERGE = 'merge'

    def __init__(self, task_name: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Segment Overlap")
        self.setModal(True)
        self._choice = None

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        lbl = QLabel(
            f'Moving this segment of <b>{task_name}</b><br>'
            f'would overlap an adjacent segment.'
        )
        lbl.setTextFormat(Qt.RichText)
        lbl.setWordWrap(True)
        layout.addWidget(lbl)

        def _opt_btn(title: str, subtitle: str) -> QPushButton:
            btn = QPushButton(f'{title}\n{subtitle}')
            btn.setMinimumHeight(46)
            btn.setStyleSheet("QPushButton { text-align:left; padding:5px 10px; }")
            return btn

        btn_merge  = _opt_btn(
            "\u2295  Merge segments",
            "Combine both segments into a single continuous task bar.",
        )
        btn_cancel = QPushButton("Cancel")

        btn_merge.clicked.connect(lambda: self._pick(self.MERGE))
        btn_cancel.clicked.connect(self.reject)

        layout.addWidget(btn_merge)
        layout.addWidget(btn_cancel)
        self.setMinimumWidth(400)

    def _pick(self, choice: str):
        self._choice = choice
        self.accept()

    def choice(self) -> str | None:
        return self._choice


# ---------------------------------------------------------------------------
# Left frozen resource-name pane
# ---------------------------------------------------------------------------

class _ResourcePane(QWidget):
    """Frozen left column: resource-name labels aligned to canvas row heights.

    Uses a paint-offset approach (set_scroll_y) so vertical sync is driven
    directly from the external scrollbar value — no QScrollArea internal scroll.
    """

    jump_to_task_requested    = pyqtSignal(int)   # emits resource row index
    resource_double_clicked   = pyqtSignal(int)   # emits resource row index

    def __init__(self, parent=None):
        super().__init__(parent)
        self._names       : list  = []
        self._row_heights : list  = []
        self._row_y       : list  = []
        self._total_h     : int   = 0
        self._conflicts   : list  = []   # list[bool] — True if row has a scheduling conflict
        self._tooltips    : list  = []   # list[str]  — tooltip text per row (empty = none)
        self._scroll_y    : int   = 0    # current vertical scroll offset (in content pixels)
        self._resources   : list  = []   # parallel list of java Resource objects
        self.setFixedWidth(RESOURCE_COL_W)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)
        self.setMouseTracking(True)

    def set_layout(self, names: list, row_heights: list, row_y_offsets: list,
                   total_content_h: int):
        """Called by canvas.layout_changed signal whenever lane layout changes."""
        self._names       = names
        self._row_heights = row_heights
        self._row_y       = row_y_offsets
        self._total_h     = total_content_h
        # Reset conflicts/tooltips to match new row count (signals arrive separately)
        self._conflicts   = [False] * len(names)
        self._tooltips    = [''] * len(names)
        # Widget fills the QScrollArea viewport (widgetResizable=True) — no fixed height.
        self.update()

    def set_resources(self, resources: list):
        """Store the parallel java Resource list for dialog opening on double-click."""
        self._resources = list(resources)

    def set_scroll_y(self, y: int):
        """Called from the external _rows_vsb to keep names aligned to canvas rows."""
        self._scroll_y = y
        self.update()

    def set_conflicts(self, conflicts: list):
        """Receive a list[bool] of conflict flags, one per resource row."""
        self._conflicts = list(conflicts)
        self.update()

    def set_tooltips(self, tooltips: list):
        """Receive a list[str] of tooltip texts, one per resource row."""
        self._tooltips = list(tooltips)

    def event(self, ev):
        if ev.type() == QEvent.ToolTip:
            row = self._y_to_row(ev.pos().y())
            tip = self._tooltips[row] if 0 <= row < len(self._tooltips) else ''
            if tip:
                QToolTip.showText(ev.globalPos(), tip, self)
            else:
                QToolTip.hideText()
                ev.ignore()
            return True
        return super().event(ev)

    def _y_to_row(self, y: int) -> int:
        """Return the row index under viewport pixel y, or -1."""
        content_y = y + self._scroll_y
        for i, (ry, rh) in enumerate(zip(self._row_y, self._row_heights)):
            if ry <= content_y < ry + rh:
                return i
        return -1

    def contextMenuEvent(self, event):
        row = self._y_to_row(event.y())
        if not (0 <= row < len(self._names)):
            return
        res_name = self._names[row]
        menu = QMenu(self)
        act_jump = menu.addAction(f"Scroll timeline to first task of '{res_name}'")
        act_info = menu.addAction(f"Resource Information\u2026")
        action = menu.exec_(event.globalPos())
        if action == act_jump:
            self.jump_to_task_requested.emit(row)
        elif action == act_info:
            self.resource_double_clicked.emit(row)

    def mouseDoubleClickEvent(self, event):
        """Double-click on a resource row → open Resource Information dialog."""
        row = self._y_to_row(event.y())
        if 0 <= row < len(self._names):
            self.resource_double_clicked.emit(row)

    def paintEvent(self, event):
        painter   = QPainter(self)
        w         = RESOURCE_COL_W
        font_bold = QFont("Segoe UI", 9, QFont.Bold)
        font_norm = QFont("Segoe UI", 9)
        fm        = QFontMetrics(font_norm)
        BADGE_R   = 5   # radius of the conflict dot badge

        for i, name in enumerate(self._names):
            y       = self._row_y[i]        if i < len(self._row_y)        else i * ROW_H
            y      -= self._scroll_y
            rh      = self._row_heights[i]  if i < len(self._row_heights)  else ROW_H
            conflict = self._conflicts[i]   if i < len(self._conflicts)    else False

            # Row background
            if conflict:
                painter.fillRect(0, y, w, rh, _C_CONFLICT_ROW_BG)
            else:
                bg = _C_ROW_EVEN if i % 2 == 0 else _C_ROW_ODD
                painter.fillRect(0, y, w, rh, bg)

            painter.setPen(QPen(_C_SEPARATOR, 1))
            painter.drawLine(0, y, w, y)

            # Text (red when conflicted)
            painter.setPen(_C_CONFLICT_ROW_TEXT if conflict else QColor(30, 30, 80))
            painter.setFont(font_bold if conflict else font_norm)
            # Reserve space on the right for the conflict badge
            text_w = w - 12 - (BADGE_R * 2 + 6) if conflict else w - 12
            text   = fm.elidedText(name, Qt.ElideRight, text_w)
            painter.drawText(QRect(8, y, text_w, rh),
                             Qt.AlignVCenter | Qt.AlignLeft, text)

            # Conflict badge: filled red circle with "!" on the right side
            if conflict:
                cx = w - BADGE_R - 6
                cy = y + rh // 2
                painter.setBrush(QBrush(_C_CONFLICT_BADGE))
                painter.setPen(Qt.NoPen)
                painter.drawEllipse(cx - BADGE_R, cy - BADGE_R,
                                    BADGE_R * 2, BADGE_R * 2)
                painter.setPen(QColor(255, 255, 255))
                f_badge = QFont("Segoe UI", 7, QFont.Bold)
                painter.setFont(f_badge)
                painter.drawText(QRect(cx - BADGE_R, cy - BADGE_R,
                                       BADGE_R * 2, BADGE_R * 2),
                                 Qt.AlignCenter, "!")

        # Right border
        painter.setPen(QPen(_C_SEPARATOR, 1))
        painter.drawLine(w - 1, 0, w - 1, self.height())
        painter.end()


# ---------------------------------------------------------------------------
# Main drawing + interaction canvas
# ---------------------------------------------------------------------------

class TeamPlannerCanvas(QWidget):
    """Paints resource rows with task bars.
    Emits:
      task_rescheduled(task, delta_days)         – bar dragged left/right
      task_reassigned(task, old_res, new_res, placement) – bar moved to new row
      layout_changed(names, heights, y_offs, h)  – lane layout recomputed
      unassigned_changed([task, ...])            – unassigned task list updated
    """

    task_rescheduled   = pyqtSignal(object, int)
    task_reassigned    = pyqtSignal(object, object, object, str)
    layout_changed     = pyqtSignal(list, list, list, int)
    unassigned_changed = pyqtSignal(list)
    conflicts_changed         = pyqtSignal(list)   # list[bool] one per resource row
    conflict_tooltips_changed = pyqtSignal(list)   # list[str]  tooltip text per row
    # layout_changed  emits (names, row_heights, row_y_offsets, total_rows_h) for _ResourcePane
    # unassigned_changed emits [task, ...] for _UnassignedPanel
    # conflicts_changed emits [bool, ...] — True where a resource has a scheduling conflict
    # conflict_tooltips_changed emits [str, ...] — rich tooltip text per row

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project       = None
        self._resources     = []          # [java Resource, ...]
        self._res_names     = []          # [str, ...]
        self._tasks_by_res  : dict = {}   # res_uid -> [java Task]
        self._unassigned    = []          # [java Task]

        self.project_start  = QDate.currentDate()
        self.total_days     = 90
        self.day_width      = DAY_WIDTH_DEF
        self.show_sundays   = True
        self._non_working   : set = set()
        # Hourly zoom fields
        self._work_hour_start   = WORK_HOUR_START
        self._work_hour_end     = WORK_HOUR_END
        self._work_day_hours    = WORK_DAY_HOURS
        self._non_working_slots: frozenset = frozenset()
        self._clock_day_span    = WORK_DAY_HOURS
        self._show_off_hours    = False

        # Lane layout (recomputed after every load or task change)
        self._lane_data    : dict = {}   # res_uid -> [{'task':..,'lane':int}]
        self._row_heights  : list = []   # per resource row height (px)
        self._row_y_off    : list = []   # cumulative y offset per resource row
        self._ua_y         : int  = 0    # y start of unassigned panel

        # Critical path
        self._critical_ids       : set  = set()   # int task IDs on the critical path
        self._zero_float_critical: bool = False   # treat zero-float as critical

        # Bar cache: list of dicts {task, res_idx, x1, x2, y_top, is_chip, chip_idx}
        self._bars          : list = []
        # Vacation-block cache: list of dicts {res_idx, x1, x2, y1, y2, vac}
        self._vac_bars      : list = []
        # Shared reference to gantt_view._task_splits for split rendering
        self._task_splits_ref: dict = {}

        # Drag state
        self._drag_task       = None
        self._drag_is_chip    = False       # dragging from unassigned area?
        self._drag_res_idx    = -1          # source resource row index (-1 if chip)
        self._drag_segment_idx = -1         # which split segment is being dragged (-1 = whole task)
        self._drag_start_x    = 0
        self._drag_start_y    = 0
        self._drag_col_off    = 0           # column offset within bar at click
        self._drag_delta      = 0           # days delta during active drag
        self._drag_target_row = -1          # current hover row index (-1 = unassigned)
        self._chip_drop_x     = 0           # canvas x for chip ghost rendering
        self._is_dragging     = False
        self._last_vacation_action: str | None = None  # choice recorded by _ask_vacation_split

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

    # ------------------------------------------------------------------ #
    # Data loading                                                        #
    # ------------------------------------------------------------------ #

    def set_zero_float_critical(self, value: bool):
        """Set whether zero-float tasks are treated as critical."""
        self._zero_float_critical = value

    def set_splits_ref(self, splits_dict: dict) -> None:
        """Set a shared reference to GanttCanvas._task_splits for split rendering."""
        self._task_splits_ref = splits_dict
        self.update()

    def _uid_for_task(self, task) -> int | None:
        """Return integer UniqueID for a Java task, or None."""
        try:
            uid = task.getUniqueID()
            if uid is None or str(uid) in ('null', 'None', ''):
                return None
            return int(str(uid))
        except Exception:
            return None

    def load_project(self, project, recompute_critical=False):
        self._project = project
        self._resources = []
        self._res_names = []
        self._tasks_by_res = {}
        self._unassigned = []
        self._bars = []
        self._vac_bars = []
        self._vacations_by_res = {}

        if project is None:
            self._apply_size()
            self.update()
            return

        # Collect resources (skip the "null" resource at uid 0)
        def _safe_uid(r):
            try:
                return int(str(r.getUniqueID()))
            except Exception:
                return None

        # Build resource list.  Resources with null/unparseable UID are still
        # included so they appear as (empty) rows in the planner.
        # Task-to-resource assignment matching requires a valid UID; resources
        # without one will simply show as rows with no task bars.
        res_list = [r for r in project.getResources()
                    if r.getName() is not None]
        self._resources = res_list
        self._res_names = [str(r.getName()) for r in res_list]
        # Build res_uid → tasks map only for resources with a valid UID.
        for r in res_list:
            uid = _safe_uid(r)
            if uid is not None:
                self._tasks_by_res[uid] = []

        for task in project.getTasks():
            if task.getName() is None or str(task.getID()) == "0":
                continue
            assignments = list(task.getResourceAssignments() or [])
            assigned = False
            for asgn in assignments:
                res = asgn.getResource()
                if res is None:
                    continue
                uid = _safe_uid(res)
                if uid is None:
                    continue
                if uid in self._tasks_by_res:
                    self._tasks_by_res[uid].append(task)
                    assigned = True
            if not assigned:
                # Skip summary (parent) tasks — they have child tasks
                try:
                    is_summary = bool(task.getSummary())
                except Exception:
                    is_summary = False
                if not is_summary:
                    self._unassigned.append(task)

        # Compute timeline extents
        all_tasks_with_dates = [t for t in project.getTasks()
                                 if t.getName() is not None and _to_qdate(t.getStart())]
        starts   = [_to_qdate(t.getStart()) for t in all_tasks_with_dates]
        starts   = [s for s in starts if s]
        finishes = [_to_qdate(t.getFinish()) for t in all_tasks_with_dates]
        finishes = [f for f in finishes if f]
        # Also consider the project-properties start date so the timeline
        # begins at the intended project start even when the first task
        # starts later (e.g. the project was opened today but scheduled
        # from a past kick-off date stored in project properties).
        try:
            props_start = _to_qdate(project.getProjectProperties().getStartDate())
        except Exception:
            props_start = None

        if starts:
            self.project_start = min(starts)
            if props_start and props_start.isValid() and props_start < self.project_start:
                self.project_start = props_start
            max_f = max(finishes) if finishes else self.project_start
            self.total_days = max(self.project_start.daysTo(max_f) + 14, 30)
        else:
            self.project_start = props_start if (props_start and props_start.isValid()) else QDate.currentDate()
            self.total_days = 90

        self._non_working = _get_non_working_dates(
            project, self.project_start, self.total_days)

        # Critical path: always recomputed via internal CPM, ignoring any flag
        # stored in the MPXJ/MS Project file.
        all_tasks_full = [t for t in project.getTasks()
                          if t.getName() is not None and str(t.getID()) != "0"]
        _normalize_schedule(all_tasks_full)
        self._critical_ids = _compute_critical_ids(
            all_tasks_full, project,
            zero_float_critical=self._zero_float_critical)

        # Read working-hour window for hourly zoom mode
        (self._work_hour_start, self._work_hour_end,
         self._work_day_hours, self._non_working_slots) = read_work_hours(project)
        self._clock_day_span = self._work_hour_end - self._work_hour_start

        # Build vacation blocks (calendar exceptions) per resource
        self._vacations_by_res = {}
        for r in res_list:
            try:
                uid = int(str(r.getUniqueID()))
            except Exception:
                continue
            self._vacations_by_res[uid] = _get_resource_vacation_blocks(r, project)

        # Extend total_days if any vacation ends beyond the current canvas
        if self.project_start:
            end_date = self.project_start.addDays(self.total_days)
            max_vac = end_date
            for vac_list in self._vacations_by_res.values():
                for vac in vac_list:
                    if vac['to_qd'] > max_vac:
                        max_vac = vac['to_qd']
            if max_vac > end_date:
                self.total_days = self.project_start.daysTo(max_vac) + 14
                self._non_working = _get_non_working_dates(
                    project, self.project_start, self.total_days)

        self._rebuild_layout()
        self._apply_size()
        self.update()

    # ------------------------------------------------------------------ #
    # Lane layout                                                         #
    # ------------------------------------------------------------------ #

    def _rebuild_layout(self):
        """Recompute lane data, row heights and y-offsets for all resources.
        Emits layout_changed and conflicts_changed so _ResourcePane stays in sync.
        """
        self._lane_data   = {}
        self._row_heights = []
        self._row_y_off   = []
        y = 0
        for res in self._resources:
            try:
                uid = int(str(res.getUniqueID()))
            except Exception:
                uid = None
            if uid is None:
                # Skip resources whose UID cannot be resolved; still add a
                # placeholder row so the name pane stays in sync.
                self._row_heights.append(ROW_H)
                self._row_y_off.append(y)
                y += ROW_H
                continue
            tasks = self._tasks_by_res.get(uid, [])
            lanes = _compute_lane_layout(tasks)
            self._lane_data[uid] = lanes
            n_lanes = (max(e['lane'] for e in lanes) + 1) if lanes else 1
            rh = _row_height_for_lanes(n_lanes)
            self._row_heights.append(rh)
            self._row_y_off.append(y)
            y += rh
        self._ua_y = y
        self.layout_changed.emit(
            list(self._res_names),
            list(self._row_heights),
            list(self._row_y_off),
            y,
        )
        self.unassigned_changed.emit(list(self._unassigned))
        flags, tips = self._compute_conflict_data()
        self.conflicts_changed.emit(flags)
        self.conflict_tooltips_changed.emit(tips)

    def _compute_conflict_data(self) -> tuple:
        """Return (list[bool], list[str]) — one entry per resource row.
        bool  : True when the resource has at least one scheduling conflict.
        str   : Rich tooltip text describing all detected problems (empty = no conflict).

        Detected conflicts:
          1. Parallel (overlapping) tasks — more than one lane in the lane layout.
          2. A task scheduled inside one of the resource's vacation blocks.
        """
        flags = []
        tips  = []

        for res in self._resources:
            try:
                uid = int(str(res.getUniqueID()))
            except Exception:
                flags.append(False)
                tips.append('')
                continue
            lanes = self._lane_data.get(uid, [])
            tasks = self._tasks_by_res.get(uid, [])

            problems: list[str] = []

            # ── 1. Parallel / overlapping tasks ──────────────────────
            if lanes and (max(e['lane'] for e in lanes) + 1) > 1:
                # Find tasks in lane > 0 — they each overlap with something
                # Build a set of overlapping task names per cluster
                # Sort all entries by start, then find pairs that actually overlap
                def _jday_s(e):
                    d = _to_qdate(e['task'].getStart())
                    return d.toJulianDay() if d else 0
                def _jday_f(e):
                    d = _to_qdate(e['task'].getFinish())
                    return d.toJulianDay() if d else _jday_s(e) + 1

                sorted_entries = sorted(lanes, key=_jday_s)
                overlap_pairs  = []
                seen_pairs     = set()
                for i, a in enumerate(sorted_entries):
                    a_s = _jday_s(a)
                    a_f = _jday_f(a)
                    for b in sorted_entries[i + 1:]:
                        b_s = _jday_s(b)
                        if b_s >= a_f:
                            break  # sorted, no more overlaps possible with a
                        b_f = _jday_f(b)
                        if a_s < b_f and a_f > b_s:
                            na = str(a['task'].getName() or "?")
                            nb = str(b['task'].getName() or "?")
                            key = (min(na, nb), max(na, nb))
                            if key not in seen_pairs:
                                seen_pairs.add(key)
                                overlap_pairs.append((na, nb))

                if overlap_pairs:
                    lines = ["Parallel tasks (overlapping at the same time):"]
                    for na, nb in overlap_pairs:
                        lines.append(f'  \u2022 "{na}"  \u2194  "{nb}"')
                    problems.append("\n".join(lines))

            # ── 2. Tasks scheduled inside a vacation block ────────────
            vac_list = self._vacations_by_res.get(uid, [])
            if vac_list:
                vac_hits: list[str] = []
                for task in tasks:
                    t_start  = _to_qdate(task.getStart())
                    t_finish = _to_qdate(task.getFinish())
                    if t_start is None:
                        continue
                    t_end = t_finish if t_finish else t_start.addDays(1)
                    for vac in vac_list:
                        vac_end = vac['to_qd'].addDays(1)
                        if t_start < vac_end and t_end > vac['from_qd']:
                            t_name = str(task.getName() or "?")
                            v_name = vac['name']
                            v_from = vac['from_qd'].toString("d MMM yyyy")
                            v_to   = vac['to_qd'].toString("d MMM yyyy")
                            date_str = v_from if v_from == v_to else f"{v_from} \u2013 {v_to}"
                            vac_hits.append(
                                f'  \u2022 "{t_name}" during "{v_name}" ({date_str})'
                            )
                if vac_hits:
                    lines = ["Tasks scheduled during non-working exceptions:"] + vac_hits
                    problems.append("\n".join(lines))

            # ── Assemble tooltip ──────────────────────────────────────
            if problems:
                tip = "\u26a0 Scheduling conflict(s):\n\n" + "\n\n".join(problems)
                flags.append(True)
                tips.append(tip)
            else:
                flags.append(False)
                tips.append('')

        return flags, tips

    # ------------------------------------------------------------------ #
    # Sizing                                                              #
    # ------------------------------------------------------------------ #

    def _total_rows(self) -> int:
        return len(self._resources)

    def _canvas_height(self) -> int:
        return max(200, self._ua_y)

    def _vis_cols(self) -> int:
        if not self.project_start:
            return self.total_days
        return _date_to_col(self.project_start,
                             self.project_start.addDays(self.total_days),
                             self.show_sundays)

    def _canvas_width(self) -> int:
        if self.day_width >= HOUR_MODE_THRESHOLD and self.project_start:
            eff_span = 24 if self._show_off_hours else self._clock_day_span
            wdays = working_day_count(self.project_start, self.total_days)
            return max(400, wdays * eff_span * self.day_width)
        return self._vis_cols() * self.day_width

    def _apply_size(self):
        self.setFixedSize(QSize(max(400, self._canvas_width()),
                                max(200, self._canvas_height())))

    def set_day_width(self, dw: int):
        self.day_width = max(DAY_WIDTH_MIN, min(DAY_WIDTH_MAX, dw))
        self._apply_size()
        self.update()

    def set_show_off_hours(self, value: bool):
        self._show_off_hours = bool(value)
        self._apply_size()
        self.update()

    def is_hourly_mode(self) -> bool:
        return self.day_width >= HOUR_MODE_THRESHOLD

    def set_show_sundays(self, val: bool):
        self.show_sundays = bool(val)
        self._apply_size()
        self.update()

    # ------------------------------------------------------------------ #
    # Chip drag control (called by TeamPlannerView)                       #
    # ------------------------------------------------------------------ #

    def start_chip_drag(self, task):
        """Notify canvas that a chip drag has started — show ghost bar."""
        self._drag_task       = task
        self._drag_is_chip    = True
        self._drag_res_idx    = -1
        self._drag_target_row = -1
        self._chip_drop_x     = 0
        self._is_dragging     = True
        self.update()

    def update_chip_drag(self, canvas_x: int, row_idx: int):
        """Update ghost position while chip is dragged over the canvas."""
        self._chip_drop_x     = canvas_x
        self._drag_target_row = row_idx
        self.update()

    def end_chip_drag(self):
        """Clear chip drag state (called before assignment logic on drop)."""
        self._drag_task       = None
        self._drag_is_chip    = False
        self._drag_target_row = -1
        self._is_dragging     = False
        self.update()

    # ------------------------------------------------------------------ #
    # Coordinate helpers                                                  #
    # ------------------------------------------------------------------ #

    def _date_to_x(self, date: QDate) -> int:
        if not self.project_start or date is None:
            return 0
        col = _date_to_col(self.project_start, date, self.show_sundays)
        return col * self.day_width

    def _date_to_hourly_x(self, java_datetime) -> int:
        """Convert an MPXJ LocalDateTime to x in hourly mode."""
        return int(datetime_to_hourly_x(
            java_datetime, self.project_start, self.day_width,
            self._work_hour_start, self._clock_day_span, self._show_off_hours))

    def _x_to_date_local(self, x: int) -> QDate:
        return _x_to_date(x, self.project_start, self.day_width, self.show_sundays)

    def _x_to_hour_local(self, x: int) -> int:
        """Return the clock hour (int) at canvas pixel x in hourly mode.
        Falls back to work-hour-start in day mode."""
        if self.day_width < HOUR_MODE_THRESHOLD or self.project_start is None:
            return self._work_hour_start
        eff_start = 0 if self._show_off_hours else self._work_hour_start
        eff_span  = 24 if self._show_off_hours else self._clock_day_span
        if eff_span <= 0 or self.day_width <= 0:
            return self._work_hour_start
        # x is measured in slots of day_width px each
        total_slots = x // self.day_width          # absolute hour slot from canvas left
        slot_in_day = total_slots % eff_span       # slot within a single working day
        hour = eff_start + slot_in_day
        return max(self._work_hour_start,
                   min(hour, self._work_hour_start + self._clock_day_span - 1))

    def _row_y(self, row_idx: int) -> int:
        return self._row_y_off[row_idx] if row_idx < len(self._row_y_off) else row_idx * ROW_H

    def _row_height(self, row_idx: int) -> int:
        return self._row_heights[row_idx] if row_idx < len(self._row_heights) else ROW_H

    def _y_to_row(self, y: int) -> int:
        """Return resource row index, or -1 if below all resource rows."""
        if y < 0:
            return 0   # above canvas → snap to first row
        if y >= self._ua_y:
            return -1  # below resource rows (unassigned zone)
        for i, (yo, rh) in enumerate(zip(self._row_y_off, self._row_heights)):
            if yo <= y < yo + rh:
                return i
        return max(0, len(self._resources) - 1)

    # ------------------------------------------------------------------ #
    # Paint                                                               #
    # ------------------------------------------------------------------ #

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        self._bars     = []
        self._vac_bars = []

        w = self.width()
        is_hourly = self.day_width >= HOUR_MODE_THRESHOLD

        font_sm  = QFont("Segoe UI", 8)
        font_vac = QFont("Segoe UI", 7)
        font_vac.setItalic(True)
        fm_vac = QFontMetrics(font_vac)

        # 1. Row backgrounds (first pass — must come before weekend shading)
        for row_idx, res in enumerate(self._resources):
            y  = self._row_y(row_idx)
            rh = self._row_height(row_idx)
            bg = _C_ROW_EVEN if row_idx % 2 == 0 else _C_ROW_ODD
            painter.fillRect(0, y, w, rh, bg)

        # 2. Column shading
        if is_hourly:
            self._paint_hourly_cols(painter)
        else:
            # 2a. Weekend / holiday column shading (on top of row backgrounds)
            self._paint_weekend_cols(painter)
            # 3. Vertical grid lines
            self._paint_grid(painter, w)

        # 4. Row content: drag highlight, row dividers, lane separators, task bars
        for row_idx, res in enumerate(self._resources):
            res_uid = int(str(res.getUniqueID()))
            y  = self._row_y(row_idx)
            rh = self._row_height(row_idx)

            # Highlight drop target row during drag (on top of weekend shading)
            if self._is_dragging and self._drag_target_row == row_idx:
                painter.fillRect(0, y, w, rh, _C_ROW_DRAG_TARGET)

            painter.setPen(QPen(_C_GRID, 1))
            painter.drawLine(0, y, w, y)

            # Lane separator lines within multi-lane rows
            lane_entries = self._lane_data.get(res_uid, [])
            n_lanes = (max(e['lane'] for e in lane_entries) + 1) if lane_entries else 1
            for ln in range(1, n_lanes):
                ly = y + LANE_PAD_V + ln * LANE_H
                painter.setPen(QPen(_C_GRID, 1, Qt.DotLine))
                painter.drawLine(0, ly, w, ly)

            # 4a. Vacation blocks (painted before task bars so bars float on top)
            self._paint_vacation_blocks_for_row(
                painter, res_uid, row_idx, y, rh, font_vac, fm_vac)

            # Task bars via lane layout
            for entry in lane_entries:
                self._paint_task_bar(painter, entry['task'], row_idx, entry['lane'], font_sm)

        # 5. Ghost / drag preview
        if self._is_dragging and self._drag_task is not None:
            self._paint_drag_ghost(painter, font_sm)

        # 6. Today line
        self._paint_today_line(painter)

        painter.end()

    def _paint_weekend_cols(self, painter: QPainter):
        """Paint Saturday/holiday and Sunday column overlays.
        Called AFTER row backgrounds so shading appears on top.
        Matches GanttCanvas: Saturday/holiday = opaque grey per row;
        Sunday = semi-transparent blue-tint (only when show_sundays=True).
        """
        if not self.project_start:
            return
        h = self._canvas_height()
        col = 0
        for d in range(self.total_days):
            date = self.project_start.addDays(d)
            dow  = date.dayOfWeek()
            if not self.show_sundays and dow == 7:
                continue
            x   = col * self.day_width
            col += 1
            iso = date.toString(Qt.ISODate)
            if dow == 6 or iso in self._non_working:
                # Saturday / public holiday: opaque alternating grey per row
                for row_idx in range(len(self._resources)):
                    ry  = self._row_y(row_idx)
                    rh  = self._row_height(row_idx)
                    row_bg = _C_SAT_EVEN if row_idx % 2 == 0 else _C_SAT_ODD
                    painter.fillRect(x, ry, self.day_width, rh, row_bg)
            elif dow == 7:
                # Sunday: semi-transparent blue-tint over full height
                painter.fillRect(x, 0, self.day_width, h, _C_SUN)

    def _paint_grid(self, painter: QPainter, w: int):
        """Draw vertical column separator lines."""
        if not self.project_start:
            return
        h = self._canvas_height()
        col = 0
        for d in range(self.total_days):
            date = self.project_start.addDays(d)
            dow  = date.dayOfWeek()
            if not self.show_sundays and dow == 7:
                continue
            x = col * self.day_width
            painter.setPen(QPen(_C_GRID, 1))
            painter.drawLine(x, 0, x, h)
            col += 1

    def _paint_hourly_cols(self, painter: QPainter):
        """In hourly mode: draw break/off-hour overlays, public-holiday shading,
        and hourly grid lines."""
        if not self.project_start:
            return
        if self._show_off_hours:
            eff_start = 0
            eff_span  = 24
            working_set = frozenset(range(self._work_hour_start, self._work_hour_end)) - self._non_working_slots
            off_slots   = frozenset(range(24)) - working_set
        else:
            eff_start = self._work_hour_start
            eff_span  = self._clock_day_span
            off_slots  = self._non_working_slots

        dw       = self.day_width
        h        = self._canvas_height()
        grid_pen = QPen(_C_GRID, 1)
        day_pen  = QPen(QColor(140, 175, 215), 1)

        wday = 0
        for di in range(self.total_days):
            d = self.project_start.addDays(di)
            if d.dayOfWeek() in (6, 7):
                continue
            is_holiday = d.toString(Qt.ISODate) in self._non_working
            day_x0 = wday * eff_span * dw
            # Day boundary
            painter.setPen(day_pen)
            painter.drawLine(day_x0, 0, day_x0, h)
            for slot_h in range(eff_span):
                sx       = day_x0 + slot_h * dw
                abs_hour = eff_start + slot_h
                # Opaque per-row shading: public holidays (same as Saturday) or break hours
                if is_holiday or abs_hour in off_slots:
                    for ri, res in enumerate(self._resources):
                        ry = self._row_y(ri)
                        rh = self._row_height(ri)
                        if is_holiday:
                            rc = _C_SAT_EVEN if ri % 2 == 0 else _C_SAT_ODD
                        else:
                            rc = QColor(225, 225, 230) if ri % 2 == 0 else QColor(215, 215, 225)
                        painter.fillRect(sx, ry, dw, rh, rc)
                # Hour grid line
                painter.setPen(grid_pen)
                painter.drawLine(sx, 0, sx, h)
            wday += 1

    def _paint_task_bar(self, painter: QPainter, task, row_idx: int,
                        lane: int, font):
        start_qd  = _to_qdate(task.getStart())
        finish_qd = _to_qdate(task.getFinish())
        if start_qd is None:
            return

        is_hourly = self.day_width >= HOUR_MODE_THRESHOLD

        # Apply drag delta if this is the dragged task
        is_dragged = (task is self._drag_task and not self._drag_is_chip
                      and self._is_dragging)
        if is_dragged:
            draw_row = self._drag_target_row if self._drag_target_row >= 0 else row_idx
            delta_d  = self._drag_delta
            delta_h  = self._drag_delta_hours
        else:
            draw_row = row_idx
            delta_d  = 0
            delta_h  = 0

        if is_hourly:
            x1 = self._date_to_hourly_x(task.getStart()) + delta_h * self.day_width
            x2 = self._date_to_hourly_x(task.getFinish()) + delta_h * self.day_width \
                 if task.getFinish() else x1 + self.day_width
        else:
            s = start_qd.addDays(delta_d)
            f = finish_qd.addDays(delta_d) if finish_qd else s.addDays(1)
            x1 = self._date_to_x(s)
            x2 = self._date_to_x(f)
        bar_w = max(self.day_width, x2 - x1)

        # Y position: row top + top-padding + lane offset, centred in lane
        row_y0 = self._row_y(draw_row)
        bar_y  = row_y0 + LANE_PAD_V + lane * LANE_H + (LANE_H - TASK_BAR_H) // 2

        try:
            _tid = task.getID()
            is_critical = (int(str(_tid)) in self._critical_ids) if (
                _tid is not None and str(_tid) not in ('null', 'None', '')) else False
        except Exception:
            is_critical = False
        if is_critical:
            color = _C_TASK_CRIT_DRAG if is_dragged else _C_TASK_CRITICAL
        else:
            color = _C_TASK_DRAG if is_dragged else _C_TASK_NORMAL

        # ── Split-task rendering (day mode) ──────────────────────────────────────
        if not is_hourly:
            uid  = self._uid_for_task(task)
            segs = self._task_splits_ref.get(uid) if uid is not None else None
            if segs and len(segs) >= 2:
                # Which segment (if any) is being dragged for this task right now?
                seg_drag = (self._drag_segment_idx
                            if is_dragged and self._drag_segment_idx >= 0 else -1)
                prev_x2 = None
                for seg_i, (seg_s, seg_e) in enumerate(segs):
                    if seg_i == seg_drag:
                        prev_x2 = None   # break the dashed connector across the gap
                        continue         # ghost (in _paint_drag_ghost) will draw this
                    sx1 = self._date_to_x(seg_s)
                    sx2 = self._date_to_x(seg_e.addDays(1))
                    sw  = max(self.day_width, sx2 - sx1)
                    painter.setBrush(QBrush(color))
                    painter.setPen(Qt.NoPen)
                    painter.drawRoundedRect(sx1, bar_y, sw, TASK_BAR_H, 3, 3)
                    if prev_x2 is not None and sx1 > prev_x2:
                        mid_y = bar_y + TASK_BAR_H // 2
                        painter.setPen(QPen(color.darker(140), 1, Qt.DashLine))
                        painter.drawLine(prev_x2, mid_y, sx1, mid_y)
                    prev_x2 = sx1 + sw
                # Label at the first visible segment
                vis = [(s, e) for i, (s, e) in enumerate(segs) if i != seg_drag]
                if vis:
                    sx1_0 = self._date_to_x(vis[0][0])
                    sw_0  = max(self.day_width, self._date_to_x(vis[0][1].addDays(1)) - sx1_0)
                    painter.setFont(font)
                    painter.setPen(_C_TASK_TEXT)
                    name  = str(task.getName()) or ""
                    _fm   = QFontMetrics(font)
                    label = _fm.elidedText(name, Qt.ElideRight, max(4, sw_0 - 6))
                    painter.drawText(QRect(sx1_0 + 3, bar_y, sw_0 - 6, TASK_BAR_H),
                                     Qt.AlignVCenter | Qt.AlignLeft, label)
                # Cache one hit-rect per segment (not the full span) so that
                # clicking in the gap between segments returns None from _hit_bar
                # and a segment click delivers the correct seg_idx.
                for seg_i, (seg_s, seg_e) in enumerate(segs):
                    sx1 = self._date_to_x(seg_s)
                    sx2 = self._date_to_x(seg_e.addDays(1))
                    self._bars.append({
                        'task': task, 'res_idx': row_idx, 'lane': lane,
                        'x1': sx1, 'x2': max(sx1 + self.day_width, sx2),
                        'y1': bar_y, 'y2': bar_y + TASK_BAR_H,
                        'is_chip': False, 'seg_idx': seg_i,
                    })
                return
        # ── Normal (unsplit or dragging) bar ───────────────────────────────
        painter.setBrush(QBrush(color))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(x1, bar_y, bar_w, TASK_BAR_H, 3, 3)

        # Progress strip
        pct = 0
        try:
            p = task.getPercentageComplete()
            if p is not None:
                pct = float(str(p))
        except Exception:
            pass
        if pct > 0:
            prog_w = int(bar_w * min(pct, 100) / 100)
            painter.setBrush(QBrush(color.darker(130)))
            painter.drawRoundedRect(x1, bar_y + TASK_BAR_H - 4, prog_w, 4, 2, 2)

        # Label
        painter.setFont(font)
        painter.setPen(_C_TASK_TEXT)
        name  = str(task.getName()) or ""
        fm    = QFontMetrics(font)
        label = fm.elidedText(name, Qt.ElideRight, max(4, bar_w - 6))
        painter.drawText(QRect(x1 + 3, bar_y, bar_w - 6, TASK_BAR_H),
                         Qt.AlignVCenter | Qt.AlignLeft, label)

        # Cache bar for hit-testing (always original/un-dragged position)
        if not is_dragged:
            orig_row_y0 = self._row_y(row_idx)
            bar_y_orig  = orig_row_y0 + LANE_PAD_V + lane * LANE_H + (LANE_H - TASK_BAR_H) // 2
            if is_hourly:
                x1_orig = self._date_to_hourly_x(task.getStart())
                x2_orig = self._date_to_hourly_x(task.getFinish()) if task.getFinish() else x1_orig + self.day_width
            else:
                x1_orig = self._date_to_x(start_qd)
                x2_orig = self._date_to_x(finish_qd) if finish_qd else x1_orig + self.day_width
            self._bars.append({
                'task': task, 'res_idx': row_idx, 'lane': lane,
                'x1': x1_orig, 'x2': max(x1_orig + self.day_width, x2_orig),
                'y1': bar_y_orig, 'y2': bar_y_orig + TASK_BAR_H,
                'is_chip': False,
            })

    def _paint_drag_ghost(self, painter: QPainter, font):
        """Draw a translucent ghost bar at the current drag position."""
        task = self._drag_task
        if task is None:
            return

        if self._drag_is_chip:
            # Ghost bar on the target resource row
            if self._drag_target_row < 0:
                return
            # Duration in working days (same unit conversion as _chip_dur_str)
            try:
                dur = task.getDuration()
                if dur is not None:
                    dur_val  = float(str(dur.getDuration()))
                    unit_str = str(dur.getUnits()).upper() if dur.getUnits() is not None else "DAYS"
                    if "HOUR" in unit_str:
                        dur_val /= 8.0
                    elif "WEEK" in unit_str:
                        dur_val *= 5.0
                    elif "MONTH" in unit_str:
                        dur_val *= 20.0
                    dur_days = max(1, int(round(dur_val)))
                else:
                    dur_days = 1
            except Exception:
                dur_days = 1
            drop_date = self._x_to_date_local(self._chip_drop_x)
            x1 = self._date_to_x(drop_date)
            x2 = x1 + dur_days * self.day_width
            y  = self._row_y(self._drag_target_row) + LANE_PAD_V
        else:
            # Segment-only drag: draw ghost for just the dragged segment
            if self._drag_segment_idx >= 0:
                uid  = self._uid_for_task(task)
                segs = self._task_splits_ref.get(uid) if uid is not None else []
                if segs and 0 <= self._drag_segment_idx < len(segs):
                    seg_s, seg_e = segs[self._drag_segment_idx]
                    s  = seg_s.addDays(self._drag_delta)
                    f  = seg_e.addDays(self._drag_delta)
                    x1 = self._date_to_x(s)
                    x2 = self._date_to_x(f.addDays(1))
                    y  = self._row_y(self._drag_res_idx) + LANE_PAD_V
                    painter.setBrush(QBrush(_C_TASK_GHOST))
                    painter.setPen(QPen(QColor(50, 100, 200), 1, Qt.DashLine))
                    painter.drawRoundedRect(x1, y, max(4, x2 - x1), TASK_BAR_H, 3, 3)
                return
            # Whole-task drag
            start_qd  = _to_qdate(task.getStart())
            finish_qd = _to_qdate(task.getFinish())
            if start_qd is None:
                return
            row = self._drag_target_row if self._drag_target_row >= 0 else self._drag_res_idx
            y  = self._row_y(row) + LANE_PAD_V
            if self.day_width >= HOUR_MODE_THRESHOLD:
                x1 = self._date_to_hourly_x(task.getStart()) + self._drag_delta_hours * self.day_width
                x2 = self._date_to_hourly_x(task.getFinish()) + self._drag_delta_hours * self.day_width \
                     if task.getFinish() else x1 + self.day_width
            else:
                s = start_qd.addDays(self._drag_delta)
                f = finish_qd.addDays(self._drag_delta) if finish_qd else s.addDays(1)
                x1 = self._date_to_x(s)
                x2 = self._date_to_x(f)

        bar_w = max(4, x2 - x1)
        blocked = self._drag_blocked_by_vacation()
        if blocked:
            painter.setBrush(QBrush(_C_GHOST_BLOCKED))
            painter.setPen(QPen(_C_GHOST_BLOCKED_PEN, 1, Qt.DashLine))
        else:
            painter.setBrush(QBrush(_C_TASK_GHOST))
            painter.setPen(QPen(QColor(50, 100, 200), 1, Qt.DashLine))
        painter.drawRoundedRect(x1, y, bar_w, TASK_BAR_H, 3, 3)

    def _paint_today_line(self, painter: QPainter):
        today = QDate.currentDate()
        if not self.project_start or today < self.project_start:
            return
        if self.day_width >= HOUR_MODE_THRESHOLD:
            eff_span  = 24 if self._show_off_hours else self._clock_day_span
            eff_start = 0  if self._show_off_hours else self._work_hour_start
            wday = date_to_working_day_idx(today, self.project_start)
            cur_hour = QTime.currentTime().hour()
            if not self._show_off_hours:
                cur_hour = max(eff_start, min(eff_start + eff_span - 1, cur_hour))
            tx = (wday * eff_span + (cur_hour - eff_start)) * self.day_width
        else:
            tx = self._date_to_x(today)
        painter.setPen(QPen(_C_TODAY, 2))
        painter.drawLine(tx, 0, tx, self._canvas_height())

    def _paint_vacation_blocks_for_row(self, painter: QPainter, res_uid: int,
                                        row_idx: int, y: int, rh: int,
                                        font_vac: QFont, fm_vac: QFontMetrics):
        """Paint all vacation blocks for one resource row and cache their rects."""
        vac_list = self._vacations_by_res.get(res_uid, [])
        if not vac_list:
            return
        is_hourly = self.day_width >= HOUR_MODE_THRESHOLD
        eff_span  = (24 if self._show_off_hours else self._clock_day_span) if is_hourly else 1
        end_of_range = self.project_start.addDays(self.total_days)
        for vac in vac_list:
            from_qd = vac['from_qd']
            to_qd   = vac['to_qd']
            # Skip blocks fully outside the visible range
            if from_qd > end_of_range or to_qd < self.project_start:
                continue
            if is_hourly:
                # In hour mode the canvas uses working-day indices × hour slots
                x1 = (date_to_working_day_idx(from_qd, self.project_start)
                       * eff_span * self.day_width)
                # to_qd is inclusive → right edge = start of the working-day slot
                # that begins on (to_qd + 1)
                x2 = (date_to_working_day_idx(to_qd.addDays(1), self.project_start)
                       * eff_span * self.day_width)
            else:
                x1 = self._date_to_x(from_qd)
                # to_date is inclusive → end pixel is start of the *next* day
                x2 = self._date_to_x(to_qd.addDays(1))
            if x2 <= x1:
                x2 = x1 + self.day_width * eff_span
            bar_w = x2 - x1

            # Filled block (orange for personal calendar, yellow for secondary)
            is_secondary = (vac.get('source') == 'secondary')
            fill_c = _C_SECONDARY_FILL if is_secondary else _C_VACATION_FILL
            border_c = _C_SECONDARY_BORDER if is_secondary else _C_VACATION_BORDER
            text_c = _C_SECONDARY_TEXT if is_secondary else _C_VACATION_TEXT
            painter.setBrush(QBrush(fill_c))
            painter.setPen(QPen(border_c, 1))
            painter.drawRect(x1, y, bar_w, rh)

            # Label (name) near the top if the block is wide enough
            if bar_w >= 20:
                painter.setFont(font_vac)
                painter.setPen(text_c)
                label = fm_vac.elidedText(vac['name'], Qt.ElideRight, bar_w - 6)
                painter.drawText(QRect(x1 + 3, y + 2, bar_w - 6, rh - 4),
                                 Qt.AlignTop | Qt.AlignLeft, label)

            # Cache rect for mouse hit-testing
            self._vac_bars.append({
                'res_idx': row_idx,
                'x1': x1, 'x2': x2,
                'y1': y,  'y2': y + rh,
                'vac': vac,
            })

    # ------------------------------------------------------------------ #
    # Vacation helpers                                                    #
    # ------------------------------------------------------------------ #

    def _hit_vacation(self, x: int, y: int) -> dict | None:
        """Return the vacation bar dict under (x, y) or None."""
        for vb in reversed(self._vac_bars):
            if vb['x1'] <= x <= vb['x2'] and vb['y1'] <= y <= vb['y2']:
                return vb
        return None

    def _get_overlapping_vacation(self, row_idx: int, start_qd: QDate,
                                    finish_qd: QDate) -> dict | None:
        """Return the first vacation on *row_idx* that overlaps [start_qd, finish_qd),
        or None if there is no overlap."""
        if row_idx < 0 or row_idx >= len(self._resources):
            return None
        res_uid  = int(str(self._resources[row_idx].getUniqueID()))
        vac_list = self._vacations_by_res.get(res_uid, [])
        end_qd   = finish_qd if finish_qd else start_qd.addDays(1)
        for vac in vac_list:
            vac_end = vac['to_qd'].addDays(1)   # to_date is inclusive
            if start_qd < vac_end and end_qd > vac['from_qd']:
                return vac
        return None

    def _overlaps_vacation(self, row_idx: int, start_qd: QDate,
                           finish_qd: QDate) -> bool:
        """Return True if [start_qd, finish_qd) overlaps any vacation on the row."""
        return self._get_overlapping_vacation(row_idx, start_qd, finish_qd) is not None

    def _drag_blocked_by_vacation(self) -> bool:
        """Return True if the current drag/drop position lands on a vacation block."""
        if not self._is_dragging or self._drag_task is None:
            return False
        tgt_row = self._drag_target_row
        if tgt_row < 0:
            return False
        task = self._drag_task
        if self._drag_is_chip:
            drop_date = self._x_to_date_local(self._chip_drop_x)
            try:
                dur = task.getDuration()
                dur_val  = float(str(dur.getDuration())) if dur else 1.0
                unit_str = str(dur.getUnits()).upper() if dur and dur.getUnits() else "DAYS"
                if "HOUR" in unit_str:
                    dur_val /= 8.0
                elif "WEEK" in unit_str:
                    dur_val *= 5.0
                elif "MONTH" in unit_str:
                    dur_val *= 20.0
                dur_days = max(1, int(round(dur_val)))
            except Exception:
                dur_days = 1
            end_date = drop_date.addDays(dur_days)
            return self._overlaps_vacation(tgt_row, drop_date, end_date)
        else:
            start_qd  = _to_qdate(task.getStart())
            finish_qd = _to_qdate(task.getFinish())
            if start_qd is None:
                return False
            s = start_qd.addDays(self._drag_delta)
            f = finish_qd.addDays(self._drag_delta) if finish_qd else s.addDays(1)
            return self._overlaps_vacation(tgt_row, s, f)

    # ------------------------------------------------------------------ #
    # Mouse events                                                        #
    # ------------------------------------------------------------------ #

    def _hit_bar(self, x: int, y: int) -> dict | None:
        """Return the bar dict under (x, y) or None."""
        for bar in reversed(self._bars):
            if bar['x1'] <= x <= bar['x2'] and bar['y1'] <= y <= bar['y2']:
                return bar
        return None

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        x, y = event.x(), event.y()
        bar = self._hit_bar(x, y)
        if bar is None:
            return
        self._drag_task        = bar['task']
        self._drag_is_chip     = bar['is_chip']
        self._drag_res_idx     = bar['res_idx']
        self._drag_segment_idx = bar.get('seg_idx', -1)
        self._drag_start_x     = x
        self._drag_start_y     = y
        self._drag_col_off     = x - bar['x1']
        self._drag_delta       = 0
        self._drag_delta_hours = 0
        self._drag_target_row  = bar['res_idx']
        self._is_dragging      = True
        self.grabMouse()          # track mouse even when it leaves the widget
        self.setCursor(Qt.ClosedHandCursor)
        self.update()

    def event(self, ev):
        if ev.type() == QEvent.ToolTip:
            vb = self._hit_vacation(ev.pos().x(), ev.pos().y())
            if vb:
                vac = vb['vac']
                from_str = vac['from_qd'].toString('dd MMM yyyy')
                to_str   = vac['to_qd'].toString('dd MMM yyyy')
                name     = vac.get('name', '')
                is_secondary = vac.get('source') == 'secondary'
                if is_secondary:
                    cal_name = vac.get('calendar_name') or vac.get('secondary_calendar', 'Regional Holiday Calendar')
                    tip = f"<b>{name}</b><br>{from_str} – {to_str}<br><i>Source: {cal_name}</i>"
                else:
                    if from_str == to_str:
                        tip = f"<b>{name}</b><br>{from_str}"
                    else:
                        tip = f"<b>{name}</b><br>{from_str} – {to_str}"
                QToolTip.showText(ev.globalPos(), tip, self)
            else:
                QToolTip.hideText()
                ev.ignore()
            return True
        return super().event(ev)

    def mouseMoveEvent(self, event):
        x, y = event.x(), event.y()
        if not self._is_dragging or self._drag_task is None:
            # Cursor hint when not dragging
            bar = self._hit_bar(x, y)
            if bar:
                self.setCursor(Qt.SizeAllCursor)
            elif self._hit_vacation(x, y):
                self.setCursor(Qt.PointingHandCursor)  # indicates double-click opens info
            else:
                self.setCursor(Qt.ArrowCursor)
            return

        dx = x - self._drag_start_x
        if self.day_width >= HOUR_MODE_THRESHOLD:
            self._drag_delta_hours = int(dx / self.day_width)
            self._drag_delta = 0
        else:
            self._drag_delta = int(dx / self.day_width)
            self._drag_delta_hours = 0
        # Segment drags may change rows (to reassign a segment to another resource)
        row = self._y_to_row(y)
        self._drag_target_row = row
        # Cursor feedback: forbidden when drop would land on a vacation block
        if self._drag_blocked_by_vacation():
            self.setCursor(Qt.ForbiddenCursor)
        else:
            self.setCursor(Qt.ClosedHandCursor)
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        if not self._is_dragging or self._drag_task is None:
            self._reset_drag()
            return

        task     = self._drag_task
        src_row  = self._drag_res_idx
        tgt_row  = self._drag_target_row
        seg_idx  = self._drag_segment_idx
        is_hourly = self.day_width >= HOUR_MODE_THRESHOLD
        delta    = self._drag_delta_hours if is_hourly else self._drag_delta

        self._reset_drag()

        # ── Per-segment drag ───────────────────────────────────────────
        if seg_idx >= 0 and not is_hourly:
            uid = self._uid_for_task(task)
            if uid is not None and uid in self._task_splits_ref:
                segs = list(self._task_splits_ref[uid])
                if 0 <= seg_idx < len(segs):
                    seg_s, seg_e = segs[seg_idx]
                    new_seg_s = seg_s.addDays(delta)
                    _nw = self._starts_on_non_working(new_seg_s)
                    # Non-working day check on segment start
                    if delta != 0 and _nw:
                        nw_result = self._ask_non_working_day(task, new_seg_s)
                        if nw_result is None:
                            return  # cancel
                        if nw_result == 'next':
                            shift_extra = new_seg_s.daysTo(self._next_working_day(new_seg_s))
                            new_seg_s = self._next_working_day(new_seg_s)
                            new_seg_e = seg_e.addDays(delta + shift_extra)
                        else:
                            new_seg_e = seg_e.addDays(delta)
                    else:
                        new_seg_e = seg_e.addDays(delta)
                    # Vacation block check — any overlap (start inside, end inside, or straddle)
                    if delta != 0 and 0 <= src_row < len(self._resources):
                        _res = self._resources[src_row]
                        _res_uid = None
                        try:
                            _res_uid = int(str(_res.getUniqueID()))
                        except Exception:
                            _res_uid = None
                        _res_blocks = self._vacations_by_res.get(_res_uid, []) if _res_uid is not None else []
                        _seg_dur = new_seg_s.daysTo(new_seg_e)
                        for _vac in _res_blocks:
                            if new_seg_s <= _vac['to_qd'] and new_seg_e >= _vac['from_qd']:
                                nw_result = self._ask_non_working_day(task, new_seg_s)
                                if nw_result is None:
                                    return  # cancel
                                if nw_result == 'next':
                                    # advance past the entire vacation block, then skip non-working days
                                    new_seg_s = _vac['to_qd'].addDays(1)
                                    while self._starts_on_non_working(new_seg_s):
                                        new_seg_s = new_seg_s.addDays(1)
                                    new_seg_e = new_seg_s.addDays(_seg_dur)
                                # 'move' → keep new_seg_s as-is (user chose to move anyway)
                                break
                    # Segment overlap guard — prevent seg from crossing adjacent segs
                    overlaps = any(
                        j != seg_idx
                        and new_seg_s <= segs[j][1]
                        and new_seg_e >= segs[j][0]
                        for j in range(len(segs))
                    )
                    if overlaps:
                        task_name = str(task.getName()) if task.getName() else "Task"
                        dlg = _SegmentMergeDialog(task_name, self)
                        dlg.exec_()
                        if dlg.choice() == _SegmentMergeDialog.MERGE:
                            del self._task_splits_ref[uid]
                            self.task_rescheduled.emit(task, 0)
                        return
                    segs[seg_idx] = (new_seg_s, new_seg_e)
                    self._task_splits_ref[uid] = segs

            # Cross-row segment drag → reassign the whole task to target resource
            if src_row != tgt_row and tgt_row >= 0 and tgt_row < len(self._resources):
                old_res = self._resources[src_row]
                new_res = self._resources[tgt_row]
                placement = self._ask_placement(task, new_res,
                                                _to_qdate(task.getStart()), tgt_row)
                if placement is None:
                    return
                self.task_reassigned.emit(task, old_res, new_res, placement)

            self.task_rescheduled.emit(task, 0)  # delta=0 → reload without shifting task dates
            return

        if tgt_row < 0 and 0 <= src_row < len(self._resources):
            # Dragged off the resource rows → unassign
            old_res = self._resources[src_row]
            self.task_reassigned.emit(task, old_res, None, 'unassign')
        elif src_row != tgt_row and tgt_row >= 0 and tgt_row < len(self._resources):
            # Bar dragged to a different resource row (reassign + optional reschedule)
            start_qd  = _to_qdate(task.getStart())
            finish_qd = _to_qdate(task.getFinish())
            if not is_hourly:
                chk_start = start_qd.addDays(delta) if start_qd else start_qd
                chk_end   = finish_qd.addDays(delta) if finish_qd else (
                    chk_start.addDays(1) if chk_start else None)
            else:
                chk_start = start_qd
                chk_end   = finish_qd.addDays(1) if finish_qd else (chk_start.addDays(1) if chk_start else None)
            # Non-working day check (before vacation check)
            if chk_start and not is_hourly and self._starts_on_non_working(chk_start):
                nw_result = self._ask_non_working_day(task, chk_start)
                if nw_result is None:
                    return
                if nw_result == 'next':
                    nwd = self._next_working_day(chk_start)
                    extra = chk_start.daysTo(nwd)
                    chk_start = nwd
                    chk_end   = chk_end.addDays(extra) if chk_end else chk_start.addDays(1)
                    delta += extra
            if chk_start and self._overlaps_vacation(tgt_row, chk_start,
                                                      chk_end or chk_start.addDays(1)):
                vac = self._get_overlapping_vacation(tgt_row, chk_start,
                                                     chk_end or chk_start.addDays(1))
                result = self._ask_vacation_split(task, vac, chk_start,
                                                  chk_end or chk_start.addDays(1), tgt_row)
                if not result:
                    return
                if result == 'split':
                    self._apply_vacation_split(task, vac, chk_start,
                                               chk_end or chk_start.addDays(1), tgt_row,
                                               delta, src_row,
                                               old_res=self._resources[src_row],
                                               new_res=self._resources[tgt_row],
                                               placement=None)
                    return
                if result == 'shift':
                    self._apply_shift_after_vacation(
                        task, vac, delta, src_row, tgt_row,
                        chk_start, chk_end or chk_start.addDays(1),
                        old_res=self._resources[src_row],
                        new_res=self._resources[tgt_row],
                        placement=None)
                    return
            old_res = self._resources[src_row]
            new_res = self._resources[tgt_row]
            drop_date = chk_start if delta != 0 else None
            placement = self._ask_placement(task, new_res,
                                            drop_date or _to_qdate(task.getStart()), tgt_row)
            if placement is None:
                return
            self.task_reassigned.emit(task, old_res, new_res, placement)
            if delta != 0:
                self.task_rescheduled.emit(task, delta)
        elif delta != 0:
            # Same row, horizontal-only drag (reschedule)
            start_qd  = _to_qdate(task.getStart())
            finish_qd = _to_qdate(task.getFinish())
            if not is_hourly and start_qd:
                new_start = start_qd.addDays(delta)
                new_end   = finish_qd.addDays(delta) if finish_qd else new_start.addDays(1)
                # Non-working day check (before vacation check)
                if self._starts_on_non_working(new_start):
                    nw_result = self._ask_non_working_day(task, new_start)
                    if nw_result is None:
                        return
                    if nw_result == 'next':
                        nwd   = self._next_working_day(new_start)
                        extra = new_start.daysTo(nwd)
                        new_start = nwd
                        new_end   = new_end.addDays(extra)
                        delta    += extra
                if self._overlaps_vacation(src_row, new_start, new_end):
                    vac = self._get_overlapping_vacation(src_row, new_start, new_end)
                    result = self._ask_vacation_split(task, vac, new_start, new_end, src_row)
                    if not result:
                        return
                    if result == 'split':
                        self._apply_vacation_split(task, vac, new_start, new_end,
                                                   src_row, delta, src_row,
                                                   old_res=None, new_res=None, placement=None)
                        return
                    if result == 'shift':
                        self._apply_shift_after_vacation(
                            task, vac, delta, src_row, src_row,
                            new_start, new_end,
                            old_res=None, new_res=None, placement=None)
                        return
            self.task_rescheduled.emit(task, delta)

    def _ask_placement(self, task, res, drop_date: QDate, row_idx: int) -> str | None:
        """Return 'serial', 'parallel', or None (cancel) for a placement choice."""
        res_uid = int(str(res.getUniqueID()))
        existing = self._tasks_by_res.get(res_uid, [])
        if not existing:
            return 'parallel'
        # Check overlap
        task_dur = 1
        try:
            dur = task.getDuration()
            if dur:
                task_dur = max(1, int(float(str(dur.getDuration()))))
        except Exception:
            pass
        drop_end = drop_date.addDays(task_dur) if drop_date else None
        overlaps = False
        if drop_date and drop_end:
            for t in existing:
                ts = _to_qdate(t.getStart())
                tf = _to_qdate(t.getFinish())
                if ts and tf:
                    if not (drop_end <= ts or drop_date >= tf):
                        overlaps = True
                        break
        if not overlaps:
            return 'parallel'
        res_name = str(res.getName()) if res.getName() else "resource"
        task_name = str(task.getName()) if task.getName() else "task"
        dlg = _PlacementDialog(task_name, res_name, self)
        dlg.exec_()
        if dlg.choice() == _PlacementDialog.CANCEL:
            return None
        return dlg.choice()

    def _starts_on_non_working(self, date: QDate) -> bool:
        """True when *date* is a weekend or a project non-working day.

        Checks weekends and the cached `_non_working` set first.  Falls
        back to a direct MPXJ calendar query when the cache is stale or empty.
        Positive results are written back to the cache.
        """
        if not date or not date.isValid():
            return False
        if date.dayOfWeek() in (6, 7):
            return True
        iso = date.toString(Qt.ISODate)
        if iso in self._non_working:
            return True
        # Fallback: query the MPXJ project calendar directly
        if self._project is not None:
            try:
                import java.time as _jtime  # type: ignore
                cal = self._project.getDefaultCalendar()
                if cal is not None:
                    ld = _jtime.LocalDate.of(date.year(), date.month(), date.day())
                    is_working = bool(cal.isWorkingDate(ld))
                    if not is_working:
                        self._non_working.add(iso)  # populate cache
                        return True
            except Exception:
                pass
        return False

    def _ask_non_working_day(self, task, date: QDate) -> str | None:
        """Show non-working-day dialog.  Returns: 'next' | 'move' | None."""
        task_name = str(task.getName()) if task.getName() else "Task"
        if date.dayOfWeek() == 6:
            day_label = f"Saturday {date.toString('dd MMM yyyy')}"
        elif date.dayOfWeek() == 7:
            day_label = f"Sunday {date.toString('dd MMM yyyy')}"
        else:
            day_label = date.toString('dddd dd MMM yyyy')  # public holiday
        dlg = _NonWorkingDayDialog(task_name, day_label, self)
        dlg.exec_()
        return dlg.choice() if dlg.result() == QDialog.Accepted else None

    def _next_working_day(self, date: QDate) -> QDate:
        """Advance *date* forward until it lands on a working day."""
        d = date
        while self._starts_on_non_working(d):
            d = d.addDays(1)
        return d

    def _ask_vacation_split(self, task, vac, new_start: QDate,
                            new_end: QDate, row_idx: int) -> str | None:
        """Show vacation-overlap dialog.  Returns: 'split' | 'shift' | 'move' | None."""
        task_name = str(task.getName()) if task.getName() else "Task"
        vac_name  = vac.get('name', 'vacation') if vac else 'vacation'
        vac_from  = vac['from_qd'].toString("dd MMM yyyy") if vac else ''
        vac_to    = vac['to_qd'].toString("dd MMM yyyy")   if vac else ''
        can_split = bool(vac and
                         vac['from_qd'] > new_start)  # vacation starts after task starts → seg1 has room
        dlg = _VacationSplitDialog(task_name, vac_name, vac_from, vac_to, can_split, self)
        dlg.exec_()
        result = dlg.choice() if dlg.result() == QDialog.Accepted else None
        self._last_vacation_action = result
        return result

    def _apply_vacation_split(self, task, vac, new_start: QDate, new_end: QDate,
                              row_idx: int, delta: int, src_row: int,
                              old_res, new_res, placement):
        """Move the task to [new_start, new_end] and split it around *vac*.

        Segment 1: new_start  … vac.from_qd - 1
        Segment 2: vac.to_qd + 1 … new_end

        Strategy: shift the MPXJ task dates here directly (instead of relying
        on the _on_task_rescheduled slot), write splits at *final* coords, then
        emit task_rescheduled(task, 0) which triggers a pure reload + history
        snapshot without any further date/split shifting.
        """
        vac_start  = vac['from_qd']
        vac_end    = vac['to_qd']
        seg1_end   = vac_start.addDays(-1)     # last day before vacation
        seg2_start = vac_end.addDays(1)         # first day after vacation
        # Skip weekends / non-working days at vacation boundary
        while self._starts_on_non_working(seg2_start):
            seg2_start = seg2_start.addDays(1)

        can_split  = seg1_end >= new_start   # vacation doesn't start on day 1
        uid = self._uid_for_task(task)

        # Compute seg2_end from remaining task working days.
        # Count working days in seg1 (new_start … seg1_end inclusive).
        def _working_days(from_qd: QDate, to_qd: QDate) -> int:
            n, d = 0, from_qd
            while d <= to_qd:
                if d.dayOfWeek() not in (6, 7) and d.toString(Qt.ISODate) not in self._non_working:
                    n += 1
                d = d.addDays(1)
            return n

        # Total task working-day duration from MPXJ (fall back to calendar span)
        total_wd = 0
        try:
            dur = task.getDuration()
            if dur:
                from net.sf.mpxj import TimeUnit  # type: ignore
                units = str(dur.getUnits())
                if 'DAY' in units.upper():
                    total_wd = max(1, round(float(str(dur.getDuration()))))
                else:
                    total_wd = max(1, round(float(str(dur.getDuration())) / 8))
        except Exception:
            pass
        if total_wd == 0:
            total_wd = _working_days(new_start, new_end)

        seg1_wd   = _working_days(new_start, seg1_end)
        seg2_wd   = max(1, total_wd - seg1_wd)

        # Walk forward from seg2_start to find seg2_end (seg2_wd working days)
        seg2_end, remaining, d = seg1_end, seg2_wd, seg2_start   # init
        remaining = seg2_wd
        d = seg2_start
        while remaining > 0:
            if d.dayOfWeek() not in (6, 7) and d.toString(Qt.ISODate) not in self._non_working:
                remaining -= 1
                if remaining == 0:
                    seg2_end = d
                    break
            d = d.addDays(1)

        # 1. Shift MPXJ task dates: start → new_start, finish → seg2_end.
        try:
            import jpype  # type: ignore
            _LDT = jpype.JClass('java.time.LocalDateTime')
            task.setStart(_LDT.of(
                new_start.year(), new_start.month(), new_start.day(), 9, 0, 0))
            task.setFinish(_LDT.of(
                seg2_end.year(), seg2_end.month(), seg2_end.day(), 17, 0, 0))
        except Exception as e:
            print(f"[TeamPlanner] vacation-split date shift error: {e}")

        # 2. Write splits at final coordinates.
        if can_split and uid is not None:
            self._task_splits_ref[uid] = [(new_start, seg1_end), (seg2_start, seg2_end)]

        # 3. delta=0 → _on_task_rescheduled just reloads + emits data_changed
        #    (no further date/split shifting).  History snapshot is taken there.
        self.task_rescheduled.emit(task, 0)

        # 4. Row reassignment (if cross-row drag).
        if new_res is not None and old_res is not None:
            self.task_reassigned.emit(task, old_res, new_res, placement or 'parallel')

    def _apply_shift_after_vacation(self, task, vac,
                                    delta: int, src_row: int, tgt_row: int,
                                    new_start: QDate, new_end: QDate,
                                    old_res, new_res, placement):
        """Move the task to start on the first working day after the vacation ends.

        Duration is preserved.  Shifts MPXJ dates directly, then emits
        task_rescheduled(task, 0) for a clean reload + history snapshot.
        """
        vac_end = vac['to_qd']
        shift_start = vac_end.addDays(1)
        while (shift_start.dayOfWeek() in (6, 7) or
               shift_start.toString(Qt.ISODate) in self._non_working):
            shift_start = shift_start.addDays(1)
        dur_days  = new_start.daysTo(new_end)   # preserve post-drag duration
        shift_end = shift_start.addDays(dur_days)
        try:
            import jpype  # type: ignore
            _LDT = jpype.JClass('java.time.LocalDateTime')
            task.setStart(_LDT.of(
                shift_start.year(), shift_start.month(), shift_start.day(), 9, 0, 0))
            task.setFinish(_LDT.of(
                shift_end.year(), shift_end.month(), shift_end.day(), 9, 0, 0))
        except Exception as e:
            print(f"[TeamPlanner] shift-after-vacation error: {e}")
        self.task_rescheduled.emit(task, 0)   # pure reload + data_changed
        if new_res is not None and old_res is not None:
            self.task_reassigned.emit(task, old_res, new_res, placement or 'parallel')

    def _reset_drag(self):
        self._drag_task         = None
        self._drag_is_chip      = False
        self._drag_res_idx      = -1
        self._drag_segment_idx  = -1
        self._drag_delta        = 0
        self._drag_delta_hours  = 0
        self._drag_target_row   = -1
        self._is_dragging       = False
        self.releaseMouse()
        self.setCursor(Qt.ArrowCursor)
        self.update()

    def mouseDoubleClickEvent(self, event):
        """Double-click on a task bar → task dialog; on vacation block → vacation info dialog."""
        if self._project is None:
            return
        x, y = event.x(), event.y()
        # Task bar takes priority
        bar = self._hit_bar(x, y)
        if bar is not None and not bar['is_chip']:
            task = bar['task']
            import sys, os
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
            try:
                from dialogs import TaskDialog  # type: ignore
                dlg = TaskDialog(task, self._project, self)
                from PyQt5.QtWidgets import QDialog  # type: ignore
                if dlg.exec_() == QDialog.Accepted:
                    dlg.apply_to_task()
                    self.task_rescheduled.emit(task, 0)  # signal 0-delta to trigger refresh
            except Exception as e:
                print(f"[TeamPlanner] dialog error: {e}")
            return
        # Vacation block: open read-only info dialog
        vb = self._hit_vacation(x, y)
        if vb is not None:
            res_idx  = vb['res_idx']
            res_name = self._res_names[res_idx] if res_idx < len(self._res_names) else ""
            dlg = _VacationDialog(vb['vac'], res_name, self)
            dlg.exec_()

    def contextMenuEvent(self, event):
        x, y = event.x(), event.y()
        bar = self._hit_bar(x, y)
        if bar is None:
            return
        task = bar['task']
        task_name = str(task.getName()) if task.getName() else "Task"
        menu = QMenu(self)
        if not bar['is_chip']:
            act_unassign   = menu.addAction(f"Unassign '{task_name}'")
            act_reschedule = menu.addAction(f"Move to start of today")
            # Split / Merge actions — delegate to the main window via parent chain
            menu.addSeparator()
            is_summary = False
            is_milestone = False
            try:
                is_summary  = bool(task.getSummary())
                is_milestone = bool(task.getMilestone())
            except Exception:
                pass
            act_split = act_merge = None
            if not is_summary and not is_milestone:
                menu.addSeparator()
                uid        = self._uid_for_task(task)
                has_splits = uid is not None and len(self._task_splits_ref.get(uid, [])) >= 2
                act_split = menu.addAction("Split Task\u2026")
                act_merge = menu.addAction("Merge Task Segments") if has_splits else None
            action = menu.exec_(event.globalPos())
            if action == act_unassign:
                res_idx = bar['res_idx']
                if 0 <= res_idx < len(self._resources):
                    old_res = self._resources[res_idx]
                    self.task_reassigned.emit(task, old_res, None, 'unassign')
            elif action == act_reschedule:
                today = QDate.currentDate()
                start = _to_qdate(task.getStart())
                if start:
                    delta = start.daysTo(today)
                    self.task_rescheduled.emit(task, delta)
            elif act_split and action == act_split:
                # Delegate to the main window's split_task_action via parent chain
                self._call_parent("split_task_for_task", task)
            elif act_merge and action == act_merge:
                self._call_parent("merge_task_for_task", task)
        else:
            menu.exec_(event.globalPos())

    def _call_parent(self, method: str, *args):
        """Walk up the parent chain to find and call a method on the main window."""
        w = self.parent()
        while w is not None:
            if hasattr(w, method):
                getattr(w, method)(*args)
                return
            try:
                w = w.parent()
            except Exception:
                break


# ---------------------------------------------------------------------------
# Unassigned Tasks Panel  (own vertical scroll, drag via grabMouse)
# ---------------------------------------------------------------------------

class _UnassignedPanel(QWidget):
    """Draws unassigned task chips in a grid with a dynamic column count.
    Each chip shows two lines: task name + duration estimate.
    Drag uses grabMouse so the drag can leave the widget area.
    Emits chip_drag_ended(task, global_x, global_y) on release.
    """

    chip_drag_started  = pyqtSignal(object)             # task — drag begins
    chip_drag_moved    = pyqtSignal(int, int)            # global_x, global_y
    chip_drag_ended    = pyqtSignal(object, int, int)   # task, global_x, global_y
    chip_double_clicked = pyqtSignal(object)             # task

    _LINE1_H = 16   # px for name line
    _LINE2_H = 14   # px for duration line
    _PAD_TOP  = 5   # top padding inside chip

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tasks:      list  = []
        self._bars:       list  = []
        self._dragging          = False
        self._drag_task         = None
        self._drag_off          = QPoint(0, 0)
        self._cols              = CHIP_COLS_MIN
        self.setMouseTracking(True)

    def set_unassigned(self, tasks: list):
        self._tasks = tasks
        self._update_height()
        self.update()

    def _cols_for_width(self) -> int:
        w = self.width()
        if w <= 0:
            return CHIP_COLS_MIN
        return max(1, (w - CHIP_PAD_H) // (CHIP_W + CHIP_PAD_H))

    def _update_height(self):
        self._cols = self._cols_for_width()
        n      = len(self._tasks)
        n_rows = max(1, (n + self._cols - 1) // self._cols)
        h      = CHIP_PAD_V + n_rows * (CHIP_H + CHIP_PAD_V)
        self.setMinimumHeight(h)
        self.setMaximumHeight(h)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_height()
        self.update()

    def _draw_chip(self, painter: QPainter, task, cx: int, cy: int,
                   font_name: QFont, fm_name, font_dur: QFont, fm_dur,
                   bg_color, opacity: float = 1.0):
        painter.setOpacity(opacity)
        painter.setBrush(QBrush(bg_color))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(cx, cy, CHIP_W, CHIP_H, 3, 3)
        # Line 1: name
        name  = str(task.getName() or "")
        label = fm_name.elidedText(name, Qt.ElideRight, CHIP_W - 8)
        painter.setFont(font_name)
        painter.setPen(_C_CHIP_TEXT)
        painter.setOpacity(opacity)
        painter.drawText(QRect(cx + 4, cy + self._PAD_TOP,
                               CHIP_W - 8, self._LINE1_H),
                         Qt.AlignVCenter | Qt.AlignLeft, label)
        # Line 2: duration
        dur = _chip_dur_str(task)
        if dur:
            painter.setFont(font_dur)
            painter.setPen(QColor(210, 235, 210))
            painter.drawText(QRect(cx + 4, cy + self._PAD_TOP + self._LINE1_H + 1,
                                   CHIP_W - 8, self._LINE2_H),
                             Qt.AlignVCenter | Qt.AlignLeft, dur)
        painter.setOpacity(1.0)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), _C_UNASSIGNED_BG)
        self._bars   = []
        font_name    = QFont("Segoe UI", 8)
        fm_name      = QFontMetrics(font_name)
        font_dur     = QFont("Segoe UI", 7)
        font_dur.setItalic(True)
        fm_dur       = QFontMetrics(font_dur)
        cols         = self._cols

        for i, task in enumerate(self._tasks):
            if self._dragging and task is self._drag_task:
                continue   # drawn as ghost
            col_i = i % cols
            row_i = i // cols
            cx    = col_i * (CHIP_W + CHIP_PAD_H) + CHIP_PAD_H
            cy    = CHIP_PAD_V + row_i * (CHIP_H + CHIP_PAD_V)
            self._draw_chip(painter, task, cx, cy,
                            font_name, fm_name, font_dur, fm_dur, _C_CHIP_NORMAL)
            self._bars.append({'task': task,
                               'x1': cx, 'x2': cx + CHIP_W,
                               'y1': cy, 'y2': cy + CHIP_H})

        # Ghost follows cursor while dragging
        if self._dragging and self._drag_task is not None:
            lpos = self.mapFromGlobal(QCursor.pos())
            gx   = lpos.x() - self._drag_off.x()
            gy   = lpos.y() - self._drag_off.y()
            painter.setPen(QPen(_C_SEPARATOR, 1, Qt.DashLine))
            self._draw_chip(painter, self._drag_task, gx, gy,
                            font_name, fm_name, font_dur, fm_dur,
                            _C_CHIP_DRAG, opacity=0.70)
        painter.end()

    def _hit_bar(self, x: int, y: int):
        for bar in reversed(self._bars):
            if bar['x1'] <= x <= bar['x2'] and bar['y1'] <= y <= bar['y2']:
                return bar
        return None

    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        bar = self._hit_bar(event.x(), event.y())
        if bar:
            self._drag_task = bar['task']
            self._drag_off  = QPoint(event.x() - bar['x1'], event.y() - bar['y1'])
            self._dragging  = True
            self.grabMouse()
            self.setCursor(Qt.ClosedHandCursor)
            self.update()
            self.chip_drag_started.emit(self._drag_task)

    def mouseMoveEvent(self, event):
        if self._dragging:
            gpos = self.mapToGlobal(event.pos())
            self.chip_drag_moved.emit(gpos.x(), gpos.y())
            self.update()
        else:
            bar = self._hit_bar(event.x(), event.y())
            self.setCursor(Qt.SizeAllCursor if bar else Qt.ArrowCursor)

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        if self._dragging:
            gpos            = self.mapToGlobal(event.pos())
            task            = self._drag_task
            self._dragging  = False
            self._drag_task = None
            self.releaseMouse()
            self.setCursor(Qt.ArrowCursor)
            self.update()
            if task is not None:
                self.chip_drag_ended.emit(task, gpos.x(), gpos.y())

    def mouseDoubleClickEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        bar = self._hit_bar(event.x(), event.y())
        if bar:
            self.chip_double_clicked.emit(bar['task'])


# ---------------------------------------------------------------------------
# Helper: scrollbar extent
# ---------------------------------------------------------------------------

def _get_sb_extent() -> int:
    """Return the platform vertical-scrollbar width in pixels."""
    from PyQt5.QtWidgets import QApplication  # type: ignore
    app = QApplication.instance()
    if app:
        return app.style().pixelMetric(QStyle.PM_ScrollBarExtent)
    return 17


# ---------------------------------------------------------------------------
# Public Team Planner View
# ---------------------------------------------------------------------------

class TeamPlannerView(QWidget):
    """Top-level Team Planner widget.

    Layout::

        nav_bar
        hdr_row:  col_corner | hdr_area(GanttHeader, H:Off V:Off) [stretch] | hdr_spacer
        body_row: res_area(_ResourcePane, H:Off V:Off) | rows_area(Canvas, H:Always V:Off) [stretch] | rows_vsb
        ua_frame: ua_label | ua_scroll(_UnassignedPanel, H:Off V:AsNeeded) [stretch]

    hdr_spacer.width == rows_vsb.width  →  hdr_area.viewport.width == rows_area.viewport.width
    →  H-scroll offsets are pixel-perfect between calendar header and task canvas.

    Scroll sync (absolute setValue — zero drift):
      rows_area H  →  hdr_area H          (unidirectional)
      rows_area V range  →  rows_vsb      (range sync)
      rows_vsb  ↔  rows_area V            (bidirectional, blockSignals)
      rows_area V  →  res_area V          (unidirectional)
    """

    data_changed           = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project = None
        sb_w = _get_sb_extent()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── navigation bar ────────────────────────────────────────────
        nav_bar = QFrame(self)
        nav_bar.setObjectName("GanttNavBar")
        nav_bar.setFixedHeight(NAV_BAR_HEIGHT)
        nav_bar.setStyleSheet(
            "QFrame { background:#EAF0FB; border-bottom:1px solid #B0C8E0; }"
            "QPushButton { background:#D0E0F8; border:1px solid #9BBAD8;"
            "              border-radius:3px; padding:1px 6px; font-size:11px; }"
            "QPushButton:hover { background:#B8D0F0; }"
        )
        nav_layout = QHBoxLayout(nav_bar)
        nav_layout.setContentsMargins(4, 0, 4, 0)
        nav_layout.setSpacing(4)
        self._nav_btn_today = QPushButton("◀ Today")
        self._nav_btn_today.setFixedHeight(20)
        self._nav_btn_today.clicked.connect(self._scroll_to_today)
        nav_layout.addWidget(self._nav_btn_today)
        nav_layout.addStretch(1)
        root.addWidget(nav_bar)

        # ── header row ────────────────────────────────────────────────
        # hdr_spacer mirrors rows_vsb width so hdr_area.viewport == rows_area.viewport
        hdr_row = QHBoxLayout()
        hdr_row.setContentsMargins(0, 0, 0, 0)
        hdr_row.setSpacing(0)

        self._col_header = QPushButton("Resource Name \u2195")
        self._col_header.setFixedSize(RESOURCE_COL_W, HEADER_HEIGHT)
        self._col_header.setObjectName("TeamPlannerColHeader")
        self._col_header.setStyleSheet(
            "QPushButton { background:#d2e4fc; color:#1a3f7a; font-weight:bold;"
            " border-bottom:2px solid #2b579a; border-right:1px solid #90b4d4;"
            " text-align:center; padding:0; }"
            "QPushButton:hover { background:#c4d8f8; }"
            "QPushButton:pressed { background:#b0c8f0; }"
        )
        self._col_header.setToolTip("Click to sort resources by name")
        self._sort_asc = True   # current sort direction
        self._col_header.clicked.connect(self._toggle_resource_sort)
        hdr_row.addWidget(self._col_header)

        self._gantt_header = GanttHeader(self)
        self._hour_header  = HourModeHeader(HEADER_HEIGHT, HEADER_MONTH_H, HEADER_WEEK_H)
        self._header_area  = QScrollArea()
        self._header_area.setWidget(self._gantt_header)
        self._header_area.setWidgetResizable(False)
        self._header_area.setFixedHeight(HEADER_HEIGHT)
        self._header_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._header_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._header_area.setFrameShape(QFrame.NoFrame)
        hdr_row.addWidget(self._header_area, 1)

        hdr_spacer = QWidget()
        hdr_spacer.setFixedWidth(sb_w)
        hdr_row.addWidget(hdr_spacer)
        root.addLayout(hdr_row)

        # ── body row ──────────────────────────────────────────────────
        body_row = QHBoxLayout()
        body_row.setContentsMargins(0, 0, 0, 0)
        body_row.setSpacing(0)

        self._res_pane = _ResourcePane()
        self._res_area = QScrollArea()
        self._res_area.setWidget(self._res_pane)
        self._res_area.setWidgetResizable(True)   # pane fills viewport; scroll via set_scroll_y
        self._res_area.setFixedWidth(RESOURCE_COL_W)
        self._res_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._res_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._res_area.setFrameShape(QFrame.NoFrame)
        body_row.addWidget(self._res_area)

        self.canvas     = TeamPlannerCanvas()
        self._rows_area = QScrollArea()
        self._rows_area.setWidget(self.canvas)
        self._rows_area.setWidgetResizable(False)
        # H:Always → scrollbar at bottom of rows area (above UA section).
        # V:Off    → no internal V scrollbar; rows_vsb widget handles it.
        self._rows_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self._rows_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._rows_area.setFrameShape(QFrame.NoFrame)
        body_row.addWidget(self._rows_area, 1)

        # External V scrollbar — same width as hdr_spacer so column widths match
        self._rows_vsb = QScrollBar(Qt.Vertical)
        self._rows_vsb.setFixedWidth(sb_w)
        body_row.addWidget(self._rows_vsb)
        # Forward wheel events from the frozen Resource Name pane to the canvas
        # scroll area so scroll gestures on the name column always move the
        # timeline rather than being silently consumed by the frozen pane.
        self._res_wheel_fwd = _WheelForwarder(self._rows_area.viewport(), self)
        self._res_area.viewport().installEventFilter(self._res_wheel_fwd)
        root.addLayout(body_row, 1)

        # ── unassigned section ────────────────────────────────────────
        ua_sep = QFrame()
        ua_sep.setFrameShape(QFrame.HLine)
        ua_sep.setFixedHeight(2)
        ua_sep.setStyleSheet("color: #2b579a;")
        root.addWidget(ua_sep)

        ua_row = QHBoxLayout()
        ua_row.setContentsMargins(0, 0, 0, 0)
        ua_row.setSpacing(0)

        self._ua_col_label = QLabel("Unassigned\nTasks\n(0)")
        self._ua_col_label.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        self._ua_col_label.setFixedWidth(RESOURCE_COL_W)
        self._ua_col_label.setStyleSheet(
            "background:#daeeda; color:#1a4a1a; font-weight:bold; font-size:10px;"
            "border-right:1px solid #90b4d4; padding:4px;"
        )
        ua_row.addWidget(self._ua_col_label)

        self._ua_panel  = _UnassignedPanel()
        self._ua_scroll = QScrollArea()
        self._ua_scroll.setWidget(self._ua_panel)
        self._ua_scroll.setWidgetResizable(True)   # panel width = viewport; height dynamic
        self._ua_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._ua_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._ua_scroll.setFrameShape(QFrame.NoFrame)
        ua_row.addWidget(self._ua_scroll, 1)

        ua_frame = QWidget()
        ua_frame.setFixedHeight(UA_SECTION_H)
        ua_frame.setLayout(ua_row)
        root.addWidget(ua_frame)

        # ── scroll sync ───────────────────────────────────────────────
        # H: rows_area drives header (unidirectional, absolute)
        self._rows_area.horizontalScrollBar().valueChanged.connect(
            self._header_area.horizontalScrollBar().setValue
        )
        # V range: rows_area internal bar range → external rows_vsb range
        self._rows_area.verticalScrollBar().rangeChanged.connect(
            self._rows_vsb.setRange
        )
        # V value: bidirectional rows_vsb ↔ rows_area.vsb (with blockSignals)
        self._rows_vsb.valueChanged.connect(self._on_rows_vsb_changed)
        self._rows_area.verticalScrollBar().valueChanged.connect(
            self._on_rows_area_v_changed
        )
        # V: keep resource name pane aligned via paint offset (bypasses QScrollArea internals)
        self._rows_vsb.valueChanged.connect(self._res_pane.set_scroll_y)

        # ── canvas / panel signals ────────────────────────────────────
        self.canvas.layout_changed.connect(self._res_pane.set_layout)
        self.canvas.layout_changed.connect(self._on_layout_changed_update_res_pane)
        self.canvas.conflicts_changed.connect(self._res_pane.set_conflicts)
        self.canvas.conflict_tooltips_changed.connect(self._res_pane.set_tooltips)
        self.canvas.unassigned_changed.connect(self._on_unassigned_changed)
        self._ua_panel.chip_drag_started.connect(self._on_chip_drag_started)
        self._ua_panel.chip_drag_moved.connect(self._on_chip_drag_moved)
        self._ua_panel.chip_drag_ended.connect(self._on_chip_drop)
        self._ua_panel.chip_double_clicked.connect(self._on_chip_dialog)

        self.canvas.task_rescheduled.connect(self._on_task_rescheduled)
        self.canvas.task_reassigned.connect(self._on_task_reassigned)
        self._res_pane.jump_to_task_requested.connect(self._on_res_pane_jump_to_task)
        self._res_pane.resource_double_clicked.connect(self._on_res_pane_resource_dbl_click)

    # ------------------------------------------------------------------ #
    # Scroll-sync helpers                                                 #
    # ------------------------------------------------------------------ #

    def _on_res_pane_jump_to_task(self, res_idx: int):
        """Scroll the team planner timeline to the first task of the given resource row."""
        c = self.canvas
        if not (0 <= res_idx < len(c._resources)):
            return
        res = c._resources[res_idx]
        res_uid = int(str(res.getUniqueID()))
        tasks = c._tasks_by_res.get(res_uid, [])
        if not tasks:
            return
        first_start = None
        for t in tasks:
            s = _to_qdate(t.getStart())
            if s and (first_start is None or s < first_start):
                first_start = s
        if first_start is not None:
            self._scroll_to_date_exact(first_start.addDays(-3))

    def _on_rows_vsb_changed(self, val: int):
        self._rows_area.verticalScrollBar().blockSignals(True)
        self._rows_area.verticalScrollBar().setValue(val)
        self._rows_area.verticalScrollBar().blockSignals(False)
        # _res_pane.set_scroll_y is connected directly to _rows_vsb.valueChanged
        # so no explicit call needed here.

    def _on_rows_area_v_changed(self, val: int):
        self._rows_vsb.blockSignals(True)
        self._rows_vsb.setValue(val)
        self._rows_vsb.blockSignals(False)
        # _rows_vsb signals were blocked so set_scroll_y wasn't triggered — do it explicitly.
        self._res_pane.set_scroll_y(val)

    def _on_unassigned_changed(self, tasks: list):
        """Update unassigned panel + counter label."""
        self._ua_panel.set_unassigned(tasks)
        n = len(tasks)
        self._ua_col_label.setText(f"Unassigned\nTasks\n({n})")

    def _on_layout_changed_update_res_pane(self, *_args):
        """Keep _res_pane's resource list in sync whenever the canvas layout changes."""
        self._res_pane.set_resources(list(self.canvas._resources))

    def _on_res_pane_resource_dbl_click(self, row_idx: int):
        """Open Resource Information dialog for the double-clicked resource row."""
        if self._project is None:
            return
        if not (0 <= row_idx < len(self.canvas._resources)):
            return
        res = self.canvas._resources[row_idx]
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
        try:
            from dialogs import ResourceDialog  # type: ignore
            from PyQt5.QtWidgets import QDialog  # type: ignore
            dlg = ResourceDialog(res, self._project, self)
            if dlg.exec_() == QDialog.Accepted:
                dlg.apply_to_resource()
                self.data_changed.emit()
                # Rebuild layout without scrolling back to today
                self.canvas._rebuild_layout()
                self.canvas._apply_size()
                self.canvas.update()
        except Exception as e:
            print(f"[TeamPlanner] resource dialog error: {e}")

    # ------------------------------------------------------------------ #
    # Public API                                                          #
    # ------------------------------------------------------------------ #

    def load_project(self, project, recompute_critical=False):
        prev_project = self._project
        self._project = project
        self.canvas.load_project(project, recompute_critical=recompute_critical)
        self._sync_header()
        # Scroll to project start so the beginning of the schedule is visible on initial load.
        # Only do this when switching to a different project (not on internal refreshes).
        if project is not None and project is not prev_project:
            from PyQt5.QtCore import QTimer  # type: ignore
            c = self.canvas
            if c.project_start:
                QTimer.singleShot(0, lambda t=c.project_start: self._scroll_to_date_exact(t))

    def set_zero_float_critical(self, value: bool):
        """Forward zero-float-is-critical setting to the canvas."""
        self.canvas.set_zero_float_critical(value)
        if self._project is not None:
            self.canvas.load_project(self._project, recompute_critical=True)
            self._sync_header()

    def set_day_width(self, dw: int):
        date = self._get_left_edge_date()
        self.canvas.set_day_width(dw)
        self._sync_header()
        if date is not None:
            self._scroll_to_date_exact(date)

    def _get_left_edge_date(self):
        """Return the QDate currently at the left edge of the visible rows area,
        or None if no project is loaded.  Used to preserve the viewport position
        across zoom and data-refresh operations."""
        c = self.canvas
        if c.project_start is None or c.day_width == 0:
            return None
        scroll_px = self._rows_area.horizontalScrollBar().value()
        if c.day_width >= HOUR_MODE_THRESHOLD:
            eff_span = 24 if c._show_off_hours else c._clock_day_span
            if eff_span == 0:
                return None
            wday_idx = int(scroll_px / (eff_span * c.day_width))
            d = c.project_start
            count = 0
            while count < wday_idx:
                d = d.addDays(1)
                if d.dayOfWeek() not in (6, 7):  # skip Sat/Sun
                    count += 1
            return d
        else:
            col = int(scroll_px / c.day_width)
            return _col_to_date(c.project_start, col, c.show_sundays)

    def _scroll_to_date_exact(self, qdate: QDate):
        """Scroll the rows area so that *qdate* appears at the left edge."""
        c = self.canvas
        if c.project_start is None:
            return
        if c.day_width >= HOUR_MODE_THRESHOLD:
            eff_span = 24 if c._show_off_hours else c._clock_day_span
            wday_idx = date_to_working_day_idx(qdate, c.project_start)
            px = max(0, wday_idx * eff_span * c.day_width)
        else:
            col = _date_to_col(c.project_start, qdate, c.show_sundays)
            px = max(0, col * c.day_width)
        self._rows_area.horizontalScrollBar().setValue(px)

    def set_show_sundays(self, val: bool):
        self.canvas.set_show_sundays(val)
        self._sync_header()

    def _sync_header(self):
        c = self.canvas
        if not c.project_start:
            return
        if c.day_width >= HOUR_MODE_THRESHOLD:
            eff_span = 24 if c._show_off_hours else c._clock_day_span
            # Configure BEFORE swapping to avoid transient size mismatch
            self._hour_header.configure(
                c.project_start, c.total_days, c.day_width,
                c._work_hour_start, eff_span, c._non_working_slots, label_width=0)
            if self._header_area.widget() is not self._hour_header:
                self._header_area.takeWidget()
                self._header_area.setWidget(self._hour_header)
        else:
            # Configure BEFORE swapping to avoid transient size mismatch
            self._gantt_header.configure(
                c.project_start, c.total_days, c.day_width,
                c.show_sundays, c._non_working)
            if self._header_area.widget() is not self._gantt_header:
                self._header_area.takeWidget()
                self._header_area.setWidget(self._gantt_header)
        # Re-sync header scroll position to canvas after any potential widget swap
        self._header_area.horizontalScrollBar().setValue(
            self._rows_area.horizontalScrollBar().value()
        )

    def set_show_off_hours(self, value: bool):
        self.canvas.set_show_off_hours(value)
        self._sync_header()

    # ------------------------------------------------------------------ #
    # Navigation                                                          #
    # ------------------------------------------------------------------ #

    def _scroll_to_today(self):
        c = self.canvas
        if not c.project_start:
            return
        today = QDate.currentDate()
        if c.day_width >= HOUR_MODE_THRESHOLD:
            eff_span = 24 if c._show_off_hours else c._clock_day_span
            wday_idx = date_to_working_day_idx(today, c.project_start)
            px = max(0, wday_idx * eff_span * c.day_width - 100)
        else:
            col = _date_to_col(c.project_start, today, c.show_sundays)
            px  = max(0, col * c.day_width - 100)
        self._rows_area.horizontalScrollBar().setValue(px)

    def _toggle_resource_sort(self):
        """Sort the resource rows alphabetically, toggling asc/desc on each click."""
        c = self.canvas
        if not c._resources:
            return
        # Build sorted index order
        pairs = list(enumerate(c._res_names))
        pairs.sort(key=lambda p: p[1].lower(), reverse=not self._sort_asc)
        self._sort_asc = not self._sort_asc
        arrow = "\u2191" if self._sort_asc else "\u2193"
        self._col_header.setText(f"Resource Name {arrow}")
        order = [p[0] for p in pairs]
        # Reorder all parallel resource data lists in the canvas
        c._resources  = [c._resources[i]  for i in order]
        c._res_names  = [c._res_names[i]   for i in order]
        old_tasks = dict(c._tasks_by_res)
        c._tasks_by_res = {}
        for res in c._resources:
            uid = int(str(res.getUniqueID()))
            c._tasks_by_res[uid] = old_tasks.get(uid, [])
        c._rebuild_layout()
        c._apply_size()
        c.update()
        c = self.canvas
        if not c.project_start:
            return
        today = QDate.currentDate()
        if c.day_width >= HOUR_MODE_THRESHOLD:
            eff_span = 24 if c._show_off_hours else c._clock_day_span
            wday_idx = date_to_working_day_idx(today, c.project_start)
            px = max(0, wday_idx * eff_span * c.day_width - 100)
        else:
            col = _date_to_col(c.project_start, today, c.show_sundays)
            px  = max(0, col * c.day_width - 100)
        self._rows_area.horizontalScrollBar().setValue(px)

    def _on_chip_dialog(self, task):
        """Open task info dialog for a double-clicked unassigned chip."""
        if self._project is None:
            return
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
        try:
            from dialogs import TaskDialog  # type: ignore
            from PyQt5.QtWidgets import QDialog  # type: ignore
            dlg = TaskDialog(task, self._project, self)
            if dlg.exec_() == QDialog.Accepted:
                dlg.apply_to_task()
                self._reload()
                self.data_changed.emit()
        except Exception as e:
            print(f"[TeamPlanner] chip dialog error: {e}")

    # ------------------------------------------------------------------ #
    # Chip drag live feedback                                             #
    # ------------------------------------------------------------------ #

    def _on_chip_drag_started(self, task):
        self.canvas.start_chip_drag(task)

    def _on_chip_drag_moved(self, gx: int, gy: int):
        """Translate global chip-drag position to canvas coords and update ghost."""
        viewport  = self._rows_area.viewport()
        vp_origin = viewport.mapToGlobal(QPoint(0, 0))
        if (vp_origin.x() <= gx < vp_origin.x() + viewport.width() and
                vp_origin.y() <= gy < vp_origin.y() + viewport.height()):
            canvas_x = (gx - vp_origin.x()) + self._rows_area.horizontalScrollBar().value()
            canvas_y = (gy - vp_origin.y()) + self._rows_area.verticalScrollBar().value()
            row_idx  = self.canvas._y_to_row(canvas_y)
            self.canvas.update_chip_drag(canvas_x, row_idx)
        else:
            self.canvas.update_chip_drag(0, -1)  # not over canvas → hide ghost

    # ------------------------------------------------------------------ #
    # Chip drop (from _UnassignedPanel into rows canvas)                 #
    # ------------------------------------------------------------------ #

    def _on_chip_drop(self, task, gx: int, gy: int):
        self.canvas.end_chip_drag()  # clear ghost before possible dialog
        """Chip released at global position (gx, gy) — assign if over rows area."""
        viewport  = self._rows_area.viewport()
        vp_origin = viewport.mapToGlobal(QPoint(0, 0))
        # Check the drop landed inside the rows viewport
        if not (vp_origin.x() <= gx < vp_origin.x() + viewport.width() and
                vp_origin.y() <= gy < vp_origin.y() + viewport.height()):
            return
        # Convert global → canvas coordinates
        canvas_x = (gx - vp_origin.x()) + self._rows_area.horizontalScrollBar().value()
        canvas_y = (gy - vp_origin.y()) + self._rows_area.verticalScrollBar().value()
        row_idx = self.canvas._y_to_row(canvas_y)
        if row_idx < 0 or row_idx >= len(self.canvas._resources):
            return
        new_res   = self.canvas._resources[row_idx]
        drop_date = self.canvas._x_to_date_local(canvas_x)
        drop_hour = self.canvas._x_to_hour_local(canvas_x)
        # Compute task end date from duration for vacation overlap check
        try:
            dur = task.getDuration()
            dur_val  = float(str(dur.getDuration())) if dur else 1.0
            unit_str = str(dur.getUnits()).upper() if dur and dur.getUnits() else "DAYS"
            if "HOUR" in unit_str:
                dur_val /= 8.0
            elif "WEEK" in unit_str:
                dur_val *= 5.0
            elif "MONTH" in unit_str:
                dur_val *= 20.0
            dur_days = max(1, int(round(dur_val)))
        except Exception:
            dur_days = 1
        drop_end = drop_date.addDays(dur_days)
        if self.canvas._overlaps_vacation(row_idx, drop_date, drop_end):
            return  # blocked: drop lands on a vacation block
        placement = self.canvas._ask_placement(task, new_res, drop_date, row_idx)
        if placement is None:
            return
        self._on_task_assigned(task, new_res, drop_date, placement, drop_hour=drop_hour)

    # ------------------------------------------------------------------ #
    # Canvas signal handlers                                              #
    # ------------------------------------------------------------------ #

    def _on_task_rescheduled(self, task, delta: int):
        if delta == 0:
            self._reload()
            self.data_changed.emit()
            return
        try:
            import jpype  # type: ignore
            old_start  = task.getStart()
            old_finish = task.getFinish()
            if self.canvas.is_hourly_mode():
                if old_start:
                    task.setStart(old_start.plusHours(delta))
                if old_finish:
                    task.setFinish(old_finish.plusHours(delta))
            else:
                if old_start:
                    task.setStart(old_start.plusDays(delta))
                if old_finish:
                    task.setFinish(old_finish.plusDays(delta))
        except Exception as e:
            print(f"[TeamPlanner] reschedule error: {e}")
        # Shift split segments (if any) by the same day delta so they stay
        # aligned with the moved task.
        if not self.canvas.is_hourly_mode() and delta != 0:
            uid = self.canvas._uid_for_task(task)
            if uid is not None and uid in self.canvas._task_splits_ref:
                segs = self.canvas._task_splits_ref[uid]
                self.canvas._task_splits_ref[uid] = [
                    (s.addDays(delta), e.addDays(delta)) for s, e in segs
                ]
        self._reload()
        self.data_changed.emit()

    def _on_task_reassigned(self, task, old_res, new_res, placement: str):
        try:
            for a in list(task.getResourceAssignments() or []):
                try:
                    a.remove()
                except Exception:
                    pass
            if new_res is not None and placement != 'unassign':
                task.addResourceAssignment(new_res)
                if placement == 'serial':
                    self._place_serial(task, new_res)
        except Exception as e:
            print(f"[TeamPlanner] reassign error: {e}")
        self._reload()
        self.data_changed.emit()

    def _on_task_assigned(self, task, new_res, drop_date: QDate, placement: str, drop_hour: int = 8):
        try:
            task.addResourceAssignment(new_res)
            if placement == 'serial':
                self._place_serial(task, new_res)
            else:
                self._place_at_date(task, drop_date, drop_hour=drop_hour)
        except Exception as e:
            print(f"[TeamPlanner] assign error: {e}")
        self._reload()
        self.data_changed.emit()

    def _place_serial(self, task, res):
        """Shift task to start after the last task on the resource's row."""
        c       = self.canvas
        res_uid = int(str(res.getUniqueID()))
        tasks   = c._tasks_by_res.get(res_uid, [])
        if not tasks:
            return
        last_finish = None
        for t in tasks:
            if t is task:
                continue
            f = _to_qdate(t.getFinish())
            if f:
                last_finish = f if last_finish is None else max(last_finish, f)
        if last_finish is None:
            return
        new_start = last_finish.addDays(1)
        while (new_start.dayOfWeek() in (6, 7) or
               new_start.toString(Qt.ISODate) in c._non_working):
            new_start = new_start.addDays(1)
        self._place_at_date(task, new_start)

    def _place_at_date(self, task, new_start: QDate, drop_hour: int = 8):
        """Set task start to new_start (at drop_hour); shift finish to preserve duration."""
        try:
            import jpype  # type: ignore
            old_start  = task.getStart()
            old_finish = task.getFinish()
            _LDT = jpype.JClass('java.time.LocalDateTime')
            ns   = _LDT.of(new_start.year(), new_start.month(), new_start.day(), drop_hour, 0, 0)
            task.setStart(ns)
            dur_days = None
            if old_start and old_finish:
                d = old_start.until(
                    old_finish,
                    jpype.JClass('java.time.temporal.ChronoUnit').DAYS
                )
                if d > 0:
                    dur_days = int(d)
            # If start/finish span less than one calendar day (e.g. same day with
            # different time components), fall back to the task's Duration property.
            if not dur_days:
                try:
                    dur = task.getDuration()
                    dv  = max(1, int(float(str(dur.getDuration())))) if dur else 1
                except Exception:
                    dv = 1
                dur_days = dv
            task.setFinish(ns.plusDays(dur_days))
        except Exception as e:
            print(f"[TeamPlanner] place_at_date error: {e}")

    def _reload(self):
        """Refresh canvas and header with current project data."""
        # Preserve the horizontal scroll position so the user's viewport stays
        # on the same date after the canvas is rebuilt.
        sb = self._rows_area.horizontalScrollBar()
        saved_x = sb.value()
        self.load_project(self._project, recompute_critical=True)
        from PyQt5.QtCore import QTimer  # type: ignore
        QTimer.singleShot(0, lambda: sb.setValue(saved_x))
