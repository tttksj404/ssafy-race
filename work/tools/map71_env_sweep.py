#!/usr/bin/env python3
"""Environment-parameter sweep for Map71 SSAFY Race candidates.

The bot reads SSAFY_* environment variables at runtime. This script does a
fast virtual gate first, then optionally promotes the best candidates to the
real simulator. It never edits my_car.py while testing candidates.
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
OUT_DIR = ROOT / "work" / "experiments" / "map71_env_sweep"
TELEMETRY_RE = re.compile(
    r"progress=(?P<progress>[0-9.]+).*?"
    r"speed=(?P<speed>[-0-9.]+).*?"
    r"collisions=(?P<collisions>\d+).*?"
    r"penalties=(?P<penalties>\d+)"
)
EXPERIMENT_LOG_RE = re.compile(r"\[ExperimentLog\] (.+)")


def run(cmd, *, env=None, timeout=None):
    merged_env = os.environ.copy()
    if env:
        merged_env.update({key: str(value) for key, value in env.items()})
    try:
        return subprocess.run(
            cmd,
            cwd=ROOT,
            env=merged_env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        cleanup_simulator()
        stdout = exc.stdout or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", errors="replace")
        return subprocess.CompletedProcess(cmd, 124, stdout=stdout + "\n[timeout]\n")


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


def cleanup_artifacts():
    subprocess.run(
        [
            "bash",
            "-lc",
            "find work/videos work/screenshots -type f -delete 2>/dev/null; "
            "find work/experiments/snapshots -mindepth 1 -maxdepth 1 -exec rm -rf {} + 2>/dev/null",
        ],
        cwd=ROOT,
        check=False,
    )


def candidates():
    rows = [
        ("baseline", {}),
        ("cap_off", {"SSAFY_MAP71_CAP_ENABLE": "0"}),
    ]

    for cap in (1.8, 2.0, 2.2, 2.6, 2.8, 3.2):
        rows.append((f"cap_{cap:.1f}", {"SSAFY_MAP71_CAP_VALUE": cap}))
    for cap in (3.6, 4.0, 4.6):
        rows.append((f"widecap_{cap:.1f}", {"SSAFY_MAP71_CAP_VALUE": cap}))
    for end in (33.4, 33.8, 34.6, 35.2):
        rows.append((f"cap24_end_{end:.1f}", {"SSAFY_MAP71_CAP_END": end}))

    for mult in (0.82, 0.95, 1.05, 1.18):
        rows.append((f"seg6767_m{int(mult * 100)}", {"SSAFY_SEG6767_MULT": mult}))

    # SSAFY Race는 충돌이 곧 실패가 아니라 시간 손실이다. Map71 기본
    # 풀브레이크 조건이 기록을 크게 깎는지 확인하기 위해 위험제어를
    # 단계적으로 완화한 후보를 실제 시뮬레이터까지 올려 본다.
    rows.extend([
        (
            "map71_relaxed_brake",
            {
                "SSAFY_MAP71_RISK_STEER": 0.66,
                "SSAFY_MAP71_RISK_SPEED": 122,
                "SSAFY_MAP71_RISK_LOW_SPEED": 128,
                "SSAFY_MAP71_RISK_LOW_BRAKE": 0.10,
                "SSAFY_MAP71_RISK_HIGH_BRAKE": 0.42,
                "SSAFY_MAP71_YAW_ANGLE": 42,
                "SSAFY_MAP71_YAW_SPEED": 112,
                "SSAFY_MAP71_YAW_BRAKE": 0.45,
                "SSAFY_MAP71_MIN_TARGET_SPEED": 92,
                "SSAFY_MAP71_SEG6767_FLOOR": 82,
                "SSAFY_RECOVERY_BACK_FRAMES": 2,
                "SSAFY_RECOVERY_FORWARD_FRAMES": 6,
                "SSAFY_RECOVERY_BACK_THROTTLE": 0.45,
            },
        ),
        (
            "map71_very_fast",
            {
                "SSAFY_MAP71_RISK_STEER": 0.74,
                "SSAFY_MAP71_RISK_SPEED": 135,
                "SSAFY_MAP71_RISK_LOW_SPEED": 145,
                "SSAFY_MAP71_RISK_LOW_BRAKE": 0.0,
                "SSAFY_MAP71_RISK_HIGH_BRAKE": 0.24,
                "SSAFY_MAP71_YAW_ANGLE": 52,
                "SSAFY_MAP71_YAW_SPEED": 128,
                "SSAFY_MAP71_YAW_BRAKE": 0.22,
                "SSAFY_MAP71_MIN_TARGET_SPEED": 105,
                "SSAFY_MAP71_SEG6767_FLOOR": 95,
                "SSAFY_RECOVERY_BACK_FRAMES": 2,
                "SSAFY_RECOVERY_FORWARD_FRAMES": 5,
                "SSAFY_RECOVERY_BACK_THROTTLE": 0.35,
            },
        ),
        (
            "map71_no_risk_brake",
            {
                "SSAFY_MAP71_RISK_BRAKE_ENABLE": "0",
                "SSAFY_MAP71_YAW_BRAKE_ENABLE": "0",
                "SSAFY_MAP71_MIN_TARGET_SPEED": 112,
                "SSAFY_MAP71_SEG6767_FLOOR": 100,
                "SSAFY_RECOVERY_BACK_FRAMES": 2,
                "SSAFY_RECOVERY_FORWARD_FRAMES": 5,
                "SSAFY_RECOVERY_BACK_THROTTLE": 0.30,
            },
        ),
        (
            "map71_short_vision_fast",
            {
                "SSAFY_MAP71_OBSTACLE_PED": 1.85,
                "SSAFY_MAP71_REACT_DIST_MIN": 52,
                "SSAFY_MAP71_REACT_DIST_MAX": 108,
                "SSAFY_MAP71_REACT_DIST_SCALE": 0.55,
                "SSAFY_MAP71_RISK_STEER": 0.68,
                "SSAFY_MAP71_RISK_SPEED": 124,
                "SSAFY_MAP71_RISK_HIGH_BRAKE": 0.35,
                "SSAFY_MAP71_YAW_ANGLE": 44,
                "SSAFY_MAP71_YAW_SPEED": 116,
                "SSAFY_MAP71_YAW_BRAKE": 0.35,
                "SSAFY_MAP71_MIN_TARGET_SPEED": 96,
                "SSAFY_MAP71_SEG6767_FLOOR": 88,
            },
        ),
        (
            "map71_wide_vision_fast",
            {
                "SSAFY_MAP71_OBSTACLE_PED": 1.95,
                "SSAFY_MAP71_REACT_DIST_MIN": 68,
                "SSAFY_MAP71_REACT_DIST_MAX": 132,
                "SSAFY_MAP71_REACT_DIST_SCALE": 0.68,
                "SSAFY_MAP71_RISK_STEER": 0.68,
                "SSAFY_MAP71_RISK_SPEED": 125,
                "SSAFY_MAP71_RISK_HIGH_BRAKE": 0.38,
                "SSAFY_MAP71_YAW_ANGLE": 44,
                "SSAFY_MAP71_YAW_SPEED": 115,
                "SSAFY_MAP71_YAW_BRAKE": 0.38,
                "SSAFY_MAP71_MIN_TARGET_SPEED": 96,
            },
        ),
    ])

    for left, right in ((-4.4, 4.6), (-5.2, 5.4), (-6.0, 6.2)):
        rows.append((
            f"mid64_{abs(int(left * 10))}_{int(right * 10)}",
            {
                "SSAFY_MAP71_MID64_ENABLE": "1",
                "SSAFY_MAP71_MID64_LEFT": left,
                "SSAFY_MAP71_MID64_RIGHT": right,
            },
        ))

    for dist, cap in ((62, 0.78), (68, 0.82), (74, 0.86), (82, 0.88)):
        rows.append((
            f"farcap_d{dist}_c{int(cap * 100)}",
            {
                "SSAFY_MAP71_FAR_BRAKE_CAP_ENABLE": "1",
                "SSAFY_MAP71_FAR_BRAKE_DIST": dist,
                "SSAFY_MAP71_FAR_BRAKE_CAP": cap,
            },
        ))
    for dist, mid, cap in (
        (72, 5.2, 0.35),
        (72, 5.8, 0.45),
        (78, 5.8, 0.45),
        (78, 6.4, 0.55),
        (88, 6.4, 0.55),
    ):
        rows.append((
            f"farsoft_d{dist}_m{int(mid * 10)}_c{int(cap * 100)}",
            {
                "SSAFY_MAP71_FAR_BRAKE_CAP_ENABLE": "1",
                "SSAFY_MAP71_FAR_BRAKE_DIST": dist,
                "SSAFY_MAP71_FAR_BRAKE_MID": mid,
                "SSAFY_MAP71_FAR_BRAKE_CAP": cap,
                "SSAFY_MAP71_FAR_BRAKE_THROTTLE_FLOOR": 0.35,
            },
        ))
    for target, brake_cap in ((142, 0.58), (146, 0.62), (150, 0.66), (154, 0.70)):
        rows.append((
            f"p31approach_t{target}_b{int(brake_cap * 100)}",
            {
                "SSAFY_MAP71_P31_APPROACH_ENABLE": "1",
                "SSAFY_MAP71_P31_APPROACH_TARGET": target,
                "SSAFY_MAP71_P31_APPROACH_BRAKE_CAP": brake_cap,
                "SSAFY_MAP71_P31_APPROACH_THROTTLE_FLOOR": 0.35,
            },
        ))
    for target, brake_cap, end in (
        (126, 0.82, 33.15),
        (132, 0.78, 33.35),
        (138, 0.74, 33.55),
        (144, 0.70, 33.75),
        (132, 0.86, 34.05),
        (140, 0.80, 34.25),
    ):
        rows.append((
            f"p31trail_t{target}_b{int(brake_cap * 100)}_e{int(end * 100)}",
            {
                "SSAFY_MAP71_P31_APPROACH_ENABLE": "1",
                "SSAFY_MAP71_P31_APPROACH_TARGET": target,
                "SSAFY_MAP71_P31_APPROACH_BRAKE_CAP": brake_cap,
                "SSAFY_MAP71_P31_APPROACH_END": end,
                "SSAFY_MAP71_P31_APPROACH_THROTTLE_FLOOR": 0.25,
            },
        ))
    for target, brake_cap, end, far_cap in (
        (132, 0.78, 33.35, 0.45),
        (138, 0.74, 33.55, 0.45),
        (140, 0.80, 34.25, 0.55),
    ):
        rows.append((
            f"p31trail_t{target}_far{int(far_cap * 100)}",
            {
                "SSAFY_MAP71_P31_APPROACH_ENABLE": "1",
                "SSAFY_MAP71_P31_APPROACH_TARGET": target,
                "SSAFY_MAP71_P31_APPROACH_BRAKE_CAP": brake_cap,
                "SSAFY_MAP71_P31_APPROACH_END": end,
                "SSAFY_MAP71_P31_APPROACH_THROTTLE_FLOOR": 0.25,
                "SSAFY_MAP71_FAR_BRAKE_CAP_ENABLE": "1",
                "SSAFY_MAP71_FAR_BRAKE_DIST": 78,
                "SSAFY_MAP71_FAR_BRAKE_MID": 5.8,
                "SSAFY_MAP71_FAR_BRAKE_CAP": far_cap,
                "SSAFY_MAP71_FAR_BRAKE_THROTTLE_FLOOR": 0.35,
            },
        ))
    for scale, left, edge in ((0.28, 0.18, 0.32), (0.36, 0.24, 0.38), (0.48, 0.30, 0.44)):
        rows.append((
            f"p33gate_s{int(scale * 100)}_l{int(left * 100)}",
            {
                "SSAFY_MAP71_P33_GATE_ENABLE": "1",
                "SSAFY_MAP71_P33_MIDDLE_SCALE": scale,
                "SSAFY_MAP71_P33_GATE_LEFT_STEER": left,
                "SSAFY_MAP71_P33_GATE_EDGE_STEER": edge,
            },
        ))
    for scale, left, target, brake_cap, end in (
        (0.28, 0.18, 132, 0.78, 33.35),
        (0.36, 0.24, 138, 0.74, 33.55),
        (0.48, 0.30, 140, 0.80, 34.25),
    ):
        rows.append((
            f"p31p33_s{int(scale * 100)}_t{target}",
            {
                "SSAFY_MAP71_P33_GATE_ENABLE": "1",
                "SSAFY_MAP71_P33_MIDDLE_SCALE": scale,
                "SSAFY_MAP71_P33_GATE_LEFT_STEER": left,
                "SSAFY_MAP71_P33_GATE_EDGE_STEER": left + 0.14,
                "SSAFY_MAP71_P31_APPROACH_ENABLE": "1",
                "SSAFY_MAP71_P31_APPROACH_TARGET": target,
                "SSAFY_MAP71_P31_APPROACH_BRAKE_CAP": brake_cap,
                "SSAFY_MAP71_P31_APPROACH_END": end,
                "SSAFY_MAP71_P31_APPROACH_THROTTLE_FLOOR": 0.25,
            },
        ))
    for fsteer, frames, done in ((0.34, 5, 9), (0.48, 6, 12), (0.62, 7, 14)):
        rows.append((
            f"p33push_f{int(fsteer * 100)}",
            {
                "SSAFY_MAP71_P33_RECOVERY_ENABLE": "1",
                "SSAFY_MAP71_P33_NO_REVERSE_ENABLE": "1",
                "SSAFY_MAP71_P33_RECOVERY_TRIGGER_BONUS": 6,
                "SSAFY_MAP71_P33_FORWARD_STEER": fsteer,
                "SSAFY_MAP71_P33_FORWARD_FRAMES": frames,
                "SSAFY_MAP71_P33_DONE_SPEED": done,
            },
        ))
    for scale, left, fsteer in ((0.28, 0.18, 0.34), (0.36, 0.24, 0.48), (0.48, 0.30, 0.62)):
        rows.append((
            f"p33gatepush_s{int(scale * 100)}_f{int(fsteer * 100)}",
            {
                "SSAFY_MAP71_P33_GATE_ENABLE": "1",
                "SSAFY_MAP71_P33_MIDDLE_SCALE": scale,
                "SSAFY_MAP71_P33_GATE_LEFT_STEER": left,
                "SSAFY_MAP71_P33_GATE_EDGE_STEER": left + 0.14,
                "SSAFY_MAP71_P33_RECOVERY_ENABLE": "1",
                "SSAFY_MAP71_P33_NO_REVERSE_ENABLE": "1",
                "SSAFY_MAP71_P33_RECOVERY_TRIGGER_BONUS": 6,
                "SSAFY_MAP71_P33_FORWARD_STEER": fsteer,
                "SSAFY_MAP71_P33_FORWARD_FRAMES": 6,
                "SSAFY_MAP71_P33_DONE_SPEED": 12,
            },
        ))
    for scale, left, guard, brake in ((0.28, 0.18, 0.34, 0.25), (0.36, 0.24, 0.42, 0.35), (0.48, 0.30, 0.50, 0.45)):
        rows.append((
            f"p33p35_s{int(scale * 100)}_g{int(guard * 100)}",
            {
                "SSAFY_MAP71_P33_GATE_ENABLE": "1",
                "SSAFY_MAP71_P33_MIDDLE_SCALE": scale,
                "SSAFY_MAP71_P33_GATE_LEFT_STEER": left,
                "SSAFY_MAP71_P33_GATE_EDGE_STEER": left + 0.14,
                "SSAFY_MAP71_P35_GUARD_ENABLE": "1",
                "SSAFY_MAP71_P35_GUARD_STEER": guard,
                "SSAFY_MAP71_P35_BRAKE": brake,
                "SSAFY_MAP71_P35_THROTTLE": 0.5,
            },
        ))
    for target, brake_cap in ((146, 0.62), (150, 0.66)):
        rows.append((
            f"p31_t{target}_farsoft",
            {
                "SSAFY_MAP71_P31_APPROACH_ENABLE": "1",
                "SSAFY_MAP71_P31_APPROACH_TARGET": target,
                "SSAFY_MAP71_P31_APPROACH_BRAKE_CAP": brake_cap,
                "SSAFY_MAP71_P31_APPROACH_THROTTLE_FLOOR": 0.35,
                "SSAFY_MAP71_FAR_BRAKE_CAP_ENABLE": "1",
                "SSAFY_MAP71_FAR_BRAKE_DIST": 78,
                "SSAFY_MAP71_FAR_BRAKE_MID": 5.8,
                "SSAFY_MAP71_FAR_BRAKE_CAP": 0.45,
                "SSAFY_MAP71_FAR_BRAKE_THROTTLE_FLOOR": 0.35,
            },
        ))

    for right_steer, left_steer in ((0.34, 0.44), (0.42, 0.52), (0.50, 0.62)):
        rows.append((
            f"p68damp_{int(right_steer * 100)}_{int(left_steer * 100)}",
            {
                "SSAFY_MAP71_P68_DAMP_ENABLE": "1",
                "SSAFY_MAP71_P68_DAMP_RIGHT_STEER": right_steer,
                "SSAFY_MAP71_P68_DAMP_LEFT_STEER": left_steer,
            },
        ))

    for left, right in ((-4.8, 5.0), (-5.6, 5.8)):
        for right_steer, left_steer in ((0.34, 0.44), (0.42, 0.52)):
            rows.append((
                f"mid64_{abs(int(left * 10))}_{int(right * 10)}_p68d{int(right_steer * 100)}",
                {
                    "SSAFY_MAP71_MID64_ENABLE": "1",
                    "SSAFY_MAP71_MID64_LEFT": left,
                    "SSAFY_MAP71_MID64_RIGHT": right,
                    "SSAFY_MAP71_P68_DAMP_ENABLE": "1",
                    "SSAFY_MAP71_P68_DAMP_RIGHT_STEER": right_steer,
                    "SSAFY_MAP71_P68_DAMP_LEFT_STEER": left_steer,
                },
            ))

    for steer_hi, steer_mid, steer_low in (
        (0.45, 0.32, 0.18),
        (0.60, 0.42, 0.24),
        (0.75, 0.52, 0.30),
        (0.85, 0.65, 0.35),
    ):
        rows.append((
            f"p68_r_{int(steer_hi * 100)}_{int(steer_mid * 100)}_{int(steer_low * 100)}",
            {
                "SSAFY_MAP71_P68_RIGHT_ENABLE": "1",
                "SSAFY_MAP71_P68_STEER_HI": steer_hi,
                "SSAFY_MAP71_P68_STEER_MID": steer_mid,
                "SSAFY_MAP71_P68_STEER_LOW": steer_low,
                },
            ))

    for left_steer in (0.18, 0.26, 0.34):
        rows.append((
            f"p54guard_{int(left_steer * 100)}",
            {
                "SSAFY_MAP71_P54_CENTER_GUARD_ENABLE": "1",
                "SSAFY_MAP71_P54_LEFT_STEER": left_steer,
            },
        ))

    for end, cap in ((94.4, 0.0), (96.0, 0.0), (96.5, 0.2)):
        rows.append((
            f"p94release_{int(end * 10)}_{int(cap * 10)}",
            {
                "SSAFY_MAP71_P94_RELEASE_ENABLE": "1",
                "SSAFY_MAP71_P94_RELEASE_END": end,
                "SSAFY_MAP71_P94_RELEASE_BRAKE_CAP": cap,
            },
        ))

    for left_steer in (0.18, 0.26):
        for end in (94.4, 96.0):
            rows.append((
                f"p54g{int(left_steer * 100)}_p94r{int(end * 10)}",
                {
                    "SSAFY_MAP71_P54_CENTER_GUARD_ENABLE": "1",
                    "SSAFY_MAP71_P54_LEFT_STEER": left_steer,
                    "SSAFY_MAP71_P94_RELEASE_ENABLE": "1",
                    "SSAFY_MAP71_P94_RELEASE_END": end,
                },
            ))

    for a, b in ((0.52, 0.38), (0.62, 0.46), (0.72, 0.58)):
        rows.append((
            f"edge33_{int(a * 100)}_{int(b * 100)}",
            {
                "SSAFY_MAP71_EDGE33_ENABLE": "1",
                "SSAFY_MAP71_EDGE33_A": a,
                "SSAFY_MAP71_EDGE33_B": b,
            },
        ))

    # p33~36은 실제 영상에서 기록 편차를 가장 크게 만든다. 충돌을 없애려는
    # 후보가 아니라, 부딪힌 뒤 짧게 빼고 바로 재가속하는 후보를 넓게 탐색한다.
    for back_frames, back_throttle, back_steer, forward_steer, forward_frames, done_speed in (
        (2, 0.42, 0.32, 0.34, 4, 16),
        (2, 0.55, 0.42, 0.46, 4, 14),
        (2, 0.70, 0.52, 0.58, 5, 12),
        (3, 0.42, 0.32, 0.46, 5, 18),
        (3, 0.55, 0.42, 0.54, 5, 14),
        (3, 0.70, 0.52, 0.66, 6, 10),
        (4, 0.42, 0.36, 0.54, 5, 18),
        (4, 0.55, 0.46, 0.62, 6, 14),
        (4, 0.70, 0.56, 0.72, 6, 10),
        (5, 0.55, 0.42, 0.40, 5, 12),
        (5, 0.70, 0.52, 0.48, 6, 10),
    ):
        rows.append((
            f"p33rec_b{back_frames}_t{int(back_throttle * 100)}_s{int(back_steer * 100)}_f{int(forward_steer * 100)}",
            {
                "SSAFY_MAP71_P33_RECOVERY_ENABLE": "1",
                "SSAFY_MAP71_P33_BACK_FRAMES": back_frames,
                "SSAFY_MAP71_P33_BACK_THROTTLE": back_throttle,
                "SSAFY_MAP71_P33_BACK_STEER": back_steer,
                "SSAFY_MAP71_P33_FORWARD_STEER": forward_steer,
                "SSAFY_MAP71_P33_FORWARD_FRAMES": forward_frames,
                "SSAFY_MAP71_P33_DONE_SPEED": done_speed,
            },
        ))

    for cap in (2.0, 2.4, 2.8):
        for mult in (0.95, 1.10):
            rows.append((
                f"cap{int(cap * 10)}_seg{int(mult * 100)}",
                {"SSAFY_MAP71_CAP_VALUE": cap, "SSAFY_SEG6767_MULT": mult},
            ))

    for cap in (2.0, 2.4):
        for steer_hi, steer_mid, steer_low in ((0.45, 0.32, 0.18), (0.60, 0.42, 0.24)):
            rows.append((
                f"cap{int(cap * 10)}_p68_{int(steer_hi * 100)}",
                {
                    "SSAFY_MAP71_CAP_VALUE": cap,
                    "SSAFY_MAP71_P68_RIGHT_ENABLE": "1",
                    "SSAFY_MAP71_P68_STEER_HI": steer_hi,
                    "SSAFY_MAP71_P68_STEER_MID": steer_mid,
                    "SSAFY_MAP71_P68_STEER_LOW": steer_low,
                },
            ))

    return rows


def score_gate(summary):
    cost = 0.0
    map71_failures = []
    map71_metrics = {}
    for result in summary.get("results", []):
        name = result.get("name", "")
        failures = result.get("failures", [])
        metrics = result.get("metrics", {})
        if result.get("map") != "71":
            continue
        map71_metrics[name] = metrics
        for failure in failures:
            map71_failures.append(f"{name}:{failure}")
            if "virtual_collision" in failure:
                if "map71_p33_slalom_exit" in failure:
                    cost += 22.0
                elif "map71_p94_left_gate" in failure:
                    cost += 24.0
                else:
                    cost += 14.0
            elif "brakes_too_early" in failure:
                cost += 5.0
            elif "p33_penalty_edge" in failure or "p94_exit_speed_low" in failure:
                cost += 12.0
            elif "p33_relaunch" in failure or "p33_right_relaunch" in failure:
                cost += 18.0
            elif "p54_penalty_edge" in failure or "p54_yaw_trap" in failure:
                cost += 16.0
            elif "far_brake_edge" in failure or "far_brake_yaw" in failure:
                cost += 18.0
            elif "far_brake_avg_high" in failure or "far_brake_throttle_low" in failure:
                cost += 6.0
            elif "p31_entry_edge" in failure or "p31_entry_yaw" in failure:
                cost += 20.0
            elif "p31_entry_speed_low" in failure:
                cost += 10.0
            elif "p31_entry_speed_high" in failure or "p31_entry_drop_low" in failure:
                cost += 8.0
            elif "p64_recovery_yaw" in failure or "p94_yaw_trap" in failure:
                cost += 14.0
            elif "edge_extreme" in failure or "yaw_high" in failure:
                cost += 8.0
            elif "throttle_low" in failure or "brake_high" in failure:
                cost += 4.0
            else:
                cost += 2.0
        cost += metrics.get("avg_brake", 0.0) * 3.0
        cost += max(0.0, metrics.get("max_edge", 0.0) - 1.0) * 4.0
        cost -= metrics.get("end_distance", 0.0) * 0.01
    return round(cost, 4), map71_failures[:18], map71_metrics


def quick_gate(name, env):
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    json_out = OUT_DIR / f"{name}_quick.json"
    proc = run(["python3", "work/tools/quick_f1_gate.py", "--quiet", "--json-out", str(json_out)], env=env)
    if not json_out.exists():
        return {
            "candidate": name,
            "quick_returncode": proc.returncode,
            "quick_cost": 999999.0,
            "error": proc.stdout[-2000:],
            "env": env,
        }
    summary = json.loads(json_out.read_text(encoding="utf-8"))
    cost, failures, metrics = score_gate(summary)
    return {
        "candidate": name,
        "quick_returncode": proc.returncode,
        "quick_cost": cost,
        "map71_failures": failures,
        "map71_metrics": metrics,
        "json": str(json_out),
        "env": env,
    }


def score_log(path):
    proc = run(["python3", "work/tools/score_logs.py", "--json", str(path)])
    if proc.returncode != 0:
        return {"score": 999999.0, "error": proc.stdout[-2000:]}
    return json.loads(proc.stdout)[0]


def actual_run(row):
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", row["candidate"])[:48]
    label = f"map71env_{safe_name}_{time.strftime('%Y%m%d_%H%M%S')}"
    env = {"START_DELAY": "2"}
    env.update(row["env"])
    merged_env = os.environ.copy()
    merged_env.update({key: str(value) for key, value in env.items()})

    cleanup_simulator()
    cleanup_artifacts()
    time.sleep(2)
    proc = subprocess.Popen(
        ["./work/run_watch.sh", "07", label],
        cwd=ROOT,
        env=merged_env,
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
            if progress < 25 and collisions >= 140:
                abort_reason = "early_collision_explosion"
            elif progress < 40 and collisions >= 180:
                abort_reason = "p33_35_collision_loop"
            elif progress < 58 and collisions >= 220:
                abort_reason = "pre_mid64_collision_explosion"
            elif progress < 74 and collisions >= 260:
                abort_reason = "p64_68_collision_loop"
            elif progress < 74 and penalties >= 24:
                abort_reason = "p64_68_penalty_explosion"
            elif progress < 80 and time.time() - started > 260:
                abort_reason = "slow_progress"
            if abort_reason:
                proc.send_signal(signal.SIGINT)
                break

        if time.time() - started > 340:
            abort_reason = "timeout"
            proc.send_signal(signal.SIGINT)
            break

    try:
        proc.wait(timeout=8)
    except subprocess.TimeoutExpired:
        proc.kill()

    if abort_reason:
        cleanup_simulator()

    parsed = score_log(log_path) if log_path else {"score": 999999.0, "error": "missing log path"}
    parsed.update({
        "candidate": row["candidate"],
        "run_returncode": proc.returncode,
        "aborted": bool(abort_reason),
        "abort_reason": abort_reason,
        "timed_out": abort_reason == "timeout",
        "log": log_path,
        "env": row["env"],
        "max_progress_seen": round(max_progress, 2),
        "last_collisions_seen": last_collisions,
        "last_penalties_seen": last_penalties,
        "tail": tail[-12:],
    })
    return parsed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--actual-top", type=int, default=0)
    parser.add_argument("--actual-names", nargs="*", default=[])
    parser.add_argument("--include-baseline-actual", action="store_true")
    args = parser.parse_args()

    subprocess.run(
        ["python3", "-m", "py_compile", "work/Template_Python/Bot_Python/my_car.py", "submissions/my_car.py"],
        cwd=ROOT,
        check=True,
    )

    rows = candidates()
    if args.limit:
        rows = rows[: args.limit]

    quick_rows = []
    for name, env in rows:
        result = quick_gate(name, env)
        quick_rows.append(result)
        print(json.dumps({
            "candidate": result["candidate"],
            "quick_cost": result["quick_cost"],
            "failures": result.get("map71_failures", [])[:4],
        }, ensure_ascii=False, sort_keys=True))

    quick_rows.sort(key=lambda item: (item["quick_cost"], item["candidate"]))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    quick_path = OUT_DIR / f"quick_summary_{time.strftime('%Y%m%d_%H%M%S')}.json"
    quick_path.write_text(json.dumps(quick_rows, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    print(f"[Map71QuickSummary] {quick_path}")

    if args.actual_top or args.actual_names:
        by_name = {row["candidate"]: row for row in quick_rows}
        actual_inputs = []
        for name in args.actual_names:
            if name not in by_name:
                raise SystemExit(f"unknown candidate for --actual-names: {name}")
            actual_inputs.append(by_name[name])
        if args.actual_top:
            seen = {row["candidate"] for row in actual_inputs}
            actual_inputs.extend(row for row in quick_rows[: args.actual_top] if row["candidate"] not in seen)
        if args.include_baseline_actual and not any(row["candidate"] == "baseline" for row in actual_inputs):
            baseline = next(row for row in quick_rows if row["candidate"] == "baseline")
            actual_inputs = [baseline] + actual_inputs
        actual_rows = []
        for row in actual_inputs:
            actual = actual_run(row)
            actual_rows.append(actual)
            print(json.dumps(actual, ensure_ascii=False, sort_keys=True))
        actual_path = OUT_DIR / f"actual_summary_{time.strftime('%Y%m%d_%H%M%S')}.json"
        actual_path.write_text(json.dumps(actual_rows, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        print(f"[Map71ActualSummary] {actual_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
