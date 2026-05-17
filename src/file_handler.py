# file_handler.py - Handles reading and writing project files for the Qt5 app
#
# Uses the Python mpxj package with JPype. The correct usage is:
#   import mpxj (registers the bundled MPXJ JAR on the classpath)
#   jpype.startJVM() (starts the JVM with no extra args)
#   Then import Java classes from org.mpxj.*

import os
import sys
import jpype  # type: ignore
import mpxj   # type: ignore - registers the MPXJ JAR on the JPype classpath


def _xml_indent(elem, level=0):
    """Add pretty-print indentation to an ElementTree element in-place.

    Delegates to xml.etree.ElementTree.indent (added in Python 3.9) when
    available; falls back to a pure-Python iterative implementation so the
    module still works on 3.8 without hitting Python's recursion limit on
    large project XML files.
    """
    import xml.etree.ElementTree as _ET
    if hasattr(_ET, 'indent'):
        # Python 3.9+ — iterative, no recursion risk
        _ET.indent(elem, space='    ', level=level)
        return
    # Fallback: iterative pre-order traversal
    stack = [(elem, level)]
    while stack:
        el, lv = stack.pop()
        indent = "\n" + "    " * lv
        child_indent = "\n" + "    " * (lv + 1)
        if len(el):
            if not el.text or not el.text.strip():
                el.text = child_indent
            children = list(el)
            for i, child in enumerate(children):
                is_last = (i == len(children) - 1)
                if not child.tail or not child.tail.strip():
                    child.tail = indent if is_last else child_indent
                stack.append((child, lv + 1))
        else:
            if not el.tail or not el.tail.strip():
                el.tail = indent
    if level == 0:
        elem.tail = "\n"


def _suppress_native_output():
    """Context manager that redirects OS-level stdout/stderr to devnull.
    Suppresses native C++ diagnostic messages from MPXJ's MPP format reader.
    """
    import contextlib

    @contextlib.contextmanager
    def _ctx():
        devnull_fd = os.open(os.devnull, os.O_WRONLY)
        old_stdout = os.dup(1)
        old_stderr = os.dup(2)
        try:
            os.dup2(devnull_fd, 1)
            os.dup2(devnull_fd, 2)
            yield
        finally:
            os.dup2(old_stdout, 1)
            os.dup2(old_stderr, 2)
            os.close(devnull_fd)
            os.close(old_stdout)
            os.close(old_stderr)

    return _ctx()


