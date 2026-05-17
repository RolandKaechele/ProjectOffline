"""Tests for integrations/email_integration.py — SMTP email module.

All SMTP connections and KeePass interactions are mocked; no real SMTP server
or KeePass database is required to run these tests.
"""

import sys
import os

import pytest
from unittest.mock import MagicMock, patch, call

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))


class TestEmailIntegration:
    """Unit tests for src/integrations/email_integration.py."""

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _mock_settings_manager(self, server="mail.example.com", port=587,
                                use_tls=True, sender="test@example.com",
                                entry="TestEntry"):
        """Create a mock SettingsManager with email settings."""
        mock_sm = MagicMock()
        mock_sm.get_email_smtp_server.return_value = server
        mock_sm.get_email_smtp_port.return_value = port
        mock_sm.get_email_smtp_use_tls.return_value = use_tls
        mock_sm.get_email_sender_address.return_value = sender
        mock_sm.get_email_keepass_entry.return_value = entry
        return mock_sm

    def _mock_smtp(self, auth_success=True, send_success=True):
        """Create a mock SMTP instance."""
        mock = MagicMock()
        mock.ehlo.return_value = (250, b"OK")
        mock.has_extn.return_value = True
        if not auth_success:
            import smtplib
            mock.login.side_effect = smtplib.SMTPAuthenticationError(535, b"Auth failed")
        if not send_success:
            import smtplib
            mock.sendmail.side_effect = smtplib.SMTPException("Send failed")
        return mock

    # ------------------------------------------------------------------
    # is_configured
    # ------------------------------------------------------------------

    def test_is_configured_true_when_all_settings_present(self):
        from integrations import email_integration
        with patch("integrations.email_integration._get_settings_manager",
                   return_value=self._mock_settings_manager()):
            assert email_integration.is_configured() is True

    def test_is_configured_false_when_server_missing(self):
        from integrations import email_integration
        with patch("integrations.email_integration._get_settings_manager",
                   return_value=self._mock_settings_manager(server="")):
            assert email_integration.is_configured() is False

    def test_is_configured_false_when_sender_missing(self):
        from integrations import email_integration
        with patch("integrations.email_integration._get_settings_manager",
                   return_value=self._mock_settings_manager(sender="")):
            assert email_integration.is_configured() is False

    def test_is_configured_false_when_entry_missing(self):
        from integrations import email_integration
        with patch("integrations.email_integration._get_settings_manager",
                   return_value=self._mock_settings_manager(entry="")):
            assert email_integration.is_configured() is False

    # ------------------------------------------------------------------
    # Configuration getters
    # ------------------------------------------------------------------

    def test_get_smtp_server_returns_value_from_settings(self):
        from integrations.email_integration import _get_smtp_server
        with patch("integrations.email_integration._get_settings_manager",
                   return_value=self._mock_settings_manager(server="smtp.test.com")):
            assert _get_smtp_server() == "smtp.test.com"

    def test_get_smtp_port_returns_value_from_settings(self):
        from integrations.email_integration import _get_smtp_port
        with patch("integrations.email_integration._get_settings_manager",
                   return_value=self._mock_settings_manager(port=465)):
            assert _get_smtp_port() == 465

    def test_get_smtp_use_tls_returns_value_from_settings(self):
        from integrations.email_integration import _get_smtp_use_tls
        with patch("integrations.email_integration._get_settings_manager",
                   return_value=self._mock_settings_manager(use_tls=False)):
            assert _get_smtp_use_tls() is False

    def test_get_sender_address_returns_value_from_settings(self):
        from integrations.email_integration import _get_sender_address
        with patch("integrations.email_integration._get_settings_manager",
                   return_value=self._mock_settings_manager(sender="noreply@test.com")):
            assert _get_sender_address() == "noreply@test.com"

    def test_get_keepass_entry_returns_value_from_settings(self):
        from integrations.email_integration import _get_keepass_entry
        with patch("integrations.email_integration._get_settings_manager",
                   return_value=self._mock_settings_manager(entry="EmailCreds")):
            assert _get_keepass_entry() == "EmailCreds"

    # ------------------------------------------------------------------
    # Configuration setters
    # ------------------------------------------------------------------

    def test_set_smtp_server_calls_settings_manager(self):
        from integrations.email_integration import set_smtp_server
        mock_sm = self._mock_settings_manager()
        with patch("integrations.email_integration._get_settings_manager",
                   return_value=mock_sm):
            set_smtp_server("new.server.com")
        mock_sm.set_email_smtp_server.assert_called_once_with("new.server.com")

    def test_set_smtp_port_calls_settings_manager(self):
        from integrations.email_integration import set_smtp_port
        mock_sm = self._mock_settings_manager()
        with patch("integrations.email_integration._get_settings_manager",
                   return_value=mock_sm):
            set_smtp_port(25)
        mock_sm.set_email_smtp_port.assert_called_once_with(25)

    def test_set_sender_address_calls_settings_manager(self):
        from integrations.email_integration import set_sender_address
        mock_sm = self._mock_settings_manager()
        with patch("integrations.email_integration._get_settings_manager",
                   return_value=mock_sm):
            set_sender_address("new@example.com")
        mock_sm.set_email_sender_address.assert_called_once_with("new@example.com")

    def test_set_keepass_entry_calls_settings_manager(self):
        from integrations.email_integration import set_keepass_entry
        mock_sm = self._mock_settings_manager()
        with patch("integrations.email_integration._get_settings_manager",
                   return_value=mock_sm):
            set_keepass_entry("NewEntry")
        mock_sm.set_email_keepass_entry.assert_called_once_with("NewEntry")

    # ------------------------------------------------------------------
    # test_connection
    # ------------------------------------------------------------------

    def test_test_connection_success(self):
        from integrations import email_integration
        mock_sm = self._mock_settings_manager()
        mock_smtp = self._mock_smtp()
        
        with patch("integrations.email_integration._get_settings_manager",
                   return_value=mock_sm), \
             patch("integrations.email_integration._get_credentials",
                   return_value=("user", "pass")), \
             patch("smtplib.SMTP", return_value=mock_smtp):
            success, error = email_integration.test_connection()
        
        assert success is True
        assert error == ""
        mock_smtp.login.assert_called_once_with("user", "pass")
        mock_smtp.quit.assert_called_once()

    def test_test_connection_fails_when_not_configured(self):
        from integrations import email_integration
        with patch("integrations.email_integration.is_configured",
                   return_value=False):
            success, error = email_integration.test_connection()
        assert success is False
        assert "not fully configured" in error

    def test_test_connection_fails_when_credentials_missing(self):
        from integrations import email_integration
        with patch("integrations.email_integration.is_configured",
                   return_value=True), \
             patch("integrations.email_integration._get_credentials",
                   return_value=("", "")):
            success, error = email_integration.test_connection()
        assert success is False
        assert "Failed to retrieve" in error

    def test_test_connection_fails_on_auth_error(self):
        from integrations import email_integration
        mock_sm = self._mock_settings_manager()
        mock_smtp = self._mock_smtp(auth_success=False)
        
        with patch("integrations.email_integration._get_settings_manager",
                   return_value=mock_sm), \
             patch("integrations.email_integration._get_credentials",
                   return_value=("user", "pass")), \
             patch("smtplib.SMTP", return_value=mock_smtp):
            success, error = email_integration.test_connection()
        
        assert success is False
        assert "authentication failed" in error.lower()

    def test_test_connection_handles_tls_when_available(self):
        from integrations import email_integration
        mock_sm = self._mock_settings_manager(use_tls=True)
        mock_smtp = self._mock_smtp()
        mock_smtp.has_extn.return_value = True
        
        with patch("integrations.email_integration._get_settings_manager",
                   return_value=mock_sm), \
             patch("integrations.email_integration._get_credentials",
                   return_value=("user", "pass")), \
             patch("smtplib.SMTP", return_value=mock_smtp):
            email_integration.test_connection()
        
        mock_smtp.starttls.assert_called_once()

    def test_test_connection_skips_tls_when_not_supported(self):
        from integrations import email_integration
        mock_sm = self._mock_settings_manager(use_tls=True)
        mock_smtp = self._mock_smtp()
        mock_smtp.has_extn.return_value = False
        
        with patch("integrations.email_integration._get_settings_manager",
                   return_value=mock_sm), \
             patch("integrations.email_integration._get_credentials",
                   return_value=("user", "pass")), \
             patch("smtplib.SMTP", return_value=mock_smtp):
            email_integration.test_connection()
        
        mock_smtp.starttls.assert_not_called()

    # ------------------------------------------------------------------
    # send_email
    # ------------------------------------------------------------------

    def test_send_email_success_single_recipient(self):
        from integrations import email_integration
        mock_sm = self._mock_settings_manager()
        mock_smtp = self._mock_smtp()
        
        with patch("integrations.email_integration._get_settings_manager",
                   return_value=mock_sm), \
             patch("integrations.email_integration._get_credentials",
                   return_value=("user", "pass")), \
             patch("smtplib.SMTP", return_value=mock_smtp):
            success, error = email_integration.send_email(
                to="recipient@example.com",
                subject="Test",
                body="Test body"
            )
        
        assert success is True
        assert error == ""
        assert mock_smtp.sendmail.called

    def test_send_email_success_multiple_recipients(self):
        from integrations import email_integration
        mock_sm = self._mock_settings_manager()
        mock_smtp = self._mock_smtp()
        
        with patch("integrations.email_integration._get_settings_manager",
                   return_value=mock_sm), \
             patch("integrations.email_integration._get_credentials",
                   return_value=("user", "pass")), \
             patch("smtplib.SMTP", return_value=mock_smtp):
            success, error = email_integration.send_email(
                to=["user1@example.com", "user2@example.com"],
                subject="Test",
                body="Test body"
            )
        
        assert success is True
        call_args = mock_smtp.sendmail.call_args[0]
        assert len(call_args[1]) == 2

    def test_send_email_with_attachments(self):
        from integrations import email_integration
        mock_sm = self._mock_settings_manager()
        mock_smtp = self._mock_smtp()
        
        with patch("integrations.email_integration._get_settings_manager",
                   return_value=mock_sm), \
             patch("integrations.email_integration._get_credentials",
                   return_value=("user", "pass")), \
             patch("smtplib.SMTP", return_value=mock_smtp):
            success, error = email_integration.send_email(
                to="recipient@example.com",
                subject="Test",
                body="Test body",
                attachments=[("test.txt", b"file content")]
            )
        
        assert success is True

    def test_send_email_fails_when_no_recipients(self):
        from integrations import email_integration
        success, error = email_integration.send_email(
            to=[],
            subject="Test",
            body="Test body"
        )
        assert success is False
        assert "No recipient" in error

    def test_send_email_fails_when_not_configured(self):
        from integrations import email_integration
        with patch("integrations.email_integration.is_configured",
                   return_value=False):
            success, error = email_integration.send_email(
                to="recipient@example.com",
                subject="Test",
                body="Test body"
            )
        assert success is False
        assert "not fully configured" in error

    def test_send_email_fails_on_smtp_error(self):
        from integrations import email_integration
        mock_sm = self._mock_settings_manager()
        mock_smtp = self._mock_smtp(send_success=False)
        
        with patch("integrations.email_integration._get_settings_manager",
                   return_value=mock_sm), \
             patch("integrations.email_integration._get_credentials",
                   return_value=("user", "pass")), \
             patch("smtplib.SMTP", return_value=mock_smtp):
            success, error = email_integration.send_email(
                to="recipient@example.com",
                subject="Test",
                body="Test body"
            )
        
        assert success is False
        assert "SMTP error" in error

    # ------------------------------------------------------------------
    # get_config_summary
    # ------------------------------------------------------------------

    def test_get_config_summary_returns_dict(self):
        from integrations import email_integration
        with patch("integrations.email_integration._get_settings_manager",
                   return_value=self._mock_settings_manager()):
            summary = email_integration.get_config_summary()
        assert isinstance(summary, dict)
        assert "configured" in summary
        assert "smtp_server" in summary
        assert "smtp_port" in summary
        assert "sender_address" in summary

    def test_get_config_summary_does_not_include_passwords(self):
        from integrations import email_integration
        with patch("integrations.email_integration._get_settings_manager",
                   return_value=self._mock_settings_manager()):
            summary = email_integration.get_config_summary()
        summary_str = str(summary)
        assert "password" not in summary_str.lower()
        assert "keepass_entry_set" in summary
        # Entry name itself should not be included for security
        assert summary["keepass_entry_set"] is True

    def test_get_config_summary_includes_last_results(self):
        from integrations import email_integration
        with patch("integrations.email_integration._get_settings_manager",
                   return_value=self._mock_settings_manager()):
            summary = email_integration.get_config_summary()
        assert "last_send" in summary
        assert "last_test" in summary

    # ------------------------------------------------------------------
    # Error message generation
    # ------------------------------------------------------------------

    def test_error_messages_are_user_friendly(self):
        """Verify error messages don't expose sensitive information."""
        from integrations import email_integration
        
        with patch("integrations.email_integration.is_configured",
                   return_value=False):
            _, error = email_integration.send_email("test@example.com", "Test", "Body")
        
        # Should not contain technical jargon or stack traces
        assert "not fully configured" in error
        assert "traceback" not in error.lower()
        assert "exception" not in error.lower()


