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
    if not "%TAHP_SILENT%"=="1" pause
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
    if not "%TAHP_SILENT%"=="1" pause
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
    if not "%TAHP_SILENT%"=="1" pause
    exit /b 1
)

echo [EasyAdapter] 运行环境检查通过
echo.

node scripts/npm-install-if-needed.mjs
if errorlevel 1 (
    echo [EasyAdapter] npm install 失败
    if not "%TAHP_SILENT%"=="1" pause
    exit /b 1
)

echo.
echo [EasyAdapter] 检查 Hermes Agent 环境（智能诊断 / 适配调试必需）...
if "%TAHP_SILENT%"=="1" (
    node scripts/ensure-hermes-agent.mjs
) else (
    call npm run setup:agent
)
if errorlevel 1 (
    echo.
    echo [EasyAdapter] Agent 环境未就绪，无法启动。
    echo   请安装 Python 3.11+ 后重试，或在 .env 中设置:
    echo   TAHP_PYTHON=C:\Path\To\Python312\python.exe
    echo   然后执行: npm run setup:agent -- --force
    echo.
    if not "%TAHP_SILENT%"=="1" pause
    exit /b 1
)

echo [EasyAdapter] 检查 Skill Python 依赖（tones-scmp 等）...
call npm run setup:skills
if errorlevel 1 (
    echo.
    echo [EasyAdapter] Skill 依赖安装失败，特性适配 SCMP 查询可能不可用。
    echo   可稍后手动执行: npm run setup:skills
    echo.
)

echo.
echo ========================================
echo   EasyAdapter Console 后台模式
echo ========================================
echo   启动顺序: 构建检查 -^> 停止旧进程 -^> 后台守护 8650 -^> 系统托盘 -^> 打开浏览器
echo   服务在后台运行，关闭本窗口不会影响使用
echo   日常使用: 任务栏托盘图标 EA 右键菜单
echo     打开控制台 / 重启 / 更新并重启 / 停止 / 查看日志
echo   配置 API Key: 系统 - 模型管理
echo ========================================
echo.

node scripts/build-if-needed.mjs
if errorlevel 1 (
    echo.
    echo [EasyAdapter] 生产构建失败，无法启动。
    echo   首次拉代码需在本地编译前端，含 Monaco，内存占用较高。
    echo   建议: 关闭其它占内存程序后重试，或手动执行:
    echo   set NODE_OPTIONS=--max-old-space-size=8192
    echo   cd tahp-console
    echo   npm run build
    echo   若仍失败，请向已构建成功的同事复制 tahp-console\dist 目录。
    echo.
    if not "%TAHP_SILENT%"=="1" pause
    exit /b 1
)

node bin\tahp-console.mjs stop >nul 2>&1

node scripts/migrate-dev-data.mjs

set TAHP_OPEN_BROWSER=0
node bin\tahp-console.mjs start
if errorlevel 1 (
    echo.
    echo [EasyAdapter] 后台启动失败。可尝试:
    echo   cd tahp-console ^&^& npm run build
    echo   cd tahp-console ^&^& npm run setup:agent -- --force
    echo   或查看日志: %%USERPROFILE%%\.tahp-console\server.log
    echo.
    if not "%TAHP_SILENT%"=="1" pause
    exit /b 1
)

echo.
if "%TAHP_SILENT%"=="1" (
    echo [EasyAdapter] 已在后台启动。
) else (
    echo [EasyAdapter] 已在后台启动，即将打开浏览器，本窗口即将关闭。
)
set TAHP_TRAY_RESTART=1
node scripts\lib\tray-launcher.mjs
if errorlevel 1 (
    echo.
    echo [EasyAdapter] 托盘启动失败，服务仍在运行。
    echo   日志: %%USERPROFILE%%\.tahp-console\tray.log
    echo   可尝试: cd tahp-console ^&^& npm install ^&^& node scripts\lib\tray-launcher.mjs
    echo.
    if not "%TAHP_SILENT%"=="1" pause
)
if not "%TAHP_SILENT%"=="1" (
    start "" "http://localhost:8650/#/tahp/dashboard"
)
if "%TAHP_SILENT%"=="1" exit /b 0
timeout /t 3 /nobreak >nul
