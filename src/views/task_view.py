# task_view.py - Editable task list view
#
# Supports inline editing of task Name, Duration, and % Done.
# Right-click context menu and Delete key for insert/delete.
# Col 0: indicator column with MS Project style status icons:
#   â—† purple  = milestone         â— red    = critical
#   âš  amber   = >100% complete    ! orange = overdue
#   âš‘ blue    = has notes
# Emits data_changed signal when tasks are modified.

from PyQt5.QtWidgets import (  # type: ignore
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QMenu, QToolTip, QFrame,
    QStyledItemDelegate, QStyleOptionViewItem, QApplication, QStyle
)
from PyQt5.QtGui import QColor, QFont, QPixmap, QIcon, QPainter, QBrush, QPen, QPolygon, QCursor  # type: ignore
from PyQt5.QtCore import Qt, QObject, pyqtSignal, QDate, QPoint, QRect, QSize, QEvent, QMimeData  # type: ignore
from gantt_view import HEADER_HEIGHT, NAV_BAR_HEIGHT, _get_visible_tasks, _compute_critical_ids, _read_critical_ids  # keep task header in sync with calendar header

FROZEN_COL_WIDTH   = 76   # width of the frozen indicator column
INDENT_PX_PER_LEVEL = 12  # pixels of indentation per outline level (MS Project ≈ 10-12 px)


class _FrozenWheelForwarder(QObject):
    """Event filter installed on the frozen indicator overlay's viewport.
    Forwards every wheel event to the main TaskView viewport so that
    scroll gestures on the icon column are handled by the main table.
    This prevents the frozen overlay from scrolling vertically out of
    sync with the task rows (which would misalign icons with tasks)
    and from accepting any horizontal scroll gesture independently.
    """
    def __init__(self, main_viewport, parent=None):
        super().__init__(parent)
        self._target = main_viewport

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Wheel:
            QApplication.sendEvent(self._target, event)
            return True   # consume from frozen overlay
        return False


# ------------------------------------------------------------------ #
# Task Name delegate – pixel-based indentation (MS Project style)     #
# ------------------------------------------------------------------ #

class _TaskNameDelegate(QStyledItemDelegate):
    """Draws the Task Name cell with pixel indentation, bold for summaries,
    and a clickable collapse/expand triangle for summary tasks.
    Data roles on the Task Name item:
      UserRole   – outline_level (int)
      UserRole+1 – is_summary    (bool)
      UserRole+2 – task_id       (str)
      UserRole+3 – is_collapsed  (bool)
    """
    _TRI_W = 10   # triangle width (px)

    def paint(self, painter, option, index):
        outline_level = index.data(Qt.UserRole) or 1
        is_summary    = bool(index.data(Qt.UserRole + 1))
        is_collapsed  = bool(index.data(Qt.UserRole + 3))
        indent        = max(0, outline_level - 1) * INDENT_PX_PER_LEVEL

        # Standard background / selection highlight
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ""
        QApplication.style().drawControl(QStyle.CE_ItemViewItem, opt, painter)

        # Collapse/expand triangle for summary tasks
        if is_summary:
            tx = option.rect.left() + indent + 2
            cy = option.rect.center().y()
            painter.save()
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setBrush(QBrush(QColor(70, 70, 70)))
            painter.setPen(Qt.NoPen)
            if is_collapsed:
                # Right-pointing ►
                pts = QPolygon([QPoint(tx, cy - 5),
                                QPoint(tx + self._TRI_W, cy),
                                QPoint(tx, cy + 5)])
            else:
                # Down-pointing ▼
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
        if option.state & QStyle.State_Selected:
            painter.setPen(option.palette.highlightedText().color())
        else:
            painter.setPen(option.palette.text().color())
        painter.drawText(rect, Qt.AlignVCenter | Qt.AlignLeft,
                         painter.fontMetrics().elidedText(text, Qt.ElideRight, rect.width()))
        painter.restore()

    def editorEvent(self, event, model, option, index):
        if event.type() == QEvent.MouseButtonPress:
            is_summary = bool(index.data(Qt.UserRole + 1))
            task_id    = index.data(Qt.UserRole + 2)
            if is_summary and task_id:
                outline_level = index.data(Qt.UserRole) or 1
                indent = max(0, outline_level - 1) * INDENT_PX_PER_LEVEL
                # Click target: triangle zone
                tri_rect = QRect(option.rect.left() + indent, option.rect.top(),
                                 self._TRI_W + 6, option.rect.height())
                if tri_rect.contains(event.pos()):
                    view = self.parent()
                    if hasattr(view, '_toggle_collapse'):
                        view._toggle_collapse(task_id)
                    return True
        return False

    def sizeHint(self, option, index):
        return super().sizeHint(option, index)


# ------------------------------------------------------------------ #
# Progress-bar delegate – % Done column                               #
# ------------------------------------------------------------------ #

class _ProgressDelegate(QStyledItemDelegate):
    """Draws a coloured progress bar inside the % Done cell."""

    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ""
        QApplication.style().drawControl(QStyle.CE_ItemViewItem, opt, painter)

        raw = index.data(Qt.DisplayRole) or "0"
        try:
            pct = float(str(raw).replace("%", "").strip())
        except ValueError:
            pct = 0.0
        pct = max(0.0, pct)  # allow values > 100 (overdue / over-allocated)

        r = option.rect.adjusted(3, 5, -3, -5)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor("#B8CBE4"), 1))
        painter.setBrush(QBrush(QColor("#E8F0FB")))
        painter.drawRoundedRect(r, 2, 2)

        if pct > 0:
            if pct > 100:
                # Over 100 %: fill the entire bar in red
                fill_r = QRect(r.left(), r.top(), r.width(), r.height())
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(QColor("#C0392B")))
            else:
                fill_w = int(r.width() * pct / 100.0)
                fill_r = QRect(r.left(), r.top(), fill_w, r.height())
                painter.setPen(Qt.NoPen)
                if pct >= 100:
                    painter.setBrush(QBrush(QColor("#217346")))
                elif pct >= 50:
                    painter.setBrush(QBrush(QColor("#2B579A")))
                else:
                    painter.setBrush(QBrush(QColor("#70A0D0")))
            painter.drawRoundedRect(fill_r, 2, 2)

        label = f"{pct:.0f}%"
        # Use white text on dark fills (≥ 50 % bar covers the centre), dark text otherwise
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
        return QSize(max(sh.width(), 65), sh.height())


