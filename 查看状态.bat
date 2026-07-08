@echo off
chcp 65001 >nul
set "REPO_ROOT=%~dp0"
cd /d "%REPO_ROOT%tahp-console"

where node >nul 2>&1
if errorlevel 1 (
    echo [EasyAdapter] 未检测到 Node.js。
    pause
    exit /b 1
)

echo.
node bin\tahp-console.mjs status
echo.
echo   日志: %USERPROFILE%\.tahp-console\server.log
echo.
pause
