# settings_dialogs.py

Provides all configuration dialogs for KeePass and Jira integration.  All dialogs share the same blue MS-Project-style visual language as `dialogs.py`.

## Shared Helpers

### `_make_header(title, subtitle="") → QFrame`

Blue header bar (`#2B579A`) with a white bold title and an optional lighter subtitle.

### `_btn(label, flat=False) → QPushButton`

Returns a styled `QPushButton`.  Flat buttons use a light blue background suitable for secondary actions.

### `_button_row(*buttons) → QWidget`

Right-aligned horizontal button row used at the bottom of every dialog.

### `_pwd_field_row(form, label, placeholder) → QLineEdit`

Adds a password row to a `QFormLayout`.  Includes a **Show / Hide** toggle button that switches the echo mode.  Returns the `QLineEdit`.

### `_browse_row(form, label, placeholder, existing, browse_slot) → QLineEdit`

Adds a `(QLineEdit + Browse…)` row to a `QFormLayout`.  Returns the `QLineEdit`.

### `_kf_row(form, label, existing, browse_slot, generate_slot) → QLineEdit`

Adds a `(QLineEdit + Browse… + Generate…)` row for key files.  Used on both Open and Create pages of `KeePassConfigDialog`.  Returns the `QLineEdit`.


## `KeePassConfigDialog`

Opens an existing KeePass database **or** creates a new one.

```
Settings → KeePass Configuration…
```

### Modes (radio buttons)

| Mode | Page content |
| - | - |
| **Open existing database** | Database file (Browse), Key file (Browse + Generate), Master password (Show/Hide), Save password checkbox, **Unlock** button |
| **Create new database** | New .kdbx save path (Browse), Key file (Browse + Generate), Password + Confirm password (Show/Hide), Save password checkbox |

**Validation (Open):** Database path must be filled.  Password is attempted; on failure a status message is shown in red.

**Validation (Create):** At least one of password or key file must be provided.  If a password is entered, the confirmation must match.  `.kdbx` is appended automatically if missing.

### Key file generation

Both pages expose a **Generate…** button that:

1. Opens a save-file dialog.
2. Calls `SettingsManager.generate_key_file()` (writes **64 random binary bytes**).
3. Fills the key file field and shows a green status message.

pykeepass treats a 64-byte binary file as a hex-encoded 32-byte key (each byte of the
stored file represents one nibble of the actual 256-bit key material).

On the **Open existing** page the generated file would need to be applied to the database externally (e.g. in KeePass desktop "Change Master Key").  On the **Create new** page pykeepass uses it immediately during database creation.

### Dialog header subtitle

The blue header subtitle updates dynamically when the user toggles between the radio
buttons via `_on_mode_changed()`:

| Mode | Subtitle |
| ---- | -------- |
| Open existing database | *Open an existing database* |
| Create new database | *Create a new KeePass database* |

### Browse / path handling

- **_browse_new_db** opens the save-file dialog in `~/Documents` (falls back to `~` if
  that directory does not exist).
- **_accept_create** converts the entered path to an absolute path via
  `os.path.abspath()` and writes it back to the field before calling
  `KeePassManager.create_db()`, so the dialog always shows (and persists) a fully
  qualified path.

### Status label

Shared across both pages.  Success messages are shown in green (`#107C10`), errors in red (`#C00000`).

### Confluence SSO Auto-fill section

Below the status label, a `QGroupBox` labelled **"Confluence SSO Auto-fill"** (`_confluence_group`) is shown **only when** the KeePass DB is already unlocked when the dialog opens (or after a successful unlock via the Unlock button).

| Control | Description |
| - | - |
| `_confluence_entry_combo` (`QComboBox`, editable) | Prepended with an empty item, followed by all entries from `SettingsManager.list_keepass_entries()`.  The saved entry (`get_confluence_keepass_entry()`) is pre-selected if it appears in the list. |

On **OK** (`_accept_open`), the current combo text is written to `SettingsManager.set_confluence_keepass_entry()`.  Setting this to a non-empty entry title causes `ConfluenceCalendarSync.run()` to pre-fill the Microsoft Azure AD SSO email and password fields automatically on the next sync.


## `KeePassNewEntryDialog`

Add a single credential entry to the currently open KeePass database.

