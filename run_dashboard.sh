#!/bin/bash
# ============================================================================
#  中国宏观经济数据分析平台 — Dashboard 启动脚本
# ============================================================================
set -e

PORT=8050
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$PROJECT_DIR/.venv312"

cd "$PROJECT_DIR"

# macOS Homebrew Python 需要正确的动态库路径（解决 libexpat 符号缺失）
export DYLD_LIBRARY_PATH="/opt/homebrew/opt/expat/lib${DYLD_LIBRARY_PATH:+:$DYLD_LIBRARY_PATH}"

echo ""
echo "  ┌──────────────────────────────────────┐"
echo "  │   中国宏观经济数据分析平台            │"
echo "  │   Terminal Fintech Dashboard          │"
echo "  └──────────────────────────────────────┘"
echo ""

# ---------- 激活虚拟环境 ----------
if [ -d "$VENV_DIR" ]; then
    source "$VENV_DIR/bin/activate"
    echo "  ✔ 虚拟环境: $VENV_DIR"
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
    echo "  ✔ 端口已释放"
fi

# ---------- 启动服务 ----------
echo ""
echo "  🚀 启动 Dashboard"
echo "  ─────────────────────────────────────"
echo "  地址: http://localhost:$PORT"
echo "  停止: Ctrl + C"
echo ""
echo "  提示: DASH_DEBUG=1 ./run_dashboard.sh 开启开发模式（热重载+调试工具）"
echo ""

python3 dashboard/app.py
