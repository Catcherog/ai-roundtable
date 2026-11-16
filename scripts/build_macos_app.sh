#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_NAME="AI圆桌"
APP_BUNDLE="${ROOT_DIR}/${APP_NAME}.app"
CONTENTS_DIR="${APP_BUNDLE}/Contents"
MACOS_DIR="${CONTENTS_DIR}/MacOS"
RES_DIR="${CONTENTS_DIR}/Resources"
EMBED_APP_DIR="${RES_DIR}/app"

echo "==> 1. 准备 ${APP_NAME}.app v4.0.0 目录结构..."
rm -rf "${APP_BUNDLE}"
mkdir -p "${MACOS_DIR}" "${EMBED_APP_DIR}/backend" "${EMBED_APP_DIR}/frontend"

echo "==> 2. 编译原生 macOS 启动器与 v4 桌面图标生成器 (WKOpenPanel + Security.framework)..."
clang -fobjc-arc -O2 \
  -framework Cocoa \
  -framework WebKit \
  -framework Security \
  -mmacosx-version-min=12.0 \
  "${ROOT_DIR}/macos_app/main.m" \
  -o "${MACOS_DIR}/${APP_NAME}"

if [ -f "${ROOT_DIR}/macos_app/make_icon.m" ]; then
  ICONSET_TMP="$(mktemp -d)/AppIcon.iconset"
  mkdir -p "${ICONSET_TMP}"
  MAKE_ICON_BIN="$(mktemp)"
  clang -fobjc-arc -O2 -framework Cocoa "${ROOT_DIR}/macos_app/make_icon.m" -o "${MAKE_ICON_BIN}"
  "${MAKE_ICON_BIN}" "${ICONSET_TMP}" "${ROOT_DIR}/docs/images/app-icon.png"
  if ! iconutil -c icns "${ICONSET_TMP}" -o "${RES_DIR}/AppIcon.icns" 2>/dev/null; then
    "${MAKE_ICON_BIN}" "${ICONSET_TMP}" --icns "${RES_DIR}/AppIcon.icns"
  fi
  rm -rf "$(dirname "${ICONSET_TMP}")" "${MAKE_ICON_BIN}"
fi

echo "==> 3. 递归同步后端多模态附件子系统与前端灵动输入舱静态产物..."
rsync -a --exclude='__pycache__' --exclude='*.pyc' --exclude='*.gdoc' "${ROOT_DIR}/backend/" "${EMBED_APP_DIR}/backend/"
rsync -a --exclude='.DS_Store' --exclude='*.gdoc' "${ROOT_DIR}/frontend/" "${EMBED_APP_DIR}/frontend/"

cat > "${CONTENTS_DIR}/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleDevelopmentRegion</key>
  <string>zh_CN</string>
  <key>CFBundleDisplayName</key>
  <string>AI圆桌</string>
  <key>CFBundleExecutable</key>
  <string>AI圆桌</string>
  <key>CFBundleIconFile</key>
  <string>AppIcon</string>
  <key>CFBundleIdentifier</key>
  <string>local.airoundtable.desktop</string>
  <key>CFBundleInfoDictionaryVersion</key>
  <string>6.0</string>
  <key>CFBundleName</key>
  <string>AI圆桌</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleShortVersionString</key>
  <string>4.0.0</string>
  <key>CFBundleVersion</key>
  <string>7</string>
  <key>LSMinimumSystemVersion</key>
  <string>12.0</string>
  <key>NSHighResolutionCapable</key>
  <true/>
  <key>NSAppTransportSecurity</key>
  <dict>
    <key>NSAllowsLocalNetworking</key>
    <true/>
  </dict>
</dict>
</plist>
PLIST

echo "==> 4. 执行 ad-hoc 签名并清理 Quarantine 属性..."
codesign --force --deep --sign - "${APP_BUNDLE}"
xattr -cr "${APP_BUNDLE}" 2>/dev/null || true

echo "==> 构建完成: ${APP_BUNDLE} (v4.0.0)"
