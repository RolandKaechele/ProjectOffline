# jira_integration.py - Jira API connectivity and credential management.
#
# Provides connection testing and authenticated JIRA client creation for syncing
# tasks between the project and Jira issues. Credentials are retrieved from either
# QSettings (manual mode) or KeePass (keepass mode).
#
# Configuration (QSettings)
# -------------------------
# All Jira server configurations are stored in QSettings under the "jira/" prefix:
#   jira/servers — JSON array of server configuration dicts
#
# Each server dict contains:
#   {
#       "name": "My Company Jira",
#       "url": "https://mycompany.atlassian.net",
#       "auth_mode": "manual" | "keepass",
#       "username": "user@example.com",  # manual mode only
#       "token": "api_token_or_password",  # manual mode only
#       "credential_type": "token" | "password",  # manual mode only
#       "keepass_entry": "Group/Title",  # keepass mode only
#   }
#
# Public API
# ----------
#   test_connection(server)        -> tuple[bool, str]
#   get_jira_client(server)        -> tuple[JIRA | None, str]
#   record_filter_test(...)        -> None  (for debug tracking)
#   get_config_summary()           -> dict   (for app_debug.py dump)
#
# See documentation/jira_sync_configuration.md for full details.

from __future__ import annotations

from typing import Optional

from app_debug import is_debug as _is_debug  # type: ignore

# ---------------------------------------------------------------------------
# Public constants — key names used in project custom properties (sidecar JSON)
# ---------------------------------------------------------------------------
# Container keys (new format): properties are stored as nested JSON objects
JIRA2PROJECT_PROP = "jira2project"   # contains filter, filter_type, fields
PROJECT2JIRA_PROP = "project2jira"   # future: export/push settings

# Legacy flat keys (kept for backward-compat reading of old sidecar files)
JIRA_SYNC_FILTER_PROP = "JIRA Sync Filter"
JIRA_SYNC_FILTER_TYPE_PROP = "JIRA Sync Filter Type"  # "jql" (default) or "filter"
# Legacy individual field keys pattern: "JIRA Sync Field {field_name}" = "True"/"False"

# ---------------------------------------------------------------------------
# Module-level history tracking (for debug dump)
# ---------------------------------------------------------------------------
_last_connection_test: Optional[dict] = None
_last_filter_test: Optional[dict] = None


# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------

def _get_settings_manager():
    """Return a SettingsManager instance (reads from shared QSettings registry)."""
    try:
        from settings_manager import SettingsManager  # type: ignore
        return SettingsManager()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def test_connection(server: dict) -> tuple[bool, str]:
    """Test connectivity to a Jira server using the provided configuration.
    
    Args:
        server: Server configuration dict (from settings_manager.get_jira_servers())
    
    Returns:
        (success, error_message): error_message is empty on success
    
    Example:
        success, error = jira_integration.test_connection(server)
        if not success:
            print(f"Connection failed: {error}")
    """
    global _last_connection_test
    
    result = {
        "server_name": server.get("name", "(unnamed)"),
        "server_url": server.get("url", ""),
        "auth_mode": server.get("auth_mode", "manual"),
        "timestamp": None,
        "success": False,
        "error": "",
    }
    
    try:
        # Import timestamp here to avoid circular imports
        import datetime
        result["timestamp"] = datetime.datetime.now().isoformat()
        
        if _is_debug():
            print(f"[DEBUG] jira_integration.test_connection: server_name={result['server_name']}, url={result['server_url']}, auth_mode={result['auth_mode']}")
        
        # Get credentials
        sm = _get_settings_manager()
        if sm is None:
            result["error"] = "SettingsManager not available"
            _last_connection_test = result
            if _is_debug():
                print(f"[DEBUG] SettingsManager not available")
            return False, result["error"]
        
        if _is_debug():
            print(f"[DEBUG] Retrieving credentials via get_jira_credentials()...")
        username, credential = sm.get_jira_credentials(server)
        
        # For PAT (Personal Access Token), username is not required
        credential_type = server.get("credential_type", "token")
        if credential_type == "pat":
            if not credential:
                result["error"] = "PAT not available (KeePass may be locked)"
                _last_connection_test = result
                if _is_debug():
                    print(f"[DEBUG] PAT not available: credential={'<set>' if credential else '<empty>'}")
                return False, result["error"]
        else:
            if not username or not credential:
                result["error"] = "Authentication data unavailable (KeePass may be locked)"
                _last_connection_test = result
                if _is_debug():
                    print(f"[DEBUG] Credentials not available: username={'<set>' if username else '<empty>'}, credential={'<set>' if credential else '<empty>'}")
                return False, result["error"]
        
        if _is_debug():
            if credential_type == "pat":
                print(f"[DEBUG] PAT retrieved successfully")
            else:
                print(f"[DEBUG] Credentials retrieved: username={username}")
        
        # Test connection
        if _is_debug():
            print(f"[DEBUG] Creating JIRA client for {server.get('url', '')}...")
        from jira import JIRA  # type: ignore
        
        # Check if this server requires Personal Access Token (PAT) instead of basic auth
        credential_type = server.get("credential_type", "token")
        if credential_type == "pat":
            # Use token_auth for Personal Access Tokens (when basic auth is disabled)
            if _is_debug():
                print(f"[DEBUG] Using token_auth (PAT mode)")
            jira = JIRA(server=server.get("url", ""), token_auth=credential)
        else:
            # Use basic_auth for username + API token or password
            if _is_debug():
                print(f"[DEBUG] Using basic_auth (username + {credential_type})")
            jira = JIRA(server=server.get("url", ""), basic_auth=(username, credential))
        
        if _is_debug():
            print(f"[DEBUG] JIRA client created, calling myself()...")
        
        # Verify authentication by calling myself()
        myself = jira.myself()
        if not myself:
            result["error"] = "Authentication succeeded but could not retrieve user info"
            _last_connection_test = result
            if _is_debug():
                print(f"[DEBUG] myself() returned None or empty")
            return False, result["error"]
        
        if _is_debug():
            print(f"[DEBUG] Successfully authenticated as: {myself.get('displayName', 'Unknown')}")
        
        result["success"] = True
        _last_connection_test = result
        return True, ""
        
    except ImportError as exc:
        result["error"] = f"Missing dependency: {exc} (run: pip install jira)"
        _last_connection_test = result
        if _is_debug():
            import traceback
            print(f"[DEBUG] ImportError during test_connection:")
            print(traceback.format_exc())
        return False, result["error"]
    except Exception as exc:
        result["error"] = str(exc)
        _last_connection_test = result
        if _is_debug():
            import traceback
            print(f"[DEBUG] Exception during test_connection:")
            print(traceback.format_exc())
        return False, result["error"]


