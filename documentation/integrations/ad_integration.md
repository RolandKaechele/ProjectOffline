# Active Directory Integration

## Overview

The `src/integrations/ad_integration.py` module queries corporate Active Directory (AD)
to look up user details (display name, email, department, SAM account name) and
synchronise them with the project resource sheet.  Lookups are performed via
**PowerShell `Get-ADUser`**, which is available on domain-joined Windows machines with
RSAT installed — exactly the same mechanism demonstrated in
`diagnostic-scripts/test_ad_email_lookup.py`.


## Prerequisites

| Requirement | Notes |
| ----------- | ----- |
| Windows (domain-joined) | PowerShell AD queries require domain membership |
| PowerShell | Must be available on `PATH` |
| RSAT — ActiveDirectory module | `Get-Module -ListAvailable -Name ActiveDirectory` must return a result |

Install RSAT if the module is missing:

```powershell
# PowerShell (Administrator)
Add-WindowsCapability -Online -Name Rsat.ActiveDirectory.DS-LDS.Tools~~~~0.0.1.0
```


## LDAP Query Patterns

The diagnostic script `diagnostic-scripts/test_ad_email_lookup.py` demonstrated three
lookup strategies.  The integration module implements all three as a fallback chain so
that names with diacritics, compound given-names, or variant capitalisation still resolve
correctly.

### Strategy 1 — Display Name (exact match)

```powershell
Get-ADUser -Filter "DisplayName -eq '<Display Name>'" `
           -Properties DisplayName, mail, Department, SamAccountName |
    Select-Object DisplayName, mail, Department, SamAccountName
```

Most reliable when the resource name in the project file exactly matches the AD
`DisplayName` attribute (e.g. `"Grubitz, Stefan"`).

### Strategy 2 — Surname + GivenName split

```powershell
Get-ADUser -Filter "Surname -eq '<Surname>' -and GivenName -eq '<GivenName>'" `
           -Properties DisplayName, mail, Department, SamAccountName |
    Select-Object DisplayName, mail, Department, SamAccountName
```

Fallback when the display name is stored differently.  The integration module splits on
`", "` (comma-space) to extract surname and given name.

### Strategy 3 — Email address (direct lookup)

```powershell
Get-ADUser -Filter "mail -eq '<email@domain.com>'" `
           -Properties DisplayName, mail, Department, SamAccountName |
    Select-Object DisplayName, mail, Department, SamAccountName
```

Used by the `lookup_by_email()` API entry point, which is called by other modules such
as the Jira sync to resolve task assignees when only an email is available.

### Strategy 4 — SAM account name

```powershell
Get-ADUser -Identity '<samaccountname>' `
           -Properties DisplayName, mail, Department, SamAccountName |
    Select-Object DisplayName, mail, Department, SamAccountName
```

Used by `lookup_by_username()`.  SAM account names are stable identifiers that survive
display-name changes.


## Module API

All public functions return a `dict` or `None`.  The dict shape is:

```python
{
    "display_name": str,       # AD DisplayName
    "email":        str,       # mail attribute
    "department":   str | None,
    "username":     str,       # SamAccountName
    "city":         str,       # l (locality) LDAP attribute; empty string when absent
    "state":        str,       # st (state/province) LDAP attribute; empty string when absent
    "country":      str,       # co (country name) LDAP attribute; empty string when absent
}
```

### `is_ad_available() -> bool`

Returns `True` when PowerShell is accessible and the `ActiveDirectory` module is loaded.
Call this before any lookup to avoid unnecessary subprocess timeouts.

### `lookup_by_name(name: str) -> dict | None`

Look up a user by display name.  Accepts `"Surname, GivenName"` format.
Tries Strategy 1 first, then Strategy 2.  Returns `None` if not found.

### `lookup_by_email(email: str) -> dict | None`

Look up a user by their email address (Strategy 3).

### `lookup_by_username(username: str) -> dict | None`

Look up a user by their SAM account name / login (Strategy 4).

### `lookup_by_email_all(email: str) -> list[dict]`

Look up **all** AD accounts that match an email address.  Uses a two-step strategy:

1. **Fast path** — executes `mail -eq '<email>'` (indexed, typically < 1 s); returns
   immediately if a match is found.
