# confluence_calendar_integration.py - Fetch Confluence Team Calendar events and apply
# them as non-working exceptions to MPXJ project / resource calendars.
#
# Authentication
# --------------
# Uses Playwright/Chromium SSO — no passwords stored anywhere.
# - Valid saved session  → headless, instant, no browser window.
# - Expired / first run → opens a Chromium window; user completes SSO once;
#                         state saved to ~/.confluence_playwright_state.json
#                         (owner-only permissions enforced on save).
#
# Enterprise Custom Fields (per-project)
# ---------------------------------------
# All keys use the CALENDAR prefix.  Create them via:
#   Project → Project Information → Custom Fields → Properties
#
#   CALENDAR Base URL     – Confluence server base URL
#   CALENDAR Space Key    – Space key to query (e.g. PROJ)
#   CALENDAR Timezone     – Optional: IANA timezone (default: Europe/Berlin)
#   CALENDAR Days Ahead   – Optional: sync window in days (default: 365)

from __future__ import annotations

import re as _re
import subprocess
import sys
import time
from datetime import date, timedelta
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse as _urlparse

# ---------------------------------------------------------------------------
# Public constants — key names used in project custom properties (sidecar JSON)
# ---------------------------------------------------------------------------
CONFLUENCE_BASE_URL_PROP   = "CALENDAR Base URL"
CONFLUENCE_SPACE_KEY_PROP  = "CALENDAR Space Key"
CONFLUENCE_TIMEZONE_PROP   = "CALENDAR Timezone"
CONFLUENCE_DAYS_AHEAD_PROP = "CALENDAR Days Ahead"

# Defaults used when the custom field is absent from the project
_DEFAULT_TIMEZONE   = "Europe/Berlin"
_DEFAULT_DAYS_AHEAD = 365

# Playwright SSO session state (owner-readable only)
_STATE_FILE = Path.home() / ".confluence_playwright_state.json"

try:
    import requests as _requests # type: ignore
    _REQUESTS_OK = True
except ImportError:
    _REQUESTS_OK = False

try:
    from playwright.sync_api import sync_playwright as _sync_playwright # type: ignore
    from playwright.sync_api import TimeoutError as _PlaywrightTimeout # type: ignore
    _PLAYWRIGHT_OK = True
except ImportError:
    _PLAYWRIGHT_OK = False

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_DATE_FMT = "%Y-%m-%d"
_RELEVANT_TYPES = {"leaves", "custom"}
_RELEVANT_KEYWORDS = {"holiday", "leave", "vacation", "feiertag", "urlaub"}

from app_debug import is_debug as _is_debug  # type: ignore


# ---------------------------------------------------------------------------
# Playwright SSO helpers
# ---------------------------------------------------------------------------

def _restrict_file_permissions(path: Path) -> None:
    """Restrict *path* to owner-only access (mode 600 on POSIX, icacls on Windows)."""
    if sys.platform == 'win32':
        try:
            import getpass
            user = getpass.getuser()
            # Remove all inherited/other permissions, then grant current user Full Control only
            subprocess.run(
                ['icacls', str(path), '/inheritance:r', '/grant:r', f'{user}:(F)'],
                check=True, capture_output=True,
            )
        except Exception:
            pass
    else:
        try:
            path.chmod(0o600)
        except Exception:
            pass


def _validate_base_url(base_url: str) -> str:
    """Validate that *base_url* is an https:// URL and return the normalised form.

    Raises ValueError for non-HTTPS or malformed URLs.
    """
    parsed = _urlparse(base_url)
    if parsed.scheme != 'https':
        raise ValueError(
            f"CALENDAR Base URL must use HTTPS (got '{parsed.scheme or base_url}').\n"
            "Only secure connections are allowed to protect SSO session cookies."
        )
    if not parsed.netloc:
        raise ValueError(f"CALENDAR Base URL is not a valid URL: '{base_url}'")
    return base_url


def _playwright_session(ctx, base_url: str) -> "_requests.Session":
    """Build a requests.Session from a Playwright browser context's cookies."""
    session = _requests.Session()
    host = _urlparse(base_url).netloc
    for c in ctx.cookies():
        session.cookies.set(c["name"], c["value"], domain=host)
    session.headers.update({
        "User-Agent":       "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept":           "application/json",
        "X-Requested-With": "XMLHttpRequest",
    })
    return session


