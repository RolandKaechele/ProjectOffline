# gantt_view.py - Gantt chart for Project Offline
#
# Features:
#   - Two-row calendar header (month band / day numbers)
#   - Weekend column shading
#   - Task bars with progress overlay, baseline strip, critical path red
#   - Milestone diamond markers
#   - Predecessor dependency arrows (Finish-to-Start elbow lines)
#   - Yellow âš  warning icon for tasks with % complete > 100
#   - Zoom in / zoom out (Ctrl++ / Ctrl+- or toolbar buttons)

from PyQt5.QtWidgets import (  # type: ignore
    QWidget, QScrollArea, QSizePolicy, QVBoxLayout, QFrame, QHBoxLayout,
    QToolButton, QMenu, QAction, QDialog, QLabel, QDateEdit, QDialogButtonBox,
    QVBoxLayout as _QVBoxLayout, QPushButton,
)
from PyQt5.QtGui import (                                                                   # type: ignore
    QPainter, QColor, QFont, QPen, QPolygon, QBrush
)
from PyQt5.QtCore import Qt, QRect, QDate, QSize, QPoint, QTime, pyqtSignal                                   # type: ignore
from hour_mode import (  # type: ignore
    HOUR_MODE_THRESHOLD, HourModeHeader,
    read_work_hours, working_day_count, date_to_working_day_idx, datetime_to_hourly_x,
    WORK_HOUR_START, WORK_HOUR_END, WORK_DAY_HOURS,
)

ROW_HEIGHT       = 36
LABEL_WIDTH      = 0    # task names are shown in the task_view splitter pane
DAY_WIDTH_DEF    = 22

# Views that support Split / Merge task context menu and ribbon buttons.
# Use the TAB_* constants from app_tabs.py.
# Imported lazily to avoid circular imports at module level.
def _split_task_views():
    from app_tabs import TAB_GANTT, TAB_TEAM_PLANNER  # type: ignore
    return (TAB_GANTT, TAB_TEAM_PLANNER)


def _load_task_jira_data(view, task) -> dict:
    """Return the sidecar Jira entry for *task*, or {} if not available."""
    try:
        sidecar_path = getattr(view, '_get_sidecar_path', lambda: "")() 
        if not sidecar_path:
            return {}
        from integrations.jira_sync import load_sidecar_task_data  # type: ignore
        all_jira = load_sidecar_task_data(sidecar_path)
        uid_str = str(task.getUniqueID())
        return all_jira.get(uid_str, {})
    except Exception:
        return {}

SPLIT_GAP_DAYS = 1   # default gap inserted between segments on split
DAY_WIDTH_MIN    = 4
DAY_WIDTH_MAX    = 80
HEADER_MONTH_H   = 22    # top row: month names
HEADER_WEEK_H    = 20    # bottom row: day numbers
HEADER_HEIGHT    = HEADER_MONTH_H + HEADER_WEEK_H
NAV_BAR_HEIGHT   = 24    # navigation buttons bar above the calendar header
BASELINE_THICK   = 3


def _to_qdate(java_date):
    if java_date is None:
        return None
    try:
        s = str(java_date)[:10]
        y, m, d = s.split("-")
        return QDate(int(y), int(m), int(d))
    except Exception:
        return None


def _add_working_days(start: QDate, working_days: float) -> QDate:
    """Advance start by working_days business days, skipping Sat/Sun.
    A "1 day" task starts and finishes on the same day (0 advances past start).
    A "2 day" task finishes one working day after start, etc.
    Used only as a fallback when MPXJ finish date is unavailable.
    """
    n = max(0, int(round(working_days)) - 1)
    d = start
    count = 0
    while count < n:
        d = d.addDays(1)
        if d.dayOfWeek() not in (6, 7):   # 6=Sat, 7=Sun
            count += 1
    return d


def _task_vacation_blocks(task) -> list:
    """Return a list of (from_qd, to_qd) QDate pairs for all non-working
    calendar exceptions on every resource assigned to *task*.
    Used by split_task to avoid placing seg2_start inside a vacation.
    """
    blocks = []
    try:
        for asgn in (task.getResourceAssignments() or []):
            try:
                res = asgn.getResource()
                if res is None:
                    continue
                cal = res.getCalendar()
                if cal is None:
                    continue
                for ex in cal.getCalendarExceptions():
                    try:
                        if bool(ex.getWorking()):
                            continue
                    except Exception:
                        pass
                    from_str = str(ex.getFromDate() or "")[:10]
                    to_str   = str(ex.getToDate()   or "")[:10]
                    if not from_str:
                        continue
                    from_qd = QDate.fromString(from_str, "yyyy-MM-dd")
                    to_qd   = QDate.fromString(to_str, "yyyy-MM-dd") if to_str else from_qd
                    if from_qd.isValid() and to_qd.isValid():
                        blocks.append((from_qd, to_qd))
            except Exception:
                pass
    except Exception:
        pass
    return blocks


def _snap_to_workday(date: QDate, non_working_dates: set = None) -> QDate:
    """If date falls on a non-working day (Sat, Sun, or a public holiday),
    advance day by day until a working day is found.
    non_working_dates: set of ISO date strings (YYYY-MM-DD) for public holidays.
    """
    nwd = non_working_dates or set()
    d = date
    while True:
        dow = d.dayOfWeek()
        iso = d.toString(Qt.ISODate)
        if dow not in (6, 7) and iso not in nwd:
            break
        d = d.addDays(1)
    return d


def _compute_finish_date(task):
    """Return QDate for task end.
    Prefers MPXJ's calendar-aware getFinish() (respects weekends + project
    calendar holidays).  Falls back to a weekend-skipping manual calculation
    only when getFinish() is unavailable.
    """
    # Primary: use MPXJ's pre-computed finish (calendar + holidays aware)
    fin = _to_qdate(task.getFinish())
    if fin:
        return fin
    # Fallback: skip weekends manually
    start = _to_qdate(task.getStart())
    if start is None:
        return None
    try:
        dur = task.getDuration()
        if dur is not None:
            dur_val = float(str(dur.getDuration()))
            unit_str = str(dur.getUnits()).upper() if dur.getUnits() is not None else "DAYS"
            if "HOUR" in unit_str:
                dur_val /= 8.0
            elif "WEEK" in unit_str:
                dur_val *= 5.0
            elif "MONTH" in unit_str:
                dur_val *= 20.0
            return _add_working_days(start, max(1, dur_val))
    except Exception:
        pass
    return None


def _normalize_schedule(all_tasks):
    """Forward-pass: push FS successor starts to be >= pred computed finish + lag.
    Modifies the Java task objects in-memory so bars and arrows stay consistent.
    """
    try:
        changed = True
        passes = 0
        max_passes = len(all_tasks) + 2
        while changed and passes < max_passes:
            changed = False
            passes += 1
            for t in all_tasks:
                if t.getName() is None:
                    continue
                try:
                    preds = t.getPredecessors()
                except Exception:
                    continue
                if not preds:
                    continue
                t_start_qd = _to_qdate(t.getStart())
                if t_start_qd is None:
                    continue
                for rel in preds:
                    try:
                        rel_type = str(rel.getType())
                    except Exception:
                        rel_type = "FINISH_START"
                    if rel_type not in ("FS", "FINISH_START"):
                        continue
                    pred_task = rel.getPredecessorTask()
                    if pred_task is None:
                        continue
                    pred_fin = _compute_finish_date(pred_task)
                    if pred_fin is None:
                        continue
                    lag_days = 0
                    try:
                        lag = rel.getLag()
                        if lag is not None:
                            lag_v = float(str(lag.getDuration()))
                            lu = str(lag.getUnits()).upper() if lag.getUnits() is not None else "DAYS"
                            if "HOUR" in lu:
                                lag_v /= 8.0
                            elif "WEEK" in lu:
                                lag_v *= 5.0
                            elif "MONTH" in lu:
                                lag_v *= 20.0
                            lag_days = int(round(lag_v))
                    except Exception:
                        lag_days = 0
                    earliest = pred_fin.addDays(lag_days)
                    if t_start_qd < earliest:
                        delta = t_start_qd.daysTo(earliest)
                        t_start_java = t.getStart()
                        t_finish_java = t.getFinish()
                        if t_start_java is not None:
                            t.setStart(t_start_java.plusDays(delta))
                        if t_finish_java is not None:
                            t.setFinish(t_finish_java.plusDays(delta))
                        t_start_qd = earliest
                        changed = True
    except Exception:
        pass


def _get_visible_tasks(all_tasks, collapsed_ids):
    """Return the subset of tasks that should be displayed given the collapsed
    summary set.  Children of a collapsed summary are omitted.
    Works by tracking the ancestor summary at each outline level.
    """
    if not collapsed_ids:
        return list(all_tasks)
    visible = []
    ancestor_at_level = {}   # outline_level (int) -> task_id (str)
    for task in all_tasks:
        level = 1
        try:
            ol = task.getOutlineLevel()
            if ol is not None:
                level = int(str(ol))
        except Exception:
            pass
        # Drop ancestor entries at the same level or deeper (we've moved to a sibling/uncle)
        for k in [k for k in list(ancestor_at_level.keys()) if k >= level]:
            del ancestor_at_level[k]
        # Skip this task if any ancestor is collapsed
        if any(tid in collapsed_ids for tid in ancestor_at_level.values()):
            continue
        visible.append(task)
        # Register this task as the current ancestor if it is a summary
        try:
            if task.getSummary():
                ancestor_at_level[level] = str(task.getID())
        except Exception:
            pass
    return visible


def _date_to_col(project_start: QDate, date: QDate, show_sundays: bool) -> int:
    """Visible column offset of *date* from *project_start*.
    When *show_sundays* is False, Sunday columns are collapsed out of the
    timeline so every visible column represents one Mon-Sat day.
    """
    n = project_start.daysTo(date)
    if show_sundays or n <= 0:
        return n
    count = 0
    for i in range(n):
        if project_start.addDays(i).dayOfWeek() != 7:   # 7 = Sunday
            count += 1
    return count


def _col_to_date(project_start: QDate, col: int, show_sundays: bool) -> QDate:
    """Inverse of _date_to_col: return the QDate for a given visible column index."""
    if show_sundays or col <= 0:
        return project_start.addDays(col)
    count = 0
    d = project_start
    while count < col:
        d = d.addDays(1)
        if d.dayOfWeek() != 7:  # skip Sundays
            count += 1
    return d


def _get_non_working_dates(project, project_start: QDate, total_calendar_days: int) -> set:
    """Return a set of ISO date strings (YYYY-MM-DD) for non-working weekdays
    as defined by the project's default calendar (public holidays, etc.).
    Saturdays and Sundays are excluded — handled separately by day-of-week.
    """
    non_working: set = set()
    if project is None or project_start is None:
        return non_working
    try:
        import java.time as _jtime   # type: ignore  (JPype runtime import)
        cal = project.getDefaultCalendar()
        if cal is None:
            return non_working
        for i in range(total_calendar_days):
            qd  = project_start.addDays(i)
            dow = qd.dayOfWeek()
            if dow in (6, 7):          # Sat/Sun handled by day-of-week
                continue
            ld = _jtime.LocalDate.of(qd.year(), qd.month(), qd.day())
            if not cal.isWorkingDate(ld):
                non_working.add(qd.toString(Qt.ISODate))
    except Exception:
        pass
    return non_working


def _read_critical_ids(all_tasks) -> set:
    """Read the critical-path flag directly from MPXJ task objects (getCritical()).
    This matches whatever MS Project stored in the file.  Returns a set of int
    task IDs, or an empty set if the flag is unavailable / not set on any task.
    """
    critical: set = set()
    any_flag_present = False
    for t in all_tasks:
        try:
            flag = t.getCritical()
            if flag is None:
                continue
            any_flag_present = True
            if bool(flag):
                tid = int(str(t.getID()))
                critical.add(tid)
        except Exception:
            pass
    return critical if any_flag_present else set()


# ---------------------------------------------------------------------------
# CPM helpers
# ---------------------------------------------------------------------------

def _lag_to_timedelta(java_duration):
    """Convert an MPXJ Duration (lag/lead) to a Python timedelta.

    MPXJ Duration objects carry a numeric magnitude and a time unit.
    We convert everything to minutes then to timedelta.
    Positive = lag (delay), negative = lead (overlap).
    Returns timedelta(0) for None or any error.
    """
    from datetime import timedelta
    if java_duration is None:
        return timedelta(0)
    try:
        minutes = float(str(java_duration.getDuration()))
        unit = str(java_duration.getUnits()).upper()
        # Map MPXJ TimeUnit names to minute equivalents
        _UNIT_MIN = {
            "MINUTES": 1,
            "HOURS": 60,
            "DAYS": 480,       # 8-hour working day
            "WEEKS": 2400,     # 5 × 8h
            "MONTHS": 9600,    # 20 × 8h (approx)
            "ELAPSED_MINUTES": 1,
            "ELAPSED_HOURS": 60,
            "ELAPSED_DAYS": 1440,    # calendar day = 24h
            "ELAPSED_WEEKS": 10080,  # 7 × 24h
        }
        factor = _UNIT_MIN.get(unit, 480)  # default: treat unknown as days
        return timedelta(minutes=minutes * factor)
    except Exception:
        return timedelta(0)


def _lag_to_working_hours(java_duration, wdh_per_day: float = 8.0) -> float:
    """Convert an MPXJ Duration lag to working hours using the project's wdh.

    Working-day units (DAYS, WEEKS, MONTHS) are scaled by *wdh_per_day*.
    Elapsed units (ELAPSED_*) use calendar hours regardless of wdh.
    Returns 0.0 for None or any error.
    """
    if java_duration is None:
        return 0.0
    try:
        mag  = float(str(java_duration.getDuration()))
        unit = str(java_duration.getUnits()).upper()
        _UNIT_WH = {
            "MINUTES":        1.0 / 60.0,
            "HOURS":          1.0,
            "DAYS":           wdh_per_day,
            "WEEKS":          wdh_per_day * 5.0,
            "MONTHS":         wdh_per_day * 20.0,
            "ELAPSED_MINUTES": 1.0 / 60.0,
            "ELAPSED_HOURS":   1.0,
            "ELAPSED_DAYS":    24.0,
            "ELAPSED_WEEKS":   24.0 * 7.0,
        }
        factor = _UNIT_WH.get(unit, wdh_per_day)
        return mag * factor
    except Exception:
        return 0.0


