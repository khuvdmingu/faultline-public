# 데이터 형식

모든 엔티티는 JSONL(한 줄에 레코드 하나)이다. 모르는 값은 `null`. 계약의 코드 원본은 `engine/schema.py` 의 `SPECS` 이고, 이 문서는 그 설명이다. 저장 위치는 `engine/store.py` 의 `FILES`.

## 공통 규칙

- ID 는 접두어 + 세 자리 번호. 파이프라인 산출물의 ID 는 **시스템이 다시 매긴다** — 모델이 준 번호는 믿지 않는다.
- `is_synthetic` 은 시스템이 부여한다. 합성 실험의 모든 파생물은 `true`.
- 참조 필드의 ID 는 반드시 존재해야 한다. 끊기면 저장이 보류된다 (`needs_review`).

| 접두어 | 엔티티 | 파일 | 만드는 스테이지 |
|---|---|---|---|
| `HT_` | 정답 tension | `hidden/ground_truth.json` | 00 (사람) |
| `RAW_` | 원문 | `hidden/corpus_labeled.jsonl` → `data/raw/raw.jsonl` | 01 → 02 |
| `BAS_` | 기준선 시나리오 | `data/baseline/baseline.jsonl` | 05 |
| `BEH_` | 행동 | `data/extracted/behaviors.jsonl` | 10 |
| `TEN_` | tension | `data/linked/tensions.jsonl` | 20 |
| `ANA_` | 유추 | `data/explore/analogies.jsonl` | 25 |
| `PKG_` | 검색 패키지 | `data/explore/packages.jsonl` | 27 |
| `PRI_` | principle | `data/linked/principles.jsonl` | 30 |
| `PREM_` | 미래 가정 | `data/explore/premises.jsonl` | 35 |
| `SCN_` | 시나리오 | `data/scenarios/scenarios.jsonl` | 40 |
| `EVAL_` | 평가 | `data/evaluate/evaluations.jsonl` | 50 |
| `FAM_` | family | `data/evaluate/families.jsonl` | 60 |
| `DEC_` | 검토 결정 | `review/decisions.jsonl` | 80 (사람) |

## 평가자 영역 (hidden/)

### ground_truth.json

```json
{"domain": "...", "tensions": [{"id": "HT_01", "pole_a": "...", "pole_b": "...", "principle": "...",
  "familiarity": "familiar|unfamiliar", "behavior_seeds": ["..."]}], "distractor_themes": ["..."]}
```

### corpus_labeled.jsonl

```json
{"id": "RAW_001", "raw_text": "댓글 안 봄ㅋ", "source_type": "synthetic_comment", "style": "short_no_motive",
 "label": {"tension": "HT_01", "role": "member", "twin_of": null, "looks_like": null,
           "expected_kind": "avoidance", "context_absent": ["device", "social"], "injection_token": null}}
```

role·style·라벨 필드의 뜻은 `DATA_GENERATION_POLICY.md` §3~§5.

## 파이프라인 영역 (data/)

### brief.json (실험 루트) — 파이프라인이 보는 탐색 과제

```json
{"domain": "...", "device": "AI TV", "device_traits": ["..."], "surroundings": ["..."], "exclude": ["..."]}
```

정답 tension 을 적지 않는다.

### raw

```json
{"id": "RAW_001", "raw_text": "...", "source_type": "synthetic_comment", "is_synthetic": true}
```

### baseline

```json
{"id": "BAS_001", "title": "...", "experience": "...", "mechanism": "...", "condition": "A"}
```

### behaviors

```json
{"id": "BEH_001", "source_id": "RAW_001", "kind": "avoidance", "action": "댓글을 읽지 않는다",
 "source_excerpt": "댓글 안 봄", "context": {"device": null, "social": null, "platform": null, "phase": null},
 "inferred_need": null, "inference_status": "none"}
```

- `kind`: `action` · `avoidance` · `workaround` · `norm` · `edge` · `opinion` · `noise`
- `source_excerpt` 는 원문의 연속 부분 문자열 (공백 차이만 허용)
- `inference_status`: `explicit`(원문에 동기 명시) · `inferred` · `none`

### tensions

```json
{"id": "TEN_001", "label": "...", "pole_a": "...", "pole_b": "...", "member_ids": ["BEH_001"],
 "counterexample_ids": ["BEH_009"], "alternative_interpretations": ["..."]}
```

