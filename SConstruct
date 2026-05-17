# SConstruct — Build script for Project Offline
#
# Produces a self-contained one-directory bundle in dist/ProjectOffline/
# with the OpenJDK 17 runtime in dist/ProjectOffline/jdk/ and the bundled
# Playwright Chromium browser in dist/ProjectOffline/ms-playwright/chromium-XXXX/.
#
# Prerequisites
# -------------
#   1. Run once to fetch third-party assets (if not already present):
#        python tools/download_openjdk.py
#        python tools/download_mpxj.py
#   2. Install PyInstaller into the project venv:
#        pip install pyinstaller
#
# Usage
# -----
#   scons                  # build everything into dist/
#   scons -c               # clean dist/ and build/ artefacts

import datetime
import glob
import os
import shutil
import sys

# -- Version (set once at SCons startup time) ----------------------------------
_now         = datetime.datetime.now()
BUILD_VERSION = _now.strftime("v%Y.%m.%d-%H.%M")

# -- Configuration --------------------------------------------------------------
APP_NAME    = "ProjectOffline"
ENTRY_POINT = os.path.join("src", "main.py")

# Output directory (all artefacts land here)
BIN_DIR     = "dist"
APP_DIR     = os.path.join(BIN_DIR, APP_NAME)      # dist/ProjectOffline/
JDK_DEST    = os.path.join(APP_DIR, "jdk")         # dist/ProjectOffline/jdk/

# Intermediate build artefacts (not shipped)
WORK_DIR    = os.path.join("build", "pyinstaller-work")
SPEC_DIR    = os.path.join("build")

# OpenJDK source: the first jdk-* sub-directory inside tools/java/
JDK_SRC_ROOT = os.path.join("tools", "java")

# Playwright Chromium source: %LOCALAPPDATA%\ms-playwright  (latest chromium-* folder)
PLAYWRIGHT_SRC  = os.path.join(os.environ.get("LOCALAPPDATA", ""), "ms-playwright")
PLAYWRIGHT_DEST = os.path.join(APP_DIR, "ms-playwright")   # dist/ProjectOffline/ms-playwright/

# Portable Git (MinGit) — optional, bundled when tools/git/ is present
GIT_SRC  = os.path.join("tools", "git")
GIT_DEST = os.path.join(APP_DIR, "git")    # dist/ProjectOffline/git/

# Portable SVN — optional, bundled when tools/svn/ is present
SVN_SRC  = os.path.join("tools", "svn")
SVN_DEST = os.path.join(APP_DIR, "svn")    # dist/ProjectOffline/svn/

# Runtime hook that sets JAVA_HOME before jpype is imported
RUNTIME_HOOK = os.path.join("tools", "pyi_rthook_jdk.py")

# Icon (optional — skip if not present)
ICON_PATH = os.path.join("src", "icons", "app.ico")

# -- Documentation PDF configuration -------------------------------------------
# The HTML source trees are pre-processed and rendered to PDF by
# tools/build_docs_pdf.py (using WeasyPrint).
# Output: dist/ProjectOffline/documentation/
DOCS_DEST = os.path.join(APP_DIR, "documentation")

# PDFs produced by build_docs_pdf.py (intermediate location)
_DOCS_PDF_BUILD_DIR    = os.path.join("build", "docs")
_PRESENTATION_PDF_SRC  = os.path.join(_DOCS_PDF_BUILD_DIR, "presentation.pdf")
_USER_DOCS_PDF_SRC     = os.path.join(_DOCS_PDF_BUILD_DIR, "user_documentation.pdf")

# Final locations inside the dist bundle
_PRESENTATION_PDF_DEST = os.path.join(DOCS_DEST, "presentation.pdf")
_USER_DOCS_PDF_DEST    = os.path.join(DOCS_DEST, "user_documentation.pdf")

# Sentinel written by _build_docs so SCons can track the target
_DOCS_SENTINEL = os.path.join(DOCS_DEST, ".copied")

# email_configs.install.json — shipped template copied to dist root as email_configs.json
EMAIL_CONFIGS_SRC  = "email_configs.install.json"
EMAIL_CONFIGS_DEST = os.path.join(APP_DIR, "email_configs.json")  # dist/ProjectOffline/email_configs.json

# email_templates/ — external JSON email templates folder, copied alongside the executable
EMAIL_TEMPLATES_SRC  = "email_templates"
EMAIL_TEMPLATES_DEST = os.path.join(APP_DIR, "email_templates")   # dist/ProjectOffline/email_templates/

# -- SFX installer configuration -----------------------------------------------
# Output: dist/ProjectOffline_v2026.05.02-19.35_installer.exe
SFX_EXE = os.path.join(BIN_DIR, f"{APP_NAME}_{BUILD_VERSION}_installer.exe")

# Intermediate 7z archive (inside build/, not shipped)
SFX_ARCHIVE = os.path.join(SPEC_DIR, "bundle.7z")

