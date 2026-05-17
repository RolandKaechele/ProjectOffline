# version_control_integration.py — Git and SVN version control integration.
#
# Provides repository detection, commit, log, branch management, update, and
# restore operations for both Git and SVN working copies. All subprocess calls
# run in a background QThread to keep the UI responsive.
#
# Authentication
# --------------
# Credentials are retrieved from KeePass — no passwords stored in QSettings.
# Git  : GIT_ASKPASS mechanism via tools/git-askpass-env.bat + env vars
#        (GIT_ASKPASS_USERNAME, GIT_ASKPASS_PASSWORD).
# SVN  : --username and --password flags + --no-auth-cache.
# Both : credentials are deleted from the environment after each subprocess call.
#
# Configuration (QSettings)
# -------------------------
#   vcs/keepass_entry        — KeePass entry title for VCS credentials
#   vcs/auto_commit_enabled  — bool (default True)
#   vcs/auto_commit_template — str (default "Auto-commit: {project_name} saved at {timestamp}")
#   vcs/auto_commit_scope    — "project" | "all" (default "project")
#   vcs/git_path             — path to git.exe (auto-detected from tools/git if empty)
#   vcs/svn_path             — path to svn.exe (auto-detected from tools/svn if empty)
#
# Public API
# ----------
#   init(project_file_path)                          -> None (call on project open)
#   reset()                                          -> None (call on project close)
#   detect_repo(project_file_path)                   -> dict
#   is_configured()                                  -> bool
#   get_vcs_type()                                   -> str   ("git" | "svn" | "")
#   get_repo_root()                                  -> str
#   get_current_branch()                             -> str
#   commit(message, scope="project", file_path=None) -> tuple[bool, str]
#   get_log(max_entries=50)                          -> tuple[bool, list[dict]]
#   branch_list()                                    -> tuple[bool, list[str]]
#   branch_create(name)                              -> tuple[bool, str]
#   branch_switch(name)                              -> tuple[bool, str]
#   pull(rebase=False)                               -> tuple[bool, str]
#   svn_update(revision="HEAD")                      -> tuple[bool, str]
#   svn_cleanup()                                    -> tuple[bool, str]
#   svn_revert(paths)                                -> tuple[bool, str]
#   restore_revision(revision, file_only=True,
#                    project_file_path=None)         -> tuple[bool, str]
#   diff_revision(revision)                          -> tuple[bool, str]
#   get_config_summary()                             -> dict   (for app_debug.py dump)
#
# See documentation/version_control_integration.md for full details.

from __future__ import annotations

import os
import sys
import subprocess
import shutil
import datetime
import threading
from typing import Optional

from PyQt5.QtCore import QThread, pyqtSignal, QObject  # type: ignore
try:
    from progress_worker import WorkerThread as _WorkerThreadBase  # type: ignore
except ImportError:
    _WorkerThreadBase = QThread  # type: ignore[misc,assignment]
from app_debug import is_debug as _is_debug  # type: ignore

# ---------------------------------------------------------------------------
# Module-level state
# ---------------------------------------------------------------------------
_repo_info: dict = {}          # {"type": "git"|"svn", "root": str, "branch": str}
_project_file_path: str = ""   # current open project file path
_last_commit_result: Optional[dict] = None
_last_status_result: Optional[dict] = None
_debug_log: list = []          # rolling buffer of debug messages for app_debug.py
_DEBUG_LOG_MAX = 100

# Debounce for auto-commit
_auto_commit_timer: Optional[threading.Timer] = None
_DEBOUNCE_SECONDS = 3


def _debug_log_append(msg: str) -> None:
    """Append a timestamped debug message to the rolling log buffer."""
    import datetime as _dt
    global _debug_log
    entry = f"{_dt.datetime.now().strftime('%H:%M:%S.%f')[:-3]} [version_control] {msg}"
    _debug_log.append(entry)
    if len(_debug_log) > _DEBUG_LOG_MAX:
        _debug_log = _debug_log[-_DEBUG_LOG_MAX:]


# ---------------------------------------------------------------------------
# Tool path resolution
# ---------------------------------------------------------------------------

def _tools_dir() -> str:
    """Return the absolute path to the tools/ directory."""
    if getattr(sys, "frozen", False):
        return os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "tools")
    # Development: tools/ is one level above src/
    return os.path.normpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "tools")
    )


