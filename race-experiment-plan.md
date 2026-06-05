# SSAFY RACE 실험 계획

작성일: 2026-05-31

## 1. 목표

확인된 문서에는 명시 점수 산식이 없다. 따라서 실험 목표는 다음 순서로 둔다.

1. 완주율 100% 확보.
2. 도로 이탈/충돌/정지/역주행 실패 제거.
3. 맵별 랩타임 최소화.
4. battle 모드에서는 타임어택 성능 저하를 최소화하면서 접촉/막힘을 줄인다.

근거: `lap_progress` 100이 완료를 의미한다는 설명은 `.context/ssafy-race-analysis/pdf-text/싸피레이스_상세가이드_20260515.reflow.txt:358-362`, 페널티 설명은 `448-450`, 트랙별 속도/코너/장애물 강조는 `520-567`.

## 2. 측정 지표

| 지표 | 정의 | 목적 |
| --- | --- | --- |
| finish_rate | 같은 맵/파라미터에서 완주한 비율 | 우승 전략의 1차 안전 게이트 |
| lap_or_race_time | UI 또는 로그로 확인한 완료 시간 | 핵심 최적화 목표 |
| max_lap_progress | 실패 시 도달한 최대 `lap_progress` | 실패 위치 파악 |
| avg_speed / p95_speed | 주행 중 평균/상위 속도 | 직선 가속과 과속 위험 확인 |
| offroad_penalty_count | `abs(to_middle) > half_road_limit` 또는 급격한 brake 0.9 추정 횟수 | 도로 이탈 리스크 측정 |
| collision_count | `collided=True` 전환 횟수 | 장애물/상대차 실패 측정 |
| stalled_ticks | 낮은 speed가 연속된 tick 수 | 정지/막힘/recovery 실패 확인 |
| steering_jerk | tick별 steering 변화량 평균/최대 | 조향 진동과 불안정성 확인 |
| brake_events | brake가 임계값 이상인 tick 수 | 과도한 감속 확인 |
| loop_time_ms | `control_driving` 계산 시간 | 0.1초 tick 초과 리스크 확인 |

센서/제어 근거: `.context/ssafy-race-analysis/pdf-text/싸피레이스_상세가이드_20260515.reflow.txt:309-446`; 제어 주기 근거: `.context/ssafy-race-analysis/extracted/MyCar_20260515/Template_Python/Bot_Python/DrivingInterface/drive_controller.py:60`, `183-197`.

## 3. 베이스라인 수집 방법

### 준비

1. 원본 ZIP/PDF는 수정하지 않는다.
2. 시뮬레이터의 `Documents\AirSim\settings.json`에 테스트할 settings 파일을 복사한 뒤 시뮬레이터를 재시작한다. 근거: Quick Start 설정 섹션과 `drive_controller.py:293-300`.
3. baseline A: `Template_Python/Bot_Python/my_car.py` 직진 봇.
4. baseline B: `Template_Python/1_Basic/my_car.py` rule-based 샘플.
5. 각 맵에서 3회 이상 반복한다. 가능하면 5회 반복해 우연한 충돌/시작 편차를 줄인다.

### 대상 맵

| 설정 파일 | Map | 목적 |
| --- | --- | --- |
| `.context/ssafy-race-analysis/extracted/settings/settings_타임어택-베이직.json` | 10 | 단순 주행/조향 안정성 |
| `.context/ssafy-race-analysis/extracted/settings/settings_타임어택-스피드.json` | 31 | 고속 직선 + 장애물 |
| `.context/ssafy-race-analysis/extracted/settings/settings_타임어택-싸피.json` | 61 | 넓은 도로 + 연속 직각 코너 + 장애물 |
| `.context/ssafy-race-analysis/extracted/settings/settings_타임어택-싸피_저사양.json` | 71 | 저사양 SSAFY 변형 |
| `.context/ssafy-race-analysis/extracted/settings/settings_타임어택-독일.json` | 161 | 좁은 도로 + hairpin braking |
| `.context/ssafy-race-analysis/extracted/settings/settings_배틀-싸피.json` | 61 | 상대 차량 회피/추월 |
| `.context/ssafy-race-analysis/extracted/settings/settings_배틀-싸피_저사양.json` | 71 | 저사양 battle |

## 4. 실험 후보 백로그

