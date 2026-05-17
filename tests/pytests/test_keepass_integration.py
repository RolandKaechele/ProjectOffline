"""Tests for integrations/keepass_integration.py — KeePassManager and module-level functions.

KeePassManager is the canonical owner of the in-memory pykeepass session.
Module-level helpers (init, is_unlocked, get_credentials, …) delegate to the singleton.

All pykeepass imports are stubbed in sys.modules by conftest.py so no real
KeePass database or pykeepass library is required.
"""

import sys
import os

import pytest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from integrations import keepass_integration
from integrations.keepass_integration import KeePassManager


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _fresh_manager():
    """Return (KeePassManager, mock_SettingsManager) with no database open."""
    mock_sm = MagicMock()
    mock_sm.get_keepass_db_path.return_value = ""
    mock_sm.get_keepass_key_file.return_value = ""
    mock_sm.get_keepass_password.return_value = ""
    return KeePassManager(mock_sm), mock_sm


def _unlocked_manager():
    """Return (KeePassManager, mock_db) with a mock database already open."""
    m, _ = _fresh_manager()
    mock_db = MagicMock()
    mock_db.root_group = MagicMock()
    m._db = mock_db
    return m, mock_db


# ---------------------------------------------------------------------------
# Module singleton management
# ---------------------------------------------------------------------------

class TestKeePassManagerInit:
    def test_init_creates_manager(self):
        mock_sm = MagicMock()
        m = keepass_integration.init(mock_sm)
        assert isinstance(m, KeePassManager)

    def test_get_manager_returns_registered_instance(self):
        mock_sm = MagicMock()
        m = keepass_integration.init(mock_sm)
        assert keepass_integration.get_manager() is m


# ---------------------------------------------------------------------------
# Module-level functions before init() — safe defaults
# ---------------------------------------------------------------------------

class TestKeePassManagerBeforeInit:
    """Module-level convenience functions return safe defaults when the singleton
    has not yet been registered via init()."""

    def setup_method(self):
        self._saved = keepass_integration._manager
        keepass_integration._manager = None

    def teardown_method(self):
        keepass_integration._manager = self._saved

    def test_is_configured_false(self):
        assert keepass_integration.is_configured() is False

    def test_is_unlocked_false(self):
        assert keepass_integration.is_unlocked() is False

    def test_unlock_returns_error_tuple(self):
        ok, err = keepass_integration.unlock("any")
        assert not ok
        assert err

    def test_auto_unlock_returns_error_tuple(self):
        ok, err = keepass_integration.auto_unlock()
        assert not ok
        assert err

    def test_get_entry_returns_none(self):
        assert keepass_integration.get_entry("anything") is None

    def test_get_credentials_returns_empty_strings(self):
        user, pwd = keepass_integration.get_credentials("anything")
        assert user == "" and pwd == ""

    def test_list_entries_returns_empty_list(self):
        assert keepass_integration.list_entries() == []

    def test_lock_does_not_raise(self):
        keepass_integration.lock()   # must not raise


# ---------------------------------------------------------------------------
# KeePassManager state queries
# ---------------------------------------------------------------------------

class TestKeePassManagerState:
    def test_is_configured_false_when_path_empty(self):
        m, sm = _fresh_manager()
        sm.get_keepass_db_path.return_value = ""
        assert m.is_configured() is False

    def test_is_configured_true_when_path_set(self):
        m, sm = _fresh_manager()
        sm.get_keepass_db_path.return_value = "/path/db.kdbx"
        assert m.is_configured() is True

    def test_is_unlocked_false_initially(self):
        m, _ = _fresh_manager()
        assert m.is_unlocked() is False

    def test_is_unlocked_true_when_db_set(self):
        m, _ = _fresh_manager()
        m._db = MagicMock()
        assert m.is_unlocked() is True


# ---------------------------------------------------------------------------
# Unlock / lock
# ---------------------------------------------------------------------------

