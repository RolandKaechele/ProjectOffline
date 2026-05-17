"""
main.py - Entry point for the Qt5 Project Offline

This script launches a PyQt5 GUI application for reading and writing project files (.mpp, .xml).
It supports command-line arguments using argparse:
    --open <file>       Open a project file at startup
    --debug / -v        Enable verbose debug output (e.g. Confluence calendar sync details)

Usage:
    python main.py [--open <file>] [--debug]
"""

from ui import MainWindow
from logic import ProjectLogic
from file_handler import ProjectFileHandler
from PyQt5.QtWidgets import QApplication # type: ignore
import sys
import os
import argparse


def _find_and_configure_jdk():
    """Locate a bundled or nearby JDK and set JAVA_HOME / PATH.

    Search order (bundled first, system as fallback):
      1. <exe_dir>/jdk                    - bundle layout produced by SConstruct
      2. Recursive search from <exe_dir>  - catches jdk-17.0.x+y sub-folders
      3. Recursive search from <src_dir>/../tools/java - dev-tree layout
      4. JAVA_HOME already set / system Java                  - fallback

    A valid JDK root is recognised by the presence of bin/java.exe (Windows)
    or bin/java (Linux/macOS) inside it.
    """
    exe_dir = os.path.dirname(os.path.abspath(sys.executable))
    src_dir = os.path.dirname(os.path.abspath(__file__))
    tools_java = os.path.normpath(os.path.join(src_dir, "..", "tools", "java"))

    def _is_jdk_root(path):
        return (
            os.path.isfile(os.path.join(path, "bin", "java.exe")) or
            os.path.isfile(os.path.join(path, "bin", "java"))
        )

    def _search(root, max_depth=4):
        """Walk *root* up to *max_depth* levels deep; return first JDK found."""
        if not os.path.isdir(root):
            return None
        for dirpath, dirnames, _ in os.walk(root):
            # Limit recursion depth
            depth = dirpath[len(root):].count(os.sep)
            if depth >= max_depth:
                dirnames.clear()
                continue
            if _is_jdk_root(dirpath):
                return dirpath
        return None

    # 1. Fixed bundle path
    candidate = os.path.join(exe_dir, "jdk")
    if _is_jdk_root(candidate):
        jdk_dir = candidate
    else:
        # 2. Recursive search from exe directory
        jdk_dir = _search(exe_dir)

    # 3. Recursive search inside tools/java (dev tree)
    if jdk_dir is None:
        jdk_dir = _search(tools_java)

    if jdk_dir is None:
        # 4. Fall back to system Java (JAVA_HOME already set or on PATH)
        print("Using system Java.")
        return

    os.environ["JAVA_HOME"] = jdk_dir

    jdk_bin    = os.path.join(jdk_dir, "bin")
    jdk_server = os.path.join(jdk_dir, "bin", "server")
    path_parts = [jdk_server, jdk_bin] + os.environ.get("PATH", "").split(os.pathsep)
    os.environ["PATH"] = os.pathsep.join(path_parts)


def _find_and_configure_git():
    """Add bundled Git to PATH (preferred); fall back to system Git."""
    import shutil as _shutil

    exe_dir = os.path.dirname(os.path.abspath(sys.executable))
    src_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(exe_dir, "git", "cmd"),
        os.path.normpath(os.path.join(src_dir, "..", "tools", "git", "cmd")),
    ]
    for candidate in candidates:
        if os.path.isfile(os.path.join(candidate, "git.exe")):
            path_parts = [candidate] + os.environ.get("PATH", "").split(os.pathsep)
            os.environ["PATH"] = os.pathsep.join(path_parts)
            return

    # Fall back to system Git
    if _shutil.which("git.exe"):
        print("Using system Git.")
        return


def _find_and_configure_svn():
    """Add bundled SVN to PATH (preferred); fall back to system SVN."""
    import shutil as _shutil

    exe_dir = os.path.dirname(os.path.abspath(sys.executable))
    src_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(exe_dir, "svn"),
        os.path.normpath(os.path.join(src_dir, "..", "tools", "svn")),
    ]
    for candidate in candidates:
        if os.path.isfile(os.path.join(candidate, "svn.exe")):
            path_parts = [candidate] + os.environ.get("PATH", "").split(os.pathsep)
            os.environ["PATH"] = os.pathsep.join(path_parts)
            return

    # Fall back to system SVN
    if _shutil.which("svn.exe"):
        print("Using system SVN.")
        return


# Main entry point for the Qt5 Project Offline app
def main():
    parser = argparse.ArgumentParser(description="Project Offline")
    parser.add_argument('--open', type=str, help='Path to a Microsoft Project file to open at startup')
    parser.add_argument('--debug', '-v', action='store_true', help='Enable verbose debug output')
    args = parser.parse_args()

    if args.debug:
        from app_debug import set_debug  # type: ignore
        set_debug(True)

    _find_and_configure_jdk()
    _find_and_configure_git()
    _find_and_configure_svn()

    app = QApplication(sys.argv)
    logic = ProjectLogic()
    file_handler = ProjectFileHandler(logic)
    window = MainWindow(logic, file_handler)

    if args.open:
        window.open_project_file(args.open)

    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
