#!/usr/bin/env python3
import argparse
import json
import math
import random
import sys
import time
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BOT_DIR = ROOT / "work" / "Template_Python" / "Bot_Python"
sys.path.insert(0, str(BOT_DIR))

# The stress harness calls only DrivingClient.control_driving(). Stub the
# simulator-facing base class so this can run without AirSim/msgpackrpc.
drive_controller_mod = types.ModuleType("DrivingInterface.drive_controller")


class DrivingController:
    def set_enable_api_control(self, enabled):
        self.enable_api_control = enabled


drive_controller_mod.DrivingController = DrivingController
package_mod = types.ModuleType("DrivingInterface")
package_mod.drive_controller = drive_controller_mod
sys.modules.setdefault("DrivingInterface", package_mod)
sys.modules["DrivingInterface.drive_controller"] = drive_controller_mod

from my_car import DrivingClient  # noqa: E402


class Bag:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def clamp(value, low, high):
    return max(low, min(high, value))


def sign(value):
    if value > 0:
        return 1
    if value < 0:
        return -1
    return 0


def make_client(map_num, prev_steering):
    client = DrivingClient.__new__(DrivingClient)
    client.is_debug = False
    client.enable_api_control = True
    client.prev_steering = prev_steering
    client.prev_progress = 3.0
    client.stuck_count = 0
    client.recovery_count = 0
    client.last_target_middle = 0.0
    client.map_num = str(map_num)
    client.half_road_limit = 10.0
    return client


def alternating_angles(rng, curve_type):
    if curve_type == "straight":
        base = rng.uniform(-2.0, 2.0)
        return [base + rng.uniform(-1.0, 1.0) for _ in range(20)]
    if curve_type == "sweep_left":
        return [clamp(4 + i * 2.8 + rng.uniform(-2, 2), -80, 80) for i in range(20)]
    if curve_type == "sweep_right":
        return [clamp(-4 - i * 2.8 + rng.uniform(-2, 2), -80, 80) for i in range(20)]
    if curve_type == "hairpin_left":
        return [clamp(18 + i * 4.0 + rng.uniform(-4, 4), -85, 85) for i in range(20)]
    if curve_type == "hairpin_right":
        return [clamp(-18 - i * 4.0 + rng.uniform(-4, 4), -85, 85) for i in range(20)]
    return [rng.uniform(-48.0, 48.0) for _ in range(20)]


def pattern_obstacles(rng, pattern, road_limit):
    if pattern == "empty":
        return []
    if pattern == "single_center_near":
        return [{"dist": rng.uniform(8, 22), "to_middle": rng.uniform(-1.2, 1.2)}]
    if pattern == "single_current_lane":
        return []
    if pattern == "side_by_side_gap":
        gap_side = rng.choice([-1, 1])
        dist = rng.uniform(16, 42)
        return [
            {"dist": dist, "to_middle": -gap_side * road_limit * 0.42},
            {"dist": dist + rng.uniform(-2, 2), "to_middle": 0.0},
            {"dist": dist + rng.uniform(-2, 2), "to_middle": gap_side * road_limit * 0.76},
        ]
    if pattern == "slalom":
        return [
            {
                "dist": 14 + i * rng.uniform(12, 21),
                "to_middle": ((-1) ** i) * rng.uniform(road_limit * 0.15, road_limit * 0.58),
            }
            for i in range(rng.randint(4, 7))
        ]
    if pattern == "edge_trap":
        side = rng.choice([-1, 1])
        return [
            {"dist": rng.uniform(10, 22), "to_middle": side * road_limit * 0.70},
            {"dist": rng.uniform(22, 45), "to_middle": side * road_limit * 0.38},
        ]
    if pattern == "dense_cluster":
        base_dist = rng.uniform(10, 34)
        center = rng.uniform(-road_limit * 0.42, road_limit * 0.42)
        return [
            {
                "dist": base_dist + rng.uniform(-5, 26),
                "to_middle": clamp(center + rng.uniform(-5.5, 5.5), -road_limit * 0.88, road_limit * 0.88),
            }
            for _ in range(rng.randint(4, 8))
        ]
    if pattern == "wall_gap":
        gap = rng.choice([-0.68, -0.34, 0.0, 0.34, 0.68]) * road_limit
        dist = rng.uniform(18, 46)
        lanes = [-0.70, -0.35, 0.0, 0.35, 0.70]
        return [
            {"dist": dist + rng.uniform(-2, 2), "to_middle": lane * road_limit}
            for lane in lanes
            if abs(lane * road_limit - gap) > road_limit * 0.18
        ]
    return []


