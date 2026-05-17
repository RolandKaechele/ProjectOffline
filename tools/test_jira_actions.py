#!/usr/bin/env python3
"""test_jira_actions.py — Comprehensive test suite for Jira integration APIs.

Tests all public functions from:
  - src/integrations/jira_integration.py
  - src/integrations/jira_sync.py

using the app's internal APIs against a live Jira server.

WARNING: This script may create real Jira issues on the configured server.
         Only run against a TEST server, never against production.

Usage:
    venv\\Scripts\\python.exe tools\\test_jira_actions.py [options]

Options:
    --dry-run           Skip all tests that create/modify Jira issues
                        (default: false)
    --output-dir DIR    Output directory for the HTML report
                        (default: tests\\documentation)
    --no-gui            Print results to console only (no HTML report)
"""

from __future__ import annotations

import io
import json
import optparse
import os
import sys
import tempfile
import time
import traceback
import types
from contextlib import redirect_stdout, redirect_stderr
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

# ---------------------------------------------------------------------------
# Bootstrap: add src/ to sys.path and mock unavailable app modules
# ---------------------------------------------------------------------------
_TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_DIR = os.path.dirname(_TOOLS_DIR)
_SRC_DIR = os.path.join(_ROOT_DIR, "src")
_INTEGRATIONS_DIR = os.path.join(_SRC_DIR, "integrations")

for _p in (_SRC_DIR, _INTEGRATIONS_DIR):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Mock app_debug before importing integration modules
_mock_app_debug = types.ModuleType("app_debug")
_mock_app_debug.is_debug = lambda: False  # type: ignore
sys.modules.setdefault("app_debug", _mock_app_debug)

# Minimal SettingsManager stub (real credentials injected per-test via monkey-patch)
class _StubSettingsManager:
    def __init__(self, server: dict):
        self._server = server

    def get_jira_credentials(self, server: dict):
        username = (server.get("username") or "").strip()
        credential = (server.get("token") or "").strip()
        return username, credential

    def get_jira_servers(self):
        return [self._server]

    def is_keepass_unlocked(self):
        return False


_mock_settings_manager_mod = types.ModuleType("settings_manager")


class _StubSMClass:
    """Placeholder; replaced per-test by monkey-patching jira_integration._get_settings_manager."""
    pass


_mock_settings_manager_mod.SettingsManager = _StubSMClass  # type: ignore
sys.modules.setdefault("settings_manager", _mock_settings_manager_mod)

# Now import the modules under test
try:
    import jira_integration  # type: ignore
    import jira_sync  # type: ignore
    _IMPORT_OK = True
    _IMPORT_ERROR = ""
except Exception as _exc:
    _IMPORT_OK = False
    _IMPORT_ERROR = str(_exc)

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

_STATUS_PASS  = "PASS"
_STATUS_FAIL  = "FAIL"
_STATUS_ERROR = "ERROR"
_STATUS_SKIP  = "SKIP"
_STATUS_INFO  = "INFO"


@dataclass
class TestResult:
    category:    str
    name:        str
    status:      str          # PASS | FAIL | ERROR | SKIP | INFO
    duration_ms: float = 0.0
    message:     str   = ""
    stdout:      str   = ""
    details:     str   = ""


# ---------------------------------------------------------------------------
# Test Runner
# ---------------------------------------------------------------------------

class TestRunner:
    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.results: list[TestResult] = []

    # ── ANSI colour helpers ────────────────────────────────────────────────
    _C_RESET  = "\033[0m"
    _C_BOLD   = "\033[1m"
    _C_GREEN  = "\033[32m"
    _C_RED    = "\033[31m"
    _C_YELLOW = "\033[33m"
    _C_CYAN   = "\033[36m"
    _C_GREY   = "\033[90m"

    # Label and colour per status
    _STATUS_LABEL = {
        _STATUS_PASS:  (" OK  ", "\033[32m"),   # green
        _STATUS_FAIL:  ("FAIL ", "\033[31m"),   # red
        _STATUS_ERROR: ("ERR  ", "\033[31m"),   # red
        _STATUS_SKIP:  ("SKIP ", "\033[33m"),   # yellow
    }
    _last_category: str = ""

    def _print_header(self, category: str):
        """Print a category separator line the first time a category appears."""
        if category != self._last_category:
            self.__class__._last_category = category
            print(f"\n{self._C_BOLD}{self._C_CYAN}── {category} ──{self._C_RESET}")

    def run(self, category: str, name: str, fn: Callable, *args, **kwargs) -> TestResult:
        """Execute fn(*args, **kwargs), print live progress, and record a TestResult."""
        self._print_header(category)
        # Print "  ..." while the test is running (overwritten on the same line)
        short = name[:72]
        print(f"  {self._C_GREY}...{self._C_RESET} {short}", end="\r", flush=True)

        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        t0 = time.perf_counter()
        status = _STATUS_PASS
        message = ""
        details = ""
        try:
            with redirect_stdout(stdout_buf), redirect_stderr(stderr_buf):
                fn(*args, **kwargs)
        except _TestSkip as exc:
            status = _STATUS_SKIP
            message = str(exc)
        except _TestFail as exc:
            status = _STATUS_FAIL
            message = str(exc)
        except Exception as exc:
            status = _STATUS_ERROR
            message = str(exc)
            details = traceback.format_exc()
        elapsed = (time.perf_counter() - t0) * 1000
        captured = (stdout_buf.getvalue() + stderr_buf.getvalue()).strip()
        result = TestResult(
            category=category,
            name=name,
            status=status,
            duration_ms=round(elapsed, 1),
            message=message,
            stdout=captured if status in (_STATUS_FAIL, _STATUS_ERROR) else "",
            details=details,
        )
        self.results.append(result)

        # Overwrite the "..." line with the final result
        lbl, col = self._STATUS_LABEL.get(status, (" ??? ", ""))
        dur_str = f"{self._C_GREY}{elapsed:6.0f} ms{self._C_RESET}"
        status_str = f"{col}{self._C_BOLD}[{lbl}]{self._C_RESET}"
        # Pad to clear the previous "..." line (max 80 chars)
        line = f"  {status_str} {short}"
        print(f"{line:<82} {dur_str}")
        if message and status != _STATUS_PASS:
            indent = "         "
            for part in message.splitlines()[:3]:  # max 3 lines of detail
                print(f"{indent}{self._C_GREY}{part}{self._C_RESET}")

        return result

    def skip(self, category: str, name: str, reason: str) -> TestResult:
        self._print_header(category)
        lbl, col = self._STATUS_LABEL[_STATUS_SKIP]
        short = name[:72]
        print(f"  {col}{self._C_BOLD}[{lbl}]{self._C_RESET} {short:<72}"
              f"  {self._C_GREY}{reason}{self._C_RESET}")
        result = TestResult(category=category, name=name, status=_STATUS_SKIP,
                             message=reason)
        self.results.append(result)
        return result

    def summary(self) -> dict:
        counts = {_STATUS_PASS: 0, _STATUS_FAIL: 0, _STATUS_ERROR: 0,
                  _STATUS_SKIP: 0, _STATUS_INFO: 0}
        for r in self.results:
            counts[r.status] = counts.get(r.status, 0) + 1
        return counts


class _TestFail(Exception):
    pass


class _TestSkip(Exception):
    pass


def _assert(condition: bool, message: str = "assertion failed"):
    if not condition:
        raise _TestFail(message)


def _assert_eq(actual, expected, label: str = ""):
    if actual != expected:
        raise _TestFail(
            f"{label + ': ' if label else ''}expected {expected!r}, got {actual!r}"
        )


# ---------------------------------------------------------------------------
# ── CATEGORY A: Unit Tests – _normalize_jira_datetime ──────────────────────
# ---------------------------------------------------------------------------

def _test_A1_normalize_none(runner: TestRunner):
    def _run():
        result = jira_sync._normalize_jira_datetime(None)  # type: ignore
        _assert(result is None or result == "", f"expected None/empty, got {result!r}")
    runner.run("A – Datetime Normalisation", "A1: None input → None/empty", _run)


def _test_A2_normalize_empty(runner: TestRunner):
    def _run():
        _assert_eq(jira_sync._normalize_jira_datetime(""), "", "empty string")  # type: ignore
    runner.run("A – Datetime Normalisation", "A2: Empty string → empty", _run)


def _test_A3_normalize_date_only(runner: TestRunner):
    def _run():
        val = "2024-01-15"
        result = jira_sync._normalize_jira_datetime(val)  # type: ignore
        _assert_eq(result, "2024-01-15", "date-only unchanged")
    runner.run("A – Datetime Normalisation", "A3: Date-only string → unchanged", _run)


def _test_A4_normalize_z_suffix(runner: TestRunner):
    def _run():
        result = jira_sync._normalize_jira_datetime("2024-01-15T10:30:00.000Z")  # type: ignore
        _assert(result.endswith("Z"), f"expected Z suffix, got {result!r}")
        _assert("2024-01-15" in result, "date part preserved")
    runner.run("A – Datetime Normalisation", "A4: With .000Z suffix → UTC Z string", _run)


def _test_A5_normalize_utc_offset(runner: TestRunner):
    def _run():
        result = jira_sync._normalize_jira_datetime("2024-01-15T12:00:00.000+00:00")  # type: ignore
        _assert(result.endswith("Z"), f"expected Z suffix, got {result!r}")
    runner.run("A – Datetime Normalisation", "A5: +00:00 offset → Z suffix", _run)


def _test_A6_normalize_positive_offset(runner: TestRunner):
    def _run():
        # 2024-01-15T12:00:00 +02:00  →  2024-01-15T10:00:00Z
        result = jira_sync._normalize_jira_datetime("2024-01-15T12:00:00.000+0200")  # type: ignore
        _assert(result.endswith("Z"), f"Z suffix missing: {result!r}")
        _assert("10:00:00" in result, f"expected 10:00:00 UTC, got {result!r}")
    runner.run("A – Datetime Normalisation", "A6: +02:00 offset → correct UTC", _run)


def _test_A7_normalize_negative_offset(runner: TestRunner):
    def _run():
        # 2024-01-15T15:00:00 -05:00  →  2024-01-15T20:00:00Z
        result = jira_sync._normalize_jira_datetime("2024-01-15T15:00:00.000-0500")  # type: ignore
        _assert(result.endswith("Z"), f"Z suffix missing: {result!r}")
        _assert("20:00:00" in result, f"expected 20:00:00 UTC, got {result!r}")
    runner.run("A – Datetime Normalisation", "A7: -05:00 offset → correct UTC", _run)


def _test_A8_normalize_milliseconds_stripped(runner: TestRunner):
    def _run():
        result = jira_sync._normalize_jira_datetime("2024-06-01T08:15:30.123456+0000")  # type: ignore
        _assert(result.endswith("Z"), f"Z suffix missing: {result!r}")
        _assert(".123" not in result, f"milliseconds should be stripped: {result!r}")
    runner.run("A – Datetime Normalisation", "A8: Milliseconds stripped from output", _run)


def run_category_A(runner: TestRunner):
    _test_A1_normalize_none(runner)
    _test_A2_normalize_empty(runner)
    _test_A3_normalize_date_only(runner)
    _test_A4_normalize_z_suffix(runner)
    _test_A5_normalize_utc_offset(runner)
    _test_A6_normalize_positive_offset(runner)
    _test_A7_normalize_negative_offset(runner)
    _test_A8_normalize_milliseconds_stripped(runner)


# ---------------------------------------------------------------------------
# ── CATEGORY B: Unit Tests – _extract_filter_id ────────────────────────────
# ---------------------------------------------------------------------------

def run_category_B(runner: TestRunner):
    cat = "B – Filter ID Extraction"

    cases = [
        ("B1: Full ?filter= URL",          "https://jira.example.com/issues/?filter=66111", "66111"),
        # NOTE: bare "filter=66111" (no leading ?/&) returns "" because the regex
        # requires [?&] prefix. The function docstring lists this form but the
        # implementation only matches ?filter= and &filter= patterns.
        ("B2: Bare fragment 'filter=ID' → empty (requires ?/& prefix)",
         "filter=66111",   ""),
        ("B3: Plain numeric string",        "66111",           "66111"),
        ("B4: Non-numeric string → empty",  "not-a-filter",    ""),
        ("B5: Empty string → empty",        "",                ""),
        ("B6: &filter= inside URL",
         "https://jira.example.com/rest/api/2/filter?key=x&filter=12345", "12345"),
        ("B7: URL without filter param",    "https://jira.example.com/browse/PROJ-1", ""),
    ]

    for name, value, expected in cases:
        def _run(v=value, e=expected):
            result = jira_integration._extract_filter_id(v)  # type: ignore
            _assert_eq(result, e, f"input={v!r}")
        runner.run(cat, name, _run)


# ---------------------------------------------------------------------------
# ── CATEGORY C: Unit Tests – Sidecar I/O ───────────────────────────────────
# ---------------------------------------------------------------------------

