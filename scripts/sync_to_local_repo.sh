#!/usr/bin/env bash
# 一键将 AI圆桌 v3 升级包同步至本地仓库、运行 16 项架构红线验收并重编译桌面端 AI圆桌.app
set -euo pipefail

SRC_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TARGET_REPO="${1:-${HOME}/Documents/AI圆桌}"

echo "[1/4] 正在同步 v3 源码 -> ${TARGET_REPO}"
mkdir -p "${TARGET_REPO}"
TARGET_REPO="$(cd "${TARGET_REPO}" && pwd -P)"
if [[ "$(cd "${SRC_ROOT}" && pwd -P)" != "${TARGET_REPO}" ]]; then
  rsync -av --exclude='.git' --exclude='__pycache__' --exclude='.DS_Store' --exclude='*.app' --exclude='/output/' --exclude='/dist/' "${SRC_ROOT}/" "${TARGET_REPO}/"
fi
chmod +x "${TARGET_REPO}/scripts/"*.sh "${TARGET_REPO}/scripts/verify_v3_redlines.py" "${TARGET_REPO}/安装到桌面.command" || true

echo "[2/4] 正在执行 16 项架构裁定红线与并发验收套件..."
qa_dir="$(mktemp -d)"
trap 'rm -rf "${qa_dir}"' EXIT
python3 "${TARGET_REPO}/scripts/verify_v3_redlines.py"
AI_ROUNDTABLE_HOME="${qa_dir}/bench" python3 "${TARGET_REPO}/scripts/check_cli.py" --bench
node --check "${TARGET_REPO}/frontend/app.js"

if [[ "$(uname -s)" == "Darwin" ]]; then
  echo "[3/4] 检测到 macOS 环境，正在使用 clang 编译原生 AI圆桌.app..."
  bash "${TARGET_REPO}/scripts/build_macos_app.sh"
  built="${TARGET_REPO}/AI圆桌.app"
  desktop_app="${HOME}/Desktop/AI圆桌.app"
  codesign --verify --deep --strict "${built}"
  echo "[4/4] 正在校验并安装桌面应用..."
  install_dir="$(mktemp -d "${HOME}/Desktop/.ai-roundtable-install.XXXXXX")"
  ditto "${built}" "${install_dir}/new.app"
  codesign --verify --deep --strict "${install_dir}/new.app"
  if [[ -e "${desktop_app}" || -L "${desktop_app}" ]]; then
    mv "${desktop_app}" "${install_dir}/previous.app"
  fi
  if ! mv "${install_dir}/new.app" "${desktop_app}"; then
    [[ ! -e "${install_dir}/previous.app" ]] || mv "${install_dir}/previous.app" "${desktop_app}"
    exit 1
  fi
  rm -rf "${install_dir}"
  echo "✔ 已安装：${desktop_app}"
else
  echo "[3/4] 当前非 macOS 环境，跳过 clang 原生 App 编译。"
fi
