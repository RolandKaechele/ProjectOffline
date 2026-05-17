# dialogs.py

Provides the modal detail dialogs that open when a user double-clicks a row in any view.

## Visual Design

All dialogs share a consistent look:

- **Blue header bar** (`#2B579A`) with a white title and an optional lighter subtitle.
- **Tabbed content** area with `QTabWidget`.
- **OK / Cancel** (or **Close** for read-only) buttons, styled in the same blue.

The shared QSS string `_DIALOG_STYLE` is applied to every `QDialog` instance.


## Shared Helpers

### `_make_header(title, subtitle="") → QFrame`

Returns a styled blue `QFrame` used as the top-most widget in every dialog layout.

### `_make_button_row(dialog, ok_label, cancel_label, read_only) → QWidget`

Returns a right-aligned button row.  In read-only mode only a **Close** button is shown.

### `_BaseDialog`

Base class for all dialogs.  Sets minimum width (520 px), enables modality, and applies `_DIALOG_STYLE`.


## `_propagate_schedule(all_tasks, changed_deltas)`

Propagates date shifts forward through the task network when a predecessor's finish date changes (e.g. after the user edits a task in the dialog).

**Parameters**

| Name | Type | Description |
| - | - | - |
| `all_tasks` | iterable | All MPXJ `Task` objects in the project |
| `changed_deltas` | `dict[int, int]` | Maps `task_unique_id → delta_days` |

**Relation-type rules**

| Type | Propagated? | Reason |
| - | - | - |
| `FINISH_START` | Yes | Successor start depends on predecessor finish |
| `FINISH_FINISH` | Yes | Successor finish depends on predecessor finish |
| `START_START` | No | Depends on predecessor start (unchanged) |
| `START_FINISH` | No | Depends on predecessor start (unchanged) |

Uses BFS so that changes cascade through chains of dependencies without re-visiting a node.


## Dialogs Reference

### Task Information Dialog

Opens on double-click in **TaskView** or **GanttView**.

**Constructor**

```python
TaskDialog(task, project, parent=None, timeline_view=None)
```

Pass `timeline_view` to expose the **Show in Timeline** checkbox on the General tab.  `GanttView` and `ResourceUsageGraphView` always supply this argument; other callers may omit it.

**Tabs**

| Tab | Fields |
| - | - |
| General | Name, ID, Outline level, Start, Finish, Duration, % Complete, Milestone flag, Critical flag, Show in Timeline (checkbox — only present when `timeline_view` is supplied) |
| Predecessors | Editable table of predecessor links (Task ID, Name, Link Type, Lag) |
| Resources | Editable table of resource assignments (see below) |
| Custom Fields | Read-only table of custom field values (Alias, Value) — field definitions managed via Project Information |
| Notes | Free-text notes field (QTextEdit) |

**Resources tab behaviour**

- The resource selector drop-down is populated **only** from resources present in the current project (never from a stale or empty list).
- Each assignment row displays the resource name resolved by **Unique ID** — if a resource was added without a UID, it would appear as "(unknown)"; the auto-UID assignment in `ResourceView` prevents this.
- Each assignment row includes a per-row **✕ delete button**.  Clicking it removes that specific assignment without affecting other rows.  The row-level delete replaces the old global "Remove" button.

Accepts changes and writes them back to the MPXJ `Task` object via its Java setter methods.  After editing dates, `_propagate_schedule` is called to shift affected successors.

**Show in Timeline checkbox**

- Shown only when `timeline_view` is not `None`.
- Pre-checked when the task is already pinned: queries `timeline_view.is_task_pinned(tid)` or `is_milestone_pinned(tid)` using the integer task ID.
- On OK, pins or unpins the task/milestone depending on the final checkbox state.


**% Complete behaviour**

- When the user sets `% Complete` to a value **< 100** the dialog calls `t.setActualFinish(None)` to clear any `actualFinish` that MPXJ may have auto-set when the task previously reached 100%.  Without this, the overdue check in `_get_indicators` would incorrectly suppress the orange indicator even after the task is reverted to incomplete.
- When `% Complete ≥ 100` the task is considered fully done; `actualFinish` is kept.

**Critical flag display**

- The **Critical** field reads `getCritical()` from MPXJ but overrides the displayed value to `No` whenever `% Complete ≥ 100`, because a finished task cannot affect the project end date regardless of what the internal flag says.

> **Custom Fields tab**: displays all task-level custom field values (Text, Number, Cost, Date, Flag, Duration slots) that have been defined in the project.  Values are editable; field aliases and slot definitions are managed centrally in the *Project Information → Custom Fields → Task Fields* subtab.


### Resource Information Dialog

Opens on double-click in **ResourceView**.

**Tabs**

