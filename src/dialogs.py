# dialogs.py - Project detail dialogs
#
# Opened when the user double-clicks a row in any view.
# Each dialog follows a consistent look:
#   - Blue header bar with title + subtitle
#   - Tabbed content area (General / Predecessors / Notes / ...)
#   - Blue OK / Cancel buttons at the bottom

from PyQt5.QtWidgets import (  # type: ignore
    QDialog, QTabWidget, QWidget, QVBoxLayout, QHBoxLayout,
    QFormLayout, QLabel, QLineEdit, QTextEdit, QPushButton,
    QComboBox, QCheckBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QDialogButtonBox, QFrame, QMessageBox,
    QSplitter, QListWidget, QStackedWidget, QListWidgetItem, QInputDialog,
    QAbstractItemView, QDateEdit, QDateTimeEdit, QTimeEdit,
    QMenu, QAction
)
from PyQt5.QtCore import Qt, QDate, QDateTime, QTime  # type: ignore


def _xml_indent_et(elem, level=0):
    """Pretty-print indent an ElementTree element in-place (Python 3.8 compatible)."""
    indent = "\n" + "    " * level
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = indent + "    "
        if not elem.tail or not elem.tail.strip():
            elem.tail = indent
        for child in elem:
            _xml_indent_et(child, level + 1)
        if not child.tail or not child.tail.strip():
            child.tail = indent
    else:
        if not elem.tail or not elem.tail.strip():
            elem.tail = indent
    if level == 0:
        elem.tail = "\n"


# ------------------------------------------------------------------ #
# Shared helpers                                                       #
# ------------------------------------------------------------------ #

_DIALOG_STYLE = """
QDialog { background: white; font-family: "Segoe UI", Arial, sans-serif; }
QTabWidget::pane { border: 1px solid #B8CBE4; background: white; }
QTabBar::tab {
    background: #E4EDF8; color: #2B579A;
    border: 1px solid #BDD0E8; border-bottom: none;
    padding: 5px 12px; font-size: 12px; font-weight: bold;
}
QTabBar { alignment: left; }
QTabBar::tab:selected { background: white; border-top: 2px solid #2B579A; }
QTabBar::tab:hover:!selected { background: #C5D8F0; }
QLineEdit, QTextEdit, QComboBox, QDateEdit, QDateTimeEdit, QTimeEdit {
    border: 1px solid #B8CBE4; padding: 3px 6px;
    font-size: 12px; border-radius: 2px;
}
QLineEdit:focus, QTextEdit:focus, QComboBox:focus,
QDateEdit:focus, QDateTimeEdit:focus, QTimeEdit:focus { border: 1px solid #2B579A; }
QLineEdit[readOnly="true"] { background: #F5F5F5; color: #555; }
QLabel { font-size: 12px; color: #1F1F1F; }
QCheckBox { font-size: 12px; }
QTableWidget {
    gridline-color: #D0DDF0; font-size: 12px;
    selection-background-color: #BDD7EE; selection-color: black;
    alternate-background-color: #F0F5FF;
}
QHeaderView::section {
    background: #ECF3FB; border-right: 1px solid #B0C8E0;
    border-bottom: 2px solid #2B579A; padding: 4px 8px;
    font-size: 12px; font-weight: bold; color: #1A3F7A;
}
"""

_BUTTON_STYLE = """
QPushButton {
    background: #2B579A; color: white; border: none;
    border-radius: 3px; padding: 5px 20px; font-size: 12px;
    min-width: 72px;
}
QPushButton:hover  { background: #3A6EBC; }
QPushButton:pressed { background: #1A4585; }
QPushButton[flat="true"] {
    background: #E4EDF8; color: #2B579A; border: 1px solid #BDD0E8;
}
QPushButton[flat="true"]:hover { background: #C5D8F0; }
"""


def _make_header(title, subtitle=""):
    """Blue MS-Project-style dialog header."""
    frame = QFrame()
    frame.setStyleSheet("background: #2B579A; border: none;")
    frame.setFixedHeight(52 if not subtitle else 68)
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(16, 8, 8, 8)
    layout.setSpacing(2)
    lbl = QLabel(title)
    lbl.setStyleSheet("color: white; font-size: 14px; font-weight: bold; background: transparent;")
    layout.addWidget(lbl)
    if subtitle:
        sub = QLabel(subtitle)
        sub.setStyleSheet("color: #CCE0FF; font-size: 11px; background: transparent;")
        layout.addWidget(sub)
    return frame


def _make_button_row(dialog, ok_label="OK", cancel_label="Cancel", read_only=False):
    """Return a styled button row widget."""
    row = QWidget()
    h = QHBoxLayout(row)
    h.setContentsMargins(12, 6, 12, 12)
    h.addStretch()
    if not read_only:
        ok_btn = QPushButton(ok_label)
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(dialog.accept)
        ok_btn.setStyleSheet(_BUTTON_STYLE)
        h.addWidget(ok_btn)
    close_btn = QPushButton(cancel_label if not read_only else "Close")
    close_btn.clicked.connect(dialog.reject)
    close_btn.setStyleSheet(_BUTTON_STYLE)
    h.addWidget(close_btn)
    return row


class _BaseDialog(QDialog):
    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setMinimumWidth(520)
        self.setModal(True)
        self.setStyleSheet(_DIALOG_STYLE)
        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(0, 0, 0, 0)
        self._root.setSpacing(0)


# ------------------------------------------------------------------ #
# Non-working day dialog (shown when a task is dragged onto a weekend) #
# ------------------------------------------------------------------ #