def _autofill_microsoft_sso(page, username: str, password: str) -> bool:
    """Fill Microsoft AAD login fields on the currently open *page*.

    Handles the standard Microsoft Online login flow:
      1. E-mail / username field  →  fill + Next
      2. Password field           →  fill + Sign in

    After Sign in, any MFA challenge (Authenticator, TOTP, …) is left for
    the user to complete manually.

    Returns True when autofill was performed, False when the page does not
    look like a Microsoft login page or selectors were not found in time.
    """
    try:
        if "login.microsoftonline.com" not in page.url:
            return False

        # --- Step 1: e-mail ---
        email_sel = "input[type='email'], #i0116"
        try:
            page.wait_for_selector(email_sel, timeout=8_000)
            page.fill(email_sel, username)
            # 'Next' button
            next_sel = "#idSIButton9, input[type='submit']"
            page.wait_for_selector(next_sel, timeout=5_000)
            page.click(next_sel)
        except Exception:
            return False

        # --- Step 2: password ---
        pwd_sel = "input[type='password'], #i0118"
        try:
            page.wait_for_selector(pwd_sel, timeout=10_000)
            page.fill(pwd_sel, password)
            # 'Sign in' button
            signin_sel = "#idSIButton9, input[type='submit']"
            page.wait_for_selector(signin_sel, timeout=5_000)
            page.click(signin_sel)
        except Exception:
            return False

        return True
    except Exception:
        return False


def _try_playwright_auth(
    base_url: str,
    keepass_creds: "tuple[str, str] | None" = None,
) -> "tuple[_requests.Session, str] | None":
    """Authenticate via Playwright/Chromium SSO.

    Tries the cached headless session first; opens a browser window for SSO
    when the session is expired or missing.

    When *keepass_creds* is provided (username, password), the Microsoft AAD
    login page is auto-filled.  Any MFA step (TOTP, Authenticator push, …)
    is left for the user to complete in the visible browser window.

    Returns (session, display_name) or None on failure.
    """
    verify_url = f"{base_url.rstrip('/')}/rest/api/user/current"
    base_re = _re.compile(_re.escape(base_url))

    try:
        with _sync_playwright() as pw:
            # --- Try cached headless session ---
            if _STATE_FILE.exists():
                browser = None
                try:
                    browser = pw.chromium.launch(headless=True)
                    ctx = browser.new_context(storage_state=str(_STATE_FILE))
                    page = ctx.new_page()
                    resp = page.goto(verify_url, timeout=20_000)
                    if resp and resp.ok:
                        data = resp.json()
                        name = data.get("displayName") or data.get("name")
                        if name:
                            session = _playwright_session(ctx, base_url)
                            browser.close()
                            return session, str(name)
                except Exception:
                    pass
                finally:
                    try:
                        browser.close()
                    except Exception:
                        pass

            # --- Open visible browser for SSO login ---
            browser = None
            try:
                browser = pw.chromium.launch(headless=False)
                ctx = browser.new_context()
                page = ctx.new_page()
                page.goto(base_url, timeout=30_000)
                # Auto-fill Microsoft AAD login if credentials were supplied
                if keepass_creds and "login.microsoftonline.com" in page.url:
                    _autofill_microsoft_sso(page, keepass_creds[0], keepass_creds[1])
                if not page.url.startswith(base_url):
                    page.wait_for_url(base_re, timeout=300_000)  # extra time for MFA
                page.wait_for_load_state("domcontentloaded", timeout=15_000)
                ctx.storage_state(path=str(_STATE_FILE))
                _restrict_file_permissions(_STATE_FILE)
                session = _playwright_session(ctx, base_url)
                browser.close()
                check = session.get(verify_url, timeout=20, verify=True)
                if check.ok:
                    data = check.json()
                    name = data.get("displayName") or data.get("name") or "unknown"
                    return session, str(name)
                return None
            except _PlaywrightTimeout:
                return None
            except Exception:
                return None
            finally:
                try:
                    browser.close()
                except Exception:
                    pass
    except Exception:
        return None


def clear_saved_session() -> None:
    """Delete the saved Playwright SSO session (forces re-authentication on next sync)."""
    if _STATE_FILE.exists():
        _STATE_FILE.unlink()


def _flatten_calendars(raw_items: list) -> list[dict]:
    """Flatten the nested subcalendars response into a plain list."""
    result = []
    for item in raw_items:
        sub = item.get("subCalendar") or {}
        if sub and sub.get("type") != "parent":
            result.append(sub)
        for child in item.get("childSubCalendars") or []:
            child_sub = child.get("subCalendar") or {}
            if child_sub and child_sub.get("type") != "parent":
                result.append(child_sub)
    return result


