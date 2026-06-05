# SSAFY RACE 리스크 검토

작성일: 2026-05-31

## 1. 전제

이 문서는 확인된 사실과 작업 가정을 분리한다. 확인된 사실의 핵심 근거는 `.context/ssafy-race-analysis/shared-context.md`, PDF 추출 텍스트, 추출 코드, settings JSON이다. 원본 ZIP/PDF는 수정하지 않았다.

## 2. 규칙 위반 리스크

| 리스크 | 심각도 | 근거 | 완화책 |
| --- | --- | --- | --- |
| 제출 대상이 아닌 파일을 수정해 성능이 오른다고 착각 | 높음 | Python은 `my_car.py`만 반영, Java/C++도 단일 파일만 반영. 상세가이드 `80-90`, `183-220`, `260-294` | 최종 변경은 제출 파일 내부로 제한. `DrivingInterface`, `airsim`, settings 수정 효과는 로컬 실험용으로만 취급 |
| 원본 ZIP/PDF 손상 | 높음 | 사용자 명시 원칙 | 원본은 읽기 전용. 추출/분석은 `.context/ssafy-race-analysis/` 아래에서만 수행 |
| 공식 점수 산식 미확인 상태에서 잘못된 목표 최적화 | 중상 | PDF 추출 텍스트에 명시 산식 미확인 | 공식 대회 페이지/랭킹 화면에서 평가 기준 확인 전까지 완주율+랩타임 중심으로 보수적 최적화 |
| 제출 파일에 외부 의존성 사용 | 중상 | 서버 제출은 단일 파일 중심 | 표준 라이브러리와 단일 파일 함수/클래스만 사용. 추가 패키지 사용은 제출 환경 확인 전 금지 |
| 팀 등록 누락 또는 이미지 규격 초과 | 중 | 팀 등록 가이드: 팀 생성 필요, 이미지 200KB 이하 | 제출 전 운영 체크리스트에 팀 등록/팀원/이미지 확인 포함 |

## 3. 기술적 실패 리스크

| 리스크 | 심각도 | 징후 | 완화책 |
| --- | --- | --- | --- |
| 과속 코너 진입으로 도로 이탈 페널티 | 높음 | `abs(to_middle) > half_road_limit`, 갑작스러운 brake 0.9, lap time 급증 | 곡률 기반 목표 속도, 도로폭 안전 마진, Map 161 전용 보수 파라미터 |
| 장애물 회피 후 코너 진입 실패 | 높음 | `collided=True`, 큰 steering jerk, 회피 직후 페널티 | corridor planner가 장애물뿐 아니라 다음 30-80m 코너를 함께 점수화 |
| 조향 진동 | 중상 | steering 부호가 tick마다 큰 폭 전환 | lookahead 가중 평균, steering rate limit, hysteresis |
| 과도한 brake/throttle 토글 | 중 | brake_events 증가, 평균속도 하락 | 목표 속도 초과분 비례 제어와 hysteresis |
| 충돌/정지 후 복구 실패 | 중상 | `collided=True` 지속, 낮은 speed 연속, `lap_progress` 정체 | recovery 상태기계. 일정 tick 동안 후진/조향/브레이크 패턴 제한 |
| 0.1초 tick 초과 | 중 | loop_time_ms p95 상승, 제어 지연 | print 제거, 후보 lane 수 제한, precompute, 필요 시 C++ 이식 |
| Python/C++ 이식 불일치 | 중 | 같은 파라미터인데 결과 급변 | Python에서 알고리즘 확정 후 함수 단위로 C++ 포팅, 맵별 회귀 테스트 |

센서/페널티/loop 근거: `.context/ssafy-race-analysis/pdf-text/싸피레이스_상세가이드_20260515.reflow.txt:309-450`, `.context/ssafy-race-analysis/extracted/MyCar_20260515/Template_Python/Bot_Python/DrivingInterface/drive_controller.py:60`, `121-183`, `197`.

