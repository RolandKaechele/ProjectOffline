"""Tests for integrations/ad_integration.py — Active Directory lookup module.

All PowerShell subprocess calls are patched; no domain membership or RSAT
installation is required to run these tests.
"""

import json
import sys
import os

import pytest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))


class TestADIntegration:
    """Unit tests for src/integrations/ad_integration.py."""

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _ad_json(self, display="Joe Smith", mail="joe.smith@corp.com",
                 dept="Engineering", sam="jsmith"):
        return json.dumps({
            "DisplayName": display,
            "mail": mail,
            "Department": dept,
            "SamAccountName": sam,
        })

    def _make_resource(self, name, email=None):
        r = MagicMock()
        r.getName.return_value = name
        r.getEmailAddress.return_value = email or ""
        return r

    # ------------------------------------------------------------------
    # is_ad_available
    # ------------------------------------------------------------------

    def test_is_ad_available_true_when_ps_returns_module(self):
        from integrations.ad_integration import is_ad_available
        with patch("integrations.ad_integration._run_ps",
                   return_value="ActiveDirectory"):
            assert is_ad_available() is True

    def test_is_ad_available_false_when_ps_returns_none(self):
        from integrations.ad_integration import is_ad_available
        with patch("integrations.ad_integration._run_ps", return_value=None):
            assert is_ad_available() is False

    def test_is_ad_available_false_when_ps_returns_empty(self):
        from integrations.ad_integration import is_ad_available
        with patch("integrations.ad_integration._run_ps", return_value=""):
            assert is_ad_available() is False

    # ------------------------------------------------------------------
    # lookup_by_name
    # ------------------------------------------------------------------

    def test_lookup_by_name_returns_dict_on_hit(self):
        from integrations.ad_integration import lookup_by_name
        with patch("integrations.ad_integration._run_ps",
                   return_value=self._ad_json()):
            result = lookup_by_name("Smith, Joe")
        assert result is not None
        assert result["email"] == "joe.smith@corp.com"
        assert result["display_name"] == "Joe Smith"
        assert result["department"] == "Engineering"
        assert result["username"] == "jsmith"

    def test_lookup_by_name_returns_none_when_ps_returns_none(self):
        from integrations.ad_integration import lookup_by_name
        with patch("integrations.ad_integration._run_ps", return_value=None):
            assert lookup_by_name("Nobody, Nope") is None

    def test_lookup_by_name_empty_string_returns_none(self):
        from integrations.ad_integration import lookup_by_name
        assert lookup_by_name("") is None

    def test_lookup_by_name_rejects_injection_chars(self):
        from integrations.ad_integration import lookup_by_name
        for bad in ["(hack)", "wild*card", "back\\slash"]:
            assert lookup_by_name(bad) is None

    def test_lookup_by_name_single_quote_escaped(self):
        """Single quotes in names must be escaped as '' in PS filter strings."""
        from integrations.ad_integration import lookup_by_name
        with patch("integrations.ad_integration._run_ps",
                   return_value=None) as mock_ps:
            lookup_by_name("O'Brien, Sean")
        first_cmd = mock_ps.call_args_list[0][0][0]
        assert "O''Brien" in first_cmd

    # ------------------------------------------------------------------
    # lookup_by_email
    # ------------------------------------------------------------------

    def test_lookup_by_email_returns_dict_on_hit(self):
        from integrations.ad_integration import lookup_by_email
        with patch("integrations.ad_integration._run_ps",
                   return_value=self._ad_json()):
            result = lookup_by_email("joe.smith@corp.com")
        assert result is not None
        assert result["email"] == "joe.smith@corp.com"

    def test_lookup_by_email_returns_none_for_invalid_input(self):
        from integrations.ad_integration import lookup_by_email
        assert lookup_by_email("") is None
        assert lookup_by_email("notanemail") is None

    def test_lookup_by_email_returns_none_when_ps_returns_none(self):
        from integrations.ad_integration import lookup_by_email
        with patch("integrations.ad_integration._run_ps", return_value=None):
            assert lookup_by_email("nobody@corp.com") is None

    # ------------------------------------------------------------------
    # lookup_by_username
    # ------------------------------------------------------------------

    def test_lookup_by_username_returns_dict_on_hit(self):
        from integrations.ad_integration import lookup_by_username
        with patch("integrations.ad_integration._run_ps",
                   return_value=self._ad_json()):
            result = lookup_by_username("jsmith")
        assert result is not None
        assert result["username"] == "jsmith"

    def test_lookup_by_username_returns_none_for_empty(self):
        from integrations.ad_integration import lookup_by_username
        assert lookup_by_username("") is None
        assert lookup_by_username("   ") is None

    def test_lookup_by_username_rejects_injection_chars(self):
        from integrations.ad_integration import lookup_by_username
        for bad in ["user;cmd", "a|b", "cmd`x", "$env", "(x)", "a<b"]:
            assert lookup_by_username(bad) is None

    def test_lookup_by_username_uses_identity_flag(self):
        """lookup_by_username must pass use_identity=True to _ps_query_to_dict."""
        from integrations.ad_integration import lookup_by_username
        with patch("integrations.ad_integration._ps_query_to_dict",
                   return_value=None) as mock_q:
            lookup_by_username("jsmith")
        mock_q.assert_called_once_with("jsmith", use_identity=True)

    # ------------------------------------------------------------------
    # Lookup history
    # ------------------------------------------------------------------

    def test_lookup_history_records_name_hit(self):
        import integrations.ad_integration as ad
        ad._last_lookup_results.clear()
        with patch("integrations.ad_integration._run_ps",
                   return_value=self._ad_json()):
            ad.lookup_by_name("Smith, Joe")
        history = ad.get_last_lookup_results()
        assert len(history) >= 1
        assert history[-1]["fn"] == "lookup_by_name"
        assert history[-1]["input"] == "Smith, Joe"
        assert history[-1]["result"] is not None

    def test_lookup_history_records_miss(self):
        import integrations.ad_integration as ad
        ad._last_lookup_results.clear()
        with patch("integrations.ad_integration._run_ps", return_value=None):
            ad.lookup_by_name("Missing, Person")
        history = ad.get_last_lookup_results()
        assert history[-1]["result"] is None

    def test_lookup_history_records_email_lookup(self):
        import integrations.ad_integration as ad
        ad._last_lookup_results.clear()
        with patch("integrations.ad_integration._run_ps",
                   return_value=self._ad_json()):
            ad.lookup_by_email("joe@corp.com")
        history = ad.get_last_lookup_results()
        assert history[-1]["fn"] == "lookup_by_email"

    def test_lookup_history_records_username_lookup(self):
        import integrations.ad_integration as ad
        ad._last_lookup_results.clear()
        with patch("integrations.ad_integration._run_ps",
                   return_value=self._ad_json()):
            ad.lookup_by_username("jsmith")
        history = ad.get_last_lookup_results()
        assert history[-1]["fn"] == "lookup_by_username"

    def test_get_last_lookup_results_returns_copy(self):
        import integrations.ad_integration as ad
        copy1 = ad.get_last_lookup_results()
        copy2 = ad.get_last_lookup_results()
        assert copy1 is not copy2

    # ------------------------------------------------------------------
    # sync_resources
    # ------------------------------------------------------------------

    def test_sync_resources_none_project_returns_zero(self):
        from integrations.ad_integration import sync_resources
        result = sync_resources(None)
        assert result["total"] == 0
        assert result["updated"] == 0

    def test_sync_resources_skips_resource_with_existing_email(self):
        from integrations.ad_integration import sync_resources
        project = MagicMock()
        res = self._make_resource("Smith, Joe", email="existing@corp.com")
        project.getResources.return_value = [res]
        with patch("integrations.ad_integration._run_ps", return_value=None):
            result = sync_resources(project)
        assert result["skipped"] == 1
        assert result["updated"] == 0

    def test_sync_resources_updates_resource_without_email(self):
        from integrations.ad_integration import sync_resources
        project = MagicMock()
        res = self._make_resource("Smith, Joe", email="")
        project.getResources.return_value = [res]
        with patch("integrations.ad_integration._run_ps",
                   return_value=self._ad_json()):
            result = sync_resources(project)
        assert result["updated"] == 1
        res.setEmailAddress.assert_called_once_with("joe.smith@corp.com")

    def test_sync_resources_attaches_ad_data(self):
        """Resolved AD data is attached as _ad_data for other modules to reuse."""
        from integrations.ad_integration import sync_resources
        project = MagicMock()
        res = self._make_resource("Smith, Joe", email="")
        project.getResources.return_value = [res]
        with patch("integrations.ad_integration._run_ps",
                   return_value=self._ad_json()):
            sync_resources(project)
        assert hasattr(res, "_ad_data")
        assert res._ad_data["email"] == "joe.smith@corp.com"

    def test_sync_resources_skips_resource_with_none_name(self):
        from integrations.ad_integration import sync_resources
        project = MagicMock()
        res = MagicMock()
        res.getName.return_value = None
        project.getResources.return_value = [res]
        with patch("integrations.ad_integration._run_ps", return_value=None):
            result = sync_resources(project)
        assert result["total"] == 0

    def test_sync_resources_returns_errors_on_exception(self):
        from integrations.ad_integration import sync_resources
        project = MagicMock()
        res = self._make_resource("Smith, Joe", email="")
        res.setEmailAddress.side_effect = RuntimeError("MPXJ error")
        project.getResources.return_value = [res]
        with patch("integrations.ad_integration._run_ps",
                   return_value=self._ad_json()):
            result = sync_resources(project)
        assert isinstance(result["errors"], list)

    # ------------------------------------------------------------------
    # get_last_sync_result
    # ------------------------------------------------------------------

    def test_get_last_sync_result_reflects_last_sync(self):
        import integrations.ad_integration as ad
        project = MagicMock()
        project.getResources.return_value = []
        with patch("integrations.ad_integration._run_ps", return_value=None):
            ad.sync_resources(project)
        result = ad.get_last_sync_result()
        assert result is not None
        assert "total" in result
        assert "updated" in result
        assert "skipped" in result
        assert "errors" in result