def _fetch_subcalendars(
    session: "_requests.Session", base_url: str, space_key: str
) -> list[dict]:
    """Fetch all sub-calendars for *space_key*, returned as a flat list."""
    ts = int(time.time() * 1000)
    url = (
        f"{base_url.rstrip('/')}/rest/calendar-services/1.0/calendar/subcalendars.json"
        f"?calendarContext=spaceCalendars&viewingSpaceKey={space_key}&_={ts}"
    )
    resp = session.get(url, timeout=30, verify=True)
    resp.raise_for_status()
    data = resp.json()
    raw = (
        data.get("payload")
        or data.get("subCalendars")
        or data.get("calendars")
        or (data if isinstance(data, list) else None)
        or []
    )
    return _flatten_calendars(raw)


def _filter_relevant(calendars: list[dict]) -> list[dict]:
    """Return only holiday / leave / vacation sub-calendars."""
    result = []
    for cal in calendars:
        cal_type = (cal.get("type") or "").lower()
        cal_name = (cal.get("name") or "").lower()
        if cal_type in _RELEVANT_TYPES or any(kw in cal_name for kw in _RELEVANT_KEYWORDS):
            result.append(cal)
    return result


def _fetch_events(
    session: "_requests.Session",
    base_url: str,
    calendar_id: str,
    start: date,
    end: date,
    timezone: str,
) -> list[dict]:
    """Fetch events for a single sub-calendar within the given date range."""
    url = f"{base_url.rstrip('/')}/rest/calendar-services/1.0/calendar/events.json"
    params = {
        "subCalendarId":  calendar_id,
        "start":          start.strftime(_DATE_FMT),
        "end":            end.strftime(_DATE_FMT),
        "userTimezoneId": timezone,
    }
    resp = session.get(url, params=params, timeout=30, verify=True)
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, list):
        return data
    return data.get("events") or data.get("payload") or []


def _parse_date(value: Optional[str]) -> Optional[date]:
    """Parse an ISO-8601 date string; returns None on failure."""
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Project calendar application
# ---------------------------------------------------------------------------

