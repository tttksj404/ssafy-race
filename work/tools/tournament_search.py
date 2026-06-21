#!/usr/bin/env python3
"""Tournament-style tuner for SSAFY Race bot candidates.

This script is intentionally conservative with the real simulator: AirSim/Wine
is a single shared runtime, so candidates are generated and stress-filtered in
bulk, then actual simulator runs are executed as a sequential tournament.
"""

import argparse
import dataclasses
import heapq
import json
import re
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BOT_PATH = ROOT / "work" / "Template_Python" / "Bot_Python" / "my_car.py"
SUBMISSION_PATH = ROOT / "submissions" / "my_car.py"
OUT_DIR = ROOT / "work" / "experiments" / "tournament"
BEST_LOG = ROOT / "work" / "experiments" / "map161_p80_split48_47_20260613_20260613_205741.log"

SPEED_MARKER = "        speed_error = speed - target_speed\n"
NEAR_SPEED_BLOCK = """        if near_obstacle is not None and not safe_current_edge_escape:
            dist, obs_mid, gap = near_obstacle
            if dist < 20.0:
                target_speed = min(target_speed, 18.0)
            elif dist < 38.0:
                target_speed = min(target_speed, 24.0)
            else:
                target_speed = min(target_speed, 30.0)
"""
LOW_SPEED_MARKER = """                    if (
                        map_num == "161"
                        and 68.90 <= progress <= 69.30
                        and 2.0 < dist < 13.5
                        and -2.85 <= obs_mid <= -2.30
                        and speed < 18.8
                        and 3.1 < to_middle < 3.8
                        and abs(moving_angle) < 11.0
                        and gap > 5.2
                    ):
                        low_speed_throttle = max(low_speed_throttle, 0.62)
"""
BRAKE_BLOCK_MARKER = """            if dist < 24.0:
                if speed > 18.0:
                    set_throttle = min(set_throttle, 0.12)
                    set_brake = max(set_brake, 0.82)
                else:
"""


@dataclasses.dataclass(frozen=True)
class Candidate:
    name: str
    family: str
    params: dict


class UnionFind:
    def __init__(self):
        self.parent = {}

    def find(self, item):
        self.parent.setdefault(item, item)
        if self.parent[item] != item:
            self.parent[item] = self.find(self.parent[item])
        return self.parent[item]

    def union(self, left, right):
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root != right_root:
            self.parent[right_root] = left_root


def run(cmd, *, timeout=None, check=False):
    proc = subprocess.run(
        cmd,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        check=False,
    )
    if check and proc.returncode != 0:
        raise RuntimeError(f"command failed ({proc.returncode}): {' '.join(cmd)}\n{proc.stdout}")
    return proc


def restore(source):
    BOT_PATH.write_text(source, encoding="utf-8")
    SUBMISSION_PATH.write_text(source, encoding="utf-8")


def insert_before(text, marker, snippet):
    if marker not in text:
        raise ValueError(f"marker not found: {marker[:60]!r}")
    return text.replace(marker, snippet + "\n" + marker, 1)


def replace_once(text, old, new):
    if old not in text:
        raise ValueError(f"replacement target not found: {old[:60]!r}")
    return text.replace(old, new, 1)


def replace_brake_release_block(text, new):
    if BRAKE_BLOCK_MARKER in text:
        return text.replace(BRAKE_BLOCK_MARKER, new, 1)
    pattern = re.compile(
        r"            if dist < 24\.0:\n"
        r"                map161_release_gate = \(\n"
        r"                    map_num == \"161\"\n"
        r"                    and \([^\n]+\)\n"
        r"                    and speed < [0-9.]+\n"
        r"                    and gap > [0-9.]+\n"
        r"                    and abs\(moving_angle\) < [0-9.]+\n"
        r"                    and edge_ratio < [0-9.]+\n"
        r"                \)\n"
        r"                if speed > 18\.0 and not map161_release_gate:\n"
        r"                    set_throttle = min\(set_throttle, 0\.12\)\n"
        r"                    set_brake = max\(set_brake, 0\.82\)\n"
        r"                elif speed > 18\.0:\n"
        r"                    set_throttle = max\(set_throttle, [0-9.]+\)\n"
        r"                    set_brake = min\(set_brake, [0-9.]+\)\n"
        r"                else:\n"
    )
    replaced, count = pattern.subn(new, text, count=1)
    if count != 1:
        raise ValueError("brake release block not found")
    return replaced


