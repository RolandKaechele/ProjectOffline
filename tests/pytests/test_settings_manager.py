"""Tests for settings_manager.py — SettingsManager KeePass / Jira / display settings.

All tests use a MagicMock in place of QSettings so that no real registry writes
occur and no QApplication is required.
"""

import sys
import os
import base64
import json

import pytest
from unittest.mock import MagicMock, call, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))

from settings_manager import SettingsManager
from integrations import keepass_integration


# ---------------------------------------------------------------------------
# Helper: SettingsManager backed by a mock QSettings
# ---------------------------------------------------------------------------

def _sm():
    """Return (SettingsManager, mock_QSettings).

    Also re-initialises the keepass_integration singleton so each test
    starts with a fresh, locked KeePassManager.
    """
    mock_qs = MagicMock()
    mock_qs.value.return_value = ""
    sm = SettingsManager(mock_qs)
    keepass_integration.init(sm)
    return sm, mock_qs


# ---------------------------------------------------------------------------
# KeePass path & key-file
# ---------------------------------------------------------------------------

class TestKeePassPaths:
    def test_get_db_path_returns_empty_string_by_default(self):
        sm, qs = _sm()
        qs.value.return_value = ""
        assert sm.get_keepass_db_path() == ""

    def test_set_db_path_calls_setValue(self):
        sm, qs = _sm()
        sm.set_keepass_db_path("/some/path.kdbx")
        qs.setValue.assert_called_with("keepass/db_path", "/some/path.kdbx")

    def test_set_db_path_calls_sync(self):
        sm, qs = _sm()
        sm.set_keepass_db_path("/db.kdbx")
        qs.sync.assert_called()

    def test_set_key_file_calls_setValue(self):
        sm, qs = _sm()
        sm.set_keepass_key_file("/some/key.keyx")
        qs.setValue.assert_called_with("keepass/key_file", "/some/key.keyx")

    def test_is_configured_false_when_path_empty(self):
        sm, qs = _sm()
        qs.value.return_value = ""
        assert not sm.is_keepass_configured()

    def test_is_configured_true_when_path_set(self):
        sm, qs = _sm()
        qs.value.return_value = "/path/to/db.kdbx"
        assert sm.is_keepass_configured()


# ---------------------------------------------------------------------------
# KeePass lock / unlock state
# ---------------------------------------------------------------------------

class TestKeePassState:
    def test_is_unlocked_false_initially(self):
        sm, _ = _sm()
        assert not sm.is_keepass_unlocked()

    def test_lock_clears_keepass_db(self):
        sm, _ = _sm()
        keepass_integration.get_manager()._db = MagicMock()
        sm.lock_keepass()
        assert sm._keepass_db is None

    def test_lock_is_safe_when_already_locked(self):
        sm, _ = _sm()
        sm.lock_keepass()   # should not raise
        assert sm._keepass_db is None

    def test_is_unlocked_true_after_manual_assignment(self):
        sm, _ = _sm()
        keepass_integration.get_manager()._db = MagicMock()
        assert sm.is_keepass_unlocked()


# ---------------------------------------------------------------------------
# KeePass master password persistence
# ---------------------------------------------------------------------------

class TestKeePassPassword:
    def test_get_password_returns_empty_when_not_set(self):
        sm, qs = _sm()
        qs.value.return_value = ""
        assert sm.get_keepass_password() == ""

    def test_set_password_base64_encodes(self):
        sm, qs = _sm()
        sm.set_keepass_password("mysecret")
        stored_key, stored_val = qs.setValue.call_args[0]
        assert stored_key == "keepass/password"
        decoded = base64.b64decode(stored_val.encode()).decode("utf-8")
        assert decoded == "mysecret"

    def test_set_empty_password_removes_key(self):
        sm, qs = _sm()
        sm.set_keepass_password("")
        qs.remove.assert_called_with("keepass/password")

    def test_get_password_decodes_stored_base64(self):
        sm, qs = _sm()
        encoded = base64.b64encode(b"topsecret").decode("ascii")
        qs.value.return_value = encoded
        assert sm.get_keepass_password() == "topsecret"

    def test_get_password_returns_empty_on_corrupt_base64(self):
        sm, qs = _sm()
        qs.value.return_value = "!!!not-valid-base64!!!"
        assert sm.get_keepass_password() == ""


