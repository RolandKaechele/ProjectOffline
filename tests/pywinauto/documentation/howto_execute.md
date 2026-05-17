# How to Execute the pywinauto System Tests

Step-by-step guide for setting up and running the end-to-end GUI system tests
on a Windows machine.


## 1  Prerequisites

| Requirement | Version / Notes |
| ----------- | --------------- |
| Operating system | **Windows 10 or Windows 11** — pywinauto UIA is Windows-only |
| Python | 3.9 – 3.12 (match your project Python version) |
| Java / JDK | Required by MPXJ (used by the app at runtime).  Either set `JAVA_HOME` or place a JDK under `tools/java/` in the project root. |
| Display | A real or virtual display.  The app cannot run headless (unlike the unit tests which use `QT_QPA_PLATFORM=offscreen`). |


## 2  Install dependencies

From the **project root**:

```powershell
pip install -r requirements.txt
```

This installs `pywinauto` (and all other dependencies) into your active
Python environment.

To install only the system-test dependency manually:

```powershell
pip install pywinauto
```


## 3  Verify pywinauto installation

```powershell
python -c "import pywinauto; print(pywinauto.__version__)"
```

Expected output: a version string such as `0.6.8`.


## 4  Run only the system tests

```powershell
# From the project root:
pytest tests/pywinauto/ -m systemtest -v
```

`-v` enables verbose output (one line per test).

> **Note:** The first test will take 30–60 s because the app starts the JVM.
> Subsequent tests in the same session reuse the running process and are much
> faster.


## 5  Run a single test file

```powershell
pytest tests/pywinauto/test_app_launch.py -v
```


## 6  Run a single test case

```powershell
pytest tests/pywinauto/test_app_launch.py::TestAppLaunch::test_main_window_title -v
```


## 7  Exclude system tests from the regular unit-test run

The standard `pytest` invocation (which uses `testpaths = ["tests"]` from
`pyproject.toml`) will discover system tests too.  To skip them:

```powershell
pytest -m "not systemtest"
```

Or add `addopts = ["-m", "not systemtest"]` to the `[tool.pytest.ini_options]`
section of `pyproject.toml` to make exclusion the default.


## 8  Coverage

System tests launch the application out-of-process, so `pytest-cov` cannot
instrument the source code inside that process.  Do **not** add `--cov` flags
when running system tests — it has no effect and adds overhead.

```powershell
# Correct — no --cov:
pytest tests/pywinauto/ -m systemtest -v
```


## 9  Troubleshooting

### App window never appears (`TimeoutError` in conftest.py)

* Check that `JAVA_HOME` is set or a JDK exists under `tools/java/`.
* Run the app manually to confirm it starts:

  ```powershell
  $env:PYTHONPATH = "src"
  python src/main.py
  ```

* Increase `APP_CONNECT_TIMEOUT` in `conftest.py` if the machine is slow.

### `ModuleNotFoundError: No module named 'pywinauto'`

```powershell
pip install pywinauto
```

### `ElementNotFoundError` for a specific control

* The UIA control tree may differ between Windows versions or DPI settings.
* Use the **pywinauto Inspector** or **Spy++** to explore the live control tree:

  ```powershell
  python -c "
  from pywinauto import Application
  app = Application(backend='uia').connect(title='Project Offline')
  app.window(title='Project Offline').print_control_identifiers()
  "
  ```

  This prints the full control hierarchy, which you can use to update test
  locators.

### Multiple windows / stale handles

Because the app is session-scoped, a test that opens a dialog and crashes
before closing it will block subsequent tests.  Close any stray dialogs
manually, or restart the pytest session.

### `PermissionError` when connecting to the process

Run the terminal / IDE **as Administrator**, or check that UAC elevation is
not required by the app manifest.


## 10  Writing new system tests

1. Create a new file `tests/pywinauto/test_<feature>.py`.
2. Import and use the `main_window` or `focused_main_window` fixture from
   `conftest.py`.
3. Decorate the test class or function with `@pytest.mark.systemtest`.
4. Keep each test **independent**: open what you need, close it before the
   test ends.

Minimal example:

```python
import pytest

@pytest.mark.systemtest
class TestFileMenu:

    def test_open_file_menu(self, focused_main_window):
        file_menu = focused_main_window.child_window(title="File", control_type="MenuItem")
        file_menu.click_input()
        # Assert a sub-menu item is now visible
        new_item = focused_main_window.child_window(title="New", control_type="MenuItem")
        assert new_item.exists(timeout=3)
        # Close the menu
        focused_main_window.type_keys("{ESCAPE}")
```


## 11  Useful pywinauto references

* Documentation: <https://pywinauto.readthedocs.io/>
* Control types reference: <https://pywinauto.readthedocs.io/en/latest/code/pywinauto.controls.uia_controls.html>
* Finding controls: `window.print_control_identifiers(depth=5)`
