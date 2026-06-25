@echo off
chcp 65001 >nul
cd /d "%~dp0tahp-console"

if not exist node_modules (
    echo [EasyAdapter] 首次运行，正在安装 npm 依赖...
) else (
    echo [EasyAdapter] 同步 npm 依赖（拉取新代码后若 package.json 有变更会自动补装）...
)
call npm install
if errorlevel 1 (
    echo [EasyAdapter] npm install 失败
    pause
    exit /b 1
)

echo.
echo [EasyAdapter] 检查 Hermes Agent 环境（智能诊断 / 适配调试必需）...
call npm run setup:agent
if errorlevel 1 (
    echo.
    echo [EasyAdapter] Agent 环境未就绪，无法启动。
    echo   请安装 Python 3.11+ 后重试，或在 .env 中设置:
    echo   TAHP_PYTHON=C:\Path\To\Python312\python.exe
    echo   然后执行: npm run setup:agent -- --force
    echo.
    pause
    exit /b 1
)

echo.
echo ========================================
echo   EasyAdapter Console 开发模式
echo ========================================
echo   启动顺序: Agent 环境 -^> 后端 8650 -^> 健康检查 -^> 前端 5173 -^> 浏览器
echo   终端出现 [dev] 后端已就绪 后再访问页面
echo   重启前请在本窗口按 Ctrl+C 结束上次进程；若仍报 EADDRINUSE 将自动释放 8650/5173
echo   配置 API Key: 系统 - 模型管理
echo ========================================
echo.

set TAHP_OPEN_BROWSER=1
set TAHP_REQUIRE_AGENT=1
set PORT=8650

call npm run dev

if errorlevel 1 (
    echo.
    echo [EasyAdapter] 启动失败。可尝试:
    echo   cd tahp-console ^&^& npm run setup:agent -- --force
    echo   或删除 hermes-agent-main\.venv 后重新双击本脚本
    echo.
)

pause
