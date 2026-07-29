@echo off
setlocal EnableExtensions EnableDelayedExpansion

set team=dzppt
set scheme=therm
set PYTHON_EXE=
set PYTHON_SOURCE=

cd /d %~dp0
echo @echo off>last_run.bat
echo cd /d %%^~dp0>>last_run.bat
echo %~nx0 %*>>last_run.bat

if exist "..\tpytest-python-embed\python.exe" (
    set "PYTHON_EXE=..\tpytest-python-embed\python.exe"
    set "PYTHON_SOURCE=embed"
) else (
    where python >nul 2>&1
    if not errorlevel 1 (
        set "PYTHON_EXE=python"
        set "PYTHON_SOURCE=system"
        echo [WARN] tpytest-python-embed not found, using system Python.
        echo        Run install-requirements-merged-env.bat if dependencies are missing.
        echo.
    )
)

if not defined PYTHON_EXE (
    echo [ERROR] Python not found.
    echo   - Copy sibling folder: tpytest-python-embed
    echo   - Or install Python 3.11 and run: install-requirements-merged-env.bat
    pause
    exit /b 1
)

echo ========================================
echo   THERM CLI One-Click Test
echo   Python   : !PYTHON_SOURCE!
echo ========================================
echo.

"%PYTHON_EXE%" --version
if errorlevel 1 (
    echo [ERROR] Python cannot run: !PYTHON_EXE!
    pause
    exit /b 1
)

"%PYTHON_EXE%" launchers\%team%\%scheme%\start_%scheme%_cli_python.py %*
set EXIT_CODE=!ERRORLEVEL!

echo.
echo ========================================
if !EXIT_CODE! equ 0 (
    echo   Result: PASS
) else (
    echo   Result: FAIL ^(exit code: !EXIT_CODE!^)
    echo   Common causes:
    echo     1^) No phone connected - run: adb devices
    echo     2^) Test cases failed - check .runtime\log\
    echo     3^) Missing deps - run install-requirements-merged-embed.bat
)
echo ========================================
pause
exit /b !EXIT_CODE!
