# 판단 모듈 (judge/) — Jev로 교체 가능한 typed judge

작성일: 2026-09-27 · 상태: **B 는 파이프라인 선택 스테이지 22 로 연결(`config.assign=on`, 2026-09-28) · A·C 미연결 · B 첫 비교 §8** · 시각 구조도: [`judge-architecture.html`](judge-architecture.html)

생성은 LLM이 하고, 판단은 이 모듈이 한다. 판단은 전부 "상태 텍스트 + 닫힌 선택지 질문 → 선택지별 확률" 모양이라, 지금은 OpenAI·OpenRouter·로컬 모델로 돌리고 Jev early access가 열리면 백엔드 한 줄만 바꾼다. 설계 근거는 원 설계 문서 §17(Jev·Judge·인간의 역할)과 §18(평가와 지도화).

## 1. 구조

```text
 Faultline 파이프라인      00 생성 → 10 추출 ─A─→ 20a 후보 ─B─→ 20b 배정 → 30 원리 → 40 시나리오 ─C─→
                                         │                    │                                  │
 ┌───────────────────────────────────────┼────────────────────┼──────────────────────────────────┼────┐
 │ 태스크 tasks.py         ExtractCheck(A)            Assign(B)                        ScenarioMapTV(C) │
 │   레코드 → 상태 텍스트 · 질문 고르기 · 답 조합(확정/검토/플래그)                                      │
 │ 질문 은행 bank/*.json   extract_check@v1 · assign@v1 · scenario_map_tv@v1 (버전 관리되는 원자 질문)   │
 │ 스키마 schema.py        Question(noul·choice·score) · Answer(확률·방식·질량·사용량)  ↔ Jev 타입      │
 │ 백엔드 backends.py      mock · openai · openrouter · custom(로컬) · adapter · jev                   │
 │ 정책 policy.py          확률 → accept / review (+이유). 여기서는 아무것도 버리지 않는다                │
 │ 기록                    <root>/judge_runs/<run>/<task>.jsonl · manifest.json · tensions.judged.jsonl │
 └──────────────────────────────────────────────────────────────────────────────────────────────────┘
 정보 차단선: hidden/labels.json ──(Phase 0 채점 때만)──→ calibrate.py → 정확도 · Brier · ECE · 구간표
             태스크·백엔드는 hidden/ 을 읽지 않는다 (selftest 가 상태에 HT_ 가 없는지 검사)
```

| 파일 | 역할 |
|---|---|
| `judge/schema.py` | 질문·답 타입. 선택지 2~255개 검사 (Jev 공개 제약 255) |
| `judge/bank/*.json` | 질문 은행. 문구가 사실상 프롬프트라 버전(`@v1`)으로 관리하고 manifest에 남긴다 |
| `judge/tasks.py` | 태스크 3종. `items()`가 상태를 만들고 `run_item()`이 묻고 조합한다 |
| `judge/backends.py` | 백엔드 6종. 전부 `ask(state, questions) → {id: Answer}` |
| `judge/policy.py` | 퍼지 결정 규칙. 임계값은 출발점이며 은행의 `policy`로 질문별로 덮어쓴다 |
| `judge/calibrate.py` | 보정 측정. hidden 을 읽는 유일한 파일 |
| `judge/selftest.py` | 외부 호출 없는 검사 43개 (가짜 OpenAI 호환 서버 포함) |
| `judge/attach/20a_tension_candidates.md` | B 자리를 열 때 쓸 20a 프롬프트 초안 |

## 2. 태스크 3종 — 붙일 자리

| 자리 | 태스크 | 판단 단위 | 원자 질문 | 조합 결과 | Phase 0 지표 |
|---|---|---|---|---|---|
| A · 10 뒤 | `extract_check` | 추출 행동 1개 | 근거 구절이 행동을 뒷받침하는가 · 방향이 뒤집혔는가 · 채워진 context 칸마다 원문에 명시됐는가 · 원문에 지시문이 있는가 · 추출이 그 지시를 따랐는가 | pass / flag(이유) / review | excerpt_grounded · hallucinated_context · negation_flip · injection_leak |
| B · 20b | `assign` | 추출 행동 1개 | tension 후보 중 어디인가(**'없음' 포함**) → 고른 후보에 대해 member인가 반례인가 | 배정·확률·차이·차순위 + accept/review, `--emit-tensions`로 tensions.jsonl 모양 출력 | distractor_intrusion · twin_merge · false_friend_split · counterexample_kept |
| C · 40 뒤 | `scenario_map_tv` | 시나리오 1개 | grounding · 흔한 기능과의 거리 · plausibility · TV fit · 시청 단위 · 입력 부담 · 미래 변화 필요 · 자기모순 | 근거×새로움 사분면 + horizon 힌트. **버리지 않는다** | (Phase 1 이후) |

