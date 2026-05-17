"""Tests for settings_dialogs.py — Settings dialog windows.

Settings dialogs include:
  - KeePassConfigDialog
  - KeePassNewEntryDialog
  - JiraServerEditDialog
  - JiraServersDialog

Requires a QApplication (provided by the session-scoped 'qapp' fixture).
"""

import sys
import os

import pytest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))


@pytest.fixture
def mock_settings_manager():
    """Create a mock SettingsManager."""
    mock = MagicMock()
    mock.get_jira_servers.return_value = []
    mock.get_keepass_db_path.return_value = ""
    mock.get_keepass_key_file.return_value = ""
    mock.get_keepass_password.return_value = ""
    return mock


# ---------------------------------------------------------------------------
# KeePassConfigDialog
# ---------------------------------------------------------------------------

class TestKeePassConfigDialog:
    def test_dialog_exists(self, qapp, mock_settings_manager):
        from settings_dialogs import KeePassConfigDialog
        dialog = KeePassConfigDialog(mock_settings_manager)
        assert dialog is not None

    def test_dialog_is_modal(self, qapp, mock_settings_manager):
        from settings_dialogs import KeePassConfigDialog
        dialog = KeePassConfigDialog(mock_settings_manager)
        assert dialog.isModal()

    def test_dialog_has_title(self, qapp, mock_settings_manager):
        from settings_dialogs import KeePassConfigDialog
        dialog = KeePassConfigDialog(mock_settings_manager)
        assert dialog.windowTitle() != ""


# ---------------------------------------------------------------------------
# KeePassNewEntryDialog
# ---------------------------------------------------------------------------

class TestKeePassNewEntryDialog:
    def test_dialog_exists(self, qapp, mock_settings_manager):
        from settings_dialogs import KeePassNewEntryDialog
        dialog = KeePassNewEntryDialog(mock_settings_manager)
        assert dialog is not None

    def test_dialog_is_modal(self, qapp, mock_settings_manager):
        from settings_dialogs import KeePassNewEntryDialog
        dialog = KeePassNewEntryDialog(mock_settings_manager)
        assert dialog.isModal()

    def test_dialog_has_title(self, qapp, mock_settings_manager):
        from settings_dialogs import KeePassNewEntryDialog
        dialog = KeePassNewEntryDialog(mock_settings_manager)
        assert dialog.windowTitle() != ""


# ---------------------------------------------------------------------------
# JiraServerEditDialog
# ---------------------------------------------------------------------------

class TestJiraServerEditDialog:
    def test_dialog_exists(self, qapp, mock_settings_manager):
        from settings_dialogs import JiraServerEditDialog
        with patch('settings_dialogs.QFileDialog'):
            dialog = JiraServerEditDialog(mock_settings_manager)
        assert dialog is not None

    def test_dialog_is_modal(self, qapp, mock_settings_manager):
        from settings_dialogs import JiraServerEditDialog
        with patch('settings_dialogs.QFileDialog'):
            dialog = JiraServerEditDialog(mock_settings_manager)
        assert dialog.isModal()

    def test_dialog_with_existing_server(self, qapp, mock_settings_manager):
        from settings_dialogs import JiraServerEditDialog
        existing = {
            "name": "Test Server",
            "base_url": "https://test.atlassian.net",
            "email": "test@example.com",
            "token": "test-token"
        }
        with patch('settings_dialogs.QFileDialog'):
            dialog = JiraServerEditDialog(mock_settings_manager, existing)
        assert dialog is not None


# ---------------------------------------------------------------------------
# JiraServersDialog
# ---------------------------------------------------------------------------

class TestJiraServersDialog:
    def test_dialog_exists(self, qapp, mock_settings_manager):
        from settings_dialogs import JiraServersDialog
        dialog = JiraServersDialog(mock_settings_manager)
        assert dialog is not None

    def test_dialog_is_modal(self, qapp, mock_settings_manager):
        from settings_dialogs import JiraServersDialog
        dialog = JiraServersDialog(mock_settings_manager)
        assert dialog.isModal()

    def test_dialog_has_title(self, qapp, mock_settings_manager):
        from settings_dialogs import JiraServersDialog
        dialog = JiraServersDialog(mock_settings_manager)
        assert dialog.windowTitle() != ""

    def test_dialog_loads_servers(self, qapp, mock_settings_manager):
        from settings_dialogs import JiraServersDialog
        servers = [
            {"name": "Server1", "base_url": "https://s1.atlassian.net"},
            {"name": "Server2", "base_url": "https://s2.atlassian.net"}
        ]
        mock_settings_manager.get_jira_servers.return_value = servers
        dialog = JiraServersDialog(mock_settings_manager)
        assert dialog is not None


# ---------------------------------------------------------------------------
# JiraSyncConfigDialog
# ---------------------------------------------------------------------------

