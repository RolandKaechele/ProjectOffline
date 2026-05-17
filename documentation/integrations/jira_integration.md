# Jira Integration

## Overview

The `src/integrations/jira_integration.py` module provides Jira API connectivity and credential management for synchronizing tasks between the project and Jira issues. The module supports both manual credentials (stored in QSettings) and secure KeePass-based authentication.

## Prerequisites

| Requirement | Notes |
| ----------- | ----- |
| Jira server access | Atlassian Cloud, Data Center, or Server instance |
| API credentials | See Authentication Methods below |
| KeePass database (optional) | For secure credential storage via `src/integrations/keepass_integration.py` |
| Python `jira` library | Official Atlassian Python JIRA API client (≥3.0) |

## Authentication Methods

The module supports three authentication methods to accommodate different Jira deployment types:

| Method | When to Use | JIRA Library Method | Required Fields |
| ------ | ----------- | ------------------- | --------------- |
| **API Token** | Jira Cloud (*.atlassian.net) | `basic_auth=(username, token)` | Username (email) + API Token |
| **Password** | Legacy Jira Server/Data Center with basic auth enabled | `basic_auth=(username, password)` | Username + Password |
| **Personal Access Token (PAT)** | Jira Server/Data Center with disabled basic authentication | `token_auth=token` | Token only (username not required) |

### When Basic Authentication is Disabled

Some Jira Server/Data Center instances disable HTTP Basic Authentication for security reasons. When this occurs, API Token and Password modes will fail with:

```
JIRAError: HTTP 403 - Basic Authentication has been disabled on this instance
```

**Solution**: Generate a Personal Access Token (PAT) from your Jira profile settings and use PAT mode. The PAT uses Bearer token authentication (`token_auth`) which bypasses basic auth restrictions.

## Configuration

All Jira server configurations are stored in **QSettings** under the `jira/` prefix and managed via `src/settings_manager.py`:

| QSettings Key | Type | Default | Description |
| ------------- | ---- | ------- | ----------- |
| `jira/servers` | JSON array | `[]` | List of server configuration objects (see below) |
| `jira/sync_server` | string | `""` | Name of the Jira server selected for project synchronization |

**Custom Properties (per-project, stored in `.custom-props.json` sidecar file):**

All per-project Jira sync settings are stored inside a single JSON container value under the key `"jira2project"` in the MPXJ custom properties. The file_handler module transparently expands this to a nested dict in the sidecar file and re-serialises it on load.

| Container Key | Type | Default | Description |
| ------------- | ---- | ------- | ----------- |
| `filter` | string | `""` | Filter value — JQL string when type is `"jql"`, or numeric filter ID / full `?filter=` URL when type is `"filter"` |
| `filter_type` | string | `"jql"` | Filter mode: `"jql"` (raw JQL) or `"filter"` (saved Jira filter referenced by ID or URL) |

### Server Configuration Object

Each server in the `jira/servers` array is a dictionary:

```python
{
    "name": "My Company Jira",                 # User-friendly server name
    "url": "https://mycompany.atlassian.net",  # Base URL
    "auth_mode": "manual",                     # "manual" or "keepass"
    "credential_type": "token",                # "token", "password", or "pat"
    "username": "user@example.com",            # For manual mode (not required for PAT)
    "token": "api_token_here",                 # For manual mode (token/password/PAT)
    "keepass_entry": "Group/Title",            # For keepass mode
    "keepass_credential_type": "token",        # For keepass mode ("token", "password", or "pat")
}
```

### Credential Type Selection

The `credential_type` field (or `keepass_credential_type` for KeePass mode) determines the authentication method:

- **`"token"`** (API Token - Jira Cloud): Uses `basic_auth=(username, token)` with username (email address) and API token
- **`"password"`** (Password): Uses `basic_auth=(username, password)` with username and password
- **`"pat"`** (Personal Access Token): Uses `token_auth=token` with token only (username not required)

### Authentication Modes

#### Manual Authentication

- **Credentials**: Username and credential stored directly in QSettings (Windows registry)
- **Security**: Only accessible to the current Windows user
- **Use case**: Single-user deployments, development/testing
- **Best practice**: Use API tokens for Jira Cloud, PAT for Server/Data Center with disabled basic auth
- **Credential types**: Supports `"token"`, `"password"`, and `"pat"`

