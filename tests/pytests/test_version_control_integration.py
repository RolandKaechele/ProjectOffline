"""Tests for integrations/version_control_integration.py.

No real git/svn executables are required; subprocess calls that reach the OS
are patched via unittest.mock.  The module-level _repo_info state is cleared
in teardown so tests do not interfere with each other.
"""

import os
import sys
import tempfile

import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))


# ---------------------------------------------------------------------------
# TestVcsAskpassScript
# ---------------------------------------------------------------------------

class TestVcsAskpassScript:
    """The git-askpass helper .bat is generated dynamically at runtime."""

    def setup_method(self, method):
        import integrations.version_control_integration as vci
        # Reset cached path before each test so they are independent
        vci._askpass_tmp_path = None

    def teardown_method(self, method):
        import integrations.version_control_integration as vci
        vci._askpass_tmp_path = None

    def test_creates_temp_file(self):
        """_askpass_script() returns a path to an existing .bat file."""
        from integrations.version_control_integration import _askpass_script
        path = _askpass_script()
        assert os.path.isfile(path)
        assert path.endswith(".bat")

    def test_file_content_has_echo_off(self):
        """The generated .bat file contains @echo off."""
        from integrations.version_control_integration import _askpass_script
        path = _askpass_script()
        with open(path, "rb") as fh:
            content = fh.read().decode("ascii")
        assert "@echo off" in content

    def test_file_content_echoes_username_env(self):
        """The .bat detects 'username' prompts and echoes GIT_ASKPASS_USERNAME."""
        from integrations.version_control_integration import _askpass_script
        path = _askpass_script()
        with open(path, "rb") as fh:
            content = fh.read().decode("ascii")
        assert "GIT_ASKPASS_USERNAME" in content
        assert "username" in content.lower()

    def test_file_content_echoes_password_env(self):
        """The .bat echoes GIT_ASKPASS_PASSWORD as the fallback (password prompt)."""
        from integrations.version_control_integration import _askpass_script
        path = _askpass_script()
        with open(path, "rb") as fh:
            content = fh.read().decode("ascii")
        assert "GIT_ASKPASS_PASSWORD" in content

    def test_cached_on_second_call(self):
        """Calling _askpass_script() twice returns the exact same path."""
        from integrations.version_control_integration import _askpass_script
        path1 = _askpass_script()
        path2 = _askpass_script()
        assert path1 == path2

    def test_regenerates_if_deleted(self):
        """If the cached temp file is deleted, a new one is created on next call."""
        from integrations.version_control_integration import _askpass_script
        import integrations.version_control_integration as vci

        path1 = _askpass_script()
        os.unlink(path1)           # simulate temp file disappearing
        vci._askpass_tmp_path = path1  # keep stale path in cache
        path2 = _askpass_script()  # must detect missing file and regenerate
        assert os.path.isfile(path2)


# ---------------------------------------------------------------------------
# TestVcsDetectRepo
# ---------------------------------------------------------------------------

