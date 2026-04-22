#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
BACKEND_VENV="$BACKEND_DIR/.venv"
SKIP_INSTALL=false

usage() {
  cat <<'EOF'
用法:
  ./start.sh [--skip-install]

参数:
  --skip-install   跳过前后端依赖安装，直接启动
  -h, --help       显示帮助
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --skip-install)
      SKIP_INSTALL=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "错误: 未知参数 $1"
      usage
      exit 1
      ;;
  esac
done

if ! command -v python3 >/dev/null 2>&1; then
  echo "错误: 未找到 python3，请先安装 Python 3.11+"
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "错误: 未找到 npm，请先安装 Node.js (含 npm)"
  exit 1
fi

if [[ ! -d "$BACKEND_DIR" || ! -d "$FRONTEND_DIR" ]]; then
  echo "错误: 请在 readagent 项目根目录运行此脚本"
  exit 1
fi

if [[ "$SKIP_INSTALL" == "false" ]]; then
  if [[ ! -d "$BACKEND_VENV" ]]; then
    echo ">> 创建后端虚拟环境..."
    python3 -m venv "$BACKEND_VENV"
  fi

  if [[ ! -f "$BACKEND_VENV/bin/activate" ]]; then
    echo "错误: 后端虚拟环境不完整，请删除 backend/.venv 后重试"
    exit 1
  fi

  echo ">> 安装/更新后端依赖..."
  source "$BACKEND_VENV/bin/activate"
  python -m pip install --upgrade pip >/dev/null
  pip install -r "$BACKEND_DIR/requirements.txt"
  deactivate

  if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
    echo ">> 安装前端依赖..."
    (cd "$FRONTEND_DIR" && npm install)
  fi
else
  echo ">> 已启用 --skip-install，跳过依赖安装"

  if [[ ! -f "$BACKEND_VENV/bin/activate" ]]; then
    echo "错误: 未检测到 backend/.venv，请先执行 ./start.sh 完整初始化"
    exit 1
  fi

  if [[ ! -d "$FRONTEND_DIR/node_modules" ]]; then
    echo "错误: 未检测到 frontend/node_modules，请先执行 ./start.sh 完整初始化"
    exit 1
  fi
fi

BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
  local code=$?
  trap - EXIT INT TERM

  if [[ -n "$BACKEND_PID" ]] && kill -0 "$BACKEND_PID" 2>/dev/null; then
    kill "$BACKEND_PID" 2>/dev/null || true
  fi
  if [[ -n "$FRONTEND_PID" ]] && kill -0 "$FRONTEND_PID" 2>/dev/null; then
    kill "$FRONTEND_PID" 2>/dev/null || true
  fi

  wait "$BACKEND_PID" 2>/dev/null || true
  wait "$FRONTEND_PID" 2>/dev/null || true

  exit "$code"
}

trap cleanup EXIT INT TERM

echo ">> 启动后端 (FastAPI): http://127.0.0.1:8000"
(
  cd "$BACKEND_DIR"
  source ".venv/bin/activate"
  uvicorn main:app --reload --host 0.0.0.0 --port 8000
) &
BACKEND_PID=$!

echo ">> 启动前端 (Vite): http://127.0.0.1:5173"
(
  cd "$FRONTEND_DIR"
  npm run dev -- --host 0.0.0.0 --port 5173
) &
FRONTEND_PID=$!

echo "========================================"
echo "ReadAgent 开发环境已启动"
echo "前端: http://127.0.0.1:5173"
echo "后端: http://127.0.0.1:8000"
echo "按 Ctrl+C 可同时关闭前后端"
echo "========================================"

wait -n "$BACKEND_PID" "$FRONTEND_PID"
