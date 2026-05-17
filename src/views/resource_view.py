# resource_view.py - Resource list view for the Project Offline app
#
# Supports add / delete resources via context menu, Edit menu, Delete key.
# Double-click opens the Resource Information dialog.

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))  # allow imports from src/

from PyQt5.QtWidgets import (  # type: ignore
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QMenu, QDialog,
    QStyledItemDelegate, QStyleOptionViewItem, QApplication, QStyle, QToolTip
)
from PyQt5.QtCore import Qt, pyqtSignal, QPoint  # type: ignore
from PyQt5.QtGui import QColor, QPainter, QBrush, QPen  # type: ignore
from PyQt5.QtCore import QRect, QSize  # type: ignore


# ------------------------------------------------------------------ #
# Progress-bar delegate – Max Units column                            #
# ------------------------------------------------------------------ #

class _ProgressDelegate(QStyledItemDelegate):
    """Draws a coloured availability bar inside the Max Units cell."""

    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        opt.text = ""
        QApplication.style().drawControl(QStyle.CE_ItemViewItem, opt, painter)

        raw = index.data(Qt.DisplayRole) or ""
        if not raw or raw == "—":
            return
        try:
            pct = float(str(raw).replace("%", "").strip())
        except ValueError:
            return
        pct = max(0.0, pct)  # allow > 100 (over-allocated resources)

        r = option.rect.adjusted(3, 5, -3, -5)
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor("#B8CBE4"), 1))
        painter.setBrush(QBrush(QColor("#E8F0FB")))
        painter.drawRoundedRect(r, 2, 2)

        if pct > 0:
            if pct > 100:
                fill_r = QRect(r.left(), r.top(), r.width(), r.height())
                painter.setPen(Qt.NoPen)
                painter.setBrush(QBrush(QColor("#C0392B")))   # red – over-allocated
            else:
                fill_w = int(r.width() * pct / 100.0)
                fill_r = QRect(r.left(), r.top(), fill_w, r.height())
                painter.setPen(Qt.NoPen)
                if pct >= 100:
                    painter.setBrush(QBrush(QColor("#217346")))   # green – fully allocated
                elif pct >= 50:
                    painter.setBrush(QBrush(QColor("#2B579A")))   # blue
                else:
                    painter.setBrush(QBrush(QColor("#70A0D0")))   # light blue
            painter.drawRoundedRect(fill_r, 2, 2)

        label = f"{pct:.0f}%"
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
        return QSize(max(sh.width(), 90), sh.height())


