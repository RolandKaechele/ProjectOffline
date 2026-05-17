# main.py

Entry point for the Project Offline application.

## `main()`

Parses command-line arguments, creates the core objects, shows the main window,
and enters the Qt event loop.

### Startup Sequence

1. Parse arguments with `argparse`.
2. Create a `QApplication`.
3. Create `ProjectLogic` (data store).
4. Create `ProjectFileHandler(logic)` — starts the JVM.
5. Create `MainWindow(logic, file_handler)`.
6. If `--open <file>` was supplied, call `window.open_project_file(file)`.
7. `window.show()` then `sys.exit(app.exec_())`.

### Command-line Arguments

| Argument | Description |
| - | - |
| `--open <file>` | Open a project file at startup (`.mpp`, `.xml`, `.mpt`, `.mpx`, or `.puml`) |
| `--debug` / `-v` | Enable verbose debug output and activate the `Ctrl+D` project-state dump shortcut |

### Usage

```
python main.py
python main.py --open "C:\Projects\schedule.mpp"
python main.py --debug
python main.py --open "C:\Projects\schedule.mpp" --debug
```
