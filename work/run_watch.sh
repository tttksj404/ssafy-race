#!/usr/bin/env bash
set -euo pipefail

MAP_INDEX="${1:-05}"
LABEL="${2:-watch_map${MAP_INDEX}}"
ROOT="/Users/tttksj/Desktop/ssafy-race"
ASSETS="/Users/tttksj/Desktop/ssafy-race-assets/Simulator"
TOOLS="/Users/tttksj/Desktop/ssafy-race-tools"
BOT_DIR="$ROOT/work/Template_Python/Bot_Python"
SETTINGS="$ROOT/work/settings/settings_${MAP_INDEX}.json"
WINEBIN="${WINEBIN:-/Applications/CrossOver.app/Contents/SharedSupport/CrossOver/bin/wine}"
CXBIN="/Applications/CrossOver.app/Contents/SharedSupport/CrossOver/bin"
CX_ROOT="/Applications/CrossOver.app/Contents/SharedSupport/CrossOver"
CROSSOVER_BOTTLE="${CROSSOVER_BOTTLE:-ssafy-race}"
WHISKY_CMD="/Users/tttksj/Applications/Whisky.app/Contents/Resources/WhiskyCmd"
WHISKY_BOTTLE="${WHISKY_BOTTLE:-ssafy-race}"
WINEPREFIX="$TOOLS/wine-prefix-ssafy"
OUT_DIR="$ROOT/work/experiments"
SNAPSHOT_ROOT="$OUT_DIR/snapshots"
mkdir -p "$OUT_DIR" "$SNAPSHOT_ROOT" "$TOOLS/logs" /Users/tttksj/Documents/AirSim

