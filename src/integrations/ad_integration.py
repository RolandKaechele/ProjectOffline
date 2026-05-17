# ad_integration.py - Active Directory lookup and resource-sheet synchronisation.
#
# Queries corporate AD via PowerShell Get-ADUser (RSAT) to resolve user details
# (display name, email, department, SAM account name) from a name, email, or
# username.  No LDAP library dependency — PowerShell is the only requirement.
#
# Public API
# ----------
#   is_ad_available()          -> bool
#   lookup_by_name(name)       -> dict | None
#   lookup_by_email(email)     -> dict | None
#   lookup_by_username(uname)  -> dict | None
#   sync_resources(project)    -> dict   (consumed by app_debug.dump_project_state)
#
# See documentation/ad_integration.md for full details and prerequisites.

from __future__ import annotations

import json
import subprocess
import sys
from typing import Optional

from app_debug import is_debug as _is_debug  # type: ignore

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_AD_PROPERTIES = "DisplayName,mail,Department,SamAccountName,l,st,co"

# Attributes returned in the JSON blob from PowerShell; lower-cased for safety
_ATTR_DISPLAY   = "displayname"
_ATTR_MAIL      = "mail"
_ATTR_DEPT      = "department"
_ATTR_SAM       = "samaccountname"
_ATTR_CITY      = "l"
_ATTR_STATE     = "st"
_ATTR_COUNTRY   = "co"

# Default timeout (seconds) per PowerShell invocation.
# Can be overridden by SettingsManager (see _get_timeout()).
# Wildcard AD scans (e.g. mail -like '*…*') must load the module AND scan the
# directory — on a first call this easily takes 20-30 s.  10 s is too tight.
_DEFAULT_TIMEOUT = 60

# Module-level last sync result (for debug dump without re-running sync)
_last_sync_result: Optional[dict] = None

# Unbounded history of individual lookup calls (name, email, username)
_last_lookup_results: list = []  # list of {fn, input, result}  (result=None when not found)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_timeout() -> int:
    """Return the configured PowerShell timeout in seconds."""
    try:
        from settings_manager import SettingsManager  # type: ignore
        sm = SettingsManager()
        return int(sm._settings.value("ad/timeout_seconds", _DEFAULT_TIMEOUT))
    except Exception:
        pass
    return _DEFAULT_TIMEOUT


def _run_ps(command: str) -> Optional[str]:
    """Run a PowerShell command and return its stdout, or None on failure.

    The command must not rely on -File or interactive features.
    Raises no exceptions — all errors are swallowed and None is returned.

    UTF-8 encoding is forced for both the console output stream and the
    PowerShell pipeline so that special characters (ä, ü, ö, é, …) in AD
    display names, department strings, and email addresses survive the
    subprocess boundary on any Windows code page.
    """
    # Prepend encoding setup so ConvertTo-Json emits UTF-8 bytes regardless
    # of the active Windows console code page (e.g. cp850, cp1252).
    _utf8_init = (
        "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
        "$OutputEncoding = [System.Text.Encoding]::UTF8; "
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command",
             _utf8_init + command],
            capture_output=True,
            timeout=_get_timeout(),
        )
        out = result.stdout.decode("utf-8", errors="replace").strip()
        return out if out else None
    except Exception:
        return None


