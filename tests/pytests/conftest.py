"""
conftest.py — Shared pytest fixtures and mock factories for the Project Offline test suite.

Import path:
    Both  src/  and  src/views/  are prepended to sys.path so every source module is
    importable without installation.

Qt:
    QT_QPA_PLATFORM is set to 'offscreen' for headless test execution.
    A single session-scoped QApplication is created once and shared by all tests.

Java / MPXJ:
    All MPXJ Java interactions are replaced with MagicMock objects.  The factory
    functions below produce mocks whose attribute shapes match what the views expect.

    jpype, mpxj, and the Java standard-library sub-packages are injected into
    sys.modules before any source module is imported.  This allows source files
    that contain lazy ``import jpype`` / ``import java.time`` calls to succeed
    without a real JVM being present.  Individual tests can still use
    ``patch.object(jpype, 'isJVMStarted', ...)`` to override specific attributes.
"""

import os
import sys
import pytest # type: ignore
from unittest.mock import MagicMock

# ── stub out Java / JVM dependencies ───────────────────────────────────────
# These must be injected before any src/ module is imported so that lazy
# `import jpype` / `import java.time` / `import org.mpxj.*` calls succeed.
_JAVA_STUBS = [
    'jpype', 'jpype._jclass', 'jpype.types', 'jpype.imports',
    'mpxj',
    'java', 'java.time', 'java.util',
    'org', 'org.mpxj', 'org.mpxj.reader', 'org.mpxj.mspdi', 'org.mpxj.writer',
    'pykeepass',
    'jira', 'atlassian', 'atlassian.jira',
    'requests',
]
for _m in _JAVA_STUBS:
    if _m not in sys.modules:
        sys.modules[_m] = MagicMock()

# ── make src/ and src/views/ importable ────────────────────────────────────
_SRC       = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))
_SRC_VIEWS = os.path.join(_SRC, 'views')
for _p in (_SRC, _SRC_VIEWS):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ── pre-import views sub-modules under their package name ──────────────────
# pytest-cov's instrumentation can interfere with the `views` namespace package
# when source modules use inline `from views.xxx import` calls.  Eagerly loading
# the relevant sub-modules here ensures they are cached in sys.modules under
# both 'xxx' (top-level) and 'views.xxx' (package-relative) before any test or
# the coverage tracer touches them.
try:
    import views  # noqa: F401
    import views.gantt_view  # noqa: F401
    import views.timeline_view  # noqa: F401
    import views.hour_mode  # noqa: F401
except Exception:  # pragma: no cover – only fails if a view module is broken
    pass

# ── headless Qt ────────────────────────────────────────────────────────────
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')


# ---------------------------------------------------------------------------
# Post-run hook: remove PNG assets from the HTML coverage report so they are
# not committed to SVN (coverage.py always writes favicon_*.png and
# keybd_closed_*.png regardless of content; the HTML report works without them).
# ---------------------------------------------------------------------------

def pytest_sessionfinish(session, exitstatus):  # noqa: ARG001
    import glob
    htmlcov_dir = os.path.join(
        os.path.dirname(__file__), '..', 'documentation', 'htmlcov'
    )
    for png in glob.glob(os.path.join(htmlcov_dir, '*.png')):
        try:
            os.remove(png)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# QApplication (session-scoped — created once for all tests)
# ---------------------------------------------------------------------------

@pytest.fixture(scope='session')
def qapp():
    """A single QApplication shared across the entire test session."""
    from PyQt5.QtWidgets import QApplication # type: ignore
    app = QApplication.instance() or QApplication([])
    yield app


# ---------------------------------------------------------------------------
# Mock Java LocalDateTime
# ---------------------------------------------------------------------------

def make_mock_ldt(year=2025, month=1, day=6, hour=8, minute=0):
    """Return a MagicMock that behaves like a java.time.LocalDateTime.

    str() returns an ISO-8601 string consumable by _to_qdate().
    """
    ldt = MagicMock()
    ldt.getYear.return_value       = year
    ldt.getMonthValue.return_value = month
    ldt.getDayOfMonth.return_value = day
    ldt.getHour.return_value       = hour
    ldt.getMinute.return_value     = minute
    ldt.__str__ = MagicMock(
        return_value=f"{year:04d}-{month:02d}-{day:02d}T{hour:02d}:{minute:02d}"
    )
    return ldt