# ---------------------------------------------------------------------------
# Integration with keepass_integration module
# ---------------------------------------------------------------------------

class TestEmailKeePassIntegration:
    """Test that email_integration correctly uses keepass_integration."""

    def test_get_credentials_returns_empty_when_keepass_locked(self):
        from integrations.email_integration import _get_credentials
        with patch("integrations.keepass_integration.is_unlocked",
                   return_value=False):
            username, password = _get_credentials()
        assert username == ""
        assert password == ""

    def test_get_credentials_retrieves_from_keepass_when_unlocked(self):
        from integrations.email_integration import _get_credentials
        with patch("integrations.keepass_integration.is_unlocked",
                   return_value=True), \
             patch("integrations.email_integration._get_keepass_entry",
                   return_value="TestEntry"), \
             patch("integrations.keepass_integration.get_credentials",
                   return_value=("testuser", "testpass")):
            username, password = _get_credentials()
        assert username == "testuser"
        assert password == "testpass"

    def test_get_credentials_returns_empty_when_entry_not_found(self):
        from integrations.email_integration import _get_credentials
        with patch("integrations.keepass_integration.is_unlocked",
                   return_value=True), \
             patch("integrations.email_integration._get_keepass_entry",
                   return_value="NonExistent"), \
             patch("integrations.keepass_integration.get_credentials",
                   return_value=("", "")):
            username, password = _get_credentials()
        assert username == ""
        assert password == ""