class TestVcsDetectRepo:
    """Repository detection — walks the directory tree looking for .git/.svn."""

    def test_no_repo_returns_empty_dict(self):
        """detect_repo returns {} for a plain directory with no VCS markers."""
        from integrations.version_control_integration import detect_repo
        with tempfile.TemporaryDirectory() as tmpdir:
            fake_file = os.path.join(tmpdir, "project.xml")
            result = detect_repo(fake_file)
        assert result == {}

    def test_detects_git_repo(self):
        """detect_repo returns type='git' when a .git directory is present."""
        from integrations.version_control_integration import detect_repo
        with tempfile.TemporaryDirectory() as tmpdir:
            os.makedirs(os.path.join(tmpdir, ".git"))
            fake_file = os.path.join(tmpdir, "project.xml")
            with patch("integrations.version_control_integration._run_git",
                       return_value=(0, "main\n", "")):
                result = detect_repo(fake_file)
        assert result.get("type") == "git"
        assert result.get("root") == tmpdir
        assert result.get("branch") == "main"

    def test_detects_svn_repo(self):
        """detect_repo returns type='svn' when a .svn directory is present."""
        from integrations.version_control_integration import detect_repo
        with tempfile.TemporaryDirectory() as tmpdir:
            os.makedirs(os.path.join(tmpdir, ".svn"))
            fake_file = os.path.join(tmpdir, "project.xml")
            with patch("integrations.version_control_integration._run_svn",
                       return_value=(0, "42\n", "")):
                result = detect_repo(fake_file)
        assert result.get("type") == "svn"
        assert result.get("root") == tmpdir
        assert result.get("revision") == 42

    def test_walks_up_to_parent(self):
        """detect_repo finds .git in a parent directory when called from a subdirectory."""
        from integrations.version_control_integration import detect_repo
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, ".git"))
            subdir = os.path.join(root, "subproject")
            os.makedirs(subdir)
            fake_file = os.path.join(subdir, "project.xml")
            with patch("integrations.version_control_integration._run_git",
                       return_value=(0, "feature\n", "")):
                result = detect_repo(fake_file)
        assert result.get("type") == "git"
        assert result.get("root") == root

    def test_empty_path_returns_empty_dict(self):
        """detect_repo returns {} for an empty string path."""
        from integrations.version_control_integration import detect_repo
        assert detect_repo("") == {}


# ---------------------------------------------------------------------------
# TestVcsModuleState
# ---------------------------------------------------------------------------

class TestVcsModuleState:
    """init(), reset(), and public state accessors."""

    def teardown_method(self, method):
        import integrations.version_control_integration as vci
        vci._repo_info = {}
        vci._project_file_path = ""

    def test_is_configured_false_initially(self):
        """is_configured() returns False when no repo has been initialised."""
        import integrations.version_control_integration as vci
        vci._repo_info = {}
        from integrations.version_control_integration import is_configured
        assert is_configured() is False

    def test_get_vcs_type_empty_initially(self):
        """get_vcs_type() returns '' when no repo is detected."""
        import integrations.version_control_integration as vci
        vci._repo_info = {}
        from integrations.version_control_integration import get_vcs_type
        assert get_vcs_type() == ""

    def test_get_repo_root_empty_initially(self):
        """get_repo_root() returns '' when no repo is detected."""
        import integrations.version_control_integration as vci
        vci._repo_info = {}
        from integrations.version_control_integration import get_repo_root
        assert get_repo_root() == ""

    def test_get_current_branch_empty_initially(self):
        """get_current_branch() returns '' when no repo is detected."""
        import integrations.version_control_integration as vci
        vci._repo_info = {}
        from integrations.version_control_integration import get_current_branch
        assert get_current_branch() == ""

    def test_reset_clears_repo_info(self):
        """reset() clears _repo_info so is_configured() returns False."""
        import integrations.version_control_integration as vci
        vci._repo_info = {"type": "git", "root": "/some/path", "branch": "main"}
        vci._project_file_path = "/some/path/project.xml"
        from integrations.version_control_integration import reset, is_configured
        reset()
        assert is_configured() is False
        assert vci._project_file_path == ""


# ---------------------------------------------------------------------------
# TestVcsConfigSummary
# ---------------------------------------------------------------------------

class TestVcsConfigSummary:
    """get_config_summary() produces a non-sensitive snapshot for app_debug.py."""

    def teardown_method(self, method):
        import integrations.version_control_integration as vci
        vci._repo_info = {}

    def test_has_expected_keys(self):
        """get_config_summary() contains all required non-sensitive keys."""
        from integrations.version_control_integration import get_config_summary
        summary = get_config_summary()
        for key in ("configured", "vcs_type", "repo_root_set",
                    "current_branch", "auto_commit_enabled"):
            assert key in summary, f"Missing key: {key}"

    def test_no_password_in_summary(self):
        """get_config_summary() must not expose any credential value."""
        import integrations.version_control_integration as vci
        vci._repo_info = {"type": "git", "root": "/repo", "branch": "main"}
        from integrations.version_control_integration import get_config_summary
        summary_str = str(get_config_summary()).lower()
        assert "password" not in summary_str
        assert "secret" not in summary_str

    def test_configured_reflects_repo_state(self):
        """get_config_summary()['configured'] matches is_configured()."""
        import integrations.version_control_integration as vci
        vci._repo_info = {"type": "git", "root": "/repo", "branch": "main"}
        from integrations.version_control_integration import get_config_summary, is_configured
        assert get_config_summary()["configured"] == is_configured()


