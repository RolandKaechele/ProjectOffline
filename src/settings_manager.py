# -*- coding: utf-8 -*-
# settings_manager.py - Persistent settings for KeePass and Jira integrations
#
# KeePass QSettings keys (db_path, key_file, optional saved password) are
# managed here.  All KeePass runtime logic (unlock/lock/entry access) lives in
# src/integrations/keepass_integration.py (KeePassManager).
#
# The backward-compat shim methods (unlock_keepass, lock_keepass, …) delegate
# to keepass_integration so that existing callers (settings_dialogs.py,
# integrations/confluence_calendar_integration.py) continue to work without modification.
#
# Jira server list (including manual credentials) is stored in QSettings as JSON.
#
# Email multi-account config (SMTP server, port, TLS, sender) is stored in a
# plain JSON file (email_configs.json) next to the executable so the file can be
# copied between machines.  The KeePass entry name is kept in QSettings because
# it is machine-specific (tied to the local KeePass database path).
#
# Usage:
#   sm = SettingsManager(qsettings_instance)
#   # keepass_integration.init(sm) is called by ui.py to wire the KeePassManager.
#   user, pwd = sm.get_jira_credentials(server_dict)

import json
import os
import sys
import base64
from PyQt5.QtCore import QSettings  # type: ignore

_ORG = "ProjectOffline"
_APP = "ProjectManager"

# ---------------------------------------------------------------------------
# Email config JSON file helpers
# ---------------------------------------------------------------------------

def _get_email_config_file_path() -> str:
    """Return the absolute path to email_configs.json.

    When running as a bundled PyInstaller executable the file sits next to the
    .exe so the whole installation folder can be copied between machines.  In
    development mode (running directly from Python) the file lives at the
    project root (one directory above src/).
    """
    if getattr(sys, "frozen", False):
        base = os.path.dirname(os.path.abspath(sys.executable))
    else:
        base = os.path.normpath(
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
        )
    return os.path.join(base, "email_configs.json")


def _read_email_config_file(path: str) -> dict:
    """Read and return the email config JSON file as a dict.

    Returns an empty dict on any error (file missing, invalid JSON, etc.).
    """
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _write_email_config_file(path: str, data: dict) -> None:
    """Atomically write *data* to the email config JSON file."""
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, ensure_ascii=False)


