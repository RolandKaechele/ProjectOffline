# settings_manager.py

Provides `SettingsManager`, the single source of truth for KeePass and Jira **persistent** settings.  A single instance is created in `MainWindow.__init__` and passed down to every configuration dialog.

> **Architecture note:** Runtime KeePass logic (unlock/lock, entry CRUD, database creation) was refactored into `src/integrations/keepass_integration.py` (`KeePassManager`).  `SettingsManager` retains shim methods with identical signatures so that existing call sites continue to work without changes — each shim simply delegates to `keepass_integration.get_manager()`.  New code should call `KeePassManager` directly.  See [`integrations/keepass_integration.md`](../integrations/keepass_integration.md) for the full runtime API.

## Persistence

Settings are stored via `QSettings("ProjectOffline", "ProjectManager")` which writes to the Windows registry under `HKEY_CURRENT_USER\Software\ProjectOffline\ProjectManager`.  Every setter calls `_sync()` immediately after writing so values survive a crash or force-close.

| QSettings key | Type | Content |
| - | - | - |
| `keepass/db_path` | `str` | Absolute path to the `.kdbx` database file |
| `keepass/key_file` | `str` | Absolute path to the key file (may be empty) |
| `keepass/password` | `str` | Master password, base64-encoded (omitted when not saved) |
| `jira/servers` | `str` | JSON array of Jira server dicts |
| `jira/sync_server` | `str` | Name of the Jira server selected for synchronization (empty string by default) |
| `confluence/keepass_entry` | `str` | `"Group/Title"` path of the KeePass entry whose credentials are pre-filled into the Microsoft SSO login form during Confluence Calendar Sync (empty string → no auto-fill) |

The live `pykeepass.KeePassFile` object is **session-only** — it is owned by `KeePassManager` in `src/integrations/keepass_integration.py` and is never serialised.  `SettingsManager._keepass_db` is a read-only property that forwards to `keepass_integration.get_manager()._db`.


## `SettingsManager`

### Construction

```python
sm = SettingsManager()                    # creates its own QSettings
sm = SettingsManager(existing_qsettings)  # share the app's QSettings instance
```

### KeePass — path & key file

| Method | Signature | Description |
| - | - | - |
| `get_keepass_db_path` | `() → str` | Return persisted `.kdbx` path, or `""` |
| `set_keepass_db_path` | `(path: str)` | Persist `.kdbx` path and sync |
| `get_keepass_key_file` | `() → str` | Return persisted key file path, or `""` |
| `set_keepass_key_file` | `(path: str)` | Persist key file path and sync |

### KeePass — password

| Method | Signature | Description |
| - | - | - |
| `get_keepass_password` | `() → str` | Decode and return saved password, or `""` |
| `set_keepass_password` | `(pwd: str)` | Base64-encode and persist; pass `""` to remove |

### KeePass — state & unlocking

> These methods are **shims** — they delegate to `KeePassManager` via `keepass_integration.get_manager()`.

| Method | Signature | Returns | Description |
| - | - | - | - |
| `is_keepass_configured` | `()` | `bool` | `True` when a DB path is stored |
| `is_keepass_unlocked` | `()` | `bool` | `True` when the DB is open in memory |
| `unlock_keepass` | `(password: str)` | `(bool, str)` | Open DB with given password; an empty string is treated as `None` (key-file-only databases); returns `(success, error)` |
| `auto_unlock_keepass` | `()` | `(bool, str)` | Unlock using saved password (no prompt) |
| `lock_keepass` | `()` | — | Clear the in-memory DB reference |

### KeePass — database creation & key files

> These methods are **shims** — they delegate to `KeePassManager`.

| Method | Signature | Returns | Description |
| - | - | - | - |
| `create_keepass_db` | `(path, password, keyfile)` | `(bool, str)` | Create a new `.kdbx` at `path`, open it, and persist the path |
| `generate_key_file` | `(path: str)` | `(bool, str)` | Write 64 cryptographically random bytes to `path` |

> **Note on key file format:** `generate_key_file` produces a **64-byte binary file**, not a KeePass XML `.keyx` file.  pykeepass treats a 64-byte binary file as a hex-encoded 32-byte key (each byte of the stored file represents one nibble of the 256-bit key material), which avoids XML/hash parsing compatibility issues.

### KeePass — entries

> These methods are **shims** — they delegate to `KeePassManager`.

| Method | Signature | Returns | Description |
| - | - | - | - |
| `add_keepass_entry` | `(title, username, password, group_name="")` | `(bool, str)` | Add entry; creates group if needed; saves DB to disk |
| `save_keepass_db` | `()` | `(bool, str)` | Save any pending changes to the open database |
| `find_keepass_entry` | `(entry_title: str)` | `Entry \| None` | First entry matching title (exact, not regex) |
| `list_keepass_entries` | `()` | `list[str]` | Sorted display strings for all entries; root-group entries show as `"Title"` only, sub-group entries as `"Group/Title"` |

### Jira Servers

| Method | Signature | Returns | Description |
| - | - | - | - |
| `get_jira_servers` | `()` | `list[dict]` | Deserialise server list from QSettings |
| `set_jira_servers` | `(servers: list[dict])` | — | Serialise to JSON and sync |
| `get_jira_credentials` | `(server: dict)` | `(str, str)` | Return `(username, token)` from manual fields or live KeePass lookup |

### Jira Sync Server Selection

| Method | Signature | Returns | Description |
| - | - | - | - |
| `get_jira_sync_server` | `()` | `str` | Return the saved sync server name (empty string by default) |
| `set_jira_sync_server` | `(server_name: str)` | — | Save the selected sync server name and sync |

The sync server is managed by `JiraSyncConfigDialog` and determines which server is used for Jira synchronization operations. The JQL filter is now stored per-project in custom properties (see `integrations/jira_integration.md`).

### Jira Server Dict Schema

```python
{
    "name":            str,   # display name
    "url":             str,   # full https:// URL
    "auth_mode":       str,   # "manual" | "keepass"
    "username":        str,   # manual only
    "token":           str,   # manual only — API token or password
    "credential_type": str,   # manual only — "token" | "password"
    "keepass_entry":   str,   # keepass only — "Group/Title" path
}
```

### Confluence SSO

| Method | Signature | Returns | Description |
| - | - | - | - |
| `get_confluence_keepass_entry` | `() → str` | `str` | Return the configured `"Group/Title"` entry path (or `""` if not set) |
| `set_confluence_keepass_entry` | `(entry: str)` | — | Persist the entry path under `confluence/keepass_entry` and sync |

When `entry` is non-empty and the KeePass DB is unlocked, `ConfluenceCalendarSync.run()` calls `find_keepass_entry(entry)` to retrieve `(username, password)` and passes them to `_try_playwright_auth` as `keepass_creds`.  This pre-fills the Microsoft Azure AD SSO form so the user only needs to complete MFA.
