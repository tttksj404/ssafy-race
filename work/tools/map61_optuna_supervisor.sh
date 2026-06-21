#!/usr/bin/env bash
# Self-healing supervisor for the map61 Optuna(TPE) loop.
# Resumes on crash (optuna.db SQLite persists all trials), stops on convergence (rc 0).
ROOT="/Users/tttksj/Desktop/ssafy-race"
PY="/Users/tttksj/Desktop/ssafy-race-tools/venv311/bin/python"
D="$ROOT/work/experiments/map61_autotune"
cd "$ROOT" || exit 1
mkdir -p "$D"
for i in $(seq 1 80); do
  echo "[optuna-sup] attempt $i start $(date '+%F %T')" >> "$D/supervisor.log"
  PYTHONUNBUFFERED=1 "$PY" -u work/tools/map61_optuna.py --patience 60 --trials 3000 >> "$D/loop_run.log" 2>&1
  rc=$?
  echo "[optuna-sup] attempt $i exited rc=$rc $(date '+%F %T')" >> "$D/supervisor.log"
  if [ "$rc" -eq 0 ]; then
    echo "[optuna-sup] converged -> stop" >> "$D/supervisor.log"
    break
  fi
  pkill -f 'my_car.py' 2>/dev/null
  pkill -f 'Algo.exe' 2>/dev/null
  sleep 5
done
echo "[optuna-sup] END $(date '+%F %T')" >> "$D/supervisor.log"