def _git_exe() -> str:
    """Return the path to git.exe, preferring the bundled version."""
    sm = _get_settings_manager()
    if sm is not None:
        configured = sm.get_vcs_git_path()
        if configured and os.path.isfile(configured):
            return configured
    # Bundled git in tools/git/cmd/git.exe or tools/git/bin/git.exe
    for candidate in (
        os.path.join(_tools_dir(), "git", "cmd", "git.exe"),
        os.path.join(_tools_dir(), "git", "bin", "git.exe"),
        os.path.join(_tools_dir(), "git", "git.exe"),
    ):
        if os.path.isfile(candidate):
            return candidate
    # Fall back to PATH
    found = shutil.which("git")
    return found or "git"


def _svn_exe() -> str:
    """Return the path to svn.exe, preferring the bundled version."""
    sm = _get_settings_manager()
    if sm is not None:
        configured = sm.get_vcs_svn_path()
        if configured and os.path.isfile(configured):
            return configured
    # Bundled svn in tools/svn/svn.exe
    candidate = os.path.join(_tools_dir(), "svn", "svn.exe")
    if os.path.isfile(candidate):
        return candidate
    found = shutil.which("svn")
    return found or "svn"


_ASKPASS_CONTENT = (
    "@echo off\r\n"
    "echo %1 | findstr /i \"username\" >nul && echo %GIT_ASKPASS_USERNAME% && exit /b\r\n"
    "echo %GIT_ASKPASS_PASSWORD%\r\n"
)

_askpass_tmp_path: str | None = None


def _askpass_script() -> str:
    """Return path to a git-askpass-env.bat helper, generating it into a temp
    file at runtime so no static file needs to be shipped or bundled."""
    global _askpass_tmp_path
    if _askpass_tmp_path and os.path.isfile(_askpass_tmp_path):
        return _askpass_tmp_path
    import tempfile
    fd, path = tempfile.mkstemp(prefix="git-askpass-", suffix=".bat")
    try:
        os.write(fd, _ASKPASS_CONTENT.encode("ascii"))
    finally:
        os.close(fd)
    _askpass_tmp_path = path
    return path


# ---------------------------------------------------------------------------
# Settings helpers
# ---------------------------------------------------------------------------

def _get_settings_manager():
    try:
        from settings_manager import SettingsManager  # type: ignore
        return SettingsManager()
    except Exception:
        return None


def _get_keepass_entry() -> str:
    sm = _get_settings_manager()
    return sm.get_vcs_keepass_entry() if sm else ""


def _get_auto_commit_enabled() -> bool:
    sm = _get_settings_manager()
    return sm.get_vcs_auto_commit_enabled() if sm else True


def _get_auto_commit_template() -> str:
    sm = _get_settings_manager()
    tpl = sm.get_vcs_auto_commit_template() if sm else ""
    return tpl or "Auto-commit: {project_name} saved at {timestamp}"


def _get_auto_commit_scope() -> str:
    sm = _get_settings_manager()
    return sm.get_vcs_auto_commit_scope() if sm else "project"


# ---------------------------------------------------------------------------
# Credential retrieval
# ---------------------------------------------------------------------------

def _get_credentials() -> tuple[str, str]:
    """Retrieve (username, password) from KeePass. Returns ("", "") on failure."""
    try:
        from integrations import keepass_integration  # type: ignore
        if not keepass_integration.is_unlocked():
            return "", ""
        entry_title = _get_keepass_entry()
        if not entry_title:
            return "", ""
        username, password = keepass_integration.get_credentials(entry_title)
        return (username or ""), (password or "")
    except Exception:
        return "", ""


# ---------------------------------------------------------------------------
# Subprocess execution
# ---------------------------------------------------------------------------

def _sanitise_output(text: str) -> str:
    """Remove any credential values from command output before logging."""
    try:
        username, password = _get_credentials()
        if username:
            text = text.replace(username, "<username>")
        if password:
            text = text.replace(password, "<password>")
    except Exception:
        pass
    return text


