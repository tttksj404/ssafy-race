#!/usr/bin/env python3
"""Autonomous map71 tuner.

Goal: make map71 *finish* (currently DNFs at ~38% by getting wedged between two
obstacles and ram-looping), then minimize finish time -- by sweeping the
map71-only `SSAFY_MAP71_*` env knobs. No edits to my_car.py during the loop;
the bot reads these knobs at runtime, so we just vary the environment, run the
headless simulator, and score the log.

Objective (lower = better):
  finished (rc=0): elapsed + collisions*0.5 + penalties*1.0   (~80-260)
  DNF:             100000 - max_progress*100                   (~89800-100000)
=> any finish ranks below any DNF; within a group, faster / further is better.

Search: greedy random-mutation hill climb from a strong seed. Each accepted
improvement replaces the champion. Stops after --patience non-improving evals
(convergence) or --max-evals, or when killed (state is on disk, resumable).
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
MAP_SETTINGS_INDEX = "07"  # settings_07.json == Map 71 (matches failing baseline)
OUT_DIR = ROOT / "work" / "experiments" / "map71_autotune"
RESULTS = OUT_DIR / "results.jsonl"
CHAMPION = OUT_DIR / "champion.json"
STATUS = OUT_DIR / "STATUS.txt"

# knob -> (kind, [candidate values]); first value is the conservative default.
KNOBS = {
    "SSAFY_MAP71_EMERGENCY_TRIGGER_FRAMES": ("int", [2, 3, 4, 5]),
    "SSAFY_MAP71_EMERGENCY_BACK_FRAMES":    ("int", [4, 6, 8, 10, 12, 16]),
    "SSAFY_MAP71_EMERGENCY_BACK_THROTTLE":  ("float", [0.5, 0.65, 0.8, 0.9, 1.0]),
    "SSAFY_MAP71_EMERGENCY_BACK_STEER":     ("float", [0.25, 0.4, 0.5, 0.65, 0.8]),
    "SSAFY_MAP71_EMERGENCY_FORWARD_FRAMES": ("int", [2, 3, 4, 5, 6]),
    "SSAFY_MAP71_EMERGENCY_FORWARD_STEER":  ("float", [0.4, 0.55, 0.7, 0.85]),
    "SSAFY_MAP71_EMERGENCY_SPEED":          ("float", [1.2, 2.0, 2.5, 3.5]),
    "SSAFY_MAP71_REACT_DIST_MIN":           ("float", [86.0, 100.0, 115.0, 130.0]),
    "SSAFY_MAP71_REACT_DIST_SCALE":         ("float", [0.86, 1.0, 1.1, 1.2]),
    "SSAFY_MAP71_OBSTACLE_PED":             ("float", [2.55, 3.0, 3.5, 4.0]),
    "SSAFY_MAP71_MIN_TARGET_SPEED":         ("float", [60.0, 70.0, 80.0]),
}

# Strong hypothesis seed: reverse longer & harder, ram-forward shorter, trigger
# sooner, react to obstacles a bit earlier so we avoid the pinch entirely.
SEED = {
    "SSAFY_MAP71_EMERGENCY_TRIGGER_FRAMES": 3,
    "SSAFY_MAP71_EMERGENCY_BACK_FRAMES": 8,
    "SSAFY_MAP71_EMERGENCY_BACK_THROTTLE": 0.85,
    "SSAFY_MAP71_EMERGENCY_BACK_STEER": 0.5,
    "SSAFY_MAP71_EMERGENCY_FORWARD_FRAMES": 3,
    "SSAFY_MAP71_EMERGENCY_FORWARD_STEER": 0.7,
    "SSAFY_MAP71_EMERGENCY_SPEED": 2.5,
    "SSAFY_MAP71_REACT_DIST_MIN": 100.0,
    "SSAFY_MAP71_REACT_DIST_SCALE": 1.0,
    "SSAFY_MAP71_OBSTACLE_PED": 3.0,
    "SSAFY_MAP71_MIN_TARGET_SPEED": 70.0,
}


def fmt(env):
    out = {}
    for key, value in env.items():
        kind = KNOBS[key][0]
        out[key] = str(int(value)) if kind == "int" else f"{float(value):g}"
    return out


def run_once(env, tag):
    label = f"m71at_{tag}"
    proc_env = {**os.environ, **fmt(env)}
    try:
        proc = subprocess.run(
            [str(RUNNER), MAP_SETTINGS_INDEX, label],
            cwd=str(ROOT), text=True, env=proc_env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=900,
        )
        out = proc.stdout
    except subprocess.TimeoutExpired as exc:
        out = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
    match = re.search(r"\[ExperimentLog\] (.+)", out)
    log_path = match.group(1).strip() if match else ""
    if not log_path or not Path(log_path).exists():
        return {"finished": False, "score": 100001.0, "max_progress": 0.0,
                "elapsed": None, "collisions": None, "penalties": None,
                "log": log_path, "error": "no log"}
    scored = subprocess.run(
        ["python3", str(SCORER), "--json", log_path],
        cwd=str(ROOT), text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )
    try:
        row = json.loads(scored.stdout)[0]
    except Exception:
        return {"finished": False, "score": 100002.0, "max_progress": 0.0,
                "log": log_path, "error": "score parse"}
    prog = row.get("max_progress") or 0.0
    if row.get("finished"):
        # Grader scores elapsed only (score_logs.py). Tiny collision weight is a
        # near-neutral robustness tiebreak (fewer collisions => less fragile),
        # negligible vs elapsed gaps. Penalties are not graded -> excluded.
        score = (row.get("elapsed") or 999999.0) + (row.get("collisions") or 0) * 0.1
    else:
        score = 100000.0 - prog * 100.0
    return {
        "finished": bool(row.get("finished")),
        "score": round(score, 3),
        "elapsed": row.get("elapsed"),
        "max_progress": prog,
        "collisions": row.get("collisions"),
        "penalties": row.get("penalties"),
        "log": log_path,
    }


def mutate(env, rng):
    nxt = dict(env)
    for key in rng.sample(list(KNOBS), rng.randint(1, 3)):
        nxt[key] = rng.choice(KNOBS[key][1])
    return nxt


def write_status(eval_n, best, no_improve, current):
    STATUS.write_text(
        f"evals={eval_n} no_improve={no_improve}\n"
        f"BEST score={best['result']['score']} finished={best['result']['finished']} "
        f"elapsed={best['result']['elapsed']} progress={best['result']['max_progress']} "
        f"collisions={best['result']['collisions']} penalties={best['result']['penalties']}\n"
        f"best_env={json.dumps(fmt(best['env']))}\n"
        f"last_eval_score={current}\n"
        f"updated={time.strftime('%Y-%m-%d %H:%M:%S')}\n",
        encoding="utf-8",
    )


def append_result(eval_n, env, result):
    with RESULTS.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"eval": eval_n, "env": fmt(env), **result}, sort_keys=True) + "\n")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--patience", type=int, default=30)
    parser.add_argument("--max-evals", type=int, default=400)
    parser.add_argument("--seed", type=int, default=20260617)
    parser.add_argument("--once", default="", help="KEY=VAL,KEY=VAL single run (smoke test)")
    args = parser.parse_args()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rng = random.Random(args.seed)

    if args.once:
        env = dict(SEED)
        if args.once != "seed":
            for pair in args.once.split(","):
                k, v = pair.split("=")
                k = k.strip()
                env[k] = float(v) if KNOBS[k][0] == "float" else int(v)
        result = run_once(env, "smoke")
        print(json.dumps({"env": fmt(env), **result}, sort_keys=True))
        return 0

    # Resume champion if present, else start from seed.
    if CHAMPION.exists():
        best = json.loads(CHAMPION.read_text(encoding="utf-8"))
        eval_n = sum(1 for _ in RESULTS.open()) if RESULTS.exists() else 0
        print(f"[resume] champion score={best['result']['score']} evals_done={eval_n}")
    else:
        result = run_once(SEED, "seed")
        eval_n = 1
        best = {"env": SEED, "result": result}
        CHAMPION.write_text(json.dumps(best, indent=2, sort_keys=True), encoding="utf-8")
        append_result(eval_n, SEED, result)
        print(f"[seed] score={result['score']} finished={result['finished']} "
              f"progress={result['max_progress']} elapsed={result['elapsed']}")

    no_improve = 0
    while no_improve < args.patience and eval_n < args.max_evals:
        candidate = mutate(best["env"], rng)
        eval_n += 1
        result = run_once(candidate, f"e{eval_n:04d}")
        append_result(eval_n, candidate, result)
        improved = result["score"] < best["result"]["score"]
        if improved:
            best = {"env": candidate, "result": result}
            CHAMPION.write_text(json.dumps(best, indent=2, sort_keys=True), encoding="utf-8")
            no_improve = 0
        else:
            no_improve += 1
        write_status(eval_n, best, no_improve, result["score"])
        tail = "*BEST*" if improved else "(best=%s ni=%d)" % (best["result"]["score"], no_improve)
        print("[%d] score=%s fin=%s prog=%s el=%s %s" % (
            eval_n, result["score"], result["finished"],
            result["max_progress"], result["elapsed"], tail))

    print(f"[done] evals={eval_n} converged_no_improve={no_improve} "
          f"BEST score={best['result']['score']} finished={best['result']['finished']} "
          f"elapsed={best['result']['elapsed']} progress={best['result']['max_progress']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
