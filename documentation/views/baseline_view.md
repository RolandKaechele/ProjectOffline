# baseline_view.py

Displays a comparison table: for each task it shows the **reference baseline** (planned)
dates against **comparison values** (current schedule or another baseline slot), plus
computed variance columns.

## Class: `BaselineView`

Extends `QTableWidget`.

### Columns

| # | Constant | Default header | Source |
| - | - | - | - |
| 0 | `_COL_ID` | ID | `task.getID()` |
| 1 | `_COL_NAME` | Name | `task.getName()` |
| 2 | `_COL_BL_START` | BL Start | `baseline_manager.get_baseline_start(task, n)` |
| 3 | `_COL_CUR_START` | Current Start | `task.getStart()` or baseline slot *nb* |
| 4 | `_COL_START_D` | Start Δ (d) | `var["start_days"]` |
| 5 | `_COL_BL_FIN` | BL Finish | `baseline_manager.get_baseline_finish(task, n)` |
| 6 | `_COL_CUR_FIN` | Current Finish | `task.getFinish()` or baseline slot *nb* |
| 7 | `_COL_FIN_D` | Finish Δ (d) | `var["finish_days"]` |
| 8 | `_COL_BL_DUR` | BL Duration | `baseline_manager.get_baseline_duration(task, n)` |
| 9 | `_COL_CUR_DUR` | Current Duration | `task.getDuration()` or baseline slot *nb* |
| 10 | `_COL_DUR_PCT` | Duration Δ % | `var["duration_pct"]` |

All cells are read-only.  Column headers for columns 3, 6, and 9 change dynamically via
`_update_headers()` to reflect the active comparison mode (e.g. `"Current Start"` vs
`"BL-1 Start"`).

### State

| Attribute | Type | Default | Description |
| - | - | - | - |
| `_baseline_number` | `int` | `0` | Active reference baseline slot (0–10) |
| `_comparison_number` | `int` | `-1` | Comparison slot: −1 = current schedule; 0–10 = another baseline slot |
| `_project` | `ProjectFile \| None` | `None` | Last loaded project |
| `_tasks` | `list` | `[]` | Task rows currently displayed |
| `_show_start_diff` | `bool` | `True` | Whether start columns are visible |
| `_show_finish_diff` | `bool` | `True` | Whether finish columns are visible |
| `_show_duration_diff` | `bool` | `True` | Whether duration columns are visible |

### Public API

| Method | Description |
| - | - |
| `set_baseline_number(number)` | Switch the reference baseline slot (0–10) and reload |
| `set_comparison_baseline(number)` | Set comparison slot (−1 = current, 0–10 = baseline slot) and reload |
| `set_show_start_diff(show)` | Show or hide the three Start columns (2, 3, 4) |
| `set_show_finish_diff(show)` | Show or hide the three Finish columns (5, 6, 7) |
| `set_show_duration_diff(show)` | Show or hide the three Duration columns (8, 9, 10) |
| `load_project(project)` | Populate the table from the given MPXJ `ProjectFile` (or clear on `None`) |
| `color_diagnostics()` | Return a debug dict describing the current cell-colour state (see below) |

### Cell Colour Coding

Individual cells in the Δ columns are coloured by the magnitude of variance.  The
current/comparison cells (Start, Finish, Duration) are highlighted yellow when they differ
from the reference value.  No green is used.

**Days (Start Δ, Finish Δ):**

| Threshold | Colour | RGB |
| - | - | - |
| 0 | None (white/alternate) | — |
| 1–2 days | Yellow | (255, 255, 160) |
| 3–5 days | Orange | (255, 210, 120) |
| ≥ 6 days | Red | (255, 150, 150) |

**Duration % (Duration Δ %):**

| Threshold | Colour | RGB |
| - | - | - |
| < 0.05% | None (treated as zero) | — |
| ≤ 10% | Yellow | (255, 255, 160) |
| ≤ 25% | Orange | (255, 210, 120) |
| > 25% | Red | (255, 150, 150) |

