#!/usr/bin/env bash
PY="/Users/tttksj/Desktop/ssafy-race-tools/venv311/bin/python"
D="/Users/tttksj/Desktop/ssafy-race/work/experiments/general_tune"
cd /Users/tttksj/Desktop/ssafy-race || exit 1
for i in $(seq 1 80); do
  echo "[sup] attempt $i $(date '+%F %T')" >> "$D/sup.log"
  PYTHONUNBUFFERED=1 "$PY" -u work/tools/general_tune.py --patience 20 --trials 300 >> "$D/loop.log" 2>&1
  rc=$?
  [ "$rc" -eq 0 ] && { echo CONVERGED > "$D/CONVERGED.flag"; break; }
  pkill -f 'my_car.py' 2>/dev/null; pkill -f 'Algo.exe' 2>/dev/null; sleep 10
done