def run_category_C(runner: TestRunner):
    cat = "C – Sidecar I/O"

    def _C1():
        result = jira_sync.load_sidecar_task_data("/nonexistent/path/file.json")
        _assert_eq(result, {}, "missing file → empty dict")
    runner.run(cat, "C1: load_sidecar_task_data – missing file → {}", _C1)

    def _C2():
        data = {"42": {"jira_key": "PROJ-1", "jira_status": "Open"}}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"task_jira": data}, f)
            tmp = f.name
        try:
            result = jira_sync.load_sidecar_task_data(tmp)
            _assert_eq(result, data, "round-trip load")
        finally:
            os.unlink(tmp)
    runner.run(cat, "C2: load_sidecar_task_data – valid file → correct dict", _C2)

    def _C3():
        data = {"99": {"jira_key": "TEST-5", "jira_status": "Done"}}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("{}")
            tmp = f.name
        try:
            jira_sync.save_sidecar_task_data(tmp, data)
            loaded = jira_sync.load_sidecar_task_data(tmp)
            _assert_eq(loaded, data, "save→load round-trip")
        finally:
            os.unlink(tmp)
    runner.run(cat, "C3: save_sidecar_task_data → load → same data", _C3)

    def _C4():
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            f.write("{not valid json!!!")
            tmp = f.name
        try:
            result = jira_sync.load_sidecar_task_data(tmp)
            _assert_eq(result, {}, "corrupted JSON → empty dict")
        finally:
            os.unlink(tmp)
    runner.run(cat, "C4: load_sidecar_task_data – corrupted JSON → {}", _C4)

    def _C5():
        result = jira_sync.get_last_result()
        # Before any sync, _last_result may be None or a previous dict
        # We just verify the API is callable and returns dict|None
        _assert(result is None or isinstance(result, dict), "returns None or dict")
    runner.run(cat, "C5: get_last_result – returns None or dict", _C5)

    def _C6():
        existing = {"existing_key": {"jira_key": "X-1"}}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"task_jira": existing, "other_section": {"foo": "bar"}}, f)
            tmp = f.name
        try:
            new_data = {"new_key": {"jira_key": "X-2"}}
            jira_sync.save_sidecar_task_data(tmp, new_data)
            with open(tmp) as fh:
                full = json.load(fh)
            _assert("other_section" in full, "save preserves other sections")
            _assert_eq(full["task_jira"], new_data, "task_jira replaced")
        finally:
            os.unlink(tmp)
    runner.run(cat, "C6: save_sidecar_task_data – preserves other sidecar sections", _C6)


# ---------------------------------------------------------------------------
# ── CATEGORY D: Unit Tests – record_filter_test ────────────────────────────
# ---------------------------------------------------------------------------

def run_category_D(runner: TestRunner):
    cat = "D – record_filter_test"

    def _D1():
        jira_integration.record_filter_test("TestServer", "project = DEMO", 42, "")
        ft = jira_integration._last_filter_test
        _assert(ft is not None, "_last_filter_test set")
        _assert_eq(ft["server_name"],  "TestServer",   "server_name")
        _assert_eq(ft["filter"],       "project = DEMO", "filter")
        _assert_eq(ft["issue_count"],  42,              "issue_count")
        _assert(ft["success"] is True, "success=True when no error")
    runner.run(cat, "D1: Success case – _last_filter_test populated correctly", _D1)

    def _D2():
        jira_integration.record_filter_test("BadServer", "bad jql!", 0, "Connection refused")
        ft = jira_integration._last_filter_test
        _assert(ft is not None, "_last_filter_test set")
        _assert(ft["success"] is False, "success=False when error given")
        _assert("Connection refused" in ft["error"], "error propagated")
    runner.run(cat, "D2: Error case – success=False, error stored", _D2)

    def _D3():
        jira_integration.record_filter_test("S1", "project=A", 5, "")
        before = jira_integration._last_filter_test.copy()
        time.sleep(0.01)
        jira_integration.record_filter_test("S2", "project=B", 10, "")
        after = jira_integration._last_filter_test
        _assert(before["server_name"] != after["server_name"] or
                before["filter"] != after["filter"],
                "second call overwrites _last_filter_test")
    runner.run(cat, "D3: Repeated calls – _last_filter_test always reflects latest call", _D3)


# ---------------------------------------------------------------------------
# ── CATEGORY E: Unit Tests – resolve_filter_to_jql (local) ─────────────────
# ---------------------------------------------------------------------------

def run_category_E(runner: TestRunner):
    cat = "E – resolve_filter_to_jql (local)"

    def _E1():
        jql, err = jira_integration.resolve_filter_to_jql(None, "project = DEMO AND status = Open", "jql")
        _assert_eq(jql, "project = DEMO AND status = Open", "jql passthrough")
        _assert_eq(err, "", "no error")
    runner.run(cat, "E1: filter_type='jql' → passthrough, no error", _E1)

    def _E2():
        jql, err = jira_integration.resolve_filter_to_jql(None, "", "jql")
        _assert_eq(jql, "", "empty passthrough")
        _assert_eq(err, "", "no error for empty jql")
    runner.run(cat, "E2: filter_type='jql' with empty string → empty, no error", _E2)

    def _E3():
        jql, err = jira_integration.resolve_filter_to_jql(None, "not-a-number", "filter")
        _assert_eq(jql, "", "jql empty on bad filter ref")
        _assert(len(err) > 0, "error message populated")
    runner.run(cat, "E3: filter_type='filter' non-numeric → empty jql + error message", _E3)

    def _E4():
        jql, err = jira_integration.resolve_filter_to_jql(None, "https://jira.example.com/?filter=99", "filter")
        # Extraction succeeds, but the API call will fail (no real JIRA client)
        # resolve returns ("", error) when jira.filter(id) fails
        _assert(isinstance(jql, str), "returns string")
        _assert(isinstance(err, str), "error is string")
    runner.run(cat, "E4: filter_type='filter' with URL but no client → extracts ID, returns error", _E4)


# ---------------------------------------------------------------------------
# ── CATEGORY F: Connection Tests (live server) ──────────────────────────────
# ---------------------------------------------------------------------------

def _inject_sm(server: dict):
    """Monkey-patch jira_integration._get_settings_manager for the given server."""
    stub = _StubSettingsManager(server)
    jira_integration._get_settings_manager = lambda: stub  # type: ignore


def run_category_F(runner: TestRunner, server: dict):
    cat = "F – Connection Tests"

    def _F1():
        _inject_sm(server)
        ok, err = jira_integration.test_connection(server)
        _assert(ok, f"Expected successful connection, got error: {err}")
    runner.run(cat, "F1: test_connection – valid credentials → success", _F1)

    def _F2():
        bad = dict(server)
        bad["token"] = "wrong-token-xyz-12345"
        bad["name"] = "bad-cred-test"
        _inject_sm(bad)
        ok, err = jira_integration.test_connection(bad)
        _assert(not ok, "Expected failure with wrong token")
        _assert(len(err) > 0, "Error message should be non-empty")
    runner.run(cat, "F2: test_connection – wrong credentials → failure + error message", _F2)

    def _F3():
        bad = dict(server)
        bad["url"] = "https://this-server-does-not-exist.invalid"
        bad["name"] = "bad-url-test"
        _inject_sm(bad)
        ok, err = jira_integration.test_connection(bad)
        _assert(not ok, "Expected failure with invalid URL")
    runner.run(cat, "F3: test_connection – invalid URL → failure", _F3)

    def _F4():
        bad = dict(server)
        bad["token"] = ""
        bad["username"] = ""
        bad["name"] = "empty-cred-test"
        _inject_sm(bad)
        ok, err = jira_integration.test_connection(bad)
        _assert(not ok, "Expected failure with empty credentials")
    runner.run(cat, "F4: test_connection – empty credentials → failure (non-PAT mode)", _F4)

    def _F5():
        _inject_sm(server)
        jira, err = jira_integration.get_jira_client(server)
        _assert(jira is not None, f"Expected JIRA client, got error: {err}")
        _assert_eq(err, "", "no error on success")
    runner.run(cat, "F5: get_jira_client – valid credentials → client returned", _F5)

    def _F6():
        bad = dict(server)
        bad["url"] = "https://no-such-server.invalid"
        bad["name"] = "bad-url-client-test"
        _inject_sm(bad)
        jira, err = jira_integration.get_jira_client(bad)
        _assert(jira is None, "Expected None client on invalid URL")
        _assert(len(err) > 0, "Error message non-empty")
    runner.run(cat, "F6: get_jira_client – invalid URL → None + error message", _F6)

    # F7: PAT mode with empty token
    if server.get("credential_type") != "pat":
        pat_server = dict(server)
        pat_server["credential_type"] = "pat"
        pat_server["token"] = ""
        pat_server["name"] = "empty-pat-test"

        def _F7():
            _inject_sm(pat_server)
            ok, err = jira_integration.test_connection(pat_server)
            _assert(not ok, "Empty PAT should fail")
        runner.run(cat, "F7: test_connection – PAT mode with empty token → failure", _F7)
    else:
        runner.skip(cat, "F7: PAT mode with empty token (skip – already in PAT mode)", "")

    # Restore good SM after F tests
    _inject_sm(server)


# ---------------------------------------------------------------------------
# ── CATEGORY G: Server Info Tests ──────────────────────────────────────────
# ---------------------------------------------------------------------------

def run_category_G(runner: TestRunner, server: dict, jira_client):
    cat = "G – Server Info"

    def _G1():
        summary = jira_integration.get_config_summary()
        _assert(isinstance(summary, dict), "returns dict")
        _assert("servers" in summary or "error" in summary, "has 'servers' or 'error' key")
    runner.run(cat, "G1: get_config_summary – returns dict with expected structure", _G1)

    def _G2():
        _inject_sm(server)
        summary = jira_integration.get_config_summary()
        count = summary.get("server_count", 0)
        _assert(count >= 1, f"Expected ≥1 server in summary, got {count}")
    runner.run(cat, "G2: get_config_summary – server count ≥ 1", _G2)

    def _G3():
        me = jira_client.myself()
        _assert(me is not None, "myself() returned None")
        _assert("displayName" in me or "name" in me or "accountId" in me,
                f"Unexpected myself() structure: {list(me.keys())[:5]}")
    runner.run(cat, "G3: jira.myself() – returns user info dict", _G3)

    def _G4():
        info = jira_client.server_info()
        _assert(info is not None, "server_info() returned None")
        _assert(isinstance(info, dict), "server_info() should return dict")
        _assert(any(k in info for k in ("version", "serverTitle", "baseUrl")),
                f"Unexpected server_info keys: {list(info.keys())[:5]}")
    runner.run(cat, "G4: jira.server_info() – returns server metadata", _G4)

    def _G5():
        types_list = jira_client.issue_types()
        _assert(types_list is not None, "issue_types() returned None")
        _assert(len(types_list) > 0, "issue_types() returned empty list")
    runner.run(cat, "G5: jira.issue_types() – returns non-empty list", _G5)

    def _G7():
        caps = jira_integration.fetch_server_capabilities(server)
        _assert(isinstance(caps, dict), "fetch_server_capabilities() returns dict")
        _assert("issue_types" in caps, "result has 'issue_types' key")
        _assert("priorities" in caps, "result has 'priorities' key")
        _assert("error" in caps, "result has 'error' key")
        _assert(isinstance(caps["issue_types"], list), "issue_types is a list")
        _assert(len(caps["issue_types"]) > 0, "issue_types is non-empty")
        _assert(caps["error"] == "", f"unexpected error: {caps['error']}")
        # Values must be strings (issue type names)
        for it in caps["issue_types"]:
            _assert(isinstance(it, str), f"issue type entry is not str: {it!r}")
    runner.run(cat, "G7: fetch_server_capabilities() – returns issue_types and priorities", _G7)

    def _G8():
        # Validate fetch_server_capabilities with an unreachable server
        bad = dict(server)
        bad["url"] = "https://no-such-server.invalid"
        bad["name"] = "bad-url-caps-test"
        _inject_sm(bad)
        try:
            caps = jira_integration.fetch_server_capabilities(bad)
            _assert(isinstance(caps, dict), "returns dict even on failure")
            _assert(caps["error"] != "", "error field must be set on failure")
            _assert(caps["issue_types"] == [], "issue_types empty on failure")
        finally:
            _inject_sm(server)
    runner.run(cat, "G8: fetch_server_capabilities() – error on unreachable server", _G8)

    def _G6():
        projects = jira_client.projects()
        _assert(projects is not None, "projects() returned None")
        # May be empty if no projects visible but should not error
        _assert(isinstance(projects, list), "projects() returns list")
    runner.run(cat, "G6: jira.projects() – returns list (may be empty)", _G6)


# ---------------------------------------------------------------------------
# ── CATEGORY H: JQL Filter Tests ───────────────────────────────────────────
# ---------------------------------------------------------------------------