## 4. 환경/제출/운영 리스크

| 리스크 | 심각도 | 근거 | 완화책 |
| --- | --- | --- | --- |
| settings 파일 변경 후 시뮬레이터 미재시작 | 중 | Quick Start는 settings 변경 후 재시작을 요구 | 맵 변경 절차에 재시작 포함 |
| 로컬 settings와 대회 settings 불일치 | 중상 | settings ZIP에 Map 10/31/61/71/161 및 battle 변형 존재 | 모든 제공 settings에서 테스트. 제출 전 공식 맵 확인 |
| 저사양 맵/PC에서 프레임 차이 | 중 | `settings_타임어택-싸피_저사양.json`, `settings_배틀-싸피_저사양.json` 존재 | Map 71을 별도 성능/안정성 게이트로 둠 |
| 시뮬레이터 바이너리 부재로 현재 분석 중 실주행 미검증 | 중상 | 현재 루트에는 ZIP/PDF/settings만 있고 simulator binary 없음 | 문서는 전략/실험계획으로 한정. 실제 성능 주장은 주행 후 확정 |
| PDF 텍스트 추출 오차 | 중 | `.context/ssafy-race-analysis/extract_pdf_text.py`는 ToUnicode/Flate 직접 추출 방식 | 중요한 규칙은 PDF 원문 또는 공식 페이지로 교차 확인 |

## 5. 보안/민감정보 리스크

| 리스크 | 심각도 | 확인 내용 | 완화책 |
| --- | --- | --- | --- |
| settings 또는 제출물에 키/토큰 포함 | 낮음-중 | 현재 settings JSON에는 Map, SimMode, Vehicle 정보만 보임 | 제출 전 `rg -n "token|secret|key|password|proxy|http"`로 재검사 |
| 대회/프록시 주소 노출 | 낮음 | 상세가이드에는 예시 proxy 문자열이 텍스트에 있음 | 문서에는 운영상 필요한 수준만 인용. 제출 파일에 개인 proxy/계정 정보 금지 |
| 로그에 개인정보/팀 정보 포함 | 중 | 팀 등록 과정에는 팀명/팀원 정보가 들어감 | 실험 로그는 차량 성능 데이터 중심으로 유지. 팀/개인 식별정보 제외 |
| 네트워크/RPC 오용 | 중 | AirSim RPC는 기본 port 41451 사용. 근거: `airsim/client.py:331-355` | 공식 인터페이스 호출만 사용. 외부 네트워크 전송/우회 자동화 금지 |

## 6. 완화 우선순위

1. **제출 파일 경계 고정**: 최종 변경은 제출 단일 파일에 들어가야 한다.
2. **완주율 게이트**: 어떤 속도 개선도 완주율을 깨면 채택하지 않는다.
3. **맵별 최소 회귀 세트**: 10/31/61/71/161에서 3회 이상 완주 확인.
4. **도로 이탈/충돌 지표화**: 감으로 보지 말고 페널티/충돌/정지 횟수를 기록한다.
5. **실시간성 확인**: debug print 제거, loop time 측정, p95 20ms 목표.
6. **운영 체크**: settings 재시작, 팀 등록, 이미지 200KB, 제출 파일명/언어 확인.
7. **공식 평가 기준 확인**: 점수 산식이 확인되면 실험 목표를 즉시 업데이트한다.

## 7. Go/No-Go 체크

- Go: 모든 contest 맵에서 완주, baseline 대비 중앙값 시간 개선, 충돌/페널티가 baseline 이하, 제출 파일 단일화 완료.
- Conditional Go: 한 맵에서만 개선됐고 다른 맵 성능이 불확실하면 맵별 프로파일 조건을 명확히 하고 공식 운영 방식 확인 후 제출.
- No-Go: 완주율 하락, 도로 이탈 페널티 증가, recovery 실패, 외부 의존성/비제출 파일 의존, 점수 산식 미확인 상태의 과도한 특화.