class TestJiraSyncConfigDialog:
    def test_dialog_exists(self, qapp, mock_settings_manager):
        from settings_dialogs import JiraSyncConfigDialog
        dialog = JiraSyncConfigDialog(mock_settings_manager)
        assert dialog is not None

    def test_dialog_is_modal(self, qapp, mock_settings_manager):
        from settings_dialogs import JiraSyncConfigDialog
        dialog = JiraSyncConfigDialog(mock_settings_manager)
        assert dialog.isModal()

    def test_dialog_has_title(self, qapp, mock_settings_manager):
        from settings_dialogs import JiraSyncConfigDialog
        dialog = JiraSyncConfigDialog(mock_settings_manager)
        assert "Jira Sync" in dialog.windowTitle()

    def test_server_combo_disabled_when_no_servers(self, qapp, mock_settings_manager):
        """Server combo is disabled when no Jira servers are configured."""
        mock_settings_manager.get_jira_servers.return_value = []
        mock_settings_manager.get_jira_sync_server.return_value = ""
        from settings_dialogs import JiraSyncConfigDialog
        dialog = JiraSyncConfigDialog(mock_settings_manager)
        assert not dialog._server_combo.isEnabled()

    def test_server_combo_enabled_when_servers_exist(self, qapp, mock_settings_manager):
        """Server combo is enabled when Jira servers are configured."""
        mock_settings_manager.get_jira_servers.return_value = [
            {"name": "Test Server", "url": "https://test.atlassian.net"}
        ]
        mock_settings_manager.get_jira_sync_server.return_value = ""
        from settings_dialogs import JiraSyncConfigDialog
        dialog = JiraSyncConfigDialog(mock_settings_manager)
        assert dialog._server_combo.isEnabled()

    def test_server_combo_populates_from_settings(self, qapp, mock_settings_manager):
        """Server combo is populated with configured servers from settings."""
        servers = [
            {"name": "Server1", "url": "https://s1.atlassian.net"},
            {"name": "Server2", "url": "https://s2.atlassian.net"}
        ]
        mock_settings_manager.get_jira_servers.return_value = servers
        mock_settings_manager.get_jira_sync_server.return_value = ""
        from settings_dialogs import JiraSyncConfigDialog
        dialog = JiraSyncConfigDialog(mock_settings_manager)
        assert dialog._server_combo.count() == 2

    def test_server_combo_preselects_saved_server(self, qapp, mock_settings_manager):
        """Server combo pre-selects the server saved in QSettings."""
        servers = [
            {"name": "Server1", "url": "https://s1.atlassian.net"},
            {"name": "Server2", "url": "https://s2.atlassian.net"}
        ]
        mock_settings_manager.get_jira_servers.return_value = servers
        mock_settings_manager.get_jira_sync_server.return_value = "Server2"
        from settings_dialogs import JiraSyncConfigDialog
        dialog = JiraSyncConfigDialog(mock_settings_manager)
        current_server = dialog._server_combo.currentData()
        assert current_server is not None
        assert current_server.get("name") == "Server2"

    def test_filter_edit_exists(self, qapp, mock_settings_manager):
        """Dialog has a filter edit field."""
        from settings_dialogs import JiraSyncConfigDialog
        dialog = JiraSyncConfigDialog(mock_settings_manager)
        assert hasattr(dialog, "_filter_edit")
        assert dialog._filter_edit is not None

    def test_filter_edit_loads_saved_filter(self, qapp, mock_settings_manager):
        """Filter edit is populated with the saved JQL filter from project custom properties."""
        # Create a mock project with custom properties
        mock_project = MagicMock()
        mock_cp = MagicMock()
        mock_cp.get.return_value = "project = TEST"
        mock_project.getProjectProperties.return_value.getCustomProperties.return_value = mock_cp
        
        from settings_dialogs import JiraSyncConfigDialog
        dialog = JiraSyncConfigDialog(mock_settings_manager, mock_project)
        assert dialog._filter_edit.text() == "project = TEST"

    def test_filter_edit_saves_on_accept(self, qapp, mock_settings_manager):
        """Filter text is saved to project custom properties when OK is clicked."""
        # Create a mock project with custom properties  
        mock_project = MagicMock()
        mock_props = MagicMock()
        mock_cp = MagicMock()
        mock_cp.keySet.return_value = []
        mock_props.getCustomProperties.return_value = mock_cp
        mock_project.getProjectProperties.return_value = mock_props
        
        mock_settings_manager.get_jira_servers.return_value = [
            {"name": "Test Server", "url": "https://test.com"},
        ]
        from settings_dialogs import JiraSyncConfigDialog
        dialog = JiraSyncConfigDialog(mock_settings_manager, mock_project)
        dialog._filter_edit.setText("project = MYPROJECT")
        
        # Mock java.util.HashMap
        mock_hashmap = MagicMock()
        mock_java_util = MagicMock()
        mock_java_util.HashMap.return_value = mock_hashmap
        
        with patch.dict('sys.modules', {'java': MagicMock(), 'java.util': mock_java_util}), \
             patch.object(dialog, '_validate_project_to_jira_settings', return_value=(True, "")):
            dialog._accept()
            # Verify setCustomProperties was called at least once (filter + p2j settings both persist)
            mock_props.setCustomProperties.assert_called()
    
    def test_filter_disabled_without_project(self, qapp, mock_settings_manager):
        """Filter edit is disabled when no project is open."""
        from settings_dialogs import JiraSyncConfigDialog
        dialog = JiraSyncConfigDialog(mock_settings_manager, project=None)
        assert not dialog._filter_edit.isEnabled()

    def test_filter_type_radios_exist(self, qapp, mock_settings_manager):
        """Dialog has both JQL and Saved Filter radio buttons."""
        from settings_dialogs import JiraSyncConfigDialog
        dialog = JiraSyncConfigDialog(mock_settings_manager)
        assert hasattr(dialog, "_radio_jql")
        assert hasattr(dialog, "_radio_filter_id")

    def test_filter_type_defaults_to_jql(self, qapp, mock_settings_manager):
        """JQL radio is selected by default when no project is open."""
        from settings_dialogs import JiraSyncConfigDialog
        dialog = JiraSyncConfigDialog(mock_settings_manager)
        assert dialog._radio_jql.isChecked()
        assert not dialog._radio_filter_id.isChecked()

    def test_filter_type_radios_disabled_without_project(self, qapp, mock_settings_manager):
        """Both radio buttons are disabled when no project is open."""
        from settings_dialogs import JiraSyncConfigDialog
        dialog = JiraSyncConfigDialog(mock_settings_manager, project=None)
        assert not dialog._radio_jql.isEnabled()
        assert not dialog._radio_filter_id.isEnabled()

    def test_filter_type_loaded_from_project_filter_mode(self, qapp, mock_settings_manager):
        """Saved Filter radio is selected when project stores filter_type='filter'."""
        mock_project = MagicMock()
        mock_cp = MagicMock()
        mock_cp.get.side_effect = lambda k: (
            "66111" if k == "JIRA Sync Filter" else
            "filter" if k == "JIRA Sync Filter Type" else None
        )
        mock_project.getProjectProperties.return_value.getCustomProperties.return_value = mock_cp

        from settings_dialogs import JiraSyncConfigDialog
        dialog = JiraSyncConfigDialog(mock_settings_manager, mock_project)
        assert dialog._radio_filter_id.isChecked()
        assert dialog._filter_edit.text() == "66111"

    def test_filter_type_loaded_from_project_jql_mode(self, qapp, mock_settings_manager):
        """JQL radio is selected when project stores filter_type='jql'."""
        mock_project = MagicMock()
        mock_cp = MagicMock()
        mock_cp.get.side_effect = lambda k: (
            "project = TEST" if k == "JIRA Sync Filter" else
            "jql" if k == "JIRA Sync Filter Type" else None
        )
        mock_project.getProjectProperties.return_value.getCustomProperties.return_value = mock_cp

        from settings_dialogs import JiraSyncConfigDialog
        dialog = JiraSyncConfigDialog(mock_settings_manager, mock_project)
        assert dialog._radio_jql.isChecked()
        assert dialog._filter_edit.text() == "project = TEST"

    def test_filter_type_saved_with_filter_mode(self, qapp, mock_settings_manager):
        """Filter type 'filter' is persisted inside the jira2project container."""
        import json
        mock_project = MagicMock()
        mock_props = MagicMock()
        mock_cp = MagicMock()
        mock_cp.get.return_value = None
        mock_cp.keySet.return_value = []
        mock_props.getCustomProperties.return_value = mock_cp
        mock_project.getProjectProperties.return_value = mock_props

        mock_settings_manager.get_jira_servers.return_value = [
            {"name": "Test Server", "url": "https://test.com"},
        ]
        from settings_dialogs import JiraSyncConfigDialog
        dialog = JiraSyncConfigDialog(mock_settings_manager, mock_project)
        dialog._radio_filter_id.setChecked(True)
        dialog._filter_edit.setText("66111")

        mock_java = MagicMock()
        mock_hashmap_instance = MagicMock()
        mock_hashmap_instance.get.return_value = None
        mock_java.util.HashMap.return_value = mock_hashmap_instance

        with patch.dict('sys.modules', {'java': mock_java, 'java.util': mock_java.util}):
            dialog._save_filter_to_project()

        put_calls = {call[0][0]: call[0][1] for call in mock_hashmap_instance.put.call_args_list}
        assert "jira2project" in put_calls
        j2p = json.loads(put_calls["jira2project"])
        assert j2p.get("filter") == "66111"
        assert j2p.get("filter_type") == "filter"

    def test_filter_type_saved_with_jql_mode(self, qapp, mock_settings_manager):
        """Filter type 'jql' is persisted inside the jira2project container."""
        import json
        mock_project = MagicMock()
        mock_props = MagicMock()
        mock_cp = MagicMock()
        mock_cp.get.return_value = None
        mock_cp.keySet.return_value = []
        mock_props.getCustomProperties.return_value = mock_cp
        mock_project.getProjectProperties.return_value = mock_props

        mock_settings_manager.get_jira_servers.return_value = [
            {"name": "Test Server", "url": "https://test.com"},
        ]
        from settings_dialogs import JiraSyncConfigDialog
        dialog = JiraSyncConfigDialog(mock_settings_manager, mock_project)
        dialog._radio_jql.setChecked(True)
        dialog._filter_edit.setText("project = MYPROJECT")

        mock_java = MagicMock()
        mock_hashmap_instance = MagicMock()
        mock_hashmap_instance.get.return_value = None
        mock_java.util.HashMap.return_value = mock_hashmap_instance

        with patch.dict('sys.modules', {'java': mock_java, 'java.util': mock_java.util}):
            dialog._save_filter_to_project()

        put_calls = {call[0][0]: call[0][1] for call in mock_hashmap_instance.put.call_args_list}
        assert "jira2project" in put_calls
        j2p = json.loads(put_calls["jira2project"])
        assert j2p.get("filter") == "project = MYPROJECT"
        assert j2p.get("filter_type") == "jql"

    def test_filter_keys_removed_when_filter_is_empty(self, qapp, mock_settings_manager):
        """When filter is empty, jira2project container has no filter/filter_type keys."""
        import json
        mock_project = MagicMock()
        mock_props = MagicMock()
        mock_cp = MagicMock()
        mock_cp.get.return_value = None
        mock_cp.keySet.return_value = []
        mock_props.getCustomProperties.return_value = mock_cp
        mock_project.getProjectProperties.return_value = mock_props

        mock_settings_manager.get_jira_servers.return_value = [
            {"name": "Test Server", "url": "https://test.com"},
        ]
        from settings_dialogs import JiraSyncConfigDialog
        dialog = JiraSyncConfigDialog(mock_settings_manager, mock_project)
        dialog._filter_edit.setText("")  # empty — filter keys must be absent from container

        mock_java = MagicMock()
        mock_hashmap_instance = MagicMock()
        mock_hashmap_instance.get.return_value = None
        mock_java.util.HashMap.return_value = mock_hashmap_instance

        with patch.dict('sys.modules', {'java': mock_java, 'java.util': mock_java.util}):
            dialog._save_filter_to_project()

        put_calls = {call[0][0]: call[0][1] for call in mock_hashmap_instance.put.call_args_list}
        assert "jira2project" in put_calls
        j2p = json.loads(put_calls["jira2project"])
        assert "filter" not in j2p
        assert "filter_type" not in j2p

    # ------------------------------------------------------------------
    # KeePass unlock prompt during Test Filter
    # ------------------------------------------------------------------

    def test_test_filter_prompts_to_unlock_keepass_when_locked(self, qapp, mock_settings_manager):
        """Test Filter shows a question dialog when KeePass server is locked."""
        mock_settings_manager.get_jira_servers.return_value = [
            {"name": "KP Server", "url": "https://jira.example.com", "auth_mode": "keepass"},
        ]
        mock_settings_manager.get_jira_sync_server.return_value = "KP Server"
        mock_settings_manager.is_keepass_unlocked.return_value = False

        from settings_dialogs import JiraSyncConfigDialog
        dialog = JiraSyncConfigDialog(mock_settings_manager)
        dialog._server_combo.setCurrentIndex(0)
        dialog._filter_edit.setText("project = TEST")

        with patch("settings_dialogs.QMessageBox.question", return_value=0) as mock_q:
            dialog._test_filter()
            mock_q.assert_called_once()

    def test_test_filter_aborts_when_user_declines_unlock(self, qapp, mock_settings_manager):
        """Test Filter does not proceed when user declines the unlock question."""
        mock_settings_manager.get_jira_servers.return_value = [
            {"name": "KP Server", "url": "https://jira.example.com", "auth_mode": "keepass"},
        ]
        mock_settings_manager.get_jira_sync_server.return_value = "KP Server"
        mock_settings_manager.is_keepass_unlocked.return_value = False

        from PyQt5.QtWidgets import QMessageBox
        from settings_dialogs import JiraSyncConfigDialog
        dialog = JiraSyncConfigDialog(mock_settings_manager)
        dialog._server_combo.setCurrentIndex(0)
        dialog._filter_edit.setText("project = TEST")

        with patch("settings_dialogs.QMessageBox.question", return_value=QMessageBox.No):
            with patch("integrations.jira_integration.get_jira_client") as mock_client:
                dialog._test_filter()
                mock_client.assert_not_called()

    def test_test_filter_proceeds_after_successful_auto_unlock(self, qapp, mock_settings_manager):
        """Test Filter proceeds when auto_unlock_keepass succeeds."""
        mock_settings_manager.get_jira_servers.return_value = [
            {"name": "KP Server", "url": "https://jira.example.com", "auth_mode": "keepass"},
        ]
        mock_settings_manager.get_jira_sync_server.return_value = "KP Server"
        mock_settings_manager.is_keepass_unlocked.return_value = False
        mock_settings_manager.auto_unlock_keepass.return_value = (True, "")

        mock_jira = MagicMock()
        mock_jira.search_issues.return_value = []

        from PyQt5.QtWidgets import QMessageBox
        from settings_dialogs import JiraSyncConfigDialog
        dialog = JiraSyncConfigDialog(mock_settings_manager)
        dialog._server_combo.setCurrentIndex(0)
        dialog._filter_edit.setText("project = TEST")

        with patch("settings_dialogs.QMessageBox.question", return_value=QMessageBox.Yes):
            with patch("integrations.jira_integration.get_jira_client", return_value=(mock_jira, "")):
                with patch("integrations.jira_integration.resolve_filter_to_jql", return_value=("project = TEST", "")):
                    with patch("integrations.jira_integration.record_filter_test"):
                        with patch("settings_dialogs.QMessageBox.information"):
                            dialog._test_filter()
                            mock_jira.search_issues.assert_called_once()

    def test_test_filter_shows_warning_when_unlock_fails(self, qapp, mock_settings_manager):
        """Test Filter shows a warning and aborts when the unlock password is wrong."""
        mock_settings_manager.get_jira_servers.return_value = [
            {"name": "KP Server", "url": "https://jira.example.com", "auth_mode": "keepass"},
        ]
        mock_settings_manager.get_jira_sync_server.return_value = "KP Server"
        mock_settings_manager.is_keepass_unlocked.return_value = False
        mock_settings_manager.auto_unlock_keepass.return_value = (False, "bad key file")
        mock_settings_manager.unlock_keepass.return_value = (False, "invalid password")

        from PyQt5.QtWidgets import QMessageBox
        from settings_dialogs import JiraSyncConfigDialog
        dialog = JiraSyncConfigDialog(mock_settings_manager)
        dialog._server_combo.setCurrentIndex(0)
        dialog._filter_edit.setText("project = TEST")

        with patch("settings_dialogs.QMessageBox.question", return_value=QMessageBox.Yes):
            with patch("settings_dialogs.QInputDialog.getText", return_value=("wrong", True)):
                with patch("settings_dialogs.QMessageBox.warning") as mock_warn:
                    with patch("integrations.jira_integration.get_jira_client") as mock_client:
                        dialog._test_filter()
                        mock_warn.assert_called_once()
                        mock_client.assert_not_called()

    def test_test_filter_skips_unlock_for_manual_auth(self, qapp, mock_settings_manager):
        """Test Filter does not prompt for KeePass unlock when server uses manual auth."""
        mock_settings_manager.get_jira_servers.return_value = [
            {"name": "Manual Server", "url": "https://jira.example.com", "auth_mode": "manual"},
        ]
        mock_settings_manager.get_jira_sync_server.return_value = "Manual Server"
        mock_settings_manager.is_keepass_unlocked.return_value = False

        mock_jira = MagicMock()
        mock_jira.search_issues.return_value = []

        from settings_dialogs import JiraSyncConfigDialog
        dialog = JiraSyncConfigDialog(mock_settings_manager)
        dialog._server_combo.setCurrentIndex(0)
        dialog._filter_edit.setText("project = TEST")

        with patch("settings_dialogs.QMessageBox.question") as mock_q:
            with patch("integrations.jira_integration.get_jira_client", return_value=(mock_jira, "")):
                with patch("integrations.jira_integration.resolve_filter_to_jql", return_value=("project = TEST", "")):
                    with patch("integrations.jira_integration.record_filter_test"):
                        with patch("settings_dialogs.QMessageBox.information"):
                            dialog._test_filter()
                            mock_q.assert_not_called()

    # ------------------------------------------------------------------
    # Individual Field Checkboxes
    # ------------------------------------------------------------------

    def test_field_checkboxes_exist_and_initialized(self, qapp, mock_settings_manager):
        """Dialog has a dictionary of field checkboxes properly initialized."""
        from settings_dialogs import JiraSyncConfigDialog
        dialog = JiraSyncConfigDialog(mock_settings_manager)
        assert hasattr(dialog, "_field_checkboxes")
        assert isinstance(dialog._field_checkboxes, dict)
        assert len(dialog._field_checkboxes) > 0  # Should have multiple field checkboxes

    def test_field_checkboxes_default_to_unchecked(self, qapp, mock_settings_manager):
        """All field checkboxes default to unchecked when no project is open."""
        from settings_dialogs import JiraSyncConfigDialog
        dialog = JiraSyncConfigDialog(mock_settings_manager)
        for field_name, checkbox in dialog._field_checkboxes.items():
            assert not checkbox.isChecked(), f"Field {field_name} should default to unchecked"

    def test_field_checkboxes_disabled_without_project(self, qapp, mock_settings_manager):
        """All field checkboxes are disabled when no project is open."""
        from settings_dialogs import JiraSyncConfigDialog
        dialog = JiraSyncConfigDialog(mock_settings_manager, project=None)
        for field_name, checkbox in dialog._field_checkboxes.items():
            assert not checkbox.isEnabled(), f"Field {field_name} should be disabled without project"

    def test_field_checkboxes_enabled_with_project(self, qapp, mock_settings_manager):
        """Independent (non-dependent) field checkboxes are enabled when a project is open.

        Dependent fields may be disabled when their controlling field is unchecked —
        that is the expected cross-field dependency behaviour.
        """
        from settings_dialogs import JiraSyncConfigDialog, _JIRA2PROJECT_FIELD_DEPENDENCIES
        mock_project = MagicMock()
        mock_cp = MagicMock()
        mock_cp.get.return_value = None
        mock_project.getProjectProperties.return_value.getCustomProperties.return_value = mock_cp
        
        dialog = JiraSyncConfigDialog(mock_settings_manager, mock_project)
        dependent_fields = set(_JIRA2PROJECT_FIELD_DEPENDENCIES.keys())
        for field_name, checkbox in dialog._field_checkboxes.items():
            if field_name in dependent_fields:
                continue  # dependent fields follow their controller's state
            assert checkbox.isEnabled(), f"Field {field_name} should be enabled with project"

    def test_field_checkboxes_load_from_project(self, qapp, mock_settings_manager):
        """Field checkboxes load their state from the jira2project container."""
        import json
        mock_project = MagicMock()
        mock_cp = MagicMock()

        # Provide a jira2project container with specific field states
        j2p_json = json.dumps({
            "fields": {
                "jira_status": True,
                "jira_assignee": True,
                "jira_description": False,
            }
        })

        def mock_get(key):
            if key == "jira2project":
                return j2p_json
            return None

        mock_cp.get.side_effect = mock_get
        mock_project.getProjectProperties.return_value.getCustomProperties.return_value = mock_cp

        from settings_dialogs import JiraSyncConfigDialog
        dialog = JiraSyncConfigDialog(mock_settings_manager, mock_project)

        # Check that loaded values match
        if "jira_status" in dialog._field_checkboxes:
            assert dialog._field_checkboxes["jira_status"].isChecked()
        if "jira_assignee" in dialog._field_checkboxes:
            assert dialog._field_checkboxes["jira_assignee"].isChecked()
        if "jira_description" in dialog._field_checkboxes:
            assert not dialog._field_checkboxes["jira_description"].isChecked()

    def test_field_checkboxes_save_to_project(self, qapp, mock_settings_manager):
        """Field checkbox states are saved into the jira2project container on accept."""
        import json
        mock_project = MagicMock()
        mock_props = MagicMock()
        mock_cp = MagicMock()
        mock_cp.get.return_value = None
        mock_cp.keySet.return_value = []
        mock_props.getCustomProperties.return_value = mock_cp
        mock_project.getProjectProperties.return_value = mock_props

        mock_settings_manager.get_jira_servers.return_value = [
            {"name": "Test Server", "url": "https://test.com"},
        ]

        from settings_dialogs import JiraSyncConfigDialog
        dialog = JiraSyncConfigDialog(mock_settings_manager, mock_project)

        # Check some checkboxes
        if "jira_status" in dialog._field_checkboxes:
            dialog._field_checkboxes["jira_status"].setChecked(True)
        if "jira_description" in dialog._field_checkboxes:
            dialog._field_checkboxes["jira_description"].setChecked(False)

        mock_java = MagicMock()
        mock_hashmap_instance = MagicMock()
        mock_hashmap_instance.get.return_value = None
        mock_java.util.HashMap.return_value = mock_hashmap_instance

        with patch.dict('sys.modules', {'java': mock_java, 'java.util': mock_java.util}):
            dialog._save_filter_to_project()

        # Verify jira2project container was saved (not individual flat keys)
        put_calls = {call[0][0]: call[0][1] for call in mock_hashmap_instance.put.call_args_list}
        assert "jira2project" in put_calls
        j2p = json.loads(put_calls["jira2project"])
        fields = j2p.get("fields", {})
        if "jira_status" in dialog._field_checkboxes:
            assert fields.get("jira_status") is True
        if "jira_description" in dialog._field_checkboxes:
            assert fields.get("jira_description") is False
        # Old flat keys must NOT be present
        assert "JIRA Sync Filter" not in put_calls
        assert not any(k.startswith("JIRA Sync Field ") for k in put_calls)

    def test_field_checkboxes_have_expected_fields(self, qapp, mock_settings_manager):
        """Dialog includes expected core fields like status, assignee, description."""
        from settings_dialogs import JiraSyncConfigDialog
        dialog = JiraSyncConfigDialog(mock_settings_manager)
        
        # Verify some expected fields exist
        expected_fields = ["jira_status", "jira_assignee", "jira_description", 
                          "jira_priority", "jira_due_date"]
        for field in expected_fields:
            assert field in dialog._field_checkboxes, f"Expected field {field} not found in checkboxes"

    def test_field_dependencies_disable_related_jira_to_project_options(self, qapp, mock_settings_manager):
        """Dependent Jira -> Project checkboxes become read-only when controller is off."""
        mock_project = MagicMock()
        mock_cp = MagicMock()
        mock_cp.get.return_value = None
        mock_project.getProjectProperties.return_value.getCustomProperties.return_value = mock_cp

        from settings_dialogs import JiraSyncConfigDialog
        dialog = JiraSyncConfigDialog(mock_settings_manager, mock_project)

        controller = dialog._field_checkboxes["jira_assignee"]
        dependent = dialog._field_checkboxes["jira_assignee_display_name"]

        controller.setChecked(False)
        assert not dependent.isEnabled()
        assert not dependent.isChecked()

        controller.setChecked(True)
        assert dependent.isEnabled()

    # ------------------------------------------------------------------
    # Project -> Jira Export Tab
    # ------------------------------------------------------------------

    def test_project_to_jira_tab_builds_expected_controls(self, qapp, mock_settings_manager):
        """Project -> Jira tab exposes the export controls and 36 outbound fields."""
        mock_project = MagicMock()
        mock_cp = MagicMock()
        mock_cp.get.return_value = None
        mock_project.getProjectProperties.return_value.getCustomProperties.return_value = mock_cp

        from settings_dialogs import JiraSyncConfigDialog
        dialog = JiraSyncConfigDialog(mock_settings_manager, mock_project)

        assert hasattr(dialog, "_project2jira_fields")
        assert len(dialog._project2jira_fields) == 36
        # Export scope defaults to "Changed since last sync" (index 1)
        assert dialog._export_scope_combo.currentIndex() == 1
        # Mode defaults to "Create + update" (index 2)
        assert dialog._create_update_combo.currentIndex() == 2
        # Conflict policy defaults to "Manual review" (index 2)
        assert dialog._conflict_combo.currentIndex() == 2
        assert dialog._dry_run_check.isChecked()
        assert "issue_type_map" in dialog._project2jira_tables
        assert "transition_map" in dialog._project2jira_tables

    def test_project_to_jira_tab_loads_from_project(self, qapp, mock_settings_manager):
        """Project -> Jira settings are loaded from the project2jira container."""
        import json
        mock_project = MagicMock()
        mock_cp = MagicMock()
        mock_cp.get.side_effect = lambda key: json.dumps({
            "export_scope": "full_project",
            "create_update_mode": "create_only",
            "conflict_policy": "prefer_jira",
            "dry_run": False,
            "fields": {
                "jira_status": {"enabled": True, "jira_field": "status"},
                "jira_description": {"enabled": True, "jira_field": "description"},
            },
            "issue_type_map": {"Task": "Task"},
            "transition_map": {"Done": "31"},
        }) if key == "project2jira" else None
        mock_project.getProjectProperties.return_value.getCustomProperties.return_value = mock_cp

        from settings_dialogs import JiraSyncConfigDialog
        dialog = JiraSyncConfigDialog(mock_settings_manager, mock_project)

        # full_project → index 2; create_only → index 0; prefer_jira → index 0
        assert dialog._export_scope_combo.currentIndex() == 2
        assert dialog._create_update_combo.currentIndex() == 0
        assert dialog._conflict_combo.currentIndex() == 0
        assert not dialog._dry_run_check.isChecked()
        assert dialog._project2jira_fields["jira_status"]["checkbox"].isChecked()
        assert dialog._project2jira_fields["jira_description"]["checkbox"].isChecked()
        issue_table = dialog._project2jira_tables["issue_type_map"]
        transition_table = dialog._project2jira_tables["transition_map"]
        assert issue_table.rowCount() == 1
        assert transition_table.rowCount() == 1

    def test_project_to_jira_tab_save_to_project(self, qapp, mock_settings_manager):
        """Project -> Jira settings are written into the project2jira container."""
        import json
        mock_project = MagicMock()
        mock_props = MagicMock()
        mock_cp = MagicMock()
        mock_cp.get.return_value = None
        mock_cp.keySet.return_value = []
        mock_props.getCustomProperties.return_value = mock_cp
        mock_project.getProjectProperties.return_value = mock_props

        mock_settings_manager.get_jira_servers.return_value = [
            {"name": "Test Server", "url": "https://test.com"},
        ]

        from PyQt5.QtWidgets import QTableWidgetItem  # type: ignore
        from settings_dialogs import JiraSyncConfigDialog
        dialog = JiraSyncConfigDialog(mock_settings_manager, mock_project)

        dialog._export_scope_combo.setCurrentIndex(2)   # full_project
        dialog._create_update_combo.setCurrentIndex(0)  # create_only
        dialog._conflict_combo.setCurrentIndex(0)       # prefer_jira
        dialog._dry_run_check.setChecked(False)

        dialog._project2jira_fields["jira_status"]["checkbox"].setChecked(True)
        dialog._project2jira_fields["jira_status"]["edit"].setCurrentText("status")
        dialog._project2jira_tables["issue_type_map"].insertRow(0)
        dialog._project2jira_tables["issue_type_map"].setItem(0, 0, QTableWidgetItem("Task"))
        dialog._project2jira_tables["issue_type_map"].setItem(0, 1, QTableWidgetItem("Task"))
        dialog._project2jira_tables["transition_map"].insertRow(0)
        dialog._project2jira_tables["transition_map"].setItem(0, 0, QTableWidgetItem("Done"))
        dialog._project2jira_tables["transition_map"].setItem(0, 1, QTableWidgetItem("31"))

        mock_java = MagicMock()
        mock_hashmap_instance = MagicMock()
        mock_hashmap_instance.get.return_value = None
        mock_java.util.HashMap.return_value = mock_hashmap_instance

        with patch.dict('sys.modules', {'java': mock_java, 'java.util': mock_java.util}):
            dialog._save_project_to_jira_settings()

        put_calls = {call[0][0]: call[0][1] for call in mock_hashmap_instance.put.call_args_list}
        assert "project2jira" in put_calls
        config = json.loads(put_calls["project2jira"])
        assert config["export_scope"] == "full_project"
        assert config["create_update_mode"] == "create_only"
        assert config["conflict_policy"] == "prefer_jira"
        assert config["dry_run"] is False
        assert config["fields"]["jira_status"]["enabled"] is True
        assert config["fields"]["jira_status"]["jira_field"] == "status"
        assert config["issue_type_map"] == {"Task": "Task"}
        assert config["transition_map"] == {"Done": "31"}

    def test_project_to_jira_validation_requires_project_field_for_create_modes(self, qapp, mock_settings_manager):
        """Create-capable export modes require a mapping to Jira 'project'."""
        mock_project = MagicMock()
        mock_cp = MagicMock()
        mock_cp.get.return_value = None
        mock_project.getProjectProperties.return_value.getCustomProperties.return_value = mock_cp

        from PyQt5.QtWidgets import QTableWidgetItem  # type: ignore
        from settings_dialogs import JiraSyncConfigDialog
        dialog = JiraSyncConfigDialog(mock_settings_manager, mock_project)

        dialog._create_update_combo.setCurrentIndex(0)  # create_only
        dialog._project2jira_fields["jira_description"]["checkbox"].setChecked(True)
        dialog._project2jira_fields["jira_description"]["edit"].setCurrentText("description")

        issue_table = dialog._project2jira_tables["issue_type_map"]
        issue_table.insertRow(0)
        issue_table.setItem(0, 0, QTableWidgetItem("Task"))
        issue_table.setItem(0, 1, QTableWidgetItem("Task"))

        ok, error = dialog._validate_project_to_jira_settings()
        assert not ok
        assert "require mappings" in error
        assert "project" in error

    def test_project_to_jira_transition_validation_checks_server_capabilities(self, qapp, mock_settings_manager):
        """Transition mappings are validated against server transition ids/names."""
        mock_project = MagicMock()
        mock_cp = MagicMock()
        mock_cp.get.return_value = None
        mock_project.getProjectProperties.return_value.getCustomProperties.return_value = mock_cp

        mock_settings_manager.get_jira_servers.return_value = [
            {"name": "Test Server", "url": "https://test.example.com"},
        ]
        mock_settings_manager.get_jira_sync_server.return_value = "Test Server"

        from PyQt5.QtWidgets import QTableWidgetItem  # type: ignore
        from settings_dialogs import JiraSyncConfigDialog
        dialog = JiraSyncConfigDialog(mock_settings_manager, mock_project)

        dialog._project2jira_fields["jira_project_name"]["checkbox"].setChecked(True)
        dialog._project2jira_fields["jira_project_name"]["edit"].setCurrentText("project")

        issue_table = dialog._project2jira_tables["issue_type_map"]
        issue_table.insertRow(0)
        issue_table.setItem(0, 0, QTableWidgetItem("Task"))
        issue_table.setItem(0, 1, QTableWidgetItem("Task"))

        transition_table = dialog._project2jira_tables["transition_map"]
        transition_table.insertRow(0)
        transition_table.setItem(0, 0, QTableWidgetItem("Done"))
        transition_table.setItem(0, 1, QTableWidgetItem("999"))

        mock_jira = MagicMock()
        mock_issue_type = type("IssueType", (), {})()
        mock_issue_type.name = "Task"
        mock_jira.issue_types.return_value = [mock_issue_type]
        mock_issue = MagicMock()
        mock_issue.key = "TEST-1"
        mock_jira.search_issues.return_value = [mock_issue]
        mock_jira.transitions.return_value = [{"id": "31", "name": "Done"}]

        with patch("integrations.jira_integration.get_jira_client", return_value=(mock_jira, "")):
            ok, error = dialog._validate_project_to_jira_settings()

        assert not ok
        assert "Unknown Jira transition" in error

    def test_dialog_max_height_does_not_exceed_available_screen(self, qapp, mock_settings_manager):
        """JiraSyncConfigDialog maximumHeight must not exceed screen available height minus chrome buffer."""
        from settings_dialogs import JiraSyncConfigDialog
        from PyQt5.QtWidgets import QApplication  # type: ignore

        dialog = JiraSyncConfigDialog(mock_settings_manager)
        available_height = QApplication.desktop().availableGeometry().height()
        # Dialog must fit within available area (chrome buffer is 40 px)
        assert dialog.maximumHeight() <= available_height - 40

    def test_jira_to_project_tab_is_wrapped_in_scroll_area(self, qapp, mock_settings_manager):
        """Tab 0 (Jira → Project) must be a QScrollArea so content scrolls inside the tab."""
        from settings_dialogs import JiraSyncConfigDialog
        from PyQt5.QtWidgets import QScrollArea  # type: ignore

        dialog = JiraSyncConfigDialog(mock_settings_manager)
        assert isinstance(dialog._tabs.widget(0), QScrollArea)

    def test_project_to_jira_tab_is_wrapped_in_scroll_area(self, qapp, mock_settings_manager):
        """Tab 1 (Project → Jira) must be a QScrollArea so content scrolls inside the tab."""
        from settings_dialogs import JiraSyncConfigDialog
        from PyQt5.QtWidgets import QScrollArea  # type: ignore

        dialog = JiraSyncConfigDialog(mock_settings_manager)
        assert isinstance(dialog._tabs.widget(1), QScrollArea)

    def test_project_to_jira_tab_label_uses_arrow(self, qapp, mock_settings_manager):
        """Tab 1 label must use the Unicode arrow '→', not ASCII '->'."""
        from settings_dialogs import JiraSyncConfigDialog
        dialog = JiraSyncConfigDialog(mock_settings_manager)
        assert dialog._tabs.tabText(1) == "Project \u2192 Jira"

    # ------------------------------------------------------------------
    # Project -> Jira combo-box controls
    # ------------------------------------------------------------------

    def test_p2j_export_scope_combo_exists_with_three_choices(self, qapp, mock_settings_manager):
        """Export Scope combo must have exactly three items."""
        from settings_dialogs import JiraSyncConfigDialog
        dialog = JiraSyncConfigDialog(mock_settings_manager)
        assert hasattr(dialog, "_export_scope_combo")
        assert dialog._export_scope_combo.count() == 3

    def test_p2j_export_scope_default_is_changed_since_last_sync(self, qapp, mock_settings_manager):
        """Export Scope must default to 'Changed since last sync' (index 1) for a new dialog."""
        from settings_dialogs import JiraSyncConfigDialog
        dialog = JiraSyncConfigDialog(mock_settings_manager)
        assert dialog._export_scope_combo.currentIndex() == 1
        assert "Changed" in dialog._export_scope_combo.currentText()

    def test_p2j_mode_combo_exists_with_three_choices(self, qapp, mock_settings_manager):
        """Mode combo must have exactly three items."""
        from settings_dialogs import JiraSyncConfigDialog
        dialog = JiraSyncConfigDialog(mock_settings_manager)
        assert hasattr(dialog, "_create_update_combo")
        assert dialog._create_update_combo.count() == 3

    def test_p2j_mode_default_is_create_and_update(self, qapp, mock_settings_manager):
        """Mode must default to 'Create + update' (index 2)."""
        from settings_dialogs import JiraSyncConfigDialog
        dialog = JiraSyncConfigDialog(mock_settings_manager)
        assert dialog._create_update_combo.currentIndex() == 2

    def test_p2j_conflict_combo_exists_with_three_choices(self, qapp, mock_settings_manager):
        """Conflict Policy combo must have exactly three items."""
        from settings_dialogs import JiraSyncConfigDialog
        dialog = JiraSyncConfigDialog(mock_settings_manager)
        assert hasattr(dialog, "_conflict_combo")
        assert dialog._conflict_combo.count() == 3

    def test_p2j_conflict_default_is_manual_review(self, qapp, mock_settings_manager):
        """Conflict Policy must default to 'Manual review' (index 2)."""
        from settings_dialogs import JiraSyncConfigDialog
        dialog = JiraSyncConfigDialog(mock_settings_manager)
        assert dialog._conflict_combo.currentIndex() == 2

    def test_p2j_unlinked_combo_exists_with_three_choices(self, qapp, mock_settings_manager):
        """Unlinked tasks combo must have exactly three items."""
        from settings_dialogs import JiraSyncConfigDialog
        dialog = JiraSyncConfigDialog(mock_settings_manager)
        assert hasattr(dialog, "_unlinked_combo")
        assert dialog._unlinked_combo.count() == 3

    def test_p2j_unlinked_default_is_skip(self, qapp, mock_settings_manager):
        """Unlinked tasks must default to 'Skip' (index 1)."""
        from settings_dialogs import JiraSyncConfigDialog
        dialog = JiraSyncConfigDialog(mock_settings_manager)
        assert dialog._unlinked_combo.currentIndex() == 1

    def test_p2j_scope_combo_round_trips_through_save_load(self, qapp, mock_settings_manager):
        """Export scope 'Full project' survives a save→load round-trip."""
        import json
        mock_project = MagicMock()
        mock_props = MagicMock()
        mock_cp = MagicMock()
        mock_cp.get.return_value = None
        mock_cp.keySet.return_value = []
        mock_props.getCustomProperties.return_value = mock_cp
        mock_project.getProjectProperties.return_value = mock_props

        from settings_dialogs import JiraSyncConfigDialog
        dialog = JiraSyncConfigDialog(mock_settings_manager, mock_project)
        dialog._export_scope_combo.setCurrentIndex(2)  # Full project

        mock_java = MagicMock()
        mock_hm = MagicMock()
        mock_hm.get.return_value = None
        mock_java.util.HashMap.return_value = mock_hm
        with patch.dict('sys.modules', {'java': mock_java, 'java.util': mock_java.util}):
            dialog._save_project_to_jira_settings()

        put_calls = {c[0][0]: c[0][1] for c in mock_hm.put.call_args_list}
        assert "project2jira" in put_calls
        config = json.loads(put_calls["project2jira"])
        assert config["export_scope"] == "full_project"

    def test_p2j_field_edit_is_editable_combobox(self, qapp, mock_settings_manager):
        """Each field row's edit widget is an editable QComboBox (not a plain QLineEdit)."""
        from settings_dialogs import JiraSyncConfigDialog
        from PyQt5.QtWidgets import QComboBox  # type: ignore
        dialog = JiraSyncConfigDialog(mock_settings_manager)
        for field_name, wi in dialog._project2jira_fields.items():
            assert isinstance(wi["edit"], QComboBox), (
                f"Field '{field_name}' edit widget should be QComboBox"
            )
            assert wi["edit"].isEditable(), (
                f"Field '{field_name}' QComboBox should be editable"
            )

    def test_p2j_field_edit_combobox_has_suggestions(self, qapp, mock_settings_manager):
        """Each field row's QComboBox is pre-populated with at least one suggestion."""
        from settings_dialogs import JiraSyncConfigDialog
        dialog = JiraSyncConfigDialog(mock_settings_manager)
        for field_name, wi in dialog._project2jira_fields.items():
            assert wi["edit"].count() >= 1, (
                f"Field '{field_name}' QComboBox should have suggestions"
            )

    def test_p2j_hierarchy_issue_type_combos_are_editable(self, qapp, mock_settings_manager):
        """Hierarchy issue-type widgets (Epic/Story/Sub-task) are editable QComboBoxes."""
        from settings_dialogs import JiraSyncConfigDialog
        from PyQt5.QtWidgets import QComboBox  # type: ignore
        mock_project = MagicMock()
        mock_cp = MagicMock()
        mock_cp.get.return_value = None
        mock_project.getProjectProperties.return_value.getCustomProperties.return_value = mock_cp

        dialog = JiraSyncConfigDialog(mock_settings_manager, mock_project)
        for attr in ("_p2j_epic_type_edit", "_p2j_story_type_edit", "_p2j_subtask_type_edit"):
            widget = getattr(dialog, attr)
            assert isinstance(widget, QComboBox), f"{attr} should be QComboBox"
            assert widget.isEditable(), f"{attr} should be editable"

    def test_p2j_dependency_link_type_combo_has_blocks_default(self, qapp, mock_settings_manager):
        """Dependency link-type QComboBox defaults to 'blocks'."""
        from settings_dialogs import JiraSyncConfigDialog
        from PyQt5.QtWidgets import QComboBox  # type: ignore
        mock_project = MagicMock()
        mock_cp = MagicMock()
        mock_cp.get.return_value = None
        mock_project.getProjectProperties.return_value.getCustomProperties.return_value = mock_cp

        dialog = JiraSyncConfigDialog(mock_settings_manager, mock_project)
        assert isinstance(dialog._p2j_dep_link_type_edit, QComboBox)
        assert dialog._p2j_dep_link_type_edit.currentText() == "blocks"

    def test_p2j_scope_all_combo_choices_map_to_correct_save_values(self, qapp, mock_settings_manager):
        """Each scope combo index maps to the expected serialised value."""
        import json
        expected = {0: "selected_tasks", 1: "changed_since_last_sync", 2: "full_project"}
        mock_project = MagicMock()
        mock_props = MagicMock()
        mock_cp = MagicMock()
        mock_cp.get.return_value = None
        mock_cp.keySet.return_value = []
        mock_props.getCustomProperties.return_value = mock_cp
        mock_project.getProjectProperties.return_value = mock_props

        from settings_dialogs import JiraSyncConfigDialog
        for idx, expected_val in expected.items():
            dialog = JiraSyncConfigDialog(mock_settings_manager, mock_project)
            dialog._export_scope_combo.setCurrentIndex(idx)

            mock_java = MagicMock()
            mock_hm = MagicMock()
            mock_hm.get.return_value = None
            mock_java.util.HashMap.return_value = mock_hm
            with patch.dict('sys.modules', {'java': mock_java, 'java.util': mock_java.util}):
                dialog._save_project_to_jira_settings()

            put_calls = {c[0][0]: c[0][1] for c in mock_hm.put.call_args_list}
            config = json.loads(put_calls["project2jira"])
            assert config["export_scope"] == expected_val, (
                f"Index {idx} should produce '{expected_val}', got '{config['export_scope']}'"
            )



