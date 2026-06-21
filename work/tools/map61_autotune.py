#!/usr/bin/env python3
"""Autonomous map61 stabilizer.

map61's apparent 242s record is fragile: re-running the *same* config 3x gave
256s / 536s / DNF -- the car drifts left (middle -6..-9) into the wall around
progress 35 and the GENERAL recovery (shared `SSAFY_RECOVERY_*`) is too weak
(reverses 8f then rams forward 12f at throttle 1.0), racking up hundreds of
collisions. Same failure class as map71, but on shared recovery knobs.

Because the failure is INTERMITTENT, every candidate is evaluated as the mean
of N_RUNS real runs -- a single lucky run must not win. Objective rewards
robustness (any DNF in the sample is heavily punished) then elapsed.

Tunes shared recovery knobs + map61-only P33 segment (the left-drift source).
Shared-knob winner MUST be validated on maps 10/31/161 before baking (done
separately, not in this loop).
"""

import argparse
import json
import os
import random
import re
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "work" / "run_experiment.sh"
SCORER = ROOT / "work" / "tools" / "score_logs.py"
MAP_SETTINGS_INDEX = "06"  # settings_06.json == Map 61
N_RUNS = 3                 # mean over runs (intermittent failure)
OUT_DIR = ROOT / "work" / "experiments" / "map61_autotune"
RESULTS = OUT_DIR / "results.jsonl"
CHAMPION = OUT_DIR / "champion.json"
STATUS = OUT_DIR / "STATUS.txt"

