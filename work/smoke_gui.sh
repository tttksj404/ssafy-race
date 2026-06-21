#!/usr/bin/env bash
set -euo pipefail

LABEL="${1:-gui_smoke}"
shift || true

ROOT="/Users/tttksj/Desktop/ssafy-race"
ASSETS="/Users/tttksj/Desktop/ssafy-race-assets/Simulator"
TOOLS="/Users/tttksj/Desktop/ssafy-race-tools"
WINEBIN="${WINEBIN:-/Users/tttksj/Applications/Wine Stable.app/Contents/Resources/wine/bin/wine}"
WINEPREFIX="${WINEPREFIX:-$TOOLS/wine-prefix-ssafy}"
SIM_LOG="$TOOLS/logs/algo_${LABEL}.log"
mkdir -p "$TOOLS/logs"

cleanup() {
  pkill -f 'Algo-Win64-Shipping.exe' >/dev/null 2>&1 || true
  pkill -f './Algo.exe' >/dev/null 2>&1 || true
}
trap cleanup EXIT

cleanup
sleep 1

if [[ -z "${CROSSOVER_BOTTLE:-}" ]]; then
  export WINEPREFIX
else
  unset WINEPREFIX
fi
if [[ -n "${WINEDLLOVERRIDES:-}" ]]; then
  export WINEDLLOVERRIDES
else
  unset WINEDLLOVERRIDES
fi
export WINEDEBUG='-all,err+all'

(
  cd "$ASSETS"
  cmd=("$WINEBIN")
  if [[ -n "${CROSSOVER_BOTTLE:-}" ]]; then
    cmd+=(--bottle "$CROSSOVER_BOTTLE")
    cmd+=("$ASSETS/Algo.exe" "$@")
  else
    cmd+=('./Algo.exe' "$@")
  fi
  nohup "${cmd[@]}" > "$SIM_LOG" 2>&1 &
)

for _ in {1..45}; do
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
    echo "READY $LABEL"
    exit 0
  fi
  sleep 1
done

echo "NOT_READY $LABEL"
tail -n 80 "$SIM_LOG" || true
exit 1