```
Opened from JiraServerEditDialog → "New Entry…" button
```

**Fields**

| Field | Notes |
| - | - |
| Title | Required |
| Group | Optional — creates the group if it does not exist |
| Username | Optional |
| Password | Password field with Show/Hide toggle |

On accept, calls `SettingsManager.add_keepass_entry()`.  The resulting entry path (`"Group/Title"` or `"Title"`) is available via `get_entry_path()`.

### `get_entry_path() → str`

Returns the `"Group/Title"` path of the newly created entry for the caller to pre-select in the combo box.


## `JiraServerEditDialog`

Add or edit a single Jira server configuration.

```
Opened from JiraServersDialog → Add… / Edit… buttons, or double-click
```

### Basic fields

| Field | Notes |
| - | - |
| Name | Display name (required) |
| URL | Full server URL; `https://` is prepended automatically if missing (required) |
| Authentication | Combo: **Manual** or **From KeePass entry** |

### Manual credentials group

Visible when Authentication = **Manual**.

| Field | Notes |
| - | - |
| Credential Type | Combo: **API Token** (default) or **Password** — updates the field label dynamically |
| Username | Username or email |
| API Token / Password | Password field with Show/Hide toggle |

### KeePass credentials group

Visible when Authentication = **From KeePass entry**.  Uses a `QStackedWidget` with three pages:

| Page | Condition | Content |
| - | - | - |
| 0 — not configured | `is_keepass_configured()` is `False` | Label + **Configure KeePass…** button → opens `KeePassConfigDialog` |
| 1 — locked | Configured but `is_keepass_unlocked()` is `False` | Label + **Unlock KeePass…** button → tries `auto_unlock_keepass()` then prompts |
| 2 — unlocked | DB is open | Entry combo (populated from `list_keepass_entries()`) + **New Entry…** button → opens `KeePassNewEntryDialog` |

**Auto-open behaviour:** switching the Authentication combo to "From KeePass entry" automatically opens `KeePassConfigDialog` if KeePass is not yet configured, and calls `auto_unlock_keepass()` if it is configured but locked.


## `JiraSyncConfigDialog`

Two-tab dialog for all Jira synchronization configuration.

```
TASK ribbon → Jira Sync Config button
Project menu → Jira → Jira Sync Configuration...
```

Each tab is wrapped in a `QScrollArea` (`setWidgetResizable=True`, `QFrame.NoFrame`) so content scrolls within the tab. The dialog height is constrained to `availableGeometry().height() − 40 px` to keep the OK/Cancel row always visible.

### Tab 1 — "Jira → Project"

| Control | Description |
| - | - |
| **Jira Server combo** | Dropdown populated from `get_jira_servers()`. Pre-selects the saved sync server from `get_jira_sync_server()`. Disabled when no servers are configured. |
| **Add...** button | Opens `JiraServersDialog`; on return the dropdown refreshes via `_refresh_servers()`. |
| **Filter Type** | Radio buttons: **JQL** (raw JQL string) or **Saved Filter (ID or URL)**. Both disabled when no project is open. |
| **JQL Filter field** | Text input for a JQL expression or saved-filter ID/URL. Pre-filled from the `jira2project` project custom property. Disabled when no project is open. |
| **Test Filter** button | Validates, connects, executes `jira.search_issues(maxResults=50)`, and shows a message box with match count and first 10 issues. |
| **Field-selection checkboxes** | 34 boolean flags controlling which Jira fields are written to the task sidecar. Dependent checkboxes (e.g. `jira_status_percent`) are auto-disabled via `_JIRA2PROJECT_FIELD_DEPENDENCIES` when their controller checkbox is unchecked. |

### Tab 2 — "Project → Jira"

Tab label uses the Unicode right-arrow character U+2192: **"Project → Jira"**.

#### Selectors (all implemented as `QComboBox` drop-downs)

| Selector | Options | Default |
| - | - | - |
| **Export Scope** | Selected Tasks / **Changed since last sync** / Full project | Changed since last sync |
| **Create/Update Mode** | Create only / Update only / Create + update | Create + update |
| **Conflict Policy** | Prefer Jira / Prefer Project / Manual review | Prefer Jira |
| **Unlinked Tasks** | Create new issue / Skip / Prompt | Skip |

