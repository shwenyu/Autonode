#!/bin/bash
# Autonode —— macOS 安装脚本
set -euo pipefail

LABEL="com.autonode"
DEST="$HOME/.config/autonode"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
HERE="$(cd "$(dirname "$0")" && pwd)"

say() { printf "\033[1;36m==>\033[0m %s\n" "$1"; }
die() { printf "\033[1;31m错误：\033[0m %s\n" "$1" >&2; exit 1; }

[ "$(uname)" = "Darwin" ] || die "这个脚本只适用于 macOS"

PY="/usr/bin/python3"
[ -x "$PY" ] || PY="$(command -v python3 || true)"
[ -n "$PY" ] || die "找不到 python3"

if [ ! -d "/Applications/Clash Verge.app" ]; then
  say "没找到 Clash Verge；装好后 Autonode 会自动接管（每 10 秒探测一次）"
fi

mkdir -p "$DEST" "$HOME/Library/LaunchAgents"
cp "$HERE/autonode.py" "$DEST/autonode.py"
chmod 700 "$DEST/autonode.py"

cat > "$PLIST" <<PLIST_EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>$LABEL</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PY</string>
        <string>$DEST/autonode.py</string>
        <string>--serve</string>
    </array>
    <key>KeepAlive</key><true/>
    <key>RunAtLoad</key><true/>
    <key>StandardOutPath</key><string>$DEST/launchd.out.log</string>
    <key>StandardErrorPath</key><string>$DEST/launchd.err.log</string>
    <key>ProcessType</key><string>Background</string>
</dict>
</plist>
PLIST_EOF

launchctl bootout "gui/$(id -u)/$LABEL" >/dev/null 2>&1 || true
sleep 1
launchctl bootstrap "gui/$(id -u)" "$PLIST" || die "launchctl 加载失败"
sleep 3
open "http://127.0.0.1:8765/" >/dev/null 2>&1 || true

say "安装完成"
echo "  程序  : $DEST/autonode.py"
echo "  配置  : $DEST/config.json（首次启动自动探测客户端与分组）"
echo "  日志  : $DEST/autonode.log"
echo "  控制台: http://127.0.0.1:8765"