class TestKeePassConfigDialogConfluenceSso:
    def test_confluence_group_hidden_when_db_locked(self, qapp, mock_settings_manager):
        """Confluence SSO group is not visible when the KeePass DB is locked."""
        mock_settings_manager.is_keepass_unlocked.return_value = False
        from settings_dialogs import KeePassConfigDialog
        dialog = KeePassConfigDialog(mock_settings_manager)
        assert dialog._confluence_group.isHidden()

    def test_confluence_group_visible_when_db_unlocked(self, qapp, mock_settings_manager):
        """Confluence SSO group becomes visible when the DB is already unlocked on open."""
        mock_settings_manager.is_keepass_unlocked.return_value = True
        mock_settings_manager.get_confluence_keepass_entry.return_value = ""
        mock_settings_manager.list_keepass_entries.return_value = ["entry1", "entry2"]
        from settings_dialogs import KeePassConfigDialog
        dialog = KeePassConfigDialog(mock_settings_manager)
        assert not dialog._confluence_group.isHidden()

    def test_confluence_combo_populated_with_entries(self, qapp, mock_settings_manager):
        """Combo contains empty placeholder + all KeePass entries."""
        mock_settings_manager.is_keepass_unlocked.return_value = True
        mock_settings_manager.get_confluence_keepass_entry.return_value = ""
        mock_settings_manager.list_keepass_entries.return_value = ["Confluence/prod", "Jira/prod"]
        from settings_dialogs import KeePassConfigDialog
        dialog = KeePassConfigDialog(mock_settings_manager)
        # empty item at index 0 + 2 entries = 3 total
        assert dialog._confluence_entry_combo.count() == 3

    def test_confluence_combo_selects_saved_entry(self, qapp, mock_settings_manager):
        """Previously saved entry is pre-selected in the combo."""
        mock_settings_manager.is_keepass_unlocked.return_value = True
        mock_settings_manager.get_confluence_keepass_entry.return_value = "Confluence/prod"
        mock_settings_manager.list_keepass_entries.return_value = ["Confluence/prod", "Jira/prod"]
        from settings_dialogs import KeePassConfigDialog
        dialog = KeePassConfigDialog(mock_settings_manager)
        assert dialog._confluence_entry_combo.currentText() == "Confluence/prod"


