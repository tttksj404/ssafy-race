#!/usr/bin/env python3
import argparse
import json
import math
import sys
import time
import types
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BOT_DIR = ROOT / "work" / "Template_Python" / "Bot_Python"
sys.path.insert(0, str(BOT_DIR))

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


def make_client(map_num):
    client = DrivingClient.__new__(DrivingClient)
    client.is_debug = False
    client.enable_api_control = True
    client.track_type = 99
    client.is_accident = False
    client.accident_count = 0
    client.accident_step = 0
    client.uturn_step = 0
    client.uturn_count = 0
    client.prev_steering = 0.0
    client.prev_progress = 0.0
    client.stuck_count = 0
    client.recovery_count = 0
    client.last_target_middle = 0.0
    client.map_num = str(map_num)
    client.half_road_limit = 10.0
    client.target_offset = 0.0
    client._prev_target_offset = 0.0
    client._half_road_limit_used = None
    client.debug_log_fp = None
    client.debug_log_writer = None
    return client


@dataclass
class Scenario:
    name: str
    map_num: str
    speed: float
    to_middle: float
    moving_angle: float
    angles: list
    obstacles: list
    duration: float = 7.0
    dt: float = 0.12
    half_limit: float = 10.0
    gate: str = "obstacle"
    progress_base: float = 1.0
    init_accident_count: int = 0
    init_accident_step: int = 0
    init_recovery_dir: int = 0
    collided_steps: int = 0


def map31_angles(kind):
    if kind == "straight":
        return [0.0 for _ in range(20)]
    if kind == "p52_entry":
        return [0, 0, 0, 0, 0, 2, 9, 34, 56, 51, 18, 3, 3, 26, 52, 62, 70, 81, 91, 97]
    if kind == "p52_exit":
        return [-5, -38, -53, -53, -30, -4, 2, 6, 9, 13, 26, 58, 68, 32, 21, 20, 24, 46, 59, 72]
    if kind == "p60_gate":
        return [3, 6, 9, 13, 26, 58, 68, 32, 21, 20, 24, 46, 59, 72, 85, 91, 93, 93, 90, 78]
    if kind == "p68_gate":
        return [0, 0, 0, 0, 0, 0, 0, -1, -3, -3, -5, -6, -7, -8, -10, -11, -12, -13, -14, -15]
    if kind == "p87_approach":
        return [0, 0, 0, 0, 1, 5, 7, 9, 18, 50, 61, 73, 87, 98, 103, 104, 101, 94, 84, 70]
    if kind == "p87_close":
        return [2, 4, 14, 45, 62, 73, 87, 98, 103, 104, 101, 94, 84, 70, 55, 39, 23, 9, 0, 0]
    if kind == "right_sweep":
        return [-3, -5, -7, -9, -12, -15, -18, -21, -24, -26, -28, -28, -26, -22, -18, -12, -8, -4, 0, 0]
    if kind == "left_sweep":
        return [abs(v) for v in map31_angles("right_sweep")]
    return [0, 3, -4, 6, -8, 10, -12, 8, -6, 4, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]