class SettingsManager:
    """Manages persistent QSettings for KeePass paths/passwords and Jira servers.

    A single instance is created in MainWindow and passed to every dialog that
    needs it.  KeePass runtime state (the open database object) lives in
    integrations.keepass_integration.KeePassManager, which is initialised by
    ui.py after this object is created.
    """

    def __init__(self, settings: QSettings | None = None):
        self._settings = settings or QSettings(_ORG, _APP)

    def _sync(self):
        """Immediately flush QSettings to persistent storage."""
        self._settings.sync()

    # ------------------------------------------------------------------ #
    # KeePass — QSettings persistence                                      #
    # ------------------------------------------------------------------ #

    def get_keepass_db_path(self) -> str:
        return self._settings.value("keepass/db_path", "", type=str)

    def set_keepass_db_path(self, path: str):
        self._settings.setValue("keepass/db_path", path)
        self._sync()

    def get_keepass_key_file(self) -> str:
        return self._settings.value("keepass/key_file", "", type=str)

    def set_keepass_key_file(self, path: str):
        self._settings.setValue("keepass/key_file", path)
        self._sync()

    def is_keepass_configured(self) -> bool:
        return bool(self.get_keepass_db_path())

    def get_keepass_password(self) -> str:
        """Return the saved master password (base64-decoded from QSettings)."""
        encoded = self._settings.value("keepass/password", "", type=str)
        if not encoded:
            return ""
        try:
            return base64.b64decode(encoded.encode()).decode("utf-8")
        except Exception:
            return ""

    def set_keepass_password(self, pwd: str):
        """Persist the master password as base64 in QSettings.  Pass '' to clear."""
        if pwd:
            self._settings.setValue(
                "keepass/password",
                base64.b64encode(pwd.encode("utf-8")).decode("ascii"),
            )
        else:
            self._settings.remove("keepass/password")
        self._sync()

    # ------------------------------------------------------------------ #
    # KeePass — backward-compat shims (delegate to keepass_integration)   #
    # ------------------------------------------------------------------ #

    @property
    def _keepass_db(self):
        """Read-only shim: returns the raw PyKeePass object from KeePassManager."""
        from integrations import keepass_integration as _kp  # type: ignore
        m = _kp.get_manager()
        return m._db if m else None

    def is_keepass_unlocked(self) -> bool:
        from integrations import keepass_integration as _kp  # type: ignore
        return _kp.is_unlocked()

    def unlock_keepass(self, password: str) -> tuple[bool, str]:
        from integrations import keepass_integration as _kp  # type: ignore
        m = _kp.get_manager()
        if m is None:
            return False, "KeePass integration not initialised."
        return m.unlock(password)

    def lock_keepass(self):
        from integrations import keepass_integration as _kp  # type: ignore
        _kp.lock()

    def auto_unlock_keepass(self) -> tuple[bool, str]:
        from integrations import keepass_integration as _kp  # type: ignore
        return _kp.auto_unlock()

    def create_keepass_db(
        self, path: str, password: str | None, keyfile: str | None
    ) -> tuple[bool, str]:
        from integrations import keepass_integration as _kp  # type: ignore
        m = _kp.get_manager()
        if m is None:
            return False, "KeePass integration not initialised."
        return m.create_db(path, password, keyfile)

    def add_keepass_entry(
        self, title: str, username: str, password: str, group_name: str = ""
    ) -> tuple[bool, str]:
        from integrations import keepass_integration as _kp  # type: ignore
        m = _kp.get_manager()
        if m is None:
            return False, "KeePass integration not initialised."
        return m.add_entry(title, username, password, group_name)

    def save_keepass_db(self) -> tuple[bool, str]:
        from integrations import keepass_integration as _kp  # type: ignore
        m = _kp.get_manager()
        if m is None:
            return False, "No database open."
        return m.save()

    def generate_key_file(self, path: str) -> tuple[bool, str]:
        from integrations.keepass_integration import KeePassManager  # type: ignore
        return KeePassManager.generate_key_file(path)

    def find_keepass_entry(self, entry_title: str):
        from integrations import keepass_integration as _kp  # type: ignore
        m = _kp.get_manager()
        return m.find_entry(entry_title) if m else None

    def list_keepass_entries(self) -> list[str]:
        from integrations import keepass_integration as _kp  # type: ignore
        return _kp.list_entries()

    # ------------------------------------------------------------------ #
    # Jira Servers                                                         #
    # ------------------------------------------------------------------ #

    def get_jira_servers(self) -> list[dict]:
        """Return the persisted list of Jira server configuration dicts."""
        raw = self._settings.value("jira/servers", "[]", type=str)
        try:
            return json.loads(raw)
        except Exception:
            return []

    def set_jira_servers(self, servers: list[dict]):
        """Persist the list of Jira server configuration dicts."""
        self._settings.setValue("jira/servers", json.dumps(servers))
        self._sync()

    def get_jira_sync_server(self) -> str:
        """Return the name of the Jira server selected for sync configuration."""
        return self._settings.value("jira/sync_server", "", type=str)

    def set_jira_sync_server(self, server_name: str):
        """Persist the name of the Jira server selected for sync configuration."""
        self._settings.setValue("jira/sync_server", server_name)
        self._sync()

    def get_jira_credentials(self, server: dict) -> tuple[str, str]:
        """Return (username, token/password) for a Jira server dict.

        If auth_mode == 'keepass', the credentials are read live from the
        open KeePass database.  Returns ("", "") when credentials are
        unavailable.
        """
        mode = server.get("auth_mode", "manual")
        if mode == "keepass":
            entry_path = server.get("keepass_entry", "")
            if not entry_path or not self.is_keepass_unlocked():
                return "", ""
            # Support "Group/Title" notation: search by the title part
            title = entry_path.rsplit("/", 1)[-1]
            entry = self.find_keepass_entry(title)
            if entry is None:
                return "", ""
            # Strip whitespace from credentials (KeePass may store with trailing newlines)
            username = (entry.username or "").strip()
            password = (entry.password or "").strip()
            return (username, password)
        # Manual credentials - strip whitespace
        return (server.get("username", "").strip(), server.get("token", "").strip())

    # ------------------------------------------------------------------ #
    # Confluence SSO                                                       #
    # ------------------------------------------------------------------ #

    def get_confluence_keepass_entry(self) -> str:
        """Return the KeePass entry title used for Confluence SSO auto-fill."""
        return self._settings.value("confluence/keepass_entry", "", type=str)

    def set_confluence_keepass_entry(self, entry: str):
        self._settings.setValue("confluence/keepass_entry", entry)
        self._sync()

    def get_confluence_auth_mode(self) -> str:
        """Return the Confluence SSO auth mode: 'manual' or 'keepass'."""
        return self._settings.value("confluence/auth_mode", "manual", type=str)

    def set_confluence_auth_mode(self, mode: str):
        self._settings.setValue("confluence/auth_mode", mode)
        self._sync()

    # ------------------------------------------------------------------ #
    # Email Integration (SMTP)                                             #
    # ------------------------------------------------------------------ #

    def get_email_smtp_server(self) -> str:
        """Return the configured SMTP server hostname."""
        return self._settings.value("email/smtp_server", "", type=str)

    def set_email_smtp_server(self, server: str):
        self._settings.setValue("email/smtp_server", server)
        self._sync()

    def get_email_smtp_port(self) -> int:
        """Return the configured SMTP port number (default: 587)."""
        return self._settings.value("email/smtp_port", 587, type=int)

    def set_email_smtp_port(self, port: int):
        self._settings.setValue("email/smtp_port", port)
        self._sync()

    def get_email_smtp_use_tls(self) -> bool:
        """Return True if STARTTLS should be used (default: True)."""
        return self._settings.value("email/smtp_use_tls", True, type=bool)

    def set_email_smtp_use_tls(self, use_tls: bool):
        self._settings.setValue("email/smtp_use_tls", bool(use_tls))
        self._sync()

    def get_email_sender_address(self) -> str:
        """Return the configured sender email address (From field)."""
        return self._settings.value("email/sender_address", "", type=str)

    def set_email_sender_address(self, address: str):
        self._settings.setValue("email/sender_address", address)
        self._sync()

    def get_email_keepass_entry(self) -> str:
        """Return the KeePass entry title for SMTP credentials."""
        return self._settings.value("email/keepass_entry", "", type=str)

    def set_email_keepass_entry(self, entry: str):
        self._settings.setValue("email/keepass_entry", entry)
        self._sync()

    # ------------------------------------------------------------------ #
    # Email Integration — multiple configurations (JSON file)              #
    # ------------------------------------------------------------------ #

    def get_email_configs(self) -> list:
        """Return the persisted list of email configuration dicts.

        Each dict has keys: name, smtp_server, smtp_port, smtp_use_tls.
        (KeePass entry is stored globally in QSettings; sender address is stored
        per-project in the project sidecar file.)

        Storage order:
          1. email_configs.json next to the executable (primary).
          2. QSettings email/configs (new-style migration source).
          3. Legacy single-config QSettings keys (email/smtp_server, …).

        On first call the function migrates existing QSettings data into the
        JSON file so users who upgrade automatically get their data moved.
        """
        path = _get_email_config_file_path()
        data = _read_email_config_file(path)
        configs = data.get("configs", [])
        if isinstance(configs, list) and configs:
            return configs

        # JSON file empty / missing — try to migrate from QSettings
        configs = self._migrate_email_configs_from_qsettings()
        if configs:
            # Persist to JSON so future reads skip QSettings
            active = data.get("active_config_name", "")
            if not active:
                active = self._settings.value("email/active_config_name", "", type=str)
            _write_email_config_file(path, {
                "active_config_name": active,
                "configs": configs,
            })
        return configs

    def _migrate_email_configs_from_qsettings(self) -> list:
        """Read email configs from QSettings (new-style or legacy) for one-time migration."""
        # New-style multi-config stored as JSON text in QSettings
        raw = self._settings.value("email/configs", "[]", type=str)
        try:
            configs = json.loads(raw)
        except Exception:
            configs = []
        if isinstance(configs, list) and configs:
            return configs

        # Legacy single-config keys
        server = self._settings.value("email/smtp_server", "", type=str)
        if server:
            return [{
                "name": "Default",
                "smtp_server": server,
                "smtp_port": self._settings.value("email/smtp_port", 587, type=int),
                "smtp_use_tls": self._settings.value("email/smtp_use_tls", True, type=bool),
            }]
        return []

    def set_email_configs(self, configs: list) -> None:
        """Persist the list of email configuration dicts to the JSON file."""
        path = _get_email_config_file_path()
        data = _read_email_config_file(path)
        data["configs"] = configs
        _write_email_config_file(path, data)

    def get_active_email_config_name(self) -> str:
        """Return the name of the active email configuration from the JSON file."""
        path = _get_email_config_file_path()
        data = _read_email_config_file(path)
        return data.get("active_config_name", "")

    def set_active_email_config_name(self, name: str) -> None:
        """Persist the name of the active email configuration to the JSON file."""
        path = _get_email_config_file_path()
        data = _read_email_config_file(path)
        data["active_config_name"] = name
        _write_email_config_file(path, data)

    def get_active_email_config(self):
        """Return the active email configuration dict, or None if not configured.

        Falls back to the first config in the list when no active name is set.
        """
        name = self.get_active_email_config_name()
        configs = self.get_email_configs()
        if name:
            for cfg in configs:
                if cfg.get("name") == name:
                    return cfg
        return configs[0] if configs else None

    # ------------------------------------------------------------------ #
    # Gantt display preferences                                            #
    # ------------------------------------------------------------------ #

    def get_zero_float_critical(self) -> bool:
        """Return True if tasks with exactly zero total float should be shown critical."""
        return self._settings.value("gantt/zero_float_critical", False, type=bool)

    def set_zero_float_critical(self, value: bool):
        self._settings.setValue("gantt/zero_float_critical", bool(value))
        self._sync()

    # ------------------------------------------------------------------ #
    # CPM Settings (display preferences stored in QSettings)              #
    # ------------------------------------------------------------------ #

    def get_critical_slack_days(self) -> int:
        """Return the numeric critical slack threshold in days (MS Project default: 0)."""
        return self._settings.value("cpm/critical_slack_days", 0, type=int)

    def set_critical_slack_days(self, days: int):
        self._settings.setValue("cpm/critical_slack_days", max(0, int(days)))
        self._sync()

    def get_cpm_dep_types(self) -> str:
        """Return the CPM dependency types mode: 'all' (FS+SS+FF+SF) or 'fs_only'."""
        return self._settings.value("cpm/dep_types", "all", type=str)

    def set_cpm_dep_types(self, mode: str):
        self._settings.setValue("cpm/dep_types", mode if mode in ("all", "fs_only") else "all")
        self._sync()

    def get_show_float_bar(self) -> bool:
        """Return True if a total-float overlay bar should be drawn on Gantt task bars."""
        return self._settings.value("cpm/show_float_bar", False, type=bool)

    def set_show_float_bar(self, value: bool):
        self._settings.setValue("cpm/show_float_bar", bool(value))
        self._sync()

    def get_show_free_float_column(self) -> bool:
        """Return True if the Free Float column should be shown in Task Sheet view."""
        return self._settings.value("cpm/show_free_float_column", False, type=bool)

    def set_show_free_float_column(self, value: bool):
        self._settings.setValue("cpm/show_free_float_column", bool(value))
        self._sync()

    def get_show_cpm_results_panel(self) -> bool:
        """Return True if the CPM Results panel tab should be visible."""
        return self._settings.value("cpm/show_cpm_results_panel", False, type=bool)

    def set_show_cpm_results_panel(self, value: bool):
        self._settings.setValue("cpm/show_cpm_results_panel", bool(value))
        self._sync()

    # ------------------------------------------------------------------ #
    # Version Control Integration                                          #
    # ------------------------------------------------------------------ #

    def get_vcs_keepass_entry(self) -> str:
        """Return the KeePass entry title used for VCS credentials."""
        return self._settings.value("vcs/keepass_entry", "", type=str)

    def set_vcs_keepass_entry(self, entry: str):
        self._settings.setValue("vcs/keepass_entry", entry)
        self._sync()

    def get_vcs_auto_commit_enabled(self) -> bool:
        """Return True if auto-commit on save is enabled (default True)."""
        return self._settings.value("vcs/auto_commit_enabled", True, type=bool)

    def set_vcs_auto_commit_enabled(self, enabled: bool):
        self._settings.setValue("vcs/auto_commit_enabled", bool(enabled))
        self._sync()

    def get_vcs_auto_commit_template(self) -> str:
        """Return the commit message template for auto-commits."""
        return self._settings.value(
            "vcs/auto_commit_template",
            "Auto-commit: {project_name} saved at {timestamp}",
            type=str,
        )

    def set_vcs_auto_commit_template(self, template: str):
        self._settings.setValue("vcs/auto_commit_template", template)
        self._sync()

    def get_vcs_auto_commit_scope(self) -> str:
        """Return 'project' (project file only) or 'all' (all tracked changes)."""
        return self._settings.value("vcs/auto_commit_scope", "project", type=str)

    def set_vcs_auto_commit_scope(self, scope: str):
        self._settings.setValue("vcs/auto_commit_scope", scope)
        self._sync()

    def get_vcs_git_path(self) -> str:
        """Return the configured path to git.exe (empty = auto-detect from tools/)."""
        return self._settings.value("vcs/git_path", "", type=str)

    def set_vcs_git_path(self, path: str):
        self._settings.setValue("vcs/git_path", path)
        self._sync()

    def get_vcs_svn_path(self) -> str:
        """Return the configured path to svn.exe (empty = auto-detect from tools/)."""
        return self._settings.value("vcs/svn_path", "", type=str)

    def set_vcs_svn_path(self, path: str):
        self._settings.setValue("vcs/svn_path", path)
        self._sync()
