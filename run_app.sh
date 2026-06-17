#!/bin/bash
# ============================================================================
#  中国宏观经济分析平台 — 新架构一键启动（FastAPI :8000 + Vue :5173）
#  Vue 为默认前端；旧 Dash 保留为 legacy（见 run_dashboard.sh）。
# ============================================================================
set -e
PORT_API=8000
PORT_WEB=5173
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$PROJECT_DIR/.venv312/bin"

cd "$PROJECT_DIR"
export DYLD_LIBRARY_PATH="/opt/homebrew/opt/expat/lib${DYLD_LIBRARY_PATH:+:$DYLD_LIBRARY_PATH}"

echo ""
echo "  ┌──────────────────────────────────────┐"
echo "  │  Macro Platform · FastAPI + Vue 3     │"
echo "  └──────────────────────────────────────┘"
echo ""

# ---------- 前端构建（首次或 dist 缺失时）----------
if [ ! -d "frontend/dist" ]; then
  echo "  📦 首次构建前端 (Vue)..."
  (cd frontend && npm install --no-audit --no-fund && npm run build)
  echo "  ✔ 前端构建完成"
fi

# ---------- 后端依赖检查 ----------
"$VENV/python" -c "import fastapi, uvicorn" 2>/dev/null || {
  echo "  📦 安装后端依赖..."
  "$VENV/pip" install -q fastapi 'uvicorn[standard]' pydantic httpx
}

cleanup() {
  echo ""; echo "  停止服务..."
  [ -n "$API_PID" ] && kill "$API_PID" 2>/dev/null
  [ -n "$WEB_PID" ] && kill "$WEB_PID" 2>/dev/null
}
trap cleanup EXIT INT TERM

# ---------- 后端 ----------
"$VENV/python" -m uvicorn backend.app.main:app --port "$PORT_API" >/tmp/macro_api.log 2>&1 &
API_PID=$!
echo "  ✔ FastAPI:    http://localhost:$PORT_API  (OpenAPI: /openapi.json)"

# ---------- 前端（preview 生产构建）----------
(cd frontend && npm run preview -- --port "$PORT_WEB" >/tmp/macro_web.log 2>&1) &
WEB_PID=$!

# 等就绪
for i in $(seq 1 20); do
  sleep 1
  curl -sf "http://localhost:$PORT_API/health" >/dev/null 2>&1 \
    && curl -sf "http://localhost:$PORT_WEB/" >/dev/null 2>&1 && break
done

echo "  ✔ Vue 前端:   http://localhost:$PORT_WEB"
echo ""
echo "  打开浏览器: http://localhost:$PORT_WEB"
echo "  停止: Ctrl + C"
echo "  提示: 旧 Dash (legacy) 仍可用 run_dashboard.sh"
echo ""
wait