def fast_window_snippet(speed, nearest, curve, mid_ratio, angle, windows):
    window_expr = " or ".join(windows)
    return f"""        if map_num == "161":
            nearest_ahead = None
            for obs in obstacles:
                dist = float(self._item_value(obs, "dist", 999.0))
                if dist > 0.0 and (nearest_ahead is None or dist < nearest_ahead):
                    nearest_ahead = dist
            map161_open_track = nearest_ahead is None or nearest_ahead > {nearest:.1f}
            map161_fast_window = ({window_expr})
            if (
                map161_fast_window
                and map161_open_track
                and curve_abs < {curve:.1f}
                and abs(to_middle) < road_limit * {mid_ratio:.2f}
                and abs(moving_angle) < {angle:.1f}
            ):
                target_speed = max(target_speed, {speed:.1f})
"""


def p69_release_snippet(throttle, speed_hi, angle_abs, progress_lo, progress_hi):
    return f"""                    if (
                        map_num == "161"
                        and {progress_lo:.2f} <= progress <= {progress_hi:.2f}
                        and 2.0 < dist < 13.5
                        and -2.85 <= obs_mid <= -2.30
                        and speed < {speed_hi:.1f}
                        and 3.0 < to_middle < 3.9
                        and abs(moving_angle) < {angle_abs:.1f}
                        and gap > 5.1
                    ):
                        low_speed_throttle = max(low_speed_throttle, {throttle:.2f})
"""


def near_speed_block(close, mid, far):
    return f"""        if near_obstacle is not None and not safe_current_edge_escape:
            dist, obs_mid, gap = near_obstacle
            if dist < 20.0:
                target_speed = min(target_speed, {close:.1f})
            elif dist < 38.0:
                target_speed = min(target_speed, {mid:.1f})
            else:
                target_speed = min(target_speed, {far:.1f})
"""


def brake_release_block(windows, speed_hi, gap_min, angle_abs, edge_max, throttle, brake):
    window_expr = " or ".join(windows)
    return f"""            if dist < 24.0:
                map161_release_gate = (
                    map_num == "161"
                    and ({window_expr})
                    and speed < {speed_hi:.1f}
                    and gap > {gap_min:.1f}
                    and abs(moving_angle) < {angle_abs:.1f}
                    and edge_ratio < {edge_max:.2f}
                )
                if speed > 18.0 and not map161_release_gate:
                    set_throttle = min(set_throttle, 0.12)
                    set_brake = max(set_brake, 0.82)
                elif speed > 18.0:
                    set_throttle = max(set_throttle, {throttle:.2f})
                    set_brake = min(set_brake, {brake:.2f})
                else:
"""


def apply_candidate(source, candidate):
    text = source
    family = candidate.family
    p = candidate.params
    if family == "open_speed":
        text = insert_before(
            text,
            SPEED_MARKER,
            fast_window_snippet(
                p["speed"],
                p["nearest"],
                p["curve"],
                p["mid_ratio"],
                p["angle"],
                p["windows"],
            ),
        )
    elif family == "p69_release":
        text = replace_once(
            text,
            LOW_SPEED_MARKER,
            p69_release_snippet(
                p["throttle"],
                p["speed_hi"],
                p["angle_abs"],
                p["progress_lo"],
                p["progress_hi"],
            ),
        )
    elif family == "near_speed":
        text = replace_once(text, NEAR_SPEED_BLOCK, near_speed_block(p["close"], p["mid"], p["far"]))
    elif family == "brake_release":
        text = replace_brake_release_block(
            text,
            brake_release_block(
                p["windows"],
                p["speed_hi"],
                p["gap_min"],
                p["angle_abs"],
                p["edge_max"],
                p["throttle"],
                p["brake"],
            ),
        )
    elif family == "combo":
        base = apply_candidate(text, Candidate(candidate.name + "_a", p["a"].family, p["a"].params))
        text = apply_candidate(base, Candidate(candidate.name + "_b", p["b"].family, p["b"].params))
    else:
        raise ValueError(f"unknown family: {family}")
    return text