class TestKeePassManagerUnlock:
    def teardown_method(self):
        sys.modules['pykeepass'].PyKeePass.side_effect = None

    def test_unlock_success_sets_db(self):
        m, sm = _fresh_manager()
        sm.get_keepass_db_path.return_value = "/db.kdbx"
        sm.get_keepass_key_file.return_value = ""
        mock_db = MagicMock()
        sys.modules['pykeepass'].PyKeePass.return_value = mock_db
        ok, err = m.unlock("masterpass")
        assert ok is True
        assert err == ""
        assert m._db is mock_db

    def test_unlock_failure_returns_error_and_clears_db(self):
        m, sm = _fresh_manager()
        sm.get_keepass_db_path.return_value = "/db.kdbx"
        sm.get_keepass_key_file.return_value = ""
        sys.modules['pykeepass'].PyKeePass.side_effect = Exception("wrong password")
        ok, err = m.unlock("bad")
        assert ok is False
        assert "wrong password" in err
        assert m._db is None

    def test_lock_clears_db(self):
        m, _ = _fresh_manager()
        m._db = MagicMock()
        m.lock()
        assert m._db is None

    def test_auto_unlock_noop_when_already_unlocked(self):
        m, sm = _fresh_manager()
        m._db = MagicMock()
        ok, err = m.auto_unlock()
        assert ok is True
        assert err == ""
        sm.get_keepass_password.assert_not_called()

    def test_auto_unlock_uses_saved_password(self):
        m, sm = _fresh_manager()
        sm.get_keepass_db_path.return_value = "/db.kdbx"
        sm.get_keepass_key_file.return_value = ""
        sm.get_keepass_password.return_value = "saved"
        sys.modules['pykeepass'].PyKeePass.return_value = MagicMock()
        ok, err = m.auto_unlock()
        assert ok is True
        sm.get_keepass_password.assert_called()

    def test_auto_unlock_fails_when_no_password_saved(self):
        m, sm = _fresh_manager()
        sm.get_keepass_db_path.return_value = "/db.kdbx"
        sm.get_keepass_key_file.return_value = ""
        sm.get_keepass_password.return_value = ""
        sys.modules['pykeepass'].PyKeePass.side_effect = Exception("credentials")
        ok, err = m.auto_unlock()
        assert not ok
        assert err

    def test_unlock_passes_keyfile_to_pykeepass(self):
        m, sm = _fresh_manager()
        sm.get_keepass_db_path.return_value = "/db.kdbx"
        sm.get_keepass_key_file.return_value = "/my.keyx"
        sys.modules['pykeepass'].PyKeePass.return_value = MagicMock()
        m.unlock("pwd")
        _, kwargs = sys.modules['pykeepass'].PyKeePass.call_args
        assert kwargs.get("keyfile") == "/my.keyx"


# ---------------------------------------------------------------------------
# Database creation
# ---------------------------------------------------------------------------

class TestKeePassManagerCreateDb:
    def teardown_method(self):
        sys.modules['pykeepass'].create_database.side_effect = None

    def test_create_db_success(self):
        from unittest.mock import patch
        m, sm = _fresh_manager()
        mock_db = MagicMock()
        sys.modules['pykeepass'].create_database.return_value = mock_db
        abs_path = os.path.abspath("/new/db.kdbx")
        with patch("integrations.keepass_integration.os.makedirs"):
            ok, err = m.create_db("/new/db.kdbx", "pwd", None)
        assert ok is True
        assert err == ""
        assert m._db is mock_db
        sm.set_keepass_db_path.assert_called_with(abs_path)

    def test_create_db_converts_relative_to_absolute(self):
        from unittest.mock import patch
        m, sm = _fresh_manager()
        sys.modules['pykeepass'].create_database.return_value = MagicMock()
        with patch("integrations.keepass_integration.os.makedirs"):
            m.create_db("relative/db.kdbx", "pwd", None)
        called_path = sm.set_keepass_db_path.call_args[0][0]
        assert os.path.isabs(called_path)

    def test_create_db_ensures_parent_directory(self):
        from unittest.mock import patch, call
        m, sm = _fresh_manager()
        sys.modules['pykeepass'].create_database.return_value = MagicMock()
        with patch("integrations.keepass_integration.os.makedirs") as mock_makedirs:
            m.create_db("/some/deep/path/db.kdbx", "pwd", None)
        mock_makedirs.assert_called_once()
        args, kwargs = mock_makedirs.call_args
        assert kwargs.get("exist_ok") is True

    def test_create_db_saves_keyfile_path(self):
        from unittest.mock import patch
        m, sm = _fresh_manager()
        sys.modules['pykeepass'].create_database.return_value = MagicMock()
        with patch("integrations.keepass_integration.os.makedirs"):
            m.create_db("/db.kdbx", "pwd", "/my.keyx")
        sm.set_keepass_key_file.assert_called_with("/my.keyx")

    def test_create_db_clears_keyfile_when_none(self):
        from unittest.mock import patch
        m, sm = _fresh_manager()
        sys.modules['pykeepass'].create_database.return_value = MagicMock()
        with patch("integrations.keepass_integration.os.makedirs"):
            m.create_db("/db.kdbx", "pwd", None)
        sm.set_keepass_key_file.assert_called_with("")

    def test_create_db_failure_returns_error(self):
        m, _ = _fresh_manager()
        sys.modules['pykeepass'].create_database.side_effect = Exception("disk full")
        ok, err = m.create_db("/new/db.kdbx", "pwd", None)
        assert ok is False
        assert "disk full" in err
        assert m._db is None