def _apply_to_project(
    project,
    holiday_events: list[dict],
    vacation_events: list[dict],
    sync_start: Optional[date] = None,
    sync_end: Optional[date] = None,
    prune_before: Optional[date] = None,
) -> tuple[int, int, int, int, int]:
    """Write calendar exceptions into the MPXJ project.

    holiday_events  → project default calendar (non-working exceptions)
    vacation_events → per-resource calendars matched by userName/title

    *sync_start* / *sync_end* define the forward-looking window:  any vacation
    exception currently on a resource calendar whose start date falls within
    that window but is absent from the new *vacation_events* is removed first
    (stale-entry cleanup — e.g. a vacation deleted in Confluence).

    *prune_before* — when set, any calendar exception (holiday **or** vacation)
    whose **end** date is strictly before this date is deleted from every
    calendar.  Pass ``today - timedelta(days=30)`` to drop entries that
    finished more than one month ago.

    Returns (n_holidays_added, n_vacations_added, n_vacations_removed, n_pruned).
    """
    import jpype  # type: ignore
    LocalDate = jpype.JClass("java.time.LocalDate")

    def _ld_to_date(ld) -> Optional[date]:
        """Convert a Java LocalDate to a Python date; returns None on error."""
        try:
            return date(int(ld.getYear()), int(ld.getMonthValue()), int(ld.getDayOfMonth()))
        except Exception:
            return None

    def _prune_expired(cal) -> int:
        """Remove exceptions whose end date is strictly before *prune_before*."""
        if prune_before is None:
            return 0
        exc_list = cal.getCalendarExceptions()
        if exc_list is None:
            return 0
        to_remove = []
        for exc in exc_list:
            end_d = _ld_to_date(exc.getToDate())
            if end_d is None:
                end_d = _ld_to_date(exc.getFromDate())
            if end_d is not None and end_d < prune_before:
                to_remove.append(exc)
        if to_remove:
            try:
                from java.util import ArrayList as _JArrayList  # type: ignore
                _rm_list = _JArrayList()
                for _exc in to_remove:
                    _rm_list.add(_exc)
                exc_list.removeAll(_rm_list)
            except Exception:
                pass
        return len(to_remove)

    def _remove_window_exceptions(cal) -> int:
        """Delete all exceptions on *cal* whose start falls in [sync_start, sync_end]."""
        if sync_start is None or sync_end is None:
            return 0
        exc_list = cal.getCalendarExceptions()
        if exc_list is None:
            return 0
        to_keep = []
        removed = 0
        for exc in exc_list:
            d = _ld_to_date(exc.getFromDate())
            if d is not None and sync_start <= d <= sync_end:
                removed += 1
            else:
                to_keep.append(exc)
        if removed:
            try:
                exc_list.clear()
                for exc in to_keep:
                    exc_list.add(exc)
            except Exception:
                # Fallback: removeAll to avoid JPype _jcollection.remove() recursion
                try:
                    from java.util import ArrayList as _JArrayList  # type: ignore
                    _rm_list = _JArrayList()
                    for exc in list(exc_list):
                        d = _ld_to_date(exc.getFromDate())
                        if d is not None and sync_start <= d <= sync_end:
                            _rm_list.add(exc)
                    if _rm_list.size() > 0:
                        exc_list.removeAll(_rm_list)
                except Exception:
                    pass
        return removed

    n_holidays = 0
    n_vacations = 0
    n_vacations_removed = 0
    n_pruned = 0
    n_resources_created = 0

    # ---- Public holidays → project default calendar ----
    default_cal = project.getDefaultCalendar()
    if default_cal is not None:
        n_pruned += _prune_expired(default_cal)
        _remove_window_exceptions(default_cal)
        # Build set of existing exception date ranges to prevent duplicates
        _existing_exc = set()
        _exc_list = default_cal.getCalendarExceptions()
        if _exc_list is not None:
            for _ex in _exc_list:
                _existing_exc.add((_ld_to_date(_ex.getFromDate()), _ld_to_date(_ex.getToDate())))
        for ev in holiday_events:
            start = _parse_date(ev.get("start") or ev.get("startDate"))
            end   = _parse_date(ev.get("end")   or ev.get("endDate"))
            if start is None:
                continue
            if end is None or end < start:
                end = start
            # Skip multi-day spans — genuine public holidays are single days
            # (start == end).  Multi-day spans are school-holiday blocks
            # ("Schulferien") or collective closures that do NOT belong in the
            # project default calendar (they would grey out entire weeks for
            # all resources).  Even a 2-day span (days == 1) must be skipped
            # because Confluence can produce them for short Schulferien blocks
            # or events where the calendar tool uses an exclusive end date.
            if (end - start).days > 0:
                continue
            if (start, end) in _existing_exc:
                continue
            try:
                exc_obj = default_cal.addCalendarException(
                    LocalDate.of(start.year, start.month, start.day),
                    LocalDate.of(end.year,   end.month,   end.day),
                )
                ev_title = str(
                    ev.get("title") or ev.get("summary") or ""
                ).strip()
                if ev_title:
                    exc_obj.setName(ev_title)
                _existing_exc.add((start, end))
                n_holidays += 1
            except Exception:
                pass

    # ---- Vacations → per-resource calendars ----
    resources = [r for r in project.getResources() if r.getName() is not None]
    name_to_res = {str(r.getName()).lower(): r for r in resources}

    # Group vacation events by matched resource
    res_to_events: dict = {}
    for ev in vacation_events:
        user_raw = (
            ev.get("userName") or ev.get("user") or ev.get("title") or ""
        )
        # Confluence sometimes stores display names with ';' as the
        # surname/forename separator — normalise to the expected ',' form.
        user_raw = user_raw.replace(";", ",").strip()
        user_lower = user_raw.lower().strip()
        res = name_to_res.get(user_lower)
        match_type = "exact" if res is not None else None
        if res is None and user_lower:
            # Partial / substring match as fallback
            for rname, r in name_to_res.items():
                if user_lower in rname or rname in user_lower:
                    res = r
                    match_type = "partial"
                    break
        # On a partial match, rename the project resource to the full Confluence
        # name so subsequent events find it by exact match and the project shows
        # the correct full name.  Only rename when the new key is not already
        # taken (avoids colliding two distinct resources onto the same name).
        if match_type == "partial":
            new_name = user_raw.strip()
            new_name_lower = new_name.lower()
            if new_name_lower not in name_to_res:
                old_name_lower = str(res.getName()).lower()
                res.setName(new_name)
                name_to_res.pop(old_name_lower, None)
                name_to_res[new_name_lower] = res
        # Auto-create a resource when the name from Confluence has no match.
        if res is None and user_raw.strip():
            res = project.addResource()
            res.setName(user_raw.strip())
            try:
                from org.mpxj import Availability  # type: ignore
                from java.time import LocalDateTime  # type: ignore
                from java.lang import Double as JDouble  # type: ignore
                res.getAvailability().add(Availability(
                    LocalDateTime.of(1900, 1, 1, 0, 0),
                    LocalDateTime.of(2100, 12, 31, 23, 59),
                    JDouble.valueOf(100.0),   # 100% availability (percentage scale, consistent with XML-loaded resources)
                ))
            except Exception:
                pass
            name_to_res[user_lower] = res
            match_type = "new"
            n_resources_created += 1

        # TODO DEBUG – remove before release
        if _is_debug():
            start_dbg = ev.get("start") or ev.get("startDate") or "?"
            end_dbg   = ev.get("end")   or ev.get("endDate")   or "?"
            if res is not None:
                print(f"[CAL DEBUG] MATCH ({match_type:7s}): '{user_raw}' → '{res.getName()}'  {start_dbg} – {end_dbg}")
            else:
                print(f"[CAL DEBUG] NO MATCH:          '{user_raw}'  {start_dbg} – {end_dbg}  (no name — skipped)")
        if res is None:
            continue
        res_id = id(res)
        if res_id not in res_to_events:
            res_to_events[res_id] = (res, [])
        res_to_events[res_id][1].append(ev)

    # Find resources that have stale window exceptions but no new vacation events
    # (e.g. a person whose entire vacation was cancelled / deleted in Confluence).
    # Also mark resources that have only expired entries so pruning runs on them.
    for r in resources:
        r_id = id(r)
        if r_id in res_to_events:
            continue
        cal = r.getCalendar()
        if cal is None:
            continue
        exc_list = cal.getCalendarExceptions()
        if exc_list is None:
            continue
        needs_processing = False
        for exc in exc_list:
            d = _ld_to_date(exc.getFromDate())
            if d is None:
                continue
            # Stale window entry?
            if sync_start is not None and sync_end is not None and sync_start <= d <= sync_end:
                needs_processing = True
                break
            # Expired entry?
            end_d = _ld_to_date(exc.getToDate())
            if end_d is None:
                end_d = d
            if prune_before is not None and end_d < prune_before:
                needs_processing = True
                break
        if needs_processing:
            res_to_events[r_id] = (r, [])  # no new events, but cleanup needed

    # Build a set of calendar UIDs already linked to a resource — used to
    # identify orphaned calendars (created by a previous sync that removed
    # the matching resource).
    _res_cal_uids = set()
    for _r in project.getResources():
        _rc_uid_raw = _r.getCalendarUniqueID()
        if _rc_uid_raw is not None:
            try:
                _res_cal_uids.add(int(str(_rc_uid_raw)))
            except Exception:
                pass

    def _next_calendar_uid():
        """Return the next free calendar UID so setCalendar stores it correctly."""
        existing = set()
        for _c in project.getCalendars():
            _u = _c.getUniqueID()
            if _u is not None:
                try:
                    existing.add(int(str(_u)))
                except Exception:
                    pass
        uid = (max(existing) + 1) if existing else 1
        while uid in existing:
            uid += 1
        return uid

    # Process each affected resource: remove stale exceptions, then add new ones.
    for res_id, (res, evts) in res_to_events.items():
        # Use getCalendarUniqueID() — getCalendar() resolves by UID and will return
        # None if the calendar was created with a null UID (before _sanitize_calendar_uids
        # runs), so the raw UID field is the reliable check.
        cal_uid_raw = res.getCalendarUniqueID()
        cal = res.getCalendar() if cal_uid_raw is not None else None

        if cal is None and cal_uid_raw is not None:
            # Calendar UID was set but the calendar object can't be found — skip
            pass

        if cal is None:
            if not evts:
                continue
            # Look for an orphaned calendar from a previous sync run that had
            # the resource deleted by the old _remove_unassigned_enterprise_resources.
            cal_name = f"{res.getName()} Calendar"
            try:
                existing_cal = project.getCalendarByName(cal_name)
            except Exception:
                existing_cal = None
            if existing_cal is not None:
                try:
                    _ec_uid = existing_cal.getUniqueID()
                    if _ec_uid is None or int(str(_ec_uid)) not in _res_cal_uids:
                        cal = existing_cal   # reuse the orphaned calendar
                except Exception:
                    pass
            if cal is None:
                # Create a new calendar derived from the project default
                cal = project.addCalendar()
                cal.setName(cal_name)
                parent = project.getDefaultCalendar()
                if parent is not None:
                    cal.setParent(parent)
                else:
                    cal.addDefaultCalendarDays()
                    cal.addDefaultCalendarHours()
            # Assign a UID to the calendar NOW before setCalendar(), because
            # setCalendar() stores getUniqueID() — if that's None, getCalendar()
            # will always return None and _remove_unassigned_enterprise_resources
            # will delete this resource during save.
            if cal.getUniqueID() is None:
                try:
                    from java.lang import Integer as _JInt  # type: ignore
                    cal.setUniqueID(_JInt(_next_calendar_uid()))
                except Exception:
                    pass
            res.setCalendar(cal)
        else:
            n_pruned += _prune_expired(cal)
            n_vacations_removed += _remove_window_exceptions(cal)

        # Build set of existing exception date ranges to prevent duplicates
        _vac_existing = set()
        _vac_exc_list = cal.getCalendarExceptions()
        if _vac_exc_list is not None:
            for _ex in _vac_exc_list:
                _vac_existing.add((_ld_to_date(_ex.getFromDate()), _ld_to_date(_ex.getToDate())))
        for ev in evts:
            start = _parse_date(ev.get("start") or ev.get("startDate"))
            end   = _parse_date(ev.get("end")   or ev.get("endDate"))
            if start is None:
                continue
            if end is None or end < start:
                end = start
            if (start, end) in _vac_existing:
                continue
            try:
                vac_exc = cal.addCalendarException(
                    LocalDate.of(start.year, start.month, start.day),
                    LocalDate.of(end.year,   end.month,   end.day),
                )
                vac_title = str(
                    ev.get("title") or ev.get("summary") or "Vacation"
                ).strip() or "Vacation"
                vac_exc.setName(vac_title)
                _vac_existing.add((start, end))
                n_vacations += 1
                # TODO DEBUG – remove before release
                if _is_debug():
                    print(f"[CAL DEBUG] ADDED  exception: {res.getName()!s:30s}  {start} – {end}")
            except Exception as _dbg_exc:
                # TODO DEBUG – remove before release
                if _is_debug():
                    print(f"[CAL DEBUG] FAILED exception: {res.getName()!s:30s}  {start} – {end}  → {_dbg_exc}")

    return n_holidays, n_vacations, n_vacations_removed, n_pruned, n_resources_created