#### Tables

| Table | Purpose |
| - | - |
| **Field Map** | Maps a project field name to a Jira field name. Each row has an enable checkbox and an editable `QComboBox` pre-populated with standard Jira field name suggestions (summary, description, priority, assignee, etc.). |
| **Issue Type Map** | Maps project task-type names to Jira issue-type names. |
| **Transition Map** | Maps project task-status values to Jira transition IDs or names. |

Hierarchy issue-type fields (Epic, Story, Sub-task) and the dependency link-type field also use editable `QComboBox` widgets pre-populated with suggestions.

#### Dry Run

A `QCheckBox`; when checked the export is simulated without writing to Jira.

#### Persistence

All Project → Jira settings are stored per-project in the `"project2jira"` sidecar JSON container via the same `java.util.HashMap` mechanism as `"jira2project"`.

#### Validation (`_validate_project_to_jira_settings`)

1. At least one field-map row must be enabled with a non-empty Jira field name.
2. Create-capable modes require an enabled `project` field row.
3. At least one Issue Type Map entry must exist.
4. Every Transition Map row must have a non-empty transition target.
5. Best-effort server capability checks for issue types and transitions (skipped when offline).

### Behavior (both tabs)

- **No project open:** Filter field, filter-type radios, and all Project → Jira combo/table controls are disabled.
- **Filter testing (saved filter):** `resolve_filter_to_jql()` is called first; on failure a "Filter Resolution Failed" dialog is shown without executing the search.
- **KeePass locked:** Test Filter / Sync from Jira prompts to unlock KeePass before connecting.
- **Persistence:** On OK, the sync server is saved to QSettings via `set_jira_sync_server()`; all other settings go to project custom properties in the sidecar JSON.


## `JiraServersDialog`

Manage the full list of Jira server configurations.

```
Project menu → Jira → Jira Servers...
JiraSyncConfigDialog → Add... button
```

### Layout

Two-panel layout: server list on the left, action buttons on the right.

**List item format:** `Name  [Manual/KeePass]  —  URL`

### Buttons

| Button | Action |
| - | - |
| **Add…** | Opens `JiraServerEditDialog` (new server) |
| **Edit…** | Opens `JiraServerEditDialog` pre-filled with selected server |
| **Delete** | Removes selected server (with confirmation) |
| **▲ / ▼** | Move selected server up or down in the list |

Double-clicking a list item opens the Edit dialog.

On **OK**, calls `SettingsManager.set_jira_servers()` to persist the updated list.


## `ConfluenceCalendarConfigDialog`

Combined configuration dialog for Confluence Calendar sync.  Opened from the ribbon
**Confluence** group or via the Project menu.

```
Project → Configure Confluence Calendar…
  (or from the RESOURCE ribbon → Confluence group)
```

Two collapsible sections:

### Section 1 — Authentication

Selects how credentials are provided for the Playwright SSO browser session.

| Auth mode | Behaviour |
| --------- | --------- |
| **Manual (no SSO auto-fill)** | A Chromium window opens and the user completes the entire login (username, password, MFA) manually.  The session is cached afterwards so subsequent syncs are headless. |
| **From KeePass entry (auto-fill SSO)** | Username and password from the selected KeePass entry are pre-filled on the Microsoft Azure AD login page; only the MFA step is completed manually. |

When `"From KeePass entry"` is selected, a `QStackedWidget` (`_kp_stack`) shows one of three pages:

| Page | Condition | Content |
| ---- | --------- | ------- |
| 0 | KeePass not configured | Label + **Configure KeePass…** button |
| 1 | Configured but locked | Label + **Unlock KeePass…** button |
| 2 | Unlocked | `_kp_entry_combo` (editable `QComboBox` listing all entries) + **New Entry…** button |

On mode switch or dialog open, `_on_auth_mode_changed` shows the relevant group and
`_refresh_kp_state` selects the correct stack page (calling `auto_unlock_keepass` first
if KeePass is configured but locked).


### Section 2 — Calendar Properties (per-project)

Four fields read from and written back to the project's enterprise custom properties via
`integrations.confluence_calendar_integration`.  All fields are **disabled** when no
project is open (a hint label is shown instead).