# ---------------------------------------------------------------------------
# KeePass entry operations (locked DB)
# ---------------------------------------------------------------------------

class TestKeePassEntriesLocked:
    def test_list_entries_returns_empty_when_locked(self):
        sm, _ = _sm()
        assert sm.list_keepass_entries() == []

    def test_find_entry_returns_none_when_locked(self):
        sm, _ = _sm()
        assert sm.find_keepass_entry("anything") is None

    def test_save_db_fails_when_locked(self):
        sm, _ = _sm()
        ok, err = sm.save_keepass_db()
        assert not ok
        assert err

    def test_add_entry_fails_when_locked(self):
        sm, _ = _sm()
        ok, err = sm.add_keepass_entry("title", "user", "pass")
        assert not ok
        assert "not open" in err.lower() or err


# ---------------------------------------------------------------------------
# KeePass entry operations (unlocked DB via mock)
# ---------------------------------------------------------------------------

class TestKeePassEntriesUnlocked:
    def _unlocked_sm(self):
        sm, qs = _sm()
        mock_db = MagicMock()
        mock_db.root_group = MagicMock()
        keepass_integration.get_manager()._db = mock_db
        return sm, mock_db

    def test_add_entry_calls_add_entry_on_db(self):
        sm, db = self._unlocked_sm()
        db.find_groups.return_value = None
        ok, err = sm.add_keepass_entry("MyTitle", "alice", "pass123")
        assert ok
        db.add_entry.assert_called()

    def test_add_entry_with_group_creates_group_if_missing(self):
        sm, db = self._unlocked_sm()
        db.find_groups.return_value = None
        sm.add_entry_group = MagicMock()
        ok, err = sm.add_keepass_entry("T", "u", "p", group_name="ProjectOffline")
        assert ok
        db.add_group.assert_called()

    def test_save_db_succeeds(self):
        sm, db = self._unlocked_sm()
        ok, err = sm.save_keepass_db()
        assert ok
        db.save.assert_called_once()

    def test_find_entry_returns_first_match(self):
        sm, db = self._unlocked_sm()
        entry = MagicMock()
        db.find_entries.return_value = [entry]
        result = sm.find_keepass_entry("MyEntry")
        assert result is entry

    def test_find_entry_returns_none_when_no_match(self):
        sm, db = self._unlocked_sm()
        db.find_entries.return_value = []
        assert sm.find_keepass_entry("NoSuch") is None

    def test_list_entries_returns_sorted_strings(self):
        sm, db = self._unlocked_sm()
        e1 = MagicMock(title="Zeta", group=None)
        e2 = MagicMock(title="Alpha", group=None)
        e2.group = db.root_group
        db.entries = [e1, e2]
        result = sm.list_keepass_entries()
        assert result == sorted(result)


# ---------------------------------------------------------------------------
# Jira servers
# ---------------------------------------------------------------------------

