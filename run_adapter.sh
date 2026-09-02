#!/usr/bin/env bash
# EasyAdapter Linux 启动脚本，对应工程根目录 run_adapter.bat。
#
# 用法:
#   ./run_adapter.sh
#   bash run_adapter.sh
#   TAHP_SILENT=1 ./run_adapter.sh   # 不打开浏览器、不等待确认
#
# 与 Windows 版的差异:
#   - 不检测 Git Bash（Linux 使用系统 bash）
#   - 不启动系统托盘（托盘仅 Windows）
#   - 用 xdg-open 打开浏览器

set -o pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

CONSOLE_URL="http://localhost:8650/#/tahp/dashboard"
LOG_HINT="${HOME}/.tahp-console/server.log"

pause_on_error() {
  if [[ "${TAHP_SILENT:-}" != "1" && -t 0 ]]; then
    echo
    read -r -p "按 Enter 键退出..."
  fi
}

die() {
  pause_on_error
  exit 1
}

open_browser() {
  local url="$1"
  if [[ -z "${DISPLAY:-}" && -z "${WAYLAND_DISPLAY:-}" ]]; then
    echo "[EasyAdapter] 无图形界面，请手动打开: $url"
    return 0
  fi
  if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$url" >/dev/null 2>&1 || true
    return 0
  fi
  echo "[EasyAdapter] 未找到 xdg-open，请手动打开: $url"
}

if ! command -v node >/dev/null 2>&1; then
  echo
  echo "[EasyAdapter] 未检测到 Node.js，无法启动。"
  echo "  需要 Node.js 22.5 或更高版本 (内置 SQLite 依赖 node:sqlite)"
  echo "  下载: https://nodejs.org/"
  echo "  安装后请重新打开终端，再执行本脚本。"
  echo
  die
fi

echo
echo "[EasyAdapter] 检查代码更新..."
node tahp-console/scripts/git-pull-safe.mjs

cd "$REPO_ROOT/tahp-console"

echo
echo "[EasyAdapter] 检查运行环境(Node.js + Python)..."
echo

if ! node scripts/preflight-env.mjs; then
  die
fi

echo "[EasyAdapter] 运行环境检查通过"
echo

if ! node scripts/npm-install-if-needed.mjs; then
  echo "[EasyAdapter] npm install 失败"
  die
fi

echo
echo "[EasyAdapter] 检查 Hermes Agent 环境(智能诊断 / 适配调试必需)..."
agent_ok=0
if [[ "${TAHP_SILENT:-}" == "1" ]]; then
  node scripts/ensure-hermes-agent.mjs && agent_ok=1
else
  npm run setup:agent && agent_ok=1
fi
if [[ "$agent_ok" != "1" ]]; then
  echo
  echo "[EasyAdapter] Agent 环境未就绪，无法启动。"
  echo "  请安装 Python 3.11-3.13 正式版后重试，推荐 3.12，不要使用 3.14。"
  echo "  或在 tahp-console/.env 中设置:"
  echo "  TAHP_PYTHON=/usr/bin/python3.12"
  echo "  然后执行: npm run setup:agent -- --force"
  echo
  die
fi

echo "[EasyAdapter] 检查 Skill Python 依赖(tones-scmp 等)..."
if ! npm run setup:skills; then
  echo
  echo "[EasyAdapter] Skill 依赖安装失败，特性适配 SCMP 查询可能不可用。"
  echo "  可稍后手动执行: npm run setup:skills"
  echo
fi

echo "[EasyAdapter] 检查 GKI Patch Tool 依赖..."
if ! npm run setup:gki-patch; then
  echo
  echo "[EasyAdapter] GKI Patch 依赖安装失败，GKI Patch 页面可能不可用。"
  echo "  可稍后手动执行: npm run setup:gki-patch"
  echo
fi

node scripts/print-hermes-version.mjs

if ! node scripts/build-if-needed.mjs; then
  echo
  echo "[EasyAdapter] 生产构建失败，无法启动。"
  echo "  首次拉代码需在本地编译前端，含 Monaco，内存占用较高。"
  echo "  建议: 关闭其它占内存程序后重试，或手动执行:"
  echo "  export NODE_OPTIONS=--max-old-space-size=8192"
  echo "  cd tahp-console"
  echo "  npm run build"
  echo "  若仍失败，请向已构建成功的同事复制 tahp-console/dist 目录。"
  echo
  die
fi

node bin/tahp-console.mjs stop >/dev/null 2>&1 || true

node scripts/migrate-dev-data.mjs

export TAHP_OPEN_BROWSER=0
if ! node bin/tahp-console.mjs start; then
  echo
  echo "[EasyAdapter] 后台启动失败。可尝试:"
  echo "  cd tahp-console && npm run build"
  echo "  cd tahp-console && npm run setup:agent -- --force"
  echo "  或查看日志: $LOG_HINT"
  echo
  die
fi

echo
if [[ "${TAHP_SILENT:-}" == "1" ]]; then
  echo "[EasyAdapter] 已在后台启动。"
  exit 0
fi

echo "[EasyAdapter] 已在后台启动，即将打开浏览器。"
echo "  控制台: $CONSOLE_URL"
echo "  日志:   $LOG_HINT"
echo "  停止:   cd tahp-console && node bin/tahp-console.mjs stop"
open_browser "$CONSOLE_URL"
sleep 3
exit 0
