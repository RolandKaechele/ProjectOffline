# tools/download_openjdk.py - Downloads and extracts OpenJDK 17 (portable) for Windows
import os
import urllib.request
import zipfile
import io
import json

API_URL = "https://api.github.com/repos/adoptium/temurin17-binaries/releases/latest"

DEST_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "tools", "java"))
os.makedirs(DEST_DIR, exist_ok=True)

print("Fetching Adoptium release info from GitHub API...")
with urllib.request.urlopen(API_URL) as response:
    release = json.load(response)


# Find the latest JDK 17 Windows x64 ZIP asset
zip_url = None
for asset in release.get("assets", []):
    name = asset["name"].lower()
    if (
        name.startswith("openjdk17u-jdk_") and
        "windows" in name and
        "x64" in name and
        name.endswith(".zip") and
        "hotspot" in name
    ):
        zip_url = asset["browser_download_url"]
        break

if not zip_url:
    print("Could not find a suitable JDK 17 Windows x64 ZIP asset in the latest release.")
    exit(1)

print(f"Downloading {zip_url} ...")
with urllib.request.urlopen(zip_url) as response:
    zip_data = response.read()

print("Extracting OpenJDK 17...")
with zipfile.ZipFile(io.BytesIO(zip_data)) as z:
    z.extractall(DEST_DIR)

print(f"OpenJDK extracted to {DEST_DIR}")
