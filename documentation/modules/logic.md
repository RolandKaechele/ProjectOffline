# logic.py

Holds the single in-memory MPXJ `ProjectFile` (Java object) for the running
application.  Acts as a thin data store; all file I/O is handled by
`ProjectFileHandler` and all display logic lives in the view modules.

## Class: `ProjectLogic`

```python
logic = ProjectLogic()
```

A single instance is created in `main.py` and passed to `ProjectFileHandler`
and `MainWindow`.

### Attributes

| Attribute | Type | Description |
| - | - | - |
| `project_data` | `ProjectFile \| None` | The currently loaded MPXJ `ProjectFile`, or `None` when no project is open |

### Methods

| Method | Signature | Description |
| - | - | - |
| `load_data` | `(data)` | Store a `ProjectFile` (or `None`) as `project_data` |
| `get_data` | `() → ProjectFile \| None` | Return the current `project_data` |
