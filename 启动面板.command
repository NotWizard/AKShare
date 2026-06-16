#!/bin/bash
# ============================================================================
#  中国宏观经济数据分析平台 — 双击启动 & 关窗即停
# ============================================================================

PORT=8050
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$PROJECT_DIR/.venv312"

cd "$PROJECT_DIR"

# macOS Homebrew Python 需要正确的动态库路径（解决 libexpat 符号缺失）
export DYLD_LIBRARY_PATH="/opt/homebrew/opt/expat/lib${DYLD_LIBRARY_PATH:+:$DYLD_LIBRARY_PATH}"

# 关闭终端窗口时自动终止服务
cleanup() {
    echo ""
    echo "  正在停止服务..."
    kill $SERVER_PID 2>/dev/null
    wait $SERVER_PID 2>/dev/null
    echo "  ✔ 服务已停止，窗口将关闭"
    sleep 1
    exit 0
}
trap cleanup EXIT INT TERM HUP

# ---------- 终端标题 ----------
echo -ne "\033]0;宏观经济分析平台\007"

clear
echo ""
echo "  ┌──────────────────────────────────────┐"
echo "  │   中国宏观经济数据分析平台            │"
echo "  │   Terminal Fintech Dashboard          │"
echo "  └──────────────────────────────────────┘"
echo ""

# ---------- 激活虚拟环境 ----------
if [ -d "$VENV_DIR" ]; then
    source "$VENV_DIR/bin/activate"
    echo "  ✔ 虚拟环境: .venv312"
else
    echo "  ⚠ 未找到 .venv312，使用系统 Python"
fi

# ---------- 检查数据库 ----------
if [ ! -f "data/macro_data.db" ]; then
    echo "  📊 数据库不存在，开始采集数据..."
    python3 scripts/01_fetch_data.py
    python3 scripts/02_compute_derived.py
    echo "  ✔ 数据采集完成"
fi

# ---------- 检查依赖 ----------
python3 -c "import dash" 2>/dev/null || {
    echo "  📦 安装依赖..."
    pip3 install -r requirements.txt --quiet
    echo "  ✔ 依赖安装完成"
}

# ---------- 清理端口占用 ----------
if lsof -ti :$PORT >/dev/null 2>&1; then
    echo "  ⚠ 端口 $PORT 被占用，正在释放..."
    lsof -ti :$PORT | xargs kill -9 2>/dev/null || true
    sleep 1
fi

# ---------- 启动服务 ----------
echo ""
echo "  🚀 启动 Dashboard"
echo "  ─────────────────────────────────────"
echo "  地址: http://localhost:$PORT"
echo ""
echo "  ╭─────────────────────────────────╮"
echo "  │  关闭此窗口即可停止服务         │"
echo "  ╰─────────────────────────────────╯"
echo ""

# 后台启动并记录 PID，然后自动打开浏览器
python3 dashboard/app.py &
SERVER_PID=$!

# 等待服务就绪后打开浏览器
sleep 2
if kill -0 $SERVER_PID 2>/dev/null; then
    open "http://localhost:$PORT"
    echo "  ✔ 浏览器已打开"
else
    echo "  ✘ 服务启动失败，请检查日志"
    exit 1
fi

echo ""
echo "  服务运行中 (PID: $SERVER_PID)..."
echo ""

# 保持脚本运行，直到服务退出或窗口关闭
wait $SERVER_PID