# ---------------------------------------------------------------------------
# TestVcsSanitiseOutput
# ---------------------------------------------------------------------------

class TestVcsSanitiseOutput:
    """_sanitise_output() removes credential values from subprocess output."""

    def test_passthrough_when_no_credentials(self):
        """_sanitise_output() returns text unchanged when credentials are empty."""
        from integrations.version_control_integration import _sanitise_output
        with patch("integrations.version_control_integration._get_credentials",
                   return_value=("", "")):
            result = _sanitise_output("some command output")
        assert result == "some command output"

    def test_replaces_password_in_output(self):
        """_sanitise_output() replaces a live password with <password>."""
        from integrations.version_control_integration import _sanitise_output
        with patch("integrations.version_control_integration._get_credentials",
                   return_value=("alice", "s3cr3t")):
            result = _sanitise_output("error: authentication with s3cr3t failed")
        assert "s3cr3t" not in result
        assert "<password>" in result

    def test_replaces_username_in_output(self):
        """_sanitise_output() replaces a live username with <username>."""
        from integrations.version_control_integration import _sanitise_output
        with patch("integrations.version_control_integration._get_credentials",
                   return_value=("alice", "s3cr3t")):
            result = _sanitise_output("user alice not authorised")
        assert "alice" not in result
        assert "<username>" in result


# ---------------------------------------------------------------------------
# TestRunSvnNoAuthCache  (bug fix: --no-auth-cache must not block cached creds)
# ---------------------------------------------------------------------------

class TestRunSvnNoAuthCache:
    """_run_svn must only add --no-auth-cache when it is also providing explicit
    credentials, so that the local SVN credential cache is usable for operations
    that don't need KeePass (e.g. svn log on a working copy with saved passwords).
    """

    def _capture_cmd(self, args, with_credentials, credentials=("", "")):
        """Run _run_svn with a patched subprocess.run and return the command list."""
        import integrations.version_control_integration as vci

        captured = {}

        def fake_run(cmd, **kw):
            captured['cmd'] = list(cmd)
            result = MagicMock()
            result.returncode = 0
            result.stdout = ""
            result.stderr = ""
            return result

        with patch("integrations.version_control_integration._svn_exe",
                   return_value="svn"), \
             patch("integrations.version_control_integration._get_credentials",
                   return_value=credentials), \
             patch("integrations.version_control_integration.subprocess.run",
                   side_effect=fake_run):
            vci._run_svn(args, cwd="/tmp", with_credentials=with_credentials)

        return captured.get('cmd', [])

    def test_no_auth_cache_absent_when_no_credentials(self):
        """Without explicit credentials --no-auth-cache must NOT be in the command."""
        cmd = self._capture_cmd(["log", "-l10", "--xml"],
                                with_credentials=True,
                                credentials=("", ""))
        assert "--no-auth-cache" not in cmd

    def test_no_auth_cache_absent_when_with_credentials_false(self):
        """When with_credentials=False --no-auth-cache must not appear regardless."""
        cmd = self._capture_cmd(["log", "-l10", "--xml"],
                                with_credentials=False,
                                credentials=("user", "pass"))
        assert "--no-auth-cache" not in cmd

    def test_no_auth_cache_present_when_explicit_password_provided(self):
        """With a real password supplied --no-auth-cache must be in the command
        to avoid storing the (KeePass-sourced) credential in the SVN cache."""
        cmd = self._capture_cmd(["commit", "-m", "msg"],
                                with_credentials=True,
                                credentials=("alice", "s3cr3t"))
        assert "--no-auth-cache" in cmd

    def test_non_interactive_always_present(self):
        """--non-interactive must always be added regardless of credential mode."""
        cmd_no_creds = self._capture_cmd(["info"], with_credentials=False,
                                         credentials=("", ""))
        cmd_creds = self._capture_cmd(["info"], with_credentials=True,
                                      credentials=("u", "p"))
        assert "--non-interactive" in cmd_no_creds
        assert "--non-interactive" in cmd_creds

    def test_svn_log_command_does_not_get_no_auth_cache_by_default(self):
        """svn_log() calls _run_svn with with_credentials=True but no KeePass
        credentials loaded; --no-auth-cache must therefore be absent so the
        local SVN credential cache is consulted."""
        import integrations.version_control_integration as vci
        vci._repo_info = {"type": "svn", "root": "/repo"}

        captured = {}

        def fake_run(cmd, **kw):
            captured['cmd'] = list(cmd)
            r = MagicMock()
            r.returncode = 0
            r.stdout = "<log></log>"
            r.stderr = ""
            return r

        with patch("integrations.version_control_integration._svn_exe",
                   return_value="svn"), \
             patch("integrations.version_control_integration._get_credentials",
                   return_value=("", "")), \
             patch("integrations.version_control_integration.subprocess.run",
                   side_effect=fake_run):
            ok, entries = vci.svn_log(max_entries=10)

        assert ok is True
        assert "--no-auth-cache" not in captured.get('cmd', [])

        # Reset module state
        vci._repo_info = {}