| Widget | Field key | Default hint |
| ------ | --------- | ------------ |
| `_cal_base_url_edit` (`QLineEdit`) | `CALENDAR Base URL` | `https://confluence.example.com` |
| `_cal_space_key_edit` (`QLineEdit`) | `CALENDAR Space Key` | `e.g. PROJ` |
| `_cal_timezone_combo` (`QComboBox`, editable) | `CALENDAR Timezone` | `Europe/Berlin` |
| `_cal_days_ahead_edit` (`QLineEdit`) | `CALENDAR Days Ahead` | `365` |

#### Timezone QComboBox details

The timezone combo is populated from `zoneinfo.available_timezones()` (IANA zones
provided by the `tzdata` package on Windows, where the OS has no built-in timezone
database).  Key properties:

- **Insert policy:** `QComboBox.NoInsert` — user-typed text does not create a new list item.
- **Completer:** `QCompleter` with `filterMode = Qt.MatchContains` and
  `caseSensitivity = Qt.CaseInsensitive`, so typing `"berlin"` instantly narrows the
  popup to `"Europe/Berlin"`.
- **Pre-selection:** When a project is open, `findText(tz_val)` + `setCurrentIndex(idx)`
  is used (not `setCurrentText`) so Qt knows the exact list index and the popup scrolls
  to the pre-selected item.  If `findText` returns `-1` (unknown / legacy value),
  `setCurrentText` is used as a fallback to preserve the stored value as free text.
- **Default:** When no project is open, `Europe/Berlin` is pre-selected as a hint.
  When a project is open but the field is unset, `Europe/Berlin` is also used as default.


### Accept behaviour

`_accept()`:

1. Saves the auth mode via `SettingsManager.set_confluence_auth_mode()`.
2. If KeePass mode and the stack is on page 2 (unlocked), saves the selected entry via
   `SettingsManager.set_confluence_keepass_entry()`.
3. If a project is open, calls `_save_calendar_props()` which reads `currentText()` /
   `text()` from the four fields and writes them back to the project's enterprise custom
   properties (`java.util.HashMap` via JPype / MPXJ).


## `EmailConfigDialog`

Project-aware dialog for selecting an SMTP account and configuring the per-project sender
display name.  Opened from the ribbon **Report** tab via **Email Config** button.
Always enabled (global settings, not project-gated).

```
Report → Email Config
```

The dialog is opened with `project=logic.get_data()` so changes to the account selection
and sender name call `_mark_dirty()` in `MainWindow.open_email_config()` when accepted
with a project open.

### Section 1 — KeePass Credentials

A `QStackedWidget` (`_kp_stack`) with three pages:

| Page | Condition | Content |
| ---- | --------- | ------- |
| 0 | KeePass not configured | Label "KeePass is not configured" + **Configure KeePass…** button |
| 1 | Configured but locked | Label "KeePass database is locked" + **Unlock KeePass…** button |
| 2 | Unlocked | Green status box "✓ KeePass Database Unlocked" + entry selector QComboBox |

The entry combo (`_kp_entry_combo`) is populated from `SettingsManager.list_keepass_entries()`
and pre-selects the saved `email/keepass_entry` value if present in the list.

### Section 2 — Account Selection

| Widget | Description |
| ------ | ----------- |
| `_account_combo` (`QComboBox`) | Lists all configured SMTP accounts by name. Hidden when no accounts exist. |
| `_no_accounts_lbl` (`QLabel`) | Warning label "No SMTP accounts configured…". Shown when the account list is empty. |
| **Manage Accounts…** button | Opens `EmailServersDialog`; on return the combo is reloaded and the previous selection re-selected. |

The combo uses `currentData()` to store the account name (user-visible text also equals the name).
`_refresh_account_combo(select_name=None)` repopulates the combo from `SettingsManager.get_email_configs()`.

`_get_current_config()` returns the selected account dict with a `"sender_name"` key injected
from the Sender Name field (when non-empty), or `None` when the combo is hidden.
The hidden check uses `isHidden()` (not `isVisible()`) so it works correctly in headless tests.

### Section 3 — Sender Name (per-project)

