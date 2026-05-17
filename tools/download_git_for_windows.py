# tools/download_git_for_windows.py - Downloads the latest Git for Windows (MinGit portable ZIP)
import os
import urllib.request
import zipfile
import io
import json

API_URL = "https://api.github.com/repos/git-for-windows/git/releases/latest"

DEST_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "git"))
os.makedirs(DEST_DIR, exist_ok=True)

print("Fetching latest Git for Windows release info from GitHub API...")
with urllib.request.urlopen(API_URL) as response:
    release = json.load(response)

# Find the MinGit 64-bit ZIP asset (minimal portable Git, no GUI tools)
zip_url = None
zip_name = None
for asset in release.get("assets", []):
    name = asset["name"].lower()
    if (
        name.startswith("mingit-") and
        "64-bit" in name and
        name.endswith(".zip")
    ):
        zip_url = asset["browser_download_url"]
        zip_name = asset["name"]
        break

if not zip_url:
    print("Could not find a MinGit 64-bit ZIP asset in the latest release.")
    exit(1)

# Skip download if git.exe already exists
git_exe = os.path.join(DEST_DIR, "cmd", "git.exe")
if os.path.exists(git_exe):
    print(f"Git for Windows already exists at {git_exe}")
    exit(0)

print(f"Downloading {zip_name} ...")
with urllib.request.urlopen(zip_url) as response:
    zip_data = response.read()

print(f"Extracting to {DEST_DIR} ...")
with zipfile.ZipFile(io.BytesIO(zip_data)) as z:
    z.extractall(DEST_DIR)

print(f"Git for Windows extracted to {DEST_DIR}")
