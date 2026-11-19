#!/usr/bin/env bash
set -euo pipefail

SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_SRC="${SRC_DIR}/AI圆桌.app"
APP_BIN="${APP_SRC}/Contents/MacOS/AI圆桌"
DESKTOP_DST="${HOME}/Desktop/AI圆桌.app"

need_rebuild=0
if [[ ! -x "${APP_BIN}" ]]; then
  need_rebuild=1
elif [[ -n "$(find "${SRC_DIR}/backend" "${SRC_DIR}/frontend" "${SRC_DIR}/macos_app" "${SRC_DIR}/scripts/build_macos_app.sh" -newer "${APP_BIN}" -print -quit 2>/dev/null)" ]]; then
  need_rebuild=1
fi

if [[ "${need_rebuild}" -eq 1 ]]; then
  echo "🔄 检测到源码已更新，正在重新编译最新版 AI圆桌.app..."
  "${SRC_DIR}/scripts/build_macos_app.sh"
fi

# 先关闭旧版正在运行的 AI圆桌 实例及任何残留的内嵌后端进程，释放端口与 SQLite 锁句柄
osascript -e 'tell application "AI圆桌" to quit' >/dev/null 2>&1 || true
pkill -x "AI圆桌" 2>/dev/null || true
pkill -f "AI圆桌.app/Contents/Resources/app/backend/server.py" 2>/dev/null || true
sleep 0.6

rm -rf "${DESKTOP_DST}"
cp -R "${APP_SRC}" "${DESKTOP_DST}"
xattr -cr "${DESKTOP_DST}" 2>/dev/null || true
touch "${DESKTOP_DST}" "${DESKTOP_DST}/Contents/Resources/AppIcon.icns" 2>/dev/null || true
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister -f "${DESKTOP_DST}" 2>/dev/null || true
killall Finder 2>/dev/null || true
killall Dock 2>/dev/null || true

echo "✅ 已将最新版「AI圆桌.app」及 3D 水晶三叶结图标同步到桌面并刷新图标缓存：${DESKTOP_DST}"
open "${DESKTOP_DST}"