class TestMultiResultLookups:
    """Tests for lookup_by_email_all and lookup_by_username_all.

    These functions were updated to try an exact (indexed) match first before
    falling back to a slower wildcard scan.  All PS calls are patched via the
    internal helpers _ps_query_to_dict and _ps_query_to_list.
    """

    def _ad_entry(self, **kw):
        return {
            "display_name": kw.get("display_name", "Joe Smith"),
            "email":        kw.get("email", "joe.smith@corp.com"),
            "department":   kw.get("department", "Engineering"),
            "username":     kw.get("username", "jsmith"),
        }

    # ------------------------------------------------------------------
    # lookup_by_email_all
    # ------------------------------------------------------------------

    def test_email_all_fast_path_returns_exact_match(self):
        """Exact indexed match found — wildcard scan must not be called."""
        from integrations.ad_integration import lookup_by_email_all
        entry = self._ad_entry()
        with patch("integrations.ad_integration._ps_query_to_dict",
                   return_value=entry) as mock_exact, \
             patch("integrations.ad_integration._ps_query_to_list",
                   return_value=[]) as mock_wild:
            result = lookup_by_email_all("joe.smith@corp.com")
        assert result == [entry]
        mock_wild.assert_not_called()

    def test_email_all_falls_back_to_wildcard_when_no_exact_match(self):
        """Exact lookup returns None — wildcard scan is attempted."""
        from integrations.ad_integration import lookup_by_email_all
        entry = self._ad_entry()
        with patch("integrations.ad_integration._ps_query_to_dict",
                   return_value=None), \
             patch("integrations.ad_integration._ps_query_to_list",
                   return_value=[entry]):
            result = lookup_by_email_all("joe.smith@corp.com")
        assert result == [entry]

    def test_email_all_returns_empty_for_no_at_sign(self):
        from integrations.ad_integration import lookup_by_email_all
        assert lookup_by_email_all("") == []
        assert lookup_by_email_all("notanemail") == []

    def test_email_all_rejects_injection_chars(self):
        from integrations.ad_integration import lookup_by_email_all
        for bad in ["joe(*)@corp.com", "joe\\smith@corp.com"]:
            assert lookup_by_email_all(bad) == []

    def test_email_all_records_history_with_all_fn(self):
        import integrations.ad_integration as ad
        ad._last_lookup_results.clear()
        entry = self._ad_entry()
        with patch("integrations.ad_integration._ps_query_to_dict",
                   return_value=entry):
            ad.lookup_by_email_all("joe.smith@corp.com")
        history = ad.get_last_lookup_results()
        assert history[-1]["fn"] == "lookup_by_email_all"

    # ------------------------------------------------------------------
    # lookup_by_username_all
    # ------------------------------------------------------------------

    def test_username_all_fast_path_returns_exact_match(self):
        """Exact -Identity lookup succeeds — wildcard scan must not be called."""
        from integrations.ad_integration import lookup_by_username_all
        entry = self._ad_entry()
        with patch("integrations.ad_integration._ps_query_to_dict",
                   return_value=entry) as mock_exact, \
             patch("integrations.ad_integration._ps_query_to_list",
                   return_value=[]) as mock_wild:
            result = lookup_by_username_all("jsmith")
        assert result == [entry]
        mock_wild.assert_not_called()

    def test_username_all_falls_back_to_wildcard_when_identity_fails(self):
        """Identity lookup returns None — wildcard scan is attempted."""
        from integrations.ad_integration import lookup_by_username_all
        entry = self._ad_entry()
        with patch("integrations.ad_integration._ps_query_to_dict",
                   return_value=None), \
             patch("integrations.ad_integration._ps_query_to_list",
                   return_value=[entry]):
            result = lookup_by_username_all("jsmith")
        assert result == [entry]

    def test_username_all_returns_empty_for_empty_input(self):
        from integrations.ad_integration import lookup_by_username_all
        assert lookup_by_username_all("") == []
        assert lookup_by_username_all("   ") == []

    def test_username_all_rejects_injection_chars(self):
        from integrations.ad_integration import lookup_by_username_all
        for bad in ["user;cmd", "a|b", "wild*card"]:
            assert lookup_by_username_all(bad) == []

    def test_username_all_records_history_with_all_fn(self):
        import integrations.ad_integration as ad
        ad._last_lookup_results.clear()
        entry = self._ad_entry()
        with patch("integrations.ad_integration._ps_query_to_dict",
                   return_value=entry):
            ad.lookup_by_username_all("jsmith")
        history = ad.get_last_lookup_results()
        assert history[-1]["fn"] == "lookup_by_username_all"


