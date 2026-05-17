# integrations/confluence_calendar_integration.py

Fetches **Confluence Team Calendar** events (public holidays and leave / vacation entries) and applies them as non-working exceptions to MPXJ project and resource calendars.

Authentication is handled transparently via **Playwright / Chromium SSO** — no passwords are stored.  A valid cached session runs entirely headless; an expired or first-time session opens a Chromium window so the user can complete SSO once.


## Authentication Flow

| Scenario | Behaviour |
| - | - |
| State file present and valid | Headless Chromium validates the session; no window opens |
| State file absent or expired | Chromium window opens; user completes SSO; session cached to `~/.confluence_playwright_state.json` (permissions 600) |
| Playwright not installed | `QMessageBox.critical` prompt listing the required `pip install` commands |
| `requests` not installed | `QMessageBox.critical` prompt listing the required `pip install` command |

Cached state is an owner-readable-only JSON file in the user's home directory.  It is consumed by `sync_playwright` and never parsed by application code.


## Configuration — Project Custom Fields

All settings are stored in the project file itself via **MPXJ custom properties**.  Set them via:

> **Project → Project Information → Custom Fields**

| Custom Field Key | Required | Default | Description |
| - | - | - | - |
| `CALENDAR Base URL` | ✅ | — | Confluence server base URL (e.g. `https://confluence.example.com`) |
| `CALENDAR Space Key` | ✅ | — | Confluence space key to query (e.g. `PROJ`) |
| `CALENDAR Timezone` | ❌ | `Europe/Berlin` | IANA timezone ID used for event fetching |
| `CALENDAR Days Ahead` | ❌ | `365` | Sync window in days from today (1–3650) |

The constants `CONFLUENCE_BASE_URL_PROP`, `CONFLUENCE_SPACE_KEY_PROP`, `CONFLUENCE_TIMEZONE_PROP`, and `CONFLUENCE_DAYS_AHEAD_PROP` expose these key names for external use.


## Module-Level Constants

| Name | Value | Description |
| - | - | - |
| `CONFLUENCE_BASE_URL_PROP` | `"CALENDAR Base URL"` | Custom field key for the Confluence server URL |
| `CONFLUENCE_SPACE_KEY_PROP` | `"CALENDAR Space Key"` | Custom field key for the space key |
| `CONFLUENCE_TIMEZONE_PROP` | `"CALENDAR Timezone"` | Custom field key for the timezone |
| `CONFLUENCE_DAYS_AHEAD_PROP` | `"CALENDAR Days Ahead"` | Custom field key for the sync window |
| `_DEFAULT_TIMEZONE` | `"Europe/Berlin"` | Fallback timezone when the field is absent |
| `_DEFAULT_DAYS_AHEAD` | `365` | Fallback look-ahead when the field is absent |
| `_STATE_FILE` | `Path.home() / ".confluence_playwright_state.json"` | Cached Playwright SSO state |


## Public API

### `clear_saved_session() → None`

Deletes the cached Playwright SSO state file (`~/.confluence_playwright_state.json`), forcing a fresh browser-based login on the next sync.


### `get_project_base_url(project) → str | None`

Reads `CALENDAR Base URL` from the project's custom properties.  Returns the URL with any trailing slash stripped, or `None` if the field is absent or empty.


### `get_project_space_key(project) → str | None`

Reads `CALENDAR Space Key` from the project's custom properties.  Returns the raw string value or `None`.


### `get_project_timezone(project) → str`

Reads `CALENDAR Timezone` from the project's custom properties.  Falls back to `"Europe/Berlin"` when the field is absent.


### `get_project_days_ahead(project) → int`

Reads `CALENDAR Days Ahead` from the project's custom properties.  The value is validated to be an integer in the range **1 – 3650**; values outside this range or non-numeric values fall back to `365`.


### `ConfluenceCalendarSync`

The main public class.  A single instance is created on first use and stored on `MainWindow`; there is no persistent state between `run()` calls.

#### `run(project, parent_widget=None, history_manager=None, settings_manager=None) → None`

Executes the full sync pipeline:

1. Check optional dependencies (`requests`, `playwright`); show a critical dialog and return early if either is missing.
2. Validate that `project` is not `None`.
3. Read `CALENDAR Base URL` and `CALENDAR Space Key` from the project custom fields; show an information dialog listing any missing fields and return early.
4. Read `CALENDAR Timezone` and `CALENDAR Days Ahead` (using defaults when absent).
5. Resolve KeePass credentials: if `settings_manager` is provided and a Confluence KeePass entry is configured (see `SettingsManager.get_confluence_keepass_entry`) and the database is unlocked, look up the entry and pass `(username, password)` as `keepass_creds` to `_try_playwright_auth`.  If any of these conditions are not met, `keepass_creds` remains `None`.
6. Authenticate via `_try_playwright_auth(base_url, keepass_creds=keepass_creds)`.
7. If `history_manager` is provided, call `history_manager.push_all()` to snapshot the pre-sync state, making the entire sync undoable in a single step.
8. Compute `today`, `until = today + days_ahead`, and `prune_cutoff = today - 30 days`.
9. Fetch all sub-calendars for the space via `_fetch_subcalendars`, then filter to holiday / leave calendars with `_filter_relevant`.
10. For each relevant calendar, fetch events in the window `[today, until]` via `_fetch_events`.
11. Categorise events: *leaves* / *vacation* / *urlaub* calendars → `vacation_events`; everything else → `holiday_events`.
12. Apply the events to the project via `_apply_to_project`, passing `sync_start=today`, `sync_end=until`, and `prune_before=prune_cutoff`.
13. Show a summary `QMessageBox.information` with counts of added exceptions, removed stale exceptions, pruned expired exceptions, and any individual calendar fetch errors.


## Private Helpers

### `_autofill_microsoft_sso(page, username, password) → bool`

Attempts to pre-fill the **Microsoft Azure AD SSO** login form in an open Playwright `Page`:

1. Checks that `page.url` contains `login.microsoftonline.com`; returns `False` immediately for any other URL.
2. Waits for the email input selector (`input[type='email'], #i0116`) to appear.
3. Fills the email field, clicks **Next** (`#idSIButton9`), waits for the password field (`input[type='password'], #i0118`).
4. Fills the password field and clicks **Sign in** (`#idSIButton9`).
5. Returns `True` on success, `False` if any selector times out or an exception occurs.

The function deliberately stops after clicking Sign in — MFA prompts (authenticator app, SMS code, etc.) are always completed manually by the user.  The browser window remains open until the user confirms login.

### `_playwright_session(ctx, base_url) → requests.Session`

Builds a `requests.Session` from the cookies in a Playwright browser context.  Sets a browser-compatible `User-Agent`, `Accept`, and `X-Requested-With` header so the Confluence REST API accepts the requests.

### `_try_playwright_auth(base_url, keepass_creds=None) → tuple[requests.Session, str] | None`

Tries the cached headless session first; falls back to opening a visible Chromium window for SSO login.

- **Headless path**: loads `~/.confluence_playwright_state.json`, navigates to `/rest/api/user/current`, and returns `(session, display_name)` on success.
- **Interactive path**: opens a visible browser, navigates to `base_url`.  If `keepass_creds` is a `(username, password)` tuple, calls `_autofill_microsoft_sso` once the browser detects `login.microsoftonline.com` in the URL — pre-filling the email and password so the user only needs to complete MFA.  Waits up to 5 minutes for the user to complete SSO (detected by a URL match), saves the new state file, and verifies the session via the REST API.
- Returns `None` on `PlaywrightTimeout` or any other error.

### `_flatten_calendars(raw_items) → list[dict]`

Flattens the nested `subCalendars` / `childSubCalendars` structure returned by the Confluence REST API into a plain list of sub-calendar dicts.  Only non-`"parent"` type entries are included.

**Input structure (example)**

```python
[
    {
        "subCalendar": {"id": "abc", "type": "custom", "name": "Holidays"},
        "childSubCalendars": [
            {"subCalendar": {"id": "xyz", "type": "leaves", "name": "Leave"}}
        ]
    }
]
```