2. **Slow path** — falls back to `mail -like '*<email>*'` wildcard scan only when the
   exact match returns nothing.  The wildcard scan is unindexed and may take 20–30 s on
   large directories; it is skipped whenever the fast path succeeds.

Returns a list of matching dicts (may be empty; never `None`).

### `lookup_by_username_all(username: str) -> list[dict]`

Look up **all** AD accounts that match a SAM account name.  Uses the same two-step
strategy:

1. **Fast path** — `Get-ADUser -Identity '<username>'` (indexed, typically < 1 s);
   returns immediately if the account is found.
2. **Slow path** — falls back to `SamAccountName -like '*<username>*'` wildcard scan
   only when the identity lookup raises an error (account not found).

Returns a list of matching dicts (may be empty; never `None`).

### `sync_resources(project) -> dict`

Iterates all resources in the MPXJ `ProjectFile`.  For each resource that has a name
but no email address, it calls `lookup_by_name()` and — if found — writes the email,
department, and a resource note back into the resource object.

Returns a summary dict:

```python
{
    "total":   int,   # resources examined
    "updated": int,   # resources updated with AD data
    "skipped": int,   # resources already had an email / not found in AD
    "errors":  list,  # list of {"resource": name, "error": message}
}
```

The result dict is consumed by `app_debug.py` for the debug dump
(`payload["ad_sync_result"]`).

### `add_resource_from_ad()` (ResourceView method)

Triggered by the **Add from AD** button in the *Resource Insert* ribbon group.
The workflow is:

1. **Search dialog** — opens `ADSearchDialog` where the user types a name; results
   are fetched from AD and displayed as a list (supports multiple matches).
2. **Duplicate guard** — if a resource with the same name already exists in the
   project (case-insensitive comparison), a warning is shown and the operation
   is aborted.  No override is possible; the user must edit the existing resource.
3. **Resource dialog** — opens `ResourceDialog` pre-filled with the AD data
   (display name, email, department, username) for review before creating.
4. **ID assignment** — after `project.addResource()`, the new resource receives
   the next free integer ID immediately (via `setID()`), so the resource sheet
   shows the ID column without requiring a save/reload cycle.
5. **Personal calendar** — `_create_resource_calendar()` creates a personal work
   calendar for the new resource.  It copies the **day-of-week work types** from
   the project default calendar (via `setCalendarDayType()`), but does **not** call
   `setParent()` and does **not** copy calendar exceptions.  This ensures company
   holidays are managed centrally on the default calendar and do not bleed into the
   individual resource calendar.
6. **Secondary calendar** — after the resource is created, `add_resource_from_ad` calls
   `assign_secondary_calendar_from_ad()` from `secondary_calendar_integration.py`.  This
   scores all installed project calendars against the AD user's `city`, `state`, and
   `country` fields and automatically assigns the best-matching regional holiday calendar
   to the resource.  The assignment is persisted in the project custom property
   `"AD Secondary Calendars"` as a JSON entry keyed by resource UID.  If no calendar
   scores above zero the step is silently skipped.


## Settings

AD integration settings are stored via `QSettings` through the `SettingsManager`:

| Setting key | Type | Default | Description |
| ----------- | ---- | ------- | ----------- |
| `ad/enabled` | bool | `False` | Master switch |
| `ad/auto_sync_on_open` | bool | `False` | Run sync when a project file is opened |
| `ad/timeout_seconds` | int | `60` | PowerShell subprocess timeout per query |


## Debug Dump

When `--debug` is active, `dump_project_state()` in `app_debug.py` includes an
`"ad_sync_result"` block:

```json
"ad_sync_result": {
    "available": true,
    "sync": {
        "total":   12,
        "updated":  3,
        "skipped":  9,
        "errors":  []
    },
    "lookups": [
        {"fn": "lookup_by_name", "input": "Smith, John",
         "result": {"display_name": "John Smith", "email": "j.smith@corp",
                    "department": "Engineering", "username": "jsmith"}},
        {"fn": "lookup_by_email", "input": "unknown@corp", "result": null}
    ]
}
```

`"available"` reflects `is_ad_available()` at dump time.  `"sync"` contains the last
result returned by `sync_resources()` (all fields `null` when no sync has been run in
the current session).  `"lookups"` is the full lookup history from
`get_last_lookup_results()` — all individual lookup calls accumulated since process start.
