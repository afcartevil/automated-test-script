#!/usr/bin/env bash
# GKI Patch Tool - Linux/Ubuntu one-click launcher (Standalone 独立运行模式)
#
# 独立运行：直接执行本脚本，默认 http://127.0.0.1:8000/app/
# 集成运行：通过 EasyAdapter 启动，由 tahp-console 自动拉起，无需执行本脚本
#   详见 EA_INTEGRATION.md
#
# Usage:
#   ./run_linux.sh              install + build + start (default, foreground)
#   ./run_linux.sh install      install/update deps and build frontend only
#   ./run_linux.sh start        same as default
#   ./run_linux.sh foreground   start server in foreground (debug)
#   ./run_linux.sh fg           alias of foreground
#   ./run_linux.sh help         show help
#
# Optional env vars:
#   GKI_HOST, GKI_PORT, GKI_VENV, GKI_WORKERS, GKI_SETTINGS

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$SCRIPT_DIR"
cd "$PROJECT_ROOT"

VENV_DIR="${GKI_VENV:-$PROJECT_ROOT/.venv}"
RUN_DIR="$PROJECT_ROOT/.run"
FRONTEND_DIR="$PROJECT_ROOT/frontend"
FRONTEND_DIST="$FRONTEND_DIR/dist/index.html"
HOST="${GKI_HOST:-0.0.0.0}"
PORT="${GKI_PORT:-8000}"
GKI_PORT_REQUESTED="$PORT"
WORKERS="${GKI_WORKERS:-1}"
SETTINGS="${GKI_SETTINGS:-$PROJECT_ROOT/gki-patch-tool.yaml}"
EXIT_CODE=0
PORT_RESOLVED=""

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    error "Missing command: $1"
    echo "         $2" >&2
    return 1
  fi
}

require_system_tools() {
  require_cmd python3 "Install Python 3.10+ (Ubuntu: sudo apt install python3 python3-venv python3-pip)" &&
  require_cmd git "Install Git (Ubuntu: sudo apt install git)" &&
  require_cmd node "Install Node.js LTS (Ubuntu: sudo apt install nodejs npm, or use NodeSource/nvm)" &&
  require_cmd npm "npm should come with Node.js; reinstall Node.js if missing."
}

python_bin() {
  if [[ -x "$VENV_DIR/bin/python" ]]; then
    echo "$VENV_DIR/bin/python"
  else
    echo "python3"
  fi
}

ensure_run_dir() {
  mkdir -p "$RUN_DIR" "$PROJECT_ROOT/outputs"
}

python_deps_ok() {
  local py
  py="$(python_bin)"
  "$py" -c "import fastapi, uvicorn, yaml, httpx, paramiko, openpyxl" >/dev/null 2>&1
}

ensure_python_env() {
  if [[ ! -x "$VENV_DIR/bin/python" ]]; then
    info "Creating virtual environment: $VENV_DIR"
    python3 -m venv "$VENV_DIR" || return 1
  fi

  local py
  py="$(python_bin)"

  if python_deps_ok; then
    info "Python dependencies OK, skipping pip install."
  else
    info "Installing/updating Python dependencies..."
    "$py" -m pip install --upgrade pip || return 1
    "$py" -m pip install -r "$PROJECT_ROOT/requirements.txt" || return 1
    python_deps_ok || {
      error "Python dependency verification failed."
      return 1
    }
  fi

  "$py" --version
}

ensure_frontend_env() {
  if [[ ! -f "$FRONTEND_DIR/package.json" ]]; then
    error "Missing frontend/package.json"
    return 1
  fi

  if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
    info "Installing frontend dependencies..."
    (cd "$FRONTEND_DIR" && npm install) || return 1
  else
    info "Frontend node_modules OK, skipping npm install."
  fi
}

build_frontend() {
  info "Building frontend..."
  (cd "$FRONTEND_DIR" && npm run build) || return 1
  if [[ ! -f "$FRONTEND_DIST" ]]; then
    error "Frontend build output missing: $FRONTEND_DIST"
    return 1
  fi
  info "Frontend build OK."
}

check_preflight() {
  local py
  py="$(python_bin)"
  if [[ ! -x "$py" ]]; then
    error "Python venv not ready. Run: $0 install"
    return 1
  fi
  if [[ ! -f "$FRONTEND_DIST" ]]; then
    error "Frontend dist not found. Run: $0 install"
    return 1
  fi
  export PYTHONPATH="$PROJECT_ROOT:$PROJECT_ROOT/tools${PYTHONPATH:+:$PYTHONPATH}"
  export GKI_SETTINGS="$SETTINGS"
  cd "$PROJECT_ROOT"
}

