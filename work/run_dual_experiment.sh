#!/usr/bin/env bash
set -euo pipefail

MAP_INDEX="${1:-01}"
LABEL="${2:-dual_map${MAP_INDEX}}"
ROOT="/Users/tttksj/Desktop/ssafy-race"
ASSETS="/Users/tttksj/Desktop/ssafy-race-assets/Simulator"
TOOLS="/Users/tttksj/Desktop/ssafy-race-tools"
BOT_DIR="$ROOT/work/Template_Python/Bot_Python"
SETTINGS="$ROOT/work/settings/settings_${MAP_INDEX}.json"
WINEBIN="/Users/tttksj/Applications/Wine Stable.app/Contents/Resources/wine/bin/wine"
WINEPREFIX="$TOOLS/wine-prefix-ssafy"
OUT_DIR="$ROOT/work/experiments"
mkdir -p "$OUT_DIR" "$TOOLS/logs" /Users/tttksj/Documents/AirSim

cleanup() {
  pkill -f 'my_car.py' >/dev/null 2>&1 || true
  pkill -f 'Algo-Win64-Shipping.exe' >/dev/null 2>&1 || true
  pkill -f './Algo.exe' >/dev/null 2>&1 || true
}
trap cleanup EXIT

cleanup
sleep 2

cp "$SETTINGS" /Users/tttksj/Documents/AirSim/settings.json

export WINEPREFIX
unset WINEDLLOVERRIDES
export WINEDEBUG='-all,err+all'

SIM_LOG="$TOOLS/logs/algo_${LABEL}.log"
STAMP="$(date +%Y%m%d_%H%M%S)"
BOT1_LOG="$OUT_DIR/${LABEL}_bot1_${STAMP}.log"
BOT2_LOG="$OUT_DIR/${LABEL}_bot2_${STAMP}.log"

(
  cd "$ASSETS"
  nohup "$WINEBIN" './Algo.exe' -nullrhi -nosound -unattended -ResX=640 -ResY=480 -windowed > "$SIM_LOG" 2>&1 &
)

SIM_READY=0
for _ in {1..90}; do
  if "$TOOLS/venv311/bin/python" - <<'PY' >/dev/null 2>&1
import msgpackrpc

try:
    client = msgpackrpc.Client(
        msgpackrpc.Address("127.0.0.1", 41451),
        timeout=1,
        pack_encoding="utf-8",
        unpack_encoding="utf-8",
    )
    raise SystemExit(0 if client.call("ping") else 1)
except Exception:
    raise SystemExit(1)
PY
  then
    SIM_READY=1
    break
  fi
  sleep 1
done
if [[ "$SIM_READY" != "1" ]]; then
  echo "[ExperimentError] simulator RPC did not become ready" >&2
  exit 1
fi
sleep 24

(
  cd "$BOT_DIR"
  PYTHONUNBUFFERED=1 "$TOOLS/venv311/bin/python" -u my_car.py
) | tee "$BOT1_LOG" &
BOT1_PID=$!

sleep 2

(
  cd "$BOT_DIR"
  PYTHONUNBUFFERED=1 "$TOOLS/venv311/bin/python" -u my_car.py
) | tee "$BOT2_LOG" &
BOT2_PID=$!

wait "$BOT1_PID" || true
wait "$BOT2_PID" || true

echo "[ExperimentLog] $BOT1_LOG"
echo "[ExperimentLog] $BOT2_LOG"