def _run_git(args: list[str], cwd: str, timeout: int = 30,
             with_credentials: bool = False) -> tuple[int, str, str]:
    """Run a git command. Returns (returncode, stdout, stderr)."""
    git = _git_exe()
    cmd = [git] + args
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"  # never prompt interactively

    if with_credentials:
        username, password = _get_credentials()
        if username or password:
            askpass = _askpass_script()
            if os.path.isfile(askpass):
                env["GIT_ASKPASS"] = askpass
                env["GIT_ASKPASS_USERNAME"] = username
                env["GIT_ASKPASS_PASSWORD"] = password
            else:
                if _is_debug():
                    _debug_log_append(f"git-askpass script not found: {askpass}")

    if _is_debug():
        # Log the command, but mask any credential flags
        safe_cmd = " ".join(str(a) for a in cmd if a not in (
            env.get("GIT_ASKPASS_PASSWORD", "__NEVER__"),
            env.get("GIT_ASKPASS_USERNAME", "__NEVER__"),
        ))
        _debug_log_append(f"git: {safe_cmd}  (cwd={cwd})")

    try:
        result = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True,
            timeout=timeout, env=env,
        )
        stdout = _sanitise_output(result.stdout or "")
        stderr = _sanitise_output(result.stderr or "")
        return result.returncode, stdout, stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Command timed out."
    except FileNotFoundError:
        return -2, "", f"git executable not found: {git}"
    finally:
        # Always clear credential vars from our copy — they are already local
        env.pop("GIT_ASKPASS_USERNAME", None)
        env.pop("GIT_ASKPASS_PASSWORD", None)


def _run_svn(args: list[str], cwd: str, timeout: int = 30,
             with_credentials: bool = False) -> tuple[int, str, str]:
    """Run an svn command. Returns (returncode, stdout, stderr)."""
    svn = _svn_exe()
    cmd = [svn] + args + ["--non-interactive"]

    if with_credentials:
        username, password = _get_credentials()
        if username:
            cmd += ["--username", username]
        if password:
            # Only suppress credential caching when we provide explicit credentials
            cmd += ["--password", password, "--no-auth-cache"]

    if _is_debug():
        # Log command, masking --password value
        safe_parts = []
        skip_next = False
        for part in cmd:
            if skip_next:
                safe_parts.append("<password>")
                skip_next = False
            elif part == "--password":
                safe_parts.append(part)
                skip_next = True
            else:
                safe_parts.append(part)
        _debug_log_append(f"svn: {' '.join(safe_parts)}  (cwd={cwd})")

    try:
        result = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True,
            timeout=timeout, encoding="utf-8", errors="replace",
        )
        stdout = _sanitise_output(result.stdout or "")
        stderr = _sanitise_output(result.stderr or "")
        return result.returncode, stdout, stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Command timed out."
    except FileNotFoundError:
        return -2, "", f"svn executable not found: {svn}"


# ---------------------------------------------------------------------------
# Repository detection
# ---------------------------------------------------------------------------

def detect_repo(project_file_path: str) -> dict:
    """Walk up from *project_file_path* to find the nearest Git or SVN repo root.

    Returns a dict:
      {"type": "git", "root": str, "branch": str}
      {"type": "svn", "root": str, "revision": int}
      {}  ← no repo detected
    """
    if not project_file_path:
        return {}
    directory = os.path.dirname(os.path.abspath(project_file_path))
    current = directory
    while True:
        git_dir = os.path.join(current, ".git")
        svn_dir = os.path.join(current, ".svn")
        if os.path.isdir(git_dir) or os.path.isfile(git_dir):  # .git can be a file (worktrees)
            branch = _git_current_branch(current)
            return {"type": "git", "root": current, "branch": branch}
        if os.path.isdir(svn_dir):
            revision = _svn_current_revision(current)
            return {"type": "svn", "root": current, "revision": revision}
        parent = os.path.dirname(current)
        if parent == current:
            break  # reached filesystem root
        current = parent
    return {}


def _git_current_branch(repo_root: str) -> str:
    rc, out, _ = _run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_root, timeout=5)
    if rc == 0:
        return out.strip()
    return ""


def _svn_current_revision(repo_root: str) -> int:
    rc, out, _ = _run_svn(["info", "--show-item", "last-changed-revision"], cwd=repo_root, timeout=5)
    if rc == 0:
        try:
            return int(out.strip())
        except ValueError:
            pass
    return -1


# ---------------------------------------------------------------------------
# Module init / reset (called from ui.py)
# ---------------------------------------------------------------------------

