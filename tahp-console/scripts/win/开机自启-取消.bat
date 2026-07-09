@echo off
chcp 65001 >nul

echo.
echo [EasyAdapter] 取消开机自启...
echo.

schtasks /delete /tn "EasyAdapterConsole" /f
if errorlevel 1 (
    echo [EasyAdapter] 未找到已注册的任务，或删除失败。
    pause
    exit /b 1
)

echo [EasyAdapter] 开机自启已取消。
echo.
pause
