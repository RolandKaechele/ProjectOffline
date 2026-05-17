"""Helpers for per-resource secondary holiday calendar assignments.

Assignments are persisted in project custom properties so they survive save/load
and can be consumed by Team Planner rendering and debug dumps.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional


_CP_KEY = "AD Secondary Calendars"


def _cp_map(project):
    if project is None:
        return None
    try:
        props = project.getProjectProperties()
        cp = props.getCustomProperties()
        if cp is None:
            from java.util import HashMap  # type: ignore

            cp = HashMap()
            props.setCustomProperties(cp)
        return cp
    except Exception:
        return None


def _normalise_uid(value: Any) -> Optional[str]:
    try:
        if value is None:
            return None
        return str(int(str(value)))
    except Exception:
        return None


def _parse_map(raw_value: Any) -> Dict[str, dict]:
    if raw_value is None:
        return {}

    data = None
    if isinstance(raw_value, dict):
        data = raw_value
    else:
        try:
            s = str(raw_value).strip()
            if not s:
                return {}
            data = json.loads(s)
        except Exception:
            return {}

    if not isinstance(data, dict):
        return {}

    out: Dict[str, dict] = {}
    for key, val in data.items():
        uid = _normalise_uid(key)
        if uid is None or not isinstance(val, dict):
            continue
        name = str(val.get("calendar_name") or "").strip()
        if not name:
            continue
        cal_uid = _normalise_uid(val.get("calendar_uid"))
        source = str(val.get("source") or "ad").strip() or "ad"
        out[uid] = {
            "calendar_name": name,
            "calendar_uid": cal_uid,
            "source": source,
        }
    return out


def _read_map(project) -> Dict[str, dict]:
    cp = _cp_map(project)
    if cp is None:
        return {}
    try:
        raw = cp.get(_CP_KEY)
    except Exception:
        raw = None
    return _parse_map(raw)


def _write_map(project, mapping: Dict[str, dict]) -> None:
    cp = _cp_map(project)
    if cp is None:
        return
    try:
        cp.put(_CP_KEY, json.dumps(mapping, ensure_ascii=False))
        project.getProjectProperties().setCustomProperties(cp)
    except Exception:
        pass


def get_secondary_calendar_map(project) -> Dict[str, dict]:
    """Return {resource_uid: {calendar_name, calendar_uid, source}}."""
    return _read_map(project)


def set_secondary_calendar_for_resource(
    project,
    resource_uid,
    calendar_name: Optional[str],
    calendar_uid: Optional[Any] = None,
    source: str = "ad",
) -> None:
    """Set or clear a resource -> secondary calendar mapping."""
    uid = _normalise_uid(resource_uid)
    if uid is None:
        return
    mapping = _read_map(project)
    name = str(calendar_name or "").strip()
    if not name:
        mapping.pop(uid, None)
        _write_map(project, mapping)
        return

    mapping[uid] = {
        "calendar_name": name,
        "calendar_uid": _normalise_uid(calendar_uid),
        "source": source or "ad",
    }
    _write_map(project, mapping)


def _resource_uid(resource) -> Optional[str]:
    if resource is None:
        return None
    try:
        return _normalise_uid(resource.getUniqueID())
    except Exception:
        return None


def _find_calendar(project, cal_uid: Optional[str], cal_name: str):
    if project is None:
        return None
    calendars = []
    try:
        calendars = list(project.getCalendars())
    except Exception:
        return None

    if cal_uid is not None:
        for cal in calendars:
            try:
                uid = _normalise_uid(cal.getUniqueID())
                if uid == cal_uid:
                    return cal
            except Exception:
                pass

    want = cal_name.strip().lower()
    for cal in calendars:
        try:
            if str(cal.getName() or "").strip().lower() == want:
                return cal
        except Exception:
            pass
    return None


def resolve_secondary_calendar(project, resource) -> Optional[dict]:
    """Resolve mapped secondary calendar for a resource.

    Returns None when no mapping exists or the mapped calendar is not found.
    """
    uid = _resource_uid(resource)
    if uid is None:
        return None
    entry = _read_map(project).get(uid)
    if not entry:
        return None
    cal = _find_calendar(project, entry.get("calendar_uid"), entry.get("calendar_name", ""))
    if cal is None:
        return {
            "resource_uid": uid,
            "calendar_name": entry.get("calendar_name"),
            "calendar_uid": entry.get("calendar_uid"),
            "source": entry.get("source") or "ad",
            "calendar": None,
        }
    return {
        "resource_uid": uid,
        "calendar_name": str(cal.getName() or entry.get("calendar_name") or ""),
        "calendar_uid": _normalise_uid(cal.getUniqueID()) or entry.get("calendar_uid"),
        "source": entry.get("source") or "ad",
        "calendar": cal,
    }


def _looks_like_personal_calendar(name: str) -> bool:
    n = name.strip().lower()
    return n.endswith(" calendar") and ("," in n or len(n.split()) <= 3)


def _calendar_exception_count(cal) -> int:
    try:
        ex = cal.getCalendarExceptions()
        return len(list(ex)) if ex is not None else 0
    except Exception:
        return 0


def infer_secondary_calendar_from_ad(project, ad_user: dict) -> Optional[dict]:
    """Infer a matching installed project calendar from AD user metadata."""
    if project is None or not isinstance(ad_user, dict):
        return None

    hint_fields = [
        ad_user.get("state"),
        ad_user.get("region"),
        ad_user.get("city"),
        ad_user.get("country"),
        ad_user.get("department"),
        ad_user.get("display_name"),
    ]
    hint_blob = " ".join(str(v) for v in hint_fields if v).lower()
    if not hint_blob:
        return None

    best = None
    best_score = 0
    try:
        calendars = list(project.getCalendars())
    except Exception:
        calendars = []

    for cal in calendars:
        try:
            name = str(cal.getName() or "").strip()
        except Exception:
            continue
        if not name or _looks_like_personal_calendar(name):
            continue

        lname = name.lower()
        score = 0
        if lname in hint_blob:
            score += 10

        for token in re.split(r"[^a-z0-9äöüß]+", lname):
            token = token.strip()
            if len(token) < 4:
                continue
            if token in hint_blob:
                score += 1

        if score <= 0:
            continue

        # Prefer calendars that actually define non-working exceptions.
        score += min(5, _calendar_exception_count(cal))

        if score > best_score:
            best_score = score
            best = cal

    if best is None:
        return None

    return {
        "calendar_name": str(best.getName() or ""),
        "calendar_uid": _normalise_uid(best.getUniqueID()),
        "source": "ad:auto-match",
        "calendar": best,
    }


def assign_secondary_calendar_from_ad(project, resource, ad_user: dict) -> Optional[dict]:
    """Infer and persist a secondary calendar assignment for an AD-added resource."""
    uid = _resource_uid(resource)
    if uid is None:
        return None

    inferred = infer_secondary_calendar_from_ad(project, ad_user)
    if not inferred:
        return None

    set_secondary_calendar_for_resource(
        project,
        uid,
        inferred.get("calendar_name"),
        inferred.get("calendar_uid"),
        source=inferred.get("source") or "ad:auto-match",
    )
    return resolve_secondary_calendar(project, resource)
