# ribbon.py - MS Project-style ribbon toolbar
#
# The ribbon consists of tab buttons (TASK | RESOURCE | REPORT | PROJECT | VIEW | FORMAT)
# at the top.  Below the tabs sits a panel area that swaps content when a tab is clicked.
# Each panel contains labelled button groups, matching the MS Project ribbon layout.

from PyQt5.QtWidgets import (  # type: ignore
    QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QToolButton,
    QLabel, QFrame, QSizePolicy, QAction, QComboBox, QMenu,
    QListWidget, QListWidgetItem, QStyledItemDelegate, QApplication,
    QStyle, QStyleOptionToolButton,
)
from PyQt5.QtCore import Qt, QSize, QEvent, pyqtSignal, QPoint  # type: ignore
from PyQt5.QtGui import QFontMetrics, QColor, QPainter, QPixmap  # type: ignore
import icons as _icons  # type: ignore
from app_tabs import (  # type: ignore
    TAB_GANTT, TAB_RESOURCES, TAB_DEPENDENCIES, TAB_BASELINE,
    TAB_TEAM_PLANNER, TAB_TASK_SHEET, TAB_RESOURCE_USAGE, TAB_CPM,
    RIBBON_BASELINE, RIBBON_VCS,
)

# Views where Split Task / Merge Task buttons are shown.
_SPLIT_TASK_VIEWS = (TAB_GANTT, TAB_TEAM_PLANNER)

# Currently visible _RibbonListPopup (at most one at a time).
_active_ribbon_popup: '_RibbonListPopup | None' = None


def _close_active_ribbon_popup() -> None:
    """Hide and deregister any visible _RibbonListPopup."""
    global _active_ribbon_popup
    if _active_ribbon_popup is not None and _active_ribbon_popup.isVisible():
        _active_ribbon_popup.hide()
    _active_ribbon_popup = None


# ---------------------------------------------------------------------------
# Approach D: QListWidget popup with two-line delegate
# ---------------------------------------------------------------------------

class _RibbonListDelegate(QStyledItemDelegate):
    """Paints each row as a large icon + bold title + small subtitle."""

    _ICON_SIZE  = 20
    _V_PAD      = 5
    _H_PAD      = 8
    _GAP        = 6   # gap between icon and text block

    _SEPARATOR_ROLE = Qt.UserRole + 3
    _SEPARATOR_H    = 9

    def sizeHint(self, option, index):
        if index.data(self._SEPARATOR_ROLE):
            return QSize(option.rect.width(), self._SEPARATOR_H)
        subtitle = index.data(Qt.UserRole + 1)
        fm_title = option.fontMetrics
        title_h  = fm_title.height()
        if subtitle:
            from PyQt5.QtGui import QFont  # type: ignore
            small = QFont(option.font)
            small.setPointSizeF(small.pointSizeF() * 0.85)
            sub_h = QFontMetrics(small).height()
            text_h = title_h + 2 + sub_h
        else:
            text_h = title_h
        row_h = max(self._ICON_SIZE, text_h) + self._V_PAD * 2
        return QSize(option.rect.width(), row_h)

    def paint(self, painter, option, index):
        if index.data(self._SEPARATOR_ROLE):
            painter.fillRect(option.rect, option.palette.base())
            y = option.rect.center().y()
            painter.setPen(QColor("#cccccc"))
            painter.drawLine(option.rect.left() + 8, y, option.rect.right() - 8, y)
            return

        is_disabled = not (index.flags() & Qt.ItemIsEnabled)

        # Populate option.icon / option.text / option.palette from the model
        self.initStyleOption(option, index)

        # Background
        if not is_disabled and option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())
        elif not is_disabled and option.state & QStyle.State_MouseOver:
            painter.fillRect(option.rect, QColor("#e8f4fd"))
        else:
            painter.fillRect(option.rect, option.palette.base())

        # Left accent bar on selection
        if not is_disabled and option.state & QStyle.State_Selected:
            accent = option.rect.adjusted(0, 0, -(option.rect.width() - 3), 0)
            painter.fillRect(accent, QColor("#2e75b6"))

        x = option.rect.left() + self._H_PAD
        cy = option.rect.center().y()

        # Icon — use option.icon (populated by initStyleOption).
        # Source icons are white-on-transparent (designed for the dark ribbon).
        # Recolor them to suit the popup's light background using compositing.
        icon = option.icon
        if not icon.isNull():
            pix = icon.pixmap(QSize(self._ICON_SIZE, self._ICON_SIZE))
            if not pix.isNull():
                if is_disabled:
                    icon_color = QColor("#aaaaaa")
                elif option.state & QStyle.State_Selected:
                    icon_color = option.palette.highlightedText().color()
                else:
                    icon_color = QColor("#2e75b6")
                recolored = QPixmap(pix.size())
                recolored.fill(Qt.transparent)
                rp = QPainter(recolored)
                rp.fillRect(recolored.rect(), icon_color)
                rp.setCompositionMode(QPainter.CompositionMode_DestinationIn)
                rp.drawPixmap(0, 0, pix)
                rp.end()
                painter.drawPixmap(x, cy - recolored.height() // 2, recolored)
        x += self._ICON_SIZE + self._GAP

        # Title and subtitle come from the model directly
        title    = index.data(Qt.DisplayRole) or ""
        subtitle = index.data(Qt.UserRole + 1) or ""

        painter.save()
        title_font = option.font
        title_font.setBold(True)
        painter.setFont(title_font)
        if is_disabled:
            painter.setPen(QColor("#aaaaaa"))
        elif option.state & QStyle.State_Selected:
            painter.setPen(option.palette.highlightedText().color())
        else:
            painter.setPen(option.palette.text().color())

        if subtitle:
            title_rect = option.rect.adjusted(x, self._V_PAD, -self._H_PAD, 0)
            title_rect.setHeight(QFontMetrics(title_font).height())
            painter.drawText(title_rect, Qt.AlignVCenter | Qt.AlignLeft, title)

            from PyQt5.QtGui import QFont  # type: ignore
            small = QFont(option.font)
            small.setPointSizeF(small.pointSizeF() * 0.85)
            painter.setFont(small)
            if is_disabled:
                painter.setPen(QColor("#cccccc"))
            elif not (option.state & QStyle.State_Selected):
                painter.setPen(QColor("#666666"))
            sub_rect = title_rect.translated(0, title_rect.height() + 2)
            sub_rect.setBottom(option.rect.bottom() - self._V_PAD)
            painter.drawText(sub_rect, Qt.AlignVCenter | Qt.AlignLeft, subtitle)
        else:
            text_rect = option.rect.adjusted(x, 0, -self._H_PAD, 0)
            painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, title)

        painter.restore()


