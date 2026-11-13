#!/bin/bash
# 构建 Autonode.app（通用二进制），用法：build-app.sh <输出 app 路径>
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
OUT="${1:-$ROOT/build/Autonode.app}"
TMP="$(mktemp -d)"

trap 'rm -rf "$TMP"' EXIT

swiftc -O -target arm64-apple-macos11 -o "$TMP/arm64" "$HERE/app/main.swift" \
  -framework Cocoa -framework WebKit

BIN="$TMP/arm64"
# Intel 版：工具链缺 x86_64 Swift 运行时库时会失败，失败则退回单架构
if swiftc -O -target x86_64-apple-macos11 -o "$TMP/x86_64" "$HERE/app/main.swift" \
     -framework Cocoa -framework WebKit 2>/dev/null; then
  lipo -create -output "$TMP/universal" "$TMP/arm64" "$TMP/x86_64"
  BIN="$TMP/universal"
  echo "模式: universal (arm64 + x86_64)"
else
  echo "模式: arm64 only（当前工具链不支持 x86_64 Swift 运行时）"
fi

rm -rf "$OUT"
mkdir -p "$OUT/Contents/MacOS" "$OUT/Contents/Resources"
cp "$BIN" "$OUT/Contents/MacOS/Autonode"
chmod +x "$OUT/Contents/MacOS/Autonode"

cp "$HERE/app/Info.plist" "$OUT/Contents/Info.plist"
if [ -f "$ROOT/assets/icon.icns" ]; then
  cp "$ROOT/assets/icon.icns" "$OUT/Contents/Resources/icon.icns"
fi

codesign --force --deep --sign - "$OUT" >/dev/null 2>&1 || true
echo "built: $OUT"
file "$OUT/Contents/MacOS/Autonode"