TV 특화 축은 `scenario_map_tv` 은행에만 있다. 다른 기기로 넓힐 때는 은행 파일을 하나 더 만들면 된다 (`scenario_map_<기기>.v1.json`).

B가 1순위인 이유: Phase 0의 연결 지표 4개가 전부 이 판정에서 갈리고, PHASE0_PLAN의 처방("'어디에도 속하지 않음' 선택지 강화")이 Choice에 `NONE`을 넣는 것과 같다.

## 3. 백엔드와 확률

| 백엔드 | 확률 산출 | 필요한 것 | 상태 |
|---|---|---|---|
| `mock` | 해시 기반 가짜 분포 | 없음 | 작동 (배선 검사용) |
| `claude_cli` | verbal (파이프라인과 같은 격리 실행기 `engine.executors.run_cli`) | `claude` 로그인 | **작동** — 외부 키·새 서비스 없음. 보정은 verbal 이라 약하다 |
| `openai` | logprobs (기본) · sampling · verbal | `OPENAI_API_KEY` | 가짜 서버로 경로 검증 · 실 API 미호출 |
| `openrouter` | 같음. 로그확률을 안 주는 모델·경로면 자동으로 sampling | `OPENROUTER_API_KEY` | 같음 |
| `custom` | 같음 | `--base-url` (Ollama·LM Studio·vLLM 등 OpenAI 호환 로컬) | 같음 |
| `adapter` | verbal (공식 어댑터가 모델에게 확률 JSON을 쓰게 함 — 소스 확인) | `pip install 'system-one-adapter[openai]'` + 해당 키 | 미설치라 생성 거부까지만 검증 |
| `jev` | Jev의 보정 확률 | TypeSafe early access + `typesafe_sdk` | **클라이언트 생성부만 빈칸** (`JevBackend._client`) |

- **logprobs 방식:** 답을 코드 한 글자(A·B… / 점수는 1~5)로 받게 하고 첫 토큰의 top_logprobs(최대 20)를 선택지별로 모은다. 유효 선택지에 실린 질량(`mass`)도 남기며, 0.5 미만이면 형식 이탈로 보고 검토로 보낸다. 선택지가 26개를 넘거나 점수가 9단계를 넘으면 그 질문만 verbal로 내려간다.
- **왜 어댑터를 기본으로 두지 않았나:** 어댑터의 확률은 모델이 말로 적은 값이라 보정이 가장 약한 방식이다. logprobs 방식이 Jev의 보정 주장과 비교할 기준선으로 더 낫다. 어댑터는 Jev와 **같은 호출 모양을 미리 리허설하는 용도**로 남겼다.
- **키:** 환경변수에서만 읽고 기록하지 않는다. 키가 없으면 첫 호출 전에 멈춘다.
- **외부 호출:** README 규칙상 웹 서버(`scripts/server.py`)는 외부 호출을 하지 않는다. 판단 모듈의 API 호출은 CLI(`python3 -m judge`)에서만 한다. 입력은 합성 데이터(S1)다.

## 4. Jev 대응과 전환 체크리스트

| 우리 | Jev (typesafe_sdk) | 확인 |
|---|---|---|
| `noul` | `Noul(instructions=…)` → `NoulAnswer(noul=p)` | 확인 (어댑터 README·소스) |
| `choice` | `Choice(criteria=[…])` → `ChoiceAnswer(choice, confidence, probabilities)` | 필드 확인 · 생성자가 `instructions`를 받는지는 **미확인** |
| `score` | `Score(criteria=[…])` → `ScoreAnswer(score, confidence, probabilities{int}, legend)` | 필드 확인 · 확률 키가 0부터인지 1부터인지 **미확인** (둘 다 받게 함) |
| 선택지 설명 | Jev는 값만 받으므로 지시문 끝에 "선택지: - 값: 설명"으로 붙인다 | 설계 결정 |
| `ask(state, questions)` | `system_one(state=…, questions={id: 질문})` | 어댑터가 "drop-in"이라 밝혀 같은 모양으로 둠 |

