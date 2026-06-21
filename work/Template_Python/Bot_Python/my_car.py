from DrivingInterface.drive_controller import DrivingController
import math
import csv
import os
import re
from datetime import datetime

before = 0  # 직전 프레임 steering 값 (부드러운 조향 스무딩용 전역 변수)


def _env_float(name, default):
    try:
        return float(os.environ.get(name, default))
    except Exception:
        return default


def _env_int(name, default):
    try:
        return int(float(os.environ.get(name, default)))
    except Exception:
        return default


def _env_bool(name, default=True):
    raw = os.environ.get(name)
    if raw is None:
        return default
    return str(raw).strip().lower() not in {"0", "false", "no", "off"}


class DrivingClient(DrivingController):

    def __init__(self):
        # =========================================================== #
        #  Area for member variables =============================== #
        # =========================================================== #

        self.is_debug = False

        # api or keyboard
        self.enable_api_control = True  # True(Controlled by code) /False(Controlled by keyboard)
        super().set_enable_api_control(self.enable_api_control)

        self.track_type = 99

        self.is_accident = False
        self.recovery_count = 0
        self.accident_count = 0
        self.accident_step = 0
        self.recovery_dir = 0
        self.uturn_step = 0
        self.uturn_count = 0
        self.escape_count = 0
        self.escape_dir = 0
        self._committed_target = None  # crash-variance stabilizer (committed line)

        # ========================= 로그(Full Spec) =========================
        self._log_dir = os.path.dirname(os.path.abspath(__file__))

        # 실행마다 debug_log_full.csv / debug_log_full_2.csv ... 자동 증가
        self.debug_log_file = self._get_next_log_path(base_name="debug_log_full", ext=".csv")

        self.debug_log_fp = None
        self.debug_log_writer = None

        self.target_offset = 0.0  # 로그에 찍을 목표 차선 offset

        # 타겟 오프셋 스무딩(92.83 구간 전용)
        self._prev_target_offset = 0.0

        # progress 90 이후 인식 도로폭(로그용)
        self._half_road_limit_used = None

        self._init_debug_logger()
        # =================================================================

        super().__init__()

    # ------------------ 자동 파일 번호 증가 ------------------ #
    def _get_next_log_path(self, base_name: str, ext: str = ".csv") -> str:
        """
        debug_log_full.csv가 있으면 다음은 debug_log_full_2.csv, _3.csv ... 식으로 자동 생성.
        - base 파일이 없으면 base를 첫 파일로 사용.
        """
        log_dir = self._log_dir
        base_path = os.path.join(log_dir, f"{base_name}{ext}")
        pattern = re.compile(rf"^{re.escape(base_name)}_(\d+){re.escape(ext)}$")

        max_idx = 0
        try:
            for fn in os.listdir(log_dir):
                m = pattern.match(fn)
                if not m:
                    continue
                try:
                    n = int(m.group(1))
                    if n > max_idx:
                        max_idx = n
                except Exception:
                    pass

            if max_idx == 0:
                # base 파일이 이미 있으면 다음은 _2
                if os.path.exists(base_path):
                    return os.path.join(log_dir, f"{base_name}_2{ext}")
                return base_path

            return os.path.join(log_dir, f"{base_name}_{max_idx + 1}{ext}")
        except Exception:
            # 최후의 보루: 타임스탬프 파일명
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            return os.path.join(log_dir, f"{base_name}_{ts}{ext}")

    def control_driving(self, car_controls, sensing_info):

        if self.is_debug:
            print("=========================================================")
            print("[MyCar] to middle: {}".format(sensing_info.to_middle))
            print("[MyCar] collided: {}".format(sensing_info.collided))
            print("[MyCar] car speed: {} km/h".format(sensing_info.speed))
            print("[MyCar] is moving forward: {}".format(sensing_info.moving_forward))
            print("[MyCar] moving angle: {}".format(sensing_info.moving_angle))
            print("[MyCar] lap_progress: {}".format(sensing_info.lap_progress))
            print("[MyCar] track_forward_angles: {}".format(sensing_info.track_forward_angles))
            print("[MyCar] track_forward_obstacles: {}".format(sensing_info.track_forward_obstacles))
            print("[MyCar] opponent_cars_info: {}".format(sensing_info.opponent_cars_info))
            print("[MyCar] distance_to_way_points: {}".format(sensing_info.distance_to_way_points))
            print("=========================================================")

        lap = sensing_info.lap_progress

        # ===== progress 90% 이후 도로폭을 더 안쪽으로 '인식' (요청사항) =====
        # 기존: half_load_width = self.half_road_limit - 1.5
        # 변경: 90% 이후는 -2.5로 (즉 half_road_limit_used를 -1.0 줄여서 동일 계산식 유지)
        half_road_limit_used = self.half_road_limit
        if lap >= 90.0 and lap <= 97.2 and str(getattr(self, "map_num", "")) in ("10", "31", "61", "71", "161"):
            half_road_limit_used -= 1.25  # known maps only (unseen-map safe)
        self._half_road_limit_used = half_road_limit_used
        # =======================================================

        half_load_width = half_road_limit_used - 1.5  # SHIN 수정3->1.5
        car_controls.throttle = 1
        car_controls.brake = 0

        # 기본 상태
        middle = sensing_info.to_middle
        spd = sensing_info.speed
        angles = sensing_info.track_forward_angles
        map_num = str(getattr(self, "map_num", ""))
        # HOLD-OUT: blank map_num => all map_num-guarded blocks skip, so the bot
        # runs the GENERAL path (as it would on an unseen test map). Diagnostic.
        if _env_bool("SSAFY_GENERAL_ONLY", False):
            map_num = ""
        # UNSEEN-MAP SAFETY: lap-only ("un-guarded") hardcoding fires ONLY on the 5
        # known maps; on any other (unseen test) map it is disabled so the bot runs
        # the clean general path instead of arbitrary fixed-progress overrides.
        known_map = map_num in ("10", "31", "61", "71", "161")
        narrow_track = self.half_road_limit <= 8.6

        # ===== 구간 하드코딩 플래그 =====
        seg_2729 = (25.2 <= lap <= 30.0)
        seg_0510 = (5.0 <= lap <= 10.0)
        seg_1783 = (17.0 <= lap <= 18.4)
        seg_3339 = (32.95 <= lap <= 33.45)  # 33.39 포함 (약 1.5초 체감 구간)
        seg_9283 = (92.45 <= lap <= 93.25)  # 92.83 포함
        seg_6767 = (67.3 <= lap <= 68.1)  # 92.83 포함
        seg_5354 = (53.0 <= lap <= 53.4)
        seg_5444 = (53.41 <= lap <= 54.7)
        seg_9898 = (98.0 <= lap <= 98.2)
        seg_8791 = (87.4 <= lap <= 91.8)
        seg_n161_4951 = (map_num == "161" and narrow_track and 49.2 <= lap <= 51.4)
        seg_n161_6870 = (map_num == "161" and narrow_track and 68.0 <= lap <= 70.25)
        seg_m61_2224 = (map_num == "61" and 21.8 <= lap <= 23.7)
        seg_m61_3035 = (map_num == "61" and 30.8 <= lap <= 34.9)
        seg_m61_5962 = (map_num == "61" and 59.6 <= lap <= 61.6)
        seg_m61_6365 = (map_num == "61" and 63.8 <= lap <= 65.2)
        seg_m61_6568 = (map_num == "61" and 65.2 < lap <= 68.5)
        seg_m61_7679 = (map_num == "61" and 76.7 <= lap <= 79.0)
        seg_m61_9294 = (map_num == "61" and 92.0 <= lap <= 94.2)
        # =============================

        ################################## 장애물 회피 / 목표 차선 계산 #########################################

        # 인식거리 설정
        ob_start = 0
        ob_end = 260  # 필요하면 200 정도까지 늘려도 됨

        # 도로 폭 전체를 0.1m 단위로 샘플링한 후보 라인
        ob_line = [round(i * 0.1, 1) for i in range(-int(half_load_width) * 10, int(half_load_width) * 10)]
        ob_line2 = []
        dist = 0
        cnt = 0

        # 장애물 근접 정도(최소 dist) 추적: 가까울수록 회피/조향 반영 강하게
        nearest_ob_dist = 10**9

        # ⚠️ 다른 로직 건드리지 말라는 요청: 장애물 순서/스코어링은 원본 유지
        obstacles = sensing_info.track_forward_obstacles or []
        # Map31 후반 3연속 장애물: -2.42 박스/타이어를 지나기 전에 라인이
        # 오른쪽으로 풀리면 충돌 후 왼쪽 바깥으로 밀린다.
        seg_8790_left_gate = (
            87.4 <= lap <= 90.25
            and middle < -3.0
            and any(0 <= obj['dist'] <= 70 and -3.3 <= obj['to_middle'] <= -1.5 for obj in obstacles)
        )

        if not known_map:
            # UNSEEN map: drop the lap-only (un-guarded) segments so they cannot
            # impose arbitrary fixed-progress speed caps / lane forces on geometry
            # they were never tuned for. (Also disabled under GENERAL_ONLY, which
            # blanks map_num.) Known maps keep their tuning unchanged.
            seg_2729 = seg_0510 = seg_1783 = seg_3339 = seg_9283 = False
            seg_6767 = seg_5354 = seg_5444 = seg_9898 = seg_8791 = seg_8790_left_gate = False

        for obj in obstacles:
            ob_dist, ob_middle = obj['dist'], obj['to_middle']

            if ob_start <= ob_dist <= ob_end:
                # ====== 커브 안쪽/직후 장애물: 너무 먼 거리에서 미리 회피하지 않기 ======
                idx = int(ob_dist / 10)
                if angles:
                    if idx >= len(angles):
                        idx = len(angles) - 1
                    if idx < 0:
                        idx = 0
                    local_angle = abs(angles[idx])
                else:
                    local_angle = 0.0
                    idx = 0

                # 커브 각도가 큰 구간 + 아직 120m 이상 남았으면 → 지금은 회피 대상에서 제외
                if local_angle > 50 and ob_dist > 120:
                    continue
                # ===========================================================

                # 여기까지 통과한 장애물만 "실제 회피 대상"
                if ob_dist < nearest_ob_dist:
                    nearest_ob_dist = ob_dist

                ped = _env_float("SSAFY_GEN_OBSTACLE_PED", 2.7 if not known_map else 2.25)  # general clearance (unseen tuned)
                if map_num == "71":
                    ped = _env_float("SSAFY_MAP71_OBSTACLE_PED", 3.0)
                elif map_num == "61":
                    ped = _env_float("SSAFY_MAP61_OBSTACLE_PED", 2.25)

                # 장애물 주변 영역 제거
                ob_line = [i for i in ob_line if not ob_middle - ped <= i <= ob_middle + ped]
                cnt += 1

            if not ob_line:
                ob_line = ob_line2[:]
                break
            else:
                ob_line2 = ob_line[:]

            # 너무 많은 장애물까지 보지 않도록 컷
            if ob_dist - dist > 50 and cnt >= 2:
                break
            else:
                dist = ob_dist

        # 내 현재 위치 기준 가장 가까운 안전 위치를 타겟으로
        edge_margin = half_road_limit_used - 1.5  # 가장자리 패널티 시작 지점

        def target_cost(x):
            # 1️⃣ 기본 비용: 현재 위치와의 거리
            cost = abs(x - middle)

            # 2️⃣ 가장자리 패널티: 트랙 끝에 가까울수록 불리
            edge_dist = abs(x)
            if edge_dist > edge_margin:
                cost += (edge_dist - edge_margin) ** 2 * 6.0

            return cost

        # map61 avoidance LOGIC dispatch (search explores modes + params).
        corridor_speed_cap = None
        _amode = os.environ.get("SSAFY_AVOID_MODE", "") or (
            os.environ.get("SSAFY_MAP61_AVOID_MODE", "ftg") if map_num == "61" else "orig")
        if _amode == "ftg" and ob_line:
            # Follow-The-Gap: center of the WIDEST free corridor.
            runs = []
            start = ob_line[0]
            prev = ob_line[0]
            for pos in ob_line[1:]:
                if pos - prev > 0.15:
                    runs.append((start, prev))
                    start = pos
                prev = pos
            runs.append((start, prev))
            best_gap = (ob_line[0], ob_line[-1])
            best_score = float("-inf")
            for lo, hi in runs:
                center = (lo + hi) / 2
                score = (hi - lo) - 0.05 * abs(center - middle)
                if score > best_score:
                    best_score = score
                    best_gap = (lo, hi)
            lo, hi = best_gap
            margin = min(_env_float("SSAFY_MAP61_FTG_MARGIN", 0.8), (hi - lo) / 2)
            target_raw = max(lo + margin, min(hi - margin, middle))
        elif _amode == "nearest" and ob_line and obstacles:
            # avoid ONLY the nearest obstacle strongly (dont over-constrain).
            nearest_mid = min(obstacles, key=lambda o: o["dist"])["to_middle"]
            target_raw = max(ob_line, key=lambda x: abs(x - nearest_mid) - 0.5 * abs(x - middle))
        elif _amode == "potential" and ob_line:
            # potential field: repulsion from near obstacles + center attraction.
            force = 0.0
            for ob in obstacles:
                if ob["dist"] < 90.0:
                    diff = middle - ob["to_middle"]
                    if abs(diff) < 0.01:
                        diff = 0.01 if diff >= 0 else -0.01
                    force += (1.0 / diff) * (90.0 - ob["dist"]) / 90.0 * 1.5
            force += -0.15 * middle
            desired = middle + max(-4.0, min(4.0, force))
            target_raw = min(ob_line, key=lambda x: abs(x - desired))
        elif _amode == "corridor" and ob_line:
            # progressive constraint propagation (kimi k2.7): keep only corridors
            # surviving ALL obstacles within a speed-scaled lookahead, dist order.
            _hw = half_load_width
            _mg = _env_float("SSAFY_MAP61_OBSTACLE_PED", 2.25)
            _look = 15.0 + 0.35 * spd
            _obs = sorted([o for o in obstacles if 0 <= o["dist"] <= _look], key=lambda o: o["dist"])
            _free = [(-_hw, _hw)]
            _narrow = 2.0 * _hw
            for _o in _obs:
                _fl = _o["to_middle"] - _mg
                _fh = _o["to_middle"] + _mg
                _nxt = []
                for _lo, _hi in _free:
                    if _lo < _fl:
                        _nxt.append((_lo, min(_hi, _fl)))
                    if _hi > _fh:
                        _nxt.append((max(_lo, _fh), _hi))
                if not _nxt:
                    break
                _free = _nxt
                _narrow = min(_narrow, min(_hi - _lo for _lo, _hi in _free))
            _best = min(_free, key=lambda g: abs((g[0] + g[1]) * 0.5 - middle))
            target_raw = (_best[0] + _best[1]) * 0.5
            _curve = sum(abs(a) for a in angles) / max(len(angles), 1)
            corridor_speed_cap = max(0.0, min(250.0, 20.0 + 10.0 * _narrow - 1.5 * _curve))
        elif _amode == "kinematic" and ob_line:
            # kinematic reachability (max/qwen): grow reachable lateral interval by
            # achievable lateral accel; collapse => inescapable wedge => brake early.
            _ay = _env_float("SSAFY_MAP61_KIN_AY", 9.0)
            _hw = half_load_width
            _mg = _env_float("SSAFY_MAP61_OBSTACLE_PED", 2.25)
            _rmin = _rmax = middle
            _cap = 250.0
            _d = 5.0
            while _d < 120.0:
                _dy = 0.5 * _ay * (5.0 / max(spd, 1.0)) ** 2
                _rmin = max(_rmin - _dy, -_hw)
                _rmax = min(_rmax + _dy, _hw)
                for _o in obstacles:
                    if abs(_o["dist"] - _d) < 5.0:
                        if _o["to_middle"] >= 0:
                            _rmax = min(_rmax, _o["to_middle"] - _mg)
                        else:
                            _rmin = max(_rmin, _o["to_middle"] + _mg)
                if _rmin > _rmax:
                    _cap = min(_cap, max(spd * 0.7, 40.0))
                    _rmin, _rmax = -_hw, _hw
                _d += 5.0
            target_raw = (_rmin + _rmax) / 2.0
            corridor_speed_cap = _cap
        elif _amode == "arc" and ob_line:
            # arc voting (glm5): score whole CURVED candidate paths by min clearance.
            _hw = half_load_width
            _best_t, _best_c, _best_cl = middle, 1e9, _hw
            _dmax = max(1.0, spd * 1.5)
            for _k in range(-6, 7):
                _t = _k * 1.5
                if abs(_t) > _hw:
                    continue
                _cost, _mincl = abs(_t - middle), _hw
                _dd = 0
                while _dd < int(_dmax):
                    _ang = angles[min(_dd // 10, len(angles) - 1)] if angles else 0.0
                    _smid = middle + (_t - middle) * (_dd / _dmax) + _dd * math.tan(math.radians(_ang))
                    for _o in obstacles:
                        if abs(_dd - _o["dist"]) < 5:
                            _mincl = min(_mincl, abs(_smid - _o["to_middle"]))
                    _dd += 4
                if _mincl < 1.0:
                    continue
                _cost += 10.0 / _mincl
                if _cost < _best_c:
                    _best_c, _best_t, _best_cl = _cost, _t, _mincl
            target_raw = _best_t
            corridor_speed_cap = max(40.0, spd * min(1.0, _best_cl / 3.0))
        elif _amode == "visgraph" and ob_line:
            # visibility-graph path planning (glm5.2): route through obstacle
            # edges; advance to furthest node whose straight line stays clear.
            _W = _env_float("SSAFY_MAP61_OBSTACLE_PED", 2.25)
            _hw = half_load_width
            _nodes = [(middle, 0.0)]
            for _o in sorted(obstacles, key=lambda x: x["dist"]):
                _nodes.append((max(-_hw, _o["to_middle"] - _W), _o["dist"]))
                _nodes.append((min(_hw, _o["to_middle"] + _W), _o["dist"]))
            _nodes.append((0.0, 200.0))
            _curr = _nodes[0]
            target_raw = middle
            for _n in _nodes[1:]:
                if _n[1] <= _curr[1]:
                    continue
                _clear = True
                for _o in obstacles:
                    _den = _n[1] - _curr[1]
                    _u = (_o["dist"] - _curr[1]) / _den
                    if 0 <= _u <= 1:
                        _lat = _curr[0] + _u * (_n[0] - _curr[0])
                        if abs(_lat - _o["to_middle"]) < _W:
                            _clear = False
                            break
                if _clear:
                    _curr = _n
                    target_raw = _n[0]
        elif _amode == "ensemble" and ob_line:
            # ENSEMBLE (combination): corridor target (interval intersection) +
            # speed cap = MIN(corridor narrowest-gap cap, kinematic collapse cap).
            _hw = half_load_width
            _mg = _env_float("SSAFY_MAP61_OBSTACLE_PED", 2.25)
            _look = 15.0 + 0.35 * spd
            _obs = sorted([o for o in obstacles if 0 <= o["dist"] <= _look], key=lambda o: o["dist"])
            _free = [(-_hw, _hw)]
            _narrow = 2.0 * _hw
            for _o in _obs:
                _fl, _fh = _o["to_middle"] - _mg, _o["to_middle"] + _mg
                _nxt = []
                for _lo, _hi in _free:
                    if _lo < _fl:
                        _nxt.append((_lo, min(_hi, _fl)))
                    if _hi > _fh:
                        _nxt.append((max(_lo, _fh), _hi))
                if not _nxt:
                    break
                _free = _nxt
                _narrow = min(_narrow, min(_hi - _lo for _lo, _hi in _free))
            _best = min(_free, key=lambda g: abs((g[0] + g[1]) * 0.5 - middle))
            target_raw = (_best[0] + _best[1]) * 0.5
            _curve = sum(abs(a) for a in angles) / max(len(angles), 1)
            _cap_c = max(0.0, min(250.0, 20.0 + 10.0 * _narrow - 1.5 * _curve))
            _ay = _env_float("SSAFY_MAP61_KIN_AY", 9.0)
            _rmin = _rmax = middle
            _cap_k = 250.0
            _d = 5.0
            while _d < 120.0:
                _dy = 0.5 * _ay * (5.0 / max(spd, 1.0)) ** 2
                _rmin = max(_rmin - _dy, -_hw)
                _rmax = min(_rmax + _dy, _hw)
                for _o in obstacles:
                    if abs(_o["dist"] - _d) < 5.0:
                        if _o["to_middle"] >= 0:
                            _rmax = min(_rmax, _o["to_middle"] - _mg)
                        else:
                            _rmin = max(_rmin, _o["to_middle"] + _mg)
                if _rmin > _rmax:
                    _cap_k = min(_cap_k, max(spd * 0.7, 40.0))
                    _rmin, _rmax = -_hw, _hw
                _d += 5.0
            corridor_speed_cap = min(_cap_c, _cap_k)
        else:
            target_raw = min(ob_line, key=target_cost)

        # CRASH-VARIANCE stabilizer (3-model consensus kimi/glm5.2/pro): commit to
        # a line + deadband to stop tick-to-tick target flip-flop + predictive TTC
        # brake when an obstacle sits on the committed line. Default OFF.
        if map_num == "61" and _env_bool("SSAFY_MAP61_STAB_ENABLE", False):
            if spd < 5.0:
                self._committed_target = None
            _sdb = _env_float("SSAFY_MAP61_STAB_DEADBAND", 1.0)
            if self._committed_target is None or abs(target_raw - self._committed_target) > _sdb:
                self._committed_target = target_raw       # commit / switch line
            target_raw = self._committed_target            # else hold the line
            _sttc = _env_float("SSAFY_MAP61_STAB_TTC", 0.6)
            _smg = _env_float("SSAFY_MAP61_OBSTACLE_PED", 2.25)
            for _so in obstacles:
                if _so["dist"] < (spd / 3.6) * _sttc + 3.0 and abs(_so["to_middle"] - target_raw) < _smg:
                    _sbk = _env_float("SSAFY_MAP61_STAB_BRAKE", 70.0)
                    corridor_speed_cap = _sbk if corridor_speed_cap is None else min(corridor_speed_cap, _sbk)
                    break

        # ===== 92.83 구간 전용: 타겟 급변 억제(좌측 돌진 방지) =====
        if seg_9283:
            max_target_step = 0.35 if spd > 80 else 0.60
            delta_target = target_raw - self._prev_target_offset
            if delta_target > max_target_step:
                target = self._prev_target_offset + max_target_step
            elif delta_target < -max_target_step:
                target = self._prev_target_offset - max_target_step
            else:
                target = target_raw

            # 너무 왼쪽 목표 금지(하드클램프)
            if target < -7.0:
                target = -7.0
        else:
            target = target_raw

        if seg_8790_left_gate:
            target = max(-6.5, min(target, -6.0))
        if seg_n161_4951:
            target = max(-0.8, min(target, 3.4))
        if seg_n161_6870:
            if any(20 <= obj['dist'] <= 95 and 4.0 <= obj['to_middle'] <= 5.5 for obj in obstacles):
                target = max(-2.2, min(target, 0.8))
            elif target < -5.2:
                target = -5.2
        if (
            map_num == "161"
            and _env_bool("SSAFY_MAP161_P69_TARGET_ENABLE", True)
            and _env_float("SSAFY_MAP161_P69_TARGET_START", 68.35) <= lap <= _env_float("SSAFY_MAP161_P69_TARGET_END", 70.75)
        ):
            target = max(
                _env_float("SSAFY_MAP161_P69_TARGET_MIN", 0.9),
                min(target, _env_float("SSAFY_MAP161_P69_TARGET_MAX", 3.4)),
            )
        if seg_m61_2224:
            target = max(-3.6, min(target, 4.6))
        if seg_m61_3035 and _env_bool("SSAFY_MAP61_P33_TARGET_ENABLE", True):
            target = max(
                _env_float("SSAFY_MAP61_P33_TARGET_MIN", -1.4),
                min(target, _env_float("SSAFY_MAP61_P33_TARGET_MAX", 0.4)),
            )
        if seg_m61_5962:
            target = max(_env_float("SSAFY_MAP61_SEG5962_LANE_MIN", -2.2), min(target, _env_float("SSAFY_MAP61_SEG5962_LANE_MAX", -0.6)))
        if seg_m61_6365:
            target = max(_env_float("SSAFY_MAP61_SEG6365_LANE_MIN", 1.6), min(target, _env_float("SSAFY_MAP61_SEG6365_LANE_MAX", 3.0)))
        if seg_m61_6568:
            target = max(_env_float("SSAFY_MAP61_SEG6568_LANE_MIN", -4.2), min(target, _env_float("SSAFY_MAP61_SEG6568_LANE_MAX", -1.0)))
        if (
            map_num == "61"
            and _env_bool("SSAFY_MAP61_P64_TARGET_OVERRIDE_ENABLE", False)
            and _env_float("SSAFY_MAP61_P64_TARGET_START", 63.6) <= lap <= _env_float("SSAFY_MAP61_P64_TARGET_END", 66.8)
        ):
            target = max(
                _env_float("SSAFY_MAP61_P64_TARGET_MIN", 0.8),
                min(target, _env_float("SSAFY_MAP61_P64_TARGET_MAX", 3.4)),
            )
        if (
            map_num == "61"
            and _env_bool("SSAFY_MAP61_P66_TARGET_OVERRIDE_ENABLE", False)
            and _env_float("SSAFY_MAP61_P66_TARGET_START", 66.4) <= lap <= _env_float("SSAFY_MAP61_P66_TARGET_END", 68.6)
        ):
            target = max(
                _env_float("SSAFY_MAP61_P66_TARGET_MIN", -1.2),
                min(target, _env_float("SSAFY_MAP61_P66_TARGET_MAX", 1.2)),
            )
        if seg_m61_7679:
            target = max(1.8, min(target, 4.8))
        if seg_m61_9294:
            target = max(-5.4, min(target, -2.6))

        self._prev_target_offset = target
        self.target_offset = target

        # P + 비선형 I 비슷한 효과로 라인 추종 보정값 계산
        p = -(middle - target) * 0.07
        i = p ** 2 * 0.05 if p >= 0 else - p ** 2 * 0.05
        middle_add = 0.5 * p + 0.4 * i

        if seg_3339:
            # 33.39 부근: 회피/코너링 중 과조향 완화(둔감하게)
            middle_add *= _env_float("SSAFY_MAP61_P33_MIDDLE_ADD_SCALE", 0.15) if map_num == "61" else 0.15
        
        #실험용
        if seg_9898:
            # 33.39 부근: 회피/코너링 중 과조향 완화(둔감하게)
            middle_add *= 1.2
        if seg_9283:
            middle_add *= 0.1

        # 장애물 없으면(이번 프레임 in-range 기준) middle_add 0 처리
        if cnt == 0:
            middle_add = 0.0

        # 장애물 가까울수록 회피 반영 가중치 상승
        avoid_gain = 1.0
        if cnt > 0:
            if nearest_ob_dist <= 35:
                avoid_gain = 1.75
            elif nearest_ob_dist <= 55:
                avoid_gain = 1.45
            elif nearest_ob_dist <= 80:
                avoid_gain = 1.25
            else:
                avoid_gain = 1.10

        # ==== 너무 먼 장애물은 "정보만 알고 조향은 아직 반영 X" ====
        if cnt > 0:
            # 속도 기반 반응 거리: 최소 80m, 최대 150m
            if map_num == "71":
                react_min = _env_float("SSAFY_MAP71_REACT_DIST_MIN", 115.0)
                react_max = _env_float("SSAFY_MAP71_REACT_DIST_MAX", 165.0)
                react_scale = _env_float("SSAFY_MAP71_REACT_DIST_SCALE", 1.2)
            else:
                react_min = 80.0
                react_max = 150.0
                react_scale = 0.8
            react_dist = max(react_min, min(react_max, spd * react_scale))
            if nearest_ob_dist > react_dist:
                middle_add = 0.0
                avoid_gain = 1.0
                cnt = 0

        ################################## 장애물 회피 / 목표 차선 계산 끝 #########################################

        # ======================== 주행 코드 ======================== #

        if spd < 50 and sensing_info.lap_progress > 1:
            tg = 0
        elif spd < 120:
            tg = 1
        elif spd < 180:
            tg = 2
        else:
            tg = 3

        # angles 인덱스 범위 보호
        if angles:
            if tg >= len(angles):
                tg = len(angles) - 1
            if tg < 0:
                tg = 0
        else:
            angles = [0.0]
            tg = 0

        # (참고할 전방의 커브 - 내 차량의 주행 각도) 기반 steering 계산
        if abs(angles[tg]) < 55:
            if cnt == 0:
                # 장애물이 없으면 중앙 근처로 주행
                car_controls.steering = (angles[tg] - sensing_info.moving_angle) / 90 - middle / 80
            else:
                if spd < 70:
                    set_steering = (angles[tg] - sensing_info.moving_angle) / 60
                else:
                    set_steering = (angles[tg] - sensing_info.moving_angle) / 90
                car_controls.steering = set_steering
                # 장애물 근접 시 회피 보정 더 강하게 반영
                car_controls.steering += middle_add * avoid_gain
        else:
            # 급커브 구간
            k = spd if spd >= 60 else 60
            if angles[tg] < 0:
                r = half_road_limit_used - 1.25 + middle
                beta = - math.pi * k * 0.1 / r
                car_controls.steering = (beta - sensing_info.moving_angle * math.pi / 180) if angles[tg] > -60 else -1
            else:
                r = half_road_limit_used - 1.25 - middle
                beta = math.pi * k * 0.1 / r
                car_controls.steering = (beta - sensing_info.moving_angle * math.pi / 180) if angles[tg] < 60 else 1

            if spd > 80:
                car_controls.throttle = -1
                car_controls.brake = 1

            # 급커브에서도 장애물 있을 때만 회피 보정 일부 반영
            if cnt > 0:
                curve_scale = 0.40
                if nearest_ob_dist <= 45:
                    curve_scale = 0.55
                car_controls.steering += (middle_add * avoid_gain) * curve_scale
                if car_controls.steering > 1:
                    car_controls.steering = 1
                elif car_controls.steering < -1:
                    car_controls.steering = -1

        # 고속 + 큰 커브에서 각도 인덱스 보호
        ang_idx = int(spd // 20)
        if ang_idx >= len(angles):
            ang_idx = len(angles) - 1
        if ang_idx < 0:
            ang_idx = 0

        # ===== 구간 하드코딩: 과조향/급돌진 완화 =====
        if seg_3339:
            # 33%대: 코너+회피에서 steering이 과하게 튀는 경향 → 반응 둔감(약 1.5초 체감)
            car_controls.steering *= _env_float("SSAFY_MAP61_P33_STEER_SCALE", 0.88) if map_num == "61" else 0.88

        if seg_9283:
            # 92.83 부근: 갑자기 왼쪽으로 돌진 → 좌회전 과도치 클램프 + 약한 우측 바이어스
            if car_controls.steering < -0.55:
                car_controls.steering = -0.55
            if middle < -6.0:
                car_controls.steering += 0.12
        if seg_8790_left_gate and middle > -5.6:
            car_controls.steering = min(car_controls.steering, -0.04)
            car_controls.throttle = 1.0
            car_controls.brake = 0.0
        if seg_n161_4951 and middle > 4.8:
            car_controls.steering = min(car_controls.steering, -0.26 if spd > 90 else -0.14)
        if seg_n161_6870 and middle < -7.2:
            car_controls.steering = max(car_controls.steering, 0.52 if spd > 70 else 0.34)
        if seg_n161_6870 and middle < -4.8:
            car_controls.steering = max(car_controls.steering, 0.24 if spd > 80 else 0.16)
        if (
            map_num == "161"
            and _env_bool("SSAFY_MAP161_P69_STEER_ENABLE", False)
            and _env_float("SSAFY_MAP161_P69_STEER_START", 68.25) <= lap <= _env_float("SSAFY_MAP161_P69_STEER_END", 70.85)
            and middle < _env_float("SSAFY_MAP161_P69_STEER_MIDDLE_MAX", -0.4)
            and any(
                0 <= obj["dist"] <= _env_float("SSAFY_MAP161_P69_STEER_OB_DIST", 75.0)
                and _env_float("SSAFY_MAP161_P69_STEER_OB_MIN", -3.2) <= obj["to_middle"] <= _env_float("SSAFY_MAP161_P69_STEER_OB_MAX", -1.0)
                for obj in obstacles
            )
        ):
            car_controls.steering = max(car_controls.steering, _env_float("SSAFY_MAP161_P69_STEER_MIN", 0.18))
            car_controls.throttle = 1.0
            car_controls.brake = 0.0
        # ============================================

        # 고속 + 큰 조향 + 중앙에서 많이 벗어났을 때 감속 (원본 유지)
        risk_angle = _env_float("SSAFY_RISK_ANGLE", 40.0)
        risk_middle = _env_float("SSAFY_RISK_MIDDLE", 9.0)
        risk_steer = _env_float("SSAFY_RISK_STEER", 0.5)
        risk_speed = _env_float("SSAFY_RISK_SPEED", 100.0)
        risk_low_brake = _env_float("SSAFY_RISK_LOW_BRAKE", 0.3)
        risk_high_brake = _env_float("SSAFY_RISK_HIGH_BRAKE", 1.0)
        if map_num == "71":
            risk_angle = _env_float("SSAFY_MAP71_RISK_ANGLE", risk_angle)
            risk_middle = _env_float("SSAFY_MAP71_RISK_MIDDLE", risk_middle)
            risk_steer = _env_float("SSAFY_MAP71_RISK_STEER", risk_steer)
            risk_speed = _env_float("SSAFY_MAP71_RISK_SPEED", risk_speed)
            risk_low_brake = _env_float("SSAFY_MAP71_RISK_LOW_BRAKE", risk_low_brake)
            risk_high_brake = _env_float("SSAFY_MAP71_RISK_HIGH_BRAKE", risk_high_brake)
        risk_brake_enabled = _env_bool("SSAFY_RISK_BRAKE_ENABLE", True) and (map_num != "71" or _env_bool("SSAFY_MAP71_RISK_BRAKE_ENABLE", True))
        if risk_brake_enabled and (abs(angles[ang_idx]) > risk_angle or abs(middle) > risk_middle or abs(car_controls.steering) >= risk_steer) and spd > risk_speed:
            car_controls.throttle = 0
            if middle > 9:
                car_controls.steering -= 0.1
            elif middle < -9:
                car_controls.steering += 0.1
            car_controls.brake = risk_low_brake if spd < 110 else risk_high_brake

        # 직선 고속에서 끝 코너 대비 감속
        if spd > 170 and abs(angles[-1]) > 10:
            car_controls.throttle = -0.5
            car_controls.brake = 1

        if spd < 5:
            if lap < 0.5 and abs(middle) > 2.0:
                car_controls.steering = -0.28 if middle > 0 else 0.28
            else:
                car_controls.steering = 0

        # ===================== 추가 안전 로직 ===================== #

        # 2) 차체 각도가 많이 틀어진 상태에서 고속이면 감속
        yaw_angle_limit = _env_float("SSAFY_YAW_ANGLE", 30.0)
        yaw_speed_limit = _env_float("SSAFY_YAW_SPEED", 80.0)
        yaw_brake = _env_float("SSAFY_YAW_BRAKE", 1.0)
        if map_num == "71":
            yaw_angle_limit = _env_float("SSAFY_MAP71_YAW_ANGLE", yaw_angle_limit)
            yaw_speed_limit = _env_float("SSAFY_MAP71_YAW_SPEED", yaw_speed_limit)
            yaw_brake = _env_float("SSAFY_MAP71_YAW_BRAKE", yaw_brake)
        yaw_brake_enabled = _env_bool("SSAFY_YAW_BRAKE_ENABLE", True) and (map_num != "71" or _env_bool("SSAFY_MAP71_YAW_BRAKE_ENABLE", True))
        if yaw_brake_enabled and abs(sensing_info.moving_angle) > yaw_angle_limit and spd > yaw_speed_limit:
            car_controls.throttle = 0.0
            car_controls.brake = max(car_controls.brake, yaw_brake)

        # 3) 커브 각도 기반 간단 타겟 속도 제어
        if self.accident_step == 0:
            abs_ang = abs(angles[tg]) if angles else 0.0

            if abs_ang < 3:
                base_target = 190
            elif abs_ang < 7:
                base_target = 170
            elif abs_ang < 15:
                base_target = 140
            elif abs_ang < 25:
                base_target = 120
            elif abs_ang < 35:
                base_target = 100
            else:
                base_target = 80

            offset = abs(middle)
            if offset > 8:
                base_target = min(base_target, 90)
            elif offset > 6:
                base_target = min(base_target, 110)
            elif offset > 4:
                base_target = min(base_target, 130)

            # ✅ 최저속도 60 요구사항
            target_floor = _env_float("SSAFY_TARGET_FLOOR", 70)
            if map_num == "71":
                target_floor = _env_float("SSAFY_MAP71_MIN_TARGET_SPEED", target_floor)
            target_speed = max(target_floor, base_target)
            if map_num != "71":
                target_speed = target_speed * _env_float("SSAFY_NON71_TARGET_SPEED_MULT", 1.0) + _env_float("SSAFY_NON71_TARGET_SPEED_BIAS", 0.0)

            # ===== 구간 하드코딩 속도 튜닝 (요청사항) =====
            if seg_0510:
                # 5~10 구간: 제한속도 150
                target_speed = min(target_speed, 150)

            if seg_1783:
                # 17.8~18.3 구간: 약간 가속
                target_speed = min(target_speed, 75)

            # if seg_3339:
            #     target_speed = 75

            if seg_9283:
                # 92.83 부근: 안정성을 위해 소폭 감속
                target_speed = max(60, target_speed - 30)

            if seg_9898:
                # 92.83 부근: 안정성을 위해 소폭 감속
                target_speed = target_speed * 0.8
            if seg_5444:
                target_speed = max(target_speed, 140)
            if seg_2729 and abs_ang < 25 and abs(middle) < 8.5:
                # 27~29 구간: 130까지 과한 감속은 불필요
                target_speed = max(target_speed, 140)

            if seg_6767:
                target_speed = max(60, target_speed * 0.7)

            if seg_5354:
                target_speed = max(60, target_speed * 0.65)
            if seg_8790_left_gate:
                target_speed = max(target_speed, 112 if abs(middle) < 7.0 else 92)
            if seg_n161_4951 and abs(middle) < half_load_width * 0.75:
                target_speed = max(target_speed, 115)
            if seg_n161_6870 and middle < -6.5:
                target_speed = min(target_speed, 92)
            if seg_m61_3035:
                # pre-corner speed cap: slowing entry prevents the high-speed
                # left drift into the wall ~progress 35 (default 999 = no cap)
                target_speed = min(target_speed, _env_float("SSAFY_MAP61_P33_SPEED_CAP", 999.0))
            # ===============================================

            # map61 global speed scale (default 1.0): push speed up where
            # the lap is NOT crash-limited (search lever; map61-only, no regress).
            if map_num == "61":
                target_speed *= _env_float("SSAFY_MAP61_SPEED_MULT", 1.0)
            # mode speed cap (corridor/kinematic/ensemble) applies on ALL maps so
            # the general avoidance algorithm works everywhere, not just map61.
            if corridor_speed_cap is not None:
                target_speed = min(target_speed, corridor_speed_cap)
            if _env_bool("SSAFY_SPEED_CONTROL_ENABLE", True) and car_controls.brake < 0.9:
                speed_margin = _env_float("SSAFY_SPEED_MARGIN", 5.0)
                if spd < target_speed - speed_margin:
                    car_controls.throttle = 1.0
                    car_controls.brake = 0.0
                elif spd > target_speed + speed_margin:
                    car_controls.throttle = 0.0
                    car_controls.brake = max(car_controls.brake, _env_float("SSAFY_SPEED_BRAKE", 0.7))
                else:
                    car_controls.throttle = max(car_controls.throttle, _env_float("SSAFY_SPEED_HOLD_THROTTLE", 0.4))
                    if car_controls.brake < 0.5:
                        car_controls.brake = 0.0

        # ===================== 조향 부드럽게 만들기 ===================== #
        global before
        max_delta = 0.18  # 기본

        # 장애물 근접 시만 조향 변화 제한 완화 (원본 수준 유지)
        if cnt > 0:
            if nearest_ob_dist <= 35:
                max_delta = 0.30
            elif nearest_ob_dist <= 55:
                max_delta = 0.26
            elif nearest_ob_dist <= 80:
                max_delta = 0.22
            else:
                max_delta = 0.20

        # 33.39 / 92.83 구간 전용: 핸들링 둔감(급변 억제)
        if seg_3339:
            max_delta = min(max_delta, _env_float("SSAFY_MAP61_P33_MAX_DELTA", 0.14) if map_num == "61" else 0.14)
        if seg_9283:
            max_delta = min(max_delta, 0.16)

        delta = car_controls.steering - before

        if delta > max_delta:
            car_controls.steering = before + max_delta
        elif delta < -max_delta:
            car_controls.steering = before - max_delta

        before = car_controls.steering

        # 최종 steering 안전 클램프. 고속일수록 핸들을 과하게 꺾으면
        # 지그재그와 edge collision이 커져서 실제 완주 시간이 늘어난다.
        steer_limit = 1.0
        if spd > 150:
            steer_limit = 0.58
        elif spd > 120:
            steer_limit = 0.66
        elif spd > 90:
            steer_limit = 0.78
        elif spd > 60:
            steer_limit = 0.90
        if abs(middle) > half_load_width * 0.82 and spd < 95:
            steer_limit = max(steer_limit, 1.0)
        if car_controls.steering > steer_limit:
            car_controls.steering = steer_limit
        elif car_controls.steering < -steer_limit:
            car_controls.steering = -steer_limit

        if (
            map_num == "61"
            and _env_bool("SSAFY_MAP61_P33_HARD_ENABLE", True)
            and 32.35 <= lap <= 33.80
            and middle > 2.1
            and any(0 <= obj['dist'] <= 45 and 1.7 <= obj['to_middle'] <= 7.8 for obj in obstacles)
        ):
            hard_outer = _env_float("SSAFY_MAP61_P33_HARD_OUTER_STEER", -0.82)
            hard_inner = _env_float("SSAFY_MAP61_P33_HARD_INNER_STEER", -0.66)
            car_controls.steering = min(car_controls.steering, hard_outer if middle > 5.5 else hard_inner)
            car_controls.throttle = 1.0
            car_controls.brake = 0.0
        elif map_num == "61" and _env_bool("SSAFY_MAP61_P33_EDGE_ENABLE", True) and 32.8 <= lap <= 33.45 and abs(middle) > half_load_width * _env_float("SSAFY_MAP61_P33_EDGE_RATIO", 0.74):
            # Map61 33% cluster: full lock crosses the track and starts a slow
            # recovery chain, so use a short inside correction while staying on throttle.
            edge_steer = _env_float("SSAFY_MAP61_P33_EDGE_STEER", 0.72)
            car_controls.steering = -edge_steer if middle > 0 else edge_steer
            car_controls.throttle = 1.0
            car_controls.brake = 0.0
        elif map_num == "61" and _env_bool("SSAFY_MAP61_P33_EXIT_ENABLE", True) and 33.45 < lap <= 34.75 and abs(middle) > half_load_width * _env_float("SSAFY_MAP61_P33_EXIT_RATIO", 0.78):
            exit_steer = _env_float("SSAFY_MAP61_P33_EXIT_STEER", 0.58)
            car_controls.steering = -exit_steer if middle > 0 else exit_steer
            car_controls.throttle = 1.0
            car_controls.brake = 0.0
        elif known_map and 32.8 <= lap <= 34.6 and abs(middle) > half_load_width * 0.74:
            car_controls.steering = -1.0 if middle > 0 else 1.0
            car_controls.throttle = 1.0
            car_controls.brake = 0.0

        if seg_8791 and middle < -8.0:
            car_controls.steering = max(car_controls.steering, 0.50 if spd > 35 else 0.42)
            car_controls.throttle = 1.0
            car_controls.brake = 0.0

        if map_num == "61" and _env_bool("SSAFY_MAP61_P33_LEFT_CAP_ENABLE", True) and 32.65 <= lap <= 33.55 and car_controls.steering < _env_float("SSAFY_MAP61_P33_LEFT_CAP", -0.42):
            car_controls.steering = _env_float("SSAFY_MAP61_P33_LEFT_CAP", -0.42)
            car_controls.throttle = 1.0
            car_controls.brake = 0.0

        if map_num == "61" and _env_bool("SSAFY_MAP61_P61_GUARD_ENABLE", True) and 60.9 <= lap <= 62.2 and middle > _env_float("SSAFY_MAP61_P61_GUARD_MIDDLE", 4.0):
            car_controls.steering = max(
                car_controls.steering,
                _env_float("SSAFY_MAP61_P61_GUARD_FAST_STEER", 0.10) if spd > 70 else _env_float("SSAFY_MAP61_P61_GUARD_SLOW_STEER", 0.18),
            )
            car_controls.throttle = 1.0
            car_controls.brake = 0.0

        if (
            map_num == "161"
            and _env_bool("SSAFY_MAP161_P71_RIGHT_ESCAPE_ENABLE", False)
            and _env_float("SSAFY_MAP161_P71_RIGHT_ESCAPE_START", 70.35) <= lap <= _env_float("SSAFY_MAP161_P71_RIGHT_ESCAPE_END", 72.05)
            and middle < _env_float("SSAFY_MAP161_P71_RIGHT_ESCAPE_MIDDLE_MAX", 1.0)
            and any(
                0 <= obj["dist"] <= _env_float("SSAFY_MAP161_P71_RIGHT_ESCAPE_DIST", 45.0)
                and _env_float("SSAFY_MAP161_P71_LEFT_OB_MIN", -4.2) <= obj["to_middle"] <= _env_float("SSAFY_MAP161_P71_LEFT_OB_MAX", -2.8)
                for obj in obstacles
            )
        ):
            car_controls.steering = max(car_controls.steering, _env_float("SSAFY_MAP161_P71_RIGHT_ESCAPE_STEER", 0.42))
            car_controls.throttle = 1.0
            car_controls.brake = 0.0

        if (
            map_num == "161"
            and _env_bool("SSAFY_MAP161_P70_FORCE_THROTTLE_ENABLE", False)
            and _env_float("SSAFY_MAP161_P70_FORCE_THROTTLE_START", 70.55) <= lap <= _env_float("SSAFY_MAP161_P70_FORCE_THROTTLE_END", 72.45)
            and middle > _env_float("SSAFY_MAP161_P70_FORCE_THROTTLE_MIDDLE_MIN", 1.0)
        ):
            car_controls.throttle = 1.0
            car_controls.brake = 0.0

        if (
            map_num == "61"
            and _env_bool("SSAFY_MAP61_P64_RIGHT_KEEP_ENABLE", False)
            and _env_float("SSAFY_MAP61_P64_RIGHT_KEEP_START", 63.55) <= lap <= _env_float("SSAFY_MAP61_P64_RIGHT_KEEP_END", 64.95)
            and middle > _env_float("SSAFY_MAP61_P64_RIGHT_KEEP_MIDDLE", 0.8)
            and any(
                0 <= obj["dist"] <= _env_float("SSAFY_MAP61_P64_RIGHT_KEEP_DIST", 70.0)
                and _env_float("SSAFY_MAP61_P64_LEFT_OB_MIN", -3.8) <= obj["to_middle"] <= _env_float("SSAFY_MAP61_P64_LEFT_OB_MAX", -2.2)
                for obj in obstacles
            )
        ):
            min_steer = _env_float("SSAFY_MAP61_P64_RIGHT_KEEP_STEER_MIN", -0.04)
            car_controls.steering = max(car_controls.steering, min_steer)
            car_controls.throttle = 1.0
            car_controls.brake = 0.0

        if (
            map_num == "61"
            and _env_bool("SSAFY_MAP61_P78_RIGHT_HOLD_ENABLE", False)
            and _env_float("SSAFY_MAP61_P78_RIGHT_HOLD_START", 77.0) <= lap <= _env_float("SSAFY_MAP61_P78_RIGHT_HOLD_END", 79.25)
            and middle > _env_float("SSAFY_MAP61_P78_RIGHT_HOLD_MIDDLE", 2.0)
            and any(
                0 <= obj["dist"] <= _env_float("SSAFY_MAP61_P78_RIGHT_HOLD_DIST", 55.0)
                and _env_float("SSAFY_MAP61_P78_OB_MIN", -3.2) <= obj["to_middle"] <= _env_float("SSAFY_MAP61_P78_OB_MAX", -0.2)
                for obj in obstacles
            )
        ):
            hold_steer = _env_float("SSAFY_MAP61_P78_RIGHT_HOLD_STEER", 0.46)
            car_controls.steering = max(car_controls.steering, hold_steer)
            car_controls.throttle = 1.0
            car_controls.brake = 0.0

        if map_num == "71" and _env_bool("SSAFY_MAP71_SEG23_CROSS_ENABLE", False):
            seg23_start = _env_float("SSAFY_MAP71_SEG23_CROSS_START", 21.8)
            seg23_end = _env_float("SSAFY_MAP71_SEG23_CROSS_END", 23.25)
            seg23_middle = _env_float("SSAFY_MAP71_SEG23_CROSS_MIDDLE", 4.0)
            seg23_steer = _env_float("SSAFY_MAP71_SEG23_CROSS_STEER", 0.92)
            seg23_brake_cap = _env_float("SSAFY_MAP71_SEG23_CROSS_BRAKE_CAP", 0.0)
            if seg23_start <= lap <= seg23_end and middle > seg23_middle:
                car_controls.steering = max(car_controls.steering, seg23_steer)
                car_controls.throttle = 1.0
                car_controls.brake = min(car_controls.brake, seg23_brake_cap)

        if map_num == "71" and _env_bool("SSAFY_MAP71_SEG61_GUARD_ENABLE", False):
            seg61_start = _env_float("SSAFY_MAP71_SEG61_GUARD_START", 60.9)
            seg61_end = _env_float("SSAFY_MAP71_SEG61_GUARD_END", 62.1)
            seg61_mid = _env_float("SSAFY_MAP71_SEG61_GUARD_MIDDLE", 7.5)
            seg61_steer = _env_float("SSAFY_MAP71_SEG61_GUARD_STEER", 0.92)
            if seg61_start <= lap <= seg61_end and middle > seg61_mid:
                car_controls.steering = min(car_controls.steering, -seg61_steer)
                car_controls.throttle = 1.0
                car_controls.brake = 0.0

        if map_num == "71" and _env_bool("SSAFY_MAP71_SEG95_LOW_ESCAPE_ENABLE", False):
            seg95_start = _env_float("SSAFY_MAP71_SEG95_LOW_ESCAPE_START", 94.8)
            seg95_end = _env_float("SSAFY_MAP71_SEG95_LOW_ESCAPE_END", 96.3)
            seg95_speed = _env_float("SSAFY_MAP71_SEG95_LOW_ESCAPE_SPEED", 32.0)
            seg95_middle = _env_float("SSAFY_MAP71_SEG95_LOW_ESCAPE_MIDDLE", -3.2)
            seg95_steer = _env_float("SSAFY_MAP71_SEG95_LOW_ESCAPE_STEER", 0.70)
            if seg95_start <= lap <= seg95_end and spd < seg95_speed and middle < seg95_middle:
                car_controls.steering = max(car_controls.steering, seg95_steer)
                car_controls.throttle = 1.0
                car_controls.brake = 0.0

        # --------------------- 충돌시 탈출 코드 --------------------- #

        if spd > 10:
            self.accident_step = 0
            self.recovery_count = 0
            self.accident_count = 0
            self.recovery_dir = 0
            self.escape_count = 0
            self.escape_dir = 0

        if sensing_info.lap_progress > 0.5 and self.accident_step == 0 and abs(spd) < 1.0:
            self.accident_count += 1

        if sensing_info.lap_progress > 0.5 and self.accident_step == 0 and sensing_info.collided and abs(spd) < 25:
            self.accident_count += 3

        accident_trigger = 5 if map_num == "71" else (3 if not known_map else 8)
        accident_trigger = _env_int("SSAFY_RECOVERY_TRIGGER", accident_trigger)

        if self.accident_count > accident_trigger:
            self.accident_step = 1
            if self.recovery_dir == 0:
                if abs(middle) > half_load_width * 0.78:
                    self.recovery_dir = -1 if middle >= 0 else 1
                elif nearest_ob_dist < 25 and obstacles:
                    self.recovery_dir = -1 if obstacles[0]['to_middle'] >= middle else 1
                else:
                    self.recovery_dir = -1 if middle >= 0 else 1

        if self.accident_step == 1:
            self.recovery_count += 1
            back_steer = _env_float("SSAFY_RECOVERY_BACK_STEER", 0.38 if map_num == "71" else (0.55 if not known_map else 0.45))
            back_throttle = _env_float("SSAFY_RECOVERY_BACK_THROTTLE", 0.48 if map_num == "71" else (0.6 if not known_map else 0.75))
            car_controls.steering = -back_steer * self.recovery_dir
            car_controls.throttle = -back_throttle
            car_controls.brake = 0

        back_frames = 4 if map_num == "71" else (10 if not known_map else 8)
        back_frames = _env_int("SSAFY_RECOVERY_BACK_FRAMES", back_frames)
        if self.recovery_count > back_frames:
            self.accident_step = 2
            self.recovery_count = 0
            self.accident_count = 0

        if self.accident_step == 2:
            self.recovery_count += 1
            forward_steer = 0.46 if map_num == "71" else (0.7 if not known_map else 0.55)
            done_speed = 12 if map_num == "71" else (22 if not known_map else 18)
            forward_frames = 8 if map_num == "71" else 12
            forward_steer = _env_float("SSAFY_RECOVERY_FORWARD_STEER", forward_steer)
            done_speed = _env_float("SSAFY_RECOVERY_DONE_SPEED", done_speed)
            forward_frames = _env_int("SSAFY_RECOVERY_FORWARD_FRAMES", forward_frames)
            car_controls.steering = forward_steer * self.recovery_dir
            car_controls.throttle = 1
            car_controls.brake = 0
            if sensing_info.speed > done_speed or self.recovery_count > forward_frames:
                self.accident_step = 0
                self.recovery_count = 0
                self.recovery_dir = 0
                car_controls.throttle = 1
                car_controls.brake = 0

        if (
            map_num == "71"
            and _env_bool("SSAFY_MAP71_EMERGENCY_ESCAPE_ENABLE", True)
            and sensing_info.lap_progress > 0.5
            and sensing_info.collided
            and abs(spd) < _env_float("SSAFY_MAP71_EMERGENCY_SPEED", 2.5)
        ):
            self.escape_count += 1
            if self.escape_dir == 0:
                if abs(middle) > half_load_width * 0.72:
                    self.escape_dir = 1 if middle > 0 else -1
                elif obstacles:
                    self.escape_dir = -1 if obstacles[0]['to_middle'] > middle else 1
                else:
                    self.escape_dir = -1 if sensing_info.moving_angle > 0 else 1

            trigger_frames = _env_int("SSAFY_MAP71_EMERGENCY_TRIGGER_FRAMES", 3)
            back_frames = _env_int("SSAFY_MAP71_EMERGENCY_BACK_FRAMES", 8)
            forward_frames = _env_int("SSAFY_MAP71_EMERGENCY_FORWARD_FRAMES", 3)
            back_throttle = _env_float("SSAFY_MAP71_EMERGENCY_BACK_THROTTLE", 0.85)
            back_steer = _env_float("SSAFY_MAP71_EMERGENCY_BACK_STEER", 0.65)
            forward_steer = _env_float("SSAFY_MAP71_EMERGENCY_FORWARD_STEER", 0.7)

            if self.escape_count > trigger_frames:
                phase = self.escape_count - trigger_frames
                self.accident_step = 0
                self.accident_count = 0
                self.recovery_count = 0
                self.recovery_dir = 0
                if phase <= back_frames:
                    car_controls.steering = -back_steer * self.escape_dir
                    car_controls.throttle = -back_throttle
                elif phase <= back_frames + forward_frames:
                    car_controls.steering = forward_steer * self.escape_dir
                    car_controls.throttle = 1.0
                else:
                    self.escape_count = 0
                    self.escape_dir = 0
                    car_controls.throttle = 1.0
                car_controls.brake = 0.0
        elif map_num == "71" and self.escape_count and abs(spd) > 8:
            self.escape_count = 0
            self.escape_dir = 0

        # --------------------- 역방향 진행시 탈출 코드 --------------------- #
        if not sensing_info.moving_forward and not (self.accident_count + self.accident_step + self.recovery_count) and spd > 0:
            self.uturn_count += 1
            if not self.uturn_step:
                if middle >= 0:
                    self.uturn_step = 1
                else:
                    self.uturn_step = -1

        if sensing_info.moving_forward:
            self.uturn_count = 0
            self.uturn_step = 0

        if self.uturn_count > 5:
            car_controls.steering = self.uturn_step
            car_controls.throttle = 0.5

        # --------- 최저속도 60 보장(비정상 감속 방지) ----------
        # - 사고/복구 단계에서는 예외(후진/정지 탈출이 필요)
        if self.accident_step == 0 and spd < 60:
            car_controls.brake = 0.0
            car_controls.throttle = max(car_controls.throttle, 0.6)

        if (
            map_num == "61"
            and _env_bool("SSAFY_MAP61_P64_SHOVE_ENABLE", True)
            and 64.05 <= lap <= 65.05
            and middle < -2.0
            and any(0 <= obj['dist'] <= 18 and -3.6 <= obj['to_middle'] <= -2.4 for obj in obstacles)
        ):
            p64_shove_steer = _env_float("SSAFY_MAP61_P64_SHOVE_STEER", 0.72)
            self.accident_step = 0
            self.accident_count = 0
            self.recovery_count = 0
            car_controls.steering = max(car_controls.steering, p64_shove_steer)
            car_controls.throttle = 1.0
            car_controls.brake = 0.0

        # --------- 로그 한 줄 기록 (Full Logging) ----------
        try:
            self._log_frame(sensing_info, car_controls, nearest_ob_dist, middle_add, avoid_gain, cnt)
        except Exception:
            pass

        if self.is_debug:
            print("[MyCar] steering:{}, throttle:{}, brake:{}".format(
                car_controls.steering, car_controls.throttle, car_controls.brake
            ))

        return car_controls

    # ===================== CSV 로깅 유틸 ===================== #

    def _init_debug_logger(self):
        """
        debug_log_full*.csv가 없으면 헤더를 만들고, 있으면 이어서 append.
        (필드명/순서는 기존 스키마 그대로 유지)
        """
        try:
            file_exists = os.path.exists(self.debug_log_file)
            need_header = (not file_exists)
            if file_exists:
                try:
                    need_header = os.path.getsize(self.debug_log_file) == 0
                except Exception:
                    need_header = False

            self.debug_log_fp = open(self.debug_log_file, mode="a", newline="", encoding="utf-8")
            self.debug_log_writer = csv.writer(self.debug_log_fp)

            if need_header:
                # 20개의 각도 헤더 생성
                angle_headers = [f"ang_{i:02d}" for i in range(20)]
                headers = [
                    "time", "speed", "target_offset", "steer", "throttle", "brake",
                    "to_middle", "moving_angle", "moving_forward", "collided",
                    "is_accident", "recovery_steps", "obstacle_close", "car_ahead_close",
                    "lap_progress", "half_road_limit"
                ] + angle_headers + [
                    "obs_dist", "obs_to_middle", "nearest_ob_dist",
                    "middle_add", "avoid_gain", "obs_cnt",
                    "all_obstacles", "all_opponents"
                ]
                self.debug_log_writer.writerow(headers)
                self.debug_log_fp.flush()
        except Exception:
            self.debug_log_fp = None
            self.debug_log_writer = None

    def _log_frame(self, sensing_info, car_controls, nearest_ob_dist, middle_add, avoid_gain, obs_cnt):
        """
        한 프레임의 요약 정보를 debug_log_full*.csv에 저장.
        """
        if not self.debug_log_writer:
            return  # 로거가 열리지 않았으면 스킵

        time_str = datetime.now().strftime("%H:%M:%S.%f")[:-3]

        speed = sensing_info.speed
        target_offset = self.target_offset
        steer = car_controls.steering
        throttle = car_controls.throttle
        brake = car_controls.brake
        to_middle = sensing_info.to_middle
        moving_angle = sensing_info.moving_angle
        moving_forward = 1 if sensing_info.moving_forward else 0
        collided = 1 if sensing_info.collided else 0
        is_accident = 1 if self.accident_step > 0 else 0
        recovery_steps = self.recovery_count
        lap_progress = sensing_info.lap_progress
        half_road = (self._half_road_limit_used if getattr(self, "_half_road_limit_used", None) is not None else self.half_road_limit)

        # 전방 각도 20개 (부족하면 0으로 채움)
        forward_angles = sensing_info.track_forward_angles or []
        logged_angles = [
            f"{forward_angles[i]:.2f}" if i < len(forward_angles) else "0.00"
            for i in range(20)
        ]

        # 가장 가까운 장애물 정보 (로그는 원본 리스트 0번 그대로 유지)
        obstacles = sensing_info.track_forward_obstacles or []
        nearest_obs_info = obstacles[0] if obstacles else None
        obs_dist = nearest_obs_info['dist'] if nearest_obs_info else -1.0
        obs_to_middle = nearest_obs_info['to_middle'] if nearest_obs_info else 0.0

        # 장애물 있음 여부 플래그
        obstacle_close = 1 if (obs_cnt > 0 and nearest_ob_dist < 50) else 0

        # 상대 차량 근접 여부
        car_ahead_close = 0
        for car in sensing_info.opponent_cars_info:
            if car['dist'] > 0 and car['dist'] < 30 and abs(car['to_middle'] - to_middle) < 3:
                car_ahead_close = 1
                break

        # 리스트 문자열 변환 (로그 분석용)
        obstacles_str = str(obstacles).replace(",", ";")
        opponents_str = str(sensing_info.opponent_cars_info).replace(",", ";")

        row = [
            time_str,
            f"{speed:.2f}",
            f"{target_offset:.2f}",
            f"{steer:.3f}",
            f"{throttle:.3f}",
            f"{brake:.3f}",
            f"{to_middle:.2f}",
            f"{moving_angle:.2f}",
            moving_forward,
            collided,
            is_accident,
            recovery_steps,
            obstacle_close,
            car_ahead_close,
            f"{lap_progress:.2f}",
            f"{half_road:.2f}"
        ] + logged_angles + [
            f"{obs_dist:.2f}",
            f"{obs_to_middle:.2f}",
            f"{nearest_ob_dist:.2f}",
            f"{middle_add:.3f}",
            f"{avoid_gain:.2f}",
            obs_cnt,
            f'"{obstacles_str}"',
            f'"{opponents_str}"'
        ]

        self.debug_log_writer.writerow(row)
        self.debug_log_fp.flush()

    def __del__(self):
        try:
            if self.debug_log_fp:
                self.debug_log_fp.close()
        except Exception:
            pass

    def set_player_name(self):
        player_name = "gdgd_FullLog"
        return player_name


if __name__ == '__main__':
    print("[MyCar] Start Bot! (PYTHON)")
    client = DrivingClient()
    return_code = client.run()
    print("[MyCar] End Bot! (PYTHON)")
    exit(return_code)