class TestJiraServers:
    def test_get_jira_servers_returns_empty_list_by_default(self):
        sm, qs = _sm()
        qs.value.return_value = "[]"
        assert sm.get_jira_servers() == []

    def test_set_jira_servers_stores_json(self):
        sm, qs = _sm()
        servers = [{"url": "https://jira.example.com", "username": "user"}]
        sm.set_jira_servers(servers)
        key, json_val = qs.setValue.call_args[0]
        assert key == "jira/servers"
        assert json.loads(json_val) == servers

    def test_get_jira_servers_deserializes_stored_json(self):
        sm, qs = _sm()
        servers = [{"url": "https://x.com"}]
        qs.value.return_value = json.dumps(servers)
        assert sm.get_jira_servers() == servers

    def test_get_jira_servers_returns_empty_on_invalid_json(self):
        sm, qs = _sm()
        qs.value.return_value = "not json {"
        assert sm.get_jira_servers() == []

    def test_get_jira_credentials_manual_mode(self):
        sm, _ = _sm()
        server = {"auth_mode": "manual", "username": "alice", "token": "tok123"}
        user, tok = sm.get_jira_credentials(server)
        assert user == "alice"
        assert tok == "tok123"

    def test_get_jira_credentials_default_is_manual(self):
        sm, _ = _sm()
        server = {"username": "bob", "token": "abc"}
        user, tok = sm.get_jira_credentials(server)
        assert user == "bob"
        assert tok == "abc"

    def test_get_jira_credentials_keepass_returns_empty_if_locked(self):
        sm, _ = _sm()
        server = {"auth_mode": "keepass", "keepass_entry": "Jira/prod"}
        user, tok = sm.get_jira_credentials(server)
        assert user == "" and tok == ""

    def test_get_jira_credentials_keepass_reads_entry(self):
        sm, _ = _sm()
        mock_db = MagicMock()
        entry = MagicMock(username="jira_user", password="jira_tok")
        mock_db.find_entries.return_value = [entry]
        keepass_integration.get_manager()._db = mock_db
        server = {"auth_mode": "keepass", "keepass_entry": "Jira/prod"}
        user, tok = sm.get_jira_credentials(server)
        assert user == "jira_user"
        assert tok == "jira_tok"

    def test_get_jira_sync_server_returns_empty_string_by_default(self):
        sm, qs = _sm()
        qs.value.return_value = ""
        assert sm.get_jira_sync_server() == ""

    def test_set_jira_sync_server_stores_server_name(self):
        sm, qs = _sm()
        sm.set_jira_sync_server("Production Jira")
        key, val = qs.setValue.call_args[0]
        assert key == "jira/sync_server"
        assert val == "Production Jira"

    def test_get_jira_sync_server_returns_stored_value(self):
        sm, qs = _sm()
        qs.value.return_value = "Test Server"
        assert sm.get_jira_sync_server() == "Test Server"


# ---------------------------------------------------------------------------
# Gantt display preferences
# ---------------------------------------------------------------------------

class TestZeroFloatCritical:
    def test_get_zero_float_critical_returns_false_by_default(self):
        sm, qs = _sm()
        qs.value.return_value = False
        assert not sm.get_zero_float_critical()

    def test_set_zero_float_critical_stores_bool(self):
        sm, qs = _sm()
        sm.set_zero_float_critical(True)
        qs.setValue.assert_called_with("gantt/zero_float_critical", True)

    def test_set_zero_float_critical_false(self):
        sm, qs = _sm()
        sm.set_zero_float_critical(False)
        qs.setValue.assert_called_with("gantt/zero_float_critical", False)


# ---------------------------------------------------------------------------
# Key-file generation
# ---------------------------------------------------------------------------

class TestGenerateKeyFile:
    def test_generates_64_bytes(self, tmp_path):
        sm, _ = _sm()
        key_path = str(tmp_path / "test.key")
        ok, err = sm.generate_key_file(key_path)
        assert ok
        assert err == ""
        with open(key_path, "rb") as f:
            data = f.read()
        assert len(data) == 64

    def test_generates_random_bytes(self, tmp_path):
        sm, _ = _sm()
        p1 = str(tmp_path / "k1.key")
        p2 = str(tmp_path / "k2.key")
        sm.generate_key_file(p1)
        sm.generate_key_file(p2)
        with open(p1, "rb") as f1, open(p2, "rb") as f2:
            assert f1.read() != f2.read()

    def test_bad_path_returns_error(self):
        sm, _ = _sm()
        ok, err = sm.generate_key_file("/no/such/dir/test.key")
        assert not ok
        assert err


