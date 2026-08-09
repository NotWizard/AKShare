#!/bin/bash
# 安装定时刷新任务（macOS launchd，每日 10:07）。幂等：已存在先 bootout 再重装。
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
PYTHON="$PROJECT_ROOT/.venv312/bin/python"
LABEL="com.macro.refresh"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"

mkdir -p "$HOME/Library/LaunchAgents"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
sed -e "s|__PROJECT_ROOT__|$PROJECT_ROOT|g" -e "s|__PYTHON__|$PYTHON|g" \
  "$SCRIPT_DIR/$LABEL.plist" > "$PLIST"
launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "✅ 已安装 $LABEL（每日 10:07）→ $PLIST"
echo "   日志: $PROJECT_ROOT/data/refresh_schedule.log"
