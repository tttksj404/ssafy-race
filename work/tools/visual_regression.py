#!/usr/bin/env python3
import argparse
import csv
import json
import math
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import cv2

ROOT = Path(__file__).resolve().parents[2]
BOT_DIR = ROOT / "work" / "Template_Python" / "Bot_Python"
RUN_WATCH = ROOT / "work" / "run_watch.sh"
CAPTURE = ROOT / "work" / "tools" / "capture_algo_window.py"
VIDEO_ROOT = ROOT / "work" / "videos" / "visual_regression"
RUN_ROOT = ROOT / "work" / "experiments" / "visual_regression"

sys.path.insert(0, str(ROOT / "work" / "tools"))
from score_logs import parse_log  # noqa: E402


MAPS = {
    "10": "00",
    "31": "05",
    "61": "06",
    "71": "07",
    "161": "03",
}


def run_quiet(cmd, **kwargs):
    return subprocess.run(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        **kwargs,
    )


def cleanup():
    patterns = [
        "my_car.py",
        "Algo-Win64-Shipping.exe",
        "./Algo.exe",
        "Algo.exe -d3d11",
        "winewrapper.exe",
        "wine-preloader",
        "wineserver",
    ]
    for pattern in patterns:
        run_quiet(["pkill", "-f", pattern], check=False)
    time.sleep(2.0)


def frames_to_video(frame_dir, out_path, fps):
    frames = sorted(frame_dir.glob("frame_*.jpg"))
    if not frames:
        return None
    out_path.parent.mkdir(parents=True, exist_ok=True)

    first = None
    good_frames = []
    for frame in frames:
        image = cv2.imread(str(frame))
        if image is None:
            continue
        if first is None:
            first = image
        good_frames.append(image)
    if first is None:
        return None

    height, width = first.shape[:2]
    writer = cv2.VideoWriter(
        str(out_path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        fps,
        (width, height),
    )
    if not writer.isOpened():
        return None
    for image in good_frames:
        if image.shape[:2] != (height, width):
            image = cv2.resize(image, (width, height), interpolation=cv2.INTER_AREA)
        writer.write(image)
    writer.release()
    return out_path


def make_contact_sheet(frame_dir, out_path, cols=4, max_frames=16):
    frames = sorted(frame_dir.glob("frame_*.jpg"))
    if not frames:
        return None
    if len(frames) > max_frames:
        step = max(1, len(frames) // max_frames)
        frames = frames[::step][:max_frames]
    images = []
    for path in frames:
        image = cv2.imread(str(path))
        if image is None:
            continue
        image = cv2.resize(image, (320, 180), interpolation=cv2.INTER_AREA)
        images.append(image)
    if not images:
        return None

    rows = math.ceil(len(images) / cols)
    blank = images[0] * 0
    while len(images) < rows * cols:
        images.append(blank.copy())
    grid_rows = []
    for row in range(rows):
        grid_rows.append(cv2.hconcat(images[row * cols : (row + 1) * cols]))
    sheet = cv2.vconcat(grid_rows)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out_path), sheet)
    return out_path


def newest_debug_csv(start_time):
    candidates = []
    for path in BOT_DIR.glob("debug_log_full*.csv"):
        try:
            if path.stat().st_mtime >= start_time - 1:
                candidates.append(path)
        except OSError:
            pass
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def sign(value):
    if value > 0:
        return 1
    if value < 0:
        return -1
    return 0