#### KeePass Authentication

- **Credentials**: Only the KeePass entry title is stored in QSettings; actual username and credential are retrieved from the KeePass database at connection time
- **Security**: Credentials never touch disk; database must be unlocked before connecting
- **Use case**: Production deployments, shared workstations, security-conscious users
- **Entry format**: Username in username field (not required for PAT), API token/password/PAT in password field
- **Credential types**: Supports `"token"`, `"password"`, and `"pat"` via dropdown selection
- **Whitespace stripping**: The module automatically calls `.strip()` on both username and credential to prevent HTTP header errors (e.g., trailing newlines from KeePass entries)

## API Connection Patterns

### API Token (Jira Cloud)

```python
from jira import JIRA

# Basic authentication with API token
jira = JIRA(
    server="https://mycompany.atlassian.net",
    basic_auth=("username@example.com", "api_token_here")
)

# Test connection
myself = jira.myself()
print(f"Authenticated as: {myself['displayName']}")
```

### Personal Access Token (Jira Server/Data Center)

```python
from jira import JIRA

# Token authentication with PAT (username not required)
jira = JIRA(
    server="https://jira.company.com",
    token_auth="personal_access_token_here"
)

# Test connection
myself = jira.myself()
print(f"Authenticated as: {myself['displayName']}")
```

### Search Issues Example

```python
# Search issues (works with all auth methods)
issues = jira.search_issues(
    'project = MYPROJECT ORDER BY created DESC',
    maxResults=10
)
for issue in issues:
    print(f"{issue.key}: {issue.fields.summary}")
```

### Common Errors

| Error | Cause | Solution |
| ----- | ----- | -------- |
| `JIRAError: HTTP 401` | Invalid credentials | Check username and credential; regenerate API token or PAT if expired |
| `JIRAError: HTTP 403 "Basic Authentication disabled"` | Server requires PAT | Generate a Personal Access Token from Jira profile and select PAT credential type |
| `JIRAError: HTTP 403` (other) | Insufficient permissions | Verify user has access to the requested project |
| `JIRAError: HTTP 404` | Invalid URL or project | Check server URL and project key |
| `ConnectionError` | Network issue | Check firewall, proxy, or VPN connection |
| `SSLError` | Certificate issue | Update `certifi` or check corporate SSL interception |
| `Invalid header value` | Trailing whitespace in credential | Automatically stripped by `settings_manager.get_jira_credentials()` |

## Module API

### `test_connection(server: dict) -> tuple[bool, str]`

Test connectivity to a Jira server using the provided configuration.

**Arguments:**

- `server` (dict): Server configuration object from `get_jira_servers()`

**Returns:**

- `(success, error_message)`: Empty error message on success

**Example:**

```python
from integrations import jira_integration

servers = settings_manager.get_jira_servers()
if servers:
    success, error = jira_integration.test_connection(servers[0])
    if not success:
        print(f"Connection failed: {error}")
```

**Behavior:**

- Retrieves credentials via `settings_manager.get_jira_credentials()` (with automatic whitespace stripping)
- Determines authentication method based on `credential_type`:
  - `"pat"`: Creates JIRA client with `token_auth=credential`
  - `"token"` or `"password"`: Creates JIRA client with `basic_auth=(username, credential)`
- Validates required fields:
  - PAT mode: Requires credential only (username optional)
  - Token/Password modes: Requires both username and credential
- Calls `jira.myself()` to verify authentication
- Records test result in `_last_connection_test` for debug dump
- Prints debug output when `--debug` flag is active

### `get_jira_client(server: dict) -> tuple[JIRA | None, str]`

Create an authenticated JIRA client instance for the specified server.

**Arguments:**

- `server` (dict): Server configuration object

**Returns:**

- `(jira_client, error_message)`: Client is `None` on failure

**Example:**

```python
from integrations import jira_integration

jira, error = jira_integration.get_jira_client(server)
if jira is None:
    print(f"Failed to connect: {error}")
else:
    # Use the client for sync operations
    issues = jira.search_issues('project = MYPROJECT', maxResults=100)
    for issue in issues:
        # Process issue and create/update tasks
        pass
```

