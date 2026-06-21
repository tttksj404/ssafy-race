#!/usr/bin/env bash
# Hardened meta-monitor for PER-MODE extreme tuning, with an INTEGRITY GUARD so
# the venv-flicker bogus-DONE bug cannot corrupt results:
#   - a DONE_<mode>.flag is only trusted if optuna_<mode>.db exists & is non-trivial
#     (a real converged study is tens of KB; a flicker-crashed one has no db).
#   - a bogus DONE is removed so the mode re-runs.
#   - CONVERGED.flag is only honored when ALL modes have a VALID DONE.
# Keeps the per-mode driver + caffeinate alive. Token-free, file-based (no python
# needed, so the guard itself survives venv flickers).
ROOT="/Users/tttksj/Desktop/ssafy-race"
D="$ROOT/work/experiments/map61_autotune"
HB="$D/monitor_heartbeat.log"
MODES="orig visgraph ensemble"
MINDB=20000   # bytes; a real per-mode study db is well above this
cd "$ROOT" || exit 1

valid_done() {  # $1=mode ; 0 if DONE flag present AND db looks real
  [ -f "$D/DONE_$1.flag" ] || return 1
  local db="$D/optuna_$1.db"
  [ -f "$db" ] || return 1
  local sz; sz=$(stat -f%z "$db" 2>/dev/null || echo 0)
  [ "$sz" -ge "$MINDB" ]
}

echo "[monitor] START(hardened per-mode) $(date '+%F %T')" >> "$HB"
while true; do
  # 1) mac awake
  pgrep -f 'caffeinate -dimsu' >/dev/null || { nohup caffeinate -dimsu >/dev/null 2>&1 & disown; }

  # 2) INTEGRITY GUARD: drop any bogus DONE (flag present but db missing/tiny)
  for M in $MODES; do
    if [ -f "$D/DONE_$M.flag" ] && ! valid_done "$M"; then
      rm -f "$D/DONE_$M.flag"
      echo "[monitor] integrity: removed BOGUS DONE_$M (db missing/empty) $(date '+%F %T')" >> "$HB"
    fi
  done

  # 3) honor CONVERGED only if ALL modes have a valid DONE; else it's bogus
  if [ -f "$D/CONVERGED.flag" ]; then
    allok=1
    for M in $MODES; do valid_done "$M" || allok=0; done
    if [ "$allok" -eq 1 ]; then
      echo "[monitor] ALL MODES validly DONE $(date '+%F %T')" >> "$HB"
      break
    else
      rm -f "$D/CONVERGED.flag"
      echo "[monitor] integrity: removed BOGUS CONVERGED.flag $(date '+%F %T')" >> "$HB"
    fi
  fi

  # 4) keep the resume-aware per-mode driver alive
  if ! pgrep -f map61_permode.sh >/dev/null; then
    nohup "$ROOT/work/tools/map61_permode.sh" >/dev/null 2>&1 & disown
    echo "[monitor] per-mode driver (re)launched $(date '+%F %T')" >> "$HB"
  fi

  # 5) heartbeat
  DONE=$(for M in $MODES; do valid_done "$M" && printf '%s ' "$M"; done)
  CUR=$(ls -t "$D"/STATUS_*.txt 2>/dev/null | head -1)
  echo "$(date '+%F %T') DONE:[$DONE] | $(basename ${CUR:-none}): $(head -1 ${CUR:-/dev/null} 2>/dev/null)" >> "$HB"

  sleep 300
done
echo "[monitor] END $(date '+%F %T')" >> "$HB"