def _ps_query_to_dict(ps_filter_or_identity: str, use_identity: bool = False) -> Optional[dict]:
    """Execute a Get-ADUser query and parse the result as a Python dict.

    *ps_filter_or_identity* is either an AD filter expression (e.g.
    ``"DisplayName -eq 'Joe Smith'"``), or an identity string when
    *use_identity* is True.

    Returns a normalised dict with keys: display_name, email, department,
    username, city, state, country — or None when no match is found.
    """
    props = _AD_PROPERTIES
    if use_identity:
        # -Identity accepts SAMAccountName, UPN, DN, or GUID
        identity = ps_filter_or_identity.replace("'", "\\'")
        cmd = (
            f"Get-ADUser -Identity '{identity}' -Properties {props} "
            f"| Select-Object {props} "
            f"| ConvertTo-Json -Compress"
        )
    else:
        cmd = (
            f"Get-ADUser -Filter \"{ps_filter_or_identity}\" -Properties {props} "
            f"| Select-Object -First 1 {props} "
            f"| ConvertTo-Json -Compress"
        )

    raw = _run_ps(cmd)
    if not raw:
        return None

    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return None

    # PowerShell may return a list when -First 1 is omitted or a single object
    if isinstance(data, list):
        if not data:
            return None
        data = data[0]

    if not isinstance(data, dict):
        return None

    # Normalise keys to lower-case (PowerShell casing is inconsistent)
    normalised = {k.lower(): v for k, v in data.items()}

    email = normalised.get(_ATTR_MAIL) or ""
    if not email or "@" not in email:
        return None   # Entry has no mail attribute — not useful

    return {
        "display_name": normalised.get(_ATTR_DISPLAY) or "",
        "email":        email,
        "department":   normalised.get(_ATTR_DEPT) or None,
        "username":     normalised.get(_ATTR_SAM) or "",
        "city":         normalised.get(_ATTR_CITY) or None,
        "state":        normalised.get(_ATTR_STATE) or None,
        "country":      normalised.get(_ATTR_COUNTRY) or None,
    }


# ---------------------------------------------------------------------------
# Multi-result helper
# ---------------------------------------------------------------------------

def _ps_query_to_list(ps_filter: str) -> list:
    """Execute a Get-ADUser filter query and return ALL matching results.

    Unlike ``_ps_query_to_dict`` (which uses ``-First 1``), this variant
    omits the limit so every matching account is returned.

    Returns a list of normalised dicts (same schema as ``_ps_query_to_dict``).
    Entries without a valid ``mail`` attribute are silently skipped.
    """
    props = _AD_PROPERTIES
    cmd = (
        f"Get-ADUser -Filter \"{ps_filter}\" -Properties {props} "
        f"| Select-Object {props} "
        f"| ConvertTo-Json -Compress"
    )
    raw = _run_ps(cmd)
    if not raw:
        return []

    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return []

    # ConvertTo-Json wraps a single object as dict, multiple as list
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        return []

    results = []
    for item in data:
        if not isinstance(item, dict):
            continue
        normalised = {k.lower(): v for k, v in item.items()}
        email = normalised.get(_ATTR_MAIL) or ""
        if not email or "@" not in email:
            continue
        results.append({
            "display_name": normalised.get(_ATTR_DISPLAY) or "",
            "email":        email,
            "department":   normalised.get(_ATTR_DEPT) or None,
            "username":     normalised.get(_ATTR_SAM) or "",
            "city":         normalised.get(_ATTR_CITY) or None,
            "state":        normalised.get(_ATTR_STATE) or None,
            "country":      normalised.get(_ATTR_COUNTRY) or None,
        })
    return results


# ---------------------------------------------------------------------------
# Lookup history helpers
# ---------------------------------------------------------------------------

def _record_lookup(fn: str, input_val: str, result) -> None:
    """Append an entry to the lookup history list."""
    _last_lookup_results.append({"fn": fn, "input": input_val, "result": result})


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def is_ad_available() -> bool:
    """Return True when PowerShell and the ActiveDirectory module are accessible.

    Result is *not* cached so that transient domain connectivity issues are
    detected on each call.  The check is fast (<1 s on a domain-joined machine).
    """
    out = _run_ps(
        "Get-Module -ListAvailable -Name ActiveDirectory "
        "| Select-Object -First 1 -ExpandProperty Name"
    )
    return bool(out and "ActiveDirectory" in out)


def lookup_by_name(name: str) -> Optional[dict]:
    """Look up an AD user by display name.

    Accepts ``"Surname, GivenName"`` or any freeform display name string.
    Tries two strategies in order:

    1. ``DisplayName -eq '<name>'``
    2. ``Surname -eq '<surname>' -and GivenName -eq '<givenname>'`` (when the
       name contains ``", "``).

    Returns a normalised dict or None.
    """
    if not name or not name.strip():
        return None

    name = name.strip()

    # Sanitise: reject strings that contain AD filter injection characters
    _forbidden = {"(", ")", "*", "\\", "\x00"}
    if any(c in name for c in _forbidden):
        return None

    # Strategy 1 — exact DisplayName match
    safe_name = name.replace("'", "''")  # escape single quotes for PS filter
    result = _ps_query_to_dict(f"DisplayName -eq '{safe_name}'")
    if result:
        _record_lookup("lookup_by_name", name, result)
        return result

    # Strategy 2 — Surname + GivenName split
    if ", " in name:
        parts = name.split(", ", 1)
        surname    = parts[0].strip().replace("'", "''")
        givenname  = parts[1].strip().replace("'", "''")
        result = _ps_query_to_dict(
            f"Surname -eq '{surname}' -and GivenName -eq '{givenname}'"
        )
        if result:
            _record_lookup("lookup_by_name", name, result)
            return result

    _record_lookup("lookup_by_name", name, None)
    return None