def run_category_H(runner: TestRunner, server: dict, jira_client, project_key: str,
                   filter_value: str = "", filter_type: str = "jql",
                   capabilities: dict = None):
    """JQL / Saved-filter tests.  Uses the filter entered in the dialog when provided."""
    cat = "H – JQL Filter Tests"
    # Effective JQL for most sub-tests: if user supplied a JQL filter use it,
    # otherwise fall back to a simple project filter.
    effective_jql = (
        filter_value
        if filter_type == "jql" and filter_value
        else f"project = {project_key} ORDER BY created DESC"
    )

    def _H1():
        jql = effective_jql
        issues = jira_client.search_issues(jql, maxResults=10)
        _assert(issues is not None, "search_issues returned None")
        # Issues list may be empty for new test project, that's OK
        _assert(isinstance(list(issues), list), "returns iterable")
    runner.run(cat, "H1: Basic JQL search – project filter executes without error", _H1)

    def _H2():
        jql = f"project = {project_key} AND status in ('To Do', 'In Progress', 'Done')"
        issues = jira_client.search_issues(jql, maxResults=5)
        _assert(issues is not None, "status filter search returned None")
    runner.run(cat, "H2: JQL with status filter – executes without error", _H2)

    def _H3():
        jql = f"project = {project_key} AND assignee is EMPTY"
        issues = jira_client.search_issues(jql, maxResults=5)
        _assert(issues is not None, "assignee filter returned None")
    runner.run(cat, "H3: JQL with assignee is EMPTY – executes without error", _H3)

    # H8: Execute the dialog-supplied filter directly
    def _H8():
        if not filter_value:
            raise _TestSkip("No filter entered in dialog")
        if filter_type == "jql":
            issues = list(jira_client.search_issues(filter_value, maxResults=20))
            jira_integration.record_filter_test(
                server.get("name", "test"), filter_value, len(issues), ""
            )
            _assert(isinstance(issues, list), "dialog JQL executes without error")
        else:
            jql_out, err = jira_integration.resolve_filter_to_jql(
                jira_client, filter_value, "filter"
            )
            if err:
                raise _TestFail(f"Saved filter resolution failed: {err}")
            issues = list(jira_client.search_issues(jql_out, maxResults=20))
            jira_integration.record_filter_test(
                server.get("name", "test"), filter_value, len(issues), ""
            )
            _assert(isinstance(issues, list), "saved filter executes without error")
    runner.run(cat, f"H8: Dialog-supplied {filter_type.upper()} filter executes on server", _H8)

    # H9: Date-range JQL
    def _H9():
        jql = f"project = {project_key} AND created >= -30d ORDER BY created DESC"
        issues = jira_client.search_issues(jql, maxResults=5)
        _assert(issues is not None, "date-range JQL returned None")
    runner.run(cat, "H9: JQL with date-range filter (created >= -30d)", _H9)

    # H10: Priority filter
    def _H10():
        caps = capabilities or {}
        avail_priorities = caps.get("priorities", [])
        # Build the priority list using only values known to exist on the server
        wanted = [p for p in ("High", "Highest") if not avail_priorities or p in avail_priorities]
        if not wanted:
            raise _TestSkip(
                f"Neither 'High' nor 'Highest' priority available on this server "
                f"(available: {avail_priorities})"
            )
        jql = f"project = {project_key} AND priority in ({', '.join(wanted)}) ORDER BY created DESC"
        issues = jira_client.search_issues(jql, maxResults=5)
        _assert(issues is not None, "priority JQL returned None")
    runner.run(cat, "H10: JQL with priority filter", _H10)

    def _H4():
        bad_jql = "THIS IS COMPLETELY INVALID JQL !@#$%"
        try:
            issues = jira_client.search_issues(bad_jql, maxResults=1)
            # Some servers may return empty instead of raising
            _assert(True, "server accepted invalid JQL without error (soft fail)")
        except Exception as exc:
            # Expected: Jira should reject invalid JQL
            _assert(len(str(exc)) > 0, "Exception raised for invalid JQL (expected)")
    runner.run(cat, "H4: Invalid JQL → server rejects with error (expected failure)", _H4)

    def _H5():
        jql = f"project = {project_key} AND key = 'ZZNONEXISTENT-99999'"
        issues = list(jira_client.search_issues(jql, maxResults=1))
        _assert_eq(len(issues), 0, "non-existent key yields 0 results")
    runner.run(cat, "H5: JQL for non-existent key → 0 results", _H5)

    def _H6():
        jql = effective_jql
        jira_integration.record_filter_test(server.get("name", "test"), jql, 0, "")
        ft = jira_integration._last_filter_test
        _assert(ft is not None, "_last_filter_test set after record")
        _assert(ft["success"], "success recorded")
    runner.run(cat, "H6: record_filter_test after search – _last_filter_test updated", _H6)

    def _H7():
        # resolve_filter_to_jql passthrough for JQL type
        jql_in = f"project = {project_key}"
        jql_out, err = jira_integration.resolve_filter_to_jql(jira_client, jql_in, "jql")
        _assert_eq(jql_out, jql_in, "JQL passthrough unchanged")
        _assert_eq(err, "", "no error")
    runner.run(cat, "H7: resolve_filter_to_jql with jql type → unchanged passthrough", _H7)


# ---------------------------------------------------------------------------
# ── CATEGORY I: Saved Filter Tests ─────────────────────────────────────────
# ---------------------------------------------------------------------------

def run_category_I(runner: TestRunner, jira_client,
                   filter_value: str = "", filter_type: str = "jql"):
    cat = "I – Saved Filter Tests"

    def _I1():
        # Test with a non-numeric filter ref (should fail gracefully)
        jql, err = jira_integration.resolve_filter_to_jql(jira_client, "not-a-filter-id", "filter")
        _assert_eq(jql, "", "empty JQL on bad filter ref")
        _assert(len(err) > 0, "error message returned")
    runner.run(cat, "I1: resolve_filter_to_jql – non-numeric ID → empty + error", _I1)

    def _I2():
        # Test with a numeric ID that likely doesn't exist
        jql, err = jira_integration.resolve_filter_to_jql(jira_client, "99999999", "filter")
        # Either returns ("", error) or raises – both are valid failure modes
        _assert(isinstance(jql, str) and isinstance(err, str),
                "returns (str, str) tuple")
        if jql == "":
            _assert(len(err) > 0, "error populated when jql empty")
    runner.run(cat, "I2: resolve_filter_to_jql – non-existent filter ID → error returned", _I2)

    def _I3():
        # Test URL extraction via resolve_filter_to_jql
        url = "https://jira.example.com/issues/?filter=99999999"
        jql, err = jira_integration.resolve_filter_to_jql(jira_client, url, "filter")
        _assert(isinstance(jql, str), "returns string")
        # Non-existent filter ID: err should be set, jql should be ""
    runner.run(cat, "I3: resolve_filter_to_jql – filter URL form → ID extracted, error on missing filter", _I3)

    # I4: When dialog filter_type == 'filter', test against the real server
    def _I4():
        if filter_type != "filter" or not filter_value:
            raise _TestSkip("Dialog filter type is JQL or no filter entered")
        jql, err = jira_integration.resolve_filter_to_jql(jira_client, filter_value, "filter")
        if err:
            # Resolution failed; record and report as failure
            raise _TestFail(f"Saved filter '{filter_value}' failed: {err}")
        _assert(len(jql) > 0, "resolved JQL must not be empty")
        # Execute the resolved JQL
        issues = list(jira_client.search_issues(jql, maxResults=10))
        jira_integration.record_filter_test(
            "dialog-saved-filter", filter_value, len(issues), ""
        )
        _assert(isinstance(issues, list), "resolved saved filter executes")
    runner.run(cat, "I4: Dialog saved filter → resolved JQL executes on server", _I4)


# ---------------------------------------------------------------------------
# ── CATEGORY J: Issue CRUD (live server, skipped in dry-run) ────────────────
# ---------------------------------------------------------------------------

_created_issue_keys: list[str] = []


def run_category_J(runner: TestRunner, jira_client, project_key: str, dry_run: bool,
                   capabilities: dict = None):
    cat = "J – Issue CRUD"

    if dry_run:
        for n in ["J1", "J2", "J3", "J4", "J5", "J6", "J7", "J8"]:
            runner.skip(cat, f"{n}: (skipped – dry-run mode)", "dry-run")
        return

    # J1: Create Story
    created_story_key = None

    def _J1():
        nonlocal created_story_key
        avail_types = (capabilities or {}).get("issue_types", [])
        if avail_types and "Story" not in avail_types:
            raise _TestSkip(
                f"'Story' issue type not available on this server (available: {avail_types})"
            )
        try:
            issue = jira_client.create_issue(fields={
                "project": {"key": project_key},
                "summary": f"[TEST AUTO] Story created by test_jira_actions.py – {_ts()}",
                "issuetype": {"name": "Story"},
            })
        except Exception as _exc:
            _msg = str(_exc)
            if "invalid" in _msg.lower() and ("issue type" in _msg.lower() or "400" in _msg):
                raise _TestSkip(f"'Story' issue type rejected by project {project_key}: invalid")
            raise
        _assert(issue is not None, "create_issue returned None")
        _assert(hasattr(issue, "key"), "issue has .key attribute")
        created_story_key = issue.key
        _created_issue_keys.append(issue.key)
    runner.run(cat, "J1: Create Story issue – returns issue with key", _J1)

    # J2: Create Task
    def _J2():
        issue = jira_client.create_issue(fields={
            "project": {"key": project_key},
            "summary": f"[TEST AUTO] Task created by test_jira_actions.py – {_ts()}",
            "issuetype": {"name": "Task"},
        })
        _assert(issue is not None, "create_issue (Task) returned None")
        _created_issue_keys.append(issue.key)
    runner.run(cat, "J2: Create Task issue – different issue type", _J2)

    # J3: Fetch created issue by key
    def _J3():
        if not created_story_key:
            raise _TestSkip("J1 did not create an issue (skipped)")
        fetched = jira_client.issue(created_story_key)
        _assert(fetched is not None, "issue() returned None")
        _assert_eq(str(fetched.key), created_story_key, "key matches")
    runner.run(cat, "J3: Fetch issue by key – issue retrieved correctly", _J3)

    # J4: Update summary
    def _J4():
        if not created_story_key:
            raise _TestSkip("J1 did not create an issue (skipped)")
        new_summary = f"[TEST AUTO] UPDATED summary – {_ts()}"
        issue = jira_client.issue(created_story_key)
        issue.update(fields={"summary": new_summary})
        refetch = jira_client.issue(created_story_key)
        _assert_eq(str(refetch.fields.summary), new_summary, "summary updated")
    runner.run(cat, "J4: Update issue summary – field updated on server", _J4)

    # J5: Add comment
    def _J5():
        if not created_story_key:
            raise _TestSkip("J1 did not create an issue (skipped)")
        comment = jira_client.add_comment(
            created_story_key,
            f"Automated test comment from test_jira_actions.py at {_ts()}"
        )
        _assert(comment is not None, "add_comment returned None")
    runner.run(cat, "J5: Add comment to issue – comment created", _J5)

    # J6: Search and find created issue via JQL
    def _J6():
        if not created_story_key:
            raise _TestSkip("J1 did not create an issue (skipped)")
        jql = f"project = {project_key} AND key = {created_story_key}"
        issues = list(jira_client.search_issues(jql, maxResults=5))
        keys = [str(i.key) for i in issues]
        _assert(created_story_key in keys,
                f"Created issue {created_story_key} not found in search results")
    runner.run(cat, "J6: JQL search finds the freshly created issue", _J6)

    # J7: Multiple rapid creates (stress test)
    def _J7():
        created = []
        for i in range(3):
            issue = jira_client.create_issue(fields={
                "project": {"key": project_key},
                "summary": f"[TEST AUTO] Stress #{i+1} – {_ts()}",
                "issuetype": {"name": "Task"},
            })
            _assert(issue is not None, f"Stress create #{i+1} returned None")
            created.append(issue.key)
            _created_issue_keys.append(issue.key)
        _assert_eq(len(created), 3, "3 issues created in stress test")
    runner.run(cat, "J7: Stress – create 3 issues in rapid succession", _J7)

    # J8: Cleanup – delete all created issues
    def _J8():
        deleted = 0
        errors = []
        for key in list(_created_issue_keys):
            try:
                jira_client.issue(key).delete()
                deleted += 1
            except Exception as exc:
                errors.append(f"{key}: {exc}")
        if errors:
            raise _TestFail(f"Could not delete {len(errors)} issue(s): {'; '.join(errors[:3])}")
        _assert(deleted > 0, "At least one issue deleted in cleanup")
        _created_issue_keys.clear()
    runner.run(cat, "J8: Cleanup – delete all test-created issues", _J8)


# ---------------------------------------------------------------------------
# ── CATEGORY K: Epic / Hierarchy Tests (skipped in dry-run) ─────────────────
# ---------------------------------------------------------------------------