def scenarios():
    return [
        Scenario(
            name="map31_open_accel_no_zigzag",
            map_num="31",
            speed=64.0,
            to_middle=0.25,
            moving_angle=0.5,
            angles=map31_angles("straight"),
            obstacles=[],
            duration=3.6,
            gate="open_accel",
        ),
        Scenario(
            name="map31_right_corner_apex_inside",
            map_num="31",
            speed=72.0,
            to_middle=3.2,
            moving_angle=-1.0,
            angles=map31_angles("right_sweep"),
            obstacles=[],
            duration=5.6,
            gate="corner_apex",
        ),
        Scenario(
            name="map31_left_corner_apex_inside",
            map_num="31",
            speed=72.0,
            to_middle=-3.2,
            moving_angle=1.0,
            angles=map31_angles("left_sweep"),
            obstacles=[],
            duration=5.6,
            gate="corner_apex",
        ),
        Scenario(
            name="map31_far_single_plan",
            map_num="31",
            speed=72.0,
            to_middle=0.0,
            moving_angle=0.0,
            angles=map31_angles("straight"),
            obstacles=[(92.0, -0.98), (188.0, 0.72)],
        ),
        Scenario(
            name="map31_first_slalom_no_edge",
            map_num="31",
            speed=76.0,
            to_middle=1.6,
            moving_angle=4.0,
            angles=map31_angles("right_sweep"),
            obstacles=[(64.0, -0.76), (121.0, 3.76), (180.0, 2.30)],
        ),
        Scenario(
            name="map31_p5_left_exit_recover_actual",
            map_num="31",
            speed=48.0,
            to_middle=-8.4,
            moving_angle=-31.0,
            angles=map31_angles("right_sweep"),
            obstacles=[(126.0, -0.76), (184.0, 3.76)],
            duration=2.8,
            gate="obstacle",
            progress_base=5.38,
        ),
        Scenario(
            name="map31_p10_right_box_left_pass_actual",
            map_num="31",
            speed=64.5,
            to_middle=3.9,
            moving_angle=7.9,
            angles=map31_angles("right_sweep"),
            obstacles=[(24.0, 3.76), (194.0, 2.30)],
            duration=3.0,
            gate="obstacle",
            progress_base=9.95,
        ),
        Scenario(
            name="map31_p27_entry_left_edge_actual",
            map_num="31",
            speed=107.0,
            to_middle=-7.2,
            moving_angle=-29.0,
            angles=map31_angles("right_sweep"),
            obstacles=[(81.8, 0.47)],
            duration=3.0,
            gate="obstacle",
            progress_base=25.27,
        ),
        Scenario(
            name="map31_p26_left_swing_actual",
            map_num="31",
            speed=82.7,
            to_middle=-5.41,
            moving_angle=32.1,
            angles=map31_angles("right_sweep"),
            obstacles=[(57.8, 0.47)],
            duration=2.6,
            gate="obstacle",
            progress_base=25.81,
        ),
        Scenario(
            name="map31_p25_left_edge_no_overshoot_actual",
            map_num="31",
            speed=102.4,
            to_middle=-10.48,
            moving_angle=-11.4,
            angles=map31_angles("right_sweep"),
            obstacles=[(69.4, 0.47)],
            duration=2.8,
            gate="obstacle",
            progress_base=25.54,
        ),
        Scenario(
            name="map31_p26_right_edge_no_pingpong_actual",
            map_num="31",
            speed=70.6,
            to_middle=11.44,
            moving_angle=50.6,
            angles=map31_angles("right_sweep"),
            obstacles=[(40.0, 0.47)],
            duration=2.6,
            gate="obstacle",
            progress_base=26.34,
        ),
        Scenario(
            name="map31_p27_late_left_edge_recover_actual",
            map_num="31",
            speed=87.0,
            to_middle=-12.33,
            moving_angle=-27.9,
            angles=map31_angles("right_sweep"),
            obstacles=[(194.9, 0.74)],
            duration=2.6,
            gate="obstacle",
            progress_base=27.69,
        ),
        Scenario(
            name="map31_p27_yaw_counter_actual",
            map_num="31",
            speed=92.0,
            to_middle=1.8,
            moving_angle=-45.9,
            angles=map31_angles("right_sweep"),
            obstacles=[(10.4, 0.47), (184.0, 0.74)],
            duration=2.4,
            gate="obstacle",
            progress_base=27.15,
        ),
        Scenario(
            name="map31_p28_right_edge_recover_actual",
            map_num="31",
            speed=76.0,
            to_middle=11.7,
            moving_angle=47.0,
            angles=map31_angles("right_sweep"),
            obstacles=[(158.0, 0.74), (238.0, 1.69)],
            duration=2.4,
            gate="obstacle",
            progress_base=28.76,
        ),
        Scenario(
            name="map31_p33_left_edge_recover_actual",
            map_num="31",
            speed=44.0,
            to_middle=-11.3,
            moving_angle=-9.0,
            angles=map31_angles("right_sweep"),
            obstacles=[(66.5, 1.69), (172.0, -0.70)],
            duration=2.6,
            gate="obstacle",
            progress_base=33.33,
        ),
        Scenario(
            name="map31_edge_trap_38pct",
            map_num="31",
            speed=78.0,
            to_middle=2.2,
            moving_angle=-8.0,
            angles=map31_angles("left_sweep"),
            obstacles=[(70.0, -0.70), (111.0, 4.87), (143.0, -2.42)],
        ),
        Scenario(
            name="map31_gate_cluster",
            map_num="31",
            speed=82.0,
            to_middle=-0.5,
            moving_angle=3.0,
            angles=map31_angles("straight"),
            obstacles=[(55.0, 7.25), (55.1, 2.90), (55.2, 0.74), (135.0, -0.98)],
        ),
        Scenario(
            name="map31_p52_entry_real",
            map_num="31",
            speed=104.0,
            to_middle=-3.5,
            moving_angle=-13.5,
            angles=map31_angles("p52_entry"),
            obstacles=[(42.7, -0.98), (139.4, 0.72)],
            duration=3.2,
            gate="obstacle",
            progress_base=51.6,
        ),
        Scenario(
            name="map31_p52_left_edge_recover_actual",
            map_num="31",
            speed=96.0,
            to_middle=-12.3,
            moving_angle=-14.0,
            angles=map31_angles("p52_entry"),
            obstacles=[(12.2, -0.98), (96.0, 0.72)],
            duration=2.6,
            gate="obstacle",
            progress_base=52.42,
        ),
        Scenario(
            name="map31_p55_exit_real",
            map_num="31",
            speed=97.0,
            to_middle=0.8,
            moving_angle=-8.8,
            angles=map31_angles("p52_exit"),
            obstacles=[(49.7, 0.72), (185.9, -0.76)],
            duration=3.2,
            gate="obstacle",
            progress_base=54.0,
        ),
        Scenario(
            name="map31_p60_box_gate_real",
            map_num="31",
            speed=112.0,
            to_middle=1.0,
            moving_angle=-7.6,
            angles=map31_angles("p60_gate"),
            obstacles=[(16.4, -0.76), (74.2, 3.76)],
            duration=3.0,
            gate="obstacle",
            progress_base=58.6,
        ),
        Scenario(
            name="map31_p60_right_edge_recover_actual",
            map_num="31",
            speed=70.0,
            to_middle=9.3,
            moving_angle=15.0,
            angles=map31_angles("p60_gate"),
            obstacles=[(19.9, -0.76), (78.0, 3.76)],
            duration=2.4,
            gate="obstacle",
            progress_base=59.95,
        ),
        Scenario(
            name="map31_p68_left_obstacle_real",
            map_num="31",
            speed=136.0,
            to_middle=2.3,
            moving_angle=1.0,
            angles=map31_angles("p68_gate"),
            obstacles=[(44.2, -3.86), (182.8, 1.38)],
            duration=3.2,
            gate="obstacle",
            progress_base=68.0,
        ),
        Scenario(
            name="map31_p68_left_obstacle_entry_actual",
            map_num="31",
            speed=142.0,
            to_middle=0.9,
            moving_angle=-0.7,
            angles=map31_angles("p68_gate"),
            obstacles=[(53.8, -3.86), (192.0, 1.38)],
            duration=3.4,
            gate="obstacle",
            progress_base=67.7,
        ),
        Scenario(
            name="map31_p40_swing_damp_real",
            map_num="31",
            speed=74.0,
            to_middle=-2.4,
            moving_angle=-18.0,
            angles=map31_angles("left_sweep"),
            obstacles=[(24.3, -2.42)],
            duration=2.8,
            gate="obstacle",
            progress_base=39.25,
        ),
        Scenario(
            name="map31_p40_right_edge_recover_actual",
            map_num="31",
            speed=72.0,
            to_middle=10.8,
            moving_angle=13.9,
            angles=map31_angles("left_sweep"),
            obstacles=[],
            duration=2.6,
            gate="obstacle",
            progress_base=40.32,
        ),
        Scenario(
            name="map31_p40_collision_escape_real",
            map_num="31",
            speed=5.4,
            to_middle=-4.6,
            moving_angle=26.5,
            angles=map31_angles("left_sweep"),
            obstacles=[(5.3, -2.42)],
            duration=2.4,
            gate="recovery",
            progress_base=39.78,
            init_accident_count=6,
            collided_steps=4,
        ),
        Scenario(
            name="map31_p87_approach_real",
            map_num="31",
            speed=126.0,
            to_middle=-0.3,
            moving_angle=-2.4,
            angles=map31_angles("p87_approach"),
            obstacles=[(70.5, -0.70), (111.6, 4.87), (143.4, -2.42)],
            duration=3.4,
            gate="obstacle",
            progress_base=86.3,
        ),
        Scenario(
            name="map31_p76_left_throw_real",
            map_num="31",
            speed=128.0,
            to_middle=-1.1,
            moving_angle=-0.4,
            angles=map31_angles("left_sweep"),
            obstacles=[(94.3, 0.47)],
            duration=2.8,
            gate="obstacle",
            progress_base=74.73,
        ),
        Scenario(
            name="map31_p87_close_real",
            map_num="31",
            speed=104.0,
            to_middle=1.3,
            moving_angle=17.6,
            angles=map31_angles("p87_close"),
            obstacles=[(9.9, -0.70), (51.0, 4.87), (82.8, -2.42)],
            duration=2.4,
            gate="obstacle",
            progress_base=87.9,
        ),
        Scenario(
            name="map31_actual_yaw_recovery",
            map_num="31",
            speed=24.5,
            to_middle=-4.36,
            moving_angle=41.4,
            angles=map31_angles("right_sweep"),
            obstacles=[(25.07, 0.72), (161.29, -0.76)],
            duration=3.0,
            gate="recovery",
        ),
        Scenario(
            name="map31_actual_pre_collision_gap",
            map_num="31",
            speed=84.9,
            to_middle=-2.19,
            moving_angle=15.1,
            angles=map31_angles("left_sweep"),
            obstacles=[(22.63, 0.74), (102.68, 1.69), (191.55, -0.70)],
            duration=3.2,
            gate="obstacle",
        ),
        Scenario(
            name="map31_p27_center_box_left_pass",
            map_num="31",
            speed=80.4,
            to_middle=-0.61,
            moving_angle=3.0,
            angles=map31_angles("left_sweep"),
            obstacles=[(28.6, 0.47), (108.7, 1.69), (197.5, -0.70)],
            duration=3.2,
            gate="obstacle",
            progress_base=26.88,
        ),
        Scenario(
            name="map10_high_speed_straight",
            map_num="10",
            speed=118.0,
            to_middle=0.4,
            moving_angle=2.0,
            angles=map31_angles("straight"),
            obstacles=[],
            duration=4.0,
        ),
        Scenario(
            name="map71_high_speed_open_no_zigzag",
            map_num="71",
            speed=118.0,
            to_middle=0.3,
            moving_angle=1.2,
            angles=map31_angles("straight"),
            obstacles=[],
            duration=3.8,
            gate="open_accel",
            progress_base=45.0,
        ),
        Scenario(
            name="map71_p33_slalom_exit",
            map_num="71",
            speed=76.0,
            to_middle=2.2,
            moving_angle=26.0,
            angles=map31_angles("straight"),
            obstacles=[(12.0, -2.78), (30.3, 7.29), (41.8, 2.38), (71.5, -2.57)],
            duration=4.2,
            gate="map71_segment",
            progress_base=32.7,
        ),
        Scenario(
            name="map71_p31_far_brake_setup",
            map_num="71",
            speed=131.0,
            to_middle=-0.2,
            moving_angle=0.2,
            angles=map31_angles("straight"),
            obstacles=[(83.0, -2.78), (101.3, 7.29), (112.8, 2.38)],
            duration=2.8,
            gate="map71_far_brake",
            progress_base=31.65,
        ),
        Scenario(
            name="map71_p31_overspeed_entry",
            map_num="71",
            speed=167.0,
            to_middle=0.15,
            moving_angle=-1.3,
            angles=map31_angles("straight"),
            obstacles=[(69.7, -2.78), (88.0, 7.29), (99.6, 2.38)],
            duration=2.4,
            gate="map71_entry_setup",
            progress_base=31.86,
        ),
        Scenario(
            name="map71_p52_far_brake_setup",
            map_num="71",
            speed=158.0,
            to_middle=-0.05,
            moving_angle=0.0,
            angles=map31_angles("straight"),
            obstacles=[(109.9, -6.62), (110.4, 6.39), (132.0, 4.66)],
            duration=3.2,
            gate="map71_far_brake",
            progress_base=52.0,
        ),
        Scenario(
            name="map71_p67_far_brake_setup",
            map_num="71",
            speed=105.0,
            to_middle=-7.2,
            moving_angle=1.3,
            angles=map31_angles("straight"),
            obstacles=[(50.7, 2.79), (128.3, -1.58)],
            duration=2.4,
            gate="map71_far_brake",
            progress_base=67.4,
        ),
        Scenario(
            name="map71_p33_collision_unwind",
            map_num="71",
            speed=4.0,
            to_middle=-8.3,
            moving_angle=22.0,
            angles=map31_angles("straight"),
            obstacles=[(5.1, -8.2), (5.2, -3.01), (61.0, 3.22), (61.1, 8.84)],
            duration=3.6,
            gate="map71_recovery",
            progress_base=35.7,
            init_accident_count=9,
            init_recovery_dir=1,
            collided_steps=2,
        ),
        Scenario(
            name="map71_p33_right_wall_unwind",
            map_num="71",
            speed=0.1,
            to_middle=5.1,
            moving_angle=43.0,
            angles=map31_angles("straight"),
            obstacles=[(2.4, 2.38), (32.1, -2.57), (58.1, -6.55), (96.5, -0.71)],
            duration=3.6,
            gate="map71_recovery",
            progress_base=33.56,
            init_accident_count=9,
            collided_steps=2,
        ),
        Scenario(
            name="map71_p64_compound_gate",
            map_num="71",
            speed=98.0,
            to_middle=3.0,
            moving_angle=12.0,
            angles=map31_angles("right_sweep"),
            obstacles=[(50.2, -3.0), (81.5, 4.54), (125.3, -4.95)],
            duration=4.8,
            gate="map71_segment",
            progress_base=64.0,
        ),
        Scenario(
            name="map71_p54_dense_wall_gate",
            map_num="71",
            speed=84.0,
            to_middle=1.35,
            moving_angle=-4.5,
            angles=map31_angles("straight"),
            obstacles=[(48.4, -6.62), (48.9, 6.39), (70.5, 4.66), (97.5, -3.78)],
            duration=4.8,
            gate="map71_segment",
            progress_base=53.0,
        ),
        Scenario(
            name="map71_p68_right_punch",
            map_num="71",
            speed=105.0,
            to_middle=5.8,
            moving_angle=3.5,
            angles=map31_angles("straight"),
            obstacles=[(58.6, 2.79), (136.2, -1.58)],
            duration=3.4,
            gate="map71_segment",
            progress_base=67.2,
        ),
        Scenario(
            name="map71_p98_finish_pair",
            map_num="71",
            speed=67.0,
            to_middle=-4.4,
            moving_angle=-12.0,
            angles=map31_angles("left_sweep"),
            obstacles=[(65.1, 1.57), (66.9, 1.47)],
            duration=4.0,
            gate="map71_segment",
            progress_base=97.4,
        ),
        Scenario(
            name="map71_p94_left_gate",
            map_num="71",
            speed=140.0,
            to_middle=-9.4,
            moving_angle=-9.0,
            angles=map31_angles("straight"),
            obstacles=[(54.0, 1.99), (54.1, 3.96), (95.0, -0.94)],
            duration=5.0,
            gate="map71_segment",
            progress_base=93.2,
        ),
    ]


