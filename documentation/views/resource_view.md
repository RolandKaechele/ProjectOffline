# resource_view.py

Displays and manages the project's resource list.

## Class: `ResourceView`

Extends `QTableWidget`.

### Columns

| # | Header | Description |
| - | - | - |
| 0 | ID | Resource sequence number |
| 1 | Name | Resource display name |
| 2 | Type | MPXJ `ResourceType` (e.g. `WORK`, `MATERIAL`, `COST`) |
| 3 | Max Units | Maximum allocation percentage (e.g. `100%`) — rendered as a coloured progress bar by `_ProgressDelegate` |
| 4 | Standard Rate | Regular pay rate |
| 5 | Overtime Rate | Overtime pay rate |

All cells are read-only in the grid; editing is done through the Resource Information dialog.

Row height is **36 px** (matching the Gantt Chart and Task Sheet views).

### Signal

| Signal | Arguments | Description |
| - | - | - |
| `data_changed` | — | A resource was added or deleted |

### Key Interactions

| Action | How to trigger |
| - | - |
| Open Resource Information dialog | Double-click any row |
| Add resource | Right-click → **Insert Resource**, or `Insert` key, or Edit / toolbar |
| Delete resource(s) | Right-click → **Delete Resource**, or `Delete` key, or Edit / toolbar |

### `load_project(project)`

Clears the table and populates it from `project.getResources()`.  Resources with `getName() == None` (the implicit "no resource" entry) are filtered out.

## Class: `_ProgressDelegate`

Custom `QStyledItemDelegate` for the **Max Units** column (column 3).

- Parses the cell text (strips `%`, converts to float) from `Qt.DisplayRole`.
- Draws a rounded progress bar with the same colour scheme as the task progress delegates:

| Range | Fill colour | Text colour |
| - | - | - |
| 0% | Empty track only | Dark |
| 1–49% | Light blue `#70A0D0` | Dark |
| 50–99% | Blue `#2B579A` | White |
| 100% | Green `#217346` | White |
| > 100% | Red `#C0392B` (full-width) | White |

- Minimum hint width: 90 px.


## Max Units Scale Normalisation

MPXJ's `getMaxUnits()` returns values on two different scales depending on the file format:

| File format | Scale | Example (100% available) |
| - | - | - |
| MSPDI / XML | Fraction | `1.0` |
| MPP (binary) | Percentage | `100.0` |

The application normalises using the heuristic `value × 100 if value ≤ 2.0 else value` in `_fill_row`, in the overallocation comparison in `GanttCanvas`, and in the `ResourceDialog` display/save path.  This ensures `90%` displays as `90%` regardless of the source file format.

When the user saves a new value via `ResourceDialog`, it is always stored back as a fraction (`÷ 100`) so MPXJ round-trips correctly.

## Automatic UID Assignment

When a new resource is added (via **Insert Resource**, the `Insert` key, or the AD import), the application automatically assigns a **unique integer UID** to the resource if it does not already have one.  The assigned value is the **smallest positive integer not currently used** by any resource in the project.

This guarantees that every resource gets a stable, unique UID immediately, which is required for:

- The **Team Planner** to show the correct swimlane for the new resource.
- **Task assignment** resolution — assignment rows look up the resource name via UID; a missing UID caused "(unknown)" to appear.

## Calendar Lifecycle

Resources may have a **personal calendar** linked via MPXJ `getCalendar()`.  This calendar defines the resource's individual working days and exceptions (vacations, absences).

### Deletion Cleanup

When one or more resources are deleted via `delete_selected_resources()`, the system automatically removes each resource's linked personal calendar from the project calendar list before removing the resource itself:

1. If `resource.getCalendar()` returns a calendar object, it is removed from `project.getCalendars()`.
2. If `getCalendar()` returns `None` (no personal calendar), deletion proceeds without error.

This prevents orphaned calendars accumulating in the project calendar list after resource deletion.

- The conflict-detection and vacation-overlay logic that indexes resources by UID.
