# baseline_manager.py

Business logic for the 11 baseline slots (Baseline 0 through Baseline 10).  Provides
set, clear, query, and variance-computation helpers used by `ui.py` and
`baseline_view.py`.

## Baseline Slots

MPXJ supports 11 independent baseline snapshots per project:

| Slot | MPXJ task getter | MPXJ props capture date |
| - | - | - |
| 0 | `task.getBaselineStart()` / `task.getBaselineFinish()` / `task.getBaselineDuration()` | `props.getBaselineDate()` |
| 1–10 | `task.getBaselineStart(n)` / … | `props.getBaselineDate(n)` |

For slots 1–10, writes use `task.set(TaskField.BASELINE{n}_START, ldt)` because MPXJ
lacks dedicated `setBaseline1Start()` / … methods.

## Public API

### `baseline_label(number) → str`

Returns a human-readable label:

- `0` → `"Baseline"`
- `n` → `"Baseline n"` (e.g. `"Baseline 3"`)

### `set_baseline(project, number=0) → None`

Snapshots the current schedule into slot *number* (0–10).  For every named task: copies
`getStart()`, `getFinish()`, `getDuration()` into the corresponding baseline fields.
Records `LocalDateTime.now()` in `ProjectProperties` via `props.setBaselineDate()` /
`props.setBaselineDate(n, ...)`.

### `clear_baseline(project, number=0) → None`

Removes all baseline data for slot *number*: sets start, finish, and duration fields to
`None` for every named task, and clears the capture date in `ProjectProperties`.

### `get_active_baselines(project) → dict[int, str]`

Returns `{slot_number: capture_date_str}` for every slot that has been set.

- Primary check: reads `ProjectProperties.getBaselineDate()` / `getBaselineDate(n)` for
  slots 0–10.  Non-null dates are formatted as `"YYYY-MM-DD HH:MM:SS"` (19 chars, `T`
  replaced by space).
- Fallback: if no capture dates exist, scans task `getBaselineStart()` values; slots with
  any non-null value are returned with `"(no date)"`.

### Per-task helpers

| Function | Description |
| - | - |
| `get_baseline_start(task, number=0)` | Returns Java `LocalDateTime` for baseline start in slot *number*, or `None` |
| `get_baseline_finish(task, number=0)` | Returns Java `LocalDateTime` for baseline finish in slot *number*, or `None` |
| `get_baseline_duration(task, number=0)` | Returns Java `Duration` for baseline duration in slot *number*, or `None` |

All three wrap the call in `try/except` and return `None` on any exception (handles files
where baseline fields are absent).

### `get_variance(task, number=0) → dict`

Computes schedule variance between the current schedule and baseline slot *number*.

**Returns:**

```python
{
    "start_days":   int | None,    # positive = current is later than baseline
    "finish_days":  int | None,    # positive = current is later than baseline
    "duration_pct": float | None,  # positive = longer than baseline
}
```

Uses `ChronoUnit.DAYS.between(baseline, current)` for date deltas and
`(curr - base) / base * 100` for the duration percentage.

### `get_variance_between(task, n_a, n_b) → dict`

Computes variance between two baseline slots for the same task.  *n_a* is the reference
("from") baseline; *n_b* is the comparison ("to") baseline.  Returns the same dict
structure as `get_variance()`.

## Private helpers

| Name | Description |
| - | - |
| `_task_field(name)` | Returns `TaskField.valueOf(name)` via JPype, or `None` on failure |
| `_props_field(name)` | Returns `ProjectPropertiesField.valueOf(name)` via JPype, or `None` on failure |
| `_START_FIELDS`, `_FINISH_FIELDS`, `_DURATION_FIELDS` | 11-element string lists mapping slot index to MPXJ `TaskField` enum name |
| `_DATE_PROP_FIELDS` | 11-element list mapping slot index to `ProjectPropertiesField` enum name for capture dates |