# -- InnoSetup installer configuration -----------------------------------------
# Template lives in installer/; SConstruct generates setup.iss at build time.
ISS_TEMPLATE  = os.path.join("installer", "setup.iss.template")
ISS_GENERATED = "setup.iss"   # written to project root; listed in .gitignore
INNO_EXE      = os.path.join(BIN_DIR, f"{APP_NAME}_{BUILD_VERSION}_setup.exe")

# Code-signing — SafeNet eToken / hardware token support
# ---------------------------------------------------------
# The signing step uses signtool.exe (Windows SDK).  Two mutually-exclusive
# ways to identify the certificate are supported:
#
#   SIGN_THUMBPRINT  — SHA-1 thumbprint (most precise; recommended)
#     scons SIGN_THUMBPRINT=<40-hex-chars>
#     set SIGN_THUMBPRINT=<40-hex-chars>  # or via environment variable
#
#   SIGN_SUBJECT     — Common Name / Subject substring (fallback)
#     scons SIGN_SUBJECT="Acme Corp"
#
# SafeNet eToken workflow:
#   1. Insert the token and unlock it (SafeNet Authentication Client must be
#      running; the PIN is prompted once per session by the middleware).
#   2. The certificate appears automatically in the Windows Personal store.
#   3. Find the thumbprint — either run `scons` with no signing args (a list
#      of available code-signing certs will be printed) or in PowerShell:
#        Get-ChildItem Cert:\CurrentUser\My |
#          Where-Object { $_.EnhancedKeyUsageList -match 'Code Signing' } |
#          Format-Table Thumbprint, Subject, NotAfter
#   4. Pass the thumbprint: scons SIGN_THUMBPRINT=<hex>
#
# When neither SIGN_THUMBPRINT nor SIGN_SUBJECT is set, signing is skipped
# and available code-signing certificates are listed as a hint.
#
SIGN_THUMBPRINT = ARGUMENTS.get(  # type: ignore[name-defined]  # SCons built-in
    "SIGN_THUMBPRINT",
    os.environ.get("SIGN_THUMBPRINT", ""),
)
SIGN_SUBJECT = ARGUMENTS.get(  # type: ignore[name-defined]
    "SIGN_SUBJECT",
    os.environ.get("SIGN_SUBJECT", ""),
)
TIMESTAMP_URL = "http://timestamp.digicert.com"

# -- Helper: locate the JDK directory ------------------------------------------
def _find_jdk_dir():
    """Return the first jdk-* sub-directory inside tools/java/, or None."""
    candidates = sorted(glob.glob(os.path.join(JDK_SRC_ROOT, "jdk*")))
    return candidates[0] if candidates else None


# -- Helper: locate the Chromium directory matching the venv Playwright --------
def _playwright_chromium_revision() -> "str | None":
    """Read the expected Chromium revision from the venv's Playwright package.

    Looks for the ``browsers.json`` that ships with playwright and returns the
    revision string (e.g. ``'1208'``) for the ``chromium`` entry, or None when
    the file cannot be found / parsed.
    """
    import json as _json
    search_roots = [
        # Venv first — most reliable
        os.path.join("venv", "Lib", "site-packages", "playwright",
                     "driver", "package", "browsers.json"),
        # Running interpreter's site-packages as fallback
        os.path.join(os.path.dirname(sys.executable),
                     "Lib", "site-packages", "playwright",
                     "driver", "package", "browsers.json"),
    ]
    for candidate in search_roots:
        if os.path.isfile(candidate):
            try:
                with open(candidate, encoding="utf-8") as fh:
                    data = _json.load(fh)
                for entry in data.get("browsers", []):
                    if entry.get("name") == "chromium":
                        rev = str(entry["revision"])
                        print(f"Playwright chromium revision (from {candidate}): {rev}")
                        return rev
            except Exception:
                pass
    return None


def _find_chromium_dirs():
    """Return the Playwright browser directories to bundle.

    Picks the revision that matches the venv's Playwright package (read from
    browsers.json).  Falls back to the highest build number when the revision
    cannot be determined.

    Playwright splits Chromium into two executables:
      chromium-<build>               — full browser, used for headless=False
      chromium_headless_shell-<build>— headless shell, used for headless=True

    Both are required because integrations/confluence_calendar_integration.py calls
    pw.chromium.launch(headless=True) AND pw.chromium.launch(headless=False).

    Returns a (possibly empty) list of absolute paths.
    """
    if not os.path.isdir(PLAYWRIGHT_SRC):
        return []

    revision = _playwright_chromium_revision()

    def _pick(pattern, preferred_suffix):
        """Return the best matching directory for *pattern*.

        When *preferred_suffix* is set, prefer the directory ending with that
        suffix (e.g. ``'chromium-1208'``).  Fall back to highest build number.
        """
        candidates = [
            p for p in glob.glob(os.path.join(PLAYWRIGHT_SRC, pattern))
            if os.path.isdir(p)
        ]
        if not candidates:
            return None
        if preferred_suffix:
            for p in candidates:
                if os.path.basename(p) == preferred_suffix:
                    return p
            print(f"WARNING: Preferred Chromium dir '{preferred_suffix}' not found in "
                  f"'{PLAYWRIGHT_SRC}' — run: venv\\Scripts\\python.exe -m playwright install chromium")
        # Fallback: highest build number
        def _build_num(p):
            part = os.path.basename(p).rsplit("-", 1)[-1]
            return int(part) if part.isdigit() else 0
        return max(candidates, key=_build_num)

    result = []
    for pat, suffix_fmt in (
        ("chromium-*",              "chromium-{rev}"),
        ("chromium_headless_shell-*", "chromium_headless_shell-{rev}"),
    ):
        preferred = suffix_fmt.format(rev=revision) if revision else None
        best = _pick(pat, preferred)
        if best:
            result.append(best)
    return result