MAP31_EDGE_RECOVERY_SCENARIOS = {
    "map31_p25_left_edge_no_overshoot_actual",
    "map31_p26_right_edge_no_pingpong_actual",
    "map31_p27_late_left_edge_recover_actual",
    "map31_p28_right_edge_recover_actual",
    "map31_p33_left_edge_recover_actual",
    "map31_p40_right_edge_recover_actual",
    "map31_p52_left_edge_recover_actual",
    "map31_p60_right_edge_recover_actual",
}


def control(client, scenario, state, progress_pct, step):
    distance = state["distance"]
    obstacles = [
        {"dist": obs_s - distance, "to_middle": obs_mid}
        for obs_s, obs_mid in scenario.obstacles
        if -8.0 < obs_s - distance < 205.0
    ]
    sensing = Bag(
        to_middle=state["to_middle"],
        collided=step < scenario.collided_steps,
        speed=state["speed"],
        moving_forward=True,
        moving_angle=state["angle"],
        lap_progress=progress_pct,
        track_forward_angles=scenario.angles,
        track_forward_obstacles=obstacles,
        opponent_cars_info=[],
        distance_to_way_points=[10.0 for _ in range(20)],
        half_road_limit=scenario.half_limit,
    )
    controls = Bag(steering=0.0, throttle=0.0, brake=0.0)
    out = client.control_driving(controls, sensing)
    return out, obstacles