def init(project_file_path: str) -> None:
    """Detect the repository for the newly opened project and store state."""
    global _repo_info, _project_file_path
    _project_file_path = project_file_path or ""
    _repo_info = detect_repo(_project_file_path) if _project_file_path else {}
    if _is_debug():
        _debug_log_append(f"init: repo_info={_repo_info}")


def reset() -> None:
    """Clear repository state on project close."""
    global _repo_info, _project_file_path, _auto_commit_timer
    _repo_info = {}
    _project_file_path = ""
    if _auto_commit_timer is not None:
        _auto_commit_timer.cancel()
        _auto_commit_timer = None


# ---------------------------------------------------------------------------
# Public state accessors
# ---------------------------------------------------------------------------

def is_configured() -> bool:
    """Return True if a repository has been detected for the open project."""
    return bool(_repo_info.get("type"))


def get_vcs_type() -> str:
    """Return "git", "svn", or "" depending on the detected repository."""
    return _repo_info.get("type", "")


def get_repo_root() -> str:
    """Return the effective repository root path, or "" if not detected."""
    return _repo_info.get("root", "")


def get_current_branch() -> str:
    """Return the current Git branch or "" for SVN/no repo."""
    return _repo_info.get("branch", "")


# ---------------------------------------------------------------------------
# Pre-flight checks
# ---------------------------------------------------------------------------

def check_git_in_progress() -> tuple[bool, str]:
    """Return (ok, message). ok=False means a merge/rebase is in progress."""
    root = get_repo_root()
    if not root:
        return True, ""
    git_dir = os.path.join(root, ".git")
    if os.path.isfile(git_dir):  # worktree: .git is a file
        git_dir_path = open(git_dir).read().strip()
        if git_dir_path.startswith("gitdir:"):
            git_dir = os.path.normpath(os.path.join(root, git_dir_path[7:].strip()))
    for marker in ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REBASE_MERGE", "REBASE_APPLY"):
        path = os.path.join(git_dir, marker)
        if os.path.exists(path):
            return False, (
                f"A {marker.replace('_', ' / ').lower()} operation is in progress.\n"
                "Please complete or abort it before committing."
            )
    return True, ""


def check_svn_clean() -> tuple[bool, str]:
    """Return (ok, message). ok=False means the working copy is locked or out-of-date."""
    root = get_repo_root()
    if not root:
        return True, ""
    rc, out, err = _run_svn(["status", "--xml"], cwd=root, timeout=10)
    if rc != 0:
        return False, err or "SVN status check failed."
    if "obstructed" in out or "locked" in out:
        return False, (
            "The SVN working copy has locked or obstructed entries.\n"
            "Run 'svn cleanup' to resolve this before committing."
        )
    return True, ""


# ---------------------------------------------------------------------------
# Git operations
# ---------------------------------------------------------------------------

def _git_has_changes(scope: str, file_path: str) -> bool:
    """Return True if there are uncommitted changes to commit."""
    root = get_repo_root()
    if not root:
        return False
    if scope == "project" and file_path:
        rc, out, _ = _run_git(["status", "--porcelain", "--", file_path], cwd=root, timeout=5)
    else:
        rc, out, _ = _run_git(["status", "--porcelain"], cwd=root, timeout=5)
    return rc == 0 and bool(out.strip())


def _git_commit(message: str, scope: str = "project", file_path: str = "") -> tuple[bool, str]:
    global _last_commit_result
    root = get_repo_root()
    if not root:
        return False, "No Git repository detected."

    ok, pre_msg = check_git_in_progress()
    if not ok:
        return False, pre_msg

    if not _git_has_changes(scope, file_path):
        _last_commit_result = {"timestamp": _now(), "success": True, "skipped": True,
                                "message": "No changes to commit."}
        return True, "No changes to commit."

    # Stage files
    if scope == "project" and file_path:
        rc, out, err = _run_git(["add", "--", file_path], cwd=root, timeout=10)
    else:
        rc, out, err = _run_git(["add", "-A"], cwd=root, timeout=10)
    if rc != 0:
        _last_commit_result = {"timestamp": _now(), "success": False, "error": err}
        return False, f"git add failed:\n{err}"

    rc, out, err = _run_git(["commit", "-m", message], cwd=root, timeout=30)
    success = rc == 0
    combined = out + err
    _last_commit_result = {
        "timestamp": _now(), "success": success,
        "message": message[:120], "output": combined[:500],
    }
    if success:
        # Refresh branch info
        _repo_info["branch"] = _git_current_branch(root)
    return success, combined if not success else out.strip()