# ---------------------------------------------------------------------------
# TestSvnIsUnversioned
# ---------------------------------------------------------------------------

class TestSvnIsUnversioned:
    """svn_is_unversioned() returns True when svn status shows '?' for the file.

    \testinit
    Patch _run_svn to return pre-defined status output and _repo_info so that
    get_repo_root() returns a non-empty path.

    \testrun
    Call svn_is_unversioned(file_path) with mocked subprocess output.

    \testexpect
    Returns True when the status line starts with '?'; False when the output is
    empty (clean file) or when no repo is configured.

    \testcheck
    Assert the boolean return value.
    """

    def teardown_method(self, method):
        import integrations.version_control_integration as vci
        vci._repo_info = {}

    def test_returns_true_when_status_has_question_mark(self):
        """Returns True when svn status output starts with '?'."""
        import integrations.version_control_integration as vci
        vci._repo_info = {"type": "svn", "root": "/repo"}
        from integrations.version_control_integration import svn_is_unversioned
        with patch("integrations.version_control_integration._run_svn",
                   return_value=(0, "? /repo/project.xml\n", "")):
            result = svn_is_unversioned("/repo/project.xml")
        assert result is True

    def test_returns_false_when_status_is_clean(self):
        """Returns False when svn status returns empty output (file is tracked)."""
        import integrations.version_control_integration as vci
        vci._repo_info = {"type": "svn", "root": "/repo"}
        from integrations.version_control_integration import svn_is_unversioned
        with patch("integrations.version_control_integration._run_svn",
                   return_value=(0, "", "")):
            result = svn_is_unversioned("/repo/project.xml")
        assert result is False

    def test_returns_false_when_no_repo(self):
        """Returns False when no SVN repo is configured (get_repo_root() empty)."""
        import integrations.version_control_integration as vci
        vci._repo_info = {}
        from integrations.version_control_integration import svn_is_unversioned
        result = svn_is_unversioned("/repo/project.xml")
        assert result is False


# ---------------------------------------------------------------------------
# TestSvnAdd
# ---------------------------------------------------------------------------

