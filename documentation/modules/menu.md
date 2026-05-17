# menu.py

Builds the application menu bar and provides helper methods to keep menu state
in sync with the rest of the UI.

## Class: `ProjectMenuBar`

Extends `QMenuBar`.

### Construction

```python
ProjectMenuBar(parent, logic, file_handler)
```

All menu actions call methods on `parent` (the `MainWindow`).

### Menus

| Menu | Items |
| - | - |
| **File** | New, Open…, Save, Save As…, **Close**, Recent Files ▶, Import ▶ (PlantUML Gantt…), Export ▶ (Complete SVG, Resource SVG, PlantUML), Exit |
| **Options** | Show Resource Units on Bars *(checkable)*, Show Sundays *(checkable)*, Show Off-Hours *(checkable)*, Zero Float = Critical *(checkable)* |
| **Project** | Project Information… (`Alt+F11`), ─, Jira submenu (Jira Sync Configuration…, Jira Servers…), ─, KeePass Configuration… |

### Recent Files Submenu

Populated from a list of file paths (up to `MAX_RECENT = 5`).  Each entry
shows `&N  <basename>` and triggers `MainWindow.open_project_file(path)` when
clicked.  A **Clear Recent Files** action appears at the bottom when the list
is non-empty.

### Public Methods

| Method | Description |
| - | - |
| `set_save_enabled(enabled)` | Enable / disable the **Save** action |
| `set_close_enabled(enabled)` | Enable / disable the **Close** action (enabled when a project is open; called by `_refresh_all_views()`) |
| `update_recent_files(paths)` | Rebuild the Recent Files submenu |
| `set_resource_units_checked(checked)` | Sync the **Show Resource Units** checkmark |
| `set_show_sundays_checked(checked)` | Sync the **Show Sundays** checkmark |
| `set_show_off_hours_checked(checked)` | Sync the **Show Off-Hours** checkmark |
| `set_zero_float_critical_checked(checked)` | Sync the **Zero Float = Critical** checkmark |
| `update_edit_actions(add_label, del_label, enabled)` | No-op — Insert/Delete are ribbon-only |
