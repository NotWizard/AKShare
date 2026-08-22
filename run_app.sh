#!/bin/bash
# ============================================================================
#  中国宏观经济分析平台 — 一键启动（单进程）
#  FastAPI (:8000) 通过 StaticFiles 同时托管 API 与已构建的 Vue SPA (frontend/dist)。
#  不再单独运行 vite preview —— 消除了端口竞争、孤儿进程与陈旧包被误托管的问题。
#  （legacy Dash/Plotly 栈已于 98de136 下线，run_dashboard.sh 不再存在。）
# ============================================================================
set -e
PORT_API=8000
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

cd "$PROJECT_DIR"
export DYLD_LIBRARY_PATH="/opt/homebrew/opt/expat/lib${DYLD_LIBRARY_PATH:+:$DYLD_LIBRARY_PATH}"

echo ""
echo "  ┌──────────────────────────────────────┐"
echo "  │  Macro Platform · FastAPI + Vue 3     │"
echo "  └──────────────────────────────────────┘"
echo ""

# ---------- Python 解释器解析（唯一入口，O-M3）----------
# 旧版把 .venv312 硬编码进每一次调用，fresh clone 上第一句 "$VENV/python" 就
# "no such file or directory" 直接崩。现在集中解析一次，顺序：
#   PYTHON 覆盖 → VENV 覆盖（venv 根，兼容 $VENV/bin/python 与 $VENV/python）
#   → .venv312（权威：Python 3.12.14）
#   → .venv（陈旧：Python 3.11.14，违反 requires-python>=3.12，仅兜底）
#   → PATH 上的 python3
# 先挑「已经能 import fastapi+uvicorn」的候选；挑不到再退回「存在即用」并尝试按
# requirements.txt 补依赖；仍然不行就打印 bootstrap 指引并 exit 1。
CANDIDATES=()
[ -n "${PYTHON:-}" ] && CANDIDATES+=("$PYTHON")
[ -n "${VENV:-}" ] && CANDIDATES+=("$VENV/bin/python" "$VENV/python")
CANDIDATES+=("$PROJECT_DIR/.venv312/bin/python" "$PROJECT_DIR/.venv/bin/python")
CANDIDATES+=("$(command -v python3 || true)")

pick_python() {   # $1=1 时额外要求能 import fastapi+uvicorn
  local p
  for p in "${CANDIDATES[@]}"; do
    [ -n "$p" ] && [ -x "$p" ] || continue
    if [ "$1" = "1" ] && ! "$p" -c "import fastapi, uvicorn" >/dev/null 2>&1; then
      continue
    fi
    printf '%s\n' "$p"
    return 0
  done
  return 1
}

PY="$(pick_python 1 || pick_python 0 || true)"
if [ -z "$PY" ]; then
  echo "  ✗ 找不到可用的 Python 解释器（已试：PYTHON/VENV 覆盖、.venv312、.venv、python3）。"
  echo "    请先创建权威环境（Python 3.12+，见 requirements.txt 顶部说明）："
  echo "      python3.12 -m venv .venv312"
  echo "      .venv312/bin/python -m pip install -r requirements.lock"
  echo "    或指定现成解释器：  PYTHON=/path/to/python ./run_app.sh"
  exit 1
fi
echo "  ✔ 解释器: $PY  ($("$PY" -V 2>&1))"

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
# 安装一律走 requirements.txt（固定版本），不再 pip install 裸包名 —— 裸包名会拉到
# 任意新版，正是 O-H2 里「声明与实际不符」的来源。
"$PY" -c "import fastapi, uvicorn" 2>/dev/null || {
  echo "  📦 安装后端依赖（按 requirements.txt 固定版本）..."
  "$PY" -m pip install -q -r requirements.txt || true
}
"$PY" -c "import fastapi, uvicorn" 2>/dev/null || {
  echo "  ✗ $PY 无法 import fastapi/uvicorn，且自动安装未成功（离线环境访问不到 PyPI）。"
  echo "    有网环境执行：  $PY -m pip install -r requirements.lock"
  echo "    或改用已装好依赖的解释器：  PYTHON=/path/to/python ./run_app.sh"
  exit 1
}

# ---------- 采集依赖检查（刷新子进程 01_fetch_data.py 需要 akshare）----------
# 后端本身不 import akshare，但「刷新数据」的采集子进程必须 import；
# 缺它会导致刷新 exit 1（ModuleNotFoundError: akshare）。重建 venv 后自动补齐防复发。
# 这里刻意不致命：缺 akshare 只影响刷新，API/SPA 仍可正常提供服务。
"$PY" -c "import akshare" 2>/dev/null || {
  echo "  📦 安装采集依赖 (akshare 等，按 requirements.txt 固定版本)..."
  "$PY" -m pip install -q -r requirements.txt || echo "  ⚠ akshare 未装上，「刷新数据」会失败（其余功能不受影响）"
}

# ---------- 日志（O-M2）----------
# 旧版写 /tmp/macro_api.log：重启即丢、无上界，端口漂移那类关键提示就是这么被吞掉的。
# 改到仓库内 data/logs/api.log，与 01_fetch_data.py 的 data/logs/fetch.log 同处一地。
# 有界：启动时若已超 5MB 就转存 .1，占用上界 ≈ 10MB（当前 + 上一份）；追加而非清空，
# 以便重启后仍能回看上一次的失败原因。
LOG_DIR="$PROJECT_DIR/data/logs"
API_LOG="$LOG_DIR/api.log"
mkdir -p "$LOG_DIR"
# 根 .gitignore 只逐个列了 data/ 下的具体文件（data/*.db、data/refresh_schedule.log…），
# 并没有 data/logs/ 规则；放一个自忽略的 .gitignore，避免日志污染 git status。
[ -f "$LOG_DIR/.gitignore" ] || printf '*\n' > "$LOG_DIR/.gitignore"
if [ -f "$API_LOG" ] && [ "$(wc -c < "$API_LOG")" -gt 5242880 ]; then
  mv -f "$API_LOG" "$API_LOG.1"
fi

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
printf '\n===== run %s · port %s · %s =====\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$PORT_API" "$PY" >> "$API_LOG"
"$PY" -m uvicorn backend.app.main:app --port "$PORT_API" >>"$API_LOG" 2>&1 &
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
  echo "  ✗ 后端未能就绪（http://localhost:$PORT_API/health 无响应）。最近日志（$API_LOG）："
  echo "  ----------------------------------------"
  tail -n 40 "$API_LOG"
  exit 1
fi

echo "  ✔ 服务就绪:  http://localhost:$PORT_API   (API + Vue SPA · OpenAPI: /openapi.json)"
echo ""
echo "  打开浏览器: http://localhost:$PORT_API"
echo "  后端日志:   data/logs/api.log   (超 5MB 自动转存 api.log.1)"
echo "  停止: Ctrl + C"
echo ""
wait "$API_PID"
