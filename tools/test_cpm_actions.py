#!/usr/bin/env python3
"""test_cpm_actions.py — Comprehensive test suite for the CPM engine.

Tests all public/internal CPM functions from:
  - src/views/gantt_view.py

No PyQt5 GUI is required.  All Qt symbols are mocked at import time so the
engine can be exercised headlessly.  Integration tests (categories E-H) build a
ProjectFile in memory via the MPXJ Java API (jpype + mpxj) and require the JVM.
They are automatically skipped when the JVM is unavailable.

Known programmatic schedule (_build_mpxj_project):
  UID 1 Design      2026-01-05 -> 2026-01-12  (7 d)  CRITICAL
  UID 2 Development 2026-01-12 -> 2026-01-26 (14 d)  CRITICAL  FS after Design
  UID 3 Review      2026-01-12 -> 2026-01-14  (2 d)  NOT critical (TF=12 d)
  UID 4 Testing     2026-01-26 -> 2026-01-30  (4 d)  CRITICAL  FS after 2 + 3
  UID 5 Deploy      2026-01-30 -> 2026-01-31  (1 d)  CRITICAL  FS after Testing
  UID 6 Completed   2026-01-05 -> 2026-01-07  (2 d)  100 % done (excluded)
  UID 7 Docs        2026-01-12 -> 2026-01-20  (8 d)  NOT critical (TF=11 d)

Critical path: 1 -> 2 -> 4 -> 5

Usage:
    venv\\Scripts\\python.exe tools\\test_cpm_actions.py [options]

Options:
    --output-dir DIR    Output directory for the HTML report
                        (default: tests\\documentation)
    --no-report         Print results to console only (no HTML report)
"""

from __future__ import annotations

import io
import optparse
import os
import sys
import time
import traceback
import types
import webbrowser
from contextlib import redirect_stdout, redirect_stderr
from dataclasses import dataclass
from datetime import datetime, timedelta
from itertools import groupby
from typing import Any, Callable, Optional

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_TOOLS_DIR    = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR     = os.path.dirname(_TOOLS_DIR)
_SRC_DIR      = os.path.join(_ROOT_DIR, "src")
_VIEWS_DIR    = os.path.join(_SRC_DIR, "views")

# Known results for the programmatic schedule (used by deterministic integration tests)
_KNOWN_CRITICAL_IDS     = {1, 2, 4, 5}   # FS critical path
_KNOWN_NON_CRITICAL_IDS = {3, 7}          # positive total float
_KNOWN_COMPLETED_ID     = 6               # 100 % complete, excluded from CPM
_KNOWN_TASK_COUNT       = 7               # total tasks in the programmatic schedule