# ---------------------------------------------------------------------------
# Confluence SSO settings
# ---------------------------------------------------------------------------

class TestConfluenceSso:
    def test_get_entry_returns_empty_string_by_default(self):
        sm, qs = _sm()
        qs.value.return_value = ""
        assert sm.get_confluence_keepass_entry() == ""

    def test_set_entry_stores_value(self):
        sm, qs = _sm()
        sm.set_confluence_keepass_entry("Confluence/prod")
        qs.setValue.assert_called_with("confluence/keepass_entry", "Confluence/prod")

    def test_set_entry_calls_sync(self):
        sm, qs = _sm()
        sm.set_confluence_keepass_entry("Confluence/prod")
        qs.sync.assert_called()

    def test_set_empty_entry_stores_empty_string(self):
        sm, qs = _sm()
        sm.set_confluence_keepass_entry("")
        qs.setValue.assert_called_with("confluence/keepass_entry", "")

    def test_get_auth_mode_returns_manual_by_default(self):
        sm, qs = _sm()
        qs.value.return_value = "manual"
        assert sm.get_confluence_auth_mode() == "manual"

    def test_set_auth_mode_stores_value(self):
        sm, qs = _sm()
        sm.set_confluence_auth_mode("keepass")
        qs.setValue.assert_called_with("confluence/auth_mode", "keepass")

    def test_set_auth_mode_calls_sync(self):
        sm, qs = _sm()
        sm.set_confluence_auth_mode("keepass")
        qs.sync.assert_called()

    def test_set_auth_mode_manual(self):
        sm, qs = _sm()
        sm.set_confluence_auth_mode("manual")
        qs.setValue.assert_called_with("confluence/auth_mode", "manual")


# ---------------------------------------------------------------------------
# Email multi-config (multiple SMTP accounts)
# ---------------------------------------------------------------------------

