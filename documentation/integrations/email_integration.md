# Email Integration

## Overview

The `src/integrations/email_integration.py` module provides SMTP email functionality to
send SVG exports (Gantt overview, Team Planner snapshot, Resource Usage graph) as email
attachments directly from the application. Authentication credentials are securely
retrieved from **KeePass** — no passwords are stored in QSettings or logged anywhere.


## Prerequisites

| Requirement | Notes |
| ----------- | ----- |
| KeePass database | Must be configured and unlocked via `src/integrations/keepass_integration.py` |
| SMTP server access | Corporate or external SMTP server with TLS support |
| Python standard library | Uses `smtplib` and `email.mime` (no external dependencies) |


## Configuration

All SMTP settings are stored in **QSettings** under the `email/` prefix and are managed
via `src/settings_manager.py` accessor methods:

| QSettings Key | Type | Default | Description |
| ------------- | ---- | ------- | ----------- |
| `email/smtp_server` | str | `""` | SMTP server hostname (e.g. `mail.example.com`) |
| `email/smtp_port` | int | `587` | SMTP port number (587 for STARTTLS, 465 for SSL/TLS, 25 for unencrypted) |
| `email/smtp_use_tls` | bool | `True` | Use STARTTLS for encrypted connection |
| `email/sender_address` | str | `""` | Sender email address (From field) |
| `email/keepass_entry` | str | `""` | KeePass entry title containing SMTP username and password |

### Security Model

- **Credentials**: Username and password are retrieved from KeePass at send-time using
  `keepass_integration.get_credentials(entry_title)`. The KeePass database must be
  unlocked before sending email.
- **No password storage**: Passwords are never stored in QSettings, never logged, and
  never written to the debug dump.
- **KeePass entry**: Only the entry *title* (e.g. `"SMTP Account"`) is stored in
  QSettings. The actual credentials live in the KeePass database.


## Diagnostic Script

The diagnostic script `diagnostic-scripts/test_email_connection.py` demonstrates the
SMTP connection flow used by the integration module:

1. **DNS / TCP reachability** — verify that the SMTP server hostname resolves and port is open
2. **SMTP handshake** — EHLO and STARTTLS negotiation
3. **Authentication** — login with username and password
4. **Message construction** — build MIME message with subject, body, and attachments
5. **Send** — `sendmail()` to deliver the email

The integration module implements the same flow but uses KeePass for credential retrieval
instead of prompting the user interactively.


## Module API

### `is_configured() -> bool`

Returns `True` when all required settings are present (SMTP server, sender address, and
KeePass entry). Does not check whether credentials are valid or the server is reachable.

### `send_email(to, subject, body, attachments=None) -> tuple[bool, str]`

Send an email with optional file attachments via SMTP.

**Arguments:**

- `to` (str | list[str]): Recipient email address(es). Single string or list of strings.
- `subject` (str): Email subject line.
- `body` (str): Email body text (plain text).
- `attachments` (list[tuple[str, bytes]] | None): Optional list of (filename, file_bytes)
  tuples to attach.

**Returns:**

- `(success, error_message)`: `error_message` is empty on success.

**Example:**

```python
from integrations import email_integration

# Send Gantt export as SVG attachment
with open("gantt_export.svg", "rb") as fh:
    svg_bytes = fh.read()

success, error = email_integration.send_email(
    to="manager@example.com",
    subject="Project Gantt Chart — Weekly Update",
    body="Please find the attached Gantt chart for review.\n\nBest regards",
    attachments=[("gantt_export.svg", svg_bytes)],
)

if not success:
    print(f"Failed to send email: {error}")
```

**Error Conditions:**

- Configuration incomplete (server, sender, or KeePass entry missing)
- KeePass database locked or entry not found
- SMTP authentication failure (wrong username/password)
- SMTP connection failure (server unreachable, timeout)
- Recipient/sender refused by server (relay restrictions)

### `test_connection() -> tuple[bool, str]`

Test SMTP connection and authentication without sending an email. Performs the full
handshake (EHLO, STARTTLS, LOGIN) but does not call `sendmail()`.

**Returns:**

- `(success, error_message)`: `error_message` is empty on success.

**Example:**

```python
from integrations import email_integration

success, error = email_integration.test_connection()
if success:
    print("SMTP connection test succeeded")
else:
    print(f"SMTP connection test failed: {error}")
```

### `get_config_summary() -> dict`

Return a summary of email integration configuration for the debug dump. Called by
`src/app_debug.py` when generating the debug dump file.

**Returns:**

```python
{
    "configured": bool,           # True when all required settings are present
    "smtp_server": str,           # SMTP server hostname (safe to log)
    "smtp_port": int,             # SMTP port number
    "smtp_use_tls": bool,         # Whether STARTTLS is enabled
    "sender_address": str,        # Sender email address (safe to log)
    "keepass_entry_set": bool,    # Whether a KeePass entry is configured
    "last_send": dict | None,     # Result of last send_email() call
    "last_test": dict | None,     # Result of last test_connection() call
}
```

**Note:** Passwords and KeePass entry names are never included in the debug dump.