class TestSvnAdd:
    """svn_add() schedules a file for addition via 'svn add -- <file_path>'.

    \testinit
    Set _repo_info to a valid SVN root; patch subprocess.run to simulate
    success (rc=0) or failure (rc=1).

    \testrun
    Call svn_add(file_path) with mocked _run_svn.

    \testexpect
    Success: returns (True, output). Failure: returns (False, error).
    The 'svn add' command is called with '--' and the file path.
    _last_status_result is updated with operation='svn_add'.

    \testcheck
    Assert return value, captured command arguments, and _last_status_result.
    """

    def teardown_method(self, method):
        import integrations.version_control_integration as vci
        vci._repo_info = {}
        vci._last_status_result = None

    def test_svn_add_calls_add_command(self):
        """svn_add() calls _run_svn with ['add', '--', file_path]."""
        import integrations.version_control_integration as vci
        vci._repo_info = {"type": "svn", "root": "/repo"}
        captured = {}

        def fake_run_svn(args, **kw):
            captured["args"] = list(args)
            return (0, "A  /repo/project.xml\n", "")

        from integrations.version_control_integration import svn_add
        with patch("integrations.version_control_integration._run_svn",
                   side_effect=fake_run_svn):
            svn_add("/repo/project.xml")

        assert captured["args"] == ["add", "--", "/repo/project.xml"]

    def test_svn_add_returns_true_on_success(self):
        """svn_add() returns (True, ...) when the svn process exits with rc=0."""
        import integrations.version_control_integration as vci
        vci._repo_info = {"type": "svn", "root": "/repo"}
        from integrations.version_control_integration import svn_add
        with patch("integrations.version_control_integration._run_svn",
                   return_value=(0, "A  /repo/project.xml\n", "")):
            ok, _ = svn_add("/repo/project.xml")
        assert ok is True

    def test_svn_add_returns_false_on_failure(self):
        """svn_add() returns (False, ...) when the svn process exits with rc=1."""
        import integrations.version_control_integration as vci
        vci._repo_info = {"type": "svn", "root": "/repo"}
        from integrations.version_control_integration import svn_add
        with patch("integrations.version_control_integration._run_svn",
                   return_value=(1, "", "svn: E200009: not a working copy")):
            ok, _ = svn_add("/repo/project.xml")
        assert ok is False

    def test_svn_add_updates_last_status_result(self):
        """svn_add() stores operation='svn_add' in _last_status_result."""
        import integrations.version_control_integration as vci
        vci._repo_info = {"type": "svn", "root": "/repo"}
        from integrations.version_control_integration import svn_add
        with patch("integrations.version_control_integration._run_svn",
                   return_value=(0, "A  /repo/project.xml\n", "")):
            svn_add("/repo/project.xml")
        assert vci._last_status_result is not None
        assert vci._last_status_result.get("operation") == "svn_add"


# ---------------------------------------------------------------------------
# TestVcsWorkerSvnAdd
# ---------------------------------------------------------------------------

class TestVcsWorkerSvnAdd:
    """VcsWorker routes operation='svn_add' to svn_add().

    \testinit
    Set _repo_info to a valid SVN root; patch svn_add to capture its call.

    \testrun
    Instantiate VcsWorker('svn_add', file_path='/repo/project.xml') and call
    run() directly (no thread).

    \testexpect
    svn_add() is called with file_path='/repo/project.xml'.
    The 'finished' signal carries (True, ...).

    \testcheck
    Assert svn_add mock was called once with the correct argument.
    """

    def teardown_method(self, method):
        import integrations.version_control_integration as vci
        vci._repo_info = {}

    def test_vcs_worker_svn_add_calls_svn_add(self):
        """VcsWorker('svn_add') delegates to svn_add() with correct file_path."""
        import integrations.version_control_integration as vci
        vci._repo_info = {"type": "svn", "root": "/repo"}

        with patch("integrations.version_control_integration.svn_add",
                   return_value=(True, "A  project.xml")) as mock_add:
            worker = vci.VcsWorker("svn_add", file_path="/repo/project.xml")
            # Call run() synchronously (no QThread.start() needed for unit test)
            worker.run()

        mock_add.assert_called_once_with(file_path="/repo/project.xml")


# ---------------------------------------------------------------------------
# TestVcsDebugLog  (new: _debug_log_append + command_log in get_config_summary)
# ---------------------------------------------------------------------------

