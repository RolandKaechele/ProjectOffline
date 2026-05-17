# app_debug.py - Central debug flag for the application.
#
# Any module that wants debug output imports this:
#   from app_debug import is_debug
#
# main.py enables it once via set_debug(True) when --debug / -v is passed.
# No other file needs to be changed when adding or removing debug-capable modules.
#
# Debug dump (Ctrl+D when --debug is active)
# ------------------------------------------
# dump_project_state(project) writes a JSON-structured snapshot of the
# in-memory project (tasks, resources, assignments, project properties)
# to  <cwd>/debug_project_dump.json  so that an AI agent or developer can
# inspect the live RAM state without needing the original file.

import json
import os
import sys
import datetime


class _JsonEncoder(json.JSONEncoder):
    """JSON encoder that handles types json.dump cannot serialize by default."""
    def default(self, obj):
        if isinstance(obj, datetime.datetime):
            return obj.isoformat()
        if isinstance(obj, datetime.date):
            return obj.isoformat()
        if isinstance(obj, datetime.timedelta):
            return obj.total_seconds()
        # PyQt5 QDate / QDateTime
        try:
            from PyQt5.QtCore import QDate, QDateTime  # type: ignore
            if isinstance(obj, QDateTime):
                return obj.toString("yyyy-MM-ddTHH:mm:ss")
            if isinstance(obj, QDate):
                return obj.toString("yyyy-MM-dd")
        except Exception:
            pass
        return super().default(obj)

try:
    from _version import BUILD_VERSION as _BUILD_VERSION  # type: ignore
except ImportError:
    _BUILD_VERSION = "dev"

_debug = False


def set_debug(enabled: bool) -> None:
    global _debug
    _debug = enabled


def is_debug() -> bool:
    return _debug


# ---------------------------------------------------------------------------
# Project state dump
# ---------------------------------------------------------------------------

def _build_cpm_entry(tid: int, ui_state: dict | None) -> dict | None:
    """Build a CPM sub-dict for task *tid* using float_data from ui_state.

    Phase 5 additions: total_float_wh / free_float_wh (calendar-aware working
    hours), work_day_hours (per-task calendar wdh), and *_d fields expressed
    in working days using the per-task wdh instead of a hardcoded 8 h/day.
    """
    try:
        # float_data keys are ints; tid may arrive as a string from _s()
        _fd_all = (ui_state or {}).get("float_data", {})
        try:
            fd = _fd_all.get(int(tid))
        except (TypeError, ValueError):
            fd = _fd_all.get(tid)
        if not fd:
            return None
        def _td_h(v):
            try:
                return round(v.total_seconds() / 3600, 2)
            except Exception:
                return None
        def _dt(v):
            try:
                return str(v) if v is not None else None
            except Exception:
                return None

        # Per-task calendar working hours/day (Phase 5); fall back to 8
        wdh = float(fd.get("work_day_hours") or 8.0)
        wdh = max(wdh, 0.25)  # safety clamp

        # Prefer calendar-aware working-hours values (Phase 5) over timedelta
        tf_wh = fd.get("total_float_wh")  # float | None
        ff_wh = fd.get("free_float_wh")   # float | None
        tf_h  = tf_wh if tf_wh is not None else _td_h(fd.get("total_float"))
        ff_h  = ff_wh if ff_wh is not None else _td_h(fd.get("free_float"))

        return {
            "es":                  _dt(fd.get("es")),
            "ef":                  _dt(fd.get("ef")),
            "ls":                  _dt(fd.get("ls")),
            "lf":                  _dt(fd.get("lf")),
            # Wall-clock hours from timedelta (legacy, always present)
            "total_float_h":       _td_h(fd.get("total_float")),
            "free_float_h":        _td_h(fd.get("free_float")),
            # Phase 5: calendar-aware working hours
            "total_float_wh":      round(tf_wh, 2) if tf_wh is not None else None,
            "free_float_wh":       round(ff_wh, 2) if ff_wh is not None else None,
            "work_day_hours":      round(wdh, 2),
            # Working-day display using per-task wdh
            "total_float_d":       round(tf_h / wdh, 2) if tf_h is not None else None,
            "free_float_d":        round(ff_h / wdh, 2) if ff_h is not None else None,
            "calendar_aware":      tf_wh is not None,
            "critical":            bool(fd.get("critical")),
        }
    except Exception:
        return None