cleanup() {
  pkill -f 'my_car.py' >/dev/null 2>&1 || true
  if [[ "${KEEP_SIM:-0}" != "1" ]]; then
    pkill -f 'Algo-Win64-Shipping.exe' >/dev/null 2>&1 || true
    pkill -f './Algo.exe' >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

dismiss_start_overlay() {
  # The simulator can sit on the start/help overlay even after RPC is ready.
  # Give the Wine window focus and send the usual start/dismiss keys before
  # the bot connects so visual regression runs do not waste a full timeout.
  if [[ "${DISMISS_START_OVERLAY:-1}" != "1" ]]; then
    return 0
  fi
  osascript >/dev/null 2>&1 <<'APPLESCRIPT' || true
tell application "System Events"
  set targetProcess to missing value
  repeat with proc in processes
    if (name of proc contains "Algo") then
      set targetProcess to proc
      exit repeat
    end if
  end repeat
  if targetProcess is not missing value then
    set frontmost of targetProcess to true
    delay 0.1
    key code 49
    delay 0.05
    key code 36
  end if
end tell
APPLESCRIPT
}

pkill -f 'my_car.py' >/dev/null 2>&1 || true
pkill -f 'Algo-Win64-Shipping.exe' >/dev/null 2>&1 || true
pkill -f './Algo.exe' >/dev/null 2>&1 || true
if [[ "${USE_CROSSOVER:-1}" == "1" && "${KILL_WINESERVER:-1}" == "1" ]]; then
  pkill -f 'wineserver|wine-preloader' >/dev/null 2>&1 || true
fi
sleep 2

cp "$SETTINGS" /Users/tttksj/Documents/AirSim/settings.json

if [[ "${USE_CROSSOVER:-1}" == "1" ]]; then
  unset WINEPREFIX
  export CX_ROOT CX_GRAPHICS_BACKEND="${CX_GRAPHICS_BACKEND:-d3dmetal}"
  export WINED3DMETAL="${WINED3DMETAL:-1}" WINEDXVK="${WINEDXVK:-0}" WINEMSYNC="${WINEMSYNC:-1}"
  export WINEDLLOVERRIDES="${WINEDLLOVERRIDES:-d3d11,dxgi,d3d10core=b}"
else
  export WINEPREFIX
  unset WINEDLLOVERRIDES
fi
export WINEDEBUG='-all,err+all'

SIM_LOG="$TOOLS/logs/algo_${LABEL}.log"
RUN_STAMP="$(date +%Y%m%d_%H%M%S)"
BOT_LOG="$OUT_DIR/${LABEL}_${RUN_STAMP}.log"
SNAPSHOT_DIR="$SNAPSHOT_ROOT/${LABEL}_${RUN_STAMP}"
SIM_PID_FILE="$OUT_DIR/.${LABEL}.sim.pid"
rm -f "$SIM_PID_FILE"
mkdir -p "$SNAPSHOT_DIR"
cp "$BOT_DIR/my_car.py" "$SNAPSHOT_DIR/my_car.py"
cp "$SETTINGS" "$SNAPSHOT_DIR/settings.json"
{
  echo "label=$LABEL"
  echo "map_index=$MAP_INDEX"
  echo "run_stamp=$RUN_STAMP"
  echo "bot_log=$BOT_LOG"
  echo "sim_log=$SIM_LOG"
  shasum -a 256 "$BOT_DIR/my_car.py" "$SETTINGS"
} > "$SNAPSHOT_DIR/manifest.txt"
env | sort | grep -E '^(SSAFY_|START_DELAY=|USE_|KEEP_SIM=|KILL_WINESERVER=|CX_|WINE|CROSSOVER_|WHISKY_)' > "$SNAPSHOT_DIR/env.txt" || true

(
  cd "$ASSETS"
  if [[ "${USE_CROSSOVER:-1}" == "1" ]]; then
    if ! "$CXBIN/cxbottle" --bottle "$CROSSOVER_BOTTLE" --status >/dev/null 2>&1; then
      "$CXBIN/cxbottle" --bottle "$CROSSOVER_BOTTLE" --create --template win10_64 \
        --description 'SSAFY Race simulator GUI' >/dev/null
    fi
    if [[ "${DISABLE_LOCAL_DXVK:-1}" == "1" ]]; then
      for dll in d3d11.dll dxgi.dll d3d10core.dll; do
        if [[ -f "$ASSETS/Algo/Binaries/Win64/$dll" ]]; then
          mv "$ASSETS/Algo/Binaries/Win64/$dll" "$ASSETS/Algo/Binaries/Win64/$dll.bak_gui"
        fi
      done
    fi
    nohup "$WINEBIN" --bottle "$CROSSOVER_BOTTLE" "$ASSETS/Algo.exe" \
      -d3d11 -nohmd -NoSplash -nosound -ResX=1280 -ResY=720 -windowed > "$SIM_LOG" 2>&1 &
    echo $! > "$SIM_PID_FILE"
  elif [[ "${USE_WHISKY:-0}" == "1" && -x "$WHISKY_CMD" ]]; then
    eval "$("$WHISKY_CMD" shellenv "$WHISKY_BOTTLE")"
    nohup wine64 './Algo.exe' -NoSplash -ResX=1280 -ResY=720 -windowed > "$SIM_LOG" 2>&1 &
    echo $! > "$SIM_PID_FILE"
  else
    nohup "$WINEBIN" './Algo.exe' -NoSplash -ResX=1280 -ResY=720 -windowed > "$SIM_LOG" 2>&1 &
    echo $! > "$SIM_PID_FILE"
  fi
)
SIM_PID="$(cat "$SIM_PID_FILE" 2>/dev/null || true)"

SIM_READY=0
for _ in {1..240}; do
  if [[ -n "${SIM_PID:-}" ]] && ! kill -0 "$SIM_PID" >/dev/null 2>&1; then
    echo "[ExperimentError] simulator process exited before RPC became ready" >&2
    tail -80 "$SIM_LOG" >&2 || true
    exit 1
  fi
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
for _ in {1..6}; do
  dismiss_start_overlay
  sleep 0.35
done
sleep "${START_DELAY:-12}"
if ! "$TOOLS/venv311/bin/python" - <<'PY' >/dev/null 2>&1
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
  echo "[ExperimentError] simulator RPC disappeared before bot start" >&2
  tail -80 "$SIM_LOG" >&2 || true
  exit 1
fi

(
  cd "$BOT_DIR"
  PYTHONUNBUFFERED=1 "$TOOLS/venv311/bin/python" -u my_car.py
) | tee "$BOT_LOG"

echo "[ExperimentLog] $BOT_LOG"
echo "[ExperimentSnapshot] $SNAPSHOT_DIR"
