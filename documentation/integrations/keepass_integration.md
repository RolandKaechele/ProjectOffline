# KeePass Integration

## Overview

Project Offline uses [pykeepass](https://github.com/libkeepass/pykeepass) to store and
retrieve credentials from a local KeePass 4.x (`.kdbx`) database.  The integration is
intentionally **offline-first**: no network round-trip is ever required to read credentials;
the database file lives on disk and is unlocked once per session.

The implementation is split across three files:

| File | Responsibility |
| ---- | -------------- |
| `src/integrations/keepass_integration.py` | Runtime KeePass session: `KeePassManager` class + module-level singleton; unlock / lock / create / entry CRUD |
| `src/settings_manager.py` | QSettings persistence (paths, password); shim methods delegate to `KeePassManager` for backward compatibility |
| `src/settings_dialogs.py` | UI dialogs: `KeePassConfigDialog`, `KeePassNewEntryDialog` |


## QSettings Keys (settings_manager.py)

| Key | Type | Description |
| --- | ---- | ----------- |
| `keepass/db_path` | `str` | Absolute path to the `.kdbx` database file |
| `keepass/key_file` | `str` | Absolute path to the `.keyx` key file (optional) |
| `keepass/password` | `str` | Base64-encoded master password (optional, only saved if the user ticks *Save password*) |
| `confluence/keepass_entry` | `str` | `"Group/Title"` path of the entry used to auto-fill Microsoft AAD SSO during Confluence Calendar Sync |

**Security note:** Storing the master password in QSettings (even base64-encoded) is
intentionally opt-in and provides convenience rather than strong security.  The encoding
is not encryption — it is only used to prevent casual shoulder-surfing of the registry /
INI file.  Users who require stronger protection should leave *Save password* unchecked
and enter the password manually on each application start.

## KeePassManager — Runtime Session (keepass_integration.py)

`KeePassManager` owns the live `pykeepass.PyKeePass` object for the session.  It is
created once at startup and stored as a module-level singleton.

```python
_db: pykeepass.KeePassFile | None   # session only, never persisted
```

The live object is held only in RAM.  It is set to `None` on lock and on any failed
unlock attempt.

### Singleton lifecycle

```python
from integrations import keepass_integration as kp

# Called once in MainWindow.__init__ after SettingsManager is created:
manager = kp.init(settings_manager)   # → KeePassManager

# Retrieve the registered singleton later:
manager = kp.get_manager()            # → KeePassManager | None
```

### KeePassManager API

```python
m = kp.get_manager()

# --- State ---
m.is_configured() -> bool       # True when db_path is set in QSettings
m.is_unlocked()   -> bool       # True when _db is not None

# --- Unlock / lock ---
m.unlock(password: str)          -> (bool, str)   # (success, error_message)
m.auto_unlock()                  -> (bool, str)   # uses saved QSettings password
m.lock()                                          # clears _db

# --- Database creation ---
m.create_db(path, password, keyfile) -> (bool, str)   # converts to abspath; creates parent dirs
m.generate_key_file(path: str)       -> (bool, str)   # static; 64 random bytes (binary .keyx)

# --- Entry access (requires unlocked DB) ---
m.find_entry(entry_title: str)                        # pykeepass Entry | None
m.list_entries()     -> list[str]                     # sorted ["Group/Title", ...]
m.add_entry(title, username, password, group_name="") -> (bool, str)
m.save()             -> (bool, str)
m.get_credentials(entry_title: str) -> (str, str)     # (username, password)
```

`find_entry` and `get_credentials` both strip a `"Group/"` prefix automatically, so
callers may pass either `"Title"` or `"Group/Title"` — the same string stored in
QSettings under `confluence/keepass_entry` or in a Jira server dict.

### Module-level convenience functions

These forward calls to the registered singleton (return safe defaults when no singleton
is registered):

```python
kp.is_configured()  -> bool
kp.is_unlocked()    -> bool
kp.unlock(password) -> (bool, str)
kp.auto_unlock()    -> (bool, str)
kp.lock()
kp.get_entry(title)        -> Entry | None
kp.get_credentials(title)  -> (str, str)
kp.list_entries()          -> list[str]
```

### SettingsManager shims

`SettingsManager` exposes identically-named wrapper methods (`unlock_keepass`,
`lock_keepass`, `find_keepass_entry`, …) that delegate to
`keepass_integration.get_manager()`.  These exist purely for backward compatibility so
existing call sites do not need to import `keepass_integration` directly.  New code
should call the module-level functions or the `KeePassManager` instance directly.


## UI Dialogs (settings_dialogs.py)

### KeePassConfigDialog

Accessible via **File → KeePass Configuration…** (or a ribbon button where wired).

Two modes, selected via radio buttons:

**Open existing database**

- Browse for `.kdbx` file
- Optional key file (Browse or Generate)
- Master password field with Show / Hide toggle
- *Save password for automatic unlock* checkbox
- *Unlock* button to test the connection without closing the dialog
- Confluence SSO Auto-fill section (visible only when the DB is successfully unlocked):
  drop-down populated with all `"Group/Title"` entries from the open database; the
  selected entry's username and password are pre-filled on the Microsoft AAD login page
  during Confluence Calendar Sync

**Create new database**

- Save-as path for the new `.kdbx` (file dialog starts in `~/Documents`; path is
  converted to an absolute path before calling `create_db` so the resulting database
  is always written with an unambiguous location)
- Optional key file (Browse or Generate)
- Password + Confirm Password fields
- At least one of password / key file is required

**Dialog header subtitle**

The blue header subtitle updates dynamically when the user switches between the two
radio buttons:

| Mode | Subtitle text |
| ---- | ------------- |
| Open existing database | *Open an existing database* |
| Create new database | *Create a new KeePass database* |

**Key file generation**

The **Generate…** button writes **64 cryptographically random bytes** to the chosen
path.  pykeepass treats a 64-byte binary file as a hex-encoded 32-byte key (each byte
of the stored file represents one nibble of the actual 256-bit key material).

**Accept flow**

1. Paths and (optionally) password are persisted to QSettings via `SettingsManager`.
2. The `KeePassManager.unlock()` shim is triggered via `SettingsManager.unlock_keepass()`.
3. The Confluence SSO entry selection is saved via `SettingsManager.set_confluence_keepass_entry()`.

### KeePassNewEntryDialog

Adds a single new entry to the currently open database.

Fields: Title (required), Group (optional), Username, Password (Show/Hide toggle).

On accept, calls `SettingsManager.add_keepass_entry()` (which delegates to
`KeePassManager.add_entry()`) and saves the database immediately.
Returns the `"Group/Title"` path via `get_entry_path()`.


## Locking Policy

- The database is **never** automatically locked on a timer in the current implementation.
  Users lock it explicitly via the menu or by closing the application.
- A future *Lock when idle* feature could call `keepass_integration.lock()` (or the
  `SettingsManager.lock_keepass()` shim) after a configurable inactivity period.
- **Sensitive data never written to disk** (except the optional base64 password in
  QSettings): the `PyKeePass` object, the master password string, and decrypted entry
  passwords are kept only in RAM for the session lifetime.


## Debug Dump

The debug dump (`Ctrl+D` when `--debug` is active) includes a `keepass_integration`
section with the following (non-sensitive) fields:

| Field | Description |
| ----- | ----------- |
| `configured` | Whether a database path has been set |
| `unlocked` | Whether the database is currently open in RAM |
| `db_path_set` | Whether `keepass/db_path` QSettings key is non-empty |
| `key_file_set` | Whether `keepass/key_file` QSettings key is non-empty |
| `password_saved` | Whether a saved password exists in QSettings |
| `entry_count` | Number of entries in the open database (only when unlocked) |
| `confluence_entry_configured` | Whether a Confluence SSO entry has been selected |

The actual database path, key file path, master password, and entry credentials are
**never** included in the dump.
