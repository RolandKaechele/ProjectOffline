# file_handler.py

Handles reading and writing Microsoft Project files using the [MPXJ](https://mpxj.org/) library via [JPype](https://jpype.readthedocs.io/).

## Class: `ProjectFileHandler`

```python
ProjectFileHandler(logic: ProjectLogic)
```

Starts the JVM on construction (if not already running) and holds a reference to `ProjectLogic` so loaded data can be stored.

### JVM Startup

The JVM is started with Log4j silenced:

```python
jpype.startJVM(
    "-Dlog4j2.loggerContextFactory=org.apache.logging.log4j.simple.SimpleLoggerContextFactory"
)
```

`mpxj` is imported before the JVM starts so that its bundled JAR is registered on the JPype classpath automatically.


### `open_project(file_path, parent=None) → bool`

Reads a project file and stores the resulting `ProjectFile` in `logic.project_data`.

Supported file formats (via `UniversalProjectReader`):

- `.mpp` — Microsoft Project binary
- `.xml` / `.mspdi` — Microsoft Project XML
- `.mpt` — Microsoft Project template
- `.mpx` — Microsoft Project Exchange

Native stdout/stderr are redirected to `/dev/null` during the read to suppress C-level diagnostic messages from the MPP format reader.

Returns `True` on success, `False` on error.  On error a `QMessageBox` is displayed if a `parent` widget is provided, and a full traceback is printed to stdout.


### `save_project(file_path) → bool`

Writes the in-memory `ProjectFile` to disk using `MSPDIWriter` (XML format).  The output format is always MSPDI XML regardless of the original file format.

Returns `True` on success, `False` on error or if no project is loaded.


## Internal Helper: `_suppress_native_output()`

A context-manager factory that redirects OS-level file descriptors 1 (stdout) and 2 (stderr) to `/dev/null` for the duration of the `with` block, then restores them.  This prevents native C++ messages from the MPXJ MPP reader from appearing in the console.