class TestSearchGroups:
    """Tests for search_groups() — AD group name search."""

    def _group_json(self, name="Team-Backend", desc="Backend developers",
                    dn="CN=Team-Backend,OU=Groups,DC=corp,DC=com",
                    scope="Global"):
        import json
        return json.dumps({
            "Name":              name,
            "Description":       desc,
            "DistinguishedName": dn,
            "GroupCategory":     "Security",
            "GroupScope":        scope,
            "SamAccountName":    name,
        })

    # ------------------------------------------------------------------
    # Input validation
    # ------------------------------------------------------------------

    def test_empty_query_returns_empty_list(self):
        from integrations.ad_integration import search_groups
        assert search_groups("") == []

    def test_whitespace_only_returns_empty_list(self):
        from integrations.ad_integration import search_groups
        assert search_groups("   ") == []

    def test_injection_chars_rejected(self):
        from integrations.ad_integration import search_groups
        for bad in ["Back(end", "Team;Hack", "Group&Cmd", "wild|card"]:
            result = search_groups(bad)
            assert result == [], f"Expected [] for {bad!r}, got {result}"

    def test_single_quote_escaped_in_ps_command(self):
        """Single quotes in the query must be doubled to avoid PS injection."""
        from integrations.ad_integration import search_groups
        with patch("integrations.ad_integration._run_ps",
                   return_value=None) as mock_ps:
            search_groups("O'Connor")
        cmd = mock_ps.call_args[0][0]
        assert "O''Connor" in cmd

    # ------------------------------------------------------------------
    # PS result parsing
    # ------------------------------------------------------------------

    def test_single_group_json_object_wrapped_to_list(self):
        """A single-result PS query returns a JSON object, not an array.
        search_groups must wrap it in a list automatically."""
        from integrations.ad_integration import search_groups
        with patch("integrations.ad_integration._run_ps",
                   return_value=self._group_json()):
            result = search_groups("Backend")
        assert len(result) == 1
        assert result[0]["name"] == "Team-Backend"

    def test_multi_group_json_array_parsed(self):
        import json
        from integrations.ad_integration import search_groups
        payload = json.dumps([
            {"Name": "Team-A", "Description": "Alpha", "DistinguishedName": "CN=A",
             "GroupCategory": "Security", "GroupScope": "Global", "SamAccountName": "Team-A"},
            {"Name": "Team-B", "Description": "Beta",  "DistinguishedName": "CN=B",
             "GroupCategory": "Security", "GroupScope": "Global", "SamAccountName": "Team-B"},
        ])
        with patch("integrations.ad_integration._run_ps", return_value=payload):
            result = search_groups("Team")
        assert len(result) == 2
        assert {r["name"] for r in result} == {"Team-A", "Team-B"}

    def test_result_schema_keys(self):
        """Each result dict must contain all required keys."""
        from integrations.ad_integration import search_groups
        with patch("integrations.ad_integration._run_ps",
                   return_value=self._group_json()):
            result = search_groups("Backend")
        assert result
        for key in ("name", "description", "dn", "category", "scope", "sam_name"):
            assert key in result[0], f"Missing key: {key}"

    def test_groups_without_name_skipped(self):
        import json
        from integrations.ad_integration import search_groups
        # Both Name and SamAccountName are missing/null
        payload = json.dumps([
            {"Name": None, "Description": "x", "DistinguishedName": "CN=X",
             "GroupCategory": "Security", "GroupScope": "Global", "SamAccountName": None},
        ])
        with patch("integrations.ad_integration._run_ps", return_value=payload):
            result = search_groups("anything")
        assert result == []

    def test_ps_returns_none_gives_empty_list(self):
        from integrations.ad_integration import search_groups
        with patch("integrations.ad_integration._run_ps", return_value=None):
            assert search_groups("Backend") == []

    def test_ps_returns_invalid_json_gives_empty_list(self):
        from integrations.ad_integration import search_groups
        with patch("integrations.ad_integration._run_ps", return_value="not json"):
            assert search_groups("Backend") == []

    def test_description_and_scope_fields_populated(self):
        from integrations.ad_integration import search_groups
        with patch("integrations.ad_integration._run_ps",
                   return_value=self._group_json(desc="My desc", scope="Universal")):
            result = search_groups("Backend")
        assert result[0]["description"] == "My desc"
        assert result[0]["scope"] == "Universal"

    def test_wildcard_query_embedded_in_ps_command(self):
        """The PS command must use *query* wildcard pattern."""
        from integrations.ad_integration import search_groups
        with patch("integrations.ad_integration._run_ps",
                   return_value=None) as mock_ps:
            search_groups("Dev")
        cmd = mock_ps.call_args[0][0]
        assert "*Dev*" in cmd


