#!/bin/bash
# ============================================================================
#  中国宏观经济数据分析平台 — 双击启动 & 关窗即停
#  新架构：单进程 FastAPI(:8000) 同时托管 API 与已构建的 Vue SPA，底层委托 run_app.sh
#  （vite preview 已下线，不再有 :5173）
# ============================================================================

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

# 终端标题
echo -ne "\033]0;宏观经济分析平台\007"

clear
echo ""
echo "  ┌──────────────────────────────────────┐"
echo "  │   中国宏观经济数据分析平台            │"
echo "  │   FastAPI + Vue 3 + ECharts          │"
echo "  └──────────────────────────────────────┘"
echo ""

if [ ! -x "$PROJECT_DIR/run_app.sh" ]; then
    chmod +x "$PROJECT_DIR/run_app.sh"
fi

echo "  启动中（首次会构建前端，约几十秒）…"
echo "  打开浏览器: http://localhost:8000"
echo "  关闭此窗口即可停止服务"
echo ""

# 委托新栈启动脚本；关窗/退出即终止整套服务
exec "$PROJECT_DIR/run_app.sh"