class ResourceView(QTableWidget):
    data_changed = pyqtSignal()

    COLUMNS = ["ID", "Name", "Type", "Max Units", "Standard Rate", "Overtime Rate"]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._project = None
        self._java_resources = []

        self.setColumnCount(len(self.COLUMNS))
        self.setHorizontalHeaderLabels(self.COLUMNS)
        self.setColumnWidth(0, 40)
        self.horizontalHeader().setSectionResizeMode(0, QHeaderView.Interactive)
        self.setColumnWidth(1, 200)
        self.horizontalHeader().setSectionResizeMode(1, QHeaderView.Interactive)
        self.setColumnWidth(2, 90)
        self.horizontalHeader().setSectionResizeMode(2, QHeaderView.Interactive)
        self.setColumnWidth(3, 110)
        self.horizontalHeader().setSectionResizeMode(3, QHeaderView.Interactive)
        self.setItemDelegateForColumn(3, _ProgressDelegate(self))
        self.setColumnWidth(4, 130)
        self.horizontalHeader().setSectionResizeMode(4, QHeaderView.Interactive)
        self.setColumnWidth(5, 130)
        self.horizontalHeader().setSectionResizeMode(5, QHeaderView.Interactive)

        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setAlternatingRowColors(True)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(36)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self.cellDoubleClicked.connect(self._on_double_click)

        self.setMouseTracking(True)
        self._tooltip_row = -1  # last row for which tooltip was shown

    # ---------------------------------------------------------------- #
    # Hover tooltip                                                     #
    # ---------------------------------------------------------------- #

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        row = self.rowAt(event.pos().y())
        if row < 0 or row >= len(self._java_resources):
            self._tooltip_row = -1
            QToolTip.hideText()
            return
        if row == self._tooltip_row:
            return  # already showing for this row
        self._tooltip_row = row
        res = self._java_resources[row]
        self._show_resource_tooltip(res, event.globalPos())

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self._tooltip_row = -1
        QToolTip.hideText()

    def _show_resource_tooltip(self, res, global_pos: QPoint):
        import base64
        try:
            from dialogs import _resource_thumbnail_store, _resource_type_pixmap
        except ImportError:
            return

        name  = str(res.getName())  if res.getName()  is not None else ""
        rtype = str(res.getType())   if res.getType()   is not None else "WORK"
        try:
            dept = str(res.getDepartment()) if res.getDepartment() is not None else ""
        except Exception:
            dept = ""

        # Thumbnail: prefer AD photo from store, else type-specific pixmap
        img_html = ""
        try:
            uid_key = str(res.getUniqueID())
            raw = _resource_thumbnail_store.get(uid_key)
            if raw:
                b64 = base64.b64encode(raw).decode()
                img_html = f'<img src="data:image/jpeg;base64,{b64}" width="64" height="64" style="border-radius:32px;"/>'
            else:
                from PyQt5.QtCore import QBuffer, QIODevice  # type: ignore
                from PyQt5.QtGui import QPixmap  # type: ignore
                pix: QPixmap = _resource_type_pixmap(rtype, 64)
                buf = QBuffer()
                buf.open(QIODevice.WriteOnly)
                pix.save(buf, "PNG")
                b64 = base64.b64encode(buf.data().data()).decode()
                img_html = f'<img src="data:image/png;base64,{b64}" width="64" height="64"/>'
        except Exception:
            pass

        rows = []
        rows.append(f'<b>{name}</b>')
        rows.append(f'Type: {rtype.capitalize()}')
        if dept:
            rows.append(f'Dept: {dept}')

        html = (
            '<table cellspacing="4" cellpadding="0"><tr>'
            f'<td valign="middle">{img_html}</td>'
            '<td valign="middle" style="padding-left:8px;">'
            + '<br/>'.join(rows) +
            '</td></tr></table>'
        )
        QToolTip.showText(global_pos, html, self)

    def load_project(self, project):
        self._project = project
        self._java_resources = []
        self.setRowCount(0)
        if project is None:
            return
        resources = [r for r in project.getResources() if r.getName() is not None]
        self.setRowCount(len(resources))
        for row, res in enumerate(resources):
            self._java_resources.append(res)
            self._fill_row(row, res)

    def _fill_row(self, row, res):
        vals = [
            str(res.getID())          if res.getID()          is not None else "",
            str(res.getName())        if res.getName()        is not None else "",
            str(res.getType())        if res.getType()        is not None else "",
            (f"{(lambda v: v * 100 if v <= 2.0 else v)(float(str(res.getMaxUnits() or 1.0))):.0f}%"),
            str(res.getStandardRate()) if res.getStandardRate() is not None else "",
            str(res.getOvertimeRate()) if res.getOvertimeRate() is not None else "",
        ]
        for col, val in enumerate(vals):
            item = QTableWidgetItem(val)
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            self.setItem(row, col, item)

    # ---------------------------------------------------------------- #
    # Add / Delete                                                      #
    # ---------------------------------------------------------------- #

    def _ensure_resource_uid(self, resource) -> None:
        """Ensure the resource has a UniqueID.  MPXJ should auto-assign one via
        addResource(), but defensively assign the next free UID if it is null."""
        try:
            if resource.getUniqueID() is not None:
                return
            from java.lang import Integer as _JInt  # type: ignore
            existing: set = set()
            for r in self._project.getResources():
                try:
                    uid = r.getUniqueID()
                    if uid is not None:
                        existing.add(int(str(uid)))
                except Exception:
                    pass
            next_uid = 1
            while next_uid in existing:
                next_uid += 1
            resource.setUniqueID(_JInt(next_uid))
        except Exception:
            pass

    def add_resource(self):
        if self._project is None:
            return
        # Collect existing IDs *before* addResource() so the new resource
        # is not included in the set (MPXJ may auto-assign an ID to it).
        try:
            from java.lang import Integer as _JInt2  # type: ignore
            existing_ids: set = set()
            for r in self._project.getResources():
                rid = r.getID()
                if rid is not None:
                    try:
                        existing_ids.add(int(str(rid)))
                    except Exception:
                        pass
        except Exception:
            existing_ids = set()

        new_res = self._project.addResource()
        self._ensure_resource_uid(new_res)
        new_res.setName("New Resource")

        # Assign the next free resource ID so the sheet shows it immediately
        try:
            next_res_id = (max(existing_ids) + 1) if existing_ids else 1
            while next_res_id in existing_ids:
                next_res_id += 1
            new_res.setID(_JInt2(next_res_id))
        except Exception:
            pass

        # Create a personal calendar linked to the project standard calendar
        self._create_resource_calendar(new_res)

        from dialogs import ResourceDialog  # type: ignore
        dlg = ResourceDialog(new_res, self._project, self)
        if dlg.exec_() == QDialog.Accepted:
            # Duplicate-name guard: compare proposed name against all other resources
            proposed = dlg._e_name.text().strip()
            try:
                new_uid = str(new_res.getUniqueID())
            except Exception:
                new_uid = None
            existing_names = [
                str(r.getName())
                for r in self._project.getResources()
                if r.getName() is not None and str(r.getUniqueID()) != new_uid
            ]
            if any(n.lower() == proposed.lower() for n in existing_names):
                from PyQt5.QtWidgets import QMessageBox  # type: ignore
                QMessageBox.warning(
                    self,
                    "Resource already exists",
                    f'A resource named "{proposed}" already exists.\n'
                    "Please use a unique name.",
                )
                try:
                    cal = new_res.getCalendar()
                    if cal is not None:
                        self._project.getCalendars().remove(cal)
                except Exception:
                    pass
                try:
                    new_res.remove()
                except Exception:
                    pass
                return
            dlg.apply_to_resource()
            self.data_changed.emit()
        else:
            try:
                cal = new_res.getCalendar()
                if cal is not None:
                    self._project.getCalendars().remove(cal)
            except Exception:
                pass
            try:
                new_res.remove()
            except Exception:
                pass

    def add_resource_from_ad(self):
        """Open the AD search dialog and add the chosen user as a new resource.

        The resource name is set to ``"Nachname, Vorname"`` as returned by the
        AD search dialog.  The e-mail address and department (if available) are
        written into the MPXJ resource object.  A personal calendar derived from
        the project default calendar is created and linked to the new resource so
        that individual working-time exceptions (vacations, public holidays) can
        be set independently.  The :pyqt:`data_changed` signal is emitted so the
        history manager captures an undo snapshot automatically.
        """
        if self._project is None:
            return
        from dialogs import ADSearchDialog, ResourceDialog  # type: ignore

        dlg = ADSearchDialog(self)
        if dlg.exec_() != QDialog.Accepted:
            return

        resource_name = dlg.get_resource_name()
        user_data     = dlg.get_user_data()
        if not resource_name:
            return

        # Check for an existing resource with the same name (case-insensitive)
        existing_names = [
            str(r.getName())
            for r in self._project.getResources()
            if r.getName() is not None
        ]
        if any(n.lower() == resource_name.lower() for n in existing_names):
            from PyQt5.QtWidgets import QMessageBox  # type: ignore
            QMessageBox.warning(
                self,
                "Resource already exists",
                f'A resource named "{resource_name}" already exists.\n'
                "Please edit the existing resource instead.",
            )
            return

        # Collect existing IDs *before* addResource() so the new resource
        # is not included in the set (MPXJ may auto-assign an ID to it).
        try:
            from java.lang import Integer as _JInt2  # type: ignore
            existing_ids: set = set()
            for r in self._project.getResources():
                rid = r.getID()
                if rid is not None:
                    try:
                        existing_ids.add(int(str(rid)))
                    except Exception:
                        pass
        except Exception:
            existing_ids = set()

        new_res = self._project.addResource()
        self._ensure_resource_uid(new_res)
        new_res.setName(resource_name)

        # Assign the next free resource ID immediately so the sheet shows it
        # before the file is saved (file_handler does this on save, but we
        # need it right away for the resource sheet display).
        try:
            next_res_id = (max(existing_ids) + 1) if existing_ids else 1
            while next_res_id in existing_ids:
                next_res_id += 1
            new_res.setID(_JInt2(next_res_id))
        except Exception:
            pass

        try:
            email = user_data.get("email", "")
            if email:
                new_res.setEmailAddress(email)
        except Exception:
            pass
        try:
            new_res._ad_data = dict(user_data or {})  # type: ignore[attr-defined]
        except Exception:
            pass

        # Create a personal calendar derived from the project default calendar
        self._create_resource_calendar(new_res)

        # Persist a secondary holiday-calendar mapping inferred from AD user
        # metadata (state/department/country) when a matching project calendar
        # exists. Team Planner consumes this mapping to render yellow blocks.
        try:
            from integrations.secondary_calendar_integration import (  # type: ignore
                assign_secondary_calendar_from_ad,
            )

            assign_secondary_calendar_from_ad(self._project, new_res, user_data or {})
        except Exception:
            pass

        # Open Resource Information dialog so the user can review / adjust details
        res_dlg = ResourceDialog(new_res, self._project, self)
        if res_dlg.exec_() == QDialog.Accepted:
            res_dlg.apply_to_resource()
            self.data_changed.emit()
        else:
            # Roll back calendar and resource when the user cancels
            try:
                cal = new_res.getCalendar()
                if cal is not None:
                    self._project.getCalendars().remove(cal)
            except Exception:
                pass
            try:
                new_res.remove()
            except Exception:
                pass

    def _create_resource_calendar(self, resource) -> None:
        """Create and link a personal calendar for a new AD resource.

        The new calendar is named ``"<Resource Name> Calendar"``.  It copies
        only the per-day-of-week working / non-working type settings from the
        project default calendar so that the resource follows the same weekly
        rhythm (e.g. Mon–Fri working, Sat–Sun non-working).  Calendar
        *exceptions* (public holidays, project closures) are intentionally NOT
        inherited: the resource calendar starts clean so that individual
        exceptions can be managed independently via the Confluence sync or by
        hand.

        If no default calendar is available the standard Mon–Fri working-week
        is configured via ``addDefaultCalendarDays()``.

        The calendar is assigned a unique UID before ``setCalendar()`` is
        called so that MSPDIWriter can persist it correctly.
        """
        try:
            from java.lang import Integer as _JInt  # type: ignore

            cal_name = f"{resource.getName()} Calendar"

            # Find the next free calendar UID
            existing_uids: set = set()
            for c in self._project.getCalendars():
                u = c.getUniqueID()
                if u is not None:
                    try:
                        existing_uids.add(int(str(u)))
                    except Exception:
                        pass
            next_uid = (max(existing_uids) + 1) if existing_uids else 1
            while next_uid in existing_uids:
                next_uid += 1

            cal = self._project.addCalendar()
            cal.setName(cal_name)
            cal.setUniqueID(_JInt(next_uid))

            parent = self._project.getDefaultCalendar()
            if parent is not None:
                # Copy per-day-of-week types only — NOT exceptions.
                try:
                    import java.time as _jt  # type: ignore
                    import jpype  # type: ignore
                    DayType = jpype.JClass("org.mpxj.DayType")
                    for dow in _jt.DayOfWeek.values():
                        try:
                            day_type = parent.getCalendarDayType(dow)
                            if day_type is not None:
                                cal.setCalendarDayType(dow, day_type)
                        except Exception:
                            pass
                except Exception:
                    cal.addDefaultCalendarDays()
                cal.addDefaultCalendarHours()
                # Link this calendar to the project standard calendar as its
                # base calendar so the "Base Calendar" field shows correctly.
                try:
                    cal.setParent(parent)
                except Exception:
                    pass
            else:
                cal.addDefaultCalendarDays()
                cal.addDefaultCalendarHours()

            resource.setCalendar(cal)
        except Exception as exc:
            print(f"[WARN] _create_resource_calendar: {exc}")

    def delete_selected_resources(self):
        if self._project is None:
            return
        rows = sorted(set(i.row() for i in self.selectedIndexes()), reverse=True)
        if not rows:
            return
        for row in rows:
            if 0 <= row < len(self._java_resources):
                res = self._java_resources[row]
                # Collect UID before removal for sidecar cleanup
                try:
                    _del_uid = str(res.getUniqueID()) if res.getUniqueID() is not None else None
                except Exception:
                    _del_uid = None
                # Remove the personal calendar linked to this resource first
                try:
                    cal = res.getCalendar()
                    if cal is not None:
                        self._project.getCalendars().remove(cal)
                except Exception as e:
                    print(f"[WARN] Remove resource calendar: {e}")
                try:
                    res.remove()
                except Exception as e:
                    print(f"[WARN] Remove resource: {e}")
                # Clean up sidecar stores (thumbnail + department)
                if _del_uid:
                    try:
                        from dialogs import (  # type: ignore
                            _resource_thumbnail_store, _resource_dept_store,
                            _save_resource_thumbnail_sidecar,
                        )
                        _resource_thumbnail_store.pop(_del_uid, None)
                        _resource_dept_store.pop(_del_uid, None)
                        _save_resource_thumbnail_sidecar()
                    except Exception:
                        pass
                self._java_resources.pop(row)
                self.removeRow(row)
        self.data_changed.emit()

    # ---------------------------------------------------------------- #
    # Double-click → Resource Information dialog                        #
    # ---------------------------------------------------------------- #

    def _on_double_click(self, row, col):
        if row < 0 or row >= len(self._java_resources):
            return
        res = self._java_resources[row]
        from dialogs import ResourceDialog  # type: ignore
        dlg = ResourceDialog(res, self._project, self)
        if dlg.exec_() == QDialog.Accepted:
            dlg.apply_to_resource()
            self._fill_row(row, res)
            self.data_changed.emit()

    # ---------------------------------------------------------------- #
    # Context menu + keyboard                                           #
    # ---------------------------------------------------------------- #

    def add_resources_from_ad_group(self):
        """Open the AD group search dialog and bulk-add members as resources.

        For each member returned:
          - Skip members whose name already exists in the resource sheet.
          - Create the MPXJ resource, assign a personal calendar.
          - Optionally assign a secondary holiday calendar via AD location.
          - Emit data_changed so history_manager captures an undo snapshot.

        A summary message box is shown when the operation completes.
        """
        if self._project is None:
            return
        from dialogs import ADGroupSearchDialog  # type: ignore
        from PyQt5.QtWidgets import QMessageBox  # type: ignore

        dlg = ADGroupSearchDialog(self)
        if dlg.exec_() != QDialog.Accepted:
            return

        users = dlg.get_selected_users()
        if not users:
            return

        # Build existing name set (case-insensitive) for duplicate check
        existing_names = {
            str(r.getName()).lower()
            for r in self._project.getResources()
            if r.getName() is not None
        }

        added   = 0
        skipped = 0
        errors: list = []

        for user_data in users:
            display_name = user_data.get("display_name", "").strip()
            if not display_name:
                skipped += 1
                continue

            from dialogs import _format_resource_name  # type: ignore
            resource_name = _format_resource_name(display_name)

            if resource_name.lower() in existing_names:
                skipped += 1
                continue

            try:
                # Collect existing IDs *before* addResource() so the new
                # resource is not counted (MPXJ may auto-assign an ID to it).
                try:
                    from java.lang import Integer as _JInt2  # type: ignore
                    existing_ids: set = set()
                    for r in self._project.getResources():
                        rid = r.getID()
                        if rid is not None:
                            try:
                                existing_ids.add(int(str(rid)))
                            except Exception:
                                pass
                except Exception:
                    existing_ids = set()

                new_res = self._project.addResource()
                self._ensure_resource_uid(new_res)
                new_res.setName(resource_name)

                # Assign the next free resource ID
                try:
                    next_res_id = (max(existing_ids) + 1) if existing_ids else 1
                    while next_res_id in existing_ids:
                        next_res_id += 1
                    new_res.setID(_JInt2(next_res_id))
                except Exception:
                    pass

                # Write AD attributes
                try:
                    email = user_data.get("email", "")
                    if email:
                        new_res.setEmailAddress(email)
                except Exception:
                    pass
                try:
                    new_res._ad_data = dict(user_data)  # type: ignore[attr-defined]
                except Exception:
                    pass

                # Create personal calendar
                self._create_resource_calendar(new_res)

                # Assign secondary holiday calendar from AD location
                try:
                    from integrations.secondary_calendar_integration import (  # type: ignore
                        assign_secondary_calendar_from_ad,
                    )
                    assign_secondary_calendar_from_ad(
                        self._project, new_res, user_data
                    )
                except Exception:
                    pass

                existing_names.add(resource_name.lower())
                added += 1

            except Exception as exc:
                errors.append(f"{display_name}: {exc}")

        if added or skipped or errors:
            self.data_changed.emit()
            self.load_project(self._project)

        # Summary
        parts = [f"{added} resource(s) added."]
        if skipped:
            parts.append(f"{skipped} skipped (already present or no name).")
        if errors:
            parts.append(f"{len(errors)} error(s):\n" + "\n".join(errors[:10]))
        QMessageBox.information(
            self, "Add from AD Group", "\n".join(parts)
        )

    def _show_context_menu(self, pos):
        n = len(set(i.row() for i in self.selectedIndexes()))
        menu = QMenu(self)
        ins_act      = menu.addAction("Insert Resource")
        ad_act       = menu.addAction("Add from Active Directory…")
        ad_group_act = menu.addAction("Add from AD Group…")
        menu.addSeparator()
        del_act = menu.addAction(f"Delete Resource{'s' if n > 1 else ''}")
        del_act.setEnabled(n > 0)
        action = menu.exec_(self.mapToGlobal(pos))
        if action == ins_act:
            self.add_resource()
        elif action == ad_act:
            self.add_resource_from_ad()
        elif action == ad_group_act:
            self.add_resources_from_ad_group()
        elif action == del_act:
            self.delete_selected_resources()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Delete and self.state() != QAbstractItemView.EditingState:
            self.delete_selected_resources()
        else:
            super().keyPressEvent(event)
