# Version Control Integration

Integration with Git and SVN version control systems, enabling auto-commit on save,
branch management, commit history, and restore from revision — all from within the app.

## Architecture

```
src/integrations/version_control_integration.py   ← module (public API)
src/settings_dialogs.py                           ← VcsConfigDialog, VcsLogDialog,
                                                     VcsBranchDialog, VcsConflictDialog
src/ribbon.py                                     ← VERSION CONTROL ribbon tab
src/ui.py                                         ← MainWindow handler methods
src/app_debug.py                                  ← vcs_integration block in debug dump
tools/git/                                        ← bundled Git for Windows
tools/svn/                                        ← bundled TortoiseSVN CLI binaries
```

> **Note:** `tools/git-askpass-env.bat` is no longer a shipped static file.
> The helper script is generated at runtime into a `tempfile.mkstemp()` path
> by `_askpass_script()` and cached for the process lifetime.
> See [Credential Handling — Git (GIT_ASKPASS)](#git-git_askpass) for details.

## Repository Detection

On project open, the module walks from the project-file directory up the directory tree,
looking for:

* `.git/` directory → Git repository
* `.svn/` directory → SVN working copy

The **effective repository root** (first ancestor containing `.git`/`.svn`) is stored
in the project state. Nested repositories are handled by stopping at the first match.

If neither marker is found, all VCS ribbon buttons are disabled and the VERSION CONTROL
tab is hidden.

```python
from integrations import version_control_integration as vcs

repo = vcs.detect_repo(project_file_path)
# repo = {"type": "git", "root": "C:\\...\\project", "branch": "main"}
# repo = {"type": "svn", "root": "C:\\...\\project", "revision": 42}
# repo = {}   ← no repo detected
```

## Credential Handling

Credentials are retrieved **exclusively from KeePass** — no passwords are stored in
QSettings or logged in any output.

### Git (GIT_ASKPASS)

A **runtime-generated** helper script is used as `GIT_ASKPASS`. The
`_askpass_script()` function writes a small `.bat` file to `tempfile.mkstemp()`
on first call and caches the path in `_askpass_tmp_path`. If the file is
deleted (e.g. by OS temp-cleanup), it is regenerated transparently.  This
approach works correctly in both development and PyInstaller bundles — no
static file needs to be shipped.

The script content (`_ASKPASS_CONTENT`) echoes the appropriate environment
variable when Git asks for "Username" or "Password".

Before spawning any git subprocess the module sets three environment variables:

| Variable | Value |
| -------- | ----- |
| `GIT_ASKPASS` | absolute path to the generated temp `.bat` |
| `GIT_ASKPASS_USERNAME` | username from KeePass entry |
| `GIT_ASKPASS_PASSWORD` | password from KeePass entry |

The batch script reads these variables and prints the appropriate value when Git
asks for "Username" or "Password", so credentials never appear in the process list.
After the subprocess completes the variables are deleted from the environment.

### SVN

Credentials are passed via `--username` and `--password` flags only when non-empty
KeePass credentials are available. When no KeePass credentials are configured or
available, `--username`, `--password`, and `--no-auth-cache` are **omitted**,
allowing the SVN client to use the local OS credential cache (e.g. Windows
Credential Manager). This enables read operations such as `svn log` to succeed
without requiring KeePass to be configured.

`--non-interactive` is **always** included so SVN never prompts for credentials
interactively. Credential values are never printed to the debug log.

## Fallback when KeePass is Locked

If KeePass is locked or missing at the time of a credential-requiring operation:

1. A dialog prompts the user to unlock KeePass.
2. If the user cancels unlock, they may enter credentials manually for this
   single operation (not persisted).
3. If the user skips, the operation is aborted — plaintext credentials are
   never persisted.

## Auto-Commit on Save

When a project file is saved and a repository is detected, an automatic commit is
triggered (if enabled in settings):

* A **debounce** of 3 seconds prevents commit storms during rapid save sequences.
* The commit is skipped if there are no staged/tracked changes.
* A configurable message template is used:
  `Auto-commit: {project_name} saved at {timestamp}`
* The user may disable auto-commit globally or per-session.
* Scope option: commit the project file only, or all tracked changes.

## Pre-flight Checks

Before any commit or update operation:

**Git:**

* Detect `MERGE_HEAD`, `CHERRY_PICK_HEAD`, `REBASE_MERGE`, `REBASE_APPLY` markers
  in `.git/` → block auto-commit with a clear message.

**SVN:**

* Run `svn info` to check working-copy state; detect locked files via `svn status`
* Offer `svn cleanup` before retry on lock errors.

## Non-Blocking Execution

All `git`/`svn` subprocess calls are run in a `QThread`-based worker
(`VcsWorker`) to avoid blocking the UI. A timeout cancels the subprocess after
a configurable duration (default: 30 s). The main thread receives results via
Qt signals.

## Conflict Handling

After `git pull` / `svn update` / `svn switch`:

1. The module checks for conflict markers in the working copy.
2. A `VcsConflictDialog` lists conflicting files with "Resolve…", "Revert…", and
   "Retry…" actions.
3. Command output is shown in a read-only text widget (sanitized — no credential values).

## Restore UX

* A **safety snapshot** of the current project file is created before any restore.
* The log view shows a diff of each revision vs. the selected revision (git diff / svn diff).
* Two restore modes: file-only (just the project XML) or full working copy.

## Ribbon Tab: VERSION CONTROL

The tab is **only shown** when a project with a repository is open.
Buttons are defined in a `VCS_RIBBON_TABS` array (same pattern as `JIRA_SYNC_RIBBON_TABS`).

| Button | Git | SVN |
| ------ | --- | --- |
| VCS Config | ✓ | ✓ |
| Commit | ✓ | ✓ |
| View Log | ✓ | ✓ |
| Branch Mgmt | ✓ | — |
| Update | — | ✓ |

## Public API (version_control_integration.py)

```python
# Repo detection
detect_repo(project_file_path: str) -> dict

# State
is_configured() -> bool
get_vcs_type() -> str          # "git" | "svn" | ""
get_repo_root() -> str         # "" if not detected

# Operations (all return (success: bool, output: str))
commit(message: str, scope: str = "project") -> tuple[bool, str]
get_log(max_entries: int = 50) -> tuple[bool, list[dict]]
branch_list() -> tuple[bool, list[str]]
branch_create(name: str) -> tuple[bool, str]
branch_switch(name: str) -> tuple[bool, str]
pull(rebase: bool = False) -> tuple[bool, str]
svn_update(revision: str = "HEAD") -> tuple[bool, str]
svn_cleanup() -> tuple[bool, str]
svn_revert(paths: list[str]) -> tuple[bool, str]
restore_revision(revision: str, file_only: bool = True) -> tuple[bool, str]
diff_revision(revision: str) -> tuple[bool, str]

# Debug
get_config_summary() -> dict
```

## Settings (QSettings)

| Key | Type | Description |
| --- | ---- | ----------- |
| `vcs/keepass_entry` | str | KeePass entry for VCS credentials |
| `vcs/auto_commit_enabled` | bool | Whether auto-commit is active (default: True) |
| `vcs/auto_commit_template` | str | Commit message template |
| `vcs/auto_commit_scope` | str | "project" or "all" |
| `vcs/git_path` | str | Path to git.exe (default: auto-detect in tools/git) |
| `vcs/svn_path` | str | Path to svn.exe (default: auto-detect in tools/svn) |

## Troubleshooting Matrix

| Symptom | Cause | Remedy |
| ------- | ----- | ------ |
| "No repository detected" | Project file not in a Git/SVN working copy | Init a repo (`git init` / `svn checkout`) in the project folder |
| Auth failure (401/403) | Wrong credentials or locked KeePass | Unlock KeePass, verify entry username/password |
| Network failure (timeout) | No network access to remote | Check VPN/firewall; retry; work offline |
| Conflict after pull/update | Remote changes conflict with local edits | Use the Conflict dialog to resolve/revert per file |
| SVN lock (E155004) | Interrupted previous operation | Run `svn cleanup` via the pre-flight prompt |
| Git merge/rebase in progress | Incomplete merge or rebase | Complete or abort the operation manually, then retry |
| Timeout (30 s exceeded) | Slow network or large repo | Increase timeout in VCS Config; check network |
| Credentials in logs | Old debug print or subprocess argument | Ensure `--password` flag is never logged; use sanitise_output() |