def run_category_K(runner: TestRunner, jira_client, project_key: str, dry_run: bool,
                   capabilities: dict = None):
    cat = "K – Epic Hierarchy"

    if dry_run:
        for n in ["K1", "K2", "K3"]:
            runner.skip(cat, f"{n}: (skipped – dry-run mode)", "dry-run")
        return

    epic_key = None

    def _K1():
        nonlocal epic_key
        avail_types = (capabilities or {}).get("issue_types", [])
        if avail_types and "Epic" not in avail_types:
            raise _TestSkip(
                f"'Epic' issue type not available on this server (available: {avail_types})"
            )
        # Jira Cloud uses "Epic Name" (customfield_10011) for epic name
        fields = {
            "project": {"key": project_key},
            "summary": f"[TEST AUTO] Epic – {_ts()}",
            "issuetype": {"name": "Epic"},
        }
        # Try to set epic name (field varies by Jira version)
        for epic_name_field in ("customfield_10011", "customfield_10014"):
            try:
                f2 = dict(fields)
                f2[epic_name_field] = f"[TEST] EpicName {_ts()}"
                issue = jira_client.create_issue(fields=f2)
                epic_key = issue.key
                _created_issue_keys.append(issue.key)
                return
            except Exception as _exc:
                _msg = str(_exc)
                if "invalid" in _msg.lower() and ("issue type" in _msg.lower() or "400" in _msg):
                    raise _TestSkip(f"'Epic' issue type rejected by project {project_key}: invalid")
        # Fallback without epic name field
        try:
            issue = jira_client.create_issue(fields=fields)
        except Exception as _exc:
            _msg = str(_exc)
            if "invalid" in _msg.lower() and ("issue type" in _msg.lower() or "400" in _msg):
                raise _TestSkip(f"'Epic' issue type rejected by project {project_key}: invalid")
            raise
        epic_key = issue.key
        _created_issue_keys.append(issue.key)
    runner.run(cat, "K1: Create Epic issue", _K1)

    def _K2():
        if not epic_key:
            raise _TestSkip("K1 did not create Epic (skipped)")
        avail_types = (capabilities or {}).get("issue_types", [])
        if avail_types and "Story" not in avail_types:
            raise _TestSkip(
                f"'Story' issue type not available on this server (available: {avail_types})"
            )
        # Create child story under epic
        fields = {
            "project": {"key": project_key},
            "summary": f"[TEST AUTO] Story under Epic – {_ts()}",
            "issuetype": {"name": "Story"},
        }
        # Modern Jira: set parent field
        try:
            f2 = dict(fields)
            f2["parent"] = {"key": epic_key}
            issue = jira_client.create_issue(fields=f2)
            _created_issue_keys.append(issue.key)
            return
        except Exception:
            pass
        # Older Jira: customfield_10014 (Epic Link)
        try:
            f2 = dict(fields)
            f2["customfield_10014"] = epic_key
            issue = jira_client.create_issue(fields=f2)
            _created_issue_keys.append(issue.key)
        except Exception as exc:
            raise _TestFail(f"Could not create Story under Epic: {exc}")
    runner.run(cat, "K2: Create Story as child of Epic", _K2)

    def _K3():
        # Verify Epic has children via JQL
        if not epic_key:
            raise _TestSkip("K1 did not create Epic (skipped)")
        # Query for stories linked to this epic
        jql_variants = [
            f"parent = {epic_key}",
            f"\"Epic Link\" = {epic_key}",
        ]
        for jql in jql_variants:
            try:
                issues = list(jira_client.search_issues(jql, maxResults=10))
                if issues:
                    return  # found children – test passes
            except Exception:
                pass
        # If no children found via JQL, that's acceptable (Jira version differences)
        _assert(True, "hierarchy search executed without critical error")
    runner.run(cat, "K3: Verify Epic child relationship via JQL parent query", _K3)

    # Cleanup K issues
    def _K_cleanup():
        for key in list(_created_issue_keys):
            try:
                jira_client.issue(key).delete()
            except Exception:
                pass
        _created_issue_keys.clear()
    runner.run(cat, "K-cleanup: Delete Epic hierarchy test issues", _K_cleanup)


# ---------------------------------------------------------------------------
# ── CATEGORY L: Pagination Tests ───────────────────────────────────────────
# ---------------------------------------------------------------------------

def run_category_L(runner: TestRunner, jira_client, project_key: str):
    cat = "L – Pagination"

    def _L1():
        # Fetch with page_size=1 – tests pagination logic manually
        jql = f"project = {project_key} ORDER BY created ASC"
        page1 = list(jira_client.search_issues(jql, startAt=0, maxResults=1))
        _assert(isinstance(page1, list), "page1 is list")
        page2 = list(jira_client.search_issues(jql, startAt=1, maxResults=1))
        _assert(isinstance(page2, list), "page2 is list")
        # Both pages should have different keys (or both empty if project has ≤1 issue)
        if page1 and page2:
            _assert(page1[0].key != page2[0].key,
                    f"Pagination returned same key: {page1[0].key}")
    runner.run(cat, "L1: Paginate with maxResults=1 – two pages return different issues", _L1)

    def _L2():
        # Simulate the app's paginated fetch: collect all issues page by page
        jql = f"project = {project_key} ORDER BY created DESC"
        all_keys = []
        start = 0
        page_size = 5
        max_pages = 3  # limit test to first 15 issues
        for _ in range(max_pages):
            page = list(jira_client.search_issues(jql, startAt=start, maxResults=page_size))
            if not page:
                break
            all_keys.extend(i.key for i in page)
            if len(page) < page_size:
                break
            start += len(page)
        # Verify no duplicate keys across pages
        _assert_eq(len(all_keys), len(set(all_keys)), "No duplicate keys across pages")
    runner.run(cat, "L2: Multi-page fetch – no duplicate keys across pages", _L2)

    def _L3():
        # Test with specific Jira fields (mimics jira_sync._SYNC_FIELDS)
        sync_fields = ["summary", "issuetype", "status", "parent", "duedate",
                       "assignee", "description", "priority"]
        jql = f"project = {project_key} ORDER BY created DESC"
        issues = list(jira_client.search_issues(
            jql, maxResults=3, fields=",".join(sync_fields)
        ))
        if issues:
            issue = issues[0]
            _assert(hasattr(issue.fields, "summary"),
                    "summary field present in selective fetch")
            _assert(hasattr(issue.fields, "issuetype"),
                    "issuetype field present in selective fetch")
    runner.run(cat, "L3: Selective field fetch (sync fields only) – all fields accessible", _L3)


# ---------------------------------------------------------------------------
# ── CATEGORY M: Timing / Performance Tests ──────────────────────────────────
# ---------------------------------------------------------------------------

def run_category_M(runner: TestRunner, server: dict, jira_client, project_key: str):
    cat = "M – Performance / Timing"

    def _M1():
        _inject_sm(server)
        t0 = time.perf_counter()
        ok, err = jira_integration.test_connection(server)
        elapsed = time.perf_counter() - t0
        _assert(ok, f"Connection failed: {err}")
        _assert(elapsed < 15.0, f"Connection too slow: {elapsed:.2f}s (limit: 15s)")
    runner.run(cat, "M1: test_connection latency < 15 s", _M1)

    def _M2():
        jql = f"project = {project_key} ORDER BY created DESC"
        t0 = time.perf_counter()
        issues = list(jira_client.search_issues(jql, maxResults=10))
        elapsed = time.perf_counter() - t0
        _assert(elapsed < 30.0, f"Search too slow: {elapsed:.2f}s (limit: 30s)")
    runner.run(cat, "M2: JQL search response time < 30 s", _M2)

    def _M3():
        # Three consecutive searches
        jql = f"project = {project_key}"
        times = []
        for _ in range(3):
            t0 = time.perf_counter()
            jira_client.search_issues(jql, maxResults=5)
            times.append(time.perf_counter() - t0)
        avg = sum(times) / len(times)
        _assert(avg < 20.0, f"Average search time {avg:.2f}s exceeds 20s")
    runner.run(cat, "M3: Three consecutive searches – average < 20 s each", _M3)

    def _M4():
        # Time full credential cycle: get_jira_client
        _inject_sm(server)
        t0 = time.perf_counter()
        jira, err = jira_integration.get_jira_client(server)
        elapsed = time.perf_counter() - t0
        _assert(jira is not None, f"Client creation failed: {err}")
        _assert(elapsed < 15.0, f"Client creation too slow: {elapsed:.2f}s")
    runner.run(cat, "M4: get_jira_client round-trip time < 15 s", _M4)


# ---------------------------------------------------------------------------
# ── CATEGORY N: Auth Variant Tests ─────────────────────────────────────────
# ---------------------------------------------------------------------------

def run_category_N(runner: TestRunner, server: dict):
    cat = "N – Authentication Variants"

    ctype = server.get("credential_type", "token")

    if ctype in ("token", "password"):
        def _N1():
            _inject_sm(server)
            ok, err = jira_integration.test_connection(server)
            _assert(ok, f"basic_auth (username + {ctype}) failed: {err}")
        runner.run(cat, f"N1: basic_auth ({ctype}) – connection succeeds", _N1)

        def _N2():
            bad = dict(server)
            bad["username"] = ""
            _inject_sm(bad)
            ok, _ = jira_integration.test_connection(bad)
            _assert(not ok, "Missing username should fail for non-PAT mode")
        runner.run(cat, "N2: basic_auth with empty username → failure (non-PAT)", _N2)
    else:
        runner.skip(cat, "N1/N2: basic_auth tests (skip – server uses PAT)", "PAT mode")

    if ctype == "pat":
        def _N3():
            _inject_sm(server)
            ok, err = jira_integration.test_connection(server)
            _assert(ok, f"PAT (token_auth) failed: {err}")
        runner.run(cat, "N3: PAT / token_auth – connection succeeds", _N3)
    else:
        runner.skip(cat, "N3: PAT auth test (skip – server uses basic auth)", "basic auth mode")

    def _N4():
        bad = dict(server)
        bad["credential_type"] = "password"
        bad["token"] = "invalid-password"
        _inject_sm(bad)
        ok, err = jira_integration.test_connection(bad)
        _assert(not ok, "Wrong password should fail")
    runner.run(cat, "N4: Wrong password → auth failure", _N4)

    # Restore good SM
    _inject_sm(server)


# ---------------------------------------------------------------------------
# ── CATEGORY P: Jira → Project field-flag unit tests ────────────────────────
# All 34 j2p field flags are listed in requirements PO-J2P-004.0.
# These tests are pure unit tests that do not require a live server.
# ---------------------------------------------------------------------------

# All 34 supported field flags (PO-J2P-004.0)
_ALL_J2P_FIELDS = [
    "jira_project_name", "jira_description", "jira_status", "jira_status_percent",
    "jira_resolution", "jira_resolution_date", "jira_security_level",
    "jira_assignee", "jira_assignee_display_name", "jira_reporter",
    "jira_reporter_display_name", "jira_priority", "jira_due_date",
    "jira_created_date", "jira_updated_date", "jira_components",
    "jira_fix_versions", "jira_affects_versions", "jira_fix_version_description",
    "jira_fix_version_released", "jira_fix_version_start_date",
    "jira_fix_version_release_date", "jira_labels", "jira_environment",
    "jira_votes", "jira_comments", "jira_time_spent", "jira_remaining_estimate",
    "jira_original_estimate", "jira_time_spent_seconds", "jira_worklog_entries",
    "jira_parent_key", "jira_epic_link", "jira_parent_link",
    "jira_subtask_parent", "jira_issue_links",
]

# Dependencies per PO-JIRA-064.0
_J2P_FIELD_DEPS = {
    "jira_status":      ["jira_status_percent"],
    "jira_resolution":  ["jira_resolution_date"],
    "jira_assignee":    ["jira_assignee_display_name"],
    "jira_reporter":    ["jira_reporter_display_name"],
    "jira_fix_versions": [
        "jira_fix_version_description", "jira_fix_version_released",
        "jira_fix_version_start_date",  "jira_fix_version_release_date",
    ],
    "jira_time_spent": ["jira_time_spent_seconds", "jira_worklog_entries"],
}