def analyze_debug_csv(path):
    if not path or not path.exists():
        return {"available": False, "verdict": "missing_csv", "failures": ["debug_csv_missing"]}

    with path.open(newline="", encoding="utf-8", errors="replace") as fp:
        rows = list(csv.DictReader(fp))
    if not rows:
        return {"available": False, "verdict": "empty_csv", "failures": ["debug_csv_empty"]}

    failures = []
    open_rows = []
    curve_rows = []
    far_brake = 0
    high_yaw = 0
    edge_overuse = 0
    high_speed_rows = 0
    prev_open_sign = 0
    open_sign_changes = 0

    for row in rows:
        try:
            speed = float(row.get("speed", 0) or 0)
            steer = float(row.get("steer", 0) or 0)
            throttle = float(row.get("throttle", 0) or 0)
            brake = float(row.get("brake", 0) or 0)
            middle = float(row.get("to_middle", 0) or 0)
            yaw = float(row.get("moving_angle", 0) or 0)
            half = max(1.0, float(row.get("half_road_limit", 10) or 10) - 1.5)
            nearest = float(row.get("nearest_ob_dist", 999) or 999)
            obs_cnt = int(float(row.get("obs_cnt", 0) or 0))
            angles = [float(row.get(f"ang_{i:02d}", 0) or 0) for i in range(10)]
        except (TypeError, ValueError):
            continue

        near_curve = sum(angles[:5]) / 5.0
        curve = sum(angles) / 10.0
        if speed > 85:
            high_speed_rows += 1
        if obs_cnt == 0 and abs(near_curve) < 4.0 and speed > 55:
            open_rows.append((speed, steer, throttle, brake))
            steer_sign = sign(steer)
            if steer_sign and prev_open_sign and steer_sign != prev_open_sign:
                open_sign_changes += 1
            if steer_sign:
                prev_open_sign = steer_sign
        if abs(curve) > 7.0 and speed > 45:
            curve_rows.append((curve, middle, half, brake, yaw))
        if nearest > 45 and brake > 0.55 and speed > 70:
            far_brake += 1
        if abs(yaw) > 48 and speed > 45:
            high_yaw += 1
        if abs(middle) / half > 1.18:
            edge_overuse += 1

    def avg(items, idx):
        return sum(item[idx] for item in items) / len(items) if items else 0.0

    open_avg_steer = avg([(abs(a[1]),) for a in open_rows], 0)
    open_avg_throttle = avg(open_rows, 2)
    open_avg_brake = avg(open_rows, 3)
    max_open_steer = max((abs(item[1]) for item in open_rows), default=0.0)

    inside_hits = 0
    for curve, middle, half, _brake, _yaw in curve_rows:
        curve_dir = sign(curve)
        if curve_dir and middle * curve_dir > half * 0.12:
            inside_hits += 1
    inside_ratio = inside_hits / len(curve_rows) if curve_rows else None
    curve_avg_brake = avg(curve_rows, 3)

    if open_rows:
        if open_avg_throttle < 0.82:
            failures.append(f"open_throttle_low:{open_avg_throttle:.3f}")
        if open_avg_brake > 0.18:
            failures.append(f"open_brake_high:{open_avg_brake:.3f}")
        if open_avg_steer > 0.13:
            failures.append(f"open_zigzag_avg_steer:{open_avg_steer:.3f}")
        if max_open_steer > 0.42:
            failures.append(f"open_zigzag_max_steer:{max_open_steer:.3f}")
        if open_sign_changes > max(5, len(open_rows) // 18):
            failures.append(f"open_steer_oscillation:{open_sign_changes}")
    if inside_ratio is not None and len(curve_rows) >= 8 and inside_ratio < 0.40:
        failures.append(f"corner_inside_ratio_low:{inside_ratio:.3f}")
    if curve_avg_brake > 0.42:
        failures.append(f"corner_brake_high:{curve_avg_brake:.3f}")
    if far_brake > max(3, len(rows) // 30):
        failures.append(f"far_obstacle_overbrake:{far_brake}")
    if high_yaw > max(4, len(rows) // 25):
        failures.append(f"yaw_breakdown:{high_yaw}")
    if edge_overuse > max(5, len(rows) // 22):
        failures.append(f"edge_overuse:{edge_overuse}")
    if high_speed_rows < max(8, len(rows) // 8):
        failures.append(f"high_speed_rows_low:{high_speed_rows}")

    return {
        "available": True,
        "verdict": "pass" if not failures else "fail",
        "failures": failures[:12],
        "metrics": {
            "rows": len(rows),
            "open_rows": len(open_rows),
            "open_avg_throttle": round(open_avg_throttle, 3),
            "open_avg_brake": round(open_avg_brake, 3),
            "open_avg_abs_steer": round(open_avg_steer, 3),
            "open_max_abs_steer": round(max_open_steer, 3),
            "open_steer_sign_changes": open_sign_changes,
            "curve_rows": len(curve_rows),
            "corner_inside_ratio": None if inside_ratio is None else round(inside_ratio, 3),
            "curve_avg_brake": round(curve_avg_brake, 3),
            "far_brake_frames": far_brake,
            "high_yaw_frames": high_yaw,
            "edge_overuse_frames": edge_overuse,
            "high_speed_rows": high_speed_rows,
        },
    }


def parse_experiment_log(stdout_path, label, start_time):
    text = stdout_path.read_text(encoding="utf-8", errors="replace") if stdout_path.exists() else ""
    matches = re.findall(r"\[ExperimentLog\]\s+(.+)", text)
    if matches:
        return Path(matches[-1].strip())
    candidates = []
    for path in (ROOT / "work" / "experiments").glob(f"{label}_*.log"):
        try:
            if path.stat().st_mtime >= start_time - 1:
                candidates.append(path)
        except OSError:
            pass
    candidates = sorted(candidates, key=lambda p: p.stat().st_mtime)
    return candidates[-1] if candidates else None


def run_map(map_name, args):
    map_index = MAPS.get(map_name, map_name)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    label = f"visual_map{map_name}_{stamp}"
    run_dir = RUN_ROOT / label
    frame_dir = VIDEO_ROOT / label / "frames"
    run_dir.mkdir(parents=True, exist_ok=True)
    frame_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = run_dir / "run_watch_stdout.log"
    capture_log_path = run_dir / "capture.log"

    cleanup()
    start_time = time.time()
    env = os.environ.copy()
    env["START_DELAY"] = str(args.start_delay)
    env["KILL_WINESERVER"] = "1"

    with stdout_path.open("w", encoding="utf-8") as stdout_fp:
        proc = subprocess.Popen(
            [str(RUN_WATCH), map_index, label],
            cwd=str(ROOT),
            stdout=stdout_fp,
            stderr=subprocess.STDOUT,
            env=env,
        )
        with capture_log_path.open("w", encoding="utf-8") as capture_fp:
            capture_proc = subprocess.Popen(
                [
                    sys.executable,
                    str(CAPTURE),
                    str(frame_dir),
                    "--duration",
                    str(args.capture_duration),
                    "--fps",
                    str(args.fps),
                    "--wait",
                    str(args.capture_wait),
                ],
                cwd=str(ROOT),
                stdout=capture_fp,
                stderr=subprocess.STDOUT,
            )

        timed_out = False
        try:
            proc.wait(timeout=args.timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            proc.terminate()
            time.sleep(3)
            if proc.poll() is None:
                proc.kill()

        try:
            capture_proc.wait(timeout=max(8, min(30, args.capture_duration + 5)))
        except subprocess.TimeoutExpired:
            capture_proc.terminate()
            time.sleep(1)
            if capture_proc.poll() is None:
                capture_proc.kill()

    experiment_log = parse_experiment_log(stdout_path, label, start_time)
    debug_csv = newest_debug_csv(start_time)
    video_path = frames_to_video(frame_dir, VIDEO_ROOT / label / f"{label}.mp4", args.fps)
    contact_path = make_contact_sheet(frame_dir, VIDEO_ROOT / label / "contact_sheet.jpg")
    score = parse_log(experiment_log) if experiment_log and experiment_log.exists() else None
    telemetry = analyze_debug_csv(debug_csv)

    cleanup()

    result = {
        "map": map_name,
        "map_index": map_index,
        "label": label,
        "timed_out": timed_out,
        "return_code": proc.returncode,
        "stdout": str(stdout_path),
        "capture_log": str(capture_log_path),
        "experiment_log": None if experiment_log is None else str(experiment_log),
        "debug_csv": None if debug_csv is None else str(debug_csv),
        "video": None if video_path is None else str(video_path),
        "contact_sheet": None if contact_path is None else str(contact_path),
        "score": score,
        "telemetry_verdict": telemetry,
    }
    (run_dir / "summary.json").write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--maps", nargs="+", default=["10", "31", "61", "71", "161"])
    parser.add_argument("--timeout", type=float, default=340.0)
    parser.add_argument("--capture-duration", type=float, default=45.0)
    parser.add_argument("--capture-wait", type=float, default=70.0)
    parser.add_argument("--fps", type=float, default=4.0)
    parser.add_argument("--start-delay", type=float, default=0.0)
    parser.add_argument("--json-out", default="")
    args = parser.parse_args()

    results = []
    for map_name in args.maps:
        result = run_map(str(map_name), args)
        results.append(result)
        print(json.dumps(result, indent=2, sort_keys=True), flush=True)

    summary = {
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "passed": all(
            (item.get("score") or {}).get("finished")
            and item.get("telemetry_verdict", {}).get("verdict") == "pass"
            for item in results
        ),
        "results": results,
    }
    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
