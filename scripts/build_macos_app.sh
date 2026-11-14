#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_NAME="AI圆桌"
APP_BUNDLE="${ROOT_DIR}/${APP_NAME}.app"
CONTENTS_DIR="${APP_BUNDLE}/Contents"
MACOS_DIR="${CONTENTS_DIR}/MacOS"
RES_DIR="${CONTENTS_DIR}/Resources"
EMBED_APP_DIR="${RES_DIR}/app"
TMP_BUILD="$(mktemp -d)"

trap 'rm -rf "${TMP_BUILD}"' EXIT

echo "1/4 正在创建 ${APP_NAME}.app 目录结构..."
rm -rf "${APP_BUNDLE}"
mkdir -p "${MACOS_DIR}" "${EMBED_APP_DIR}"

echo "2/4 正在生成高清多分辨率应用图标 AppIcon.icns..."
ICONSET_DIR="${TMP_BUILD}/AppIcon.iconset"
mkdir -p "${ICONSET_DIR}"
clang -fobjc-arc -framework Cocoa "${ROOT_DIR}/macos_app/make_icon.m" -o "${TMP_BUILD}/make_icon"
"${TMP_BUILD}/make_icon" "${ICONSET_DIR}"

python3 - "${ICONSET_DIR}" "${RES_DIR}/AppIcon.icns" <<'PY'
import os, struct, sys

icon_dir, out_icns = sys.argv[1], sys.argv[2]
mapping = [
    (b"ic07", "icon_128x128.png"),
    (b"ic08", "icon_256x256.png"),
    (b"ic09", "icon_512x512.png"),
    (b"ic10", "icon_512x512@2x.png"),
]
chunks = bytearray()
for ostype, fname in mapping:
    data = open(os.path.join(icon_dir, fname), "rb").read()
    chunks.extend(ostype)
    chunks.extend(struct.pack(">I", 8 + len(data)))
    chunks.extend(data)

with open(out_icns, "wb") as f:
    f.write(b"icns")
    f.write(struct.pack(">I", 8 + len(chunks)))
    f.write(chunks)
PY

echo "3/4 正在编译原生 arm64 Cocoa + WKWebView 可执行程序..."
clang -O2 -fobjc-arc -framework Cocoa -framework WebKit \
  -mmacosx-version-min=12.0 \
  "${ROOT_DIR}/macos_app/main.m" \
  -o "${MACOS_DIR}/${APP_NAME}"

echo "4/4 正在打包内嵌资源与 Info.plist 并签名..."
cp -R "${ROOT_DIR}/backend" "${EMBED_APP_DIR}/backend"
cp -R "${ROOT_DIR}/frontend" "${EMBED_APP_DIR}/frontend"
find "${EMBED_APP_DIR}" \( -name "__pycache__" -o -name "*.pyc" -o -name ".DS_Store" \) -exec rm -rf {} + 2>/dev/null || true

cat << 'EOF' > "${CONTENTS_DIR}/Info.plist"
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
  <string>1.0.0</string>
  <key>CFBundleVersion</key>
  <string>1</string>
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
EOF

codesign --force -s - "${APP_BUNDLE}"
codesign --verify --deep --strict "${APP_BUNDLE}"

echo "✅ 构建完成: ${APP_BUNDLE}"
