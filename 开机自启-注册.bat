@echo off
chcp 65001 >nul
set "REPO_ROOT=%~dp0"
set "VBS=%REPO_ROOT%tahp-console\scripts\win\autostart.vbs"

if not exist "%VBS%" (
    echo [EasyAdapter] 未找到自启脚本: %VBS%
    pause
    exit /b 1
)

echo.
echo [EasyAdapter] 注册开机自启（登录后静默后台启动）...
echo   任务名称: EasyAdapterConsole
echo   启动脚本: %VBS%
echo.

schtasks /create /tn "EasyAdapterConsole" /sc onlogon /tr "wscript.exe \"%VBS%\"" /f
if errorlevel 1 (
    echo [EasyAdapter] 注册失败，请尝试右键「以管理员身份运行」本脚本。
    pause
    exit /b 1
)

echo [EasyAdapter] 开机自启已注册。下次登录后将自动在后台启动服务。
echo   取消自启: 双击「开机自启-取消.bat」
echo.
pause