## Credential Retrieval

The email integration module uses `integrations.keepass_integration` to retrieve SMTP credentials at
send-time:

```python
from integrations import keepass_integration

# Check if KeePass is unlocked before attempting to send
if not keepass_integration.is_unlocked():
    # Prompt user to unlock KeePass first
    print("Please unlock KeePass before sending email")
    return

# Retrieve credentials from the configured entry
entry_title = email_integration._get_keepass_entry()
username, password = keepass_integration.get_credentials(entry_title)

if not username or not password:
    print("KeePass entry not found or empty")
    return

# Use credentials for SMTP authentication
smtp.login(username, password)
```


## SettingsManager Integration

The integration module uses dedicated accessor methods in `settings_manager.py` instead
of directly calling `QSettings.value()` / `setValue()`. This ensures consistent defaults
and type coercion across the application.

### Accessor Methods

```python
from settings_manager import get_instance as get_settings_manager

sm = get_settings_manager()

# SMTP server
server = sm.get_email_smtp_server()       # -> str
sm.set_email_smtp_server("mail.example.com")

# SMTP port
port = sm.get_email_smtp_port()           # -> int (default: 587)
sm.set_email_smtp_port(587)

# SMTP TLS
use_tls = sm.get_email_smtp_use_tls()     # -> bool (default: True)
sm.set_email_smtp_use_tls(True)

# Sender address
sender = sm.get_email_sender_address()    # -> str
sm.set_email_sender_address("noreply@example.com")

# KeePass entry
entry = sm.get_email_keepass_entry()      # -> str
sm.set_email_keepass_entry("SMTP Account")
```


## Debug Logging

When `--debug` is passed to `main.py`, the module writes diagnostic messages to stdout:

```plaintext
[email_integration] Message built: 1 recipient(s), 1 attachment(s)
[email_integration] Connecting to mail.example.com:587 (TLS: True)
[email_integration] Authenticated as 'user@example.com'
[email_integration] Email sent successfully to ['manager@example.com']
```

Enable debug mode via:

```bash
python main.py --debug
```


## Error Handling

All public functions return `(bool, str)` tuples — success flag and error message. The
error message is empty on success. Example error messages:

| Error | Message |
| ----- | ------- |
| Configuration incomplete | `"Email integration is not fully configured (server, sender, or KeePass entry missing)"` |
| KeePass locked | `"Failed to retrieve SMTP credentials from KeePass (database locked or entry not found)"` |
| Authentication failure | `"SMTP authentication failed: (535, b'5.7.8 Authentication failed')"` |
| Connection failure | `"SMTP error: [Errno 11001] getaddrinfo failed"` |
| Recipient refused | `"Recipient refused: {'user@example.com': (550, b'5.1.1 User unknown')}"` |
| Sender refused | `"Sender refused: (550, b'5.7.1 Relay access denied')"` |


## SMTP Port Reference

| Port | Usage | Description |
| ---- | ----- | ----------- |
| 587 | STARTTLS (recommended) | Starts unencrypted, then upgrades to TLS via `STARTTLS` command |
| 465 | SSL/TLS (deprecated) | Encrypted from the start (legacy SMTPS) — not supported by this module |
| 25 | Unencrypted (insecure) | Plain SMTP without encryption — avoid for credential transmission |

**Recommendation:** Use port 587 with `smtp_use_tls=True` for maximum compatibility and
security.


## Integration with UI

The email integration module is a backend service — it does not interact with the UI
directly. UI components (dialogs, ribbon buttons) will be implemented separately and will
call the module API. Typical UI workflow:

1. **Configuration dialog** — user enters SMTP server, port, sender address, and selects
   a KeePass entry (similar to `ConfluenceCalendarConfigDialog`).
2. **Export email dialog** — user selects which view to export (Gantt, Team Planner,
   Resource Usage), enters recipient address, subject, and message body.
3. **Send button** — calls `send_email()` with the generated SVG as an attachment;
   displays success/error message in a QMessageBox.


## Multiple Email Accounts

The email integration supports storing **multiple named SMTP configurations** (e.g. a
corporate mail server and a personal account) and selecting which one is active.
This is analogous to the Jira server list pattern.

### Storage

SMTP connection settings (server, port, TLS, sender address) and the active account
name are stored in a plain **`email_configs.json`** file next to the executable.
This file can be copied between machines to share the account list.

| Location | Contents |
| -------- | -------- |
| `<exe dir>/email_configs.json` | `{ "active_config_name": "...", "configs": [...] }` |
| QSettings `email/keepass_entry` | Global KeePass entry name (machine-specific, stays in registry) |