# ---------------------------------------------------------------------------
# Entry operations — locked database
# ---------------------------------------------------------------------------

class TestKeePassManagerEntriesLocked:
    def test_find_entry_returns_none_when_locked(self):
        m, _ = _fresh_manager()
        assert m.find_entry("MyEntry") is None

    def test_list_entries_returns_empty_when_locked(self):
        m, _ = _fresh_manager()
        assert m.list_entries() == []

    def test_add_entry_fails_when_locked(self):
        m, _ = _fresh_manager()
        ok, err = m.add_entry("title", "user", "pass")
        assert not ok
        assert "not open" in err.lower()

    def test_save_fails_when_locked(self):
        m, _ = _fresh_manager()
        ok, err = m.save()
        assert not ok
        assert err


# ---------------------------------------------------------------------------
# Entry operations — unlocked database (mock db)
# ---------------------------------------------------------------------------

class TestKeePassManagerEntriesUnlocked:
    def test_find_entry_returns_first_match(self):
        m, db = _unlocked_manager()
        entry = MagicMock()
        db.find_entries.return_value = [entry]
        result = m.find_entry("MyEntry")
        assert result is entry
        db.find_entries.assert_called_with(title="MyEntry", regex=False)

    def test_find_entry_no_match_returns_none(self):
        m, db = _unlocked_manager()
        db.find_entries.return_value = []
        assert m.find_entry("NoSuch") is None

    def test_list_entries_sorted(self):
        m, db = _unlocked_manager()
        e1 = MagicMock(title="Zeta", group=None)
        e2 = MagicMock(title="Alpha", group=None)
        e2.group = db.root_group
        db.entries = [e1, e2]
        result = m.list_entries()
        assert result == sorted(result)

    def test_list_entries_with_group_prefix(self):
        m, db = _unlocked_manager()
        group = MagicMock()
        group.name = "MyGroup"
        entry = MagicMock(title="MyEntry")
        entry.group = group
        db.entries = [entry]
        result = m.list_entries()
        assert "MyGroup/MyEntry" in result

    def test_add_entry_no_group_uses_root(self):
        m, db = _unlocked_manager()
        ok, err = m.add_entry("title", "user", "pass")
        assert ok
        db.add_entry.assert_called_with(db.root_group, "title", "user", "pass")
        db.save.assert_called_once()

    def test_add_entry_creates_missing_group(self):
        m, db = _unlocked_manager()
        db.find_groups.return_value = None
        ok, err = m.add_entry("title", "user", "pass", group_name="NewGroup")
        assert ok
        db.add_group.assert_called()

    def test_add_entry_uses_existing_group(self):
        m, db = _unlocked_manager()
        existing = MagicMock()
        db.find_groups.return_value = existing
        ok, err = m.add_entry("title", "user", "pass", group_name="Existing")
        assert ok
        db.add_group.assert_not_called()
        db.add_entry.assert_called_with(existing, "title", "user", "pass")

    def test_save_calls_db_save(self):
        m, db = _unlocked_manager()
        ok, err = m.save()
        assert ok
        db.save.assert_called_once()

    def test_save_returns_error_on_exception(self):
        m, db = _unlocked_manager()
        db.save.side_effect = Exception("io error")
        ok, err = m.save()
        assert not ok
        assert "io error" in err

    def test_get_credentials_returns_username_and_password(self):
        m, db = _unlocked_manager()
        entry = MagicMock(username="alice", password="secret")
        db.find_entries.return_value = [entry]
        user, pwd = m.get_credentials("MyEntry")
        assert user == "alice"
        assert pwd == "secret"

    def test_get_credentials_strips_group_prefix(self):
        m, db = _unlocked_manager()
        entry = MagicMock(username="bob", password="tok")
        db.find_entries.return_value = [entry]
        m.get_credentials("Group/MyEntry")
        db.find_entries.assert_called_with(title="MyEntry", regex=False)

    def test_get_credentials_not_found_returns_empty_strings(self):
        m, db = _unlocked_manager()
        db.find_entries.return_value = []
        user, pwd = m.get_credentials("NoSuch")
        assert user == "" and pwd == ""


