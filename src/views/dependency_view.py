# dependency_view.py - Task dependency list view for the Project Offline app
#
# Supports add / delete dependencies via context menu, Edit menu, Delete key.
# Double-click opens the Task Dependency dialog.

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))  # allow imports from src/

from PyQt5.QtWidgets import (  # type: ignore
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QMenu, QDialog
)
from PyQt5.QtCore import Qt, pyqtSignal  # type: ignore


class DependencyView(QTableWidget):
    data_changed = pyqtSignal()

    COLUMNS = ["Task ID", "Task Name", "Predecessor ID", "Predecessor Name", "Link Type", "Lag"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project = None
        self._relations = []   # list of (successor_task, Relation)

        self.setColumnCount(len(self.COLUMNS))
        self.setHorizontalHeaderLabels(self.COLUMNS)
        self.setColumnWidth(0, 60)
        self.horizontalHeader().setSectionResizeMode(0, QHeaderView.Interactive)
        self.setColumnWidth(1, 180)
        self.horizontalHeader().setSectionResizeMode(1, QHeaderView.Interactive)
        self.setColumnWidth(2, 100)
        self.horizontalHeader().setSectionResizeMode(2, QHeaderView.Interactive)
        self.setColumnWidth(3, 180)
        self.horizontalHeader().setSectionResizeMode(3, QHeaderView.Interactive)
        self.setColumnWidth(4, 120)
        self.horizontalHeader().setSectionResizeMode(4, QHeaderView.Interactive)
        self.setColumnWidth(5, 80)
        self.horizontalHeader().setSectionResizeMode(5, QHeaderView.Interactive)

        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setAlternatingRowColors(True)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(22)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self.cellDoubleClicked.connect(self._on_double_click)

    def load_project(self, project):
        self._project = project
        self._relations = []
        self.setRowCount(0)
        if project is None:
            return
        for task in project.getTasks():
            if task.getName() is None:
                continue
            preds = task.getPredecessors()
            if preds is None:
                continue
            for rel in preds:
                pred_task = rel.getPredecessorTask()
                self._relations.append((task, rel))
                row = self.rowCount()
                self.setRowCount(row + 1)
                vals = [
                    str(task.getID())          if task.getID()          is not None else "",
                    str(task.getName()),
                    str(pred_task.getID())     if pred_task.getID()     is not None else "",
                    str(pred_task.getName())   if pred_task.getName()   is not None else "",
                    str(rel.getType())         if rel.getType()         is not None else "",
                    str(rel.getLag())          if rel.getLag()          is not None else "",
                ]
                for col, val in enumerate(vals):
                    item = QTableWidgetItem(val)
                    item.setFlags(item.flags() & ~Qt.ItemIsEditable)
                    self.setItem(row, col, item)

    # ---------------------------------------------------------------- #
    # Add / Delete                                                      #
    # ---------------------------------------------------------------- #

    def add_dependency(self):
        if self._project is None:
            return
        from dialogs import DependencyDialog  # type: ignore
        dlg = DependencyDialog(self._project, parent=self)
        if dlg.exec_() == QDialog.Accepted:
            if dlg.apply_dependency():
                self.data_changed.emit()

    def delete_selected_dependencies(self):
        if self._project is None:
            return
        rows = sorted(set(i.row() for i in self.selectedIndexes()), reverse=True)
        if not rows:
            return
        for row in rows:
            if 0 <= row < len(self._relations):
                task, rel = self._relations[row]
                try:
                    # MPXJ: remove via the task's predecessor list
                    preds = task.getPredecessors()
                    preds.remove(rel)
                except Exception as e:
                    print(f"[WARN] Remove dependency: {e}")
                self._relations.pop(row)
                self.removeRow(row)
        self.data_changed.emit()

    # ---------------------------------------------------------------- #
    # Double-click → view/add dialog                                    #
    # ---------------------------------------------------------------- #

    def _on_double_click(self, row, col):
        if self._project is None:
            return
        # Show read-only info about the clicked dependency
        if row < 0 or row >= len(self._relations):
            return
        task, rel = self._relations[row]
        from dialogs import DependencyDialog  # type: ignore
        dlg = DependencyDialog(self._project, read_only=True, parent=self)
        # Pre-select the existing tasks in the combo boxes
        try:
            pred_task = rel.getPredecessorTask()
            for i, t in enumerate(dlg._task_list):
                if t.getID() == pred_task.getID():
                    dlg._c_pred.setCurrentIndex(i)
                if t.getID() == task.getID():
                    dlg._c_succ.setCurrentIndex(i)
            link_type = str(rel.getType()) if rel.getType() is not None else "FINISH_START"
            idx = dlg._LINK_TYPES.index(link_type) if link_type in dlg._LINK_TYPES else 0
            dlg._c_type.setCurrentIndex(idx)
            dlg._e_lag.setText(str(rel.getLag()) if rel.getLag() is not None else "0")
        except Exception:
            pass
        dlg.exec_()

    # ---------------------------------------------------------------- #
    # Context menu + keyboard                                           #
    # ---------------------------------------------------------------- #

    def _show_context_menu(self, pos):
        n = len(set(i.row() for i in self.selectedIndexes()))
        menu = QMenu(self)
        ins_act = menu.addAction("Insert Dependency")
        menu.addSeparator()
        del_act = menu.addAction(f"Delete Dependenc{'ies' if n > 1 else 'y'}")
        del_act.setEnabled(n > 0)
        action = menu.exec_(self.mapToGlobal(pos))
        if action == ins_act:
            self.add_dependency()
        elif action == del_act:
            self.delete_selected_dependencies()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Delete and self.state() != QAbstractItemView.EditingState:
            self.delete_selected_dependencies()
        else:
            super().keyPressEvent(event)