| Tab | Fields |
| - | - |
| General | Avatar, Name, Type, E-Mail, Department, Max Units, Standard Rate, Overtime Rate |
| Active Directory | AD Display Name (read-only), Username (read-only), E-Mail, Department, City, Country (editable combo box) |
| Custom Fields | Read-only table of custom field values (Alias, Value) — field definitions managed via Project Information |
| Notes | Free-text notes field |

**Avatar (64 px circular)**

A 64×64 px circular image widget is shown in the dialog header.  If an AD photo has been fetched via *Look up in AD…*, it is displayed; otherwise a type-emoji fallback is rendered:

| Resource Type | Fallback emoji |
| - | - |
| Work | 👤 |
| Material | 📦 |
| Cost | 💰 |

**Field order and type-conditional visibility**

The **Type** selector is positioned directly below **Name** so it governs the rest of the form.  The **E-Mail** and **Department** rows — together with the **Look up in AD…** button — are visible **only** when Type is *Work*; switching to *Material* or *Cost* hides these rows via `_update_ad_btn_visibility()`.

**Duplicate-name guard**

When the user clicks **OK**, `_is_duplicate_name(name, uid)` is called against all existing resources.  If a conflict is detected the changes are rolled back and a `QMessageBox` warning is shown; the dialog stays open for correction.

**Type persistence**

`apply_to_resource()` calls `r.setType()` so the resource type is written back to the MPXJ model and survives the next file save/reload cycle.

**AD photo and department sidecar**

After a successful AD lookup and user confirmation, the fetched photo bytes are stored in `dialogs._resource_thumbnail_store[uid]` and the department string in `dialogs._resource_dept_store[uid]`.  On project save these in-memory stores are serialised to `<project-basename>.thumbnails.json`:

```json
{
  "resources": {
    "42": {
      "thumbnail": "<base64-encoded JPEG>",
      "department": "Engineering / Embedded Systems"
    }
  }
}
```

Entries are pruned from both the in-memory store and the sidecar when the corresponding resource is deleted.  The sidecar is loaded back into `_resource_thumbnail_store` / `_resource_dept_store` when the project is opened.

**Active Directory tab**

The **Active Directory** tab (`_tab_active_directory`) is always present and exposes the full set of AD-sourced location attributes alongside the email address:

| Field | Source (pre-fill order) | Editable | Saved via |
| - | - | - | - |
| AD Display Name | `_ad_data["display_name"]` | No | — |
| Username | `_ad_data["username"]` | No | — |
| E-Mail | `_ad_data["email"]` → `EMAIL_ADDRESS` field → `getEmailAddress()` | Yes | `setEmailAddress()` (when non-empty) |
| Department | `_ad_data["department"]` → `TEXT2` resource field | Yes | MPXJ `TEXT2` |
| City | `_ad_data["city"]` → `TEXT1` resource field | Yes | MPXJ `TEXT1` |
| Country | `_ad_data["country"]` → `TEXT3` resource field | Yes | MPXJ `TEXT3` |

The Country field is an **editable `QComboBox`** pre-populated with a full list of country names (`_COUNTRIES`); the user can type freely or select from the list.

On `apply_to_resource()`, values from this tab are written to the MPXJ resource object: E-Mail via `setEmailAddress()` (skipped when empty), and City / Department / Country stored in TEXT1 / TEXT2 / TEXT3 resource fields via `r.set(ResourceField.TEXT1, ...)` etc.

**Max Units display and storage**

MPXJ's `getMaxUnits()` returns values on two scales depending on file format: a **fraction** (e.g. `1.0` = 100%) for MSPDI/XML files, and a **percentage** (e.g. `100.0` = 100%) for MPP binary files.  The dialog normalises the raw value for display using the heuristic `raw × 100 if raw ≤ 2.0 else raw`, showing the user a familiar percentage like `100%`.  When the user saves a new value, it is always written back as a fraction (`user_value ÷ 100`) so the MPXJ round-trip is consistent regardless of source format.


### Dependency Dialog

Opens on double-click in **DependencyView** or when adding a new dependency.

**Fields**

| Field | Description |
| - | - |
| Successor Task | Combo box selecting the task that depends on another |
| Predecessor Task | Combo box selecting the task that must finish first |
| Link Type | FS / FF / SS / SF |
| Lag | Duration string (e.g. `1d`, `0d`) |


### Baseline Entry Dialog

Opens on double-click in **BaselineView**.  Read-only.  Shows baseline vs. current dates
and durations side by side for a single task.

> **Note:** The **Set Baseline** and **Clear Baselines** dialogs are defined in `ui.py`
> (as inline `QDialog` instances, not subclasses here) because they need live access to
> both the project and the ribbon combo state.  See `ui.py` — *Baseline Actions* for
> details.


### Assignment Details Dialog

Opens from the Resources tab inside the Task Information dialog.  Allows editing the **Units %** of a specific resource assignment.


### Project Information Dialog

