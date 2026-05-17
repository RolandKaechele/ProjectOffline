# export_gantt.py

Exports the Gantt chart to SVG and PlantUML formats.

## Public API

### `export_gantt_svg(canvas, output_path: str) → None`

Renders the complete Gantt chart (all visible tasks) to a single SVG file at `output_path`.

Uses Qt's `QSvgGenerator` to draw exactly what the on-screen `GanttView` renders, including:

- Two-row calendar header (month band / day numbers)
- Weekend column shading
- Non-working (holiday) column shading
- Task bars with progress overlay
- Baseline strips
- Critical-path highlighting (red bars)
- Milestone diamonds
- Predecessor dependency arrows
- A task-name column (`EXPORT_LABEL_W = 220 px`) prepended to the left


### `export_resource_gantt_svg(canvas, output_dir: str) → int`

Exports **one SVG per work resource** into `output_dir`.

For each resource, only the tasks that have at least one assignment to that resource are included.  The output filename is derived from the resource name (characters that are not alphanumeric, hyphens, or underscores are replaced with `_`).

Returns the number of SVG files written.  If no resources or assignments are found, shows a warning dialog and returns `0`.


### `export_gantt_plantuml(canvas, output_path: str) → None`

Exports the complete Gantt chart as a PlantUML `@startgantt` file at `output_path`.

The output uses the same syntax that `import_plantuml.py` can read:

```plantuml
@startgantt
Project starts YYYY-MM-DD
printscale daily

[Task Name] as [alias_0] starts YYYY-MM-DD and lasts N days
[alias_0] is N% completed
[alias_0] is colored in SteelBlue

[Alias_1] starts after [alias_0]'s end
@endgantt
```

Tasks are colour-coded by status:

| Colour | Condition |
| - | - |
| `Crimson` | Critical path task |
| `SteelBlue` | Normal task |
| `DarkGray` | Milestone |


## Layout Constants

| Constant | Value | Description |
| - | - | - |
| `EXPORT_LABEL_W` | 220 px | Width of the task-name column in exported SVGs |
| `_INDENT_PX` | 12 px | Indentation per outline level |


## Shared Helpers (from `gantt_view`)

`export_gantt.py` re-uses the following helpers from `gantt_view.py`:

| Helper | Signature | Purpose |
| - | - | - |
| `_to_qdate` | `(java_date)` | Convert MPXJ date to `QDate` |
| `_compute_finish_date` | `(task)` | Resolve task finish with calendar fallback |
| `_date_to_col` | `(project_start, date, show_sundays)` | Map a `QDate` to a visible column index |
| `_get_visible_tasks` | `(all_tasks, collapsed_ids)` | Filter out collapsed children |
| `_get_non_working_dates` | `(project, project_start, total_calendar_days)` | Collect holiday dates from the project calendar |
| `_compute_critical_ids` | `(all_tasks, project, zero_float_critical)` | Return the set of critical-path task IDs |
| `_normalize_schedule` | `(all_tasks)` | Forward-pass FS propagation to keep task dates coherent |