| ID | 실험 | 성공 기준 | 난이도 | 리스크 |
| --- | --- | --- | --- | --- |
| E01 | `1_Basic`을 기준선으로 채택 | 직진 봇 대비 finish_rate와 시간 모두 개선 | 하 | 없음. 기준선 선택 |
| E02 | 가까운 전방 각도 가중 평균 조향 | Map 10/31에서 steering_jerk 감소, 시간 악화 없음 | 중 | 반응이 늦어질 수 있음 |
| E03 | 곡률 기반 목표 속도 엔벨로프 | Map 31/161 완주율 유지, lap time 3% 이상 단축 | 중 | 과감한 속도 설정 시 이탈 |
| E04 | brake hysteresis | brake_events 감소, 코너 탈출 속도 증가 | 하중 | 코너 진입 감속 부족 |
| E05 | 목표 `to_middle` racing line | Map 61/161 lap time 3-7% 단축 | 중상 | 경계 마진 부족 시 페널티 |
| E06 | 장애물 corridor planner | Map 31/61/161 collision_count 감소, lap time 악화 2% 이하 | 중상 | 회피 후 코너 진입 실패 |
| E07 | recovery 상태기계 | 충돌/정지 시 10초 이내 정상 주행 복귀 | 중 | 후진/브레이크 패턴이 시간 손실 |
| E08 | 맵별 파라미터 프로파일 | 각 맵에서 단일 파라미터 대비 시간 개선 | 중 | 제출 환경에서 맵 식별 불확실 |
| E09 | battle 상대차 회피 overlay | battle 완주율 개선, 타임어택 성능 변화 없음 | 중상 | 지나친 회피로 시간 손실 |
| E10 | Python loop profiling | p95 loop_time_ms < 20ms | 하 | 계측 코드가 성능을 흐릴 수 있음 |
| E11 | C++ 이식 검토 | 동일 알고리즘에서 시간/loop 안정성 개선이 명확할 때만 진행 | 상 | 이식 버그와 검증 비용 |

## 5. 반복 최적화 루프

`compound-engineering:ce-optimize` 원칙에 맞춰 대화보다 디스크 로그를 기준으로 반복한다.

1. **Spec**: 맵, 파라미터, 성공 기준, 고정 조건을 한 줄로 정의한다.
2. **Baseline**: 같은 맵에서 baseline B를 3-5회 측정한다.
3. **Single Change**: 한 번에 하나의 전략만 바꾼다.
4. **Measure**: 완주율, 시간, 충돌, 페널티, loop time을 기록한다.
5. **Gate**: 완주율이 떨어지면 시간 개선이 있어도 보류한다.
6. **Keep or Revert**: 맵별로 개선된 파라미터만 유지한다.
7. **Digest**: 배치마다 어떤 조건에서 왜 좋아졌는지 5줄 이내로 요약한다.

권장 로그 위치: `.context/ssafy-race-analysis/experiments/`. 이 폴더는 분석 산출물 위치이며 원본 ZIP/PDF를 변경하지 않는다.

## 6. 실험별 성공 기준

- 안정성 게이트: 각 contest 맵에서 3회 연속 완주 전까지는 lap time 개선을 채택하지 않는다.
- 성능 게이트: 완주율을 유지하면서 같은 맵 baseline 중앙값 대비 3% 이상 단축하면 채택 후보로 둔다.
- 회피 게이트: 장애물/상대차 실험은 collision_count를 낮추고 lap time 악화가 2% 이하일 때 채택한다.
- 실시간 게이트: `control_driving` p95 계산 시간이 20ms를 넘으면 알고리즘 단순화 또는 C++ 검토를 시작한다. 0.1초 tick 자체를 넘기면 즉시 실패다.
- 제출 게이트: 최종 로직은 제출 대상 단일 파일에 들어가야 한다.

## 7. 결과 기록 템플릿

```markdown
## Experiment E__

- Date:
- Map/settings:
- Bot version/commit or file copy:
- Changed parameter/logic:
- Runs:
  - run 1: finish yes/no, time, max_lap_progress, collisions, penalties, notes
  - run 2:
  - run 3:
- Median time:
- Finish rate:
- Collision/penalty summary:
- Loop time summary:
- Decision: keep / tune / reject
- Evidence screenshot/log path:
- Next hypothesis:
```

## 8. 첫날 권장 순서

1. Map 10에서 baseline B 완주와 로그 포맷을 확정한다.
2. Map 31에서 목표 속도 엔벨로프와 brake hysteresis를 튜닝한다.
3. Map 61에서 racing line과 장애물 corridor를 조합한다.
4. Map 161에서 좁은 도로/hairpin 전용 감속 마진을 만든다.
5. Battle 설정은 타임어택 로직이 안정된 뒤 상대차 overlay만 추가한다.