def make_opponents(rng, mode, road_limit, to_middle):
    if mode == "none":
        return []
    if mode == "side_same":
        return [{"dist": rng.uniform(-4, 16), "to_middle": clamp(to_middle + rng.uniform(-1.4, 1.4), -road_limit, road_limit)}]
    if mode == "side_other":
        return [{"dist": rng.uniform(-4, 16), "to_middle": clamp(-to_middle + rng.uniform(-1.4, 1.4), -road_limit, road_limit)}]
    return [
        {"dist": rng.uniform(8, 45), "to_middle": rng.uniform(-road_limit * 0.75, road_limit * 0.75)}
        for _ in range(rng.randint(1, 3))
    ]


def min_relevant_obstacle_gap(obstacles, to_middle):
    nearest = None
    for obs in obstacles:
        dist = float(obs["dist"])
        gap = abs(float(obs["to_middle"]) - to_middle)
        if 0 < dist < 24 and gap < 4.5:
            if nearest is None or dist < nearest[0]:
                nearest = (dist, gap)
    return nearest


def evaluate(case, controls):
    findings = []
    road_limit = case["road_limit"]
    to_middle = case["to_middle"]
    speed = case["speed"]
    steering = controls.steering
    throttle = controls.throttle
    brake = controls.brake

    values = [steering, throttle, brake]
    if any(not math.isfinite(value) for value in values):
        findings.append(("hard", "non_finite_control"))
    if not -1.0 <= steering <= 1.0:
        findings.append(("hard", "steering_out_of_range"))
    if not -1.0 <= throttle <= 1.0:
        findings.append(("hard", "throttle_out_of_range"))
    if not 0.0 <= brake <= 1.0:
        findings.append(("hard", "brake_out_of_range"))

    edge_ratio = abs(to_middle) / max(road_limit, 1.0)
    inward = -sign(to_middle)
    if edge_ratio > 0.88 and speed > 35 and inward and steering * inward < -0.38:
        findings.append(("hard", "hard_outward_at_edge"))
    elif edge_ratio > 0.72 and speed > 65 and inward and steering * inward < -0.18:
        findings.append(("warn", "weak_edge_return"))

    nearest = min_relevant_obstacle_gap(case["obstacles"], to_middle)
    if nearest is not None:
        dist, gap = nearest
        if speed > 38 and brake < 0.18 and abs(steering) < 0.10:
            findings.append(("hard", "near_obstacle_no_reaction"))
        if dist < 14 and speed > 48 and brake < 0.45:
            findings.append(("warn", "late_braking_near_obstacle"))

    if abs(case["moving_angle"]) > 45 and speed > 55 and throttle > 0.55 and brake < 0.30:
        findings.append(("warn", "bad_heading_keeps_speed"))

    side_opponent = any(-8 < car["dist"] < 18 and abs(car["to_middle"] - to_middle) < 2.4 for car in case["opponents"])
    if side_opponent and speed > 45 and throttle > 0.55 and brake < 0.20:
        findings.append(("warn", "side_opponent_too_aggressive"))

    return findings