def dijkstra_weighted_release_candidates():
    """Rank recursive p68 variants with weighted graph search.

    State fields are deliberately small and local around the current best.
    Dijkstra cost combines expected time gain, instability risk, and deviation
    from known-safe values. Union-find then keeps one representative per
    similar strategy basin so actual simulator runs are not wasted on clones.
    """
    start = (0.88, 36.0, 30.0, 5.1, 0.76, 66.0, 72.2)
    moves = (
        (0, -0.02), (0, 0.02),
        (1, -2.0), (1, 2.0),
        (2, -2.0), (2, 2.0),
        (3, -0.2), (3, 0.2),
        (4, -0.02), (4, 0.02),
        (5, -0.2), (5, 0.2),
        (6, -0.4), (6, 0.4),
    )
    bounds = (
        (0.82, 0.94),
        (32.0, 42.0),
        (26.0, 34.0),
        (4.7, 5.5),
        (0.72, 0.80),
        (65.6, 66.4),
        (71.6, 73.0),
    )

    def normalized(state):
        return (
            round(state[0], 2),
            round(state[1], 1),
            round(state[2], 1),
            round(state[3], 1),
            round(state[4], 2),
            round(state[5], 1),
            round(state[6], 1),
        )

    def clamp_step(state, index, delta):
        values = list(state)
        lo, hi = bounds[index]
        values[index] = min(hi, max(lo, values[index] + delta))
        return normalized(tuple(values))

    def risk_cost(state):
        throttle, speed_hi, angle_abs, gap_min, edge_max, start_p, end_p = state
        aggressive = max(0.0, throttle - 0.88) * 18.0
        aggressive += max(0.0, speed_hi - 36.0) * 0.22
        aggressive += max(0.0, angle_abs - 30.0) * 0.15
        aggressive += max(0.0, 5.1 - gap_min) * 0.8
        aggressive += max(0.0, edge_max - 0.76) * 9.0
        wide_window = max(0.0, 66.0 - start_p) * 0.55 + max(0.0, end_p - 72.2) * 0.45
        conservative = max(0.0, 0.88 - throttle) * 3.0 + max(0.0, 36.0 - speed_hi) * 0.05
        return aggressive + wide_window + conservative

    pq = [(0.0, start)]
    best = {start: 0.0}
    visited = []
    while pq and len(visited) < 96:
        cost, state = heapq.heappop(pq)
        if cost != best[state]:
            continue
        visited.append(state)
        for index, delta in moves:
            nxt = clamp_step(state, index, delta)
            step_cost = 0.18 + risk_cost(nxt) * 0.18
            new_cost = cost + step_cost
            if new_cost < best.get(nxt, float("inf")):
                best[nxt] = new_cost
                heapq.heappush(pq, (new_cost, nxt))

    uf = UnionFind()
    states = sorted(best, key=lambda item: (risk_cost(item), best[item]))
    for left in states:
        for right in states:
            if left >= right:
                continue
            similar = (
                abs(left[0] - right[0]) <= 0.02
                and abs(left[1] - right[1]) <= 2.0
                and abs(left[2] - right[2]) <= 2.0
                and abs(left[3] - right[3]) <= 0.2
                and abs(left[4] - right[4]) <= 0.02
                and abs(left[5] - right[5]) <= 0.2
                and abs(left[6] - right[6]) <= 0.4
            )
            if similar:
                uf.union(left, right)

    representatives = {}
    for state in states:
        root = uf.find(state)
        score = risk_cost(state) + best[state] * 0.20
        if root not in representatives or score < representatives[root][0]:
            representatives[root] = (score, state)

    ranked = sorted((score, state) for score, state in representatives.values())
    candidates = []
    for index, (_, state) in enumerate(ranked[:10], 1):
        throttle, speed_hi, angle_abs, gap_min, edge_max, start_p, end_p = state
        name = (
            f"dij_r{index:02d}_t{int(round(throttle * 100))}"
            f"_v{int(round(speed_hi))}_g{int(round(gap_min * 10))}"
            f"_e{int(round(edge_max * 100))}_w{int(round(start_p * 10))}_{int(round(end_p * 10))}"
        )
        candidates.append(Candidate(
            name,
            "brake_release",
            {
                "windows": [f"{start_p:.1f} <= progress <= {end_p:.1f}"],
                "speed_hi": speed_hi,
                "gap_min": gap_min,
                "angle_abs": angle_abs,
                "edge_max": edge_max,
                "throttle": throttle,
                "brake": 0.0,
            },
        ))
    return candidates