# ------------------------------------------------------------------ #
# Icon factory â€” all icons are 16Ã—16 pixmaps drawn with QPainter     #
# ------------------------------------------------------------------ #

def _make_icon(kind: str) -> QIcon:
    """
    kind: 'milestone' | 'overdue' | 'critical' | 'notes' | 'warning'
    Returns a 32x32 QIcon.
    """
    px = QPixmap(32, 32)
    px.fill(Qt.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing)

    if kind == "warning":          # amber triangle with !
        tri = QPolygon([QPoint(16, 1), QPoint(31, 30), QPoint(1, 30)])
        p.setBrush(QBrush(QColor(255, 195, 0)))
        p.setPen(QPen(QColor(160, 100, 0), 1))
        p.drawPolygon(tri)
        p.setPen(QPen(QColor(80, 50, 0), 1))
        p.setFont(QFont("Arial", 12, QFont.Bold))
        p.drawText(QRect(8, 9, 16, 17), Qt.AlignCenter, "!")

    elif kind == "milestone":      # purple diamond
        pts = [QPoint(16, 1), QPoint(31, 16), QPoint(16, 31), QPoint(1, 16)]
        p.setBrush(QBrush(QColor(120, 0, 200)))
        p.setPen(QPen(QColor(70, 0, 130), 1))
        p.drawPolygon(QPolygon(pts))

    elif kind == "critical":       # red filled circle
        p.setBrush(QBrush(QColor(210, 30, 30)))
        p.setPen(QPen(QColor(140, 0, 0), 1))
        p.drawEllipse(2, 2, 28, 28)

    elif kind == "notes":          # blue page
        p.setBrush(QBrush(QColor(0, 110, 220)))
        p.setPen(QPen(QColor(0, 70, 160), 1))
        p.drawRect(4, 1, 18, 29)
        p.setPen(QPen(QColor(180, 210, 255), 1))
        for y in (8, 13, 19, 24):
            p.drawLine(8, y, 20, y)
        # dog-ear
        p.setPen(QPen(QColor(0, 70, 160), 1))
        p.setBrush(QBrush(QColor(90, 160, 255)))
        p.drawPolygon(QPolygon([QPoint(16, 1), QPoint(23, 1), QPoint(23, 8)]))

    elif kind == "overdue":        # orange exclamation circle
        p.setBrush(QBrush(QColor(230, 100, 0)))
        p.setPen(Qt.NoPen)
        p.drawEllipse(2, 2, 28, 28)
        p.setPen(QPen(Qt.white, 2))
        p.drawLine(16, 8, 16, 21)
        p.drawPoint(16, 25)

    p.end()
    return QIcon(px)


def _make_combined_icon(kinds: list) -> QIcon:
    """Combine multiple 32x32 icons into one wide pixmap (32px each, 2px gap)."""
    if not kinds:
        return QIcon()
    if len(kinds) == 1:
        return _make_icon(kinds[0])
    gap = 2
    w = len(kinds) * 32 + (len(kinds) - 1) * gap
    px = QPixmap(w, 32)
    px.fill(Qt.transparent)
    p = QPainter(px)
    for i, kind in enumerate(kinds):
        src = _make_icon(kind).pixmap(32, 32)
        p.drawPixmap(i * (32 + gap), 0, src)
    p.end()
    return QIcon(px)