준비된 것: 원자 질문 분해 · 타입·선택지 수 검사 · 구조화된 상태 빌더 · 확률 기반 결정 규칙 · 백엔드 교체 인터페이스 · 보정 측정기 · 사용량·지연 기록.

Jev 받으면 할 일 (이 순서로, 대략 반나절):
1. `typesafe_sdk` 설치 → `JevBackend._client()`를 공식 문서대로 채운다 (키는 `TYPESAFE_API_KEY`).
2. `to_sdk()`의 미확인 가정 두 개(Choice·Score 생성자 인자)를 문서로 확인해 고친다.
3. `python3 -m judge run assign --backend jev --limit 5`로 형식만 확인 → 전체 실행.
4. 같은 corpus에서 `openai`/`openrouter`(logprobs) 결과와 `calibrate` 표를 나란히 비교한다.

## 5. 쓰는 법

```bash
python3 -m judge selftest                                   # 외부 호출 없음, 43개 검사
python3 -m judge banks                                      # 질문 은행 목록
python3 -m judge run scenario_map_tv --root examples/mini --backend mock
export OPENROUTER_API_KEY=...                               # 키는 셸에서만
python3 -m judge run assign --root experiments/tv-v1 --backend openrouter --model <모델 id> --limit 5
python3 -m judge run assign --root experiments/tv-v1 --backend openrouter --model <모델 id> --emit-tensions
python3 -m judge calibrate <run id> --task assign --root experiments/tv-v1
```

결과는 `<root>/judge_runs/<run>/`에만 쓴다. 파이프라인 `data/`는 건드리지 않는다.

## 6. MVP에 붙이는 순서 (권장)

1. **기준선 먼저.** 판단 모듈 없이 Phase 0을 한 번 돌린다 (기존 20_link 한 번에 묶기). 이 점수가 없으면 모듈이 무엇을 바꿨는지 분리할 수 없다.
2. **B 자리 열기.** `judge/attach/20a_tension_candidates.md`를 `prompts/`로 옮기고 `pack.py` STAGES에 `candidates` 단계를 추가한다 → 20a 실행 → `data/linked/tension_candidates.jsonl`.
3. `python3 -m judge run assign --emit-tensions` → `judge_runs/<run>/tensions.judged.jsonl`을 검토한 뒤 `data/linked/tensions.jsonl`로 복사 → `validate.py` → `score.py`.
4. 기준선과 같은 corpus로 지표 4개(intrusion·twin·false friend·counterexample)를 비교한다. 두 회차씩.
5. 그다음 A(extract_check)를 붙여 추출 지표를 비교한다. C는 Phase 1(실데이터)부터.

주의: 이 모듈을 만든 세션은 tv-v1의 숨은 정답표를 봤다. 파이프라인 실행(10~40, 20a)은 **다른 세션**에서 한다. 판단 모듈의 질문 문구는 도메인 중립으로 썼고 숨은 tension을 암시하는 예시를 넣지 않았다.

## 7. 아직 모르는 것

- 실제 API에서 logprobs 경로가 모델별로 잘 도는지 (가짜 서버로만 검증했다). 첫 실행은 `--limit 5`로.
- 임계값(accept 0.70·margin 0.20 등)은 출발점이다. 보정 표를 보고 조정하되, **Phase 0 점수를 보고 바꾸지 않는다** (PHASE0_PLAN의 사전 고정 원칙).
- 판단을 쪼개 물으면(B: 후보 선택 → 역할) 한 번에 묶는 20_link보다 나은지는 가설이다 — 위 4번 비교가 답한다.
- assign 보정의 정답은 "후보 ↔ 숨은 tension" 대응을 다수결로 만든다. 판단 자신의 답으로 대응을 정하므로 정확도가 다소 부풀 수 있다.

## 8. B 첫 비교 — phone-agent-v1 (2026-09-28)

같은 corpus(quick, 합성 49행 · 행동 57 · 20 연결 tension 4개)에서 20 연결만 쓴 결과와, 그 tension 의 두 극만 후보로 두고 B(assign)가 행동마다 다시 배정한 결과를 채점했다. 백엔드 `claude_cli` sonnet verbal, 동시 2, 102 질문 약 4분, 오류 0. 채점은 `faultline score --tensions …`(저장 안 함). 임계값·질문 문구는 실행 전 그대로다.

