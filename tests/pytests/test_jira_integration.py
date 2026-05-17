"""Tests for integrations/jira_integration.py — Jira API connectivity and credential management.

All JIRA connections and KeePass interactions are mocked; no real Jira server
or KeePass database is required to run these tests.
"""

import sys
import os

import pytest
from unittest.mock import MagicMock, patch, call

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))


class TestJiraIntegration:
    """Unit tests for src/integrations/jira_integration.py.
    
    \testinit
    Mock the SettingsManager to return test credentials; mock the JIRA library
    to avoid real network calls.
    
    \testrun
    Call test_connection, get_jira_client, or get_config_summary with various
    server configurations.
    
    \testexpect
    Functions return expected success/failure states, error messages, and client
    instances as documented.
    
    \testcheck
    Assertions verify return values, JIRA constructor calls use correct auth
    methods (basic_auth vs token_auth), and credentials are properly retrieved
    from settings or KeePass.
    """

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _mock_settings_manager(self, username="testuser@example.com", 
                                credential="test_token_123", 
                                servers=None):
        """Create a mock SettingsManager with Jira settings."""
        mock_sm = MagicMock()
        mock_sm.get_jira_credentials.return_value = (username, credential)
        mock_sm.get_jira_servers.return_value = servers or []
        return mock_sm

    def _mock_jira_instance(self, auth_success=True, myself_result=None):
        """Create a mock JIRA instance."""
        mock_jira = MagicMock()
        if myself_result is None and not auth_success:
            # Explicitly return None for failed auth
            mock_jira.myself.return_value = None
        elif myself_result is None:
            # Default success case
            mock_jira.myself.return_value = {"displayName": "Test User", "emailAddress": "test@example.com"}
        else:
            # Use provided result
            mock_jira.myself.return_value = myself_result
        return mock_jira

    def _make_server_config(self, name="Test Jira", url="https://test.atlassian.net",
                           auth_mode="manual", credential_type="token",
                           username="testuser", token="test_token",
                           keepass_entry=""):
        """Create a test server configuration dict."""
        config = {
            "name": name,
            "url": url,
            "auth_mode": auth_mode,
            "credential_type": credential_type,
        }
        if auth_mode == "manual":
            config["username"] = username
            config["token"] = token
        else:
            config["keepass_entry"] = keepass_entry
        return config

    # ------------------------------------------------------------------
    # test_connection - Basic functionality
    # ------------------------------------------------------------------

    def test_connection_succeeds_with_valid_manual_credentials(self):
        """
        \testinit
        Mock SettingsManager returns valid username and token.
        Mock JIRA client succeeds authentication and returns user info.
        
        \testrun
        Call test_connection with manual mode server using API token.
        
        \testexpect
        Returns (True, "") indicating success.
        
        \testcheck
        Assert success is True and error message is empty.
        """
        from integrations import jira_integration
        server = self._make_server_config(credential_type="token")
        
        with patch("integrations.jira_integration._get_settings_manager",
                   return_value=self._mock_settings_manager()):
            with patch("jira.JIRA",
                      return_value=self._mock_jira_instance(auth_success=True)):
                success, error = jira_integration.test_connection(server)
                assert success is True
                assert error == ""

    def test_connection_fails_when_credentials_missing(self):
        """
        \testinit
        Mock SettingsManager returns empty username and credential.
        
        \testrun
        Call test_connection with manual mode server.
        
        \testexpect
        Returns (False, error_message) about missing credentials.
        
        \testcheck
        Assert success is False and error mentions credentials unavailable.
        """
        from integrations import jira_integration
        server = self._make_server_config(credential_type="token")
        
        with patch("integrations.jira_integration._get_settings_manager",
                   return_value=self._mock_settings_manager(username="", credential="")):
            success, error = jira_integration.test_connection(server)
            assert success is False
            assert "Credentials not available" in error

    def test_connection_fails_when_jira_raises_exception(self):
        """
        \testinit
        Mock JIRA constructor raises an exception (network error, auth failure, etc).
        
        \testrun
        Call test_connection with valid credentials.
        
        \testexpect
        Returns (False, error_message) with exception details.
        
        \testcheck
        Assert success is False and error contains exception message.
        """
        from integrations import jira_integration
        server = self._make_server_config(credential_type="token")
        
        with patch("integrations.jira_integration._get_settings_manager",
                   return_value=self._mock_settings_manager()):
            with patch("jira.JIRA",
                      side_effect=Exception("Connection refused")):
                success, error = jira_integration.test_connection(server)
                assert success is False
                assert "Connection refused" in error

    def test_connection_fails_when_myself_returns_none(self):
        """
        \testinit
        Mock JIRA client succeeds but myself() returns None.
        
        \testrun
        Call test_connection.
        
        \testexpect
        Returns (False, error_message) about unable to retrieve user info.
        
        \testcheck
        Assert success is False and error mentions user info retrieval.
        """
        from integrations import jira_integration
        server = self._make_server_config(credential_type="token")
        
        with patch("integrations.jira_integration._get_settings_manager",
                   return_value=self._mock_settings_manager()):
            # Create a mock that explicitly returns None for myself()
            mock_jira = MagicMock()
            mock_jira.myself.return_value = None
            with patch("jira.JIRA",
                      return_value=mock_jira):
                success, error = jira_integration.test_connection(server)
                assert success is False
                assert "could not retrieve user info" in error

    # ------------------------------------------------------------------
    # test_connection - Personal Access Token (PAT) mode
    # ------------------------------------------------------------------

    def test_connection_uses_token_auth_for_pat_mode(self):
        """
        \testinit
        Server configuration with credential_type='pat'.
        Mock SettingsManager returns PAT in credential field.
        
        \testrun
        Call test_connection.
        
        \testexpect
        JIRA constructor is called with token_auth parameter (not basic_auth).
        
        \testcheck
        Assert JIRA was called with token_auth=credential.
        """
        from integrations import jira_integration
        server = self._make_server_config(credential_type="pat")
        
        with patch("integrations.jira_integration._get_settings_manager",
                   return_value=self._mock_settings_manager(credential="pat_token_xyz")):
            with patch("jira.JIRA",
                      return_value=self._mock_jira_instance()) as mock_jira_class:
                success, error = jira_integration.test_connection(server)
                assert success is True
                # Verify token_auth was used
                mock_jira_class.assert_called_once()
                call_kwargs = mock_jira_class.call_args[1]
                assert "token_auth" in call_kwargs
                assert call_kwargs["token_auth"] == "pat_token_xyz"
                assert "basic_auth" not in call_kwargs

    def test_connection_uses_basic_auth_for_token_mode(self):
        """
        \testinit
        Server configuration with credential_type='token'.
        Mock SettingsManager returns username and token.
        
        \testrun
        Call test_connection.
        
        \testexpect
        JIRA constructor is called with basic_auth parameter (username, token).
        
        \testcheck
        Assert JIRA was called with basic_auth=(username, credential).
        """
        from integrations import jira_integration
        server = self._make_server_config(credential_type="token")
        
        with patch("integrations.jira_integration._get_settings_manager",
                   return_value=self._mock_settings_manager(username="testuser", credential="api_token")):
            with patch("jira.JIRA",
                      return_value=self._mock_jira_instance()) as mock_jira_class:
                success, error = jira_integration.test_connection(server)
                assert success is True
                # Verify basic_auth was used
                mock_jira_class.assert_called_once()
                call_kwargs = mock_jira_class.call_args[1]
                assert "basic_auth" in call_kwargs
                assert call_kwargs["basic_auth"] == ("testuser", "api_token")
                assert "token_auth" not in call_kwargs

    def test_connection_pat_mode_does_not_require_username(self):
        """
        \testinit
        Server with credential_type='pat', username is empty but PAT is provided.
        
        \testrun
        Call test_connection.
        
        \testexpect
        Connection succeeds (username not required for PAT).
        
        \testcheck
        Assert success is True even with empty username.
        """
        from integrations import jira_integration
        server = self._make_server_config(credential_type="pat")
        
        with patch("integrations.jira_integration._get_settings_manager",
                   return_value=self._mock_settings_manager(username="", credential="pat_token")):
            with patch("jira.JIRA",
                      return_value=self._mock_jira_instance()):
                success, error = jira_integration.test_connection(server)
                assert success is True

    def test_connection_pat_mode_fails_when_token_missing(self):
        """
        \testinit
        Server with credential_type='pat' but credential is empty.
        
        \testrun
        Call test_connection.
        
        \testexpect
        Returns (False, error) about missing PAT.
        
        \testcheck
        Assert success is False and error mentions Personal Access Token.
        """
        from integrations import jira_integration
        server = self._make_server_config(credential_type="pat")
        
        with patch("integrations.jira_integration._get_settings_manager",
                   return_value=self._mock_settings_manager(credential="")):
            success, error = jira_integration.test_connection(server)
            assert success is False
            assert "Personal Access Token not available" in error

    # ------------------------------------------------------------------
    # test_connection - Password mode
    # ------------------------------------------------------------------

    def test_connection_uses_basic_auth_for_password_mode(self):
        """
        \testinit
        Server configuration with credential_type='password'.
        
        \testrun
        Call test_connection.
        
        \testexpect
        JIRA constructor is called with basic_auth=(username, password).
        
        \testcheck
        Assert JIRA was called with basic_auth.
        """
        from integrations import jira_integration
        server = self._make_server_config(credential_type="password")
        
        with patch("integrations.jira_integration._get_settings_manager",
                   return_value=self._mock_settings_manager(username="user", credential="pass123")):
            with patch("jira.JIRA",
                      return_value=self._mock_jira_instance()) as mock_jira_class:
                success, error = jira_integration.test_connection(server)
                assert success is True
                call_kwargs = mock_jira_class.call_args[1]
                assert "basic_auth" in call_kwargs
                assert call_kwargs["basic_auth"] == ("user", "pass123")

    # ------------------------------------------------------------------
    # test_connection - KeePass mode
    # ------------------------------------------------------------------

    def test_connection_works_with_keepass_mode(self):
        """
        \testinit
        Server with auth_mode='keepass' and keepass_entry specified.
        Mock SettingsManager retrieves credentials from KeePass entry.
        
        \testrun
        Call test_connection.
        
        \testexpect
        Connection succeeds using credentials from KeePass.
        
        \testcheck
        Assert success is True.
        """
        from integrations import jira_integration
        server = self._make_server_config(auth_mode="keepass", 
                                         credential_type="token",
                                         keepass_entry="Jira/MyEntry")
        
        with patch("integrations.jira_integration._get_settings_manager",
                   return_value=self._mock_settings_manager()):
            with patch("jira.JIRA",
                      return_value=self._mock_jira_instance()):
                success, error = jira_integration.test_connection(server)
                assert success is True

    # ------------------------------------------------------------------
    # get_jira_client - Basic functionality
    # ------------------------------------------------------------------

    def test_get_jira_client_returns_client_instance(self):
        """
        \testinit
        Mock SettingsManager and JIRA constructor.
        
        \testrun
        Call get_jira_client with valid server config.
        
        \testexpect
        Returns (client, "") where client is JIRA instance.
        
        \testcheck
        Assert client is not None and error is empty string.
        """
        from integrations import jira_integration
        server = self._make_server_config()
        
        with patch("integrations.jira_integration._get_settings_manager",
                   return_value=self._mock_settings_manager()):
            with patch("jira.JIRA",
                      return_value=self._mock_jira_instance()) as mock_jira_class:
                client, error = jira_integration.get_jira_client(server)
                assert client is not None
                assert error == ""
                mock_jira_class.assert_called_once()

    def test_get_jira_client_returns_none_when_credentials_missing(self):
        """
        \testinit
        Mock SettingsManager returns empty credentials.
        
        \testrun
        Call get_jira_client.
        
        \testexpect
        Returns (None, error_message).
        
        \testcheck
        Assert client is None and error mentions credentials.
        """
        from integrations import jira_integration
        server = self._make_server_config()
        
        with patch("integrations.jira_integration._get_settings_manager",
                   return_value=self._mock_settings_manager(username="", credential="")):
            client, error = jira_integration.get_jira_client(server)
            assert client is None
            assert "Credentials not available" in error

    def test_get_jira_client_returns_none_on_exception(self):
        """
        \testinit
        Mock JIRA constructor raises exception.
        
        \testrun
        Call get_jira_client.
        
        \testexpect
        Returns (None, error_message) with exception details.
        
        \testcheck
        Assert client is None and error contains exception message.
        """
        from integrations import jira_integration
        server = self._make_server_config()
        
        with patch("integrations.jira_integration._get_settings_manager",
                   return_value=self._mock_settings_manager()):
            with patch("jira.JIRA",
                      side_effect=Exception("Network error")):
                client, error = jira_integration.get_jira_client(server)
                assert client is None
                assert "Network error" in error

    def test_get_jira_client_uses_token_auth_for_pat(self):
        """
        \testinit
        Server with credential_type='pat'.
        
        \testrun
        Call get_jira_client.
        
        \testexpect
        JIRA is instantiated with token_auth parameter.
        
        \testcheck
        Assert token_auth was used in JIRA constructor call.
        """
        from integrations import jira_integration
        server = self._make_server_config(credential_type="pat")
        
        with patch("integrations.jira_integration._get_settings_manager",
                   return_value=self._mock_settings_manager(credential="pat_xyz")):
            with patch("jira.JIRA",
                      return_value=self._mock_jira_instance()) as mock_jira_class:
                client, error = jira_integration.get_jira_client(server)
                assert client is not None
                call_kwargs = mock_jira_class.call_args[1]
                assert "token_auth" in call_kwargs
                assert call_kwargs["token_auth"] == "pat_xyz"

    def test_get_jira_client_uses_basic_auth_for_token(self):
        """
        \testinit
        Server with credential_type='token'.
        
        \testrun
        Call get_jira_client.
        
        \testexpect
        JIRA is instantiated with basic_auth parameter.
        
        \testcheck
        Assert basic_auth was used in JIRA constructor call.
        """
        from integrations import jira_integration
        server = self._make_server_config(credential_type="token")
        
        with patch("integrations.jira_integration._get_settings_manager",
                   return_value=self._mock_settings_manager(username="user", credential="token")):
            with patch("jira.JIRA",
                      return_value=self._mock_jira_instance()) as mock_jira_class:
                client, error = jira_integration.get_jira_client(server)
                assert client is not None
                call_kwargs = mock_jira_class.call_args[1]
                assert "basic_auth" in call_kwargs
                assert call_kwargs["basic_auth"] == ("user", "token")

    # ------------------------------------------------------------------
    # get_config_summary - Debug dump
    # ------------------------------------------------------------------

    def test_get_config_summary_returns_server_list(self):
        """
        \testinit
        Mock SettingsManager with two configured Jira servers.
        
        \testrun
        Call get_config_summary.
        
        \testexpect
        Returns dict with 'servers' list containing non-sensitive server info.
        
        \testcheck
        Assert servers list has correct count and contains name/url/auth_mode.
        """
        from integrations import jira_integration
        servers = [
            self._make_server_config(name="Jira 1", url="https://jira1.com"),
            self._make_server_config(name="Jira 2", url="https://jira2.com", auth_mode="keepass"),
        ]
        
        with patch("integrations.jira_integration._get_settings_manager",
                   return_value=self._mock_settings_manager(servers=servers)):
            summary = jira_integration.get_config_summary()
            assert "servers" in summary
            assert len(summary["servers"]) == 2
            assert summary["servers"][0]["name"] == "Jira 1"
            assert summary["servers"][0]["url"] == "https://jira1.com"
            assert summary["servers"][0]["auth_mode"] == "manual"
            assert summary["servers"][1]["auth_mode"] == "keepass"

    def test_get_config_summary_excludes_sensitive_data(self):
        """
        \testinit
        Mock SettingsManager with server containing username/token/keepass_entry.
        
        \testrun
        Call get_config_summary.
        
        \testexpect
        Summary does not include username, token, or keepass_entry fields.
        
        \testcheck
        Assert sensitive fields are not in summary output.
        """
        from integrations import jira_integration
        servers = [
            self._make_server_config(username="secret_user", token="secret_token"),
        ]
        
        with patch("integrations.jira_integration._get_settings_manager",
                   return_value=self._mock_settings_manager(servers=servers)):
            summary = jira_integration.get_config_summary()
            assert "servers" in summary
            server_info = summary["servers"][0]
            assert "username" not in server_info
            assert "token" not in server_info
            assert "keepass_entry" not in server_info

    def test_get_config_summary_includes_last_connection_test(self):
        """
        \testinit
        Call test_connection to populate _last_connection_test.
        
        \testrun
        Call get_config_summary.
        
        \testexpect
        Summary includes last_connection_test with timestamp and result.
        
        \testcheck
        Assert last_connection_test key exists with expected fields.
        """
        from integrations import jira_integration
        server = self._make_server_config()
        
        with patch("integrations.jira_integration._get_settings_manager",
                   return_value=self._mock_settings_manager()):
            with patch("jira.JIRA",
                      return_value=self._mock_jira_instance()):
                # Perform a connection test first
                jira_integration.test_connection(server)
                
                # Get summary
                summary = jira_integration.get_config_summary()
                assert "last_connection_test" in summary
                assert summary["last_connection_test"]["success"] is True
                assert "timestamp" in summary["last_connection_test"]

    def test_get_config_summary_returns_error_when_settings_manager_unavailable(self):
        """
        \testinit
        Mock _get_settings_manager to return None.
        
        \testrun
        Call get_config_summary.
        
        \testexpect
        Returns dict with 'error' key.
        
        \testcheck
        Assert error key exists and mentions SettingsManager.
        """
        from integrations import jira_integration
        
        with patch("integrations.jira_integration._get_settings_manager",
                   return_value=None):
            summary = jira_integration.get_config_summary()
            assert "error" in summary
            assert "SettingsManager not available" in summary["error"]

    # ------------------------------------------------------------------
    # Credential stripping (whitespace handling)
    # ------------------------------------------------------------------

    def test_connection_strips_whitespace_from_credentials(self):
        """
        \testinit
        Mock SettingsManager returns credentials with trailing newline/whitespace.
        This is handled by settings_manager.get_jira_credentials() which strips.
        
        \testrun
        Call test_connection.
        
        \testexpect
        Connection succeeds without "Invalid header value" error.
        
        \testcheck
        Assert success is True (whitespace was stripped by settings_manager).
        """
        from integrations import jira_integration
        server = self._make_server_config(credential_type="pat")
        
        # Note: whitespace stripping happens in settings_manager.get_jira_credentials()
        # so we mock it returning already-stripped credentials
        with patch("integrations.jira_integration._get_settings_manager",
                   return_value=self._mock_settings_manager(credential="pat_token")):
            with patch("jira.JIRA",
                      return_value=self._mock_jira_instance()):
                success, error = jira_integration.test_connection(server)
                assert success is True

    # ------------------------------------------------------------------
    # record_filter_test - Filter test tracking
    # ------------------------------------------------------------------

    def test_record_filter_test_stores_successful_test(self):
        """
        \testinit
        Import jira_integration module.
        
        \testrun
        Call record_filter_test with success parameters (no error).
        
        \testexpect
        _last_filter_test global is set with test details.
        
        \testcheck
        Assert _last_filter_test contains server_name, filter, issue_count, success=True, error="".
        """
        from integrations import jira_integration
        
        jira_integration.record_filter_test(
            server_name="Test Server",
            filter_text="project = TEST",
            issue_count=42,
            error=""
        )
        
        assert jira_integration._last_filter_test is not None
        assert jira_integration._last_filter_test["server_name"] == "Test Server"
        assert jira_integration._last_filter_test["filter"] == "project = TEST"
        assert jira_integration._last_filter_test["issue_count"] == 42
        assert jira_integration._last_filter_test["success"] is True
        assert jira_integration._last_filter_test["error"] == ""
        assert "timestamp" in jira_integration._last_filter_test

    def test_record_filter_test_stores_failed_test(self):
        """
        \testinit
        Import jira_integration module.
        
        \testrun
        Call record_filter_test with error parameter.
        
        \testexpect
        _last_filter_test global is set with error details.
        
        \testcheck
        Assert _last_filter_test contains success=False and error message.
        """
        from integrations import jira_integration
        
        jira_integration.record_filter_test(
            server_name="Test Server",
            filter_text="invalid JQL",
            issue_count=0,
            error="JQL syntax error"
        )
        
        assert jira_integration._last_filter_test is not None
        assert jira_integration._last_filter_test["server_name"] == "Test Server"
        assert jira_integration._last_filter_test["filter"] == "invalid JQL"
        assert jira_integration._last_filter_test["issue_count"] == 0
        assert jira_integration._last_filter_test["success"] is False
        assert jira_integration._last_filter_test["error"] == "JQL syntax error"

    def test_record_filter_test_overwrites_previous_test(self):
        """
        \testinit
        Import jira_integration module.
        Call record_filter_test to set initial state.
        
        \testrun
        Call record_filter_test again with different parameters.
        
        \testexpect
        _last_filter_test contains only the most recent test.
        
        \testcheck
        Assert _last_filter_test reflects second call, not first.
        """
        from integrations import jira_integration
        
        # First test
        jira_integration.record_filter_test(
            server_name="Server 1",
            filter_text="project = FIRST",
            issue_count=10,
            error=""
        )
        
        # Second test
        jira_integration.record_filter_test(
            server_name="Server 2",
            filter_text="project = SECOND",
            issue_count=20,
            error=""
        )
        
        assert jira_integration._last_filter_test["server_name"] == "Server 2"
        assert jira_integration._last_filter_test["filter"] == "project = SECOND"
        assert jira_integration._last_filter_test["issue_count"] == 20

    def test_get_config_summary_includes_last_filter_test(self):
        """
        \testinit
        Mock SettingsManager to return test servers.
        Call record_filter_test to set _last_filter_test.
        
        \testrun
        Call get_config_summary.
        
        \testexpect
        Returns dict including last_filter_test key.
        
        \testcheck
        Assert result contains "last_filter_test" with recorded data.
        """
        from integrations import jira_integration
        
        servers = [self._make_server_config(name="Test Server")]
        
        # Record a filter test
        jira_integration.record_filter_test(
            server_name="Test Server",
            filter_text="project = PROJ",
            issue_count=15,
            error=""
        )
        
        with patch("integrations.jira_integration._get_settings_manager",
                   return_value=self._mock_settings_manager(servers=servers)):
            result = jira_integration.get_config_summary()
        
        assert "last_filter_test" in result
        assert result["last_filter_test"]["server_name"] == "Test Server"
        assert result["last_filter_test"]["filter"] == "project = PROJ"
        assert result["last_filter_test"]["issue_count"] == 15
        assert result["last_filter_test"]["success"] is True

    def test_get_config_summary_excludes_filter_test_when_none(self):
        """
        \testinit
        Mock SettingsManager to return test servers.
        Set _last_filter_test to None.
        
        \testrun
        Call get_config_summary.
        
        \testexpect
        Returns dict without last_filter_test key.
        
        \testcheck
        Assert result does not contain "last_filter_test".
        """
        from integrations import jira_integration
        
        servers = [self._make_server_config(name="Test Server")]
        jira_integration._last_filter_test = None
        
        with patch("integrations.jira_integration._get_settings_manager",
                   return_value=self._mock_settings_manager(servers=servers)):
            result = jira_integration.get_config_summary()
        
        assert "last_filter_test" not in result

    # ------------------------------------------------------------------
    # _extract_filter_id - URL / ID parsing
    # ------------------------------------------------------------------

    def test_extract_filter_id_from_full_url(self):
        """
        \testinit
        Import jira_integration.

        \testrun
        Call _extract_filter_id with a full Jira filter URL.

        \testexpect
        Returns the numeric filter ID string.

        \testcheck
        Assert returned value equals the ID portion of the URL.
        """
        from integrations import jira_integration
        result = jira_integration._extract_filter_id(
            "https://jira.example.com/issues/?filter=66111"
        )
        assert result == "66111"

    def test_extract_filter_id_from_url_with_other_params(self):
        """
        \testinit
        Import jira_integration.

        \testrun
        Call _extract_filter_id with URL containing multiple query parameters.

        \testexpect
        Returns the numeric filter ID extracted from the filter= param.

        \testcheck
        Assert returned value equals the filter ID.
        """
        from integrations import jira_integration
        result = jira_integration._extract_filter_id(
            "https://jira.example.com/issues/?startAt=0&filter=12345&foo=bar"
        )
        assert result == "12345"

    def test_extract_filter_id_from_plain_number(self):
        """
        \testinit
        Import jira_integration.

        \testrun
        Call _extract_filter_id with a plain numeric string.

        \testexpect
        Returns the same numeric string.

        \testcheck
        Assert returned value equals the input.
        """
        from integrations import jira_integration
        result = jira_integration._extract_filter_id("66111")
        assert result == "66111"

    def test_extract_filter_id_returns_empty_for_invalid_input(self):
        """
        \testinit
        Import jira_integration.

        \testrun
        Call _extract_filter_id with a non-numeric, non-URL string.

        \testexpect
        Returns empty string.

        \testcheck
        Assert returned value is "".
        """
        from integrations import jira_integration
        result = jira_integration._extract_filter_id("project = MYPROJECT")
        assert result == ""

    def test_extract_filter_id_strips_whitespace(self):
        """
        \testinit
        Import jira_integration.

        \testrun
        Call _extract_filter_id with whitespace around a numeric ID.

        \testexpect
        Returns the numeric ID without surrounding whitespace.

        \testcheck
        Assert returned value equals the trimmed number.
        """
        from integrations import jira_integration
        result = jira_integration._extract_filter_id("  66111  ")
        assert result == "66111"

    # ------------------------------------------------------------------
    # resolve_filter_to_jql
    # ------------------------------------------------------------------

    def test_resolve_filter_to_jql_passes_through_jql_unchanged(self):
        """
        \testinit
        Create a mock JIRA client (not called).

        \testrun
        Call resolve_filter_to_jql with filter_type="jql".

        \testexpect
        Returns the raw JQL string unchanged without calling the Jira API.

        \testcheck
        Assert returned jql equals the input value and error is empty.
        """
        from integrations import jira_integration
        mock_jira = MagicMock()
        jql = "project = MYPROJECT AND status = 'In Progress'"
        result_jql, error = jira_integration.resolve_filter_to_jql(mock_jira, jql, "jql")
        assert result_jql == jql
        assert error == ""
        mock_jira.filter.assert_not_called()

    def test_resolve_filter_to_jql_resolves_filter_id(self):
        """
        \testinit
        Create a mock JIRA client whose filter() returns a saved filter with JQL.

        \testrun
        Call resolve_filter_to_jql with filter_type="filter" and a numeric ID.

        \testexpect
        Returns the JQL retrieved from the saved filter.

        \testcheck
        Assert returned jql equals the saved filter's JQL and error is empty.
        """
        from integrations import jira_integration
        mock_jira = MagicMock()
        mock_filter = MagicMock()
        mock_filter.jql = "project = SAVED AND status IN ('Open')"
        mock_jira.filter.return_value = mock_filter

        result_jql, error = jira_integration.resolve_filter_to_jql(mock_jira, "66111", "filter")
        assert result_jql == "project = SAVED AND status IN ('Open')"
        assert error == ""
        mock_jira.filter.assert_called_once_with("66111")

    def test_resolve_filter_to_jql_resolves_filter_url(self):
        """
        \testinit
        Create a mock JIRA client whose filter() returns a saved filter with JQL.

        \testrun
        Call resolve_filter_to_jql with filter_type="filter" and a full filter URL.

        \testexpect
        Extracts the filter ID from the URL and returns the JQL.

        \testcheck
        Assert jira.filter was called with the extracted ID and jql is correct.
        """
        from integrations import jira_integration
        mock_jira = MagicMock()
        mock_filter = MagicMock()
        mock_filter.jql = "project = URL_FILTER"
        mock_jira.filter.return_value = mock_filter

        url = "https://jira.example.com/issues/?filter=66111"
        result_jql, error = jira_integration.resolve_filter_to_jql(mock_jira, url, "filter")
        assert result_jql == "project = URL_FILTER"
        assert error == ""
        mock_jira.filter.assert_called_once_with("66111")

    def test_resolve_filter_to_jql_returns_error_for_unresolvable_filter(self):
        """
        \testinit
        Import jira_integration.

        \testrun
        Call resolve_filter_to_jql with filter_type="filter" and a non-numeric value.

        \testexpect
        Returns ("", error_message) without calling the Jira API.

        \testcheck
        Assert returned jql is "" and error is non-empty.
        """
        from integrations import jira_integration
        mock_jira = MagicMock()
        result_jql, error = jira_integration.resolve_filter_to_jql(
            mock_jira, "not-a-filter-id", "filter"
        )
        assert result_jql == ""
        assert error != ""
        mock_jira.filter.assert_not_called()

    def test_resolve_filter_to_jql_returns_error_when_jira_raises(self):
        """
        \testinit
        Create a mock JIRA client whose filter() raises an exception.

        \testrun
        Call resolve_filter_to_jql with a valid filter ID.

        \testexpect
        Returns ("", error_message) containing the exception details.

        \testcheck
        Assert returned jql is "" and error contains exception message.
        """
        from integrations import jira_integration
        mock_jira = MagicMock()
        mock_jira.filter.side_effect = Exception("403 Forbidden")

        result_jql, error = jira_integration.resolve_filter_to_jql(mock_jira, "66111", "filter")
        assert result_jql == ""
        assert "403 Forbidden" in error

    def test_resolve_filter_to_jql_returns_error_when_jql_is_empty(self):
        """
        \testinit
        Create a mock JIRA client whose filter() returns a filter object with no jql attribute.

        \testrun
        Call resolve_filter_to_jql with a valid filter ID.

        \testexpect
        Returns ("", error_message) indicating no JQL was found.

        \testcheck
        Assert returned jql is "" and error is non-empty.
        """
        from integrations import jira_integration
        mock_jira = MagicMock()
        mock_filter = MagicMock()
        mock_filter.jql = None
        mock_jira.filter.return_value = mock_filter

        result_jql, error = jira_integration.resolve_filter_to_jql(mock_jira, "66111", "filter")
        assert result_jql == ""
        assert error != ""
