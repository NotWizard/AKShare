#!/bin/bash
# 卸载定时刷新任务（launchd）。幂等：未安装也不报错。
set -e
LABEL="com.macro.refresh"
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
rm -f "$HOME/Library/LaunchAgents/$LABEL.plist"
echo "✅ 已卸载 $LABEL"
