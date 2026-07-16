@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM GKI Patch Tool - Windows one-click launcher (Standalone mode)
REM
REM Standalone: run this script directly; default http://127.0.0.1:8000/app/
REM Integrated: started by EasyAdapter / tahp-console; do not run this script
REM   See EA_INTEGRATION.md
REM
REM Usage:
REM   run_gki-patch-tool.bat              install + build + start (default)
REM   run_gki-patch-tool.bat install      install/update deps and build frontend only
REM   run_gki-patch-tool.bat start        same as default
REM   run_gki-patch-tool.bat foreground   start server in foreground (debug)
REM   run_gki-patch-tool.bat fg           alias of foreground
REM   run_gki-patch-tool.bat help         show help
REM
REM Optional env vars:
REM   GKI_HOST, GKI_PORT, GKI_VENV, GKI_WORKERS, GKI_SETTINGS

set "PROJECT_ROOT=%~dp0"
if "%PROJECT_ROOT:~-1%"=="\" set "PROJECT_ROOT=%PROJECT_ROOT:~0,-1%"
cd /d "%PROJECT_ROOT%"

if not defined GKI_VENV set "GKI_VENV=%PROJECT_ROOT%\.venv"
if not defined GKI_HOST set "GKI_HOST=0.0.0.0"
if not defined GKI_PORT set "GKI_PORT=8000"
if not defined GKI_WORKERS set "GKI_WORKERS=1"
if not defined GKI_SETTINGS set "GKI_SETTINGS=%PROJECT_ROOT%\gki-patch-tool.yaml"

set "VENV_DIR=%GKI_VENV%"
set "PY=%VENV_DIR%\Scripts\python.exe"
set "RUN_DIR=%PROJECT_ROOT%\.run"
set "FRONTEND_DIR=%PROJECT_ROOT%\frontend"
set "FRONTEND_DIST=%FRONTEND_DIR%\dist\index.html"
set "EXIT_CODE=0"
set "GKI_PORT_REQUESTED=%GKI_PORT%"

set "CMD=%~1"
if "%CMD%"=="" set "CMD=start"
if /I "%CMD%"=="help" goto :show_help
if /I "%CMD%"=="-h" goto :show_help
if /I "%CMD%"=="--help" goto :show_help

call :require_system_tools
if errorlevel 1 goto :fail_pause

call :ensure_run_dir
if errorlevel 1 goto :fail_pause

if /I "%CMD%"=="install" (
  call :ensure_python_env
  if errorlevel 1 goto :fail_pause
  call :ensure_frontend_env
  if errorlevel 1 goto :fail_pause
  call :build_frontend
  if errorlevel 1 goto :fail_pause
  call :print_config_hint
  echo [INFO] install completed.
  goto :done_pause
)

if /I "%CMD%"=="start" goto :do_start
if /I "%CMD%"=="foreground" goto :do_foreground
if /I "%CMD%"=="fg" goto :do_foreground

echo [ERROR] Unknown command: %CMD%
goto :show_help

:do_start
call :ensure_python_env
if errorlevel 1 goto :fail_pause
call :ensure_frontend_env
if errorlevel 1 goto :fail_pause
call :build_frontend
if errorlevel 1 goto :fail_pause
call :check_preflight
if errorlevel 1 goto :fail_pause
call :ensure_free_port
if errorlevel 1 goto :fail_pause
call :print_config_hint
call :open_browser
goto :do_foreground

:do_foreground
call :check_preflight
if errorlevel 1 goto :fail_pause
if not defined PORT_RESOLVED (
  call :ensure_free_port
  if errorlevel 1 goto :fail_pause
)

echo [INFO] Starting web server: http://127.0.0.1:%GKI_PORT%/app/
echo [INFO] Press Ctrl+C to stop the server.
echo.

"%PY%" -m uvicorn web_app.app:app --host %GKI_HOST% --port %GKI_PORT% --workers %GKI_WORKERS% --log-level info
set "EXIT_CODE=!ERRORLEVEL!"

echo.
if not "!EXIT_CODE!"=="0" (
  echo [ERROR] Server failed to start or exited abnormally. Exit code: !EXIT_CODE!
  echo         Common causes:
  echo           - Port %GKI_PORT% is already in use
  echo           - Python dependencies are missing or broken
  echo           - Invalid config in %GKI_SETTINGS%
  echo         See error output above for details.
) else (
  echo [INFO] Server stopped.
)
goto :done_pause

:require_system_tools
call :require_cmd python "Install Python 3.10+ from https://www.python.org/downloads/ and enable 'Add to PATH'."
if errorlevel 1 exit /b 1
call :require_cmd git "Install Git from https://git-scm.com/download/win"
if errorlevel 1 exit /b 1
call :require_cmd node "Install Node.js LTS from https://nodejs.org/"
if errorlevel 1 exit /b 1
call :require_cmd npm "npm should come with Node.js; reinstall Node.js if missing."
exit /b 0

:require_cmd
where %~1 >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Missing command: %~1
  echo         %~2
  exit /b 1
)
exit /b 0

:ensure_run_dir
if not exist "%RUN_DIR%" mkdir "%RUN_DIR%"
if not exist "%PROJECT_ROOT%\outputs" mkdir "%PROJECT_ROOT%\outputs"
exit /b 0

