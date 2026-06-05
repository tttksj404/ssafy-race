# SSAFY RACE 우승 전략

작성일: 2026-05-31

## 1. 확인된 사실과 작업 가정

### 확인된 사실

- 지원 언어는 Python, Java, C++이다. 근거: `.context/ssafy-race-analysis/pdf-text/싸피레이스_상세가이드_20260515.reflow.txt:30-35`.
- 서버 제출/반영 대상은 언어별 단일 파일이다. Java는 `MyCar.java`, Python은 `my_car.py`, C++은 `MyCar.cpp`만 업로드/제출 대상이다. 근거: `.context/ssafy-race-analysis/pdf-text/싸피레이스_상세가이드_20260515.reflow.txt:80-90`, `183-220`, `260-294`.
- 제어 함수는 약 0.1초 주기로 호출된다. 근거: `.context/ssafy-race-analysis/pdf-text/싸피레이스_상세가이드_20260515.reflow.txt:80-90`, `211`; Python 구현 근거: `.context/ssafy-race-analysis/extracted/MyCar_20260515/Template_Python/Bot_Python/DrivingInterface/drive_controller.py:60`, `183-197`.
- 사용 가능한 핵심 센서는 `to_middle`, `speed`, `moving_angle`, `track_forward_angles`, `track_forward_obstacles`, `opponent_cars_info`, `distance_to_way_points`, `half_road_limit`, `lap_progress`이다. 근거: `.context/ssafy-race-analysis/pdf-text/싸피레이스_상세가이드_20260515.reflow.txt:309-446`.
- 조작 범위는 `steering` -1..1, `throttle` -1..1, `brake` 0..1이다. 근거: `.context/ssafy-race-analysis/pdf-text/싸피레이스_상세가이드_20260515.reflow.txt:431-446`.
- 차가 도로를 벗어나면 시뮬레이터가 `brake = 0.9` 수준의 페널티를 적용하고 속도를 감소시킨다. 근거: `.context/ssafy-race-analysis/pdf-text/싸피레이스_상세가이드_20260515.reflow.txt:448-450`, `.context/ssafy-race-analysis/extracted/MyCar_20260515/Template_Python/Bot_Python/DrivingInterface/drive_controller.py:168-181`.
- 공식 ZIP에는 시뮬레이터 바이너리가 없고, 현재 저장소 루트에는 제출용 작업 파일이 아니라 원본 ZIP/PDF/settings만 있다. 근거: 루트 파일 조사 및 `.context/ssafy-race-analysis/shared-context.md`.

### 작업 가정

- 명시적인 점수 산식은 추출된 PDF 텍스트에서 확인되지 않았다. 따라서 현재 전략은 "완주율을 유지하면서 랩/주행 시간을 최소화한다"를 우승 목표로 둔다. 근거: `lap_progress` 100이 완료를 의미하고, UI 주행 시간과 트랙 설명에서 속도/라인/브레이킹이 강조된다. 근거: `.context/ssafy-race-analysis/pdf-text/싸피레이스_상세가이드_20260515.reflow.txt:358-362`, `520-567`.
- Python을 1차 구현 언어로 삼고, 0.1초 루프 성능이나 안정성 문제가 실측되면 C++ 이전을 검토한다. 근거: Python 템플릿의 가독성 및 빠른 반복 가능성, C++ 템플릿/라이브러리 존재.

## 2. 대회 규칙/점수 방식 요약

| 항목 | 요약 | 근거 |
| --- | --- | --- |
| 언어 | Python, Java, C++ | 상세가이드 `30-35` |
| 제출 파일 | Python `my_car.py`, Java `MyCar.java`, C++ `MyCar.cpp`만 반영 | 상세가이드 `80-90`, `183-220`, `260-294` |
| 제어 주기 | 약 0.1초마다 `control_driving` 호출 | 상세가이드 `80-90`, `211`; `drive_controller.py:60`, `183-197` |
| 진행/완주 | `lap_progress`가 목표까지의 진행률이고 100이면 완료 | 상세가이드 `358-362` |
| 페널티 | 도로 이탈 시 brake 0.9와 감속 페널티 | 상세가이드 `448-450`; `drive_controller.py:168-181` |
| 장애물 | 전방 200m, 가까운 순서, 길이 2m, 좌우 약 1m | 상세가이드 `365-379` |
| 상대 차량 | 전후방 200m 차량 정보, 거리/좌우 위치/속도 포함 | 상세가이드 `380-412` |
| 맵 | 10 Basic, 31 Speed 장애물, 61 SSAFY 장애물, 71 SSAFY 저사양 장애물, 161 Germany 장애물 | Quick Start `157-186`; settings JSON |