# ---------------------------------------------------------------------------
# Multi-config API (EmailServersDialog / multiple SMTP accounts)
# ---------------------------------------------------------------------------

class TestEmailMultiConfig:
    """Tests for the multiple email configuration (multi-account) feature."""

    def _cfg(self, name="Work", server="smtp.work.com", port=587,
             use_tls=True, sender="me@work.com", entry="Work/SMTP") -> dict:
        return {
            "name": name,
            "smtp_server": server,
            "smtp_port": port,
            "smtp_use_tls": use_tls,
            "sender_address": sender,
            "keepass_entry": entry,
        }

    def _mock_sm_multi(self, configs=None, active_name=""):
        """SettingsManager mock with multi-config support."""
        if configs is None:
            configs = []
        mock_sm = MagicMock()
        mock_sm.get_email_configs.return_value = configs
        mock_sm.get_active_email_config_name.return_value = active_name
        # get_active_email_config returns the matching dict or None
        def _active():
            for c in configs:
                if c.get("name") == active_name:
                    return c
            return configs[0] if configs else None
        mock_sm.get_active_email_config.side_effect = _active
        return mock_sm

    # ------------------------------------------------------------------
    # get_active_config
    # ------------------------------------------------------------------

    def test_get_active_config_returns_none_when_no_sm(self):
        from integrations import email_integration
        with patch("integrations.email_integration._get_settings_manager", return_value=None):
            assert email_integration.get_active_config() is None

    def test_get_active_config_returns_none_when_sm_returns_non_dict(self):
        from integrations import email_integration
        mock_sm = MagicMock()
        mock_sm.get_active_email_config.return_value = "not-a-dict"
        with patch("integrations.email_integration._get_settings_manager", return_value=mock_sm):
            assert email_integration.get_active_config() is None

    def test_get_active_config_returns_dict_from_sm(self):
        from integrations import email_integration
        cfg = self._cfg()
        mock_sm = self._mock_sm_multi([cfg], active_name="Work")
        with patch("integrations.email_integration._get_settings_manager", return_value=mock_sm):
            result = email_integration.get_active_config()
        assert result == cfg

    # ------------------------------------------------------------------
    # is_configured with explicit config dict
    # ------------------------------------------------------------------

    def test_is_configured_true_with_explicit_config(self):
        from integrations import email_integration
        cfg = self._cfg()
        # No SM needed — config dict is passed directly
        assert email_integration.is_configured(config=cfg) is True

    def test_is_configured_false_with_explicit_config_missing_server(self):
        from integrations import email_integration
        cfg = self._cfg(server="")
        assert email_integration.is_configured(config=cfg) is False

    def test_is_configured_false_with_explicit_config_missing_sender(self):
        from integrations import email_integration
        cfg = self._cfg(sender="")
        assert email_integration.is_configured(config=cfg) is False

    def test_is_configured_false_with_explicit_config_missing_entry(self):
        from integrations import email_integration
        cfg = self._cfg(entry="")
        mock_sm = MagicMock()
        mock_sm.get_email_keepass_entry.return_value = ""  # global fallback also empty
        with patch("integrations.email_integration._get_settings_manager", return_value=mock_sm):
            assert email_integration.is_configured(config=cfg) is False

    # ------------------------------------------------------------------
    # _resolve_config: falls back to active config when None
    # ------------------------------------------------------------------

    def test_resolve_config_uses_active_when_none_given(self):
        from integrations import email_integration
        cfg = self._cfg()
        mock_sm = self._mock_sm_multi([cfg], active_name="Work")
        with patch("integrations.email_integration._get_settings_manager", return_value=mock_sm):
            server = email_integration._get_smtp_server(config=None)
        assert server == "smtp.work.com"

    def test_resolve_config_explicit_overrides_active(self):
        from integrations import email_integration
        active_cfg = self._cfg(server="smtp.active.com")
        override_cfg = self._cfg(server="smtp.override.com")
        mock_sm = self._mock_sm_multi([active_cfg], active_name="Work")
        with patch("integrations.email_integration._get_settings_manager", return_value=mock_sm):
            server = email_integration._get_smtp_server(config=override_cfg)
        assert server == "smtp.override.com"

    # ------------------------------------------------------------------
    # send_email with explicit config
    # ------------------------------------------------------------------

    def test_send_email_uses_explicit_config(self):
        from integrations import email_integration
        cfg = self._cfg()
        mock_smtp = MagicMock()
        mock_smtp.ehlo.return_value = (250, b"OK")
        mock_smtp.has_extn.return_value = True
        with patch("integrations.email_integration._get_credentials", return_value=("u", "p")), \
             patch("smtplib.SMTP", return_value=mock_smtp):
            success, error = email_integration.send_email(
                to="to@example.com", subject="S", body="B", config=cfg
            )
        assert success is True
        assert error == ""

    def test_send_email_fails_when_explicit_config_incomplete(self):
        from integrations import email_integration
        cfg = self._cfg(server="")  # missing server
        success, error = email_integration.send_email(
            to="to@example.com", subject="S", body="B", config=cfg
        )
        assert success is False
        assert "not fully configured" in error

    # ------------------------------------------------------------------
    # test_connection with explicit config
    # ------------------------------------------------------------------

    def test_test_connection_uses_explicit_config(self):
        from integrations import email_integration
        cfg = self._cfg()
        mock_smtp = MagicMock()
        mock_smtp.ehlo.return_value = (250, b"OK")
        mock_smtp.has_extn.return_value = False
        with patch("integrations.email_integration._get_credentials", return_value=("u", "p")), \
             patch("smtplib.SMTP", return_value=mock_smtp):
            success, error = email_integration.test_connection(config=cfg)
        assert success is True
        assert error == ""

    def test_test_connection_fails_when_explicit_config_incomplete(self):
        from integrations import email_integration
        cfg = self._cfg(entry="")  # missing KeePass entry in config and no global fallback
        mock_sm = MagicMock()
        mock_sm.get_email_keepass_entry.return_value = ""  # global fallback also empty
        with patch("integrations.email_integration._get_settings_manager", return_value=mock_sm):
            success, error = email_integration.test_connection(config=cfg)
        assert success is False
        assert "not fully configured" in error

    # ------------------------------------------------------------------
    # get_config_summary multi-config fields
    # ------------------------------------------------------------------

    def test_get_config_summary_includes_multi_config_keys(self):
        from integrations import email_integration
        configs = [self._cfg("Work"), self._cfg("Personal", server="smtp.personal.com", sender="me@personal.com")]
        mock_sm = self._mock_sm_multi(configs, active_name="Work")
        with patch("integrations.email_integration._get_settings_manager", return_value=mock_sm):
            summary = email_integration.get_config_summary()
        assert "num_configs" in summary
        assert summary["num_configs"] == 2
        assert "active_config_name" in summary
        assert "configs" in summary
        assert len(summary["configs"]) == 2

    def test_get_config_summary_configs_have_no_keepass_entry_names(self):
        from integrations import email_integration
        configs = [self._cfg()]
        mock_sm = self._mock_sm_multi(configs, active_name="Work")
        with patch("integrations.email_integration._get_settings_manager", return_value=mock_sm):
            summary = email_integration.get_config_summary()
        for cfg_summary in summary["configs"]:
            assert "keepass_entry" not in cfg_summary
            assert "keepass_entry_set" in cfg_summary

    def test_get_config_summary_empty_when_no_configs(self):
        from integrations import email_integration
        mock_sm = self._mock_sm_multi([], active_name="")
        with patch("integrations.email_integration._get_settings_manager", return_value=mock_sm):
            summary = email_integration.get_config_summary()
        assert summary["num_configs"] == 0
        assert summary["configs"] == []

    # ------------------------------------------------------------------
    # Legacy fallback: no active config → use legacy SM keys
    # ------------------------------------------------------------------

    def test_get_smtp_server_falls_back_to_legacy_key_when_no_active_config(self):
        from integrations import email_integration
        mock_sm = MagicMock()
        mock_sm.get_active_email_config.return_value = None
        mock_sm.get_email_smtp_server.return_value = "legacy.server.com"
        with patch("integrations.email_integration._get_settings_manager", return_value=mock_sm):
            server = email_integration._get_smtp_server(config=None)
        assert server == "legacy.server.com"

    # ------------------------------------------------------------------
    # _get_keepass_entry: per-config entry vs global fallback
    # ------------------------------------------------------------------

    def test_get_keepass_entry_uses_per_config_entry_when_present(self):
        """When the config dict has a non-empty keepass_entry, it is used directly."""
        from integrations.email_integration import _get_keepass_entry
        cfg = self._cfg(entry="PerAccount/Entry")
        mock_sm = MagicMock()
        mock_sm.get_email_keepass_entry.return_value = "Global/Entry"
        with patch("integrations.email_integration._get_settings_manager", return_value=mock_sm):
            result = _get_keepass_entry(config=cfg)
        assert result == "PerAccount/Entry"
        mock_sm.get_email_keepass_entry.assert_not_called()

    def test_get_keepass_entry_falls_back_to_global_when_config_entry_empty(self):
        """When the config dict has an empty keepass_entry, the global setting is used."""
        from integrations.email_integration import _get_keepass_entry
        cfg = self._cfg(entry="")
        mock_sm = MagicMock()
        mock_sm.get_email_keepass_entry.return_value = "Global/Entry"
        with patch("integrations.email_integration._get_settings_manager", return_value=mock_sm):
            result = _get_keepass_entry(config=cfg)
        assert result == "Global/Entry"
        mock_sm.get_email_keepass_entry.assert_called_once()

    def test_get_keepass_entry_falls_back_to_global_when_config_has_no_entry_key(self):
        """When the config dict has no keepass_entry key at all, global setting is used."""
        from integrations.email_integration import _get_keepass_entry
        cfg = {"name": "Work", "smtp_server": "smtp.work.com", "smtp_port": 587,
               "smtp_use_tls": True, "sender_address": "me@work.com"}
        mock_sm = MagicMock()
        mock_sm.get_email_keepass_entry.return_value = "Global/Entry"
        with patch("integrations.email_integration._get_settings_manager", return_value=mock_sm):
            result = _get_keepass_entry(config=cfg)
        assert result == "Global/Entry"

    def test_is_configured_true_with_config_missing_entry_but_global_set(self):
        """Config without keepass_entry is considered configured when global entry exists."""
        from integrations import email_integration
        cfg = {"name": "Work", "smtp_server": "smtp.work.com", "smtp_port": 587,
               "smtp_use_tls": True, "sender_address": "me@work.com"}
        mock_sm = MagicMock()
        mock_sm.get_email_keepass_entry.return_value = "Global/Entry"
        with patch("integrations.email_integration._get_settings_manager", return_value=mock_sm):
            result = email_integration.is_configured(config=cfg)
        assert result is True
