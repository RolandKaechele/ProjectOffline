# toolbar.py

Wraps `ProjectRibbon` in a `QToolBar` so that it can be added to
`MainWindow` with `addToolBar()`.  All public methods delegate to the embedded
ribbon so that `ui.py` does not need to know the ribbon's implementation.

## Class: `ProjectToolBar`

Extends `QToolBar`.

### Construction

```python
ProjectToolBar(parent, logic, file_handler)
```

The toolbar is non-movable and non-floatable.  A single `ProjectRibbon` instance
is embedded via `addWidget()`.

### Properties

| Property | Type | Description |
| - | - | - |
| `ribbon` | `ProjectRibbon` | Read-only access to the embedded ribbon widget |

### Public Methods (delegated to ribbon)

| Method | Description |
| - | - |
| `set_save_enabled(enabled)` | Delegates to `ProjectRibbon.set_save_enabled()` (currently a no-op in the ribbon) |
| `set_delete_enabled(enabled)` | Delegates to `ProjectRibbon.set_delete_enabled()` |
| `update_actions(add_label, del_label, enabled, zoom_enabled)` | Delegates to `ProjectRibbon.update_actions()` |