member 와 counterexample 에 같은 행동이 동시에 있으면 오류. member 3개 미만이면 경고.

### analogies

```json
{"id": "ANA_001", "source_domain": "games", "source_pattern": "Fog of War",
 "abstract_mechanism": "...", "target_tension_ids": ["TEN_001"], "mapping": {"원래 요소": "대응 요소"},
 "transfer_limitations": ["..."], "distance": "adjacent|distant"}
```

### packages (스크립트 생성)

```json
{"id": "PKG_001", "tension_id": "TEN_001", "relevant_ids": ["BEH_..."], "adjacent_ids": ["BEH_..."],
 "distant_analogy_ids": ["ANA_..."], "counterexample_ids": ["BEH_..."], "reasons": {"BEH_007": "phase=during 공유 · TEN_002 소속"},
 "shortfall": {"relevant": 0, "adjacent": 0, "distant": 1}, "retrieval_version": "retrieval_v01", "ratio": {"relevant": 0.6, "adjacent": 0.2, "distant": 0.2}}
```

### principles

```json
{"id": "PRI_001", "statement": "...", "tension_ids": ["TEN_001"], "package_ids": ["PKG_001"], "analogy_ids": ["ANA_002"], "rationale": "..."}
```

### premises

```json
{"id": "PREM_001", "what_if": "...", "changed_assumption": "...", "future_rule": "...",
 "horizon": "probable|plausible|possible|preferable|wildcard", "origin_tension_ids": ["TEN_001"],
 "principle_ids": ["PRI_001"], "analogy_ids": [], "required_changes": ["..."], "beneficiaries": ["..."], "tradeoffs": ["..."]}
```

### scenarios

```json
{"id": "SCN_001", "title": "...", "principle_ids": ["PRI_001"], "tension_ids": ["TEN_001"], "evidence_ids": ["BEH_001"],
 "premise_ids": ["PREM_001"], "analogy_ids": [], "horizon": "possible", "trigger": "...", "experience": "...",
 "device_role": "...", "required_capabilities": ["..."], "assumptions": ["..."], "failure_case": "..."}
```

`evidence_ids` 는 비어 있으면 오류, 연결된 tension 밖에서 왔으면 경고.

### evaluations

```json
{"id": "EVAL_001", "scenario_id": "SCN_001", "rubric_version": "rubric_v01",
 "scores": {"behavioral_grounding": 4, "tension_strength": 4, "novelty": 3, "cliche_level": 2,
            "plausibility": 4, "device_fit": 3, "ai_necessity": null},
 "similar_baseline_ids": [], "insufficient_information": ["ai_necessity"], "rationale": {"novelty": "..."},
 "review_route": "develop_candidate|question_candidate|improve_candidate|low_priority|human_review"}
```

점수는 1~5 또는 `null`. `null` 은 0점이 아니라 판정 불가. `cliche_level` 은 높을수록 뻔하다.

### families

```json
{"id": "FAM_001", "label": "...", "mechanism": "...", "scenario_ids": ["SCN_001"], "principle_ids": ["PRI_001"], "distinct_from": "..."}
```

한 시나리오는 정확히 한 family 에 속한다 (두 곳이면 오류, 없으면 경고).

## 인간 영역 (review/)

### decisions

```json
{"id": "DEC_001", "scenario_id": "SCN_001", "decision": "develop|hold|reject", "reason": "...",
 "blind": true, "saw_evidence": false, "reviewer": "user", "at": "2026-09-27T18:00:00"}
```

추가만 한다. 최신 결정이 유효하다. 이유는 필수.

## 실행 기록 (runs/)

| 경로 | 내용 |
|---|---|
| `runs/jobs/<id>/job.json` | 작업 상태·배치·결과·로그 |
| `runs/jobs/<id>/batch_NN.prompt.md` · `.out.txt` | 배치별 프롬프트와 원본 모델 출력 |
| `runs/jobs/<id>/rejected.jsonl` | 검증 오류로 보류된 결과 |
| `runs/provenance.jsonl` | 저장될 때마다 한 줄 (키·행 수·작업·모델·실행기) |
| `runs/qa/corpus_qa.json` | 합성 corpus 품질 검사 |
| `runs/score/phase0.json` | 최근 Phase 0 채점 (+ 시각별 사본) |