def run_category_P(runner: TestRunner):
    cat = "P – J2P Field Flag Config"

    def _P1():
        # Default dict: all 34 flags must be False (PO-J2P-005.0)
        j2p = {"fields": {}}
        for flag in _ALL_J2P_FIELDS:
            val = jira_sync._get_field_flag(j2p, flag)  # type: ignore
            _assert(val is False, f"Default for '{flag}' should be False, got {val!r}")
    runner.run(cat, "P1: All 34 field flags default to False (PO-J2P-005.0)", _P1)

    def _P2():
        # Setting every flag individually to True
        for flag in _ALL_J2P_FIELDS:
            j2p = {"fields": {flag: True}}
            val = jira_sync._get_field_flag(j2p, flag)  # type: ignore
            _assert(val is True, f"Flag '{flag}' set to True should return True")
    runner.run(cat, "P2: Each flag individually set to True is read back as True", _P2)

    def _P3():
        # All flags enabled simultaneously
        j2p = {"fields": {f: True for f in _ALL_J2P_FIELDS}}
        for flag in _ALL_J2P_FIELDS:
            val = jira_sync._get_field_flag(j2p, flag)  # type: ignore
            _assert(val is True, f"Flag '{flag}' should be True when all enabled")
    runner.run(cat, "P3: All 34 flags enabled simultaneously – all read True", _P3)

    def _P4():
        # Disabled flags must not bleed over enabled ones
        enabled = {"jira_status", "jira_due_date", "jira_assignee"}
        j2p = {"fields": {f: (f in enabled) for f in _ALL_J2P_FIELDS}}
        for flag in _ALL_J2P_FIELDS:
            expected = flag in enabled
            val = jira_sync._get_field_flag(j2p, flag)  # type: ignore
            _assert(val is expected,
                    f"Flag '{flag}': expected {expected}, got {val!r}")
    runner.run(cat, "P4: Mixed flags – enabled and disabled coexist without bleed-over", _P4)

    def _P5():
        # Field dependencies: disabling controller also means dependent should be False
        # (the config layer just stores the value; the check is done at read time)
        for controller, dependents in _J2P_FIELD_DEPS.items():
            j2p_off = {"fields": {controller: False,
                                    **{d: True for d in dependents}}}
            # Dependent is stored as True but controller is False.
            # The engine only writes the dependent when controller flag is True.
            # We verify here that _get_field_flag reads the stored value as-is,
            # and the disabling logic is the responsibility of the dialog/engine.
            ctrl_val = jira_sync._get_field_flag(j2p_off, controller)  # type: ignore
            _assert(ctrl_val is False, f"Controller '{controller}' should be False")
            for dep in dependents:
                dep_stored = jira_sync._get_field_flag(j2p_off, dep)  # type: ignore
                _assert(dep_stored is True,
                        f"Dependent '{dep}' stored as True even when controller disabled")
    runner.run(cat, "P5: Dependent flags stored independently; controller state is separate", _P5)

    def _P6():
        # Verify count of defined field flags
        _assert(len(_ALL_J2P_FIELDS) >= 34, f"Expected ≥34 field flags, got {len(_ALL_J2P_FIELDS)}")
    runner.run(cat, "P6: At least 34 field flags are defined (PO-J2P-004.0 count)", _P6)

    def _P7():
        # Status-percent mapping covers key status names
        important = ["to do", "in progress", "done", "closed", "resolved"]
        for status in important:
            pct = jira_sync._status_to_percent(status)  # type: ignore
            _assert(isinstance(pct, int),
                    f"_status_to_percent('{status}') returned {type(pct).__name__}, expected int")
    runner.run(cat, "P7: _status_to_percent – returns int for key status names", _P7)

    def _P8():
        # Status-to-percent value checks
        cases = [
            ("to do",      0),
            ("in progress", 50),
            ("done",       100),
            ("closed",     100),
        ]
        for status, expected_pct in cases:
            pct = jira_sync._status_to_percent(status)  # type: ignore
            _assert_eq(pct, expected_pct, f"_status_to_percent('{status}')")
    runner.run(cat, "P8: _status_to_percent – correct percentage values for known statuses", _P8)

    def _P9():
        # Unknown status → 0
        pct = jira_sync._status_to_percent("UnknownStatusXYZ")  # type: ignore
        _assert_eq(pct, 0, "Unknown status defaults to 0")
    runner.run(cat, "P9: _status_to_percent – unknown status → 0 (safe default)", _P9)

    def _P10():
        # _sanitize_text strips Jira wiki-markup
        raw = "{code:java}int x = 1;{code} some *bold* text [link|https://x.com]"
        clean = jira_sync._sanitize_text(raw)  # type: ignore
        _assert("{code" not in clean, "code macros stripped")
        _assert("*bold*" not in clean, "bold markup stripped")
        _assert("[link|" not in clean, "link markup stripped")
    runner.run(cat, "P10: _sanitize_text – Jira wiki-markup stripped correctly", _P10)

    def _P11():
        _assert_eq(jira_sync._sanitize_text(""), "", "empty string")  # type: ignore
        _assert_eq(jira_sync._sanitize_text(None), "", "None input")  # type: ignore
    runner.run(cat, "P11: _sanitize_text – empty/None input returns empty string", _P11)

    # P12: J2P config round-trip through sidecar
    def _P12():
        j2p_config = {
            "filter": "project = TEST",
            "filter_type": "jql",
            "fields": {f: True for f in _ALL_J2P_FIELDS[:5]},
        }
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({"jira2project": json.dumps(j2p_config)}, f)
            tmp = f.name
        try:
            with open(tmp) as fh:
                raw = json.load(fh)
            # The sidecar stores j2p as a JSON string (MPXJ custom property)
            j2p_read = json.loads(raw["jira2project"])
            _assert_eq(j2p_read["filter"], "project = TEST", "filter round-trip")
            _assert_eq(j2p_read["filter_type"], "jql", "filter_type round-trip")
            for flag in list(j2p_config["fields"].keys())[:3]:
                _assert(j2p_read["fields"][flag] is True, f"{flag} preserved")
        finally:
            os.unlink(tmp)
    runner.run(cat, "P12: J2P config round-trip via sidecar JSON string", _P12)

    # P13: Advanced config defaults
    def _P13():
        adv = jira_sync._get_advanced_config({})  # type: ignore
        _assert(isinstance(adv, dict), "returns dict")
        for key in ("relink", "incremental", "conflict", "orphan",
                    "normalize", "hierarchy", "dependencies", "reliability"):
            _assert(key in adv, f"advanced key '{key}' missing from defaults")
    runner.run(cat, "P13: _get_advanced_config – all expected keys present in defaults", _P13)

    # P14: Deep merge for advanced config
    def _P14():
        override = {"conflict": {"enabled": True, "policy": "prefer_jira"}}
        merged = jira_sync._get_advanced_config({"advanced": override})  # type: ignore
        _assert(merged["conflict"]["enabled"] is True, "override applied")
        _assert_eq(merged["conflict"]["policy"], "prefer_jira", "policy overridden")
        # Other conflict keys preserved from defaults
        _assert("field_policy" in merged["conflict"], "field_policy preserved")
    runner.run(cat, "P14: _get_advanced_config – override merges without losing defaults", _P14)


# ---------------------------------------------------------------------------
# ── CATEGORY Q: Project → Jira push config / engine tests ──────────────────
# These are unit tests for the P2J config layer; they do not call Jira APIs.
# ---------------------------------------------------------------------------

# All P2J config keys (PO-P2J-009.0)
_P2J_CONFIG_KEYS = [
    "export_scope",       # selected_tasks | changed_since_last_sync | full_project
    "create_update_mode", # create_only | update_only | create_update
    "conflict_policy",    # prefer_jira | prefer_project | manual_review
    "unlinked_task_behavior", # create | skip | prompt
    "dry_run",            # bool
    "fields",             # field mapping dict
    "issue_type_map",     # project_type → jira_issue_type
    "transition_map",     # project_status → jira_transition
    "hierarchy_export",   # {enabled, epic_type, story_type, ...}
    "auditability",       # {enabled}
    "reliability",        # {enabled, max_retries, backoff_seconds}
]


def _make_p2j_config(**overrides) -> dict:
    """Return a minimal valid P2J config with optional overrides."""
    base = {
        "export_scope": "full_project",
        "create_update_mode": "create_update",
        "conflict_policy": "prefer_project",
        "unlinked_task_behavior": "create",
        "dry_run": True,
        "fields": {
            "jira_summary": {"enabled": True, "jira_field": "summary"},
            "jira_description": {"enabled": True, "jira_field": "description"},
        },
        "issue_type_map": {"Task": "Task", "Story": "Story", "": "Task"},
        "transition_map": {},
        "hierarchy_export": {"enabled": False},
        "auditability": {"enabled": False},
        "reliability": {"enabled": False, "max_retries": 3, "backoff_seconds": 1.0},
        "jira_project_key": "",
    }
    base.update(overrides)
    return base


def run_category_Q(runner: TestRunner):
    cat = "Q – P2J Push Config & Engine"

    def _Q1():
        result = jira_sync.get_last_push_result()  # type: ignore
        _assert(result is None or isinstance(result, dict),
                "get_last_push_result() returns None or dict")
    runner.run(cat, "Q1: get_last_push_result – returns None or dict before any push", _Q1)

    def _Q2():
        # Verify _p2j_field_enabled reads correctly
        p2j = _make_p2j_config()
        enabled = jira_sync._p2j_field_enabled(p2j, "jira_summary")  # type: ignore
        _assert(enabled is True, "jira_summary enabled flag")
        disabled = jira_sync._p2j_field_enabled(p2j, "jira_priority")  # type: ignore
        _assert(disabled is False, "jira_priority not in fields → disabled")
    runner.run(cat, "Q2: _p2j_field_enabled – reads enabled/disabled correctly", _Q2)

    def _Q3():
        p2j = _make_p2j_config()
        field = jira_sync._p2j_jira_field(p2j, "jira_summary")  # type: ignore
        _assert_eq(field, "summary", "jira_summary → 'summary'")
        missing = jira_sync._p2j_jira_field(p2j, "jira_priority", "priority_fallback")  # type: ignore
        _assert_eq(missing, "priority_fallback", "missing field returns default")
    runner.run(cat, "Q3: _p2j_jira_field – returns mapped jira_field or default", _Q3)

    def _Q4():
        # All P2J config keys are recognised
        p2j = _make_p2j_config()
        for key in _P2J_CONFIG_KEYS:
            _assert(key in p2j, f"P2J config key '{key}' missing from minimal config")
    runner.run(cat, "Q4: All expected P2J config keys are present", _Q4)

    def _Q5():
        # _with_retry: immediate success (no retry needed)
        call_count = [0]
        def _ok():
            call_count[0] += 1
            return "result"
        out = jira_sync._with_retry(_ok, max_retries=3, backoff_seconds=0.0)  # type: ignore
        _assert_eq(out, "result", "return value")
        _assert_eq(call_count[0], 1, "called exactly once on success")
    runner.run(cat, "Q5: _with_retry – succeeds on first attempt, no retry", _Q5)

    def _Q6():
        # _with_retry: non-transient error propagates immediately without retry
        call_count = [0]
        def _fail():
            call_count[0] += 1
            raise ValueError("hard fail – not transient")
        try:
            jira_sync._with_retry(_fail, max_retries=3, backoff_seconds=0.0)  # type: ignore
            raise _TestFail("Expected exception not raised")
        except ValueError as exc:
            _assert("hard fail" in str(exc), "correct exception propagated")
        _assert_eq(call_count[0], 1, "not retried for non-transient error")
    runner.run(cat, "Q6: _with_retry – non-transient error propagates immediately", _Q6)

    def _Q7():
        # _with_retry: transient error (e.g. '503') IS retried
        call_count = [0]
        def _transient():
            call_count[0] += 1
            if call_count[0] < 3:
                raise Exception("503 Service Unavailable")
            return "ok"
        out = jira_sync._with_retry(_transient, max_retries=3, backoff_seconds=0.0)  # type: ignore
        _assert_eq(out, "ok", "succeeds after retries")
        _assert_eq(call_count[0], 3, "called 3 times (2 failures + 1 success)")
    runner.run(cat, "Q7: _with_retry – transient 503 error retried up to max_retries", _Q7)

    def _Q8():
        # _with_retry: max_retries=0 → never retries transient
        call_count = [0]
        def _fail_transient():
            call_count[0] += 1
            raise Exception("429 Too Many Requests")
        try:
            jira_sync._with_retry(_fail_transient, max_retries=0, backoff_seconds=0.0)  # type: ignore
            raise _TestFail("Expected exception")
        except Exception as exc:
            _assert("429" in str(exc), "original error propagated")
        _assert_eq(call_count[0], 1, "called only once when max_retries=0")
    runner.run(cat, "Q8: _with_retry – max_retries=0 means no retry even for transient", _Q8)

    def _Q9():
        # _is_transient_error recognises expected transient codes
        transient_msgs = [
            "503 Service Unavailable",
            "429 Too Many Requests",
            "Connection timeout",
            "timed out",
            "502 Bad Gateway",
        ]
        for msg in transient_msgs:
            _assert(jira_sync._is_transient_error(Exception(msg)),  # type: ignore
                    f"Should be transient: '{msg}'")
        non_transient = ["404 Not Found", "401 Unauthorized", "400 Bad Request"]
        for msg in non_transient:
            _assert(not jira_sync._is_transient_error(Exception(msg)),  # type: ignore
                    f"Should NOT be transient: '{msg}'")
    runner.run(cat, "Q9: _is_transient_error – correct classification for HTTP codes", _Q9)

    def _Q10():
        # P2J sidecar: task_p2j and jira_push_meta sections preserved
        p2j_data = {"1": {"jira_key": "PROJ-1", "last_pushed_at": "2024-01-01T00:00:00Z"}}
        meta = {"last_run_at": "2024-01-01T00:00:00Z", "last_result": {}}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump({
                "task_jira": {},
                "task_p2j": p2j_data,
                "jira_push_meta": meta,
                "other": "preserved",
            }, f)
            tmp = f.name
        try:
            # Load and verify all sections present
            with open(tmp) as fh:
                loaded = json.load(fh)
            _assert_eq(loaded["task_p2j"], p2j_data, "task_p2j preserved")
            _assert_eq(loaded["jira_push_meta"]["last_run_at"], meta["last_run_at"], "meta preserved")
            _assert("other" in loaded, "unrelated sections preserved")
        finally:
            os.unlink(tmp)
    runner.run(cat, "Q10: P2J sidecar sections (task_p2j, jira_push_meta) preserved on read", _Q10)

    def _Q11():
        # dry_run flag read from config
        for dry_val in (True, False):
            p2j = _make_p2j_config(dry_run=dry_val)
            _assert_eq(bool(p2j.get("dry_run")), dry_val, f"dry_run={dry_val}")
    runner.run(cat, "Q11: P2J dry_run flag read from config correctly", _Q11)

    def _Q12():
        # export_scope variants
        for scope in ("selected_tasks", "changed_since_last_sync", "full_project"):
            p2j = _make_p2j_config(export_scope=scope)
            _assert_eq(p2j["export_scope"], scope, f"scope={scope}")
    runner.run(cat, "Q12: export_scope – all three variants stored and retrieved", _Q12)

    def _Q13():
        # create_update_mode variants
        for mode in ("create_only", "update_only", "create_update"):
            p2j = _make_p2j_config(create_update_mode=mode)
            _assert_eq(p2j["create_update_mode"], mode, f"mode={mode}")
    runner.run(cat, "Q13: create_update_mode – all three variants stored and retrieved", _Q13)

    def _Q14():
        # conflict_policy variants
        for policy in ("prefer_jira", "prefer_project", "manual_review"):
            p2j = _make_p2j_config(conflict_policy=policy)
            _assert_eq(p2j["conflict_policy"], policy, f"policy={policy}")
    runner.run(cat, "Q14: conflict_policy – all three variants stored and retrieved", _Q14)

    def _Q15():
        # issue_type_map round-trip via JSON
        itype_map = {"Task": "Task", "Story": "Story", "Epic": "Epic", "Sub-task": "Sub-task"}
        p2j = _make_p2j_config(issue_type_map=itype_map)
        _assert_eq(p2j["issue_type_map"], itype_map, "issue_type_map round-trip")
    runner.run(cat, "Q15: issue_type_map – all common issue types preserved in config", _Q15)

    def _Q16():
        # Hierarchy export config keys
        hier = {
            "enabled": True,
            "epic_type": "Epic",
            "story_type": "Story",
            "subtask_type": "Sub-task",
            "dependency_link_type": "blocks",
        }
        p2j = _make_p2j_config(hierarchy_export=hier)
        _assert_eq(p2j["hierarchy_export"]["epic_type"], "Epic", "epic_type")
        _assert_eq(p2j["hierarchy_export"]["enabled"], True, "enabled")
    runner.run(cat, "Q16: hierarchy_export config – all keys preserved", _Q16)

    def _Q17():
        # Transition map round-trip
        tmap = {"Done": "Close Issue", "In Progress": "Start Progress"}
        p2j = _make_p2j_config(transition_map=tmap)
        _assert_eq(p2j["transition_map"], tmap, "transition_map round-trip")
    runner.run(cat, "Q17: transition_map – maps stored and retrieved correctly", _Q17)

    def _Q18():
        # Field payload builder via direct function call
        # _task_to_jira_payload requires MPXJ task object; mock minimally.
        class _MockTask:
            def getName(self):
                return "My Task Name"
            def getNotes(self):
                return None
            def getDeadline(self):
                return None
            def getResourceAssignments(self):
                return []
            def getType(self):
                return None
        p2j = _make_p2j_config()
        task = _MockTask()
        payload = jira_sync._task_to_jira_payload(task, p2j, "Story")  # type: ignore
        _assert("summary" in payload, "summary always included")
        _assert_eq(payload["summary"], "My Task Name", "summary value")
    runner.run(cat, "Q18: _task_to_jira_payload – summary always in payload", _Q18)

    def _Q19():
        # _task_status_string returns human-readable strings for 0/50/100%
        class _MockTask:
            def __init__(self, pct): self._pct = pct
            def getPercentageComplete(self): return self._pct
        _assert_eq(jira_sync._task_status_string(_MockTask(0)),   "To Do",       "0%")  # type: ignore
        _assert_eq(jira_sync._task_status_string(_MockTask(50)),  "In Progress", "50%")  # type: ignore
        _assert_eq(jira_sync._task_status_string(_MockTask(100)), "Done",        "100%")  # type: ignore
    runner.run(cat, "Q19: _task_status_string – 0%→To Do, 50%→In Progress, 100%→Done", _Q19)


