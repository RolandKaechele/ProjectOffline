@echo off

REM =============================================
REM Python + MPXJ Project Launcher
REM ---------------------------------------------
REM - Sets up and activates a Python virtual environment
REM - Installs dependencies from requirements.txt if present
REM - Ensures OpenJDK are present (downloads if needed)
REM - Dynamically detects and sets JAVA_HOME to the correct portable JDK
REM - Updates PATH to use the detected JDK
REM - Displays cli.txt if present
REM - Activates the virtual environment
REM Usage: Double-click, run from command line, or use cli.lnk
REM =============================================

REM Enable delayed variable expansion for use inside loops/blocks
setlocal enabledelayedexpansion

REM --- Virtual Environment Setup ---
REM Define the path to the virtual environment directory (relative to script location)
set VENV_DIR=%~dp0venv

if exist "%VENV_DIR%" (
    echo Virtual environment already exists at %VENV_DIR%
    goto :venvready
)

REM Venv does not exist - detect which Python to use
set "PYTHON_EXE="

if exist "%~dp0temp\Python312\python.exe" (
    set "PYTHON_EXE=%~dp0temp\Python312\python.exe"
    echo Using portable Python from temp\Python312
    goto :pythonready
)

REM Look for a Python installer (Python*.exe) in .\temp\
for %%F in ("%~dp0temp\Python*.exe") do (
    set "PYTHON_INSTALLER=%%F"
    goto :foundinstaller
)
goto :pythonready

:foundinstaller
echo Extracting Python from !PYTHON_INSTALLER! to temp\Python312 ...
"!PYTHON_INSTALLER!" -o"%~dp0temp\Python312" -y
if exist "%~dp0temp\Python312\python.exe" (
    set "PYTHON_EXE=%~dp0temp\Python312\python.exe"
    echo Python extracted successfully.
) else (
    echo ERROR: Python extraction failed!
    exit /b 1
)

:pythonready
if not defined PYTHON_EXE (
    set "PYTHON_EXE=python"
    echo Using system Python.
)

echo Creating virtual environment at %VENV_DIR% ...
"!PYTHON_EXE!" -m venv "%VENV_DIR%"

:venvready

REM Upgrade pip in the virtual environment
"%VENV_DIR%\Scripts\python.exe" -m pip install --upgrade pip

REM Install dependencies from requirements.txt if present (skip if unchanged)
if exist "%~dp0requirements.txt" (
    set "REQ_FILE=%~dp0requirements.txt"
    set "HASH_FILE=%VENV_DIR%\.requirements.hash"
    set "CUR_HASH="

    REM Compute current SHA256 hash of requirements.txt (skip certutil header/footer lines)
    for /f "skip=1 tokens=*" %%H in ('certutil -hashfile "!REQ_FILE!" SHA256 2^>nul') do (
        if not defined CUR_HASH set "CUR_HASH=%%H"
    )
    REM Normalize: strip stray spaces to prevent false mismatches
    if defined CUR_HASH set "CUR_HASH=!CUR_HASH: =!"

    set "OLD_HASH="
    if exist "!HASH_FILE!" (
        set /p OLD_HASH=<"!HASH_FILE!"
        if defined OLD_HASH set "OLD_HASH=!OLD_HASH: =!"
    )

    REM Determine whether install is needed
    set "DO_INSTALL=1"
    if defined CUR_HASH (
        if /i "!CUR_HASH!" == "!OLD_HASH!" (
            set "DO_INSTALL="
            echo Requirements are up to date, skipping pip install.
        )
    ) else (
        echo WARNING: Could not compute requirements hash ^(certutil unavailable^) - forcing install.
    )

    if defined DO_INSTALL (
        echo Installing requirements from requirements.txt ...
        "%VENV_DIR%\Scripts\python.exe" -m pip install -r "!REQ_FILE!"
        if !errorlevel! neq 0 (
            echo WARNING: pip install encountered errors. Requirements hash not updated.
        ) else (
            if defined CUR_HASH echo !CUR_HASH!>"!HASH_FILE!"
        )
    )
    set "DO_INSTALL="
)

REM Install Playwright Chromium browser if not already present
"%VENV_DIR%\Scripts\python.exe" -c "from playwright.sync_api import sync_playwright; pw=sync_playwright().start(); b=pw.chromium.executable_path; pw.stop(); exit(0 if __import__('os').path.exists(b) else 1)" >nul 2>&1
if errorlevel 1 (
    echo Installing Playwright Chromium browser ...
    "%VENV_DIR%\Scripts\playwright.exe" install chromium
) else (
    echo Playwright Chromium already installed.
)

REM --- OpenJDK Detection and Setup ---
REM Search all subdirectories in tools\java for a valid JDK (java.exe)
set "JAVACHECK="
set "JAVA_HOME="
for /d %%D in ("%~dp0tools\java\*") do (
    if exist "%%D\bin\java.exe" (
        set "JAVACHECK=%%D\bin\java.exe"
        set "JAVA_HOME=%%D"
        goto :afterjavaloop
    )
)
:afterjavaloop
if not defined JAVA_HOME (
    echo Downloading and extracting OpenJDK ...
    "%VENV_DIR%\Scripts\python.exe" "%~dp0tools\download_openjdk.py"
    REM After download, set JAVA_HOME to the new JDK folder
    for /d %%D in ("%~dp0tools\java\*") do (
        if exist "%%D\bin\java.exe" (
            set "JAVA_HOME=%%D"
            goto :aftersetjdk
        )
    )
    :aftersetjdk
    if not defined JAVA_HOME (
        echo ERROR: Could not find JDK after download!
        exit /b 1
    )
) else (
    echo OpenJDK already present in tools\java
)
REM Update PATH to use the detected JDK
set "PATH=%JAVA_HOME%\bin;%PATH%"

REM --- Git for Windows (MinGit portable) ---
if exist "%~dp0tools\git\cmd\git.exe" (
    echo Git already present in tools\git
) else (
    echo Downloading Git for Windows ...
    "%VENV_DIR%\Scripts\python.exe" "%~dp0tools\download_git_for_windows.py"
)

REM --- TortoiseSVN command-line binaries ---
if exist "%~dp0tools\svn\svn.exe" (
    echo SVN already present in tools\svn
) else (
    echo Copying TortoiseSVN binaries to tools\svn ...
    "%VENV_DIR%\Scripts\python.exe" "%~dp0tools\copy_tortoisesvn_bin.py"
)

REM --- Inno Setup (ISCC portable install) ---
if exist "%~dp0tools\innosetup\ISCC.exe" (
    echo Inno Setup already present in tools\innosetup
) else (
    echo Downloading Inno Setup ...
    "%VENV_DIR%\Scripts\python.exe" "%~dp0tools\download_innosetup.py"
)

REM Display contents of cli.txt if present
if exist "%~dp0cli.txt" (
    type "%~dp0cli.txt"
)

REM Activate the virtual environment and keep the shell open
cmd /K "call "!VENV_DIR!\Scripts\activate.bat" && python "%~dp0src\main.py" -h"