Opens via **Project → Project Information…** (`Alt+F11`).

**Tabs**

| Tab | Contents |
| - | - |
| Summary | High-level display of title, author, subject, manager, company |
| Project | Editable project metadata (title, author, subject, manager, company, category, keywords, comments) |
| Calendar | Default calendar name and working-day configuration |
| Calendars | List of all project calendars with non-working exception editor |
| Currency | Currency symbol, decimal separator, and thousands separator |
| Settings | Application-specific display settings |
| Custom Fields | Three inner subtabs: **Project Properties**, **Task Fields**, **Resource Fields** |

**Custom Fields tab — inner subtabs**

| Subtab | Description |
| - | - |
| Project Properties | Free-form key–value pairs stored in `ProjectProperties.getCustomProperties()` |
| Task Fields | Add, delete, and alias `TaskField` custom-field slot definitions (Text1–30, Number1–20, Cost1–10, Date1–10, Flag1–20, Duration1–10); changes are written via `CustomFieldContainer.getOrCreate(ft).setAlias()` |
| Resource Fields | Same as Task Fields but for `ResourceField` slots |

Displays project-level properties read from `ProjectProperties`:

| Field | MPXJ getter |
| - | - |
| Project Title | `getName()` |
| Author | `getAuthor()` |
| Subject | `getSubject()` |
| Start Date | `getStartDate()` |
| Finish Date | `getFinishDate()` |
| Status Date | `getStatusDate()` |
| Calendar | `getCalendarName()` |

**Project tab — new project defaults**

When the Project Information dialog is opened for a **brand-new project** (i.e. the
project currently has no start date), the **Start Date** and **Finish Date** fields are
pre-filled with today's date so the user has a sensible baseline to edit rather than a
blank field.  The *Current Date* field that appeared on this tab in earlier versions
has been removed to keep the layout compact.

The **Default Start Time** and **Default Finish Time** fields default to `08:00` and
`17:00` respectively for new projects, matching a standard 9-hour working day.

**Calendars tab — action buttons**

In addition to the standard *Add* / *Remove* / *Edit exceptions* controls the Calendars
tab now provides two extra buttons:

| Button | Action |
| ------ | ------ |
| **Import ICS…** | Opens a file dialog; reads any `.ics` / `.ical` iCalendar file and converts every `VEVENT` with `DTSTART` into a non-working exception on the currently selected calendar.  Events with both `DTSTART` and `DTEND` spanning multiple days generate one exception per day in the range. |

**Calendar name list sizing:** the calendar name list widget is sized so that calendar names are displayed in full without truncation, even for long names.
| **Add Holidays…** | Opens `NewProjectCalendarsDialog` so the user can install additional regional or country-specific holiday sets into the selected calendar at any time (not just during new-project creation). |

All calendar exception columns use a fixed 110 px width to prevent truncation.
Tooltips are shown on all calendar UI controls to guide the user.


### `NewProjectCalendarsDialog`

A compact `QDialog` shown in two contexts:

1. **Immediately after** `File → New` — `MainWindow._setup_new_project_calendars()` calls
   it so the user can select optional regional calendars alongside the automatically
   created "Standard (Deutschland)" national holiday calendar.
2. Via the **Add Holidays…** button on the Calendars tab of Project Information, for
   adding calendars to an already-open project.

**Layout**

- A short instruction label at the top.
- A **German federal states** section: 15 `QCheckBox` entries, one per state, listed
  alphabetically.
- An **Other countries** section: 5 `QCheckBox` entries (France, India, Romania,
  China, Japan).
- Standard **OK / Cancel** buttons.

All checkboxes start unchecked; the user picks only the extra calendars they need.

**Module-level constants**

| Constant | Value |
| -------- | ----- |
| `_GERMAN_STATES` | Tuple of 15 state names (alphabetical order) |
| `_OTHER_COUNTRIES` | Tuple of 5 country names: `"France"`, `"India"`, `"Romania"`, `"China"`, `"Japan"` |

**Public method**

```python
dialog.get_selected() → list[tuple[str, str]]
```

Returns a list of `(kind, name)` tuples where `kind` is either `"state"` or
`"country"` and `name` is the display string (e.g. `("state", "Bayern")` or
`("country", "France")`).  Returns `[]` when the dialog is cancelled or no
checkboxes are ticked.

**Calendar UID null-safety in `_cal_add_holidays`**

After MPXJ creates a new calendar via `addCalendar()` or `addCalendarDays()`,
the returned `ProjectCalendar` object may have a `null` Java unique ID (mapped
to Python `None`).  When this happens, `_cal_add_holidays` derives the next
available integer UID from the set of UIDs already present in the project's
calendar list and assigns it via `setUniqueID(_JInt(uid))` before using the
calendar.  This prevents a `TypeError: int() argument must be … not 'NoneType'`
at runtime.