def lookup_by_email(email: str) -> Optional[dict]:
    """Look up an AD user by their email address (``mail`` attribute).

    Returns a normalised dict or None.
    """
    if not email or "@" not in email:
        return None

    safe_email = email.strip().replace("'", "''")
    result = _ps_query_to_dict(f"mail -eq '{safe_email}'")
    _record_lookup("lookup_by_email", email.strip(), result)
    return result


def lookup_by_username(username: str) -> Optional[dict]:
    """Look up an AD user by SAM account name (Windows login name).

    Uses ``-Identity`` which is faster and more precise than a filter query.
    Returns a normalised dict or None.
    """
    if not username or not username.strip():
        return None

    # SAM account names must not contain shell-injection characters
    safe = username.strip()
    _forbidden = {";", "&", "|", "`", "$", "(", ")", "<", ">", "\x00"}
    if any(c in safe for c in _forbidden):
        return None

    result = _ps_query_to_dict(safe, use_identity=True)
    _record_lookup("lookup_by_username", safe, result)
    return result


def sync_resources(project) -> dict:
    """Synchronise AD data into the MPXJ project resource sheet.

    For every resource that has a name but no email address, performs a
    ``lookup_by_name()`` and — when found — writes the email address and
    department back into the resource object.

    Also writes all found AD details into a ``_ad_data`` attribute on the
    resource object so that other modules (e.g. Jira sync) can retrieve them
    without a second AD query.

    Returns a summary dict::

        {
            "total":   int,
            "updated": int,
            "skipped": int,
            "errors":  [{"resource": str, "error": str}, ...]
        }

    The returned dict is stored in ``_last_sync_result`` for the debug dump.
    """
    global _last_sync_result

    summary = {"total": 0, "updated": 0, "skipped": 0, "errors": []}

    if project is None:
        _last_sync_result = summary
        return summary

    try:
        resources = list(project.getResources())
    except Exception as exc:
        summary["errors"].append({"resource": "<getResources>", "error": str(exc)})
        _last_sync_result = summary
        return summary

    for resource in resources:
        try:
            name = resource.getName()
            if name is None:
                continue
            name = str(name).strip()
            if not name:
                continue

            summary["total"] += 1

            # Skip resources that already have an email
            existing_email = resource.getEmailAddress()
            if existing_email and str(existing_email).strip():
                summary["skipped"] += 1
                continue

            ad_entry = lookup_by_name(name)
            if ad_entry is None:
                summary["skipped"] += 1
                if _is_debug():
                    print(f"[AD] Not found in AD: {name!r}")
                continue

            # Write email and department into the MPXJ resource object
            try:
                resource.setEmailAddress(ad_entry["email"])
            except Exception:
                pass

            # Attach the full AD dict as a Python-side attribute for other modules
            try:
                resource._ad_data = ad_entry  # type: ignore[attr-defined]
            except Exception:
                pass

            summary["updated"] += 1
            if _is_debug():
                print(
                    f"[AD] Updated {name!r}: email={ad_entry['email']!r}"
                    f" dept={ad_entry['department']!r}"
                )

        except Exception as exc:
            resource_name = "<unknown>"
            try:
                resource_name = str(resource.getName())
            except Exception:
                pass
            summary["errors"].append({"resource": resource_name, "error": str(exc)})

    _last_sync_result = summary
    return summary


def get_last_sync_result() -> Optional[dict]:
    """Return the result of the most recent ``sync_resources()`` call, or None."""
    return _last_sync_result