class TestEmailConfigs:
    """Tests for get_email_configs / set_email_configs / get_active_email_config.

    All file I/O uses a temporary directory so tests are hermetic.
    The module-level _get_email_config_file_path() is patched to return a path
    inside tmp_path, which also prevents accidental writes to the real project root.
    """

    def _cfg(self, name="Work", server="smtp.work.com", sender="me@work.com") -> dict:
        """Return a minimal SMTP config dict (no keepass_entry — that is global)."""
        return {
            "name": name,
            "smtp_server": server,
            "smtp_port": 587,
            "smtp_use_tls": True,
            "sender_address": sender,
        }

    def _sm_with_file(self, tmp_path):
        """Return (sm, qs, json_path) with the config file path pointing into tmp_path."""
        sm, qs = _sm()
        json_path = str(tmp_path / "email_configs.json")
        return sm, qs, json_path

    # ------------------------------------------------------------------
    # get_email_configs — JSON file as primary source
    # ------------------------------------------------------------------

    def test_get_email_configs_returns_empty_list_when_no_file(self, tmp_path):
        sm, qs, path = self._sm_with_file(tmp_path)
        def qs_default(key, default="", **kwargs):
            if key == "email/configs":
                return "[]"
            return default
        qs.value.side_effect = qs_default
        with patch("settings_manager._get_email_config_file_path", return_value=path):
            configs = sm.get_email_configs()
        assert configs == []

    def test_get_email_configs_reads_from_json_file(self, tmp_path):
        sm, qs, path = self._sm_with_file(tmp_path)
        import json as _json
        data = {"active_config_name": "Work", "configs": [self._cfg("Work")]}
        with open(path, "w") as fh:
            _json.dump(data, fh)
        with patch("settings_manager._get_email_config_file_path", return_value=path):
            configs = sm.get_email_configs()
        assert len(configs) == 1
        assert configs[0]["name"] == "Work"

    def test_get_email_configs_returns_empty_on_invalid_json_file(self, tmp_path):
        sm, qs, path = self._sm_with_file(tmp_path)
        with open(path, "w") as fh:
            fh.write("not valid json {{{")
        def qs_default(key, default="", **kwargs):
            if key == "email/configs":
                return "[]"
            return default
        qs.value.side_effect = qs_default
        with patch("settings_manager._get_email_config_file_path", return_value=path):
            configs = sm.get_email_configs()
        assert configs == []

    # ------------------------------------------------------------------
    # set_email_configs — writes JSON file
    # ------------------------------------------------------------------

    def test_set_email_configs_writes_json_file(self, tmp_path):
        import json as _json
        sm, qs, path = self._sm_with_file(tmp_path)
        configs = [self._cfg("Work"), self._cfg("Personal", server="smtp.p.com", sender="p@p.com")]
        with patch("settings_manager._get_email_config_file_path", return_value=path):
            sm.set_email_configs(configs)
        with open(path, "r") as fh:
            saved = _json.load(fh)
        assert saved["configs"] == configs

    def test_set_email_configs_preserves_active_config_name(self, tmp_path):
        import json as _json
        sm, qs, path = self._sm_with_file(tmp_path)
        # Pre-populate file with an active name
        with open(path, "w") as fh:
            _json.dump({"active_config_name": "Work", "configs": []}, fh)
        with patch("settings_manager._get_email_config_file_path", return_value=path):
            sm.set_email_configs([self._cfg("Work")])
        with open(path, "r") as fh:
            saved = _json.load(fh)
        assert saved["active_config_name"] == "Work"

    def test_set_email_configs_does_not_touch_qsettings(self, tmp_path):
        sm, qs, path = self._sm_with_file(tmp_path)
        with patch("settings_manager._get_email_config_file_path", return_value=path):
            sm.set_email_configs([self._cfg()])
        qs.setValue.assert_not_called()

    # ------------------------------------------------------------------
    # get_active_email_config_name / set_active_email_config_name
    # ------------------------------------------------------------------

    def test_get_active_email_config_name_returns_empty_when_no_file(self, tmp_path):
        sm, qs, path = self._sm_with_file(tmp_path)
        with patch("settings_manager._get_email_config_file_path", return_value=path):
            assert sm.get_active_email_config_name() == ""

    def test_set_and_get_active_email_config_name_round_trip(self, tmp_path):
        sm, qs, path = self._sm_with_file(tmp_path)
        with patch("settings_manager._get_email_config_file_path", return_value=path):
            sm.set_active_email_config_name("Work")
            assert sm.get_active_email_config_name() == "Work"

    def test_set_active_email_config_name_preserves_configs(self, tmp_path):
        import json as _json
        sm, qs, path = self._sm_with_file(tmp_path)
        configs = [self._cfg("Work")]
        with open(path, "w") as fh:
            _json.dump({"active_config_name": "", "configs": configs}, fh)
        with patch("settings_manager._get_email_config_file_path", return_value=path):
            sm.set_active_email_config_name("Work")
        with open(path, "r") as fh:
            saved = _json.load(fh)
        assert saved["configs"] == configs
        assert saved["active_config_name"] == "Work"

    def test_set_active_email_config_name_does_not_touch_qsettings(self, tmp_path):
        sm, qs, path = self._sm_with_file(tmp_path)
        with patch("settings_manager._get_email_config_file_path", return_value=path):
            sm.set_active_email_config_name("Work")
        qs.setValue.assert_not_called()

    # ------------------------------------------------------------------
    # Migration from QSettings on first access
    # ------------------------------------------------------------------

    def test_get_email_configs_migrates_new_style_qsettings_to_json(self, tmp_path):
        sm, qs, path = self._sm_with_file(tmp_path)
        existing = [self._cfg("Work")]
        def qs_default(key, default="", **kwargs):
            if key == "email/configs":
                return json.dumps(existing)
            return default
        qs.value.side_effect = qs_default
        with patch("settings_manager._get_email_config_file_path", return_value=path):
            configs = sm.get_email_configs()
        assert len(configs) == 1
        assert configs[0]["name"] == "Work"
        # JSON file should now exist
        import os as _os
        assert _os.path.exists(path)

    def test_get_email_configs_migrates_legacy_single_config_to_json(self, tmp_path):
        sm, qs, path = self._sm_with_file(tmp_path)
        def qs_default(key, default="", **kwargs):
            if key == "email/configs":
                return "[]"
            if key == "email/smtp_server":
                return "legacy.server.com"
            if key == "email/smtp_port":
                return 587
            if key == "email/smtp_use_tls":
                return True
            if key == "email/sender_address":
                return "legacy@example.com"
            return default
        qs.value.side_effect = qs_default
        with patch("settings_manager._get_email_config_file_path", return_value=path):
            configs = sm.get_email_configs()
        assert len(configs) == 1
        assert configs[0]["name"] == "Default"
        assert configs[0]["smtp_server"] == "legacy.server.com"
        assert "sender_address" not in configs[0], (
            "sender_address must not be stored per-account in email_configs.json; "
            "it is now stored per-project in the project sidecar file."
        )
        assert "keepass_entry" not in configs[0]

    def test_get_email_configs_no_migration_when_no_legacy_key(self, tmp_path):
        sm, qs, path = self._sm_with_file(tmp_path)
        def qs_default(key, default="", **kwargs):
            if key == "email/configs":
                return "[]"
            return default
        qs.value.side_effect = qs_default
        with patch("settings_manager._get_email_config_file_path", return_value=path):
            configs = sm.get_email_configs()
        assert configs == []

    # ------------------------------------------------------------------
    # get_active_email_config (composite)
    # ------------------------------------------------------------------

    def test_get_active_email_config_returns_matching_config(self, tmp_path):
        import json as _json
        sm, qs, path = self._sm_with_file(tmp_path)
        configs = [self._cfg("Work"), self._cfg("Personal", server="smtp.p.com", sender="p@p.com")]
        with open(path, "w") as fh:
            _json.dump({"active_config_name": "Personal", "configs": configs}, fh)
        with patch("settings_manager._get_email_config_file_path", return_value=path):
            result = sm.get_active_email_config()
        assert result is not None
        assert result["name"] == "Personal"
        assert result["smtp_server"] == "smtp.p.com"

    def test_get_active_email_config_falls_back_to_first_when_name_unset(self, tmp_path):
        import json as _json
        sm, qs, path = self._sm_with_file(tmp_path)
        configs = [self._cfg("Work"), self._cfg("Personal", server="smtp.p.com", sender="p@p.com")]
        with open(path, "w") as fh:
            _json.dump({"active_config_name": "", "configs": configs}, fh)
        with patch("settings_manager._get_email_config_file_path", return_value=path):
            result = sm.get_active_email_config()
        assert result is not None
        assert result["name"] == "Work"

    def test_get_active_email_config_returns_none_when_no_configs(self, tmp_path):
        sm, qs, path = self._sm_with_file(tmp_path)
        def qs_default(key, default="", **kwargs):
            if key == "email/configs":
                return "[]"
            return default
        qs.value.side_effect = qs_default
        with patch("settings_manager._get_email_config_file_path", return_value=path):
            result = sm.get_active_email_config()
        assert result is None