### `get_config_summary() -> dict`

Return a summary of Jira configuration for the debug dump.

**Returns:**

- Dictionary with server count, server list (names, URLs, auth modes), and last connection test result

**Example output:**

```python
{
    "server_count": 2,
    "servers": [
        {
            "name": "Production Jira",
            "url": "https://company.atlassian.net",
            "auth_mode": "keepass",
            "keepass_locked": False
        },
        {
            "name": "Dev Jira",
            "url": "https://dev-company.atlassian.net",
            "auth_mode": "manual",
            "keepass_locked": False
        }
    ],
    "last_connection_test": {
        "server_name": "Production Jira",
        "server_url": "https://company.atlassian.net",
        "auth_mode": "keepass",
        "timestamp": "2026-05-05T14:32:10.123456",
        "success": True,
        "error": ""
    }
}
```

**Security**: No passwords, tokens, or KeePass entry credentials are included.

### `_extract_filter_id(value: str) -> str`

Extract a numeric Jira filter ID from a URL, query fragment, or plain numeric string.

**Accepts:**

- `https://jira.example.com/issues/?filter=66111`
- `filter=66111` (query fragment)
- `66111` (plain number)

**Returns:** The numeric ID as a string, or `""` if no ID can be extracted.

### `resolve_filter_to_jql(jira, filter_value: str, filter_type: str) -> tuple[str, str]`

Resolve a filter value to a JQL string ready for `jira.search_issues()`.

**Arguments:**

- `jira`: Authenticated JIRA client instance
- `filter_value` (str): JQL string (when `filter_type="jql"`) or filter ID / URL (when `filter_type="filter"`)
- `filter_type` (str): `"jql"` — return value unchanged; `"filter"` — call `jira.filter(id).jql`

**Returns:** `(jql_string, error_message)` — error message is empty on success.

**Example:**

```python
from integrations import jira_integration

jira, _ = jira_integration.get_jira_client(server)

# Resolve a saved filter URL to JQL
jql, err = jira_integration.resolve_filter_to_jql(
    jira,
    "https://jira.example.com/issues/?filter=66111",
    "filter"
)
if err:
    print(f"Could not resolve filter: {err}")
else:
    issues = jira.search_issues(jql, maxResults=50)
```


### `fetch_server_capabilities(server: dict, project_key: str = "") -> dict`

Fetch the list of issue types and priorities available on a Jira server.  Called by `_validate_project_to_jira_settings` in `settings_dialogs.py` to pre-populate the issue-type and transition map dropdowns in the **Project → Jira** tab.

**Arguments:**

- `server` (dict): Server configuration object from `get_jira_servers()`
- `project_key` (str, optional): Jira project key (e.g. `"MYPROJ"`).  When provided, issue types are fetched for that specific project via the `createmeta` endpoint (reflects project-level issue-type configuration); falls back to the global `issue_types` endpoint when omitted or when the project-specific call fails.

**Returns:** A dict with three keys:

| Key | Type | Description |
| - | - | - |
| `issue_types` | `list[str]` | Sorted list of issue type name strings; empty on failure |
| `priorities` | `list[str]` | Sorted list of priority name strings; empty on failure |
| `error` | `str` | Non-empty when the server could not be reached |

**Failure behaviour:**  Priorities are fetched independently of issue types; a failure to retrieve priorities does not prevent issue types from being returned (`error` stays empty in that case).

**Example:**

```python
from integrations import jira_integration

caps = jira_integration.fetch_server_capabilities(server, project_key="PROJ")
if caps["error"]:
    print(f"Could not fetch capabilities: {caps['error']}")
else:
    print("Issue types:", caps["issue_types"])
    print("Priorities:",  caps["priorities"])
```

## Configuration Dialogs

### JiraSyncConfigDialog

Primary entry point for Jira synchronization setup, accessible from:

- **TASK ribbon** → "Jira Sync Config" button (always enabled)
- **Project menu** → Jira → "Jira Sync Configuration..."

**Purpose**: Select which Jira server to use for project synchronization and specify a filter. The server is saved per-user in QSettings under `jira/sync_server`. The filter value, filter type, and field-checkbox states are saved per-project inside a single `"jira2project"` JSON container in custom properties.

**Features:**