def _find_chromium_dir():
    """Backwards-compat: return the full-browser chromium path (or None)."""
    dirs = _find_chromium_dirs()
    return next((d for d in dirs if os.path.basename(d).startswith("chromium-")), None)


# -- Helper: resolve the Python executable to use ------------------------------
def _python():
    """Prefer the venv interpreter; fall back to the running interpreter."""
    venv_py = os.path.join("venv", "Scripts", "python.exe")
    if os.path.isfile(venv_py):
        return os.path.abspath(venv_py)
    return sys.executable


# -- Helper: write a Windows PE version-resource file -------------------------
def _write_version_file(path, version_str):
    """Write a PyInstaller-compatible Windows version resource file.

    version_str is expected in the form 'vYYYY.MM.DD-HH.MM'.
    The four-tuple used by Windows (major, minor, patch, build) is derived as
    (YYYY, MM, DD, HHMM).
    """
    # Strip leading 'v', split on '-' to get date and time parts
    bare = version_str.lstrip("v")
    date_part, time_part = bare.split("-", 1)
    year, month, day = (int(x) for x in date_part.split("."))
    hhmm = int(time_part.replace(".", ""))
    ver_tuple = (year, month, day, hhmm)
    ver_str   = f"{year}.{month}.{day}.{hhmm}"

    content = f'''\
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={ver_tuple},
    prodvers={ver_tuple},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        u'040904B0',
        [StringStruct(u'CompanyName',      u''),
         StringStruct(u'FileDescription',  u'Project Offline'),
         StringStruct(u'FileVersion',      u'{ver_str}'),
         StringStruct(u'InternalName',     u'ProjectOffline'),
         StringStruct(u'ProductName',      u'Project Offline'),
         StringStruct(u'ProductVersion',   u'{version_str}')])
    ]),
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
  ]
)
'''
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)


# -- Helper: write src/_version.py so the running app knows its build version ---
def _write_version_module(version_str):
    """Write (or overwrite) src/_version.py with the current build version.

    The module exposes a single constant::

        from _version import BUILD_VERSION   # e.g. 'v2026.05.02-19.35'

    The file is committed to the repo only as a template; SConstruct always
    regenerates it before PyInstaller runs so the bundle contains the correct
    timestamp.
    """
    module_path = os.path.join("src", "_version.py")
    with open(module_path, "w", encoding="utf-8") as fh:
        fh.write(
            "# Auto-generated by SConstruct — do not edit manually.\n"
            f'BUILD_VERSION = "{version_str}"\n'
        )
    print(f"Wrote {module_path}  ({version_str})")


