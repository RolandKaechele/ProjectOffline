# timeline_view.py - Timeline view for Project Offline
#
# Displays the project span as a fixed-height bar that always fills the full
# available width.  No scroll, no zoom — day width is computed automatically
# from the widget width on every resize.
# Tasks added to the timeline appear as labelled bars above the project bar.
# A green "Today" line marks the current date.
#
# Layout (fixed height, width = parent width):
#   ┌──────────────────────────────────────────────────────────────────┐
#   │  header  (GanttHeader – month / week columns)                    │
#   │  canvas  (_TimelineCanvas – project bar + task bars + today)     │
#   └──────────────────────────────────────────────────────────────────┘
#
# The view is NOT wired to any tab, toolbar, or menu at module-load time.
# Call TimelineView.load_project(project) to populate it and
# add_task() / remove_task() to manage which tasks appear on the bar.

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from PyQt5.QtWidgets import (  # type: ignore
    QWidget, QSizePolicy, QVBoxLayout, QApplication, QToolTip,
)
from PyQt5.QtGui import (  # type: ignore
    QPainter, QColor, QFont, QPen, QBrush, QFontMetrics, QPolygon,
)
from PyQt5.QtCore import Qt, QRect, QDate, QSize, QPoint, pyqtSignal  # type: ignore

from gantt_view import (  # type: ignore
    GanttHeader, _to_qdate, _get_non_working_dates,
    HEADER_HEIGHT,
)
from app_tabs import (  # type: ignore
    TAB_GANTT, TAB_TEAM_PLANNER, TAB_RESOURCE_USAGE, TAB_TASK_SHEET,
)

# ---------------------------------------------------------------------------
# Configuration arrays
# ---------------------------------------------------------------------------

# Views on which the timeline strip is displayed above the tab content.
# Uses TAB_* constants from app_tabs.py.  Edit this list to change the
# default set of views that show the timeline.
_VIEWS_SHOWING_TIMELINE: list = [TAB_GANTT, TAB_TEAM_PLANNER]

# Views whose right-click context menu gets "Add / Remove from Timeline" items.
# Uses TAB_* constants from app_tabs.py.
_SOURCE_VIEWS_WITH_CONTEXT_MENU: list = [TAB_GANTT, TAB_TASK_SHEET]

# ---------------------------------------------------------------------------
# Layout constants
# ---------------------------------------------------------------------------

# The view has a fixed total height; no scrollbars, no zoom controls.
ROW_H           = 56    # height of the project-bar area
PROJECT_BAR_H   = 24    # height of the main project span bar
PROJECT_BAR_Y   = (ROW_H - PROJECT_BAR_H) // 2

TASK_BAR_H      = 18    # height of a task bar
TASK_LANE_H     = TASK_BAR_H + 4
TASK_AREA_H     = 80    # pixels above the project bar for task lanes
TOTAL_CANVAS_H  = TASK_AREA_H + ROW_H
FIXED_HEIGHT    = HEADER_HEIGHT + TOTAL_CANVAS_H  # total widget height

# Colours
_C_BG              = QColor(245, 248, 252)
_C_WEEKEND         = QColor(222, 222, 222)
_C_GRID            = QColor(210, 220, 235)
_C_TODAY_LINE      = QColor(0, 168, 0)
_C_TODAY_BADGE_BG  = QColor(0, 168, 0)
_C_TODAY_BADGE_FG  = QColor(255, 255, 255)
_C_PROJECT_BAR_BG  = QColor(220, 220, 220)
_C_PROJECT_BAR_BDR = QColor(120, 120, 120)
_C_PROJECT_BAR_TXT = QColor(90, 90, 90)
_C_START_LABEL     = QColor(50, 50, 50)
_C_FINISH_LABEL    = QColor(50, 50, 50)
_C_TASK_BAR_BG     = QColor(46, 117, 182)
_C_TASK_BAR_BDR    = QColor(20, 70, 140)
_C_TASK_BAR_TXT    = QColor(255, 255, 255)
_C_TASK_BAR_COLORS = [
    QColor(46,  117, 182),   # blue
    QColor(84,  130,  53),   # green
    QColor(192,  80,  77),   # red
    QColor(118, 113, 113),   # grey
    QColor(255, 192,   0),   # yellow
    QColor(146,  57, 136),   # purple
]
_C_HEADER_BG         = QColor(210, 228, 252)
_C_MILESTONE_FILL    = QColor(120,   0, 200)   # purple diamond fill
_C_MILESTONE_BDR     = QColor( 70,   0, 130)   # darker border
_C_MILESTONE_TXT     = QColor( 50,  50,  50)   # label below diamond

