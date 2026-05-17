# keepass_integration.py - KeePass credential manager.
#
# KeePassManager owns the in-memory PyKeePass session and all runtime
# operations (unlock / lock / create / entry access).  QSettings persistence
# (db_path, key_file, saved password) is delegated to the SettingsManager
# instance passed at construction.
#
# Usage:
#   # ui.py — called once after SettingsManager is created:
#   from integrations import keepass_integration
#   keepass_integration.init(settings_manager)
#
#   # any integration module:
#   from integrations import keepass_integration
#   if keepass_integration.is_unlocked():
#       user, pwd = keepass_integration.get_credentials("MyJiraAccount")

from __future__ import annotations

import os

_manager: "KeePassManager | None" = None


# ---------------------------------------------------------------------------
# KeePassManager class
# ---------------------------------------------------------------------------

class KeePassManager:
    """Owns the in-memory KeePass database session.

    Settings (db_path, key_file, saved password) are read from and written
    to the SettingsManager instance passed at construction.  The PyKeePass
    object is kept only in RAM and is never persisted.
    """

    def __init__(self, settings_manager):
        self._sm = settings_manager   # SettingsManager — used for QSettings access only
        self._db = None               # pykeepass.KeePassFile — session only

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    def is_configured(self) -> bool:
        """Return True when a database path has been saved in QSettings."""
        return bool(self._sm.get_keepass_db_path())

    def is_unlocked(self) -> bool:
        """Return True when the database is currently open in memory."""
        return self._db is not None

    # ------------------------------------------------------------------
    # Unlock / lock
    # ------------------------------------------------------------------

    def unlock(self, password: str) -> tuple[bool, str]:
        """Open the configured database with *password*.

        Returns (success, error_message).  Paths are taken from QSettings.
        """
        try:
            from pykeepass import PyKeePass  # type: ignore
            db_path = self._sm.get_keepass_db_path()
            key_file = self._sm.get_keepass_key_file() or None
            self._db = PyKeePass(db_path, password=password or None, keyfile=key_file)
            return True, ""
        except Exception as exc:
            self._db = None
            return False, str(exc)

    def lock(self) -> None:
        """Discard the in-memory database reference (does not modify the file)."""
        self._db = None

    def auto_unlock(self) -> tuple[bool, str]:
        """Try to unlock using the password saved in QSettings.

        Returns (success, error_message).  No-op if already unlocked.
        """
        if self._db is not None:
            return True, ""
        return self.unlock(self._sm.get_keepass_password())

    # ------------------------------------------------------------------
    # Database creation
    # ------------------------------------------------------------------

    def create_db(
        self, path: str, password: str | None, keyfile: str | None
    ) -> tuple[bool, str]:
        """Create a new KeePass database at *path* and set it as the active database.

        Returns (success, error_message).
        """
        try:
            from pykeepass import create_database  # type: ignore
            path = os.path.abspath(path)
            parent = os.path.dirname(path)
            if parent:
                os.makedirs(parent, exist_ok=True)
            db = create_database(path, password=password or None, keyfile=keyfile or None)
            self._db = db
            self._sm.set_keepass_db_path(path)
            self._sm.set_keepass_key_file(keyfile or "")
            return True, ""
        except Exception as exc:
            self._db = None
            return False, str(exc)

    @staticmethod
    def generate_key_file(path: str) -> tuple[bool, str]:
        """Write 64 cryptographically random bytes to *path* as a binary .keyx key file.

        pykeepass treats a 64-byte file as a hex-encoded 32-byte key.

        Returns (success, error_message).
        """
        try:
            with open(path, "wb") as fh:
                fh.write(os.urandom(64))
            return True, ""
        except Exception as exc:
            return False, str(exc)

    # ------------------------------------------------------------------
    # Entry access
    # ------------------------------------------------------------------

    def find_entry(self, entry_title: str):
        """Return the first pykeepass Entry whose title matches *entry_title*, or None.

        The database must be unlocked; returns None otherwise.
        """
        if self._db is None:
            return None
        entries = self._db.find_entries(title=entry_title, regex=False)
        return entries[0] if entries else None

    def list_entries(self) -> list[str]:
        """Return 'Group/Title' display strings for every entry in the open database."""
        if self._db is None:
            return []
        root = self._db.root_group
        result = []
        for entry in self._db.entries:
            is_root = entry.group is None or entry.group == root
            group = "" if is_root else (entry.group.name or "")
            title = entry.title or ""
            result.append(f"{group}/{title}" if group else title)
        return sorted(result)

    def add_entry(
        self, title: str, username: str, password: str, group_name: str = ""
    ) -> tuple[bool, str]:
        """Add a new entry to the open database and save it to disk.

        Creates *group_name* if it does not exist.
        Returns (success, error_message).
        """
        if self._db is None:
            return False, "KeePass database is not open."
        try:
            if group_name:
                group = self._db.find_groups(name=group_name, first=True)
                if group is None:
                    group = self._db.add_group(self._db.root_group, group_name)
            else:
                group = self._db.root_group
            self._db.add_entry(group, title, username, password)
            self._db.save()
            return True, ""
        except Exception as exc:
            return False, str(exc)

    def save(self) -> tuple[bool, str]:
        """Flush any pending changes to the open database file.

        Returns (success, error_message).
        """
        if self._db is None:
            return False, "No database open."
        try:
            self._db.save()
            return True, ""
        except Exception as exc:
            return False, str(exc)

    def get_credentials(self, entry_title: str) -> tuple[str, str]:
        """Return (username, password) for the entry named *entry_title*.

        Supports 'Group/Title' notation — only the Title part is searched.
        Returns ("", "") when the database is locked or the entry is not found.
        """
        title = entry_title.rsplit("/", 1)[-1]
        entry = self.find_entry(title)
        if entry is None:
            return "", ""
        return (entry.username or "", entry.password or "")


