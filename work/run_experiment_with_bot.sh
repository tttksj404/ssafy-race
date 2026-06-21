#!/usr/bin/env bash
set -euo pipefail

MAP_INDEX="${1:?map index required}"
LABEL="${2:?label required}"
BOT_SOURCE="${3:?bot source my_car.py required}"
ROOT="/Users/tttksj/Desktop/ssafy-race"
ASSETS="/Users/tttksj/Desktop/ssafy-race-assets/Simulator"
TOOLS="/Users/tttksj/Desktop/ssafy-race-tools"
BASE_BOT_DIR="$ROOT/work/Template_Python/Bot_Python"
RUN_BOT_DIR="$ROOT/work/tmp_bot_${LABEL}_$$"
SETTINGS="$ROOT/work/settings/settings_${MAP_INDEX}.json"
WINEBIN="/Users/tttksj/Applications/Wine Stable.app/Contents/Resources/wine/bin/wine"
WINEPREFIX="$TOOLS/wine-prefix-ssafy"
OUT_DIR="$ROOT/work/experiments"
mkdir -p "$OUT_DIR" "$TOOLS/logs" /Users/tttksj/Documents/AirSim "$RUN_BOT_DIR"

cleanup() {
  pkill -f 'my_car.py' >/dev/null 2>&1 || true
  pkill -f 'Algo-Win64-Shipping.exe' >/dev/null 2>&1 || true
  pkill -f './Algo.exe' >/dev/null 2>&1 || true
  rm -rf "$RUN_BOT_DIR"
}
trap cleanup EXIT

cp -R "$BASE_BOT_DIR/DrivingInterface" "$RUN_BOT_DIR/"
cp "$BOT_SOURCE" "$RUN_BOT_DIR/my_car.py"

pkill -f 'my_car.py' >/dev/null 2>&1 || true
pkill -f 'Algo-Win64-Shipping.exe' >/dev/null 2>&1 || true
pkill -f './Algo.exe' >/dev/null 2>&1 || true
sleep 2

cp "$SETTINGS" /Users/tttksj/Documents/AirSim/settings.json

export WINEPREFIX
unset WINEDLLOVERRIDES
export WINEDEBUG='-all,err+all'

SIM_LOG="$TOOLS/logs/algo_${LABEL}.log"
BOT_LOG="$OUT_DIR/${LABEL}_$(date +%Y%m%d_%H%M%S).log"

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
  cd "$RUN_BOT_DIR"
  PYTHONUNBUFFERED=1 "$TOOLS/venv311/bin/python" -u my_car.py
) | tee "$BOT_LOG"

pkill -f 'Algo-Win64-Shipping.exe' >/dev/null 2>&1 || true
pkill -f './Algo.exe' >/dev/null 2>&1 || true

echo "[ExperimentLog] $BOT_LOG"