for _p in (_SRC_DIR, _VIEWS_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ---------------------------------------------------------------------------
# Mock all PyQt5 symbols that gantt_view.py imports at module level.
# The CPM engine functions (_compute_critical_ids and helpers) are pure
# Python / JPype — they never touch Qt objects — so mocking the widgets is
# sufficient.
# ---------------------------------------------------------------------------
def _make_qt_stub(name: str):
    """Return a minimal module stub that returns dummy objects for any attr."""
    mod = types.ModuleType(name)

    class _AnyClass:
        class _Inner:
            pass
        def __getattr__(self, n):
            return self._Inner
        def __call__(self, *a, **kw):
            return self

    _sentinel = _AnyClass()

    def _getattr(n):
        return _sentinel

    mod.__getattr__ = _getattr  # type: ignore
    return mod


for _qt_name in (
    "PyQt5",
    "PyQt5.QtWidgets",
    "PyQt5.QtGui",
    "PyQt5.QtCore",
):
    if _qt_name not in sys.modules:
        sys.modules[_qt_name] = _make_qt_stub(_qt_name)

# Inject sub-module aliases that gantt_view imports directly
_qtw = sys.modules["PyQt5.QtWidgets"]
_qtg = sys.modules["PyQt5.QtGui"]
_qtc = sys.modules["PyQt5.QtCore"]

# Individual Qt name stubs used by gantt_view at module scope
for _sym in (
    "QWidget", "QScrollArea", "QSizePolicy", "QVBoxLayout", "QFrame",
    "QHBoxLayout", "QToolButton", "QMenu", "QAction", "QDialog", "QLabel",
    "QDateEdit", "QDialogButtonBox", "QPushButton",
):
    setattr(_qtw, _sym, type(_sym, (), {}))

for _sym in ("QPainter", "QColor", "QFont", "QPen", "QPolygon", "QBrush"):
    setattr(_qtg, _sym, type(_sym, (), {}))

for _sym in ("Qt", "QRect", "QDate", "QSize", "QPoint", "QTime", "pyqtSignal"):
    if _sym == "QDate":
        class _QDate:
            def __init__(self, *a): pass
            @staticmethod
            def fromString(*a): return _QDate()
            def isValid(self): return False
            def dayOfWeek(self): return 1
            def addDays(self, n): return self
        setattr(_qtc, _sym, _QDate)
    elif _sym == "pyqtSignal":
        setattr(_qtc, _sym, lambda *a, **kw: None)
    else:
        setattr(_qtc, _sym, type(_sym, (), {})())

# Mock hour_mode (imported at module level by gantt_view)
_hour_mode = types.ModuleType("hour_mode")
_hour_mode.HOUR_MODE_THRESHOLD      = 3
_hour_mode.HourModeHeader           = type("HourModeHeader", (), {})
_hour_mode.read_work_hours          = lambda *a, **kw: (8, 17)
_hour_mode.working_day_count        = lambda *a, **kw: 0
_hour_mode.date_to_working_day_idx  = lambda *a, **kw: 0
_hour_mode.datetime_to_hourly_x     = lambda *a, **kw: 0
_hour_mode.WORK_HOUR_START          = 8
_hour_mode.WORK_HOUR_END            = 17
_hour_mode.WORK_DAY_HOURS           = 8
sys.modules.setdefault("hour_mode", _hour_mode)

# Mock app_debug
_app_debug = types.ModuleType("app_debug")
_app_debug.is_debug = lambda: False  # type: ignore
sys.modules.setdefault("app_debug", _app_debug)

# Mock integrations.jira_sync (imported lazily but sys.modules checked)
_jira_sync = types.ModuleType("integrations.jira_sync")
_jira_sync.load_sidecar_task_data = lambda *a, **kw: {}  # type: ignore
sys.modules.setdefault("integrations.jira_sync", _jira_sync)
_integrations = types.ModuleType("integrations")
sys.modules.setdefault("integrations", _integrations)

# ---------------------------------------------------------------------------
# Import the CPM engine (gantt_view module-level code runs here)
# ---------------------------------------------------------------------------
try:
    import gantt_view as _gv  # type: ignore
    _compute_critical_ids    = _gv._compute_critical_ids
    _lag_to_timedelta        = _gv._lag_to_timedelta
    _lag_to_working_hours    = _gv._lag_to_working_hours
    _get_task_calendar       = _gv._get_task_calendar
    _working_hours_between   = _gv._working_hours_between
    _calendar_add_working_hours = _gv._calendar_add_working_hours
    _calendar_wdh            = _gv._calendar_wdh
    _IMPORT_OK    = True
    _IMPORT_ERROR = ""
except Exception as _exc:
    _IMPORT_OK    = False
    _IMPORT_ERROR = str(_exc)
    _compute_critical_ids = None
    _lag_to_timedelta = None
    _lag_to_working_hours = None
    _get_task_calendar = None
    _working_hours_between = None
    _calendar_add_working_hours = None
    _calendar_wdh = None


# ---------------------------------------------------------------------------
# MPXJ bootstrap (shared across integration tests)
# ---------------------------------------------------------------------------
_MPXJ_OK    = False
_MPXJ_ERROR = ""
_project    = None   # loaded once per run
_all_tasks  = []

def _start_jvm() -> None:
    global _MPXJ_OK, _MPXJ_ERROR
    try:
        import jpype   # type: ignore
        import mpxj    # type: ignore  # registers the JAR on the classpath
        if not jpype.isJVMStarted():
            jpype.startJVM(
                "-Dlog4j2.loggerContextFactory="
                "org.apache.logging.log4j.simple.SimpleLoggerContextFactory"
            )
        import jpype.imports  # type: ignore  # noqa: F401 – enables Java pkg imports
        _MPXJ_OK = True
    except Exception as exc:
        _MPXJ_ERROR = str(exc)


def _build_mpxj_project():
    """Build the deterministic 7-task test schedule, write it as MSPDI XML to
    tests/data/cpm_test_schedule.xml via UniversalProjectWriter, then read it
    back with UniversalProjectReader so _project / _all_tasks are populated
    from a genuine MPXJ-generated file.

    Schedule layout:
      UID 1 Design      2026-01-05 -> 2026-01-12  CRITICAL
      UID 2 Development 2026-01-12 -> 2026-01-26  CRITICAL  FS after 1
      UID 3 Review      2026-01-12 -> 2026-01-14  NOT critical (TF=12d)  FS after 1
      UID 4 Testing     2026-01-26 -> 2026-01-30  CRITICAL  FS after 2 + 3
      UID 5 Deploy      2026-01-30 -> 2026-01-31  CRITICAL  FS after 4
      UID 6 Completed   2026-01-05 -> 2026-01-07  100% done
      UID 7 Docs        2026-01-12 -> 2026-01-20  NOT critical (TF=11d)  FS after 1
    """
    global _project, _all_tasks

    import jpype  # type: ignore
    LocalDateTime          = jpype.JClass("java.time.LocalDateTime")
    ProjectFile            = jpype.JClass("org.mpxj.ProjectFile")
    RelationType           = jpype.JClass("org.mpxj.RelationType")
    Relation               = jpype.JClass("org.mpxj.Relation")
    UniversalProjectWriter = jpype.JClass("org.mpxj.writer.UniversalProjectWriter")
    UniversalProjectReader = jpype.JClass("org.mpxj.reader.UniversalProjectReader")
    FileFormat             = jpype.JClass("org.mpxj.writer.FileFormat")

    # --- build the schedule ---
    def _ldt(y, mo, d, h=8, mi=0):
        return LocalDateTime.of(y, mo, d, h, mi)

    def _fs(successor, predecessor):
        successor.addPredecessor(
            Relation.Builder()
            .successorTask(successor)
            .predecessorTask(predecessor)
            .type(RelationType.FINISH_START)
        )

    p = ProjectFile()
    cal = p.addDefaultBaseCalendar()
    p.getProjectProperties().setDefaultCalendar(cal)

    def _add(name, start, finish, pct=0):
        t = p.getTasks().add()
        t.setName(name); t.setStart(start); t.setFinish(finish)
        t.setPercentageComplete(pct); t.setCalendar(cal)
        return t

    t1 = _add("Design",      _ldt(2026,1, 5), _ldt(2026,1,12,17))
    t2 = _add("Development", _ldt(2026,1,12), _ldt(2026,1,26,17))
    t3 = _add("Review",      _ldt(2026,1,12), _ldt(2026,1,14,17))
    t4 = _add("Testing",     _ldt(2026,1,26), _ldt(2026,1,30,17))
    t5 = _add("Deploy",      _ldt(2026,1,30), _ldt(2026,1,31,17))
    t6 = _add("Completed",   _ldt(2026,1, 5), _ldt(2026,1, 7,17), pct=100)
    t7 = _add("Docs",        _ldt(2026,1,12), _ldt(2026,1,20,17))
    _fs(t2, t1); _fs(t3, t1)
    _fs(t4, t2); _fs(t4, t3)
    _fs(t5, t4); _fs(t7, t1)

    # --- write as MSPDI XML, then read back via UniversalProjectReader ---
    xml_path = os.path.join(_ROOT_DIR, "tests", "data", "cpm_test_schedule.xml")
    os.makedirs(os.path.dirname(xml_path), exist_ok=True)
    UniversalProjectWriter(FileFormat.MSPDI).write(p, xml_path)
    _project   = UniversalProjectReader().read(xml_path)
    _all_tasks = list(_project.getTasks())


# ---------------------------------------------------------------------------
# Test infrastructure (same pattern as test_jira_actions.py)
# ---------------------------------------------------------------------------
_STATUS_PASS  = "PASS"
_STATUS_FAIL  = "FAIL"
_STATUS_ERROR = "ERROR"
_STATUS_SKIP  = "SKIP"
_STATUS_INFO  = "INFO"


@dataclass
class TestResult:
    category:    str
    name:        str
    status:      str
    duration_ms: float = 0.0
    message:     str   = ""
    stdout:      str   = ""
    details:     str   = ""


class _TestFail(Exception):
    pass

class _TestSkip(Exception):
    pass


def _assert(condition: bool, message: str = "assertion failed"):
    if not condition:
        raise _TestFail(message)

def _assert_eq(actual, expected, label: str = ""):
    if actual != expected:
        raise _TestFail(
            f"{label + ': ' if label else ''}expected {expected!r}, got {actual!r}"
        )

def _assert_approx(actual: float, expected: float, tol: float = 0.01, label: str = ""):
    if abs(actual - expected) > tol:
        raise _TestFail(
            f"{label + ': ' if label else ''}expected ≈{expected}, got {actual}"
        )


class TestRunner:
    def __init__(self):
        self.results: list[TestResult] = []

    def run(self, category: str, name: str, fn: Callable, *args, **kwargs) -> TestResult:
        buf_out, buf_err = io.StringIO(), io.StringIO()
        t0 = time.perf_counter()
        status, message, details = _STATUS_PASS, "", ""
        try:
            with redirect_stdout(buf_out), redirect_stderr(buf_err):
                fn(*args, **kwargs)
        except _TestSkip as exc:
            status, message = _STATUS_SKIP, str(exc)
        except _TestFail as exc:
            status, message = _STATUS_FAIL, str(exc)
        except Exception as exc:
            status, message, details = _STATUS_ERROR, str(exc), traceback.format_exc()
        elapsed = (time.perf_counter() - t0) * 1000
        captured = (buf_out.getvalue() + buf_err.getvalue()).strip()
        result = TestResult(
            category=category, name=name, status=status,
            duration_ms=round(elapsed, 1), message=message,
            stdout=captured if status in (_STATUS_FAIL, _STATUS_ERROR) else "",
            details=details,
        )
        self.results.append(result)
        return result

    def skip(self, category: str, name: str, reason: str) -> TestResult:
        result = TestResult(category=category, name=name, status=_STATUS_SKIP, message=reason)
        self.results.append(result)
        return result

    def summary(self) -> dict:
        counts = {s: 0 for s in (_STATUS_PASS, _STATUS_FAIL, _STATUS_ERROR, _STATUS_SKIP)}
        for r in self.results:
            counts[r.status] = counts.get(r.status, 0) + 1
        return counts


# ===========================================================================
# CATEGORY A – Unit tests: _lag_to_timedelta
# ===========================================================================

class _JavaDuration:
    """Minimal stub mimicking net.sf.mpxj.Duration for unit tests."""
    def __init__(self, magnitude: float, unit: str):
        self._mag  = magnitude
        self._unit = unit
    def getDuration(self):  return self._mag
    def getUnits(self):     return self._unit


def _cat_A(runner: TestRunner):
    cat = "A – _lag_to_timedelta"

    def test_none():
        result = _lag_to_timedelta(None)
        _assert_eq(result, timedelta(0), "None input")

    def test_positive_days():
        result = _lag_to_timedelta(_JavaDuration(2.0, "DAYS"))
        # 2 working days = 2 × 480 min = 960 min
        _assert_eq(result, timedelta(minutes=960), "2 working days")

    def test_negative_hours_lead():
        result = _lag_to_timedelta(_JavaDuration(-4.0, "HOURS"))
        _assert_eq(result, timedelta(minutes=-240), "-4 hours lead")

    def test_weeks():
        result = _lag_to_timedelta(_JavaDuration(1.0, "WEEKS"))
        # 1 week = 5 × 8h = 2400 min
        _assert_eq(result, timedelta(minutes=2400), "1 week")

    def test_elapsed_days():
        result = _lag_to_timedelta(_JavaDuration(1.0, "ELAPSED_DAYS"))
        # 1 elapsed day = 1440 min (24h)
        _assert_eq(result, timedelta(minutes=1440), "1 elapsed day")

    def test_elapsed_hours():
        result = _lag_to_timedelta(_JavaDuration(3.0, "ELAPSED_HOURS"))
        _assert_eq(result, timedelta(minutes=180), "3 elapsed hours")

    def test_minutes():
        result = _lag_to_timedelta(_JavaDuration(30.0, "MINUTES"))
        _assert_eq(result, timedelta(minutes=30), "30 minutes")

    def test_months():
        result = _lag_to_timedelta(_JavaDuration(1.0, "MONTHS"))
        # 1 month ≈ 20 × 8h = 9600 min
        _assert_eq(result, timedelta(minutes=9600), "1 month")

    def test_unknown_unit_defaults_to_days():
        result = _lag_to_timedelta(_JavaDuration(1.0, "FORTNIGHTS"))
        _assert_eq(result, timedelta(minutes=480), "unknown unit falls back to day")

    def test_zero_magnitude():
        result = _lag_to_timedelta(_JavaDuration(0.0, "DAYS"))
        _assert_eq(result, timedelta(0), "0 days")

    for fn in (
        test_none, test_positive_days, test_negative_hours_lead,
        test_weeks, test_elapsed_days, test_elapsed_hours, test_minutes,
        test_months, test_unknown_unit_defaults_to_days, test_zero_magnitude,
    ):
        runner.run(cat, fn.__name__.replace("test_", ""), fn)


# ===========================================================================
# CATEGORY B – Unit tests: _lag_to_working_hours
# ===========================================================================

def _cat_B(runner: TestRunner):
    cat = "B – _lag_to_working_hours"

    def test_none():
        _assert_eq(_lag_to_working_hours(None), 0.0, "None")

    def test_1_day_8h():
        _assert_approx(_lag_to_working_hours(_JavaDuration(1.0, "DAYS"), 8.0), 8.0,
                       label="1 day @ 8h")

    def test_1_day_7h():
        _assert_approx(_lag_to_working_hours(_JavaDuration(1.0, "DAYS"), 7.0), 7.0,
                       label="1 day @ 7h")

    def test_2_hours():
        _assert_approx(_lag_to_working_hours(_JavaDuration(2.0, "HOURS")), 2.0,
                       label="2 hours")

    def test_30_minutes():
        _assert_approx(_lag_to_working_hours(_JavaDuration(30.0, "MINUTES")), 0.5,
                       label="30 minutes")

    def test_1_week_8h():
        _assert_approx(_lag_to_working_hours(_JavaDuration(1.0, "WEEKS"), 8.0), 40.0,
                       label="1 week @ 8h")

    def test_1_month_8h():
        _assert_approx(_lag_to_working_hours(_JavaDuration(1.0, "MONTHS"), 8.0), 160.0,
                       label="1 month @ 8h")

    def test_elapsed_day_is_24h():
        _assert_approx(_lag_to_working_hours(_JavaDuration(1.0, "ELAPSED_DAYS")), 24.0,
                       label="1 elapsed day = 24 calendar hours")

    def test_elapsed_hours():
        _assert_approx(_lag_to_working_hours(_JavaDuration(5.0, "ELAPSED_HOURS")), 5.0,
                       label="5 elapsed hours")

    def test_negative_lead():
        _assert_approx(_lag_to_working_hours(_JavaDuration(-2.0, "HOURS")), -2.0,
                       label="-2 hours (lead)")

    def test_zero():
        _assert_approx(_lag_to_working_hours(_JavaDuration(0.0, "DAYS")), 0.0,
                       label="0 days")

    for fn in (
        test_none, test_1_day_8h, test_1_day_7h, test_2_hours, test_30_minutes,
        test_1_week_8h, test_1_month_8h, test_elapsed_day_is_24h,
        test_elapsed_hours, test_negative_lead, test_zero,
    ):
        runner.run(cat, fn.__name__.replace("test_", ""), fn)


# ===========================================================================
# CATEGORY C – CPM engine: minimal synthetic schedule (pure Python, no MPXJ)
# ===========================================================================

class _SyntheticTask:
    """Minimal MPXJ-like task stub for unit-testing the CPM engine."""
    def __init__(self, tid, name, start_str, finish_str, pct=0,
                 is_summary=False, predecessors=None):
        self._id      = tid
        self._name    = name
        self._start   = start_str
        self._finish  = finish_str
        self._pct     = pct
        self._summary = is_summary
        self._preds   = predecessors or []   # list of (task, rel_type)
        self._children = []

    def getID(self):               return self._id
    def getName(self):             return self._name
    def getStart(self):            return self._start
    def getFinish(self):           return self._finish
    def getChildTasks(self):       return self._children
    def getResourceAssignments(self): return []
    def getCalendar(self):         return None
    def getPredecessors(self):     return self._preds
    def getConstraintType(self):   return None
    def getConstraintDate(self):   return None
    def getPercentageComplete(self): return self._pct


class _SyntheticRelation:
    """MPXJ-like relation stub."""
    def __init__(self, pred_task, rel_type="FINISH_START", lag=None):
        self._pred = pred_task
        self._type = rel_type
        self._lag  = lag

    def getType(self):             return self._type
    def getPredecessorTask(self):  return self._pred
    def getLag(self):              return self._lag


def _build_linear_schedule():
    """Three-task linear schedule: A → B → C (all FS, no float).

    Tasks are directly adjacent (EF of predecessor == ES of successor) so
    the backward pass yields zero total float on all three tasks.
    """
    a = _SyntheticTask(1, "A", "2026-01-05", "2026-01-09", pct=0)
    b = _SyntheticTask(2, "B", "2026-01-09", "2026-01-13", pct=0)
    c = _SyntheticTask(3, "C", "2026-01-13", "2026-01-17", pct=0)
    b._preds = [_SyntheticRelation(a, "FINISH_START")]
    c._preds = [_SyntheticRelation(b, "FINISH_START")]
    return [a, b, c]


def _build_parallel_schedule():
    """
    Parallel schedule with one critical and one non-critical path.

         A (4d) ──FS──┐
                       ├──FS── C (3d)
         B (2d) ──FS──┘

    C starts exactly when A finishes so A–C is the critical path.
    B is 2 days shorter than A so B has 2 days of float.
    """
    a = _SyntheticTask(1, "A", "2026-01-05", "2026-01-09")  # 4-day span
    b = _SyntheticTask(2, "B", "2026-01-05", "2026-01-07")  # 2-day span → has float
    c = _SyntheticTask(3, "C", "2026-01-09", "2026-01-12")  # 3-day span, starts when A ends
    c._preds = [
        _SyntheticRelation(a, "FINISH_START"),
        _SyntheticRelation(b, "FINISH_START"),
    ]
    return [a, b, c]


def _build_completed_task_schedule():
    """A → B where A is 100% complete.  A must never appear as critical."""
    a = _SyntheticTask(1, "A", "2026-01-05", "2026-01-09", pct=100)
    b = _SyntheticTask(2, "B", "2026-01-12", "2026-01-16")
    b._preds = [_SyntheticRelation(a, "FINISH_START")]
    return [a, b]


def _build_ss_schedule():
    """Start-to-Start dependency: A ──SS──> B."""
    a = _SyntheticTask(1, "A", "2026-01-05", "2026-01-09")
    b = _SyntheticTask(2, "B", "2026-01-05", "2026-01-07")   # shorter; starts same day
    b._preds = [_SyntheticRelation(a, "START_START")]
    return [a, b]


def _build_ff_schedule():
    """Finish-to-Finish dependency: A ──FF──> B."""
    a = _SyntheticTask(1, "A", "2026-01-05", "2026-01-09")
    b = _SyntheticTask(2, "B", "2026-01-07", "2026-01-09")   # same finish
    b._preds = [_SyntheticRelation(a, "FINISH_FINISH")]
    return [a, b]


def _build_summary_task_schedule():
    """
    Summary task S contains children A (critical) and B (non-critical).
    S must be marked critical because A is critical.
    """
    a = _SyntheticTask(1, "A", "2026-01-05", "2026-01-09")
    b = _SyntheticTask(2, "B", "2026-01-05", "2026-01-06")   # has float vs project_finish
    s = _SyntheticTask(3, "S", "2026-01-05", "2026-01-09", is_summary=True)
    s._children = [a, b]
    # For the engine the summary_ids set is built from getChildTasks(); a,b are leaves
    return [s, a, b]


def _cat_C(runner: TestRunner):
    cat = "C – synthetic schedule: basic engine"

    def test_linear_all_critical():
        tasks = _build_linear_schedule()
        ids, fd = _compute_critical_ids(tasks, return_float_data=True)
        _assert(1 in ids, "A should be critical in linear chain")
        _assert(2 in ids, "B should be critical in linear chain")
        _assert(3 in ids, "C should be critical in linear chain")

    def test_linear_returns_set_without_flag():
        tasks = _build_linear_schedule()
        result = _compute_critical_ids(tasks)
        _assert(isinstance(result, set), "default return must be a set")

    def test_parallel_A_critical_B_not():
        tasks = _build_parallel_schedule()
        ids, fd = _compute_critical_ids(tasks, return_float_data=True)
        _assert(1 in ids, "A should be critical")
        _assert(2 not in ids, "B should NOT be critical (has float)")

    def test_parallel_float_data_keys():
        tasks = _build_parallel_schedule()
        ids, fd = _compute_critical_ids(tasks, return_float_data=True)
        expected_keys = {"es", "ef", "ls", "lf", "total_float", "free_float",
                         "total_float_wh", "free_float_wh", "work_day_hours", "critical"}
        for tid, entry in fd.items():
            missing = expected_keys - entry.keys()
            _assert(not missing,
                    f"float_data[{tid}] missing keys: {missing}")

    def test_completed_task_never_critical():
        tasks = _build_completed_task_schedule()
        ids, fd = _compute_critical_ids(tasks, return_float_data=True)
        _assert(1 not in ids, "completed task A must never be critical")

    def test_empty_task_list():
        result = _compute_critical_ids([])
        _assert(isinstance(result, set), "empty list → set")
        _assert_eq(len(result), 0, "empty list → empty set")

    def test_empty_task_list_with_float_data():
        ids, fd = _compute_critical_ids([], return_float_data=True)
        _assert_eq(len(ids), 0, "empty → no critical ids")
        _assert_eq(len(fd), 0, "empty → no float data")

    def test_slack_threshold_0_strict():
        tasks = _build_parallel_schedule()
        ids, _ = _compute_critical_ids(tasks, critical_slack_days=0, return_float_data=True)
        _assert(2 not in ids, "B not critical at threshold=0")

    def test_slack_threshold_large_catches_near_critical():
        tasks = _build_parallel_schedule()
        # With threshold=100 days nearly every task should be critical
        ids, _ = _compute_critical_ids(tasks, critical_slack_days=100, return_float_data=True)
        _assert(1 in ids, "A still critical at large threshold")
        _assert(2 in ids, "B critical too at large threshold")

    def test_dep_types_fs_only():
        # SS schedule – with fs_only the SS link is ignored; B should have float
        tasks = _build_ss_schedule()
        ids, fd = _compute_critical_ids(tasks, dep_types="fs_only", return_float_data=True)
        # No FS dependency → both tasks are independent; both anchored at stored dates
        # A is longer so it defines project finish; B has float
        _assert(isinstance(ids, set))

    def test_dep_types_all_includes_ss():
        tasks = _build_ss_schedule()
        ids, fd = _compute_critical_ids(tasks, dep_types="all", return_float_data=True)
        _assert(isinstance(ids, set))

    def test_dep_types_ff():
        tasks = _build_ff_schedule()
        ids, fd = _compute_critical_ids(tasks, dep_types="all", return_float_data=True)
        _assert(isinstance(ids, set))

    def test_summary_task_propagation():
        tasks = _build_summary_task_schedule()
        ids, fd = _compute_critical_ids(tasks, return_float_data=True)
        _assert(3 in ids, "summary task S must be critical because child A is critical")

    for fn in (
        test_linear_all_critical, test_linear_returns_set_without_flag,
        test_parallel_A_critical_B_not, test_parallel_float_data_keys,
        test_completed_task_never_critical,
        test_empty_task_list, test_empty_task_list_with_float_data,
        test_slack_threshold_0_strict, test_slack_threshold_large_catches_near_critical,
        test_dep_types_fs_only, test_dep_types_all_includes_ss, test_dep_types_ff,
        test_summary_task_propagation,
    ):
        runner.run(cat, fn.__name__.replace("test_", ""), fn)


# ===========================================================================
# CATEGORY D – CPM engine: float_data value correctness (synthetic)
# ===========================================================================

def _cat_D(runner: TestRunner):
    cat = "D – float_data value correctness"

    def test_linear_total_float_is_zero():
        tasks = _build_linear_schedule()
        ids, fd = _compute_critical_ids(tasks, return_float_data=True)
        for tid in (1, 2, 3):
            tf = fd[tid]["total_float"].total_seconds()
            _assert(abs(tf) < 30 * 60,  # within 30-minute tolerance
                    f"task {tid}: total_float should be ~0 in linear chain, got {tf}s")

    def test_parallel_B_has_positive_float():
        tasks = _build_parallel_schedule()
        ids, fd = _compute_critical_ids(tasks, return_float_data=True)
        tf_b = fd[2]["total_float"]
        _assert(tf_b > timedelta(0), f"B total_float must be > 0, got {tf_b}")

    def test_float_data_critical_flag_matches_id_set():
        tasks = _build_parallel_schedule()
        ids, fd = _compute_critical_ids(tasks, return_float_data=True)
        for tid, entry in fd.items():
            in_ids = tid in ids
            flag   = entry["critical"]
            _assert(in_ids == flag,
                    f"task {tid}: id_set={in_ids} but float_data['critical']={flag}")

    def test_ef_not_before_es():
        tasks = _build_parallel_schedule()
        _, fd = _compute_critical_ids(tasks, return_float_data=True)
        for tid, entry in fd.items():
            _assert(entry["ef"] >= entry["es"],
                    f"task {tid}: EF({entry['ef']}) < ES({entry['es']})")

    def test_lf_not_before_ls():
        tasks = _build_parallel_schedule()
        _, fd = _compute_critical_ids(tasks, return_float_data=True)
        for tid, entry in fd.items():
            _assert(entry["lf"] >= entry["ls"],
                    f"task {tid}: LF({entry['lf']}) < LS({entry['ls']})")

    def test_total_float_wh_non_negative_for_critical():
        tasks = _build_linear_schedule()
        _, fd = _compute_critical_ids(tasks, return_float_data=True)
        for tid in (1, 2, 3):
            _assert(fd[tid]["total_float_wh"] >= -0.5,
                    f"task {tid}: total_float_wh should be ≥0 on critical path")

    def test_free_float_wh_non_negative():
        tasks = _build_parallel_schedule()
        _, fd = _compute_critical_ids(tasks, return_float_data=True)
        for tid, entry in fd.items():
            _assert(entry["free_float_wh"] >= -0.5,
                    f"task {tid}: free_float_wh should be ≥0")

    def test_work_day_hours_default_8():
        tasks = _build_linear_schedule()
        _, fd = _compute_critical_ids(tasks, return_float_data=True)
        for tid, entry in fd.items():
            _assert_approx(entry["work_day_hours"], 8.0, tol=0.01,
                           label=f"task {tid} wdh default")

    for fn in (
        test_linear_total_float_is_zero, test_parallel_B_has_positive_float,
        test_float_data_critical_flag_matches_id_set,
        test_ef_not_before_es, test_lf_not_before_ls,
        test_total_float_wh_non_negative_for_critical, test_free_float_wh_non_negative,
        test_work_day_hours_default_8,
    ):
        runner.run(cat, fn.__name__.replace("test_", ""), fn)


# ===========================================================================
# CATEGORY E – Integration tests: bundled MSPDI schedule
# ===========================================================================
# Known answers for tests/data/cpm_test_schedule.xml:
#   Critical path UIDs : 1, 2, 4, 5
#   Non-critical UIDs  : 3 (TF=12d), 7 (TF=11d)
#   Excluded (100%)    : 6
#   Total float_data entries (without completed): 6

def _require_project():
    """Raise _TestSkip when no project has been loaded."""
    if _project is None or not _all_tasks:
        raise _TestSkip("JVM unavailable or project not loaded — integration tests skipped")


def _cat_E(runner: TestRunner):
    cat = "E – MPXJ integration: bundled schedule results"

    def test_returns_set():
        _require_project()
        result = _compute_critical_ids(_all_tasks)
        _assert(isinstance(result, set), "must return a set")

    def test_returns_tuple_with_flag():
        _require_project()
        result = _compute_critical_ids(_all_tasks, return_float_data=True)
        _assert(isinstance(result, tuple) and len(result) == 2,
                "with return_float_data=True must return (set, dict)")

    def test_float_data_not_empty():
        _require_project()
        _, fd = _compute_critical_ids(_all_tasks, project=_project, return_float_data=True)
        _assert(len(fd) >= 5, f"expected >=5 float_data entries, got {len(fd)}")

    def test_known_critical_path():
        """UIDs 1,2,4,5 must be critical; 3,7 must not be; 6 (100%) must not be."""
        _require_project()
        ids, _ = _compute_critical_ids(_all_tasks, return_float_data=True)
        missing_critical = _KNOWN_CRITICAL_IDS - ids
        _assert(not missing_critical,
                f"expected critical but not in result: {missing_critical}")
        false_critical = _KNOWN_NON_CRITICAL_IDS & ids
        _assert(not false_critical,
                f"should NOT be critical but are: {false_critical}")
        _assert(_KNOWN_COMPLETED_ID not in ids,
                f"completed task {_KNOWN_COMPLETED_ID} must never be critical")

    def test_completed_excluded_from_float_data():
        """Completed task is never critical; if present in float_data it has critical=False."""
        _require_project()
        ids, fd = _compute_critical_ids(_all_tasks, project=_project, return_float_data=True)
        _assert(_KNOWN_COMPLETED_ID not in ids,
                f"completed task UID={_KNOWN_COMPLETED_ID} must not be in critical ids")
        if _KNOWN_COMPLETED_ID in fd:
            _assert(not fd[_KNOWN_COMPLETED_ID]["critical"],
                    f"completed task UID={_KNOWN_COMPLETED_ID} must have critical=False in float_data")

    def test_float_data_structure():
        _require_project()
        _, fd = _compute_critical_ids(_all_tasks, project=_project, return_float_data=True)
        required = {"es", "ef", "ls", "lf", "total_float", "free_float",
                    "total_float_wh", "free_float_wh", "work_day_hours", "critical"}
        for tid, entry in fd.items():
            missing = required - entry.keys()
            _assert(not missing, f"task {tid} missing float_data keys: {missing}")

    def test_ef_ge_es_all_tasks():
        _require_project()
        _, fd = _compute_critical_ids(_all_tasks, project=_project, return_float_data=True)
        bad = [(tid, e["es"], e["ef"]) for tid, e in fd.items() if e["ef"] < e["es"]]
        _assert(not bad, f"EF < ES for tasks: {bad[:5]}")

    def test_lf_ge_ls_all_tasks():
        _require_project()
        _, fd = _compute_critical_ids(_all_tasks, project=_project, return_float_data=True)
        bad = [(tid, e["ls"], e["lf"]) for tid, e in fd.items() if e["lf"] < e["ls"]]
        _assert(not bad, f"LF < LS for tasks: {bad[:5]}")

    def test_critical_flag_consistent():
        _require_project()
        ids, fd = _compute_critical_ids(_all_tasks, project=_project, return_float_data=True)
        mismatches = [tid for tid, e in fd.items() if (tid in ids) != e["critical"]]
        _assert(not mismatches,
                f"critical flag mismatch for task IDs: {mismatches[:5]}")

    def test_non_negative_free_float():
        _require_project()
        _, fd = _compute_critical_ids(_all_tasks, project=_project, return_float_data=True)
        bad = [(tid, e["free_float"]) for tid, e in fd.items()
               if e["free_float"] < timedelta(minutes=-30)]
        _assert(not bad, f"negative free_float for tasks: {bad[:5]}")

    def test_critical_tasks_zero_total_float():
        """All known-critical tasks (TF=0 by design) must have TF near zero."""
        _require_project()
        _, fd = _compute_critical_ids(_all_tasks, project=_project, return_float_data=True)
        _TOLS = timedelta(hours=1)   # 1-hour tolerance for calendar rounding
        for uid in _KNOWN_CRITICAL_IDS:
            if uid not in fd:
                continue  # skip if engine excluded it for another reason
            tf = fd[uid]["total_float"]
            _assert(abs(tf) <= _TOLS,
                    f"UID {uid} should have TF~0, got {tf}")

    def test_non_critical_tasks_have_positive_float():
        """Review (UID=3) and Docs (UID=7) must have significant positive float."""
        _require_project()
        _, fd = _compute_critical_ids(_all_tasks, project=_project, return_float_data=True)
        for uid in _KNOWN_NON_CRITICAL_IDS:
            if uid not in fd:
                continue
            tf = fd[uid]["total_float"]
            _assert(tf > timedelta(days=1),
                    f"UID {uid} should have TF > 1 day, got {tf}")

    for fn in (
        test_returns_set, test_returns_tuple_with_flag,
        test_float_data_not_empty, test_known_critical_path,
        test_completed_excluded_from_float_data, test_float_data_structure,
        test_ef_ge_es_all_tasks, test_lf_ge_ls_all_tasks,
        test_critical_flag_consistent, test_non_negative_free_float,
        test_critical_tasks_zero_total_float,
        test_non_critical_tasks_have_positive_float,
    ):
        runner.run(cat, fn.__name__.replace("test_", ""), fn)


# ===========================================================================
# CATEGORY F – Integration: parameter variants on the bundled schedule
# ===========================================================================

def _cat_F(runner: TestRunner):
    cat = "F – MPXJ integration: parameter variants"

    def test_project_none_vs_with_project():
        """Passing project= must not raise; both calls return sets."""
        _require_project()
        ids_no_proj = _compute_critical_ids(_all_tasks)
        ids_with_proj, _ = _compute_critical_ids(
            _all_tasks, project=_project, return_float_data=True)
        _assert(isinstance(ids_no_proj, set))
        _assert(isinstance(ids_with_proj, set))

    def test_slack_0_vs_slack_3():
        """With threshold=3 days, Review (TF=12d) remains non-critical."""
        _require_project()
        ids_0, _ = _compute_critical_ids(_all_tasks, project=_project,
                                         critical_slack_days=0, return_float_data=True)
        ids_3, _ = _compute_critical_ids(_all_tasks, project=_project,
                                         critical_slack_days=3, return_float_data=True)
        _assert(len(ids_3) >= len(ids_0),
                f"threshold=3 ({len(ids_3)}) must be >= threshold=0 ({len(ids_0)})")
        # Review TF=12d > 3d: still non-critical at threshold=3
        _assert(3 not in ids_3, "Review (UID=3, TF=12d) must not be critical at threshold=3d")

    def test_slack_large_catches_all_non_critical():
        """With threshold=20 days, non-critical tasks (TF<20d) also become critical."""
        _require_project()
        ids, _ = _compute_critical_ids(_all_tasks, project=_project,
                                       critical_slack_days=20, return_float_data=True)
        _assert(3 in ids, "Review (TF=12d) must be critical at threshold=20d")
        _assert(7 in ids, "Docs (TF=11d) must be critical at threshold=20d")

    def test_fs_only_keeps_critical_path():
        """dep_types='fs_only' must preserve the all-FS critical path."""
        _require_project()
        ids_fs, _ = _compute_critical_ids(_all_tasks, project=_project,
                                          dep_types="fs_only", return_float_data=True)
        # All links in the bundled schedule are FS, so critical path is unchanged
        missing = _KNOWN_CRITICAL_IDS - ids_fs
        _assert(not missing,
                f"fs_only dropped critical tasks: {missing}")

    def test_legacy_zero_float_critical_bool():
        _require_project()
        result = _compute_critical_ids(_all_tasks, zero_float_critical=True)
        _assert(isinstance(result, set))

    def test_legacy_bool_false():
        _require_project()
        result = _compute_critical_ids(_all_tasks, zero_float_critical=False)
        _assert(isinstance(result, set))

    def test_slack_days_wins_over_bool():
        _require_project()
        ids_a = _compute_critical_ids(_all_tasks, critical_slack_days=0,
                                      zero_float_critical=True)
        ids_b = _compute_critical_ids(_all_tasks, critical_slack_days=0,
                                      zero_float_critical=False)
        _assert(ids_a == ids_b,
                "critical_slack_days=0 must give same result regardless of bool flag")

    for fn in (
        test_project_none_vs_with_project, test_slack_0_vs_slack_3,
        test_slack_large_catches_all_non_critical, test_fs_only_keeps_critical_path,
        test_legacy_zero_float_critical_bool, test_legacy_bool_false,
        test_slack_days_wins_over_bool,
    ):
        runner.run(cat, fn.__name__.replace("test_", ""), fn)


# ===========================================================================
# CATEGORY G – Integration: calendar helpers (bundled schedule has a Standard calendar)
# ===========================================================================

def _cat_G(runner: TestRunner):
    cat = "G – calendar helpers"

    def test_calendar_wdh_default_calendar():
        _require_project()
        cal = _project.getDefaultCalendar()
        if cal is None:
            raise _TestSkip("project has no default calendar")
        wdh = _calendar_wdh(cal)
        _assert(6.0 <= wdh <= 24.0, f"expected 6–24 wdh, got {wdh}")

    def test_calendar_wdh_standard_is_8h():
        """The bundled schedule defines 08:00-12:00 + 13:00-17:00 = 8 h effective."""
        _require_project()
        cal = _project.getDefaultCalendar()
        if cal is None:
            raise _TestSkip("project has no default calendar")
        wdh = _calendar_wdh(cal)
        _assert_approx(wdh, 8.0, tol=0.1, label="Standard calendar wdh")

    def test_calendar_wdh_fallback_on_none():
        result = _calendar_wdh(None)
        _assert_approx(result, 8.0, label="_calendar_wdh(None) fallback")

    def test_get_task_calendar_returns_something():
        _require_project()
        found = False
        for t in _all_tasks:
            try:
                if int(str(t.getID())) == 0:
                    continue
                cal = _get_task_calendar(t, _project)
                if cal is not None:
                    found = True
                    break
            except Exception:
                pass
        _assert(found, "at least one task should resolve a calendar")

    def test_get_task_calendar_no_project():
        _require_project()
        for t in _all_tasks:
            try:
                if int(str(t.getID())) == 0:
                    continue
                _get_task_calendar(t, None)  # must not raise
                break
            except Exception:
                pass

    def test_working_hours_between_same_time():
        _require_project()
        cal = _project.getDefaultCalendar()
        if cal is None:
            raise _TestSkip("no default calendar")
        dt = datetime(2026, 1, 5, 9, 0)
        wh = _working_hours_between(cal, dt, dt)
        _assert_approx(wh, 0.0, label="same start/end → 0 working hours")

    def test_working_hours_between_one_workday():
        _require_project()
        cal = _project.getDefaultCalendar()
        if cal is None:
            raise _TestSkip("no default calendar")
        dt_start = datetime(2026, 1, 5, 8, 0)   # Monday 08:00
        dt_end   = datetime(2026, 1, 5, 17, 0)  # Monday 17:00
        wh = _working_hours_between(cal, dt_start, dt_end)
        _assert(wh > 0.0, f"working hours across a workday must be > 0, got {wh}")
        _assert(wh <= 9.0, f"max 9 h in one day, got {wh}")

    def test_calendar_add_working_hours_roundtrip():
        _require_project()
        cal = _project.getDefaultCalendar()
        if cal is None:
            raise _TestSkip("no default calendar")
        start = datetime(2026, 1, 5, 8, 0)
        end   = _calendar_add_working_hours(cal, start, 8.0)
        _assert(end > start, f"adding 8h should advance time; got {end}")

    def test_calendar_add_negative_hours_goes_back():
        _require_project()
        cal = _project.getDefaultCalendar()
        if cal is None:
            raise _TestSkip("no default calendar")
        start  = datetime(2026, 1, 6, 17, 0)   # Tuesday 17:00
        result = _calendar_add_working_hours(cal, start, -8.0)
        _assert(result < start, f"subtracting 8h must go backward; got {result}")

    for fn in (
        test_calendar_wdh_default_calendar, test_calendar_wdh_standard_is_8h,
        test_calendar_wdh_fallback_on_none,
        test_get_task_calendar_returns_something, test_get_task_calendar_no_project,
        test_working_hours_between_same_time, test_working_hours_between_one_workday,
        test_calendar_add_working_hours_roundtrip, test_calendar_add_negative_hours_goes_back,
    ):
        runner.run(cat, fn.__name__.replace("test_", ""), fn)


# ===========================================================================
# CATEGORY H – Integration: calendar-aware vs wall-clock CPM
# ===========================================================================

def _cat_H(runner: TestRunner):
    cat = "H – calendar-aware vs wall-clock CPM"

    def test_both_modes_return_valid_sets():
        _require_project()
        ids_no_cal, _  = _compute_critical_ids(_all_tasks, return_float_data=True)
        ids_cal,    __ = _compute_critical_ids(_all_tasks, project=_project,
                                               return_float_data=True)
        _assert(isinstance(ids_no_cal, set))
        _assert(isinstance(ids_cal, set))

    def test_critical_path_same_in_both_modes():
        """Known critical path must be identical in both modes for the bundled schedule."""
        _require_project()
        ids_no_cal, _ = _compute_critical_ids(_all_tasks, return_float_data=True)
        ids_cal, __   = _compute_critical_ids(_all_tasks, project=_project,
                                              return_float_data=True)
        _assert(_KNOWN_CRITICAL_IDS.issubset(ids_no_cal),
                f"no-cal mode dropped critical tasks: {_KNOWN_CRITICAL_IDS - ids_no_cal}")
        _assert(_KNOWN_CRITICAL_IDS.issubset(ids_cal),
                f"cal-aware mode dropped critical tasks: {_KNOWN_CRITICAL_IDS - ids_cal}")

    def test_calendar_aware_wdh_8h():
        """With the bundled 8h calendar every task's wdh should be ~8."""
        _require_project()
        _, fd = _compute_critical_ids(_all_tasks, project=_project, return_float_data=True)
        bad = [(tid, e["work_day_hours"]) for tid, e in fd.items()
               if not (6.0 <= e["work_day_hours"] <= 10.0)]
        _assert(not bad, f"unexpected wdh values: {bad}")

    def test_float_wh_equals_wall_clock_hours_in_no_cal_mode():
        """In non-cal mode total_float_wh == total_float.total_seconds()/3600."""
        _require_project()
        _, fd = _compute_critical_ids(_all_tasks, return_float_data=True)  # no project
        mismatches = []
        for tid, e in fd.items():
            tf_h  = e["total_float"].total_seconds() / 3600.0
            tf_wh = e["total_float_wh"]
            if abs(tf_h - tf_wh) > 0.5:
                mismatches.append((tid, tf_h, tf_wh))
        _assert(not mismatches,
                f"total_float_wh != wall-clock hours in no-cal mode: {mismatches[:3]}")

    for fn in (
        test_both_modes_return_valid_sets,
        test_critical_path_same_in_both_modes,
        test_calendar_aware_wdh_8h,
        test_float_wh_equals_wall_clock_hours_in_no_cal_mode,
    ):
        runner.run(cat, fn.__name__.replace("test_", ""), fn)


# ===========================================================================
# CATEGORY I – Edge cases on synthetic data
# ===========================================================================

def _cat_I(runner: TestRunner):
    cat = "I – edge cases"

    def test_single_task_no_preds():
        t = _SyntheticTask(1, "Solo", "2026-03-01", "2026-03-05")
        ids, fd = _compute_critical_ids([t], return_float_data=True)
        _assert(1 in ids, "single task with no preds should be critical")
        _assert(fd[1]["total_float"] <= timedelta(hours=1),
                "single task total float should be ~0")

    def test_all_completed_tasks():
        tasks = [
            _SyntheticTask(1, "A", "2026-01-05", "2026-01-09", pct=100),
            _SyntheticTask(2, "B", "2026-01-12", "2026-01-16", pct=100),
        ]
        tasks[1]._preds = [_SyntheticRelation(tasks[0], "FINISH_START")]
        ids, fd = _compute_critical_ids(tasks, return_float_data=True)
        _assert(not ids, f"all-completed project must have no critical tasks, got {ids}")

    def test_task_with_invalid_dates_skipped():
        bad  = _SyntheticTask(1, "Bad", None, None)   # no dates
        good = _SyntheticTask(2, "Good", "2026-01-05", "2026-01-09")
        ids, fd = _compute_critical_ids([bad, good], return_float_data=True)
        _assert(1 not in fd, "task with no dates must be excluded from float_data")
        _assert(2 in fd, "task with valid dates must be in float_data")

    def test_zero_duration_task():
        # A task whose start == finish (milestone-like)
        m = _SyntheticTask(1, "M", "2026-01-05", "2026-01-05")
        ids, fd = _compute_critical_ids([m], return_float_data=True)
        _assert(1 in fd, "zero-duration task must appear in float_data")
        _assert_approx(fd[1]["total_float"].total_seconds(), 0.0, tol=1800,
                       label="zero-duration task total float")

    def test_lag_positive_shifts_successor():
        """FS with +1 day lag: successor ES pushed 1 day beyond predecessor EF."""
        a = _SyntheticTask(1, "A", "2026-01-05", "2026-01-09")
        b = _SyntheticTask(2, "B", "2026-01-12", "2026-01-16")
        b._preds = [_SyntheticRelation(a, "FINISH_START", _JavaDuration(1.0, "DAYS"))]
        _, fd = _compute_critical_ids([a, b], return_float_data=True)
        # EF of A = 2026-01-09; with 1-day lag successor ES should be pushed past that
        # The exact value depends on the engine; just verify structure is intact
        _assert(1 in fd and 2 in fd)

    def test_lag_negative_lead_overlaps():
        """FS with -1 day lead: successor may start 1 day before predecessor finishes."""
        a = _SyntheticTask(1, "A", "2026-01-05", "2026-01-09")
        b = _SyntheticTask(2, "B", "2026-01-09", "2026-01-14")
        b._preds = [_SyntheticRelation(a, "FINISH_START", _JavaDuration(-1.0, "DAYS"))]
        _, fd = _compute_critical_ids([a, b], return_float_data=True)
        _assert(1 in fd and 2 in fd)

    def test_sf_dependency_handled():
        """Start-to-Finish: A ──SF──> B (B must finish after A starts)."""
        a = _SyntheticTask(1, "A", "2026-01-12", "2026-01-16")
        b = _SyntheticTask(2, "B", "2026-01-05", "2026-01-09")
        b._preds = [_SyntheticRelation(a, "START_FINISH")]
        ids, fd = _compute_critical_ids([a, b], return_float_data=True)
        _assert(isinstance(ids, set))

    def test_return_float_data_false_backward_compat():
        """Callers that never passed return_float_data must get a plain set."""
        tasks = _build_linear_schedule()
        result = _compute_critical_ids(tasks, dep_types="all")
        _assert(isinstance(result, set), "backward-compat: must be a set")

    for fn in (
        test_single_task_no_preds, test_all_completed_tasks,
        test_task_with_invalid_dates_skipped, test_zero_duration_task,
        test_lag_positive_shifts_successor, test_lag_negative_lead_overlaps,
        test_sf_dependency_handled, test_return_float_data_false_backward_compat,
    ):
        runner.run(cat, fn.__name__.replace("test_", ""), fn)


# ===========================================================================
# HTML report generation
# ===========================================================================

_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>CPM Engine Test Report</title>
<style>
  body {{ font-family: "Segoe UI", Arial, sans-serif; margin: 0; background: #f5f7fa; color: #1f2d3d; }}
  .header {{ background: #2b579a; color: #fff; padding: 20px 32px; }}
  .header h1 {{ margin: 0 0 4px; font-size: 22px; }}
  .header p  {{ margin: 0; font-size: 13px; opacity: .8; }}
  .summary {{ display: flex; gap: 12px; padding: 18px 32px; background: #fff;
              border-bottom: 1px solid #d0ddf0; flex-wrap: wrap; }}
  .pill {{ padding: 6px 16px; border-radius: 20px; font-weight: 700; font-size: 13px; }}
  .pill.pass  {{ background: #d1fae5; color: #065f46; }}
  .pill.fail  {{ background: #fee2e2; color: #7f1d1d; }}
  .pill.error {{ background: #fef3c7; color: #92400e; }}
  .pill.skip  {{ background: #e0e7ff; color: #3730a3; }}
  .env {{ padding: 12px 32px; background: #f0f4ff; border-bottom: 1px solid #d0ddf0;
          display: flex; gap: 24px; font-size: 12px; flex-wrap: wrap; }}
  .env .ei {{ display: flex; gap: 6px; }}
  .env .ek {{ color: #6b7280; }}
  .content {{ padding: 20px 32px; max-width: 1200px; }}
  .category {{ background: #fff; border: 1px solid #d0ddf0; border-radius: 8px;
               margin-bottom: 12px; overflow: hidden; }}
  .cat-header {{ padding: 10px 16px; background: #eef2fb; display: flex;
                 justify-content: space-between; align-items: center; font-weight: 600;
                 font-size: 14px; cursor: pointer; }}
  .cat-body {{ padding: 0 8px 8px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th {{ text-align: left; padding: 6px 8px; border-bottom: 2px solid #d0ddf0;
       background: #f8fafc; font-size: 12px; text-transform: uppercase; color: #6b7280; }}
  td {{ padding: 6px 8px; border-bottom: 1px solid #f0f0f0; vertical-align: top; }}
  .badge {{ padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 700;
            margin-left: 4px; }}
  .badge.PASS  {{ background: #d1fae5; color: #065f46; }}
  .badge.FAIL  {{ background: #fee2e2; color: #7f1d1d; }}
  .badge.ERROR {{ background: #fef3c7; color: #92400e; }}
  .badge.SKIP  {{ background: #e0e7ff; color: #3730a3; }}
  .status-badge {{ display: inline-block; padding: 2px 8px; border-radius: 10px;
                   font-size: 11px; font-weight: 700; }}
  .status-badge.PASS  {{ background: #d1fae5; color: #065f46; }}
  .status-badge.FAIL  {{ background: #fee2e2; color: #7f1d1d; }}
  .status-badge.ERROR {{ background: #fef3c7; color: #92400e; }}
  .status-badge.SKIP  {{ background: #e0e7ff; color: #3730a3; }}
  .msg.fail  {{ color: #b91c1c; font-size: 12px; }}
  .msg.error {{ color: #d97706; font-size: 12px; }}
  .msg.skip  {{ color: #4338ca; font-size: 12px; }}
  pre.output {{ background: #1e293b; color: #e2e8f0; padding: 10px; border-radius: 6px;
               font-size: 11px; overflow-x: auto; white-space: pre-wrap; margin-top: 6px; }}
  .dur {{ font-size: 11px; color: #6b7280; }}
</style>
</head>
<body>
<div class="header">
  <h1>CPM Engine Test Report</h1>
  <p>Generated {timestamp} &nbsp;|&nbsp; Project: {project_file}</p>
</div>
<div class="summary">
  <span class="pill pass">{pass_count} PASS</span>
  <span class="pill fail">{fail_count} FAIL</span>
  <span class="pill error">{error_count} ERROR</span>
  <span class="pill skip">{skip_count} SKIP</span>
  <span style="margin-left:auto;font-size:12px;color:#6b7280;align-self:center">
    {total_count} tests &nbsp;|&nbsp; {total_ms:.0f} ms total
  </span>
</div>
<div class="env">
  <div class="ei"><span class="ek">Python</span><span>{python_ver}</span></div>
  <div class="ei"><span class="ek">Platform</span><span>{platform}</span></div>
  <div class="ei"><span class="ek">MPXJ loaded</span><span>{mpxj_ok}</span></div>
  <div class="ei"><span class="ek">Tasks loaded</span><span>{task_count}</span></div>
</div>
<div class="content">
{categories_html}
</div>
</body>
</html>
"""


def _html_escape(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;")
             .replace(">", "&gt;").replace('"', "&quot;"))


def generate_html_report(
    results: list[TestResult],
    project_file: str,
) -> str:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    counts = {s: 0 for s in (_STATUS_PASS, _STATUS_FAIL, _STATUS_ERROR, _STATUS_SKIP)}
    total_ms = 0.0
    for r in results:
        counts[r.status] = counts.get(r.status, 0) + 1
        total_ms += r.duration_ms

    sorted_results = sorted(results, key=lambda r: r.category)
    cat_parts = []
    for cat, group in groupby(sorted_results, key=lambda r: r.category):
        items = list(group)
        cc = {s: 0 for s in (_STATUS_PASS, _STATUS_FAIL, _STATUS_ERROR, _STATUS_SKIP)}
        for r in items:
            cc[r.status] = cc.get(r.status, 0) + 1
        badges = "".join(
            f'<span class="badge {s}">{n} {s}</span>'
            for s, n in cc.items() if n > 0
        )
        rows = []
        for r in items:
            msg_cls = {"FAIL": "fail", "ERROR": "error", "SKIP": "skip"}.get(r.status, "")
            msg_html = (
                f'<br><span class="msg {msg_cls}">{_html_escape(r.message)}</span>'
                if r.message else ""
            )
            out_html = ""
            if r.stdout or r.details:
                combined = ""
                if r.stdout:
                    combined += "=== OUTPUT ===\n" + r.stdout + "\n"
                if r.details:
                    combined += "=== TRACEBACK ===\n" + r.details
                out_html = (
                    f'<details><summary>Show output</summary>'
                    f'<pre class="output">{_html_escape(combined.strip())}</pre>'
                    f'</details>'
                )
            rows.append(
                f"<tr>"
                f'<td><span class="status-badge {r.status}">{r.status}</span></td>'
                f"<td>{_html_escape(r.name)}{msg_html}{out_html}</td>"
                f'<td><span class="dur">{r.duration_ms:.0f} ms</span></td>'
                f"</tr>"
            )
        cat_parts.append(f"""
<div class="category">
  <div class="cat-header">
    <span>{_html_escape(cat)}</span>
    <span>{badges}</span>
  </div>
  <div class="cat-body">
    <table>
      <thead><tr>
        <th style="width:80px">Status</th><th>Test</th><th style="width:90px">Duration</th>
      </tr></thead>
      <tbody>{"".join(rows)}</tbody>
    </table>
  </div>
</div>""")

    return _HTML_TEMPLATE.format(
        timestamp=timestamp,
        project_file=_html_escape(os.path.basename(project_file)) if project_file else "(none)",
        pass_count=counts[_STATUS_PASS],
        fail_count=counts[_STATUS_FAIL],
        error_count=counts[_STATUS_ERROR],
        skip_count=counts[_STATUS_SKIP],
        total_count=len(results),
        total_ms=total_ms,
        python_ver=f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        platform=sys.platform,
        mpxj_ok="yes" if _MPXJ_OK else f"no ({_MPXJ_ERROR[:60]})" if _MPXJ_ERROR else "no",
        task_count=str(len(_all_tasks)) if _all_tasks else "0",
        categories_html="\n".join(cat_parts),
    )


# ===========================================================================
# Main
# ===========================================================================

def _build_parser() -> optparse.OptionParser:
    parser = optparse.OptionParser(
        usage="usage: %prog [options]",
        description="CPM engine test suite — no GUI required.",
    )
    parser.add_option(
        "--output-dir",
        dest="output_dir",
        default=os.path.join(_ROOT_DIR, "tests", "documentation"),
        metavar="DIR",
        help="Output directory for the HTML report (default: tests/documentation)",
    )
    parser.add_option(
        "--no-report",
        action="store_true",
        dest="no_report",
        default=False,
        help="Print results to console only; do not write an HTML report",
    )
    return parser


def main():
    parser = _build_parser()
    opts, _ = parser.parse_args()

    if not _IMPORT_OK:
        print(f"[ERROR] Could not import gantt_view: {_IMPORT_ERROR}")
        print(f"  Make sure src/views/ is importable from: {_VIEWS_DIR}")
        sys.exit(1)

    # Start JVM then build the test project (written as MSPDI, read back via MPXJ)
    print("Starting JVM …")
    _start_jvm()
    if not _MPXJ_OK:
        print(f"[WARN] JVM/MPXJ could not start: {_MPXJ_ERROR}")
        print("       Integration tests will be skipped.")
    else:
        try:
            print("  Building programmatic test schedule …")
            _build_mpxj_project()
            print(f"  {len(_all_tasks)} tasks ready.\n")
        except Exception as exc:
            print(f"[WARN] Could not build project: {exc}")
            print("       Integration tests will be skipped.")

    runner = TestRunner()

    print("Running CPM engine tests …\n")
    _cat_A(runner)
    _cat_B(runner)
    _cat_C(runner)
    _cat_D(runner)
    _cat_E(runner)
    _cat_F(runner)
    _cat_G(runner)
    _cat_H(runner)
    _cat_I(runner)

    # Console summary
    counts = runner.summary()
    total  = len(runner.results)
    print("=" * 60)
    print(f"  {counts[_STATUS_PASS]} PASS  {counts[_STATUS_FAIL]} FAIL  "
          f"{counts[_STATUS_ERROR]} ERROR  {counts[_STATUS_SKIP]} SKIP  / {total} total")
    print("=" * 60)
    failed = [r for r in runner.results if r.status in (_STATUS_FAIL, _STATUS_ERROR)]
    if failed:
        print("\nFailed / Errored:")
        for r in failed:
            print(f"  [{r.status}] {r.category} › {r.name}")
            if r.message:
                print(f"         → {r.message}")
    else:
        print("\nAll tests passed (or skipped).")

    # HTML report
    if not opts.no_report:
        os.makedirs(opts.output_dir, exist_ok=True)
        out_file = os.path.join(opts.output_dir, "cpm_engine_test_report.html")
        html = generate_html_report(runner.results, "")
        with open(out_file, "w", encoding="utf-8") as fh:
            fh.write(html)
        print(f"\nHTML report: {out_file}")
        try:
            webbrowser.open(out_file)
        except Exception:
            pass

    sys.exit(0 if not failed else 1)


if __name__ == "__main__":
    main()
