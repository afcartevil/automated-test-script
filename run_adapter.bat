@echo off
chcp 65001 >nul
set "REPO_ROOT=%~dp0"
cd /d "%REPO_ROOT%"

where node >nul 2>&1
if errorlevel 1 (
    echo [EasyAdapter] 未检测到 Node.js，无法启动。
    echo   需要 Node.js 22.5 或更高版本 ^(内置 SQLite 依赖 node:sqlite^)
    echo   下载: https://nodejs.org/
    echo   安装后请关闭并重新打开终端，再双击本脚本。
    echo.
    pause
    exit /b 1
)

echo.
echo [EasyAdapter] 检查代码更新...
node tahp-console\scripts\git-pull-safe.mjs

cd /d "%REPO_ROOT%tahp-console"

echo.
echo [EasyAdapter] 检查运行环境（Node.js + Python）...
echo.

node scripts/preflight-env.mjs
if errorlevel 1 (
    echo.
    pause
    exit /b 1
)

echo [EasyAdapter] 检测 Git Bash（Hermes 终端工具必需）...
node scripts/ensure-git-bash-env.mjs
if errorlevel 1 (
    echo.
    echo [EasyAdapter] 未找到 Git Bash，Agent 终端功能将不可用。
    echo   请安装 Git for Windows: https://git-scm.com/download/win
    echo   或在 tahp-console\.env 中设置:
    echo   HERMES_GIT_BASH_PATH=你的安装路径\bin\bash.exe
    echo.
    pause
    exit /b 1
)

echo [EasyAdapter] 运行环境检查通过
echo.

node scripts/npm-install-if-needed.mjs
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
set TAHP_SKIP_PREDEV_AGENT=1
set TAHP_AGENT_SKIP_IMPORT_VERIFY=1
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