# -- Action: run PyInstaller ----------------------------------------------------
def _run_pyinstaller(target, source, env):
    import subprocess

    py = _python()

    # Generate the Windows version resource file into the build directory
    os.makedirs(SPEC_DIR, exist_ok=True)
    ver_file = os.path.abspath(os.path.join(SPEC_DIR, "version_info.txt"))
    _write_version_file(ver_file, BUILD_VERSION)

    # Write src/_version.py so the running bundle can read its own version
    _write_version_module(BUILD_VERSION)

    print(f"Build version:  {BUILD_VERSION}")

    cmd = [
        py, "-m", "PyInstaller",
        "--name",        APP_NAME,
        "--windowed",                           # no console window
        "--onedir",                             # directory bundle (faster startup)
        "--distpath",    BIN_DIR,               # ? bin/ProjectOffline/
        "--workpath",    WORK_DIR,
        "--specpath",    SPEC_DIR,
        "--noconfirm",                          # overwrite previous build
        "--version-file", ver_file,             # Windows PE version resource
        # -- Sources --------------------------------------------------------
        "--paths",       "src",                 # resolve top-level src imports
        "--paths",       os.path.join("src", "views"),  # resolve view imports
        "--paths",       os.path.join("src", "integrations"),  # resolve integrations imports
        # views/ modules are imported lazily (inside functions); PyInstaller
        # cannot trace that dynamically, so every view module is listed here
        # as a hidden import so they are collected into the bundle.
        "--hidden-import", "task_view",
        "--hidden-import", "gantt_view",
        "--hidden-import", "resource_view",
        "--hidden-import", "dependency_view",
        "--hidden-import", "baseline_view",
        "--hidden-import", "team_planner_view",
        "--hidden-import", "task_sheet_view",
        "--hidden-import", "resource_usage_graph_view",
        "--hidden-import", "resource_usage_histogram_view",
        "--hidden-import", "timeline_view",
        "--hidden-import", "hour_mode",
        # integrations/ modules are imported lazily (inside functions); PyInstaller
        # cannot trace that dynamically, so every integration module is listed here
        # as a hidden import so they are collected into the bundle.
        "--hidden-import", "ad_integration",
        "--hidden-import", "confluence_calendar_integration",
        "--hidden-import", "email_integration",
        "--hidden-import", "jira_integration",
        "--hidden-import", "jira_sync",
        "--hidden-import", "keepass_integration",
        "--hidden-import", "secondary_calendar_integration",
        "--hidden-import", "version_control_integration",
        # -- Data files ----------------------------------------------------
        # (mpxj JARs are collected automatically via --collect-all mpxj)
        # -- Hidden / dynamic imports --------------------------------------
        "--hidden-import", "PyQt5.sip",
        "--hidden-import", "PyQt5.QtPrintSupport",
        "--hidden-import", "PyQt5.QtSvg",
        "--hidden-import", "PyQt5.QtXml",
        # -- Full package collection (C extensions + data) -----------------
        "--collect-all", "jpype",               # JPype C extensions + helpers
        "--collect-all", "mpxj",                # MPXJ JARs in mpxj/lib/
        "--collect-all", "tzdata",              # IANA timezone database (Windows: zoneinfo has no built-in data)
        "--collect-all", "playwright",          # Playwright driver (node.exe + package) required at runtime
        # -- Runtime hook — sets JAVA_HOME before jpype is imported --------
        "--runtime-hook", RUNTIME_HOOK,
    ]

    # Add icon only when the file exists
    if os.path.isfile(ICON_PATH):
        cmd += ["--icon", ICON_PATH]

    cmd.append(str(source[0]))   # entry point: src/main.py

    print("Running PyInstaller ...")
    print(" ".join(cmd))
    subprocess.check_call(cmd)


# -- Action: copy OpenJDK into the bundle --------------------------------------
def _copy_jdk(target, source, env):
    jdk_src = _find_jdk_dir()
    if not jdk_src:
        raise Exception(
            f"No JDK found in '{JDK_SRC_ROOT}'. "
            "Run:  python tools/download_openjdk.py"
        )

    if os.path.exists(JDK_DEST):
        shutil.rmtree(JDK_DEST)

    print(f"Copying OpenJDK  {jdk_src}  ?  {JDK_DEST}")
    shutil.copytree(jdk_src, JDK_DEST)


# -- Action: copy Playwright Chromium into the bundle --------------------------
def _copy_chromium(target, source, env):
    chromium_dirs = _find_chromium_dirs()
    sentinel = str(target[0])

    if not chromium_dirs:
        print(
            f"WARNING: No Chromium installation found in '{PLAYWRIGHT_SRC}'.\n"
            "         Playwright Confluence Calendar Sync will not work in the bundle.\n"
            "         Fix:  playwright install chromium"
        )
        os.makedirs(PLAYWRIGHT_DEST, exist_ok=True)
        open(sentinel, "w").close()
        return

    if os.path.exists(PLAYWRIGHT_DEST):
        shutil.rmtree(PLAYWRIGHT_DEST)
    os.makedirs(PLAYWRIGHT_DEST, exist_ok=True)

    copied = []
    for chromium_src in chromium_dirs:
        chromium_name = os.path.basename(chromium_src)   # e.g. chromium-1208
        dest = os.path.join(PLAYWRIGHT_DEST, chromium_name)
        print(f"Copying Chromium  {chromium_src}  ?  {dest}")
        shutil.copytree(chromium_src, dest)
        copied.append(chromium_name)

    # Write sentinel so SCons knows this target is up-to-date
    with open(sentinel, "w") as fh:
        fh.write("\n".join(copied) + "\n")


