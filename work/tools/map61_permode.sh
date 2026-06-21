#!/usr/bin/env bash
# Per-mode EXTREME tuning: a SEPARATE optuna study per avoidance algorithm
# (AVOID_MODE fixed), each tuned to convergence, then compare per-mode champions.
# Resume-aware (skips DONE modes). CRASH-SAFE: only marks DONE on a genuine
# convergence (python rc 0). If all attempts crash (e.g. transient venv error),
# the driver EXITS non-zero so the monitor relaunches it and retries that mode
# (never falsely advances / writes CONVERGED).
ROOT="/Users/tttksj/Desktop/ssafy-race"
PY="/Users/tttksj/Desktop/ssafy-race-tools/venv311/bin/python"
D="$ROOT/work/experiments/map61_autotune"
MODES="orig visgraph ensemble"
cd "$ROOT" || exit 1
echo "[permode] START $(date '+%F %T')" >> "$D/permode.log"
for M in $MODES; do
  if [ -f "$D/DONE_${M}.flag" ]; then
    echo "[permode] $M already DONE, skip" >> "$D/permode.log"
    continue
  fi
  echo "[permode] >>> $M start $(date '+%F %T')" >> "$D/permode.log"
  converged=0
  for attempt in $(seq 1 20); do
    # sanity: python must actually launch (guards transient venv breakage)
    if ! "$PY" -c "pass" >/dev/null 2>&1; then
      echo "[permode] $M attempt $attempt: python not runnable, sleep 60" >> "$D/permode.log"
      sleep 60
      continue
    fi
    PYTHONUNBUFFERED=1 "$PY" -u work/tools/map61_optuna.py --mode "$M" --patience 12 --trials 200 >> "$D/permode_${M}.log" 2>&1
    rc=$?
    if [ "$rc" -eq 0 ]; then converged=1; break; fi
    echo "[permode] $M attempt $attempt: rc=$rc (crash), retry" >> "$D/permode.log"
    pkill -f 'my_car.py' 2>/dev/null; pkill -f 'Algo.exe' 2>/dev/null
    sleep 15
  done
  if [ "$converged" -ne 1 ]; then
    echo "[permode] $M FAILED all attempts -> exit so monitor relaunches & retries" >> "$D/permode.log"
    exit 1
  fi
  echo "DONE $M $(date '+%F %T')" > "$D/DONE_${M}.flag"
  echo "[permode] <<< $M DONE $(date '+%F %T')" >> "$D/permode.log"
done
echo "ALL_MODES_DONE $(date '+%F %T')" > "$D/CONVERGED.flag"
echo "[permode] ALL DONE $(date '+%F %T')" >> "$D/permode.log"
