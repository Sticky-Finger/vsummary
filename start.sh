#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
ENV_NAME="vsummary"
CONDA_BIN="${CONDA_EXE:-}"

cd "$ROOT"

# —— conda 发现(沿用 start.command 逻辑)——
if [ -z "$CONDA_BIN" ] || [ ! -x "$CONDA_BIN" ]; then
  if command -v conda >/dev/null 2>&1; then
    CONDA_BIN="$(command -v conda)"
  else
    for c in "$HOME/miniconda3/bin/conda" "$HOME/anaconda3/bin/conda" "$HOME/mambaforge/bin/conda"; do
      if [ -x "$c" ]; then
        CONDA_BIN="$c"
        break
      fi
    done
  fi
fi

if [ -z "$CONDA_BIN" ] || [ ! -x "$CONDA_BIN" ]; then
  echo "Conda was not found. Install it, then create the source environment with environment.cpu.yml."
  exit 1
fi

ENV_PATH="$($CONDA_BIN env list | awk -v n="$ENV_NAME" '$1 == n { print $NF; exit }')"
PYTHON="$ENV_PATH/bin/python"
if [ -z "$ENV_PATH" ] || [ ! -x "$PYTHON" ]; then
  echo "Conda environment '$ENV_NAME' was not found."
  echo "Run: conda env create -f environment.cpu.yml"
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "npm was not found. Install Node.js 18 or newer."
  exit 1
fi

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo "[warn] ffmpeg not found; video transcription and screenshots will fail."
fi

mkdir -p "$ROOT/data/logs"

# —— 端口占用探测(纯 Python,无需 lsof)——
port_in_use() {
  "$PYTHON" - "$1" <<'PY'
import socket, sys
port = int(sys.argv[1])
sock = socket.socket()
sock.settimeout(0.3)
try:
    sock.connect(("127.0.0.1", port))
    print("1")
except Exception:
    print("0")
PY
}

if [ "$(port_in_use 8001)" = "0" ]; then
  nohup "$PYTHON" -m backend.api.http.server --host 127.0.0.1 --port 8001 \
    >"$ROOT/data/logs/backend.log" 2>&1 &
fi
if [ "$(port_in_use 4173)" = "0" ]; then
  (
    cd "$ROOT/src/frontend"
    nohup npm run dev >"$ROOT/data/logs/frontend.log" 2>&1 &
  )
fi

sleep 1
URL="http://127.0.0.1:4173"
echo "Backend:  http://127.0.0.1:8001"
echo "Frontend: $URL"
if command -v xdg-open >/dev/null 2>&1; then
  xdg-open "$URL" >/dev/null 2>&1 &
elif [ -n "${BROWSER:-}" ]; then
  "$BROWSER" "$URL" >/dev/null 2>&1 &
else
  echo "Open $URL in your browser."
fi