# -- Helper: locate 7z.exe -----------------------------------------------------
def _find_7zip():
    """Return the absolute path to 7z.exe, or raise FileNotFoundError."""
    which = shutil.which("7z")
    if which:
        return which
    candidates = [
        r"C:\Program Files\7-Zip\7z.exe",
        r"C:\Program Files (x86)\7-Zip\7z.exe",
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    raise FileNotFoundError(
        "7-Zip not found. Install from https://www.7-zip.org/ "
        "or add 7z.exe to PATH."
    )


# -- Helper: locate signtool.exe from the Windows SDK -------------------------
def _find_signtool():
    """Return path to signtool.exe, or None."""
    # Fixed locations checked in priority order
    fixed = [
        r"C:\Program Files (x86)\Windows Kits\10\App Certification Kit\signtool.exe",
        r"C:\Program Files\Windows Kits\10\App Certification Kit\signtool.exe",
    ]
    for path in fixed:
        if os.path.isfile(path):
            return path
    # Fallback: versioned SDK bins (newest first)
    patterns = [
        r"C:\Program Files (x86)\Windows Kits\10\bin\*\x64\signtool.exe",
        r"C:\Program Files\Windows Kits\10\bin\*\x64\signtool.exe",
    ]
    for pat in patterns:
        matches = sorted(glob.glob(pat), reverse=True)
        if matches:
            return matches[0]
    return shutil.which("signtool")


# -- Helper: locate ISCC.exe (Inno Setup Compiler) ----------------------------
def _find_iscc():
    """Return the absolute path to ISCC.exe, or raise FileNotFoundError.

    Search order:
      1. tools/innosetup/ISCC.exe  — local portable install via download_innosetup.py
      2. PATH
      3. Standard system-wide Inno Setup 6 / 5 install locations
    """
    # 1. Local portable install (preferred — no system-wide requirement)
    local = os.path.abspath(os.path.join("tools", "innosetup", "ISCC.exe"))
    if os.path.isfile(local):
        return local
    # 2. PATH
    which = shutil.which("ISCC") or shutil.which("iscc")
    if which:
        return which
    # 3. Standard install locations
    candidates = [
        r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
        r"C:\Program Files\Inno Setup 6\ISCC.exe",
        r"C:\Program Files (x86)\Inno Setup 5\ISCC.exe",
        r"C:\Program Files\Inno Setup 5\ISCC.exe",
    ]
    for c in candidates:
        if os.path.isfile(c):
            return c
    raise FileNotFoundError(
        "ISCC.exe (Inno Setup Compiler) not found.\n"
        "Run:  python tools/download_innosetup.py\n"
        "Or install Inno Setup 6 from https://jrsoftware.org/isdl.php"
    )


# -- Helper: list code-signing certs available in the Windows Personal store ---
def _list_code_signing_certs():
    """Print all code-signing certificates visible in the current user store.

    Called automatically when no signing credentials are provided, so the
    user can identify their SafeNet eToken certificate thumbprint.
    """
    import subprocess as _sp
    ps = (
        "Get-ChildItem Cert:\\CurrentUser\\My "
        "| Where-Object { $_.EnhancedKeyUsageList -match 'Code Signing' } "
        "| Select-Object Thumbprint, Subject, NotAfter "
        "| Format-Table -AutoSize"
    )
    print()
    print("No signing credentials supplied -- skipping code signing.")
    print("If you have a SafeNet eToken: insert it and ensure SafeNet")
    print("Authentication Client is running, then re-run scons.")
    print()
    print("Available code-signing certificates in Windows Personal store:")
    try:
        result = _sp.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            capture_output=True, text=True,
        )
        output = result.stdout.strip()
        print(output if output else "  (none found -- is your eToken inserted?)")
    except Exception:
        print("  (could not enumerate -- ensure PowerShell is available)")
    print()
    print("Then pass the thumbprint:  scons SIGN_THUMBPRINT=<40-hex-chars>")
    print("Or by subject name:        scons SIGN_SUBJECT=\"Your Name\"")
    print()


# -- Helper: code-sign a file using the Windows Certificate Store --------------
def _sign_file(file_path, thumbprint, subject=""):
    """Sign *file_path* using signtool.exe.

    Certificate selection (optional, highest priority first):
      1. *thumbprint* — ``/sha1 <hex>``  most precise
      2. *subject*    — ``/n <name>``    CN substring match

    When neither is provided signtool selects the certificate automatically
    (Windows picks the best available code-signing cert in the Personal store).
    """
    thumb = thumbprint.strip() if thumbprint else ""
    subj  = (subject or SIGN_SUBJECT).strip()
    signtool = _find_signtool()
    if not signtool:
        print("WARNING: signtool.exe not found -- skipping code signing.")
        return
    import subprocess as _sp
    cmd = [
        signtool, "sign",
        "/fd",   "SHA256",      # file digest algorithm
        "/tr",   TIMESTAMP_URL, # RFC 3161 timestamp authority
        "/td",   "SHA256",      # timestamp digest algorithm
    ]
    if thumb:
        cmd += ["/sha1", thumb]
    elif subj:
        cmd += ["/n", subj]
    # else: no selector — signtool picks automatically
    cmd.append(file_path)
    print(f"Signing  {file_path} ...")
    try:
        _sp.check_call(cmd)
    except _sp.CalledProcessError as exc:
        print(f"WARNING: Code signing failed (exit {exc.returncode}) -- skipping. "
              "Insert your eToken or check certificate availability.")