def git_pull(rebase: bool = False) -> tuple[bool, str]:
    global _last_status_result
    root = get_repo_root()
    if not root:
        return False, "No Git repository detected."
    args = ["pull"]
    if rebase:
        args.append("--rebase")
    rc, out, err = _run_git(args, cwd=root, timeout=60, with_credentials=True)
    success = rc == 0
    combined = out + err
    _last_status_result = {"timestamp": _now(), "operation": "pull", "success": success}
    return success, combined.strip()


def git_fetch() -> tuple[bool, str]:
    """Fetch all remotes without merging or rebasing."""
    global _last_status_result
    root = get_repo_root()
    if not root:
        return False, "No Git repository detected."
    rc, out, err = _run_git(["fetch", "--all"], cwd=root, timeout=60, with_credentials=True)
    success = rc == 0
    combined = out + err
    _last_status_result = {"timestamp": _now(), "operation": "fetch", "success": success}
    return success, combined.strip()


def git_log(max_entries: int = 50) -> tuple[bool, list[dict]]:
    root = get_repo_root()
    if not root:
        return False, []
    fmt = "%H\x1f%h\x1f%an\x1f%ae\x1f%ai\x1f%s"
    rc, out, err = _run_git(
        ["log", f"-{max_entries}", f"--pretty=format:{fmt}"],
        cwd=root, timeout=15,
    )
    if rc != 0:
        return False, []
    entries = []
    for line in out.splitlines():
        parts = line.split("\x1f")
        if len(parts) >= 6:
            entries.append({
                "hash":    parts[0],
                "short":   parts[1],
                "author":  parts[2],
                "email":   parts[3],
                "date":    parts[4],
                "subject": parts[5],
            })
    return True, entries


def git_branch_list() -> tuple[bool, list[str]]:
    root = get_repo_root()
    if not root:
        return False, []
    rc, out, _ = _run_git(["branch", "--list", "--format=%(refname:short)"], cwd=root, timeout=5)
    if rc != 0:
        return False, []
    branches = [b.strip() for b in out.splitlines() if b.strip()]
    return True, branches


def git_branch_create(name: str) -> tuple[bool, str]:
    root = get_repo_root()
    if not root:
        return False, "No Git repository detected."
    rc, out, err = _run_git(["branch", name], cwd=root, timeout=10)
    return rc == 0, (out + err).strip()


def git_branch_switch(name: str) -> tuple[bool, str]:
    root = get_repo_root()
    if not root:
        return False, "No Git repository detected."
    rc, out, err = _run_git(["checkout", name], cwd=root, timeout=15)
    success = rc == 0
    if success:
        _repo_info["branch"] = name
    return success, (out + err).strip()


def git_diff_revision(revision: str) -> tuple[bool, str]:
    root = get_repo_root()
    if not root:
        return False, "No Git repository."
    file_path = _project_file_path
    args = ["diff", revision, "--", file_path] if file_path else ["diff", revision]
    rc, out, err = _run_git(args, cwd=root, timeout=15)
    return rc == 0, (out or err).strip()


def git_restore_revision(revision: str, file_only: bool = True,
                         project_file: str = "") -> tuple[bool, str]:
    root = get_repo_root()
    if not root:
        return False, "No Git repository."
    # Create safety snapshot first
    _create_safety_snapshot(project_file or _project_file_path)
    if file_only and (project_file or _project_file_path):
        fp = project_file or _project_file_path
        rc, out, err = _run_git(["checkout", revision, "--", fp], cwd=root, timeout=15)
    else:
        rc, out, err = _run_git(["checkout", revision], cwd=root, timeout=20)
    return rc == 0, (out + err).strip()


# ---------------------------------------------------------------------------
# SVN operations
# ---------------------------------------------------------------------------

def svn_is_unversioned(file_path: str) -> bool:
    """Return True if *file_path* has SVN status '?' (unversioned).

    Only meaningful when get_vcs_type() == 'svn'.
    """
    root = get_repo_root()
    if not root or not file_path:
        return False
    rc, out, _err = _run_svn(["status", "--", file_path], cwd=root, timeout=10)
    for line in out.splitlines():
        if line.startswith("?"):
            return True
    return False