# ---------------------------------------------------------------------------
# Public helper: read Confluence settings from project custom properties
# ---------------------------------------------------------------------------

def _get_enterprise_prop(project, key: str) -> Optional[str]:
    """Return a stripped string value for *key* from the project's custom fields.

    Checks two sources in order:
    1. MPXJ custom properties (``getCustomProperties()``) — populated from the
       sidecar JSON by ``_patch_load_custom_properties`` on file open.  This is
       the preferred storage for Confluence settings because custom properties
       are saved in a sidecar JSON file and never written into the MS Project
       XML, so they cannot crash MS Project on import.
    2. Enterprise custom fields (``UserDefinedField``) on the project summary
       task (UID=0) — legacy path for projects that stored settings as XML
       enterprise attributes before this was changed.
    """
    # -- 1. Custom properties (sidecar JSON) ---------------------------------
    try:
        cp = project.getProjectProperties().getCustomProperties()
        if cp is not None:
            raw = cp.get(key)
            if raw is not None:
                val = str(raw).strip()
                if val not in ('null', 'None', ''):
                    return val
    except Exception:
        pass

    # -- 2. Enterprise custom fields (legacy / MS Project Server fields) -----
    try:
        from org.mpxj import UserDefinedField  # type: ignore

        summary_task = None
        for t in project.getTasks():
            try:
                if int(str(t.getUniqueID())) == 0:
                    summary_task = t
                    break
            except Exception:
                pass

        if summary_task is None:
            return None

        for cf in project.getCustomFields():
            ft = cf.getFieldType()
            if ft is None:
                continue
            if str(ft.getFieldTypeClass()) != 'TASK':
                continue
            if not isinstance(ft, UserDefinedField):
                continue
            alias = str(cf.getAlias()).strip() if cf.getAlias() else ''
            if alias != key:
                continue
            raw = summary_task.getCachedValue(ft)
            if raw is None:
                return None
            val = str(raw).strip()
            return val if val not in ('null', 'None', '') else None
    except Exception:
        pass
    return None