def get_last_lookup_results() -> list:
    """Return a copy of the full lookup history list.

    Each entry is a dict::

        {"fn": str, "input": str, "result": dict | None}
    """
    return list(_last_lookup_results)


# ---------------------------------------------------------------------------
# Multi-result public API
# ---------------------------------------------------------------------------

def lookup_by_name_all(name: str) -> list:
    """Look up ALL AD users whose DisplayName contains *name* (case-insensitive wildcard).

    Falls back to a Surname/GivenName split search when *name* contains ``", "``.
    Returns a (possibly empty) list of normalised dicts.
    """
    if not name or not name.strip():
        return []
    name = name.strip()
    _forbidden = {"(", ")", "*", "\\", "\x00"}
    if any(c in name for c in _forbidden):
        return []
    safe = name.replace("'", "''")
    results = _ps_query_to_list(f"DisplayName -like '*{safe}*'")
    if not results and ", " in name:
        parts = name.split(", ", 1)
        surname   = parts[0].strip().replace("'", "''")
        givenname = parts[1].strip().replace("'", "''")
        results = _ps_query_to_list(
            f"Surname -like '*{surname}*' -and GivenName -like '*{givenname}*'"
        )
    _record_lookup("lookup_by_name_all", name, results or None)
    return results


def lookup_by_email_all(email: str) -> list:
    """Look up ALL AD users whose mail attribute contains *email* (wildcard).

    Returns a (possibly empty) list of normalised dicts.
    """
    if not email:
        return []
    email = email.strip()
    # Require at least a '@' to avoid full-domain table scans
    if "@" not in email:
        return []
    _forbidden = {"(", ")", "*", "\\", "\x00"}
    if any(c in email for c in _forbidden):
        return []
    safe = email.replace("'", "''")

    # Fast path: try an exact indexed match first (mail -eq is case-insensitive
    # in AD and uses an index, so it returns in <1 s).
    exact = _ps_query_to_dict(f"mail -eq '{safe}'")
    if exact:
        _record_lookup("lookup_by_email_all", email, [exact])
        return [exact]

    # Slow path: wildcard scan (no index, may take 20-30 s on large directories).
    results = _ps_query_to_list(f"mail -like '*{safe}*'")
    _record_lookup("lookup_by_email_all", email, results or None)
    return results


def lookup_by_username_all(username: str) -> list:
    """Look up ALL AD users whose SamAccountName contains *username* (wildcard).

    Returns a (possibly empty) list of normalised dicts.
    """
    if not username or not username.strip():
        return []
    safe_input = username.strip()
    _forbidden = {";", "&", "|", "`", "$", "(", ")", "<", ">", "\x00", "*", "\\"}
    if any(c in safe_input for c in _forbidden):
        return []
    safe = safe_input.replace("'", "''")

    # Fast path: -Identity uses an indexed lookup and returns in <1 s.
    exact = _ps_query_to_dict(safe_input, use_identity=True)
    if exact:
        _record_lookup("lookup_by_username_all", safe_input, [exact])
        return [exact]

    # Slow path: wildcard filter (no index, may take 20-30 s on large directories).
    results = _ps_query_to_list(f"SamAccountName -like '*{safe}*'")
    _record_lookup("lookup_by_username_all", safe_input, results or None)
    return results


def get_thumbnail(username: str) -> Optional[bytes]:
    """Fetch the ``thumbnailPhoto`` binary from AD for the given SAM account name.

    Returns the raw JPEG/PNG bytes on success, or ``None`` when the attribute
    is absent or the request fails.
    """
    if not username or not username.strip():
        return None
    safe_input = username.strip()
    _forbidden = {";", "&", "|", "`", "$", "(", ")", "<", ">", "\x00", "*", "\\"}
    if any(c in safe_input for c in _forbidden):
        return None
    safe = safe_input.replace("'", "\\'")
    cmd = (
        f"$u = Get-ADUser -Identity '{safe}' -Properties thumbnailPhoto; "
        f"if ($u.thumbnailPhoto) "
        f"{{ [System.Convert]::ToBase64String($u.thumbnailPhoto) }}"
    )
    raw = _run_ps(cmd)
    if not raw:
        return None
    try:
        import base64
        return base64.b64decode(raw.strip())
    except Exception:
        return None