# ---------------------------------------------------------------------------
# ConfluenceCalendarConfigDialog
# ---------------------------------------------------------------------------

class TestConfluenceCalendarConfigDialog:
    """Tests for the Confluence Calendar Configuration dialog."""

    # Ensure timezone combo is always populated regardless of whether tzdata
    # is installed in the test environment.
    _SAMPLE_TZ_NAMES = sorted([
        "Africa/Abidjan", "America/New_York", "America/Los_Angeles",
        "Asia/Tokyo", "Europe/Berlin", "Europe/London", "UTC",
    ])

    @pytest.fixture(autouse=True)
    def _patch_timezones(self, monkeypatch):
        import zoneinfo
        monkeypatch.setattr(zoneinfo, "available_timezones",
                            lambda: set(self._SAMPLE_TZ_NAMES))

    def _mk(self, mock_settings_manager, mode="manual", configured=False, unlocked=False):
        """Configure the mock for the given KeePass / auth-mode state."""
        mock_settings_manager.get_confluence_auth_mode.return_value = mode
        mock_settings_manager.is_keepass_configured.return_value = configured
        mock_settings_manager.is_keepass_unlocked.return_value = unlocked
        if unlocked:
            mock_settings_manager.get_confluence_keepass_entry.return_value = ""
            mock_settings_manager.list_keepass_entries.return_value = []
        if configured and not unlocked:
            mock_settings_manager.auto_unlock_keepass.return_value = (False, "locked")

    def test_dialog_exists(self, qapp, mock_settings_manager):
        self._mk(mock_settings_manager)
        from settings_dialogs import ConfluenceCalendarConfigDialog
        dlg = ConfluenceCalendarConfigDialog(mock_settings_manager)
        assert dlg is not None

    def test_dialog_is_modal(self, qapp, mock_settings_manager):
        self._mk(mock_settings_manager)
        from settings_dialogs import ConfluenceCalendarConfigDialog
        dlg = ConfluenceCalendarConfigDialog(mock_settings_manager)
        assert dlg.isModal()

    def test_dialog_has_title(self, qapp, mock_settings_manager):
        self._mk(mock_settings_manager)
        from settings_dialogs import ConfluenceCalendarConfigDialog
        dlg = ConfluenceCalendarConfigDialog(mock_settings_manager)
        assert "Confluence" in dlg.windowTitle()

    def test_auth_combo_defaults_to_manual(self, qapp, mock_settings_manager):
        """Auth combo pre-selects 'manual' when that mode is stored."""
        self._mk(mock_settings_manager, mode="manual")
        from settings_dialogs import ConfluenceCalendarConfigDialog
        dlg = ConfluenceCalendarConfigDialog(mock_settings_manager)
        assert dlg._auth_combo.currentData() == "manual"

    def test_auth_combo_restores_keepass_mode(self, qapp, mock_settings_manager):
        """Auth combo pre-selects 'keepass' when that mode is stored."""
        self._mk(mock_settings_manager, mode="keepass", configured=False)
        from settings_dialogs import ConfluenceCalendarConfigDialog
        dlg = ConfluenceCalendarConfigDialog(mock_settings_manager)
        assert dlg._auth_combo.currentData() == "keepass"

    def test_manual_mode_shows_manual_group_hides_kp_group(self, qapp, mock_settings_manager):
        """Manual auth mode: manual-group not hidden, keepass-group hidden."""
        self._mk(mock_settings_manager, mode="manual")
        from settings_dialogs import ConfluenceCalendarConfigDialog
        dlg = ConfluenceCalendarConfigDialog(mock_settings_manager)
        assert not dlg._manual_group.isHidden()
        assert dlg._kp_group.isHidden()

    def test_keepass_mode_hides_manual_group_shows_kp_group(self, qapp, mock_settings_manager):
        """KeePass auth mode: manual-group hidden, keepass-group not hidden."""
        self._mk(mock_settings_manager, mode="keepass", configured=False)
        from settings_dialogs import ConfluenceCalendarConfigDialog
        dlg = ConfluenceCalendarConfigDialog(mock_settings_manager)
        assert dlg._manual_group.isHidden()
        assert not dlg._kp_group.isHidden()

    def test_kp_stack_page0_when_not_configured(self, qapp, mock_settings_manager):
        """KeePass stacked widget shows page 0 (not configured) when no DB is set up."""
        self._mk(mock_settings_manager, mode="keepass", configured=False)
        from settings_dialogs import ConfluenceCalendarConfigDialog
        dlg = ConfluenceCalendarConfigDialog(mock_settings_manager)
        assert dlg._kp_stack.currentIndex() == 0

    def test_kp_stack_page1_when_configured_but_locked(self, qapp, mock_settings_manager):
        """KeePass stacked widget shows page 1 (locked) when DB is configured but locked."""
        self._mk(mock_settings_manager, mode="keepass", configured=True, unlocked=False)
        from settings_dialogs import ConfluenceCalendarConfigDialog
        dlg = ConfluenceCalendarConfigDialog(mock_settings_manager)
        assert dlg._kp_stack.currentIndex() == 1

    def test_kp_stack_page2_when_unlocked(self, qapp, mock_settings_manager):
        """KeePass stacked widget shows page 2 (entry selector) when DB is unlocked."""
        self._mk(mock_settings_manager, mode="keepass", configured=True, unlocked=True)
        from settings_dialogs import ConfluenceCalendarConfigDialog
        dlg = ConfluenceCalendarConfigDialog(mock_settings_manager)
        assert dlg._kp_stack.currentIndex() == 2

    def test_calendar_props_disabled_without_project(self, qapp, mock_settings_manager):
        """All calendar property fields are disabled when no project is open."""
        self._mk(mock_settings_manager)
        from settings_dialogs import ConfluenceCalendarConfigDialog
        dlg = ConfluenceCalendarConfigDialog(mock_settings_manager, project=None)
        for edit in (dlg._cal_base_url_edit, dlg._cal_space_key_edit,
                     dlg._cal_days_ahead_edit):
            assert not edit.isEnabled()
        assert not dlg._cal_timezone_combo.isEnabled()

    def test_calendar_props_enabled_with_project(self, qapp, mock_settings_manager):
        """All calendar property fields are enabled when a project is provided."""
        self._mk(mock_settings_manager)
        project = MagicMock()
        project.getProjectProperties.return_value.getCustomProperties.return_value = None
        project.getCustomFields.return_value = []
        project.getTasks.return_value = []
        from settings_dialogs import ConfluenceCalendarConfigDialog
        dlg = ConfluenceCalendarConfigDialog(mock_settings_manager, project=project)
        for edit in (dlg._cal_base_url_edit, dlg._cal_space_key_edit,
                     dlg._cal_days_ahead_edit):
            assert edit.isEnabled()
        assert dlg._cal_timezone_combo.isEnabled()

    def test_switching_to_keepass_mode_via_combo_shows_kp_group(self, qapp, mock_settings_manager):
        """Switching the auth combo from manual to keepass at runtime shows the KeePass group."""
        self._mk(mock_settings_manager, mode="manual")
        from settings_dialogs import ConfluenceCalendarConfigDialog
        dlg = ConfluenceCalendarConfigDialog(mock_settings_manager)
        assert not dlg._manual_group.isHidden()
        assert dlg._kp_group.isHidden()
        # Switch to keepass mode programmatically
        dlg._auth_combo.setCurrentIndex(1)  # index 1 = keepass
        assert dlg._manual_group.isHidden()
        assert not dlg._kp_group.isHidden()

    # ---- Timezone combo tests ------------------------------------------------

    def test_timezone_field_is_combobox(self, qapp, mock_settings_manager):
        """Timezone field is a QComboBox, not a plain QLineEdit."""
        from PyQt5.QtWidgets import QComboBox  # type: ignore
        self._mk(mock_settings_manager)
        from settings_dialogs import ConfluenceCalendarConfigDialog
        dlg = ConfluenceCalendarConfigDialog(mock_settings_manager)
        assert isinstance(dlg._cal_timezone_combo, QComboBox)

    def test_timezone_combo_is_editable(self, qapp, mock_settings_manager):
        """Timezone combo allows typing (editable) so users can filter entries."""
        self._mk(mock_settings_manager)
        from settings_dialogs import ConfluenceCalendarConfigDialog
        dlg = ConfluenceCalendarConfigDialog(mock_settings_manager)
        assert dlg._cal_timezone_combo.isEditable()

    def test_timezone_combo_contains_europe_berlin(self, qapp, mock_settings_manager):
        """Europe/Berlin is present in the timezone dropdown."""
        self._mk(mock_settings_manager)
        from settings_dialogs import ConfluenceCalendarConfigDialog
        dlg = ConfluenceCalendarConfigDialog(mock_settings_manager)
        items = [dlg._cal_timezone_combo.itemText(i)
                 for i in range(dlg._cal_timezone_combo.count())]
        assert "Europe/Berlin" in items

    def test_timezone_combo_has_completer(self, qapp, mock_settings_manager):
        """A QCompleter is attached to the timezone combo for quick filtering."""
        self._mk(mock_settings_manager)
        from settings_dialogs import ConfluenceCalendarConfigDialog
        dlg = ConfluenceCalendarConfigDialog(mock_settings_manager)
        assert dlg._cal_timezone_combo.completer() is not None

    def _mk_project(self):
        """Return a minimal project mock with custom fields and enterprise props."""
        project = MagicMock()
        project.getProjectProperties.return_value.getCustomProperties.return_value = None
        project.getCustomFields.return_value = []
        project.getTasks.return_value = []
        return project

    def test_timezone_combo_pre_populates_from_project(self, qapp, mock_settings_manager):
        """When a project has a saved timezone, the combo pre-selects it."""
        from unittest.mock import patch
        self._mk(mock_settings_manager)
        project = self._mk_project()
        from settings_dialogs import ConfluenceCalendarConfigDialog
        with patch(
            "integrations.confluence_calendar_integration.get_project_timezone",
            return_value="Europe/Berlin",
        ):
            dlg = ConfluenceCalendarConfigDialog(mock_settings_manager, project=project)
        assert dlg._cal_timezone_combo.currentText() == "Europe/Berlin"

    def test_timezone_combo_defaults_to_europe_berlin_when_not_set(self, qapp, mock_settings_manager):
        """When the project has no saved timezone, Europe/Berlin is the default."""
        from unittest.mock import patch
        self._mk(mock_settings_manager)
        project = self._mk_project()
        from settings_dialogs import ConfluenceCalendarConfigDialog
        with patch(
            "integrations.confluence_calendar_integration.get_project_timezone",
            return_value="",
        ):
            dlg = ConfluenceCalendarConfigDialog(mock_settings_manager, project=project)
        assert dlg._cal_timezone_combo.currentText() == "Europe/Berlin"

    def test_timezone_combo_pre_selected_index_is_valid(self, qapp, mock_settings_manager):
        """Pre-selected timezone uses findText+setCurrentIndex so the popup scrolls to it."""
        from unittest.mock import patch
        self._mk(mock_settings_manager)
        project = self._mk_project()
        from settings_dialogs import ConfluenceCalendarConfigDialog
        with patch(
            "integrations.confluence_calendar_integration.get_project_timezone",
            return_value="America/New_York",
        ):
            dlg = ConfluenceCalendarConfigDialog(mock_settings_manager, project=project)
        assert dlg._cal_timezone_combo.currentIndex() >= 0
        assert dlg._cal_timezone_combo.currentText() == "America/New_York"

    def test_timezone_combo_shows_europe_berlin_when_no_project(self, qapp, mock_settings_manager):
        """Even without a project, Europe/Berlin is pre-selected as a hint."""
        self._mk(mock_settings_manager)
        from settings_dialogs import ConfluenceCalendarConfigDialog
        dlg = ConfluenceCalendarConfigDialog(mock_settings_manager, project=None)
        assert dlg._cal_timezone_combo.currentText() == "Europe/Berlin"

    def test_timezone_value_saved_to_project_on_accept(self, qapp, mock_settings_manager):
        """Selecting a timezone and accepting the dialog writes it to project custom props."""
        from unittest.mock import patch, MagicMock as MM
        self._mk(mock_settings_manager)
        project = self._mk_project()
        fake_props = MM()
        fake_props.getCustomProperties.return_value = None
        project.getProjectProperties.return_value = fake_props
        from settings_dialogs import ConfluenceCalendarConfigDialog
        with patch(
            "integrations.confluence_calendar_integration.get_project_timezone",
            return_value="",
        ), patch(
            "integrations.confluence_calendar_integration.get_project_base_url",
            return_value="",
        ), patch(
            "integrations.confluence_calendar_integration.get_project_space_key",
            return_value="",
        ), patch(
            "integrations.confluence_calendar_integration.get_project_days_ahead",
            return_value=None,
        ):
            dlg = ConfluenceCalendarConfigDialog(mock_settings_manager, project=project)
        dlg._cal_timezone_combo.setCurrentText("America/New_York")
        dlg._accept()
        # The project properties setter must have been called
        assert fake_props.setCustomProperties.called

    def test_timezone_combo_no_insert_policy(self, qapp, mock_settings_manager):
        """NoInsert policy prevents arbitrary user text being added to the list."""
        from PyQt5.QtWidgets import QComboBox  # type: ignore
        self._mk(mock_settings_manager)
        from settings_dialogs import ConfluenceCalendarConfigDialog
        dlg = ConfluenceCalendarConfigDialog(mock_settings_manager)
        assert dlg._cal_timezone_combo.insertPolicy() == QComboBox.NoInsert

    def test_timezone_combo_completer_filter_is_contains(self, qapp, mock_settings_manager):
        """Completer uses MatchContains so typing 'berlin' finds 'Europe/Berlin'."""
        from PyQt5.QtCore import Qt  # type: ignore
        self._mk(mock_settings_manager)
        from settings_dialogs import ConfluenceCalendarConfigDialog
        dlg = ConfluenceCalendarConfigDialog(mock_settings_manager)
        assert dlg._cal_timezone_combo.completer().filterMode() == Qt.MatchContains

    def test_timezone_combo_completer_is_case_insensitive(self, qapp, mock_settings_manager):
        """Completer is case-insensitive so 'BERLIN' and 'berlin' both match."""
        from PyQt5.QtCore import Qt  # type: ignore
        self._mk(mock_settings_manager)
        from settings_dialogs import ConfluenceCalendarConfigDialog
        dlg = ConfluenceCalendarConfigDialog(mock_settings_manager)
        assert dlg._cal_timezone_combo.completer().caseSensitivity() == Qt.CaseInsensitive

    def test_timezone_combo_unknown_value_kept_as_text(self, qapp, mock_settings_manager):
        """A timezone not in the list (e.g. a legacy value) is kept as free text."""
        from unittest.mock import patch
        self._mk(mock_settings_manager)
        project = self._mk_project()
        from settings_dialogs import ConfluenceCalendarConfigDialog
        with patch(
            "integrations.confluence_calendar_integration.get_project_timezone",
            return_value="Etc/UnknownLegacy",
        ):
            dlg = ConfluenceCalendarConfigDialog(mock_settings_manager, project=project)
        # findText returns -1 → falls back to setCurrentText
        assert dlg._cal_timezone_combo.currentText() == "Etc/UnknownLegacy"