KNOBS = {
    # shared general recovery (affects all maps -> validate winner later)
    "SSAFY_RECOVERY_TRIGGER":        ("int", [3, 4, 5, 6, 8]),
    "SSAFY_RECOVERY_BACK_STEER":     ("float", [0.35, 0.45, 0.55, 0.65]),
    "SSAFY_RECOVERY_BACK_THROTTLE":  ("float", [0.6, 0.75, 0.9, 1.0]),
    "SSAFY_RECOVERY_BACK_FRAMES":    ("int", [6, 8, 10, 12, 14, 16, 20]),
    "SSAFY_RECOVERY_FORWARD_STEER":  ("float", [0.35, 0.45, 0.55, 0.7]),
    "SSAFY_RECOVERY_FORWARD_FRAMES": ("int", [3, 4, 6, 8, 12]),
    "SSAFY_RECOVERY_DONE_SPEED":     ("float", [12.0, 14.0, 18.0, 22.0]),
    # map61-only P33 segment (left-drift into wall ~progress 35)
    "SSAFY_MAP61_P33_TARGET_MIN":    ("float", [-1.4, -1.0, -0.5, 0.0]),
    "SSAFY_MAP61_P33_TARGET_MAX":    ("float", [0.0, 0.4, 1.0, 1.6]),
    "SSAFY_MAP61_P33_LEFT_CAP":      ("float", [-0.5, -0.42, -0.3, -0.2]),
    "SSAFY_MAP61_P33_STEER_SCALE":   ("float", [0.8, 0.88, 0.95, 1.0]),
    "SSAFY_MAP61_P33_MAX_DELTA":     ("float", [0.1, 0.14, 0.2]),
    # pre-corner speed cap (added knob): slow entry to prevent the left drift.
    # 999 = no cap (current behavior) so the search can opt out.
    "SSAFY_MAP61_P33_SPEED_CAP":     ("float", [100.0, 115.0, 130.0, 999.0]),
    # 60-70 segment (biggest time sink: ~37s, slowest+crashiest per lap profile).
    # The P64/P66 TARGET line override is gated by *_OVERRIDE_ENABLE (default
    # OFF) -- so those knobs were INERT until we let the search flip the enable.
    "SSAFY_MAP61_P64_TARGET_OVERRIDE_ENABLE": ("bool", ["0", "1"]),
    "SSAFY_MAP61_P64_TARGET_START":  ("float", [60.0, 61.5, 63.0, 63.6]),
    "SSAFY_MAP61_P64_TARGET_MIN":    ("float", [0.0, 0.4, 0.8, 1.2, 1.8]),
    "SSAFY_MAP61_P64_TARGET_MAX":    ("float", [2.6, 3.0, 3.4, 4.0]),
    "SSAFY_MAP61_P64_SHOVE_STEER":   ("float", [0.5, 0.6, 0.72, 0.85, 1.0]),
    "SSAFY_MAP61_P66_TARGET_OVERRIDE_ENABLE": ("bool", ["0", "1"]),
    "SSAFY_MAP61_P66_TARGET_MIN":    ("float", [-2.0, -1.2, -0.6, 0.0]),
    "SSAFY_MAP61_P66_TARGET_MAX":    ("float", [0.6, 1.2, 1.8, 2.4]),
    # newly-EXPOSED hardcoded racing lines through the 60-68 time-sink (were
    # fixed literals, no knob). Grids include the original literal (no regress).
    "SSAFY_MAP61_SEG5962_LANE_MIN":  ("float", [-3.5, -2.8, -2.2, -1.5, -0.8]),
    "SSAFY_MAP61_SEG5962_LANE_MAX":  ("float", [-1.5, -0.6, 0.5, 1.5]),
    "SSAFY_MAP61_SEG6365_LANE_MIN":  ("float", [0.5, 1.0, 1.6, 2.2]),
    "SSAFY_MAP61_SEG6365_LANE_MAX":  ("float", [2.0, 3.0, 4.0]),
    "SSAFY_MAP61_SEG6568_LANE_MIN":  ("float", [-5.0, -4.2, -3.4, -2.6]),
    "SSAFY_MAP61_SEG6568_LANE_MAX":  ("float", [-2.0, -1.0, 0.0, 1.0]),
    # AVOIDANCE LOGIC exploration (broad: which algorithm; deep: its params).
    "SSAFY_MAP61_AVOID_MODE":        ("cat", ["orig", "ftg", "nearest", "potential", "corridor", "kinematic", "arc", "visgraph", "ensemble"]),
    "SSAFY_MAP61_FTG_MARGIN":        ("float", [0.4, 0.6, 0.8, 1.0, 1.2]),
    "SSAFY_MAP61_OBSTACLE_PED":      ("float", [1.8, 2.25, 2.7, 3.2]),
    "SSAFY_MAP61_KIN_AY":            ("float", [6.0, 9.0, 13.0]),
    # crash-variance stabilizer (Round 2): commitment+deadband+TTC-brake on top
    # of the chosen mode. Default OFF so the seed reproduces baseline.
    "SSAFY_MAP61_STAB_ENABLE":       ("bool", ["0", "1"]),
    "SSAFY_MAP61_STAB_DEADBAND":     ("float", [0.5, 1.0, 1.5, 2.0]),
    "SSAFY_MAP61_STAB_TTC":          ("float", [0.4, 0.6, 0.9, 1.2]),
    "SSAFY_MAP61_STAB_BRAKE":        ("float", [50.0, 70.0, 90.0]),
}