점수 산식은 미확인이다. 문서에서는 "점수 최적화"를 "완주 성공률, 페널티/충돌 최소화, 랩타임 단축"의 복합 목표로 둔다.

## 3. 현재 프로젝트 구조와 핵심 제어 흐름

### 프로젝트 구조

- `.context/ssafy-race-analysis/extracted/MyCar_20260515/Template_Python/Bot_Python/my_car.py`: 기본 Python 봇. 현재는 `steering=0`, `throttle=1`, `brake=0`에 가까운 직진 예제다. 근거: `my_car.py:49-52`.
- `.context/ssafy-race-analysis/extracted/MyCar_20260515/Template_Python/1_Basic/my_car.py`: 더 강한 rule-based 샘플. 전방 각도, 중앙 보정, 속도별 조향 보정, 커브 브레이킹을 사용한다. 근거: `my_car.py:59-122`.
- `.context/ssafy-race-analysis/extracted/MyCar_20260515/Template_Python/Bot_Python/DrivingInterface/drive_controller.py`: AirSim 연결, 센서 생성, `control_driving` 호출, 페널티 적용, 0.1초 sleep을 수행한다. 근거: `drive_controller.py:60-63`, `121-183`, `197`.
- `.context/ssafy-race-analysis/extracted/MyCar_20260515/Template_Python/Bot_Python/DrivingInterface/airsim/client.py`: RPC 포트 41451, `setCarControls`, `getCarState`, `getAlgoUserAPI`, `getAlgoAdminAPI`, `input_player_lap_progress` 제공. 근거: `client.py:331-355`.
- `.context/ssafy-race-analysis/extracted/settings/*.json`: 맵/차량 배치를 담은 설정 파일. 예: `settings_타임어택-스피드.json`은 Map 31, `settings_타임어택-싸피.json`은 Map 61, `settings_타임어택-독일.json`은 Map 161.

### 제어 흐름

1. 시뮬레이터/AirSim 설정은 사용자 문서 폴더의 `Documents\AirSim\settings.json`에서 읽힌다. 근거: `drive_controller.py:293-300`.
2. 인터페이스가 `getAlgoUserAPI()`로 도로 폭, 웨이포인트, 장애물, 랩 상태를 가져온다. 근거: `drive_controller.py:63`, `273`.
3. 매 tick마다 차량 상태와 전방 각도/장애물/상대차 정보를 `sensing_info`에 채운다. 근거: `drive_controller.py:121-162`.
4. 사용자 코드의 `control_driving(car_controls, sensing_info)`가 steering/throttle/brake를 갱신한다. 근거: `drive_controller.py:160-183`.
5. 도로 이탈이면 제어값 위에 페널티가 적용된 뒤 `setCarControls`로 전송된다. 근거: `drive_controller.py:168-183`.

## 4. 우승 전략 Top 10