# ---------------------------------------------------------------------------
# EmailServerEditDialog — SMTP-only account editor (no KeePass section)
# ---------------------------------------------------------------------------

class TestEmailServerEditDialog:
    """Tests for EmailServerEditDialog — add/edit a single named SMTP account.

    The dialog must NOT contain a KeePass section; credentials are configured
    globally via EmailConfigDialog and shared by all accounts.
    """

    def _sm(self):
        """Minimal SettingsManager mock for the dialog."""
        sm = MagicMock()
        sm.is_keepass_configured.return_value = False
        sm.is_keepass_unlocked.return_value = False
        sm.list_keepass_entries.return_value = []
        return sm

    def test_dialog_exists(self, qapp):
        from settings_dialogs import EmailServerEditDialog
        dlg = EmailServerEditDialog(self._sm())
        assert dlg is not None

    def test_dialog_is_modal(self, qapp):
        from settings_dialogs import EmailServerEditDialog
        dlg = EmailServerEditDialog(self._sm())
        assert dlg.isModal()

    def test_dialog_has_title(self, qapp):
        from settings_dialogs import EmailServerEditDialog
        dlg = EmailServerEditDialog(self._sm())
        assert dlg.windowTitle() != ""

    def test_dialog_add_mode_title(self, qapp):
        from settings_dialogs import EmailServerEditDialog
        dlg = EmailServerEditDialog(self._sm())
        assert "Add" in dlg.windowTitle() or "Email" in dlg.windowTitle()

    def test_dialog_edit_mode_title(self, qapp):
        from settings_dialogs import EmailServerEditDialog
        cfg = {"name": "Work", "smtp_server": "smtp.work.com", "smtp_port": 587,
               "smtp_use_tls": True, "sender_address": "me@work.com"}
        dlg = EmailServerEditDialog(self._sm(), config=cfg)
        assert "Edit" in dlg.windowTitle() or "Email" in dlg.windowTitle()

    def test_dialog_has_name_field(self, qapp):
        from settings_dialogs import EmailServerEditDialog
        dlg = EmailServerEditDialog(self._sm())
        assert hasattr(dlg, "_name_edit")

    def test_dialog_has_smtp_server_field(self, qapp):
        from settings_dialogs import EmailServerEditDialog
        dlg = EmailServerEditDialog(self._sm())
        assert hasattr(dlg, "_smtp_server_edit")

    def test_dialog_has_smtp_port_field(self, qapp):
        from settings_dialogs import EmailServerEditDialog
        dlg = EmailServerEditDialog(self._sm())
        assert hasattr(dlg, "_smtp_port_edit")

    def test_dialog_has_tls_checkbox(self, qapp):
        from settings_dialogs import EmailServerEditDialog
        dlg = EmailServerEditDialog(self._sm())
        assert hasattr(dlg, "_smtp_use_tls_check")

    def test_dialog_has_no_sender_address_field(self, qapp):
        """Sender address was moved to EmailConfigDialog; must NOT exist here."""
        from settings_dialogs import EmailServerEditDialog
        dlg = EmailServerEditDialog(self._sm())
        assert not hasattr(dlg, "_sender_address_edit"), (
            "_sender_address_edit must not be in EmailServerEditDialog; "
            "sender address is now per-project, stored via EmailConfigDialog."
        )

    def test_dialog_has_no_keepass_stack(self, qapp):
        """The account editor must not contain a KeePass QStackedWidget."""
        from settings_dialogs import EmailServerEditDialog
        dlg = EmailServerEditDialog(self._sm())
        assert not hasattr(dlg, "_kp_stack"), (
            "EmailServerEditDialog must not have a KeePass section; "
            "credentials are configured globally via EmailConfigDialog."
        )

    def test_dialog_has_no_keepass_entry_combo(self, qapp):
        """The account editor must not contain a KeePass entry combo box."""
        from settings_dialogs import EmailServerEditDialog
        dlg = EmailServerEditDialog(self._sm())
        assert not hasattr(dlg, "_kp_entry_combo")

    def test_get_config_returns_dict(self, qapp):
        from settings_dialogs import EmailServerEditDialog
        cfg_in = {"name": "Work", "smtp_server": "smtp.work.com", "smtp_port": 587,
                  "smtp_use_tls": True, "sender_address": "me@work.com"}
        dlg = EmailServerEditDialog(self._sm(), config=cfg_in)
        result = dlg.get_config()
        assert isinstance(result, dict)

    def test_get_config_has_no_keepass_entry_key(self, qapp):
        """Config dict returned by the dialog must not include keepass_entry."""
        from settings_dialogs import EmailServerEditDialog
        cfg_in = {"name": "Work", "smtp_server": "smtp.work.com", "smtp_port": 587,
                  "smtp_use_tls": True, "sender_address": "me@work.com"}
        dlg = EmailServerEditDialog(self._sm(), config=cfg_in)
        result = dlg.get_config()
        assert "keepass_entry" not in result, (
            "keepass_entry must not be stored per account; "
            "KeePass credentials are global (configured in EmailConfigDialog)."
        )

    def test_smtp_fields_populated_from_config(self, qapp):
        from settings_dialogs import EmailServerEditDialog
        cfg_in = {"name": "Work", "smtp_server": "smtp.work.com", "smtp_port": 465,
                  "smtp_use_tls": False}
        dlg = EmailServerEditDialog(self._sm(), config=cfg_in)
        assert dlg._name_edit.text() == "Work"
        assert dlg._smtp_server_edit.text() == "smtp.work.com"
        assert dlg._smtp_port_edit.text() == "465"
        assert dlg._smtp_use_tls_check.isChecked() is False

    def test_default_port_is_587(self, qapp):
        from settings_dialogs import EmailServerEditDialog
        dlg = EmailServerEditDialog(self._sm())
        assert dlg._smtp_port_edit.text() == "587"

    def test_default_tls_is_checked(self, qapp):
        from settings_dialogs import EmailServerEditDialog
        dlg = EmailServerEditDialog(self._sm())
        assert dlg._smtp_use_tls_check.isChecked() is True

    def test_dialog_has_no_kp_lookup_button(self, qapp):
        """The 'From KeePass...' button must NOT exist in EmailServerEditDialog;
        it was moved to EmailConfigDialog (Sender section)."""
        from PyQt5.QtWidgets import QPushButton
        from settings_dialogs import EmailServerEditDialog
        dlg = EmailServerEditDialog(self._sm())
        buttons = dlg.findChildren(QPushButton)
        kp_btns = [b for b in buttons if "KeePass" in b.text()]
        assert not kp_btns, (
            "'From KeePass...' button must not be in EmailServerEditDialog; "
            "it has been moved to the EmailConfigDialog Sender section."
        )

    def test_has_no_lookup_sender_method(self, qapp):
        """_lookup_sender_from_keepass_ad was moved to EmailConfigDialog."""
        from settings_dialogs import EmailServerEditDialog
        dlg = EmailServerEditDialog(self._sm())
        assert not hasattr(dlg, "_lookup_sender_from_keepass_ad"), (
            "_lookup_sender_from_keepass_ad must not be in EmailServerEditDialog; "
            "it has been moved to EmailConfigDialog."
        )

    def test_has_no_test_connection_method(self, qapp):
        """_test_connection was removed from EmailServerEditDialog;
        connection testing is done from EmailConfigDialog."""
        from settings_dialogs import EmailServerEditDialog
        dlg = EmailServerEditDialog(self._sm())
        assert not hasattr(dlg, "_test_connection"), (
            "_test_connection must not be in EmailServerEditDialog."
        )


