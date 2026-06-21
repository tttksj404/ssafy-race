#!/usr/bin/env python3
"""Actual simulator sweep for Map61 minimum-time candidates.

The quick gate is too weak for the 33% and 64-80% obstacle clusters, so this
runner uses the real simulator and aborts candidates that clearly enter a slow
collision loop. Candidates intentionally test wide/binary changes first.
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
OUT_DIR = ROOT / "work" / "experiments" / "map61_env_sweep"
TELEMETRY_RE = re.compile(
    r"progress=(?P<progress>[0-9.]+).*?"
    r"speed=(?P<speed>[-0-9.]+).*?"
    r"collisions=(?P<collisions>\d+).*?"
    r"penalties=(?P<penalties>\d+)"
)
EXPERIMENT_LOG_RE = re.compile(r"\[ExperimentLog\] (.+)")


def run(cmd, *, env=None, timeout=None):
    merged = os.environ.copy()
    if env:
        merged.update({key: str(value) for key, value in env.items()})
    return subprocess.run(
        cmd,
        cwd=ROOT,
        env=merged,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        check=False,
    )


def cleanup_simulator():
    run([
        "bash",
        "-lc",
        "pkill -f 'my_car.py|Algo-Win64-Shipping.exe|Algo.exe|wine-preloader|wineserver|winedevice.exe' >/dev/null 2>&1 || true",
    ])


def cleanup_artifacts():
    run([
        "bash",
        "-lc",
        "find work/videos work/screenshots -type f -delete 2>/dev/null\n"
        "find work/experiments/snapshots -mindepth 1 -maxdepth 1 -exec rm -rf {} + 2>/dev/null",
    ])


def candidates():
    return [
        ("baseline", {}),
        ("p33_medium_hard_on", {
            "SSAFY_MAP61_P33_TARGET_MIN": -2.4,
            "SSAFY_MAP61_P33_TARGET_MAX": 2.4,
            "SSAFY_MAP61_P33_MIDDLE_ADD_SCALE": 0.25,
            "SSAFY_MAP61_P33_STEER_SCALE": 0.94,
            "SSAFY_MAP61_P33_MAX_DELTA": 0.18,
            "SSAFY_MAP61_P33_HARD_ENABLE": 1,
        }),
        ("p33_wide_hard_on", {
            "SSAFY_MAP61_P33_TARGET_MIN": -3.6,
            "SSAFY_MAP61_P33_TARGET_MAX": 4.6,
            "SSAFY_MAP61_P33_MIDDLE_ADD_SCALE": 0.35,
            "SSAFY_MAP61_P33_STEER_SCALE": 1.0,
            "SSAFY_MAP61_P33_MAX_DELTA": 0.22,
            "SSAFY_MAP61_P33_HARD_ENABLE": 1,
        }),
        ("p33_wide_soft_hard", {
            "SSAFY_MAP61_P33_TARGET_MIN": -3.2,
            "SSAFY_MAP61_P33_TARGET_MAX": 3.8,
            "SSAFY_MAP61_P33_MIDDLE_ADD_SCALE": 0.32,
            "SSAFY_MAP61_P33_STEER_SCALE": 0.98,
            "SSAFY_MAP61_P33_MAX_DELTA": 0.20,
            "SSAFY_MAP61_P33_HARD_ENABLE": 1,
            "SSAFY_MAP61_P33_HARD_OUTER_STEER": -0.62,
            "SSAFY_MAP61_P33_HARD_INNER_STEER": -0.50,
        }),
        ("p33_medium_fast_recovery", {
            "SSAFY_MAP61_P33_TARGET_MIN": -2.4,
            "SSAFY_MAP61_P33_TARGET_MAX": 2.4,
            "SSAFY_MAP61_P33_MIDDLE_ADD_SCALE": 0.25,
            "SSAFY_MAP61_P33_STEER_SCALE": 0.94,
            "SSAFY_MAP61_P33_MAX_DELTA": 0.18,
            "SSAFY_MAP61_P33_HARD_ENABLE": 1,
            "SSAFY_RECOVERY_TRIGGER": 5,
            "SSAFY_RECOVERY_BACK_FRAMES": 3,
            "SSAFY_RECOVERY_BACK_THROTTLE": 0.50,
            "SSAFY_RECOVERY_BACK_STEER": 0.34,
            "SSAFY_RECOVERY_FORWARD_FRAMES": 7,
            "SSAFY_RECOVERY_FORWARD_STEER": 0.82,
            "SSAFY_RECOVERY_DONE_SPEED": 12,
        }),
        ("p33_medium_fast_recovery_p78_hold", {
            "SSAFY_MAP61_P33_TARGET_MIN": -2.4,
            "SSAFY_MAP61_P33_TARGET_MAX": 2.4,
            "SSAFY_MAP61_P33_MIDDLE_ADD_SCALE": 0.25,
            "SSAFY_MAP61_P33_STEER_SCALE": 0.94,
            "SSAFY_MAP61_P33_MAX_DELTA": 0.18,
            "SSAFY_MAP61_P33_HARD_ENABLE": 1,
            "SSAFY_RECOVERY_TRIGGER": 5,
            "SSAFY_RECOVERY_BACK_FRAMES": 3,
            "SSAFY_RECOVERY_BACK_THROTTLE": 0.50,
            "SSAFY_RECOVERY_BACK_STEER": 0.34,
            "SSAFY_RECOVERY_FORWARD_FRAMES": 7,
            "SSAFY_RECOVERY_FORWARD_STEER": 0.82,
            "SSAFY_RECOVERY_DONE_SPEED": 12,
            "SSAFY_MAP61_P78_RIGHT_HOLD_ENABLE": 1,
            "SSAFY_MAP61_P78_RIGHT_HOLD_STEER": 0.46,
        }),
        ("p33_medium_fast_recovery_p64_keep", {
            "SSAFY_MAP61_P33_TARGET_MIN": -2.4,
            "SSAFY_MAP61_P33_TARGET_MAX": 2.4,
            "SSAFY_MAP61_P33_MIDDLE_ADD_SCALE": 0.25,
            "SSAFY_MAP61_P33_STEER_SCALE": 0.94,
            "SSAFY_MAP61_P33_MAX_DELTA": 0.18,
            "SSAFY_MAP61_P33_HARD_ENABLE": 1,
            "SSAFY_RECOVERY_TRIGGER": 5,
            "SSAFY_RECOVERY_BACK_FRAMES": 3,
            "SSAFY_RECOVERY_BACK_THROTTLE": 0.50,
            "SSAFY_RECOVERY_BACK_STEER": 0.34,
            "SSAFY_RECOVERY_FORWARD_FRAMES": 7,
            "SSAFY_RECOVERY_FORWARD_STEER": 0.82,
            "SSAFY_RECOVERY_DONE_SPEED": 12,
            "SSAFY_MAP61_P64_RIGHT_KEEP_ENABLE": 1,
            "SSAFY_MAP61_P64_RIGHT_KEEP_STEER_MIN": -0.04,
        }),
        ("p33_medium_fast_recovery_p64_strict", {
            "SSAFY_MAP61_P33_TARGET_MIN": -2.4,
            "SSAFY_MAP61_P33_TARGET_MAX": 2.4,
            "SSAFY_MAP61_P33_MIDDLE_ADD_SCALE": 0.25,
            "SSAFY_MAP61_P33_STEER_SCALE": 0.94,
            "SSAFY_MAP61_P33_MAX_DELTA": 0.18,
            "SSAFY_MAP61_P33_HARD_ENABLE": 1,
            "SSAFY_RECOVERY_TRIGGER": 5,
            "SSAFY_RECOVERY_BACK_FRAMES": 3,
            "SSAFY_RECOVERY_BACK_THROTTLE": 0.50,
            "SSAFY_RECOVERY_BACK_STEER": 0.34,
            "SSAFY_RECOVERY_FORWARD_FRAMES": 7,
            "SSAFY_RECOVERY_FORWARD_STEER": 0.82,
            "SSAFY_RECOVERY_DONE_SPEED": 12,
            "SSAFY_MAP61_P64_RIGHT_KEEP_ENABLE": 1,
            "SSAFY_MAP61_P64_RIGHT_KEEP_STEER_MIN": 0.08,
        }),
        ("p33_medium_fast_recovery_p64_target_late", {
            "SSAFY_MAP61_P33_TARGET_MIN": -2.4,
            "SSAFY_MAP61_P33_TARGET_MAX": 2.4,
            "SSAFY_MAP61_P33_MIDDLE_ADD_SCALE": 0.25,
            "SSAFY_MAP61_P33_STEER_SCALE": 0.94,
            "SSAFY_MAP61_P33_MAX_DELTA": 0.18,
            "SSAFY_MAP61_P33_HARD_ENABLE": 1,
            "SSAFY_RECOVERY_TRIGGER": 5,
            "SSAFY_RECOVERY_BACK_FRAMES": 3,
            "SSAFY_RECOVERY_BACK_THROTTLE": 0.50,
            "SSAFY_RECOVERY_BACK_STEER": 0.34,
            "SSAFY_RECOVERY_FORWARD_FRAMES": 7,
            "SSAFY_RECOVERY_FORWARD_STEER": 0.82,
            "SSAFY_RECOVERY_DONE_SPEED": 12,
            "SSAFY_MAP61_P64_TARGET_OVERRIDE_ENABLE": 1,
            "SSAFY_MAP61_P64_TARGET_START": 63.6,
            "SSAFY_MAP61_P64_TARGET_END": 66.7,
            "SSAFY_MAP61_P64_TARGET_MIN": 1.4,
            "SSAFY_MAP61_P64_TARGET_MAX": 3.6,
        }),
        ("p33_medium_fast_recovery_p64_center_bridge", {
            "SSAFY_MAP61_P33_TARGET_MIN": -2.4,
            "SSAFY_MAP61_P33_TARGET_MAX": 2.4,
            "SSAFY_MAP61_P33_MIDDLE_ADD_SCALE": 0.25,
            "SSAFY_MAP61_P33_STEER_SCALE": 0.94,
            "SSAFY_MAP61_P33_MAX_DELTA": 0.18,
            "SSAFY_MAP61_P33_HARD_ENABLE": 1,
            "SSAFY_RECOVERY_TRIGGER": 5,
            "SSAFY_RECOVERY_BACK_FRAMES": 3,
            "SSAFY_RECOVERY_BACK_THROTTLE": 0.50,
            "SSAFY_RECOVERY_BACK_STEER": 0.34,
            "SSAFY_RECOVERY_FORWARD_FRAMES": 7,
            "SSAFY_RECOVERY_FORWARD_STEER": 0.82,
            "SSAFY_RECOVERY_DONE_SPEED": 12,
            "SSAFY_MAP61_P64_TARGET_OVERRIDE_ENABLE": 1,
            "SSAFY_MAP61_P64_TARGET_START": 63.6,
            "SSAFY_MAP61_P64_TARGET_END": 66.2,
            "SSAFY_MAP61_P64_TARGET_MIN": 0.2,
            "SSAFY_MAP61_P64_TARGET_MAX": 2.4,
            "SSAFY_MAP61_P66_TARGET_OVERRIDE_ENABLE": 1,
            "SSAFY_MAP61_P66_TARGET_START": 66.2,
            "SSAFY_MAP61_P66_TARGET_END": 68.6,
            "SSAFY_MAP61_P66_TARGET_MIN": -0.8,
            "SSAFY_MAP61_P66_TARGET_MAX": 1.2,
        }),
        ("p33_medium_fast_recovery_p64_left_soft", {
            "SSAFY_MAP61_P33_TARGET_MIN": -2.4,
            "SSAFY_MAP61_P33_TARGET_MAX": 2.4,
            "SSAFY_MAP61_P33_MIDDLE_ADD_SCALE": 0.25,
            "SSAFY_MAP61_P33_STEER_SCALE": 0.94,
            "SSAFY_MAP61_P33_MAX_DELTA": 0.18,
            "SSAFY_MAP61_P33_HARD_ENABLE": 1,
            "SSAFY_RECOVERY_TRIGGER": 5,
            "SSAFY_RECOVERY_BACK_FRAMES": 3,
            "SSAFY_RECOVERY_BACK_THROTTLE": 0.50,
            "SSAFY_RECOVERY_BACK_STEER": 0.34,
            "SSAFY_RECOVERY_FORWARD_FRAMES": 7,
            "SSAFY_RECOVERY_FORWARD_STEER": 0.82,
            "SSAFY_RECOVERY_DONE_SPEED": 12,
            "SSAFY_MAP61_P64_TARGET_OVERRIDE_ENABLE": 1,
            "SSAFY_MAP61_P64_TARGET_START": 63.6,
            "SSAFY_MAP61_P64_TARGET_END": 65.8,
            "SSAFY_MAP61_P64_TARGET_MIN": 1.0,
            "SSAFY_MAP61_P64_TARGET_MAX": 3.2,
            "SSAFY_MAP61_P66_TARGET_OVERRIDE_ENABLE": 1,
            "SSAFY_MAP61_P66_TARGET_START": 65.8,
            "SSAFY_MAP61_P66_TARGET_END": 68.6,
            "SSAFY_MAP61_P66_TARGET_MIN": -2.0,
            "SSAFY_MAP61_P66_TARGET_MAX": 0.4,
        }),
        ("p33_medium_fast_recovery_p78_strong", {
            "SSAFY_MAP61_P33_TARGET_MIN": -2.4,
            "SSAFY_MAP61_P33_TARGET_MAX": 2.4,
            "SSAFY_MAP61_P33_MIDDLE_ADD_SCALE": 0.25,
            "SSAFY_MAP61_P33_STEER_SCALE": 0.94,
            "SSAFY_MAP61_P33_MAX_DELTA": 0.18,
            "SSAFY_MAP61_P33_HARD_ENABLE": 1,
            "SSAFY_RECOVERY_TRIGGER": 5,
            "SSAFY_RECOVERY_BACK_FRAMES": 3,
            "SSAFY_RECOVERY_BACK_THROTTLE": 0.50,
            "SSAFY_RECOVERY_BACK_STEER": 0.34,
            "SSAFY_RECOVERY_FORWARD_FRAMES": 7,
            "SSAFY_RECOVERY_FORWARD_STEER": 0.82,
            "SSAFY_RECOVERY_DONE_SPEED": 12,
            "SSAFY_MAP61_P78_RIGHT_HOLD_ENABLE": 1,
            "SSAFY_MAP61_P78_RIGHT_HOLD_STEER": 0.70,
        }),
        ("p33_wide_hard_fast_recovery", {
            "SSAFY_MAP61_P33_TARGET_MIN": -3.6,
            "SSAFY_MAP61_P33_TARGET_MAX": 4.6,
            "SSAFY_MAP61_P33_MIDDLE_ADD_SCALE": 0.35,
            "SSAFY_MAP61_P33_STEER_SCALE": 1.0,
            "SSAFY_MAP61_P33_MAX_DELTA": 0.22,
            "SSAFY_MAP61_P33_HARD_ENABLE": 1,
            "SSAFY_RECOVERY_TRIGGER": 5,
            "SSAFY_RECOVERY_BACK_FRAMES": 3,
            "SSAFY_RECOVERY_BACK_THROTTLE": 0.50,
            "SSAFY_RECOVERY_BACK_STEER": 0.34,
            "SSAFY_RECOVERY_FORWARD_FRAMES": 7,
            "SSAFY_RECOVERY_FORWARD_STEER": 0.82,
            "SSAFY_RECOVERY_DONE_SPEED": 12,
        }),
        ("p33_open_short_recovery", {
            "SSAFY_MAP61_P33_TARGET_MIN": -3.6,
            "SSAFY_MAP61_P33_TARGET_MAX": 4.6,
            "SSAFY_MAP61_P33_MIDDLE_ADD_SCALE": 0.35,
            "SSAFY_MAP61_P33_STEER_SCALE": 1.0,
            "SSAFY_MAP61_P33_MAX_DELTA": 0.22,
            "SSAFY_MAP61_P33_HARD_ENABLE": 0,
            "SSAFY_RECOVERY_TRIGGER": 4,
            "SSAFY_RECOVERY_BACK_FRAMES": 2,
            "SSAFY_RECOVERY_BACK_THROTTLE": 0.42,
            "SSAFY_RECOVERY_BACK_STEER": 0.30,
            "SSAFY_RECOVERY_FORWARD_FRAMES": 6,
            "SSAFY_RECOVERY_FORWARD_STEER": 0.90,
            "SSAFY_RECOVERY_DONE_SPEED": 10,
        }),
    ]


def score_log(path):
    if not path:
        return {"score": 999999.0, "finished": False, "error": "missing log path"}
    proc = run(["python3", "work/tools/score_logs.py", "--json", path])
    if proc.returncode != 0:
        return {"score": 999999.0, "finished": False, "error": proc.stdout[-2000:]}
    return json.loads(proc.stdout)[0]


def find_log_for_label(label):
    matches = sorted((ROOT / "work" / "experiments").glob(f"{label}_*.log"))
    return str(matches[-1]) if matches else ""


def should_abort(progress, collisions, penalties, wall_elapsed):
    if 32.0 <= progress <= 37.0 and collisions >= 18:
        return "p33_collision_loop"
    if progress < 45 and collisions >= 28:
        return "early_collision_loop"
    if 63.0 <= progress <= 70.5 and collisions >= 22:
        return "p64_collision_loop"
    if 68.0 <= progress <= 81.0 and penalties >= 18:
        return "p70_80_penalty_explosion"
    if progress < 80 and wall_elapsed > 210:
        return "slow_progress"
    return ""


def run_candidate(name, env_values, timeout, verbose=False):
    cleanup_simulator()
    cleanup_artifacts()
    time.sleep(2)
    label = f"map61env_{name}_{time.strftime('%Y%m%d_%H%M%S')}"
    env = {"START_DELAY": "1"}
    env.update(env_values)
    merged = os.environ.copy()
    merged.update({key: str(value) for key, value in env.items()})

    proc = subprocess.Popen(
        ["./work/run_watch.sh", "06", label],
        cwd=ROOT,
        env=merged,
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
    last_progress_bucket = -10

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
            if verbose and progress >= last_progress_bucket + 10:
                last_progress_bucket = int(progress // 10) * 10
                print(
                    f"[Map61Progress] {name} progress={progress:.2f} "
                    f"collisions={collisions} penalties={penalties}",
                    flush=True,
                )
            abort_reason = should_abort(progress, collisions, penalties, time.time() - started)
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

    if not log_path:
        log_path = find_log_for_label(label)

    if abort_reason:
        cleanup_simulator()

    parsed = score_log(log_path)
    if not abort_reason and not parsed.get("finished"):
        abort_reason = "nonfinish_return"
    parsed.update({
        "candidate": name,
        "run_returncode": proc.returncode,
        "aborted": bool(abort_reason),
        "abort_reason": abort_reason,
        "log": log_path,
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
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--timeout", type=int, default=320)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    run(["python3", "-m", "py_compile", "work/Template_Python/Bot_Python/my_car.py", "submissions/my_car.py"], timeout=30)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    rows = candidates()
    if args.start:
        rows = rows[args.start:]
    if args.limit:
        rows = rows[: args.limit]

    results = []
    for name, env_values in rows:
        result = run_candidate(name, env_values, args.timeout, verbose=args.verbose)
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
            "log": result.get("log"),
        }, ensure_ascii=False, sort_keys=True), flush=True)

    summary = OUT_DIR / f"summary_{time.strftime('%Y%m%d_%H%M%S')}.json"
    summary.write_text(json.dumps(results, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    print(f"[Map61Summary] {summary}")
    cleanup_artifacts()


if __name__ == "__main__":
    raise SystemExit(main())