| 우선순위 | 전략 | 기대 효과 | 난이도 | 리스크/검증 |
| --- | --- | --- | --- | --- |
| 1 | 곡률 기반 목표 속도 엔벨로프 | 고속 직선과 코너 안정성의 균형. 샘플의 단순 `fwd_angle > 45/80` 브레이킹보다 세밀함 | 중 | 목표 속도별 완주율/랩타임 비교. 근거: 샘플 `1_Basic/my_car.py:91-108` |
| 2 | lookahead 조향 개선 | `track_forward_angles` 20개, 200m 정보를 가중 평균/곡률로 사용해 조향 진동 감소 | 중 | 0.1초 안에 계산 완료, 조향 jerk 감소 측정. 근거: 상세가이드 `343-355` |
| 3 | 도로 폭을 활용한 racing line | 중앙 고정이 아니라 코너 진입-정점-탈출에서 목표 `to_middle`을 이동해 회전 반경 확보 | 중상 | `half_road_limit` 안전 마진 위반 금지. 근거: 상세가이드 `422-431` |
| 4 | 장애물 corridor planner | 장애물 `dist/to_middle`과 도로 폭으로 좌/우/중앙 통로를 선택 | 중상 | 장애물과 도로 경계 동시 회피. 근거: 상세가이드 `365-379` |
| 5 | track/map별 파라미터 프로파일 | Basic, Speed, SSAFY, Germany의 폭/길이/코너 특성이 다르므로 속도/브레이크/마진을 분리 | 중 | 맵별 설정으로 실험. 근거: 상세가이드 `520-567`, settings JSON |
| 6 | 충돌/정지/역주행 recovery 상태기계 | `collided`, `moving_forward`, speed 정체, `lap_progress` 정체를 기반으로 빠른 복구 | 중 | 복구가 오히려 후진/재충돌하지 않는지 시나리오 검증. 근거: 상세가이드 `318-322`, `drive_controller.py:124-128`, `217` |
| 7 | throttle/brake hysteresis | 브레이크/스로틀 토글로 생기는 진동을 줄이고 코너 탈출 가속을 안정화 | 하중 | control 로그에서 throttle/brake 전환 횟수와 랩타임 측정 |
| 8 | 상대 차량-aware battle logic | `opponent_cars_info`로 추월/방어/접촉 회피. 타임어택 로직 위에 얇게 추가 | 중상 | 타임어택 성능 저하 금지. 근거: 상세가이드 `380-412` |
| 9 | 텔레메트리 기반 파라미터 sweep | 추측 대신 맵별 목표 속도, lookahead, 마진, brake 계수를 실험으로 고정 | 중 | 실험 로그 누락 방지. `docs/race-experiment-plan.md`에 템플릿 정의 |
| 10 | Python 우선, C++ 백업 | 빠른 반복은 Python, 최종 loop time 문제가 실측되면 C++ 이식 | 중상 | 동일 알고리즘 재현성 비교. 근거: 언어별 템플릿 및 제출 파일 제약 |

## 5. 즉시 할 수 있는 Quick Wins

1. `Bot_Python/my_car.py` 대신 `Template_Python/1_Basic/my_car.py`를 기준선으로 삼는다. 직진 봇보다 전방 각도/브레이크/센터링이 이미 있다. 근거: `Bot_Python/my_car.py:49-52`, `1_Basic/my_car.py:59-122`.
2. `is_debug = False`를 기본값으로 유지한다. debug print는 0.1초 루프에서 불필요한 I/O 병목과 콘솔 지연을 만든다. 근거: `1_Basic/my_car.py:36-50`, 제어 주기 `drive_controller.py:60`.
3. 커브 판단을 단일 최대각이 아니라 가까운 구간 가중치로 바꾼다. 10m 단위 20개 각도가 있으므로 가까운 30-80m는 강하게, 먼 100-200m는 약하게 반영한다. 근거: 상세가이드 `343-355`.
4. `to_middle` 보정값을 단순 `(to_middle / 80) * -1`에서 속도/도로폭/코너 방향 기반 목표선 추종으로 바꾼다. 근거: `1_Basic/my_car.py:63`, 상세가이드 `309-315`, `422-431`.
5. 브레이크를 `fwd_angle > 45/80` 계단식에서 목표 속도 초과분 비례 방식으로 바꾼다. 근거: `1_Basic/my_car.py:91-108`.
6. 장애물 회피는 먼저 50m 이내 근접 장애물부터 처리하고, 통로가 없을 때만 강한 감속을 한다. 근거: 상세가이드 `365-379`.
7. 각 실험마다 `map`, 파라미터, 완주 여부, 시간, 충돌/페널티 추정, 관찰 메모를 남긴다. 첫 2시간은 코드 멋보다 계측 품질이 더 중요하다.

## 6. 중기 개선 과제

