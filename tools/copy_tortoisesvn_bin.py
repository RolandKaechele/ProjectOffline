# tools/copy_tortoisesvn_bin.py - Copies TortoiseSVN command-line binaries to tools/svn/
import os
import shutil

SVN_BIN = r"C:\Program Files\TortoiseSVN\bin"
DEST_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "svn"))

if not os.path.isdir(SVN_BIN):
    print(f"TortoiseSVN bin directory not found: {SVN_BIN}")
    print("Install TortoiseSVN (with command-line tools) from https://tortoisesvn.net/downloads.html")
    exit(1)

os.makedirs(DEST_DIR, exist_ok=True)

# Only copy the executables and DLLs needed for command-line SVN use.
# svn.exe requires a small set of DLLs from the same bin folder.
INCLUDE_EXTS = {".exe", ".dll"}

copied = []
skipped = []
for entry in os.scandir(SVN_BIN):
    if not entry.is_file():
        continue
    ext = os.path.splitext(entry.name)[1].lower()
    if ext not in INCLUDE_EXTS:
        skipped.append(entry.name)
        continue
    dest_path = os.path.join(DEST_DIR, entry.name)
    if os.path.exists(dest_path):
        skipped.append(entry.name)
        continue
    shutil.copy2(entry.path, dest_path)
    copied.append(entry.name)

if copied:
    print(f"Copied {len(copied)} file(s) to {DEST_DIR}:")
    #for name in sorted(copied):
    #    print(f"  {name}")
else:
    print(f"No new files copied (all already present in {DEST_DIR})")