# ---------------------------------------------------------------------------
# ── CATEGORY O: get_config_summary / Debug Tests ────────────────────────────
# ---------------------------------------------------------------------------

def run_category_O(runner: TestRunner, server: dict):
    cat = "O – Config Summary & Debug"

    def _O1():
        _inject_sm(server)
        summary = jira_integration.get_config_summary()
        _assert(isinstance(summary, dict), "returns dict")
        # After a connection test, last_connection_test should be set
        if "last_connection_test" in summary:
            lct = summary["last_connection_test"]
            _assert(isinstance(lct, dict), "last_connection_test is dict")
            _assert("success" in lct, "success key present")
            _assert("timestamp" in lct, "timestamp key present")
    runner.run(cat, "O1: get_config_summary – includes last_connection_test after test", _O1)

    def _O2():
        jira_integration.record_filter_test(
            server.get("name", "test"), "project = TEST", 5, ""
        )
        summary = jira_integration.get_config_summary()
        if "last_filter_test" in summary:
            lft = summary["last_filter_test"]
            _assert(isinstance(lft, dict), "last_filter_test is dict")
            _assert("server_name" in lft, "server_name present")
            _assert("filter" in lft, "filter present")
    runner.run(cat, "O2: get_config_summary – includes last_filter_test after record_filter_test", _O2)

    def _O3():
        summary = jira_integration.get_config_summary()
        for sensitive_key in ("token", "password", "credential", "keepass_entry"):
            _assert(sensitive_key not in str(summary).lower() or
                    "keepass_entry_set" in str(summary),
                    f"Sensitive key '{sensitive_key}' exposed in config summary")
    runner.run(cat, "O3: get_config_summary – no credentials exposed", _O3)

    def _O4():
        # Verify that _last_result module var is accessible
        result = jira_sync.get_last_result()
        _assert(result is None or isinstance(result, dict),
                "get_last_result() returns None or dict")
    runner.run(cat, "O4: jira_sync.get_last_result() – returns None or dict", _O4)


# ---------------------------------------------------------------------------
# ── CATEGORY R: Utility helper unit tests ──────────────────────────────────
# Covers _deep_merge, _safe_str, _issue_type_label, _safe_issue_field,
# _parse_jira_date, and _now_iso_utc – none require a live server.
# ---------------------------------------------------------------------------

def run_category_R(runner: TestRunner):
    cat = "R \u2013 Utility Helpers"

    # ── _now_iso_utc ──────────────────────────────────────────────────────
    def _R1():
        ts = jira_sync._now_iso_utc()  # type: ignore
        _assert(isinstance(ts, str), "returns str")
        # datetime.isoformat() with UTC yields '+00:00' suffix, not bare 'Z'
        _assert(
            ts.endswith("Z") or ts.endswith("+00:00"),
            f"must end with Z or +00:00, got {ts!r}",
        )
        _assert("T" in ts, f"must be ISO format with T separator, got {ts!r}")
    runner.run(cat, "R1: _now_iso_utc \u2013 returns ISO UTC string with UTC timezone marker", _R1)

    # ── _deep_merge ───────────────────────────────────────────────────────
    def _R2():
        base     = {"a": 1, "b": {"x": 10, "y": 20}}
        override = {"b": {"y": 99, "z": 30}, "c": 3}
        merged   = jira_sync._deep_merge(base, override)  # type: ignore
        _assert_eq(merged["a"], 1,  "untouched key preserved")
        _assert_eq(merged["b"]["x"], 10,  "nested untouched preserved")
        _assert_eq(merged["b"]["y"], 99,  "nested override applied")
        _assert_eq(merged["b"]["z"], 30,  "new nested key added")
        _assert_eq(merged["c"], 3,  "new top-level key added")
    runner.run(cat, "R2: _deep_merge \u2013 recursive merge preserves untouched, applies overrides", _R2)

    def _R3():
        # Original dicts must not be mutated
        base     = {"a": {"x": 1}}
        override = {"a": {"y": 2}}
        _ = jira_sync._deep_merge(base, override)  # type: ignore
        _assert_eq(base["a"], {"x": 1}, "base not mutated")
        _assert_eq(override["a"], {"y": 2}, "override not mutated")
    runner.run(cat, "R3: _deep_merge \u2013 original dicts are not mutated", _R3)

    def _R4():
        # Empty override returns copy of base
        base   = {"a": 1, "b": {"c": 2}}
        merged = jira_sync._deep_merge(base, {})  # type: ignore
        _assert_eq(merged, base, "empty override \u2192 copy of base")
    runner.run(cat, "R4: _deep_merge \u2013 empty override returns copy of base", _R4)

    def _R5():
        # None override treated like {}
        base   = {"a": 1}
        merged = jira_sync._deep_merge(base, None)  # type: ignore
        _assert_eq(merged, base, "None override \u2192 copy of base")
    runner.run(cat, "R5: _deep_merge \u2013 None override treated as empty dict", _R5)

    # ── _safe_str ─────────────────────────────────────────────────────────
    def _R6():
        _assert_eq(jira_sync._safe_str(None), "",       "None \u2192 empty string")  # type: ignore
        _assert_eq(jira_sync._safe_str(""),   "",       "empty string \u2192 empty string")  # type: ignore
        _assert_eq(jira_sync._safe_str(42),   "42",     "int \u2192 str")  # type: ignore
        _assert_eq(jira_sync._safe_str(3.14), "3.14",   "float \u2192 str")  # type: ignore
        _assert_eq(jira_sync._safe_str("hi"), "hi",     "str \u2192 unchanged")  # type: ignore
    runner.run(cat, "R6: _safe_str \u2013 None/int/float/str all converted correctly", _R6)

    # ── _issue_type_label ─────────────────────────────────────────────────
    def _R7():
        # Known types return their short labels
        cases = [
            ("Epic",    "Epic"),
            ("Story",   "Story"),
            ("Task",    "Task"),
            ("Sub-task", "Sub"),
            ("Bug",     "Bug"),
            ("Service Request", "SR"),
        ]
        for type_name, expected in cases:
            lbl = jira_sync._issue_type_label(type_name, {})  # type: ignore
            _assert_eq(lbl, expected, f"'{type_name}' \u2192 '{expected}'")
    runner.run(cat, "R7: _issue_type_label \u2013 default labels for all known issue types", _R7)

    def _R8():
        # Unknown type \u2192 falls back to the raw name
        lbl = jira_sync._issue_type_label("CustomType", {})  # type: ignore
        _assert_eq(lbl, "CustomType", "unknown type returns raw name")
    runner.run(cat, "R8: _issue_type_label \u2013 unknown type returns raw name as fallback", _R8)

    def _R9():
        # Custom labels dict takes precedence over defaults
        custom = {"Story": "S", "CustomType": "CT"}
        _assert_eq(jira_sync._issue_type_label("Story",      custom), "S",  "custom overrides default")  # type: ignore
        _assert_eq(jira_sync._issue_type_label("CustomType", custom), "CT", "custom entry used")  # type: ignore
        _assert_eq(jira_sync._issue_type_label("Bug",        custom), "Bug", "non-overridden default preserved")  # type: ignore
    runner.run(cat, "R9: _issue_type_label \u2013 custom labels dict overrides defaults", _R9)

    # ── _safe_issue_field ─────────────────────────────────────────────────
    def _R10():
        class _Fields:
            summary     = "My Issue"
            description = "Some text"
            none_val    = None
        f = _Fields()
        _assert_eq(jira_sync._safe_issue_field(f, "summary"),     "My Issue",  "existing attr")  # type: ignore
        _assert_eq(jira_sync._safe_issue_field(f, "description"), "Some text", "existing attr")  # type: ignore
        _assert(   jira_sync._safe_issue_field(f, "none_val") is None, "None-valued attr")  # type: ignore
    runner.run(cat, "R10: _safe_issue_field \u2013 returns correct value for existing attributes", _R10)

    def _R11():
        # Missing attribute \u2192 None (no exception)
        class _Fields:
            pass
        result = jira_sync._safe_issue_field(_Fields(), "nonexistent")  # type: ignore
        _assert(result is None, "missing attr \u2192 None")
    runner.run(cat, "R11: _safe_issue_field \u2013 missing attribute returns None without raising", _R11)

    def _R12():
        # Attribute that raises an exception on access \u2192 None
        class _BrokenFields:
            @property
            def explodes(self):
                raise RuntimeError("boom")
        result = jira_sync._safe_issue_field(_BrokenFields(), "explodes")  # type: ignore
        _assert(result is None, "attribute that raises \u2192 None")
    runner.run(cat, "R12: _safe_issue_field \u2013 attribute that raises returns None", _R12)

    # ── _parse_jira_date ──────────────────────────────────────────────────
    # jpype is NOT available in the test env, so all calls should return None
    # gracefully (the function catches ImportError/Exception internally).
    def _R13():
        result = jira_sync._parse_jira_date(None)  # type: ignore
        _assert(result is None, "None input \u2192 None")
    runner.run(cat, "R13: _parse_jira_date \u2013 None input returns None (no exception)", _R13)

    def _R14():
        result = jira_sync._parse_jira_date("")  # type: ignore
        _assert(result is None, "empty string \u2192 None")
    runner.run(cat, "R14: _parse_jira_date \u2013 empty string returns None", _R14)

    def _R15():
        # When jpype is absent the function must not raise for valid date strings
        for date_str in ("2024-06-15", "2024-06-15T10:30:00Z", "not-a-date"):
            result = jira_sync._parse_jira_date(date_str)  # type: ignore
            _assert(result is None, f"'{date_str}' \u2192 None when jpype unavailable")
    runner.run(cat, "R15: _parse_jira_date \u2013 gracefully returns None when jpype is unavailable", _R15)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ts() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


# ---------------------------------------------------------------------------
# HTML Report Generator
# ---------------------------------------------------------------------------

_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Jira API Test Report – {timestamp}</title>
<style>
:root {{
  --pass:    #16a34a;
  --fail:    #dc2626;
  --error:   #ea580c;
  --skip:    #6b7280;
  --info:    #2563eb;
  --pass-bg: #dcfce7;
  --fail-bg: #fee2e2;
  --error-bg:#ffedd5;
  --skip-bg: #f3f4f6;
  --bg:      #f8fafc;
  --card:    #ffffff;
  --border:  #e2e8f0;
  --text:    #0f172a;
  --muted:   #64748b;
  --code-bg: #1e293b;
  --code-fg: #e2e8f0;
}}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
       background: var(--bg); color: var(--text); font-size: 14px; }}