class NonWorkingDayDialog(QDialog):
    """Ask the user what to do when a dragged task lands on a non-working day."""

    SNAP    = "snap"     # move to next working day
    KEEP    = "keep"     # keep on the non-working day
    CANCEL  = "cancel"  # cancel the move

    def __init__(self, task_name: str, raw_date_str: str, snapped_date_str: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Planning Wizard")
        self.setModal(True)
        self.setMinimumWidth(420)
        self.setStyleSheet(_DIALOG_STYLE)
        self._choice = self.CANCEL

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # Blue header
        root.addWidget(_make_header("Planning Wizard"))

        # Body
        body = QWidget()
        body.setStyleSheet("background: white;")
        bl = QVBoxLayout(body)
        bl.setContentsMargins(16, 14, 16, 6)
        bl.setSpacing(10)

        info = QLabel(
            f"You moved <b>'{task_name}'</b> to start on a non-working day "
            f"(<b>{raw_date_str}</b>)."
        )
        info.setWordWrap(True)
        info.setStyleSheet("font-size: 12px; color: #1F1F1F;")
        bl.addWidget(info)

        you_can = QLabel("You can:")
        you_can.setStyleSheet("font-size: 12px; font-weight: bold; color: #1F1F1F;")
        bl.addWidget(you_can)

        # Radio-button group inside a dashed frame (like MS Project)
        frame = QFrame()
        frame.setFrameShape(QFrame.Box)
        frame.setStyleSheet("QFrame { border: 1px dashed #9AB0D0; border-radius: 3px; background: #F5F9FF; }")
        fl = QVBoxLayout(frame)
        fl.setContentsMargins(12, 8, 12, 8)
        fl.setSpacing(6)

        from PyQt5.QtWidgets import QRadioButton  # type: ignore
        self._rb_snap = QRadioButton(
            f"Move '{task_name}' to the next working day ({snapped_date_str})"
        )
        self._rb_snap.setChecked(True)
        self._rb_snap.setStyleSheet("font-size: 12px;")

        self._rb_keep = QRadioButton(
            f"Keep '{task_name}' on {raw_date_str} (non-working day)"
        )
        self._rb_keep.setStyleSheet("font-size: 12px;")

        fl.addWidget(self._rb_snap)
        fl.addWidget(self._rb_keep)
        bl.addWidget(frame)
        root.addWidget(body)

        # Button row
        btn_row = QWidget()
        btn_row.setStyleSheet("background: white;")
        bh = QHBoxLayout(btn_row)
        bh.setContentsMargins(12, 4, 12, 14)
        bh.addStretch()

        ok_btn = QPushButton("OK")
        ok_btn.setDefault(True)
        ok_btn.setStyleSheet(_BUTTON_STYLE)
        ok_btn.clicked.connect(self._on_ok)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(_BUTTON_STYLE)
        cancel_btn.clicked.connect(self.reject)

        bh.addWidget(ok_btn)
        bh.addWidget(cancel_btn)
        root.addWidget(btn_row)

    def _on_ok(self):
        self._choice = self.SNAP if self._rb_snap.isChecked() else self.KEEP
        self.accept()

    def choice(self) -> str:
        return self._choice


# ------------------------------------------------------------------ #
# Schedule propagation helper                                          #
# ------------------------------------------------------------------ #

def _propagate_schedule(all_tasks, changed_deltas):
    """Shift successor tasks when predecessor finish dates change.

    changed_deltas: {task_unique_id (int): delta_days (int)}

    Relation-type rules (we only changed predecessor FINISH):
      FS (Finish→Start): succ_start = pred_finish + lag  → propagate delta ✓
      FF (Finish→Finish): succ_finish = pred_finish + lag → propagate delta ✓
      SS (Start→Start):  succ_start = pred_start + lag   → pred_start unchanged, skip
      SF (Start→Finish): succ_finish = pred_start + lag  → pred_start unchanged, skip
    """
    from collections import deque

    # Build uid -> task map
    uid_to_task = {}
    for t in all_tasks:
        if t.getName() is not None:
            try:
                uid_to_task[int(str(t.getUniqueID()))] = t
            except Exception:
                pass

    # Build successor map: pred_uid -> list of (succ_uid, relation_type_str)
    succ_map = {}
    for t in all_tasks:
        if t.getName() is None:
            continue
        try:
            preds = t.getPredecessors()
        except Exception:
            continue
        if preds is None:
            continue
        for rel in preds:
            pred_task = rel.getPredecessorTask()
            if pred_task is None:
                continue
            try:
                pred_uid = int(str(pred_task.getUniqueID()))
                succ_uid = int(str(t.getUniqueID()))
            except Exception:
                continue
            try:
                rel_type = str(rel.getType())  # e.g. "FINISH_START"
            except Exception:
                rel_type = "FINISH_START"
            succ_map.setdefault(pred_uid, []).append((succ_uid, rel_type))

    # BFS: propagate deltas forward only for FS and FF relations
    queue = deque(changed_deltas.items())
    visited = set()
    while queue:
        pred_uid, delta = queue.popleft()
        if pred_uid in visited or delta == 0:
            continue
        visited.add(pred_uid)
        for succ_uid, rel_type in succ_map.get(pred_uid, []):
            # SS and SF depend on predecessor START which we didn't change → skip
            if rel_type in ("SS", "SF", "START_START", "START_FINISH"):
                continue
            succ = uid_to_task.get(succ_uid)
            if succ is None:
                continue
            s = succ.getStart()
            f = succ.getFinish()
            if s is None or f is None:
                continue
            succ.setStart(s.plusDays(delta))
            succ.setFinish(f.plusDays(delta))
            queue.append((succ_uid, delta))


# ------------------------------------------------------------------ #
# Custom field write-back helper                                       #
# ------------------------------------------------------------------ #

def _set_cf_value(entity, ft, text):
    """Write a custom-field value back to an MPXJ task/resource.

    Converts the plain-text string from the dialog table to the Java type
    expected by the field.  An empty string clears the field (sets None).
    """
    try:
        if not text:
            entity.set(ft, None)
            return
        try:
            dt = str(ft.getDataType())
        except Exception:
            dt = "STRING"
        dt = dt.upper()
        if "NUMERIC" in dt or "CURRENCY" in dt or "PERCENTAGE" in dt:
            from java.lang import Double  # type: ignore
            entity.set(ft, Double.valueOf(float(text)))
        elif "INTEGER" in dt:
            from java.lang import Integer  # type: ignore
            entity.set(ft, Integer.valueOf(int(text)))
        elif "BOOLEAN" in dt:
            from java.lang import Boolean  # type: ignore
            entity.set(ft, Boolean.valueOf(text.lower() in ("true", "yes", "1")))
        else:
            # STRING, TEXT, DATE (as text), DURATION (as text), unknown → string
            entity.set(ft, text)
    except Exception as e:
        print(f"[WARN] _set_cf_value: {e}")


# Common custom-field slot names shared by TaskField and ResourceField
_CF_SLOTS = (
    [(f"Text{i}",     f"TEXT{i}")     for i in range(1, 31)] +
    [(f"Number{i}",   f"NUMBER{i}")   for i in range(1, 21)] +
    [(f"Cost{i}",     f"COST{i}")     for i in range(1, 11)] +
    [(f"Date{i}",     f"DATE{i}")     for i in range(1, 11)] +
    [(f"Flag{i}",     f"FLAG{i}")     for i in range(1, 21)] +
    [(f"Duration{i}", f"DURATION{i}") for i in range(1, 11)]
)


def _build_cf_slot_combo(combo, java_class_name, used_fts):
    """Populate *combo* with custom-field slots not yet used in the table.

    Returns a list of (display_name, java_FieldType) for the items added.
    """
    import jpype  # type: ignore
    items = []
    try:
        FT = jpype.JClass(java_class_name)
        for display, attr in _CF_SLOTS:
            try:
                ft = getattr(FT, attr)
                if str(ft) in used_fts:
                    continue
                items.append((display, ft))
                combo.addItem(display)
            except Exception:
                pass
    except Exception as e:
        print(f"[WARN] _build_cf_slot_combo: {e}")
    return items


# ------------------------------------------------------------------ #
# Task Information                                                     #
# ------------------------------------------------------------------ #
# Assignment Details (opened from TaskDialog Resources tab)            #
# ------------------------------------------------------------------ #

class AssignmentDetailDialog(_BaseDialog):
    """Detail view / editor for a single ResourceAssignment."""

    def __init__(self, assignment, task_name, parent=None):
        super().__init__("Assignment Details", parent)
        self._ass = assignment
        self.setMinimumWidth(460)
        self.setMinimumHeight(400)

        res_name = "?"
        try:
            res = assignment.getResource()
            if res is not None:
                res_name = str(res.getName() or "?")
        except Exception:
            pass

        self._root.addWidget(_make_header("Assignment Details",
                                          f"{res_name}  \u2192  {task_name}"))

        tabs = QTabWidget()
        tabs.addTab(self._tab_general(), "General")
        tabs.addTab(self._tab_notes(),   "Notes")

        body = QWidget()
        bv = QVBoxLayout(body)
        bv.setContentsMargins(12, 12, 12, 0)
        bv.addWidget(tabs)
        self._root.addWidget(body)
        self._root.addWidget(_make_button_row(self))

    def _tab_general(self):
        ass = self._ass
        w = QWidget()
        f = QFormLayout(w)
        f.setContentsMargins(16, 16, 16, 16)
        f.setSpacing(8)

        def _val(getter):
            try:
                v = getter()
                return str(v) if v is not None else ""
            except Exception:
                return ""

        def _ro(text=""):
            le = QLineEdit(text)
            le.setReadOnly(True)
            return le

        self._e_units = QLineEdit(_val(ass.getUnits))
        f.addRow("Units %:", self._e_units)
        f.addRow("Start:",           _ro(_val(ass.getStart)))
        f.addRow("Finish:",          _ro(_val(ass.getFinish)))
        f.addRow("Actual Start:",    _ro(_val(ass.getActualStart)))
        f.addRow("Actual Finish:",   _ro(_val(ass.getActualFinish)))
        f.addRow("Work:",            _ro(_val(ass.getWork)))
        f.addRow("Actual Work:",     _ro(_val(ass.getActualWork)))
        f.addRow("Remaining Work:",  _ro(_val(ass.getRemainingWork)))
        f.addRow("% Work Complete:", _ro(_val(ass.getPercentageWorkComplete)))
        f.addRow("Cost:",            _ro(_val(ass.getCost)))
        f.addRow("Actual Cost:",     _ro(_val(ass.getActualCost)))
        return w

    def _tab_notes(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(8, 8, 8, 8)
        self._notes_edit = QTextEdit()
        try:
            n = self._ass.getNotes()
            self._notes_edit.setPlainText(str(n) if n else "")
        except Exception:
            pass
        v.addWidget(self._notes_edit)
        return w

    def get_units(self):
        try:
            return float(self._e_units.text().strip() or "100")
        except ValueError:
            return 100.0

    def get_notes(self):
        return self._notes_edit.toPlainText()


# ------------------------------------------------------------------ #

class TaskDialog(_BaseDialog):
    """Task Information dialog with General / Predecessors / Resources / Notes tabs."""

    def __init__(self, task, project, parent=None, timeline_view=None, critical_ids=None,
                 float_data: dict | None = None,
                 task_jira_data: dict | None = None):
        super().__init__("Task Information", parent)
        self._task = task
        self._project = project
        self._timeline_view = timeline_view
        self._critical_ids = critical_ids  # CPM-calculated set of int task IDs
        self._float_data   = float_data or {}
        self._task_jira_data = task_jira_data or {}
        # list of (resource_java_obj_or_None, units_float) for pending assignments
        self._pending_assignments = []
        # row → java ResourceAssignment (existing assignments only, for detail view)
        self._assignment_java_objects = {}
        # per-resource detail data (notes, etc.) keyed by resource unique ID
        self._assignment_detail_data = {}
        # list of (row_index, java_FieldType) for the Custom Fields tab
        self._custom_field_types = []
        self.setMinimumWidth(580)
        self.setMinimumHeight(460)
        name = str(task.getName()) if task.getName() is not None else ""
        self._root.addWidget(_make_header("Task Information", name))

        tabs = QTabWidget()
        tabs.addTab(self._tab_general(), "General")
        tabs.addTab(self._tab_predecessors(), "Predecessors")
        tabs.addTab(self._tab_resources(), "Resources")
        tabs.addTab(self._tab_custom_fields(), "Custom Fields")
        tabs.addTab(self._tab_notes(), "Notes")
        tabs.addTab(self._tab_schedule(), "Schedule")
        tabs.addTab(self._tab_jira(), "Jira")

        body = QWidget()
        bv = QVBoxLayout(body)
        bv.setContentsMargins(12, 12, 12, 0)
        bv.addWidget(tabs)
        self._root.addWidget(body)
        self._root.addWidget(_make_button_row(self))

    # -- tabs --

    def _tab_general(self):
        t = self._task
        w = QWidget()
        f = QFormLayout(w)
        f.setContentsMargins(12, 12, 12, 12)
        f.setSpacing(10)

        self._e_name = QLineEdit(str(t.getName()) if t.getName() is not None else "")
        f.addRow("Name:", self._e_name)

        self._e_dur = QLineEdit(str(t.getDuration()) if t.getDuration() is not None else "")
        f.addRow("Duration:", self._e_dur)

        self._e_start = QLineEdit(str(t.getStart()) if t.getStart() is not None else "")
        self._e_start.setReadOnly(True)
        f.addRow("Start:", self._e_start)

        self._e_finish = QLineEdit(str(t.getFinish()) if t.getFinish() is not None else "")
        self._e_finish.setReadOnly(True)
        f.addRow("Finish:", self._e_finish)

        pct_raw = str(t.getPercentageComplete()) if t.getPercentageComplete() is not None else "0"
        self._e_pct = QLineEdit(pct_raw.replace('%', '').strip())
        f.addRow("% Complete:", self._e_pct)

        try:
            is_milestone = bool(t.getMilestone())
        except Exception:
            is_milestone = False
        self._cb_milestone = QCheckBox()
        self._cb_milestone.setChecked(is_milestone)
        f.addRow("Milestone:", self._cb_milestone)

        is_critical = False
        if self._critical_ids is not None:
            try:
                tid = int(str(t.getID()))
                is_critical = tid in self._critical_ids
            except Exception:
                pass
        elif t.getCritical():
            # Fallback when no CPM set is provided
            try:
                pct_raw = t.getPercentageComplete()
                pct_val = float(str(pct_raw).replace('%', '').strip()) if pct_raw is not None else 0.0
                is_critical = pct_val < 100.0
            except Exception:
                is_critical = True
        crit_lbl = QLabel("Yes" if is_critical else "No")
        crit_lbl.setStyleSheet("color: #CC0000; font-weight: bold;" if is_critical else "color: #1F1F1F;")
        f.addRow("Critical:", crit_lbl)

        # Timeline checkbox — only shown when a timeline_view reference was passed in
        self._cb_timeline = None
        if self._timeline_view is not None:
            try:
                tid = int(str(t.getID()))
                is_pinned = (
                    self._timeline_view.is_task_pinned(tid)
                    or self._timeline_view.is_milestone_pinned(tid)
                )
            except Exception:
                is_pinned = False
            self._cb_timeline = QCheckBox()
            self._cb_timeline.setChecked(is_pinned)
            self._cb_timeline.setToolTip(
                "When checked, this task/milestone is shown on the Timeline strip"
            )
            f.addRow("Show in Timeline:", self._cb_timeline)

        return w

    def _tab_predecessors(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(8, 8, 8, 8)
        v.setSpacing(6)

        # Build task name → java object map (excluding self)
        self._pred_task_map = {}   # display_name → java task
        try:
            for t in self._project.getTasks():
                if t.getName() is None:
                    continue
                if int(str(t.getUniqueID())) == int(str(self._task.getUniqueID())):
                    continue
                display = f"{t.getID()} – {t.getName()}"
                self._pred_task_map[display] = t
        except Exception:
            pass

        _LINK_TYPES = ["FINISH_START", "START_START", "FINISH_FINISH", "START_FINISH"]
        _LINK_SHORT = {"FINISH_START": "FS", "START_START": "SS",
                       "FINISH_FINISH": "FF", "START_FINISH": "SF"}

        # Table: ID | Task Name | Type | Lag
        self._pred_tbl = QTableWidget()
        self._pred_tbl.setColumnCount(4)
        self._pred_tbl.setHorizontalHeaderLabels(["ID", "Task Name", "Type", "Lag (d)"])
        self._pred_tbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._pred_tbl.setColumnWidth(0, 40)
        self._pred_tbl.setColumnWidth(2, 110)
        self._pred_tbl.setColumnWidth(3, 72)
        self._pred_tbl.setSelectionBehavior(QTableWidget.SelectRows)
        self._pred_tbl.setAlternatingRowColors(True)
        self._pred_tbl.verticalHeader().setVisible(False)
        self._pred_tbl.verticalHeader().setDefaultSectionSize(24)

        def _add_pred_row(pred_display="", rel_type="FINISH_START", lag_d=0.0):
            row = self._pred_tbl.rowCount()
            self._pred_tbl.setRowCount(row + 1)

            # ID (derived from combo choice, read-only label)
            id_item = QTableWidgetItem("")
            id_item.setFlags(Qt.ItemIsEnabled)
            self._pred_tbl.setItem(row, 0, id_item)

            # Task name combo
            combo = QComboBox()
            combo.addItem("")
            combo.addItems(sorted(self._pred_task_map.keys()))
            if pred_display in self._pred_task_map:
                combo.setCurrentText(pred_display)
                t = self._pred_task_map[pred_display]
                id_item.setText(str(t.getID()) if t.getID() is not None else "")
            def _on_combo(text, r=row):
                t = self._pred_task_map.get(text)
                self._pred_tbl.item(r, 0).setText(
                    str(t.getID()) if t and t.getID() is not None else "")
            combo.currentTextChanged.connect(_on_combo)
            self._pred_tbl.setCellWidget(row, 1, combo)

            # Type combo
            _TYPE_TOOLTIP = (
                "FS – Finish to Start: successor starts after predecessor finishes\n"
                "SS – Start to Start: successor starts when predecessor starts\n"
                "FF – Finish to Finish: successor finishes when predecessor finishes\n"
                "SF – Start to Finish: successor finishes when predecessor starts"
            )
            type_combo = QComboBox()
            type_combo.addItems([_LINK_SHORT[k] for k in _LINK_TYPES])
            type_combo.setToolTip(_TYPE_TOOLTIP)
            short = _LINK_SHORT.get(rel_type, "FS")
            type_combo.setCurrentText(short)
            self._pred_tbl.setCellWidget(row, 2, type_combo)

            # Lag
            lag_item = QTableWidgetItem(f"{lag_d:.1f}")
            self._pred_tbl.setItem(row, 3, lag_item)

        # Populate existing predecessors
        try:
            preds = self._task.getPredecessors()
            if preds:
                for rel in preds:
                    pt = rel.getPredecessorTask()
                    if pt is None:
                        continue
                    display = f"{pt.getID()} – {pt.getName()}"
                    try:
                        rel_type = str(rel.getType())
                    except Exception:
                        rel_type = "FINISH_START"
                    try:
                        lag_raw = rel.getLag()
                        lag_d = float(str(lag_raw.getDuration())) if lag_raw is not None else 0.0
                    except Exception:
                        lag_d = 0.0
                    _add_pred_row(display, rel_type, lag_d)
        except Exception:
            pass

        self._add_pred_row_fn = _add_pred_row
        v.addWidget(self._pred_tbl)

        # Add / Remove buttons
        btn_row = QWidget()
        bh = QHBoxLayout(btn_row)
        bh.setContentsMargins(0, 0, 0, 0)
        bh.setSpacing(6)
        add_btn = QPushButton("Add")
        add_btn.setStyleSheet(_BUTTON_STYLE)
        add_btn.setFixedWidth(60)
        add_btn.clicked.connect(lambda: _add_pred_row())
        bh.addWidget(add_btn)
        rem_btn = QPushButton("Remove")
        rem_btn.setStyleSheet(_BUTTON_STYLE)
        rem_btn.setFixedWidth(72)
        rem_btn.clicked.connect(self._remove_pred_row)
        bh.addWidget(rem_btn)
        bh.addStretch()
        v.addWidget(btn_row)
        return w

    def _remove_pred_row(self):
        rows = sorted(set(i.row() for i in self._pred_tbl.selectedIndexes()), reverse=True)
        for row in rows:
            self._pred_tbl.removeRow(row)

    def _tab_notes(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(8, 8, 8, 8)
        self._notes = QTextEdit()
        try:
            notes = self._task.getNotes()
            self._notes.setPlainText(str(notes) if notes else "")
        except Exception:
            pass
        v.addWidget(self._notes)
        return w

    def _tab_schedule(self):
        """Read-only CPM schedule data (Early/Late dates + float) for this task."""
        from PyQt5.QtWidgets import QFormLayout, QLabel, QFrame  # type: ignore
        from PyQt5.QtCore import Qt  # type: ignore
        w = QWidget()
        form = QFormLayout(w)
        form.setContentsMargins(12, 12, 12, 12)
        form.setSpacing(8)

        def _ro(text: str) -> QLabel:
            lbl = QLabel(text)
            lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
            return lbl

        # Look up CPM data for this task
        tid = None
        fd  = None
        try:
            tid = int(str(self._task.getID()))
            fd  = self._float_data.get(tid)
        except Exception:
            pass

        def _dt(v) -> str:
            try:
                return str(v)[:10] if v else "—"
            except Exception:
                return "—"

        def _td_d(v) -> str:
            try:
                if v is None:
                    return "—"
                days = round(v.total_seconds() / 3600 / 8.0, 1)
                return f"{days}d"
            except Exception:
                return "—"

        def _td_d_wh(data, key_wh, key_td) -> str:
            """Prefer Phase 5 calendar-aware working hours over timedelta fallback."""
            wh = data.get(key_wh) if data else None
            if wh is not None:
                row_wdh = max(data.get("work_day_hours") or 8.0, 1.0)
                return f"{round(float(wh) / row_wdh, 1)}d"
            return _td_d(data.get(key_td) if data else None)

        if fd:
            form.addRow("Early Start:",   _ro(_dt(fd.get("es"))))
            form.addRow("Early Finish:",  _ro(_dt(fd.get("ef"))))
            sep = QFrame(); sep.setFrameShape(QFrame.HLine); sep.setFrameShadow(QFrame.Sunken)
            form.addRow(sep)
            form.addRow("Late Start:",    _ro(_dt(fd.get("ls"))))
            form.addRow("Late Finish:",   _ro(_dt(fd.get("lf"))))
            sep2 = QFrame(); sep2.setFrameShape(QFrame.HLine); sep2.setFrameShadow(QFrame.Sunken)
            form.addRow(sep2)
            form.addRow("Total Float:",   _ro(_td_d_wh(fd, "total_float_wh", "total_float")))
            form.addRow("Free Float:",    _ro(_td_d_wh(fd, "free_float_wh", "free_float")))
            is_crit = fd.get("critical")
            status_lbl = _ro("CRITICAL" if is_crit else "OK")
            if is_crit:
                status_lbl.setStyleSheet("color: #C0392B; font-weight: bold;")
            form.addRow("CPM Status:", status_lbl)
        else:
            form.addRow(QLabel("No CPM data available for this task.\n"
                               "Open a project with tasks and dependencies."))
        return w

    def _tab_jira(self):
        """Read-only Jira metadata tab (populated from the sidecar .custom-props.json)."""
        from PyQt5.QtWidgets import QFormLayout, QLabel  # type: ignore
        from PyQt5.QtCore import Qt  # type: ignore
        w = QWidget()
        f = QFormLayout(w)
        f.setContentsMargins(12, 12, 12, 12)
        f.setSpacing(10)

        d = self._task_jira_data

        def _ro(text: str) -> QLineEdit:
            le = QLineEdit(text)
            le.setReadOnly(True)
            return le

        if not d:
            lbl = QLabel("No Jira data linked to this task.\n\nRun \u2018Sync from Jira\u2019 to import tickets.")
            lbl.setWordWrap(True)
            lbl.setStyleSheet("color: #808080;")
            f.addRow(lbl)
            return w

        jira_key = d.get("jira_key", "")
        f.addRow("Jira Key:", _ro(jira_key))
        f.addRow("Status:", _ro(d.get("jira_status", "")))

        # Build a clickable URL if a server URL can be determined from the project
        url = ""
        try:
            import json as _json
            cp = self._project.getProjectProperties().getCustomProperties()
            if cp is not None:
                raw = cp.get("jira2project")
                if raw:
                    j2p = _json.loads(str(raw))
                    server_name = j2p.get("server", "")
                    from integrations import settings_manager as _sm_mod  # type: ignore
                    sm = _sm_mod.get_instance() if hasattr(_sm_mod, "get_instance") else None
                    if sm is not None:
                        servers = sm.get_jira_servers() if hasattr(sm, "get_jira_servers") else []
                        srv = next((s for s in servers if s.get("name") == server_name), None)
                        if srv is None and servers:
                            srv = servers[0]
                        if srv:
                            base = str(srv.get("url", "")).rstrip("/")
                            if base and jira_key:
                                url = f"{base}/browse/{jira_key}"
        except Exception:
            pass

        if url:
            link = QLabel(f'<a href="{url}">{url}</a>')
            link.setOpenExternalLinks(True)
            link.setTextFormat(Qt.RichText)
            f.addRow("Link:", link)

        return w

    def _tab_custom_fields(self):
        """Show task custom fields (defined in Project Information). Value column is editable."""
        w = QWidget()
        vbox = QVBoxLayout(w)
        vbox.setContentsMargins(12, 12, 12, 12)
        vbox.setSpacing(6)

        hint = QLabel(
            "Field definitions and aliases are managed in "
            "<b>Project Information → Custom Fields → Task Fields</b>."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #808080; font-size: 10px;")
        vbox.addWidget(hint)

        tbl = QTableWidget(0, 2)
        tbl.setHorizontalHeaderLabels(["Field (Alias)", "Value"])
        tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.Interactive)
        tbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        tbl.horizontalHeader().resizeSection(0, 160)
        tbl.setAlternatingRowColors(True)
        tbl.verticalHeader().setVisible(False)
        tbl.verticalHeader().setDefaultSectionSize(22)
        tbl.setEditTriggers(QTableWidget.DoubleClicked | QTableWidget.EditKeyPressed)
        self._cf_tbl = tbl

        try:
            from org.mpxj import FieldTypeClass  # type: ignore
            for cf in self._project.getCustomFields():
                ft = cf.getFieldType()
                if ft is None:
                    continue
                try:
                    is_task = ft.getFieldTypeClass() == FieldTypeClass.TASK
                except Exception:
                    is_task = "Task" in str(ft.getClass().getSimpleName())
                if not is_task:
                    continue
                alias = str(cf.getAlias()) if cf.getAlias() else str(ft)
                try:
                    val = self._task.get(ft)
                except Exception:
                    val = None
                val_str = str(val) if val is not None else ""
                row = tbl.rowCount()
                tbl.insertRow(row)
                name_item = QTableWidgetItem(alias)
                name_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                tbl.setItem(row, 0, name_item)
                tbl.setItem(row, 1, QTableWidgetItem(val_str))
                self._custom_field_types.append((row, ft))
        except Exception as e:
            print(f"[WARN] task custom fields load: {e}")

        if tbl.rowCount() == 0:
            vbox.addWidget(QLabel("No custom fields defined. Add them in Project Information."))
        vbox.addWidget(tbl)
        return w

    def _tab_resources(self):
        """Resources tab – list assignments, allow add / remove."""
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(8, 8, 8, 8)
        v.setSpacing(6)

        # Build resource name → java object map for the project
        self._res_map = {}   # name → java resource
        try:
            for res in self._project.getResources():
                n = str(res.getName()) if res.getName() is not None else ""
                if n:
                    self._res_map[n] = res
        except Exception:
            pass

        # Table: Name | Units (%) | (delete)
        self._res_tbl = QTableWidget()
        self._res_tbl.setColumnCount(3)
        self._res_tbl.setHorizontalHeaderLabels(["Resource Name", "Units (%)", ""])
        self._res_tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._res_tbl.setColumnWidth(1, 90)
        self._res_tbl.setColumnWidth(2, 30)
        self._res_tbl.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self._res_tbl.setEditTriggers(QTableWidget.NoEditTriggers)
        self._res_tbl.setSelectionBehavior(QTableWidget.SelectRows)
        self._res_tbl.setAlternatingRowColors(True)
        self._res_tbl.verticalHeader().setVisible(False)
        self._res_tbl.verticalHeader().setDefaultSectionSize(24)

        # Track delete-button objects in a list parallel to _pending_assignments
        # so _delete_assignment_row can reliably find the right row via identity.
        self._del_btns: list = []

        # Populate from existing assignments
        try:
            for ass in self._task.getResourceAssignments():
                res = ass.getResource()
                rname = str(res.getName()) if res and res.getName() is not None else "(unknown)"
                raw_u = ass.getUnits()
                units_pct = float(str(raw_u)) if raw_u is not None else 100.0
                self._pending_assignments.append((res, units_pct))
                r = self._res_tbl.rowCount()
                self._res_tbl.setRowCount(r + 1)
                self._res_tbl.setItem(r, 0, QTableWidgetItem(rname))
                self._res_tbl.setItem(r, 1, QTableWidgetItem(f"{units_pct:.0f}"))
                self._assignment_java_objects[r] = ass  # track for detail dialog
                btn = self._make_delete_btn()
                self._res_tbl.setCellWidget(r, 2, btn)
                self._del_btns.append(btn)
        except Exception:
            pass

        self._res_tbl.cellDoubleClicked.connect(self._open_assignment_detail)

        v.addWidget(self._res_tbl)

        # Add row (no separate "Remove" button — each row has its own ✕)
        btn_row = QWidget()
        bh = QHBoxLayout(btn_row)
        bh.setContentsMargins(0, 0, 0, 0)
        bh.setSpacing(6)

        # Resource picker combo
        self._res_combo = QComboBox()
        self._res_combo.addItems(sorted(self._res_map.keys()))
        self._res_combo.setMinimumWidth(180)
        bh.addWidget(self._res_combo, 1)

        # Units input
        self._units_edit = QLineEdit("100")
        self._units_edit.setFixedWidth(60)
        self._units_edit.setPlaceholderText("Units %")
        bh.addWidget(QLabel("Units %:"))
        bh.addWidget(self._units_edit)

        add_btn = QPushButton("Add")
        add_btn.setStyleSheet(_BUTTON_STYLE)
        add_btn.setFixedWidth(60)
        add_btn.clicked.connect(self._add_assignment_row)
        bh.addWidget(add_btn)

        v.addWidget(btn_row)
        return w

    def _make_delete_btn(self) -> "QPushButton":
        """Return a small ✕ button for inline deletion of an assignment row."""
        btn = QPushButton("✕")
        btn.setFlat(True)
        btn.setFixedSize(24, 20)
        btn.setStyleSheet(
            "QPushButton { color:#cc3333; font-weight:bold; border:none;"
            "              background:transparent; }"
            "QPushButton:hover { color:#ff0000; }"
        )
        btn.setToolTip("Remove this resource assignment")
        btn.clicked.connect(self._delete_assignment_row)
        return btn

    def _add_assignment_row(self):
        name = self._res_combo.currentText()
        if not name:
            return
        # Primary lookup by exact key; fallback to case-insensitive scan in
        # case Qt's text() and the dict key differ in subtle ways (e.g. whitespace).
        res = self._res_map.get(name)
        if res is None:
            name_stripped = name.strip()
            for k, v in self._res_map.items():
                if k.strip() == name_stripped:
                    res = v
                    break
        if res is None:
            # Resource not found in map – do NOT add a null-resource row.
            import app_debug  # type: ignore
            if app_debug.is_debug():
                print(f"[TaskDialog] _add_assignment_row: resource '{name}' not in _res_map, ignoring")
            return
        try:
            units_pct = float(self._units_edit.text().strip() or "100")
        except ValueError:
            units_pct = 100.0
        # Prevent duplicate resource in the same task
        for i in range(self._res_tbl.rowCount()):
            item = self._res_tbl.item(i, 0)
            if item is not None and item.text() == name:
                return
        r = self._res_tbl.rowCount()
        self._res_tbl.setRowCount(r + 1)
        self._res_tbl.setItem(r, 0, QTableWidgetItem(name))
        self._res_tbl.setItem(r, 1, QTableWidgetItem(f"{units_pct:.0f}"))
        btn = self._make_delete_btn()
        self._res_tbl.setCellWidget(r, 2, btn)
        self._del_btns.append(btn)
        self._pending_assignments.append((res, units_pct))

    def _delete_assignment_row(self):
        """Remove the assignment row whose ✕ button was clicked."""
        btn = self.sender()
        # Find row using the _del_btns list (Python identity, not cellWidget which
        # may return a different wrapper object in some PyQt5 versions).
        row = -1
        for i, b in enumerate(self._del_btns):
            if b is btn:
                row = i
                break
        if row < 0:
            # Fallback: scan by cellWidget identity
            for r in range(self._res_tbl.rowCount()):
                if self._res_tbl.cellWidget(r, 2) is btn:
                    row = r
                    break
        if row < 0:
            return
        self._res_tbl.removeRow(row)
        if row < len(self._pending_assignments):
            self._pending_assignments.pop(row)
        if row < len(self._del_btns):
            self._del_btns.pop(row)
        # Shift _assignment_java_objects keys for rows after the deleted one
        new_java = {}
        for k, v in self._assignment_java_objects.items():
            if k == row:
                continue
            new_java[k - 1 if k > row else k] = v
        self._assignment_java_objects = new_java

    def _remove_assignment_row(self):
        rows = sorted(set(i.row() for i in self._res_tbl.selectedIndexes()), reverse=True)
        for row in rows:
            self._res_tbl.removeRow(row)
            if row < len(self._pending_assignments):
                self._pending_assignments.pop(row)

    def _open_assignment_detail(self, row, col):
        """Open AssignmentDetailDialog when user double-clicks an existing assignment row."""
        if col == 2:
            return  # ignore clicks on the delete-button column
        ass = self._assignment_java_objects.get(row)
        if ass is None:
            return  # newly-added row, not yet saved — nothing to show
        task_name = ""
        try:
            task_name = str(self._task.getName() or "")
        except Exception:
            pass
        dlg = AssignmentDetailDialog(ass, task_name, self)
        if dlg.exec_() == QDialog.Accepted:
            new_units = dlg.get_units()
            ui = self._res_tbl.item(row, 1)
            if ui is not None:
                ui.setText(f"{new_units:.0f}")
            try:
                res = ass.getResource()
                if res is not None:
                    res_uid = int(res.getUniqueID()) if res.getUniqueID() is not None else None
                    if res_uid is not None:
                        self._assignment_detail_data[res_uid] = {
                            "notes": dlg.get_notes(),
                            "units": new_units,
                        }
            except Exception as e:
                print(f"[WARN] assignment detail store: {e}")

    def apply_to_task(self):
        t = self._task
        try:
            t.setName(self._e_name.text().strip())
            dur_str = "".join(c for c in self._e_dur.text() if c.isdigit() or c == '.')
            if dur_str:
                from org.mpxj import Duration, TimeUnit  # type: ignore
                t.setDuration(Duration.getInstance(float(dur_str), TimeUnit.DAYS))
            pct_str = self._e_pct.text().strip()
            if pct_str:
                from java.lang import Double  # type: ignore
                new_pct = float(pct_str)
                t.setPercentageComplete(Double.valueOf(new_pct))
                # If reverted below 100%, clear any stale actualFinish that
                # MPXJ may have auto-set when the task was previously at 100%.
                if new_pct < 100.0:
                    try:
                        t.setActualFinish(None)
                    except Exception:
                        pass
            try:
                t.setNotes(self._notes.toPlainText())
            except Exception:
                pass
        except Exception as e:
            print(f"[WARN] TaskDialog.apply: {e}")

        # Sync resource assignments from the Resources tab table.
        # Use _pending_assignments for the resource Java object (avoids
        # unreliable name-based lookup via _res_map) and the table's units
        # cell for the units value (updated live by AssignmentDetailDialog).
        try:
            from java.lang import Double  # type: ignore
            import app_debug  # type: ignore
            _dbg = app_debug.is_debug()
            # Remove all existing assignments
            for ass in list(t.getResourceAssignments()):
                try:
                    ass.remove()
                except Exception:
                    pass
            # Rebuild from current table rows
            for row in range(self._res_tbl.rowCount()):
                units_item = self._res_tbl.item(row, 1)
                # Get resource object from _pending_assignments (kept in sync
                # with table rows by _add_assignment_row / _delete_assignment_row)
                if row >= len(self._pending_assignments):
                    if _dbg:
                        print(f"[TaskDialog] apply: row {row} out of _pending_assignments range ({len(self._pending_assignments)})")
                    continue
                res = self._pending_assignments[row][0]
                if res is None:
                    # Attempt fallback: look up by name from table
                    name_item = self._res_tbl.item(row, 0)
                    if name_item is not None:
                        res = self._res_map.get(name_item.text())
                    if _dbg:
                        print(f"[TaskDialog] apply: row {row} had None res; fallback={'found' if res else 'failed'}")
                if res is None:
                    if _dbg:
                        name_item = self._res_tbl.item(row, 0)
                        print(f"[TaskDialog] apply: skipping row {row} '{name_item.text() if name_item else '?'}' – resource not resolved")
                    continue
                try:
                    units_pct = float(units_item.text()) if units_item else 100.0
                except ValueError:
                    units_pct = 100.0
                if _dbg:
                    try:
                        ruid = res.getUniqueID()
                        rname = res.getName()
                    except Exception:
                        ruid, rname = '?', '?'
                    print(f"[TaskDialog] apply: addResourceAssignment uid={ruid} name={rname} units={units_pct}")
                ass = t.addResourceAssignment(res)
                ass.setUnits(Double.valueOf(units_pct))
                # Restore assignment notes from AssignmentDetailDialog if any
                try:
                    res_uid = int(res.getUniqueID()) if res.getUniqueID() is not None else None
                    if res_uid is not None and res_uid in self._assignment_detail_data:
                        notes = self._assignment_detail_data[res_uid].get("notes", "")
                        if notes:
                            ass.setNotes(notes)
                except Exception:
                    pass
        except Exception as e:
            print(f"[WARN] TaskDialog.apply assignments: {e}")

        # Apply timeline checkbox state (add/remove from timeline)
        if self._cb_timeline is not None and self._timeline_view is not None:
            try:
                tid = int(str(self._task.getID()))
                want_pinned = self._cb_timeline.isChecked()
                try:
                    is_ms = bool(self._task.getMilestone())
                except Exception:
                    is_ms = False
                if want_pinned:
                    if is_ms:
                        self._timeline_view.add_milestone(self._task)
                    else:
                        self._timeline_view.add_task(self._task)
                else:
                    if is_ms:
                        self._timeline_view.remove_milestone(tid)
                    else:
                        self._timeline_view.remove_task(tid)
            except Exception as e:
                print(f"[WARN] TaskDialog.apply timeline: {e}")

        # Sync predecessors from the Predecessors tab table
        _LINK_LONG = {"FS": "FINISH_START", "SS": "START_START",
                      "FF": "FINISH_FINISH", "SF": "START_FINISH"}
        try:
            from org.mpxj import RelationType, Duration, TimeUnit  # type: ignore
            rt_map = {
                "FINISH_START":  RelationType.FINISH_START,
                "START_START":   RelationType.START_START,
                "FINISH_FINISH": RelationType.FINISH_FINISH,
                "START_FINISH":  RelationType.START_FINISH,
            }
            # Remove all existing predecessors
            for rel in list(t.getPredecessors() or []):
                try:
                    t.getPredecessors().remove(rel)
                except Exception:
                    pass
            # Rebuild from table rows
            for row in range(self._pred_tbl.rowCount()):
                combo = self._pred_tbl.cellWidget(row, 1)
                type_combo = self._pred_tbl.cellWidget(row, 2)
                lag_item = self._pred_tbl.item(row, 3)
                if combo is None:
                    continue
                pred_display = combo.currentText()
                pred_task = self._pred_task_map.get(pred_display)
                if pred_task is None:
                    continue
                short = type_combo.currentText() if type_combo else "FS"
                rel_type = rt_map.get(_LINK_LONG.get(short, "FINISH_START"),
                                      RelationType.FINISH_START)
                try:
                    lag_d = float(lag_item.text()) if lag_item else 0.0
                except ValueError:
                    lag_d = 0.0
                import jpype  # type: ignore
                lag_dur = Duration.getInstance(lag_d, TimeUnit.DAYS)
                _RelBuilder = jpype.JClass('org.mpxj.Relation$Builder')
                t.addPredecessor(_RelBuilder().predecessorTask(pred_task).type(rel_type).lag(lag_dur))
        except Exception as e:
            print(f"[WARN] TaskDialog.apply predecessors: {e}")

        # Sync custom field values from the Custom Fields tab
        try:
            for row, ft in self._custom_field_types:
                val_item = self._cf_tbl.item(row, 1)
                val_text = val_item.text().strip() if val_item else ""
                _set_cf_value(self._task, ft, val_text)
        except Exception as e:
            print(f"[WARN] TaskDialog.apply custom fields: {e}")


# ------------------------------------------------------------------ #
# Resource Information                                                 #
# ------------------------------------------------------------------ #

class ResourceDialog(_BaseDialog):
    """Resource Information dialog."""

    _RES_TYPES = ["WORK", "MATERIAL", "COST"]

    # Common country names for the AD tab country dropdown
    _COUNTRIES = [
        "", "Afghanistan", "Albania", "Algeria", "Argentina", "Australia", "Austria",
        "Bangladesh", "Belarus", "Belgium", "Bosnia and Herzegovina", "Brazil", "Bulgaria",
        "Canada", "Chile", "China", "Colombia", "Croatia", "Czech Republic",
        "Denmark", "Egypt", "Estonia", "Ethiopia", "Finland", "France",
        "Germany", "Ghana", "Greece", "Hungary", "India", "Indonesia", "Iran",
        "Iraq", "Ireland", "Israel", "Italy", "Japan", "Jordan", "Kenya",
        "Latvia", "Lebanon", "Lithuania", "Luxembourg", "Malaysia", "Mexico",
        "Morocco", "Netherlands", "New Zealand", "Nigeria", "Norway", "Pakistan",
        "Peru", "Philippines", "Poland", "Portugal", "Romania", "Russia",
        "Saudi Arabia", "Serbia", "Singapore", "Slovakia", "Slovenia",
        "South Africa", "South Korea", "Spain", "Sri Lanka", "Sweden",
        "Switzerland", "Taiwan", "Thailand", "Tunisia", "Turkey", "Ukraine",
        "United Arab Emirates", "United Kingdom", "United States", "Vietnam",
    ]

    def __init__(self, resource, project=None, parent=None):
        super().__init__("Resource Information", parent)
        self._res = resource
        self._project = project
        # list of (row_index, java_FieldType) for the Custom Fields tab
        self._custom_field_types = []
        self.setMinimumHeight(420)
        self.setMinimumWidth(520)
        name = str(resource.getName()) if resource.getName() is not None else ""
        self._root.addWidget(_make_header("Resource Information", name))

        tabs = QTabWidget()
        tabs.addTab(self._tab_general(), "General")
        tabs.addTab(self._tab_active_directory(), "Active Directory")
        tabs.addTab(self._tab_custom_fields(), "Custom Fields")
        tabs.addTab(self._tab_notes(), "Notes")

        body = QWidget()
        bv = QVBoxLayout(body)
        bv.setContentsMargins(12, 12, 12, 0)
        bv.addWidget(tabs)
        self._root.addWidget(body)
        self._root.addWidget(_make_button_row(self))

    def _tab_general(self):
        r = self._res
        w = QWidget()
        outer = QVBoxLayout(w)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Avatar ──────────────────────────────────────────────────
        avatar_row = QWidget()
        avatar_row.setStyleSheet("background: white;")
        ah = QHBoxLayout(avatar_row)
        ah.setContentsMargins(0, 12, 0, 4)
        ah.addStretch()
        self._avatar_lbl = QLabel()
        self._avatar_lbl.setFixedSize(64, 64)
        self._avatar_lbl.setAlignment(Qt.AlignCenter)
        ah.addWidget(self._avatar_lbl)
        ah.addStretch()
        outer.addWidget(avatar_row)

        # ── Form ────────────────────────────────────────────────────
        form_w = QWidget()
        f = QFormLayout(form_w)
        f.setContentsMargins(12, 4, 12, 12)
        f.setSpacing(10)
        outer.addWidget(form_w)

        self._e_name = QLineEdit(str(r.getName()) if r.getName() is not None else "")
        f.addRow("Name:", self._e_name)

        self._e_type = QComboBox()
        self._e_type.addItems(self._RES_TYPES)
        try:
            rt = str(r.getType()) if r.getType() is not None else "WORK"
            idx = next((i for i, x in enumerate(self._RES_TYPES) if x in rt.upper()), 0)
            self._e_type.setCurrentIndex(idx)
        except Exception:
            pass
        f.addRow("Type:", self._e_type)

        _units = r.getMaxUnits()
        # Normalize: MPXJ returns fraction (1.0=100%) for XML, percentage (100.0=100%) for MPP
        if _units is not None:
            _raw = float(str(_units))
            _units_disp = f"{(_raw * 100 if _raw <= 2.0 else _raw):.0f}"
        else:
            _units_disp = "100"
        self._e_units = QLineEdit(_units_disp)
        f.addRow("Max Units (%):", self._e_units)

        self._e_rate = QLineEdit(str(r.getStandardRate()) if r.getStandardRate() is not None else "")
        f.addRow("Standard Rate:", self._e_rate)

        self._e_ot = QLineEdit(str(r.getOvertimeRate()) if r.getOvertimeRate() is not None else "")
        f.addRow("Overtime Rate:", self._e_ot)

        # E-mail field with optional AD lookup button
        try:
            _email_val = str(r.getEmailAddress()) if r.getEmailAddress() is not None else ""
        except Exception:
            _email_val = ""
        self._e_email = QLineEdit(_email_val)
        self._e_email.setPlaceholderText("e.g. john.doe@company.com")
        email_row = QWidget()
        email_h = QHBoxLayout(email_row)
        email_h.setContentsMargins(0, 0, 0, 0)
        email_h.setSpacing(4)
        email_h.addWidget(self._e_email)
        self._ad_lookup_btn = QPushButton("Look up in AD\u2026")
        self._ad_lookup_btn.setFixedWidth(120)
        self._ad_lookup_btn.setToolTip(
            "Search Active Directory by this resource's display name and pre-fill "
            "the e-mail and department fields."
        )
        self._ad_lookup_btn.clicked.connect(self._do_ad_lookup)
        email_h.addWidget(self._ad_lookup_btn)
        self._email_form_row = f.rowCount()
        f.addRow("E-Mail:", email_row)
        self._email_row = email_row

        # Department field – prefer value stored in sidecar, fall back to MPXJ
        try:
            _uid_key = str(r.getUniqueID()) if r.getUniqueID() is not None else ""
        except Exception:
            _uid_key = ""
        _dept_val = _resource_dept_store.get(_uid_key, "")
        if not _dept_val:
            try:
                _dept_val = str(r.getDepartment()) if r.getDepartment() is not None else ""
            except Exception:
                _dept_val = ""
        self._e_dept = QLineEdit(_dept_val)
        self._e_dept.setPlaceholderText("e.g. Engineering")
        self._dept_form_row = f.rowCount()
        f.addRow("Department:", self._e_dept)

        # Store form layout ref for row visibility toggling
        self._f_general = f

        # Connect type changes and initialise avatar + AD button visibility
        self._e_type.currentIndexChanged.connect(self._on_type_changed)
        self._update_ad_btn_visibility()
        self._update_avatar()

        return w

    def _tab_active_directory(self):
        """Active Directory tab — shows and allows editing of AD-sourced attributes."""
        from PyQt5.QtWidgets import QScrollArea, QFrame  # type: ignore
        r = self._res

        # Load AD data: first try in-memory _ad_data attribute, then MPXJ TEXT fields
        ad = {}
        try:
            ad = dict(getattr(r, "_ad_data", {}) or {})
        except Exception:
            pass

        # Helper: read MPXJ resource text field
        def _get_text(field_name: str, default: str = "") -> str:
            try:
                import jpype  # type: ignore
                RF = jpype.JClass("org.mpxj.ResourceField")
                fld = getattr(RF, field_name, None)
                if fld is not None:
                    val = r.get(fld)
                    return str(val) if val is not None else default
            except Exception:
                pass
            return default

        # Prefer _ad_data; fall back to MPXJ email / TEXT fields
        email_val   = ad.get("email", "")       or _get_text("EMAIL_ADDRESS", "")
        city_val    = ad.get("city", "")        or _get_text("TEXT1", "")
        dept_val    = ad.get("department", "")  or _get_text("TEXT2", "")
        country_val = ad.get("country", "")     or _get_text("TEXT3", "")
        username_val = ad.get("username", "")
        dispname_val = ad.get("display_name", "")
        if not email_val:
            try:
                ev = r.getEmailAddress()
                email_val = str(ev) if ev is not None else ""
            except Exception:
                pass

        outer = QWidget()
        outer_v = QVBoxLayout(outer)
        outer_v.setContentsMargins(0, 0, 0, 0)
        outer_v.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        inner = QWidget()
        inner.setStyleSheet("background: white;")
        f = QFormLayout(inner)
        f.setContentsMargins(12, 12, 12, 12)
        f.setSpacing(10)

        # Display Name (read-only — comes from AD)
        self._ad_display_name = QLineEdit(dispname_val)
        self._ad_display_name.setReadOnly(True)
        self._ad_display_name.setStyleSheet("background:#f5f5f5; color:#555;")
        self._ad_display_name.setPlaceholderText("(not imported from AD)")
        f.addRow("AD Display Name:", self._ad_display_name)

        # Username (read-only — SAM account name)
        self._ad_username = QLineEdit(username_val)
        self._ad_username.setReadOnly(True)
        self._ad_username.setStyleSheet("background:#f5f5f5; color:#555;")
        self._ad_username.setPlaceholderText("(not imported from AD)")
        f.addRow("Username:", self._ad_username)

        # E-Mail (editable — saved to MPXJ email field)
        self._ad_email = QLineEdit(email_val)
        self._ad_email.setPlaceholderText("e.g. max.mustermann@company.com")
        f.addRow("E-Mail:", self._ad_email)

        # Department (editable)
        self._ad_dept = QLineEdit(dept_val)
        self._ad_dept.setPlaceholderText("e.g. Engineering")
        f.addRow("Department:", self._ad_dept)

        # City (editable)
        self._ad_city = QLineEdit(city_val)
        self._ad_city.setPlaceholderText("e.g. Stuttgart")
        f.addRow("City:", self._ad_city)

        # Country (editable combobox with common countries)
        self._ad_country = QComboBox()
        self._ad_country.setEditable(True)
        self._ad_country.addItems(self._COUNTRIES)
        if country_val:
            idx = self._ad_country.findText(country_val)
            if idx >= 0:
                self._ad_country.setCurrentIndex(idx)
            else:
                self._ad_country.setCurrentText(country_val)
        else:
            self._ad_country.setCurrentIndex(0)
        self._ad_country.lineEdit().setPlaceholderText("e.g. Germany")
        f.addRow("Country:", self._ad_country)

        # Hint about data source
        hint = QLabel(
            "Fields imported from Active Directory. E-Mail, Department, City, and Country "
            "are editable and saved with the project."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #808080; font-size: 10px;")
        f.addRow(hint)

        scroll.setWidget(inner)
        outer_v.addWidget(scroll)
        return outer

    def _do_ad_lookup(self):
        """Search AD by the resource's current display name and pre-fill email/department."""
        name = self._e_name.text().strip()
        if not name:
            QMessageBox.information(
                self, "AD Lookup",
                "Please enter the resource name before searching Active Directory."
            )
            return

        try:
            from integrations import ad_integration  # type: ignore
        except ImportError:
            QMessageBox.warning(
                self, "AD Lookup",
                "Active Directory integration module is not available."
            )
            return

        if not ad_integration.is_ad_available():
            QMessageBox.warning(
                self, "AD Lookup",
                "Active Directory is not reachable on this machine.\n"
                "Ensure you are on a domain-joined Windows PC with RSAT installed."
            )
            return

        self._ad_lookup_btn.setEnabled(False)
        try:
            try:
                from progress_worker import run_indeterminate  # type: ignore
                results = run_indeterminate(
                    self,
                    f"Searching Active Directory for \u201c{name}\u201d\u2026",
                    lambda: ad_integration.lookup_by_name_all(name),
                )
                if results is None:
                    results = []
            except Exception:
                results = ad_integration.lookup_by_name_all(name)

            if not results:
                QMessageBox.information(
                    self, "AD Lookup",
                    f"No Active Directory entry found for \u201c{name}\u201d."
                )
                return

            # Always show ADUserSelectDialog so the user can confirm (single
            # result) or choose (multiple results) before any fields are updated.
            sel_dlg = ADUserSelectDialog(results, self)
            if sel_dlg.exec_() != QDialog.Accepted or sel_dlg.selected_user() is None:
                return
            user = sel_dlg.selected_user()

            # Update name, email and department; user can still edit before saving
            formatted = _format_resource_name(user.get("display_name", ""))
            if formatted:
                self._e_name.setText(formatted)
            self._e_email.setText(user.get("email", ""))
            dept = user.get("department") or ""
            self._e_dept.setText(dept)

            # Fetch and persist the AD thumbnail so it shows in the avatar
            try:
                username = user.get("username", "")
                if username:
                    from integrations import ad_integration as _adi  # type: ignore
                    img_bytes = _adi.get_thumbnail(username)
                    if img_bytes:
                        uid = ""
                        try:
                            uid = str(self._res.getUniqueID())
                        except Exception:
                            pass
                        if uid:
                            _resource_thumbnail_store[uid] = img_bytes
                            if dept:
                                _resource_dept_store[uid] = dept
                            _save_resource_thumbnail_sidecar()
            except Exception:
                pass
            self._update_avatar()

        finally:
            self._ad_lookup_btn.setEnabled(True)

    def _update_avatar(self) -> None:
        """Refresh the avatar label: AD photo from store if available, else type fallback."""
        uid = ""
        try:
            uid = str(self._res.getUniqueID())
        except Exception:
            pass
        img_bytes = _resource_thumbnail_store.get(uid) if uid else None
        if img_bytes:
            from PyQt5.QtGui import QPixmap  # type: ignore
            from PyQt5.QtCore import Qt  # type: ignore
            pix = QPixmap()
            if pix.loadFromData(img_bytes):
                pix = pix.scaled(
                    64, 64,
                    Qt.KeepAspectRatioByExpanding,
                    Qt.SmoothTransformation,
                )
                self._avatar_lbl.setPixmap(pix)
                self._avatar_lbl.setText("")
                self._avatar_lbl.setStyleSheet(
                    "border: 2px solid #B8CBE4; border-radius: 32px; background: transparent;"
                )
                return
        # Fallback: type-specific coloured circle
        pix = _resource_type_pixmap(self._e_type.currentText(), 64)
        self._avatar_lbl.setPixmap(pix)
        self._avatar_lbl.setText("")
        self._avatar_lbl.setStyleSheet("border: none;")

    def _update_ad_btn_visibility(self) -> None:
        """Show/hide the AD button and work-only fields (email, department) based on type."""
        is_work = self._e_type.currentText().strip().upper() == "WORK"
        self._ad_lookup_btn.setVisible(is_work)
        # Toggle email and department form rows (label + field)
        try:
            from PyQt5.QtWidgets import QFormLayout  # type: ignore
            for form_row in (self._email_form_row, self._dept_form_row):
                lbl_item = self._f_general.itemAt(form_row, QFormLayout.LabelRole)
                fld_item = self._f_general.itemAt(form_row, QFormLayout.FieldRole)
                if lbl_item and lbl_item.widget():
                    lbl_item.widget().setVisible(is_work)
                if fld_item and fld_item.widget():
                    fld_item.widget().setVisible(is_work)
        except Exception:
            pass

    def _on_type_changed(self) -> None:
        """Update the fallback avatar and AD button when the resource type combobox changes."""
        self._update_ad_btn_visibility()
        uid = ""
        try:
            uid = str(self._res.getUniqueID())
        except Exception:
            pass
        # Only redraw if no AD photo is stored (AD photo takes priority)
        if not _resource_thumbnail_store.get(uid):
            self._update_avatar()

    def _tab_notes(self):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(8, 8, 8, 8)
        self._notes = QTextEdit()
        try:
            notes = self._res.getNotes()
            self._notes.setPlainText(str(notes) if notes else "")
        except Exception:
            pass
        v.addWidget(self._notes)
        return w

    def _tab_custom_fields(self):
        """Show resource custom fields (defined in Project Information). Value column is editable."""
        from PyQt5.QtWidgets import QScrollArea, QFrame  # type: ignore
        outer = QWidget()
        outer_v = QVBoxLayout(outer)
        outer_v.setContentsMargins(0, 0, 0, 0)
        outer_v.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        w = QWidget()
        w.setStyleSheet("background: white;")
        vbox = QVBoxLayout(w)
        vbox.setContentsMargins(12, 12, 12, 12)
        vbox.setSpacing(6)

        hint = QLabel(
            "Field definitions and aliases are managed in "
            "<b>Project Information → Custom Fields → Resource Fields</b>."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #808080; font-size: 10px;")
        vbox.addWidget(hint)

        tbl = QTableWidget(0, 2)
        tbl.setHorizontalHeaderLabels(["Field (Alias)", "Value"])
        tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.Interactive)
        tbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        tbl.horizontalHeader().resizeSection(0, 160)
        tbl.setAlternatingRowColors(True)
        tbl.verticalHeader().setVisible(False)
        tbl.verticalHeader().setDefaultSectionSize(22)
        tbl.setEditTriggers(QTableWidget.DoubleClicked | QTableWidget.EditKeyPressed)
        self._cf_tbl = tbl

        try:
            project = self._project
            if project is None:
                raise ValueError("no project reference")
            from org.mpxj import FieldTypeClass  # type: ignore
            for cf in project.getCustomFields():
                ft = cf.getFieldType()
                if ft is None:
                    continue
                try:
                    is_res = ft.getFieldTypeClass() == FieldTypeClass.RESOURCE
                except Exception:
                    is_res = "Resource" in str(ft.getClass().getSimpleName())
                if not is_res:
                    continue
                alias = str(cf.getAlias()) if cf.getAlias() else str(ft)
                try:
                    val = self._res.get(ft)
                except Exception:
                    val = None
                val_str = str(val) if val is not None else ""
                row = tbl.rowCount()
                tbl.insertRow(row)
                name_item = QTableWidgetItem(alias)
                name_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                tbl.setItem(row, 0, name_item)
                tbl.setItem(row, 1, QTableWidgetItem(val_str))
                self._custom_field_types.append((row, ft))
        except Exception as e:
            print(f"[WARN] resource custom fields load: {e}")

        if tbl.rowCount() == 0:
            vbox.addWidget(QLabel("No custom fields defined. Add them in Project Information."))
        vbox.addWidget(tbl)

        scroll.setWidget(w)
        outer_v.addWidget(scroll)
        return outer

    def apply_to_resource(self):
        r = self._res
        try:
            r.setName(self._e_name.text().strip())
            units_str = self._e_units.text().strip()
            if units_str:
                from java.lang import Double  # type: ignore
                from org.mpxj import Availability, Duration, TimeUnit  # type: ignore
                from java.time import LocalDateTime  # type: ignore

                # User types a percentage (e.g. 90) — store as fraction for MPXJ (0.9)
                new_max = float(units_str)
                units_val = Double.valueOf(new_max / 100.0)

                # Read old max units and normalize to percentage scale for the recalc below
                old_max_u = r.getMaxUnits()
                _old_raw = float(str(old_max_u)) if old_max_u is not None else 1.0
                old_max = _old_raw * 100.0 if _old_raw <= 2.0 else _old_raw
                start = LocalDateTime.of(1900, 1, 1, 0, 0)
                end = LocalDateTime.of(2100, 12, 31, 23, 59)
                r.getAvailability().clear()
                r.getAvailability().add(Availability(start, end, units_val))

                # Recalculate durations for tasks assigned to this resource
                # Formula: work = duration × old_effective_units
                #          new_duration = work / new_effective_units
                # effective_units = min(assignment_units, max_units)
                if old_max > 0 and new_max > 0 and old_max != new_max:
                    try:
                        r_uid = int(str(r.getUniqueID()))
                        all_tasks = []
                        for proj in r.getProjectContext().getProjects():
                            for task in proj.getTasks():
                                all_tasks.append(task)
                        changed_deltas = {}  # task_uid -> delta_days applied to finish
                        for task in all_tasks:
                            if task.getName() is None:
                                continue
                            for ass in task.getResourceAssignments():
                                res = ass.getResource()
                                if res is None:
                                    continue
                                try:
                                    if int(str(res.getUniqueID())) != r_uid:
                                        continue
                                except Exception:
                                    continue
                                u = ass.getUnits()
                                u_val = float(str(u)) if u is not None else 100.0
                                old_eff = min(u_val, old_max)
                                new_eff = min(u_val, new_max)
                                if old_eff > 0 and new_eff > 0 and abs(old_eff - new_eff) > 0.001:
                                    cur_dur = task.getDuration()
                                    old_start = task.getStart()
                                    if cur_dur is not None and old_start is not None:
                                        old_days = float(str(cur_dur.getDuration()))
                                        new_days = old_days * old_eff / new_eff
                                        task.setDuration(
                                            Duration.getInstance(new_days, TimeUnit.DAYS))
                                        # Shift finish by rounded work days so Gantt
                                        # bars (which use getFinish()) update too.
                                        delta_days = int(round(new_days - old_days))
                                        task.setFinish(old_start.plusDays(int(round(new_days))))
                                        # Track day shift for successor propagation
                                        try:
                                            t_uid = int(str(task.getUniqueID()))
                                            changed_deltas[t_uid] = delta_days
                                        except Exception:
                                            pass
                        # Propagate finish changes forward through dependency links
                        if changed_deltas:
                            _propagate_schedule(all_tasks, changed_deltas)
                    except Exception as e:
                        print(f"[WARN] Duration recalc: {e}")

            try:
                r.setNotes(self._notes.toPlainText())
            except Exception:
                pass

            try:
                email_val = self._e_email.text().strip()
                r.setEmailAddress(email_val if email_val else None)
            except Exception:
                pass

            try:
                dept_val = self._e_dept.text().strip()
                r.setDepartment(dept_val if dept_val else None)
            except Exception:
                pass

            # Persist department to the sidecar store
            try:
                _uid_key = str(r.getUniqueID()) if r.getUniqueID() is not None else ""
                if _uid_key:
                    _resource_dept_store[_uid_key] = self._e_dept.text().strip()
                    _save_resource_thumbnail_sidecar()
            except Exception:
                pass

            try:
                from org.mpxj import ResourceType  # type: ignore
                type_str = self._e_type.currentText().strip().upper()
                rt = getattr(ResourceType, type_str, ResourceType.WORK)
                r.setType(rt)
            except Exception:
                pass

        except Exception as e:
            print(f"[WARN] ResourceDialog.apply: {e}")

        # Sync custom field values from the Custom Fields tab
        try:
            for row, ft in self._custom_field_types:
                val_item = self._cf_tbl.item(row, 1)
                val_text = val_item.text().strip() if val_item else ""
                _set_cf_value(self._res, ft, val_text)
        except Exception as e:
            print(f"[WARN] ResourceDialog.apply custom fields: {e}")

        # Save Active Directory tab fields
        try:
            email = self._ad_email.text().strip()
            if email:
                r.setEmailAddress(email)
            # Persist city, department, country to MPXJ TEXT fields (TEXT1/2/3)
            import jpype  # type: ignore
            RF = jpype.JClass("org.mpxj.ResourceField")
            city_val    = self._ad_city.text().strip()
            dept_val    = self._ad_dept.text().strip()
            country_val = self._ad_country.currentText().strip()
            for field_name, value in [("TEXT1", city_val), ("TEXT2", dept_val), ("TEXT3", country_val)]:
                try:
                    fld = getattr(RF, field_name, None)
                    if fld is not None:
                        r.set(fld, value if value else None)
                except Exception:
                    pass
            # Update in-memory _ad_data if present
            ad = getattr(r, "_ad_data", None)
            if ad is not None:
                ad["email"]      = email
                ad["city"]       = city_val
                ad["department"] = dept_val
                ad["country"]    = country_val
        except Exception as e:
            print(f"[WARN] ResourceDialog.apply AD fields: {e}")


# ------------------------------------------------------------------ #
# Dependency / Task Link                                               #
# ------------------------------------------------------------------ #

class DependencyDialog(_BaseDialog):
    """Add or view a task dependency."""

    _LINK_TYPES = ["FINISH_START", "START_START", "FINISH_FINISH", "START_FINISH"]

    def __init__(self, project, read_only=False, parent=None):
        title = "Task Dependency"
        super().__init__(title, parent)
        self._project = project
        self._read_only = read_only
        self.setMinimumHeight(300)
        self._root.addWidget(_make_header(title, "Define a dependency between two tasks"))

        w = QWidget()
        f = QFormLayout(w)
        f.setContentsMargins(16, 16, 16, 16)
        f.setSpacing(12)

        task_labels = []
        self._task_list = []
        for t in project.getTasks():
            if t.getName() is not None:
                task_labels.append(f"{t.getID()} – {t.getName()}")
                self._task_list.append(t)

        self._c_pred = QComboBox()
        self._c_pred.addItems(task_labels)
        f.addRow("Predecessor:", self._c_pred)

        self._c_succ = QComboBox()
        self._c_succ.addItems(task_labels)
        # pre-select a different task for successor
        if len(task_labels) > 1:
            self._c_succ.setCurrentIndex(1)
        f.addRow("Successor:", self._c_succ)

        self._c_type = QComboBox()
        self._c_type.addItems(self._LINK_TYPES)
        f.addRow("Link Type:", self._c_type)

        self._e_lag = QLineEdit("0")
        f.addRow("Lag (days):", self._e_lag)

        if read_only:
            for widget in [self._c_pred, self._c_succ, self._c_type, self._e_lag]:
                widget.setEnabled(False)

        body = QWidget()
        bv = QVBoxLayout(body)
        bv.setContentsMargins(0, 0, 0, 0)
        bv.addWidget(w)
        self._root.addWidget(body)
        self._root.addWidget(_make_button_row(self, read_only=read_only))

    def apply_dependency(self):
        """Create the dependency. Returns True on success."""
        if self._read_only or not self._task_list:
            return False
        pred = self._task_list[self._c_pred.currentIndex()]
        succ = self._task_list[self._c_succ.currentIndex()]
        if pred is succ:
            QMessageBox.warning(self, "Invalid", "Predecessor and successor must be different tasks.")
            return False
        try:
            from org.mpxj import RelationType, Duration, TimeUnit  # type: ignore
            rt_map = {
                "FINISH_START":  RelationType.FINISH_START,
                "START_START":   RelationType.START_START,
                "FINISH_FINISH": RelationType.FINISH_FINISH,
                "START_FINISH":  RelationType.START_FINISH,
            }
            rel_type = rt_map.get(self._c_type.currentText(), RelationType.FINISH_START)
            lag_str = "".join(c for c in self._e_lag.text() if c.isdigit() or c == '.')
            import jpype  # type: ignore
            lag_dur = Duration.getInstance(float(lag_str) if lag_str else 0.0, TimeUnit.DAYS)
            _RelBuilder = jpype.JClass('org.mpxj.Relation$Builder')
            succ.addPredecessor(_RelBuilder().predecessorTask(pred).type(rel_type).lag(lag_dur))
            return True
        except Exception as e:
            print(f"[WARN] DependencyDialog.apply: {e}")
            QMessageBox.warning(self, "Error", f"Could not create dependency:\n{e}")
            return False


# ------------------------------------------------------------------ #
# Baseline Details (read-only)                                        #
# ------------------------------------------------------------------ #

class BaselineEntryDialog(_BaseDialog):
    """Read-only baseline vs actual dialog for a single task."""

    def __init__(self, task, parent=None):
        super().__init__("Baseline Details", parent)
        self.setMinimumHeight(320)
        name = str(task.getName()) if task.getName() is not None else ""
        self._root.addWidget(_make_header("Baseline Details", name))

        w = QWidget()
        f = QFormLayout(w)
        f.setContentsMargins(16, 16, 16, 16)
        f.setSpacing(10)

        def ro(val):
            le = QLineEdit(val)
            le.setReadOnly(True)
            return le

        def safe(fn):
            try:
                v = fn()
                return str(v) if v is not None else ""
            except Exception:
                return ""

        f.addRow("Name:",               ro(name))
        f.addRow("Baseline Start:",     ro(safe(task.getBaselineStart)))
        f.addRow("Actual Start:",       ro(safe(task.getActualStart)))
        f.addRow("Baseline Finish:",    ro(safe(task.getBaselineFinish)))
        f.addRow("Actual Finish:",      ro(safe(task.getActualFinish)))
        f.addRow("Baseline Duration:",  ro(safe(task.getBaselineDuration)))
        f.addRow("Actual Duration:",    ro(safe(task.getActualDuration)))

        self._root.addWidget(w)
        self._root.addWidget(_make_button_row(self, read_only=True))


# ------------------------------------------------------------------ #
# Project Information                                                  #
# ------------------------------------------------------------------ #

_WELL_KNOWN_FIELDS = [
    "Project Code",
    "Department",
    "Cost Center",
    "Phase",
    "Client",
    "Version",
    "Description",
    # Confluence calendar sync settings (stored in sidecar JSON, not in XML)
    "CALENDAR Base URL",
    "CALENDAR Space Key",
    "CALENDAR Timezone",
    "CALENDAR Days Ahead",
]


class ProjectInfoDialog(_BaseDialog):
    """Project Information dialog — mirrors MS Project > Project > Project Information."""

    def __init__(self, project, parent=None, file_path=None):
        super().__init__("Project Information", parent)
        self._project = project
        self._file_path = file_path
        self._props = project.getProjectProperties()
        self.setMinimumWidth(720)
        self.setMinimumHeight(500)

        try:
            hdr_sub = str(self._props.getProjectTitle() or self._props.getName() or "")
        except Exception:
            hdr_sub = ""
        self._root.addWidget(_make_header("Project Information", hdr_sub))

        tabs = QTabWidget()
        tabs.addTab(self._tab_summary(),      "Summary")
        tabs.addTab(self._tab_project(),      "Project")
        tabs.addTab(self._tab_calendar(),     "Calendar")
        tabs.addTab(self._tab_calendars(),    "Calendars")
        tabs.addTab(self._tab_currency(),     "Currency")
        tabs.addTab(self._tab_settings(),     "Settings")
        tabs.addTab(self._tab_custom(),       "Custom Fields")

        content = QWidget()
        cl = QVBoxLayout(content)
        cl.setContentsMargins(8, 8, 8, 4)
        cl.addWidget(tabs)
        self._root.addWidget(content)
        self._root.addWidget(_make_button_row(self))

    # ---------------------------------------------------------------- #
    # Static helpers                                                    #
    # ---------------------------------------------------------------- #

    @staticmethod
    def _safe(fn):
        try:
            v = fn()
            return str(v) if v is not None else ""
        except Exception:
            return ""

    @staticmethod
    def _fmt_dt(java_dt):
        if java_dt is None:
            return ""
        try:
            return str(java_dt)[:16].replace("T", " ")
        except Exception:
            return ""

    @staticmethod
    def _fmt_lt(java_lt):
        if java_lt is None:
            return ""
        try:
            return str(java_lt)[:5]
        except Exception:
            return ""

    @staticmethod
    def _ro(val):
        le = QLineEdit(val)
        le.setReadOnly(True)
        return le

    # ---------------------------------------------------------------- #
    # Tabs                                                              #
    # ---------------------------------------------------------------- #

    def _tab_summary(self):
        props = self._props
        w = QWidget()
        f = QFormLayout(w)
        f.setContentsMargins(16, 16, 16, 16)
        f.setSpacing(10)

        self._e_title    = QLineEdit(self._safe(props.getProjectTitle))
        self._e_subject  = QLineEdit(self._safe(props.getSubject))
        self._e_author   = QLineEdit(self._safe(props.getAuthor))
        self._e_manager  = QLineEdit(self._safe(props.getManager))
        self._e_company  = QLineEdit(self._safe(props.getCompany))
        self._e_category = QLineEdit(self._safe(props.getCategory))
        self._e_keywords = QLineEdit(self._safe(props.getKeywords))

        self._e_comments = QTextEdit()
        self._e_comments.setPlainText(self._safe(props.getComments))
        self._e_comments.setMaximumHeight(80)

        f.addRow("Title:",    self._e_title)
        f.addRow("Subject:",  self._e_subject)
        f.addRow("Author:",   self._e_author)
        f.addRow("Manager:",  self._e_manager)
        f.addRow("Company:",  self._e_company)
        f.addRow("Category:", self._e_category)
        f.addRow("Keywords:", self._e_keywords)
        f.addRow("Comments:", self._e_comments)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #D0DDF0;")
        f.addRow(sep)

        try:
            f.addRow("Revision:",   self._ro(self._safe(props.getRevision)))
        except Exception:
            pass
        try:
            f.addRow("Created:",    self._ro(self._fmt_dt(props.getCreationDate())))
        except Exception:
            pass
        try:
            f.addRow("Last Saved:", self._ro(self._fmt_dt(props.getLastSaved())))
        except Exception:
            pass
        return w

    def _tab_project(self):
        props = self._props
        w = QWidget()
        f = QFormLayout(w)
        f.setContentsMargins(16, 16, 16, 16)
        f.setSpacing(10)

        def dt_field(getter, default_today=False):
            dte = QDateTimeEdit()
            dte.setDisplayFormat("yyyy-MM-dd HH:mm")
            dte.setCalendarPopup(True)
            dte.setSpecialValueText(" ")
            dte.setMinimumDateTime(QDateTime(QDate(1900, 1, 1), QTime(0, 0)))
            try:
                s = self._fmt_dt(getter())
                if s:
                    dte.setDateTime(QDateTime.fromString(s, "yyyy-MM-dd HH:mm"))
                else:
                    dte.setDateTime(
                        QDateTime.currentDateTime() if default_today
                        else dte.minimumDateTime()
                    )
            except Exception:
                dte.setDateTime(
                    QDateTime.currentDateTime() if default_today
                    else dte.minimumDateTime()
                )
            return dte

        self._e_start  = dt_field(props.getStartDate,  default_today=True)
        self._e_finish = dt_field(props.getFinishDate, default_today=True)
        self._e_status = dt_field(props.getStatusDate, default_today=True)

        self._c_schedule = QComboBox()
        self._c_schedule.addItems(["Project Start Date", "Project Finish Date"])
        try:
            if "FINISH" in str(props.getScheduleFrom()).upper():
                self._c_schedule.setCurrentIndex(1)
        except Exception:
            pass

        f.addRow("Start Date:",    self._e_start)
        f.addRow("Finish Date:",   self._e_finish)
        f.addRow("Status Date:",   self._e_status)
        f.addRow("Schedule From:", self._c_schedule)
        return w

    def _tab_calendar(self):
        props = self._props
        w = QWidget()
        f = QFormLayout(w)
        f.setContentsMargins(16, 16, 16, 16)
        f.setSpacing(10)

        def _time_field(getter, default_hhmm=None):
            te = QTimeEdit()
            te.setDisplayFormat("HH:mm")
            try:
                s = self._fmt_lt(getter())
                if s:
                    te.setTime(QTime.fromString(s, "HH:mm"))
                elif default_hhmm:
                    te.setTime(QTime.fromString(default_hhmm, "HH:mm"))
            except Exception:
                if default_hhmm:
                    te.setTime(QTime.fromString(default_hhmm, "HH:mm"))
            return te

        self._e_def_start  = _time_field(props.getDefaultStartTime, default_hhmm="08:00")
        self._e_def_finish = _time_field(props.getDefaultEndTime,   default_hhmm="17:00")

        def mins_to_h(getter):
            try:
                v = getter()
                return "{:.2f}".format(int(str(v)) / 60) if v is not None else ""
            except Exception:
                return ""

        self._e_hours_day  = QLineEdit(mins_to_h(props.getMinutesPerDay))
        self._e_hours_week = QLineEdit(mins_to_h(props.getMinutesPerWeek))

        self._e_days_month = QLineEdit()
        try:
            v = props.getDaysPerMonth()
            self._e_days_month.setText(str(v) if v is not None else "")
        except Exception:
            pass

        _DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        self._c_week_start = QComboBox()
        self._c_week_start.addItems(_DAYS)
        try:
            wsd = props.getWeekStartDay()
            if wsd is not None:
                name = str(wsd).title()
                if name in _DAYS:
                    self._c_week_start.setCurrentText(name)
        except Exception:
            pass

        hint = QLabel("Hours per day/week are converted to minutes internally.")
        hint.setStyleSheet("color: #808080; font-size: 10px;")
        hint.setWordWrap(True)

        f.addRow("Default Start Time:",  self._e_def_start)
        f.addRow("Default Finish Time:", self._e_def_finish)
        f.addRow("Hours per Day:",       self._e_hours_day)
        f.addRow("Hours per Week:",      self._e_hours_week)
        f.addRow("Days per Month:",      self._e_days_month)
        f.addRow("Week Starts On:",      self._c_week_start)
        f.addRow("", hint)
        return w

    def _tab_calendars(self):
        """Full editor for project work calendars."""
        self._cal_editors   = {}   # uid → {name, default, days, exc_tbl, cal}
        self._cal_uid_order = []   # preserve display order

        w = QWidget()
        outer = QVBoxLayout(w)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(4)

        hint = QLabel("Define working / non-working days for each calendar.  "
                      "Day-type and name changes are saved when you click OK.  "
                      "Add / Remove are applied immediately.")
        hint.setStyleSheet("color: #808080; font-size: 10px;")
        hint.setWordWrap(True)
        outer.addWidget(hint)

        split = QSplitter(Qt.Horizontal)

        # ---- Left: calendar list ----
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 4, 0)
        lv.setSpacing(4)
        lbl_cals = QLabel("Project Calendars:")
        lbl_cals.setStyleSheet("font-weight: bold;")
        lbl_cals.setToolTip("All calendars defined in this project.\n"
                            "The starred (★) entry is the project default calendar.")
        lv.addWidget(lbl_cals)

        self._cal_list = QListWidget()
        self._cal_list.setMinimumWidth(210)
        self._cal_list.setMaximumWidth(260)
        self._cal_list.setToolTip("Select a calendar to view or edit its working days and exceptions.\n"
                                   "Double-click to rename.")
        lv.addWidget(self._cal_list, 1)  # stretch=1 so the list fills available height

        # Row 1: Add / Remove
        btn_cal_row = QWidget()
        bch = QHBoxLayout(btn_cal_row)
        bch.setContentsMargins(0, 0, 0, 0)
        bch.setSpacing(4)
        btn_add_cal = QPushButton("Add")
        btn_add_cal.setStyleSheet(_BUTTON_STYLE)
        btn_add_cal.setToolTip("Add a new blank calendar to this project")
        btn_add_cal.clicked.connect(self._cal_add)
        btn_rem_cal = QPushButton("Remove")
        btn_rem_cal.setStyleSheet(_BUTTON_STYLE)
        btn_rem_cal.setToolTip("Remove the selected calendar from this project")
        btn_rem_cal.clicked.connect(self._cal_remove)
        bch.addWidget(btn_add_cal)
        bch.addWidget(btn_rem_cal)
        bch.addStretch()
        lv.addWidget(btn_cal_row)

        # Row 2: Import ICS (full width)
        btn_import_ics = QPushButton("Import ICS…")
        btn_import_ics.setStyleSheet(_BUTTON_STYLE)
        btn_import_ics.setToolTip(
            "Import non-working day exceptions from an iCalendar (.ics / .ical) file.\n"
            "You will be asked which calendar to import into.\n"
            "Yearly-recurring events are expanded for the full project year range."
        )
        btn_import_ics.clicked.connect(self._cal_import_ics)
        lv.addWidget(btn_import_ics)

        # Row 3: Add Holidays (full width)
        btn_add_hol = QPushButton("Add Holidays…")
        btn_add_hol.setStyleSheet(_BUTTON_STYLE)
        btn_add_hol.setToolTip(
            "Add a pre-built national or regional holiday calendar.\n"
            "German state calendars inherit the national holidays\n"
            "and only store the state-specific extra public holidays."
        )
        btn_add_hol.clicked.connect(self._cal_add_holidays)
        lv.addWidget(btn_add_hol)

        split.addWidget(left)

        # ---- Right: stacked detail pages ----
        self._cal_stack = QStackedWidget()
        try:
            import java.time as _jt  # type: ignore
            import jpype  # type: ignore
            _DOWS     = list(_jt.DayOfWeek.values())
            _DAY_TYPES = ["WORKING", "NON_WORKING", "DEFAULT"]
            for cal in self._project.getCalendars():
                uid = int(cal.getUniqueID())
                self._cal_uid_order.append(uid)
                page, einfo = self._build_cal_page(cal, _DOWS, _DAY_TYPES)
                self._cal_editors[uid] = einfo
                self._cal_stack.addWidget(page)
                name_str = str(cal.getName() or f"Calendar {uid}")
                if cal.getDefault():
                    name_str += "  \u2605"
                item = QListWidgetItem(name_str)
                item.setData(Qt.UserRole, uid)
                self._cal_list.addItem(item)
        except Exception as e:
            print(f"[WARN] _tab_calendars load: {e}")

        self._cal_list.currentRowChanged.connect(self._cal_stack.setCurrentIndex)
        if self._cal_list.count() > 0:
            self._cal_list.setCurrentRow(0)

        split.addWidget(self._cal_stack)
        split.setStretchFactor(0, 0)
        split.setStretchFactor(1, 1)
        split.setSizes([200, 430])
        outer.addWidget(split)
        return w

    def _build_cal_page(self, cal, days_of_week, day_types):
        """Build the right-side detail widget for one ProjectCalendar."""
        page = QWidget()
        pv = QVBoxLayout(page)
        pv.setContentsMargins(6, 4, 4, 4)
        pv.setSpacing(6)

        # Name / parent / default
        hdr = QWidget()
        hf = QFormLayout(hdr)
        hf.setContentsMargins(0, 0, 0, 0)
        hf.setSpacing(4)
        e_name = QLineEdit(str(cal.getName() or ""))
        e_name.setToolTip("The display name of this calendar")
        hf.addRow("Name:", e_name)
        parent_cal = None
        try:
            parent_cal = cal.getParent()
        except Exception:
            pass

        # ---- Base Calendar combo ----------------------------------------
        cbo_parent = QComboBox()
        cbo_parent.setToolTip(
            "The base calendar this one inherits from.\n"
            "Working days marked DEFAULT use the parent\u2019s definition."
        )
        cbo_parent.addItem("(none)", None)

        # Determine current calendar UID to exclude self from list
        _this_uid = None
        try:
            _this_uid = int(cal.getUniqueID())
        except Exception:
            pass

        # Identify the project standard (default) calendar
        _def_cal   = None
        _def_uid   = None
        try:
            _def_cal = self._project.getDefaultCalendar()
            if _def_cal is not None:
                _def_uid = int(_def_cal.getUniqueID())
        except Exception:
            pass

        # Add the default calendar first (with ★) if it's not this calendar
        if _def_cal is not None and _def_uid != _this_uid:
            cbo_parent.addItem(
                "\u2605 " + str(_def_cal.getName() or f"Calendar {_def_uid}"),
                _def_uid,
            )

        # Add all remaining calendars (skip self and the already-added default)
        try:
            for _oc in self._project.getCalendars():
                try:
                    _oc_uid = int(_oc.getUniqueID())
                except Exception:
                    continue
                if _oc_uid == _this_uid or _oc_uid == _def_uid:
                    continue
                cbo_parent.addItem(
                    str(_oc.getName() or f"Calendar {_oc_uid}"),
                    _oc_uid,
                )
        except Exception:
            pass

        # Pre-select: current parent → project default → (none)
        _preselect_uid = None
        if parent_cal is not None:
            try:
                _preselect_uid = int(parent_cal.getUniqueID())
            except Exception:
                pass
        elif _def_uid is not None and _def_uid != _this_uid:
            _preselect_uid = _def_uid

        if _preselect_uid is not None:
            _idx = cbo_parent.findData(_preselect_uid)
            if _idx >= 0:
                cbo_parent.setCurrentIndex(_idx)

        hf.addRow("Base Calendar:", cbo_parent)
        # ---------------------------------------------------------------------

        chk_default = QCheckBox("Set as project default calendar")
        chk_default.setToolTip(
            "Make this the project-wide default calendar.\n"
            "Tasks without an explicit calendar assignment use this one."
        )
        try:
            chk_default.setChecked(bool(cal.getDefault()))
        except Exception:
            pass
        hf.addRow("", chk_default)
        pv.addWidget(hdr)

        # Day types table
        lbl_days = QLabel("Working Days:")
        lbl_days.setStyleSheet("font-weight: bold;")
        lbl_days.setToolTip(
            "Define whether each weekday is WORKING, NON_WORKING, or DEFAULT (inherits from base calendar)."
        )
        pv.addWidget(lbl_days)
        day_tbl = QTableWidget(len(days_of_week), 3)
        day_tbl.setHorizontalHeaderLabels(["Day", "Type", "Working Hours (read-only)"])
        day_tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        day_tbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        day_tbl.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        day_tbl.verticalHeader().setVisible(False)
        day_tbl.verticalHeader().setDefaultSectionSize(28)
        day_tbl.verticalHeader().setMinimumSectionSize(28)
        day_tbl.setAlternatingRowColors(True)
        day_tbl.setMaximumHeight(230)
        day_combos = []
        for i, dow in enumerate(days_of_week):
            d_item = QTableWidgetItem(str(dow))
            d_item.setFlags(Qt.ItemIsEnabled)
            day_tbl.setItem(i, 0, d_item)
            cbo = QComboBox()
            cbo.addItems(day_types)
            cbo.setToolTip(
                "WORKING\u00a0\u2013 normal working day\n"
                "NON_WORKING\u00a0\u2013 always off\n"
                "DEFAULT\u00a0\u2013 inherit from base calendar"
            )
            try:
                dt_str = str(cal.getCalendarDayType(dow))
                if dt_str in day_types:
                    cbo.setCurrentText(dt_str)
            except Exception:
                pass
            day_tbl.setCellWidget(i, 1, cbo)
            day_combos.append(cbo)
            try:
                hrs_obj = cal.getCalendarHours(dow)
                hr_parts = []
                if hrs_obj:
                    for rng in hrs_obj:
                        hr_parts.append(f"{rng.getStart()}-{rng.getEnd()}")
                hr_text = ", ".join(hr_parts)
            except Exception:
                hr_text = ""
            hrs_item = QTableWidgetItem(hr_text)
            hrs_item.setFlags(Qt.ItemIsEnabled)
            day_tbl.setItem(i, 2, hrs_item)
        pv.addWidget(day_tbl)

        # Exceptions
        lbl_exc = QLabel("Calendar Exceptions (holidays / special days):")
        lbl_exc.setStyleSheet("font-weight: bold;")
        lbl_exc.setToolTip(
            "Date ranges that override the normal day-type rules.\n"
            "Typically used for public holidays, company shutdowns, or special events."
        )
        pv.addWidget(lbl_exc)
        exc_tbl = QTableWidget(0, 3)
        exc_tbl.setHorizontalHeaderLabels(["Name", "From Date", "To Date"])
        exc_tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        exc_tbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        exc_tbl.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        exc_tbl.horizontalHeader().resizeSection(1, 110)
        exc_tbl.horizontalHeader().resizeSection(2, 110)
        exc_tbl.verticalHeader().setVisible(False)
        exc_tbl.verticalHeader().setDefaultSectionSize(28)
        exc_tbl.verticalHeader().setMinimumSectionSize(28)
        exc_tbl.setAlternatingRowColors(True)
        try:
            for ex in cal.getCalendarExceptions():
                r = exc_tbl.rowCount()
                exc_tbl.insertRow(r)
                exc_tbl.setItem(r, 0, QTableWidgetItem(str(ex.getName() or "")))
                from_de = QDateEdit()
                from_de.setDisplayFormat("yyyy-MM-dd")
                from_de.setCalendarPopup(True)
                from_str = str(ex.getFromDate() or "")[:10]
                if from_str:
                    from_de.setDate(QDate.fromString(from_str, "yyyy-MM-dd"))
                exc_tbl.setCellWidget(r, 1, from_de)
                to_de = QDateEdit()
                to_de.setDisplayFormat("yyyy-MM-dd")
                to_de.setCalendarPopup(True)
                to_str = str(ex.getToDate() or "")[:10]
                if to_str:
                    to_de.setDate(QDate.fromString(to_str, "yyyy-MM-dd"))
                exc_tbl.setCellWidget(r, 2, to_de)
        except Exception:
            pass
        pv.addWidget(exc_tbl)

        # Exception buttons
        exc_btn_row = QWidget()
        ebh = QHBoxLayout(exc_btn_row)
        ebh.setContentsMargins(0, 0, 0, 0)
        ebh.setSpacing(4)
        btn_exc_add = QPushButton("Add Exception")
        btn_exc_add.setStyleSheet(_BUTTON_STYLE)
        btn_exc_add.setToolTip("Append a new non-working exception row (e.g. a public holiday)")
        btn_exc_add.clicked.connect(lambda checked, t=exc_tbl: self._exc_add_row(t))
        btn_exc_rem = QPushButton("Remove Exception")
        btn_exc_rem.setStyleSheet(_BUTTON_STYLE)
        btn_exc_rem.setToolTip("Remove the selected exception row(s)")
        btn_exc_rem.clicked.connect(lambda checked, t=exc_tbl: self._exc_remove_row(t))
        ebh.addWidget(btn_exc_add)
        ebh.addWidget(btn_exc_rem)
        ebh.addStretch()
        pv.addWidget(exc_btn_row)

        return page, {
            "name":         e_name,
            "default":      chk_default,
            "days":         day_combos,
            "exc_tbl":      exc_tbl,
            "cal":          cal,
            "parent_combo": cbo_parent,
        }

    def _cal_add(self):
        """Add a new project calendar with default working days."""
        name, ok = QInputDialog.getText(self, "New Calendar", "Calendar name:")
        if not ok or not name.strip():
            return
        try:
            import java.time as _jt  # type: ignore
            _DOWS      = list(_jt.DayOfWeek.values())
            _DAY_TYPES = ["WORKING", "NON_WORKING", "DEFAULT"]
            new_cal = self._project.addCalendar()
            new_cal.setName(name.strip())
            new_cal.addDefaultCalendarDays()
            new_cal.addDefaultCalendarHours()
            uid = int(new_cal.getUniqueID())
            self._cal_uid_order.append(uid)
            page, einfo = self._build_cal_page(new_cal, _DOWS, _DAY_TYPES)
            self._cal_editors[uid] = einfo
            self._cal_stack.addWidget(page)
            item = QListWidgetItem(name.strip())
            item.setData(Qt.UserRole, uid)
            self._cal_list.addItem(item)
            self._cal_list.setCurrentRow(self._cal_list.count() - 1)
        except Exception as e:
            print(f"[WARN] cal_add: {e}")

    def _cal_remove(self):
        """Remove the currently selected calendar from the project."""
        row = self._cal_list.currentRow()
        if row < 0:
            return
        item = self._cal_list.item(row)
        uid  = item.data(Qt.UserRole)
        einfo = self._cal_editors.get(uid)
        if einfo is None:
            return
        try:
            einfo["cal"].remove()
        except Exception as e:
            print(f"[WARN] cal_remove java: {e}")
        del self._cal_editors[uid]
        if uid in self._cal_uid_order:
            self._cal_uid_order.remove(uid)
        widget = self._cal_stack.widget(row)
        self._cal_stack.removeWidget(widget)
        self._cal_list.takeItem(row)

    def _exc_add_row(self, exc_tbl):
        """Append a blank exception row."""
        r = exc_tbl.rowCount()
        exc_tbl.insertRow(r)
        exc_tbl.setItem(r, 0, QTableWidgetItem("Holiday"))
        today = QDate.currentDate()
        for col in (1, 2):
            de = QDateEdit(today)
            de.setDisplayFormat("yyyy-MM-dd")
            de.setCalendarPopup(True)
            exc_tbl.setCellWidget(r, col, de)
        exc_tbl.scrollToBottom()

    def _exc_remove_row(self, exc_tbl):
        """Remove selected exception rows."""
        rows = sorted(set(i.row() for i in exc_tbl.selectedIndexes()), reverse=True)
        for r in rows:
            exc_tbl.removeRow(r)

    # ---------------------------------------------------------------- #
    # ICS import                                                        #
    # ---------------------------------------------------------------- #

    def _cal_import_ics(self):
        """Import VEVENT entries from an ICS file.

        Step 1 – Pick the .ics file.
        Step 2 – Ask which calendar to import into (current selection, any
                 existing calendar, or a newly created one).
        Step 3 – Parse and add exception rows to that calendar's exc_tbl.
        """
        from PyQt5.QtWidgets import QFileDialog, QDialog, QRadioButton, QButtonGroup  # type: ignore

        # Step 1: pick file first so the user can bail out before choosing calendar
        path, _ = QFileDialog.getOpenFileName(
            self, "Import ICS Calendar File", "",
            "iCalendar Files (*.ics *.ical);;All Files (*)"
        )
        if not path:
            return

        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except Exception as e:
            QMessageBox.warning(self, "Import ICS", f"Could not read file:\n{e}")
            return

        events = self._ics_parse(text)
        if not events:
            QMessageBox.information(self, "Import ICS",
                                    "No VEVENT entries found in the selected file.")
            return

        # Step 2: ask which calendar to import into
        cal_names = []
        cal_uids  = []
        for i in range(self._cal_list.count()):
            it = self._cal_list.item(i)
            cal_names.append(it.text().replace("  \u2605", "").strip())
            cal_uids.append(it.data(Qt.UserRole))

        _NEW = "<Create new calendar…>"
        choices = cal_names + [_NEW]

        # Pre-select the currently highlighted calendar
        pre = max(self._cal_list.currentRow(), 0)

        chosen_name, ok = QInputDialog.getItem(
            self,
            "Import ICS – Select Calendar",
            f"Import exceptions from:\n{path}\n\nInto which calendar?",
            choices,
            current=pre,
            editable=False,
        )
        if not ok:
            return

        if chosen_name == _NEW:
            new_name, ok2 = QInputDialog.getText(
                self, "Import ICS – New Calendar", "New calendar name:"
            )
            if not ok2 or not new_name.strip():
                return
            # Create the new calendar immediately
            try:
                import java.time as _jt  # type: ignore
                _DOWS      = list(_jt.DayOfWeek.values())
                _DAY_TYPES = ["WORKING", "NON_WORKING", "DEFAULT"]
                new_cal = self._project.addCalendar()
                new_cal.setName(new_name.strip())
                new_cal.addDefaultCalendarDays()
                new_cal.addDefaultCalendarHours()
                uid = int(new_cal.getUniqueID())
                self._cal_uid_order.append(uid)
                page, einfo = self._build_cal_page(new_cal, _DOWS, _DAY_TYPES)
                self._cal_editors[uid] = einfo
                self._cal_stack.addWidget(page)
                list_item = QListWidgetItem(new_name.strip())
                list_item.setData(Qt.UserRole, uid)
                self._cal_list.addItem(list_item)
                self._cal_list.setCurrentRow(self._cal_list.count() - 1)
                exc_tbl = einfo["exc_tbl"]
            except Exception as e:
                QMessageBox.warning(self, "Import ICS",
                                    f"Could not create new calendar:\n{e}")
                return
        else:
            idx  = cal_names.index(chosen_name)
            uid  = cal_uids[idx]
            einfo = self._cal_editors.get(uid)
            if einfo is None:
                return
            exc_tbl = einfo["exc_tbl"]
            # Switch the visible list row to the target calendar
            self._cal_list.setCurrentRow(idx)

        # Step 3: expand and insert exceptions
        try:
            from holidays import default_holiday_years  # type: ignore
            years = list(default_holiday_years())
        except Exception:
            import datetime as _dt
            cy = _dt.date.today().year
            years = list(range(cy - 2, cy + 13))

        import datetime as _dt

        added = 0
        for ev in events:
            summary  = (ev.get("SUMMARY") or "Holiday").strip() or "Holiday"
            rrule    = ev.get("RRULE", "")
            dtstart  = ev.get("DTSTART", "")
            dtend    = ev.get("DTEND", "")
            duration = ev.get("DURATION", "")

            start = self._ics_parse_date(dtstart)
            if start is None:
                continue

            if dtend:
                end = self._ics_parse_date(dtend)
                if end is None or end <= start:
                    end = start
                else:
                    if "T" not in dtstart:
                        end = end - _dt.timedelta(days=1)
            elif duration:
                import re as _re
                m = _re.search(r'P(\d+)D', duration)
                days = int(m.group(1)) - 1 if m else 0
                end = start + _dt.timedelta(days=max(days, 0))
            else:
                end = start

            if "FREQ=YEARLY" in rrule.upper():
                for y in years:
                    try:
                        ds = start.replace(year=y)
                        de = end.replace(year=y)
                    except ValueError:
                        continue
                    self._ics_exc_add(exc_tbl, summary, ds, de)
                    added += 1
            else:
                self._ics_exc_add(exc_tbl, summary, start, end)
                added += 1

        if added:
            exc_tbl.scrollToBottom()
            QMessageBox.information(
                self, "Import ICS",
                f"Added {added} exception(s) from:\n{path}\n\n"
                "Click OK in the Project Information dialog to save."
            )
        else:
            QMessageBox.information(self, "Import ICS",
                                    "No usable date entries found in the selected file.")

    @staticmethod
    def _ics_parse(text: str) -> list:
        """Minimal RFC 5545 VEVENT parser. Returns list of property dicts."""
        import re
        # Unfold folded lines
        text = re.sub(r'\r?\n[ \t]', '', text)
        events: list = []
        in_event = False
        current: dict = {}
        for raw in text.splitlines():
            line = raw.rstrip('\r')
            if line == 'BEGIN:VEVENT':
                in_event = True
                current = {}
            elif line == 'END:VEVENT':
                if in_event:
                    events.append(current)
                in_event = False
                current = {}
            elif in_event and ':' in line:
                prop_part, _, val = line.partition(':')
                prop_name = prop_part.split(';')[0].upper()
                val = (val
                       .replace('\\n', '\n')
                       .replace('\\,', ',')
                       .replace('\\;', ';')
                       .replace('\\\\', '\\'))
                current[prop_name] = val
        return events

    @staticmethod
    def _ics_parse_date(val: str):
        """Convert an ICS date/datetime string (YYYYMMDD…) to a Python date, or None."""
        import datetime as _dt
        if not val:
            return None
        val = val.replace('Z', '').strip()
        try:
            if len(val) >= 8:
                return _dt.date(int(val[:4]), int(val[4:6]), int(val[6:8]))
        except Exception:
            pass
        return None

    def _ics_exc_add(self, exc_tbl, name: str, from_date, to_date) -> None:
        """Append one exception row to *exc_tbl* (QTableWidget)."""
        r = exc_tbl.rowCount()
        exc_tbl.insertRow(r)
        exc_tbl.setItem(r, 0, QTableWidgetItem(name))
        from_de = QDateEdit()
        from_de.setDisplayFormat("yyyy-MM-dd")
        from_de.setCalendarPopup(True)
        from_de.setDate(QDate(from_date.year, from_date.month, from_date.day))
        exc_tbl.setCellWidget(r, 1, from_de)
        to_de = QDateEdit()
        to_de.setDisplayFormat("yyyy-MM-dd")
        to_de.setCalendarPopup(True)
        to_de.setDate(QDate(to_date.year, to_date.month, to_date.day))
        exc_tbl.setCellWidget(r, 2, to_de)

    # ---------------------------------------------------------------- #
    # Add holiday calendar                                              #
    # ---------------------------------------------------------------- #

    def _cal_add_holidays(self):
        """Add pre-built national/state holiday calendars not yet in this project."""
        # Collect names already installed (strip the ★ default marker)
        installed: set = set()
        for i in range(self._cal_list.count()):
            installed.add(self._cal_list.item(i).text().replace("  \u2605", "").strip())

        _ALL_STATES    = NewProjectCalendarsDialog._GERMAN_STATES
        _ALL_COUNTRIES = NewProjectCalendarsDialog._OTHER_COUNTRIES
        avail_states    = [s for s in _ALL_STATES    if s not in installed]
        avail_countries = [c for c in _ALL_COUNTRIES if c not in installed]

        if not avail_states and not avail_countries:
            QMessageBox.information(self, "Add Holidays",
                                    "All available holiday calendars are already installed.")
            return

        # ---- Build picker dialog ----
        from PyQt5.QtWidgets import QGridLayout  # type: ignore
        dlg = QDialog(self)
        dlg.setWindowTitle("Add Holiday Calendars")
        dlg.setStyleSheet(_DIALOG_STYLE)
        dlg.setMinimumWidth(500)

        root = QVBoxLayout(dlg)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(_make_header("Add Holiday Calendars",
                                    "Select calendars to add to this project"))

        body = QWidget()
        bv = QVBoxLayout(body)
        bv.setContentsMargins(16, 10, 16, 10)
        bv.setSpacing(10)

        checkboxes: dict = {}

        if avail_states:
            lbl_s = QLabel("German Federal States")
            lbl_s.setStyleSheet("font-weight: bold; color: #2B579A; font-size: 12px;")
            bv.addWidget(lbl_s)
            hint_s = QLabel(
                "State calendars are derived from Standard\u00a0(Deutschland) "
                "and carry only the state-specific extra holidays."
            )
            hint_s.setWordWrap(True)
            hint_s.setStyleSheet("color: #666; font-size: 10px;")
            bv.addWidget(hint_s)
            grid_w = QWidget()
            grid = QGridLayout(grid_w)
            grid.setContentsMargins(0, 0, 0, 0)
            grid.setSpacing(2)
            for idx, s in enumerate(avail_states):
                chk = QCheckBox(s)
                grid.addWidget(chk, idx // 2, idx % 2)
                checkboxes[s] = chk
            bv.addWidget(grid_w)

        if avail_countries:
            lbl_c = QLabel("Countries")
            lbl_c.setStyleSheet("font-weight: bold; color: #2B579A; font-size: 12px;")
            bv.addWidget(lbl_c)
            for country in avail_countries:
                chk = QCheckBox(country)
                checkboxes[country] = chk
                bv.addWidget(chk)

        root.addWidget(body)

        btn_row = QWidget()
        btn_row.setStyleSheet("background: white;")
        brh = QHBoxLayout(btn_row)
        brh.setContentsMargins(12, 4, 12, 12)
        brh.addStretch()
        ok_btn = QPushButton("OK")
        ok_btn.setStyleSheet(_BUTTON_STYLE)
        ok_btn.setDefault(True)
        ok_btn.clicked.connect(dlg.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(_BUTTON_STYLE)
        cancel_btn.clicked.connect(dlg.reject)
        brh.addWidget(ok_btn)
        brh.addWidget(cancel_btn)
        root.addWidget(btn_row)

        if dlg.exec_() != QDialog.Accepted:
            return

        selected = [name for name, chk in checkboxes.items() if chk.isChecked()]
        if not selected:
            return

        # ---- Create the calendars ----
        try:
            from holidays import (  # type: ignore
                german_state_extra_holidays,
                france_holidays, india_holidays, romania_holidays,
                china_holidays, japan_holidays,
                add_holidays_to_calendar, default_holiday_years,
            )
            import java.time as _jt  # type: ignore
            _DOWS      = list(_jt.DayOfWeek.values())
            _DAY_TYPES = ["WORKING", "NON_WORKING", "DEFAULT"]
            years = default_holiday_years()

            default_cal = self._project.getDefaultCalendar()

            _COUNTRY_FUNS = {
                "France":   lambda: france_holidays(years),
                "India":    lambda: india_holidays(years),
                "Romania":  lambda: romania_holidays(years),
                "China":    lambda: china_holidays(years),
                "Japan":    lambda: japan_holidays(years),
            }

            for name in selected:
                new_cal = self._project.addCalendar()
                new_cal.setName(name)
                if name in _ALL_STATES:
                    if default_cal is not None:
                        try:
                            new_cal.setParent(default_cal)
                        except Exception:
                            new_cal.addDefaultCalendarDays()
                            new_cal.addDefaultCalendarHours()
                    else:
                        new_cal.addDefaultCalendarDays()
                        new_cal.addDefaultCalendarHours()
                    add_holidays_to_calendar(
                        new_cal, german_state_extra_holidays(name, years))
                elif name in _COUNTRY_FUNS:
                    new_cal.addDefaultCalendarDays()
                    new_cal.addDefaultCalendarHours()
                    add_holidays_to_calendar(new_cal, _COUNTRY_FUNS[name]())

                # Register in the UI
                raw_uid = new_cal.getUniqueID()
                if raw_uid is None:
                    # MPXJ didn't auto-assign a UID; derive one from existing UIDs
                    uid = (max(self._cal_uid_order, default=0) + 1) if self._cal_uid_order else 1
                    try:
                        from java.lang import Integer as _JInt  # type: ignore
                        new_cal.setUniqueID(_JInt(uid))
                    except Exception:
                        pass
                else:
                    uid = int(raw_uid)
                self._cal_uid_order.append(uid)
                page, einfo = self._build_cal_page(new_cal, _DOWS, _DAY_TYPES)
                self._cal_editors[uid] = einfo
                self._cal_stack.addWidget(page)
                list_item = QListWidgetItem(name)
                list_item.setData(Qt.UserRole, uid)
                self._cal_list.addItem(list_item)

            self._cal_list.setCurrentRow(self._cal_list.count() - 1)
            QMessageBox.information(
                self, "Add Holidays",
                f"Added {len(selected)} holiday calendar(s).\n"
                "Click OK in the Project Information dialog to save."
            )
        except Exception as e:
            print(f"[WARN] _cal_add_holidays: {e}")
            QMessageBox.warning(self, "Add Holidays",
                                f"Error creating calendars:\n{e}")

    def _tab_currency(self):
        props = self._props
        w = QWidget()
        f = QFormLayout(w)
        f.setContentsMargins(16, 16, 16, 16)
        f.setSpacing(10)

        self._e_curr_sym    = QLineEdit(self._safe(props.getCurrencySymbol))
        self._e_curr_code   = QLineEdit(self._safe(props.getCurrencyCode))
        self._e_curr_digits = QLineEdit()
        try:
            d = props.getCurrencyDigits()
            self._e_curr_digits.setText(str(d) if d is not None else "2")
        except Exception:
            self._e_curr_digits.setText("2")

        _POS_LABELS  = ["Before number  (£1.23)", "After number  (1.23£)",
                        "Before with space  (£ 1.23)", "After with space  (1.23 £)"]
        _POS_NAMES   = ["BEFORE", "AFTER", "BEFORE_WITH_SPACE", "AFTER_WITH_SPACE"]
        self._c_curr_pos = QComboBox()
        self._c_curr_pos.addItems(_POS_LABELS)
        try:
            pos_str = str(props.getSymbolPosition())
            if pos_str in _POS_NAMES:
                self._c_curr_pos.setCurrentIndex(_POS_NAMES.index(pos_str))
        except Exception:
            pass

        f.addRow("Currency Symbol:", self._e_curr_sym)
        f.addRow("Currency Code:",   self._e_curr_code)
        f.addRow("Decimal Digits:",  self._e_curr_digits)
        f.addRow("Symbol Position:", self._c_curr_pos)
        return w

    def _tab_custom(self):
        """Custom Fields tab with three sub-sections: project properties, task fields, resource fields."""
        w = QWidget()
        vbox = QVBoxLayout(w)
        vbox.setContentsMargins(4, 4, 4, 4)
        vbox.setSpacing(0)

        inner_tabs = QTabWidget()
        inner_tabs.setUsesScrollButtons(True)
        inner_tabs.addTab(self._subtab_enterprise_fields(), "Enterprise")
        inner_tabs.addTab(self._subtab_entity_fields("task"),      "Task Fields")
        inner_tabs.addTab(self._subtab_entity_fields("resource"),  "Resources")
        inner_tabs.addTab(self._subtab_project_props(),     "Properties")
        vbox.addWidget(inner_tabs)
        return w

    # -- Enterprise Fields (read-only; stored on project summary task UID=0) --

    def _subtab_enterprise_fields(self):
        """Read-only view of enterprise custom field values for the project."""
        w = QWidget()
        vbox = QVBoxLayout(w)
        vbox.setContentsMargins(12, 12, 12, 12)
        vbox.setSpacing(6)

        hint = QLabel(
            "Enterprise custom field values from the project summary task (UID=0). "
            "Read-only — edit the source file in MS Project to change these."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #808080; font-size: 10px;")
        vbox.addWidget(hint)

        tbl = QTableWidget(0, 2)
        tbl.setHorizontalHeaderLabels(["Custom Field Name", "Value"])
        tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        tbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        tbl.setSelectionBehavior(QTableWidget.SelectRows)
        tbl.setAlternatingRowColors(True)
        tbl.setEditTriggers(QTableWidget.NoEditTriggers)
        tbl.verticalHeader().setVisible(False)
        tbl.verticalHeader().setDefaultSectionSize(22)

        rows = self._load_enterprise_fields_data()
        for name, val_str, tooltip in rows:
            r = tbl.rowCount()
            tbl.insertRow(r)
            name_item = QTableWidgetItem(name)
            if tooltip:
                name_item.setToolTip(tooltip)
            tbl.setItem(r, 0, name_item)
            tbl.setItem(r, 1, QTableWidgetItem(val_str))

        vbox.addWidget(tbl)
        return w

    # ---------------------------------------------------------------- #
    # Data loading                                                      #
    # ---------------------------------------------------------------- #

    def _load_enterprise_fields_data(self):
        """Return list of (display_name, value_str, tooltip) for all enterprise
        custom fields on the project summary task.

        Strategy:
          1. If an XML file path was supplied, parse the XML directly — this is
             the most reliable path for original MS Project exports and avoids
             MPXJ's FieldID remapping issue.
          2. Fall back to MPXJ in-memory cache via getCachedValue().
        """
        fp = getattr(self, '_file_path', None)
        if fp and fp.lower().endswith('.xml'):
            try:
                return self._read_enterprise_fields_from_xml(fp)
            except Exception as e:
                print(f"[WARN] enterprise fields XML read: {e}")
        # Fallback: read from MPXJ in-memory project
        return self._read_enterprise_fields_from_project()

    def _read_enterprise_fields_from_xml(self, file_path):
        """Parse enterprise field values for UID=0 directly from MSPDI XML."""
        import xml.etree.ElementTree as ET

        NS = 'http://schemas.microsoft.com/project'
        tree = ET.parse(file_path)
        root = tree.getroot()

        # -- 1. Build FieldID → field name from project-level definitions --
        # Show all UserDef=1 fields (ElemType=20 Task and =21 Resource).
        # Resource fields (ElemType=21) will appear with an empty value because
        # their values are stored per resource, not on Task UID=0.
        fid_to_name = {}   # int FieldID → display name str
        ea_section = root.find(f'{{{NS}}}ExtendedAttributes')
        if ea_section is not None:
            for ea_def in ea_section.findall(f'{{{NS}}}ExtendedAttribute'):
                udf_el   = ea_def.find(f'{{{NS}}}UserDef')
                if udf_el is None or udf_el.text != '1':
                    continue
                fid_el   = ea_def.find(f'{{{NS}}}FieldID')
                name_el  = ea_def.find(f'{{{NS}}}FieldName')
                alias_el = ea_def.find(f'{{{NS}}}Alias')
                if fid_el is None or name_el is None:
                    continue
                # Prefer <Alias> (set by MPXJ on round-trip) over <FieldName>
                display = (alias_el.text or '').strip() if alias_el is not None and alias_el.text else (name_el.text or '').strip()
                try:
                    fid_to_name[int(fid_el.text)] = display
                except (ValueError, TypeError):
                    pass

        if not fid_to_name:
            return []

        # -- 2. Find the project summary task (UID=0) --
        summary_task_el = None
        for task_el in root.findall(f'.//{{{NS}}}Task'):
            uid_el = task_el.find(f'{{{NS}}}UID')
            if uid_el is not None and uid_el.text == '0':
                summary_task_el = task_el
                break

        if summary_task_el is None:
            return []

        # -- 3. Collect FieldID → value from <EnterpriseExtendedAttribute> elements --
        fid_to_value = {}
        for ea in summary_task_el.findall(f'{{{NS}}}EnterpriseExtendedAttribute'):
            fid_el = ea.find(f'{{{NS}}}FieldID')
            val_el = ea.find(f'{{{NS}}}Value')
            if fid_el is None:
                continue
            try:
                fid = int(fid_el.text)
            except (ValueError, TypeError):
                continue
            val = (val_el.text or '') if val_el is not None else ''
            fid_to_value[fid] = val

        # -- 4. Build result: all defined enterprise fields, with values where set --
        result = []
        for fid, name in sorted(fid_to_name.items(), key=lambda x: x[1]):
            val_str = fid_to_value.get(fid, '')
            result.append((name, val_str, f'FieldID: {fid}'))
        return result

    def _read_enterprise_fields_from_project(self):
        """Fallback: read enterprise field values from MPXJ in-memory project."""
        result = []
        try:
            from org.mpxj import UserDefinedField  # type: ignore

            summary_task = None
            for t in self._project.getTasks():
                try:
                    if int(str(t.getUniqueID())) == 0:
                        summary_task = t
                        break
                except Exception:
                    pass

            if summary_task is None:
                return result

            for cf in self._project.getCustomFields():
                ft = cf.getFieldType()
                if ft is None:
                    continue
                if str(ft.getFieldTypeClass()) != 'TASK':
                    continue
                if not isinstance(ft, UserDefinedField):
                    continue
                raw = summary_task.getCachedValue(ft)
                alias = str(cf.getAlias()) if cf.getAlias() else str(ft)
                val_str = ''
                if raw is not None:
                    val_str = str(raw)
                    if val_str in ('null', 'None'):
                        val_str = ''
                result.append((alias, val_str, str(ft)))
        except Exception as e:
            print(f"[WARN] enterprise fields fallback load: {e}")
        return result

    # -- Project Properties (free-form metadata key/value) --

    def _subtab_project_props(self):
        w = QWidget()
        vbox = QVBoxLayout(w)
        vbox.setContentsMargins(12, 12, 12, 12)
        vbox.setSpacing(6)

        hint = QLabel("Custom properties stored in the project file. "
                      "Add well-known fields from the dropdown, or type a custom name.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #808080; font-size: 10px;")
        vbox.addWidget(hint)

        self._tbl_custom = QTableWidget(0, 3)
        self._tbl_custom.setHorizontalHeaderLabels(["Name", "Value", ""])
        self._tbl_custom.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._tbl_custom.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self._tbl_custom.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self._tbl_custom.horizontalHeader().resizeSection(2, 28)
        self._tbl_custom.setSelectionBehavior(QTableWidget.SelectRows)
        self._tbl_custom.setAlternatingRowColors(True)
        self._tbl_custom.setContextMenuPolicy(Qt.CustomContextMenu)
        self._tbl_custom.customContextMenuRequested.connect(self._custom_context_menu)

        try:
            cp = self._props.getCustomProperties()
            if cp is not None:
                for key in cp.keySet():
                    val = cp.get(key)
                    self._custom_tbl_add_row(str(key), str(val) if val is not None else "")
        except Exception as e:
            print(f"[WARN] custom fields load: {e}")

        vbox.addWidget(self._tbl_custom)

        add_row = QHBoxLayout()
        add_row.setSpacing(4)
        self._add_key_combo = QComboBox()
        self._add_key_combo.setEditable(True)
        for name in _WELL_KNOWN_FIELDS:
            self._add_key_combo.addItem(name)
        self._add_key_combo.setCurrentIndex(-1)
        self._add_key_combo.lineEdit().setPlaceholderText("Select or type field name\u2026")
        self._add_key_combo.setMinimumWidth(200)
        self._add_val_edit = QLineEdit()
        self._add_val_edit.setPlaceholderText("Value")
        btn_add = QPushButton("+ Add")
        btn_add.setFixedHeight(26)
        btn_add.clicked.connect(self._custom_add_row)
        add_row.addWidget(self._add_key_combo, 2)
        add_row.addWidget(self._add_val_edit, 2)
        add_row.addWidget(btn_add)
        add_row.addStretch()
        vbox.addLayout(add_row)
        return w

    # -- Generic entity-field subtab (task or resource) --

    def _subtab_entity_fields(self, entity):
        """Build the Task Fields or Resource Fields sub-tab.

        *entity* is 'task' or 'resource'.
        """
        is_task = (entity == "task")
        java_class = 'org.mpxj.TaskField' if is_task else 'org.mpxj.ResourceField'
        ftc_attr   = 'TASK'               if is_task else 'RESOURCE'
        hint_text  = (
            "Define custom field aliases for tasks.  Each slot (Text1, Number1 …) can "
            "have a display name (alias).  Right-click a row to delete the definition."
            if is_task else
            "Define custom field aliases for resources.  Right-click a row to delete."
        )

        w = QWidget()
        vbox = QVBoxLayout(w)
        vbox.setContentsMargins(12, 12, 12, 12)
        vbox.setSpacing(6)

        hint = QLabel(hint_text)
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #808080; font-size: 10px;")
        vbox.addWidget(hint)

        tbl = QTableWidget(0, 3)
        tbl.setHorizontalHeaderLabels(["Slot", "Alias", ""])
        tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.Interactive)
        tbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        tbl.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        tbl.horizontalHeader().resizeSection(0, 130)
        tbl.horizontalHeader().resizeSection(2, 28)
        tbl.setAlternatingRowColors(True)
        tbl.verticalHeader().setVisible(False)
        tbl.verticalHeader().setDefaultSectionSize(22)
        tbl.setSelectionBehavior(QTableWidget.SelectRows)
        tbl.setEditTriggers(QTableWidget.DoubleClicked | QTableWidget.EditKeyPressed)
        tbl.setContextMenuPolicy(Qt.CustomContextMenu)

        # State stored on self so apply() can reach it
        ft_list_attr    = f"_ef_ft_list_{entity}"    # [(row, ft), ...]
        del_list_attr   = f"_ef_del_list_{entity}"   # [ft, ...]
        tbl_attr        = f"_ef_tbl_{entity}"
        slot_combo_attr = f"_ef_slot_combo_{entity}"
        slot_items_attr = f"_ef_slot_items_{entity}"
        setattr(self, ft_list_attr, [])
        setattr(self, del_list_attr, [])
        setattr(self, tbl_attr, tbl)

        # ── Shared single-row delete (used by × button and context menu) ──────
        def _delete_rows(rows_to_del,
                         _tbl=tbl, _ft_attr=ft_list_attr, _del_attr=del_list_attr,
                         _sc_attr=slot_combo_attr, _si_attr=slot_items_attr):
            ft_list    = getattr(self, _ft_attr)
            del_list   = getattr(self, _del_attr)
            slot_combo = getattr(self, _sc_attr, None)
            slot_items = getattr(self, _si_attr, [])
            for r in sorted(rows_to_del, reverse=True):
                for i, (ri, ft) in enumerate(ft_list):
                    if ri == r:
                        del_list.append(ft)
                        ft_list.pop(i)
                        label = str(ft)
                        slot_items.append((label, ft))
                        if slot_combo is not None:
                            slot_combo.addItem(label)
                        break
                ft_list[:] = [(ri - 1 if ri > r else ri, f) for ri, f in ft_list]
                _tbl.removeRow(r)

        def _make_del_btn(row_ref):
            """Return a × QPushButton that deletes its own row."""
            btn = QPushButton("×")
            btn.setFixedSize(22, 22)
            btn.setStyleSheet(
                "QPushButton { color: #c00; border: none; font-weight: bold; }"
                "QPushButton:hover { color: #f00; }"
            )
            def _clicked(_tbl=tbl):
                # find the current row of this button
                for r in range(_tbl.rowCount()):
                    if _tbl.cellWidget(r, 2) is btn:
                        _delete_rows([r])
                        return
            btn.clicked.connect(_clicked)
            return btn

        used_ft_strs = set()
        try:
            from org.mpxj import FieldTypeClass  # type: ignore
            fc = getattr(FieldTypeClass, ftc_attr)
            for cf in self._project.getCustomFields():
                ft = cf.getFieldType()
                if ft is None:
                    continue
                try:
                    if ft.getFieldTypeClass() != fc:
                        continue
                except Exception:
                    pass
                alias     = str(cf.getAlias()) if cf.getAlias() else ""
                slot_name = str(ft)
                row = tbl.rowCount()
                tbl.insertRow(row)
                slot_item = QTableWidgetItem(slot_name)
                slot_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                tbl.setItem(row, 0, slot_item)
                tbl.setItem(row, 1, QTableWidgetItem(alias))
                tbl.setCellWidget(row, 2, _make_del_btn(row))
                getattr(self, ft_list_attr).append((row, ft))
                used_ft_strs.add(slot_name)
        except Exception as e:
            print(f"[WARN] entity fields load ({entity}): {e}")

        vbox.addWidget(tbl)

        # Context menu (also triggers shared _delete_rows)
        def _ctx_menu(pos, _tbl=tbl):
            if not _tbl.indexAt(pos).isValid():
                return
            menu = QMenu(_tbl)
            act_del = QAction("Delete", menu)
            act_del.triggered.connect(
                lambda: _delete_rows({i.row() for i in _tbl.selectedIndexes()})
            )
            menu.addAction(act_del)
            menu.exec_(_tbl.viewport().mapToGlobal(pos))

        tbl.customContextMenuRequested.connect(_ctx_menu)

        # Add panel
        add_row = QHBoxLayout()
        add_row.setSpacing(4)

        slot_combo = QComboBox()
        slot_combo.setEditable(True)
        slot_combo.setInsertPolicy(QComboBox.NoInsert)
        slot_combo.lineEdit().setPlaceholderText("Select or type slot name…")
        slot_combo.setMinimumWidth(120)
        slot_items = _build_cf_slot_combo(slot_combo, java_class, used_ft_strs)
        # Build a name→ft lookup for free-typed entries
        slot_name_map = {display: ft for display, ft in slot_items}
        setattr(self, slot_combo_attr, slot_combo)
        setattr(self, slot_items_attr, slot_items)

        alias_edit = QLineEdit()
        alias_edit.setPlaceholderText("Alias")

        btn_add = QPushButton("+ Add")
        btn_add.setFixedHeight(26)
        btn_add.setStyleSheet(_BUTTON_STYLE)

        def _do_add(_sc=slot_combo, _si=slot_items, _ae=alias_edit,
                    _tbl=tbl, _ft_attr=ft_list_attr, _snm=slot_name_map):
            typed = _sc.currentText().strip()
            if not typed:
                return
            idx = _sc.currentIndex()
            # Try to resolve ft: prefer exact index match, then name lookup
            ft = None
            if 0 <= idx < len(_si) and _si[idx][0] == typed:
                ft = _si[idx][1]
            else:
                ft = _snm.get(typed)
            display = typed
            alias = _ae.text().strip() or display
            row = _tbl.rowCount()
            _tbl.insertRow(row)
            slot_label = str(ft) if ft is not None else typed
            slot_item = QTableWidgetItem(slot_label)
            slot_item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            _tbl.setItem(row, 0, slot_item)
            _tbl.setItem(row, 1, QTableWidgetItem(alias))
            _tbl.setCellWidget(row, 2, _make_del_btn(row))
            if ft is not None:
                getattr(self, _ft_attr).append((row, ft))
                # Remove from combo list
                for i, (d, _) in enumerate(_si):
                    if d == typed:
                        _si.pop(i)
                        _sc.removeItem(_sc.findText(typed))
                        break
            _ae.clear()
            _sc.clearEditText()

        btn_add.clicked.connect(lambda: _do_add())
        add_row.addWidget(slot_combo, 2)
        add_row.addWidget(alias_edit, 3)
        add_row.addWidget(btn_add)
        vbox.addLayout(add_row)
        return w

    def _custom_tbl_add_row(self, key, val):
        """Insert a row with a × delete button into the custom-properties table."""
        tbl = self._tbl_custom
        r = tbl.rowCount()
        tbl.insertRow(r)
        tbl.setItem(r, 0, QTableWidgetItem(key))
        tbl.setItem(r, 1, QTableWidgetItem(val))
        btn = QPushButton("×")
        btn.setFixedSize(22, 22)
        btn.setStyleSheet(
            "QPushButton { color: #c00; border: none; font-weight: bold; }"
            "QPushButton:hover { color: #f00; }"
        )
        btn.clicked.connect(lambda: self._custom_del_btn_row(btn))
        tbl.setCellWidget(r, 2, btn)

    def _custom_del_btn_row(self, btn):
        """Remove the row whose × button was clicked."""
        tbl = self._tbl_custom
        for r in range(tbl.rowCount()):
            if tbl.cellWidget(r, 2) is btn:
                tbl.removeRow(r)
                return

    def _custom_add_row(self):
        key = self._add_key_combo.currentText().strip()
        if not key:
            return
        self._custom_tbl_add_row(key, self._add_val_edit.text())
        self._add_key_combo.setCurrentIndex(-1)

    def _custom_context_menu(self, pos):
        index = self._tbl_custom.indexAt(pos)
        if not index.isValid():
            return
        menu = QMenu(self._tbl_custom)
        act_del = QAction("Delete", menu)
        act_del.triggered.connect(self._custom_del_row)
        menu.addAction(act_del)
        menu.exec_(self._tbl_custom.viewport().mapToGlobal(pos))

    def _custom_del_row(self):
        rows = sorted({idx.row() for idx in self._tbl_custom.selectedIndexes()}, reverse=True)
        for r in rows:
            self._tbl_custom.removeRow(r)

    def _tab_settings(self):
        props = self._props
        w = QWidget()
        f = QFormLayout(w)
        f.setContentsMargins(16, 16, 16, 16)
        f.setSpacing(10)

        def chk(getter):
            b = QCheckBox()
            try:
                v = getter()
                b.setChecked(bool(v) if v is not None else False)
            except Exception:
                pass
            return b

        self._chk_manual   = chk(props.getNewTasksAreManual)
        self._chk_honor    = chk(props.getHonorConstraints)
        self._chk_autolink = chk(props.getAutolink)
        self._chk_effort   = chk(props.getNewTasksEffortDriven)
        self._chk_est      = chk(props.getNewTasksEstimated)
        self._chk_multi    = chk(props.getMultipleCriticalPaths)
        self._chk_splits   = chk(props.getSplitInProgressTasks)

        self._e_crit_slack = QLineEdit("0")
        try:
            cs = props.getCriticalSlackLimit()
            if cs is not None:
                try:
                    self._e_crit_slack.setText(str(float(str(cs.getDuration()))))
                except Exception:
                    self._e_crit_slack.setText(str(cs))
        except Exception:
            pass

        _TT_NAMES  = ["FIXED_UNITS", "FIXED_DURATION", "FIXED_WORK"]
        _TT_LABELS = ["Fixed Units", "Fixed Duration", "Fixed Work"]
        self._c_task_type = QComboBox()
        self._c_task_type.addItems(_TT_LABELS)
        try:
            tt = str(props.getDefaultTaskType())
            if tt in _TT_NAMES:
                self._c_task_type.setCurrentIndex(_TT_NAMES.index(tt))
        except Exception:
            pass

        f.addRow("New Tasks Are Manual:",     self._chk_manual)
        f.addRow("Honor Constraints:",        self._chk_honor)
        f.addRow("Autolink Tasks:",           self._chk_autolink)
        f.addRow("New Tasks Effort Driven:",  self._chk_effort)
        f.addRow("New Tasks Estimated:",      self._chk_est)
        f.addRow("Multiple Critical Paths:",  self._chk_multi)
        f.addRow("Splits in Progress Tasks:", self._chk_splits)
        f.addRow("Critical Slack Limit (d):", self._e_crit_slack)
        f.addRow("Default Task Type:",        self._c_task_type)
        return w

    # ---------------------------------------------------------------- #
    # Apply                                                             #
    # ---------------------------------------------------------------- #

    def apply(self):
        props = self._props

        def _s(fn, val):
            try:
                fn(val)
            except Exception as e:
                print(f"[WARN] ProjectInfo.apply: {e}")

        def _str_to_ldt(s):
            from java.time import LocalDateTime  # type: ignore
            s = s.strip().replace(" ", "T")
            if len(s) == 10:
                s += "T00:00:00"
            elif len(s) == 16:
                s += ":00"
            return LocalDateTime.parse(s)

        def _str_to_lt(s):
            from java.time import LocalTime  # type: ignore
            s = s.strip()
            if len(s) == 5:
                s += ":00"
            return LocalTime.parse(s)

        # Summary
        _s(props.setProjectTitle, self._e_title.text().strip()    or None)
        _s(props.setSubject,  self._e_subject.text().strip()  or None)
        _s(props.setAuthor,   self._e_author.text().strip()   or None)
        _s(props.setManager,  self._e_manager.text().strip()  or None)
        _s(props.setCompany,  self._e_company.text().strip()  or None)
        _s(props.setCategory, self._e_category.text().strip() or None)
        _s(props.setKeywords, self._e_keywords.text().strip() or None)
        _s(props.setComments, self._e_comments.toPlainText().strip() or None)

        # Project dates
        _min_dt = QDateTime(QDate(1900, 1, 1), QTime(0, 0))
        for dte, setter in [
            (self._e_start,  props.setStartDate),
            (self._e_finish, props.setFinishDate),
            (self._e_status, props.setStatusDate),
        ]:
            try:
                if dte.dateTime() > _min_dt:
                    raw = dte.dateTime().toString("yyyy-MM-dd HH:mm")
                    _s(setter, _str_to_ldt(raw))
            except Exception as e:
                print(f"[WARN] ProjectInfo date parse: {e}")

        # Schedule from
        try:
            import jpype  # type: ignore
            ScheduleFrom = jpype.JClass("org.mpxj.ScheduleFrom")
            sf = ScheduleFrom.FINISH if self._c_schedule.currentIndex() == 1 else ScheduleFrom.START
            props.setScheduleFrom(sf)
        except Exception as e:
            print(f"[WARN] ProjectInfo scheduleFrom: {e}")

        # Calendar times
        for te, setter in [
            (self._e_def_start,  props.setDefaultStartTime),
            (self._e_def_finish, props.setDefaultEndTime),
        ]:
            try:
                raw = te.time().toString("HH:mm")
                _s(setter, _str_to_lt(raw))
            except Exception as e:
                print(f"[WARN] ProjectInfo time parse: {e}")

        try:
            props.setMinutesPerDay(int(float(self._e_hours_day.text()) * 60))
        except Exception:
            pass
        try:
            props.setMinutesPerWeek(int(float(self._e_hours_week.text()) * 60))
        except Exception:
            pass
        try:
            props.setDaysPerMonth(int(self._e_days_month.text()))
        except Exception:
            pass

        # Week start day
        try:
            import jpype  # type: ignore
            DayOfWeek = jpype.JClass("java.time.DayOfWeek")
            props.setWeekStartDay(DayOfWeek.valueOf(self._c_week_start.currentText().upper()))
        except Exception as e:
            print(f"[WARN] ProjectInfo weekStartDay: {e}")

        # Currency
        _s(props.setCurrencySymbol, self._e_curr_sym.text().strip() or None)
        _s(props.setCurrencyCode,   self._e_curr_code.text().strip() or None)
        try:
            props.setCurrencyDigits(int(self._e_curr_digits.text()))
        except Exception:
            pass
        try:
            import jpype  # type: ignore
            CSP = jpype.JClass("org.mpxj.CurrencySymbolPosition")
            _POS = ["BEFORE", "AFTER", "BEFORE_WITH_SPACE", "AFTER_WITH_SPACE"]
            props.setSymbolPosition(CSP.valueOf(_POS[self._c_curr_pos.currentIndex()]))
        except Exception as e:
            print(f"[WARN] ProjectInfo currencyPos: {e}")

        # Settings
        _s(props.setNewTasksAreManual,     bool(self._chk_manual.isChecked()))
        _s(props.setHonorConstraints,      bool(self._chk_honor.isChecked()))
        _s(props.setAutolink,              bool(self._chk_autolink.isChecked()))
        _s(props.setNewTasksEffortDriven,  bool(self._chk_effort.isChecked()))
        _s(props.setNewTasksEstimated,     bool(self._chk_est.isChecked()))
        _s(props.setMultipleCriticalPaths, bool(self._chk_multi.isChecked()))
        _s(props.setSplitInProgressTasks, bool(self._chk_splits.isChecked()))

        try:
            from org.mpxj import Duration, TimeUnit  # type: ignore
            slack = float(self._e_crit_slack.text())
            props.setCriticalSlackLimit(Duration.getInstance(slack, TimeUnit.DAYS))
        except Exception:
            pass

        try:
            import jpype  # type: ignore
            TaskType = jpype.JClass("org.mpxj.TaskType")
            _TT = ["FIXED_UNITS", "FIXED_DURATION", "FIXED_WORK"]
            props.setDefaultTaskType(TaskType.valueOf(_TT[self._c_task_type.currentIndex()]))
        except Exception as e:
            print(f"[WARN] ProjectInfo taskType: {e}")

        # Custom properties
        try:
            import java.util  # type: ignore
            cp = java.util.HashMap()
            for row in range(self._tbl_custom.rowCount()):
                key_item = self._tbl_custom.item(row, 0)
                val_item = self._tbl_custom.item(row, 1)
                key = key_item.text().strip() if key_item else ""
                val = val_item.text().strip() if val_item else ""
                if key:
                    cp.put(key, val)
            props.setCustomProperties(cp)
        except Exception as e:
            print(f"[WARN] ProjectInfo customProperties: {e}")

        # ---- Save Task / Resource field definitions ----
        for entity in ("task", "resource"):
            ft_list_attr  = f"_ef_ft_list_{entity}"
            del_list_attr = f"_ef_del_list_{entity}"
            tbl_attr      = f"_ef_tbl_{entity}"
            if not hasattr(self, ft_list_attr):
                continue
            try:
                # Remove deleted definitions
                for ft in getattr(self, del_list_attr, []):
                    try:
                        cfc = self._project.getCustomFields()
                        existing = cfc.get(ft)
                        if existing is not None:
                            cfc.add(ft)  # re-add with empty alias effectively clears
                            existing.setAlias(None)
                    except Exception:
                        pass
                # Update / create definitions with aliases
                tbl = getattr(self, tbl_attr)
                for row, ft in getattr(self, ft_list_attr, []):
                    alias_item = tbl.item(row, 1)
                    alias = alias_item.text().strip() if alias_item else ""
                    try:
                        cf_def = self._project.getCustomFields().getOrCreate(ft)
                        cf_def.setAlias(alias if alias else None)
                    except Exception as fe:
                        print(f"[WARN] entity field alias save ({entity}): {fe}")
            except Exception as e:
                print(f"[WARN] ProjectInfo entity fields save ({entity}): {e}")

        # ---- Save calendar changes ----
        if hasattr(self, "_cal_editors"):
            try:
                import java.time as _jt  # type: ignore
                import jpype  # type: ignore
                DayType   = jpype.JClass("org.mpxj.DayType")
                DOWS      = list(_jt.DayOfWeek.values())
                for uid, info in self._cal_editors.items():
                    cal = info["cal"]
                    # Name
                    new_name = info["name"].text().strip()
                    if new_name:
                        try:
                            cal.setName(new_name)
                        except Exception:
                            pass
                    # Default calendar flag
                    if info["default"].isChecked():
                        try:
                            self._project.setDefaultCalendar(cal)
                        except Exception:
                            try:
                                cal.setDefault(True)
                            except Exception:
                                pass
                    # Parent / base calendar
                    parent_combo = info.get("parent_combo")
                    if parent_combo is not None:
                        try:
                            parent_uid = parent_combo.currentData()
                            if parent_uid is None:
                                cal.setParent(None)
                            else:
                                for _pc in self._project.getCalendars():
                                    try:
                                        if int(_pc.getUniqueID()) == parent_uid:
                                            cal.setParent(_pc)
                                            break
                                    except Exception:
                                        pass
                        except Exception as e:
                            print(f"[WARN] calendar parent save: {e}")
                    # Day types
                    for i, dow in enumerate(DOWS):
                        if i < len(info["days"]):
                            dt_str = info["days"][i].currentText()
                            try:
                                cal.setCalendarDayType(dow, DayType.valueOf(dt_str))
                            except Exception:
                                pass
                    # Exceptions: rebuild from exc_tbl
                    exc_tbl = info.get("exc_tbl")
                    if exc_tbl is not None:
                        try:
                            cal.clearCalendarExceptions()
                            from java.time import LocalDate  # type: ignore
                            for row in range(exc_tbl.rowCount()):
                                name_item = exc_tbl.item(row, 0)
                                from_de   = exc_tbl.cellWidget(row, 1)
                                to_de     = exc_tbl.cellWidget(row, 2)
                                from_str  = from_de.date().toString("yyyy-MM-dd") if from_de else ""
                                to_str    = to_de.date().toString("yyyy-MM-dd")   if to_de   else ""
                                exc_name  = name_item.text().strip() if name_item else ""
                                if from_str:
                                    try:
                                        from_date = LocalDate.parse(from_str)
                                        to_date   = LocalDate.parse(to_str if to_str else from_str)
                                        ex = cal.addCalendarException(from_date, to_date)
                                        if exc_name:
                                            ex.setName(exc_name)
                                    except Exception as ex_e:
                                        print(f"[WARN] exception parse: {ex_e}")
                        except Exception as e:
                            print(f"[WARN] calendar exceptions save: {e}")
            except Exception as e:
                print(f"[WARN] ProjectInfo.apply calendars: {e}")


# ------------------------------------------------------------------ #
# Active Directory – helpers                                           #
# ------------------------------------------------------------------ #

def _format_resource_name(display_name: str) -> str:
    """Format a display name as ``"Nachname, Vorname"``.

    If the value already contains ``", "`` it is returned unchanged.
    Otherwise the last space-separated token is treated as the surname.
    Falls back to *display_name* unchanged when there is only one token.
    """
    if not display_name:
        return display_name
    if ", " in display_name:
        return display_name
    parts = display_name.strip().split()
    if len(parts) < 2:
        return display_name
    nachname = parts[-1]
    vorname  = " ".join(parts[:-1])
    return f"{nachname}, {vorname}"


def _ad_initials(display_name: str) -> str:
    """Return up to two uppercase initials extracted from *display_name*."""
    parts = display_name.replace(",", " ").split()
    return "".join(p[0].upper() for p in parts if p)[:2] if parts else "?"


# ------------------------------------------------------------------ #
# Resource thumbnail store (populated by ui.py on project open/close) #
# ------------------------------------------------------------------ #

_resource_thumbnail_store: dict = {}   # str(uid) → bytes
_resource_dept_store: dict = {}        # str(uid) → str
_resource_thumbnail_sidecar: str | None = None


def set_resource_thumbnail_store(store: dict, dept_store: dict = None, sidecar_path=None) -> None:
    """Called by ui.py when a project is opened or closed to wire up the store."""
    global _resource_thumbnail_store, _resource_dept_store, _resource_thumbnail_sidecar
    _resource_thumbnail_store = store
    _resource_dept_store = dept_store if dept_store is not None else {}
    _resource_thumbnail_sidecar = sidecar_path


def _save_resource_thumbnail_sidecar() -> None:
    """Persist thumbnail + department stores to the shared sidecar JSON.

    Format::

        {
          "resources": {
            "<uid>": {
              "thumbnail": "<base64>",   # optional
              "department": "Engineering" # optional
            }
          }
        }
    """
    import base64
    import json
    if not _resource_thumbnail_sidecar:
        return
    try:
        # Collect all UIDs that appear in either store
        all_uids = set(_resource_thumbnail_store) | set(_resource_dept_store)
        resources: dict = {}
        for uid in all_uids:
            entry: dict = {}
            if uid in _resource_thumbnail_store:
                entry["thumbnail"] = base64.b64encode(_resource_thumbnail_store[uid]).decode()
            if uid in _resource_dept_store and _resource_dept_store[uid]:
                entry["department"] = _resource_dept_store[uid]
            if entry:
                resources[uid] = entry
        with open(_resource_thumbnail_sidecar, "w", encoding="utf-8") as _f:
            json.dump({"resources": resources}, _f, indent=2)
    except Exception as _e:
        print(f"[WARN] resource sidecar save: {_e}")


def _resource_type_pixmap(res_type: str, size: int = 64):
    """Return a circular QPixmap fallback avatar for the given resource type.

    WORK     → blue circle  + 👷 (Bauarbeiter / construction worker)
    MATERIAL → green circle + 📦 (package / box)
    COST     → orange circle + 💰 (money bag)

    Emoji are drawn via the "Segoe UI Emoji" font (Windows 10/11).  If the
    glyph fails to render (older platform / font missing) the function falls
    back to the abbreviated text label so the avatar is never blank.
    """
    from PyQt5.QtGui import QPixmap, QPainter, QColor, QBrush, QFont  # type: ignore
    from PyQt5.QtCore import Qt  # type: ignore

    configs = {
        "WORK":     ("#2B579A", "\U0001f477", "WK"),   # 👷
        "MATERIAL": ("#2E7D32", "\U0001f4e6", "MT"),   # 📦
        "COST":     ("#E65100", "\U0001f4b0", "CO"),   # 💰
    }
    rtype = (res_type or "").strip().upper().split("_")[0]
    color, emoji, fallback_text = configs.get(rtype, configs["WORK"])

    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QBrush(QColor(color)))
    p.setPen(Qt.NoPen)
    p.drawEllipse(0, 0, size, size)

    # Try emoji first (Segoe UI Emoji, Windows 10/11)
    emoji_font = QFont("Segoe UI Emoji")
    emoji_font.setPixelSize(max(1, int(size * 0.55)))
    p.setFont(emoji_font)
    p.setPen(QColor("white"))   # pen must be non-NoPen; emoji glyphs override colour
    p.drawText(pix.rect(), Qt.AlignCenter, emoji)

    # Check whether the glyph was actually drawn: sample the centre pixel.
    # If it's still the background colour the emoji font is absent — overlay
    # a plain-text fallback in white so the avatar is never blank.
    p.end()
    centre = pix.toImage().pixel(size // 2, size // 2)
    bg = QColor(color)
    drawn = QColor(centre)
    if (abs(drawn.red()   - bg.red())   < 8 and
            abs(drawn.green() - bg.green()) < 8 and
            abs(drawn.blue()  - bg.blue())  < 8):
        # Emoji did not change the pixel — draw text fallback
        p2 = QPainter(pix)
        p2.setRenderHint(QPainter.Antialiasing)
        txt_font = QFont()
        txt_font.setPixelSize(max(1, size // 3))
        txt_font.setBold(True)
        p2.setFont(txt_font)
        p2.setPen(QColor("white"))
        p2.drawText(pix.rect(), Qt.AlignCenter, fallback_text)
        p2.end()

    return pix


# ------------------------------------------------------------------ #
# Active Directory – Group Search Dialog                               #
# ------------------------------------------------------------------ #

class ADGroupSearchDialog(QDialog):
    """Search Active Directory for groups, preview their members, and add them.

    Workflow:
      1. User types a group name fragment and clicks "Search Groups".
      2. Matching groups are listed with checkboxes.
      3. Checking a group reveals its members in the Members panel.
      4. The user clicks "Add Members to Project" to accept.

    After ``exec_()`` returns ``QDialog.Accepted`` call
    ``get_selected_users()`` to retrieve the de-duplicated list of user
    dicts (same schema as :func:`ad_integration.lookup_by_name`).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Resources from AD Group")
        self.setModal(True)
        self.setStyleSheet(_DIALOG_STYLE)
        self.setMinimumWidth(700)
        self.setMinimumHeight(520)
        self._selected_users: list = []   # de-duplicated list of user dicts
        self._group_members: dict  = {}   # group_name -> [user dicts]
        self._group_checkboxes: dict = {} # group_name -> QCheckBox
        self._setup_ui()

    # ---------------------------------------------------------------- #
    # UI setup                                                           #
    # ---------------------------------------------------------------- #

    def _setup_ui(self):
        from PyQt5.QtWidgets import QSplitter, QScrollArea  # type: ignore

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(_make_header(
            "Add Resources from AD Group",
            "Search for an AD group and add all members as project resources",
        ))

        body = QWidget()
        body.setStyleSheet("background: white;")
        bv = QVBoxLayout(body)
        bv.setContentsMargins(16, 12, 16, 12)
        bv.setSpacing(10)

        # Search row
        search_row = QWidget()
        sh = QHBoxLayout(search_row)
        sh.setContentsMargins(0, 0, 0, 0)
        sh.setSpacing(8)

        lbl = QLabel("Group name:")
        lbl.setStyleSheet("font-size: 12px;")
        sh.addWidget(lbl)

        self._e_group = QLineEdit()
        self._e_group.setPlaceholderText("e.g. Team-Backend  or  Developers")
        self._e_group.returnPressed.connect(self._do_search)
        sh.addWidget(self._e_group, 1)

        self._search_btn = QPushButton("Search Groups")
        self._search_btn.setStyleSheet(_BUTTON_STYLE)
        self._search_btn.clicked.connect(self._do_search)
        sh.addWidget(self._search_btn)

        bv.addWidget(search_row)

        self._status_lbl = QLabel("")
        self._status_lbl.setWordWrap(True)
        self._status_lbl.setStyleSheet("color: #555; font-size: 11px;")
        bv.addWidget(self._status_lbl)

        # Splitter: groups on the left, members on the right
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(6)

        # ---- Left: group list with checkboxes ----
        groups_outer = QWidget()
        groups_outer.setStyleSheet("background: white;")
        gv = QVBoxLayout(groups_outer)
        gv.setContentsMargins(0, 0, 0, 0)
        gv.setSpacing(4)

        lbl_grps = QLabel("Groups found:")
        lbl_grps.setStyleSheet(
            "font-weight: bold; font-size: 11px; color: #2B579A;")
        gv.addWidget(lbl_grps)

        self._group_scroll = QScrollArea()
        self._group_scroll.setWidgetResizable(True)
        self._group_scroll.setFrameShape(QFrame.StyledPanel)
        self._group_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self._group_container = QWidget()
        self._group_container.setStyleSheet("background: white;")
        self._group_inner_layout = QVBoxLayout(self._group_container)
        self._group_inner_layout.setContentsMargins(4, 4, 4, 4)
        self._group_inner_layout.setSpacing(4)
        self._group_inner_layout.addStretch()
        self._group_scroll.setWidget(self._group_container)
        gv.addWidget(self._group_scroll, 1)

        splitter.addWidget(groups_outer)

        # ---- Right: members preview ----
        members_outer = QWidget()
        members_outer.setStyleSheet("background: white;")
        mv = QVBoxLayout(members_outer)
        mv.setContentsMargins(0, 0, 0, 0)
        mv.setSpacing(4)

        lbl_mbr = QLabel("Members preview:")
        lbl_mbr.setStyleSheet(
            "font-weight: bold; font-size: 11px; color: #2B579A;")
        mv.addWidget(lbl_mbr)

        self._members_tbl = QTableWidget(0, 3)
        self._members_tbl.setHorizontalHeaderLabels(["Name", "E-Mail", "Department"])
        hdr = self._members_tbl.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Stretch)
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self._members_tbl.setEditTriggers(QTableWidget.NoEditTriggers)
        self._members_tbl.setSelectionBehavior(QTableWidget.SelectRows)
        self._members_tbl.setAlternatingRowColors(True)
        self._members_tbl.verticalHeader().setVisible(False)
        self._members_tbl.verticalHeader().setDefaultSectionSize(24)
        mv.addWidget(self._members_tbl, 1)

        self._member_count_lbl = QLabel("")
        self._member_count_lbl.setStyleSheet("color: #555; font-size: 10px;")
        mv.addWidget(self._member_count_lbl)

        splitter.addWidget(members_outer)
        splitter.setSizes([280, 400])
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        bv.addWidget(splitter, 1)

        root.addWidget(body)

        # Button row
        btn_row = QWidget()
        btn_row.setStyleSheet("background: white;")
        bh = QHBoxLayout(btn_row)
        bh.setContentsMargins(12, 4, 12, 12)
        bh.addStretch()

        self._ok_btn = QPushButton("Add Members to Project")
        self._ok_btn.setStyleSheet(_BUTTON_STYLE)
        self._ok_btn.setEnabled(False)
        self._ok_btn.clicked.connect(self._accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(_BUTTON_STYLE)
        cancel_btn.clicked.connect(self.reject)
        bh.addWidget(self._ok_btn)
        bh.addWidget(cancel_btn)
        root.addWidget(btn_row)

    # ---------------------------------------------------------------- #
    # Search logic                                                       #
    # ---------------------------------------------------------------- #

    def _do_search(self):
        from PyQt5.QtWidgets import QApplication  # type: ignore
        try:
            from integrations import ad_integration  # type: ignore
        except ImportError:
            self._status_lbl.setText("Active Directory integration module not available.")
            return

        if not ad_integration.is_ad_available():
            self._status_lbl.setText(
                "Active Directory is not available on this machine.\n"
                "Ensure you are on a domain-joined Windows PC with RSAT installed."
            )
            return

        query = self._e_group.text().strip()
        if not query:
            self._status_lbl.setText("Please enter a group name to search for.")
            return

        self._search_btn.setEnabled(False)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            groups = ad_integration.search_groups(query)
        finally:
            QApplication.restoreOverrideCursor()
            self._search_btn.setEnabled(True)

        # Clear previous results
        self._group_members.clear()
        self._group_checkboxes.clear()
        while self._group_inner_layout.count() > 1:
            item = self._group_inner_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._members_tbl.setRowCount(0)
        self._member_count_lbl.setText("")
        self._ok_btn.setEnabled(False)

        if not groups:
            self._status_lbl.setText(f"No groups found matching \"{query}\".")
            return

        self._status_lbl.setText(
            f"Found {len(groups)} group(s). Check groups to preview members."
        )

        for group in groups:
            card = self._make_group_card(group)
            self._group_inner_layout.insertWidget(
                self._group_inner_layout.count() - 1, card
            )

    def _make_group_card(self, group: dict) -> QWidget:
        """Build a checkbox card for one group entry."""
        card = QFrame()
        card.setFrameShape(QFrame.StyledPanel)
        card.setStyleSheet(
            "QFrame { background: #FAFBFD; border: 1px solid #D0DBE8;"
            " border-radius: 4px; }"
            "QFrame:hover { background: #EBF0FB; }"
        )

        h = QHBoxLayout(card)
        h.setContentsMargins(8, 6, 8, 6)
        h.setSpacing(8)

        chk = QCheckBox()
        chk.setFixedSize(20, 20)
        h.addWidget(chk)

        info = QWidget()
        info.setStyleSheet("background: transparent;")
        iv = QVBoxLayout(info)
        iv.setContentsMargins(0, 0, 0, 0)
        iv.setSpacing(1)

        name_lbl = QLabel(group.get("name", ""))
        name_lbl.setStyleSheet(
            "font-weight: bold; font-size: 11px; color: #1F1F1F; border: none;")
        desc  = group.get("description") or ""
        scope = group.get("scope") or ""
        sub_parts = [str(x) for x in [scope, desc] if x]
        sub_lbl = QLabel("  \u00b7  ".join(sub_parts) if sub_parts else "")
        sub_lbl.setStyleSheet("color: #666; font-size: 10px; border: none;")
        sub_lbl.setWordWrap(True)

        iv.addWidget(name_lbl)
        iv.addWidget(sub_lbl)
        h.addWidget(info, 1)

        group_name = group.get("name", "")
        self._group_checkboxes[group_name] = chk
        chk.stateChanged.connect(
            lambda state, gn=group_name, gd=group.get("dn", group_name):
                self._on_group_toggled(gn, gd, state)
        )
        return card

    def _on_group_toggled(self, group_name: str, group_dn: str, state: int):
        """Load members when a group is checked; refresh the members table."""
        from PyQt5.QtWidgets import QApplication  # type: ignore
        if state == Qt.Checked and group_name not in self._group_members:
            try:
                from integrations import ad_integration  # type: ignore
                QApplication.setOverrideCursor(Qt.WaitCursor)
                try:
                    members = ad_integration.get_group_members(
                        group_dn if group_dn else group_name
                    )
                finally:
                    QApplication.restoreOverrideCursor()
                self._group_members[group_name] = members
            except Exception:
                self._group_members[group_name] = []

        self._refresh_members_table()

    def _refresh_members_table(self):
        """Rebuild the members table from all currently checked groups."""
        seen: set = set()
        all_members: list = []
        for gname, chk in self._group_checkboxes.items():
            if chk.isChecked():
                for m in self._group_members.get(gname, []):
                    key = m.get("username") or m.get("email", "")
                    if key and key not in seen:
                        seen.add(key)
                        all_members.append(m)

        self._members_tbl.setRowCount(0)
        for user in all_members:
            formatted = _format_resource_name(user.get("display_name", ""))
            r = self._members_tbl.rowCount()
            self._members_tbl.insertRow(r)
            self._members_tbl.setItem(r, 0, QTableWidgetItem(formatted))
            self._members_tbl.setItem(r, 1, QTableWidgetItem(user.get("email", "")))
            self._members_tbl.setItem(r, 2, QTableWidgetItem(user.get("department") or ""))

        count = len(all_members)
        if count:
            self._member_count_lbl.setText(f"{count} unique member(s) will be added.")
        else:
            self._member_count_lbl.setText("")
        self._ok_btn.setEnabled(count > 0)
        self._selected_users = all_members

    # ---------------------------------------------------------------- #
    # Accept / Result accessors                                         #
    # ---------------------------------------------------------------- #

    def _accept(self):
        self._refresh_members_table()
        if self._selected_users:
            self.accept()

    def get_selected_users(self) -> list:
        """Return the de-duplicated list of user dicts for the selected groups.

        Each entry is a dict with keys: display_name, email, department,
        username, city, state, country — same schema as the individual lookup
        functions in :mod:`integrations.ad_integration`.
        """
        return list(self._selected_users)


# ------------------------------------------------------------------ #
# New-Project optional holiday calendars dialog                        #
# ------------------------------------------------------------------ #

class NewProjectCalendarsDialog(_BaseDialog):
    """Dialog shown after a new project is created.

    Lets the user select optional regional holiday calendars to install
    alongside the default German national holiday calendar.  German state
    calendars are derived from the standard calendar (they inherit the
    national holidays) and only carry their state-specific extra exceptions.
    Country calendars are standalone.
    """

    _GERMAN_STATES = [
        "Baden-Württemberg",
        "Bayern",
        "Berlin",
        "Brandenburg",
        "Bremen",
        "Hamburg",
        "Hessen",
        "Mecklenburg-Vorpommern",
        "Niedersachsen",
        "Rheinland-Pfalz",
        "Saarland",
        "Sachsen",
        "Sachsen-Anhalt",
        "Schleswig-Holstein",
        "Thüringen",
    ]

    _OTHER_COUNTRIES = [
        "France",
        "India",
        "Romania",
        "China",
        "Japan",
    ]

    def __init__(self, parent=None):
        super().__init__("Install Optional Holiday Calendars", parent)
        self.setMinimumWidth(520)
        self._checkboxes: dict[str, QCheckBox] = {}

        self._root.addWidget(_make_header(
            "Install Optional Holiday Calendars",
            "Standard (Deutschland) calendar already created"
        ))

        body = QWidget()
        bv = QVBoxLayout(body)
        bv.setContentsMargins(16, 8, 16, 8)
        bv.setSpacing(10)

        info = QLabel(
            "A <b>Standard (Deutschland)</b> calendar with German national public "
            "holidays has been created and set as the project default.<br>"
            "Select any additional regional calendars to install:"
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #444; font-size: 12px; padding-bottom: 4px;")
        bv.addWidget(info)

        # ---- German federal states section ----
        states_grp = QWidget()
        states_grp.setStyleSheet(
            "QWidget { border: 1px solid #B8CBE4; border-radius: 4px; "
            "background: #F5F9FF; }"
        )
        sv = QVBoxLayout(states_grp)
        sv.setContentsMargins(10, 8, 10, 8)
        sv.setSpacing(4)

        lbl_states = QLabel("German Federal States")
        lbl_states.setStyleSheet(
            "font-weight: bold; color: #2B579A; font-size: 12px; border: none;"
        )
        sv.addWidget(lbl_states)

        hint_states = QLabel(
            "State calendars inherit the national holidays and add "
            "only the state-specific extra public holidays."
        )
        hint_states.setWordWrap(True)
        hint_states.setStyleSheet("color: #666; font-size: 10px; border: none;")
        sv.addWidget(hint_states)

        # Two-column grid for states
        grid_w = QWidget()
        grid_w.setStyleSheet("border: none;")
        from PyQt5.QtWidgets import QGridLayout  # type: ignore
        grid = QGridLayout(grid_w)
        grid.setContentsMargins(0, 4, 0, 0)
        grid.setSpacing(2)
        for idx, state in enumerate(self._GERMAN_STATES):
            chk = QCheckBox(state)
            chk.setChecked(False)
            grid.addWidget(chk, idx // 2, idx % 2)
            self._checkboxes[state] = chk
        sv.addWidget(grid_w)
        bv.addWidget(states_grp)

        # ---- Other countries section ----
        country_grp = QWidget()
        country_grp.setStyleSheet(
            "QWidget { border: 1px solid #B8CBE4; border-radius: 4px; "
            "background: #F5F9FF; }"
        )
        cv = QVBoxLayout(country_grp)
        cv.setContentsMargins(10, 8, 10, 8)
        cv.setSpacing(4)

        lbl_countries = QLabel("Other Countries")
        lbl_countries.setStyleSheet(
            "font-weight: bold; color: #2B579A; font-size: 12px; border: none;"
        )
        cv.addWidget(lbl_countries)

        for country in self._OTHER_COUNTRIES:
            chk = QCheckBox(country)
            chk.setChecked(False)
            cv.addWidget(chk)
            self._checkboxes[country] = chk
        bv.addWidget(country_grp)

        self._root.addWidget(body)
        self._root.addWidget(_make_button_row(self))

    def get_selected(self) -> list:
        """Return list of calendar names (states/countries) that were checked."""
        return [name for name, chk in self._checkboxes.items() if chk.isChecked()]


# ------------------------------------------------------------------ #
# Active Directory – user selection dialog                             #
# ------------------------------------------------------------------ #

class ADUserSelectDialog(QDialog):
    """Selection dialog shown when multiple AD users match the search query.

    Shows one clickable card per user; the user clicks the desired card to
    accept the dialog and retrieve the selected user via ``selected_user()``.
    """

    def __init__(self, users: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select User")
        self.setStyleSheet(_DIALOG_STYLE)
        self.setMinimumWidth(580)
        self.setMinimumHeight(320)
        self._selected = None
        self._thumb_jobs: list = []   # list of (username, QLabel)
        self._setup_ui(users)

    def _setup_ui(self, users: list):
        from PyQt5.QtWidgets import QScrollArea  # type: ignore
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        count = len(users)
        if count == 1:
            header_title = "User Found"
            header_sub   = "1 user matched your search – confirm to proceed"
        else:
            header_title = "Multiple Users Found"
            header_sub   = f"{count} users matched your search – please select one"
        root.addWidget(_make_header(header_title, header_sub))

        body = QWidget()
        body.setStyleSheet("background: white;")
        bv = QVBoxLayout(body)
        bv.setContentsMargins(12, 12, 12, 12)
        bv.setSpacing(6)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        inner = QWidget()
        inner.setStyleSheet("background: white;")
        inner_v = QVBoxLayout(inner)
        inner_v.setContentsMargins(0, 0, 0, 0)
        inner_v.setSpacing(6)

        for user in users:
            inner_v.addWidget(self._make_card(user))
        inner_v.addStretch()
        scroll.setWidget(inner)
        bv.addWidget(scroll)
        root.addWidget(body)

        cancel_row = QWidget()
        cancel_row.setStyleSheet("background: white;")
        ch = QHBoxLayout(cancel_row)
        ch.setContentsMargins(12, 4, 12, 12)
        ch.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(_BUTTON_STYLE)
        cancel_btn.clicked.connect(self.reject)
        ch.addWidget(cancel_btn)
        root.addWidget(cancel_row)

    def _make_card(self, user: dict) -> QFrame:
        """Build a clickable card widget for one AD user."""
        card = QFrame()
        card.setFrameShape(QFrame.StyledPanel)
        card.setCursor(Qt.PointingHandCursor)
        card.setStyleSheet(
            "QFrame { background: #FAFBFD; border: 1px solid #D0DBE8;"
            " border-radius: 6px; }"
            "QFrame:hover { background: #E8F0FB; border: 1px solid #2B579A; }"
        )

        h = QHBoxLayout(card)
        h.setContentsMargins(10, 8, 10, 8)
        h.setSpacing(10)

        # Initials / thumbnail placeholder
        thumb = QLabel()
        thumb.setFixedSize(40, 40)
        thumb.setAlignment(Qt.AlignCenter)
        thumb.setStyleSheet(
            "background: #2B579A; color: white; border-radius: 20px;"
            " font-weight: bold; font-size: 13px; border: none;"
        )
        thumb.setText(_ad_initials(user.get("display_name", "")))
        h.addWidget(thumb)
        # Schedule real-photo load after the dialog becomes visible
        uname = user.get("username", "")
        if uname:
            self._thumb_jobs.append((uname, thumb))

        # User info block
        info = QWidget()
        info.setStyleSheet("background: transparent;")
        iv = QVBoxLayout(info)
        iv.setContentsMargins(0, 0, 0, 0)
        iv.setSpacing(1)

        formatted = _format_resource_name(user.get("display_name", ""))
        name_lbl = QLabel(formatted)
        name_lbl.setStyleSheet(
            "font-weight: bold; font-size: 12px; color: #1F1F1F; border: none;"
        )
        email   = user.get("email", "")
        dept    = user.get("department") or ""
        sub_txt = email + (f"  ·  {dept}" if dept else "")
        sub_lbl = QLabel(sub_txt)
        sub_lbl.setStyleSheet("color: #555; font-size: 11px; border: none;")
        uname   = user.get("username", "")
        u_lbl   = QLabel(f"@{uname}" if uname else "")
        u_lbl.setStyleSheet("color: #888; font-size: 10px; border: none;")

        iv.addWidget(name_lbl)
        iv.addWidget(sub_lbl)
        iv.addWidget(u_lbl)
        h.addWidget(info, 1)

        # Make the whole card clickable
        card.mousePressEvent = lambda _evt, u=user: self._select(u)
        return card

    def showEvent(self, event):
        super().showEvent(event)
        if self._thumb_jobs:
            from PyQt5.QtCore import QTimer  # type: ignore
            QTimer.singleShot(0, self._load_thumbnails)

    def _load_thumbnails(self):
        """Load AD thumbnail photos for every user card (called after show)."""
        try:
            from integrations import ad_integration  # type: ignore
            from PyQt5.QtGui import QPixmap  # type: ignore
        except ImportError:
            return
        for username, lbl in self._thumb_jobs:
            try:
                img_bytes = ad_integration.get_thumbnail(username)
                if not img_bytes:
                    continue
                pix = QPixmap()
                if pix.loadFromData(img_bytes):
                    pix = pix.scaled(
                        40, 40,
                        Qt.KeepAspectRatioByExpanding,
                        Qt.SmoothTransformation,
                    )
                    lbl.setPixmap(pix)
                    lbl.setText("")
                    lbl.setStyleSheet(
                        "border: 1px solid #B8CBE4; border-radius: 20px;"
                        " background: transparent;"
                    )
            except Exception:
                pass

    def _select(self, user: dict):
        formatted = _format_resource_name(user.get("display_name", ""))
        user["formatted_name"] = formatted
        self._selected = user
        self.accept()

    def selected_user(self):
        """Return the chosen user dict, or ``None`` when the dialog was cancelled."""
        return self._selected


# ------------------------------------------------------------------ #
# Active Directory – resource search dialog                            #
# ------------------------------------------------------------------ #

class ADSearchDialog(QDialog):
    """Search Active Directory and add the result as a project resource.

    Searches by username (SAM), display name, or email address.  If a single
    user matches the query it is shown immediately for confirmation.  If
    multiple users match, :class:`ADUserSelectDialog` opens to let the user
    pick one.

    After ``exec_()`` returns ``QDialog.Accepted``, call ``get_resource_name()``
    to retrieve the formatted ``"Nachname, Vorname"`` string and
    ``get_user_data()`` for the full AD dict.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Add Resource from Active Directory")
        self.setStyleSheet(_DIALOG_STYLE)
        self.setMinimumWidth(500)
        self._selected_user = None
        self._setup_ui()

    # ---------------------------------------------------------------- #
    # UI setup                                                           #
    # ---------------------------------------------------------------- #

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(_make_header(
            "Add Resource from Active Directory",
            "Search by username, display name, or e-mail address",
        ))

        body = QWidget()
        body.setStyleSheet("background: white;")
        bv = QVBoxLayout(body)
        bv.setContentsMargins(16, 16, 16, 16)
        bv.setSpacing(10)

        form = QFormLayout()
        form.setSpacing(8)

        self._e_username = QLineEdit()
        self._e_username.setPlaceholderText("e.g. john.doe")
        form.addRow("Username (SAM):", self._e_username)

        self._e_name = QLineEdit()
        self._e_name.setPlaceholderText("e.g. Doe, John  or  John Doe")
        form.addRow("Display Name:", self._e_name)

        self._e_email = QLineEdit()
        self._e_email.setPlaceholderText("e.g. john.doe@company.com")
        form.addRow("E-Mail:", self._e_email)

        bv.addLayout(form)

        search_row = QWidget()
        sh = QHBoxLayout(search_row)
        sh.setContentsMargins(0, 0, 0, 0)
        self._search_btn = QPushButton("Search")
        self._search_btn.setStyleSheet(_BUTTON_STYLE)
        self._search_btn.clicked.connect(self._do_search)
        sh.addStretch()
        sh.addWidget(self._search_btn)
        bv.addWidget(search_row)

        self._status_lbl = QLabel("")
        self._status_lbl.setWordWrap(True)
        self._status_lbl.setStyleSheet("color: #555; font-size: 11px;")
        bv.addWidget(self._status_lbl)

        # Selected-user card (hidden until a result is confirmed)
        self._result_frame = QFrame()
        self._result_frame.setFrameShape(QFrame.StyledPanel)
        self._result_frame.setStyleSheet(
            "QFrame { background: #F5F8FF; border: 1px solid #B8CBE4;"
            " border-radius: 4px; }"
        )
        self._result_frame.setVisible(False)
        rf = QHBoxLayout(self._result_frame)
        rf.setContentsMargins(12, 10, 12, 10)
        rf.setSpacing(12)

        self._thumb_lbl = QLabel()
        self._thumb_lbl.setFixedSize(48, 48)
        self._thumb_lbl.setAlignment(Qt.AlignCenter)
        self._thumb_lbl.setStyleSheet(
            "background: #2B579A; color: white; border-radius: 24px;"
            " font-weight: bold; font-size: 15px; border: none;"
        )
        rf.addWidget(self._thumb_lbl)

        info_w = QWidget()
        info_w.setStyleSheet("background: transparent;")
        iv = QVBoxLayout(info_w)
        iv.setContentsMargins(0, 0, 0, 0)
        iv.setSpacing(2)
        self._res_name_lbl = QLabel()
        self._res_name_lbl.setStyleSheet(
            "font-weight: bold; font-size: 13px; color: #1F1F1F; border: none;"
        )
        self._res_email_lbl = QLabel()
        self._res_email_lbl.setStyleSheet("color: #555; font-size: 11px; border: none;")
        self._res_dept_lbl = QLabel()
        self._res_dept_lbl.setStyleSheet("color: #888; font-size: 11px; border: none;")
        iv.addWidget(self._res_name_lbl)
        iv.addWidget(self._res_email_lbl)
        iv.addWidget(self._res_dept_lbl)
        rf.addWidget(info_w, 1)
        bv.addWidget(self._result_frame)

        root.addWidget(body)

        btn_row = QWidget()
        btn_row.setStyleSheet("background: white;")
        bh = QHBoxLayout(btn_row)
        bh.setContentsMargins(12, 4, 12, 12)
        bh.addStretch()
        self._ok_btn = QPushButton("Add Resource")
        self._ok_btn.setStyleSheet(_BUTTON_STYLE)
        self._ok_btn.setEnabled(False)
        self._ok_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet(_BUTTON_STYLE)
        cancel_btn.clicked.connect(self.reject)
        bh.addWidget(self._ok_btn)
        bh.addWidget(cancel_btn)
        root.addWidget(btn_row)

        for edit in (self._e_username, self._e_name, self._e_email):
            edit.returnPressed.connect(self._do_search)

    # ---------------------------------------------------------------- #
    # Search logic                                                       #
    # ---------------------------------------------------------------- #

    def _do_search(self):
        from PyQt5.QtWidgets import QApplication  # type: ignore
        try:
            from integrations import ad_integration  # type: ignore
        except ImportError:
            self._status_lbl.setText(
                "Active Directory integration module not available."
            )
            return

        if not ad_integration.is_ad_available():
            self._status_lbl.setText(
                "Active Directory is not available on this machine.\n"
                "Ensure you are on a domain-joined Windows PC with RSAT installed."
            )
            return

        username = self._e_username.text().strip()
        name     = self._e_name.text().strip()
        email    = self._e_email.text().strip()

        if not username and not name and not email:
            self._status_lbl.setText("Please enter at least one search term.")
            return

        self._search_btn.setEnabled(False)
        try:
            from progress_worker import run_indeterminate  # type: ignore

            def _run_ad_search():
                results_inner = []
                seen_inner: set = set()

                def _merge(new_entries):
                    for r in new_entries:
                        key = r.get("username") or r.get("email", "")
                        if key and key not in seen_inner:
                            seen_inner.add(key)
                            results_inner.append(r)

                if username:
                    _merge(ad_integration.lookup_by_username_all(username))
                if name:
                    _merge(ad_integration.lookup_by_name_all(name))
                if email:
                    _merge(ad_integration.lookup_by_email_all(email))
                return results_inner

            results = run_indeterminate(
                self, "Searching Active Directory\u2026", _run_ad_search)
            if results is None:
                results = []
        except Exception:
            # Fallback to original blocking call without dialog
            results = []
            seen: set = set()

            def _merge(new_entries):
                for r in new_entries:
                    key = r.get("username") or r.get("email", "")
                    if key and key not in seen:
                        seen.add(key)
                        results.append(r)

            if username:
                _merge(ad_integration.lookup_by_username_all(username))
            if name:
                _merge(ad_integration.lookup_by_name_all(name))
            if email:
                _merge(ad_integration.lookup_by_email_all(email))
        finally:
            self._search_btn.setEnabled(True)

        if not results:
            self._status_lbl.setText("No matching users found in Active Directory.")
            self._result_frame.setVisible(False)
            self._ok_btn.setEnabled(False)
            self._selected_user = None
            return

        if len(results) == 1:
            self._set_selected(results[0])
        else:
            sel_dlg = ADUserSelectDialog(results, self)
            if sel_dlg.exec_() == QDialog.Accepted and sel_dlg.selected_user():
                self._set_selected(sel_dlg.selected_user())
            else:
                self._status_lbl.setText(
                    f"Found {len(results)} users. Refine your search or try again."
                )

    def _set_selected(self, user: dict):
        self._selected_user = user
        formatted = _format_resource_name(user.get("display_name", ""))
        user["formatted_name"] = formatted

        self._status_lbl.setText(f"Selected: {formatted}")
        self._res_name_lbl.setText(formatted)
        self._res_email_lbl.setText(user.get("email", ""))
        self._res_dept_lbl.setText(user.get("department") or "")
        self._result_frame.setVisible(True)
        self._ok_btn.setEnabled(True)

        # Show initials immediately, then try to load the real thumbnail
        initials = _ad_initials(user.get("display_name", ""))
        self._thumb_lbl.setText(initials)
        self._thumb_lbl.setPixmap(self._thumb_lbl.style().standardIcon(
            self._thumb_lbl.style().SP_DialogNoButton
        ).pixmap(1, 1))  # clear any stale pixmap
        self._thumb_lbl.setText(initials)
        self._thumb_lbl.setStyleSheet(
            "background: #2B579A; color: white; border-radius: 24px;"
            " font-weight: bold; font-size: 15px; border: none;"
        )
        self._load_thumbnail(user.get("username", ""))

    def _load_thumbnail(self, username: str):
        """Attempt to load the AD photo; falls back silently to initials."""
        if not username:
            return
        try:
            from integrations import ad_integration  # type: ignore
            from PyQt5.QtGui import QPixmap  # type: ignore
            img_bytes = ad_integration.get_thumbnail(username)
            if img_bytes:
                pix = QPixmap()
                if pix.loadFromData(img_bytes):
                    pix = pix.scaled(
                        48, 48,
                        Qt.KeepAspectRatioByExpanding,
                        Qt.SmoothTransformation,
                    )
                    self._thumb_lbl.setPixmap(pix)
                    self._thumb_lbl.setText("")
                    self._thumb_lbl.setStyleSheet(
                        "border: 1px solid #B8CBE4; border-radius: 24px;"
                        " background: transparent;"
                    )
        except Exception:
            pass

    # ---------------------------------------------------------------- #
    # Result accessors                                                   #
    # ---------------------------------------------------------------- #

    def get_resource_name(self) -> str:
        """Return the formatted ``"Nachname, Vorname"`` string for the selected user."""
        if self._selected_user:
            return self._selected_user.get(
                "formatted_name",
                self._selected_user.get("display_name", ""),
            )
        return ""

    def get_user_data(self) -> dict:
        """Return the full AD dict for the selected user, or an empty dict."""
        return self._selected_user or {}

    def _tab_settings(self):
        props = self._props
        w = QWidget()
        f = QFormLayout(w)
        f.setContentsMargins(16, 16, 16, 16)
        f.setSpacing(10)

        def chk(getter):
            b = QCheckBox()
            try:
                v = getter()
                b.setChecked(bool(v) if v is not None else False)
            except Exception:
                pass
            return b

        self._chk_manual   = chk(props.getNewTasksAreManual)
        self._chk_honor    = chk(props.getHonorConstraints)
        self._chk_autolink = chk(props.getAutolink)
        self._chk_effort   = chk(props.getNewTasksEffortDriven)
        self._chk_est      = chk(props.getNewTasksEstimated)
        self._chk_multi    = chk(props.getMultipleCriticalPaths)
        self._chk_splits   = chk(props.getSplitInProgressTasks)

        self._e_crit_slack = QLineEdit("0")
        try:
            cs = props.getCriticalSlackLimit()
            if cs is not None:
                try:
                    self._e_crit_slack.setText(str(float(str(cs.getDuration()))))
                except Exception:
                    self._e_crit_slack.setText(str(cs))
        except Exception:
            pass

        _TT_NAMES  = ["FIXED_UNITS", "FIXED_DURATION", "FIXED_WORK"]
        _TT_LABELS = ["Fixed Units", "Fixed Duration", "Fixed Work"]
        self._c_task_type = QComboBox()
        self._c_task_type.addItems(_TT_LABELS)
        try:
            tt = str(props.getDefaultTaskType())
            if tt in _TT_NAMES:
                self._c_task_type.setCurrentIndex(_TT_NAMES.index(tt))
        except Exception:
            pass

        f.addRow("New Tasks Are Manual:",     self._chk_manual)
        f.addRow("Honor Constraints:",        self._chk_honor)
        f.addRow("Autolink Tasks:",           self._chk_autolink)
        f.addRow("New Tasks Effort Driven:",  self._chk_effort)
        f.addRow("New Tasks Estimated:",      self._chk_est)
        f.addRow("Multiple Critical Paths:",  self._chk_multi)
        f.addRow("Splits in Progress Tasks:", self._chk_splits)
        f.addRow("Critical Slack Limit (d):", self._e_crit_slack)
        f.addRow("Default Task Type:",        self._c_task_type)
        return w

    # ---------------------------------------------------------------- #
    # Apply                                                             #
    # ---------------------------------------------------------------- #

    def apply(self):
        props = self._props

        def _s(fn, val):
            try:
                fn(val)
            except Exception as e:
                print(f"[WARN] ProjectInfo.apply: {e}")

        def _str_to_ldt(s):
            from java.time import LocalDateTime  # type: ignore
            s = s.strip().replace(" ", "T")
            if len(s) == 10:
                s += "T00:00:00"
            elif len(s) == 16:
                s += ":00"
            return LocalDateTime.parse(s)

        def _str_to_lt(s):
            from java.time import LocalTime  # type: ignore
            s = s.strip()
            if len(s) == 5:
                s += ":00"
            return LocalTime.parse(s)

        # Summary
        _s(props.setProjectTitle, self._e_title.text().strip()    or None)
        _s(props.setSubject,  self._e_subject.text().strip()  or None)
        _s(props.setAuthor,   self._e_author.text().strip()   or None)
        _s(props.setManager,  self._e_manager.text().strip()  or None)
        _s(props.setCompany,  self._e_company.text().strip()  or None)
        _s(props.setCategory, self._e_category.text().strip() or None)
        _s(props.setKeywords, self._e_keywords.text().strip() or None)
        _s(props.setComments, self._e_comments.toPlainText().strip() or None)

        # Project dates
        _min_dt = QDateTime(QDate(1900, 1, 1), QTime(0, 0))
        for dte, setter in [
            (self._e_start,  props.setStartDate),
            (self._e_finish, props.setFinishDate),
            (self._e_status, props.setStatusDate),
        ]:
            try:
                if dte.dateTime() > _min_dt:
                    raw = dte.dateTime().toString("yyyy-MM-dd HH:mm")
                    _s(setter, _str_to_ldt(raw))
            except Exception as e:
                print(f"[WARN] ProjectInfo date parse: {e}")

        # Schedule from
        try:
            import jpype  # type: ignore
            ScheduleFrom = jpype.JClass("org.mpxj.ScheduleFrom")
            sf = ScheduleFrom.FINISH if self._c_schedule.currentIndex() == 1 else ScheduleFrom.START
            props.setScheduleFrom(sf)
        except Exception as e:
            print(f"[WARN] ProjectInfo scheduleFrom: {e}")

        # Calendar times
        for te, setter in [
            (self._e_def_start,  props.setDefaultStartTime),
            (self._e_def_finish, props.setDefaultEndTime),
        ]:
            try:
                raw = te.time().toString("HH:mm")
                _s(setter, _str_to_lt(raw))
            except Exception as e:
                print(f"[WARN] ProjectInfo time parse: {e}")

        try:
            props.setMinutesPerDay(int(float(self._e_hours_day.text()) * 60))
        except Exception:
            pass
        try:
            props.setMinutesPerWeek(int(float(self._e_hours_week.text()) * 60))
        except Exception:
            pass
        try:
            props.setDaysPerMonth(int(self._e_days_month.text()))
        except Exception:
            pass

        # Week start day
        try:
            import jpype  # type: ignore
            DayOfWeek = jpype.JClass("java.time.DayOfWeek")
            props.setWeekStartDay(DayOfWeek.valueOf(self._c_week_start.currentText().upper()))
        except Exception as e:
            print(f"[WARN] ProjectInfo weekStartDay: {e}")

        # Currency
        _s(props.setCurrencySymbol, self._e_curr_sym.text().strip() or None)
        _s(props.setCurrencyCode,   self._e_curr_code.text().strip() or None)
        try:
            props.setCurrencyDigits(int(self._e_curr_digits.text()))
        except Exception:
            pass
        try:
            import jpype  # type: ignore
            CSP = jpype.JClass("org.mpxj.CurrencySymbolPosition")
            _POS = ["BEFORE", "AFTER", "BEFORE_WITH_SPACE", "AFTER_WITH_SPACE"]
            props.setSymbolPosition(CSP.valueOf(_POS[self._c_curr_pos.currentIndex()]))
        except Exception as e:
            print(f"[WARN] ProjectInfo currencyPos: {e}")

        # Settings
        _s(props.setNewTasksAreManual,     bool(self._chk_manual.isChecked()))
        _s(props.setHonorConstraints,      bool(self._chk_honor.isChecked()))
        _s(props.setAutolink,              bool(self._chk_autolink.isChecked()))
        _s(props.setNewTasksEffortDriven,  bool(self._chk_effort.isChecked()))
        _s(props.setNewTasksEstimated,     bool(self._chk_est.isChecked()))
        _s(props.setMultipleCriticalPaths, bool(self._chk_multi.isChecked()))
        _s(props.setSplitInProgressTasks, bool(self._chk_splits.isChecked()))

        try:
            from org.mpxj import Duration, TimeUnit  # type: ignore
            slack = float(self._e_crit_slack.text())
            props.setCriticalSlackLimit(Duration.getInstance(slack, TimeUnit.DAYS))
        except Exception:
            pass

        try:
            import jpype  # type: ignore
            TaskType = jpype.JClass("org.mpxj.TaskType")
            _TT = ["FIXED_UNITS", "FIXED_DURATION", "FIXED_WORK"]
            props.setDefaultTaskType(TaskType.valueOf(_TT[self._c_task_type.currentIndex()]))
        except Exception as e:
            print(f"[WARN] ProjectInfo taskType: {e}")

        # Custom properties
        try:
            import java.util  # type: ignore
            cp = java.util.HashMap()
            for row in range(self._tbl_custom.rowCount()):
                key_item = self._tbl_custom.item(row, 0)
                val_item = self._tbl_custom.item(row, 1)
                key = key_item.text().strip() if key_item else ""
                val = val_item.text().strip() if val_item else ""
                if key:
                    cp.put(key, val)
            props.setCustomProperties(cp)
        except Exception as e:
            print(f"[WARN] ProjectInfo customProperties: {e}")

        # ---- Save Task / Resource field definitions ----
        for entity in ("task", "resource"):
            ft_list_attr  = f"_ef_ft_list_{entity}"
            del_list_attr = f"_ef_del_list_{entity}"
            tbl_attr      = f"_ef_tbl_{entity}"
            if not hasattr(self, ft_list_attr):
                continue
            try:
                # Remove deleted definitions
                for ft in getattr(self, del_list_attr, []):
                    try:
                        cfc = self._project.getCustomFields()
                        existing = cfc.get(ft)
                        if existing is not None:
                            cfc.add(ft)  # re-add with empty alias effectively clears
                            existing.setAlias(None)
                    except Exception:
                        pass
                # Update / create definitions with aliases
                tbl = getattr(self, tbl_attr)
                for row, ft in getattr(self, ft_list_attr, []):
                    alias_item = tbl.item(row, 1)
                    alias = alias_item.text().strip() if alias_item else ""
                    try:
                        cf_def = self._project.getCustomFields().getOrCreate(ft)
                        cf_def.setAlias(alias if alias else None)
                    except Exception as fe:
                        print(f"[WARN] entity field alias save ({entity}): {fe}")
            except Exception as e:
                print(f"[WARN] ProjectInfo entity fields save ({entity}): {e}")

        # ---- Save calendar changes ----
        if hasattr(self, "_cal_editors"):
            try:
                import java.time as _jt  # type: ignore
                import jpype  # type: ignore
                DayType   = jpype.JClass("org.mpxj.DayType")
                DOWS      = list(_jt.DayOfWeek.values())
                for uid, info in self._cal_editors.items():
                    cal = info["cal"]
                    # Name
                    new_name = info["name"].text().strip()
                    if new_name:
                        try:
                            cal.setName(new_name)
                        except Exception:
                            pass
                    # Default calendar flag
                    if info["default"].isChecked():
                        try:
                            self._project.setDefaultCalendar(cal)
                        except Exception:
                            try:
                                cal.setDefault(True)
                            except Exception:
                                pass
                    # Day types
                    for i, dow in enumerate(DOWS):
                        if i < len(info["days"]):
                            dt_str = info["days"][i].currentText()
                            try:
                                cal.setCalendarDayType(dow, DayType.valueOf(dt_str))
                            except Exception:
                                pass
                    # Exceptions: rebuild from exc_tbl
                    exc_tbl = info.get("exc_tbl")
                    if exc_tbl is not None:
                        try:
                            cal.clearCalendarExceptions()
                            from java.time import LocalDate  # type: ignore
                            for row in range(exc_tbl.rowCount()):
                                name_item = exc_tbl.item(row, 0)
                                from_de   = exc_tbl.cellWidget(row, 1)
                                to_de     = exc_tbl.cellWidget(row, 2)
                                from_str  = from_de.date().toString("yyyy-MM-dd") if from_de else ""
                                to_str    = to_de.date().toString("yyyy-MM-dd")   if to_de   else ""
                                exc_name  = name_item.text().strip() if name_item else ""
                                if from_str:
                                    try:
                                        from_date = LocalDate.parse(from_str)
                                        to_date   = LocalDate.parse(to_str if to_str else from_str)
                                        ex = cal.addCalendarException(from_date, to_date)
                                        if exc_name:
                                            ex.setName(exc_name)
                                    except Exception as ex_e:
                                        print(f"[WARN] exception parse: {ex_e}")
                        except Exception as e:
                            print(f"[WARN] calendar exceptions save: {e}")
            except Exception as e:
                print(f"[WARN] ProjectInfo.apply calendars: {e}")


# ------------------------------------------------------------------ #
# Email Export — compose & send dialog                                 #
# ------------------------------------------------------------------ #

def _load_email_templates():
    """Load all *.json template files from the email_templates/ folder.

    Returns a list of dicts with keys 'name', 'subject', 'body'.
    The folder is located next to the executable (bundled) or at the
    project root (development).  Invalid / unreadable files are skipped.
    """
    import os as _os
    import json as _json
    import sys as _sys

    if getattr(_sys, "frozen", False):
        base = _os.path.dirname(_os.path.abspath(_sys.executable))
    else:
        base = _os.path.normpath(
            _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..")
        )
    folder = _os.path.join(base, "email_templates")
    templates = []
    if not _os.path.isdir(folder):
        return templates
    for fname in sorted(_os.listdir(folder)):
        if not fname.lower().endswith(".json"):
            continue
        try:
            with open(_os.path.join(folder, fname), "r", encoding="utf-8") as fh:
                data = _json.load(fh)
            if isinstance(data, dict) and "name" in data and "subject" in data and "body" in data:
                templates.append(data)
        except Exception:
            pass
    return templates


def _apply_template_placeholders(text, placeholders):
    """Replace {key} placeholders in *text* using *placeholders* dict."""
    for key, value in placeholders.items():
        text = text.replace("{" + key + "}", str(value) if value else "")
    return text


class EmailExportDialog(QDialog):
    """Compose and send an email with the current view attached as SVG.

    Parameters
    ----------
    project:
        The open MPXJ ProjectFile (used to resolve project name and manager).
    email_configs:
        List of email config dicts from SettingsManager.get_email_configs().
    active_config_name:
        Name of the currently active email config.
    view_name:
        Human-readable name of the view being exported (e.g. "Gantt Chart").
    parent:
        Parent QWidget.
    """

    def __init__(
        self,
        project,
        email_configs,
        active_config_name,
        view_name="Current View",
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Email Export")
        self.setMinimumWidth(560)
        self.setModal(True)
        self.setStyleSheet(_DIALOG_STYLE)

        self._project = project
        self._configs = email_configs
        self._view_name = view_name
        self._placeholders = self._build_placeholders(resource_name="")
        self._current_body_html: "str | None" = None  # set by _on_template_changed

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(_make_header(
            "Email Export",
            "Send '" + view_name + "' as an SVG attachment",
        ))

        body = QWidget()
        bv = QVBoxLayout(body)
        bv.setContentsMargins(16, 12, 16, 8)
        bv.setSpacing(8)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setSpacing(6)

        # Email config selector
        self._config_combo = QComboBox()
        if email_configs:
            for cfg in email_configs:
                self._config_combo.addItem(cfg.get("name", ""), cfg)
            for i, cfg in enumerate(email_configs):
                if cfg.get("name") == active_config_name:
                    self._config_combo.setCurrentIndex(i)
                    break
        else:
            self._config_combo.addItem("(no email configurations — configure in Email Accounts)", None)
            self._config_combo.setEnabled(False)
        form.addRow("Email account:", self._config_combo)

        # Template selector
        self._templates = _load_email_templates()
        self._template_combo = QComboBox()
        self._template_combo.addItem("\u2014 no template \u2014", None)
        for tmpl in self._templates:
            self._template_combo.addItem(tmpl["name"], tmpl)
        self._template_combo.currentIndexChanged.connect(self._on_template_changed)
        form.addRow("Template:", self._template_combo)

        # Recipient
        self._to_edit = QLineEdit()
        self._to_edit.setPlaceholderText("recipient@example.com")
        form.addRow("To:", self._to_edit)

        # Subject
        self._subject_edit = QLineEdit()
        self._subject_edit.setPlaceholderText("Email subject")
        form.addRow("Subject:", self._subject_edit)

        bv.addLayout(form)

        # Body
        bv.addWidget(QLabel("Body:"))
        self._body_edit = QTextEdit()
        self._body_edit.setMinimumHeight(120)
        bv.addWidget(self._body_edit)

        root.addWidget(body)

        send_btn = QPushButton("Send")
        send_btn.setDefault(True)
        send_btn.clicked.connect(self.accept)
        send_btn.setStyleSheet(_BUTTON_STYLE)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        cancel_btn.setStyleSheet(_BUTTON_STYLE)

        btn_row = QWidget()
        btn_h = QHBoxLayout(btn_row)
        btn_h.setContentsMargins(12, 6, 12, 12)
        btn_h.addStretch()
        btn_h.addWidget(send_btn)
        btn_h.addWidget(cancel_btn)
        root.addWidget(btn_row)

    # ------------------------------------------------------------------

    def _build_placeholders(self, resource_name=""):
        import datetime
        project_name = ""
        project_manager = ""
        try:
            if self._project is not None:
                props = self._project.getProjectProperties()
                project_name    = str(props.getName() or "")
                project_manager = str(props.getAuthor() or "")
        except Exception:
            pass
        return {
            "resource_name":   resource_name,
            "project_name":    project_name,
            "project_manager": project_manager,
            "date":            datetime.date.today().isoformat(),
            "view_name":       self._view_name,
        }

    def _on_template_changed(self, index):
        tmpl = self._template_combo.currentData()
        if tmpl is None:
            self._current_body_html = None
            return
        subject = _apply_template_placeholders(tmpl.get("subject", ""), self._placeholders)
        body    = _apply_template_placeholders(tmpl.get("body", ""),    self._placeholders)
        self._subject_edit.setText(subject)
        self._body_edit.setPlainText(body)
        # Store HTML body (with {svg_inline} still as a placeholder — caller resolves it)
        raw_html = tmpl.get("body_html")
        if raw_html:
            self._current_body_html = _apply_template_placeholders(raw_html, self._placeholders)
        else:
            self._current_body_html = None

    # Result accessors

    def get_selected_config(self):
        """Return the chosen email config dict, or None."""
        return self._config_combo.currentData()

    def get_to(self):
        return self._to_edit.text().strip()

    def get_subject(self):
        return self._subject_edit.text().strip()

    def get_body(self):
        return self._body_edit.toPlainText()

    def get_body_html(self) -> "str | None":
        """Return the HTML body from the selected template, or None if no HTML template is active.

        The string may still contain the ``{svg_inline}`` placeholder — the caller
        is responsible for substituting it with an ``<img src='cid:...'>`` tag.
        """
        return self._current_body_html

    def set_to(self, address):
        self._to_edit.setText(address)


# ------------------------------------------------------------------ #
# Email Export — bulk per-resource preview dialog                      #
# ------------------------------------------------------------------ #

class BulkEmailPreviewDialog(QDialog):
    """Preview and confirm a per-resource bulk email send.

    Shows a table with one row per resource: name, email address,
    resolved subject, and an Include checkbox.  Resources without a
    known email address are pre-deselected and highlighted.

    Parameters
    ----------
    rows:
        List of dicts with keys:
          'resource_name' (str)
          'email'         (str, may be empty if no address found)
          'subject'       (str, already-resolved subject line)
    parent:
        Parent QWidget.
    """

    def __init__(self, rows, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Email Export \u2014 Bulk Send Preview")
        self.setMinimumWidth(720)
        self.setMinimumHeight(460)
        self.setModal(True)
        self.setStyleSheet(_DIALOG_STYLE)

        self._rows = rows
        self._checkboxes = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(_make_header(
            "Bulk Email Send \u2014 Preview",
            "Review recipients. Uncheck rows to skip. Resources without an email address are highlighted.",
        ))

        body = QWidget()
        bv = QVBoxLayout(body)
        bv.setContentsMargins(16, 12, 16, 8)
        bv.setSpacing(8)

        skipped_count = sum(1 for r in rows if not r.get("email"))
        summary = QLabel(
            "<b>" + str(len(rows)) + "</b> resource(s) found. "
            "<b>" + str(skipped_count) + "</b> without a stored email address (pre-deselected). "
            "Uncheck rows to exclude them."
        )
        summary.setWordWrap(True)
        bv.addWidget(summary)

        tbl = QTableWidget(len(rows), 4)
        tbl.setHorizontalHeaderLabels(["Include", "Resource", "Email", "Subject"])
        tbl.setAlternatingRowColors(True)
        tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        tbl.verticalHeader().setVisible(False)
        tbl.horizontalHeader().setStretchLastSection(True)
        tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        tbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        tbl.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        tbl.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)

        from PyQt5.QtGui import QColor as _QColor  # type: ignore
        _NO_EMAIL_COLOR = _QColor("#fff3cd")

        for row_idx, row in enumerate(rows):
            has_email = bool(row.get("email"))

            cb = QCheckBox()
            cb.setChecked(has_email)
            cb_w = QWidget()
            cb_h = QHBoxLayout(cb_w)
            cb_h.setContentsMargins(4, 0, 4, 0)
            cb_h.addWidget(cb)
            cb_h.setAlignment(cb, Qt.AlignCenter)
            tbl.setCellWidget(row_idx, 0, cb_w)
            self._checkboxes.append(cb)

            for col, text in [
                (1, row.get("resource_name", "")),
                (2, row.get("email", "") or "(no email)"),
                (3, row.get("subject", "")),
            ]:
                item = QTableWidgetItem(text)
                item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                if not has_email:
                    item.setBackground(_NO_EMAIL_COLOR)
                tbl.setItem(row_idx, col, item)

        bv.addWidget(tbl)

        sel_row = QWidget()
        sel_h = QHBoxLayout(sel_row)
        sel_h.setContentsMargins(0, 0, 0, 0)
        sel_h.setSpacing(8)
        sel_all = QPushButton("Select All")
        sel_all.setProperty("flat", "true")
        sel_all.setStyleSheet(_BUTTON_STYLE)
        sel_all.clicked.connect(lambda: [cb.setChecked(True) for cb in self._checkboxes])
        desel_all = QPushButton("Deselect All")
        desel_all.setProperty("flat", "true")
        desel_all.setStyleSheet(_BUTTON_STYLE)
        desel_all.clicked.connect(lambda: [cb.setChecked(False) for cb in self._checkboxes])
        sel_h.addWidget(sel_all)
        sel_h.addWidget(desel_all)
        sel_h.addStretch()
        bv.addWidget(sel_row)

        root.addWidget(body)

        send_btn = QPushButton("Send Selected")
        send_btn.setDefault(True)
        send_btn.clicked.connect(self.accept)
        send_btn.setStyleSheet(_BUTTON_STYLE)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.clicked.connect(self.reject)
        cancel_btn.setStyleSheet(_BUTTON_STYLE)

        btn_row_w = QWidget()
        btn_row_h2 = QHBoxLayout(btn_row_w)
        btn_row_h2.setContentsMargins(12, 6, 12, 12)
        btn_row_h2.addStretch()
        btn_row_h2.addWidget(send_btn)
        btn_row_h2.addWidget(cancel_btn)
        root.addWidget(btn_row_w)

    def get_included_rows(self):
        """Return only the rows whose Include checkbox is checked."""
        return [
            row for cb, row in zip(self._checkboxes, self._rows)
            if cb.isChecked()
        ]


# ------------------------------------------------------------------ #
# Email Export — bulk send summary dialog                              #
# ------------------------------------------------------------------ #

class BulkEmailSummaryDialog(QDialog):
    """Show a summary of a completed bulk email send operation.

    Parameters
    ----------
    results:
        List of dicts with keys:
          'resource_name' (str)
          'email'         (str)
          'success'       (bool)
          'message'       (str)  -- error message or 'Sent'
    parent:
        Parent QWidget.
    """

    def __init__(self, results, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Email Export \u2014 Send Summary")
        self.setMinimumWidth(620)
        self.setMinimumHeight(380)
        self.setModal(True)
        self.setStyleSheet(_DIALOG_STYLE)

        sent   = sum(1 for r in results if r.get("success"))
        failed = len(results) - sent

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(_make_header(
            "Bulk Send \u2014 Complete",
            str(sent) + " sent successfully, " + str(failed) + " failed.",
        ))

        body = QWidget()
        bv = QVBoxLayout(body)
        bv.setContentsMargins(16, 12, 16, 8)
        bv.setSpacing(8)

        tbl = QTableWidget(len(results), 3)
        tbl.setHorizontalHeaderLabels(["Resource", "Email", "Result"])
        tbl.setAlternatingRowColors(True)
        tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        tbl.verticalHeader().setVisible(False)
        tbl.horizontalHeader().setStretchLastSection(True)
        tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        tbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        tbl.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)

        from PyQt5.QtGui import QColor as _QColor  # type: ignore
        _OK_COLOR   = _QColor("#d4edda")
        _FAIL_COLOR = _QColor("#f8d7da")

        for row_idx, res in enumerate(results):
            success = bool(res.get("success"))
            color   = _OK_COLOR if success else _FAIL_COLOR
            for col, text in [
                (0, res.get("resource_name", "")),
                (1, res.get("email", "")),
                (2, res.get("message", "Sent" if success else "Failed")),
            ]:
                item = QTableWidgetItem(text)
                item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                item.setBackground(color)
                tbl.setItem(row_idx, col, item)

        bv.addWidget(tbl)
        root.addWidget(body)

        close_btn = QPushButton("Close")
        close_btn.setDefault(True)
        close_btn.clicked.connect(self.accept)
        close_btn.setStyleSheet(_BUTTON_STYLE)

        btn_row_w = QWidget()
        btn_row_h3 = QHBoxLayout(btn_row_w)
        btn_row_h3.setContentsMargins(12, 6, 12, 12)
        btn_row_h3.addStretch()
        btn_row_h3.addWidget(close_btn)
        root.addWidget(btn_row_w)
