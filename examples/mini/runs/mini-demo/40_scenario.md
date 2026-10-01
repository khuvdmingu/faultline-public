# 40 — principle → scenario

너는 principle을 구체적인 장면으로 만드는 디자이너다. 기기 중심은 AI TV이지만 주변 서비스(폰·SNS·검색·커뮤니티)도 포함할 수 있다.

## 규칙

1. 모든 scenario는 `principle_ids`, `tension_ids`, `evidence_ids`(행동 ID) 를 반드시 가진다. **입력에 없는 ID를 만들지 않는다.**
2. `evidence_ids` 는 그 tension의 `member_ids` 에서 고른다. 근거가 약하면 `assumptions` 에 적는다.
3. 추천·요약·음성비서 같은 기능명으로 차별성을 설명하지 않는다. 어떤 trade-off의 관계가 바뀌는지를 쓴다.
4. 현재 기술로 안 되는 부분은 `assumptions` 에 "미래 가정:"으로 표시한다.
5. 반드시 `failure_case`(이 시나리오가 틀어지는 장면)를 쓴다.
6. principle 하나당 서로 **메커니즘이 다른** scenario 2~3개.

## 입력

principles, tensions (member_ids 포함), behaviors 를 함께 받는다.

```
## principles
{"id": "PRI_001", "statement": "경험 진행도에 맞춰 정보 노출 경계를 조절한다", "tension_ids": ["TEN_001"], "is_synthetic": true}
{"id": "PRI_002", "statement": "공동 시청의 진행도를 분기하고 다시 합류할 수 있게 한다", "tension_ids": ["TEN_002"], "is_synthetic": true}

## tensions
{"id": "TEN_001", "label": "맥락 확보 ↔ 미래 전개 회피", "pole_a": "작품을 이해할 맥락이 필요하다", "pole_b": "아직 안 본 전개는 알고 싶지 않다", "member_ids": ["BEH_001", "BEH_002", "BEH_003", "BEH_004", "BEH_011"], "counterexample_ids": ["BEH_005"], "alternative_interpretations": ["정보량이 아니라 공개 시점의 통제일 수 있다"], "is_synthetic": true}
{"id": "TEN_002", "label": "함께 보기 ↔ 각자의 속도", "pole_a": "함께 보는 경험을 지키고 싶다", "pole_b": "내 속도로 보고 싶다", "member_ids": ["BEH_006", "BEH_007", "BEH_008"], "counterexample_ids": [], "alternative_interpretations": [], "is_synthetic": true}

## behaviors
{"id": "BEH_001", "source_id": "RAW_001", "kind": "avoidance", "action": "댓글을 읽지 않는다", "source_excerpt": "댓글 안 봄", "context": {"device": null, "social": null, "platform": null, "phase": null}, "inferred_need": null, "inference_status": "none", "is_synthetic": true}
{"id": "BEH_002", "source_id": "RAW_002", "kind": "workaround", "action": "전편 대신 요약 영상으로 기억을 보충한다", "source_excerpt": "유튜브 요약 보고 들어감", "context": {"device": "TV", "social": null, "platform": "YouTube", "phase": "before"}, "inferred_need": "감상 전 맥락 확보", "inference_status": "inferred", "is_synthetic": true}
{"id": "BEH_003", "source_id": "RAW_003", "kind": "avoidance", "action": "결말 노출을 피하려 SNS를 끊는다", "source_excerpt": "이번주는 인스타 끊음", "context": {"device": null, "social": null, "platform": "Instagram", "phase": "during"}, "inferred_need": "결말을 모르고 보고 싶다", "inference_status": "explicit", "is_synthetic": true}
{"id": "BEH_004", "source_id": "RAW_004", "kind": "norm", "action": "진행도를 먼저 밝히고 대화한다", "source_excerpt": "몇화까지 봤는지 먼저 쓰고", "context": {"device": null, "social": "online_group", "platform": null, "phase": "during"}, "inferred_need": "서로의 진행도 존중", "inference_status": "inferred", "is_synthetic": true}
{"id": "BEH_005", "source_id": "RAW_005", "kind": "edge", "action": "결말을 먼저 찾아본 뒤 감상한다", "source_excerpt": "결말부터 나무위키로 찾아보고", "context": {"device": null, "social": null, "platform": "namuwiki", "phase": "before"}, "inferred_need": "불확실성 회피", "inference_status": "inferred", "is_synthetic": true}
{"id": "BEH_006", "source_id": "RAW_006", "kind": "action", "action": "파트너를 기다리며 다음 화를 보류한다", "source_excerpt": "남친 기다리느라 다음화 못틀고", "context": {"device": null, "social": "partner", "platform": null, "phase": "during"}, "inferred_need": null, "inference_status": "none", "is_synthetic": true}
{"id": "BEH_007", "source_id": "RAW_007", "kind": "workaround", "action": "먼저 본 사실을 숨기고 함께 본다", "source_excerpt": "같이 볼때 처음 보는 척함", "context": {"device": null, "social": "partner", "platform": null, "phase": "during"}, "inferred_need": "함께 보는 경험 유지", "inference_status": "inferred", "is_synthetic": true}
{"id": "BEH_008", "source_id": "RAW_008", "kind": "norm", "action": "함께 볼 작품을 따로 지정한다", "source_excerpt": "애인이랑 보는 드라마는 따로 정해둠", "context": {"device": null, "social": "partner", "platform": null, "phase": "before"}, "inferred_need": null, "inference_status": "none", "is_synthetic": true}
{"id": "BEH_009", "source_id": "RAW_009", "kind": "action", "action": "배우자를 기다리며 시청을 참는다", "source_excerpt": "와이프 올때까지 참는 중", "context": {"device": null, "social": "spouse", "platform": null, "phase": "during"}, "inferred_need": null, "inference_status": "none", "is_synthetic": true}
{"id": "BEH_010", "source_id": "RAW_010", "kind": "opinion", "action": "화질에 불만을 표한다", "source_excerpt": "화질 왜이럼", "context": {"device": "TV", "social": null, "platform": null, "phase": null}, "inferred_need": null, "inference_status": "none", "is_synthetic": true}
{"id": "BEH_011", "source_id": "RAW_011", "kind": "opinion", "action": "구독료 인상에 불만을 표한다", "source_excerpt": "구독료 올랐네", "context": {"device": null, "social": null, "platform": null, "phase": null}, "inferred_need": null, "inference_status": "none", "is_synthetic": true}
{"id": "BEH_012", "source_id": "RAW_012", "kind": "action", "action": "리모컨을 잃어버린다", "source_excerpt": "리모컨 또 잃어버림", "context": {"device": "TV", "social": null, "platform": null, "phase": null}, "inferred_need": null, "inference_status": "none", "is_synthetic": true}
```

## 출력

설명 없이 JSONL만. ID는 `SCN_001` 부터.

```json
{"id":"SCN_001","title":"...","principle_ids":["PRI_001"],"tension_ids":["TEN_001"],"evidence_ids":["BEH_001"],"trigger":"...","experience":"...","assumptions":["..."],"failure_case":"...","is_synthetic":true}
```
