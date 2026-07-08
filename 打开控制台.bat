@echo off
chcp 65001 >nul

echo.
echo [EasyAdapter] 正在打开控制台页面...
start "" "http://localhost:8650/#/tahp/dashboard"
timeout /t 2 /nobreak >nul