# ---------------------------------------------------------------------------
# Mock MPXJ Task
# ---------------------------------------------------------------------------

def make_mock_task(
    task_id=1, name="Test Task", duration_days=5,
    pct=0.0, outline_level=1, is_summary=False,
    is_milestone=False, uid=1, is_critical=False,
    notes=None, predecessors=None,
    start_year=2025, start_month=1, start_day=6,
    finish_year=2025, finish_month=1, finish_day=12,
):
    """Return a MagicMock that behaves like an MPXJ Task Java object."""
    task = MagicMock()
    task.getID.return_value  = task_id
    task.getName.return_value = name

    # Duration
    dur      = MagicMock()
    unit_str = MagicMock()
    unit_str.__str__ = MagicMock(return_value="DAYS")
    dur.getDuration.return_value = float(duration_days)
    dur.getUnits.return_value    = unit_str
    dur.__str__                  = MagicMock(return_value=f"{duration_days} days")
    task.getDuration.return_value = dur

    # Start / Finish as LocalDateTime mocks
    task.getStart.return_value  = make_mock_ldt(start_year,  start_month,  start_day,  8,  0)
    task.getFinish.return_value = make_mock_ldt(finish_year, finish_month, finish_day, 17, 0)

    task.getPredecessors.return_value       = predecessors or []
    task.getPercentageComplete.return_value = pct
    task.getOutlineLevel.return_value       = outline_level

    # Non-summary tasks have no children (None is falsy — safe for 'if kids:' checks)
    task.getChildTasks.return_value = None
    task.getSummary.return_value    = is_summary

    task.getMilestone.return_value      = is_milestone
    task.getNotes.return_value          = notes
    task.getActualFinish.return_value   = None
    task.getActualStart.return_value    = None
    task.getActualDuration.return_value = None
    task.getUniqueID.return_value       = uid
    task.getCritical.return_value       = is_critical
    task.getResourceAssignments.return_value = []
    task.getBaselineStart.return_value    = None
    task.getBaselineFinish.return_value   = None
    task.getBaselineDuration.return_value = None
    return task


# ---------------------------------------------------------------------------
# Mock MPXJ Resource
# ---------------------------------------------------------------------------

def make_mock_resource(res_id=1, name="Resource A"):
    """Return a MagicMock that behaves like an MPXJ Resource Java object."""
    res = MagicMock()
    res.getID.return_value         = res_id
    res.getUniqueID.return_value   = res_id
    res.getName.return_value       = name

    type_mock = MagicMock()
    type_mock.__str__ = MagicMock(return_value="Work")
    res.getType.return_value = type_mock

    res.getMaxUnits.return_value = 1.0

    std  = MagicMock(); std.__str__  = MagicMock(return_value="$0.00/h")
    ovt  = MagicMock(); ovt.__str__  = MagicMock(return_value="$0.00/h")
    res.getStandardRate.return_value = std
    res.getOvertimeRate.return_value  = ovt
    return res


# ---------------------------------------------------------------------------
# Mock MPXJ ProjectFile
# ---------------------------------------------------------------------------

def make_mock_project(tasks=None, resources=None):
    """Return a MagicMock that behaves like an MPXJ ProjectFile Java object."""
    project = MagicMock()
    t_list  = tasks     if tasks     is not None else [make_mock_task()]
    r_list  = resources if resources is not None else [make_mock_resource()]

    project.getTasks.return_value     = t_list
    project.getResources.return_value = r_list

    # addTask / addResource return fresh mock objects
    project.addTask.return_value     = make_mock_task(task_id=99, uid=99, name="New Task")
    project.addResource.return_value = make_mock_resource(res_id=99, name="New Resource")

    props = MagicMock()
    props.getStartDate.return_value = None
    project.getProjectProperties.return_value = props

    cal = MagicMock()
    cal.isWorkingDate.return_value = True
    project.getDefaultCalendar.return_value = cal

    return project


# ---------------------------------------------------------------------------
# Convenience fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_task():
    return make_mock_task()


@pytest.fixture
def mock_resource():
    return make_mock_resource()


@pytest.fixture
def mock_project():
    return make_mock_project()