def generate_candidates():
    candidates = []
    all_windows = [
        "29.2 <= progress <= 42.9",
        "54.2 <= progress <= 64.7",
        "progress >= 94.8",
    ]
    early_window = ["29.2 <= progress <= 39.2"]
    finish_window = ["progress >= 94.8"]

    for speed in (84.0, 88.0, 92.0):
        for nearest in (150.0, 170.0, 190.0):
            candidates.append(Candidate(
                f"open_s{int(speed)}_n{int(nearest)}_all",
                "open_speed",
                {
                    "speed": speed,
                    "nearest": nearest,
                    "curve": 12.0,
                    "mid_ratio": 0.30,
                    "angle": 7.0,
                    "windows": all_windows,
                },
            ))
    for speed in (84.0, 88.0, 92.0):
        candidates.append(Candidate(
            f"open_s{int(speed)}_early",
            "open_speed",
            {
                "speed": speed,
                "nearest": 170.0,
                "curve": 10.0,
                "mid_ratio": 0.26,
                "angle": 6.0,
                "windows": early_window,
            },
        ))
        candidates.append(Candidate(
            f"open_s{int(speed)}_finish",
            "open_speed",
            {
                "speed": speed,
                "nearest": 170.0,
                "curve": 12.0,
                "mid_ratio": 0.32,
                "angle": 8.0,
                "windows": finish_window,
            },
        ))

    for throttle in (0.54, 0.62, 0.70):
        for speed_hi in (18.8, 19.6, 20.4):
            candidates.append(Candidate(
                f"p69_t{int(throttle * 100)}_v{str(speed_hi).replace('.', '')}",
                "p69_release",
                {
                    "throttle": throttle,
                    "speed_hi": speed_hi,
                    "angle_abs": 11.0,
                    "progress_lo": 68.90,
                    "progress_hi": 69.30,
                },
            ))

    for close, mid, far in (
        (18.0, 24.0, 32.0),
        (18.0, 26.0, 34.0),
        (20.0, 26.0, 32.0),
        (16.0, 24.0, 32.0),
        (18.0, 22.0, 30.0),
    ):
        candidates.append(Candidate(
            f"near_c{int(close)}_m{int(mid)}_f{int(far)}",
            "near_speed",
            {"close": close, "mid": mid, "far": far},
        ))

    bottleneck_windows = {
        "p45": ["43.0 <= progress <= 54.2"],
        "p68": ["65.0 <= progress <= 72.8"],
        "p45p68": ["43.0 <= progress <= 54.2", "65.0 <= progress <= 72.8"],
    }
    for label, windows in bottleneck_windows.items():
        for throttle, brake, speed_hi, angle_abs in (
            (0.45, 0.35, 24.0, 18.0),
            (0.55, 0.25, 26.0, 20.0),
            (0.65, 0.18, 28.0, 22.0),
        ):
            candidates.append(Candidate(
                f"rel_{label}_t{int(throttle * 100)}_b{int(brake * 100)}_v{int(speed_hi)}",
                "brake_release",
                {
                    "windows": windows,
                    "speed_hi": speed_hi,
                    "gap_min": 4.8 if label == "p45" else 5.0,
                    "angle_abs": angle_abs,
                    "edge_max": 0.78,
                    "throttle": throttle,
                    "brake": brake,
                },
            ))
    for label, windows, gap_min, edge_max in (
        ("p68n", ["66.0 <= progress <= 72.2"], 5.1, 0.76),
        ("p68w", ["64.6 <= progress <= 73.4"], 5.0, 0.80),
    ):
        for throttle, brake, speed_hi, angle_abs in (
            (0.60, 0.22, 27.0, 20.0),
            (0.70, 0.12, 29.0, 23.0),
            (0.75, 0.08, 30.0, 24.0),
        ):
            candidates.append(Candidate(
                f"rel_{label}_t{int(throttle * 100)}_b{int(brake * 100)}_v{int(speed_hi)}",
                "brake_release",
                {
                    "windows": windows,
                    "speed_hi": speed_hi,
                    "gap_min": gap_min,
                    "angle_abs": angle_abs,
                    "edge_max": edge_max,
                    "throttle": throttle,
                    "brake": brake,
                },
            ))
    for throttle, brake, speed_hi, angle_abs in (
        (0.73, 0.10, 30.0, 24.0),
        (0.77, 0.06, 31.0, 25.0),
        (0.80, 0.04, 32.0, 26.0),
        (0.84, 0.00, 34.0, 28.0),
        (0.88, 0.00, 36.0, 30.0),
        (0.92, 0.00, 40.0, 32.0),
        (0.96, 0.00, 44.0, 34.0),
    ):
        candidates.append(Candidate(
            f"rel_p68n_hi_t{int(throttle * 100)}_b{int(brake * 100)}_v{int(speed_hi)}",
            "brake_release",
            {
                "windows": ["66.0 <= progress <= 72.2"],
                "speed_hi": speed_hi,
                "gap_min": 5.1,
                "angle_abs": angle_abs,
                "edge_max": 0.76,
                "throttle": throttle,
                "brake": brake,
            },
        ))
    candidates.extend(dijkstra_weighted_release_candidates())

    best_release = Candidate(
        "rel_p68n_hi_t88_b0_v36",
        "brake_release",
        {
            "windows": ["66.0 <= progress <= 72.2"],
            "speed_hi": 36.0,
            "gap_min": 5.1,
            "angle_abs": 30.0,
            "edge_max": 0.76,
            "throttle": 0.88,
            "brake": 0.0,
        },
    )
    for speed, window_label, windows, nearest, curve, mid_ratio, angle in (
        (84.0, "finish", ["progress >= 94.8"], 180.0, 10.0, 0.30, 7.0),
        (88.0, "finish", ["progress >= 94.8"], 190.0, 10.0, 0.28, 6.5),
        (84.0, "early", ["29.2 <= progress <= 39.2"], 190.0, 9.0, 0.22, 5.0),
        (84.0, "mid", ["54.2 <= progress <= 64.7"], 190.0, 9.0, 0.22, 5.0),
        (88.0, "late_open", ["80.0 <= progress <= 90.0", "progress >= 94.8"], 190.0, 9.0, 0.24, 5.5),
    ):
        open_candidate = Candidate(
            f"open_s{int(speed)}_{window_label}_weighted",
            "open_speed",
            {
                "speed": speed,
                "nearest": nearest,
                "curve": curve,
                "mid_ratio": mid_ratio,
                "angle": angle,
                "windows": windows,
            },
        )
        candidates.append(Candidate(
            f"combo_t88_{window_label}_s{int(speed)}",
            "combo",
            {"a": best_release, "b": open_candidate},
        ))

    # A small binary-search style combination set: pair a conservative open
    # straight boost with a mild obstacle release.
    mild_open = Candidate(
        "open_s84_n190_all",
        "open_speed",
        {
            "speed": 84.0,
            "nearest": 190.0,
            "curve": 10.0,
            "mid_ratio": 0.24,
            "angle": 5.5,
            "windows": all_windows,
        },
    )
    for throttle in (0.54, 0.62):
        release = Candidate(
            f"p69_t{int(throttle * 100)}_v196",
            "p69_release",
            {
                "throttle": throttle,
                "speed_hi": 19.6,
                "angle_abs": 9.0,
                "progress_lo": 68.94,
                "progress_hi": 69.26,
            },
        )
        candidates.append(Candidate(
            f"combo_open84_p69_t{int(throttle * 100)}",
            "combo",
            {"a": mild_open, "b": release},
        ))

    return candidates