def get_project_base_url(project) -> Optional[str]:
    """Read CALENDAR Base URL from the project's enterprise custom fields."""
    val = _get_enterprise_prop(project, CONFLUENCE_BASE_URL_PROP)
    return val.rstrip("/") if val else None


def get_project_space_key(project) -> Optional[str]:
    """Read CALENDAR Space Key from the project's enterprise custom fields."""
    return _get_enterprise_prop(project, CONFLUENCE_SPACE_KEY_PROP)


def get_project_timezone(project) -> str:
    """Read CALENDAR Timezone from enterprise fields, falling back to the default."""
    return _get_enterprise_prop(project, CONFLUENCE_TIMEZONE_PROP) or _DEFAULT_TIMEZONE


def get_project_days_ahead(project) -> int:
    """Read CALENDAR Days Ahead from enterprise fields, falling back to the default."""
    raw = _get_enterprise_prop(project, CONFLUENCE_DAYS_AHEAD_PROP)
    if raw:
        try:
            val = int(raw)
            if 1 <= val <= 3650:
                return val
        except ValueError:
            pass
    return _DEFAULT_DAYS_AHEAD


# ---------------------------------------------------------------------------
# Public sync class
# ---------------------------------------------------------------------------

class ConfluenceCalendarSync:
    """Fetch Confluence calendar events and apply them to an MPXJ project.

    Authentication is via Playwright/Chromium SSO — no passwords needed.
    Both the Base URL and Space Key are read per-project from the project’s
    custom properties.  Set them via:
      Project → Project Information → Custom Fields → Properties
    """

    def run(self, project, parent_widget=None, history_manager=None, settings_manager=None) -> None:
        """Full sync pipeline — fetches and applies calendar exceptions.

        *history_manager* — optional :class:`HistoryManager` instance.  When
        provided, the pre-sync project state is pushed onto every view stack
        so the entire sync can be undone in a single step.

        *settings_manager* — optional :class:`SettingsManager` instance.  When
        provided and a Confluence KeePass entry is configured, username and
        password are auto-filled on the Microsoft SSO login page.  The MFA /
        Authenticator step is always completed manually by the user.
        """
        from PyQt5.QtWidgets import QMessageBox  # type: ignore

        if not _REQUESTS_OK:
            QMessageBox.critical(
                parent_widget, "Missing Dependency",
                "The 'requests' library is required.\n\nRun:  pip install requests",
            )
            return

        if not _PLAYWRIGHT_OK:
            QMessageBox.critical(
                parent_widget, "Missing Dependency",
                "The 'playwright' library is required for SSO.\n\n"
                "Run:  pip install playwright\n"
                "      playwright install chromium",
            )
            return

        if project is None:
            QMessageBox.warning(
                parent_widget, "No Project Open",
                "Please open a project file before syncing calendars.",
            )
            return

        base_url  = get_project_base_url(project)
        space_key = get_project_space_key(project)

        if base_url:
            try:
                base_url = _validate_base_url(base_url)
            except ValueError as exc:
                QMessageBox.critical(parent_widget, "Invalid Base URL", str(exc))
                return

        if not base_url or not space_key:
            missing = []
            if not base_url:
                missing.append(f"‘{CONFLUENCE_BASE_URL_PROP}’")
            if not space_key:
                missing.append(f"‘{CONFLUENCE_SPACE_KEY_PROP}’")
            QMessageBox.information(
                parent_widget, "Confluence Settings Not Set",
                "The following custom properties are missing from this project:\n\n"
                + "\n".join(f"  \u2022 {m}" for m in missing)
                + "\n\nAdd them via  Project \u2192 Project Information \u2192 Custom Fields \u2192 Properties.",
            )
            return

        days_ahead = get_project_days_ahead(project)
        timezone   = get_project_timezone(project)

        # Optional KeePass auto-fill for Microsoft SSO login page (QSettings-based)
        keepass_creds = None
        if settings_manager is not None:
            entry_title = settings_manager.get_confluence_keepass_entry()
            if entry_title and settings_manager.is_keepass_unlocked():
                entry = settings_manager.find_keepass_entry(entry_title)
                if entry is not None:
                    keepass_creds = (entry.username or "", entry.password or "") or None

        try:
            result = _try_playwright_auth(base_url, keepass_creds=keepass_creds)
        except Exception as exc:
            QMessageBox.critical(parent_widget, "Auth Error", str(exc))
            return

        if result is None:
            QMessageBox.critical(
                parent_widget, "Authentication Failed",
                "Could not authenticate with Confluence via SSO.\n\n"
                "The browser window may have been closed before login completed.\n"
                f"Try again, or delete  {_STATE_FILE}  to force a fresh login.",
            )
            return

        session, auth_name = result

        # Snapshot pre-sync state so the entire sync is a single undo step.
        if history_manager is not None:
            history_manager.push_all()

        today        = date.today()
        until        = today + timedelta(days=days_ahead)
        prune_cutoff = today - timedelta(days=30)

        try:
            calendars = _fetch_subcalendars(session, base_url, space_key)
            relevant  = _filter_relevant(calendars)

            if not relevant:
                QMessageBox.information(
                    parent_widget, "No Calendars Found",
                    f"No holiday or vacation calendars found in space \u2018{space_key}\u2019.\n\n"
                    "Check the Space Key in Project Information \u2192 Enterprise.",
                )
                return

            holiday_events: list[dict] = []
            vacation_events: list[dict] = []
            errors: list[str] = []

            for cal in relevant:
                cal_id   = cal.get("id")
                cal_name = cal.get("name", "Unknown")
                cal_type = (cal.get("type") or "").lower()
                if not cal_id:
                    continue
                try:
                    evts = _fetch_events(session, base_url, cal_id, today, until, timezone)
                except Exception as exc:
                    errors.append(f"  \u2022 {cal_name}: {exc}")
                    continue

                if cal_type == "leaves" or any(
                    kw in cal_name.lower() for kw in ("leave", "vacation", "urlaub")
                ):
                    vacation_events.extend(evts)
                else:
                    holiday_events.extend(evts)

        except Exception as exc:
            QMessageBox.critical(parent_widget, "Sync Error", str(exc))
            return

        # TODO DEBUG – remove before release
        if _is_debug():
            from PyQt5.QtWidgets import QDialog, QTextEdit, QVBoxLayout, QPushButton  # type: ignore
            dbg_lines = [
                f"Vacation events received from Confluence ({len(vacation_events)} total):",
                f"Space: {space_key}   Period: {today} – {until}",
                "-" * 80,
            ]
            for i, ev in enumerate(vacation_events, 1):
                user  = ev.get("userName") or ev.get("user") or ev.get("title") or "(unknown)"
                start = ev.get("start") or ev.get("startDate") or "?"
                end   = ev.get("end")   or ev.get("endDate")   or "?"
                dbg_lines.append(f"{i:4}.  {user:35s}  {start}  →  {end}")
            if not vacation_events:
                dbg_lines.append("(none)")
            dbg_lines += [
                "-" * 80,
                f"Holiday events: {len(holiday_events)}",
                "",
                "See the console / terminal for per-event match and import details.",
            ]
            print("[CAL DEBUG] " + "=" * 68)
            print(f"[CAL DEBUG] Vacation events received: {len(vacation_events)}")
            print(f"[CAL DEBUG] Holiday events received:  {len(holiday_events)}")
            print(f"[CAL DEBUG] Resources in project:     {len([r for r in project.getResources() if r.getName()])}")
            print("[CAL DEBUG] " + "-" * 68)
            dlg = QDialog(parent_widget)
            dlg.setWindowTitle("DEBUG – Received Vacation Events")
            dlg.resize(720, 480)
            layout = QVBoxLayout(dlg)
            te = QTextEdit()
            te.setReadOnly(True)
            te.setFontFamily("Courier New")
            te.setPlainText("\n".join(dbg_lines))
            layout.addWidget(te)
            btn = QPushButton("OK – continue with import")
            btn.clicked.connect(dlg.accept)
            layout.addWidget(btn)
            dlg.exec_()

        n_h, n_v, n_v_rem, n_pruned, n_res_new = _apply_to_project(
            project, holiday_events, vacation_events, today, until, prune_cutoff
        )

        lines = [
            f"Calendar sync completed (as \u2018{auth_name}\u2019).\n",
            f"  \u2022 {n_h} public holiday exception(s) added to the project calendar",
            f"  \u2022 {n_v} vacation exception(s) added to resource calendars",
        ]
        if n_res_new:
            lines.append(
                f"  \u2022 {n_res_new} resource(s) automatically created from Confluence calendar"
            )
        if n_v_rem:
            lines.append(
                f"  \u2022 {n_v_rem} stale vacation exception(s) removed from resource calendars"
            )
        if n_pruned:
            lines.append(
                f"  \u2022 {n_pruned} expired exception(s) older than 1 month removed"
            )
        if errors:
            lines.append("\nCalendars with fetch errors:")
            lines.extend(errors)

        # Return the result message instead of showing it — the caller
        # (ui.sync_confluence_calendars) will display it after the progress
        # dialog has been fully closed.
        return "\n".join(lines)