# ---------------------------------------------------------------------------
# Email config file helpers (module-level functions)
# ---------------------------------------------------------------------------

class TestEmailConfigFileHelpers:
    """Unit tests for the three module-level helpers in settings_manager.py:
    _get_email_config_file_path, _read_email_config_file, _write_email_config_file.
    """

    # ------------------------------------------------------------------
    # _get_email_config_file_path — path resolution
    # ------------------------------------------------------------------

    def test_file_path_in_dev_mode_ends_with_correct_filename(self):
        """In dev/test mode sys.frozen is absent; filename must be email_configs.json."""
        from settings_manager import _get_email_config_file_path
        import sys as _sys
        # Ensure sys.frozen is not set (it never is in test runs, but be explicit)
        assert not getattr(_sys, "frozen", False)
        path = _get_email_config_file_path()
        assert path.endswith("email_configs.json")

    def test_file_path_in_dev_mode_is_one_level_above_src(self):
        """In dev mode the file lives at project root (parent of src/)."""
        from settings_manager import _get_email_config_file_path
        import os as _os
        path = _get_email_config_file_path()
        # The directory containing the file must not be src/ itself
        parent = _os.path.basename(_os.path.dirname(path))
        assert parent != "src"

    def test_file_path_in_frozen_mode_is_next_to_executable(self, tmp_path, monkeypatch):
        """When sys.frozen is True the file must live next to sys.executable."""
        from settings_manager import _get_email_config_file_path
        import sys as _sys
        fake_exe = str(tmp_path / "ProjectOffline.exe")
        monkeypatch.setattr(_sys, "frozen", True, raising=False)
        monkeypatch.setattr(_sys, "executable", fake_exe)
        try:
            path = _get_email_config_file_path()
        finally:
            monkeypatch.delattr(_sys, "frozen", raising=False)
        assert path == str(tmp_path / "email_configs.json")

    # ------------------------------------------------------------------
    # _read_email_config_file — error paths
    # ------------------------------------------------------------------

    def test_read_returns_empty_dict_when_file_missing(self, tmp_path):
        from settings_manager import _read_email_config_file
        path = str(tmp_path / "nonexistent.json")
        assert _read_email_config_file(path) == {}

    def test_read_returns_empty_dict_on_invalid_json(self, tmp_path):
        from settings_manager import _read_email_config_file
        path = str(tmp_path / "bad.json")
        with open(path, "w") as fh:
            fh.write("{broken json")
        assert _read_email_config_file(path) == {}

    def test_read_returns_parsed_dict_for_valid_file(self, tmp_path):
        from settings_manager import _read_email_config_file
        path = str(tmp_path / "cfg.json")
        with open(path, "w") as fh:
            fh.write('{"active_config_name": "Work", "configs": []}')
        result = _read_email_config_file(path)
        assert result == {"active_config_name": "Work", "configs": []}

    # ------------------------------------------------------------------
    # _write_email_config_file — round-trip
    # ------------------------------------------------------------------

    def test_write_creates_file_with_valid_json(self, tmp_path):
        from settings_manager import _write_email_config_file, _read_email_config_file
        path = str(tmp_path / "out.json")
        data = {"active_config_name": "X", "configs": [{"name": "X", "smtp_server": "s"}]}
        _write_email_config_file(path, data)
        result = _read_email_config_file(path)
        assert result == data

    def test_write_uses_utf8_encoding(self, tmp_path):
        """Non-ASCII chars in sender addresses must survive a round-trip."""
        from settings_manager import _write_email_config_file, _read_email_config_file
        path = str(tmp_path / "utf8.json")
        data = {"active_config_name": "Ä", "configs": []}
        _write_email_config_file(path, data)
        result = _read_email_config_file(path)
        assert result["active_config_name"] == "Ä"

    # ------------------------------------------------------------------
    # Migration: verify the JSON file contents after migration
    # ------------------------------------------------------------------

    def test_migration_writes_json_file_with_correct_content(self, tmp_path):
        """After migrating from QSettings the JSON file must contain the configs."""
        sm, qs = _sm()
        path = str(tmp_path / "email_configs.json")
        existing = [{"name": "Work", "smtp_server": "smtp.work.com",
                     "smtp_port": 587, "smtp_use_tls": True,
                     "sender_address": "me@work.com"}]

        def qs_default(key, default="", **kwargs):
            if key == "email/configs":
                return json.dumps(existing)
            if key == "email/active_config_name":
                return "Work"
            return default

        qs.value.side_effect = qs_default
        with patch("settings_manager._get_email_config_file_path", return_value=path):
            sm.get_email_configs()

        from settings_manager import _read_email_config_file
        saved = _read_email_config_file(path)
        assert saved.get("configs") == existing
        assert saved.get("active_config_name") == "Work"

    def test_migration_does_not_include_keepass_entry_in_legacy_migrated_config(self, tmp_path):
        """Legacy migration must NOT copy email/keepass_entry into the per-account dict."""
        sm, qs = _sm()
        path = str(tmp_path / "email_configs.json")

        def qs_default(key, default="", **kwargs):
            if key == "email/configs":
                return "[]"
            if key == "email/smtp_server":
                return "smtp.legacy.com"
            if key == "email/keepass_entry":
                return "Legacy/Entry"
            return default

        qs.value.side_effect = qs_default
        with patch("settings_manager._get_email_config_file_path", return_value=path):
            configs = sm.get_email_configs()

        assert len(configs) == 1
        assert "keepass_entry" not in configs[0]


