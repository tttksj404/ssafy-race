#!/usr/bin/env python3
"""Actual simulator sweep for recovery profiles.

Some SSAFY Race maps are dominated by collision recovery at repeated obstacle
gates. The quick kinematic gate cannot model that well, so this runner promotes
a small set of recovery profiles directly to the simulator and aborts bad runs
early when collisions or penalties explode.
"""

import argparse
import json
import os
import re
import signal
import subprocess
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "work" / "experiments" / "map31_env_sweep"
TELEMETRY_RE = re.compile(
    r"progress=(?P<progress>[0-9.]+).*?"
    r"speed=(?P<speed>[-0-9.]+).*?"
    r"collisions=(?P<collisions>\d+).*?"
    r"penalties=(?P<penalties>\d+)"
)
EXPERIMENT_LOG_RE = re.compile(r"\[ExperimentLog\] (.+)")


def cleanup_simulator():
    subprocess.run(
        [
            "bash",
            "-lc",
            "pkill -f 'my_car.py|Algo-Win64-Shipping.exe|Algo.exe|wine-preloader|wineserver|winedevice.exe' >/dev/null 2>&1 || true",
        ],
        cwd=ROOT,
        check=False,
    )


def candidates():
    rows = [
        ("current_default", {}),
        ("old_recovery", {
            "SSAFY_RECOVERY_BACK_FRAMES": 8,
            "SSAFY_RECOVERY_BACK_THROTTLE": 0.75,
            "SSAFY_RECOVERY_BACK_STEER": 0.45,
            "SSAFY_RECOVERY_FORWARD_STEER": 0.55,
            "SSAFY_RECOVERY_FORWARD_FRAMES": 12,
            "SSAFY_RECOVERY_DONE_SPEED": 18,
        }),
        ("mild_6_070", {
            "SSAFY_RECOVERY_BACK_FRAMES": 6,
            "SSAFY_RECOVERY_BACK_THROTTLE": 0.65,
            "SSAFY_RECOVERY_BACK_STEER": 0.40,
            "SSAFY_RECOVERY_FORWARD_STEER": 0.70,
            "SSAFY_RECOVERY_FORWARD_FRAMES": 10,
            "SSAFY_RECOVERY_DONE_SPEED": 15,
        }),
        ("mild_5_075", {
            "SSAFY_RECOVERY_BACK_FRAMES": 5,
            "SSAFY_RECOVERY_BACK_THROTTLE": 0.60,
            "SSAFY_RECOVERY_BACK_STEER": 0.38,
            "SSAFY_RECOVERY_FORWARD_STEER": 0.75,
            "SSAFY_RECOVERY_FORWARD_FRAMES": 9,
            "SSAFY_RECOVERY_DONE_SPEED": 14,
        }),
        ("short_4_082", {
            "SSAFY_RECOVERY_BACK_FRAMES": 4,
            "SSAFY_RECOVERY_BACK_THROTTLE": 0.55,
            "SSAFY_RECOVERY_BACK_STEER": 0.35,
            "SSAFY_RECOVERY_FORWARD_STEER": 0.82,
            "SSAFY_RECOVERY_FORWARD_FRAMES": 8,
            "SSAFY_RECOVERY_DONE_SPEED": 12,
        }),
        ("fast_3_090", {
            "SSAFY_RECOVERY_BACK_FRAMES": 3,
            "SSAFY_RECOVERY_BACK_THROTTLE": 0.50,
            "SSAFY_RECOVERY_BACK_STEER": 0.30,
            "SSAFY_RECOVERY_FORWARD_STEER": 0.90,
            "SSAFY_RECOVERY_FORWARD_FRAMES": 7,
            "SSAFY_RECOVERY_DONE_SPEED": 10,
        }),
        ("long_9_050", {
            "SSAFY_RECOVERY_BACK_FRAMES": 9,
            "SSAFY_RECOVERY_BACK_THROTTLE": 0.75,
            "SSAFY_RECOVERY_BACK_STEER": 0.45,
            "SSAFY_RECOVERY_FORWARD_STEER": 0.50,
            "SSAFY_RECOVERY_FORWARD_FRAMES": 14,
            "SSAFY_RECOVERY_DONE_SPEED": 20,
        }),
    ]
    return rows