class TaskView(QTableWidget):
    data_changed      = pyqtSignal()
    task_reordered    = pyqtSignal()   # emitted after row drag-drop reorder
    selection_changed = pyqtSignal(bool)  # True when ≥1 row selected
    show_in_gantt     = pyqtSignal(object)  # emits java task to scroll Gantt to its bar
    # Emitted when the user toggles a task in/out of the timeline via context menu.
    # Payload is the java task object.  Connected by ui.py if TAB_GANTT is in
    # timeline_view._SOURCE_VIEWS_WITH_CONTEXT_MENU.
    timeline_toggle_requested = pyqtSignal(object)
    split_task_requested  = pyqtSignal(object)  # emits java task — open split dialog
    merge_task_requested  = pyqtSignal(object)  # emits java task — merge all segments

    #           0            1     2            3           4       5               6               7         8
    COLUMNS = ["", "ID", "Task Name", "Duration", "Start", "Finish", "Predecessors", "% Done", "Resources"]
    EDITABLE_COLS = {2, 3, 7}  # Task Name, Duration, % Done

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project = None
        self._java_tasks = []
        self._critical_ids: set = set()   # int IDs on current critical path
        self._float_data: dict = {}            # task_id -> float info from CPM
        self._collapsed_ids: set = set()   # IDs (str) of collapsed summary tasks
        self._zero_float_critical: bool = False  # when True, zero-float tasks are critical
        self._id_to_name: dict = {}        # int(task_id) -> name, for predecessor labels

        self.setColumnCount(len(self.COLUMNS))
        self.setHorizontalHeaderLabels(self.COLUMNS)
        self.horizontalHeader().setMinimumHeight(HEADER_HEIGHT + NAV_BAR_HEIGHT)
        # Indicator col (wide enough for up to 2 side-by-side 32px icons)
        self.setColumnWidth(0, 76)
        self.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.setIconSize(QSize(32, 32))
        # ID col
        self.setColumnWidth(1, 40)
        self.horizontalHeader().setSectionResizeMode(1, QHeaderView.Interactive)
        # Task Name — interactive (user-resizable) with a generous default width
        self.setColumnWidth(2, 200)
        self.horizontalHeader().setSectionResizeMode(2, QHeaderView.Interactive)
        self.setItemDelegateForColumn(2, _TaskNameDelegate(self))
        self.setColumnWidth(3, 80)
        self.horizontalHeader().setSectionResizeMode(3, QHeaderView.Interactive)
        self.setColumnWidth(4, 110)
        self.horizontalHeader().setSectionResizeMode(4, QHeaderView.Interactive)
        self.setColumnWidth(5, 110)
        self.horizontalHeader().setSectionResizeMode(5, QHeaderView.Interactive)
        self.setColumnWidth(6, 220)
        self.horizontalHeader().setSectionResizeMode(6, QHeaderView.Interactive)
        self.setColumnWidth(7, 90)
        self.horizontalHeader().setSectionResizeMode(7, QHeaderView.Interactive)
        self.setItemDelegateForColumn(7, _ProgressDelegate(self))
        self.setColumnWidth(8, 140)
        self.horizontalHeader().setSectionResizeMode(8, QHeaderView.Interactive)

        self.setEditTriggers(QAbstractItemView.AnyKeyPressed)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setAlternatingRowColors(True)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(36)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self.itemChanged.connect(self._on_item_changed)
        self.cellDoubleClicked.connect(self._on_double_click)
        self.itemSelectionChanged.connect(self._on_selection_changed)
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self.viewport().installEventFilter(self)

        # --- Frozen indicator column ---
        # The frozen overlay sits directly on top of col 0 (covering its
        # header and all row cells). No viewport-margin tricks needed:
        # col 0 stays a real column so the header and content are naturally
        # aligned. The overlay is opaque, so it hides col 0 behind it.
        # As the user scrolls right, other columns scroll under the overlay.

        self._frozen = QTableWidget(0, 1, self)
        self._frozen.setHorizontalHeaderLabels([""])
        self._frozen.setColumnWidth(0, FROZEN_COL_WIDTH)
        self._frozen.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self._frozen.horizontalHeader().setMinimumHeight(HEADER_HEIGHT + NAV_BAR_HEIGHT)
        self._frozen.setIconSize(QSize(32, 32))
        self._frozen.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._frozen.setFocusPolicy(Qt.NoFocus)
        self._frozen.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._frozen.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._frozen.verticalHeader().setVisible(False)
        self._frozen.verticalHeader().setDefaultSectionSize(36)
        self._frozen.setSelectionMode(QAbstractItemView.NoSelection)
        self._frozen.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self._frozen.setFrameShape(QFrame.NoFrame)
        self._frozen.setStyleSheet(
            "QTableWidget { border-right: 2px solid #B8CBE4; background: #F5F7FA; }"
            "QHeaderView::section { background: #ECF3FB; border-right: 1px solid #B0C8E0;"
            "  border-bottom: 2px solid #2B579A; }"
        )
        # Clicking the frozen panel selects the corresponding main row
        self._frozen.cellPressed.connect(lambda r, c: self.selectRow(r))
        # Keep frozen in sync with main vertical scroll
        self.verticalScrollBar().valueChanged.connect(
            self._frozen.verticalScrollBar().setValue
        )
        # Forward all wheel events on the frozen overlay to the main viewport so
        # that scroll gestures on the icon column are handled by the main table.
        # This prevents the overlay from scrolling vertically out of sync (which
        # would misalign icons with task rows) or accepting horizontal gestures.
        self._frozen_wheel_fwd = _FrozenWheelForwarder(self.viewport(), self)
        self._frozen.viewport().installEventFilter(self._frozen_wheel_fwd)
        self._update_frozen_geometry()

        # --- Row drag-drop reordering ---
        # State
        self._row_drag_active  = False     # drag is in progress
        self._row_drag_src     = -1        # source row
        self._row_drag_press_y = 0         # mouse Y at press
        self._drop_row         = -1        # target row index (-1 = end of list)
        self._drop_mode        = 'between' # 'between' or 'child'

        # Visual drop indicator: 2-px blue line (between) or 1-px highlight border
        self._drop_line = QFrame(self.viewport())
        self._drop_line.setFrameShape(QFrame.HLine)
        self._drop_line.setFixedHeight(2)
        self._drop_line.setStyleSheet("background-color: #0078D7; border: none;")
        self._drop_line.hide()

        # Two custom cursors
        self._cursor_between = Qt.SplitVCursor    # insert-between mode
        self._cursor_child   = Qt.PointingHandCursor  # make-child mode

    # ---------------------------------------------------------------- #
    # Frozen column geometry                                            #
    # ---------------------------------------------------------------- #

    def updateGeometries(self):
        super().updateGeometries()
        if hasattr(self, '_frozen'):
            self._update_frozen_geometry()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, '_frozen'):
            self._update_frozen_geometry()

    def _update_frozen_geometry(self):
        fw  = self.frameWidth()
        # Cover exactly col 0: from the top of the horizontal header down to
        # the bottom of the viewport (both header cell and row cells).
        hdr_h = self.horizontalHeader().height()
        vp_h  = self.viewport().height()
        self._frozen.setGeometry(
            fw,
            fw,
            FROZEN_COL_WIDTH,
            hdr_h + vp_h
        )
        self._frozen.raise_()

    # ---------------------------------------------------------------- #
    # Disable horizontal scrolling                                      #
    # ---------------------------------------------------------------- #

    def scrollContentsBy(self, dx, dy):
        """Lock out horizontal scrolling entirely so the task columns cannot
        drift out of alignment with the Gantt chart on the right. Vertical
        scrolling (dy) is forwarded normally.
        """
        super().scrollContentsBy(0, dy)

    # ---------------------------------------------------------------- #
    # Tooltip event filter (ensures tooltips fire on icon-only cells)  #
    # ---------------------------------------------------------------- #

    def eventFilter(self, obj, event):
        if obj is self.viewport():
            t = event.type()
            if t == QEvent.ToolTip:
                pos = event.pos()
                item = self.itemAt(pos)
                if item is not None:
                    tip = item.toolTip()
                    if tip:
                        QToolTip.showText(event.globalPos(), tip, self.viewport())
                        return True
                QToolTip.hideText()
                return True

            # ---- Row drag-drop ----
            if t == QEvent.MouseButtonPress and event.button() == Qt.LeftButton:
                row = self.rowAt(event.pos().y())
                if row >= 0 and self.state() != QAbstractItemView.EditingState:
                    self._row_drag_src     = row
                    self._row_drag_press_y = event.pos().y()
                    self._row_drag_active  = False
                    # Don't consume — allow normal selection too

            elif t == QEvent.MouseMove and self._row_drag_src >= 0:
                dy = abs(event.pos().y() - self._row_drag_press_y)
                if dy > 8:                     # hysteresis threshold
                    self._row_drag_active = True
                if self._row_drag_active:
                    drop_row, drop_mode = self._get_drop_info(event.pos().y())
                    self._drop_row  = drop_row
                    self._drop_mode = drop_mode
                    self._show_drop_indicator(drop_row, drop_mode)
                    cursor = self._cursor_child if drop_mode == 'child' else self._cursor_between
                    self.viewport().setCursor(QCursor(cursor))
                    return True

            elif t == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
                if self._row_drag_active and self._row_drag_src >= 0:
                    self._hide_drop_indicator()
                    self.viewport().unsetCursor()
                    self._apply_row_reorder(self._row_drag_src, self._drop_row, self._drop_mode)
                    self._row_drag_src    = -1
                    self._row_drag_active = False
                    self._drop_row        = -1
                    return True
                self._row_drag_src    = -1
                self._row_drag_active = False

        return super().eventFilter(obj, event)

    # ---------------------------------------------------------------- #
    # Row drag-drop helpers                                             #
    # ---------------------------------------------------------------- #

    def _get_drop_info(self, mouse_y: int):
        """Return (drop_row, mode) for a given viewport Y coordinate.

        mode='between': insert before drop_row (blue line indicator).
        mode='child'  : make the dragged task a child of drop_row.
        drop_row == -1 means append at end.
        """
        total_rows = self.rowCount()
        if total_rows == 0:
            return (-1, 'between')

        row = self.rowAt(mouse_y)          # correctly handles scroll offset
        if row < 0:
            return (-1, 'between')         # below last row → append

        row_top    = self.rowViewportPosition(row)
        row_h      = self.verticalHeader().defaultSectionSize()
        row_bottom = row_top + row_h
        zone       = row_h * 0.30

        if row_top + zone < mouse_y < row_bottom - zone:
            return (row, 'child')
        elif mouse_y <= (row_top + row_bottom) // 2:
            return (row, 'between')
        else:
            nxt = row + 1
            return (nxt if nxt < total_rows else -1, 'between')

    def _show_drop_indicator(self, drop_row: int, mode: str):
        row_h = self.verticalHeader().defaultSectionSize()
        vw    = self.viewport().width()

        if mode == 'between':
            if drop_row < 0:
                # Below all rows
                last = self.rowCount() - 1
                y = self.rowViewportPosition(last) + row_h - 1 if last >= 0 else 0
            else:
                y = self.rowViewportPosition(drop_row) - 1
            self._drop_line.setFixedHeight(2)
            self._drop_line.setGeometry(0, max(0, y), vw, 2)
            self._drop_line.setStyleSheet("background-color: #0078D7; border: none;")
        else:
            y = self.rowViewportPosition(drop_row)
            self._drop_line.setFixedHeight(row_h)
            self._drop_line.setGeometry(0, y, vw, row_h)
            self._drop_line.setStyleSheet(
                "background-color: rgba(0,120,215,30);"
                "border: 2px solid #0078D7;"
            )
        self._drop_line.show()
        self._drop_line.raise_()

    def _hide_drop_indicator(self):
        self._drop_line.hide()
        self._drop_line.setFixedHeight(2)
        self._drop_line.setStyleSheet("background-color: #0078D7; border: none;")

    def _reorder_mpxj_tasks(self, ordered_tasks: list) -> bool:
        """Write a new iteration order into the MPXJ TaskContainer via reflection.

        TaskContainer extends ListWithCallbacks (org.mpxj.ListWithCallbacks)
        which holds a 'm_list' field (java.util.List) as its backing store.
        We set that list's contents directly to reorder tasks.
        """
        try:
            import jpype  # type: ignore
            task_container = self._project.getTasks()
            # JClass() returns a Python type wrapper; getDeclaredField lives on
            # java.lang.Class instances.  Class.forName() gives us the real one.
            JavaClass = jpype.JClass('java.lang.Class')
            lwc_cls = JavaClass.forName('org.mpxj.ListWithCallbacks')
            field = lwc_cls.getDeclaredField('m_list')
            field.setAccessible(True)
            java_list = field.get(task_container)

            # Preserve root / null tasks (ID=0 or name=None) at the front
            root_tasks = [t for t in java_list
                          if t.getName() is None or str(t.getID()) == "0"]
            java_list.clear()
            for t in root_tasks:
                java_list.add(t)
            for t in ordered_tasks:
                java_list.add(t)
            return True

        except Exception as e:
            print(f"[WARN] _reorder_mpxj_tasks: {e}")
            import traceback; traceback.print_exc()
            return False

        except Exception as e:
            print(f"[WARN] _reorder_mpxj_tasks: {e}")
            import traceback; traceback.print_exc()
            return False

    def _apply_row_reorder(self, src_row: int, dst_row: int, mode: str):
        """Move src_row task to dst_row position with given indentation mode."""
        if self._project is None:
            return
        if src_row < 0 or src_row >= len(self._java_tasks):
            return
        if dst_row == src_row or (mode == 'between' and dst_row == src_row + 1):
            return  # no-op
        try:
            self._do_row_reorder(src_row, dst_row, mode)
        except BaseException as e:
            print(f"[WARN] row reorder ({type(e).__name__}): {e}")
            import traceback; traceback.print_exc()

    def _do_row_reorder(self, src_row: int, dst_row: int, mode: str):
        import jpype  # type: ignore
        src_task = self._java_tasks[src_row]

        # TaskContainer is Iterable<Task>, NOT a List — no get(int) method.
        all_tasks = [t for t in self._project.getTasks()
                     if t.getName() is not None and str(t.getID()) != "0"]

        src_idx = next((i for i, t in enumerate(all_tasks) if t == src_task), -1)
        if src_idx < 0:
            return

        # --- Determine insert position and new outline level ---
        if mode == 'child':
            if dst_row < 0 or dst_row >= len(self._java_tasks):
                return
            dst_task = self._java_tasks[dst_row]
            dst_idx  = next((i for i, t in enumerate(all_tasks) if t == dst_task), -1)
            if dst_idx < 0:
                return
            insert_idx = dst_idx + 1
            try:
                ol = dst_task.getOutlineLevel()
                new_level = int(str(ol or 1)) + 1
            except BaseException:
                new_level = 2
            # Do NOT call setSummary — it triggers MPXJ internal callbacks
            # that crash because the Java child-tree hasn't been updated yet.
            # The summary flag is recalculated automatically by MPXJ when
            # the outline-level structure is consistent.
        else:
            # 'between' mode
            if dst_row < 0 or dst_row >= len(self._java_tasks):
                insert_idx = len(all_tasks)
                ref_task   = self._java_tasks[-1] if self._java_tasks else None
            else:
                dst_task   = self._java_tasks[dst_row]
                dst_idx    = next((i for i, t in enumerate(all_tasks) if t == dst_task), len(all_tasks))
                insert_idx = dst_idx
                ref_task   = dst_task
            try:
                new_level = int(str(ref_task.getOutlineLevel() or 1)) if ref_task else 1
            except Exception:
                new_level = 1

        try:
            src_task.setOutlineLevel(jpype.JInt(new_level))
        except BaseException as e:
            print(f"[WARN] setOutlineLevel ({type(e).__name__}): {e}")

        # --- Reorder Python list and write back ---
        all_tasks.pop(src_idx)
        if insert_idx > src_idx:
            insert_idx -= 1
        if insert_idx == src_idx:
            return  # no actual change in position
        all_tasks.insert(insert_idx, src_task)

        self._reorder_mpxj_tasks(all_tasks)
        self._update_parent_dates()
        self._renumber_task_ids()
        self._reload()
        self.task_reordered.emit()

    def _update_parent_dates(self):
        """Recalculate each summary task's start/finish from its children.

        Does NOT use task.getChildTasks() — that reflects the pre-parse tree
        stored internally by MPXJ and is NOT updated when we reorder m_list.
        Instead we derive parent-child relationships from outline levels in
        the current m_list iteration order (the same order getVisible sees).
        """
        if self._project is None:
            return
        try:
            tasks = [t for t in self._project.getTasks()
                     if t.getName() is not None and str(t.getID()) != "0"]
            if not tasks:
                return

            # Read outline levels once
            levels = []
            for t in tasks:
                try:
                    ol = t.getOutlineLevel()
                    levels.append(int(str(ol)) if (ol is not None and str(ol) not in ('null', 'None', '')) else 1)
                except Exception:
                    levels.append(1)

            # Build children list per task index using outline level.
            # Parent of tasks[i] = nearest preceding task with a strictly lower level.
            children_of = [[] for _ in tasks]  # type: ignore
            for i in range(1, len(tasks)):
                for j in range(i - 1, -1, -1):
                    if levels[j] < levels[i]:
                        children_of[j].append(i)
                        break

            # Process in reverse order: leaves before parents, so nested
            # summaries (grandparent → parent → child) cascade correctly.
            for i in range(len(tasks) - 1, -1, -1):
                if not children_of[i]:
                    continue  # leaf — nothing to aggregate
                child_start_strs   = []
                child_finish_strs  = []
                child_start_objs   = []
                child_finish_objs  = []
                for ci in children_of[i]:
                    try:
                        s = tasks[ci].getStart()
                        if s is not None and str(s) not in ('null', 'None', ''):
                            child_start_strs.append(str(s))
                            child_start_objs.append(s)
                    except Exception:
                        pass
                    try:
                        f = tasks[ci].getFinish()
                        if f is not None and str(f) not in ('null', 'None', ''):
                            child_finish_strs.append(str(f))
                            child_finish_objs.append(f)
                    except Exception:
                        pass
                if not child_start_strs or not child_finish_strs:
                    continue
                # ISO strings are lexicographically sortable for same-century dates
                min_s = min(child_start_strs)
                max_f = max(child_finish_strs)
                s_obj = child_start_objs[child_start_strs.index(min_s)]
                f_obj = child_finish_objs[child_finish_strs.index(max_f)]
                try:
                    tasks[i].setStart(s_obj)
                    tasks[i].setFinish(f_obj)
                except Exception as e:
                    print(f"[WARN] _update_parent_dates set: {e}")
        except Exception as e:
            print(f"[WARN] _update_parent_dates: {e}")
            import traceback; traceback.print_exc()

    def _renumber_task_ids(self):
        """Assign sequential IDs (1, 2, 3…) to tasks in container iteration order."""
        if self._project is None:
            return
        try:
            seq = 1
            for t in self._project.getTasks():
                if t.getName() is not None and str(t.getID()) != "0":
                    import jpype  # type: ignore
                    t.setID(jpype.JInt(seq))
                    seq += 1
        except Exception as e:
            print(f"[WARN] renumber IDs: {e}")

    # ---------------------------------------------------------------- #
    # Load                                                              #
    # ---------------------------------------------------------------- #

    def set_zero_float_critical(self, value: bool):
        self._zero_float_critical = bool(value)

    def load_project(self, project):
        self.blockSignals(True)
        self._frozen.setRowCount(0)
        self._project = project
        self._java_tasks = []
        self._id_to_name = {}
        self.setRowCount(0)
        if project is not None:
            all_tasks = [t for t in project.getTasks()
                         if t.getName() is not None and str(t.getID()) != "0"]
            # Build id→name lookup for predecessor labels
            for t in all_tasks:
                try:
                    self._id_to_name[int(str(t.getID()))] = str(t.getName()) if t.getName() is not None else ""
                except Exception:
                    pass
            self._critical_ids, self._float_data = _compute_critical_ids(
                all_tasks, project,
                zero_float_critical=self._zero_float_critical,
                return_float_data=True,
            )
            tasks = _get_visible_tasks(all_tasks, self._collapsed_ids)
            self.setRowCount(len(tasks))
            self._frozen.setRowCount(len(tasks))
            for row, task in enumerate(tasks):
                self._java_tasks.append(task)
                self._fill_row(row, task)
        self.blockSignals(False)

    def _fill_row(self, row, task):
        task_id  = str(task.getID())                 if task.getID()                 is not None else ""
        name_raw = str(task.getName())               if task.getName()               is not None else ""

        # Outline level and summary flag — stored as UserRole data for the delegate
        outline_level = 1
        try:
            ol = task.getOutlineLevel()
            if ol is not None:
                outline_level = int(str(ol))
        except Exception:
            pass

        is_summary = False
        try:
            sv = task.getSummary()
            if sv is not None and str(sv) not in ('null', 'None', '') and bool(sv):
                # Only treat as summary if it actually has child tasks.
                # MPXJ sometimes sets getSummary()=true based on outline level
                # alone, which causes false collapse triangles on new leaf tasks.
                children = task.getChildTasks()
                is_summary = children is not None and children.size() > 0
        except Exception:
            pass

        duration = str(task.getDuration())           if task.getDuration()           is not None else ""
        start    = str(task.getStart())              if task.getStart()              is not None else ""
        finish   = str(task.getFinish())             if task.getFinish()             is not None else ""
        pct      = str(task.getPercentageComplete()) if task.getPercentageComplete() is not None else "0%"

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

        is_critical = int(task_id) in self._critical_ids if task_id else False

        # col 0: all applicable indicator icons + combined tooltip
        indicators = self._get_indicators(task, pct, finish, is_critical)
        ind_item = QTableWidgetItem()
        ind_item.setFlags(ind_item.flags() & ~Qt.ItemIsEditable)
        ind_item.setTextAlignment(Qt.AlignCenter)
        if indicators:
            kinds   = [k for k, _ in indicators]
            tooltip = "\n".join(t for _, t in indicators)
            ind_item.setIcon(_make_combined_icon(kinds))
            ind_item.setToolTip(tooltip)
        self.setItem(row, 0, ind_item)

        # Mirror col 0 into the frozen overlay (a QTableWidgetItem can only
        # belong to one table, so we create a fresh item with the same data)
        frozen_item = QTableWidgetItem()
        frozen_item.setFlags(frozen_item.flags() & ~Qt.ItemIsEditable)
        frozen_item.setTextAlignment(Qt.AlignCenter)
        if indicators:
            frozen_item.setIcon(_make_combined_icon([k for k, _ in indicators]))
            frozen_item.setToolTip("\n".join(t for _, t in indicators))
        self._frozen.setItem(row, 0, frozen_item)

        # cols 1-8: data
        res_names = ""
        try:
            assignments = task.getResourceAssignments()
            if assignments:
                names = []
                for ass in assignments:
                    res = ass.getResource()
                    if res and res.getName() is not None:
                        u = ass.getUnits()
                        u_pct = f" [{float(str(u)):.0f}%]" if u is not None else ""
                        names.append(str(res.getName()) + u_pct)
                res_names = ", ".join(names)
        except Exception:
            pass

        for col, val in enumerate([task_id, name_raw, duration, start, finish, pred_str, pct, res_names], start=1):
            item = QTableWidgetItem(val)
            if col not in self.EDITABLE_COLS:
                item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            if col == 2:
                # Delegate uses UserRole for indent, UserRole+1 for bold/summary,
                # UserRole+2 for task_id (collapse toggle), UserRole+3 for is_collapsed
                item.setData(Qt.UserRole,     outline_level)
                item.setData(Qt.UserRole + 1, is_summary)
                item.setData(Qt.UserRole + 2, task_id)
                item.setData(Qt.UserRole + 3, task_id in self._collapsed_ids)
            self.setItem(row, col, item)

    @staticmethod
    def _get_indicators(task, pct_str, finish_str, is_critical=False):
        """Return list of (icon_kind, tooltip) for ALL applicable statuses."""
        results = []

        # Milestone shown alone
        try:
            if task.getMilestone():
                return [("milestone", "Milestone")]
        except Exception:
            pass

        # Notes
        try:
            notes = task.getNotes()
            if notes and str(notes).strip():
                note_preview = str(notes).strip()[:80]
                results.append(("notes", f"Note: {note_preview}"))
        except Exception:
            pass

        # >100% complete
        try:
            pct_val = float(pct_str.replace("%", ""))
            if pct_val > 100:
                results.append(("warning", f"% Complete is over 100% ({pct_val:.0f}%)"))
        except Exception:
            pass

        # Overdue: finish datetime in the past and task not 100% done
        try:
            if finish_str and len(finish_str) >= 10:
                from datetime import datetime as _dt

                _pct_raw = task.getPercentageComplete()
                _pct_str = str(_pct_raw) if _pct_raw is not None else ''
                # JPype may return "100.0", "100", or "100%" depending on version
                try:
                    _pct_num = float(_pct_str.replace('%', '').strip())
                except Exception:
                    _pct_num = 0.0

                _raw = str(finish_str).replace(" ", "T")[:16]
                try:
                    finish_dt = _dt.fromisoformat(_raw)
                except Exception:
                    finish_dt = _dt.fromisoformat(str(finish_str)[:10])

                _is_past = finish_dt < _dt.now()

                # Note: intentionally do NOT gate on actualFinish being unset —
                # MPXJ auto-sets actualFinish when a task reaches 100%, and it
                # is not always cleared when the user reverts the percentage.
                if _pct_num < 100.0 and _is_past:
                    results.append(("overdue",
                        f"Task is overdue (due {finish_str[:16]},"
                        f" {_pct_num:.0f}% done)"))
        except Exception:
            pass

        # Critical path
        if is_critical:
            results.append(("critical", "Critical path task"))

        return results

    # ---------------------------------------------------------------- #
    # Edit callbacks                                                    #
    # ---------------------------------------------------------------- #

    def _on_item_changed(self, item):
        row, col = item.row(), item.column()
        if row < 0 or row >= len(self._java_tasks):
            return
        task = self._java_tasks[row]
        val = item.text().strip()
        try:
            if col == 2:   # Task Name
                task.setName(val)
            elif col == 3: # Duration
                self._set_duration(task, val)
            elif col == 7: # % Done
                pct_str = val.replace('%', '').strip()
                if pct_str:
                    from java.lang import Double  # type: ignore
                    task.setPercentageComplete(Double.valueOf(float(pct_str)))
        except Exception as e:
            print(f"[WARN] Task update: {e}")
        self.data_changed.emit()

    def _set_duration(self, task, val):
        try:
            from org.mpxj import Duration, TimeUnit  # type: ignore
            num_str = "".join(c for c in val if c.isdigit() or c == '.')
            if num_str:
                task.setDuration(Duration.getInstance(float(num_str), TimeUnit.DAYS))
        except Exception as e:
            print(f"[WARN] Duration: {e}")

    # ---------------------------------------------------------------- #
    # Add / Delete                                                      #
    # ---------------------------------------------------------------- #

    def _on_selection_changed(self):
        self.selection_changed.emit(bool(self.selectedIndexes()))

    def add_task(self):
        if self._project is None:
            return
        self.blockSignals(True)

        # Determine insertion point — snapshot BEFORE addTask() so new task
        # is never in the list. Also resolve ref_task and outline level now.
        sel_rows = sorted(set(i.row() for i in self.selectedIndexes()))
        insert_after_row = sel_rows[-1] if sel_rows else None
        outline_level = 1
        ref_uid = None   # UniqueID (int str) of the task we insert after
        existing_before = []
        if insert_after_row is not None and insert_after_row < len(self._java_tasks):
            ref_task = self._java_tasks[insert_after_row]
            try:
                ol = ref_task.getOutlineLevel()
                if ol is not None:
                    outline_level = int(str(ol))
            except Exception:
                pass
            try:
                uid = ref_task.getUniqueID()
                if uid is not None and str(uid) not in ('null', 'None', ''):
                    ref_uid = str(uid)
            except Exception:
                pass
            # Snapshot existing tasks in container order BEFORE we add the new one
            existing_before = [t for t in self._project.getTasks()
                               if t.getName() is not None and str(t.getID()) != "0"]

        try:
            import jpype  # type: ignore
            new_task = self._project.addTask()  # appended to end of container
            new_task.setName("New Task")
            new_task.setOutlineLevel(jpype.JInt(outline_level))
            # Set default start / duration / finish so cells aren't blank
            try:
                from org.mpxj import Duration, TimeUnit  # type: ignore
                from java.time import LocalDateTime       # type: ignore
                proj_start = None
                try:
                    ps = self._project.getProjectProperties().getStartDate()
                    if ps is not None and str(ps) not in ('null', 'None', ''):
                        proj_start = ps
                except Exception:
                    pass
                if proj_start is None:
                    proj_start = LocalDateTime.now().withHour(8).withMinute(0).withSecond(0).withNano(0)
                new_task.setStart(proj_start)
                new_task.setDuration(Duration.getInstance(1.0, TimeUnit.DAYS))
                new_task.setFinish(proj_start.plusDays(1))
                new_task.setPercentageComplete(0.0)
            except Exception as e:
                print(f"[WARN] Add task defaults: {e}")
            # If a row was selected, insert after it using the pre-snapshot list.
            # We compare by UniqueID to avoid JPype proxy identity issues.
            if ref_uid is not None and existing_before:
                ref_idx = next(
                    (i for i, t in enumerate(existing_before)
                     if str(t.getUniqueID()) == ref_uid),
                    -1
                )
                if ref_idx >= 0:
                    ordered = existing_before[:ref_idx + 1] + [new_task] + existing_before[ref_idx + 1:]
                else:
                    ordered = existing_before + [new_task]
                self._reorder_mpxj_tasks(ordered)
            # Renumber all IDs in container order
            self._renumber_task_ids()
        except Exception as e:
            print(f"[ERROR] Add task: {e}")
            self.blockSignals(False)
            return

        # Reload so row positions and IDs are correct
        new_uid = None
        try:
            uid = new_task.getUniqueID()
            if uid is not None and str(uid) not in ('null', 'None', ''):
                new_uid = str(uid)
        except Exception:
            pass
        self.blockSignals(False)
        self.load_project(self._project)
        # Find new task by UniqueID and select / start editing
        for r, t in enumerate(self._java_tasks):
            try:
                match = (new_uid is not None and str(t.getUniqueID()) == new_uid)
            except Exception:
                match = False
            if match:
                self.scrollTo(self.model().index(r, 2))
                self.selectRow(r)
                self.edit(self.model().index(r, 2))
                break
        self.data_changed.emit()

    def delete_selected_tasks(self):
        if self._project is None:
            return
        rows = sorted(set(i.row() for i in self.selectedIndexes()), reverse=True)
        if not rows:
            return
        self.blockSignals(True)
        for row in rows:
            if 0 <= row < len(self._java_tasks):
                try:
                    self._java_tasks[row].remove()
                except Exception as e:
                    print(f"[WARN] Remove task: {e}")
                self._java_tasks.pop(row)
                self.removeRow(row)
                self._frozen.removeRow(row)
        self._renumber_task_ids()
        self.blockSignals(False)
        self.data_changed.emit()

    # ---------------------------------------------------------------- #
    # Collapse / expand summary tasks                                   #
    # ---------------------------------------------------------------- #

    def get_collapsed_ids(self) -> set:
        return set(self._collapsed_ids)

    def _toggle_collapse(self, task_id: str):
        """Flip the collapsed state of a summary and redraw both panes."""
        if task_id in self._collapsed_ids:
            self._collapsed_ids.discard(task_id)
        else:
            self._collapsed_ids.add(task_id)
        self._reload()

    def _reload(self):
        """Rebuild the table from the current project (preserving collapse state)."""
        if self._project is not None:
            self.load_project(self._project)
        self.data_changed.emit()

    # ---------------------------------------------------------------- #
    # Context menu, double-click, keyboard                              #
    # ---------------------------------------------------------------- #

    def _show_context_menu(self, pos):
        n_sel = len(set(i.row() for i in self.selectedIndexes()))
        rows_sel = sorted(set(i.row() for i in self.selectedIndexes()))
        menu = QMenu(self)
        insert_act = menu.addAction("Insert Task")
        menu.addSeparator()
        del_act = menu.addAction(f"Delete Task{'s' if n_sel > 1 else ''}")
        del_act.setEnabled(n_sel > 0)
        # Show in Gantt: only available for a single selected task that has a start date
        show_gantt_act = None
        if n_sel == 1 and rows_sel:
            row = rows_sel[0]
            if 0 <= row < len(self._java_tasks) and self._java_tasks[row] is not None:
                menu.addSeparator()
                show_gantt_act = menu.addAction("Show in Gantt Chart")
        # Timeline toggle: only when ui.py has wired _timeline_is_pinned
        tl_act = None
        if (n_sel == 1 and rows_sel
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
                    if show_gantt_act is None:
                        menu.addSeparator()
                    tl_act = menu.addAction(
                        "Remove from Timeline" if in_tl else "Add to Timeline"
                    )
        # Split / Merge: only for a single non-summary, non-milestone task
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
                    menu.addSeparator()
                    split_act = menu.addAction("Split Task\u2026")
                    merge_act = menu.addAction("Merge Task Segments") if has_splits else None
        action = menu.exec_(self.mapToGlobal(pos))
        if action == insert_act:
            self.add_task()
        elif action == del_act:
            self.delete_selected_tasks()
        elif show_gantt_act and action == show_gantt_act:
            self.show_in_gantt.emit(self._java_tasks[rows_sel[0]])
        elif tl_act and action == tl_act:
            self.timeline_toggle_requested.emit(self._java_tasks[rows_sel[0]])
        elif split_act and action == split_act:
            self.split_task_requested.emit(self._java_tasks[rows_sel[0]])
        elif merge_act and action == merge_act:
            self.merge_task_requested.emit(self._java_tasks[rows_sel[0]])

    def _on_double_click(self, row, col):
        if row < 0 or row >= len(self._java_tasks):
            return
        task = self._java_tasks[row]
        import sys, os
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
        from dialogs import TaskDialog  # type: ignore
        tl = getattr(self, '_timeline_view_ref', None)
        dlg = TaskDialog(task, self._project, self,
                         timeline_view=tl,
                         critical_ids=self._critical_ids,
                         float_data=self._float_data,
                         task_jira_data={})
        if dlg.exec_() == dlg.Accepted:
            dlg.apply_to_task()
            self.blockSignals(True)
            self._fill_row(row, task)
            self.blockSignals(False)
            self.data_changed.emit()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Delete and self.state() != QAbstractItemView.EditingState:
            self.delete_selected_tasks()
        else:
            super().keyPressEvent(event)