- **Server dropdown**: Lists all configured Jira servers from `settings_manager.get_jira_servers()`
  - Disabled when no servers are configured
  - Pre-selects the previously saved sync server from `settings_manager.get_jira_sync_server()`
- **Add button**: Opens `JiraServersDialog` to configure new servers
  - Dropdown automatically refreshes when returning from server management
- **Filter Type selector**: Two radio buttons — "JQL" and "Saved Filter (ID or URL)"
  - Both disabled when no project is open
- **Filter field**: Text input whose placeholder and tooltip adapt to the selected filter type
  - **JQL mode**: Accepts a raw JQL string; tooltip shows JQL syntax examples
  - **Saved Filter mode**: Accepts a numeric filter ID (e.g., `66111`) or a full `?filter=` URL (e.g., `https://jira.example.com/issues/?filter=66111`)
  - Pre-filled with previously saved filter from project custom properties
  - Disabled when no project is open
- **Test Filter button**: Validates the filter by connecting to the selected server and fetching issues
  - If the selected server uses KeePass auth and the database is locked: prompts the user to unlock before connecting (question dialog → auto-unlock → password prompt fallback)
  - **JQL mode**: executes `jira.search_issues(jql, maxResults=50)` directly
  - **Saved Filter mode**: calls `resolve_filter_to_jql()` to fetch the saved filter's JQL from the server, then executes the search; shows a "Filter Resolution Failed" error if the ID cannot be resolved
  - Shows resolved JQL in the result message box when filter type is "Saved Filter"
  - Requires a server to be selected and a filter value to be specified
- **Persistence**: Saves selected server name to QSettings; saves filter value and type to project custom properties on OK; removes both custom property keys when filter is cleared
- **Blue header**: MS Project-style dialog with "Jira Sync Configuration" title

**Workflow:**

1. User clicks "Jira Sync Config" ribbon button or menu item
2. Dialog opens with dropdown of available servers, filter type selector, and filter field
3. If no servers exist: dropdown is disabled, user clicks "Add..." to configure
4. If no project open: filter type radios and filter field disabled with hint message
5. User selects server, chooses filter type (JQL or Saved Filter), and enters the filter value
6. (Optional) User clicks "Test Filter" to resolve and validate the filter and see a preview of matching issues
7. On OK: selected server name, filter value, and filter type are persisted
8. Future sync operations use the selected server and resolved filter

### JiraServerEditDialog

Single-server add/edit dialog accessible from:

- **JiraServersDialog** → Add/Edit buttons
- **JiraSyncConfigDialog** → "Add..." button

**Features:**

- **Basic fields**: Name, URL, authentication mode radio buttons
- **Credential Type dropdown**: Three options with clear labels:
  - "API Token (Jira Cloud)" – for Atlassian Cloud instances
  - "Password" – for legacy servers with basic auth enabled
  - "Personal Access Token (Server/Data Center)" – for servers with disabled basic auth
- **Dynamic field labels**: Username field label and placeholder update based on credential type:
  - PAT mode: "Username (optional)" with placeholder "Not required for PAT"
  - Token/Password modes: "Username" with standard placeholder
- **Manual credentials section**: Username, credential type dropdown, credential field with show/hide toggle
- **KeePass credentials section**: Three-state stacked widget with credential type dropdown:
  - Page 0: "Configure KeePass…" button when not configured
  - Page 1: "Unlock KeePass…" button when configured but locked
  - Page 2: Entry selector combo + credential type dropdown + "New Entry…" button when unlocked
- **Test Connection button**: Validates form fields before attempting connection:
  - PAT mode: Requires credential only
  - Token/Password modes: Requires username and credential
- **Connection test feedback**: Shows modal dialog with success (green checkmark + authenticated username) or error message (red X + error details)
- **Auto-configuration**: Opens KeePass config dialog when switching to KeePass mode if not yet configured
- **Manual unlock**: No automatic unlock; users must click "Unlock KeePass…" button

### JiraServersDialog

Multi-server management dialog for organizing multiple Jira connections, accessible from:

- **Project menu** → Jira → "Jira Servers..."
- **JiraSyncConfigDialog** → "Add..." button

**Features:**

