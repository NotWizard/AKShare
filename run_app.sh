#!/bin/bash
# ============================================================================
#  中国宏观经济分析平台 — 一键启动（单进程）
#  FastAPI (:8000) 通过 StaticFiles 同时托管 API 与已构建的 Vue SPA (frontend/dist)。
#  不再单独运行 vite preview —— 消除了端口竞争、孤儿进程与陈旧包被误托管的问题。
#  旧 Dash 保留为 legacy（见 run_dashboard.sh）。
# ============================================================================
set -e
PORT_API=8000
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$PROJECT_DIR/.venv312/bin"

cd "$PROJECT_DIR"
export DYLD_LIBRARY_PATH="/opt/homebrew/opt/expat/lib${DYLD_LIBRARY_PATH:+:$DYLD_LIBRARY_PATH}"

echo ""
echo "  ┌──────────────────────────────────────┐"
echo "  │  Macro Platform · FastAPI + Vue 3     │"
echo "  └──────────────────────────────────────┘"
echo ""

# ---------- 前端构建（仅当 dist 缺失或源码指纹变化时重建）----------
# 指纹 = frontend/src 全部文件内容 + package.json + package-lock.json 的内容哈希，
# 与 frontend/dist/.buildstamp 比对：不一致（或首次、dist 缺失）才用 `npm ci && npm run build`
# 重建，构建后写入新指纹。避免源码改动后仍静默托管旧包（O-M1）。
fingerprint() {
  {
    find frontend/src -type f -print0 | LC_ALL=C sort -z | xargs -0 shasum
    shasum frontend/package.json frontend/package-lock.json
  } | shasum | awk '{print $1}'
}

FP="$(fingerprint)"
if [ ! -f frontend/dist/.buildstamp ] || [ "$(cat frontend/dist/.buildstamp 2>/dev/null)" != "$FP" ]; then
  echo "  📦 构建前端 (Vue) — 首次或源码有变更..."
  (cd frontend && npm ci && npm run build)
  printf '%s\n' "$FP" > frontend/dist/.buildstamp
  echo "  ✔ 前端构建完成"
else
  echo "  ✔ 前端已是最新（跳过构建）"
fi

# ---------- 后端依赖检查 ----------
"$VENV/python" -c "import fastapi, uvicorn" 2>/dev/null || {
  echo "  📦 安装后端依赖..."
  "$VENV/pip" install -q fastapi 'uvicorn[standard]' pydantic httpx
}

# ---------- 采集依赖检查（刷新子进程 01_fetch_data.py 需要 akshare）----------
# 后端本身不 import akshare，但「刷新数据」的采集子进程必须 import；
# 缺它会导致刷新 exit 1（ModuleNotFoundError: akshare）。重建 venv 后自动补齐防复发。
"$VENV/python" -c "import akshare" 2>/dev/null || {
  echo "  📦 安装采集依赖 (akshare)..."
  "$VENV/pip" install -q -r requirements.txt
}

cleanup() {
  set +e   # 清理阶段绝不因单个命令失败而中断（O-C2）：确保 uvicorn 被彻底停掉
  echo ""; echo "  停止服务..."
  if [ -n "${API_PID:-}" ]; then
    kill "$API_PID" 2>/dev/null
    wait "$API_PID" 2>/dev/null
  fi
}
trap cleanup EXIT INT TERM

# ---------- 启动（单进程：FastAPI 同时托管 API 与 SPA）----------
"$VENV/python" -m uvicorn backend.app.main:app --port "$PORT_API" >/tmp/macro_api.log 2>&1 &
API_PID=$!

# 等待就绪：轮询 /health；超时则打印日志并以非零码退出（绝不打印成功横幅）。
READY=0
for _ in $(seq 1 30); do
  if curl -sf "http://localhost:$PORT_API/health" >/dev/null 2>&1; then
    READY=1; break
  fi
  kill -0 "$API_PID" 2>/dev/null || break   # uvicorn 已退出，停止空等
  sleep 1
done

if [ "$READY" -ne 1 ]; then
  echo "  ✗ 后端未能就绪（http://localhost:$PORT_API/health 无响应）。最近日志："
  echo "  ----------------------------------------"
  tail -n 40 /tmp/macro_api.log
  exit 1
fi

echo "  ✔ 服务就绪:  http://localhost:$PORT_API   (API + Vue SPA · OpenAPI: /openapi.json)"
echo ""
echo "  打开浏览器: http://localhost:$PORT_API"
echo "  停止: Ctrl + C"
echo "  提示: 旧 Dash (legacy) 仍可用 run_dashboard.sh"
echo ""
wait "$API_PID"
