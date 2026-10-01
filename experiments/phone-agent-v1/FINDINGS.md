# phone-agent-v1 실행 결과 (2026-09-28)

스마트폰 · 개인 비서형 AI 에이전트에게 일상의 일(일정·연락·결제·예약·정보 찾기)을 맡기는 경험. 기반 기술 = 에이전틱 AI(기본값). **quick · 짧게(short) · full · 동시 3** — 짧은 테스트 방향의 첫 실측. 전부 합성 데이터.

## 시간 — 15분 50초 (00 정답표 57초 별도)

| 단계 | 초 | 비고 |
|---|---:|---|
| 01 합성 생성 | 108 | 3배치 동시. QA 「재생성 권장」으로 **한 번 더 돈 뒤**의 값 (첫 생성 ≈ 2분 추가) |
| 10 추출 | 150 | 2배치 |
| 20 연결 | 90 | sonnet (quick) · tension 4 |
| 25 유추 | 54 | |
| 30 principle | 75 | |
| 35 미래 가정 | 46 | |
| 40 시나리오 | 102 | |
| 50 평가 | 123 | |
| 60 family | 30 | |
| 70 윤문 | 66 | 후보 5개만 |
| 05 기준선 | 17 | 본 사슬과 나란히 |

비교: familyhub-v1(standard) 22분 · tv-v1(순차) 36분. 재생성이 없었으면 ≈ 14분. 이 실행은 25 유추·30 principle 배치 분할 **이전** 코드로 돌았다(다음 실행부터 적용).

첫 시도는 01 생성에서 `JSONDecodeError` 로 멈췄다 — 병렬 배치가 `job.json` 을 쓰는 중에 다른 배치가 다시 읽었다. 원자적 쓰기로 고친 뒤 재개했다.

## 글 길이 (레코드당 평균 글자) — 짧게 쓰기 효과

| | phone-agent-v1 (short) | familyhub-v1 (normal) |
|---|---:|---:|
| principle | 137 | 346 (−60%) |
| 미래 가정 | 265 | 375 (−29%) |
| 시나리오 | 423 | 751 (−44%) |

시나리오에 `agent_actions`·`human_checkpoints`·`reversal` 이 붙고도 절반 가까이 짧다.

## Phase 0 — 10개 중 9 PASS

FAIL 1: false_friend_split 0.67(≥0.7). 정답 tension 4/4 복원(순도 0.64~1.0). distractor_intrusion 0.07 · counterexample_kept 0.75 — familyhub 에서 FAIL 이던 방해물 침입은 통과.

## 판단 모듈 B(assign) 첫 비교 — 같은 corpus

`python3 -m judge run assign --backend claude_cli --model sonnet --emit-tensions` (102 질문 ≈ 4분) → `faultline score --tensions judge_runs/20260928-050945/tensions.judged.jsonl`.

| 지표 | 20 연결 | B (accept 만) |
|---|---:|---:|
| distractor_intrusion | 0.07 | **0.00** |
| false_friend_split | 0.67 FAIL | **1.00** |
| counterexample_kept | 0.75 | 0.50 FAIL |
| 커버 평균 | 0.79 | 0.62 |

B 는 거짓 친구·방해물을 고치고 반례·커버를 잃는다. review 까지 넣으면 recall 0.75 로 나빠진다. n=1 — 상세는 `docs/JUDGE.md` §8.

## 탐색 층

- tension 4 → principle 5 → 미래 가정 5 → 시나리오 10 → 평가 10 → 후보 5 (적격 7).
- 자동 후보: SCN_009 관계별 공개 기준 설정 · SCN_002 필요할 때만 되묻기 · SCN_004 되돌릴 수 있나로 판단 · SCN_006 분쟁 나면 바로 제출 · SCN_008 말투 학습형 자동손질. 위임의 경계(금액·되돌림·관계·진정성)가 주제로 모였다 — 에이전틱 규칙이 의도대로 작동.
- **family: 10 → 5, 그러나 principle 과 1:1 로 겹친다.** 레버 기준·목표 개수 규칙으로 "거의 전부 단독"(tv 18→17, familyhub 24→20)은 벗어났지만, 이번엔 principle 묶음을 그대로 되풀이해 지도가 새 정보를 주지 않는다. → 60 프롬프트에 "principle 과 같은 묶음이면 정보가 없다 — principle 을 가로지르는 레버를 찾는다" 규칙 추가, 다음 실험에서 확인.

## 드러난 것 / 다음

1. 01 생성의 member 수 요청이 정책(twin·함정 포함)과 어긋나 QA 가 매번 재생성을 권했다 — 고침(다음 실험에서 확인).
2. 짧은 테스트(quick·short)는 15분대. 병목은 추출(150)·평가(123)·생성(108)·시나리오(102).
3. B 를 필터로 쓰는 조합(20 연결의 반례 유지 + B 의 member·무소속 판정)을 **먼저 정의하고** 새 corpus 로 비교.