:ensure_python_env
if not exist "%VENV_DIR%\Scripts\python.exe" (
  echo [INFO] Creating virtual environment: %VENV_DIR%
  python -m venv "%VENV_DIR%"
  if errorlevel 1 (
    echo [ERROR] Failed to create virtual environment.
    exit /b 1
  )
)

call :python_deps_ok
if errorlevel 1 (
  echo [INFO] Installing/updating Python dependencies...
  "%PY%" -m pip install --upgrade pip
  if errorlevel 1 (
    echo [ERROR] Failed to upgrade pip.
    exit /b 1
  )
  "%PY%" -m pip install -r "%PROJECT_ROOT%\requirements.txt"
  if errorlevel 1 (
    echo [ERROR] pip install failed.
    exit /b 1
  )
  call :python_deps_ok
  if errorlevel 1 (
    echo [ERROR] Python dependency verification failed.
    exit /b 1
  )
) else (
  echo [INFO] Python dependencies OK, skipping pip install.
)
"%PY%" --version
exit /b 0

:python_deps_ok
"%PY%" -c "import fastapi, uvicorn, yaml, httpx, paramiko, openpyxl" >nul 2>&1
exit /b %ERRORLEVEL%

:ensure_frontend_env
if not exist "%FRONTEND_DIR%\package.json" (
  echo [ERROR] Missing frontend\package.json
  exit /b 1
)
if not exist "%FRONTEND_DIR%\node_modules" (
  echo [INFO] Installing frontend dependencies...
  pushd "%FRONTEND_DIR%"
  call npm install
  set "NPM_ERR=!ERRORLEVEL!"
  popd
  if not "!NPM_ERR!"=="0" (
    echo [ERROR] npm install failed.
    exit /b 1
  )
) else (
  echo [INFO] Frontend node_modules OK, skipping npm install.
)
exit /b 0

:build_frontend
echo [INFO] Building frontend...
pushd "%FRONTEND_DIR%"
call npm run build
set "BUILD_ERR=!ERRORLEVEL!"
popd
if not "!BUILD_ERR!"=="0" (
  echo [ERROR] npm run build failed.
  exit /b 1
)
if not exist "%FRONTEND_DIST%" (
  echo [ERROR] Frontend build output missing: %FRONTEND_DIST%
  exit /b 1
)
echo [INFO] Frontend build OK.
exit /b 0

:check_preflight
if not exist "%PY%" (
  echo [ERROR] Python venv not ready. Run: %~nx0 install
  exit /b 1
)
if not exist "%FRONTEND_DIST%" (
  echo [ERROR] Frontend dist not found. Run: %~nx0 install
  exit /b 1
)
set "PYTHONPATH=%PROJECT_ROOT%;%PROJECT_ROOT%\tools"
set "GKI_SETTINGS=%GKI_SETTINGS%"
cd /d "%PROJECT_ROOT%"
exit /b 0

:print_config_hint
echo.
echo [INFO] Config:
echo   Settings: %GKI_SETTINGS%
echo   Port: %GKI_PORT%
if not "%GKI_PORT%"=="%GKI_PORT_REQUESTED%" (
  echo   Requested port %GKI_PORT_REQUESTED% was busy, using %GKI_PORT% instead.
)
if exist "%GKI_SETTINGS%" (
  echo   Found gki-patch-tool.yaml
) else (
  echo [WARN] gki-patch-tool.yaml not found, using defaults.
)
echo   Project: %PROJECT_ROOT%
echo.
exit /b 0

:open_browser
start "" "http://127.0.0.1:%GKI_PORT%/app/"
exit /b 0

:ensure_free_port
if defined PORT_RESOLVED exit /b 0
set "GKI_PORT_REQUESTED=%GKI_PORT%"
:ensure_free_port_loop
call :is_port_in_use
if errorlevel 1 goto :ensure_free_port_done
echo [WARN] Port %GKI_PORT% is already in use.
set /a GKI_PORT+=1
if !GKI_PORT! GTR 8100 (
  echo [ERROR] Could not find a free port between %GKI_PORT_REQUESTED% and 8100.
  exit /b 1
)
goto :ensure_free_port_loop

:ensure_free_port_done
if not "%GKI_PORT%"=="%GKI_PORT_REQUESTED%" (
  echo [INFO] Automatically switched to port %GKI_PORT%.
  echo        Access: http://127.0.0.1:%GKI_PORT%/app/
) else (
  echo [INFO] Port %GKI_PORT% is available.
)
set "PORT_RESOLVED=1"
exit /b 0

:is_port_in_use
netstat -ano | findstr LISTENING | findstr /C:":%GKI_PORT% " >nul 2>&1
if errorlevel 1 exit /b 1
exit /b 0

:fail_pause
set "EXIT_CODE=1"
echo.
echo [ERROR] Startup failed. See error messages above for details.
goto :done_pause

:done_pause
echo.
pause
exit /b %EXIT_CODE%

:show_help
echo GKI Patch Tool - Windows Launcher
echo.
echo Usage:
echo   %~nx0                 install + build + start
echo   %~nx0 install         install/update deps and build frontend only
echo   %~nx0 start           same as default
echo   %~nx0 foreground      start server in foreground
echo   %~nx0 fg              alias of foreground
echo   %~nx0 help            show this help
echo.
echo Optional env vars:
echo   GKI_HOST, GKI_PORT, GKI_VENV, GKI_WORKERS, GKI_SETTINGS
exit /b 0