- **Map 31 Speed**: 긴 직선에서 throttle을 오래 유지하되, 급커브/장애물 전 목표 속도를 먼저 낮춘다. 근거: 상세가이드 `533-543`.
- **Map 61/71 SSAFY**: 폭이 22m로 넓지만 연속 직각 코너와 고저차가 핵심이다. racing line과 속도 엔벨로프의 이득이 크다. 근거: 상세가이드 `547-556`.
- **Map 161 Germany**: 폭 14m로 좁고 hairpin braking이 중요하다. 도로 경계 마진과 코너 진입 감속이 우선이다. 근거: 상세가이드 `557-567`.
- **Recovery 모듈**: 속도가 0에 가깝고 `collided=True` 또는 `moving_forward=False`이면 일정 tick 동안 brake/reverse/steer를 제한된 패턴으로 수행한다.
- **Battle 모드 분리**: 기본 racing line을 유지하고, 상대차가 30m 이내이고 같은 lane이면 회피 목표 `to_middle`만 덧씌운다.

## 7. 고위험/고보상 실험

- **경량 MPC 스타일 탐색**: 전방 200m 각도와 장애물로 5-7개 후보 lane을 점수화한다. 이득은 크지만 Python 0.1초 루프를 넘기면 손해다.
- **트랙별 hardcoded 파라미터**: settings 맵 번호와 트랙 특성을 이용하면 빠르게 성능이 오른다. 단, 제출 환경에서 맵 식별을 코드가 직접 알 수 없으면 런타임 센서 기반 분류로 대체해야 한다.
- **C++ 최종 이식**: Python에서 검증한 알고리즘을 C++로 옮겨 loop latency를 줄인다. 이식 비용과 버그 위험이 있으므로 Python loop time이 실제로 문제일 때만 진행한다.
- **오프라인 튜닝 시뮬레이터 흉내**: PDF/센서 규격만으로 간이 모델을 만들 수 있지만 실제 AirSim 물리와 다르면 잘못된 최적화가 된다. 실제 주행 로그 보정 전에는 보조 도구로만 사용한다.

## 8. 하지 말아야 할 함정

- 제출 반영이 안 되는 `DrivingInterface`, `airsim`, settings 내부 로직을 수정해 성능을 올리려 하지 않는다. 제출 파일 제약 때문에 서버에 반영되지 않는다. 근거: 상세가이드 `183-220`.
- 도로 중앙 유지에만 집착하지 않는다. 빠른 랩타임에는 도로 폭과 코너 방향을 이용한 목표선이 필요하다.
- 최고속만 올리지 않는다. 도로 이탈은 brake 0.9 페널티로 곧바로 손해다. 근거: 상세가이드 `448-450`.
- debug print를 켠 상태로 성능을 판단하지 않는다. I/O가 tick 안정성을 흐린다.
- 장애물을 단일 회피 조향으로만 처리하지 않는다. 장애물 뒤 코너와 도로 경계를 함께 봐야 한다.
- 명시 점수 산식이 없는데 특정 점수 공식을 가정하지 않는다. 공식 페이지나 랭킹 화면 확인 전까지는 랩타임/완주율 중심으로 둔다.

## 9. 제출 전 체크리스트

- [ ] 최종 수정 파일이 제출 대상 단일 파일인지 확인: Python `my_car.py`, Java `MyCar.java`, C++ `MyCar.cpp`.
- [ ] 원본 ZIP/PDF를 수정하지 않았는지 확인.
- [ ] debug print와 불필요한 파일 I/O가 꺼져 있는지 확인.
- [ ] 모든 contest 맵 설정 10/31/61/71/161에서 최소 3회 이상 완주 테스트.
- [ ] 도로 이탈/충돌/정지/역주행 recovery 시나리오를 별도로 테스트.
- [ ] 타임어택 성능과 battle 모드 회피 로직을 분리 검증.
- [ ] 팀 등록, 팀 이미지 200KB 이하, 팀원 선택, 저장까지 운영 체크 완료. 근거: `.context/ssafy-race-analysis/pdf-text/싸피레이스_팀등록가이드_20260515.reflow.txt:6-45`.
- [ ] 공식 대회 페이지나 시뮬레이터 랭킹 화면에서 실제 평가 기준을 최종 확인.

