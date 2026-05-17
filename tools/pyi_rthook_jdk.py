# tools/pyi_rthook_jdk.py
# PyInstaller runtime hook — configure JAVA_HOME and PLAYWRIGHT_BROWSERS_PATH
# to point to the bundled JDK and Chromium before any application module
# (especially jpype / mpxj / playwright) is imported.
#
# Layout produced by the SConstruct build:
#
#   dist/
#     ProjectOffline/
#       ProjectOffline.exe        ← sys.executable
#       jdk/                      ← bundled OpenJDK (copied by SConstruct)
#         bin/
#         lib/
#         ...
#       ms-playwright/            ← bundled Playwright Chromium
#         chromium-1208/
#           chrome-win64/
#           INSTALLATION_COMPLETE
#         .bundled
#       _internal/                ← PyInstaller ≥ 6 layout (all .pyd / .dll / .pyc)
#         ...

import os
import sys

# sys.executable is always the real launcher .exe in both onedir and onefile.
_exe_dir = os.path.dirname(os.path.abspath(sys.executable))

# ── OpenJDK ───────────────────────────────────────────────────────────────────
_jdk_dir = os.path.join(_exe_dir, "jdk")

if os.path.isdir(_jdk_dir):
    os.environ["JAVA_HOME"] = _jdk_dir

    # Add jdk/bin and jdk/bin/server to PATH so that jvm.dll is resolvable
    # by ctypes (which is what JPype uses under the hood on Windows).
    _jdk_bin    = os.path.join(_jdk_dir, "bin")
    _jdk_server = os.path.join(_jdk_dir, "bin", "server")

    _path_parts = [_jdk_server, _jdk_bin] + os.environ.get("PATH", "").split(os.pathsep)
    os.environ["PATH"] = os.pathsep.join(_path_parts)

# ── Playwright Chromium ───────────────────────────────────────────────────────
# PLAYWRIGHT_BROWSERS_PATH must point to the directory that *contains*
# the chromium-XXXX sub-folder (i.e. the ms-playwright directory itself).
_pw_dir = os.path.join(_exe_dir, "ms-playwright")

if os.path.isdir(_pw_dir) and not os.environ.get("PLAYWRIGHT_BROWSERS_PATH"):
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = _pw_dir