def get_jira_client(server: dict) -> tuple[Optional["JIRA"], str]:  # type: ignore
    """Create an authenticated JIRA client instance for the specified server.
    
    Args:
        server: Server configuration dict (from settings_manager.get_jira_servers())
    
    Returns:
        (jira_client, error_message): client is None on failure
    
    Example:
        jira, error = jira_integration.get_jira_client(server)
        if jira is None:
            print(f"Failed to connect: {error}")
        else:
            issues = jira.search_issues('project = MYPROJECT', maxResults=10)
    """
    try:
        # Get credentials
        sm = _get_settings_manager()
        if sm is None:
            return None, "SettingsManager not available"
        
        username, credential = sm.get_jira_credentials(server)
        
        # For PAT (Personal Access Token), username is not required
        credential_type = server.get("credential_type", "token")
        if credential_type == "pat":
            if not credential:
                return None, "PAT not available (KeePass may be locked)"
        else:
            if not username or not credential:
                return None, "Authentication data unavailable (KeePass may be locked)"
        
        # Create client
        from jira import JIRA  # type: ignore
        
        # Check if this server requires Personal Access Token (PAT) instead of basic auth
        if credential_type == "pat":
            # Use token_auth for Personal Access Tokens (when basic auth is disabled)
            jira = JIRA(server=server.get("url", ""), token_auth=credential)
        else:
            # Use basic_auth for username + API token or password
            jira = JIRA(server=server.get("url", ""), basic_auth=(username, credential))
        
        return jira, ""
        
    except ImportError as exc:
        return None, f"Missing dependency: {exc} (run: pip install jira)"
    except Exception as exc:
        return None, str(exc)


def _extract_filter_id(value: str) -> str:
    """Extract a numeric Jira filter ID from a URL or a plain numeric string.

    Accepts:
      - ``https://jira.example.com/issues/?filter=66111``
      - ``filter=66111``
      - ``66111``

    Returns the numeric ID as a string, or ``""`` if extraction fails.
    """
    import re
    value = value.strip()
    m = re.search(r'[?&]filter=(\d+)', value)
    if m:
        return m.group(1)
    if value.isdigit():
        return value
    return ""