def svn_add(file_path: str) -> tuple[bool, str]:
    """Schedule *file_path* for addition in SVN (``svn add <file>``).

    Returns ``(success, output_message)``.  Call ``svn_commit`` afterwards to
    permanently add the file to the repository.
    """
    global _last_status_result
    root = get_repo_root()
    if not root:
        return False, "No SVN working copy detected."
    rc, out, err = _run_svn(["add", "--", file_path], cwd=root, timeout=15)
    success = rc == 0
    combined = (out + err).strip()
    _last_status_result = {
        "timestamp": _now(),
        "operation": "svn_add",
        "success": success,
        "file": file_path,
    }
    return success, combined


def svn_update(revision: str = "HEAD") -> tuple[bool, str]:
    global _last_status_result
    root = get_repo_root()
    if not root:
        return False, "No SVN working copy detected."
    ok, msg = check_svn_clean()
    if not ok:
        return False, msg
    args = ["update"]
    if revision != "HEAD":
        args += ["-r", revision]
    rc, out, err = _run_svn(args, cwd=root, timeout=60, with_credentials=True)
    success = rc == 0
    combined = out + err
    _last_status_result = {"timestamp": _now(), "operation": "svn_update", "success": success}
    # Refresh revision info
    if success:
        _repo_info["revision"] = _svn_current_revision(root)
    return success, combined.strip()


def svn_commit(message: str, scope: str = "project", file_path: str = "") -> tuple[bool, str]:
    global _last_commit_result
    root = get_repo_root()
    if not root:
        return False, "No SVN working copy detected."
    ok, msg = check_svn_clean()
    if not ok:
        return False, msg
    if scope == "project" and file_path:
        args = ["commit", "-m", message, file_path]
    else:
        args = ["commit", "-m", message]
    rc, out, err = _run_svn(args, cwd=root, timeout=60, with_credentials=True)
    success = rc == 0
    combined = out + err
    _last_commit_result = {
        "timestamp": _now(), "success": success,
        "message": message[:120], "output": combined[:500],
    }
    if success:
        _repo_info["revision"] = _svn_current_revision(root)
    return success, combined.strip()


def svn_log(max_entries: int = 50) -> tuple[bool, list[dict]]:
    root = get_repo_root()
    if not root:
        return False, []
    rc, out, err = _run_svn(
        ["log", f"-l{max_entries}", "--xml"],
        cwd=root, timeout=15, with_credentials=True,
    )
    if rc != 0:
        return False, []
    entries = _parse_svn_log_xml(out)
    return True, entries


def _parse_svn_log_xml(xml_text: str) -> list[dict]:
    """Parse svn log --xml output into a list of dicts."""
    import xml.etree.ElementTree as ET
    entries = []
    try:
        root_el = ET.fromstring(xml_text)
        for entry in root_el.findall("logentry"):
            rev = entry.get("revision", "")
            author = (entry.findtext("author") or "").strip()
            date = (entry.findtext("date") or "").strip()[:19]
            msg = (entry.findtext("msg") or "").strip()
            entries.append({
                "hash": rev, "short": f"r{rev}",
                "author": author, "email": "",
                "date": date, "subject": msg,
            })
    except Exception:
        pass
    return entries


def svn_cleanup() -> tuple[bool, str]:
    root = get_repo_root()
    if not root:
        return False, "No SVN working copy detected."
    rc, out, err = _run_svn(["cleanup"], cwd=root, timeout=30)
    return rc == 0, (out + err).strip()


def svn_revert(paths: list[str]) -> tuple[bool, str]:
    root = get_repo_root()
    if not root:
        return False, "No SVN working copy detected."
    args = ["revert", "--"] + paths
    rc, out, err = _run_svn(args, cwd=root, timeout=15)
    return rc == 0, (out + err).strip()


def svn_diff_revision(revision: str) -> tuple[bool, str]:
    root = get_repo_root()
    if not root:
        return False, "No SVN working copy."
    file_path = _project_file_path
    if file_path:
        args = ["diff", "-r", f"{revision}:BASE", "--", file_path]
    else:
        args = ["diff", "-r", f"{revision}:BASE"]
    rc, out, err = _run_svn(args, cwd=root, timeout=15, with_credentials=True)
    return rc == 0, (out or err).strip()