The file is gitignored. When it is absent, the module migrates from QSettings on first
access (see [Legacy migration](#legacy-migration) below).

Each config dict in the array — note that **KeePass credentials are not stored per account**;
they are configured globally via `Email Config` and looked up by `email/keepass_entry`:

```json
{
    "name":           "Work",
    "smtp_server":    "mail.corp.com",
    "smtp_port":      587,
    "smtp_use_tls":   true,
    "sender_address": "alice@corp.com"
}
```

### Legacy migration

On first call to `SettingsManager.get_email_configs()`, if the JSON file is absent or
empty **and** the legacy `email/smtp_server` QSettings key is set, the existing
single-config values are automatically migrated into a single entry named `"Default"`
and saved to `email_configs.json`. No manual migration step is needed.

### SettingsManager API

```python
sm = get_settings_manager()

configs = sm.get_email_configs()             # -> list[dict]
sm.set_email_configs(configs)               # writes email_configs.json

sm.get_active_email_config_name()           # -> str (empty = use first)
sm.set_active_email_config_name("Work")

active = sm.get_active_email_config()       # -> dict | None
```

### email_integration API (multi-config)

All public functions accept an optional `config: dict | None` parameter:

```python
# Use active account (resolved from QSettings)
send_email(to, subject, body)

# Use a specific account explicitly
cfg = {"smtp_server": "smtp.personal.com", "smtp_port": 587, ...}
send_email(to, subject, body, config=cfg)
test_connection(config=cfg)
is_configured(config=cfg)
```

`_resolve_config(config)` resolution order:

1. Explicit `config` parameter (if provided)
2. `SettingsManager.get_active_email_config()` (active named account)
3. Legacy single-config QSettings keys (`email/smtp_server`, …) for backward compat

### Credential lookup

KeePass credentials are **configured globally** (not per account). `_get_keepass_entry(config)`
uses this fallback chain:

1. `config.get("keepass_entry")` — if the config dict has an entry (e.g. migrated legacy config)
2. `sm.get_email_keepass_entry()` — global `email/keepass_entry` QSettings key

This means all SMTP accounts share the same KeePass entry by default. Configure it once
in the **Email Config** dialog.

### UI dialogs

| Dialog | Access | Purpose |
| ------ | ------ | ------- |
| `EmailServersDialog` | Report → **Email Accounts** | Manage list of named SMTP accounts: Add / Edit / Delete / Set Active / Move Up / Move Down |
| `EmailServerEditDialog` | Inside `EmailServersDialog` | Add or edit one account: Name, SMTP Server, Port, TLS, Sender; **"From KeePass…" button** auto-fills Sender Address by looking up the KeePass entry username via AD/LDAP; **no KeePass section** — credentials are global |
| `EmailConfigDialog` | Report → **Email Config** | Project-aware dialog: KeePass entry selector + account `QComboBox` (all named accounts) + **"Manage Accounts…"** button + per-project **Sender Name** `QLineEdit`; active account name and sender display name saved to the project sidecar JSON under `"Email Active Account"` / `"Email Sender Name"` custom props; opened with `project=logic.get_data()` so `_mark_dirty()` fires on accept |

The **Email Accounts** button is always enabled (global QSettings, not project-gated).
The **Email Config** button is always enabled; when a project is open the account selection
and sender name are also project-specific.

### Sender display name (`sender_name`)

Each account dict may include an optional `"sender_name"` key (a human-readable display
name, e.g. `"Alice Smith"`). This is **not** stored in `email_configs.json` — it is
a per-project value saved in the project sidecar under the `"Email Sender Name"` custom
property and injected into the config dict by `EmailConfigDialog._get_current_config()`.

`_get_sender_address(config)` checks for this key and, when present and non-empty,
formats the From address as `"Alice Smith <alice@corp.com>"` using
`email.utils.formataddr` (RFC 2822 name-addr).  When the key is absent or empty, the
plain email address is returned unchanged.

```python
# With sender_name in config → "Alice Smith <alice@corp.com>"
# Without sender_name        → "alice@corp.com"
```

### `get_config_summary()` multi-config keys

```python
{
    # legacy keys (always present for backward compat)
    "configured":          bool,
    "smtp_server":         str,
    "smtp_port":           int,
    "smtp_use_tls":        bool,
    "sender_address":      str,
    "keepass_entry_set":   bool,
    # multi-config keys
    "num_configs":         int,
    "active_config_name":  str,
    "active_configured":   bool,
    "configs": [
        {
            "name":             str,
            "smtp_server":      str,
            "smtp_port":        int,
            "smtp_use_tls":     bool,
            "sender_address":   str,
            "keepass_entry_set": bool,   # bool, NOT the raw entry string
        },
        ...
    ],
    "last_send":   dict | None,
    "last_test":   dict | None,
}
```

> **Security note:** The `keepass_entry` string is replaced by `keepass_entry_set` (bool)
> in the summary so entry names are never written to the debug dump.


## Future Enhancements

- **HTML body support** — currently only plain text body is supported; add MIME multipart
  alternative for rich-formatted emails.
- **Inline images** — embed SVG exports as inline images (Content-ID) instead of
  attachments.
- **Email Export button** — Report ribbon button to select which view to export (Gantt,
  Team Planner, Resource Usage), enter recipient, subject, and body; generate SVG and
  send via the active email account.
- **Email templates** — save subject/body templates in QSettings for reuse.
- **Recipient history** — remember recently used recipient addresses for quick selection.
- **Batch send** — send the same report to multiple recipients with per-recipient
  customisation.
