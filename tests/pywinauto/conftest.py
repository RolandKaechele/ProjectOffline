"""
conftest.py — pywinauto system-test fixtures for Project Offline.

These fixtures launch a *real* instance of the application as an external
process and provide pywinauto handles to the running window.

Design decisions
----------------
* Session-scoped ``pw_app``:
  The application is started once per test session, not once per test.
  JVM / MPXJ initialisation can take 10–30 s, so restarting for every test
  would make the suite impractically slow.

* Subprocess + connect pattern:
  ``subprocess.Popen`` is used for full process control (env, cwd, teardown).
  pywinauto then *connects* to the running PID rather than using
  ``Application.start()``, which does not expose the ``env`` parameter.

* UIA backend:
  The ``uia`` backend (Windows UI Automation) is recommended for PyQt5
  applications.  It exposes richer control metadata than the legacy
  ``win32`` backend.

* PYTHONPATH:
  ``src/`` is injected via PYTHONPATH so that ``main.py`` can resolve its
  sibling imports (``from ui import MainWindow``, etc.) without modifying
  any source file.
"""

import os
import pathlib
import subprocess
import sys

import pytest # type: ignore
from pywinauto import Application
from pywinauto.timings import TimeoutError as PWTimeoutError  # noqa: A004 # type: ignore

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
PROJECT_ROOT: pathlib.Path = pathlib.Path(__file__).resolve().parent.parent.parent
SRC_DIR: pathlib.Path = PROJECT_ROOT / "src"

MAIN_WINDOW_TITLE: str = "Project Offline"

#: How long to wait for the process to be connectable (JVM startup included).
APP_CONNECT_TIMEOUT: int = 120  # seconds

#: How long to wait for the main window to become ready after connecting.
WINDOW_READY_TIMEOUT: int = 60  # seconds


# ---------------------------------------------------------------------------
# Session-scoped fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def pw_app():
    """Launch Project Offline and yield ``(Application, main_window)``.

    The application is started exactly once per pytest session.  Teardown
    closes the main window gracefully; if that fails the process is killed.

    Usage::

        def test_something(pw_app):
            app, win = pw_app
            win.child_window(title="File").click_input()
    """
    # Resolve the portable JDK bundled in tools/java/ (any subdirectory that
    # contains bin/java.exe).  This mirrors the logic in cli.bat so the tests
    # use the same JDK regardless of what is installed system-wide.
    _java_home: pathlib.Path | None = None
    _tools_java = PROJECT_ROOT / "tools" / "java"
    if _tools_java.is_dir():
        for _candidate in _tools_java.iterdir():
            if (_candidate / "bin" / "java.exe").exists():
                _java_home = _candidate
                break

    env = {
        **os.environ,
        "PYTHONPATH": str(SRC_DIR),
        **({"JAVA_HOME": str(_java_home)} if _java_home else {}),
    }

    proc = subprocess.Popen(
        [sys.executable, str(SRC_DIR / "main.py")],
        cwd=str(PROJECT_ROOT),
        env=env,
    )

    app = Application(backend="uia")
    main_win = None
    try:
        app.connect(process=proc.pid, timeout=APP_CONNECT_TIMEOUT)
        # Debug: print all top-level windows found for this process
        try:
            wins = app.windows()
            print(f"\n[conftest] Windows found after connect: {[w.window_text() for w in wins]}")
        except Exception as _e:
            print(f"\n[conftest] Could not enumerate windows: {_e}")
        main_win = app.window(title=MAIN_WINDOW_TITLE)
        main_win.wait("ready", timeout=WINDOW_READY_TIMEOUT)

        yield app, main_win

    finally:
        # Graceful shutdown first, hard-kill as fallback.
        try:
            if main_win is not None:
                main_win.close()
            proc.wait(timeout=10)
        except Exception:  # noqa: BLE001
            proc.kill()


@pytest.fixture(scope="session")
def main_window(pw_app):
    """Convenience fixture: returns the main window wrapper directly.

    Usage::

        def test_title(main_window):
            assert main_window.window_text() == "Project Offline"
    """
    _app, win = pw_app
    return win


# ---------------------------------------------------------------------------
# Function-scoped helper fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def focused_main_window(main_window):
    """Return the main window after bringing it to the foreground.

    Use this instead of ``main_window`` in tests that interact with the UI,
    to ensure the window has focus before sending keyboard/mouse events.
    """
    main_window.set_focus()
    return main_window