# ---------------------------------------------------------------------------
# CPM Settings (Phases 1–2)
# ---------------------------------------------------------------------------

class TestCpmSettingsManager:
    """Tests for the CPM-related SettingsManager methods added in Phases 1–2."""

    def test_get_critical_slack_days_default_zero(self):
        sm, qs = _sm()
        qs.value.return_value = 0
        assert sm.get_critical_slack_days() == 0

    def test_set_critical_slack_days_saves_value(self):
        sm, qs = _sm()
        sm.set_critical_slack_days(3)
        qs.setValue.assert_any_call("cpm/critical_slack_days", 3)

    def test_set_critical_slack_days_clamps_negative_to_zero(self):
        sm, qs = _sm()
        sm.set_critical_slack_days(-5)
        qs.setValue.assert_any_call("cpm/critical_slack_days", 0)

    def test_set_critical_slack_days_calls_sync(self):
        sm, qs = _sm()
        sm.set_critical_slack_days(1)
        qs.sync.assert_called()

    def test_get_cpm_dep_types_default_all(self):
        sm, qs = _sm()
        qs.value.return_value = "all"
        assert sm.get_cpm_dep_types() == "all"

    def test_set_cpm_dep_types_saves_fs_only(self):
        sm, qs = _sm()
        sm.set_cpm_dep_types("fs_only")
        qs.setValue.assert_any_call("cpm/dep_types", "fs_only")

    def test_set_cpm_dep_types_saves_all(self):
        sm, qs = _sm()
        sm.set_cpm_dep_types("all")
        qs.setValue.assert_any_call("cpm/dep_types", "all")

    def test_set_cpm_dep_types_invalid_falls_back_to_all(self):
        sm, qs = _sm()
        sm.set_cpm_dep_types("invalid_mode")
        qs.setValue.assert_any_call("cpm/dep_types", "all")

    def test_get_show_float_bar_default_false(self):
        sm, qs = _sm()
        qs.value.return_value = False
        assert sm.get_show_float_bar() is False

    def test_set_show_float_bar_saves_true(self):
        sm, qs = _sm()
        sm.set_show_float_bar(True)
        qs.setValue.assert_any_call("cpm/show_float_bar", True)

    def test_get_show_free_float_column_default_false(self):
        sm, qs = _sm()
        qs.value.return_value = False
        assert sm.get_show_free_float_column() is False

    def test_set_show_free_float_column_saves_true(self):
        sm, qs = _sm()
        sm.set_show_free_float_column(True)
        qs.setValue.assert_any_call("cpm/show_free_float_column", True)

    def test_get_show_cpm_results_panel_default_false(self):
        sm, qs = _sm()
        qs.value.return_value = False
        assert sm.get_show_cpm_results_panel() is False

    def test_set_show_cpm_results_panel_saves_true(self):
        sm, qs = _sm()
        sm.set_show_cpm_results_panel(True)
        qs.setValue.assert_any_call("cpm/show_cpm_results_panel", True)