class _RibbonListPopup(QFrame):
    """Floating QListWidget panel anchored below a ribbon QToolButton.

    Usage::

        popup = _RibbonListPopup(actions, parent=ribbon_widget)
        btn.clicked.connect(lambda: popup.show_below(btn))

    ``actions`` is a list of ``(label, callback)`` or
    ``(label, callback, icon)`` or ``(label, callback, icon, subtitle)``
    tuples.
    """

    def __init__(self, actions: list, parent=None):
        # Plain child widget — no separate OS window at all.
        # This avoids all Windows activation/focus-stealing issues:
        # clicking a tab or button outside needs exactly one click.
        # The widget is reparented to the top-level window on first show
        # so it can overlay the content area below the ribbon.
        super().__init__(parent)
        self.setObjectName("RibbonListPopup")
        self.hide()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(1, 1, 1, 1)
        layout.setSpacing(0)

        self._list = QListWidget()
        self._list.setObjectName("RibbonListPopup")
        self._list.setItemDelegate(_RibbonListDelegate(self._list))
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._list.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._list.setFrameShape(QFrame.NoFrame)
        self._list.setMouseTracking(True)
        self._list.setUniformItemSizes(False)
        layout.addWidget(self._list)

        self._callbacks: list = []
        for entry in actions:
            if entry is None:
                # Separator
                item = QListWidgetItem()
                item.setData(_RibbonListDelegate._SEPARATOR_ROLE, True)
                item.setFlags(Qt.NoItemFlags)
                self._list.addItem(item)
                continue

            label    = entry[0]
            cb       = entry[1]
            icon     = entry[2] if len(entry) > 2 else None
            subtitle = entry[3] if len(entry) > 3 else None

            item = QListWidgetItem(label)
            if icon is not None:
                item.setIcon(icon)
            if subtitle:
                item.setData(Qt.UserRole + 1, subtitle)
            item.setData(Qt.UserRole + 2, len(self._callbacks))
            self._list.addItem(item)
            self._callbacks.append(cb)

        # Auto-size width to longest item
        self._list.setMinimumWidth(220)
        self._list.setMaximumWidth(400)
        # Height: show all items without scroll when <= 10 entries
        self._list.setMaximumHeight(400)

        self._list.itemClicked.connect(self._on_item_clicked)
        self._list.itemActivated.connect(self._on_item_clicked)  # Enter key

    # ------------------------------------------------------------------
    # Child-widget popup: no OS window, so Qt.Popup auto-close is gone.
    # We install an app-level event filter while visible to detect outside
    # clicks and hide without consuming them.
    def showEvent(self, event):  # noqa: N802
        super().showEvent(event)
        QApplication.instance().installEventFilter(self)

    def hideEvent(self, event):  # noqa: N802
        super().hideEvent(event)
        QApplication.instance().removeEventFilter(self)

    def eventFilter(self, obj, event):  # noqa: N802
        t = event.type()
        if t in (QEvent.MouseButtonPress, QEvent.MouseButtonDblClick):
            # self.rect() is in local coordinates; map global click to local
            local = self.mapFromGlobal(event.globalPos())
            inside = self.rect().contains(local)
            if not inside:
                self.hide()
                return False   # do NOT consume – let click reach tab/button
        elif t == QEvent.ApplicationDeactivate:
            self.hide()
        return False

    # ------------------------------------------------------------------
    def set_item_enabled(self, label: str, enabled: bool, tooltip: str = "") -> None:
        """Enable or disable a menu item by its display label."""
        for i in range(self._list.count()):
            item = self._list.item(i)
            if item.data(Qt.DisplayRole) == label:
                if enabled:
                    item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                    item.setData(Qt.ToolTipRole, None)
                else:
                    item.setFlags(Qt.NoItemFlags)
                    item.setData(Qt.ToolTipRole, tooltip)
                self._list.viewport().update()
                break

    def _on_item_clicked(self, item: QListWidgetItem):
        if item.data(_RibbonListDelegate._SEPARATOR_ROLE):
            return
        if not (item.flags() & Qt.ItemIsEnabled):
            return
        idx = item.data(Qt.UserRole + 2)
        self.hide()
        if idx is not None and 0 <= idx < len(self._callbacks):
            self._callbacks[idx]()

    def keyPressEvent(self, event):  # noqa: N802
        if event.key() in (Qt.Key_Escape, Qt.Key_Return, Qt.Key_Enter):
            if event.key() == Qt.Key_Escape:
                self.hide()
            elif self._list.currentItem():
                self._on_item_clicked(self._list.currentItem())
        else:
            super().keyPressEvent(event)

    def show_below(self, anchor: QWidget):
        """Position the popup directly below *anchor* and show it.

        Clicking the arrow again while the popup is already open toggles it
        closed (mirrors standard combobox / menu-button behaviour).
        """
        global _active_ribbon_popup
        # Toggle: hide if we are already the visible popup
        if self.isVisible():
            self.hide()
            return
        # Close any other open popup first
        if _active_ribbon_popup is not None and _active_ribbon_popup is not self:
            _active_ribbon_popup.hide()
        _active_ribbon_popup = self

        # Reparent lazily to the top-level window so the popup can overlay
        # the content area below the ribbon (not clipped by the ribbon widget).
        top = anchor.window()
        if self.parent() is not top:
            self.setParent(top)  # setParent hides the widget; show() below re-shows it

        # Resize height to fit all rows
        total_h = 2  # border
        delegate = self._list.itemDelegate()
        option   = self._list.viewOptions()
        for i in range(self._list.count()):
            idx = self._list.model().index(i, 0)
            total_h += delegate.sizeHint(option, idx).height()
        self._list.setFixedHeight(min(total_h, 400))
        self.adjustSize()

        # Position in top-level window coordinates
        pos = anchor.mapTo(top, QPoint(0, anchor.height()))
        # Clamp to window right edge
        if pos.x() + self.width() > top.width():
            pos.setX(top.width() - self.width())
        self.move(pos)
        self._list.clearSelection()
        self.raise_()
        self.show()


# ---------------------------------------------------------------------------
# Helper: one labelled group of buttons inside a ribbon panel
# ---------------------------------------------------------------------------

class _SplitToolButton(QToolButton):
    """QToolButton that opens a custom popup instead of a QMenu.

    Overrides ``mousePressEvent`` to intercept clicks on the arrow sub-control
    (MenuButtonPopup) or the whole button (InstantPopup) *before* Qt starts
    its popup timer or sets any OS-level mouse grab.  This means no grab is
    ever created, so clicking any other widget after the popup closes always
    requires exactly one click.
    """
    popup_requested = pyqtSignal()

    def mousePressEvent(self, event):  # noqa: N802
        if event.button() == Qt.LeftButton:
            mode = self.popupMode()
            if mode == QToolButton.InstantPopup:
                self.popup_requested.emit()
                event.accept()
                return
            elif mode == QToolButton.MenuButtonPopup:
                opt = QStyleOptionToolButton()
                self.initStyleOption(opt)
                arrow_rect = self.style().subControlRect(
                    QStyle.CC_ToolButton, opt, QStyle.SC_ToolButtonMenu, self
                )
                if arrow_rect.contains(event.pos()):
                    self.popup_requested.emit()
                    event.accept()
                    return
        super().mousePressEvent(event)