def score_log(path):
    if not path:
        return {"score": 999999.0, "finished": False, "error": "missing log path"}
    proc = subprocess.run(
        ["python3", "work/tools/score_logs.py", "--json", path],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if proc.returncode != 0:
        return {"score": 999999.0, "finished": False, "error": proc.stdout[-2000:]}
    return json.loads(proc.stdout)[0]


def should_abort(progress, collisions, penalties, wall_elapsed, slow_abort=True):
    if progress < 8 and penalties >= 8:
        return "early_penalty_explosion"
    if progress < 8 and collisions >= 18:
        return "early_collision_loop"
    if progress < 45 and collisions >= 28:
        return "mid_collision_loop"
    if progress < 60 and penalties >= 12:
        return "mid_penalty_explosion"
    if slow_abort and progress < 75 and wall_elapsed > 150:
        return "slow_progress"
    return ""


def run_candidate(name, env_values, timeout, map_index, prefix, verbose=False, slow_abort=True):
    cleanup_simulator()
    time.sleep(2)
    label = f"{prefix}sweep_{name}_{time.strftime('%Y%m%d_%H%M%S')}"
    env = os.environ.copy()
    env.update({"START_DELAY": "2"})
    env.update({key: str(value) for key, value in env_values.items()})

    proc = subprocess.Popen(
        ["./work/run_watch.sh", map_index, label],
        cwd=ROOT,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
    )

    started = time.time()
    log_path = ""
    max_progress = 0.0
    last_collisions = 0
    last_penalties = 0
    abort_reason = ""
    tail = []
    last_progress_print = -10

    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            tail.append(line.rstrip())
            tail = tail[-40:]
            log_match = EXPERIMENT_LOG_RE.search(line)
            if log_match:
                log_path = log_match.group(1).strip()

            telemetry = TELEMETRY_RE.search(line)
            if telemetry:
                progress = float(telemetry.group("progress"))
                collisions = int(telemetry.group("collisions"))
                penalties = int(telemetry.group("penalties"))
                max_progress = max(max_progress, progress)
                last_collisions = collisions
                last_penalties = penalties
                if verbose and progress >= last_progress_print + 10:
                    last_progress_print = int(progress // 10) * 10
                    print(
                        f"[RecoverySweepProgress] {prefix}:{name} progress={progress:.2f} "
                        f"collisions={collisions} penalties={penalties}",
                        flush=True,
                    )
                abort_reason = should_abort(
                    progress,
                    collisions,
                    penalties,
                    time.time() - started,
                    slow_abort=slow_abort,
                )
                if abort_reason:
                    proc.send_signal(signal.SIGINT)
                    break

            if time.time() - started > timeout:
                abort_reason = "timeout"
                proc.send_signal(signal.SIGINT)
                break
        try:
            proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            proc.kill()
    finally:
        if abort_reason:
            cleanup_simulator()

    parsed = score_log(log_path)
    parsed.update({
        "candidate": name,
        "aborted": bool(abort_reason),
        "abort_reason": abort_reason,
        "env": env_values,
        "max_progress_seen": round(max_progress, 2),
        "last_collisions_seen": last_collisions,
        "last_penalties_seen": last_penalties,
        "tail": tail[-12:],
    })
    return parsed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--map-index", default="05")
    parser.add_argument("--prefix", default="map31")
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--timeout", type=int, default=260)
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--no-slow-abort", action="store_true")
    args = parser.parse_args()

    subprocess.run(
        ["python3", "-m", "py_compile", "work/Template_Python/Bot_Python/my_car.py", "submissions/my_car.py"],
        cwd=ROOT,
        check=True,
    )

    rows = candidates()
    if args.start:
        rows = rows[args.start:]
    if args.limit:
        rows = rows[: args.limit]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    results = []
    for name, env_values in rows:
        result = run_candidate(
            name,
            env_values,
            args.timeout,
            args.map_index,
            args.prefix,
            verbose=args.verbose,
            slow_abort=not args.no_slow_abort,
        )
        results.append(result)
        print(json.dumps({
            "candidate": name,
            "finished": result.get("finished"),
            "elapsed": result.get("elapsed"),
            "score": result.get("score"),
            "aborted": result.get("aborted"),
            "abort_reason": result.get("abort_reason"),
            "max_progress_seen": result.get("max_progress_seen"),
            "collisions": result.get("collisions", result.get("last_collisions_seen")),
            "penalties": result.get("penalties", result.get("last_penalties_seen")),
        }, ensure_ascii=False, sort_keys=True))

    path = OUT_DIR / f"{args.prefix}_summary_{time.strftime('%Y%m%d_%H%M%S')}.json"
    path.write_text(json.dumps(results, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    print(f"[Map31SweepSummary] {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