MILESTONE_D         = 14   # half-diagonal of the diamond (total size = 2*D x 2*D)
MILESTONE_LABEL_GAP = 3    # gap between diamond bottom and label


# ---------------------------------------------------------------------------
# Internal data structure
# ---------------------------------------------------------------------------

class _TimelineTask:
    """Lightweight holder for a task pinned to the timeline."""

    def __init__(self, task_id: int, name: str, start: QDate, finish: QDate,
                 color: QColor | None = None):
        self.task_id = task_id
        self.name    = name
        self.start   = start
        self.finish  = finish
        self.color   = color


class _TimelineMilestone:
    """Lightweight holder for a milestone pinned to the timeline."""

    def __init__(self, milestone_id: int, name: str, date: QDate,
                 color: QColor | None = None):
        self.milestone_id = milestone_id
        self.name  = name
        self.date  = date
        self.color = color   # if None, _C_MILESTONE_FILL is used


# ---------------------------------------------------------------------------
# Canvas widget
# ---------------------------------------------------------------------------

class _TimelineCanvas(QWidget):
    """Draws the project span bar and all pinned task bars."""

    # Emitted when the user right-clicks a bar/diamond and chooses Remove.
    # (item_id: int, is_milestone: bool)
    remove_requested = pyqtSignal(int, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(TOTAL_CANVAS_H)
        self.setMouseTracking(True)

        # State
        self._project_start:  QDate | None = None
        self._project_finish: QDate | None = None
        self._total_days:     int          = 0
        self._day_width:      int          = 10   # kept in sync with GanttHeader
        self._non_working:    set          = set()
        self._tasks:          list[_TimelineTask]      = []
        self._milestones:     list[_TimelineMilestone] = []

    # ------------------------------------------------------------------
    # Public helpers called by TimelineView
    # ------------------------------------------------------------------

    def set_project(self, start: QDate | None, finish: QDate | None,
                    non_working: set):
        self._project_start  = start
        self._project_finish = finish
        self._non_working    = non_working
        self._total_days     = (start.daysTo(finish) + 1) if (start and finish) else 0
        self.update()

    def set_day_width(self, dw: int):
        """Keep canvas x-positions in sync with the GanttHeader."""
        self._day_width = max(1, dw)
        self.update()

    def set_tasks(self, tasks: list):
        self._tasks = tasks
        self.update()

    def set_milestones(self, milestones: list):
        self._milestones = milestones
        self.update()

    # ------------------------------------------------------------------
    # Geometry helpers  (proportional: span fills full widget width)
    # ------------------------------------------------------------------

    def _x_for_date(self, date: QDate) -> int:
        """Map a QDate to an x pixel coordinate, matching GanttHeader's column grid."""
        if self._project_start is None or self._total_days <= 0:
            return 0
        offset = self._project_start.daysTo(date)
        return offset * self._day_width

    # ------------------------------------------------------------------
    # Paint
    # ------------------------------------------------------------------

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)

        w = self.width()

        # Background
        painter.fillRect(0, 0, w, TOTAL_CANVAS_H, _C_BG)

        if self._project_start is None or self._project_finish is None:
            self._draw_empty_hint(painter, w)
            painter.end()
            return

        # Weekend columns
        self._draw_weekends(painter, w)

        # Task lanes (above project bar)
        self._draw_task_bars(painter)

        # Project bar (solid rect — must come before milestones)
        self._draw_project_bar(painter)

        # Milestones on top of the project bar
        self._draw_milestones(painter)

        # Today line
        self._draw_today_line(painter)

        painter.end()

    def _draw_empty_hint(self, painter: QPainter, w: int):
        painter.setPen(QColor(160, 160, 160))
        font = QFont("Segoe UI", 10)
        painter.setFont(font)
        painter.drawText(
            QRect(0, TASK_AREA_H, w, ROW_H),
            Qt.AlignCenter,
            "Add tasks with dates to the timeline",
        )

    def _draw_weekends(self, painter: QPainter, w: int):
        if self._project_start is None or self._total_days <= 0:
            return
        dw   = self._day_width
        date = self._project_start
        for i in range(self._total_days):
            dow = date.dayOfWeek()
            if dow in (6, 7) or date.toString(Qt.ISODate) in self._non_working:
                x     = i * dw
                day_w = max(1, dw)
                painter.fillRect(x, 0, day_w, TOTAL_CANVAS_H, _C_WEEKEND)
            date = date.addDays(1)

    def _draw_project_bar(self, painter: QPainter):
        if self._project_start is None or self._project_finish is None:
            return
        x1 = 0
        x2 = self.width()
        bar_y = TASK_AREA_H + PROJECT_BAR_Y
        bar_w = x2 - x1

        # Bar fill
        painter.setPen(QPen(_C_PROJECT_BAR_BDR, 1))
        painter.setBrush(QBrush(_C_PROJECT_BAR_BG))
        painter.drawRect(x1, bar_y, bar_w, PROJECT_BAR_H)

        # Placeholder text when no tasks are added
        if not self._tasks:
            painter.setPen(_C_PROJECT_BAR_TXT)
            font = QFont("Segoe UI", 9)
            painter.setFont(font)
            painter.drawText(
                QRect(x1, bar_y, bar_w, PROJECT_BAR_H),
                Qt.AlignCenter,
                "Add tasks with dates to the timeline",
            )

        # Start / Finish date labels below the bar, pinned to the edges
        label_y = bar_y + PROJECT_BAR_H + 2
        painter.setPen(_C_START_LABEL)
        painter.setFont(QFont("Segoe UI", 8))
        start_str  = f"Start  {self._project_start.toString('ddd dd.MM.yy')}"
        finish_str = f"Finish  {self._project_finish.toString('ddd dd.MM.yy')}"
        painter.drawText(QRect(x1 + 2, label_y, (x2 - x1) // 2, 18), Qt.AlignLeft  | Qt.AlignVCenter, start_str)
        painter.drawText(QRect(x1,     label_y, x2 - x1 - 2,  18), Qt.AlignRight | Qt.AlignVCenter, finish_str)

    def _draw_task_bars(self, painter: QPainter):
        if not self._tasks or self._project_start is None:
            return
        painter.setFont(QFont("Segoe UI", 8))

        # Assign lanes greedily (no overlap within a lane)
        lanes: list[list[_TimelineTask]] = []
        for task in self._tasks:
            placed = False
            for lane in lanes:
                # Check if task overlaps the last task in this lane
                last = lane[-1]
                if task.start > last.finish:
                    lane.append(task)
                    placed = True
                    break
            if not placed:
                lanes.append([task])

        color_count = len(_C_TASK_BAR_COLORS)
        for lane_idx, lane in enumerate(lanes):
            bar_y = TASK_AREA_H - (lane_idx + 1) * TASK_LANE_H - 2
            if bar_y < 0:
                bar_y = 0
            for task in lane:
                color_idx = self._tasks.index(task) % color_count
                color = task.color if task.color else _C_TASK_BAR_COLORS[color_idx]

                x1 = self._x_for_date(task.start)
                x2 = self._x_for_date(task.finish.addDays(1))
                bar_w = max(4, x2 - x1)

                # Bar fill
                painter.setPen(QPen(_C_TASK_BAR_BDR, 1))
                painter.setBrush(QBrush(color))
                painter.drawRect(x1, bar_y, bar_w, TASK_BAR_H)

                # Task name inside bar (elided)
                painter.setPen(_C_TASK_BAR_TXT)
                fm = painter.fontMetrics()
                text_rect = QRect(x1 + 3, bar_y, max(0, bar_w - 6), TASK_BAR_H)
                elided = fm.elidedText(task.name, Qt.ElideRight, text_rect.width())
                painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, elided)

    def _draw_milestones(self, painter: QPainter):
        if not self._milestones or self._project_start is None:
            return
        painter.setRenderHint(QPainter.Antialiasing, True)
        font = QFont("Segoe UI", 7)
        painter.setFont(font)
        fm = QFontMetrics(font)

        # Milestones sit on the project-bar row, centred vertically
        cx_y = TASK_AREA_H + PROJECT_BAR_Y + PROJECT_BAR_H // 2

        for ms in self._milestones:
            cx = self._x_for_date(ms.date)
            D  = MILESTONE_D
            fill   = ms.color if ms.color else _C_MILESTONE_FILL
            border = _C_MILESTONE_BDR

            # Diamond polygon
            diamond = QPolygon([
                QPoint(cx,     cx_y - D),
                QPoint(cx + D, cx_y),
                QPoint(cx,     cx_y + D),
                QPoint(cx - D, cx_y),
            ])
            painter.setBrush(QBrush(fill))
            painter.setPen(QPen(border, 1))
            painter.drawPolygon(diamond)

            # Label above the diamond (baseline sits just above the top point)
            label = fm.elidedText(ms.name, Qt.ElideRight, 120)
            lx = cx - fm.horizontalAdvance(label) // 2
            ly = cx_y - D - MILESTONE_LABEL_GAP  # baseline above top tip
            painter.setPen(_C_MILESTONE_TXT)
            painter.drawText(lx, ly, label)

        painter.setRenderHint(QPainter.Antialiasing, False)

    def _draw_today_line(self, painter: QPainter):
        today = QDate.currentDate()
        if self._project_start is None or self._total_days <= 0:
            return
        if today < self._project_start or (self._project_finish and today > self._project_finish):
            return

        x = self._x_for_date(today)

        # Vertical line
        painter.setPen(QPen(_C_TODAY_LINE, 2))
        painter.drawLine(x, 0, x, TOTAL_CANVAS_H)

        # "Today" badge
        badge_text = "Today"
        font = QFont("Segoe UI", 8, QFont.Bold)
        fm = QFontMetrics(font)
        badge_w = fm.horizontalAdvance(badge_text) + 10
        badge_h = fm.height() + 4
        badge_x = x - badge_w // 2
        badge_y = 0

        painter.setBrush(QBrush(_C_TODAY_BADGE_BG))
        painter.setPen(Qt.NoPen)
        painter.drawRect(badge_x, badge_y, badge_w, badge_h)
        painter.setPen(_C_TODAY_BADGE_FG)
        painter.setFont(font)
        painter.drawText(
            QRect(badge_x, badge_y, badge_w, badge_h),
            Qt.AlignCenter,
            badge_text,
        )

    # ------------------------------------------------------------------
    # Tooltip on hover
    # ------------------------------------------------------------------

    def mouseMoveEvent(self, event):
        if (not self._tasks and not self._milestones) or self._project_start is None:
            QToolTip.hideText()
            return
        pos = event.pos()

        # Check milestone diamonds first
        cx_y = TASK_AREA_H + PROJECT_BAR_Y + PROJECT_BAR_H // 2
        for ms in self._milestones:
            cx = self._x_for_date(ms.date)
            D  = MILESTONE_D
            hit = QRect(cx - D, cx_y - D, 2 * D, 2 * D)
            if hit.contains(pos):
                QToolTip.showText(
                    event.globalPos(),
                    f"{ms.name}\nDate: {ms.date.toString('dd MMM yyyy')}",
                    self,
                )
                return

        # Check task bars
        if not self._tasks:
            QToolTip.hideText()
            return
        # Search task bars (top lanes first)
        lanes: list[list[_TimelineTask]] = []
        for task in self._tasks:
            placed = False
            for lane in lanes:
                if task.start > lane[-1].finish:
                    lane.append(task)
                    placed = True
                    break
            if not placed:
                lanes.append([task])

        for lane_idx, lane in enumerate(lanes):
            bar_y = TASK_AREA_H - (lane_idx + 1) * TASK_LANE_H - 2
            for task in lane:
                x1 = self._x_for_date(task.start)
                x2 = self._x_for_date(task.finish.addDays(1))
                rect = QRect(x1, bar_y, x2 - x1, TASK_BAR_H)
                if rect.contains(pos):
                    tip = (
                        f"{task.name}\n"
                        f"Start:  {task.start.toString('dd MMM yyyy')}\n"
                        f"Finish: {task.finish.toString('dd MMM yyyy')}"
                    )
                    QToolTip.showText(event.globalPos(), tip, self)
                    return
        QToolTip.hideText()


    # ------------------------------------------------------------------
    # Right-click context menu (remove from timeline)
    # ------------------------------------------------------------------

    def contextMenuEvent(self, event):
        if self._project_start is None:
            return
        pos = event.pos()

        # Check milestone diamonds first
        cx_y = TASK_AREA_H + PROJECT_BAR_Y + PROJECT_BAR_H // 2
        for ms in self._milestones:
            cx = self._x_for_date(ms.date)
            D  = MILESTONE_D
            hit = QRect(cx - D, cx_y - D, 2 * D, 2 * D)
            if hit.contains(pos):
                from PyQt5.QtWidgets import QMenu  # type: ignore
                menu = QMenu(self)
                act  = menu.addAction(f"Remove '{ms.name}' from Timeline")
                if menu.exec_(event.globalPos()) == act:
                    self.remove_requested.emit(ms.milestone_id, True)
                return

        # Check task bars
        if not self._tasks:
            return
        lanes: list = []
        for task in self._tasks:
            placed = False
            for lane in lanes:
                if task.start > lane[-1].finish:
                    lane.append(task)
                    placed = True
                    break
            if not placed:
                lanes.append([task])
        for lane_idx, lane in enumerate(lanes):
            bar_y = TASK_AREA_H - (lane_idx + 1) * TASK_LANE_H - 2
            if bar_y < 0:
                bar_y = 0
            for task in lane:
                x1   = self._x_for_date(task.start)
                x2   = self._x_for_date(task.finish.addDays(1))
                rect = QRect(x1, bar_y, max(4, x2 - x1), TASK_BAR_H)
                if rect.contains(pos):
                    from PyQt5.QtWidgets import QMenu  # type: ignore
                    menu = QMenu(self)
                    act  = menu.addAction(f"Remove '{task.name}' from Timeline")
                    if menu.exec_(event.globalPos()) == act:
                        self.remove_requested.emit(task.task_id, False)
                    return


# ---------------------------------------------------------------------------
# Top-level view widget
# ---------------------------------------------------------------------------

class TimelineView(QWidget):
    """MS-Project-style timeline strip.

    Shows the project start-to-finish span as a horizontal bar with a date
    header.  Selected tasks can be pinned to the timeline via add_task().

    The view is self-contained and NOT connected to any tab or menu at
    construction time — the caller is responsible for embedding it.
    """

    data_changed = pyqtSignal()   # emitted when the task list is modified

    # Forwarded from _TimelineCanvas.remove_requested so external code only
    # needs to connect to one signal.  (item_id: int, is_milestone: bool)
    remove_from_canvas_requested = pyqtSignal(int, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project      = None
        self._non_working: set = set()
        self._proj_start:  QDate | None = None
        self._proj_finish: QDate | None = None

        # Ordered list of _TimelineTask objects visible on the bar
        self._timeline_tasks:      list[_TimelineTask]      = []
        self._timeline_milestones: list[_TimelineMilestone] = []

        self._build_ui()
        # Start collapsed (hidden); _set_collapsed(False) is called by
        # _update_timeline_visibility when the user enables the strip.
        self._fixed_h = FIXED_HEIGHT
        self.setMaximumHeight(0)
        self.setMinimumHeight(0)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        # Forward canvas remove-requests as a single top-level signal
        self._canvas.remove_requested.connect(self.remove_from_canvas_requested)

    def _set_collapsed(self, collapsed: bool):
        """Explicitly collapse or expand the strip within the parent layout.

        Always call this instead of setVisible() so that the height
        constraints stay in sync with the visibility flag.  This avoids
        race conditions with Qt's own internal show/hide calls that happen
        during window state changes (e.g. showMaximized).
        """
        if collapsed:
            self.setMaximumHeight(0)
            self.setMinimumHeight(0)
            self.setVisible(False)
        else:
            self.setMinimumHeight(self._fixed_h)
            self.setMaximumHeight(self._fixed_h)
            self.setVisible(True)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Header (month / day columns) — fills full width, redrawn on resize
        self._header = GanttHeader()
        self._header.setFixedHeight(HEADER_HEIGHT)
        root.addWidget(self._header)

        # Canvas — fills remaining fixed height
        self._canvas = _TimelineCanvas()
        self._canvas.setFixedHeight(TOTAL_CANVAS_H)
        root.addWidget(self._canvas)

    # ------------------------------------------------------------------
    # Project loading
    # ------------------------------------------------------------------

    def load_project(self, project):
        """Populate the timeline from an MPXJ project object.

        Clears any previously pinned tasks — call add_task() afterwards to
        re-pin tasks from the new project.
        """
        self._project = project
        self._timeline_tasks.clear()
        self._timeline_milestones.clear()

        if project is None:
            self._proj_start  = None
            self._proj_finish = None
            self._non_working = set()
            self._canvas.set_project(None, None, set())
            self._header.configure(project_start=None, total_days=90,
                                   day_width=10, show_sundays=True)
            self.data_changed.emit()
            return

        # Read project start / finish from properties
        self._proj_start  = self._read_project_start(project)
        self._proj_finish = self._read_project_finish(project)

        total_days = (
            self._proj_start.daysTo(self._proj_finish) + 1
            if self._proj_start and self._proj_finish else 0
        )
        self._non_working = (
            _get_non_working_dates(project, self._proj_start, total_days)
            if total_days > 0 else set()
        )
        self._canvas.set_project(
            self._proj_start,
            self._proj_finish,
            self._non_working,
        )
        self._sync_header()
        self.data_changed.emit()

    # ------------------------------------------------------------------
    # Add / remove tasks
    # ------------------------------------------------------------------

    def add_task(self, task) -> bool:
        """Pin a task to the timeline bar.

        Parameters
        ----------
        task:
            An MPXJ Task object (java proxy) with getName(), getID(),
            getStart(), and getFinish() methods.

        Returns
        -------
        bool
            True if the task was added; False if it was already present
            or its dates could not be read.
        """
        if task is None:
            return False

        # Resolve task id
        try:
            task_id = int(str(task.getID()))
        except Exception:
            return False

        # Prevent duplicates
        if any(t.task_id == task_id for t in self._timeline_tasks):
            return False

        # Resolve dates
        start  = _to_qdate(task.getStart())
        finish = _to_qdate(task.getFinish())
        if start is None or finish is None:
            return False
        if finish < start:
            finish = start

        try:
            name = str(task.getName()) if task.getName() is not None else f"Task {task_id}"
        except Exception:
            name = f"Task {task_id}"

        tl_task = _TimelineTask(task_id=task_id, name=name, start=start, finish=finish)
        self._timeline_tasks.append(tl_task)

        # Expand project bar if necessary
        self._maybe_expand_span(start, finish)
        self._canvas.set_tasks(list(self._timeline_tasks))
        self.data_changed.emit()
        return True

    def remove_task(self, task_id: int) -> bool:
        """Remove a pinned task by its integer ID. Returns True if found."""
        before = len(self._timeline_tasks)
        self._timeline_tasks = [t for t in self._timeline_tasks if t.task_id != task_id]
        if len(self._timeline_tasks) == before:
            return False
        self._canvas.set_tasks(list(self._timeline_tasks))
        self.data_changed.emit()
        return True

    def remove_all_tasks(self):
        """Remove every pinned task from the timeline bar."""
        self._timeline_tasks.clear()
        self._canvas.set_tasks([])
        self.data_changed.emit()

    def pinned_task_ids(self) -> list[int]:
        """Return the list of task IDs currently pinned to the timeline."""
        return [t.task_id for t in self._timeline_tasks]

    # ------------------------------------------------------------------
    # Add / remove milestones
    # ------------------------------------------------------------------

    def add_milestone(self, task) -> bool:
        """Pin a milestone diamond to the timeline bar.

        Parameters
        ----------
        task:
            An MPXJ Task object whose getMilestone() returns True.
            The diamond is placed at the task's start date.

        Returns
        -------
        bool
            True if the milestone was added; False if already present
            or its date could not be read.
        """
        if task is None:
            return False
        try:
            mid = int(str(task.getID()))
        except Exception:
            return False
        if any(m.milestone_id == mid for m in self._timeline_milestones):
            return False
        date = _to_qdate(task.getStart())
        if date is None:
            return False
        try:
            name = str(task.getName()) if task.getName() is not None else f"Milestone {mid}"
        except Exception:
            name = f"Milestone {mid}"
        ms = _TimelineMilestone(milestone_id=mid, name=name, date=date)
        self._timeline_milestones.append(ms)
        self._maybe_expand_span(date, date)
        self._canvas.set_milestones(list(self._timeline_milestones))
        self.data_changed.emit()
        return True

    def remove_milestone(self, milestone_id: int) -> bool:
        """Remove a pinned milestone by its integer ID. Returns True if found."""
        before = len(self._timeline_milestones)
        self._timeline_milestones = [m for m in self._timeline_milestones
                                     if m.milestone_id != milestone_id]
        if len(self._timeline_milestones) == before:
            return False
        self._canvas.set_milestones(list(self._timeline_milestones))
        self.data_changed.emit()
        return True

    def remove_all_milestones(self):
        """Remove every pinned milestone from the timeline bar."""
        self._timeline_milestones.clear()
        self._canvas.set_milestones([])
        self.data_changed.emit()

    def pinned_milestone_ids(self) -> list[int]:
        """Return the list of milestone IDs currently pinned to the timeline."""
        return [m.milestone_id for m in self._timeline_milestones]

    # ------------------------------------------------------------------
    # Date range
    # ------------------------------------------------------------------

    def set_date_range(self, start: QDate, finish: QDate, non_working: set | None = None):
        """Set the timeline date range without an MPXJ project object.

        Sufficient to make the view display a date header, project bar,
        and today line.  Previously pinned tasks are kept.
        """
        if not start.isValid() or not finish.isValid() or finish < start:
            return
        self._proj_start  = start
        self._proj_finish = finish
        self._non_working = non_working or set()
        self._canvas.set_project(start, finish, self._non_working)
        self._sync_header()
    # ------------------------------------------------------------------

    def _read_project_start(self, project) -> QDate | None:
        try:
            ps = project.getProjectProperties().getStartDate()
            if ps is not None and str(ps) not in ('null', 'None', ''):
                return _to_qdate(ps)
        except Exception:
            pass
        # Fall back: minimum task start
        try:
            dates = []
            for t in project.getTasks():
                if t.getName() is not None and str(t.getID()) != "0":
                    d = _to_qdate(t.getStart())
                    if d:
                        dates.append(d)
            if dates:
                return min(dates, key=lambda d: d.toJulianDay())
        except Exception:
            pass
        return None

    def _read_project_finish(self, project) -> QDate | None:
        try:
            pf = project.getProjectProperties().getFinishDate()
            if pf is not None and str(pf) not in ('null', 'None', ''):
                return _to_qdate(pf)
        except Exception:
            pass
        # Fall back: maximum task finish
        try:
            dates = []
            for t in project.getTasks():
                if t.getName() is not None and str(t.getID()) != "0":
                    d = _to_qdate(t.getFinish())
                    if d:
                        dates.append(d)
            if dates:
                return max(dates, key=lambda d: d.toJulianDay())
        except Exception:
            pass
        return None

    def _maybe_expand_span(self, start: QDate, finish: QDate):
        """Grow the displayed span to include a newly added task's dates."""
        changed = False
        if self._proj_start is None or start < self._proj_start:
            self._proj_start = start
            changed = True
        if self._proj_finish is None or finish > self._proj_finish:
            self._proj_finish = finish
            changed = True
        if changed:
            self._canvas.set_project(
                self._proj_start,
                self._proj_finish,
                self._non_working,
            )
            self._sync_header()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._sync_header()

    def _sync_header(self):
        """(Re-)configure the GanttHeader to fill the current widget width."""
        if not (self._proj_start and self._proj_finish):
            return
        w          = self.width()
        total_days = self._proj_start.daysTo(self._proj_finish) + 1
        # Integer day_width shared by header and canvas so their grids align
        day_width  = max(1, int(round(w / total_days))) if total_days > 0 else 1
        self._canvas.set_day_width(day_width)
        self._header.configure(
            project_start    = self._proj_start,
            total_days       = total_days,
            day_width        = day_width,
            show_sundays     = True,
            non_working_dates= self._non_working,
        )
        # Force header to occupy exactly the widget width (no scroll)
        self._header.setFixedWidth(w)

    # ------------------------------------------------------------------
    # Query helpers
    # ------------------------------------------------------------------

    def is_task_pinned(self, task_id: int) -> bool:
        """Return True if the given task ID is currently pinned."""
        return any(t.task_id == task_id for t in self._timeline_tasks)

    def is_milestone_pinned(self, milestone_id: int) -> bool:
        """Return True if the given milestone ID is currently pinned."""
        return any(m.milestone_id == milestone_id for m in self._timeline_milestones)

    # ------------------------------------------------------------------
    # Registration API
    # ------------------------------------------------------------------

    def register(self, main_window) -> None:
        """Wire this view's signals to *main_window*.

        The caller is responsible for embedding this widget into the layout
        before calling register().  This method only sets up signal/slot
        connections and stores a reference to the main window so that future
        callbacks can reach it.

        Expected methods on *main_window*:
            _on_timeline_data_changed()
            _on_timeline_remove_from_canvas(item_id: int, is_milestone: bool)
        """
        self._main_window = main_window
        self.data_changed.connect(main_window._on_timeline_data_changed)
        self.remove_from_canvas_requested.connect(
            main_window._on_timeline_remove_from_canvas
        )

    # ------------------------------------------------------------------
    # Export
    # ------------------------------------------------------------------

    def export_svg(self, path: str) -> None:
        """Render the full timeline strip (header + canvas) to an SVG file."""
        from PyQt5.QtSvg import QSvgGenerator  # type: ignore
        from PyQt5.QtCore import QSize, QRect, QPoint  # type: ignore
        from PyQt5.QtGui import QPainter  # type: ignore

        w = self.width()
        h = self.height()
        gen = QSvgGenerator()
        gen.setFileName(path)
        gen.setSize(QSize(w, h))
        gen.setViewBox(QRect(0, 0, w, h))
        gen.setTitle("Timeline View")
        painter = QPainter(gen)
        self._header.render(painter, QPoint(0, 0))
        self._canvas.render(painter, QPoint(0, HEADER_HEIGHT))
        painter.end()

    def export_plantuml(self, path: str) -> None:
        """Export pinned tasks and milestones as a @startgantt PlantUML file."""
        lines: list[str] = ["@startgantt", ""]
        if self._proj_start:
            lines.append(f"Project starts {self._proj_start.toString('yyyy-MM-dd')}")
            lines.append("")
        # Project Start boundary milestone — before all content
        if self._proj_start:
            lines.append(f"[Project Start] happens {self._proj_start.toString('yyyy-MM-dd')}")
            lines.append("")
        for task in self._timeline_tasks:
            safe_name = task.name.replace("[", "(").replace("]", ")")
            days = max(1, task.start.daysTo(task.finish) + 1)
            lines.append(f"[{safe_name}] lasts {days} days")
            lines.append(f"[{safe_name}] starts {task.start.toString('yyyy-MM-dd')}")
        if self._timeline_tasks and self._timeline_milestones:
            lines.append("")
        for ms in self._timeline_milestones:
            safe_name = ms.name.replace("[", "(").replace("]", ")")
            lines.append(f"[{safe_name}] happens {ms.date.toString('yyyy-MM-dd')}")
        # Project End boundary milestone — after all content
        if self._proj_finish:
            lines.append("")
            lines.append(f"[Project End] happens {self._proj_finish.toString('yyyy-MM-dd')}")
        lines.append("")
        lines.append("@endgantt")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