def py_compile_and_cmp():
    proc = run(["python3", "-m", "py_compile", str(BOT_PATH), str(SUBMISSION_PATH)])
    if proc.returncode != 0:
        return False, proc.stdout
    proc = run(["cmp", "-s", str(BOT_PATH), str(SUBMISSION_PATH)])
    if proc.returncode != 0:
        return False, "candidate files differ"
    return True, ""


def stress_candidate(candidate, cases, seed):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    json_out = OUT_DIR / f"{candidate.name}_stress.json"
    proc = run([
        "python3",
        "work/tools/stress_my_car.py",
        "--cases",
        str(cases),
        "--seed",
        str(seed),
        "--json-out",
        str(json_out),
    ])
    data = {}
    if json_out.exists():
        data = json.loads(json_out.read_text(encoding="utf-8"))
    return {
        "returncode": proc.returncode,
        "hard": data.get("hard_findings", 999999),
        "warnings": data.get("warnings", 999999),
        "json": str(json_out),
    }


def score_log(path):
    proc = run(["python3", "work/tools/score_logs.py", "--json", str(path)])
    if proc.returncode != 0:
        return {"score": 999999.0, "error": proc.stdout}
    rows = json.loads(proc.stdout)
    return rows[0]


def run_actual(candidate):
    label = f"tour_{candidate.name}_{time.strftime('%Y%m%d_%H%M%S')}"
    proc = run(["./work/run_experiment.sh", "03", label], timeout=900)
    match = re.search(r"\[ExperimentLog\] (.+)", proc.stdout)
    log_path = match.group(1).strip() if match else ""
    row = score_log(log_path) if log_path else {"score": 999999.0, "error": "missing log path"}
    row["log"] = log_path
    row["run_returncode"] = proc.returncode
    return row


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--stress-only", action="store_true")
    parser.add_argument(
        "--actual-candidates",
        default="",
        help="Comma-separated candidate names to run in the real simulator.",
    )
    parser.add_argument("--run-top", type=int, default=0)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--cases", type=int, default=12000)
    parser.add_argument("--seed", type=int, default=20260620)
    parser.add_argument("--keep", default="")
    args = parser.parse_args()

    source = BOT_PATH.read_text(encoding="utf-8")
    candidates = generate_candidates()
    if args.limit:
        candidates = candidates[:args.limit]

    if args.list:
        for index, candidate in enumerate(candidates, 1):
            print(f"{index:02d} {candidate.name} {candidate.family} {candidate.params}")
        return 0

    if args.actual_candidates:
        requested = [name.strip() for name in args.actual_candidates.split(",") if name.strip()]
        by_name = {candidate.name: candidate for candidate in candidates}
        missing = [name for name in requested if name not in by_name]
        if missing:
            raise SystemExit(f"unknown --actual-candidates: {', '.join(missing)}")
        actual_results = []
        try:
            for name in requested:
                candidate = by_name[name]
                restore(apply_candidate(source, candidate))
                ok, detail = py_compile_and_cmp()
                if not ok:
                    actual_results.append({"candidate": name, "compile_ok": False, "detail": detail})
                else:
                    actual = run_actual(candidate)
                    actual_results.append({"candidate": name, "compile_ok": True, **actual})
                print(json.dumps(actual_results[-1], sort_keys=True))
        finally:
            restore(source)
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        actual_path = OUT_DIR / f"actual_{time.strftime('%Y%m%d_%H%M%S')}.json"
        actual_path.write_text(json.dumps(actual_results, indent=2, sort_keys=True), encoding="utf-8")
        print(f"[TournamentActual] {actual_path}")
        return 0

    results = []
    try:
        for index, candidate in enumerate(candidates, 1):
            candidate_source = apply_candidate(source, candidate)
            restore(candidate_source)
            ok, detail = py_compile_and_cmp()
            if not ok:
                result = {"candidate": candidate.name, "compile_ok": False, "detail": detail}
            else:
                stress = stress_candidate(candidate, args.cases, args.seed + index)
                result = {"candidate": candidate.name, "compile_ok": True, **stress}
            results.append(result)
            print(json.dumps(result, sort_keys=True))
    finally:
        if args.keep:
            selected = next((candidate for candidate in candidates if candidate.name == args.keep), None)
            if selected is None:
                restore(source)
                raise SystemExit(f"unknown --keep candidate: {args.keep}")
            restore(apply_candidate(source, selected))
        else:
            restore(source)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    summary_path = OUT_DIR / f"summary_{time.strftime('%Y%m%d_%H%M%S')}.json"
    summary_path.write_text(json.dumps(results, indent=2, sort_keys=True), encoding="utf-8")
    print(f"[TournamentSummary] {summary_path}")

    if args.run_top:
        safe = [row for row in results if row.get("compile_ok") and row.get("hard") == 0]
        safe.sort(key=lambda row: (row.get("hard", 999999), row.get("warnings", 999999)))
        actual_results = []
        try:
            for row in safe[: args.run_top]:
                candidate = next(item for item in candidates if item.name == row["candidate"])
                restore(apply_candidate(source, candidate))
                actual = run_actual(candidate)
                actual_results.append({"candidate": candidate.name, **actual})
                print(json.dumps(actual_results[-1], sort_keys=True))
        finally:
            restore(source)
        actual_path = OUT_DIR / f"actual_{time.strftime('%Y%m%d_%H%M%S')}.json"
        actual_path.write_text(json.dumps(actual_results, indent=2, sort_keys=True), encoding="utf-8")
        print(f"[TournamentActual] {actual_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
