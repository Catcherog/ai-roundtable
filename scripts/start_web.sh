#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${PORT:-8765}"
HOST="${HOST:-127.0.0.1}"
URL="http://${HOST}:${PORT}"
DEFAULT_WS="${HOME}/.ai-roundtable/workspace"
mkdir -p "${DEFAULT_WS}"

echo "正在启动 AI圆桌 Web 服务 -> ${URL}"

# 毫秒级探测端口就绪后立即唤起默认浏览器（取代固定 1 秒盲等）
(
  for _ in $(seq 1 80); do
    if python3 -c "import socket,sys; s=socket.socket(); s.settimeout(0.05); sys.exit(0 if s.connect_ex(('${HOST}', ${PORT}))==0 else 1)" 2>/dev/null; then
      open "${URL}" >/dev/null 2>&1 || true
      exit 0
    fi
    sleep 0.03
  done
  open "${URL}" >/dev/null 2>&1 || true
) &

AI_ROUNDTABLE_LOGIN_SHELL=1 exec python3 "${ROOT_DIR}/backend/server.py" --host "${HOST}" --port "${PORT}" --workspace "${DEFAULT_WS}"
