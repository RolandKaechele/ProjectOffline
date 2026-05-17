# icons.py

Generates `QIcon` objects for the ribbon buttons at runtime by painting Unicode
glyphs or simple shapes onto a `QPixmap`.  No external image files are required.

## Low-level Helpers

### `_icon_from_glyph(glyph: str, color: str = "#FFFFFF", size: int = 24) → QIcon`

Paints a single Unicode glyph centred on a transparent `size × size` pixmap using
`"Segoe UI Symbol"` bold at `size × 0.55` pt.  Returns a `QIcon`.

### `_std(sp) → QIcon`

Returns a Qt standard pixmap icon via `QApplication.style().standardIcon(sp)`.


## Public Icon Accessors

Each function returns a `QIcon` for a specific ribbon button:

| Function | Glyph / source | Used by |
| - | - | - |
| `gantt_chart()` | 📊 | TASK → View → Gantt Chart |
| `resource_sheet()` | 👥 | RESOURCE → View → Resource Sheet |
| `paste()` | `QStyle.SP_DialogSaveButton` (standard) | TASK → Clipboard → Paste |
| `cut()` | ✂ | TASK → Clipboard → Cut |
| `copy()` | ⎘ | TASK → Clipboard → Copy |
| `insert_task()` | ➕ | TASK → Insert → Insert Task |
| `delete_task()` | ✖ | TASK → Editing → Delete Task |
| `add_resource()` | ➕ | RESOURCE → Insert → Add Resource |
| `delete_resource()` | ✖ | RESOURCE → Editing → Delete Resource |
| `export_svg()` | 📤 | REPORT → Export → Gantt SVG / Resource SVG |
| `export_plantuml()` | 📄 | REPORT → Export → PlantUML |
| `dependencies()` | 🔗 | TASK → View → Dependencies |
| `baseline()` | 📏 | TASK → View → Baseline |
