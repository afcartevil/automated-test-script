@echo off
chcp 65001 >nul
cd /d "%~dp0tahp-console"

if not exist node_modules (
    echo [TAHP] 正在安装依赖...
    call npm install
    if errorlevel 1 (
        echo [TAHP] npm install 失败
        pause
        exit /b 1
    )
)

echo.
echo ========================================
echo   TAHP Console 开发模式
echo ========================================
echo   启动顺序: 后端 8650 -^> 健康检查 -^> 前端 5173 -^> 浏览器
echo   首次启动会检查 Agent 环境，约需 5-15 秒，终端出现 [dev] 后端已就绪 后再访问页面
echo   重启前请在本窗口按 Ctrl+C 结束上次进程；若仍报 EADDRINUSE 将自动释放 8650/5173
echo   配置 API Key: 系统 - 模型管理
echo ========================================
echo.

set TAHP_OPEN_BROWSER=1
set PORT=8650

call npm run dev

if errorlevel 1 (
    echo.
    echo [TAHP] 启动失败。可尝试:
    echo   cd tahp-console ^&^& npm run setup:agent -- --force
    echo   或删除 hermes-agent-main\.venv 后重新双击本脚本
    echo.
)

pause
