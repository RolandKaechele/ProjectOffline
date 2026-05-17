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


## Internal Helper: `_patch_save_cal_exc_names(project, file_path)`

Persists calendar exception names that `MSPDIWriter` silently drops.  MPXJ's XML writer never emits a `<Name>` child element for `<Exception>` nodes; this helper captures all non-empty exception names before the file is written and serialises them to a JSON sidecar:

```
<file_path>.cal-exc-names.json
```

Each entry in the JSON array is:

```json
{ "cal": "<calendar name>", "from": "YYYY-MM-DD", "to": "YYYY-MM-DD", "name": "<exception name>" }
```

The sidecar is **deleted** automatically when no named exceptions remain, preventing stale files from accumulating.


## Internal Helper: `_patch_load_cal_exc_names(project, file_path)`

Restores calendar exception names after a project file is loaded.  Reads the sidecar produced by `_patch_save_cal_exc_names`, builds a `(calendar_name, from_date, to_date) → name` lookup, then calls `ex.setName(name)` on every matching exception that is currently unnamed.  Already-named exceptions are skipped.

Called unconditionally in `open_project()` after `UniversalProjectReader` finishes; the helper is a no-op when the sidecar file does not exist.
