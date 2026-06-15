#!/bin/bash
# 中国宏观经济分析平台 - 一键启动
set -e

cd "$(dirname "$0")"

echo "=========================================="
echo "  中国宏观经济数据分析平台"
echo "=========================================="

# 检查数据库
if [ ! -f "data/macro_data.db" ]; then
    echo "📊 数据库不存在，开始采集数据..."
    python3 scripts/01_fetch_data.py
    python3 scripts/02_compute_derived.py
fi

# 安装依赖（如果缺失）
python3 -c "import dash" 2>/dev/null || {
    echo "📦 安装依赖..."
    pip3 install -r requirements.txt --quiet
}

echo ""
echo "🚀 启动 Dashboard..."
echo "   浏览器访问: http://localhost:8050"
echo "   按 Ctrl+C 停止"
echo ""

python3 dashboard/app.py