### `_fetch_subcalendars(session, base_url, space_key) → list[dict]`

Calls `GET /rest/calendar-services/1.0/calendar/subcalendars.json` and returns the flattened list of sub-calendars.  Raises `requests.HTTPError` on a non-2xx response.

### `_filter_relevant(calendars) → list[dict]`

Keeps only calendars whose `type` is `"leaves"` or `"custom"`, **or** whose name contains a keyword from `{"holiday", "leave", "vacation", "feiertag", "urlaub"}` (case-insensitive).

### `_fetch_events(session, base_url, calendar_id, start, end, timezone) → list[dict]`

Calls `GET /rest/calendar-services/1.0/calendar/events.json` for a single sub-calendar within a date range.  Returns the event list extracted from the `"events"`, `"payload"`, or raw-list response shapes.

### `_parse_date(value) → date | None`

Parses an ISO-8601 date string (or any string whose first 10 characters form a valid `YYYY-MM-DD` date).  Returns `None` for empty / `None` input or an unparseable string.

### `_apply_to_project(project, holiday_events, vacation_events, sync_start=None, sync_end=None, prune_before=None) → tuple[int, int, int, int, int]`

Writes calendar exceptions into the MPXJ project:

| Event type | Target calendar | Matching strategy |
| - | - | - |
| Holiday | Project default calendar | All holidays added unconditionally |
| Vacation | Per-resource calendar | Matched by `userName` field; partial / substring match used as fallback; **auto-creates resource** if no match found |

**Holiday filtering:** Only events where `start == end` (duration = 0 days) are written to the project default calendar.  Any event where `end` differs from `start` (duration > 0 days) is silently skipped.  This prevents multi-day blocks — such as school-holiday spans (*Schulferien*) or collective closures — from being written as anonymous multi-day `ProjectCalendarException` entries, which would otherwise grey out entire weeks for all resources in the Team Planner.

**Stale-entry removal** (forward window): when `sync_start` and `sync_end` are provided, any existing calendar exception whose start date falls in `[sync_start, sync_end]` but has no corresponding event in the new `vacation_events` list is deleted first.  This ensures vacations that were cancelled or deleted in Confluence are removed from the project.

**Expired-entry pruning** (backward cutoff): when `prune_before` is provided, any calendar exception — on both the default (holiday) calendar and every resource calendar — whose **end** date is strictly before `prune_before` is deleted.  `run()` always passes `today - 30 days` as this cutoff, so exceptions older than one month are automatically cleaned up on every sync.

**Resource calendar creation**: if a matched resource has no personal calendar, one is created (named `"{Resource Name} Calendar"`) derived from the project default calendar.  If no default exists, default working days and hours are added.

**Resource auto-creation**: when a vacation event's `userName` has no matching resource (exact or partial), a new resource is created automatically with the name from the event.  This ensures all vacation events are imported even if the project's resource list is incomplete.  Empty or blank userNames are skipped.

Returns `(n_holidays_added, n_vacations_added, n_vacations_removed, n_pruned, n_resources_created)`.

### `_validate_base_url(base_url) → str`

Validates that `base_url` is an `https://` URL.  Returns the normalised URL on success; raises `ValueError` with a descriptive message for non-HTTPS URLs or malformed URLs.  This enforces secure connections to protect SSO session cookies.

### `_restrict_file_permissions(path) → None`

Platform-specific file permission restriction to owner-only access:

- **Windows**: uses `icacls` to remove inheritance and grant the current user Full Control only
- **POSIX**: sets permissions to `0o600` via `chmod`

All exceptions are silently ignored to prevent failures on restricted file systems or unsupported platforms.

### `_get_custom_prop(project, key) → str | None`

Reads a single key from `project.getProjectProperties().getCustomProperties()`.  Returns a stripped, non-empty string, or `None` if the key is missing, blank, or any exception occurs.


## Calendar Relevance Heuristic

The module uses a two-tier filter (`_filter_relevant`) to decide which Confluence calendars to sync:

1. **Type match**: `cal["type"]` in `{"leaves", "custom"}`
2. **Name match**: any of `{"holiday", "leave", "vacation", "feiertag", "urlaub"}` appears in the name (lowercase)

Calendars matching **either** criterion are included.  Parent calendars (type `"parent"`) are always excluded by `_flatten_calendars`.


## Vacation Event → Resource Matching

Each vacation event is matched to an MPXJ resource using this precedence:

1. **Exact match**: `event["userName"].lower() == resource.getName().lower()`
2. **Partial match**: the event's user string is a substring of the resource name, or vice versa

If no resource matches and the `userName` is non-blank, **a new resource is auto-created** with that name (see `_apply_to_project` → resource auto-creation).  Events with empty or blank userNames are skipped.  All matching is case-insensitive.


## Dependencies

| Package | Role | Optional? |
| - | - | - |
| `requests` | HTTP calls to Confluence REST API | No (checked at runtime) |
| `playwright` | Chromium SSO authentication | No (checked at runtime) |
| `jpype` (via MPXJ) | `java.time.LocalDate` for calendar exceptions | No (available when JVM is running) |
| `PyQt5` | `QMessageBox` for user feedback | No (always present) |

Missing `requests` or `playwright` triggers a `QMessageBox.critical` dialog rather than a crash.


## Security Notes

- The Playwright state file is written with **permissions 600** (owner read/write only).
- No credentials are stored by application code.  The state file is a browser cookie dump managed entirely by Playwright.
- All HTTP requests use `verify=True` (TLS certificate validation is always enforced).
- A `X-Requested-With: XMLHttpRequest` header is sent on REST calls to satisfy Confluence CSRF requirements.


## Testing

The module is fully tested in `tests/test_confluence_calendar_integration.py` with comprehensive coverage of all public and private functions:

| Test Class | Coverage Areas |
| - | - |
| `TestConstants` | Module-level constant values |
| `TestFlattenCalendars` | Nested structure flattening, parent filtering, edge cases |
| `TestFilterRelevant` | Type and keyword matching, case-insensitivity |
| `TestParseDate` | ISO date parsing, datetime strings, invalid inputs |
| `TestValidateBaseUrl` | HTTPS enforcement, HTTP rejection, malformed URL detection |
| `TestRestrictFilePermissions` | Windows (`icacls`) and POSIX (`chmod`) platform-specific handling, exception safety |
| `TestGetCustomProp` | Custom field reading, whitespace stripping, exception handling |
| `TestGetProjectBaseUrl` | Trailing slash normalization |
| `TestGetProjectSpaceKey` | Raw value retrieval |
| `TestGetProjectTimezone` | Default fallback logic |
| `TestGetProjectDaysAhead` | Range validation (1–3650), non-numeric fallback |
| `TestApplyToProject` | Holiday/vacation exception writing, resource matching (exact/partial), calendar creation; multi-day holiday spans skipped (Schulferien filter) |
| `TestApplyToProjectRemoval` | Stale-entry removal in sync window, expired-entry pruning, combined operations |
| `TestResourceAutoCreation` | Auto-creation of resources for unmatched usernames, blank username handling, duplicate prevention |
| `TestPlaywrightSession` | Cookie transfer from browser context, header configuration |
| `TestClearSavedSession` | State file deletion, missing file safety |
| `TestConfluenceCalendarSyncRun` | All early-exit branches, dependency checks, auth flow, `history_manager.push_all()` ordering, summary message |
| `TestConfluenceCalendarSyncInvalidUrl` | Invalid URL error messages in `run()` |

All tests run fully offline without a JVM, Confluence server, or browser by mocking `requests`, `playwright`, `jpype`, and `PyQt5` dependencies.  The test suite completes in under a second.

**Key test patterns:**

- **Mocked dependencies**: `requests` and `playwright` are stubbed in `sys.modules` before the module is imported
- **Java mocking**: `jpype.JClass` is patched to return a mock `LocalDate` factory
- **Qt dialogs**: `QMessageBox` is patched to capture dialog calls without displaying UI

Run the Confluence Calendar tests:

```bash
pytest tests/test_confluence_calendar_integration.py -v
```