def dump_project_state(project, ui_state: dict | None = None) -> str:
    """Serialise the live MPXJ ProjectFile (and optional UI state) to a JSON
    file and return the path.

    Only callable when is_debug() is True (enforced by the caller).
    ui_state is a plain dict of scalar values collected by the caller.
    """
    if project is None:
        return ""

    def _s(v):
        """Convert any value to a plain Python scalar safe for json.dumps."""
        if v is None:
            return None
        try:
            # java.time.LocalDateTime / LocalDate ? ISO string
            s = str(v)
            # Keep only printable ASCII; JPype objects stringify cleanly
            return s
        except Exception:
            return None

    def _f(v):
        """Float or None."""
        if v is None:
            return None
        try:
            return float(str(v))
        except Exception:
            return None

    # ---- Project properties ------------------------------------------------
    try:
        props = project.getProjectProperties()
        project_block = {
            "name":          _s(props.getName()),
            "start":         _s(props.getStartDate()),
            "finish":        _s(props.getFinishDate()),
            "author":        _s(props.getAuthor()),
            "company":       _s(props.getCompany()),
            "status_date":   _s(props.getStatusDate()),
            "currency":      _s(props.getCurrencySymbol()),
        }
        # Baseline capture dates (slots 0-10)
        baseline_dates = {}
        try:
            for _n in range(11):
                try:
                    _d = props.getBaselineDate() if _n == 0 else props.getBaselineDate(_n)
                    if _d is not None:
                        baseline_dates[str(_n)] = str(_d)[:10]
                except Exception:
                    pass
        except Exception:
            pass
        project_block["baseline_dates"] = baseline_dates
    except Exception as exc:
        project_block = {"error": str(exc)}

    # ---- Pre-build custom field type lists for task and resource values ----
    _task_cf_types = []
    _res_cf_types = []
    try:
        from org.mpxj import UserDefinedField  # type: ignore
        for cf in project.getCustomFields():
            try:
                ft = cf.getFieldType()
                if ft is None:
                    continue
                alias = str(cf.getAlias()).strip() if cf.getAlias() else str(ft)
                ftc = str(ft.getFieldTypeClass())
                if ftc == 'TASK':
                    _task_cf_types.append((ft, alias))
                elif ftc == 'RESOURCE':
                    _res_cf_types.append((ft, alias))
            except Exception:
                pass
    except Exception:
        pass

    # ---- Tasks -------------------------------------------------------------
    tasks_list = []
    try:
        for t in project.getTasks():
            try:
                tid = _s(t.getID())
                if tid == "0" or t.getName() is None:
                    continue
                # Predecessors
                preds = []
                try:
                    for rel in (t.getPredecessors() or []):
                        try:
                            preds.append({
                                "pred_id": _s(rel.getPredecessorTask().getID()),
                                "type":    _s(rel.getType()),
                                "lag":     _s(rel.getLag()),
                            })
                        except Exception:
                            pass
                except Exception:
                    pass
                # Assignments
                assignments = []
                try:
                    for a in (t.getResourceAssignments() or []):
                        try:
                            res = a.getResource()
                            res_uid = None
                            try:
                                res_uid = _s(res.getUniqueID()) if res else None
                            except Exception:
                                pass
                            assignments.append({
                                "resource":     _s(res.getName()) if res else None,
                                "resource_uid": res_uid,
                                "units":        _f(a.getUnits()),
                            })
                        except Exception:
                            pass
                except Exception:
                    pass

                # Baseline data for all slots (only populated slots are included)
                task_baselines = {}
                try:
                    import baseline_manager as _bm
                    for _n in range(11):
                        try:
                            _bs = _bm.get_baseline_start(t, _n)
                            _bf = _bm.get_baseline_finish(t, _n)
                            _bd = _bm.get_baseline_duration(t, _n)
                            if _bs is None and _bf is None and _bd is None:
                                continue
                            _v = _bm.get_variance(t, _n)
                            task_baselines[str(_n)] = {
                                "start":        _s(_bs),
                                "finish":       _s(_bf),
                                "duration":     _s(_bd),
                                "start_days":   _v["start_days"],
                                "finish_days":  _v["finish_days"],
                                "duration_pct": _v["duration_pct"],
                            }
                        except Exception:
                            pass
                except Exception:
                    pass

                # Custom field values for this task
                task_cf_values = {}
                for ft, alias in _task_cf_types:
                    try:
                        raw = t.getCachedValue(ft)
                        if raw is not None:
                            val = str(raw).strip()
                            if val not in ('null', 'None', ''):
                                task_cf_values[alias] = val
                    except Exception:
                        pass

                # MPXJ-level split segments from task.getSplits() (embedded in XML)
                mpxj_splits = []
                try:
                    raw_splits = t.getSplits()
                    if raw_splits is not None:
                        for dr in raw_splits:
                            mpxj_splits.append({
                                "start":  _s(dr.getStart()),
                                "finish": _s(dr.getEnd()),
                            })
                except Exception:
                    pass

                tasks_list.append({
                    "id":                tid,
                    "name":              _s(t.getName()),
                    "start":             _s(t.getStart()),
                    "finish":            _s(t.getFinish()),
                    "duration":          _s(t.getDuration()),
                    "pct_complete":      _f(t.getPercentageComplete()),
                    "critical":          _s(t.getCritical()),
                    "milestone":         _s(t.getMilestone()),
                    "summary":           _s(t.getSummary()),
                    "constraint_type":   _s(t.getConstraintType()),
                    "constraint_date":   _s(t.getConstraintDate()),
                    "baseline_start":    _s(t.getBaselineStart()),
                    "baseline_finish":   _s(t.getBaselineFinish()),
                    "baselines":         task_baselines,
                    "predecessors":      preds,
                    "assignments":       assignments,
                    "custom_fields":     task_cf_values,
                    "mpxj_splits":       mpxj_splits or None,
                    "cpm":               _build_cpm_entry(tid, ui_state),
                })
            except Exception as exc:
                tasks_list.append({"error": str(exc)})
    except Exception as exc:
        tasks_list = [{"error": str(exc)}]

    # ---- Resources ---------------------------------------------------------
    resources_list = []
    try:
        for r in project.getResources():
            try:
                if r.getName() is None:
                    continue
                # Custom field values for this resource
                res_cf_values = {}
                for ft, alias in _res_cf_types:
                    try:
                        raw = r.getCachedValue(ft)
                        if raw is not None:
                            val = str(raw).strip()
                            if val not in ('null', 'None', ''):
                                res_cf_values[alias] = val
                    except Exception:
                        pass

                # Personal calendar linked to this resource
                res_cal_block = None
                sec_cal_block = None
                try:
                    rc = r.getCalendar()
                    if rc is not None:
                        cal_exceptions = []
                        try:
                            for ex in rc.getCalendarExceptions():
                                try:
                                    cal_exceptions.append({
                                        "from":    str(ex.getFromDate())[:10] if ex.getFromDate() else None,
                                        "to":      str(ex.getToDate())[:10]   if ex.getToDate()   else None,
                                        "name":    str(ex.getName())          if ex.getName()     else None,
                                        "working": bool(ex.getWorking()),
                                    })
                                except Exception:
                                    pass
                        except Exception:
                            pass
                        parent_name = None
                        try:
                            p = rc.getParent()
                            if p is not None:
                                parent_name = str(p.getName()) if p.getName() else None
                        except Exception:
                            pass
                        res_cal_block = {
                            "name":            _s(rc.getName()),
                            "uid":             _s(rc.getUniqueID()),
                            "parent_calendar": parent_name,
                            "exception_count": len(cal_exceptions),
                            "exceptions":      cal_exceptions,
                        }
                except Exception:
                    pass

                # Optional AD-mapped secondary calendar linked via custom props
                try:
                    from integrations.secondary_calendar_integration import (  # type: ignore
                        resolve_secondary_calendar,
                    )

                    sec = resolve_secondary_calendar(project, r)
                    if sec:
                        sec_exceptions = []
                        sec_cal = sec.get("calendar")
                        if sec_cal is not None:
                            try:
                                for ex in sec_cal.getCalendarExceptions():
                                    try:
                                        if bool(ex.getWorking()):
                                            continue
                                    except Exception:
                                        pass
                                    sec_exceptions.append({
                                        "from": str(ex.getFromDate())[:10] if ex.getFromDate() else None,
                                        "to": str(ex.getToDate())[:10] if ex.getToDate() else None,
                                        "name": str(ex.getName()) if ex.getName() else None,
                                        "working": bool(ex.getWorking()),
                                    })
                            except Exception:
                                pass
                        sec_cal_block = {
                            "name": _s(sec.get("calendar_name")),
                            "uid": _s(sec.get("calendar_uid")),
                            "source": _s(sec.get("source")),
                            "resolved": sec_cal is not None,
                            "exception_count": len(sec_exceptions),
                            "exceptions": sec_exceptions,
                        }
                except Exception:
                    pass

                resources_list.append({
                    "id":           _s(r.getID()),
                    "unique_id":    _s(r.getUniqueID()),
                    "name":         _s(r.getName()),
                    "max_units":    _f(r.getMaxUnits()),
                    "type":         _s(r.getType()),
                    "email":        _s(r.getEmailAddress()),
                    "department_mpxj": (lambda: (lambda v: str(v) if v is not None else None)(r.getDepartment()) if hasattr(r, 'getDepartment') else None)(),
                    "calendar":     res_cal_block,
                    "secondary_calendar": sec_cal_block,
                    "custom_fields": res_cf_values,
                })
            except Exception as exc:
                resources_list.append({"error": str(exc)})
    except Exception as exc:
        resources_list = [{"error": str(exc)}]

    # ---- Custom properties (sidecar JSON, loaded into getCustomProperties()) --
    custom_properties = {}
    try:
        cp = project.getProjectProperties().getCustomProperties()
        if cp is not None:
            for key in cp.keySet():
                val = cp.get(key)
                custom_properties[str(key)] = str(val) if val is not None else None
    except Exception:
        pass

    # ---- Task custom field definitions (alias per slot) --------------------
    task_fields = {}
    try:
        from org.mpxj import TaskField  # type: ignore
        for cf in project.getCustomFields():
            try:
                ft = cf.getFieldType()
                if ft is None or str(ft.getFieldTypeClass()) != 'TASK':
                    continue
                alias = str(cf.getAlias()).strip() if cf.getAlias() else None
                if alias:
                    task_fields[str(ft)] = alias
            except Exception:
                pass
    except Exception:
        pass

    # ---- Resource custom field definitions (alias per slot) ----------------
    resource_fields = {}
    try:
        for cf in project.getCustomFields():
            try:
                ft = cf.getFieldType()
                if ft is None or str(ft.getFieldTypeClass()) != 'RESOURCE':
                    continue
                alias = str(cf.getAlias()).strip() if cf.getAlias() else None
                if alias:
                    resource_fields[str(ft)] = alias
            except Exception:
                pass
    except Exception:
        pass

    # ---- Enterprise custom fields (UID=0 summary task) -------------------
    # Read directly from XML when available (MPXJ getCachedValue does not
    # expose <EnterpriseExtendedAttribute> values for these fields).
    enterprise_fields = {}
    _xml_fp = (ui_state or {}).get('file_path', '') or ''
    if _xml_fp and _xml_fp.lower().endswith('.xml'):
        try:
            import xml.etree.ElementTree as ET
            _NS = 'http://schemas.microsoft.com/project'
            _tree = ET.parse(_xml_fp)
            _root = _tree.getroot()
            # Build FieldID ? display name (all UserDef=1 fields)
            _fid_to_name = {}
            _ea_sec = _root.find(f'{{{_NS}}}ExtendedAttributes')
            if _ea_sec is not None:
                for _ea in _ea_sec.findall(f'{{{_NS}}}ExtendedAttribute'):
                    _udf = _ea.find(f'{{{_NS}}}UserDef')
                    if _udf is None or _udf.text != '1':
                        continue
                    _fid_el = _ea.find(f'{{{_NS}}}FieldID')
                    _nm_el  = _ea.find(f'{{{_NS}}}FieldName')
                    _al_el  = _ea.find(f'{{{_NS}}}Alias')
                    if _fid_el is None or _nm_el is None:
                        continue
                    _disp = (_al_el.text or '').strip() if _al_el is not None and _al_el.text else (_nm_el.text or '').strip()
                    try:
                        _fid_to_name[int(_fid_el.text)] = _disp
                    except (ValueError, TypeError):
                        pass
            # Find Task UID=0 and read EnterpriseExtendedAttribute values
            _fid_to_val = {}
            for _task_el in _root.findall(f'.//{{{_NS}}}Task'):
                _uid = _task_el.find(f'{{{_NS}}}UID')
                if _uid is not None and _uid.text == '0':
                    for _eea in _task_el.findall(f'{{{_NS}}}EnterpriseExtendedAttribute'):
                        _fid_el = _eea.find(f'{{{_NS}}}FieldID')
                        _val_el = _eea.find(f'{{{_NS}}}Value')
                        if _fid_el is None:
                            continue
                        try:
                            _fid = int(_fid_el.text)
                        except (ValueError, TypeError):
                            continue
                        _fid_to_val[_fid] = (_val_el.text or '').strip() if _val_el is not None else ''
                    break
            for _fid, _name in sorted(_fid_to_name.items(), key=lambda x: x[1]):
                _v = _fid_to_val.get(_fid)
                if _v is not None and _v:
                    enterprise_fields[_name] = _v
        except Exception:
            pass
    if not enterprise_fields:
        # Fallback: MPXJ getCachedValue (works for locally-defined UDFs)
        try:
            from org.mpxj import UserDefinedField  # type: ignore
            summary_task = None
            for t in project.getTasks():
                try:
                    if int(str(t.getUniqueID())) == 0:
                        summary_task = t
                        break
                except Exception:
                    pass
            if summary_task is not None:
                for cf in project.getCustomFields():
                    try:
                        ft = cf.getFieldType()
                        if ft is None:
                            continue
                        if str(ft.getFieldTypeClass()) != 'TASK':
                            continue
                        if not isinstance(ft, UserDefinedField):
                            continue
                        alias = str(cf.getAlias()).strip() if cf.getAlias() else str(ft)
                        raw = summary_task.getCachedValue(ft)
                        val = str(raw).strip() if raw is not None else None
                        if val in ('null', 'None', ''):
                            val = None
                        if val is not None:
                            enterprise_fields[alias] = val
                    except Exception:
                        pass
        except Exception:
            pass

    # ---- Assemble & write --------------------------------------------------
    # Collect active baselines summary (slot -> iso date)
    _active_baselines: dict = {}
    try:
        import baseline_manager as _bm2
        _active_baselines = _bm2.get_active_baselines(project)
        _active_baselines = {str(k): v for k, v in _active_baselines.items()}
    except Exception:
        pass

    # ---- Compute expected cell colours from variance data ------------------
    # Independent re-implementation of the threshold logic in baseline_view.py.
    # Lets us verify data vs rendering: if expected_colors has entries but
    # ui.baseline_view.colored_cells is empty, setBackground() is never called.
    # If colored_cells matches expected_colors the issue is purely in the delegate.
    def _color_label_days(days):
        if days is None or days == 0:
            return None
        return "yellow" if abs(days) <= 2 else "orange" if abs(days) <= 5 else "red"

    def _color_label_pct(pct):
        if pct is None or abs(pct) < 0.05:
            return None
        return "yellow" if abs(pct) <= 10.0 else "orange" if abs(pct) <= 25.0 else "red"

    expected_colors = []
    _bl_slot = (ui_state or {}).get("baseline_view", {}).get("baseline_slot", 0)
    try:
        import baseline_manager as _bm3
        for t in project.getTasks():
            if t.getName() is None:
                continue
            _tid = _s(t.getID())
            if _tid == "0":
                continue
            try:
                _v = _bm3.get_variance(t, _bl_slot)
            except Exception:
                continue
            _sd = _color_label_days(_v.get("start_days"))
            _fd = _color_label_days(_v.get("finish_days"))
            _dp = _color_label_pct(_v.get("duration_pct"))
            if _sd or _fd or _dp:
                expected_colors.append({
                    "task_id":     _tid,
                    "task_name":   _s(t.getName()),
                    "start_?":    _sd,
                    "finish_?":   _fd,
                    "dur_%":      _dp,
                    "start_days":  _v.get("start_days"),
                    "finish_days": _v.get("finish_days"),
                    "dur_pct":     _v.get("duration_pct"),
                })
    except Exception:
        pass

    payload = {
        "build_version":    _BUILD_VERSION,
        "dump_timestamp":   datetime.datetime.now().isoformat(timespec="seconds"),
        "python_version":   sys.version,
        "platform":         sys.platform,
        "frozen":           getattr(sys, "frozen", False),
        "ui":               ui_state or {},
        "project":          project_block,
        "active_baselines": _active_baselines,
        "expected_baseline_colors": expected_colors,
        "custom_properties":  custom_properties,
        "task_fields":        task_fields,
        "resource_fields":    resource_fields,
        "enterprise_fields":  enterprise_fields,
        "tasks":              tasks_list,
        "resources":          resources_list,
    }

    # ---- Calendar / non-working-day diagnostics ----------------------------
    # Tests whether MPXJ's ProjectCalendar.isWorkingDate() agrees with the
    # cached _non_working sets captured in ui_state.  This is the primary
    # tool for diagnosing why the non-working-day drag dialog may not fire.
    calendar_diag = {}
    try:
        import java.time as _jtime2  # type: ignore
        cal2 = project.getDefaultCalendar()
        if cal2 is not None:
            calendar_diag["default_calendar_name"] = str(cal2.getName())
            calendar_diag["default_calendar_uid"]  = _s(cal2.getUniqueID())
            # Read calendar exceptions directly from MPXJ
            mpxj_exceptions = []
            try:
                for ex in cal2.getCalendarExceptions():
                    try:
                        mpxj_exceptions.append({
                            "from": str(ex.getFromDate())[:10] if ex.getFromDate() else None,
                            "to":   str(ex.getToDate())[:10]   if ex.getToDate()   else None,
                            "name": str(ex.getName())          if ex.getName()     else None,
                            "working": bool(ex.getWorking()),
                        })
                    except Exception:
                        pass
            except Exception:
                pass
            calendar_diag["mpxj_exceptions"] = mpxj_exceptions

            # Direct isWorkingDate probe: 60 days around today / project end
            from PyQt5.QtCore import QDate as _QDate2, Qt as _Qt2  # type: ignore
            _today = _QDate2.currentDate()
            probe_non_working = []
            probe_errors = []
            for _di in range(-5, 65):
                _qd2 = _today.addDays(_di)
                _dow = _qd2.dayOfWeek()
                if _dow in (6, 7):
                    continue  # weekends already known
                _iso2 = _qd2.toString(_Qt2.ISODate)
                try:
                    _ld2 = _jtime2.LocalDate.of(_qd2.year(), _qd2.month(), _qd2.day())
                    _working = bool(cal2.isWorkingDate(_ld2))
                    if not _working:
                        probe_non_working.append(_iso2)
                except Exception as _ex2:
                    probe_errors.append({"date": _iso2, "error": str(_ex2)})
            calendar_diag["mpxj_isWorkingDate_non_working_weekdays"] = probe_non_working
            if probe_errors:
                calendar_diag["mpxj_isWorkingDate_errors"] = probe_errors
        else:
            calendar_diag["default_calendar_name"] = None
            calendar_diag["error"] = "getDefaultCalendar() returned None"
    except Exception as _ce:
        calendar_diag["error"] = str(_ce)
    payload["calendar_diagnostics"] = calendar_diag

    # ---- Split task details -------------------------------------------------
    # Collected from GanttView._task_splits via ui_state["split_tasks"] if provided.
    split_tasks_block = []
    try:
        _split_data = (ui_state or {}).get("split_tasks", {})
        if _split_data:
            # Build uid ? task name lookup for human-readable output
            _uid_to_name = {}
            _uid_to_id   = {}
            try:
                for t in project.getTasks():
                    if t.getName() is None:
                        continue
                    try:
                        _uid = str(t.getUniqueID())
                        _uid_to_name[_uid] = str(t.getName())
                        _uid_to_id[_uid]   = str(t.getID())
                    except Exception:
                        pass
            except Exception:
                pass
            for uid_str, segs in _split_data.items():
                try:
                    split_tasks_block.append({
                        "unique_id":      uid_str,
                        "task_id":        _uid_to_id.get(uid_str, "?"),
                        "task_name":      _uid_to_name.get(uid_str, "?"),
                        "num_segments":   len(segs),
                        "segments": [
                            {"start": seg[0], "finish": seg[1]}
                            for seg in segs
                        ],
                    })
                except Exception:
                    pass
        else:
            # Also try to read splits directly from MPXJ if available
            try:
                for t in project.getTasks():
                    if t.getName() is None:
                        continue
                    try:
                        splits = t.getSplits()
                        if splits is None or splits.isEmpty():
                            continue
                        segs = []
                        for seg in splits:
                            try:
                                segs.append({
                                    "start":  str(seg.getStart())[:10],
                                    "finish": str(seg.getEnd())[:10],
                                })
                            except Exception:
                                pass
                        if len(segs) >= 2:
                            split_tasks_block.append({
                                "unique_id":    str(t.getUniqueID()),
                                "task_id":      str(t.getID()),
                                "task_name":    str(t.getName()),
                                "num_segments": len(segs),
                                "segments":     segs,
                                "source":       "mpxj",
                            })
                    except Exception:
                        pass
            except Exception:
                pass
    except Exception:
        pass
    payload["split_tasks"] = split_tasks_block

    # ---- KeePass integration status ----------------------------------------
    # Non-sensitive fields only: no paths, no passwords, no entry credentials.
    keepass_block = {}
    try:
        _kp = (ui_state or {}).get("keepass", {})
        if _kp:
            keepass_block = {
                "configured":                  _kp.get("configured"),
                "unlocked":                    _kp.get("unlocked"),
                "db_path_set":                 _kp.get("db_path_set"),
                "key_file_set":                _kp.get("key_file_set"),
                "password_saved":              _kp.get("password_saved"),
                "entry_count":                 _kp.get("entry_count"),
                "confluence_entry_configured": _kp.get("confluence_entry_configured"),
            }
    except Exception:
        pass
    payload["keepass_integration"] = keepass_block

    # ---- Confluence Calendar properties (enterprise custom fields) ----------
    confluence_cal_block = {}
    try:
        from integrations.confluence_calendar_integration import (  # type: ignore
            get_project_base_url, get_project_space_key,
            get_project_timezone, get_project_days_ahead,
        )
        if project is not None:
            base_url  = get_project_base_url(project)
            space_key = get_project_space_key(project)
            timezone  = get_project_timezone(project)
            days_ahead = get_project_days_ahead(project)
            confluence_cal_block = {
                "base_url_set":    bool(base_url),
                "base_url":        base_url or None,
                "space_key_set":   bool(space_key),
                "space_key":       space_key or None,
                "timezone":        timezone,
                "days_ahead":      days_ahead,
            }
    except Exception:
        pass
    payload["confluence_calendar_props"] = confluence_cal_block

    # ---- Active Directory sync result, lookup history, and resource calendars
    ad_sync_block = {}
    try:
        from integrations.ad_integration import (  # type: ignore
            is_ad_available, get_last_sync_result, get_last_lookup_results,
        )
        last = get_last_sync_result()
        raw_lookups = get_last_lookup_results()

        # Summarise multi-result searches (lookup_by_*_all) separately from
        # single-result lookups so the dump stays readable.
        single_lookups  = []
        multi_lookups   = []
        ad_search_history = []
        for entry in raw_lookups:
            fn     = entry.get("fn", "")
            inp    = entry.get("input", "")
            result = entry.get("result")
            if fn.endswith("_all"):
                # result is a list (or None)
                hits = result if isinstance(result, list) else []
                multi_lookups.append({
                    "fn":          fn,
                    "input":       inp,
                    "match_count": len(hits),
                    "matches":     [
                        {
                            "display_name": h.get("display_name"),
                            "email":        h.get("email"),
                            "department":   h.get("department"),
                            "username":     h.get("username"),
                            "city":         h.get("city"),
                            "state":        h.get("state"),
                            "country":      h.get("country"),
                        }
                        for h in hits
                    ],
                })
                ad_search_history.append({
                    "fn":      fn,
                    "input":   inp,
                    "matches": len(hits),
                })
            else:
                single_lookups.append({
                    "fn":     fn,
                    "input":  inp,
                    "found":  result is not None,
                    "result": {
                        "display_name": result.get("display_name") if result else None,
                        "email":        result.get("email")        if result else None,
                        "department":   result.get("department")   if result else None,
                        "username":     result.get("username")     if result else None,
                        "city":         result.get("city")         if result else None,
                        "state":        result.get("state")        if result else None,
                        "country":      result.get("country")      if result else None,
                    } if result else None,
                })

        # Per-resource calendar summary (name, parent, exception count)
        resource_calendars = []
        if project is not None:
            try:
                try:
                    from integrations.secondary_calendar_integration import (  # type: ignore
                        resolve_secondary_calendar,
                    )
                except Exception:
                    resolve_secondary_calendar = None

                for _r in project.getResources():
                    if _r.getName() is None:
                        continue
                    try:
                        _rc = _r.getCalendar()
                        if _rc is None:
                            continue
                        _parent_name = None
                        try:
                            _p = _rc.getParent()
                            if _p is not None:
                                _parent_name = str(_p.getName()) if _p.getName() else None
                        except Exception:
                            pass
                        _exc_count = 0
                        try:
                            _excs = _rc.getCalendarExceptions()
                            _exc_count = len(list(_excs)) if _excs is not None else 0
                        except Exception:
                            pass

                        _secondary = None
                        if resolve_secondary_calendar is not None:
                            try:
                                _sec = resolve_secondary_calendar(project, _r)
                                if _sec:
                                    _sec_count = 0
                                    _sec_cal = _sec.get("calendar")
                                    if _sec_cal is not None:
                                        try:
                                            _sec_ex = _sec_cal.getCalendarExceptions()
                                            _sec_count = len(list(_sec_ex)) if _sec_ex is not None else 0
                                        except Exception:
                                            pass
                                    _secondary = {
                                        "calendar_name": _s(_sec.get("calendar_name")),
                                        "calendar_uid": _s(_sec.get("calendar_uid")),
                                        "source": _s(_sec.get("source")),
                                        "resolved": _sec_cal is not None,
                                        "exception_count": _sec_count,
                                    }
                            except Exception:
                                pass

                        resource_calendars.append({
                            "resource":        _s(_r.getName()),
                            "calendar_name":   _s(_rc.getName()),
                            "calendar_uid":    _s(_rc.getUniqueID()),
                            "parent_calendar": _parent_name,
                            "exception_count": _exc_count,
                            "secondary_calendar": _secondary,
                        })
                    except Exception:
                        pass
            except Exception:
                pass

        ad_sync_block = {
            "available": is_ad_available(),
            "sync": {
                "total":   last.get("total")   if last else None,
                "updated": last.get("updated") if last else None,
                "skipped": last.get("skipped") if last else None,
                "errors":  last.get("errors")  if last else None,
            },
            "ad_search_history":  ad_search_history,
            "multi_result_searches": multi_lookups,
            "single_lookups":     single_lookups,
            "resource_calendars": resource_calendars,
        }
    except Exception:
        pass
    payload["ad_sync_result"] = ad_sync_block

    # ---- Email integration configuration -----------------------------------
    # Non-sensitive fields only: SMTP server, port, sender email, whether
    # KeePass entry is configured. No passwords or entry names.
    email_config_block = {}
    try:
        from integrations.email_integration import get_config_summary  # type: ignore
        email_config_block = get_config_summary()
    except Exception:
        pass
    payload["email_integration"] = email_config_block

    # ---- Email export status (last export run, no addresses) ---------------
    email_export_block = {}
    try:
        from integrations import email_integration as _ei  # type: ignore
        raw = getattr(_ei, "_last_export_result", None)
        if isinstance(raw, dict):
            email_export_block = {k: v for k, v in raw.items() if k != "to"}
    except Exception:
        pass
    payload["email_export_status"] = email_export_block

    # ---- Email templates status --------------------------------------------
    email_templates_block = {}
    try:
        import os as _os
        import json as _json
        _tmpl_dir = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "email_templates")
        _tmpl_dir = _os.path.normpath(_tmpl_dir)
        _exists = _os.path.isdir(_tmpl_dir)
        _names = []
        if _exists:
            for _fn in sorted(_os.listdir(_tmpl_dir)):
                if _fn.endswith(".json"):
                    try:
                        with open(_os.path.join(_tmpl_dir, _fn), "r", encoding="utf-8") as _fh:
                            _d = _json.load(_fh)
                        _names.append(_d.get("name") or _fn.replace(".json", ""))
                    except Exception:
                        _names.append(_fn.replace(".json", ""))
        email_templates_block = {
            "folder_exists":    _exists,
            "template_count":   len(_names),
            "template_names":   _names,
        }
    except Exception:
        pass
    payload["email_templates_status"] = email_templates_block

    # ---- Resource sidecar diagnostics ------------------------------------
    # Shows the state of the in-memory thumbnail/department stores and the
    # sidecar JSON file so avatar display and department persistence issues
    # can be diagnosed without access to the file system.
    resource_sidecar_block: dict = {}
    try:
        from dialogs import (  # type: ignore
            _resource_thumbnail_store as _rts,
            _resource_dept_store as _rds,
            _resource_thumbnail_sidecar as _rsc_path,
        )
        _sidecar_exists = bool(_rsc_path and os.path.exists(_rsc_path))
        _sidecar_size = 0
        if _sidecar_exists:
            try:
                _sidecar_size = os.path.getsize(_rsc_path)
            except Exception:
                pass
        # Per-resource sidecar state (keyed by UID)
        _all_uids = set(_rts) | set(_rds)
        # Build UID -> resource lookup from the live project (passed via closure)
        _uid_to_res: dict = {}
        try:
            for _r in project.getResources():
                if _r.getName() is None:
                    continue
                try:
                    _uid_to_res[str(_r.getUniqueID())] = _r
                except Exception:
                    pass
        except Exception:
            pass
        _per_uid = []
        for _uid in sorted(_all_uids, key=lambda x: int(x) if x.isdigit() else 0):
            _res_obj = _uid_to_res.get(_uid)
            _per_uid.append({
                "uid":             _uid,
                "name":            _s(_res_obj.getName())  if _res_obj else None,
                "type":            _s(_res_obj.getType())  if _res_obj else None,
                "resource_exists": _res_obj is not None,
                "has_thumbnail":   _uid in _rts,
                "thumbnail_bytes": len(_rts[_uid]) if _uid in _rts else None,
                "department":      _rds.get(_uid),
            })
        resource_sidecar_block = {
            "sidecar_path":    _rsc_path,
            "sidecar_exists":  _sidecar_exists,
            "sidecar_size_b":  _sidecar_size,
            "thumbnail_count": len(_rts),
            "dept_count":      len(_rds),
            "entries":         _per_uid,
        }
    except Exception as _rse:
        resource_sidecar_block = {"error": str(_rse)}
    payload["resource_sidecar"] = resource_sidecar_block

    # ---- Jira integration configuration ------------------------------------
    # Non-sensitive fields only: server names, URLs, auth modes, whether
    # KeePass is locked. No API tokens, passwords, or entry credentials.
    jira_config_block = {}
    try:
        from integrations.jira_integration import get_config_summary  # type: ignore
        jira_config_block = get_config_summary()
    except Exception:
        pass
    payload["jira_sync_config"] = jira_config_block

    # ---- Jira sync result (last run_sync() call) ----------------------------
    jira_sync_result_block = {}
    try:
        from integrations.jira_sync import get_last_result as _jsr  # type: ignore
        _res = _jsr()
        if _res:
            jira_sync_result_block = {
                "created": _res.get("created"),
                "updated": _res.get("updated"),
                "skipped": _res.get("skipped"),
                "processed": _res.get("processed"),
                "orphans": _res.get("orphans"),
                "preview_actions": (_res.get("preview_actions") or [])[:50],
                "errors":  (_res.get("errors") or [])[:20],
                "log":     (_res.get("log") or [])[:50],
            }
    except Exception:
        pass
    payload["jira_sync_result"] = jira_sync_result_block

    # ---- Jira project properties (per-project custom fields) --------------
    jira_project_block = {}
    try:
        import json as _json_mod
        if project is not None:
            cp = project.getProjectProperties().getCustomProperties()
            if cp is not None:
                # New container format: "jira2project" = JSON string
                j2p_str = cp.get("jira2project")
                j2p = {}
                if j2p_str:
                    try:
                        j2p = _json_mod.loads(str(j2p_str))
                    except Exception:
                        pass
                filter_val = j2p.get("filter")
                filter_type = j2p.get("filter_type")
                jira_project_block = {
                    "filter_set": bool(filter_val),
                    "filter": filter_val,
                    "filter_type": filter_type,
                }

                def _redact_j2p_value(key: str, value):
                    key_lower = str(key).lower()
                    if any(token in key_lower for token in ("password", "token", "secret", "credential", "keyfile", "keepass")):
                        return "<redacted>"
                    if isinstance(value, dict):
                        return {str(k): _redact_j2p_value(str(k), v) for k, v in value.items()}
                    if isinstance(value, list):
                        return [_redact_j2p_value(key, item) for item in value]
                    return value

                # Field checkboxes: read from jira2project.fields
                field_checkboxes = {}
                field_names = [
                    "jira_project_name", "jira_description",
                    "jira_status", "jira_status_percent", "jira_resolution", "jira_resolution_date", "jira_security_level",
                    "jira_assignee", "jira_assignee_display_name", "jira_reporter", "jira_reporter_display_name",
                    "jira_priority", "jira_due_date", "jira_created_date", "jira_updated_date",
                    "jira_components", "jira_fix_versions", "jira_affects_versions",
                    "jira_fix_version_description", "jira_fix_version_released", "jira_fix_version_start_date", "jira_fix_version_release_date",
                    "jira_labels", "jira_environment", "jira_votes", "jira_comments",
                    "jira_time_spent", "jira_remaining_estimate", "jira_original_estimate", "jira_time_spent_seconds", "jira_worklog_entries",
                    "jira_parent_key", "jira_epic_link", "jira_parent_link", "jira_subtask_parent", "jira_issue_links",
                ]
                fields = j2p.get("fields") or {}
                for field_name in field_names:
                    field_checkboxes[field_name] = bool(fields.get(field_name, False))

                jira_project_block["field_checkboxes"] = field_checkboxes
                jira_project_block["advanced"] = _redact_j2p_value("advanced", j2p.get("advanced") or {})
    except Exception:
        pass
    payload["jira_project_props"] = jira_project_block

    # ---- Jira Project -> Jira properties (per-project export config) ------
    project_to_jira_block = {}
    try:
        import json as _json_mod
        if project is not None:
            cp = project.getProjectProperties().getCustomProperties()
            if cp is not None:
                raw = cp.get("project2jira")
                data = {}
                if raw:
                    try:
                        data = _json_mod.loads(str(raw))
                    except Exception:
                        data = {}

                def _redact_value(key: str, value):
                    key_lower = str(key).lower()
                    if any(token in key_lower for token in ("password", "token", "secret", "credential", "keyfile", "keepass")):
                        return "<redacted>"
                    if isinstance(value, dict):
                        return {str(k): _redact_value(str(k), v) for k, v in value.items()}
                    if isinstance(value, list):
                        return [_redact_value(key, item) for item in value]
                    return value

                project_to_jira_block = {
                    str(k): _redact_value(str(k), v)
                    for k, v in (data or {}).items()
                }
    except Exception:
        pass
    payload["jira_project_to_jira_props"] = project_to_jira_block

    # ---- Jira push result (last run_push_to_jira() call) -------------------
    jira_push_result_block = {}
    try:
        from integrations.jira_sync import get_last_push_result as _jpr  # type: ignore
        _pr = _jpr()
        if _pr:
            jira_push_result_block = {
                "dry_run":     _pr.get("dry_run"),
                "created":     _pr.get("created"),
                "updated":     _pr.get("updated"),
                "transitioned": _pr.get("transitioned"),
                "skipped":     _pr.get("skipped"),
                "preview_actions": (_pr.get("preview_actions") or [])[:50],
                "errors":      (_pr.get("errors") or [])[:20],
                "log":         (_pr.get("log") or [])[:50],
            }
    except Exception:
        pass
    payload["jira_push_result"] = jira_push_result_block

    # ---- Jira push metadata from sidecar (per-task push timestamps) --------
    jira_push_meta_block = {}
    try:
        import json as _json_push
        if project is not None and "sidecar_path" in dir():
            pass  # sidecar_path not available here; use file path from context
        # Read from sidecar via app state if available
        _sidecar_fn = None
        try:
            from app_debug import _current_sidecar_path  # type: ignore
            _sidecar_fn = _current_sidecar_path
        except Exception:
            pass
        if _sidecar_fn is None:
            # Fallback: try to resolve from project file path stored in payload
            _proj_path = payload.get("project_file", "")
            if _proj_path:
                _sidecar_fn = str(_proj_path) + ".custom-props.json"
        if _sidecar_fn:
            import os as _os_push
            if _os_push.path.exists(_sidecar_fn):
                with open(_sidecar_fn, "r", encoding="utf-8") as _f_push:
                    _sc_data = _json_push.load(_f_push)
                _push_meta = _sc_data.get("jira_push_meta") or {}
                jira_push_meta_block = {
                    "last_run_at":         _push_meta.get("last_run_at"),
                    "last_successful_push": _push_meta.get("last_successful_push"),
                    "last_result": {
                        k: v for k, v in (_push_meta.get("last_result") or {}).items()
                        if k != "errors"
                    },
                    "audit_session_count": len(_push_meta.get("audit_sessions") or []),
                    "task_p2j_count": len(_sc_data.get("task_p2j") or {}),
                }
    except Exception:
        pass
    payload["jira_push_meta"] = jira_push_meta_block

    # ---- Version control integration status --------------------------------
    # Non-sensitive fields only: repo type, root presence, branch, entry flag.
    # No credentials, repo URL, or commit messages are included.
    vcs_block = {}
    try:
        from integrations.version_control_integration import get_config_summary as _vcs_summary  # type: ignore
        vcs_block = _vcs_summary()
    except Exception:
        pass
    payload["vcs_integration"] = vcs_block

    # ---- Long-running operation timing log ---------------------------------
    # Populated by progress_worker.record_timing() during the current session.
    # Entries are most recent last; at most 50 entries are kept.
    # elapsed_seconds does NOT include time waiting in the progress dialog
    # (e.g. the user staring at the dialog before clicking Cancel).
    timing_block: list = []
    try:
        from progress_worker import get_timing_log as _gtl  # type: ignore
        timing_block = _gtl()
    except Exception:
        pass
    payload["long_running_timings"] = timing_block

    # ---- Project calendars (all calendars, full detail) --------------------
    # Covers: name, UID, parent, default flag, per-weekday types, all
    # exceptions (date / name / working flag), and which holidays-module
    # calendars are installed vs. still available to install.
    project_calendars_block: dict = {
        "installed_calendars": [],
        "default_calendar_name": None,
        "holidays_module_available": False,
        "installed_holiday_names": [],
        "available_holiday_names": [],
        "ics_import_note": (
            "Each calendar's exceptions list is the ICS-level source of truth. "
            "Use 'Project Information > Calendars > Import ICS\u2026' to import "
            "from external .ics files, or 'Add Holidays\u2026' to install "
            "pre-built national/state calendars."
        ),
    }
    try:
        import java.time as _jt_cal  # type: ignore

        _dow_names = [str(d).title() for d in _jt_cal.DayOfWeek.values()]
        _dows      = list(_jt_cal.DayOfWeek.values())

        default_cal = project.getDefaultCalendar()
        if default_cal is not None:
            project_calendars_block["default_calendar_name"] = _s(default_cal.getName())

        all_cal_names: list[str] = []
        cal_list = []
        for cal in project.getCalendars():
            cal_name = str(cal.getName() or "")
            all_cal_names.append(cal_name)

            # Per-weekday types
            day_types: dict = {}
            try:
                for dow, dow_name in zip(_dows, _dow_names):
                    try:
                        dt = str(cal.getCalendarDayType(dow))
                        day_types[dow_name] = dt
                    except Exception:
                        day_types[dow_name] = "UNKNOWN"
            except Exception:
                pass

            # Calendar exceptions (holidays / shutdowns)
            exceptions_list = []
            try:
                for ex in cal.getCalendarExceptions():
                    try:
                        from_d = str(ex.getFromDate())[:10] if ex.getFromDate() else None
                        to_d   = str(ex.getToDate())[:10]   if ex.getToDate()   else None
                        exceptions_list.append({
                            "name":    str(ex.getName()) if ex.getName() else None,
                            "from":    from_d,
                            "to":      to_d,
                            "working": bool(ex.getWorking()),
                        })
                    except Exception:
                        pass
            except Exception:
                pass

            # Parent calendar info
            parent_name = None
            parent_uid  = None
            try:
                p = cal.getParent()
                if p is not None:
                    parent_name = str(p.getName()) if p.getName() else None
                    parent_uid  = _s(p.getUniqueID())
            except Exception:
                pass

            is_default = False
            try:
                is_default = bool(cal.getDefault())
            except Exception:
                if default_cal is not None:
                    try:
                        is_default = (
                            int(str(cal.getUniqueID())) ==
                            int(str(default_cal.getUniqueID()))
                        )
                    except Exception:
                        pass

            # Resource usage: which resources use this calendar
            assigned_resources: list[str] = []
            try:
                cal_uid_int = int(str(cal.getUniqueID()))
                for _r in project.getResources():
                    if _r.getName() is None:
                        continue
                    try:
                        _rc = _r.getCalendar()
                        if _rc is not None and int(str(_rc.getUniqueID())) == cal_uid_int:
                            assigned_resources.append(str(_r.getName()))
                    except Exception:
                        pass
            except Exception:
                pass

            cal_list.append({
                "name":               cal_name,
                "uid":                _s(cal.getUniqueID()),
                "is_default":         is_default,
                "parent_name":        parent_name,
                "parent_uid":         parent_uid,
                "exception_count":    len(exceptions_list),
                "exceptions":         exceptions_list,
                "day_types":          day_types,
                "assigned_resources": assigned_resources,
            })

        project_calendars_block["installed_calendars"] = cal_list

        # Which holidays-module calendars are installed vs. available
        try:
            from dialogs import NewProjectCalendarsDialog as _NPCD  # type: ignore
            _all_holiday_names = (
                list(_NPCD._GERMAN_STATES) + list(_NPCD._OTHER_COUNTRIES)
            )
            project_calendars_block["holidays_module_available"] = True
        except Exception:
            _all_holiday_names = [
                "Baden-Württemberg", "Bayern", "Berlin", "Brandenburg", "Bremen",
                "Hamburg", "Hessen", "Mecklenburg-Vorpommern", "Niedersachsen",
                "Rheinland-Pfalz", "Saarland", "Sachsen", "Sachsen-Anhalt",
                "Schleswig-Holstein", "Thüringen",
                "France", "India", "Romania", "China", "Japan",
            ]

        installed_holiday_names = [
            n for n in _all_holiday_names if n in all_cal_names
        ]
        available_holiday_names = [
            n for n in _all_holiday_names if n not in all_cal_names
        ]
        project_calendars_block["installed_holiday_names"]  = installed_holiday_names
        project_calendars_block["available_holiday_names"]  = available_holiday_names

    except Exception as _ce2:
        project_calendars_block["error"] = str(_ce2)

    payload["project_calendars"] = project_calendars_block

    # ---- Team Planner filter diagnostics -----------------------------------
    # Shows which resources pass / fail the TeamPlannerCanvas res_list filter
    # so we can diagnose "new resource not visible in Team Planner" issues.
    tp_diagnostics = []
    try:
        for r in project.getResources():
            try:
                rname = _s(r.getName())
                raw_uid = r.getUniqueID()
                try:
                    uid_int = int(str(raw_uid)) if raw_uid is not None else None
                except Exception:
                    uid_int = None
                included = rname is not None and uid_int is not None
                tp_diagnostics.append({
                    "name":     rname,
                    "raw_uid":  _s(raw_uid),
                    "uid_int":  uid_int,
                    "included_in_team_planner": included,
                    "exclusion_reason": (
                        "null name" if rname is None
                        else "null/unparseable uid" if uid_int is None
                        else None
                    ),
                })
            except Exception as exc:
                tp_diagnostics.append({"error": str(exc)})
    except Exception as exc:
        tp_diagnostics = [{"error": str(exc)}]
    payload["team_planner_filter_diagnostics"] = tp_diagnostics

    # ---- Resource Usage Histogram ------------------------------------------
    # Dump the histogram data so capacity and allocation issues can be diagnosed.
    histogram_block: dict = {
        "visible": (ui_state or {}).get("histogram_visible", False),
        "height_px": (ui_state or {}).get("histogram_height_px", 120),
        "data": [],
    }
    try:
        from views.resource_usage_histogram_view import compute_histogram_data  # type: ignore
        from PyQt5.QtCore import QDate  # type: ignore
        _tp_start_str = (ui_state or {}).get("tp_project_start")
        _tp_days      = (ui_state or {}).get("tp_total_days", 0)
        _non_working  = set((ui_state or {}).get("tp_non_working_dates", []))
        if project is not None and _tp_start_str and _tp_days > 0:
            _start = QDate.fromString(_tp_start_str, "yyyy-MM-dd")
            _end   = _start.addDays(_tp_days)
            _hdata = compute_histogram_data(project, _start, _end, _non_working)
            # Only include days that have actual capacity or allocation to keep
            # the dump readable; skip pure-zero weekend/holiday rows.
            histogram_block["data"] = [
                {
                    "date":            d["date"].toString("yyyy-MM-dd"),
                    "total_hours":     round(d["total_hours"], 2),
                    "capacity_hours":  round(d["capacity_hours"], 2),
                    "utilisation_pct": round(d["utilisation_pct"], 1),
                }
                for d in _hdata
                if d["capacity_hours"] > 0 or d["total_hours"] > 0
            ]
            histogram_block["over_capacity_days"] = sum(
                1 for d in _hdata if d["utilisation_pct"] > 100.0
            )
    except Exception as _he:
        histogram_block["error"] = str(_he)
    payload["resource_usage_histogram"] = histogram_block

    # ---- CPM settings & summary --------------------------------------------
    cpm_settings_block: dict = {}
    cpm_summary_block: dict = {}
    try:
        _cpm_cfg = (ui_state or {}).get("cpm_settings", {})
        _fd = (ui_state or {}).get("float_data", {})

        # Detect whether Phase 5 calendar-aware mode was active for any task
        _cal_aware_active = any(
            v.get("total_float_wh") is not None for v in _fd.values()
        )
        # Project-level wdh: median of per-task wdh values when available
        _wdh_list = [
            float(v.get("work_day_hours") or 8.0)
            for v in _fd.values()
            if v.get("work_day_hours") is not None
        ]
        _project_wdh = (
            sorted(_wdh_list)[len(_wdh_list) // 2]
            if _wdh_list else 8.0
        )

        cpm_settings_block = {
            "critical_slack_days":  _cpm_cfg.get("critical_slack_days", 0),
            "dep_types":            _cpm_cfg.get("dep_types", "all"),
            # Phase 5
            "calendar_aware_active": _cal_aware_active,
            "project_wdh":           round(_project_wdh, 2),
        }

        _critical_count = sum(1 for v in _fd.values() if v.get("critical"))
        _near_critical  = 0
        _slack = _cpm_cfg.get("critical_slack_days", 0)
        if _slack > 0:
            # Use calendar-aware working hours when available; fall back to
            # wall-clock hours / project_wdh for the threshold comparison.
            for v in _fd.values():
                if v.get("critical"):
                    continue
                _vwdh = float(v.get("work_day_hours") or _project_wdh)
                _tf_wh = v.get("total_float_wh")
                if _tf_wh is not None:
                    _tf_days = _tf_wh / max(_vwdh, 0.25)
                elif v.get("total_float") is not None:
                    _tf_days = v["total_float"].total_seconds() / 3600 / max(_vwdh, 0.25)
                else:
                    continue
                if _tf_days <= _slack:
                    _near_critical += 1

        # Project duration: span from min ES to max EF using calendar-aware
        # working hours when possible.
        _all_es = [v.get("es") for v in _fd.values() if v.get("es")]
        _all_ef = [v.get("ef") for v in _fd.values() if v.get("ef")]
        _project_duration_d = None
        if _all_es and _all_ef:
            _span_h = (max(_all_ef) - min(_all_es)).total_seconds() / 3600
            _project_duration_d = round(_span_h / max(_project_wdh, 0.25), 1)

        cpm_summary_block = {
            "total_leaf_tasks":     len(_fd),
            "critical_count":       _critical_count,
            "near_critical_count":  _near_critical,
            # Phase 5
            "project_duration_d":   _project_duration_d,
            "calendar_aware_active": _cal_aware_active,
        }
    except Exception as _ce:
        cpm_settings_block["error"] = str(_ce)
    payload["cpm_settings"]  = cpm_settings_block
    payload["cpm_summary"]   = cpm_summary_block

    # ---- System locale / currency diagnostics ------------------------------
    locale_block: dict = {}
    try:
        import locale as _locale
        saved_lc = _locale.getlocale(_locale.LC_MONETARY)
        try:
            _locale.setlocale(_locale.LC_MONETARY, "")
            conv = _locale.localeconv()
            lc_name = _locale.getlocale(_locale.LC_MONETARY)
        finally:
            try:
                _locale.setlocale(_locale.LC_MONETARY, saved_lc)
            except Exception:
                pass
        locale_block["lc_monetary_name"]   = str(lc_name)
        locale_block["currency_symbol"]    = conv.get("currency_symbol")
        locale_block["int_curr_symbol"]    = (conv.get("int_curr_symbol") or "").strip() or None
        locale_block["frac_digits"]        = conv.get("frac_digits")
        locale_block["p_cs_precedes"]      = conv.get("p_cs_precedes")
        locale_block["p_sep_by_space"]     = conv.get("p_sep_by_space")
        locale_block["thousands_sep"]      = conv.get("thousands_sep")
        locale_block["decimal_point"]      = conv.get("decimal_point")
        # Also record the LC_CTYPE locale for completeness
        try:
            locale_block["lc_ctype_name"] = str(_locale.getlocale(_locale.LC_CTYPE))
        except Exception:
            pass
    except Exception as exc:
        locale_block["error"] = str(exc)
    payload["system_locale"] = locale_block

    # ---- Assemble & write --------------------------------------------------
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    # In a PyInstaller bundle __file__ lives inside _internal/; use the
    # directory that contains the executable instead so the dump folder is
    # placed next to the .exe rather than buried in the bundle internals.
    if getattr(sys, "frozen", False):
        _base = os.path.dirname(os.path.abspath(sys.executable))
    else:
        _base = os.path.dirname(os.path.abspath(__file__))
    dump_dir = os.path.join(_base, "dump")
    os.makedirs(dump_dir, exist_ok=True)
    out_path = os.path.join(dump_dir, f"debug_project_dump_{ts}.json")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False, cls=_JsonEncoder)

    return out_path