is_port_in_use() {
  local port=$1
  if command -v ss >/dev/null 2>&1; then
    ss -ltn 2>/dev/null | grep -qE ":${port}( |$)"
    return $?
  fi
  if command -v netstat >/dev/null 2>&1; then
    netstat -ltn 2>/dev/null | grep -qE ":${port}( |$)"
    return $?
  fi
  (echo >/dev/tcp/127.0.0.1/"$port") >/dev/null 2>&1
}

ensure_free_port() {
  if [[ -n "$PORT_RESOLVED" ]]; then
    return 0
  fi

  GKI_PORT_REQUESTED="$PORT"
  while is_port_in_use "$PORT"; do
    warn "Port $PORT is already in use."
    PORT=$((PORT + 1))
    if (( PORT > 8100 )); then
      error "Could not find a free port between $GKI_PORT_REQUESTED and 8100."
      return 1
    fi
  done

  if [[ "$PORT" != "$GKI_PORT_REQUESTED" ]]; then
    info "Automatically switched to port $PORT."
    info "Access: http://127.0.0.1:${PORT}/app/"
  else
    info "Port $PORT is available."
  fi
  export GKI_PORT="$PORT"
  PORT_RESOLVED=1
}

print_config_hint() {
  echo
  info "Config:"
  echo "  Settings: $SETTINGS"
  echo "  Port: $PORT"
  if [[ "$PORT" != "$GKI_PORT_REQUESTED" ]]; then
    echo "  Requested port $GKI_PORT_REQUESTED was busy, using $PORT instead."
  fi
  if [[ -f "$SETTINGS" ]]; then
    echo "  Found gki-patch-tool.yaml"
  else
    warn "gki-patch-tool.yaml not found, using defaults."
  fi
  echo "  Project: $PROJECT_ROOT"
  echo
}

open_browser() {
  local url="http://127.0.0.1:${PORT}/app/"
  if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$url" >/dev/null 2>&1 || true
  elif command -v sensible-browser >/dev/null 2>&1; then
    sensible-browser "$url" >/dev/null 2>&1 || true
  else
    info "Open in browser: $url"
  fi
}

do_install() {
  ensure_run_dir || return 1
  ensure_python_env || return 1
  ensure_frontend_env || return 1
  build_frontend || return 1
  print_config_hint
  info "install completed."
}

do_start() {
  ensure_run_dir || return 1
  ensure_python_env || return 1
  ensure_frontend_env || return 1
  build_frontend || return 1
  check_preflight || return 1
  ensure_free_port || return 1
  print_config_hint
  open_browser
  do_foreground
}

do_foreground() {
  check_preflight || return 1
  if [[ -z "$PORT_RESOLVED" ]]; then
    ensure_free_port || return 1
  fi

  info "Starting web server: http://127.0.0.1:${PORT}/app/"
  info "Press Ctrl+C to stop the server."
  echo

  local py
  py="$(python_bin)"
  "$py" -m uvicorn web_app.app:app \
    --host "$HOST" \
    --port "$PORT" \
    --workers "$WORKERS" \
    --log-level info
  EXIT_CODE=$?

  echo
  if (( EXIT_CODE != 0 )); then
    error "Server failed to start or exited abnormally. Exit code: $EXIT_CODE"
    echo "         Common causes:" >&2
    echo "           - Port $PORT is already in use" >&2
    echo "           - Python dependencies are missing or broken" >&2
    echo "           - Invalid config in $SETTINGS" >&2
    echo "         See error output above for details." >&2
    return "$EXIT_CODE"
  fi

  info "Server stopped."
  return 0
}

fail_pause() {
  EXIT_CODE=1
  echo
  error "Startup failed. See error messages above for details."
  done_pause
}

done_pause() {
  echo
  if [[ -t 0 ]]; then
    read -r -p "Press Enter to continue..."
  fi
  exit "$EXIT_CODE"
}

usage() {
  sed -n '2,14p' "$0" | sed 's/^# \?//'
}

CMD="${1:-start}"

case "$CMD" in
  install)
    require_system_tools || fail_pause
    do_install || fail_pause
    done_pause
    ;;
  start)
    require_system_tools || fail_pause
    do_start || fail_pause
    done_pause
    ;;
  foreground|fg)
    require_system_tools || fail_pause
    do_foreground || fail_pause
    done_pause
    ;;
  help|-h|--help)
    usage
    exit 0
    ;;
  *)
    error "Unknown command: $CMD"
    usage
    exit 1
    ;;
esac