# -- Action: copy portable Git into the bundle --------------------------------
def _copy_git(target, source, env):
    sentinel = str(target[0])
    if not os.path.isdir(GIT_SRC):
        print(
            f"INFO: tools/git/ not found — skipping Git bundle.\n"
            "      Run:  python tools/download_git_for_windows.py"
        )
        os.makedirs(GIT_DEST, exist_ok=True)
        open(sentinel, "w").close()
        return

    if os.path.exists(GIT_DEST):
        shutil.rmtree(GIT_DEST)

    print(f"Copying Git  {GIT_SRC}  ->  {GIT_DEST}")
    shutil.copytree(GIT_SRC, GIT_DEST)

    with open(sentinel, "w") as fh:
        fh.write(GIT_SRC + "\n")


# -- Action: copy portable SVN into the bundle ---------------------------------
def _copy_svn(target, source, env):
    sentinel = str(target[0])
    if not os.path.isdir(SVN_SRC):
        print(
            f"INFO: tools/svn/ not found — skipping SVN bundle."
        )
        os.makedirs(SVN_DEST, exist_ok=True)
        open(sentinel, "w").close()
        return

    if os.path.exists(SVN_DEST):
        shutil.rmtree(SVN_DEST)

    print(f"Copying SVN  {SVN_SRC}  ->  {SVN_DEST}")
    shutil.copytree(SVN_SRC, SVN_DEST)

    with open(sentinel, "w") as fh:
        fh.write(SVN_SRC + "\n")


# -- Action: build PDF documentation and copy into the bundle -----------------
def _build_docs(target, source, env):
    """Run tools/build_docs_pdf.py to produce PDFs, then copy them to dist.

    Produces:
      build/docs/presentation.pdf      → dist/.../documentation/presentation.pdf
      build/docs/user_documentation.pdf → dist/.../documentation/user_documentation.pdf
    """
    import subprocess as _sp

    pdf_script = os.path.abspath(os.path.join("tools", "build_docs_pdf.py"))
    out_dir    = os.path.abspath(_DOCS_PDF_BUILD_DIR)

    python_exe = sys.executable  # use the same interpreter that runs SCons

    print(f"Building PDF documentation  ->  {out_dir}")
    _sp.check_call([python_exe, pdf_script, "--out-dir", out_dir])

    # Copy the produced PDFs into the dist bundle
    os.makedirs(DOCS_DEST, exist_ok=True)
    for src, dest in (
        (_PRESENTATION_PDF_SRC, _PRESENTATION_PDF_DEST),
        (_USER_DOCS_PDF_SRC,    _USER_DOCS_PDF_DEST),
    ):
        src_abs  = os.path.abspath(src)
        dest_abs = os.path.abspath(dest)
        print(f"Copying  {src_abs}  ->  {dest_abs}")
        shutil.copy2(src_abs, dest_abs)

    with open(str(target[0]), "w") as fh:
        fh.write("presentation.pdf\n")
        fh.write("user_documentation.pdf\n")

    print(f"Documentation PDFs ready in  {DOCS_DEST}")


# -- Action: copy email_configs.install.json → dist/ProjectOffline/email_configs.json -----------
def _copy_email_configs(target, source, env):
    """Copy the install-time email_configs.install.json to the dist bundle root.

    The file is placed at dist/ProjectOffline/email_configs.json so that the
    bundled application finds a default (empty) config on first launch.  The
    source file intentionally contains no sender address (per-project only).
    """
    dest = str(target[0])
    print(f"Copying email config  {EMAIL_CONFIGS_SRC}  ->  {dest}")
    shutil.copy2(EMAIL_CONFIGS_SRC, dest)


# -- Action: copy email_templates/ → dist/ProjectOffline/email_templates/ ------
def _copy_email_templates(target, source, env):
    """Copy the email_templates/ folder into the dist bundle.

    The folder is placed at dist/ProjectOffline/email_templates/ so the
    bundled application finds the shipped JSON templates on launch.
    If the destination already exists (incremental build) it is removed first
    to ensure a clean copy.
    """
    dest = os.path.join(APP_DIR, "email_templates")
    if os.path.exists(dest):
        shutil.rmtree(dest)
    print(f"Copying email templates  {EMAIL_TEMPLATES_SRC}/  ->  {dest}/")
    shutil.copytree(EMAIL_TEMPLATES_SRC, dest)