class TestVcsDebugLog:
    """_debug_log_append() maintains a rolling in-memory log; get_config_summary()
    exposes it as 'command_log'.

    \testinit
    Clear _debug_log before each test so tests are isolated.

    \testrun
    Call _debug_log_append() with known messages, then inspect _debug_log and
    get_config_summary()['command_log'].

    \testexpect
    Each appended message appears as a timestamped entry.  The rolling buffer
    never exceeds _DEBUG_LOG_MAX entries.  get_config_summary() returns a copy
    of the current buffer under the key 'command_log'.

    \testcheck
    Assert buffer length, entry content, and get_config_summary() return value.
    """

    def setup_method(self, method):
        import integrations.version_control_integration as vci
        vci._debug_log = []

    def teardown_method(self, method):
        import integrations.version_control_integration as vci
        vci._debug_log = []
        vci._repo_info = {}

    def test_append_adds_entry(self):
        """_debug_log_append() adds one entry per call."""
        import integrations.version_control_integration as vci
        from integrations.version_control_integration import _debug_log_append
        _debug_log_append("hello world")
        assert len(vci._debug_log) == 1

    def test_entry_contains_message(self):
        """The appended entry contains the original message text."""
        import integrations.version_control_integration as vci
        from integrations.version_control_integration import _debug_log_append
        _debug_log_append("git: status (cwd=/repo)")
        assert "git: status (cwd=/repo)" in vci._debug_log[0]

    def test_entry_contains_version_control_prefix(self):
        """The entry is tagged with '[version_control]' for log triage."""
        import integrations.version_control_integration as vci
        from integrations.version_control_integration import _debug_log_append
        _debug_log_append("test msg")
        assert "[version_control]" in vci._debug_log[0]

    def test_multiple_appends_grow_buffer(self):
        """Appending three messages produces a buffer of length 3."""
        from integrations.version_control_integration import _debug_log_append
        import integrations.version_control_integration as vci
        _debug_log_append("a")
        _debug_log_append("b")
        _debug_log_append("c")
        assert len(vci._debug_log) == 3

    def test_buffer_capped_at_max(self):
        """Buffer never exceeds _DEBUG_LOG_MAX entries."""
        import integrations.version_control_integration as vci
        from integrations.version_control_integration import _debug_log_append
        for i in range(vci._DEBUG_LOG_MAX + 20):
            _debug_log_append(f"msg {i}")
        assert len(vci._debug_log) <= vci._DEBUG_LOG_MAX

    def test_oldest_entries_dropped_when_over_max(self):
        """After exceeding the cap the oldest entries are removed."""
        import integrations.version_control_integration as vci
        from integrations.version_control_integration import _debug_log_append
        for i in range(vci._DEBUG_LOG_MAX + 5):
            _debug_log_append(f"msg {i}")
        # The very first messages should have been dropped
        assert not any("msg 0 " in e or e.endswith("msg 0") for e in vci._debug_log)

    def test_get_config_summary_includes_command_log_key(self):
        """get_config_summary() always includes the 'command_log' key."""
        from integrations.version_control_integration import get_config_summary
        summary = get_config_summary()
        assert "command_log" in summary

    def test_get_config_summary_command_log_reflects_debug_log(self):
        """get_config_summary()['command_log'] matches the current _debug_log."""
        import integrations.version_control_integration as vci
        from integrations.version_control_integration import _debug_log_append, get_config_summary
        _debug_log_append("sentinel-entry-xyz")
        summary = get_config_summary()
        assert any("sentinel-entry-xyz" in e for e in summary["command_log"])

    def test_get_config_summary_command_log_is_copy(self):
        """Mutating the returned list does not affect _debug_log."""
        import integrations.version_control_integration as vci
        from integrations.version_control_integration import _debug_log_append, get_config_summary
        _debug_log_append("original")
        log_copy = get_config_summary()["command_log"]
        log_copy.clear()
        assert len(vci._debug_log) >= 1