# Seed: high-confidence recovery fix (shorter forward ram, trigger sooner,
# stronger reverse); P33 left default so the search explores it.
SEED = {
    "SSAFY_RECOVERY_TRIGGER": 4,
    "SSAFY_RECOVERY_BACK_STEER": 0.55,
    "SSAFY_RECOVERY_BACK_THROTTLE": 0.9,
    "SSAFY_RECOVERY_BACK_FRAMES": 10,
    "SSAFY_RECOVERY_FORWARD_STEER": 0.5,
    "SSAFY_RECOVERY_FORWARD_FRAMES": 4,
    "SSAFY_RECOVERY_DONE_SPEED": 14.0,
    "SSAFY_MAP61_P33_TARGET_MIN": -1.4,
    "SSAFY_MAP61_P33_TARGET_MAX": 0.4,
    "SSAFY_MAP61_P33_LEFT_CAP": -0.42,
    "SSAFY_MAP61_P33_STEER_SCALE": 0.88,
    "SSAFY_MAP61_P33_MAX_DELTA": 0.14,
    "SSAFY_MAP61_P33_SPEED_CAP": 130.0,
    "SSAFY_MAP61_P64_TARGET_OVERRIDE_ENABLE": "0",
    "SSAFY_MAP61_P64_TARGET_START": 63.6,
    "SSAFY_MAP61_P64_TARGET_MIN": 0.8,
    "SSAFY_MAP61_P64_TARGET_MAX": 3.4,
    "SSAFY_MAP61_P64_SHOVE_STEER": 0.72,
    "SSAFY_MAP61_P66_TARGET_OVERRIDE_ENABLE": "0",
    "SSAFY_MAP61_P66_TARGET_MIN": -1.2,
    "SSAFY_MAP61_P66_TARGET_MAX": 1.2,
    "SSAFY_MAP61_SEG5962_LANE_MIN": -2.2,
    "SSAFY_MAP61_SEG5962_LANE_MAX": -0.6,
    "SSAFY_MAP61_SEG6365_LANE_MIN": 1.6,
    "SSAFY_MAP61_SEG6365_LANE_MAX": 3.0,
    "SSAFY_MAP61_SEG6568_LANE_MIN": -4.2,
    "SSAFY_MAP61_SEG6568_LANE_MAX": -1.0,
    "SSAFY_MAP61_AVOID_MODE": "orig",
    "SSAFY_MAP61_FTG_MARGIN": 0.8,
    "SSAFY_MAP61_OBSTACLE_PED": 2.25,
    "SSAFY_MAP61_KIN_AY": 9.0,
    "SSAFY_MAP61_STAB_ENABLE": "0",
    "SSAFY_MAP61_STAB_DEADBAND": 1.0,
    "SSAFY_MAP61_STAB_TTC": 0.6,
    "SSAFY_MAP61_STAB_BRAKE": 70.0,
}


def fmt(env):
    out = {}
    for key, value in env.items():
        kind = KNOBS[key][0]
        if kind in ("bool", "cat"):
            out[key] = str(value)  # passed through verbatim (bool: "0"/"1")
        elif kind == "int":
            out[key] = str(int(value))
        else:
            out[key] = f"{float(value):g}"
    return out