def simulate(scenario):
    client = make_client(scenario.map_num)
    client.accident_count = scenario.init_accident_count
    client.accident_step = scenario.init_accident_step
    client.recovery_dir = scenario.init_recovery_dir
    road_limit = max(2.5, scenario.half_limit - 1.7)
    state = {
        "distance": 0.0,
        "speed": scenario.speed,
        "to_middle": scenario.to_middle,
        "angle": scenario.moving_angle,
    }
    rows = []
    failures = []
    prev_steering = 0.0
    brake_sum = 0.0
    brake_count = 0
    throttle_sum = 0.0
    abs_steer_sum = 0.0
    max_abs_steering = 0.0
    steering_sign_changes = 0
    prev_steer_sign = 0
    apex_inside_hits = 0
    apex_samples = 0
    max_edge = abs(state["to_middle"]) / road_limit
    max_abs_angle = abs(state["angle"])
    max_steer_delta = 0.0
    start_speed = state["speed"]
    curve_dir = sign(sum(scenario.angles[:10]))

    steps = int(scenario.duration / scenario.dt)
    for step in range(steps):
        progress_pct = scenario.progress_base + state["distance"] / 18.0
        out, visible_obstacles = control(client, scenario, state, progress_pct, step)
        nearest = min((obs["dist"] for obs in visible_obstacles if obs["dist"] > 0), default=None)
        nearest_gap = None
        if nearest is not None:
            nearest_gap = min(
                abs(obs["to_middle"] - state["to_middle"])
                for obs in visible_obstacles
                if obs["dist"] > 0 and abs(obs["dist"] - nearest) < 0.01
            )

        steer_delta = abs(out.steering - prev_steering)
        max_steer_delta = max(max_steer_delta, steer_delta)
        prev_steering = out.steering
        brake_sum += max(0.0, out.brake)
        throttle_sum += out.throttle
        abs_steer_sum += abs(out.steering)
        max_abs_steering = max(max_abs_steering, abs(out.steering))
        brake_count += 1
        steer_sign = sign(out.steering)
        if steer_sign and prev_steer_sign and steer_sign != prev_steer_sign:
            steering_sign_changes += 1
        if steer_sign:
            prev_steer_sign = steer_sign

        if scenario.gate == "corner_apex" and 38.0 <= state["distance"] <= 92.0:
            apex_samples += 1
            if curve_dir and state["to_middle"] * curve_dir > road_limit * 0.16:
                apex_inside_hits += 1

        early_brake_limit = 0.22
        if scenario.gate == "map71_far_brake":
            early_brake_limit = 0.55
        elif scenario.gate == "map71_entry_setup":
            early_brake_limit = 0.82
        if nearest is not None and nearest > 45.0 and out.brake > early_brake_limit:
            failures.append(f"brakes_too_early@{step}:dist={nearest:.1f},brake={out.brake:.2f}")
        if scenario.gate == "open_accel" and out.brake > 0.05:
            failures.append(f"open_accel_brake@{step}:brake={out.brake:.2f}")
        if scenario.gate == "open_accel" and out.throttle < 0.92:
            failures.append(f"open_accel_lifts@{step}:throttle={out.throttle:.2f}")
        if scenario.gate == "open_accel" and abs(out.steering) > 0.12:
            failures.append(f"open_accel_zigzag_steer@{step}:steer={out.steering:.2f}")
        if scenario.gate in ("recovery", "map71_recovery") and step < 4:
            # 현 목표는 무충돌이 아니라 빠른 완주다. 복구 게이트도
            # 장시간 정지/풀브레이크보다 즉시 재가속 가능한지를 본다.
            if out.brake > 0.8:
                failures.append(f"recovery_overbrake@{step}:brake={out.brake:.2f}")
            if out.throttle < -0.8:
                failures.append(f"recovery_reverse_too_hard@{step}:throttle={out.throttle:.2f}")
        if scenario.name == "map31_p40_collision_escape_real" and step < 6:
            if out.steering < -0.05:
                failures.append(f"map31_p40_wrong_escape_steer@{step}:steer={out.steering:.2f}")
        edge_limit = 1.05
        if scenario.gate in ("map71_segment", "map71_recovery", "map71_far_brake", "map71_entry_setup"):
            edge_limit = 1.28
        if scenario.name == "map31_p5_left_exit_recover_actual":
            edge_limit = 1.28
        if scenario.name == "map31_p27_entry_left_edge_actual":
            edge_limit = 1.30
        if scenario.name == "map31_p27_yaw_counter_actual":
            edge_limit = 1.18
        if scenario.name in MAP31_EDGE_RECOVERY_SCENARIOS:
            edge_limit = 1.95
        if abs(state["to_middle"]) / road_limit > edge_limit:
            failures.append(f"edge_overuse@{step}:middle={state['to_middle']:.2f}")
        if steer_delta > 0.72 and state["speed"] > 35.0:
            failures.append(f"steer_snap@{step}:delta={steer_delta:.2f},speed={state['speed']:.1f}")
        if scenario.name not in MAP31_EDGE_RECOVERY_SCENARIOS and scenario.name != "map31_p27_yaw_counter_actual" and abs(state["angle"]) > 42.0 and state["speed"] > 24.0:
            failures.append(f"yaw_breakdown@{step}:angle={state['angle']:.1f},speed={state['speed']:.1f}")
        virtual_collision_gap = 1.0
        if scenario.name == "map31_p40_collision_escape_real":
            virtual_collision_gap = 0.35
        if scenario.name == "map31_p40_swing_damp_real":
            virtual_collision_gap = 0.50
        if nearest is not None and -1.0 < nearest < 1.0 and nearest_gap is not None and nearest_gap < virtual_collision_gap:
            failures.append(f"virtual_collision@{step}:gap={nearest_gap:.2f}")

        accel = out.throttle * 7.4 - out.brake * 16.0 - abs(out.steering) * max(state["speed"], 20.0) * 0.018
        speed_cap = 190.0 if scenario.map_num == "71" else 135.0
        state["speed"] = clamp(state["speed"] + accel * scenario.dt, 0.0, speed_cap)
        state["angle"] += (out.steering * 78.0 - state["angle"] * 1.35) * scenario.dt
        state["to_middle"] += math.sin(math.radians(state["angle"])) * max(state["speed"], 5.0) * scenario.dt / 3.6
        state["distance"] += state["speed"] * scenario.dt / 3.6
        max_edge = max(max_edge, abs(state["to_middle"]) / road_limit)
        max_abs_angle = max(max_abs_angle, abs(state["angle"]))

        rows.append(
            {
                "step": step,
                "distance": round(state["distance"], 2),
                "speed": round(state["speed"], 2),
                "middle": round(state["to_middle"], 2),
                "angle": round(state["angle"], 2),
                "steering": round(out.steering, 3),
                "throttle": round(out.throttle, 3),
                "brake": round(out.brake, 3),
                "nearest": None if nearest is None else round(nearest, 2),
            }
        )

    avg_brake = brake_sum / max(brake_count, 1)
    avg_throttle = throttle_sum / max(brake_count, 1)
    avg_abs_steering = abs_steer_sum / max(brake_count, 1)
    inside_ratio = apex_inside_hits / max(apex_samples, 1)

    if scenario.gate == "open_accel":
        if avg_throttle < 0.96:
            failures.append(f"open_accel_avg_throttle_low:{avg_throttle:.3f}")
        if avg_brake > 0.02:
            failures.append(f"open_accel_avg_brake_high:{avg_brake:.3f}")
        if avg_abs_steering > 0.045:
            failures.append(f"open_accel_avg_steer_high:{avg_abs_steering:.3f}")
        if max_abs_steering > 0.12:
            failures.append(f"open_accel_max_steer_high:{max_abs_steering:.3f}")
        if steering_sign_changes > 1:
            failures.append(f"open_accel_steer_oscillation:{steering_sign_changes}")
        if state["speed"] < start_speed + 14.0:
            failures.append(f"open_accel_speed_gain_low:{state['speed'] - start_speed:.2f}")

    if scenario.gate == "corner_apex":
        if apex_samples == 0:
            failures.append("corner_apex_no_samples")
        elif inside_ratio < 0.62:
            failures.append(f"corner_apex_not_inside:{inside_ratio:.3f}")
        if avg_brake > 0.08:
            failures.append(f"corner_apex_brake_high:{avg_brake:.3f}")
        if max_abs_angle > 30.0:
            failures.append(f"corner_apex_yaw_high:{max_abs_angle:.1f}")

    if scenario.map_num == "31" and avg_brake > 0.36:
        failures.append(f"brake_average_high:{avg_brake:.3f}")
    if scenario.map_num == "31" and scenario.name not in {"map31_p5_left_exit_recover_actual", "map31_p27_entry_left_edge_actual", "map31_p27_yaw_counter_actual"} | MAP31_EDGE_RECOVERY_SCENARIOS and max_edge > 1.08:
        failures.append(f"max_edge_high:{max_edge:.3f}")
    if scenario.name == "map31_p5_left_exit_recover_actual" and abs(state["to_middle"]) > 5.8:
        failures.append(f"map31_p5_exit_not_recovered:{state['to_middle']:.1f}")
    if scenario.name == "map31_p27_entry_left_edge_actual" and abs(state["to_middle"]) > 5.8:
        failures.append(f"map31_p27_entry_not_recovered:{state['to_middle']:.1f}")
    if scenario.name == "map31_p27_yaw_counter_actual":
        if abs(state["to_middle"]) > 6.4:
            failures.append(f"map31_p27_yaw_not_contained:{state['to_middle']:.1f}")
        if max_abs_angle > 48.0:
            failures.append(f"map31_p27_yaw_counter_angle:{max_abs_angle:.1f}")
    if scenario.name in MAP31_EDGE_RECOVERY_SCENARIOS:
        if scenario.to_middle > 0 and state["to_middle"] > scenario.to_middle - 2.6:
            failures.append(f"map31_edge_recovery_weak:{state['to_middle']:.1f}")
        if scenario.to_middle < 0 and state["to_middle"] < scenario.to_middle + 2.6:
            failures.append(f"map31_edge_recovery_weak:{state['to_middle']:.1f}")
        if state["speed"] < max(34.0, scenario.speed - 12.0):
            failures.append(f"map31_edge_recovery_slow:{state['speed']:.1f}")
    if scenario.map_num == "31" and scenario.gate != "recovery" and scenario.name not in MAP31_EDGE_RECOVERY_SCENARIOS and scenario.name != "map31_p27_yaw_counter_actual" and max_abs_angle > 38.0:
        failures.append(f"max_yaw_high:{max_abs_angle:.1f}")
    if scenario.map_num == "31" and scenario.name not in MAP31_EDGE_RECOVERY_SCENARIOS and scenario.name != "map31_p40_collision_escape_real" and max_steer_delta > 0.68:
        failures.append(f"steer_delta_high:{max_steer_delta:.2f}")
    if scenario.gate in ("map71_segment", "map71_recovery", "map71_far_brake", "map71_entry_setup"):
        if avg_throttle < 0.74:
            failures.append(f"map71_throttle_low:{avg_throttle:.3f}")
        if avg_brake > 0.34:
            failures.append(f"map71_brake_high:{avg_brake:.3f}")
        if max_abs_angle > 72.0:
            failures.append(f"map71_yaw_high:{max_abs_angle:.1f}")
        if max_edge > 1.35:
            failures.append(f"map71_edge_extreme:{max_edge:.3f}")
        if scenario.name == "map71_p33_slalom_exit" and max_edge > 1.08:
            failures.append(f"map71_p33_penalty_edge:{max_edge:.3f}")
        if scenario.gate == "map71_far_brake":
            if avg_brake > 0.46:
                failures.append(f"map71_far_brake_avg_high:{avg_brake:.3f}")
            if max_edge > 1.08:
                failures.append(f"map71_far_brake_edge:{max_edge:.3f}")
            if max_abs_angle > 38.0:
                failures.append(f"map71_far_brake_yaw:{max_abs_angle:.1f}")
            if avg_throttle < 0.50:
                failures.append(f"map71_far_brake_throttle_low:{avg_throttle:.3f}")
        if scenario.name == "map71_p31_overspeed_entry":
            speed_drop = start_speed - state["speed"]
            if state["speed"] > 145.0:
                failures.append(f"map71_p31_entry_speed_high:{state['speed']:.1f}")
            if state["speed"] < 105.0:
                failures.append(f"map71_p31_entry_speed_low:{state['speed']:.1f}")
            if speed_drop < 22.0:
                failures.append(f"map71_p31_entry_drop_low:{speed_drop:.1f}")
            if max_edge > 1.02:
                failures.append(f"map71_p31_entry_edge:{max_edge:.3f}")
            if max_abs_angle > 42.0:
                failures.append(f"map71_p31_entry_yaw:{max_abs_angle:.1f}")
        if scenario.name == "map71_p33_collision_unwind":
            if state["speed"] < 30.0:
                failures.append(f"map71_p33_relaunch_speed_low:{state['speed']:.1f}")
            if state["distance"] < 15.0:
                failures.append(f"map71_p33_relaunch_distance_low:{state['distance']:.1f}")
            if max_abs_angle > 46.0:
                failures.append(f"map71_p33_relaunch_yaw:{max_abs_angle:.1f}")
            if avg_brake > 0.06:
                failures.append(f"map71_p33_relaunch_brake:{avg_brake:.3f}")
        if scenario.name == "map71_p33_right_wall_unwind":
            if state["speed"] < 24.0:
                failures.append(f"map71_p33_right_relaunch_speed_low:{state['speed']:.1f}")
            if state["distance"] < 10.0:
                failures.append(f"map71_p33_right_relaunch_distance_low:{state['distance']:.1f}")
            if max_abs_angle > 58.0:
                failures.append(f"map71_p33_right_relaunch_yaw:{max_abs_angle:.1f}")
            if state["to_middle"] > 6.8:
                failures.append(f"map71_p33_right_relaunch_edge:{state['to_middle']:.1f}")
        if scenario.name == "map71_p64_compound_gate" and max_abs_angle > 40.0:
            failures.append(f"map71_p64_recovery_yaw:{max_abs_angle:.1f}")
        if scenario.name == "map71_p54_dense_wall_gate":
            if max_edge > 1.08:
                failures.append(f"map71_p54_penalty_edge:{max_edge:.3f}")
            if max_abs_angle > 38.0:
                failures.append(f"map71_p54_yaw_trap:{max_abs_angle:.1f}")
            if avg_brake > 0.30:
                failures.append(f"map71_p54_brake_high:{avg_brake:.3f}")
        if scenario.name == "map71_p94_left_gate":
            if max_abs_angle > 46.0:
                failures.append(f"map71_p94_yaw_trap:{max_abs_angle:.1f}")
            if state["speed"] < 72.0:
                failures.append(f"map71_p94_exit_speed_low:{state['speed']:.1f}")
    if scenario.name == "map31_p40_collision_escape_real":
        if state["distance"] < 7.0:
            failures.append(f"map31_p40_escape_distance_low:{state['distance']:.1f}")
        if state["speed"] < 18.0:
            failures.append(f"map31_p40_escape_speed_low:{state['speed']:.1f}")
        if state["to_middle"] < -4.7:
            failures.append(f"map31_p40_escape_still_left:{state['to_middle']:.1f}")

    return {
        "name": scenario.name,
        "map": scenario.map_num,
        "passed": not failures,
        "failures": failures[:12],
        "metrics": {
            "avg_brake": round(avg_brake, 3),
            "avg_throttle": round(avg_throttle, 3),
            "avg_abs_steering": round(avg_abs_steering, 3),
            "inside_ratio": round(inside_ratio, 3) if scenario.gate == "corner_apex" else None,
            "max_edge": round(max_edge, 3),
            "max_abs_steering": round(max_abs_steering, 3),
            "max_abs_angle": round(max_abs_angle, 2),
            "max_steer_delta": round(max_steer_delta, 3),
            "steering_sign_changes": steering_sign_changes,
            "end_distance": round(state["distance"], 2),
            "end_speed": round(state["speed"], 2),
            "speed_drop": round(start_speed - state["speed"], 2),
        },
        "last_rows": rows[-5:],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--json-out", default="")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--map", dest="map_filter", default="")
    parser.add_argument("--name-prefix", default="")
    args = parser.parse_args()

    started = time.time()
    selected = scenarios()
    if args.map_filter:
        selected = [scenario for scenario in selected if scenario.map_num == args.map_filter]
    if args.name_prefix:
        selected = [scenario for scenario in selected if scenario.name.startswith(args.name_prefix)]
    results = [simulate(scenario) for scenario in selected]
    summary = {
        "elapsed_sec": round(time.time() - started, 4),
        "passed": all(item["passed"] for item in results),
        "results": results,
    }

    if args.json_out:
        output_path = Path(args.json_out)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")

    if not args.quiet:
        print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