| Widget | Custom property key | Notes |
| ------ | ------------------- | ----- |
| `_sender_name_edit` (`QLineEdit`) | `"Email Sender Name"` | Display name used in the From: header (e.g. `"Alice Smith"`). Saved to and loaded from the project sidecar JSON. Empty by default when no project is open. |

### Per-project persistence

Two module-level constants define the custom property keys:

```python
EMAIL_ACTIVE_ACCOUNT_PROP = "Email Active Account"
EMAIL_SENDER_NAME_PROP    = "Email Sender Name"
```

`_load_project_settings()` reads both from `project.getProjectProperties().getCustomProperties()`,
falling back to `SettingsManager.get_active_email_config_name()` for the account when absent.

`_save_settings()` writes both to the project sidecar via `java.util.HashMap` and
`project.getProjectProperties().setCustomProperties()` — the same mechanism used by
`JiraSyncConfigDialog`.

### Test Connection & Send Test Email

| Button | Behaviour |
| ------ | --------- |
| **Test Connection** | Calls `_get_current_config()` to resolve the selected account (with sender name injected), calls `email_integration.test_connection(config=...)`, displays result dialog |
| **Send Test Email** | Calls `_get_current_config()`, shows wider QInputDialog (400 px) to enter recipient address, includes **Use My Email** button to auto-fill user's email from AD, calls `email_integration.send_email(config=...)` with test subject/body, displays result dialog |


## `EmailServerEditDialog`

Add or edit a single named SMTP account.  Opened from `EmailServersDialog` via
**Add…** or **Edit…** buttons (or double-click).

```
Report → Email Accounts → Add… / Edit…
```

This dialog does **not** contain a KeePass section.  A blue informational banner
reminds the user that credentials are configured globally via `EmailConfigDialog`.

### SMTP fields

| Widget | Attribute | Default | Notes |
| ------ | --------- | ------- | ----- |
| `_name_edit` (`QLineEdit`) | `name` | `""` | Account display name (required) |
| `_smtp_server_edit` (`QLineEdit`) | `smtp_server` | `""` | SMTP hostname |
| `_smtp_port_edit` (`QLineEdit`) | `smtp_port` | `"587"` | `QIntValidator(1, 65535)` |
| `_smtp_use_tls_check` (`QCheckBox`) | `smtp_use_tls` | checked | STARTTLS flag |
| `_sender_address_edit` (`QLineEdit`) | `sender_address` | `""` | From address — see note below |

#### "From KeePass…" button

Placed next to `_sender_address_edit`.  When clicked, `_lookup_sender_from_keepass_ad()`:

1. Checks `sm.get_email_keepass_entry()` is non-empty — warns and aborts if not.
2. Checks `keepass_integration.is_unlocked()` — warns and aborts if locked.
3. Calls `keepass_integration.get_credentials(entry_title)` to obtain the username.
4. Calls `ad_integration.lookup_by_username(username)` to look up the AD record.
5. Sets `_sender_address_edit.setText(result["email"])`.

### Title modes

| Mode | Window title |
| ---- | ------------ |
| No config supplied | "Add Email Account" |
| `config` dict supplied | "Edit Email Account" |

### `get_config()` return value

Returns a `dict` with the five SMTP fields.  Does **not** include a `keepass_entry` key —
credentials are global.

### Test Connection

Builds a temporary config from the current form fields (with the global `keepass_entry`
appended for credential resolution) and calls `email_integration.test_connection(config=tmp)`.


## `EmailServersDialog`

Manage the full list of named SMTP accounts.

```
Report → Email Accounts
Project menu → Email → Email Accounts…
```

### Layout

Two-panel layout: account list on the left, action buttons on the right.

**List item format:** `name ★ — server (sender_address)` with `★` on the active account.

### Buttons

| Button | Action |
| ------ | ------ |
| **Add…** | Opens `EmailServerEditDialog` (new account) |
| **Edit…** | Opens `EmailServerEditDialog` pre-filled with selected account |
| **Delete** | Removes selected account (with confirmation) |
| **Set Active** | Marks selected account as active (writes `active_config_name` to `email_configs.json`) |
| **▲ / ▼** | Reorders accounts in the list |

Double-clicking a list item opens the Edit dialog.

On **OK**, calls `SettingsManager.set_email_configs(configs)` to persist the updated list.