# ---------------------------------------------------------------------------
# Phase 5 — Calendar-aware CPM helpers
# ---------------------------------------------------------------------------

def _get_task_calendar(task, project):
    """Return the effective MPXJ calendar for a task.

    Priority: task.getCalendar() → first resource assignment's calendar
    → project default calendar.  Returns None on total failure.
    """
    try:
        cal = task.getCalendar()
        if cal is not None:
            return cal
    except Exception:
        pass
    try:
        for asgn in (task.getResourceAssignments() or []):
            try:
                res = asgn.getResource()
                if res is None:
                    continue
                cal = res.getCalendar()
                if cal is not None:
                    return cal
            except Exception:
                continue
    except Exception:
        pass
    try:
        if project is not None:
            return project.getDefaultCalendar()
    except Exception:
        pass
    return None


def _py_dt_to_java_ldt(dt):
    """Convert a Python datetime to a Java LocalDateTime via JPype."""
    import java.time  # type: ignore
    return java.time.LocalDateTime.of(
        int(dt.year), int(dt.month), int(dt.day),
        int(dt.hour), int(dt.minute), int(dt.second),
    )


def _working_hours_between(calendar, start_dt, end_dt) -> float:
    """Return the number of working hours between two Python datetimes.

    Uses the MPXJ calendar's ``getWork()`` method.  Falls back to
    wall-clock hours on any error so Phase 1–4 behaviour is preserved.
    """
    try:
        import net.sf.mpxj as _mpxj  # type: ignore
        j_start = _py_dt_to_java_ldt(start_dt)
        j_end   = _py_dt_to_java_ldt(end_dt)
        dur = calendar.getWork(j_start, j_end, _mpxj.TimeUnit.HOURS)
        return max(float(str(dur.getDuration())), 0.0)
    except Exception:
        return max((end_dt - start_dt).total_seconds() / 3600.0, 0.0)


def _calendar_add_working_hours(calendar, start_dt, hours):
    """Advance *start_dt* by *hours* of working time using the MPXJ calendar.

    Negative *hours* moves backward (used in the backward CPM pass).
    Falls back to a simple timedelta on any error.
    """
    from datetime import timedelta
    try:
        import net.sf.mpxj as _mpxj  # type: ignore
        j_start = _py_dt_to_java_ldt(start_dt)
        dur     = _mpxj.Duration.getInstance(float(hours), _mpxj.TimeUnit.HOURS)
        j_result = calendar.getDate(j_start, dur)
        from datetime import datetime
        return datetime.fromisoformat(str(j_result)[:16])
    except Exception:
        return start_dt + timedelta(hours=hours)


def _calendar_wdh(calendar) -> float:
    """Return working hours per day for an MPXJ calendar.

    Reads the CalendarHours for Monday–Friday and returns the total
    working hours for the first working weekday found.
    Falls back to 8.0 on any error.
    """
    try:
        import java.time  # type: ignore
        for dow in (
            java.time.DayOfWeek.MONDAY,
            java.time.DayOfWeek.TUESDAY,
            java.time.DayOfWeek.WEDNESDAY,
            java.time.DayOfWeek.THURSDAY,
            java.time.DayOfWeek.FRIDAY,
        ):
            hours = calendar.getCalendarHours(dow)
            if not hours:
                continue
            total = 0.0
            for rng in hours:
                s, e = rng.getStart(), rng.getEnd()
                if s is not None and e is not None:
                    sh = int(s.getHour()) + int(s.getMinute()) / 60.0
                    eh = int(e.getHour()) + int(e.getMinute()) / 60.0
                    if eh > sh:
                        total += eh - sh
            if total > 0:
                return total
    except Exception:
        pass
    return 8.0


def _compute_critical_ids(
    all_tasks,
    project=None,
    zero_float_critical: bool = False,   # KEEP — existing callers pass this
    dep_types: str = "all",              # "all" (FS+SS+FF+SF) or "fs_only"
    critical_slack_days: int | None = None,   # numeric threshold, wins over bool
    return_float_data: bool = False,     # NEW — opt-in to (set, dict) return
):
    """CPM forward+backward pass with all dependency types and free float.

    Summary tasks are excluded from the CPM calculation because their
    start/finish span their children and give incorrect float values.
    Instead, a summary task is marked critical when ANY of its leaf
    descendants is critical (matching MS Project behaviour).

    ``project`` (optional): the MPXJ ProjectFile.  When supplied its
    stored finish date is used as the CPM deadline so that moving one
    task cannot cause independent parallel tasks to gain false zero-float.

    When ``return_float_data=True`` returns a ``(set, dict)`` tuple where
    the dict maps task ID → {es, ef, ls, lf, total_float, free_float, critical}.
    All existing callers that do not pass ``return_float_data`` receive only the
    ``set`` and are unaffected.
    """
    from datetime import datetime, timedelta

    # Resolve the critical threshold in timedelta.
    # critical_slack_days wins when supplied; legacy bool is the fallback.
    # MS Project default = 0 days (Total Float ≤ 0 → critical).
    _threshold_days = (
        critical_slack_days if critical_slack_days is not None
        else (1 if zero_float_critical else 0)
    )
    _THRESHOLD = timedelta(days=_threshold_days)

    # Supported dependency type tokens
    _SUPPORTED = {
        "FS", "FINISH_START", "SS", "START_START",
        "FF", "FINISH_FINISH", "SF", "START_FINISH",
    }
    _FS_ONLY = {"FS", "FINISH_START"}

    def _to_dt(java_date):
        if java_date is None:
            return None
        try:
            return datetime.fromisoformat(str(java_date)[:16])
        except Exception:
            try:
                return datetime.fromisoformat(str(java_date)[:10])
            except Exception:
                return None

    # Separate summary tasks from leaf tasks; build parent → children map
    summary_ids:  set  = set()
    children_map: dict = {}   # int parent_tid -> [int child_tid, ...]

    for t in all_tasks:
        try:
            tid = int(str(t.getID()))
            kids = t.getChildTasks()
            if kids:
                summary_ids.add(tid)
                children_map[tid] = [int(str(k.getID())) for k in kids]
        except Exception:
            pass

    early_start:  dict = {}   # int tid -> datetime  (stored, leaf tasks only)
    early_finish: dict = {}
    completed_ids: set = set()  # tasks at 100% complete – never critical

    for t in all_tasks:
        try:
            tid = int(str(t.getID()))
            if tid in summary_ids:
                continue
            es = _to_dt(t.getStart())
            ef = _to_dt(t.getFinish())
            if es and ef:
                early_start[tid]  = es
                early_finish[tid] = ef
            # Mark as completed if percentage is 100
            try:
                pct_raw = t.getPercentageComplete()
                if pct_raw is not None:
                    pct_val = float(str(pct_raw).replace('%', '').strip())
                    if pct_val >= 100.0:
                        completed_ids.add(tid)
            except Exception:
                pass
        except Exception:
            pass

    if not early_finish:
        if return_float_data:
            return set(), {}
        return set()

    # Duration: calendar span between stored start and finish.
    duration_td: dict = {
        tid: early_finish[tid] - early_start[tid]
        for tid in early_finish
    }

    # ----------------------------------------------------------------
    # Phase 5 — per-task calendar setup.
    # When project is available we compute each task's effective calendar
    # (task → resource → project default) and express task durations in
    # actual working hours instead of wall-clock seconds.  This feeds
    # calendar-aware date arithmetic in the forward/backward passes and
    # accurate working-day display in the CPM Results panel.
    # ----------------------------------------------------------------
    _cal_aware: bool = False
    proj_cal          = None
    proj_wdh: float   = 8.0
    task_cal:  dict   = {}   # tid -> MPXJ ProjectCalendar
    dur_wh:    dict   = {}   # tid -> working hours of task duration
    task_wdh:  dict   = {}   # tid -> working hours/day for this task's calendar
    lag_wh_map: dict  = {}   # (pid, sid) -> lag working hours

    if project is not None:
        try:
            proj_cal = project.getDefaultCalendar()
            if proj_cal is not None:
                proj_wdh = _calendar_wdh(proj_cal)
            # Map tid → Java task object for tasks in early_start
            _tid_to_jtask: dict = {}
            for _t in all_tasks:
                try:
                    _tid = int(str(_t.getID()))
                    if _tid in early_start:
                        _tid_to_jtask[_tid] = _t
                except Exception:
                    pass
            for _tid, _t in _tid_to_jtask.items():
                _tcal = _get_task_calendar(_t, project)
                if _tcal is None:
                    _tcal = proj_cal
                task_cal[_tid]  = _tcal
                task_wdh[_tid]  = _calendar_wdh(_tcal) if _tcal is not None else proj_wdh
                if _tcal is not None:
                    dur_wh[_tid] = _working_hours_between(
                        _tcal, early_start[_tid], early_finish[_tid]
                    )
                else:
                    dur_wh[_tid] = duration_td[_tid].total_seconds() / 3600.0
            _cal_aware = True
        except Exception:
            _cal_aware = False

    # Read task constraints (SNET, MFO, etc.) from MPXJ
    constraint_type: dict = {}   # tid -> str e.g. "START_NO_EARLIER_THAN"
    constraint_date: dict = {}   # tid -> datetime
    for t in all_tasks:
        try:
            tid = int(str(t.getID()))
            if tid not in early_finish:
                continue
            ct = t.getConstraintType()
            cd = t.getConstraintDate()
            if ct is not None:
                constraint_type[tid] = str(ct)
            if cd is not None:
                constraint_date[tid] = _to_dt(cd)
        except Exception:
            pass

    # Build successor map for all dependency types (SS, FF, SF, FS) + lag.
    # Each entry: successors[pid] = [(sid, rel_type_str, lag_timedelta), ...]
    # predecessors[tid] = [(pid, rel_type_str, lag_timedelta), ...]
    successors:   dict = {tid: [] for tid in early_finish}
    predecessors: dict = {tid: [] for tid in early_finish}
    for t in all_tasks:
        try:
            tid = int(str(t.getID()))
            if tid not in early_finish:
                continue
            preds_java = t.getPredecessors()
            if not preds_java:
                continue
            for rel in preds_java:
                try:
                    rt = str(rel.getType())
                except Exception:
                    rt = "FINISH_START"
                # Filter by dep_types setting
                if dep_types == "fs_only" and rt not in _FS_ONLY:
                    continue
                if rt not in _SUPPORTED:
                    continue
                pred_t = rel.getPredecessorTask()
                if pred_t is None:
                    continue
                pid = int(str(pred_t.getID()))
                if pid not in early_finish:
                    continue
                try:
                    lag_td = _lag_to_timedelta(rel.getLag())
                    if _cal_aware:
                        lag_wh_map[(pid, tid)] = _lag_to_working_hours(rel.getLag(), proj_wdh)
                except Exception:
                    lag_td = timedelta(0)
                successors[pid].append((tid, rt, lag_td))
                predecessors[tid].append((pid, rt, lag_td))
        except Exception:
            pass

    # ----------------------------------------------------------------
    # Forward pass: compute net_es[tid] and net_ef[tid].
    # FS: ES_succ = EF_pred + lag
    # SS: ES_succ = ES_pred + lag
    # FF: EF_succ >= EF_pred + lag  (EF constraint on successor)
    # SF: EF_succ >= ES_pred + lag  (EF constraint on successor)
    # Root tasks (no predecessors) anchor to their stored start/finish.
    # ----------------------------------------------------------------
    net_es: dict = {}
    net_ef: dict = {}

    # We need two passes per iteration: one for ES (from FS/SS) then EF (from FF/SF)
    for _ in range(len(early_finish) + 2):
        changed = False
        for tid in early_finish:
            preds = predecessors[tid]
            # Compute minimum ES from FS/SS predecessors
            if not preds:
                candidate_es = early_start[tid]
            else:
                # Start from stored start; push out by each predecessor's constraint
                candidate_es = early_start[tid]
                all_preds_computed = True
                for (pid, rt, lag_td) in preds:
                    if pid not in net_ef:
                        all_preds_computed = False
                        break
                    if rt in ("FS", "FINISH_START"):
                        if _cal_aware and proj_cal is not None:
                            _lw = lag_wh_map.get((pid, tid), lag_td.total_seconds() / 3600.0)
                            _pushed = _calendar_add_working_hours(proj_cal, net_ef[pid], _lw)
                        else:
                            _pushed = net_ef[pid] + lag_td
                        candidate_es = max(candidate_es, _pushed)
                    elif rt in ("SS", "START_START"):
                        pid_es = net_es.get(pid, early_start.get(pid))
                        if pid_es:
                            if _cal_aware and proj_cal is not None:
                                _lw = lag_wh_map.get((pid, tid), lag_td.total_seconds() / 3600.0)
                                _pushed = _calendar_add_working_hours(proj_cal, pid_es, _lw)
                            else:
                                _pushed = pid_es + lag_td
                            candidate_es = max(candidate_es, _pushed)
                    # FF and SF constrain EF, not ES — handled below
                if not all_preds_computed:
                    continue

            # Apply start-type constraints
            ct = constraint_type.get(tid, "")
            cd = constraint_date.get(tid)
            stored_start = early_start.get(tid)
            constraint_overridden = (
                stored_start is not None and cd is not None
                and stored_start < cd
                and ct in ("START_NO_EARLIER_THAN", "SNET",
                           "START_NO_LATER_THAN", "SNLT",
                           "MUST_START_ON", "MSO")
            )
            if cd is not None and not constraint_overridden:
                if ct in ("START_NO_EARLIER_THAN", "SNET"):
                    candidate_es = max(candidate_es, cd)
                elif ct in ("START_NO_LATER_THAN", "SNLT"):
                    candidate_es = min(candidate_es, cd)
                elif ct in ("MUST_START_ON", "MSO"):
                    candidate_es = cd
                elif ct in ("MUST_FINISH_ON", "MFO"):
                    new_ef = cd
                    if net_es.get(tid) != candidate_es or net_ef.get(tid) != new_ef:
                        net_es[tid] = candidate_es
                        net_ef[tid] = new_ef
                        changed = True
                    continue
                elif ct in ("FINISH_NO_EARLIER_THAN", "FNET"):
                    if _cal_aware and tid in task_cal and task_cal[tid] is not None:
                        _fnet_ef = _calendar_add_working_hours(task_cal[tid], candidate_es, dur_wh[tid])
                    else:
                        _fnet_ef = candidate_es + duration_td[tid]
                    new_ef = max(_fnet_ef, cd)
                    if net_es.get(tid) != candidate_es or net_ef.get(tid) != new_ef:
                        net_es[tid] = candidate_es
                        net_ef[tid] = new_ef
                        changed = True
                    continue

            # Compute EF from ES + duration, then push by FF/SF constraints
            if _cal_aware and tid in task_cal and task_cal[tid] is not None:
                candidate_ef = _calendar_add_working_hours(task_cal[tid], candidate_es, dur_wh[tid])
            else:
                candidate_ef = candidate_es + duration_td[tid]
            for (pid, rt, lag_td) in preds:
                if rt in ("FF", "FINISH_FINISH"):
                    pid_ef = net_ef.get(pid, early_finish.get(pid))
                    if pid_ef:
                        if _cal_aware and proj_cal is not None:
                            _lw = lag_wh_map.get((pid, tid), lag_td.total_seconds() / 3600.0)
                            _pushed = _calendar_add_working_hours(proj_cal, pid_ef, _lw)
                        else:
                            _pushed = pid_ef + lag_td
                        candidate_ef = max(candidate_ef, _pushed)
                elif rt in ("SF", "START_FINISH"):
                    pid_es = net_es.get(pid, early_start.get(pid))
                    if pid_es:
                        if _cal_aware and proj_cal is not None:
                            _lw = lag_wh_map.get((pid, tid), lag_td.total_seconds() / 3600.0)
                            _pushed = _calendar_add_working_hours(proj_cal, pid_es, _lw)
                        else:
                            _pushed = pid_es + lag_td
                        candidate_ef = max(candidate_ef, _pushed)

            if net_es.get(tid) != candidate_es or net_ef.get(tid) != candidate_ef:
                net_es[tid] = candidate_es
                net_ef[tid] = candidate_ef
                changed = True

        if not changed:
            break

    # Fill any tasks not reached in the iteration (disconnected / root)
    for tid in early_finish:
        if tid not in net_es:
            net_es[tid] = early_start[tid]
        if tid not in net_ef:
            net_ef[tid] = early_finish[tid]

    # Effective EF = max(network_ef, stored_ef).
    fp_es: dict = {tid: max(net_es[tid], early_start[tid])  for tid in early_finish}
    fp_ef: dict = {tid: max(net_ef[tid], early_finish[tid]) for tid in early_finish}

    # ----------------------------------------------------------------
    # Project finish anchor for the backward pass.
    # The raw stored deadline is kept separately so the overdue check in
    # _is_critical can compare against the original project deadline
    # rather than the inflated value (which SNET tasks can raise).
    # ----------------------------------------------------------------
    raw_deadline: datetime = None
    if project is not None:
        try:
            pf = project.getProjectProperties().getFinishDate()
            if pf is not None:
                raw_deadline = _to_dt(pf)
        except Exception:
            pass
    # Use ALL net_ef values (including constrained tasks) for the backward
    # pass anchor so float is computed correctly for every task.
    net_max = max(net_ef.values())
    project_finish = max(raw_deadline, net_max) if raw_deadline else net_max

    # ----------------------------------------------------------------
    # Backward pass: LF anchored at project_finish, propagated backward
    # through FS links using stored durations.
    # ----------------------------------------------------------------
    late_finish: dict = {tid: project_finish for tid in fp_ef}
    for _ in range(len(all_tasks) + 2):
        changed = False
        for tid, succs in successors.items():
            if not succs:
                continue
            new_lf = late_finish[tid]
            for (sid, rt, lag_td) in succs:
                if sid not in late_finish:
                    continue
                _lw = lag_wh_map.get((tid, sid), lag_td.total_seconds() / 3600.0) if _cal_aware else 0.0
                _sid_cal = task_cal.get(sid) if _cal_aware else None
                _tid_cal = task_cal.get(tid) if _cal_aware else None
                # Backward pass rules (mirror of forward pass)
                if rt in ("FS", "FINISH_START"):
                    # LF_pred = LS_succ - lag = LF_succ - dur_succ - lag
                    if _cal_aware and _sid_cal is not None:
                        ls_succ     = _calendar_add_working_hours(_sid_cal, late_finish[sid], -dur_wh[sid])
                        lf_from_succ = _calendar_add_working_hours(proj_cal or _sid_cal, ls_succ, -_lw)
                    else:
                        ls_succ      = late_finish[sid] - duration_td[sid]
                        lf_from_succ = ls_succ - lag_td
                elif rt in ("SS", "START_START"):
                    # LS_pred = LS_succ - lag → LF_pred = LS_succ - lag + dur_pred
                    if _cal_aware and _sid_cal is not None and _tid_cal is not None:
                        ls_succ      = _calendar_add_working_hours(_sid_cal, late_finish[sid], -dur_wh[sid])
                        ls_pred      = _calendar_add_working_hours(proj_cal or _sid_cal, ls_succ, -_lw)
                        lf_from_succ = _calendar_add_working_hours(_tid_cal, ls_pred, dur_wh[tid])
                    else:
                        ls_succ      = late_finish[sid] - duration_td[sid]
                        lf_from_succ = ls_succ - lag_td + duration_td[tid]
                elif rt in ("FF", "FINISH_FINISH"):
                    # LF_pred = LF_succ - lag
                    if _cal_aware and proj_cal is not None:
                        lf_from_succ = _calendar_add_working_hours(proj_cal, late_finish[sid], -_lw)
                    else:
                        lf_from_succ = late_finish[sid] - lag_td
                elif rt in ("SF", "START_FINISH"):
                    # LS_pred = LF_succ - lag → LF_pred = LF_succ - lag + dur_pred
                    if _cal_aware and _tid_cal is not None and proj_cal is not None:
                        ls_pred      = _calendar_add_working_hours(proj_cal, late_finish[sid], -_lw)
                        lf_from_succ = _calendar_add_working_hours(_tid_cal, ls_pred, dur_wh[tid])
                    else:
                        lf_from_succ = late_finish[sid] - lag_td + duration_td[tid]
                else:
                    if _cal_aware and _sid_cal is not None:
                        ls_succ      = _calendar_add_working_hours(_sid_cal, late_finish[sid], -dur_wh[sid])
                        lf_from_succ = _calendar_add_working_hours(proj_cal or _sid_cal, ls_succ, -_lw)
                    else:
                        ls_succ      = late_finish[sid] - duration_td[sid]
                        lf_from_succ = ls_succ - lag_td
                if lf_from_succ < new_lf:
                    new_lf = lf_from_succ
            if new_lf < late_finish[tid]:
                late_finish[tid] = new_lf
                changed = True
        if not changed:
            break

    # ----------------------------------------------------------------
    # Free Float (post-backward-pass):
    # FF(t) = min(ES of all direct successors) - EF(t)
    # For leaf tasks (no successors): project_finish - EF(t)
    # ----------------------------------------------------------------
    _ZERO = timedelta(0)
    free_float: dict = {}
    for tid in fp_ef:
        succs = successors.get(tid, [])
        if not succs:
            free_float[tid] = max(project_finish - fp_ef[tid], _ZERO)
        else:
            min_succ_es = min(
                (fp_es[sid] for (sid, _, _) in succs if sid in fp_es),
                default=project_finish,
            )
            free_float[tid] = max(min_succ_es - fp_ef[tid], _ZERO)

    # ----------------------------------------------------------------
    # Criticality: Total Float ≤ threshold  (MS Project default: 0)
    # ----------------------------------------------------------------
    _SMALL = timedelta(minutes=30)  # tolerance for floating-point rounding

    def _is_critical(tid):
        if tid in completed_ids:
            return False
        flt = late_finish[tid] - fp_ef[tid]
        if raw_deadline and early_finish[tid] >= raw_deadline:
            return True
        if flt <= _THRESHOLD:
            return True
        return False

    critical_leaf_ids = {tid for tid in fp_ef if _is_critical(tid)}

    # Propagate criticality up to summary tasks
    def _any_critical_descendant(tid: int) -> bool:
        for child_id in children_map.get(tid, []):
            if child_id in critical_leaf_ids:
                return True
            if child_id in summary_ids and _any_critical_descendant(child_id):
                return True
        return False

    critical_summary_ids = {
        tid for tid in summary_ids
        if _any_critical_descendant(tid)
    }

    result_ids = critical_leaf_ids | critical_summary_ids

    if not return_float_data:
        return result_ids

    # Build the float_data dict for all leaf tasks
    float_data: dict = {}
    for tid in fp_ef:
        total_flt = late_finish[tid] - fp_ef[tid]
        _wdh = task_wdh.get(tid, proj_wdh) if _cal_aware else 8.0
        _tcal = task_cal.get(tid) if _cal_aware else None

        # Calendar-aware float in working hours (falls back to wall-clock / wdh)
        if _cal_aware and _tcal is not None:
            _total_flt_wh = _working_hours_between(_tcal, fp_ef[tid], late_finish[tid])
            _free_flt_wh  = _working_hours_between(_tcal, fp_ef[tid], fp_ef[tid] + free_float[tid])
        else:
            _total_flt_wh = total_flt.total_seconds() / 3600.0
            _free_flt_wh  = free_float[tid].total_seconds() / 3600.0

        # LS computed calendar-aware when possible
        if _cal_aware and _tcal is not None:
            _ls = _calendar_add_working_hours(_tcal, late_finish[tid], -dur_wh[tid])
        else:
            _ls = late_finish[tid] - duration_td[tid]

        float_data[tid] = {
            "es":              fp_es[tid],
            "ef":              fp_ef[tid],
            "ls":              _ls,
            "lf":              late_finish[tid],
            "total_float":     total_flt,
            "free_float":      free_float[tid],
            "total_float_wh":  _total_flt_wh,   # Phase 5: working hours of total float
            "free_float_wh":   _free_flt_wh,    # Phase 5: working hours of free float
            "work_day_hours":  _wdh,             # Phase 5: per-task calendar wdh
            "critical":        tid in result_ids,
        }
    return result_ids, float_data


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