# ---------------------------------------------------------------------------
# Module-level singleton management
# ---------------------------------------------------------------------------

def init(settings_manager) -> KeePassManager:
    """Create and register the module-level KeePassManager singleton.

    Called once by MainWindow.__init__ after SettingsManager is created.
    Returns the new manager.
    """
    global _manager
    _manager = KeePassManager(settings_manager)
    return _manager


def get_manager() -> "KeePassManager | None":
    """Return the registered KeePassManager, or None if init() has not been called."""
    return _manager


# ---------------------------------------------------------------------------
# Module-level convenience functions (for other integration modules)
# ---------------------------------------------------------------------------

def is_configured() -> bool:
    """Return True when a KeePass database path has been set in QSettings."""
    return _manager.is_configured() if _manager else False


def is_unlocked() -> bool:
    """Return True when the database is open in memory for this session."""
    return _manager.is_unlocked() if _manager else False


def unlock(password: str) -> tuple[bool, str]:
    """Unlock the configured database with *password*.

    Returns (success, error_message).
    """
    if _manager is None:
        return False, "KeePass integration not initialised."
    return _manager.unlock(password)


def auto_unlock() -> tuple[bool, str]:
    """Unlock using the saved password from QSettings.

    Returns (success, error_message).
    """
    if _manager is None:
        return False, "KeePass integration not initialised."
    return _manager.auto_unlock()


def lock() -> None:
    """Discard the in-memory database reference (does not modify the file)."""
    if _manager:
        _manager.lock()


def get_entry(entry_title: str):
    """Return the first pykeepass Entry matching *entry_title*, or None.

    Supports 'Group/Title' notation — only the Title part is searched.
    """
    if _manager is None or not _manager.is_unlocked():
        return None
    return _manager.find_entry(entry_title.rsplit("/", 1)[-1])


def get_credentials(entry_title: str) -> tuple[str, str]:
    """Return (username, password) for the KeePass entry named *entry_title*.

    Returns ("", "") when the database is locked, entry is not found,
    or init() has not been called.
    """
    return _manager.get_credentials(entry_title) if _manager else ("", "")


def list_entries() -> list[str]:
    """Return 'Group/Title' display strings for every entry in the open database."""
    return _manager.list_entries() if _manager else []
