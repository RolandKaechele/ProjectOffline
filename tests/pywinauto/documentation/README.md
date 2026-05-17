# System Tests — pywinauto

This folder contains **end-to-end GUI system tests** for the Project Offline
application.  Unlike the unit/component tests in `tests/`, these tests launch
the **real application** as an external process and interact with it through
the Windows UI Automation (UIA) API via [pywinauto](https://pywinauto.readthedocs.io/).


## What is tested

| Module | File | Description |
| ------ | ---- | ----------- |
| Application startup | `test_app_launch.py` | Main window visible, title correct, menu bar present |

> Additional test modules will cover file operations, view switching, dialog
> interactions, and Gantt chart rendering.


## Folder structure

```
tests/pywinauto/
├── __init__.py
├── conftest.py              # Session-scoped fixtures: app launch / teardown
├── test_app_launch.py       # Smoke tests: window visible, title, menu bar
└── documentation/
    ├── README.md            # This file
    └── howto_execute.md     # Step-by-step execution guide
```


## Technology

| Component | Details |
| --------- | ------- |
| Test runner | pytest |
| GUI automation | pywinauto (UIA backend) |
| OS | Windows only |
| GUI framework | PyQt5 |

pywinauto's `uia` backend is used because it exposes the richer Windows UI
Automation control tree, which works well with PyQt5's accessibility layer.


## Marker

All system tests are tagged with the `systemtest` pytest marker.  This allows
them to be **excluded from the regular unit-test run**:

```bash
# Run only unit tests (skip system tests):
pytest -m "not systemtest"

# Run only system tests:
pytest -m systemtest tests/pywinauto/
```


## Key design decisions

### Session-scoped application fixture

The application is started **once per pytest session**, not once per test.
Starting the app includes JVM / MPXJ initialisation, which can take 10–30 s.
Restarting for every test would make the suite impractically slow.

As a consequence, tests must **not leave the application in a modified or
broken state** between test cases.  Each test is responsible for cleaning up
any dialogs it opens or files it modifies.

### Subprocess + connect pattern

`subprocess.Popen` is used to launch the process (giving control over
environment variables and working directory).  pywinauto then *connects* to
the running PID.  This is preferred over `Application.start()` because it
allows injecting `PYTHONPATH=src` without relying on pywinauto's own
environment handling.


## Prerequisites

See [howto_execute.md](howto_execute.md) for full setup and execution instructions.