class ProjectFileHandler:
    def __init__(self, logic):
        self.logic = logic
        self._source_xml_path = None   # path of the last XML file opened
        if not jpype.isJVMStarted():
            # Silence the Log4j "no logging provider" warning
            jpype.startJVM("-Dlog4j2.loggerContextFactory=org.apache.logging.log4j.simple.SimpleLoggerContextFactory")

    def open_project(self, file_path, parent=None):
        try:
            from org.mpxj.reader import UniversalProjectReader  # type: ignore
            with _suppress_native_output():
                project = UniversalProjectReader().read(file_path)
            # MPXJ's MSPDIReader can't read back enterprise custom-field values
            # (it assigns DataType.CUSTOM and parseCustomField has no handler for
            # it).  Re-read them directly from the XML when opening an XML file.
            if file_path.lower().endswith('.xml'):
                self._source_xml_path = file_path
                self._patch_load_enterprise_cf_values(project, file_path)
                self._patch_load_custom_properties(project, file_path)
            else:
                self._source_xml_path = None
            self.logic.load_data(project)
            return True
        except Exception as e:
            import traceback
            error_msg = f"Error opening project: {e}\n\n{traceback.format_exc()}"
            print(error_msg)
            try:
                from PyQt5.QtWidgets import QMessageBox  # type: ignore
                if parent is not None:
                    QMessageBox.critical(parent, "Error", error_msg)
            except Exception:
                pass
            return False

    def _break_circular_calendar_refs(self, project):
        """Detect and sever circular parent-calendar chains.

        MSPDIWriter.write() follows parent-calendar references when ordering
        calendars for output.  A cycle (A → B → A) causes a Java
        StackOverflowError which JPype surfaces as
        ``RecursionError: maximum recursion depth exceeded``.

        Walk each calendar's ancestor chain; if a UID is seen twice, remove
        the parent link that closes the cycle.
        """
        try:
            for cal in list(project.getCalendars()):
                visited: set = set()
                cur = cal
                while cur is not None:
                    try:
                        uid = cur.getUniqueID()
                        key = id(cur) if uid is None else int(str(uid))
                    except Exception:
                        break
                    if key in visited:
                        try:
                            cur.setParent(None)
                        except Exception:
                            pass
                        break
                    visited.add(key)
                    try:
                        cur = cur.getParent()
                    except Exception:
                        break
        except Exception as exc:
            print(f"[WARN] _break_circular_calendar_refs: {exc}")

    def _sanitize_calendar_uids(self, project):
        """Ensure every calendar in the project has a non-null uniqueID.

        MPXJ's MSPDIWriter calls calendarUniqueID.equals(...) during write,
        which throws NullPointerException if any calendar was created without
        a UID (e.g. resource calendars added by the Confluence sync).
        """
        from java.lang import Integer as JInteger  # type: ignore
        calendars = list(project.getCalendars())
        existing = set()
        for cal in calendars:
            uid = cal.getUniqueID()
            if uid is not None:
                existing.add(int(str(uid)))
        next_uid = (max(existing) + 1) if existing else 1
        for cal in calendars:
            if cal.getUniqueID() is None:
                cal.setUniqueID(JInteger(next_uid))
                next_uid += 1

    def sanitize_resource_uids(self, project):
        """Called after Confluence sync to assign UIDs and sequential IDs immediately."""
        self._sanitize_resource_uids(project)
        self._sanitize_resource_ids(project)

    def _sanitize_resource_uids(self, project):
        """Ensure every resource has a non-null, non-zero uniqueID before writing.

        Enterprise resources added by the Confluence sync may have null or zero
        UIDs. MSPDIWriter then omits the <UID> element (null) or writes <UID>0</UID>
        (zero), causing MS Project to treat them all as the unassigned placeholder
        (UID=0) and reject the file with "invalid data" on import.
        """
        from java.lang import Integer as JInteger  # type: ignore
        resources = list(project.getResources())
        existing = set()
        for res in resources:
            uid = res.getUniqueID()
            if uid is not None:
                existing.add(int(str(uid)))
        next_uid = (max(existing) + 1) if existing else 1
        for res in resources:
            uid = res.getUniqueID()
            # Assign new UID if null, or if 0 but the resource has a name
            # (0 is the reserved unassigned-work placeholder; it must have no name)
            if uid is None or (int(str(uid)) == 0 and res.getName()):
                while next_uid in existing:
                    next_uid += 1
                res.setUniqueID(JInteger(next_uid))
                existing.add(next_uid)
                next_uid += 1

    def _sanitize_resource_ids(self, project):
        """Assign sequential IDs to resources that have a null getID().

        MPXJ does not auto-assign sequential IDs when project.addResource() is
        called (e.g. resources created by the Confluence sync).  Without an ID
        the resource sheet shows a blank ID column and some views skip the row.
        """
        from java.lang import Integer as JInteger  # type: ignore
        resources = list(project.getResources())
        existing = set()
        for res in resources:
            rid = res.getID()
            if rid is not None:
                existing.add(int(str(rid)))
        next_id = (max(existing) + 1) if existing else 1
        for res in resources:
            if res.getID() is None:
                while next_id in existing:
                    next_id += 1
                res.setID(JInteger(next_id))
                existing.add(next_id)
                next_id += 1

    def _remove_unassigned_enterprise_resources(self, project):
        """Remove enterprise resources that have no assignments in this project.

        The Confluence calendar sync looks up enterprise resources by name and
        attaches vacation calendars to them. MPXJ then includes those resources
        in the written XML even though they have no tasks, no assignments, and
        lack required fields (GUID, Initials) that MS Project expects for named
        resources. MS Project rejects the file with "invalid data in <Name>".
        """
        assigned_resource_uids = set()
        for assignment in project.getResourceAssignments():
            r = assignment.getResource()
            if r is not None:
                uid = r.getUniqueID()
                if uid is not None:
                    assigned_resource_uids.add(int(str(uid)))

        to_remove = []
        for res in project.getResources():
            uid = res.getUniqueID()
            if uid is None:
                to_remove.append(res)
                continue
            uid_int = int(str(uid))
            # UID=0 is the reserved unassigned placeholder — keep it
            if uid_int == 0:
                continue
            if uid_int not in assigned_resource_uids and res.getName():
                # Named resource with no assignments — check if it was an enterprise add.
                # Keep resources that have a personal calendar (created by Confluence sync
                # for vacation tracking); remove only bare enterprise placeholders.
                if res.getGUID() is None and res.getCalendar() is None:
                    to_remove.append(res)

        if to_remove:
            # JPype's _jcollection.remove(obj) wraps the argument in JObject
            # which re-enters remove() recursively until Python's stack limit is
            # hit.  removeAll(Collection) goes through a different code path and
            # does not exhibit the bug.
            from java.util import ArrayList as _JArrayList  # type: ignore
            remove_list = _JArrayList()
            for res in to_remove:
                remove_list.add(res)
            project.getResources().removeAll(remove_list)


    def _remove_orphaned_resource_calendars(self, project):
        """Remove calendars named '<Name> Calendar' that are not linked to any resource.

        These are left behind when a previous save (with the old
        _remove_unassigned_enterprise_resources logic) deleted the resource but
        kept its calendar.  The Confluence sync now reuses them when it finds
        them, so any that remain after sync are truly orphaned.
        """
        try:
            linked_cal_ids = set()
            for res in project.getResources():
                rc = res.getCalendar()
                if rc is not None:
                    try:
                        uid = rc.getUniqueID()
                        if uid is not None:
                            linked_cal_ids.add(int(str(uid)))
                    except Exception:
                        pass
            to_remove = []
            for cal in list(project.getCalendars()):
                try:
                    uid = cal.getUniqueID()
                    uid_int = int(str(uid)) if uid is not None else None
                except Exception:
                    continue
                # Only target auto-generated resource calendars (end with " Calendar")
                cal_name = str(cal.getName()) if cal.getName() is not None else ""
                if not cal_name.endswith(" Calendar"):
                    continue
                if uid_int is not None and uid_int not in linked_cal_ids:
                    to_remove.append(cal)
            for cal in to_remove:
                try:
                    project.getCalendars().remove(cal)
                except Exception:
                    pass
        except Exception as exc:
            print(f"[WARN] _remove_orphaned_resource_calendars: {exc}")

    def save_project(self, file_path):
        try:
            from org.mpxj.mspdi import MSPDIWriter  # type: ignore
            project = self.logic.get_data()
            if project:
                self._sanitize_calendar_uids(project)
                self._sanitize_resource_uids(project)
                self._sanitize_resource_ids(project)
                self._remove_unassigned_enterprise_resources(project)
                self._remove_orphaned_resource_calendars(project)
                self._break_circular_calendar_refs(project)
                MSPDIWriter().write(project, file_path)
                self._patch_enterprise_cf_values(project, file_path)
                self._patch_save_custom_properties(project, file_path)
                return True
            return False
        except Exception as e:
            import traceback
            print(f"Error saving project: {e}\n\n{traceback.format_exc()}")
            return False

    def _patch_enterprise_cf_values(self, project, dest_path):
        """Inject enterprise custom-field values that MSPDIWriter silently drops.

        When the project was loaded from an XML file, we copy the
        <EnterpriseExtendedAttribute> elements directly from the source XML to
        the destination XML — this is reliable regardless of MPXJ's internal
        FieldID remapping.

        When the source was an MPP (or no source XML is known), we fall back to
        querying MPXJ's in-memory project via getCachedValue().
        """
        try:
            import xml.etree.ElementTree as ET

            NS = 'http://schemas.microsoft.com/project'
            ET.register_namespace('', NS)

            tree = ET.parse(dest_path)
            root = tree.getroot()

            modified = False

            # ------------------------------------------------------------------ #
            # Normalize resource names: replace ';' separator with ','           #
            # (Confluence sometimes delivers "Surname; Forename")                #
            # ------------------------------------------------------------------ #
            for res_el in root.findall(f'.//{{{NS}}}Resource'):
                name_el = res_el.find(f'{{{NS}}}Name')
                if name_el is not None and name_el.text and ';' in name_el.text:
                    name_el.text = name_el.text.replace(';', ',').strip()
                    modified = True

            # ------------------------------------------------------------------ #
            # Primary path: source is an XML file → copy elements directly       #
            # ------------------------------------------------------------------ #
            if self._source_xml_path and os.path.isfile(self._source_xml_path):
                modified |= self._copy_enterprise_attrs_from_xml(
                    self._source_xml_path, root, NS
                )

            # ------------------------------------------------------------------ #
            # Fallback: source was MPP → read from MPXJ in-memory project        #
            # ------------------------------------------------------------------ #
            if not modified:
                modified |= self._inject_enterprise_attrs_from_mpxj(
                    project, root, NS
                )

            if modified:
                _xml_indent(root)
                tree.write(dest_path, xml_declaration=True, encoding='UTF-8')
                # After a successful save the dest file becomes the new source
                self._source_xml_path = dest_path

        except Exception as e:
            print(f"[WARN] _patch_enterprise_cf_values: {e}")

    def _copy_enterprise_attrs_from_xml(self, src_path, dest_root, NS):
        """Copy <EnterpriseExtendedAttribute> elements from src XML to dest root.

        Returns True if any elements were injected.
        """
        import xml.etree.ElementTree as ET

        src_tree = ET.parse(src_path)
        src_root = src_tree.getroot()

        # Build uid → list of (FieldID, FieldIDInHex, Value) from source
        src_attrs = {}   # uid (int) → {FieldID (int) → (hex_str, val_str)}
        for task_el in src_root.findall(f'.//{{{NS}}}Task'):
            uid_el = task_el.find(f'{{{NS}}}UID')
            if uid_el is None:
                continue
            try:
                uid = int(uid_el.text)
            except (ValueError, TypeError):
                continue
            for ea in task_el.findall(f'{{{NS}}}EnterpriseExtendedAttribute'):
                fid_el = ea.find(f'{{{NS}}}FieldID')
                hex_el = ea.find(f'{{{NS}}}FieldIDInHex')
                val_el = ea.find(f'{{{NS}}}Value')
                if fid_el is None or val_el is None:
                    continue
                try:
                    fid = int(fid_el.text)
                except (ValueError, TypeError):
                    continue
                hex_str = hex_el.text if hex_el is not None else hex(fid)[2:]
                val_str = val_el.text or ''
                src_attrs.setdefault(uid, {})[fid] = (hex_str, val_str)

        if not src_attrs:
            return False

        modified = False
        for task_el in dest_root.findall(f'.//{{{NS}}}Task'):
            uid_el = task_el.find(f'{{{NS}}}UID')
            if uid_el is None:
                continue
            try:
                uid = int(uid_el.text)
            except (ValueError, TypeError):
                continue
            attrs = src_attrs.get(uid)
            if not attrs:
                continue

            # Collect FieldIDs already present
            existing_fids = set()
            for ea in (
                list(task_el.findall(f'{{{NS}}}ExtendedAttribute')) +
                list(task_el.findall(f'{{{NS}}}EnterpriseExtendedAttribute'))
            ):
                fid_el = ea.find(f'{{{NS}}}FieldID')
                if fid_el is not None:
                    try:
                        existing_fids.add(int(fid_el.text))
                    except (ValueError, TypeError):
                        pass

            for fid, (hex_str, val_str) in sorted(attrs.items()):
                if fid in existing_fids:
                    continue
                ea_el = ET.SubElement(
                    task_el, f'{{{NS}}}EnterpriseExtendedAttribute'
                )
                ET.SubElement(ea_el, f'{{{NS}}}FieldIDInHex').text = hex_str
                ET.SubElement(ea_el, f'{{{NS}}}FieldID').text = str(fid)
                ET.SubElement(ea_el, f'{{{NS}}}Value').text = val_str
                modified = True

        return modified

    def _inject_enterprise_attrs_from_mpxj(self, project, dest_root, NS):
        """Fallback: inject enterprise CF values from MPXJ in-memory project.

        Used when the source was an MPP file (no source XML available).
        Returns True if any elements were injected.
        """
        try:
            import xml.etree.ElementTree as ET
            from org.mpxj import UserDefinedField  # type: ignore

            name_to_ft = {}
            for cf in project.getCustomFields():
                ft = cf.getFieldType()
                if ft is None:
                    continue
                if str(ft.getFieldTypeClass()) != 'TASK':
                    continue
                if not isinstance(ft, UserDefinedField):
                    continue
                name_to_ft[str(ft)] = ft
                alias = cf.getAlias()
                if alias:
                    name_to_ft[str(alias)] = ft

            if not name_to_ft:
                return False

            # Derive real MSPDI FieldIDs from the dest XML definitions
            ecf_fields = {}
            ea_section = dest_root.find(f'{{{NS}}}ExtendedAttributes')
            if ea_section is not None:
                for ea_def in ea_section.findall(f'{{{NS}}}ExtendedAttribute'):
                    udf_el = ea_def.find(f'{{{NS}}}UserDef')
                    if udf_el is None or udf_el.text != '1':
                        continue
                    fid_el  = ea_def.find(f'{{{NS}}}FieldID')
                    name_el = ea_def.find(f'{{{NS}}}FieldName')
                    alias_el = ea_def.find(f'{{{NS}}}Alias')
                    if fid_el is None:
                        continue
                    try:
                        fid = int(fid_el.text)
                    except (ValueError, TypeError):
                        continue
                    for cand in [
                        alias_el.text if alias_el is not None else None,
                        name_el.text  if name_el  is not None else None,
                    ]:
                        if cand:
                            ft = name_to_ft.get(cand.strip())
                            if ft is not None:
                                ecf_fields[fid] = ft
                                break

            if not ecf_fields:
                # Last resort: ft.getValue()
                for cf in project.getCustomFields():
                    ft = cf.getFieldType()
                    if ft is None:
                        continue
                    if str(ft.getFieldTypeClass()) != 'TASK':
                        continue
                    if not isinstance(ft, UserDefinedField):
                        continue
                    try:
                        ecf_fields[int(str(ft.getValue()))] = ft
                    except Exception:
                        pass

            if not ecf_fields:
                return False

            # Collect per-task values
            task_values = {}
            for task in project.getTasks():
                uid = int(str(task.getUniqueID()))
                vals = {}
                for fid, ft in ecf_fields.items():
                    raw = task.getCachedValue(ft)
                    if raw is None:
                        continue
                    dt = str(ft.getDataType()).upper()
                    if 'BOOLEAN' in dt:
                        if str(raw).lower() not in ('true', '1'):
                            continue
                        val_str = '1'
                    elif 'NUMERIC' in dt or 'CURRENCY' in dt or 'PERCENTAGE' in dt:
                        num = float(str(raw))
                        if num == 0.0:
                            continue
                        val_str = str(num)
                    elif 'DURATION' in dt:
                        val_str = str(raw)
                        if not val_str or val_str in ('null', 'None'):
                            continue
                    elif 'DATE' in dt:
                        val_str = str(raw)[:19].replace(' ', 'T')
                        if not val_str or val_str in ('null', 'None'):
                            continue
                    else:
                        val_str = str(raw)
                        if not val_str or val_str in ('null', 'None'):
                            continue
                    vals[fid] = val_str
                if vals:
                    task_values[uid] = vals

            if not task_values:
                return False

            modified = False
            for task_el in dest_root.findall(f'.//{{{NS}}}Task'):
                uid_el = task_el.find(f'{{{NS}}}UID')
                if uid_el is None:
                    continue
                try:
                    uid = int(uid_el.text)
                except (ValueError, TypeError):
                    continue
                vals = task_values.get(uid)
                if not vals:
                    continue
                existing_fids = {
                    int(ea.find(f'{{{NS}}}FieldID').text)
                    for ea in (
                        list(task_el.findall(f'{{{NS}}}ExtendedAttribute')) +
                        list(task_el.findall(f'{{{NS}}}EnterpriseExtendedAttribute'))
                    )
                    if ea.find(f'{{{NS}}}FieldID') is not None
                }
                for fid, val_str in sorted(vals.items()):
                    if fid in existing_fids:
                        continue
                    ea_el = ET.SubElement(
                        task_el, f'{{{NS}}}EnterpriseExtendedAttribute'
                    )
                    ET.SubElement(ea_el, f'{{{NS}}}FieldIDInHex').text = hex(fid)[2:]
                    ET.SubElement(ea_el, f'{{{NS}}}FieldID').text = str(fid)
                    ET.SubElement(ea_el, f'{{{NS}}}Value').text = val_str
                    modified = True

            return modified

        except Exception as e:
            print(f"[WARN] _inject_enterprise_attrs_from_mpxj: {e}")
            return False


        except Exception as e:
            print(f"[WARN] _patch_enterprise_cf_values: {e}")

    def _patch_load_enterprise_cf_values(self, project, file_path):
        """Restore enterprise custom-field values that MPXJ's MSPDIReader ignores.

        MPXJ reads UserDefinedField definitions (aliases) from XML but silently
        discards the per-task values because it assigns DataType.CUSTOM to all
        enterprise custom fields and DatatypeConverter.parseCustomField has no
        handler for that type.

        When MPXJ loads from XML it assigns sequential counters (1, 2, 3…) as
        ft.getValue(), NOT the MSPDI FieldIDs stored in the XML (e.g. 190873604).
        We therefore build the FieldID→ft map two ways:
          • ft.getValue()-keyed  — works for our own re-saved XML files
          • name-keyed via XML project-level definitions — works for original
            MS Project XML exports where the FieldIDs are the real MSPDI values.

        This method re-parses the XML to extract those values and sets them on
        the in-memory task objects via task.set(fieldType, value).
        """
        try:
            import xml.etree.ElementTree as ET
            from org.mpxj import UserDefinedField  # type: ignore

            NS = 'http://schemas.microsoft.com/project'

            # -- 1. Collect all TASK-class UserDefinedField instances from MPXJ --
            # name_to_ft: str(ft) and alias → ft  (for name-based XML matching)
            # val_to_ft:  ft.getValue()      → ft  (for our own saved XML)
            name_to_ft = {}
            val_to_ft  = {}
            for cf in project.getCustomFields():
                ft = cf.getFieldType()
                if ft is None:
                    continue
                if str(ft.getFieldTypeClass()) != 'TASK':
                    continue
                if not isinstance(ft, UserDefinedField):
                    continue
                name_to_ft[str(ft)] = ft
                alias = cf.getAlias()
                if alias:
                    name_to_ft[str(alias)] = ft
                try:
                    val_to_ft[int(str(ft.getValue()))] = ft
                except Exception:
                    pass

            if not name_to_ft and not val_to_ft:
                return

            # -- 2. Parse XML --
            tree = ET.parse(file_path)
            root = tree.getroot()

            # -- 3. Build FieldID → ft map --
            # Start with getValue()-based entries (works for our saved XML format).
            ecf_fields = dict(val_to_ft)

            # Add MSPDI-FieldID → ft entries by matching field names from the
            # project-level <ExtendedAttributes> section (works for original
            # MS Project XML where the FieldIDs are the real MSPDI values).
            ea_section = root.find(f'{{{NS}}}ExtendedAttributes')
            if ea_section is not None:
                for ea_def in ea_section.findall(f'{{{NS}}}ExtendedAttribute'):
                    udf_el = ea_def.find(f'{{{NS}}}UserDef')
                    if udf_el is None or udf_el.text != '1':
                        continue
                    fid_el  = ea_def.find(f'{{{NS}}}FieldID')
                    name_el = ea_def.find(f'{{{NS}}}FieldName')
                    if fid_el is None or name_el is None:
                        continue
                    try:
                        fid = int(fid_el.text)
                    except (ValueError, TypeError):
                        continue
                    fname = (name_el.text or '').strip()
                    ft = name_to_ft.get(fname)
                    if ft is not None:
                        ecf_fields[fid] = ft   # add real MSPDI FieldID → ft

            if not ecf_fields:
                return

            # -- 4. Build UID → task map --
            task_map = {int(str(t.getUniqueID())): t for t in project.getTasks()}

            # -- 5. Read per-task values from both element formats --
            for task_el in root.findall(f'.//{{{NS}}}Task'):
                uid_el = task_el.find(f'{{{NS}}}UID')
                if uid_el is None:
                    continue
                uid = int(uid_el.text)
                task = task_map.get(uid)
                if task is None:
                    continue

                # <ExtendedAttribute>          — our saved XML format
                # <EnterpriseExtendedAttribute> — original MS Project XML format
                ea_elements = (
                    list(task_el.findall(f'{{{NS}}}ExtendedAttribute')) +
                    list(task_el.findall(f'{{{NS}}}EnterpriseExtendedAttribute'))
                )
                for ea in ea_elements:
                    fid_el = ea.find(f'{{{NS}}}FieldID')
                    val_el = ea.find(f'{{{NS}}}Value')
                    if fid_el is None or val_el is None or not val_el.text:
                        continue
                    try:
                        fid = int(fid_el.text)
                    except (ValueError, TypeError):
                        continue
                    ft = ecf_fields.get(fid)
                    if ft is None:
                        continue
                    if task.getCachedValue(ft) is not None:
                        continue   # already set (e.g. by MPXJ for non-CUSTOM types)
                    try:
                        task.set(ft, val_el.text)
                    except Exception:
                        pass

        except Exception as e:
            print(f"[WARN] _patch_load_enterprise_cf_values: {e}")

    def _patch_save_custom_properties(self, project, file_path):
        """Persist custom properties that MSPDIWriter drops.

        The MSPDI XML format has no <CustomProperties> element — it is simply
        absent from the schema (confirmed in org.mpxj.mspdi.schema.Project.java
        and org.mpxj.mspdi.MSPDIWriter.writeProjectProperties).  Even MS Project
        itself loses them when saving to XML.

        We store them in a JSON sidecar file (<xml_path>.custom-props.json)
        so they survive our app's round-trip without touching the XML itself.
        The sidecar is invisible to MS Project and other MSPDI consumers.
        """
        try:
            import json

            cp = project.getProjectProperties().getCustomProperties()
            if not cp or cp.size() == 0:
                return

            import json as _json
            props = {}
            for key in cp.keySet():
                val = cp.get(key)
                key_str = str(key)
                if val is None:
                    props[key_str] = ''
                else:
                    val_str = str(val)
                    # Expand JSON-object strings to nested dicts for clean sidecar storage
                    if val_str.startswith('{'):
                        try:
                            props[key_str] = _json.loads(val_str)
                            continue
                        except (ValueError, Exception):
                            pass
                    props[key_str] = val_str

            if not props:
                return

            sidecar = file_path + '.custom-props.json'
            with open(sidecar, 'w', encoding='utf-8') as f:
                _json.dump(props, f, ensure_ascii=False, indent=2)

        except Exception as e:
            print(f"[WARN] _patch_save_custom_properties: {e}")

    def _patch_load_custom_properties(self, project, file_path):
        """Restore custom properties from the sidecar JSON file.

        Reads <xml_path>.custom-props.json written by
        _patch_save_custom_properties and populates the project's custom
        property map so the data is available in the UI.
        """
        try:
            import json

            sidecar = file_path + '.custom-props.json'
            if not os.path.exists(sidecar):
                return

            with open(sidecar, 'r', encoding='utf-8') as f:
                props = json.load(f)

            if not props:
                return

            import json as _json
            from java.util import HashMap  # type: ignore
            cp = HashMap()
            for k, v in props.items():
                if isinstance(v, dict):
                    # Re-serialise nested dicts (container blocks) back to JSON strings
                    cp.put(k, _json.dumps(v, ensure_ascii=False))
                else:
                    cp.put(k, str(v) if v is not None else '')

            project.getProjectProperties().setCustomProperties(cp)

        except Exception as e:
            print(f"[WARN] _patch_load_custom_properties: {e}")

    # ------------------------------------------------------------------ #
    # CPM sidecar helpers                                                  #
    # ------------------------------------------------------------------ #

    _CPM_DEFAULTS = {"critical_slack_days": 0, "dep_types": "all"}

    def load_cpm_settings(self, file_path: str) -> dict:
        """Load CPM settings from the 'cpm' block of the project sidecar JSON.

        Returns MS Project defaults if the file or block is absent.
        """
        defaults = dict(self._CPM_DEFAULTS)
        if not file_path:
            return defaults
        sidecar = file_path + '.custom-props.json'
        if not os.path.exists(sidecar):
            return defaults
        try:
            import json
            with open(sidecar, 'r', encoding='utf-8') as f:
                data = json.load(f)
            cpm = data.get("cpm", {})
            return {
                "critical_slack_days": int(cpm.get("critical_slack_days", 0)),
                "dep_types": str(cpm.get("dep_types", "all")),
            }
        except Exception as e:
            print(f"[WARN] load_cpm_settings: {e}")
            return defaults

    def save_cpm_settings(self, file_path: str, cpm_cfg: dict) -> None:
        """Write CPM settings into the 'cpm' block of the project sidecar JSON."""
        if not file_path:
            return
        import json
        sidecar = file_path + '.custom-props.json'
        data: dict = {}
        if os.path.exists(sidecar):
            try:
                with open(sidecar, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except Exception:
                pass
        data["cpm"] = {
            "critical_slack_days": cpm_cfg.get("critical_slack_days", 0),
            "dep_types": cpm_cfg.get("dep_types", "all"),
        }
        with open(sidecar, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