def svn_restore_revision(revision: str, file_only: bool = True,
                         project_file: str = "") -> tuple[bool, str]:
    root = get_repo_root()
    if not root:
        return False, "No SVN working copy."
    _create_safety_snapshot(project_file or _project_file_path)
    fp = project_file or _project_file_path
    if file_only and fp:
        rc, out, err = _run_svn(
            ["update", "-r", revision, "--", fp],
            cwd=root, timeout=30, with_credentials=True,
        )
    else:
        rc, out, err = _run_svn(
            ["update", "-r", revision],
            cwd=root, timeout=60, with_credentials=True,
        )
    return rc == 0, (out + err).strip()


# ---------------------------------------------------------------------------
# Unified public API
# ---------------------------------------------------------------------------

def commit(message: str, scope: str = "project",
           file_path: str = "") -> tuple[bool, str]:
    """Commit using the detected VCS."""
    vcs = get_vcs_type()
    if vcs == "git":
        return _git_commit(message, scope, file_path or _project_file_path)
    if vcs == "svn":
        return svn_commit(message, scope, file_path or _project_file_path)
    return False, "No version control repository detected."


def get_log(max_entries: int = 50) -> tuple[bool, list[dict]]:
    vcs = get_vcs_type()
    if vcs == "git":
        return git_log(max_entries)
    if vcs == "svn":
        return svn_log(max_entries)
    return False, []


def branch_list() -> tuple[bool, list[str]]:
    if get_vcs_type() == "git":
        return git_branch_list()
    return False, []


def branch_create(name: str) -> tuple[bool, str]:
    if get_vcs_type() == "git":
        return git_branch_create(name)
    return False, "Branch management is only supported for Git."


def branch_switch(name: str) -> tuple[bool, str]:
    if get_vcs_type() == "git":
        return git_branch_switch(name)
    return False, "Branch management is only supported for Git."


def pull(rebase: bool = False) -> tuple[bool, str]:
    if get_vcs_type() == "git":
        return git_pull(rebase)
    return False, "Pull is only supported for Git. Use 'Update' for SVN."


def diff_revision(revision: str) -> tuple[bool, str]:
    vcs = get_vcs_type()
    if vcs == "git":
        return git_diff_revision(revision)
    if vcs == "svn":
        return svn_diff_revision(revision)
    return False, "No repository detected."


def restore_revision(revision: str, file_only: bool = True,
                     project_file_path: str = "") -> tuple[bool, str]:
    vcs = get_vcs_type()
    if vcs == "git":
        return git_restore_revision(revision, file_only, project_file_path)
    if vcs == "svn":
        return svn_restore_revision(revision, file_only, project_file_path)
    return False, "No repository detected."


# ---------------------------------------------------------------------------
# Auto-commit (called from ui.py save_project)
# ---------------------------------------------------------------------------

def schedule_auto_commit(project_file_path: str, project_name: str) -> None:
    """Schedule an auto-commit after DEBOUNCE_SECONDS of inactivity.

    Cancels any pending auto-commit first (debounce).
    Does nothing if auto-commit is disabled or no repo is detected.
    """
    global _auto_commit_timer

    if not is_configured():
        return
    if not _get_auto_commit_enabled():
        return

    # Cancel previous pending commit
    if _auto_commit_timer is not None:
        _auto_commit_timer.cancel()
        _auto_commit_timer = None

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    template = _get_auto_commit_template()
    try:
        message = template.format(
            project_name=project_name or os.path.basename(project_file_path),
            timestamp=timestamp,
        )
    except Exception:
        message = f"Auto-commit: saved at {timestamp}"

    scope = _get_auto_commit_scope()

    def _do_commit():
        global _auto_commit_timer
        _auto_commit_timer = None
        if _is_debug():
            _debug_log_append(f"auto-commit triggered: {message!r}")
        ok, output = commit(message, scope=scope, file_path=project_file_path)
        if _is_debug():
            _debug_log_append(f"auto-commit result: ok={ok}, output={output[:200]!r}")

    _auto_commit_timer = threading.Timer(_DEBOUNCE_SECONDS, _do_commit)
    _auto_commit_timer.daemon = True
    _auto_commit_timer.start()


# ---------------------------------------------------------------------------
# Safety snapshot
# ---------------------------------------------------------------------------