def resolve_filter_to_jql(jira, filter_value: str, filter_type: str) -> tuple[str, str]:
    """Resolve a filter value to a JQL string.

    Args:
        jira: Authenticated JIRA client instance.
        filter_value: Either a JQL string (when *filter_type* is ``"jql"``) or a
            Jira filter ID / filter URL (when *filter_type* is ``"filter"``).
        filter_type: ``"jql"`` to use *filter_value* directly, or ``"filter"`` to
            look up a saved filter by ID / URL and retrieve its JQL.

    Returns:
        ``(jql_string, error_message)`` — *error_message* is empty on success.
    """
    if filter_type == "filter":
        filter_id = _extract_filter_id(filter_value)
        if not filter_id:
            return "", f"Could not extract a numeric filter ID from: {filter_value!r}"
        try:
            jira_filter = jira.filter(filter_id)
            jql = getattr(jira_filter, "jql", None)
            if not jql:
                return "", f"Saved filter {filter_id} returned no JQL"
            return str(jql), ""
        except Exception as exc:
            return "", f"Could not retrieve saved filter {filter_id}: {exc}"
    # Default — treat as raw JQL
    return filter_value, ""


def record_filter_test(server_name: str, filter_text: str, issue_count: int, error: str = ""):
    """Record the result of a filter test for the debug dump.
    
    Args:
        server_name: Name of the server tested
        filter_text: JQL filter string that was tested
        issue_count: Number of issues returned (0 if error)
        error: Error message if the test failed (empty string on success)
    """
    global _last_filter_test
    
    try:
        import datetime
        _last_filter_test = {
            "server_name": server_name,
            "filter": filter_text,
            "issue_count": issue_count,
            "timestamp": datetime.datetime.now().isoformat(),
            "success": not bool(error),
            "error": error,
        }
        
        if _is_debug():
            print(f"[DEBUG] jira_integration.record_filter_test: server={server_name}, filter={filter_text}, issues={issue_count}, error={error}")
    except Exception:
        pass


def fetch_server_capabilities(server: dict, project_key: str = "") -> dict:
    """Fetch the list of issue types and priorities available on a Jira server.

    When *project_key* is provided the issue types are fetched for that specific
    project via the createmeta endpoint (Jira DC/Server) or project issue-types
    API, which reflects the project-level configuration rather than the global
    server list.  Falls back to the global ``issue_types`` endpoint when no key
    is given or when the project-specific call fails.

    Returns a dict with:
      ``issue_types`` — sorted list of issue type name strings (empty on failure)
      ``priorities``  — sorted list of priority name strings (empty on failure)
      ``error``       — non-empty string when the server could not be reached
    """
    result: dict = {"issue_types": [], "priorities": [], "error": ""}
    try:
        jira, err = get_jira_client(server)
        if jira is None:
            result["error"] = err or "Could not connect to Jira server"
            return result

        # Try to fetch project-specific issue types when a project key is given.
        fetched_types = False
        if project_key:
            try:
                meta = jira.createmeta(
                    projectKeys=project_key,
                    expand="projects.issuetypes",
                )
                projects = (meta or {}).get("projects", [])
                if projects:
                    result["issue_types"] = sorted(
                        str(it.get("name", "")) for it in projects[0].get("issuetypes", [])
                        if it.get("name")
                    )
                    fetched_types = True
            except Exception:
                pass  # fall through to global fallback below

        if not fetched_types:
            try:
                result["issue_types"] = sorted(
                    str(getattr(it, "name", it)) for it in jira.issue_types()
                )
            except Exception as exc:
                result["error"] = str(exc)

        try:
            result["priorities"] = sorted(
                str(getattr(p, "name", p)) for p in jira.priorities()
            )
        except Exception:
            pass  # priorities endpoint is optional

        return result
    except Exception as exc:
        result["error"] = str(exc)
        return result


def get_config_summary() -> dict:
    """Return a summary of Jira configuration for the debug dump.
    
    This includes server names, URLs, and auth modes but excludes credentials.
    """
    sm = _get_settings_manager()
    if sm is None:
        return {"error": "SettingsManager not available"}
    
    servers = sm.get_jira_servers()
    server_list = []
    for s in servers:
        server_list.append({
            "name": s.get("name", "(unnamed)"),
            "url": s.get("url", ""),
            "auth_mode": s.get("auth_mode", "manual"),
            "keepass_locked": (
                s.get("auth_mode") == "keepass" and not sm.is_keepass_unlocked()
            ),
        })
    
    result = {
        "server_count": len(servers),
        "servers": server_list,
    }
    
    # Include last connection test result if available
    if _last_connection_test is not None:
        result["last_connection_test"] = _last_connection_test
    
    # Include last filter test result if available
    if _last_filter_test is not None:
        result["last_filter_test"] = _last_filter_test
    
    return result
