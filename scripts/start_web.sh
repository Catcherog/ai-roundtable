#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${PORT:-8765}"
HOST="${HOST:-127.0.0.1}"
DEFAULT_WS="${HOME}/.ai-roundtable/workspace"
mkdir -p "${DEFAULT_WS}"

read -r BOOT_TOKEN BOOT_ID BOOTSTRAP_CODE < <(
  python3 -c "import secrets; print(secrets.token_hex(32), secrets.token_hex(16), secrets.token_urlsafe(24))"
)

BASE_URL="http://${HOST}:${PORT}"
LAUNCH_URL="${BASE_URL}/#bootstrap=${BOOTSTRAP_CODE}"

echo "正在启动 AI圆桌 Web 安全控制面 -> ${BASE_URL}"

(
  for _ in $(seq 1 90); do
    if python3 -c "import socket,sys; s=socket.socket(); s.settimeout(0.05); sys.exit(0 if s.connect_ex(('${HOST}', ${PORT}))==0 else 1)" 2>/dev/null; then
      open "${LAUNCH_URL}" >/dev/null 2>&1 || true
      exit 0
    fi
    sleep 0.03
  done
  open "${LAUNCH_URL}" >/dev/null 2>&1 || true
) &

export AI_ROUNDTABLE_LOGIN_SHELL=1
export AI_ROUNDTABLE_BOOT_TOKEN="${BOOT_TOKEN}"
export AI_ROUNDTABLE_BOOT_ID="${BOOT_ID}"
export AI_ROUNDTABLE_BOOTSTRAP_CODE="${BOOTSTRAP_CODE}"

exec python3 "${ROOT_DIR}/backend/server.py" --host "${HOST}" --port "${PORT}" --workspace "${DEFAULT_WS}"