class TestGetGroupMembers:
    """Tests for get_group_members() — enabled user members of an AD group."""

    def _user_json(self, display="Bob Smith", mail="bob@corp.com",
                   dept="IT", sam="bsmith", enabled=True):
        import json
        return json.dumps({
            "DisplayName":    display,
            "mail":           mail,
            "Department":     dept,
            "SamAccountName": sam,
            "Enabled":        enabled,
            "City":           None,
            "StateOrProvince": None,
            "co":             None,
        })

    def _multi_user_json(self, users):
        import json
        return json.dumps(users)

    # ------------------------------------------------------------------
    # Input validation
    # ------------------------------------------------------------------

    def test_empty_input_returns_empty_list(self):
        from integrations.ad_integration import get_group_members
        assert get_group_members("") == []

    def test_whitespace_only_returns_empty_list(self):
        from integrations.ad_integration import get_group_members
        assert get_group_members("   ") == []

    def test_injection_chars_rejected(self):
        from integrations.ad_integration import get_group_members
        for bad in ["Group;cmd", "DN&hack", "pipe|test", "back`tick"]:
            assert get_group_members(bad) == [], f"Expected [] for {bad!r}"

    def test_single_quote_in_dn_escaped(self):
        """Single quotes in DNs must be doubled for safe PS embedding."""
        from integrations.ad_integration import get_group_members
        with patch("integrations.ad_integration._run_ps",
                   return_value=None) as mock_ps:
            get_group_members("CN=O'Hara Team,OU=Groups,DC=corp,DC=com")
        cmd = mock_ps.call_args[0][0]
        assert "O''Hara" in cmd

    # ------------------------------------------------------------------
    # PS result parsing
    # ------------------------------------------------------------------

    def test_single_user_wrapped_to_list(self):
        """A single user PS response (dict) is treated as a one-element list."""
        from integrations.ad_integration import get_group_members
        with patch("integrations.ad_integration._run_ps",
                   return_value=self._user_json()):
            result = get_group_members("Team-Backend")
        assert len(result) == 1
        assert result[0]["email"] == "bob@corp.com"

    def test_result_schema_keys(self):
        """Each user dict must contain display_name, email, department, username."""
        from integrations.ad_integration import get_group_members
        with patch("integrations.ad_integration._run_ps",
                   return_value=self._user_json()):
            result = get_group_members("Team-Backend")
        assert result
        for key in ("display_name", "email", "department", "username"):
            assert key in result[0], f"Missing key: {key}"

    def test_users_without_email_excluded(self):
        """Members with no mail attribute (or no @) are silently skipped."""
        import json
        from integrations.ad_integration import get_group_members
        payload = json.dumps([
            {"DisplayName": "Alice", "mail": None, "Department": "IT",
             "SamAccountName": "alice", "City": None, "StateOrProvince": None, "co": None},
            {"DisplayName": "Bob",   "mail": "bob@corp.com", "Department": "IT",
             "SamAccountName": "bob", "City": None, "StateOrProvince": None, "co": None},
        ])
        with patch("integrations.ad_integration._run_ps", return_value=payload):
            result = get_group_members("Team-Backend")
        assert len(result) == 1
        assert result[0]["username"] == "bob"

    def test_users_with_no_at_sign_in_mail_excluded(self):
        import json
        from integrations.ad_integration import get_group_members
        payload = json.dumps(
            {"DisplayName": "Bad", "mail": "notanemail", "Department": "IT",
             "SamAccountName": "bad", "City": None, "StateOrProvince": None, "co": None}
        )
        with patch("integrations.ad_integration._run_ps", return_value=payload):
            result = get_group_members("Team-Backend")
        assert result == []

    def test_ps_returns_none_gives_empty_list(self):
        from integrations.ad_integration import get_group_members
        with patch("integrations.ad_integration._run_ps", return_value=None):
            assert get_group_members("Team-Backend") == []

    def test_ps_returns_invalid_json_gives_empty_list(self):
        from integrations.ad_integration import get_group_members
        with patch("integrations.ad_integration._run_ps", return_value="bad json"):
            assert get_group_members("Team-Backend") == []

    def test_recursive_flag_in_ps_command(self):
        """-Recursive must be present so nested group members are included."""
        from integrations.ad_integration import get_group_members
        with patch("integrations.ad_integration._run_ps",
                   return_value=None) as mock_ps:
            get_group_members("Team-Backend")
        cmd = mock_ps.call_args[0][0]
        assert "-Recursive" in cmd

    def test_multiple_users_all_returned(self):
        import json
        from integrations.ad_integration import get_group_members
        payload = json.dumps([
            {"DisplayName": "Alice", "mail": "alice@corp.com", "Department": "A",
             "SamAccountName": "alice", "City": None, "StateOrProvince": None, "co": None},
            {"DisplayName": "Bob",   "mail": "bob@corp.com",   "Department": "B",
             "SamAccountName": "bob",   "City": None, "StateOrProvince": None, "co": None},
            {"DisplayName": "Carol", "mail": "carol@corp.com", "Department": "C",
             "SamAccountName": "carol", "City": None, "StateOrProvince": None, "co": None},
        ])
        with patch("integrations.ad_integration._run_ps", return_value=payload):
            result = get_group_members("Team-Big")
        assert len(result) == 3
        assert {r["username"] for r in result} == {"alice", "bob", "carol"}