# ---------------------------------------------------------------------------
# AD Group search API
# ---------------------------------------------------------------------------

_AD_GROUP_PROPERTIES = "Name,Description,DistinguishedName,GroupCategory,GroupScope,SamAccountName"

_ATTR_GROUP_NAME   = "name"
_ATTR_GROUP_DESC   = "description"
_ATTR_GROUP_DN     = "distinguishedname"
_ATTR_GROUP_CAT    = "groupcategory"
_ATTR_GROUP_SCOPE  = "groupscope"
_ATTR_GROUP_SAM    = "samaccountname"


def search_groups(query: str) -> list:
    """Search Active Directory for groups whose name contains *query*.

    Returns a (possibly empty) list of dicts with keys:
      name, description, dn (distinguished name), category, scope, sam_name.

    Security: the query is sanitised before being embedded in the PowerShell
    command.  Characters commonly used for injection are rejected.
    """
    if not query or not query.strip():
        return []
    safe_input = query.strip()
    _forbidden = {"(", ")", "\\", "\x00", ";", "&", "|", "`", "$"}
    if any(c in safe_input for c in _forbidden):
        return []
    safe = safe_input.replace("'", "''")
    props = _AD_GROUP_PROPERTIES
    cmd = (
        f"Get-ADGroup -Filter \"Name -like '*{safe}*'\" -Properties {props} "
        f"| Select-Object {props} "
        f"| ConvertTo-Json -Compress"
    )
    raw = _run_ps(cmd)
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return []
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        return []
    results = []
    for item in data:
        if not isinstance(item, dict):
            continue
        n = {k.lower(): v for k, v in item.items()}
        name = n.get(_ATTR_GROUP_NAME) or n.get(_ATTR_GROUP_SAM) or ""
        if not name:
            continue
        results.append({
            "name":        name,
            "description": n.get(_ATTR_GROUP_DESC) or "",
            "dn":          n.get(_ATTR_GROUP_DN)   or "",
            "category":    n.get(_ATTR_GROUP_CAT)  or "",
            "scope":       n.get(_ATTR_GROUP_SCOPE) or "",
            "sam_name":    n.get(_ATTR_GROUP_SAM)  or name,
        })
    return results


def get_group_members(group_name_or_dn: str) -> list:
    """Return all enabled AD users who are (direct) members of *group_name_or_dn*.

    *group_name_or_dn* may be a SAM account name, a distinguished name, or a
    plain group display name.  Only members that have a valid ``mail`` attribute
    are included in the result — entries without e-mail are silently skipped.

    Returns a list of normalised user dicts (same schema as ``_ps_query_to_dict``).
    """
    if not group_name_or_dn or not group_name_or_dn.strip():
        return []
    safe_input = group_name_or_dn.strip()
    _forbidden = {";", "&", "|", "`", "$", "\x00"}
    if any(c in safe_input for c in _forbidden):
        return []
    safe = safe_input.replace("'", "''")
    props = _AD_PROPERTIES
    # Get-ADGroupMember retrieves direct members; pipe through Get-ADUser to
    # resolve full user attributes (department, mail, etc.) and filter to
    # enabled user objects only.
    cmd = (
        f"Get-ADGroupMember -Identity '{safe}' -Recursive "
        f"| Where-Object {{ $_.objectClass -eq 'user' }} "
        f"| Get-ADUser -Properties {props} "
        f"| Where-Object {{ $_.Enabled -eq $true }} "
        f"| Select-Object {props} "
        f"| ConvertTo-Json -Compress"
    )
    raw = _run_ps(cmd)
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return []
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        return []
    results = []
    for item in data:
        if not isinstance(item, dict):
            continue
        normalised = {k.lower(): v for k, v in item.items()}
        email = normalised.get(_ATTR_MAIL) or ""
        if not email or "@" not in email:
            continue
        results.append({
            "display_name": normalised.get(_ATTR_DISPLAY) or "",
            "email":        email,
            "department":   normalised.get(_ATTR_DEPT) or None,
            "username":     normalised.get(_ATTR_SAM)  or "",
            "city":         normalised.get(_ATTR_CITY) or None,
            "state":        normalised.get(_ATTR_STATE) or None,
            "country":      normalised.get(_ATTR_COUNTRY) or None,
        })
    return results