# -- Action: create self-extracting 7z installer (console SFX) -----------------
def _create_sfx(target, source, env):
    """Pack dist/ProjectOffline/ into a console SFX executable.

    The SFX is built by concatenating the 7-Zip console SFX module (7z.sfx)
    with a plain 7z archive of the application bundle.

    Usage of the produced installer (command line, no GUI):
      ProjectOffline_vYYYY.MM.DD-HH.MM_installer.exe
          ? extracts ProjectOffline\\ into the current working directory

      ProjectOffline_vYYYY.MM.DD-HH.MM_installer.exe -o"C:\\Target"
          ? extracts ProjectOffline\\ into C:\\Target\\

    To install next to the installer, open a cmd window in the same directory
    and run the exe without arguments (or use -o".").
    """
    import subprocess as _sp

    seven_zip = _find_7zip()
    seven_zip_dir = os.path.dirname(seven_zip)

    # 7zCon.sfx  — console SFX, NO GUI, NO UAC elevation  (from 7-Zip Extra)
    # 7z.sfx     — GUI installer SFX with admin manifest  (bundled with 7-Zip)
    # We must use 7zCon.sfx; 7z.sfx would trigger a UAC prompt every time.
    #
    # 7zCon.sfx ships in the "7-Zip Extra" package available at:
    #   https://www.7-zip.org/download.html  ("Download 7-Zip Extra: …")
    # Extract it and place 7zCon.sfx in the same folder as 7z.exe, e.g.:
    #   C:\Program Files\7-Zip\7zCon.sfx
    # Alternatively, place it next to this SConstruct as tools/7zCon.sfx.
    _sfx_candidates = [
        os.path.join(seven_zip_dir, "7zCon.sfx"),       # standard install location
        os.path.join("tools", "7zCon.sfx"),              # local fallback in repo
    ]
    sfx_module = next((p for p in _sfx_candidates if os.path.isfile(p)), None)
    if sfx_module is None:
        raise FileNotFoundError(
            "7zCon.sfx (console SFX module, no UAC) not found.\n"
            "Download the '7-Zip Extra' package from https://www.7-zip.org/download.html\n"
            "and place 7zCon.sfx in one of:\n"
            + "\n".join(f"  {p}" for p in _sfx_candidates)
        )

    # -- 1. Sign the application executable (before archiving) -----------------
    _exe_to_sign = os.path.abspath(os.path.join(APP_DIR, f"{APP_NAME}.exe"))
    _sign_file(_exe_to_sign, SIGN_THUMBPRINT)

    # -- 2. Pack the bundle into a 7z archive ----------------------------------
    # Run 7z from BIN_DIR so the archive root is ProjectOffline/ (not dist/ProjectOffline/)
    archive_abs = os.path.abspath(SFX_ARCHIVE)
    os.makedirs(os.path.dirname(archive_abs), exist_ok=True)
    if os.path.isfile(archive_abs):
        os.remove(archive_abs)

    print(f"Creating 7z archive  ...  {archive_abs}")
    _sp.check_call(
        [seven_zip, "a", "-t7z", "-mx=5", "-mmt=on", archive_abs, APP_NAME,
         # exclude internal SCons sentinel files (not part of the application)
         "-xr!.copied", "-xr!.bundled"],
        cwd=os.path.abspath(BIN_DIR),   # archive root = ProjectOffline/
    )

    # -- 3. Concatenate [7zCon.sfx] + [bundle.7z] ? installer exe ------------
    sfx_exe = str(target[0])
    os.makedirs(os.path.dirname(sfx_exe) or ".", exist_ok=True)
    print(f"Building SFX  ?  {sfx_exe}")
    with open(sfx_exe, "wb") as out:
        for part in (sfx_module, archive_abs):
            with open(part, "rb") as inp:
                shutil.copyfileobj(inp, out)

    # -- 4. Code-sign the SFX installer (optional) ---------------------------
    _sign_file(sfx_exe, SIGN_THUMBPRINT)

    print(f"\nInstaller ready:  {sfx_exe}")
    print(f"  Silent extract to current dir : {os.path.basename(sfx_exe)}")
    print(f"  Extract to specific path      : {os.path.basename(sfx_exe)} -o\"C:\\Target\"")