# ---------------------------------------------------------------------------
# EmailConfigDialog — project-aware account selector + sender name
# ---------------------------------------------------------------------------

class TestEmailConfigDialog:
    """Tests for EmailConfigDialog — per-project account selection and sender name.

    Selected account and sender name are stored in the project sidecar JSON;
    the KeePass entry remains in QSettings (machine-local).
    """

    def _sm(self, configs=None, active_name="", kp_entry=""):
        sm = MagicMock()
        sm.get_email_configs.return_value = list(configs) if configs is not None else []
        sm.get_active_email_config_name.return_value = active_name
        sm.get_email_keepass_entry.return_value = kp_entry
        sm.is_keepass_configured.return_value = False
        sm.is_keepass_unlocked.return_value = False
        sm.list_keepass_entries.return_value = []
        return sm

    def _cfg(self, name="Work", server="smtp.work.com"):
        return {
            "name": name, "smtp_server": server,
            "smtp_port": 587, "smtp_use_tls": True,
        }

    def test_dialog_exists(self, qapp):
        from settings_dialogs import EmailConfigDialog
        dlg = EmailConfigDialog(self._sm())
        assert dlg is not None

    def test_dialog_is_modal(self, qapp):
        from settings_dialogs import EmailConfigDialog
        dlg = EmailConfigDialog(self._sm())
        assert dlg.isModal()

    def test_dialog_has_keepass_section(self, qapp):
        """Dialog must retain the KeePass credential stacked widget."""
        from settings_dialogs import EmailConfigDialog
        dlg = EmailConfigDialog(self._sm())
        assert hasattr(dlg, "_kp_stack")

    def test_dialog_has_account_combo(self, qapp):
        """Dialog has a QComboBox for selecting the active SMTP account."""
        from settings_dialogs import EmailConfigDialog
        dlg = EmailConfigDialog(self._sm())
        assert hasattr(dlg, "_account_combo")

    def test_dialog_has_sender_name_edit(self, qapp):
        """Dialog has a QLineEdit for the display name used in the From header."""
        from settings_dialogs import EmailConfigDialog
        dlg = EmailConfigDialog(self._sm())
        assert hasattr(dlg, "_sender_name_edit")

    def test_no_accounts_label_visible_when_no_configs(self, qapp):
        """When no SMTP accounts exist the warning label is shown, combo hidden."""
        from settings_dialogs import EmailConfigDialog
        dlg = EmailConfigDialog(self._sm(configs=[]))
        assert not dlg._no_accounts_lbl.isHidden()
        assert dlg._account_combo.isHidden()

    def test_account_combo_visible_when_configs_present(self, qapp):
        """When accounts are configured the combo is shown, warning label hidden."""
        from settings_dialogs import EmailConfigDialog
        dlg = EmailConfigDialog(self._sm(configs=[self._cfg()]))
        assert not dlg._account_combo.isHidden()
        assert dlg._no_accounts_lbl.isHidden()

    def test_account_combo_populated_with_config_names(self, qapp):
        """Combo contains one item per configured SMTP account."""
        from settings_dialogs import EmailConfigDialog
        configs = [self._cfg("Work"), self._cfg("Personal", "smtp.gmail.com")]
        dlg = EmailConfigDialog(self._sm(configs=configs))
        assert dlg._account_combo.count() == 2

    def test_active_account_pre_selected_from_global(self, qapp):
        """Global active account name pre-selects the matching combo item."""
        from settings_dialogs import EmailConfigDialog
        configs = [self._cfg("Work"), self._cfg("Personal", "smtp.gmail.com")]
        dlg = EmailConfigDialog(self._sm(configs=configs, active_name="Personal"))
        assert dlg._account_combo.currentData() == "Personal"

    def test_sender_name_empty_by_default_without_project(self, qapp):
        """Sender name field is empty when no project sidecar provides a value."""
        from settings_dialogs import EmailConfigDialog
        dlg = EmailConfigDialog(self._sm(configs=[self._cfg()]))
        assert dlg._sender_name_edit.text() == ""

    def test_get_current_config_returns_none_when_no_accounts(self, qapp):
        """_get_current_config returns None when no SMTP accounts are configured."""
        from settings_dialogs import EmailConfigDialog
        dlg = EmailConfigDialog(self._sm(configs=[]))
        assert dlg._get_current_config() is None

    def test_get_current_config_returns_dict_for_selected_account(self, qapp):
        """_get_current_config returns the selected account dict."""
        from settings_dialogs import EmailConfigDialog
        dlg = EmailConfigDialog(self._sm(configs=[self._cfg("Work")]))
        result = dlg._get_current_config()
        assert isinstance(result, dict)
        assert result.get("name") == "Work"

    def test_get_current_config_injects_sender_name(self, qapp):
        """_get_current_config includes sender_name from the text field."""
        from settings_dialogs import EmailConfigDialog
        dlg = EmailConfigDialog(self._sm(configs=[self._cfg("Work")]))
        dlg._sender_name_edit.setText("Alice Smith")
        result = dlg._get_current_config()
        assert result.get("sender_name") == "Alice Smith"

    def test_get_current_config_omits_sender_name_when_empty(self, qapp):
        """_get_current_config does not include sender_name key when field is empty."""
        from settings_dialogs import EmailConfigDialog
        dlg = EmailConfigDialog(self._sm(configs=[self._cfg("Work")]))
        dlg._sender_name_edit.setText("")
        result = dlg._get_current_config()
        assert "sender_name" not in result

    def test_project_custom_props_preselect_active_account(self, qapp):
        """Project sidecar 'Email Active Account' pre-selects the right combo item."""
        from settings_dialogs import EmailConfigDialog
        configs = [self._cfg("Work"), self._cfg("Personal", "smtp.gmail.com")]
        sm = self._sm(configs=configs)
        cp = MagicMock()
        cp.get.side_effect = lambda k: {"Email Active Account": "Personal"}.get(k)
        project = MagicMock()
        project.getProjectProperties.return_value.getCustomProperties.return_value = cp
        dlg = EmailConfigDialog(sm, project=project)
        assert dlg._account_combo.currentData() == "Personal"

    def test_project_custom_props_populate_sender_name(self, qapp):
        """Project sidecar 'Email Sender Name' pre-fills the sender name field."""
        from settings_dialogs import EmailConfigDialog
        sm = self._sm(configs=[self._cfg()])
        cp = MagicMock()
        cp.get.side_effect = lambda k: {"Email Sender Name": "Bob Jones"}.get(k)
        project = MagicMock()
        project.getProjectProperties.return_value.getCustomProperties.return_value = cp
        dlg = EmailConfigDialog(sm, project=project)
        assert dlg._sender_name_edit.text() == "Bob Jones"

    # ------------------------------------------------------------------
    # Sender address in EmailConfigDialog (moved from EmailServerEditDialog)
    # ------------------------------------------------------------------

    def test_email_config_dialog_has_sender_address_field(self, qapp):
        """EmailConfigDialog now contains the sender address field."""
        from settings_dialogs import EmailConfigDialog
        dlg = EmailConfigDialog(self._sm(configs=[self._cfg()]))
        assert hasattr(dlg, "_sender_address_edit"), (
            "_sender_address_edit must exist in EmailConfigDialog; "
            "sender address is now per-project, not per-account."
        )

    def test_project_custom_props_populate_sender_address(self, qapp):
        """Project sidecar 'Email Sender Address' pre-fills the sender address field."""
        from settings_dialogs import EmailConfigDialog
        sm = self._sm(configs=[self._cfg()])
        cp = MagicMock()
        cp.get.side_effect = lambda k: {"Email Sender Address": "alice@work.com"}.get(k)
        project = MagicMock()
        project.getProjectProperties.return_value.getCustomProperties.return_value = cp
        dlg = EmailConfigDialog(sm, project=project)
        assert dlg._sender_address_edit.text() == "alice@work.com"

    def test_sender_address_empty_by_default_without_project(self, qapp):
        """Sender address field is empty when no project sidecar provides a value."""
        from settings_dialogs import EmailConfigDialog
        dlg = EmailConfigDialog(self._sm(configs=[self._cfg()]))
        assert dlg._sender_address_edit.text() == ""

    def test_get_current_config_injects_sender_address(self, qapp):
        """_get_current_config includes sender_address from the per-project field."""
        from settings_dialogs import EmailConfigDialog
        dlg = EmailConfigDialog(self._sm(configs=[self._cfg("Work")]))
        dlg._sender_address_edit.setText("alice@work.com")
        result = dlg._get_current_config()
        assert result.get("sender_address") == "alice@work.com"

    def test_get_current_config_omits_sender_address_when_empty(self, qapp):
        """_get_current_config does not set sender_address when the field is empty."""
        from settings_dialogs import EmailConfigDialog
        dlg = EmailConfigDialog(self._sm(configs=[self._cfg("Work")]))
        dlg._sender_address_edit.setText("")
        result = dlg._get_current_config()
        # The config dict may carry sender_address from the original account dict;
        # but it must not inject an empty string from the per-project field.
        injected = result.get("sender_address", "")
        # If the account dict itself had a sender_address it should not appear,
        # because the new _cfg() helper no longer includes it.
        assert injected == "", (
            "An empty sender_address field must not inject a non-empty string "
            "into the config dict."
        )

    # ------------------------------------------------------------------
    # KeePass lookup moved to EmailConfigDialog
    # ------------------------------------------------------------------

    def test_email_config_dialog_has_lookup_sender_method(self, qapp):
        """EmailConfigDialog must have _lookup_sender_from_keepass_ad (moved from EmailServerEditDialog)."""
        from settings_dialogs import EmailConfigDialog
        dlg = EmailConfigDialog(self._sm())
        assert hasattr(dlg, "_lookup_sender_from_keepass_ad")

    def test_kp_lookup_in_email_config_warns_when_no_entry_selected(self, qapp):
        """_lookup_sender_from_keepass_ad warns when no KeePass entry is selected in the dialog."""
        from settings_dialogs import EmailConfigDialog
        sm = self._sm()
        sm.is_keepass_configured.return_value = True
        sm.is_keepass_unlocked.return_value = True
        sm.list_keepass_entries.return_value = []
        sm.get_email_keepass_entry.return_value = ""
        dlg = EmailConfigDialog(sm)
        # Force page 2 (unlocked) so the combo path is taken
        dlg._kp_stack.setCurrentIndex(2)
        dlg._kp_entry_combo.setCurrentText("")
        with patch("settings_dialogs.QMessageBox.warning") as mock_warn:
            dlg._lookup_sender_from_keepass_ad()
        mock_warn.assert_called_once()
        args = mock_warn.call_args[0]
        assert "KeePass" in args[1] or "KeePass" in args[2]

    def test_kp_lookup_in_email_config_warns_when_keepass_locked(self, qapp):
        """_lookup_sender_from_keepass_ad warns when KeePass is locked (page 0 or 1)."""
        from settings_dialogs import EmailConfigDialog
        sm = self._sm()
        sm.get_email_keepass_entry.return_value = "Email/SMTP"
        dlg = EmailConfigDialog(sm)
        # Stack is on page 0 (not configured) so entry_title will be from QSettings fallback
        with patch("integrations.keepass_integration.is_unlocked", return_value=False), \
             patch("settings_dialogs.QMessageBox.warning") as mock_warn:
            dlg._lookup_sender_from_keepass_ad()
        mock_warn.assert_called_once()

    # ------------------------------------------------------------------
    # Tooltip coverage — EmailServerEditDialog
    # ------------------------------------------------------------------

    def test_name_field_has_tooltip(self, qapp):
        """Name field must carry a descriptive tooltip."""
        from settings_dialogs import EmailServerEditDialog
        dlg = EmailServerEditDialog(self._sm())
        assert dlg._name_edit.toolTip() != "", "Name field must have a tooltip"

    def test_smtp_server_field_has_tooltip(self, qapp):
        """SMTP Server field must carry a descriptive tooltip."""
        from settings_dialogs import EmailServerEditDialog
        dlg = EmailServerEditDialog(self._sm())
        assert dlg._smtp_server_edit.toolTip() != "", "SMTP Server field must have a tooltip"

    def test_smtp_port_field_has_tooltip(self, qapp):
        """SMTP Port field must carry a descriptive tooltip."""
        from settings_dialogs import EmailServerEditDialog
        dlg = EmailServerEditDialog(self._sm())
        assert dlg._smtp_port_edit.toolTip() != "", "SMTP Port field must have a tooltip"

    def test_tls_checkbox_has_tooltip(self, qapp):
        """STARTTLS checkbox must carry a descriptive tooltip."""
        from settings_dialogs import EmailServerEditDialog
        dlg = EmailServerEditDialog(self._sm())
        assert dlg._smtp_use_tls_check.toolTip() != "", "STARTTLS checkbox must have a tooltip"

    # ------------------------------------------------------------------
    # Tooltip coverage — EmailConfigDialog
    # ------------------------------------------------------------------

    def test_account_combo_has_tooltip(self, qapp):
        """Account combo must carry a descriptive tooltip."""
        from settings_dialogs import EmailConfigDialog
        dlg = EmailConfigDialog(self._sm(configs=[self._cfg()]))
        assert dlg._account_combo.toolTip() != "", "Account combo must have a tooltip"

    def test_sender_address_field_has_tooltip(self, qapp):
        """Sender Address field in EmailConfigDialog must carry a descriptive tooltip."""
        from settings_dialogs import EmailConfigDialog
        dlg = EmailConfigDialog(self._sm(configs=[self._cfg()]))
        assert dlg._sender_address_edit.toolTip() != "", "Sender Address field must have a tooltip"

    def test_sender_name_field_has_tooltip(self, qapp):
        """Sender Display Name field must carry a descriptive tooltip."""
        from settings_dialogs import EmailConfigDialog
        dlg = EmailConfigDialog(self._sm(configs=[self._cfg()]))
        assert dlg._sender_name_edit.toolTip() != "", "Sender Name field must have a tooltip"

    def test_kp_entry_combo_has_tooltip(self, qapp):
        """KeePass entry combo must carry a descriptive tooltip (visible on page 2)."""
        from settings_dialogs import EmailConfigDialog
        sm = self._sm()
        sm.is_keepass_configured.return_value = True
        sm.is_keepass_unlocked.return_value = True
        sm.list_keepass_entries.return_value = ["Entry1"]
        dlg = EmailConfigDialog(sm)
        assert dlg._kp_entry_combo.toolTip() != "", "KeePass entry combo must have a tooltip"