- Add/edit/delete server configurations
- Reorder servers with up/down buttons (for dropdown priority)
- List view shows: `{name} [{auth_mode}] — {url}`
- Persists all changes to QSettings on OK

## Usage in Application

### Ribbon Integration

The "Jira Sync Config" button is in the **TASK** ribbon panel (task-relevant functionality):

```python
# ribbon.py
grp_jira = _RibbonGroup("Jira")
self._jira_config_btn = grp_jira.add_button(
    "Jira Sync\nConfig",
    "Configure Jira server connections and sync settings",
    lambda: self._call("open_jira_config"),
    icon=_icons.confluence_settings()
)
panel.add_group(grp_jira)

# Hidden on Resource Usage view
self._hidden_groups_by_app_tab[TAB_RESOURCE_USAGE] = [grp_jira]
```

### UI Handler

```python
# ui.py
def open_jira_config(self):
    """Open the Jira servers configuration dialog."""
    from settings_dialogs import JiraServersDialog
    dlg = JiraServersDialog(self._settings_manager, self)
    dlg.exec_()
```

### Debug Dump

The `src/app_debug.py` debug dump includes a `jira_sync_config` section:

```python
payload["jira_sync_config"] = {
    "server_count": 2,
    "servers": [...],
    "last_connection_test": {...}
}
```

**Excludes**: API tokens, passwords, KeePass entry details.

## Best Practices

### Authentication

1. **Prefer API tokens over passwords** for Jira Cloud (tokens can be revoked without changing the user's main password)
2. **Use KeePass mode** in production or on shared workstations
3. **Rotate API tokens** periodically (every 90-180 days recommended)
4. **Test connections** before bulk sync operations to fail fast on credential issues

### Error Handling

1. **Fail fast**: Call `test_connection()` before starting sync to validate credentials
2. **Retry with backoff**: Implement exponential backoff for transient network errors
3. **Clear feedback**: Show actionable error messages in the UI (avoid raw stack traces)
4. **Log connection attempts**: Debug dump includes last connection test for troubleshooting

### Configuration Management

1. **Named servers**: Use descriptive names (e.g., "Production Jira", "Dev Jira")
2. **Server ordering**: Place frequently used servers at the top (first in dropdown)
3. **Backup credentials**: Store backup accounts in KeePass for each server
4. **Document projects**: Add project keys to server names if managing multiple projects per server

## Security Considerations

### Manual Mode

- Credentials stored in Windows registry at `HKEY_CURRENT_USER\Software\{org}\{app}\jira\servers`
- Only accessible to the current Windows user account
- Plain text in registry (obfuscation not provided by QSettings)
- Suitable for single-user workstations with OS-level security

### KeePass Mode

- No credentials stored in registry
- Master password required to unlock database
- Credentials retrieved from memory only (never written to disk)
- Database auto-locks on idle (configurable in KeePass)
- Suitable for shared workstations, team environments, security-conscious users

### Network Security

- HTTPS required for Jira Cloud (enforced by Atlassian)
- Corporate proxy/firewall may require certificate trust configuration
- Use `certifi` package for CA certificate bundle updates

## Dependencies

Install via `requirements.txt`:

```bash
pip install jira pykeepass
```

| Package | Version | Purpose |
| ------- | ------- | ------- |
| `jira` | ≥3.0 | Official Atlassian Python JIRA API client |
| `pykeepass` | ≥4.0 | KeePass database access (when using KeePass auth) |

## See Also

- [src/integrations/jira_integration.py](../../src/integrations/jira_integration.py) — Connection logic, get_jira_client(), test_connection()
- [src/settings_manager.py](../../src/settings_manager.py) — get_jira_servers(), set_jira_servers(), get_jira_sync_server(), set_jira_sync_server(), get_jira_credentials()
- [src/settings_dialogs.py](../../src/settings_dialogs.py) — JiraSyncConfigDialog, JiraServerEditDialog, and JiraServersDialog implementations
- [integrations/keepass_integration.md](keepass_integration.md) — KeePass credential storage and retrieval
- [jira_sync_configuration.md](../jira_sync_configuration.md) — User guide for Jira sync configuration workflow
- [diagnostic-scripts/test_jira_connection.py](../../diagnostic-scripts/test_jira_connection.py) — Connection testing script