# ---------------------------------------------------------------------------
# Module-level convenience functions (with manager registered)
# ---------------------------------------------------------------------------

class TestModuleLevelFunctions:
    def setup_method(self):
        mock_sm = MagicMock()
        mock_sm.get_keepass_db_path.return_value = ""
        mock_sm.get_keepass_key_file.return_value = ""
        mock_sm.get_keepass_password.return_value = ""
        self._manager = keepass_integration.init(mock_sm)

    def test_is_configured_delegates_to_manager(self):
        self._manager._sm.get_keepass_db_path.return_value = "/db.kdbx"
        assert keepass_integration.is_configured() is True

    def test_is_unlocked_delegates_to_manager(self):
        self._manager._db = MagicMock()
        assert keepass_integration.is_unlocked() is True

    def test_lock_clears_manager_db(self):
        self._manager._db = MagicMock()
        keepass_integration.lock()
        assert self._manager._db is None

    def test_get_entry_returns_matching_entry(self):
        mock_db = MagicMock()
        entry = MagicMock()
        mock_db.find_entries.return_value = [entry]
        self._manager._db = mock_db
        result = keepass_integration.get_entry("MyEntry")
        assert result is entry

    def test_list_entries_returns_entry_titles(self):
        mock_db = MagicMock()
        mock_db.root_group = MagicMock()
        e = MagicMock(title="E1", group=None)
        mock_db.entries = [e]
        self._manager._db = mock_db
        assert "E1" in keepass_integration.list_entries()


# ---------------------------------------------------------------------------
# Key-file generation (static method — tested directly on KeePassManager)
# ---------------------------------------------------------------------------

class TestKeePassManagerGenerateKeyFile:
    def test_generates_64_bytes(self, tmp_path):
        path = str(tmp_path / "test.keyx")
        ok, err = KeePassManager.generate_key_file(path)
        assert ok
        assert err == ""
        with open(path, "rb") as f:
            assert len(f.read()) == 64

    def test_key_file_is_binary(self, tmp_path):
        """Generated key file must be binary, not XML."""
        path = str(tmp_path / "test.keyx")
        KeePassManager.generate_key_file(path)
        with open(path, "rb") as f:
            content = f.read()
        assert not content.startswith(b"<?xml") and not content.startswith(b"<Key")

    def test_generates_random_bytes(self, tmp_path):
        p1 = str(tmp_path / "k1.keyx")
        p2 = str(tmp_path / "k2.keyx")
        KeePassManager.generate_key_file(p1)
        KeePassManager.generate_key_file(p2)
        with open(p1, "rb") as f1, open(p2, "rb") as f2:
            assert f1.read() != f2.read()

    def test_bad_path_returns_error(self):
        ok, err = KeePassManager.generate_key_file("/no/such/dir/test.keyx")
        assert not ok
        assert err