class _RibbonGroup(QWidget):
    """A vertical-layout widget: buttons on top, group label at the bottom."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(4, 4, 4, 2)
        outer.setSpacing(0)

        self._btn_row = QHBoxLayout()
        self._btn_row.setContentsMargins(0, 0, 0, 0)
        self._btn_row.setSpacing(2)
        outer.addLayout(self._btn_row)
        outer.addStretch(1)

        label = QLabel(title)
        label.setAlignment(Qt.AlignCenter)
        label.setObjectName("RibbonGroupLabel")
        outer.addWidget(label)

        # Right-side separator line
        self._sep = QFrame(self)
        self._sep.setFrameShape(QFrame.VLine)
        self._sep.setFrameShadow(QFrame.Sunken)
        self._sep.setObjectName("RibbonGroupSep")

    def add_button(self, text: str, tooltip: str, slot=None, checkable=False,
                   icon=None) -> QToolButton:
        btn = QToolButton()
        btn.setText(text)
        btn.setToolTip(tooltip)
        btn.setCheckable(checkable)
        btn.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        btn.setIconSize(QSize(22, 22))
        if icon is not None:
            btn.setIcon(icon)
        btn.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        if slot:
            btn.clicked.connect(slot)
        self._btn_row.addWidget(btn)
        return btn

    def add_menu_button(self, text: str, tooltip: str, actions: list,
                        default_slot=None, icon=None,
                        popup_mode=None) -> QToolButton:
        """Create a QToolButton with an attached QMenu (split-button).

        Args:
            text:         Button label shown under the icon.
            tooltip:      Tooltip for the whole button.
            actions:      List of (label, callback) or (label, callback, icon) tuples.
                          Each entry produces one QAction in the drop-down menu.
            default_slot: Callable invoked when the main button area is clicked
                          (MenuButtonPopup mode).  Defaults to the first action's callback.
            icon:         QIcon for the button face.
            popup_mode:   QToolButton.MenuButtonPopup (default) or
                          QToolButton.InstantPopup.
        Returns:
            The configured QToolButton (already added to the group's button row).
        """
        btn = QToolButton()
        btn.setText(text)
        btn.setToolTip(tooltip)
        btn.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        btn.setIconSize(QSize(22, 22))
        if icon is not None:
            btn.setIcon(icon)
        btn.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)

        menu = QMenu(btn)
        for entry in actions:
            entry_label = entry[0]
            entry_cb    = entry[1]
            entry_icon  = entry[2] if len(entry) > 2 else None
            act = QAction(entry_label, menu)
            if entry_icon is not None:
                act.setIcon(entry_icon)
            act.triggered.connect(entry_cb)
            menu.addAction(act)

        btn.setMenu(menu)
        mode = popup_mode if popup_mode is not None else QToolButton.MenuButtonPopup
        btn.setPopupMode(mode)

        if default_slot is not None:
            btn.clicked.connect(default_slot)
        elif actions:
            btn.clicked.connect(actions[0][1])

        self._btn_row.addWidget(btn)
        return btn

    def add_widget(self, widget) -> None:
        """Add any QWidget directly to the button row."""
        self._btn_row.addWidget(widget)

    def add_listview_button(self, text: str, tooltip: str, actions: list,
                            default_slot=None, icon=None,
                            popup_mode=None) -> QToolButton:
        """Create a QToolButton that opens a _RibbonListPopup on click.

        The popup is a floating QListWidget with a two-line delegate
        (bold title + optional subtitle), without a search bar.

        Args:
            text:         Button label shown under the icon.
            tooltip:      Tooltip for the whole button.
            actions:      List of (label, callback), (label, callback, icon),
                          or (label, callback, icon, subtitle) tuples.
            default_slot: Callable for the main-area click when using
                          MenuButtonPopup.  Defaults to the first callback.
            icon:         QIcon for the button face.
            popup_mode:   QToolButton.MenuButtonPopup (default — left area
                          triggers default_slot, ▾ opens popup) or
                          QToolButton.InstantPopup (whole button opens popup).
        Returns:
            The configured QToolButton (already added to the group's button row).
        """
        btn = _SplitToolButton()
        btn.setText(text)
        btn.setToolTip(tooltip)
        btn.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        btn.setIconSize(QSize(22, 22))
        if icon is not None:
            btn.setIcon(icon)
        btn.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)

        # The popup is parented to the button so it is destroyed with it.
        popup = _RibbonListPopup(actions, parent=btn)
        btn._ribbon_popup = popup  # expose for external enable/disable control

        mode = popup_mode if popup_mode is not None else QToolButton.MenuButtonPopup
        if mode == QToolButton.MenuButtonPopup:
            # A dummy menu is required only so Qt renders the ▾ arrow.
            # showMenu() is overridden so this menu is never actually shown.
            btn.setMenu(QMenu(btn))
        btn.setPopupMode(mode)
        # _SplitToolButton.showMenu() emits popup_requested for both modes.
        btn.popup_requested.connect(lambda: popup.show_below(btn))

        if mode != QToolButton.InstantPopup:
            if default_slot is not None:
                # Clicking the main area closes any open popup then runs default
                btn.clicked.connect(lambda: _close_active_ribbon_popup())
                btn.clicked.connect(default_slot)
            elif actions:
                btn.clicked.connect(lambda: _close_active_ribbon_popup())
                btn.clicked.connect(actions[0][1])

        self._btn_row.addWidget(btn)
        return btn

    def separator_widget(self):
        return self._sep


# ---------------------------------------------------------------------------
# One ribbon panel (content area for a single tab)
# ---------------------------------------------------------------------------

class _RibbonPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(4, 2, 4, 0)
        self._layout.setSpacing(0)
        self._layout.addStretch(1)

    def add_group(self, group: _RibbonGroup):
        # Insert before the trailing stretch
        idx = self._layout.count() - 1
        self._layout.insertWidget(idx, group)
        self._layout.insertWidget(idx + 1, group.separator_widget())


# ---------------------------------------------------------------------------
# Main ribbon widget
# ---------------------------------------------------------------------------

class ProjectRibbon(QWidget):
    """Tab-based ribbon bar.  Emits action signals instead of calling parent
    directly so that it remains loosely coupled to the main window."""

    # Emitted when the user clicks a ribbon tab (0=Task, 1=Resource, 2=Report)
    ribbon_tab_changed = pyqtSignal(int)

    # Tab names (order matters – index 0 = Task)
    TAB_NAMES = ["TASK", "RESOURCE", "REPORT", "BASELINE", "VERSION CONTROL"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ProjectRibbon")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # --- Tab row ---
        tab_row = QHBoxLayout()
        tab_row.setContentsMargins(0, 0, 0, 0)
        tab_row.setSpacing(0)
        self._tab_buttons: list[QPushButton] = []
        for i, name in enumerate(self.TAB_NAMES):
            btn = QPushButton(name)
            btn.setCheckable(True)
            btn.setObjectName("RibbonTab")
            btn.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
            btn.clicked.connect(lambda checked, idx=i: self._on_tab_clicked(idx))
            self._tab_buttons.append(btn)
            tab_row.addWidget(btn)
        tab_row.addStretch(1)
        root.addLayout(tab_row)

        # --- Panel stack ---
        self._panels: list[_RibbonPanel] = []
        self._panel_container = QWidget()
        self._panel_container.setObjectName("RibbonPanelContainer")
        panel_stack = QVBoxLayout(self._panel_container)
        panel_stack.setContentsMargins(0, 0, 0, 0)
        panel_stack.setSpacing(0)

        # Create all panels (hidden by default except first)
        for i in range(len(self.TAB_NAMES)):
            p = _RibbonPanel(self._panel_container)
            p.setVisible(False)
            self._panels.append(p)
            panel_stack.addWidget(p)

        root.addWidget(self._panel_container)

        # Stored button references for external enable/disable
        self._add_btn:  QToolButton | None = None
        self._del_btn:  QToolButton | None = None
        self._split_btn:  QToolButton | None = None
        self._merge_btn:  QToolButton | None = None
        self._baseline_combo: QComboBox | None = None
        self._comparison_combo: QComboBox | None = None
        # Diff-toggle button references (baseline panel)
        self._diff_bars_btn:     QToolButton | None = None
        self._diff_duration_btn: QToolButton | None = None
        self._diff_start_btn:    QToolButton | None = None
        self._diff_finish_btn:   QToolButton | None = None
        # Buttons that require an open project
        self._project_btns: list[QToolButton] = []
        # Buttons that require a selection (subset of project_btns)
        self._selection_btns: list[QToolButton] = []
        # Track project-open and email-configured states for CPM button
        self._project_open: bool = False
        self._email_actions_enabled: bool = True
        # Map from app-tab index to its view-switching button (for highlighting)
        self._view_btns_by_app_tab: dict = {}
        # Groups whose visibility changes with the active view:
        #   _toggle_groups       — all (group, separator) pairs that may be toggled
        #   _hidden_groups_by_app_tab — app_tab_idx → [groups to HIDE for that tab]
        #
        # HOW TO ADD A NEW VISIBILITY RULE
        # ---------------------------------
        # 1. Create the _RibbonGroup and call panel.add_group() as usual.
        # 2. Append (group, group.separator_widget()) to self._toggle_groups ONCE
        #    (done at the end of _build_resource_panel).
        # 3. Add an entry to self._hidden_groups_by_app_tab:
        #       self._hidden_groups_by_app_tab[APP_TAB_IDX] = [grp_a, grp_b, ...]
        #    where APP_TAB_IDX is the QTabWidget index of the view that should
        #    hide those groups (see MainWindow._TAB_LABELS for the index mapping).
        # Groups not listed in _toggle_groups are never touched (always visible).
        self._toggle_groups: list = []
        self._hidden_groups_by_app_tab: dict = {}

        self._build_panels()

        # Activate first tab
        self._active_tab = 0
        self._activate_tab(0)

    # ------------------------------------------------------------------
    # Panel construction
    # ------------------------------------------------------------------

    def _build_panels(self):
        self._build_task_panel()
        self._build_resource_panel()
        self._build_report_panel()
        self._build_baseline_panel()
        self._build_vcs_panel()

    def _build_task_panel(self):
        panel = self._panels[0]  # TASK ribbon panel

        # Task Sheet group — standalone task-list view (before Gantt group)
        grp_sheet = _RibbonGroup("Sheet")
        _sheet_btn = grp_sheet.add_button("Task\nSheet", "Switch to Task Sheet view",
                            lambda: self._call("switch_to_task_sheet"),
                            checkable=True, icon=_icons.task_sheet())
        self._project_btns.append(_sheet_btn)
        self._view_btns_by_app_tab[TAB_TASK_SHEET] = _sheet_btn
        panel.add_group(grp_sheet)

        # View group — all task-related views
        grp_view = _RibbonGroup("View")
        _gantt_btn = grp_view.add_button("Gantt\nChart", "Switch to Gantt Chart view",
                            lambda: self._call("switch_to_gantt"),
                            checkable=True, icon=_icons.gantt_chart())
        self._view_btns_by_app_tab[TAB_GANTT] = _gantt_btn
        _dep_btn = grp_view.add_button("Depend-\ncies", "Switch to Dependencies view",
                            lambda: self._call("switch_to_dependencies"),
                            checkable=True, icon=_icons.dependencies())
        self._view_btns_by_app_tab[TAB_DEPENDENCIES] = _dep_btn
        self._project_btns.extend([_dep_btn])
        panel.add_group(grp_view)

        # Clipboard group
        grp_clip = _RibbonGroup("Clipboard")
        grp_clip.add_button("Paste", "Paste (Ctrl+V)", None, icon=_icons.paste())
        grp_clip.add_button("Cut",   "Cut (Ctrl+X)",   None, icon=_icons.cut())
        grp_clip.add_button("Copy",  "Copy (Ctrl+C)",  None, icon=_icons.copy())
        panel.add_group(grp_clip)

        # Jira group — task synchronization configuration
        # HOW TO CONFIGURE: add/remove app-tab indexes to JIRA_SYNC_RIBBON_TABS (below)
        # to control on which ribbon-TASK-panel views the Jira group is active.
        grp_jira = _RibbonGroup("Jira")
        self._jira_config_btn = grp_jira.add_button(
            "Jira Sync\nConfig",
            "Configure Jira server connections and sync settings",
            lambda: self._call("open_jira_config"),
            icon=_icons.confluence_settings(),  # Reuse settings icon
        )
        # Jira config button is always enabled — it manages global QSettings, not the open project
        self._jira_sync_btn = grp_jira.add_listview_button(
            "Sync from\nJira",
            "Synchronize tasks from Jira — click to run normal sync, or ▾ for advanced modes",
            [
                ("Sync now (normal)",       lambda: self._call("run_jira_sync"),                  _icons.sync_calendar(),       "Default · uses current filter scope"),
                ("Changed since last sync", lambda: self._call("run_jira_sync_changed_since"),    _icons.sync_calendar(),       "Incremental · skips issues unchanged since last run"),
                ("Full resync",             lambda: self._call("run_jira_sync_full_resync"),      _icons.sync_calendar(),       "Clears timestamp · re-fetches all matching issues"),
            ],
            default_slot=lambda: self._call("run_jira_sync"),
            icon=_icons.sync_calendar(),
        )
        # Sync button requires an open project
        self._project_btns.append(self._jira_sync_btn)

        self._jira_push_btn = grp_jira.add_listview_button(
            "Sync to\nJira",
            "Push project task changes to Jira — click to run normal push, or ▾ for preview",
            [
                ("Sync to Jira (normal)", lambda: self._call("run_jira_push"),         _icons.export_svg(),          "Push all pending task changes to Jira"),
                ("Dry-run preview",       lambda: self._call("run_jira_push_dry_run"), _icons.export_svg(),          "Shows changes without applying them"),
            ],
            default_slot=lambda: self._call("run_jira_push"),
            icon=_icons.export_svg(),
        )
        # Push button requires an open project
        self._project_btns.append(self._jira_push_btn)
        panel.add_group(grp_jira)
        # Store reference for use in _build_resource_panel's _toggle_groups
        self._grp_jira = grp_jira

        # Insert group — buttons kept for future GUI customisation, not shown in ribbon
        # Groups are parented to self so Qt never shows them as top-level windows.
        self._hidden_grp_ins = _RibbonGroup("Insert", self)
        self._add_btn = self._hidden_grp_ins.add_button("Insert\nTask", "Add a new entry (Ins)",
                                           lambda: self._call("add_entry"),
                                           icon=_icons.insert_task())
        self._hidden_grp_ins.hide()
        self._project_btns.append(self._add_btn)

        # Editing group — buttons kept for future GUI customisation, not shown in ribbon
        self._hidden_grp_edit = _RibbonGroup("Editing", self)
        self._del_btn = self._hidden_grp_edit.add_button("Delete\nTask", "Delete selected entry (Del)",
                                            lambda: self._call("delete_entry"),
                                            icon=_icons.delete_task())
        self._hidden_grp_edit.hide()
        self._project_btns.append(self._del_btn)
        self._selection_btns.append(self._del_btn)

        # Split / Merge group — buttons kept for future GUI customisation, not shown in ribbon
        grp_split = _RibbonGroup("Split", self)
        self._split_btn = grp_split.add_button(
            "Split\nTask", "Split the selected task at a date (creates a gap)",
            lambda: self._call("split_task_action"),
            icon=_icons.split_task_icon(),
        )
        self._merge_btn = grp_split.add_button(
            "Merge\nSegments", "Merge all split segments back into a single bar",
            lambda: self._call("merge_task_action"),
            icon=_icons.merge_task_icon(),
        )
        grp_split.hide()
        self._project_btns.extend([self._split_btn, self._merge_btn])

        # Register the split group so update_button_visibility can hide it when needed
        # (added to _toggle_groups in _build_resource_panel — but we need it available
        # here; we store it as an instance attribute for use in _build_resource_panel).
        self._grp_split_task = grp_split

    def _build_resource_panel(self):
        panel = self._panels[1]  # RESOURCE ribbon panel

        grp_view = _RibbonGroup("View")
        _tp_btn = grp_view.add_button("Team\nPlanner", "Switch to Team Planner view",
                            lambda: self._call("switch_to_team_planner"),
                            checkable=True, icon=_icons.team_planner())
        self._project_btns.append(_tp_btn)
        self._view_btns_by_app_tab[TAB_TEAM_PLANNER] = _tp_btn
        _rs_btn = grp_view.add_button("Resource\nSheet", "Switch to Resource Sheet view",
                            lambda: self._call("switch_to_resources"),
                            checkable=True, icon=_icons.resource_sheet())
        self._view_btns_by_app_tab[TAB_RESOURCES] = _rs_btn
        _rug_btn = grp_view.add_button("Resource\nUsage", "Switch to Resource Usage Graph view",
                            lambda: self._call("switch_to_resource_usage_graph"),
                            checkable=True, icon=_icons.resource_usage_graph())
        self._project_btns.append(_rug_btn)
        self._view_btns_by_app_tab[TAB_RESOURCE_USAGE] = _rug_btn
        panel.add_group(grp_view)

        grp_ins = _RibbonGroup("Insert")
        _add_res = grp_ins.add_listview_button(
            "Add\nResource",
            "Add a new resource — click for manual entry, or ▾ for Active Directory options",
            [
                ("Add Resource (manual)",     lambda: self._call("add_resource"),                  _icons.add_resource(), "Enter name, role and availability manually"),
                ("Add from Active Directory", lambda: self._call("add_resource_from_ad"),          _icons.add_resource(), "Look up a single AD user and import as resource"),
                ("Add from AD Group",         lambda: self._call("add_resources_from_ad_group"),   _icons.add_resource(), "Import all members of an AD group as resources"),
            ],
            default_slot=lambda: self._call("add_resource"),
            icon=_icons.add_resource(),
        )
        self._project_btns.append(_add_res)
        panel.add_group(grp_ins)

        grp_edit = _RibbonGroup("Editing")
        _del_res = grp_edit.add_button("Delete\nResource", "Delete the selected resource",
                            lambda: self._call("delete_resource"),
                            icon=_icons.delete_resource())
        self._project_btns.append(_del_res)
        self._selection_btns.append(_del_res)
        panel.add_group(grp_edit)

        grp_confluence = _RibbonGroup("Confluence")
        self._confluence_config_btn = grp_confluence.add_button(
            "Calendar\nConfig",
            "Configure Confluence Calendar settings (KeePass SSO entry and calendar properties)",
            lambda: self._call("open_confluence_calendar_config"),
            icon=_icons.confluence_settings(),
        )
        # Config button is always enabled — it manages global QSettings, not the open project
        self._confluence_sync_btn = grp_confluence.add_button(
            "Sync\nCalendar",
            "Fetch vacations and public holidays from Confluence Team Calendars\n"
            "and apply them as non-working exceptions to resource / project calendars",
            lambda: self._call("sync_confluence_calendars"),
            icon=_icons.sync_calendar(),
        )
        self._confluence_sync_btn.setEnabled(False)
        # Sync button requires an open project
        self._project_btns.append(self._confluence_sync_btn)
        panel.add_group(grp_confluence)

        # Register toggle-able groups and define per-view hidden sets.
        # HOW TO CONFIGURE
        # ----------------
        # _toggle_groups    : list every (group, separator) pair that can be
        #                     shown or hidden depending on the active view.
        #                     Each group must appear in this list exactly once.
        # _hidden_groups_by_app_tab : map app-tab index → list of groups that
        #                     must be HIDDEN when that tab is active.
        #                     Tabs not listed here show all groups in _toggle_groups.
        #
        # App-tab index reference (see MainWindow._TAB_LABELS in ui.py):
        #   0 Gantt Chart  | 1 Resources     | 2 Dependencies
        #   3 TAB_BASELINE       | 4 TAB_TEAM_PLANNER  | 5 TAB_TASK_SHEET
        #   6 TAB_RESOURCE_USAGE
        self._toggle_groups = [
            (grp_ins,        grp_ins.separator_widget()),
            (grp_edit,       grp_edit.separator_widget()),
            (grp_confluence, grp_confluence.separator_widget()),
            (self._grp_jira, self._grp_jira.separator_widget()),
        ]
        # Resource Usage Graph: editing/insert/confluence/jira groups not applicable
        self._hidden_groups_by_app_tab[TAB_RESOURCE_USAGE] = [grp_ins, grp_edit, grp_confluence, self._grp_jira]

        # _grp_split_task is not in any ribbon panel (reserved for GUI customisation),
        # so it must NOT be in _toggle_groups — otherwise update_button_visibility
        # would call setVisible(True) on it, popping it up as a floating window.

    def _build_report_panel(self):
        panel = self._panels[2]  # REPORT ribbon panel

        grp_export = _RibbonGroup("Export")
        _gantt_exp = grp_export.add_listview_button(
            "Gantt\nExport",
            "Export Gantt Chart — click for SVG, or ▾ for format options",
            [
                ("Gantt SVG",            lambda: self._call("export_gantt_svg"),        _icons.export_svg(),    "Save to file · vector, scalable for print and web"),
                ("Gantt PlantUML",       lambda: self._call("export_gantt_plantuml"),   _icons.export_svg(),    "Save to file · editable diagram markup"),
                None,
                ("Email Gantt SVG",      lambda: self._call("email_gantt_svg"),         _icons.email_send_icon(), "Send Gantt chart as SVG email attachment"),
                ("Email to All Resources", lambda: self._call("email_resource_gantt_svg"), _icons.email_send_icon(), "Send one personalised per-resource Gantt SVG to each resource"),
            ],
            default_slot=lambda: self._call("export_gantt_svg"),
            icon=_icons.export_svg(),
        )
        _rsvg = grp_export.add_listview_button(
            "Resource\nSVG",
            "Resource Gantt Charts — click to save to folder, or ▾ to email",
            [
                ("Save Resource SVGs",     lambda: self._call("export_resource_gantt_svg"),  _icons.export_svg(),    "Save one SVG per resource to a selected folder"),
                None,
                ("Email to All Resources", lambda: self._call("email_resource_gantt_svg"),   _icons.email_send_icon(), "Send one personalised per-resource Gantt SVG to each resource"),
            ],
            default_slot=lambda: self._call("export_resource_gantt_svg"),
            icon=_icons.export_svg(),
        )
        _tl_exp = grp_export.add_listview_button(
            "Timeline\nExport",
            "Export Timeline strip — click for SVG, or ▾ for format options",
            [
                ("Timeline SVG",       lambda: self._call("export_timeline_svg"),      _icons.export_svg(),      "Save to file · vector, scalable for print and web"),
                ("Timeline PlantUML",  lambda: self._call("export_timeline_plantuml"), _icons.export_svg(),      "Save to file · editable diagram markup"),
                None,
                ("Email Timeline SVG", lambda: self._call("email_timeline_svg"),       _icons.email_send_icon(), "Send Timeline strip as SVG email attachment"),
            ],
            default_slot=lambda: self._call("export_timeline_svg"),
            icon=_icons.export_svg(),
        )
        self._project_btns.extend([_gantt_exp, _rsvg, _tl_exp])
        self._gantt_exp_popup = _gantt_exp._ribbon_popup
        self._rsvg_popup      = _rsvg._ribbon_popup
        self._tl_exp_popup    = _tl_exp._ribbon_popup
        _CPM_EXP_TIP = "Send CPM critical-path report — click to email report, or ▾ for options"
        _cpm_exp = grp_export.add_listview_button(
            "CPM\nReport",
            _CPM_EXP_TIP,
            [
                ("Email CPM Report",          lambda: self._call("email_cpm_report"),          _icons.email_send_icon(), "Send CPM results table as an HTML email"),
                ("Email CPM Report + Gantt",  lambda: self._call("email_cpm_report_with_gantt"), _icons.email_send_icon(), "Send CPM results table with Gantt SVG attached"),
            ],
            default_slot=lambda: self._call("email_cpm_report"),
            icon=_icons.email_send_icon(),
        )
        self._cpm_exp_btn     = _cpm_exp
        self._cpm_exp_btn_tip = _CPM_EXP_TIP
        self._project_btns.append(_cpm_exp)
        panel.add_group(grp_export)

        grp_views = _RibbonGroup("Views")
        _cpm_view_btn = grp_views.add_button(
            "CPM\nResults",
            "Switch to CPM Results view — critical-path analysis table",
            lambda: self._call("switch_to_cpm_results"),
            checkable=True,
            icon=_icons.cpm_settings_icon() if hasattr(_icons, 'cpm_settings_icon') else _icons.export_svg(),
        )
        self._project_btns.append(_cpm_view_btn)
        self._view_btns_by_app_tab[TAB_CPM] = _cpm_view_btn
        panel.add_group(grp_views)

        grp_email = _RibbonGroup("Email")
        self._email_configs_btn = grp_email.add_button(
            "Email\nAccounts",
            "Manage multiple Email (SMTP) configurations",
            lambda: self._call("open_email_configs"),
            icon=_icons.confluence_settings(),  # Reuse settings icon
        )
        self._email_config_btn = grp_email.add_button(
            "Email\nConfig",
            "Configure SMTP settings and KeePass credentials for sending emails",
            lambda: self._call("open_email_config"),
            icon=_icons.confluence_settings(),  # Reuse settings icon
        )
        # Both email config buttons are always enabled — they manage global QSettings, not the open project
        panel.add_group(grp_email)
        self._grp_email = grp_email

    def _build_baseline_panel(self):
        panel = self._panels[RIBBON_BASELINE]  # BASELINE ribbon panel

        # --- Reference group: Set / Clear / Active baseline selector ---
        grp_ref = _RibbonGroup("Reference")
        _set_btn = grp_ref.add_listview_button(
            "Set\nBaseline",
            "Snapshot the current schedule into a baseline slot — click to open dialog, or ▾ for quick options",
            [
                ("Set baseline (dialog)",   lambda: self._call("set_baseline"),           _icons.set_baseline_icon(), "Choose slot and scope in a dialog"),
                ("Set into next free slot", lambda: self._call("set_baseline_next_free"), _icons.set_baseline_icon(), "Saves to the first empty slot without a dialog"),
                ("Set all slots (bulk)",    lambda: self._call("set_baseline_all_slots"), _icons.set_baseline_icon(), "Snapshots current schedule into all 11 slots"),
            ],
            default_slot=lambda: self._call("set_baseline"),
            icon=_icons.set_baseline_icon(),
        )
        _clr_btn = grp_ref.add_listview_button(
            "Clear\nBaseline",
            "Remove baseline data — click to open dialog, or ▾ for quick options",
            [
                ("Clear baseline (dialog)", lambda: self._call("clear_baseline"),     _icons.clear_baseline_icon(), "Select slot and scope to clear in a dialog"),
                ("Clear all baselines",     lambda: self._call("clear_baseline_all"), _icons.clear_baseline_icon(), "Removes all 11 slots after confirmation"),
            ],
            default_slot=lambda: self._call("clear_baseline"),
            icon=_icons.clear_baseline_icon(),
        )
        # Active-baseline drop-down (which slot is shown / compared)
        self._baseline_combo = QComboBox()
        self._baseline_combo.setToolTip(
            "Select the active baseline slot used for comparison"
        )
        self._baseline_combo.addItems(
            ["Baseline"] + [f"Baseline {n}" for n in range(1, 11)]
        )
        self._baseline_combo.setMinimumWidth(160)
        self._baseline_combo.currentIndexChanged.connect(
            self._on_baseline_combo_changed
        )

        # Comparison selector — both combos stacked top-to-bottom in a container
        # Build a small container: two rows (label + combo each)
        _combo_container = QWidget()
        _combo_vbox = QVBoxLayout(_combo_container)
        _combo_vbox.setContentsMargins(0, 0, 0, 0)
        _combo_vbox.setSpacing(2)

        _ref_row = QHBoxLayout()
        _ref_row.setContentsMargins(0, 0, 0, 0)
        _ref_lbl = QLabel("Ref:")
        _ref_lbl.setToolTip("Reference baseline for comparison")
        _ref_row.addWidget(_ref_lbl)
        _ref_row.addWidget(self._baseline_combo)
        _combo_vbox.addLayout(_ref_row)

        _vs_row = QHBoxLayout()
        _vs_row.setContentsMargins(0, 0, 0, 0)
        _vs_lbl = QLabel("vs.:")
        _vs_lbl.setToolTip("Compare against this slot (or current schedule)")
        _vs_row.addWidget(_vs_lbl)
        self._comparison_combo = QComboBox()
        self._comparison_combo.setToolTip(
            "Select what to compare the reference baseline against"
        )
        self._comparison_combo.addItem("Current")   # index 0 → comparison number -1
        self._comparison_combo.addItems(
            ["Baseline"] + [f"Baseline {n}" for n in range(1, 11)]
        )                                            # index k+1 → comparison number k (0-10)
        self._comparison_combo.setMinimumWidth(160)
        self._comparison_combo.currentIndexChanged.connect(
            lambda idx: self._call("set_comparison_baseline", idx - 1)
        )
        _vs_row.addWidget(self._comparison_combo)
        _combo_vbox.addLayout(_vs_row)

        grp_ref.add_widget(_combo_container)
        self._project_btns.extend([_set_btn, _clr_btn])
        panel.add_group(grp_ref)

        # --- Gantt Diff group: toggle options for Gantt variance display ---
        grp_gantt = _RibbonGroup("Gantt Diff")
        self._diff_bars_btn = grp_gantt.add_button(
            "Show\nBars",
            "Show the selected baseline as a reference strip behind each Gantt bar",
            lambda checked: self._call("toggle_gantt_diff_bars", checked),
            checkable=True,
            icon=_icons.diff_bars_icon(),
        )
        self._diff_bars_btn.setChecked(True)
        self._diff_duration_btn = grp_gantt.add_button(
            "Duration\n%",
            "Highlight tasks where duration deviates from baseline",
            lambda checked: self._call("toggle_gantt_diff_duration", checked),
            checkable=True,
            icon=_icons.diff_delta_icon(),
        )
        self._diff_duration_btn.setChecked(True)
        self._diff_start_btn = grp_gantt.add_button(
            "Start\nΔ",
            "Highlight tasks where start date deviates from baseline",
            lambda checked: self._call("toggle_gantt_diff_start", checked),
            checkable=True,
            icon=_icons.diff_delta_icon(),
        )
        self._diff_start_btn.setChecked(True)
        self._diff_finish_btn = grp_gantt.add_button(
            "Finish\nΔ",
            "Highlight tasks where finish date deviates from baseline",
            lambda checked: self._call("toggle_gantt_diff_finish", checked),
            checkable=True,
            icon=_icons.diff_delta_icon(),
        )
        self._diff_finish_btn.setChecked(True)
        self._project_btns.extend([
            self._diff_bars_btn, self._diff_duration_btn,
            self._diff_start_btn, self._diff_finish_btn,
        ])
        panel.add_group(grp_gantt)

        # --- View group: switch to Baseline comparison table ---
        grp_view = _RibbonGroup("View")
        _tbl_btn = grp_view.add_button(
            "Baseline\nTable",
            "Switch to the Baseline comparison table",
            lambda: self._call("switch_to_baseline"),
            checkable=True,
            icon=_icons.view_baseline_icon(),
        )
        self._view_btns_by_app_tab[TAB_BASELINE] = _tbl_btn
        self._project_btns.append(_tbl_btn)
        panel.add_group(grp_view)

    def _build_vcs_panel(self):
        panel = self._panels[RIBBON_VCS]  # VERSION CONTROL ribbon panel

        # Config group — always enabled (manages global QSettings)
        grp_cfg = _RibbonGroup("Setup")
        self._vcs_config_btn = grp_cfg.add_button(
            "VCS\nConfig",
            "Configure Version Control credentials (KeePass) and auto-commit settings",
            lambda: self._call("open_vcs_config"),
            icon=_icons.vcs_config_icon(),
        )
        self._vcs_register_btn = grp_cfg.add_button(
            "Register\nwith VCS",
            "Register the project file with SVN (svn add) — enabled only when the file is unversioned",
            lambda: self._call("run_vcs_svn_register"),
            icon=_icons.vcs_commit_icon(),
        )
        self._vcs_register_btn.setVisible(False)  # shown only for SVN + unversioned file
        # Config button is always enabled — manages global QSettings only
        panel.add_group(grp_cfg)

        # Operations group — require an open project with a detected repo
        grp_ops = _RibbonGroup("Operations")
        self._vcs_commit_btn = grp_ops.add_listview_button(
            "Commit",
            "Commit to version control — click to commit project file, or ▾ for scope options",
            [
                ("Commit project file only",   lambda: self._call("run_vcs_commit"),     _icons.vcs_commit_icon(), "Stages and commits the .pof file only"),
                ("Commit all tracked changes", lambda: self._call("run_vcs_commit_all"), _icons.vcs_commit_icon(), "Stages all modified tracked files and commits"),
            ],
            default_slot=lambda: self._call("run_vcs_commit"),
            icon=_icons.vcs_commit_icon(),
        )
        self._vcs_log_btn = grp_ops.add_button(
            "View\nLog",
            "View the commit history for the current repository",
            lambda: self._call("open_vcs_log"),
            icon=_icons.vcs_log_icon(),
        )
        panel.add_group(grp_ops)
        self._project_btns.extend([self._vcs_commit_btn, self._vcs_log_btn])

        # Git-specific group
        grp_git = _RibbonGroup("Git")
        self._vcs_branch_btn = grp_git.add_button(
            "Branch\nManagement",
            "Create, list, and switch Git branches",
            lambda: self._call("open_vcs_branch_dialog"),
            icon=_icons.vcs_branch_icon(),
        )
        self._vcs_pull_btn = grp_git.add_listview_button(
            "Pull",
            "Pull from the remote Git repository — click for merge pull, or ▾ for strategy options",
            [
                ("Pull (merge)",  lambda: self._call("run_vcs_pull"),        _icons.vcs_update_icon(), "Fetches and merges remote changes (git pull)"),
                ("Pull (rebase)", lambda: self._call("run_vcs_pull_rebase"), _icons.vcs_update_icon(), "Fetches and rebases local commits (git pull --rebase)"),
                ("Fetch only",    lambda: self._call("run_vcs_fetch_only"),  _icons.vcs_update_icon(), "Downloads remote refs without merging (git fetch)"),
            ],
            default_slot=lambda: self._call("run_vcs_pull"),
            icon=_icons.vcs_update_icon(),
        )
        panel.add_group(grp_git)
        self._project_btns.extend([self._vcs_branch_btn, self._vcs_pull_btn])
        self._grp_vcs_git = grp_git

        # SVN-specific group
        grp_svn = _RibbonGroup("SVN")
        self._vcs_update_btn = grp_svn.add_listview_button(
            "Update",
            "Update SVN working copy — click to update to HEAD, or ▾ for revision options",
            [
                ("Update to HEAD",      lambda: self._call("run_vcs_svn_update"),              _icons.vcs_update_icon(), "svn update · brings working copy to latest revision"),
                ("Update to revision…", lambda: self._call("run_vcs_svn_update_to_revision"),  _icons.vcs_update_icon(), "Prompts for a revision number before updating"),
            ],
            default_slot=lambda: self._call("run_vcs_svn_update"),
            icon=_icons.vcs_update_icon(),
        )
        self._vcs_cleanup_btn = grp_svn.add_button(
            "Cleanup",
            "Run SVN cleanup to fix a locked or interrupted working copy",
            lambda: self._call("run_vcs_svn_cleanup"),
            icon=_icons.vcs_config_icon(),
        )
        panel.add_group(grp_svn)
        self._project_btns.extend([self._vcs_update_btn, self._vcs_cleanup_btn])
        self._grp_vcs_svn = grp_svn

        # The tab itself is hidden by default and shown only when a repo is detected.
        # We also hide git/svn groups depending on detected VCS type.
        self._vcs_tab_visible: bool = False
        self._tab_buttons[RIBBON_VCS].setVisible(False)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _call(self, method: str, *args):
        """Call a method on the parent main window, if it exists."""
        window = self.parent()
        while window and not hasattr(window, method):
            window = window.parent() if hasattr(window, "parent") else None
        if window:
            fn = getattr(window, method)
            fn(*args)

    def _on_baseline_combo_changed(self, idx: int) -> None:
        """Handle reference-baseline combo change.

        If the comparison combo is set to the same slot, auto-reset it to
        'Current' so the user never ends up comparing a baseline against itself.
        """
        self._call("set_active_baseline", idx)
        if self._comparison_combo is not None:
            # comparison index 0 = "Current" (slot -1), index k+1 = slot k
            cmp_slot = self._comparison_combo.currentIndex() - 1
            if cmp_slot >= 0 and cmp_slot == idx:
                self._comparison_combo.blockSignals(True)
                self._comparison_combo.setCurrentIndex(0)   # "Current"
                self._comparison_combo.blockSignals(False)
                self._call("set_comparison_baseline", -1)

    def _on_tab_clicked(self, idx: int):
        _close_active_ribbon_popup()
        self._activate_tab(idx)
        self.ribbon_tab_changed.emit(idx)

    def _activate_tab(self, idx: int):
        for i, btn in enumerate(self._tab_buttons):
            btn.setChecked(i == idx)
        for i, panel in enumerate(self._panels):
            panel.setVisible(i == idx)
        self._active_tab = idx

    # ------------------------------------------------------------------
    # Public API (called from ui.py to keep state in sync)
    # ------------------------------------------------------------------

    def set_save_enabled(self, enabled: bool):
        pass  # No Save button in ribbon

    def set_project_open(self, is_open: bool):
        """Enable/disable all buttons that require an open project."""
        self._project_open = is_open
        for btn in self._project_btns:
            if btn not in self._selection_btns:
                btn.setEnabled(is_open)
        # Selection-gated buttons stay disabled until a row is selected
        for btn in self._selection_btns:
            btn.setEnabled(False)
        # CPM Report button is email-only — keep it disabled when email is not configured
        if is_open and not self._email_actions_enabled:
            self._cpm_exp_btn.setEnabled(False)

    def set_confluence_sync_state(self, enabled: bool, tooltip: str):
        """Set enabled state and tooltip of the Confluence Sync Calendar button."""
        self._confluence_sync_btn.setEnabled(enabled)
        self._confluence_sync_btn.setToolTip(tooltip)

    def set_confluence_config_state(self, enabled: bool, tooltip: str = ""):
        """Set enabled state and tooltip of the Confluence Calendar Config button."""
        self._confluence_config_btn.setEnabled(enabled)
        if tooltip:
            self._confluence_config_btn.setToolTip(tooltip)

    def set_email_configs_state(self, enabled: bool, tooltip: str = ""):
        """Set enabled state and tooltip of the Email Accounts button."""
        self._email_configs_btn.setEnabled(enabled)
        if tooltip:
            self._email_configs_btn.setToolTip(tooltip)

    def set_email_config_state(self, enabled: bool, tooltip: str = ""):
        """Set enabled state and tooltip of the Email Config button."""
        self._email_config_btn.setEnabled(enabled)
        if tooltip:
            self._email_config_btn.setToolTip(tooltip)

    def set_email_actions_enabled(self, enabled: bool, tooltip: str = "") -> None:
        """Enable or disable all email action items in the export dropdowns.

        Also enables/disables the CPM Report button entirely, since all of its
        actions are email-based.
        """
        self._email_actions_enabled = enabled
        _EMAIL_LABELS = [
            "Email Gantt SVG",
            "Email to All Resources",
            "Email Timeline SVG",
        ]
        for popup in (self._gantt_exp_popup, self._rsvg_popup, self._tl_exp_popup):
            for label in _EMAIL_LABELS:
                popup.set_item_enabled(label, enabled, tooltip)
        # CPM Report button: enable/disable as a whole (all actions are email)
        if enabled:
            # Re-enable only if a project is open; always restore the original tooltip
            self._cpm_exp_btn.setEnabled(self._project_open)
            self._cpm_exp_btn.setToolTip(self._cpm_exp_btn_tip)
        else:
            self._cpm_exp_btn.setEnabled(False)
            if tooltip:
                self._cpm_exp_btn.setToolTip(tooltip)

    def set_vcs_tab_visible(self, visible: bool):
        """Show or hide the VERSION CONTROL ribbon tab."""
        self._vcs_tab_visible = visible
        self._tab_buttons[RIBBON_VCS].setVisible(visible)

    def set_vcs_repo_type(self, vcs_type: str):
        """Show only the Git or SVN group depending on detected repo type."""
        is_git = vcs_type == "git"
        is_svn = vcs_type == "svn"
        self._grp_vcs_git.setVisible(is_git)
        self._grp_vcs_git.separator_widget().setVisible(is_git)
        self._grp_vcs_svn.setVisible(is_svn)
        self._grp_vcs_svn.separator_widget().setVisible(is_svn)

    def set_vcs_commit_state(self, enabled: bool, tooltip: str = ""):
        """Enable/disable the VCS Commit button."""
        self._vcs_commit_btn.setEnabled(enabled)
        if tooltip:
            self._vcs_commit_btn.setToolTip(tooltip)

    def set_vcs_register_state(self, visible: bool, enabled: bool = True):
        """Show/hide and enable/disable the 'Register with VCS' button.

        The button is only meaningful for SVN repos where the project file
        has status '?' (unversioned).
        """
        self._vcs_register_btn.setVisible(visible)
        self._vcs_register_btn.setEnabled(enabled)

    def set_delete_enabled(self, enabled: bool):
        if self._del_btn:
            self._del_btn.setEnabled(enabled)

    def set_resource_units_checked(self, checked: bool):
        pass  # No Format buttons in ribbon

    def set_show_sundays_checked(self, checked: bool):
        pass  # No Format buttons in ribbon

    def highlight_view_button(self, app_tab_idx: int):
        """Check the view button for the active app tab, uncheck all others."""
        for idx, btn in self._view_btns_by_app_tab.items():
            btn.setChecked(idx == app_tab_idx)

    def update_button_visibility(self, app_tab_idx: int):
        """Show/hide ribbon groups according to _hidden_groups_by_app_tab."""
        hidden = self._hidden_groups_by_app_tab.get(app_tab_idx, [])
        for grp, sep in self._toggle_groups:
            visible = grp not in hidden
            grp.setVisible(visible)
            sep.setVisible(visible)

    def update_baseline_list(self, active_baselines: dict) -> None:
        """Repopulate the active-baseline combo with set/unset indicators.

        *active_baselines* maps slot number → ISO date string (from
        baseline_manager.get_active_baselines).  Unset slots are shown in
        grey; set slots show their capture date.
        """
        if self._baseline_combo is None:
            return
        current = self._baseline_combo.currentIndex()
        self._baseline_combo.blockSignals(True)
        self._baseline_combo.clear()
        for n in range(11):
            label = "Baseline" if n == 0 else f"Baseline {n}"
            if n in active_baselines:
                label += f"  ({active_baselines[n]})"
            self._baseline_combo.addItem(label)
        idx = current if 0 <= current < self._baseline_combo.count() else 0
        self._baseline_combo.setCurrentIndex(idx)
        self._baseline_combo.blockSignals(False)

        # Also update the comparison combo (keeps "Current" as first item)
        if self._comparison_combo is not None:
            cur_cmp = self._comparison_combo.currentIndex()
            self._comparison_combo.blockSignals(True)
            self._comparison_combo.clear()
            self._comparison_combo.addItem("Current")   # index 0 → number -1
            for n in range(11):
                label = "Baseline" if n == 0 else f"Baseline {n}"
                if n in active_baselines:
                    label += f"  ({active_baselines[n]})"
                self._comparison_combo.addItem(label)
            idx_c = cur_cmp if 0 <= cur_cmp < self._comparison_combo.count() else 0
            self._comparison_combo.setCurrentIndex(idx_c)
            self._comparison_combo.blockSignals(False)

    def update_actions(self, add_label: str, del_label: str, enabled: bool = True,
                       zoom_enabled: bool = True):
        """Called by ui._on_tab_changed to update context-sensitive buttons."""
        if self._add_btn:
            self._add_btn.setText(add_label.replace("\u2795 ", "").replace("\n", "\n"))
            self._add_btn.setEnabled(enabled)
        if self._del_btn:
            self._del_btn.setText(del_label.replace("\u2716 ", "").replace("\n", "\n"))
            self._del_btn.setEnabled(enabled)
