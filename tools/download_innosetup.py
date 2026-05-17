# tools/download_innosetup.py — Downloads and silently installs the latest Inno Setup
#
# The Inno Setup compiler (ISCC.exe) is placed in tools/innosetup/ so that
# SConstruct can locate it without requiring a system-wide installation.
#
# Usage:
#   python tools/download_innosetup.py
#
# After the script completes, ISCC.exe is available at:
#   tools/innosetup/ISCC.exe
#
# To re-install (upgrade), delete tools/innosetup/ first and re-run.

import json
import os
import subprocess
import sys
import tempfile
import urllib.request

API_URL  = "https://api.github.com/repos/jrsoftware/issrc/releases/latest"
DEST_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "innosetup"))
ISCC_EXE = os.path.join(DEST_DIR, "ISCC.exe")

# Skip if already installed.
if os.path.isfile(ISCC_EXE):
    print(f"Inno Setup already installed at {ISCC_EXE}")
    sys.exit(0)

print("Fetching latest Inno Setup release info from GitHub API ...")
req = urllib.request.Request(
    API_URL,
    headers={"Accept": "application/vnd.github+json",
             "User-Agent": "ProjectOffline-build"},
)
with urllib.request.urlopen(req) as resp:
    release = json.load(resp)

tag  = release.get("tag_name", "unknown")
name = release.get("name",     "unknown")
print(f"Latest release: {name}  (tag: {tag})")

# Find the installer asset — the .exe (not the .issig signature sidecar).
exe_url  = None
exe_name = None
for asset in release.get("assets", []):
    n = asset["name"]
    if n.startswith("innosetup-") and n.endswith(".exe"):
        exe_url  = asset["browser_download_url"]
        exe_name = n
        break

if not exe_url:
    print("ERROR: Could not find an innosetup-*.exe asset in the latest release.")
    sys.exit(1)

# Download to a temporary file (the asset is a Windows installer exe, not a zip).
print(f"Downloading {exe_name} ...")
with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as tmp:
    tmp_path = tmp.name

try:
    with urllib.request.urlopen(exe_url) as resp:
        data = resp.read()
    with open(tmp_path, "wb") as fh:
        fh.write(data)
    print(f"Downloaded {len(data) // 1024:,} KB  ->  {tmp_path}")

    # Run the installer silently into DEST_DIR.
    # Inno Setup's own installer understands the standard Inno Setup CLI flags.
    os.makedirs(DEST_DIR, exist_ok=True)
    cmd = [
        tmp_path,
        f"/DIR={DEST_DIR}",
        "/VERYSILENT",        # no wizard UI
        "/SUPPRESSMSGBOXES",  # suppress any error dialogs
        "/NORESTART",         # never prompt for a reboot
        "/NOICONS",           # skip Start Menu and Desktop shortcuts
        "/CLOSEAPPLICATIONS", # close apps using files being updated (silent)
    ]
    print(f"Installing into {DEST_DIR} ...")
    print("  " + " ".join(cmd))
    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        print(f"ERROR: Installer exited with code {result.returncode}")
        sys.exit(result.returncode)

finally:
    try:
        os.unlink(tmp_path)
    except OSError:
        pass

# Verify the install produced ISCC.exe.
if not os.path.isfile(ISCC_EXE):
    print(f"ERROR: Installation finished but ISCC.exe not found at {ISCC_EXE}")
    sys.exit(1)

print(f"\nInno Setup installed successfully.")
print(f"  ISCC.exe : {ISCC_EXE}")