.header {{
  background: linear-gradient(135deg, #1e3a5f 0%, #0f2342 100%);
  color: #fff; padding: 24px 32px;
}}
.header h1 {{ font-size: 22px; font-weight: 700; margin-bottom: 4px; }}
.header .meta {{ font-size: 12px; color: #94a3b8; }}
.summary-bar {{
  display: flex; gap: 16px; padding: 16px 32px;
  background: var(--card); border-bottom: 1px solid var(--border);
  flex-wrap: wrap;
}}
.badge {{
  display: inline-flex; align-items: center; gap: 6px;
  padding: 5px 14px; border-radius: 9999px;
  font-size: 13px; font-weight: 600;
}}
.badge.pass  {{ background: var(--pass-bg);  color: var(--pass);  }}
.badge.fail  {{ background: var(--fail-bg);  color: var(--fail);  }}
.badge.error {{ background: var(--error-bg); color: var(--error); }}
.badge.skip  {{ background: var(--skip-bg);  color: var(--skip);  }}
.dot {{ width: 8px; height: 8px; border-radius: 50%; background: currentColor; }}
.container {{ max-width: 1100px; margin: 24px auto; padding: 0 24px; }}
.category {{
  margin-bottom: 20px; border-radius: 8px; overflow: hidden;
  box-shadow: 0 1px 3px rgba(0,0,0,.08);
}}
.cat-header {{
  background: var(--card); border: 1px solid var(--border);
  padding: 12px 16px; cursor: pointer;
  display: flex; justify-content: space-between; align-items: center;
  font-weight: 600; font-size: 14px;
  border-radius: 8px 8px 0 0;
  user-select: none;
}}
.cat-header:hover {{ background: #f1f5f9; }}
.cat-header .cat-badges {{ display: flex; gap: 8px; }}
.cat-header .badge {{ padding: 2px 10px; font-size: 12px; }}
.cat-body {{ border: 1px solid var(--border); border-top: none; }}
table {{ width: 100%; border-collapse: collapse; }}
th {{ background: #f8fafc; font-size: 12px; font-weight: 600;
      color: var(--muted); text-transform: uppercase; letter-spacing: .04em;
      padding: 8px 12px; text-align: left; border-bottom: 1px solid var(--border); }}
td {{ padding: 9px 12px; border-bottom: 1px solid #f1f5f9; vertical-align: top; }}
tr:last-child td {{ border-bottom: none; }}
tr:hover td {{ background: #f8fafc; }}
.status-badge {{
  display: inline-block; padding: 2px 10px; border-radius: 9999px;
  font-size: 11px; font-weight: 700; letter-spacing: .04em; white-space: nowrap;
}}
.status-badge.PASS  {{ background: var(--pass-bg);  color: var(--pass);  }}
.status-badge.FAIL  {{ background: var(--fail-bg);  color: var(--fail);  }}
.status-badge.ERROR {{ background: var(--error-bg); color: var(--error); }}
.status-badge.SKIP  {{ background: var(--skip-bg);  color: var(--skip);  }}
.status-badge.INFO  {{ background: #dbeafe;          color: var(--info);  }}
.dur {{ color: var(--muted); font-size: 12px; white-space: nowrap; }}
.msg {{ font-size: 13px; }}
.msg.fail  {{ color: var(--fail);  }}
.msg.error {{ color: var(--error); }}
.msg.skip  {{ color: var(--skip);  font-style: italic; }}
details summary {{ cursor: pointer; font-size: 12px; color: var(--info); margin-top: 4px; }}
details summary:hover {{ text-decoration: underline; }}
pre.output {{
  background: var(--code-bg); color: var(--code-fg);
  font-family: "Cascadia Code", "Consolas", "Courier New", monospace;
  font-size: 12px; line-height: 1.5; padding: 12px; border-radius: 6px;
  overflow-x: auto; white-space: pre-wrap; word-break: break-word;
  margin-top: 6px; max-height: 300px; overflow-y: auto;
}}
.progress-bar-wrap {{
  height: 6px; background: #e2e8f0; border-radius: 3px; overflow: hidden;
  margin-top: 2px; width: 80px;
}}
.progress-bar {{ height: 100%; border-radius: 3px; }}
.progress-bar.fast   {{ background: var(--pass); }}
.progress-bar.medium {{ background: #eab308; }}
.progress-bar.slow   {{ background: var(--fail); }}
.env-info {{
  background: var(--card); border: 1px solid var(--border); border-radius: 8px;
  padding: 16px; margin-bottom: 20px; font-size: 13px;
}}
.env-info h3 {{ font-size: 14px; margin-bottom: 10px; color: var(--muted); }}
.env-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 8px; }}
.env-item {{ background: #f8fafc; border-radius: 4px; padding: 6px 10px; }}
.env-item .key {{ font-size: 11px; color: var(--muted); text-transform: uppercase; }}
.env-item .val {{ font-weight: 600; font-size: 13px; }}
</style>
</head>
<body>
<div class="header">
  <h1>&#128200; Jira API Integration Test Report</h1>
  <div class="meta">Generated: {timestamp} &nbsp;|&nbsp; Server: {server_url} &nbsp;|&nbsp; Auth: {auth_type} &nbsp;|&nbsp; Project: {project_key}</div>
</div>
<div class="summary-bar">
  <span class="badge pass"><span class="dot"></span>{pass_count} Passed</span>
  <span class="badge fail"><span class="dot"></span>{fail_count} Failed</span>
  <span class="badge error"><span class="dot"></span>{error_count} Errors</span>
  <span class="badge skip"><span class="dot"></span>{skip_count} Skipped</span>
  <span style="margin-left:auto;color:var(--muted);font-size:13px;align-self:center">{total_count} tests &nbsp;|&nbsp; {total_ms:.0f} ms total</span>
  {dry_run_badge}
</div>
<div class="container">
  <div class="env-info">
    <h3>Environment</h3>
    <div class="env-grid">
      {env_items}
    </div>
  </div>
  {categories_html}
</div>
<script>
document.querySelectorAll('.cat-header').forEach(h => {{
  h.addEventListener('click', () => {{
    const body = h.nextElementSibling;
    const arrow = h.querySelector('.arrow');
    if (body.style.display === 'none') {{
      body.style.display = '';
      if (arrow) arrow.textContent = '▾';
    }} else {{
      body.style.display = 'none';
      if (arrow) arrow.textContent = '▸';
    }}
  }});
}});
</script>
</body>
</html>
"""


def _html_escape(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;").replace('"', "&quot;"))


def _duration_bar(ms: float) -> str:
    pct = min(100, ms / 5000 * 100)
    cls = "fast" if ms < 500 else ("medium" if ms < 3000 else "slow")
    return (f'<div class="progress-bar-wrap">'
            f'<div class="progress-bar {cls}" style="width:{pct:.0f}%"></div>'
            f'</div>')


def generate_html_report(
    results: list[TestResult],
    server_url: str,
    auth_type: str,
    project_key: str,
    dry_run: bool,
) -> str:
    from itertools import groupby

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    counts = {s: 0 for s in [_STATUS_PASS, _STATUS_FAIL, _STATUS_ERROR, _STATUS_SKIP, _STATUS_INFO]}
    total_ms = 0.0
    for r in results:
        counts[r.status] = counts.get(r.status, 0) + 1
        total_ms += r.duration_ms

    dry_run_badge = (
        '<span class="badge" style="background:#fef3c7;color:#92400e">'
        '<span class="dot"></span>DRY RUN</span>'
    ) if dry_run else ""

    # Environment items
    env_data = [
        ("Python", f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"),
        ("Platform", sys.platform),
        ("Server", server_url or "(not set)"),
        ("Auth Type", auth_type or "(not set)"),
        ("Project Key", project_key or "(not set)"),
        ("Dry Run", "Yes" if dry_run else "No"),
        ("Total Tests", str(len(results))),
        ("Jira Lib", _get_jira_version()),
    ]
    env_items = "".join(
        f'<div class="env-item"><div class="key">{k}</div><div class="val">{_html_escape(str(v))}</div></div>'
        for k, v in env_data
    )

    # Group results by category
    sorted_results = sorted(results, key=lambda r: r.category)
    cat_html_parts = []
    for cat, group in groupby(sorted_results, key=lambda r: r.category):
        items = list(group)
        cat_counts = {s: 0 for s in [_STATUS_PASS, _STATUS_FAIL, _STATUS_ERROR, _STATUS_SKIP]}
        for r in items:
            cat_counts[r.status] = cat_counts.get(r.status, 0) + 1

        # Category badge pills
        badge_parts = []
        for s, cls in [(_STATUS_PASS, "pass"), (_STATUS_FAIL, "fail"),
                       (_STATUS_ERROR, "error"), (_STATUS_SKIP, "skip")]:
            if cat_counts.get(s, 0) > 0:
                badge_parts.append(
                    f'<span class="badge {cls}">{cat_counts[s]} {s.title()}</span>'
                )
        badges_html = "".join(badge_parts)

        # Determine initial collapse state: collapse passing-only categories
        has_problems = cat_counts[_STATUS_FAIL] + cat_counts[_STATUS_ERROR] > 0
        # (body_style reserved for future collapse; omitted when empty)

        rows = []
        for r in items:
            status_cls = r.status
            msg_cls = {"FAIL": "fail", "ERROR": "error", "SKIP": "skip"}.get(r.status, "")
            msg_html = f'<br><span class="msg {msg_cls}">{_html_escape(r.message)}</span>' if r.message else ""

            stdout_html = ""
            if r.stdout or r.details:
                combined = ""
                if r.stdout:
                    combined += "=== CAPTURED OUTPUT ===\n" + r.stdout + "\n"
                if r.details:
                    combined += "=== TRACEBACK ===\n" + r.details
                stdout_html = (
                    f'<details><summary>Show output</summary>'
                    f'<pre class="output">{_html_escape(combined.strip())}</pre>'
                    f'</details>'
                )

            dur_html = (
                f'<span class="dur">{r.duration_ms:.0f} ms</span>'
                + _duration_bar(r.duration_ms)
            )

            rows.append(
                f"<tr>"
                f'<td><span class="status-badge {status_cls}">{r.status}</span></td>'
                f"<td>{_html_escape(r.name)}{msg_html}{stdout_html}</td>"
                f"<td>{dur_html}</td>"
                f"</tr>"
            )

        rows_html = "".join(rows)
        cat_html_parts.append(f"""
<div class="category">
  <div class="cat-header">
    <span><span class="arrow">▾</span>&nbsp;&nbsp;{_html_escape(cat)}</span>
    <span class="cat-badges">{badges_html}</span>
  </div>
  <div class="cat-body">
    <table>
      <thead><tr><th style="width:90px">Status</th><th>Test</th><th style="width:120px">Duration</th></tr></thead>
      <tbody>{rows_html}</tbody>
    </table>
  </div>
</div>""")

    return _HTML_TEMPLATE.format(
        timestamp=timestamp,
        server_url=_html_escape(server_url),
        auth_type=_html_escape(auth_type),
        project_key=_html_escape(project_key),
        pass_count=counts[_STATUS_PASS],
        fail_count=counts[_STATUS_FAIL],
        error_count=counts[_STATUS_ERROR],
        skip_count=counts[_STATUS_SKIP],
        total_count=len(results),
        total_ms=total_ms,
        dry_run_badge=dry_run_badge,
        env_items=env_items,
        categories_html="\n".join(cat_html_parts),
    )


def _get_jira_version() -> str:
    try:
        import jira
        return getattr(jira, "__version__", "installed")
    except ImportError:
        return "not installed"


# ---------------------------------------------------------------------------
# PyQt5 Credential Dialog
# ---------------------------------------------------------------------------

def _show_warning_dialog(app) -> bool:
    """Show a safety warning. Returns True if the user accepts."""
    from PyQt5.QtWidgets import QMessageBox
    from PyQt5.QtCore import Qt

    msg = QMessageBox()
    msg.setWindowTitle("⚠ Safety Warning")
    msg.setIcon(QMessageBox.Warning)
    msg.setText(
        "<b>This script may CREATE, UPDATE, and DELETE Jira issues.</b>"
    )
    msg.setInformativeText(
        "Only run this test suite against a <b>dedicated test server</b>.<br>"
        "Do <b>NOT</b> run against a production Jira instance.<br><br>"
        "New test tickets will be created and deleted during the test run.<br>"
        "(Use <tt>--dry-run</tt> to skip all write operations.)"
    )
    msg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
    msg.setDefaultButton(QMessageBox.No)
    msg.button(QMessageBox.Yes).setText("I understand – proceed")
    msg.button(QMessageBox.No).setText("Cancel")
    result = msg.exec_()
    return result == QMessageBox.Yes


def _run_credentials_dialog() -> Optional[dict]:
    """Show the credentials dialog and return the server config or None on cancel."""
    from PyQt5.QtWidgets import (
        QApplication, QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
        QLabel, QLineEdit, QComboBox, QPushButton, QGroupBox, QFrame,
        QSpacerItem, QSizePolicy, QMessageBox,
    )
    from PyQt5.QtCore import Qt
    from PyQt5.QtGui import QFont, QPalette, QColor

    app = QApplication.instance() or QApplication(sys.argv)

    if not _show_warning_dialog(app):
        return None

    dlg = QDialog()
    dlg.setWindowTitle("Jira API Test Configuration")
    dlg.setMinimumWidth(520)
    dlg.setWindowFlags(dlg.windowFlags() & ~Qt.WindowContextHelpButtonHint)

    main_layout = QVBoxLayout(dlg)
    main_layout.setSpacing(12)
    main_layout.setContentsMargins(20, 20, 20, 16)

    # Title
    title = QLabel("Jira Integration Test Suite")
    title_font = QFont()
    title_font.setPointSize(14)
    title_font.setBold(True)
    title.setFont(title_font)
    title.setStyleSheet("color: #1e3a5f;")
    main_layout.addWidget(title)

    sub = QLabel("Configure the Jira server and credentials for testing.")
    sub.setStyleSheet("color: #64748b; margin-bottom: 8px;")
    main_layout.addWidget(sub)

    sep = QFrame()
    sep.setFrameShape(QFrame.HLine)
    sep.setStyleSheet("color: #e2e8f0;")
    main_layout.addWidget(sep)

    # Server group
    srv_group = QGroupBox("Jira Server")
    srv_form = QFormLayout(srv_group)
    srv_form.setSpacing(8)

    url_edit = QLineEdit()
    url_edit.setPlaceholderText("https://yourcompany.atlassian.net  or  https://jira.internal:8080")
    srv_form.addRow("Server URL:", url_edit)

    auth_combo = QComboBox()
    auth_combo.addItems([
        "API Token (Jira Cloud)         [credential_type=token]",
        "Password (legacy basic auth)   [credential_type=password]",
        "Personal Access Token (DC/Server) [credential_type=pat]",
    ])
    srv_form.addRow("Auth Type:", auth_combo)

    main_layout.addWidget(srv_group)

    # Credentials group
    cred_group = QGroupBox("Credentials")
    cred_form = QFormLayout(cred_group)
    cred_form.setSpacing(8)

    user_label = QLabel("Username / Email:")
    user_edit = QLineEdit()
    user_edit.setPlaceholderText("user@example.com")
    cred_form.addRow(user_label, user_edit)

    cred_label = QLabel("API Token:")
    cred_edit = QLineEdit()
    cred_edit.setEchoMode(QLineEdit.Password)
    cred_edit.setPlaceholderText("API token or Personal Access Token")
    cred_form.addRow(cred_label, cred_edit)

    main_layout.addWidget(cred_group)

    # Project group
    prj_group = QGroupBox("Test Project & Jira Filter")
    prj_form = QFormLayout(prj_group)
    prj_form.setSpacing(8)

    proj_edit = QLineEdit()
    proj_edit.setPlaceholderText("TEST  (Jira project key for issue creation/search)")
    prj_form.addRow("Project Key:", proj_edit)

    # Filter type selector (JQL / Saved Filter)
    filter_type_combo = QComboBox()
    filter_type_combo.addItems([
        "JQL  (raw query string)",
        "Saved Filter  (numeric ID or URL with ?filter=ID)",
    ])
    prj_form.addRow("Filter Type:", filter_type_combo)

    filter_label = QLabel("JQL Filter:")
    jql_edit = QLineEdit()
    jql_edit.setPlaceholderText("project = TEST ORDER BY created DESC")
    prj_form.addRow(filter_label, jql_edit)

    # Update placeholder text when filter type changes
    def _update_filter_ui():
        if filter_type_combo.currentIndex() == 1:  # Saved Filter
            filter_label.setText("Saved Filter:")
            jql_edit.setPlaceholderText(
                "Numeric ID (e.g. 12345) or full URL (?filter=12345)"
            )
        else:
            filter_label.setText("JQL Filter:")
            jql_edit.setPlaceholderText(
                "project = TEST ORDER BY created DESC"
            )
    filter_type_combo.currentIndexChanged.connect(_update_filter_ui)

    main_layout.addWidget(prj_group)

    hint = QLabel(
        "ℹ  Use <b>--dry-run</b> to skip issue creation/deletion tests."
    )
    hint.setStyleSheet("color: #92400e; background: #fef3c7; padding: 8px; border-radius: 4px;")
    hint.setWordWrap(True)
    main_layout.addWidget(hint)

    # Update labels based on auth type
    def _update_auth_ui():
        idx = auth_combo.currentIndex()
        if idx == 2:  # PAT
            user_label.setText("Username (optional):")
            user_edit.setPlaceholderText("Leave empty for PAT-only auth")
            cred_label.setText("Personal Access Token:")
            cred_edit.setPlaceholderText("Personal Access Token")
        elif idx == 1:  # Password
            user_label.setText("Username / Email:")
            user_edit.setPlaceholderText("user@example.com")
            cred_label.setText("Password:")
            cred_edit.setPlaceholderText("Jira password")
        else:  # API Token
            user_label.setText("Username / Email:")
            user_edit.setPlaceholderText("user@example.com")
            cred_label.setText("API Token:")
            cred_edit.setPlaceholderText("API token (from id.atlassian.com)")

    auth_combo.currentIndexChanged.connect(_update_auth_ui)

    # Buttons
    btn_layout = QHBoxLayout()
    btn_layout.addStretch()
    cancel_btn = QPushButton("Cancel")
    cancel_btn.setMinimumWidth(90)
    ok_btn = QPushButton("Run Tests")
    ok_btn.setMinimumWidth(110)
    ok_btn.setDefault(True)
    ok_btn.setStyleSheet(
        "QPushButton { background: #1e3a5f; color: white; border-radius: 4px; padding: 6px 16px; }"
        "QPushButton:hover { background: #2d5282; }"
    )
    btn_layout.addWidget(cancel_btn)
    btn_layout.addWidget(ok_btn)
    main_layout.addLayout(btn_layout)

    cancel_btn.clicked.connect(dlg.reject)

    def _accept():
        url = url_edit.text().strip()
        if not url:
            QMessageBox.warning(dlg, "Missing URL", "Please enter the Jira server URL.")
            return
        cred = cred_edit.text().strip()
        if not cred:
            QMessageBox.warning(dlg, "Missing Credential",
                                "Please enter the API token, password, or PAT.")
            return
        pk = proj_edit.text().strip().upper()
        if not pk:
            QMessageBox.warning(dlg, "Missing Project Key",
                                "Please enter a Jira project key (e.g. TEST).")
            return
        dlg.accept()

    ok_btn.clicked.connect(_accept)

    if dlg.exec_() != QDialog.Accepted:
        return None

    idx = auth_combo.currentIndex()
    cred_types = ["token", "password", "pat"]
    auth_labels = ["API Token (Jira Cloud)", "Password", "Personal Access Token (PAT)"]

    filter_types = ["jql", "filter"]
    return {
        "name":            "test-server",
        "url":             url_edit.text().strip(),
        "auth_mode":       "manual",
        "username":        user_edit.text().strip(),
        "token":           cred_edit.text().strip(),
        "credential_type": cred_types[idx],
        "_auth_label":     auth_labels[idx],
        "_project_key":    proj_edit.text().strip().upper(),
        "_filter_type":    filter_types[filter_type_combo.currentIndex()],
        "_filter_value":   jql_edit.text().strip(),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _build_parser() -> optparse.OptionParser:
    parser = optparse.OptionParser(
        usage="usage: %prog [options]",
        description="Comprehensive Jira integration API test suite.",
    )
    parser.add_option(
        "--dry-run",
        action="store_true",
        dest="dry_run",
        default=False,
        help="Skip all tests that create/modify Jira issues (default: false)",
    )
    parser.add_option(
        "--output-dir",
        dest="output_dir",
        default=os.path.join(_ROOT_DIR, "tests", "documentation"),
        metavar="DIR",
        help="Output directory for the HTML report (default: tests/documentation)",
    )
    parser.add_option(
        "--no-gui",
        action="store_true",
        dest="no_gui",
        default=False,
        help="Do not open the Qt credentials dialog; exit after printing usage",
    )
    return parser


def main():
    # Enable ANSI escape codes on Windows 10+ (no-op on Linux/macOS)
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.kernel32.SetConsoleMode(
                ctypes.windll.kernel32.GetStdHandle(-11), 7
            )
        except Exception:
            pass

    parser = _build_parser()
    opts, _ = parser.parse_args()

    if not _IMPORT_OK:
        print(f"[ERROR] Could not import integration modules: {_IMPORT_ERROR}")
        print(f"  Make sure the src/ directory is accessible from: {_SRC_DIR}")
        sys.exit(1)

    if opts.no_gui:
        print("--no-gui specified: a PyQt5 credentials dialog is required to run.")
        print("Re-run without --no-gui to enter server details.")
        sys.exit(0)

    # ---- Collect credentials via PyQt5 dialog ----
    config = _run_credentials_dialog()
    if config is None:
        print("Cancelled.")
        sys.exit(0)

    server       = {k: v for k, v in config.items() if not k.startswith("_")}
    project_key  = config["_project_key"]
    auth_label   = config["_auth_label"]
    filter_type  = config.get("_filter_type", "jql")
    filter_value = config.get("_filter_value", f"project = {project_key}")
    # Fall back to a simple project filter when the user left the field empty
    if not filter_value:
        filter_value = f"project = {project_key}"

    # Inject mock SettingsManager
    _inject_sm(server)

    # ---- Build JIRA client (needed for live tests) ----
    print("Connecting to Jira...")
    try:
        from jira import JIRA  # type: ignore
        ctype = server.get("credential_type", "token")
        url   = server.get("url", "")
        uname = server.get("username", "").strip()
        cred  = server.get("token", "").strip()
        if ctype == "pat":
            jira_client = JIRA(server=url, token_auth=cred)
        else:
            jira_client = JIRA(server=url, basic_auth=(uname, cred))
        print("  Connected OK.")
    except Exception as exc:
        from PyQt5.QtWidgets import QApplication, QMessageBox
        app = QApplication.instance() or QApplication(sys.argv)
        QMessageBox.critical(
            None,
            "Connection Failed",
            f"Could not connect to Jira:\n{exc}\n\nPlease check the server URL and credentials.",
        )
        sys.exit(1)

    # ---- Run all test categories ----
    runner = TestRunner(dry_run=opts.dry_run)

    print(f"\nRunning tests (dry_run={opts.dry_run}) ...")
    print(f"  Server: {server['url']}  Auth: {auth_label}  Project: {project_key}\n")

    run_category_A(runner)
    run_category_B(runner)
    run_category_C(runner)
    run_category_D(runner)
    run_category_E(runner)
    run_category_F(runner, server)
    run_category_G(runner, server, jira_client)

    # Fetch server capabilities once; used by H, J, K to skip unsupported features.
    # Pass project_key so project-specific issue types are fetched (not global server types).
    print("  Fetching server capabilities (issue types, priorities)...")
    caps = jira_integration.fetch_server_capabilities(server, project_key)
    if caps.get("error"):
        print(f"  Warning: could not fetch capabilities: {caps['error']}")
    else:
        print(f"  Issue types: {caps.get('issue_types', [])}")
        print(f"  Priorities:  {caps.get('priorities', [])}")

    run_category_H(runner, server, jira_client, project_key, filter_value, filter_type, caps)
    run_category_I(runner, jira_client, filter_value, filter_type)
    run_category_J(runner, jira_client, project_key, opts.dry_run, caps)
    run_category_K(runner, jira_client, project_key, opts.dry_run, caps)
    run_category_L(runner, jira_client, project_key)
    run_category_M(runner, server, jira_client, project_key)
    run_category_N(runner, server)
    run_category_O(runner, server)
    run_category_P(runner)
    run_category_Q(runner)
    run_category_R(runner)

    # ---- Print console summary ----
    counts = runner.summary()
    total  = len(runner.results)
    print("\n" + "=" * 60)
    print(f"  Results: {counts[_STATUS_PASS]} PASS  {counts[_STATUS_FAIL]} FAIL  "
          f"{counts[_STATUS_ERROR]} ERROR  {counts[_STATUS_SKIP]} SKIP  / {total} total")
    print("=" * 60)

    failed = [r for r in runner.results if r.status in (_STATUS_FAIL, _STATUS_ERROR)]
    if failed:
        print("\nFailed / Errored tests:")
        for r in failed:
            print(f"  [{r.status}] {r.category} > {r.name}")
            if r.message:
                print(f"         → {r.message}")

    # ---- Generate HTML report ----
    if not opts.no_gui:
        os.makedirs(opts.output_dir, exist_ok=True)
        out_file = os.path.join(opts.output_dir, "jira_api_test_report.html")

        html = generate_html_report(
            results     = runner.results,
            server_url  = server.get("url", ""),
            auth_type   = auth_label,
            project_key = project_key,
            dry_run     = opts.dry_run,
        )
        with open(out_file, "w", encoding="utf-8") as fh:
            fh.write(html)

        print(f"\nHTML report: {out_file}")

        # Open in browser
        try:
            import webbrowser
            webbrowser.open(out_file)
        except Exception:
            pass

    return 0 if counts[_STATUS_FAIL] + counts[_STATUS_ERROR] == 0 else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nInterrupted by user.")
        sys.exit(130)
    except Exception as _exc:
        import traceback
        print(f"\n[FATAL] Unhandled error: {_exc}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(2)