class _NonWorkingDayDialog(QDialog):
    """Ask the user how to handle a task drag that starts on a non-working day
    (weekend or public holiday).

    Options:
      • Move to next working day  – shift start forward to first working day
      • Move anyway               – keep the date as dragged
      • Cancel
    """

    NEXT = 'next'
    MOVE = 'move'

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


class GanttHeader(QWidget):
    """Fixed two-row calendar header (month band / day numbers).
    Scrolls horizontally in sync with the canvas; never scrolls vertically.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.project_start     = None
        self.total_days        = 90
        self.day_width         = DAY_WIDTH_DEF
        self.show_sundays      = True
        self.non_working_dates: set = set()
        self.setFixedHeight(HEADER_HEIGHT)

    def configure(self, project_start, total_days, day_width,
                  show_sundays=True, non_working_dates=None):
        self.project_start     = project_start
        self.total_days        = total_days
        self.day_width         = day_width
        self.show_sundays      = show_sundays
        self.non_working_dates = non_working_dates if non_working_dates is not None else set()
        vis = (_date_to_col(project_start, project_start.addDays(total_days), show_sundays)
               if project_start else total_days)
        self.setFixedSize(QSize(max(400, LABEL_WIDTH + vis * day_width), HEADER_HEIGHT))
        self.update()

    def paintEvent(self, event):
        if not self.project_start:
            return
        painter    = QPainter(self)
        font_bold  = QFont("Segoe UI", 9, QFont.Bold)
        font_small = QFont("Segoe UI", 7)

        vis_cols = _date_to_col(self.project_start,
                                self.project_start.addDays(self.total_days),
                                self.show_sundays)
        total_w  = LABEL_WIDTH + vis_cols * self.day_width

        painter.fillRect(0, 0, LABEL_WIDTH, HEADER_HEIGHT, QColor(236, 243, 251))
        painter.setPen(QPen(QColor(150, 180, 220), 1))
        painter.drawLine(LABEL_WIDTH, 0, LABEL_WIDTH, HEADER_HEIGHT)

        # Top row: month names — iterate calendar days grouped by month,
        # counting only visible columns (skip Sundays when show_sundays=False)
        d   = 0
        col = 0
        while d < self.total_days:
            date         = self.project_start.addDays(d)
            end_of_month = QDate(date.year(), date.month(), date.daysInMonth())
            cal_span     = min(date.daysTo(end_of_month) + 1, self.total_days - d)
            vis_span     = sum(
                1 for dd in range(d, d + cal_span)
                if self.show_sundays or self.project_start.addDays(dd).dayOfWeek() != 7
            )
            if vis_span == 0:
                d += cal_span
                continue
            x        = LABEL_WIDTH + col * self.day_width
            month_px = vis_span * self.day_width
            bg = QColor(210, 228, 252) if date.month() % 2 == 0 else QColor(195, 215, 245)
            painter.fillRect(x, 0, month_px, HEADER_MONTH_H, bg)
            painter.setPen(QColor(26, 63, 122))
            painter.setFont(font_bold)
            label = date.toString("MMM yyyy") if month_px > 64 else date.toString("MMM")
            painter.drawText(QRect(x + 3, 0, month_px - 6, HEADER_MONTH_H),
                             Qt.AlignVCenter | Qt.AlignLeft, label)
            painter.setPen(QPen(QColor(140, 175, 215), 1))
            painter.drawLine(x, 0, x, HEADER_HEIGHT)
            col += vis_span
            d   += cal_span

        # Bottom row: day numbers (skip Sundays when show_sundays=False)
        painter.setFont(font_small)
        col = 0
        for d in range(self.total_days):
            date = self.project_start.addDays(d)
            dow  = date.dayOfWeek()
            if not self.show_sundays and dow == 7:
                continue
            x   = LABEL_WIDTH + col * self.day_width
            col += 1
            iso = date.toString(Qt.ISODate)
            if dow == 6 or iso in self.non_working_dates:
                bg = QColor(220, 220, 220)    # Saturday / public holiday: light grey
            elif dow == 7:
                bg = QColor(215, 222, 238)    # Sunday: blue-tint (unchanged)
            elif dow == 1:
                bg = QColor(230, 240, 254)    # Monday slight highlight
            else:
                bg = QColor(242, 247, 255)
            painter.fillRect(x, HEADER_MONTH_H, self.day_width, HEADER_WEEK_H, bg)
            if self.day_width >= 14:
                painter.setPen(QColor(80, 100, 140))
                painter.drawText(QRect(x, HEADER_MONTH_H, self.day_width, HEADER_WEEK_H),
                                 Qt.AlignCenter, str(date.day()))
            elif self.day_width >= 8 and dow == 1:
                painter.setPen(QColor(80, 100, 140))
                painter.drawText(QRect(x, HEADER_MONTH_H, self.day_width * 5, HEADER_WEEK_H),
                                 Qt.AlignLeft | Qt.AlignVCenter,
                                 f"W{date.weekNumber()[0]}")
            painter.setPen(QPen(QColor(215, 225, 240), 1))
            painter.drawLine(x, HEADER_MONTH_H, x, HEADER_HEIGHT)

        # Heavy bottom border
        painter.setPen(QPen(QColor(43, 87, 154), 2))
        painter.drawLine(0, HEADER_HEIGHT - 1, total_w, HEADER_HEIGHT - 1)

        # Today line: bold green vertical indicator in the header
        today = QDate.currentDate()
        if self.project_start and today >= self.project_start:
            tc = _date_to_col(self.project_start, today, self.show_sundays)
            tx = LABEL_WIDTH + tc * self.day_width
            painter.setPen(QPen(QColor(0, 168, 0), 2, Qt.SolidLine))
            painter.drawLine(tx, 0, tx, HEADER_HEIGHT)
            # Small triangle pointer at bottom of header
            painter.setBrush(QBrush(QColor(0, 168, 0)))
            painter.setPen(Qt.NoPen)
            sz = 5
            painter.drawPolygon(QPolygon([
                QPoint(tx - sz, HEADER_HEIGHT - sz * 2),
                QPoint(tx + sz, HEADER_HEIGHT - sz * 2),
                QPoint(tx,      HEADER_HEIGHT),
            ]))
        painter.end()


class GanttCanvas(QWidget):
    task_moved   = pyqtSignal(object, int)   # (java task, delta) — days in day mode, hours in hourly mode
    zoom_changed = pyqtSignal(int)           # emits current day_width after every zoom
    task_edited  = pyqtSignal()              # emitted after a task is edited via dialog

    def __init__(self, parent=None):
        super().__init__(parent)
        self.tasks              = []
        self._project           = None
        self.project_start      = None
        self.total_days         = 90
        self.day_width          = DAY_WIDTH_DEF
        self.show_resource_units = False   # when True: "Name [100%]", else "Name"
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMouseTracking(True)
        self._bar_rects        = []   # cached from last paint for hit-testing
        self._drag_idx         = -1   # index into self.tasks, or -1
        self._drag_start_x     = 0
        self._drag_delta_days  = 0
        self._drag_delta_hours = 0   # used in hourly mode instead of _drag_delta_days
        self._collapsed_ids      = set()   # IDs of collapsed summary tasks
        self.show_sundays        = True
        self._non_working_dates  = set()   # ISO-date non-working weekday dates
        self._critical_ids       = set()   # int task IDs on the critical path
        self._float_data         = {}      # int tid → {es, ef, ls, lf, total_float, free_float, critical}
        self._zero_float_critical = False  # when True, zero-float tasks are critical
        self._critical_slack_days: int = 0   # numeric critical threshold (days)
        self._cpm_dep_types: str = "all"      # "all" or "fs_only"
        self._show_float_bar: bool = False    # draw total-float overlay on Gantt bars
        # Hourly zoom fields (populated when a project is loaded)
        self._work_hour_start   = WORK_HOUR_START
        self._work_hour_end     = WORK_HOUR_END
        self._work_day_hours    = WORK_DAY_HOURS
        self._non_working_slots: frozenset = frozenset()
        self._clock_day_span    = WORK_DAY_HOURS   # total hour columns per working day
        self._show_off_hours    = False
        # Baseline display settings
        self._baseline_number: int  = 0     # which slot to draw (0-10)
        self._show_baseline_bars: bool = True  # toggle baseline strip
        self._timeline_view = None  # set via GanttView.set_timeline_view()
        # Split-task data: int task_unique_id → list of (QDate start, QDate finish) segments
        # Populated by load_splits_from_project() or split_task() / merge_task().
        self._task_splits: dict = {}   # {int uid: [(QDate, QDate), ...]}
        self._drag_segment_idx = -1   # segment being dragged (-1 = whole task)
        self._split_seg_rects  = []   # [{task_idx, uid, seg_idx, x1, x2, bar_y, bar_h}]

    def set_show_resource_units(self, value: bool):
        self.show_resource_units = bool(value)
        self.update()

    def set_zero_float_critical(self, value: bool):
        self._zero_float_critical = bool(value)
        self.update()

    def set_critical_slack_days(self, days: int):
        self._critical_slack_days = max(0, int(days))
        self.update()

    def set_cpm_dep_types(self, mode: str):
        self._cpm_dep_types = mode if mode in ("all", "fs_only") else "all"
        self.update()

    def set_show_float_bar(self, value: bool):
        self._show_float_bar = bool(value)
        self.update()

    def set_collapsed_ids(self, ids):
        self._collapsed_ids = set(ids)
        self.update()

    def set_show_sundays(self, value: bool):
        self.show_sundays = bool(value)
        self._apply_size()
        self.update()
        self.zoom_changed.emit(self.day_width)

    def set_baseline_number(self, number: int) -> None:
        """Select which baseline slot (0-10) is drawn as a reference strip."""
        self._baseline_number = max(0, min(10, int(number)))
        self.update()

    def set_show_baseline_bars(self, show: bool) -> None:
        """Show or hide the baseline reference strip on Gantt bars."""
        self._show_baseline_bars = bool(show)
        self.update()

    # ---------------------------------------------------------------- #
    # Split / Merge task API                                            #
    # ---------------------------------------------------------------- #

    def _uid_for_task(self, task) -> int | None:
        """Return the integer UniqueID for a Java task, or None."""
        try:
            uid = task.getUniqueID()
            if uid is None or str(uid) in ('null', 'None', ''):
                return None
            return int(str(uid))
        except Exception:
            return None

    def _segments_for_uid(self, uid: int):
        """Return the current split segments for uid (defaults to full task bar)."""
        return self._task_splits.get(uid, None)

    def split_task(self, task, split_qdate: QDate) -> bool:
        """Split *task* at *split_qdate* creating a 1-day gap.

        If the task is already split, the segment containing *split_qdate* is
        divided. Returns True on success, False if the date is out of range or
        the task is a summary / milestone.
        """
        try:
            if bool(task.getSummary()) or bool(task.getMilestone()):
                return False
        except Exception:
            pass
        uid = self._uid_for_task(task)
        if uid is None:
            return False

        start_qd = _to_qdate(task.getStart())
        finish_qd = _compute_finish_date(task)
        if start_qd is None or finish_qd is None:
            return False

        # Current segments (use existing splits or full bar as single segment)
        current = self._task_splits.get(uid) or [(start_qd, finish_qd)]

        new_segments = []
        split_done = False
        for seg_start, seg_end in current:
            if not split_done and seg_start <= split_qdate <= seg_end:
                # Keep at least 1 day in each segment
                if split_qdate > seg_start and split_qdate.addDays(SPLIT_GAP_DAYS) <= seg_end:
                    seg1_end   = split_qdate.addDays(-1)
                    seg2_start = split_qdate.addDays(SPLIT_GAP_DAYS)
                    # Step 1: skip project non-working days (weekends / holidays)
                    while self._starts_on_non_working(seg2_start) and seg2_start < seg_end:
                        seg2_start = seg2_start.addDays(1)
                    # Step 2: skip resource vacation blocks.
                    # When seg2_start falls inside a vacation we shift BOTH
                    # seg2_start and seg_end forward by the same distance so
                    # the remaining segment duration is preserved.
                    vac_blocks = _task_vacation_blocks(task)
                    if vac_blocks:
                        _changed = True
                        while _changed:
                            _changed = False
                            for _vf, _vt in vac_blocks:
                                if _vf <= seg2_start <= _vt:
                                    _advance = seg2_start.daysTo(_vt.addDays(1))
                                    seg2_start = _vt.addDays(1)
                                    seg_end = seg_end.addDays(_advance)
                                    # skip non-working days landing right after vacation
                                    while self._starts_on_non_working(seg2_start):
                                        seg2_start = seg2_start.addDays(1)
                                        seg_end = seg_end.addDays(1)
                                    _changed = True
                                    break
                    new_segments.append((seg_start, seg1_end))
                    new_segments.append((seg2_start, seg_end))
                    split_done = True
                else:
                    new_segments.append((seg_start, seg_end))
            else:
                new_segments.append((seg_start, seg_end))

        if not split_done:
            return False

        self._task_splits[uid] = new_segments
        self.update()
        return True

    def merge_task(self, task) -> bool:
        """Remove all splits for *task*, restoring a single contiguous bar."""
        uid = self._uid_for_task(task)
        if uid is None:
            return False
        if uid in self._task_splits:
            del self._task_splits[uid]
            self.update()
        return True

    def get_splits(self, task):
        """Return list of (QDate start, QDate finish) segments, or empty list."""
        uid = self._uid_for_task(task)
        if uid is None:
            return []
        return list(self._task_splits.get(uid, []))

    def load_splits_from_project(self, project) -> None:
        """Populate _task_splits from MPXJ task.getSplits() for MPP/XML imports."""
        self._task_splits.clear()
        if project is None:
            return
        try:
            for task in project.getTasks():
                if task.getName() is None:
                    continue
                uid = self._uid_for_task(task)
                if uid is None:
                    continue
                try:
                    splits = task.getSplits()
                    if splits is None or splits.isEmpty():
                        continue
                    segments = []
                    for seg in splits:
                        try:
                            s = _to_qdate(seg.getStart())
                            e = _to_qdate(seg.getEnd())
                            if s and e and s <= e:
                                segments.append((s, e))
                        except Exception:
                            pass
                    if len(segments) >= 2:
                        self._task_splits[uid] = segments
                except Exception:
                    pass
        except Exception:
            pass

    def clear_splits(self) -> None:
        """Clear all split data (called on project close / new project)."""
        self._task_splits.clear()
        self.update()

    def load_splits_from_dict(self, data: dict) -> None:
        """Load splits from a plain dict {str_uid: [[iso_start, iso_finish], ...]}."""
        self._task_splits.clear()
        for uid_str, segs in data.items():
            try:
                uid = int(uid_str)
                parsed = []
                for seg in segs:
                    s = QDate.fromString(seg[0], "yyyy-MM-dd")
                    e = QDate.fromString(seg[1], "yyyy-MM-dd")
                    if s.isValid() and e.isValid():
                        parsed.append((s, e))
                if parsed:
                    self._task_splits[uid] = parsed
            except Exception:
                pass
        self.update()

    def splits_to_dict(self) -> dict:
        """Serialise _task_splits to a plain dict suitable for JSON."""
        result = {}
        for uid, segs in self._task_splits.items():
            result[str(uid)] = [
                [s.toString("yyyy-MM-dd"), e.toString("yyyy-MM-dd")]
                for s, e in segs
            ]
        return result

    def _get_baseline_start(self, task):
        """Return the baseline start for the active slot, or None."""
        try:
            import sys, os
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
            import baseline_manager  # type: ignore
            return baseline_manager.get_baseline_start(task, self._baseline_number)
        except Exception:
            return None

    def _get_baseline_finish(self, task):
        """Return the baseline finish for the active slot, or None."""
        try:
            import sys, os
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
            import baseline_manager  # type: ignore
            return baseline_manager.get_baseline_finish(task, self._baseline_number)
        except Exception:
            return None

    # ---------------------------------------------------------------- #
    # Data                                                              #
    # ---------------------------------------------------------------- #

    def load_project(self, project, recompute_critical=False):
        self._project = project
        self.tasks = []
        self._bar_rects = []
        if project is None:
            self._apply_size()
            self.update()
            return
        all_tasks_full = [t for t in project.getTasks()
                    if t.getName() is not None and str(t.getID()) != "0"]
        # Propagate predecessor finish dates on the FULL list (schedule must stay coherent)
        _normalize_schedule(all_tasks_full)
        # Critical path: always recomputed via internal CPM, ignoring any flag
        # stored in the MPXJ/MS Project file.
        # Wrapped in run_indeterminate so a spinner appears for large schedules
        # (operation > 400 ms).  For small/fast schedules the QProgressDialog
        # minimum-duration guard suppresses the dialog entirely.  The call
        # stays on the main thread, keeping JPype/JVM access safe.
        try:
            from progress_worker import run_indeterminate as _run_cpm  # type: ignore
        except ImportError:
            _run_cpm = lambda _p, _t, fn, *a, **kw: fn(*a, **kw)
        self._critical_ids, self._float_data = _run_cpm(
            self, "Calculating critical path\u2026",
            _compute_critical_ids,
            all_tasks_full, project,
            zero_float_critical=self._zero_float_critical,
            dep_types=self._cpm_dep_types,
            critical_slack_days=self._critical_slack_days,
            return_float_data=True,
        )
        # Apply collapse filter for display only
        all_tasks = _get_visible_tasks(all_tasks_full, self._collapsed_ids)
        # Use calendar-aware finish for viewport sizing
        starts   = [_to_qdate(t.getStart()) for t in all_tasks]
        starts   = [s for s in starts if s]
        finishes = [_compute_finish_date(t) for t in all_tasks]
        finishes = [f for f in finishes if f]
        if starts:
            self.project_start = min(starts)
            max_finish = max(finishes) if finishes else self.project_start
            self.total_days = max(self.project_start.daysTo(max_finish) + 14, 30)
            # Extend canvas to cover resource vacation end dates so scrolling
            # shows the full picture even past the last task.
            try:
                for res in project.getResources():
                    try:
                        cal = res.getCalendar()
                        if cal is None:
                            continue
                        for ex in cal.getCalendarExceptions():
                            try:
                                if bool(ex.getWorking()):
                                    continue
                            except Exception:
                                pass
                            to_str = str(ex.getToDate() or "")[:10]
                            if not to_str:
                                continue
                            to_qd = QDate.fromString(to_str, "yyyy-MM-dd")
                            if to_qd.isValid():
                                end = self.project_start.addDays(self.total_days)
                                if to_qd > end:
                                    self.total_days = self.project_start.daysTo(to_qd) + 14
                    except Exception:
                        continue
            except Exception:
                pass
        else:
            self.project_start = QDate.currentDate()
            self.total_days    = 90
        self.tasks = all_tasks
        self._non_working_dates = _get_non_working_dates(
            project, self.project_start, self.total_days)
        # Read working-hour window for hourly zoom mode
        (self._work_hour_start, self._work_hour_end,
         self._work_day_hours, self._non_working_slots) = read_work_hours(project)
        self._clock_day_span = self._work_hour_end - self._work_hour_start
        self._apply_size()
        self.update()

    def set_day_width(self, dw):
        self.day_width = max(DAY_WIDTH_MIN, min(DAY_WIDTH_MAX, dw))
        self._apply_size()
        self.update()
        self.zoom_changed.emit(self.day_width)

    def set_show_off_hours(self, value: bool):
        self._show_off_hours = bool(value)
        self._apply_size()
        self.update()
        self.zoom_changed.emit(self.day_width)

    def is_hourly_mode(self) -> bool:
        return self.day_width >= HOUR_MODE_THRESHOLD

    def zoom_in(self):
        self.set_day_width(self.day_width + 4)

    def zoom_out(self):
        self.set_day_width(self.day_width - 4)

    # ---------------------------------------------------------------- #
    # Drag and drop                                                     #
    # ---------------------------------------------------------------- #

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.project_start:
            y = event.y()
            x = event.x()
            # Check per-segment rects first – clicking in the gap between segments does nothing
            for sr in reversed(self._split_seg_rects):
                if sr['x1'] <= x <= sr['x2'] and sr['bar_y'] <= y <= sr['bar_y'] + sr['bar_h']:
                    self._drag_idx         = sr['task_idx']
                    self._drag_segment_idx = sr['seg_idx']
                    self._drag_start_x     = x
                    self._drag_delta_days  = 0
                    self._drag_delta_hours = 0
                    self.setCursor(Qt.ClosedHandCursor)
                    return
            # Full-task bar hit-testing (non-split tasks only; gap area not draggable)
            for i, br in enumerate(self._bar_rects):
                if br[1] is None:
                    continue
                _, x1, x2, bar_y, bar_h = br
                if x1 <= x <= x2 and bar_y <= y <= bar_y + bar_h:
                    if i < len(self.tasks):
                        uid = self._uid_for_task(self.tasks[i])
                        if uid is not None and uid in self._task_splits and len(self._task_splits[uid]) >= 2:
                            continue   # split task – handled by segment rects above
                    self._drag_idx         = i
                    self._drag_segment_idx = -1
                    self._drag_start_x     = x
                    self._drag_delta_days  = 0
                    self._drag_delta_hours = 0
                    self.setCursor(Qt.ClosedHandCursor)
                    break

    def mouseMoveEvent(self, event):
        x = event.x()
        if self._drag_idx >= 0:
            dx = x - self._drag_start_x
            if self.day_width >= HOUR_MODE_THRESHOLD:
                self._drag_delta_hours = int(dx / self.day_width)
            else:
                self._drag_delta_days  = int(dx / self.day_width)
            self.update()
        else:
            cursor = Qt.ArrowCursor
            ey = event.y()
            # Segment rects take priority (finer hit area)
            for sr in self._split_seg_rects:
                if sr['x1'] <= x <= sr['x2'] and sr['bar_y'] <= ey <= sr['bar_y'] + sr['bar_h']:
                    cursor = Qt.SizeHorCursor
                    break
            else:
                for br in self._bar_rects:
                    if br[1] is None:
                        continue
                    _, x1_br, x2_br, by_br, bh_br = br
                    if x1_br <= x <= x2_br and by_br <= ey <= by_br + bh_br:
                        cursor = Qt.SizeHorCursor
                        break
            self.setCursor(cursor)

    def event(self, ev):
        from PyQt5.QtCore import QEvent  # type: ignore
        if ev.type() == QEvent.ToolTip and self.project_start:
            from PyQt5.QtWidgets import QToolTip  # type: ignore
            y = ev.y()
            row = y // ROW_HEIGHT
            if 0 <= row < len(self.tasks):
                task = self.tasks[row]
                uid = self._uid_for_task(task)
                segments = self._task_splits.get(uid) if uid is not None else None
                if segments and len(segments) >= 2:
                    n = len(segments)
                    total_start = segments[0][0]
                    total_end   = segments[-1][1]
                    total_days = total_start.daysTo(total_end) + 1
                    lines = [f"Split task — {n} segment(s)",
                             f"Overall span: {total_start.toString('dd MMM yyyy')} → {total_end.toString('dd MMM yyyy')} ({total_days}d)"]
                    for i, (s, e) in enumerate(segments, 1):
                        d = s.daysTo(e) + 1
                        lines.append(f"  Seg {i}: {s.toString('dd MMM yyyy')} → {e.toString('dd MMM yyyy')} ({d}d)")
                    # Append CPM float info if available
                    try:
                        _tid_int = int(str(task.getID()))
                        _fd = self._float_data.get(_tid_int)
                        if _fd:
                            _wdh = max(_fd.get("work_day_hours") or self._work_day_hours, 1)
                            if _fd.get("total_float_wh") is not None:
                                _tf_d = round(_fd["total_float_wh"] / _wdh, 1)
                                _ff_d = round(_fd.get("free_float_wh", 0.0) / _wdh, 1)
                            else:
                                _tf_d = round(_fd["total_float"].total_seconds() / 3600 / _wdh, 1)
                                _ff_d = round(_fd["free_float"].total_seconds() / 3600 / _wdh, 1)
                            lines.append(f"TF: {_tf_d}d / FF: {_ff_d}d")
                    except Exception:
                        pass
                    QToolTip.showText(ev.globalPos(), "\n".join(lines), self)
                    return True
            # Regular (non-split) task — show float info if available
            if 0 <= row < len(self.tasks):
                task = self.tasks[row]
                try:
                    _tid_int = int(str(task.getID()))
                    _fd = self._float_data.get(_tid_int)
                    if _fd:
                        _wdh = max(_fd.get("work_day_hours") or self._work_day_hours, 1)
                        if _fd.get("total_float_wh") is not None:
                            _tf_d = round(_fd["total_float_wh"] / _wdh, 1)
                            _ff_d = round(_fd.get("free_float_wh", 0.0) / _wdh, 1)
                        else:
                            _tf_d = round(_fd["total_float"].total_seconds() / 3600 / _wdh, 1)
                            _ff_d = round(_fd["free_float"].total_seconds() / 3600 / _wdh, 1)
                        status = "Critical" if _fd.get("critical") else f"TF: {_tf_d}d / FF: {_ff_d}d"
                        QToolTip.showText(ev.globalPos(), status, self)
                        return True
                except Exception:
                    pass
            QToolTip.hideText()
        return super().event(ev)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton and self._project is not None:
            # Cancel any drag that the first click may have started
            self._drag_idx = -1
            self._drag_delta_days = 0
            self.setCursor(Qt.ArrowCursor)
            row = event.y() // ROW_HEIGHT
            if 0 <= row < len(self.tasks):
                task = self.tasks[row]
                import sys, os
                sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
                from dialogs import TaskDialog  # type: ignore
                task_jira_data = _load_task_jira_data(self, task)
                dlg = TaskDialog(task, self._project, self,
                                 timeline_view=getattr(self, '_timeline_view', None),
                                 critical_ids=self._critical_ids,
                                 float_data=self._float_data,
                                 task_jira_data=task_jira_data)
                if dlg.exec_() == dlg.Accepted:
                    dlg.apply_to_task()
                    self.task_edited.emit()

    def _starts_on_non_working(self, date: QDate) -> bool:
        """True when *date* is a weekend or a project non-working day.

        Checks weekends and the cached `_non_working_dates` set first.  Falls
        back to a direct MPXJ calendar query when the cache is stale or empty.
        Positive results are written back to the cache.
        """
        if not date or not date.isValid():
            return False
        if date.dayOfWeek() in (6, 7):
            return True
        iso = date.toString(Qt.ISODate)
        if iso in self._non_working_dates:
            return True
        if self._project is not None:
            try:
                import java.time as _jtime  # type: ignore
                cal = self._project.getDefaultCalendar()
                if cal is not None:
                    ld = _jtime.LocalDate.of(date.year(), date.month(), date.day())
                    is_working = bool(cal.isWorkingDate(ld))
                    if not is_working:
                        self._non_working_dates.add(iso)
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

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._drag_idx >= 0:
            is_hourly = self.day_width >= HOUR_MODE_THRESHOLD
            delta = self._drag_delta_hours if is_hourly else self._drag_delta_days
            # Non-working day guard (whole-day mode only)
            if delta != 0 and not is_hourly and self._drag_idx < len(self.tasks):
                task_chk = self.tasks[self._drag_idx]
                uid_chk  = self._uid_for_task(task_chk)
                if (self._drag_segment_idx >= 0 and uid_chk is not None
                        and uid_chk in self._task_splits):
                    segs_chk = self._task_splits[uid_chk]
                    idx_chk  = self._drag_segment_idx
                    chk_date = segs_chk[idx_chk][0].addDays(delta) if 0 <= idx_chk < len(segs_chk) else None
                else:
                    start_qd = _to_qdate(task_chk.getStart())
                    chk_date = start_qd.addDays(delta) if start_qd else None
                if chk_date and self._starts_on_non_working(chk_date):
                    nw_result = self._ask_non_working_day(task_chk, chk_date)
                    if nw_result is None:
                        self._drag_idx         = -1
                        self._drag_delta_days  = 0
                        self._drag_delta_hours = 0
                        self._drag_segment_idx = -1
                        self.setCursor(Qt.ArrowCursor)
                        self.update()
                        return
                    if nw_result == 'next':
                        nwd = _snap_to_workday(chk_date, self._non_working_dates)
                        delta += chk_date.daysTo(nwd)
            if delta != 0 and self._drag_idx < len(self.tasks):
                task = self.tasks[self._drag_idx]
                uid  = self._uid_for_task(task)
                if self._drag_segment_idx >= 0 and uid is not None and uid in self._task_splits:
                    # Per-segment drag: only shift the one segment that was dragged
                    segs = list(self._task_splits[uid])
                    idx  = self._drag_segment_idx
                    if 0 <= idx < len(segs):
                        new_s = segs[idx][0].addDays(delta)
                        new_e = segs[idx][1].addDays(delta)
                        # Check for overlap with adjacent segments
                        overlaps = any(
                            j != idx and new_s <= segs[j][1] and new_e >= segs[j][0]
                            for j in range(len(segs))
                        )
                        if overlaps:
                            task_name = str(task.getName()) if task.getName() else "Task"
                            dlg = _SegmentMergeDialog(task_name, self)
                            dlg.exec_()
                            if dlg.choice() == _SegmentMergeDialog.MERGE:
                                self.merge_task(task)
                                self.task_edited.emit()
                        else:
                            segs[idx] = (new_s, new_e)
                            self._task_splits[uid] = segs
                            self.task_edited.emit()
                else:
                    # Whole-task drag: also shift all split-segment dates
                    if uid is not None and uid in self._task_splits:
                        self._task_splits[uid] = [
                            (s.addDays(delta), e.addDays(delta))
                            for s, e in self._task_splits[uid]
                        ]
                    self.task_moved.emit(task, delta)
            self._drag_idx         = -1
            self._drag_delta_days  = 0
            self._drag_delta_hours = 0
            self._drag_segment_idx = -1
            self.setCursor(Qt.ArrowCursor)
            self.update()

    def contextMenuEvent(self, event):
        """Right-click context menu: Split Task / Merge Task."""
        if self._project is None or not self.project_start:
            return
        x = event.x()
        y = event.y()
        row = y // ROW_HEIGHT
        if row < 0 or row >= len(self.tasks):
            return
        task = self.tasks[row]
        # Don't show split/merge for summaries or milestones
        try:
            if bool(task.getSummary()) or bool(task.getMilestone()):
                return
        except Exception:
            return

        uid = self._uid_for_task(task)
        if uid is None:
            return

        has_splits = uid in self._task_splits and len(self._task_splits[uid]) >= 2

        menu = QMenu(self)
        act_split       = menu.addAction("Split Task\u2026")
        act_merge       = menu.addAction("Merge Task Segments") if has_splits else None
        act_assign_seg2 = menu.addAction("Assign second segment to resource\u2026") if has_splits else None

        chosen = menu.exec_(event.globalPos())
        if chosen is None:
            return

        if act_split and chosen == act_split:
            self._do_split_interactive(task, None)
        elif act_merge and chosen == act_merge:
            self._do_merge(task)
        elif act_assign_seg2 and chosen == act_assign_seg2:
            self._do_assign_segment_to_resource(task)

    def _do_split_interactive(self, task, default_date: QDate | None):
        """Show a date-picker dialog (pre-filled with default_date) then split."""
        start_qd  = _to_qdate(task.getStart())
        finish_qd = _compute_finish_date(task)
        if start_qd is None or finish_qd is None:
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("Split Task")
        layout = _QVBoxLayout(dlg)
        layout.addWidget(QLabel(f"Split task '{task.getName()}' at date:"))
        date_edit = QDateEdit(dlg)
        date_edit.setCalendarPopup(True)
        date_edit.setDisplayFormat("dd MMM yyyy")
        # Clamp default to valid range [start+1, finish-1]
        lo = start_qd.addDays(1)
        hi = finish_qd.addDays(-1)
        if lo > hi:
            lo = start_qd
            hi = finish_qd
        date_edit.setMinimumDate(lo)
        date_edit.setMaximumDate(hi)
        pick = default_date if (default_date and lo <= default_date <= hi) else lo
        date_edit.setDate(pick)
        layout.addWidget(date_edit)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, dlg)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        layout.addWidget(btns)
        if dlg.exec_() != QDialog.Accepted:
            return

        split_date = date_edit.date()
        if not self.split_task(task, split_date):
            from PyQt5.QtWidgets import QMessageBox  # type: ignore
            QMessageBox.warning(self, "Split Task",
                                "Cannot split the task at the selected date.\n"
                                "Choose a date within the task's span with at least 1 day on each side.")
        else:
            self.task_edited.emit()

    def _do_merge(self, task):
        """Remove all splits from task."""
        self.merge_task(task)
        self.task_edited.emit()

    def _do_assign_segment_to_resource(self, task):
        """Create a new task for the second segment and assign it to a user-chosen resource."""
        uid = self._uid_for_task(task)
        if uid is None or uid not in self._task_splits:
            return
        segs = self._task_splits[uid]
        if len(segs) < 2 or self._project is None:
            return
        resources = [r for r in self._project.getResources()
                     if r.getName() is not None and str(r.getName()) not in ('None', '')]
        if not resources:
            from PyQt5.QtWidgets import QMessageBox  # type: ignore
            QMessageBox.information(self, "No Resources",
                                    "No resources are defined in this project.")
            return
        from PyQt5.QtWidgets import QListWidget  # type: ignore
        dlg = QDialog(self)
        dlg.setWindowTitle("Assign Second Segment to Resource")
        lay = _QVBoxLayout(dlg)
        lay.addWidget(QLabel("Select resource for the second segment:"))
        list_w = QListWidget(dlg)
        for r in resources:
            list_w.addItem(str(r.getName()))
        list_w.setCurrentRow(0)
        lay.addWidget(list_w)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel, dlg)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)
        if dlg.exec_() != QDialog.Accepted:
            return
        row = list_w.currentRow()
        if row < 0 or row >= len(resources):
            return
        chosen_res = resources[row]
        seg1_start, seg1_end = segs[0]
        seg2_start, seg2_end = segs[1]
        orig_start_qd = _to_qdate(task.getStart())
        if orig_start_qd is None:
            return
        self._push_history()
        try:
            new_task = self._project.addTask()
            new_task.setName(str(task.getName() or "") + " (Part 2)")
            delta_s = orig_start_qd.daysTo(seg2_start)
            delta_e = orig_start_qd.daysTo(seg2_end) + 1
            new_task.setStart(task.getStart().plusDays(delta_s))
            new_task.setFinish(task.getStart().plusDays(delta_e))
            try:
                new_task.addResourceAssignment(chosen_res)
            except Exception:
                pass
            # Update original task finish to end of segment 1
            task.setFinish(task.getStart().plusDays(orig_start_qd.daysTo(seg1_end) + 1))
            # Remove segment 2 from the splits dict
            remaining = segs[:1] if len(segs) == 2 else segs[:1] + segs[2:]
            if len(remaining) < 2:
                del self._task_splits[uid]
            else:
                self._task_splits[uid] = remaining
            self.task_edited.emit()
        except Exception as exc:
            from PyQt5.QtWidgets import QMessageBox  # type: ignore
            QMessageBox.warning(self, "Error",
                                f"Could not create task for second segment:\n{exc}")

    def _push_history(self):
        """Push undo snapshot via the parent chain if history_manager is available."""
        try:
            w = self.parent()
            while w is not None:
                if hasattr(w, '_history') and hasattr(w._history, 'push'):
                    view_name = getattr(w, '_active_history_view', lambda: 'tasks')()
                    w._history.push(view_name)
                    return
                w = w.parent() if callable(getattr(w, 'parent', None)) else None
        except Exception:
            pass

    def _canvas_width(self) -> int:
        """Total canvas pixel width for the current zoom mode."""
        if not self.project_start:
            return 400
        if self.day_width >= HOUR_MODE_THRESHOLD:
            eff_span = 24 if self._show_off_hours else self._clock_day_span
            wdays = working_day_count(self.project_start, self.total_days)
            return max(400, LABEL_WIDTH + wdays * eff_span * self.day_width)
        vis = _date_to_col(self.project_start,
                           self.project_start.addDays(self.total_days),
                           self.show_sundays)
        return max(400, LABEL_WIDTH + vis * self.day_width)

    def _apply_size(self):
        w = self._canvas_width()
        h = max(200, len(self.tasks) * ROW_HEIGHT + 20)
        self.setFixedSize(QSize(w, h))

    def sizeHint(self):
        w = self._canvas_width()
        h = max(200, len(self.tasks) * ROW_HEIGHT + 20)
        return QSize(w, h)

    # ---------------------------------------------------------------- #
    # Paint                                                             #
    # ---------------------------------------------------------------- #

    def paintEvent(self, event):
        if not self.project_start:
            return
        painter  = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        n_rows   = len(self.tasks)
        total_w  = self._canvas_width()
        is_hourly = self.day_width >= HOUR_MODE_THRESHOLD

        # 1. Alternating row backgrounds (even=white, odd=light-blue to match task_view)
        for i in range(n_rows):
            bg = QColor(255, 255, 255) if i % 2 == 0 else QColor(240, 245, 255)
            painter.fillRect(0, i * ROW_HEIGHT, total_w, ROW_HEIGHT, bg)

        if is_hourly:
            # 2h. Hourly column shading: break/off-hour slots get a grey overlay
            if self._show_off_hours:
                eff_start = 0
                eff_span  = 24
                working_set = frozenset(range(self._work_hour_start, self._work_hour_end)) - self._non_working_slots
                off_slots   = frozenset(range(24)) - working_set
            else:
                eff_start = self._work_hour_start
                eff_span  = self._clock_day_span
                off_slots  = self._non_working_slots
            wday = 0
            for di in range(self.total_days):
                d = self.project_start.addDays(di)
                if d.dayOfWeek() in (6, 7):
                    continue
                is_holiday = d.toString(Qt.ISODate) in self._non_working_dates
                for hi in range(eff_span):
                    hour = eff_start + hi
                    hx   = LABEL_WIDTH + (wday * eff_span + hi) * self.day_width
                    if is_holiday or hour in off_slots:
                        for ri in range(n_rows):
                            if is_holiday:
                                c = QColor(232, 232, 232) if ri % 2 == 0 else QColor(222, 222, 222)
                            else:
                                c = QColor(225, 225, 230) if ri % 2 == 0 else QColor(215, 215, 225)
                            painter.fillRect(hx, ri * ROW_HEIGHT, self.day_width, ROW_HEIGHT, c)
                    painter.setPen(QPen(QColor(220, 228, 242), 1))
                    painter.drawLine(hx, 0, hx, n_rows * ROW_HEIGHT)
                # Day boundary: slightly darker line
                dx = LABEL_WIDTH + wday * eff_span * self.day_width
                painter.setPen(QPen(QColor(140, 175, 215), 1))
                painter.drawLine(dx, 0, dx, n_rows * ROW_HEIGHT)
                wday += 1
        else:
            # 2. Column shading: Saturday/holidays (grey), Sunday (blue-tint)
            col = 0
            for d in range(self.total_days):
                date = self.project_start.addDays(d)
                dow  = date.dayOfWeek()
                if not self.show_sundays and dow == 7:
                    continue
                x   = LABEL_WIDTH + col * self.day_width
                col += 1
                iso = date.toString(Qt.ISODate)
                if dow == 6 or iso in self._non_working_dates:
                    # Opaque alternating grey — overrides the blue row background entirely
                    for i in range(n_rows):
                        row_bg = QColor(232, 232, 232) if i % 2 == 0 else QColor(222, 222, 222)
                        painter.fillRect(x, i * ROW_HEIGHT, self.day_width, ROW_HEIGHT, row_bg)
                elif dow == 7:
                    painter.fillRect(x, 0, self.day_width, n_rows * ROW_HEIGHT,
                                     QColor(205, 215, 235, 140))  # Sunday: blue-tint

        # 3. Task bars + dependency arrows
        bar_rects = []
        self._split_seg_rects = []
        for i, task in enumerate(self.tasks):
            bar_rects.append(self._draw_task_row(painter, i, task))
        self._bar_rects = bar_rects
        self._draw_dependency_arrows(painter, bar_rects)
        # Drag: dashed outline at drag position (skipped for split tasks – segments show movement)
        if self._drag_idx >= 0 and self._drag_idx < len(bar_rects):
            _, x1, x2, by, bh = bar_rects[self._drag_idx]
            if x1 is not None:
                drag_task = self.tasks[self._drag_idx] if self._drag_idx < len(self.tasks) else None
                drag_uid  = self._uid_for_task(drag_task) if drag_task else None
                if drag_uid is None or drag_uid not in self._task_splits:
                    painter.setPen(QPen(QColor(255, 140, 0), 2, Qt.DashLine))
                    painter.setBrush(Qt.NoBrush)
                    painter.drawRect(x1 - 2, by - 2, (x2 - x1) + 4, bh + 4)

        # Container finish lines: dashed vertical from wedge-tip through children
        # Summary bar geometry (must match _draw_task_row):
        #   bar_top  = bar_y + 3
        #   thin_h   = 7   (height of horizontal strip)
        #   tri_h    = 10  (wedge depth)
        #   wedge tip Y = bar_y + 3 + 7 + 10 = bar_y + 20
        _WEDGE_TIP_OFFSET = 20   # bar_y + this = right-wedge tip Y
        tid_to_row = {}
        for i, t in enumerate(self.tasks):
            try:
                tid_to_row[int(str(t.getID()))] = i
            except Exception:
                pass

        for i, task in enumerate(self.tasks):
            try:
                if not task.getSummary():
                    continue
            except Exception:
                continue
            _, sx1, sx2, sbar_y, sbar_h = bar_rects[i]
            if sx2 is None:
                continue
            # Descend to find the deepest visible child row
            last_row = i
            def _collect_last(t):
                nonlocal last_row
                try:
                    for ch in t.getChildTasks():
                        try:
                            cid = int(str(ch.getID()))
                            if cid in tid_to_row:
                                last_row = max(last_row, tid_to_row[cid])
                            _collect_last(ch)
                        except Exception:
                            pass
                except Exception:
                    pass
            _collect_last(task)
            tip_y    = sbar_y + _WEDGE_TIP_OFFSET
            bottom_y = last_row * ROW_HEIGHT + ROW_HEIGHT
            if bottom_y > tip_y:
                painter.setPen(QPen(QColor(40, 40, 40), 1, Qt.DashLine))
                painter.setBrush(Qt.NoBrush)
                painter.drawLine(sx2, tip_y, sx2, bottom_y)

        # Today line: bold green vertical through full canvas
        today = QDate.currentDate()
        if self.project_start and today >= self.project_start:
            if is_hourly:
                eff_span  = 24 if self._show_off_hours else self._clock_day_span
                eff_start = 0  if self._show_off_hours else self._work_hour_start
                wday = date_to_working_day_idx(today, self.project_start)
                cur_hour = QTime.currentTime().hour()
                if not self._show_off_hours:
                    cur_hour = max(eff_start, min(eff_start + eff_span - 1, cur_hour))
                tx = LABEL_WIDTH + (wday * eff_span + (cur_hour - eff_start)) * self.day_width
            else:
                tc = _date_to_col(self.project_start, today, self.show_sundays)
                tx = LABEL_WIDTH + tc * self.day_width
            painter.setPen(QPen(QColor(0, 168, 0), 2, Qt.SolidLine))
            painter.drawLine(tx, 0, tx, n_rows * ROW_HEIGHT)

        painter.end()

    # ---------------------------------------------------------------- #
    # Calendar header                                                   #
    # ---------------------------------------------------------------- #

    def _draw_header(self, painter):
        n_rows  = len(self.tasks)
        total_h = HEADER_HEIGHT + n_rows * ROW_HEIGHT
        total_w = LABEL_WIDTH + self.total_days * self.day_width

        # Left label area header
        painter.fillRect(0, 0, LABEL_WIDTH, HEADER_HEIGHT, QColor(236, 243, 251))
        painter.setPen(QPen(QColor(150, 180, 220), 1))
        painter.drawLine(LABEL_WIDTH, 0, LABEL_WIDTH, total_h)

        font_bold  = QFont("Segoe UI", 9, QFont.Bold)
        font_small = QFont("Segoe UI", 7)

        # ---- Top row: month names ----
        d = 0
        while d < self.total_days:
            date          = self.project_start.addDays(d)
            end_of_month  = QDate(date.year(), date.month(), date.daysInMonth())
            span          = min(date.daysTo(end_of_month) + 1, self.total_days - d)
            x             = LABEL_WIDTH + d * self.day_width
            month_px      = span * self.day_width
            bg = QColor(210, 228, 252) if date.month() % 2 == 0 else QColor(195, 215, 245)
            painter.fillRect(x, 0, month_px, HEADER_MONTH_H, bg)
            painter.setPen(QColor(26, 63, 122))
            painter.setFont(font_bold)
            label = date.toString("MMM yyyy") if month_px > 64 else date.toString("MMM")
            painter.drawText(QRect(x + 3, 0, month_px - 6, HEADER_MONTH_H),
                             Qt.AlignVCenter | Qt.AlignLeft, label)
            # left border of month
            painter.setPen(QPen(QColor(140, 175, 215), 1))
            painter.drawLine(x, 0, x, HEADER_HEIGHT + n_rows * ROW_HEIGHT)
            d += span

        # ---- Bottom row: day numbers + weekend shading ----
        painter.setFont(font_small)
        for d in range(self.total_days):
            date = self.project_start.addDays(d)
            x    = LABEL_WIDTH + d * self.day_width

            # Weekend shading across the full chart height
            if date.dayOfWeek() in (6, 7):
                painter.fillRect(x, HEADER_HEIGHT, self.day_width,
                                 n_rows * ROW_HEIGHT, QColor(238, 243, 252))

            # Day cell background
            bg = QColor(230, 240, 254) if date.dayOfWeek() == 1 else QColor(242, 247, 255)
            painter.fillRect(x, HEADER_MONTH_H, self.day_width, HEADER_WEEK_H, bg)

            # Day number (only if there is room)
            if self.day_width >= 14:
                painter.setPen(QColor(80, 100, 140))
                painter.drawText(QRect(x, HEADER_MONTH_H, self.day_width, HEADER_WEEK_H),
                                 Qt.AlignCenter, str(date.day()))
            elif self.day_width >= 8 and date.dayOfWeek() == 1:
                # Show "Wnn" on Monday only when very zoomed out
                painter.setPen(QColor(80, 100, 140))
                painter.drawText(QRect(x, HEADER_MONTH_H, self.day_width * 5, HEADER_WEEK_H),
                                 Qt.AlignLeft | Qt.AlignVCenter,
                                 f"W{date.weekNumber()[0]}")

            # Thin vertical grid
            painter.setPen(QPen(QColor(215, 225, 240), 1))
            painter.drawLine(x, HEADER_HEIGHT, x, total_h)

        # Heavy bottom border below header
        painter.setPen(QPen(QColor(43, 87, 154), 2))
        painter.drawLine(0, HEADER_HEIGHT, total_w, HEADER_HEIGHT)

    # ---------------------------------------------------------------- #
    # Task row + bar                                                    #
    # ---------------------------------------------------------------- #

    def _draw_task_row(self, painter, row, task):
        """Draws one row's bar; row backgrounds and column shading handled in paintEvent."""
        y = row * ROW_HEIGHT
        # Mini task name label
        if LABEL_WIDTH > 0:
            name = str(task.getName()) if task.getName() else ""
            painter.setPen(Qt.black)
            painter.setFont(QFont("Segoe UI", 8))
            painter.drawText(QRect(4, y, LABEL_WIDTH - 8, ROW_HEIGHT), Qt.AlignVCenter, name)

        start_date  = _to_qdate(task.getStart())
        if not start_date:
            return (row, None, None, None, None)

        # Primary: MPXJ's finish already respects the project calendar
        # (weekends + public holidays defined in the .mpp file).
        # Fall back to a weekend-aware manual calculation only when absent.
        finish_date = _to_qdate(task.getFinish())
        if finish_date is None:
            try:
                dur = task.getDuration()
                if dur is not None:
                    dur_val = float(str(dur.getDuration()))
                    unit_str = str(dur.getUnits()) if dur.getUnits() is not None else "DAYS"
                    if "HOUR" in unit_str.upper():
                        dur_val /= 8.0
                    elif "WEEK" in unit_str.upper():
                        dur_val *= 5.0
                    elif "MONTH" in unit_str.upper():
                        dur_val *= 20.0
                    finish_date = _add_working_days(start_date, max(1, dur_val))
            except Exception:
                pass
        if not finish_date:
            return (row, None, None, None, None)

        is_dragged = (row == self._drag_idx)
        if self.day_width >= HOUR_MODE_THRESHOLD:
            # ── Hourly mode: use actual task start/finish times ──────────────
            java_start  = task.getStart()
            java_finish = task.getFinish()
            x1 = LABEL_WIDTH + int(datetime_to_hourly_x(java_start,  self.project_start, self.day_width,
                                          self._work_hour_start, self._clock_day_span,
                                          self._show_off_hours))
            x2 = LABEL_WIDTH + int(datetime_to_hourly_x(java_finish, self.project_start, self.day_width,
                                          self._work_hour_start, self._clock_day_span,
                                          self._show_off_hours))
            if is_dragged and self._drag_delta_hours != 0:
                x1 += self._drag_delta_hours * self.day_width
                x2 += self._drag_delta_hours * self.day_width
            bar_w = max(x2 - x1, self.day_width)
            # Baseline strip (date-only, positional enough for hourly view)
            try:
                if self._show_baseline_bars:
                    b1 = _to_qdate(self._get_baseline_start(task))
                    b2 = _to_qdate(self._get_baseline_finish(task))
                    if b1 and b2:
                        bx1 = LABEL_WIDTH + int(datetime_to_hourly_x(
                            self._get_baseline_start(task), self.project_start, self.day_width,
                            self._work_hour_start, self._clock_day_span, self._show_off_hours))
                        bx2 = LABEL_WIDTH + int(datetime_to_hourly_x(
                            self._get_baseline_finish(task), self.project_start, self.day_width,
                            self._work_hour_start, self._clock_day_span, self._show_off_hours))
                        painter.fillRect(bx1, y + ROW_HEIGHT - 8 + ROW_HEIGHT - 8 - BASELINE_THICK,
                                         max(bx2 - bx1, self.day_width), BASELINE_THICK * 2,
                                         QColor(80, 80, 200, 160))
            except Exception:
                pass
        else:
            # ── Day mode (original logic) ──────────────────────────────────
            orig_col_s = _date_to_col(self.project_start, start_date,  self.show_sundays)
            orig_col_f = _date_to_col(self.project_start, finish_date, self.show_sundays)
            if is_dragged and self._drag_delta_days != 0:
                dragged_start = start_date.addDays(self._drag_delta_days)
                snap_col_s = _date_to_col(self.project_start, dragged_start, self.show_sundays)
                snap_col_f = snap_col_s + (orig_col_f - orig_col_s)
                x1 = LABEL_WIDTH + snap_col_s * self.day_width
                x2 = LABEL_WIDTH + snap_col_f * self.day_width
            else:
                x1 = LABEL_WIDTH + orig_col_s * self.day_width
                x2 = LABEL_WIDTH + orig_col_f * self.day_width
            bar_w = max(x2 - x1, self.day_width)
            # Baseline strip
            try:
                if self._show_baseline_bars:
                    b1 = _to_qdate(self._get_baseline_start(task))
                    b2 = _to_qdate(self._get_baseline_finish(task))
                    if b1 and b2:
                        bx1 = LABEL_WIDTH + _date_to_col(self.project_start, b1, self.show_sundays) * self.day_width
                        bx2 = LABEL_WIDTH + _date_to_col(self.project_start, b2, self.show_sundays) * self.day_width
                        painter.fillRect(bx1, y + ROW_HEIGHT - 8 - BASELINE_THICK,
                                         max(bx2 - bx1, self.day_width), BASELINE_THICK * 2,
                                         QColor(80, 80, 200, 160))
            except Exception:
                pass

        _tid = task.getID()
        is_critical = (int(str(_tid)) in self._critical_ids) if (_tid is not None and str(_tid) not in ('null', 'None', '')) else False
        bar_h = ROW_HEIGHT - 8
        bar_y = y + 4
        is_summary = False
        try:
            is_summary = bool(task.getSummary())
        except Exception:
            pass
        is_milestone = False
        try:
            is_milestone = bool(task.getMilestone())
        except Exception:
            pass

        if is_milestone:
            # MS Project-style black diamond milestone
            mid_x = x1 + bar_w // 2
            mid_y = bar_y + bar_h // 2
            s     = bar_h // 2
            diamond = QPolygon([
                QPoint(mid_x,     mid_y - s),
                QPoint(mid_x + s, mid_y),
                QPoint(mid_x,     mid_y + s),
                QPoint(mid_x - s, mid_y),
            ])
            painter.setBrush(QBrush(QColor(20, 20, 20)))
            painter.setPen(QPen(QColor(0, 0, 0), 1))
            painter.drawPolygon(diamond)
        elif is_summary:
            # MS Project-style summary bracket bar: thin dark bar with downward wedges at each end
            bar_dark = QColor(40, 40, 40)
            thin_h   = 7    # height of the horizontal strip
            tri_w    = 9    # base width of each downward wedge
            tri_h    = 10   # how far below the strip the wedge tip drops
            bar_top  = bar_y + 3
            x_right  = x1 + bar_w

            painter.setBrush(QBrush(bar_dark))
            painter.setPen(Qt.NoPen)
            # Horizontal bar
            painter.drawRect(x1, bar_top, bar_w, thin_h)
            # Left downward wedge
            painter.drawPolygon(QPolygon([
                QPoint(x1,              bar_top + thin_h),
                QPoint(x1 + tri_w,      bar_top + thin_h),
                QPoint(x1,              bar_top + thin_h + tri_h),
            ]))
            # Right downward wedge
            painter.drawPolygon(QPolygon([
                QPoint(x_right,         bar_top + thin_h),
                QPoint(x_right - tri_w, bar_top + thin_h),
                QPoint(x_right,         bar_top + thin_h + tri_h),
            ]))
            painter.setPen(Qt.NoPen)
        else:
            # Check for split segments
            uid = self._uid_for_task(task)
            segments = self._task_splits.get(uid) if uid is not None else None

            if segments and len(segments) >= 2:
                drag_delta = self._drag_delta_hours if self.day_width >= HOUR_MODE_THRESHOLD else self._drag_delta_days
                return self._draw_split_segments(painter, row, task, bar_y, bar_h,
                                                 is_critical, segments, uid,
                                                 is_dragged, self._drag_segment_idx, drag_delta)

            # Regular task – flat bar, no color change for progress
            color = QColor(255, 120, 100) if is_critical else QColor(157, 195, 230)
            painter.fillRect(x1, bar_y, bar_w, bar_h, color)
            painter.setBrush(Qt.NoBrush)   # prevent dark summary brush from leaking
            painter.setPen(QPen(color.darker(120), 1))
            painter.drawRect(x1, bar_y, bar_w, bar_h)

            # Progress: thin black line across the middle of the completed portion
            pct_val = 0.0
            try:
                pct_raw = task.getPercentageComplete()
                if pct_raw is not None:
                    pct_val = float(str(pct_raw).replace("%", "")) / 100.0
                    if pct_val > 0:
                        prog_w  = int(bar_w * min(pct_val, 1.0))
                        mid_y   = bar_y + bar_h // 2
                        painter.setPen(QPen(QColor(0, 0, 0), 2, Qt.SolidLine))
                        painter.drawLine(x1, mid_y, x1 + prog_w, mid_y)
            except Exception:
                pass

            # Warning icon if > 100 %
            if pct_val > 1.0:
                self._draw_warning_icon(painter, x1 + bar_w + 4, bar_y + 1, bar_h - 2)

            # Overallocation: orange border if any assignment exceeds resource max units
            overallocated = False
            res_label_parts = []
            try:
                for ass in task.getResourceAssignments():
                    res = ass.getResource()
                    if res is None:
                        continue
                    rname = str(res.getName()) if res.getName() is not None else ""
                    u = ass.getUnits()
                    u_val = float(str(u)) if u is not None else 100.0
                    max_u = res.getMaxUnits()
                    max_raw = float(str(max_u)) if max_u is not None else 100.0
                    # Normalize: MPXJ returns fraction (1.0=100%) for XML, percentage (100.0=100%) for MPP
                    max_val = max_raw * 100.0 if max_raw <= 2.0 else max_raw
                    if u_val > max_val:
                        overallocated = True
                    if rname:
                        if self.show_resource_units:
                            res_label_parts.append(f"{rname} [{int(u_val)}%]")
                        else:
                            res_label_parts.append(rname)
            except Exception:
                pass

            if overallocated:
                painter.setBrush(Qt.NoBrush)
                painter.setPen(QPen(QColor(220, 80, 0), 2))
                painter.drawRect(x1, bar_y, bar_w, bar_h)

            # Float bar overlay: translucent blue strip right of bar, sized to total float
            if self._show_float_bar and not is_critical:
                try:
                    _tid_int = int(str(task.getID()))
                    _fd = self._float_data.get(_tid_int)
                    if _fd:
                        total_flt = _fd.get("total_float")
                        if total_flt and total_flt.total_seconds() > 0:
                            float_days = total_flt.total_seconds() / 86400
                            float_px   = max(1, int(float_days * self.day_width))
                            float_rect = QRect(x1 + bar_w, bar_y + bar_h // 4,
                                               float_px, bar_h // 2)
                            painter.fillRect(float_rect, QColor(36, 113, 163, 60))
                            painter.setPen(QPen(QColor(36, 113, 163, 120), 1))
                            painter.setBrush(Qt.NoBrush)
                            painter.drawRect(float_rect)
                except Exception:
                    pass

            # Resource name label to the right of the bar (MS Project style – name only)
            if res_label_parts and self.day_width >= 6:
                label_x = x1 + bar_w + (4 if not (pct_val > 1.0) else bar_h + 8)
                label_text = ", ".join(res_label_parts)
                painter.setPen(QColor(40, 40, 40))
                painter.setFont(QFont("Segoe UI", 8))
                painter.drawText(QRect(label_x, bar_y, 200, bar_h),
                                 Qt.AlignVCenter | Qt.AlignLeft, label_text)

        return (row, x1, x1 + bar_w, bar_y, bar_h)

    # ---------------------------------------------------------------- #
    # Split segment rendering                                           #
    # ---------------------------------------------------------------- #

    def _draw_split_segments(self, painter, row, task, bar_y, bar_h,
                              is_critical, segments, uid=None,
                              is_dragged=False, drag_seg_idx=-1, drag_delta=0):
        """Draw multiple coloured bars with dashed gaps between them.
        Returns the tuple (row, x1_of_first, x2_of_last, bar_y, bar_h) for
        dependency-arrow anchoring (same format as _draw_task_row return value).
        """
        if not segments:
            return (row, None, None, None, None)

        first_x1 = None
        last_x2  = None
        color = QColor(255, 120, 100) if is_critical else QColor(157, 195, 230)

        for i, (seg_start_orig, seg_end_orig) in enumerate(segments):
            # Original (undragged) position for per-segment hit-test cache
            col_s_o = _date_to_col(self.project_start, seg_start_orig, self.show_sundays)
            col_e_o = _date_to_col(self.project_start, seg_end_orig,   self.show_sundays)
            x1_o = LABEL_WIDTH + col_s_o * self.day_width
            x2_o = LABEL_WIDTH + (col_e_o + 1) * self.day_width
            bw_o = max(x2_o - x1_o, self.day_width)
            if uid is not None:
                self._split_seg_rects.append({
                    'task_idx': row, 'uid': uid, 'seg_idx': i,
                    'x1': x1_o, 'x2': x1_o + bw_o,
                    'bar_y': bar_y, 'bar_h': bar_h,
                })

            # Render position: apply drag delta when this segment is moving
            if is_dragged and drag_delta != 0 and (drag_seg_idx < 0 or drag_seg_idx == i):
                seg_start = seg_start_orig.addDays(drag_delta)
                seg_end   = seg_end_orig.addDays(drag_delta)
                col_s = _date_to_col(self.project_start, seg_start, self.show_sundays)
                col_e = _date_to_col(self.project_start, seg_end,   self.show_sundays)
            else:
                col_s, col_e = col_s_o, col_e_o
            x1 = LABEL_WIDTH + col_s * self.day_width
            x2 = LABEL_WIDTH + (col_e + 1) * self.day_width
            bar_w = max(x2 - x1, self.day_width)

            # Draw segment bar
            painter.fillRect(x1, bar_y, bar_w, bar_h, color)
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(color.darker(120), 1))
            painter.drawRect(x1, bar_y, bar_w, bar_h)

            # Dashed connecting line between segments (in the gap)
            if i > 0 and last_x2 is not None and x1 > last_x2:
                mid_y = bar_y + bar_h // 2
                painter.setPen(QPen(QColor(100, 140, 190), 2, Qt.DashLine))
                painter.drawLine(last_x2, mid_y, x1, mid_y)
                painter.setPen(QPen(QColor(80, 110, 160), 1))
                painter.drawLine(last_x2, bar_y, last_x2, bar_y + bar_h)
                painter.drawLine(x1,      bar_y, x1,      bar_y + bar_h)

            if first_x1 is None:
                first_x1 = x1
            last_x2 = x1 + bar_w

        return (row, first_x1, last_x2, bar_y, bar_h)

    def _draw_warning_icon(self, painter, x, y, size):
        """Yellow triangle with '!' for tasks > 100 % complete."""
        s = size
        tri = QPolygon([
            QPoint(x + s // 2, y),
            QPoint(x + s,      y + s),
            QPoint(x,          y + s),
        ])
        painter.setBrush(QBrush(QColor(255, 200, 0)))
        painter.setPen(QPen(QColor(160, 110, 0), 1))
        painter.drawPolygon(tri)
        painter.setPen(QPen(QColor(90, 50, 0), 1))
        painter.setFont(QFont("Segoe UI", max(6, s - 5), QFont.Bold))
        painter.drawText(QRect(x, y + 1, s, s - 1), Qt.AlignCenter, "!")

    # ---------------------------------------------------------------- #
    # Dependency arrows                                                 #
    # ---------------------------------------------------------------- #

    def _draw_dependency_arrows(self, painter, bar_rects):
        """Elbow-line arrows from predecessor bar finish â†’ successor bar start."""
        if not self.project_start:
            return
        # Build task-id â†’ bar_rect map
        id_map = {}
        for task, br in zip(self.tasks, bar_rects):
            tid = task.getID()
            if tid is not None and br[1] is not None:
                id_map[int(str(tid))] = br   # (row, x1, x2, bar_y, bar_h)

        pen = QPen(QColor(30, 30, 30), 1, Qt.SolidLine)
        pen.setCapStyle(Qt.RoundCap)

        for task, br in zip(self.tasks, bar_rects):
            if br[1] is None:
                continue
            _, x1, x2, bar_y, bar_h = br
            try:
                preds = task.getPredecessors()
                if not preds:
                    continue
                for rel in preds:
                    pred_task = rel.getPredecessorTask()
                    if pred_task is None:
                        continue
                    pid = int(str(pred_task.getID()))
                    if pid not in id_map:
                        continue
                    _, px1, px2, p_bar_y, p_bar_h = id_map[pid]
                    pred_mid_y = p_bar_y + p_bar_h // 2

                    if bar_y >= p_bar_y:
                        # --- Successor BELOW: exit bottom-right → down → horizontal → ↓ into succ top ---
                        pred_exit_y = p_bar_y + p_bar_h
                        enter_y     = bar_y
                        approach_y  = enter_y - 5
                        painter.setPen(pen)
                        painter.drawLine(px2, pred_exit_y, px2, approach_y)
                        painter.drawLine(px2, approach_y,  x1,  approach_y)
                        painter.drawLine(x1,  approach_y,  x1,  enter_y)
                        # Downward arrowhead at top of successor bar
                        ah = 4
                        painter.setBrush(QBrush(QColor(20, 20, 20)))
                        painter.setPen(Qt.NoPen)
                        painter.drawPolygon(QPolygon([
                            QPoint(x1,      enter_y),
                            QPoint(x1 - ah, enter_y - ah),
                            QPoint(x1 + ah, enter_y - ah),
                        ]))
                    else:
                        # --- Successor ABOVE: exit top-right → straight up → horizontal → ↑ into succ bottom ---
                        pred_exit_y = p_bar_y
                        enter_y     = bar_y + bar_h
                        approach_y  = enter_y + 5
                        painter.setPen(pen)
                        painter.drawLine(px2, pred_exit_y, px2, approach_y)
                        painter.drawLine(px2, approach_y,  x1,  approach_y)
                        painter.drawLine(x1,  approach_y,  x1,  enter_y)
                        # Upward arrowhead at bottom of successor bar
                        ah = 4
                        painter.setBrush(QBrush(QColor(20, 20, 20)))
                        painter.setPen(Qt.NoPen)
                        painter.drawPolygon(QPolygon([
                            QPoint(x1,      enter_y),
                            QPoint(x1 - ah, enter_y + ah),
                            QPoint(x1 + ah, enter_y + ah),
                        ]))
                    painter.setBrush(Qt.NoBrush)
                    painter.setPen(pen)
            except Exception:
                pass


class GanttView(QWidget):
    """Fixed calendar header + scrollable row canvas."""

    task_moved   = pyqtSignal(object, int)   # forwarded from canvas
    zoom_changed = pyqtSignal(int)           # forwarded from canvas (day_width)
    task_edited  = pyqtSignal()              # forwarded from canvas

    def __init__(self, parent=None):
        super().__init__(parent)
        self.canvas = GanttCanvas()
        self.canvas.task_moved.connect(self.task_moved)
        self.canvas.zoom_changed.connect(self.zoom_changed)
        self.canvas.task_edited.connect(self.task_edited)

        # Fixed calendar header — scrolls only horizontally in sync with canvas
        self._header      = GanttHeader()
        self._hour_header = HourModeHeader(HEADER_HEIGHT, HEADER_MONTH_H, HEADER_WEEK_H)
        self._header_area = QScrollArea()
        self._header_area.setWidget(self._header)
        self._header_area.setWidgetResizable(False)
        self._header_area.setFixedHeight(HEADER_HEIGHT)
        self._header_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._header_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._header_area.setFrameShape(QFrame.NoFrame)

        # Scrollable canvas (rows only — no vertical scrollbar shown here)
        self._scroll_area = QScrollArea()
        self._scroll_area.setWidget(self.canvas)
        self._scroll_area.setWidgetResizable(False)
        self._scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        self._scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._scroll_area.setFrameShape(QFrame.NoFrame)

        # Keep header horizontally in sync with canvas
        self._scroll_area.horizontalScrollBar().valueChanged.connect(
            self._header_area.horizontalScrollBar().setValue
        )

        # --- Navigation buttons (Gantt view only) ---
        self._nav_bar = QWidget()
        self._nav_bar.setFixedHeight(NAV_BAR_HEIGHT)
        nav_layout = QHBoxLayout(self._nav_bar)
        nav_layout.setContentsMargins(2, 1, 2, 1)
        nav_layout.setSpacing(4)

        def _nav_btn(label, tip, slot):
            b = QToolButton()
            b.setText(label)
            b.setToolTip(tip)
            b.setFixedHeight(20)
            b.clicked.connect(slot)
            nav_layout.addWidget(b)
            return b

        _nav_btn("◀◀ First",  "Jump to 1 week before the first task",   self._scroll_to_first)
        _nav_btn("◀ Today",   "Jump to 1 week before today",             self._scroll_to_today)
        _nav_btn("Last ▶▶",   "Jump to 1 week before the last task end", self._scroll_to_last)
        nav_layout.addStretch()
        self._nav_bar.setStyleSheet(
            "QWidget { background: #EAF0FB; border-bottom: 1px solid #B0C8E0; }"
            "QToolButton { background: #D0E0F8; border: 1px solid #9BBAD8; border-radius: 3px;"
            "              padding: 1px 6px; font-size: 11px; }"
            "QToolButton:hover { background: #B8D0F0; }"
            "QToolButton:pressed { background: #90B8E8; }"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._nav_bar)
        layout.addWidget(self._header_area)
        layout.addWidget(self._scroll_area)

        # Initialise header to default canvas state
        self._sync_header()

    def set_timeline_view(self, timeline_view):
        """Store a reference to the TimelineView so TaskDialog can show the checkbox."""
        self.canvas._timeline_view = timeline_view

    def verticalScrollBar(self):
        """Return the canvas scroll area's vertical scrollbar for external sync."""
        return self._scroll_area.verticalScrollBar()

    # ---------------------------------------------------------------- #
    # Navigation                                                        #
    # ---------------------------------------------------------------- #

    def scroll_to_date(self, qdate: QDate, margin_days: int = 7):
        """Scroll the Gantt horizontally so the given date is visible.

        Day mode  : scrolls so (qdate - margin_days) is at the left edge.
        Hourly mode: margin_days is ignored; instead scrolls so qdate lands
                     2 hour-slots from the left edge (or exact left edge when
                     margin_days==0, i.e. zoom-preserve calls).
        """
        if self.canvas.project_start is None:
            return
        c = self.canvas
        if c.day_width >= HOUR_MODE_THRESHOLD:
            eff_span = 24 if c._show_off_hours else c._clock_day_span
            wday_idx = date_to_working_day_idx(qdate, c.project_start)
            px = wday_idx * eff_span * c.day_width
            if margin_days > 0:
                px = max(0, px - 2 * c.day_width)   # 2 hour-slot margin before task
            else:
                px = max(0, px)
        else:
            target = qdate.addDays(-margin_days)
            col    = _date_to_col(c.project_start, target, c.show_sundays)
            px     = max(0, col * c.day_width)
        self._scroll_area.horizontalScrollBar().setValue(px)

    def _scroll_to_today(self):
        self.scroll_to_date(QDate.currentDate())

    def _scroll_to_first(self):
        if not self.canvas.tasks:
            return
        starts = [_to_qdate(t.getStart()) for t in self.canvas.tasks]
        starts = [s for s in starts if s]
        if starts:
            self.scroll_to_date(min(starts))

    def _scroll_to_last(self):
        if not self.canvas.tasks:
            return
        finishes = [_compute_finish_date(t) for t in self.canvas.tasks]
        finishes = [f for f in finishes if f]
        if finishes:
            self.scroll_to_date(max(finishes))

    def resizeEvent(self, event):
        super().resizeEvent(event)

    def showEvent(self, event):
        super().showEvent(event)

    def _sync_header(self):
        c = self.canvas
        if c.day_width >= HOUR_MODE_THRESHOLD and c.project_start:
            # Configure the hour header to the correct size BEFORE putting it in the
            # scroll area — this prevents a transient width mismatch that desyncs scroll
            if c._show_off_hours:
                eff_start = 0
                eff_span  = 24
                working_set = frozenset(range(c._work_hour_start, c._work_hour_end)) - c._non_working_slots
                off_slots   = frozenset(range(24)) - working_set
            else:
                eff_start = c._work_hour_start
                eff_span  = c._clock_day_span
                off_slots  = c._non_working_slots
            self._hour_header.configure(
                c.project_start, c.total_days, c.day_width,
                eff_start, eff_span, off_slots,
            )
            if self._header_area.widget() is not self._hour_header:
                self._header_area.takeWidget()
                self._header_area.setWidget(self._hour_header)
        else:
            # Configure the day header BEFORE putting it in the scroll area
            if c.project_start:
                self._header.configure(
                    c.project_start, c.total_days, c.day_width,
                    c.show_sundays, c._non_working_dates,
                )
            if self._header_area.widget() is not self._header:
                self._header_area.takeWidget()
                self._header_area.setWidget(self._header)
        # Re-sync header scroll position to canvas after any potential widget swap
        self._header_area.horizontalScrollBar().setValue(
            self._scroll_area.horizontalScrollBar().value()
        )

    def load_project(self, project, recompute_critical=False, preserve_scroll=False):
        self.canvas.load_project(project, recompute_critical=recompute_critical)
        self._sync_header()
        if not preserve_scroll:
            # Auto-scroll to 1 week before today so current work is visible
            from PyQt5.QtCore import QTimer  # type: ignore
            QTimer.singleShot(0, self._scroll_to_today)

    def _get_left_edge_date(self):
        """Return the QDate currently at the left edge of the visible canvas area,
        or None if no project is loaded.  Used to preserve the viewport position
        across zoom and data-refresh operations."""
        c = self.canvas
        if c.project_start is None or c.day_width == 0:
            return None
        scroll_px = self._scroll_area.horizontalScrollBar().value()
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

    def zoom_in(self):
        date = self._get_left_edge_date()
        self.canvas.zoom_in()
        self._sync_header()
        if date is not None:
            self.scroll_to_date(date, margin_days=0)

    def zoom_out(self):
        date = self._get_left_edge_date()
        self.canvas.zoom_out()
        self._sync_header()
        if date is not None:
            self.scroll_to_date(date, margin_days=0)

    def set_day_width(self, dw: int):
        date = self._get_left_edge_date()
        self.canvas.set_day_width(dw)
        self._sync_header()
        if date is not None:
            self.scroll_to_date(date, margin_days=0)

    def set_show_resource_units(self, value: bool):
        self.canvas.set_show_resource_units(value)

    def set_show_off_hours(self, value: bool):
        self.canvas.set_show_off_hours(value)
        self._sync_header()

    def set_zero_float_critical(self, value: bool):
        self.canvas.set_zero_float_critical(value)

    def set_show_sundays(self, value: bool):
        self.canvas.set_show_sundays(value)
        self._sync_header()

    def set_collapsed_ids(self, ids):
        self.canvas.set_collapsed_ids(ids)

    # ---------------------------------------------------------------- #
    # Split / Merge task public API (delegates to canvas)              #
    # ---------------------------------------------------------------- #

    def split_task(self, task, split_qdate: QDate) -> bool:
        return self.canvas.split_task(task, split_qdate)

    def merge_task(self, task) -> bool:
        return self.canvas.merge_task(task)

    def get_splits(self, task):
        return self.canvas.get_splits(task)

    def load_splits_from_project(self, project) -> None:
        self.canvas.load_splits_from_project(project)

    def clear_splits(self) -> None:
        self.canvas.clear_splits()

    def load_splits_from_dict(self, data: dict) -> None:
        self.canvas.load_splits_from_dict(data)

    def splits_to_dict(self) -> dict:
        return self.canvas.splits_to_dict()
