#!/usr/bin/env bash
# 一键将 AI圆桌 v4（多模态图片/文件附件 + 灵动胶囊输入舱 + 专属矢量图标 + 三分导航降噪版）
# 同步至本地仓库、注入幂等 AST 补丁、运行 v3(16项) + v4(10项) 全量自动化验收并更新桌面 AI圆桌.app
set -euo pipefail

SRC_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_REPO="${1:-${SRC_ROOT}}"

if [[ ! -d "${TARGET_REPO}/backend" ]]; then
  echo "✖ 未找到本地基准仓库 ${TARGET_REPO}，请确认路径正确。" >&2
  exit 1
fi

TARGET_REPO="$(cd "${TARGET_REPO}" && pwd -P)"
echo "==> [1/5] 正在同步 AI圆桌 v4 增量与覆盖源码 -> ${TARGET_REPO}"

if [[ "$(cd "${SRC_ROOT}" && pwd -P)" != "${TARGET_REPO}" ]]; then
  rsync -av \
    --exclude='.git' \
    --exclude='__pycache__' \
    --exclude='.DS_Store' \
    --exclude='*.gdoc' \
    --exclude='*.gsheet' \
    --exclude='*.gslides' \
    --exclude='*.app' \
    "${SRC_ROOT}/backend/" "${TARGET_REPO}/backend/"

  rsync -av \
    --exclude='.DS_Store' \
    --exclude='*.gdoc' \
    "${SRC_ROOT}/frontend/" "${TARGET_REPO}/frontend/"

  rsync -av \
    --exclude='.DS_Store' \
    --exclude='*.gdoc' \
    "${SRC_ROOT}/macos_app/" "${TARGET_REPO}/macos_app/"

  rsync -av \
    --exclude='.DS_Store' \
    --exclude='*.gdoc' \
    "${SRC_ROOT}/scripts/" "${TARGET_REPO}/scripts/"
fi

chmod +x "${TARGET_REPO}/scripts/"*.sh \
         "${TARGET_REPO}/scripts/apply_v4_patches.py" \
         "${TARGET_REPO}/scripts/verify_v4_acceptance.py" || true

echo "==> [2/5] 正在应用 v4 后端多模态联动补丁并执行语法静态检查..."
python3 "${TARGET_REPO}/scripts/apply_v4_patches.py" "${TARGET_REPO}"
python3 -m py_compile \
  "${TARGET_REPO}/backend/attachments.py" \
  "${TARGET_REPO}/backend/server.py" \
  "${TARGET_REPO}/backend/orchestrator.py" \
  "${TARGET_REPO}/backend/cli_adapters.py" \
  "${TARGET_REPO}/scripts/verify_v3_redlines.py" \
  "${TARGET_REPO}/scripts/verify_v4_acceptance.py"
node --check "${TARGET_REPO}/frontend/app.js"
node --check "${TARGET_REPO}/frontend/v4_ui.js"

echo "==> [3/5] 正在运行 v3 16 项安全红线回归 + v4 10 项多模态与交互验收套件..."
qa_tmp="$(mktemp -d)"
trap 'rm -rf "${qa_tmp}"' EXIT
python3 "${TARGET_REPO}/scripts/verify_v3_redlines.py"
python3 "${TARGET_REPO}/scripts/verify_v4_acceptance.py"
if [[ -f "${TARGET_REPO}/scripts/verify_v4_boundaries.py" ]]; then
  python3 "${TARGET_REPO}/scripts/verify_v4_boundaries.py"
fi
AI_ROUNDTABLE_HOME="${qa_tmp}/bench" python3 "${TARGET_REPO}/scripts/check_cli.py" --bench

if [[ "$(uname -s)" == "Darwin" ]]; then
  echo "==> [4/5] 正在使用 clang 编译原生 AI圆桌.app (v4 + 新版图标 + WKOpenPanel)..."
  bash "${TARGET_REPO}/scripts/build_macos_app.sh"
  built="${TARGET_REPO}/AI圆桌.app"
  desktop_app="${HOME}/Desktop/AI圆桌.app"
  codesign --verify --deep --strict "${built}"

  echo "==> [5/5] 正在原子替换更新桌面应用 ${desktop_app}..."
  install_dir="$(mktemp -d "${HOME}/Desktop/.ai-roundtable-v4.XXXXXX")"
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
  echo "✔ AI圆桌 v4 已就绪：${desktop_app}"
else
  echo "==> [4/5] 当前非 macOS 环境，跳过 clang 原生 App 编译。"
fi
