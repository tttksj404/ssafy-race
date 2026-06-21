#!/usr/bin/env bash
# Self-healing supervisor for the map61 autotune loop.
# Resumes on crash (champion.json/results.jsonl persist), stops on convergence (rc 0).
ROOT="/Users/tttksj/Desktop/ssafy-race"
PY="/Users/tttksj/Desktop/ssafy-race-tools/venv311/bin/python"
D="$ROOT/work/experiments/map61_autotune"
cd "$ROOT" || exit 1
mkdir -p "$D"
for i in $(seq 1 80); do
  echo "[supervisor] attempt $i start $(date '+%F %T')" >> "$D/supervisor.log"
  PYTHONUNBUFFERED=1 "$PY" -u work/tools/map61_autotune.py --patience 12 --max-evals 60 >> "$D/loop_run.log" 2>&1
  rc=$?
  echo "[supervisor] attempt $i exited rc=$rc $(date '+%F %T')" >> "$D/supervisor.log"
  if [ "$rc" -eq 0 ]; then
    echo "[supervisor] converged -> stop" >> "$D/supervisor.log"
    break
  fi
  # crashed/killed -> clean stray sim and resume
  pkill -f 'my_car.py' 2>/dev/null
  pkill -f 'Algo.exe' 2>/dev/null
  sleep 5
done
echo "[supervisor] END $(date '+%F %T')" >> "$D/supervisor.log"
