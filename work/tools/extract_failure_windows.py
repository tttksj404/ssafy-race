#!/usr/bin/env python3
import argparse
import csv
import json
from pathlib import Path


def as_float(row, key, default=0.0):
    try:
        return float(row.get(key, default))
    except (TypeError, ValueError):
        return default


def as_int(row, key, default=0):
    try:
        return int(float(row.get(key, default)))
    except (TypeError, ValueError):
        return default


def bucket(progress, width):
    return round(int(progress / width) * width, 2)


def summarize_csv(path, bucket_width=1.0):
    rows = []
    with Path(path).open(newline="", errors="replace") as fp:
        reader = csv.DictReader(fp)
        for row in reader:
            lap = as_float(row, "lap_progress")
            if lap <= 0:
                continue
            rows.append(row)

    if not rows:
        return {"path": str(path), "rows": 0}

    windows = {}
    for row in rows:
        lap = as_float(row, "lap_progress")
        key = bucket(lap, bucket_width)
        item = windows.setdefault(
            key,
            {
                "progress": key,
                "frames": 0,
                "avg_speed": 0.0,
                "min_speed": 9999.0,
                "max_abs_middle": 0.0,
                "max_abs_yaw": 0.0,
                "max_abs_steer": 0.0,
                "brake_frames": 0,
                "collision_frames": 0,
                "recovery_frames": 0,
                "obstacle_frames": 0,
                "far_obstacle_brake": 0,
                "open_zigzag": 0,
                "inside_score": 0.0,
                "corner_frames": 0,
            },
        )
        speed = as_float(row, "speed")
        middle = as_float(row, "to_middle")
        yaw = as_float(row, "moving_angle")
        steer = as_float(row, "steer")
        brake = as_float(row, "brake")
        obs_cnt = as_int(row, "obs_cnt")
        nearest = as_float(row, "nearest_ob_dist", 1_000_000.0)
        collided = as_int(row, "collided")
        recovery = as_int(row, "recovery_steps")
        angles = [as_float(row, f"ang_{i:02d}") for i in range(12)]
        near_curve = sum(angles[:5]) / 5.0 if angles else 0.0
        far_curve = sum(angles[5:12]) / 7.0 if len(angles) >= 12 else near_curve
        curve_ref = near_curve if abs(near_curve) >= abs(far_curve) * 0.55 else far_curve

        item["frames"] += 1
        item["avg_speed"] += speed
        item["min_speed"] = min(item["min_speed"], speed)
        item["max_abs_middle"] = max(item["max_abs_middle"], abs(middle))
        item["max_abs_yaw"] = max(item["max_abs_yaw"], abs(yaw))
        item["max_abs_steer"] = max(item["max_abs_steer"], abs(steer))
        item["brake_frames"] += 1 if brake > 0.05 else 0
        item["collision_frames"] += collided
        item["recovery_frames"] += 1 if recovery > 0 else 0
        item["obstacle_frames"] += 1 if obs_cnt > 0 else 0
        item["far_obstacle_brake"] += 1 if obs_cnt > 0 and nearest > 55 and brake > 0.05 else 0
        item["open_zigzag"] += 1 if obs_cnt == 0 and abs(steer) > 0.22 and speed > 65 else 0
        if abs(curve_ref) >= 7.0:
            item["corner_frames"] += 1
            inside_sign = 1 if curve_ref > 0 else -1
            item["inside_score"] += 1.0 if middle * inside_sign > 1.0 else 0.0

    for item in windows.values():
        frames = max(item["frames"], 1)
        item["avg_speed"] = round(item["avg_speed"] / frames, 2)
        item["min_speed"] = round(item["min_speed"], 2)
        item["max_abs_middle"] = round(item["max_abs_middle"], 2)
        item["max_abs_yaw"] = round(item["max_abs_yaw"], 2)
        item["max_abs_steer"] = round(item["max_abs_steer"], 3)
        item["inside_ratio"] = round(item["inside_score"] / item["corner_frames"], 3) if item["corner_frames"] else None
        del item["inside_score"]

    ordered = list(windows.values())
    risk_rows = sorted(
        ordered,
        key=lambda x: (
            x["collision_frames"] * 80
            + x["recovery_frames"] * 30
            + max(0, x["max_abs_middle"] - 7.0) * 12
            + max(0, x["max_abs_yaw"] - 24.0) * 3
            + x["far_obstacle_brake"] * 5
            + x["open_zigzag"] * 4
            + max(0, 70.0 - x["avg_speed"]) * 2
        ),
        reverse=True,
    )
    slow_rows = sorted(ordered, key=lambda x: (x["avg_speed"], -x["frames"]))
    zigzag_rows = sorted(ordered, key=lambda x: (x["open_zigzag"], x["max_abs_steer"]), reverse=True)
    brake_rows = sorted(ordered, key=lambda x: (x["far_obstacle_brake"], x["brake_frames"]), reverse=True)
    inside_rows = sorted(
        [x for x in ordered if x["inside_ratio"] is not None],
        key=lambda x: (x["inside_ratio"], -x["corner_frames"]),
    )

    return {
        "path": str(path),
        "rows": len(rows),
        "max_progress": max(as_float(row, "lap_progress") for row in rows),
        "top_risk": risk_rows[:8],
        "slowest": slow_rows[:6],
        "open_zigzag": zigzag_rows[:6],
        "far_obstacle_brake": brake_rows[:6],
        "bad_inside": inside_rows[:6],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("csvs", nargs="+")
    parser.add_argument("--bucket", type=float, default=1.0)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    summaries = [summarize_csv(path, args.bucket) for path in args.csvs]
    if args.json:
        print(json.dumps(summaries, indent=2, ensure_ascii=False))
        return

    for summary in summaries:
        print(f"\n## {summary['path']}")
        print(f"rows={summary['rows']} max_progress={summary.get('max_progress')}")
        for section in ("top_risk", "slowest", "open_zigzag", "far_obstacle_brake", "bad_inside"):
            print(f"\n{section}:")
            for row in summary.get(section, []):
                print(json.dumps(row, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
