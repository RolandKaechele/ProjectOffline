# integrations/secondary_calendar_integration.py

Manages **per-resource secondary holiday calendar** assignments.  A secondary calendar
is a project-level holiday calendar (e.g. *"Bayern"* or *"Baden-Württemberg"*) that
supplements a resource's personal working calendar with region-specific public holidays,
without modifying the personal calendar itself.

Assignments are persisted in the project file via MPXJ enterprise custom properties so
they survive save/load cycles and travel with the project file.


## Storage Format

All assignments for a project are stored as a single JSON string in the MPXJ project
custom property with key **`"AD Secondary Calendars"`**.

```json
{
  "3": {
    "calendar_name": "Bayern",
    "calendar_uid": "7",
    "source": "ad:auto-match"
  },
  "11": {
    "calendar_name": "Baden-Württemberg",
    "calendar_uid": null,
    "source": "ad"
  }
}
```

| Field | Type | Description |
| ----- | ---- | ----------- |
| key (outer) | `str` | Resource unique ID (integer serialised as string) |
| `calendar_name` | `str` | Display name of the secondary calendar |
| `calendar_uid` | `str \| null` | MPXJ calendar unique ID (integer as string); `null` when the UID was not available at assignment time |
| `source` | `str` | Origin tag — `"ad:auto-match"` for automatic inference, `"ad"` for manually triggered AD assignment, `"manual"` for user-set values |


## Module-level Constant

| Name | Value | Description |
| ---- | ----- | ----------- |
| `_CP_KEY` | `"AD Secondary Calendars"` | Custom property key used to read/write the JSON map |


## Public API

### `get_secondary_calendar_map(project) → dict[str, dict]`

Returns the full `{resource_uid → entry}` dict read from the project custom properties.
Returns `{}` when the project is `None`, the property is absent, or the stored JSON is
malformed.


### `set_secondary_calendar_for_resource(project, resource_uid, calendar_name, calendar_uid=None, source="ad") → None`

Create or update the mapping for one resource.

| Parameter | Type | Description |
| --------- | ---- | ----------- |
| `project` | MPXJ `ProjectFile` | The open project |
| `resource_uid` | int \| str | Resource unique ID |
| `calendar_name` | `str \| None` | Calendar name; passing `None` or `""` **clears** the entry |
| `calendar_uid` | int \| str \| None | Optional calendar UID for faster lookup |
| `source` | `str` | Origin tag written into the entry |

When `calendar_name` is empty or `None` the entry for this resource is removed from the map.


### `resolve_secondary_calendar(project, resource) → dict | None`

Resolve the mapped secondary calendar for a resource to an actual MPXJ calendar object.

**Return values:**

| Case | Return value |
| ---- | ------------ |
| No mapping for this resource | `None` |
| Mapping exists, calendar found | `{"resource_uid", "calendar_name", "calendar_uid", "source", "calendar": <MPXJ object>}` |
| Mapping exists, calendar **not found** | Same dict but with `"calendar": None` |

The lookup tries **UID first** (faster, survives renames), then falls back to a
case-insensitive name match across all project calendars.


### `infer_secondary_calendar_from_ad(project, ad_user: dict) → dict | None`

Score all installed project calendars against the AD user's location metadata and return
the best match.

**Scoring algorithm:**

1. Build a *hint blob* from the AD user dict: `state`, `region`, `city`, `country`,
   `department`, `display_name` fields — concatenated, lowercased.
2. For each non-personal project calendar:
   - +10 points if the full calendar name appears verbatim in the hint blob.
   - +1 point for each name token (≥ 4 characters) that appears in the hint blob.
   - +0–5 bonus points proportional to the number of non-working exceptions defined in
     the calendar (populated calendars are preferred over empty placeholders).
3. Return the calendar with the highest score if that score is > 0; otherwise `None`.

Personal resource calendars (those whose name ends in `" Calendar"` and have ≤ 3 name
tokens) are excluded from scoring to avoid confusing a resource's own work schedule
with a regional holiday calendar.

Returns a dict `{"calendar_name", "calendar_uid", "source": "ad:auto-match", "calendar": <MPXJ object>}`
or `None` when no calendar scores above zero.


### `assign_secondary_calendar_from_ad(project, resource, ad_user: dict) → dict | None`

Infer a secondary calendar via `infer_secondary_calendar_from_ad()` and immediately
persist the result with `set_secondary_calendar_for_resource()`.

Returns the inferred entry dict on success, or `None` when no match is found or
`resource` has no accessible unique ID.


## Integration Points

| Consumer | Usage |
| -------- | ----- |
| `views/team_planner_view.py` — `_get_resource_vacation_blocks()` | Calls `resolve_secondary_calendar()` for each resource; appends secondary calendar exceptions to `_vacations_by_res` with `source="secondary"` and `calendar_name` set |
| `views/resource_view.py` — `add_resource_from_ad()` | Calls `assign_secondary_calendar_from_ad()` after creating the resource |
| `app_debug.py` — `dump_project_state()` | Reads the map and includes a `"secondary_calendar"` block per resource in the debug dump |


## Team Planner Rendering

Secondary calendar exceptions are painted as **semi-transparent yellow** blocks (colour
constants `_C_SECONDARY_FILL` and `_C_SECONDARY_BORDER`) inside the resource swimlane,
visually distinct from personal vacation blocks (orange).  Hovering over a secondary
block shows a `QToolTip` with the exception name, date range, and source calendar name.
Drag-and-drop scheduling treats these blocks as non-working periods in the same way as
personal vacation blocks.