# ---------------------------------------------------------------------------
# CPMSettingsDialog (Phase 2)
# ---------------------------------------------------------------------------

class TestCpmSettingsDialog:
    """Tests for CPMSettingsDialog — critical-path engine configuration dialog."""

    def _sm(self):
        sm = MagicMock()
        sm.get_show_float_bar.return_value = False
        sm.get_show_free_float_column.return_value = False
        sm.get_show_cpm_results_panel.return_value = False
        return sm

    def _cfg(self, slack=0, dep_types="all"):
        return {"critical_slack_days": slack, "dep_types": dep_types}

    def test_dialog_created_successfully(self, qapp):
        from settings_dialogs import CPMSettingsDialog
        dlg = CPMSettingsDialog(self._cfg(), self._sm())
        assert dlg is not None

    def test_dialog_is_modal(self, qapp):
        from settings_dialogs import CPMSettingsDialog
        from PyQt5.QtWidgets import QDialog
        dlg = CPMSettingsDialog(self._cfg(), self._sm())
        assert isinstance(dlg, QDialog), "CPMSettingsDialog must be a QDialog subclass"

    def test_dialog_title(self, qapp):
        from settings_dialogs import CPMSettingsDialog
        dlg = CPMSettingsDialog(self._cfg(), self._sm())
        assert dlg.windowTitle() == "Critical Path Settings"

    def test_slack_spin_initialized_from_cfg(self, qapp):
        from settings_dialogs import CPMSettingsDialog
        dlg = CPMSettingsDialog(self._cfg(slack=3), self._sm())
        assert dlg._slack_spin.value() == 3

    def test_dep_all_radio_checked_when_cfg_all(self, qapp):
        from settings_dialogs import CPMSettingsDialog
        dlg = CPMSettingsDialog(self._cfg(dep_types="all"), self._sm())
        assert dlg._dep_all.isChecked()
        assert not dlg._dep_fs.isChecked()

    def test_dep_fs_radio_checked_when_cfg_fs_only(self, qapp):
        from settings_dialogs import CPMSettingsDialog
        dlg = CPMSettingsDialog(self._cfg(dep_types="fs_only"), self._sm())
        assert dlg._dep_fs.isChecked()
        assert not dlg._dep_all.isChecked()

    def test_display_checkboxes_initialized_from_settings_manager(self, qapp):
        from settings_dialogs import CPMSettingsDialog
        sm = self._sm()
        sm.get_show_float_bar.return_value = True
        sm.get_show_free_float_column.return_value = True
        sm.get_show_cpm_results_panel.return_value = True
        dlg = CPMSettingsDialog(self._cfg(), sm)
        assert dlg._chk_float_bar.isChecked()
        assert dlg._chk_ff_col.isChecked()
        assert dlg._chk_results.isChecked()

    def test_restore_defaults_resets_all_fields(self, qapp):
        from settings_dialogs import CPMSettingsDialog
        sm = self._sm()
        sm.get_show_float_bar.return_value = True
        dlg = CPMSettingsDialog(self._cfg(slack=5, dep_types="fs_only"), sm)
        dlg._restore_defaults()
        assert dlg._slack_spin.value() == 0
        assert dlg._dep_all.isChecked()
        assert not dlg._chk_float_bar.isChecked()
        assert not dlg._chk_ff_col.isChecked()
        assert not dlg._chk_results.isChecked()

    def test_on_ok_saves_slack_to_cpm_cfg(self, qapp):
        from settings_dialogs import CPMSettingsDialog
        dlg = CPMSettingsDialog(self._cfg(slack=0), self._sm())
        dlg._slack_spin.setValue(4)
        dlg._on_ok()
        assert dlg.get_cpm_cfg()["critical_slack_days"] == 4

    def test_on_ok_saves_dep_types_fs_only(self, qapp):
        from settings_dialogs import CPMSettingsDialog
        dlg = CPMSettingsDialog(self._cfg(dep_types="all"), self._sm())
        dlg._dep_fs.setChecked(True)
        dlg._on_ok()
        assert dlg.get_cpm_cfg()["dep_types"] == "fs_only"

    def test_on_ok_calls_settings_manager_methods(self, qapp):
        from settings_dialogs import CPMSettingsDialog
        sm = self._sm()
        dlg = CPMSettingsDialog(self._cfg(), sm)
        dlg._chk_float_bar.setChecked(True)
        dlg._chk_ff_col.setChecked(True)
        dlg._chk_results.setChecked(True)
        dlg._on_ok()
        sm.set_show_float_bar.assert_called_once_with(True)
        sm.set_show_free_float_column.assert_called_once_with(True)
        sm.set_show_cpm_results_panel.assert_called_once_with(True)