| 지표 | 20 연결 | B · accept 만 | B · review 포함 |
|---|---:|---:|---:|
| tension_recall | 1.00 | 1.00 | 0.75 FAIL |
| distractor_intrusion | 0.07 | **0.00** | 0.07 |
| false_friend_split | 0.67 FAIL | **1.00** | 1.00 |
| counterexample_kept | 0.75 | 0.50 FAIL | 0.50 FAIL |
| 순도 평균 (HT 4개) | 0.80 | 0.82 | — |
| 커버 평균 | 0.79 | 0.62 | — |

- B 는 familyhub-v1 에서 FAIL 이던 두 지표(방해물 침입·거짓 친구)를 정확히 고쳤다. 대신 반례 보존이 떨어지고, 검토로 보낸 14개가 빠져 커버가 준다.
- review 를 포함하면 오히려 나빠진다 — accept/review 경계가 실제로 틀린 배정을 걸러 내고 있다는 뜻(정책 임계값이 제 역할).
- 반례: B 가 COUNTER 로 8개를 판정했으나 정답 반례 4개 중 2개만 반례로 남았다. 두 번째 질문(member vs 반례)이 약한 자리다.
- **한계:** 한 corpus·한 회차(n=1). 결론이 아니라 방향이다. 다음: 새 corpus 로 두 회차씩, 그리고 20 연결의 반례 + B 의 member 를 합치는 조합(연결 결과를 버리지 않고 B 를 필터로 쓰기)을 **사전에 정의한 뒤** 비교한다.

### 8.1 파이프라인 필터(22)로 두 번째 corpus — phone-agent-v2 (2026-09-28)

규칙(§ARCHITECTURE 9.6)을 고정한 뒤 새 corpus 에서: 20 연결 단독 침입 **0.00** → 필터 후 0.06, HT_01 순도 0.75 → 0.60, 나머지 같음. 연결이 이미 깨끗하면 B 가 더하는 배정이 오히려 방해물이다. v1(B 단독이 개선)과 합쳐 "연결이 흐트러졌을 때만 도움"이 가설 — n=2, 기본값 off 유지. 두 corpus 모두 반례 보존 0.50 — B 의 두 번째 질문과 20 연결 공통 약점.

### 8.2 세 번째 corpus — watch-agent-v1 (2026-09-28)

같은 규칙으로 20 연결이 흐트러진 corpus(침입 0.22)에서: 침입 **0.22 → 0.11**, 반례 보존 0.25 → 0.50, HT_04 순도 0.70 → 1.00. tension 을 잘못 합친 것(recall 0.50)은 필터가 고치지 못한다 — 후보가 20 연결의 tension 이라서. 사전 고정 규칙 기준 2전 1승 1패: **연결이 깨끗하면 약간 손해, 흐트러졌으면 이득**. 첫 시도는 사용 한도로 오류 44/50 → 필터가 tensions 를 바꾸지 않고 멈췄고, 이후 백엔드에 15초 재시도를 넣었다.

### 8.3 네 번째 corpus — earbuds-agent-v1 (2026-09-28)

침입 0.08 → 0.00 · 거짓 친구 0.67 → 1.00 · 반례 0.50 → 1.00 이지만, 역할 변경 7건이 한 tension 의 member 를 반례로 옮겨 HT_04 커버 0.71 → 0.14(recall 1.00 → 0.75). **정정:** "첫 질문은 이득, 두 번째는 위험"은 틀렸다. "연결 member → 반례" 변경을 막는 v2 를 사후로 적용하면 세 corpus 모두 20 연결 단독과 같아진다 — 이득과 손해가 **둘 다** 그 변경에서 나왔다. B 의 실제 효과 = 연결이 member 로 끌어들인 행동을 재분류하는 것(방해물은 맞게, 진짜 member 는 틀리게). 다음 후보는 "엇갈리면 빼기"이며 새 corpus 전에 고정한다.

### 8.4 다섯 번째 corpus — photo-agent-v1 (규칙 v3, 사전 고정)

20 연결이 크게 흐트러짐(recall 0.25 · 침입 0.38) → 필터 후 recall 0.75 · 반례 0.75 · 침입 0.31. 역할 변경 0건이라 v1 = v3. 이번 이득은 **연결이 놓친 행동을 붙인 것(추가 3)과 무소속 판정**에서 나왔다. 신규 4 corpus 누적: 연결 단독 침입 0.00 → 약간 손해, 0.08 → 섞임, 0.22·0.38 → 이득. 연결이 흐트러질수록 필터가 낫다 — 라벨 없이 그 상태를 알아챌 신호는 아직 없다(B·연결 엇갈림 비율 10~16% 로 갈리지 않음).