**Comparison data cells (columns 3, 6, 9):** highlighted `_YELLOW` whenever their string
value differs from the reference cell.

### `_CellColorDelegate`

Custom `QStyledItemDelegate` that bypasses Qt's stylesheet engine entirely.

**Why it exists:** `QStyleSheetStyle` intercepts the full `CE_ItemViewItem` paint path
whenever *any* `QTableWidget::item` QSS rule exists — even a padding-only rule.  This
means `item.setBackground()` is silently ignored at paint time.  The only reliable fix is
to **never call `super().paint()`** and instead draw background and text manually.

**How it works:**

1. `initStyleOption` is called to read the `Alternate` feature flag and font.
2. The background is filled using (in priority order): selection highlight → custom
   `Qt.BackgroundRole` color → alternating-row brush → base brush.
3. Text is drawn with 6 px horizontal / 3 px vertical padding, respecting
   `Qt.TextAlignmentRole`.

### Hover Tooltips

Every row that has at least one non-zero variance field shows an HTML tooltip on all its
cells.  The tooltip shows:

- Task name (bold)
- A subtitle like *"Baseline vs Current"* or *"Baseline 2 vs BL-1"*
- Per-field lines for Start, Finish, and Duration — only when they differ:
  - `Start:    {b_start} → {c_start}  ({delta} d)`
  - `Finish:   {b_finish} → {c_finish}  ({delta} d)`
  - `Duration: {b_dur} → {c_dur}  ({pct})`

### Same-Slot Guard

If `_comparison_number == _baseline_number` (both set to the same slot), the comparison
falls back to `−1` (current schedule) automatically during `load_project()`.  This
prevents the view from showing a blank/all-zero table when the user sets both combos to
the same slot.

### Key Interactions

| Action | How to trigger |
| - | - |
| Open Baseline detail dialog | Double-click any row → `BaselineEntryDialog` (read-only) |
| Switch reference baseline | Ribbon **Ref:** combo → `set_baseline_number()` |
| Switch comparison baseline | Ribbon **vs.:** combo → `set_comparison_baseline()` |
| Toggle Start columns | BASELINE ribbon **Start Δ** button → `set_show_start_diff()` |
| Toggle Finish columns | BASELINE ribbon **Finish Δ** button → `set_show_finish_diff()` |
| Toggle Duration columns | BASELINE ribbon **Duration %** button → `set_show_duration_diff()` |

### `color_diagnostics()`

Returns a JSON-serializable dict used in debug dumps (`Ctrl+D`):

| Key | Type | Description |
| - | - | - |
| `delegate_type` | `str` | Class name of the installed delegate (`"_CellColorDelegate"`) |
| `baseline_slot` | `int` | Current `_baseline_number` |
| `comparison_slot` | `int` | Current `_comparison_number` |
| `show_start_diff` | `bool` | `_show_start_diff` flag |
| `show_finish_diff` | `bool` | `_show_finish_diff` flag |
| `show_duration_diff` | `bool` | `_show_duration_diff` flag |
| `row_count` | `int` | Number of rows currently in the table |
| `colored_cells_count` | `int` | Number of cells with a non-null `BackgroundRole` |
| `uncolored_delta_count` | `int` | Delta-column cells with no background (expected zero when variance is non-zero) |
| `colored_cells` | `list[dict]` | One entry per coloured cell: `{"task", "col", "rgb"}` |

### Module-Level Helpers

| Function | Description |
| - | - |
| `_fmt_days(days)` | Format `int \| None` as `"+3"`, `"−2"`, `"0"`, or `""` |
| `_fmt_pct(pct)` | Format `float \| None` as `"+15.0%"`, `"0.0%"`, or `""` |
| `_cell_color_days(days)` | Return `_YELLOW / _ORANGE / _RED / None` for a days delta |
| `_cell_color_pct(pct)` | Return `_YELLOW / _ORANGE / _RED / None` for a percent delta |