# -- Action: generate setup.iss from template and compile with ISCC -----------
def _create_inno_installer(target, source, env):
    """Generate setup.iss from installer/setup.iss.template and run ISCC.

    Build-time substitutions applied to the template:
      @@VERSION@@          BUILD_VERSION string (e.g. v2026.05.14-17.21)
      @@SOURCE_DIR@@       absolute path to dist/ProjectOffline/
      @@OUTPUT_DIR@@       absolute path to dist/
      @@ICON_PATH@@        absolute path to src/icons/app.ico (if present)
      @@OUTPUT_FILENAME@@  installer filename without .exe extension

    The produced installer executable is then code-signed when signing
    credentials are available (SIGN_THUMBPRINT / SIGN_SUBJECT).
    """
    import subprocess as _sp

    # 1. Read the template.
    with open(ISS_TEMPLATE, encoding="utf-8") as fh:
        content = fh.read()

    # 2. Substitute build-time placeholders.
    output_filename = f"{APP_NAME}_{BUILD_VERSION}_setup"
    icon_path = os.path.abspath(ICON_PATH) if os.path.isfile(ICON_PATH) else ""
    substitutions = {
        "@@VERSION@@":         BUILD_VERSION,
        "@@SOURCE_DIR@@":      os.path.abspath(APP_DIR),
        "@@OUTPUT_DIR@@":      os.path.abspath(BIN_DIR),
        "@@ICON_PATH@@":       icon_path,
        "@@OUTPUT_FILENAME@@": output_filename,
    }
    for marker, value in substitutions.items():
        content = content.replace(marker, value)

    # 3. Write the generated script to the project root.
    with open(ISS_GENERATED, "w", encoding="utf-8") as fh:
        fh.write(content)
    print(f"Generated  {ISS_GENERATED}")

    # 4. Locate ISCC.
    try:
        iscc = _find_iscc()
    except FileNotFoundError as exc:
        print(f"\nWARNING: {exc}\nSkipping Inno Setup installer creation.")
        # Touch the target so SCons does not re-run unnecessarily.
        open(str(target[0]), "w").close()
        return

    # 5. Sign the application executable before packaging (same as SFX step).
    _exe_to_sign = os.path.abspath(os.path.join(APP_DIR, f"{APP_NAME}.exe"))
    _sign_file(_exe_to_sign, SIGN_THUMBPRINT)

    # 6. Compile the installer.
    iss_abs = os.path.abspath(ISS_GENERATED)
    print(f"Running ISCC  {iss_abs}")
    _sp.check_call([iscc, iss_abs])

    # 7. Code-sign the produced installer.
    _sign_file(str(target[0]), SIGN_THUMBPRINT)

    print(f"\nInno Setup installer ready:  {str(target[0])}")


# -- SCons environment ----------------------------------------------------------
env = Environment(ENV=os.environ) # type: ignore


# -- Target 1: PyInstaller build -----------------------------------------------
# Sentinel: the main executable produced by PyInstaller.
_exe_sentinel = os.path.join(APP_DIR, f"{APP_NAME}.exe")

pyinstaller_build = env.Command(
    target = _exe_sentinel,
    source = ENTRY_POINT,
    action = _run_pyinstaller,
)

# Always re-run if source files changed (SCons tracks the entry point;
# for a full rebuild force 'scons -c && scons').
env.AlwaysBuild(pyinstaller_build)


# -- Target 2: copy OpenJDK ----------------------------------------------------
_jdk_sentinel = os.path.join(JDK_DEST, "release")   # stable file inside any JDK

copy_jdk = env.Command(
    target = _jdk_sentinel,
    source = pyinstaller_build,
    action = _copy_jdk,
)


# -- Target 3: copy Playwright Chromium ----------------------------------------
# Sentinel: ms-playwright/.bundled records which chromium version was copied.
_chromium_sentinel = os.path.join(PLAYWRIGHT_DEST, ".bundled")

copy_chromium = env.Command(
    target = _chromium_sentinel,
    source = copy_jdk,
    action = _copy_chromium,
)


# -- Target 4a: copy portable Git ---------------------------------------------
_git_sentinel = os.path.join(GIT_DEST, ".bundled")

copy_git = env.Command(
    target = _git_sentinel,
    source = copy_chromium,
    action = _copy_git,
)


# -- Target 4b: copy portable SVN ---------------------------------------------
_svn_sentinel = os.path.join(SVN_DEST, ".bundled")

copy_svn = env.Command(
    target = _svn_sentinel,
    source = copy_git,
    action = _copy_svn,
)


# -- Target 5: build PDF documentation and copy into bundle -------------------
generate_docs = env.Command(
    target = _DOCS_SENTINEL,
    source = copy_svn,
    action = _build_docs,
)


# -- Target 6: copy email_configs.install.json → dist root --------------------
copy_email_configs = env.Command(
    target = EMAIL_CONFIGS_DEST,
    source = generate_docs,
    action = _copy_email_configs,
)


# -- Target 7: copy email_templates/ → dist bundle ----------------------------
# Sentinel file used so SCons can track the target (copytree has no single target).
_EMAIL_TEMPLATES_SENTINEL = os.path.join(EMAIL_TEMPLATES_DEST, ".copied")
copy_email_templates = env.Command(
    target = _EMAIL_TEMPLATES_SENTINEL,
    source = copy_email_configs,
    action = [_copy_email_templates,
              lambda target, source, env: open(str(target[0]), "w").close()],
)


# -- Target 8: create SFX installer -------------------------------------------
create_sfx = env.Command(
    target = SFX_EXE,
    source = copy_email_templates,
    action = _create_sfx,
)


# -- Target 9: create Inno Setup installer ------------------------------------
# Depends on create_sfx so the app executable is already code-signed when
# InnoSetup packages it.  Produces dist/ProjectOffline_<ver>_setup.exe.
create_inno = env.Command(
    target = INNO_EXE,
    source = create_sfx,
    action = _create_inno_installer,
)


# -- Default + clean -----------------------------------------------------------
env.Default(create_inno)

# 'scons -c' removes these directories and the generated setup.iss.
env.Clean(create_inno, [BIN_DIR, WORK_DIR, SPEC_DIR, ISS_GENERATED])