def build_case(rng, map_num, index):
    half_limit = rng.choice([7.2, 8.4, 10.0, 11.8])
    road_limit = max(2.5, half_limit - 1.7)
    to_middle = rng.uniform(-road_limit * 0.98, road_limit * 0.98)
    speed = rng.choice([0, 8, 18, 32, 48, 68, 88, 110, 132]) + rng.uniform(-3.0, 3.0)
    speed = max(0.0, speed)
    moving_angle = rng.choice([-72, -48, -28, -12, 0, 12, 28, 48, 72]) + rng.uniform(-5, 5)
    curve_type = rng.choice(["straight", "sweep_left", "sweep_right", "hairpin_left", "hairpin_right", "random"])
    pattern = rng.choice([
        "empty",
        "single_center_near",
        "single_current_lane",
        "side_by_side_gap",
        "slalom",
        "edge_trap",
        "dense_cluster",
        "wall_gap",
    ])
    obstacles = pattern_obstacles(rng, pattern, road_limit)
    if pattern == "single_current_lane":
        obstacles = [{"dist": rng.uniform(7, 24), "to_middle": clamp(to_middle + rng.uniform(-1.8, 1.8), -road_limit, road_limit)}]
    opponents = make_opponents(rng, rng.choice(["none", "none", "side_same", "side_other", "pack"]), road_limit, to_middle)
    progress = rng.uniform(1.3, 98.0)

    return {
        "id": index,
        "map": str(map_num),
        "half_limit": half_limit,
        "road_limit": road_limit,
        "to_middle": to_middle,
        "speed": speed,
        "moving_angle": moving_angle,
        "curve_type": curve_type,
        "pattern": pattern,
        "angles": alternating_angles(rng, curve_type),
        "obstacles": obstacles,
        "opponents": opponents,
        "progress": progress,
        "prev_steering": rng.choice([-0.65, -0.25, 0.0, 0.25, 0.65]),
    }


def run_case(case):
    client = make_client(case["map"], case["prev_steering"])
    controls = Bag(steering=0.0, throttle=0.0, brake=0.0)
    sensing = Bag(
        to_middle=case["to_middle"],
        collided=False,
        speed=case["speed"],
        moving_forward=True,
        moving_angle=case["moving_angle"],
        lap_progress=case["progress"],
        track_forward_angles=case["angles"],
        track_forward_obstacles=case["obstacles"],
        opponent_cars_info=case["opponents"],
        distance_to_way_points=[10.0 for _ in range(20)],
        half_road_limit=case["half_limit"],
    )
    out = client.control_driving(controls, sensing)
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", type=int, default=20000)
    parser.add_argument("--seed", type=int, default=20260612)
    parser.add_argument("--maps", default="10,31,61,71,161")
    parser.add_argument("--json-out", default="")
    args = parser.parse_args()

    rng = random.Random(args.seed)
    maps = [item.strip() for item in args.maps.split(",") if item.strip()]
    findings = []
    by_map = {map_num: {"cases": 0, "hard": 0, "warn": 0} for map_num in maps}
    started = time.time()

    for index in range(args.cases):
        map_num = maps[index % len(maps)]
        case = build_case(rng, map_num, index)
        by_map[map_num]["cases"] += 1
        try:
            controls = run_case(case)
            case_findings = evaluate(case, controls)
            case["control"] = {
                "steering": controls.steering,
                "throttle": controls.throttle,
                "brake": controls.brake,
            }
        except Exception as exc:  # pylint: disable=broad-except
            case_findings = [("hard", "exception:" + exc.__class__.__name__)]
            case["exception"] = str(exc)
            case["control"] = None

        hard_count = sum(1 for level, _ in case_findings if level == "hard")
        warn_count = sum(1 for level, _ in case_findings if level == "warn")
        by_map[map_num]["hard"] += hard_count
        by_map[map_num]["warn"] += warn_count
        for level, reason in case_findings:
            if level == "hard" or len(findings) < 200:
                findings.append({"level": level, "reason": reason, "case": case})

    hard_samples = [finding for finding in findings if finding["level"] == "hard"]
    warn_samples = [finding for finding in findings if finding["level"] != "hard"]

    summary = {
        "cases": args.cases,
        "seed": args.seed,
        "elapsed_sec": round(time.time() - started, 3),
        "hard_findings": sum(row["hard"] for row in by_map.values()),
        "warnings": sum(row["warn"] for row in by_map.values()),
        "by_map": by_map,
        "sample_findings": (hard_samples + warn_samples)[:30],
    }

    if args.json_out:
        output_path = Path(args.json_out)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")

    print(json.dumps(summary, indent=2, sort_keys=True))
    return 1 if summary["hard_findings"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