def score_run(env, tag):
    """One real run -> (score, row). RETRIES transient FLICKER crashes (venv/FS
    PermissionError => no log, or a log with no 'finished return_code' line =>
    bot/sim crashed mid-run) instead of mis-scoring them as a genuine DNF, so the
    3-run mean reflects DRIVING, not flickers. A real DNF (log has
    'finished return_code=2') is scored normally, not retried."""
    proc_env = {**os.environ, **fmt(env)}
    for attempt in range(4):
        try:
            proc = subprocess.run(
                [str(RUNNER), MAP_SETTINGS_INDEX, f"m61at_{tag}"],
                cwd=str(ROOT), text=True, env=proc_env,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=1200,
            )
            out = proc.stdout
        except subprocess.TimeoutExpired as exc:
            out = exc.stdout if isinstance(getattr(exc, "stdout", None), str) else ""
        match = re.search(r"\[ExperimentLog\] (.+)", out or "")
        log_path = match.group(1).strip() if match else ""
        flicker = (not log_path) or (not Path(log_path).exists())
        if not flicker:
            try:
                if "finished return_code" not in Path(log_path).read_text(errors="replace"):
                    flicker = True  # crashed mid-run, not a genuine race outcome
            except Exception:
                flicker = True
        if flicker:
            subprocess.run(["pkill", "-f", "my_car.py"], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
            subprocess.run(["pkill", "-f", "Algo.exe"], stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
            if attempt < 3:
                time.sleep(20)
                continue
            return 100000.0, {"finished": False, "elapsed": None, "max_progress": 0.0,
                              "collisions": None, "log": log_path, "error": "flicker_x4"}
        scored = subprocess.run(["python3", str(SCORER), "--json", log_path],
                                cwd=str(ROOT), text=True, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT)
        try:
            row = json.loads(scored.stdout)[0]
        except Exception:
            return 100000.0, {"finished": False, "max_progress": 0.0, "log": log_path,
                              "error": "score parse"}
        prog = row.get("max_progress") or 0.0
        if row.get("finished"):
            score = (row.get("elapsed") or 999999.0) + (row.get("collisions") or 0) * 0.1
        else:
            score = 100000.0 - prog * 100.0
        return score, row


def evaluate(env, tag):
    """Mean of N_RUNS. Robustness: any DNF dominates the mean."""
    scores, rows = [], []
    for i in range(N_RUNS):
        subprocess.run(["pkill", "-f", "my_car.py"], stderr=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL)
        subprocess.run(["pkill", "-f", "Algo.exe"], stderr=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL)
        s, r = score_run(env, f"{tag}_r{i+1}")
        scores.append(s)
        rows.append({"fin": bool(r.get("finished")), "el": r.get("elapsed"),
                     "col": r.get("collisions"), "prog": r.get("max_progress")})
    finishes = sum(1 for r in rows if r["fin"])
    return {
        "score": round(sum(scores) / len(scores), 2),
        "worst": round(max(scores), 2),
        "finishes": finishes, "n": N_RUNS,
        "runs": rows,
    }


def mutate(env, rng):
    nxt = dict(env)
    for key in rng.sample(list(KNOBS), rng.randint(1, 3)):
        nxt[key] = rng.choice(KNOBS[key][1])
    return nxt


def write_status(eval_n, best, no_improve, last):
    b = best["result"]
    STATUS.write_text(
        f"evals={eval_n} no_improve={no_improve} runs_per_eval={N_RUNS}\n"
        f"BEST mean_score={b['score']} worst={b['worst']} finishes={b['finishes']}/{b['n']} "
        f"runs={json.dumps(b['runs'])}\n"
        f"best_env={json.dumps(fmt(best['env']))}\n"
        f"last_eval mean={last['score']} finishes={last['finishes']}/{last['n']}\n"
        f"updated={time.strftime('%Y-%m-%d %H:%M:%S')}\n",
        encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--patience", type=int, default=12)
    parser.add_argument("--max-evals", type=int, default=60)
    parser.add_argument("--seed", type=int, default=20260617)
    args = parser.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rng = random.Random(args.seed)

    if CHAMPION.exists():
        best = json.loads(CHAMPION.read_text(encoding="utf-8"))
        eval_n = sum(1 for _ in RESULTS.open()) if RESULTS.exists() else 0
        print(f"[resume] champion mean={best['result']['score']} evals_done={eval_n}")
    else:
        result = evaluate(SEED, "seed")
        eval_n = 1
        best = {"env": SEED, "result": result}
        CHAMPION.write_text(json.dumps(best, indent=2, sort_keys=True), encoding="utf-8")
        with RESULTS.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"eval": 1, "env": fmt(SEED), **result}, sort_keys=True) + "\n")
        print(f"[seed] mean={result['score']} finishes={result['finishes']}/{result['n']} "
              f"runs={result['runs']}")

    no_improve = 0
    while no_improve < args.patience and eval_n < args.max_evals:
        candidate = mutate(best["env"], rng)
        eval_n += 1
        result = evaluate(candidate, f"e{eval_n:03d}")
        with RESULTS.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"eval": eval_n, "env": fmt(candidate), **result},
                                sort_keys=True) + "\n")
        improved = result["score"] < best["result"]["score"]
        if improved:
            best = {"env": candidate, "result": result}
            CHAMPION.write_text(json.dumps(best, indent=2, sort_keys=True), encoding="utf-8")
            no_improve = 0
        else:
            no_improve += 1
        write_status(eval_n, best, no_improve, result)
        tail = "*BEST*" if improved else "(best=%s ni=%d)" % (best["result"]["score"], no_improve)
        print("[%d] mean=%s worst=%s fin=%d/%d %s" % (
            eval_n, result["score"], result["worst"], result["finishes"], result["n"], tail))

    b = best["result"]
    print(f"[done] evals={eval_n} converged_no_improve={no_improve} "
          f"BEST mean={b['score']} worst={b['worst']} finishes={b['finishes']}/{b['n']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