def _create_safety_snapshot(file_path: str) -> None:
    """Copy *file_path* to <name>.vcs-snapshot.<timestamp>.xml before restore."""
    if not file_path or not os.path.isfile(file_path):
        return
    base, ext = os.path.splitext(file_path)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    snapshot_path = f"{base}.vcs-snapshot.{stamp}{ext}"
    try:
        shutil.copy2(file_path, snapshot_path)
        if _is_debug():
            _debug_log_append(f"safety snapshot: {snapshot_path}")
    except Exception as exc:
        if _is_debug():
            _debug_log_append(f"safety snapshot failed: {exc}")


# ---------------------------------------------------------------------------
# Conflict detection
# ---------------------------------------------------------------------------

def get_conflicts() -> list[str]:
    """Return a list of conflicting file paths in the working copy."""
    root = get_repo_root()
    vcs = get_vcs_type()
    if not root or not vcs:
        return []
    if vcs == "git":
        rc, out, _ = _run_git(["diff", "--name-only", "--diff-filter=U"], cwd=root, timeout=10)
        if rc == 0:
            return [p.strip() for p in out.splitlines() if p.strip()]
    elif vcs == "svn":
        rc, out, _ = _run_svn(["status", "--xml"], cwd=root, timeout=10)
        if rc == 0 and "conflict" in out.lower():
            import xml.etree.ElementTree as ET
            try:
                root_el = ET.fromstring(out)
                conflicts = []
                for entry in root_el.findall(".//entry"):
                    wc = entry.find("wc-status")
                    if wc is not None and wc.get("item") in ("conflicted",):
                        path = entry.get("path", "")
                        if path:
                            conflicts.append(path)
                return conflicts
            except Exception:
                pass
    return []


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------------------
# Debug dump
# ---------------------------------------------------------------------------

def get_config_summary() -> dict:
    """Return a non-sensitive config snapshot for app_debug.py."""
    return {
        "configured": is_configured(),
        "vcs_type": get_vcs_type(),
        "repo_root_set": bool(get_repo_root()),
        "current_branch": get_current_branch(),
        "keepass_entry_set": bool(_get_keepass_entry()),
        "auto_commit_enabled": _get_auto_commit_enabled(),
        "auto_commit_scope": _get_auto_commit_scope(),
        "last_commit": {
            k: v for k, v in (_last_commit_result or {}).items()
            if k not in ("message",)  # message may contain project name
        } if _last_commit_result else None,
        "last_status": _last_status_result,
        "command_log": list(_debug_log),
    }


# ---------------------------------------------------------------------------
# Background worker (QThread wrapper for non-blocking calls)
# ---------------------------------------------------------------------------

class VcsWorker(_WorkerThreadBase):
    """Run a VCS operation in a background thread.

    Signals (inherited from WorkerThread / QThread):
        progress(int, str)  — (percent or -1 for indeterminate, status text)
        finished(bool, str) — emitted when the operation completes
    """
    # Declare signals unconditionally so they are always available regardless
    # of whether the WorkerThread base was successfully imported.
    finished = pyqtSignal(bool, str)
    progress = pyqtSignal(int, str)

    def __init__(self, operation: str, **kwargs):
        super().__init__()
        self._operation = operation
        self._kwargs = kwargs
        self._result: tuple[bool, str] = (False, "Not started")
        self.cancelled: bool = False

    def run(self):
        op = self._operation
        self.progress.emit(-1, f"{op.replace('_', ' ').title()}\u2026")
        try:
            if op == "commit":
                ok, msg = commit(**self._kwargs)
            elif op == "pull":
                ok, msg = pull(**self._kwargs)
            elif op == "fetch":
                ok, msg = git_fetch()
            elif op == "svn_update":
                ok, msg = svn_update(**self._kwargs)
            elif op == "svn_cleanup":
                ok, msg = svn_cleanup()
            elif op == "svn_add":
                ok, msg = svn_add(**self._kwargs)
            elif op == "diff":
                ok, msg = diff_revision(**self._kwargs)
            elif op == "restore":
                ok, msg = restore_revision(**self._kwargs)
            else:
                ok, msg = False, f"Unknown operation: {op}"
        except Exception as exc:
            ok, msg = False, str(exc)
        self._result = (ok, msg)
        self.finished.emit(ok, msg)
