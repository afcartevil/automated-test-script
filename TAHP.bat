@echo off
chcp 65001 >nul
cd /d "%~dp0tahp-console"
if not exist node_modules (
    echo Installing dependencies...
    call npm install
)
echo.
echo [TAHP] 启动中… 首次运行会在本窗口打印配置提示（不阻塞）
echo [TAHP] 请在浏览器打开后进入: 系统 - 模型管理 - 配置 API Key
echo.
start http://localhost:5173
call npm run dev
if errorlevel 1 (
  echo.
  echo [TAHP] 启动失败。若 Agent 安装报错，可删除 hermes-agent-main\.venv 后重试，或执行:
  echo        cd tahp-console ^&^& npm run setup:agent -- --force
  echo.
)
pause
