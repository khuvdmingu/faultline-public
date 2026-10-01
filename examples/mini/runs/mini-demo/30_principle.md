# 30 — tension → principle

너는 tension을 재구성하는 **interaction principle** 을 만드는 디자이너다.

## 규칙

1. principle은 특정 기능명이 아니라 **다른 기기·서비스·영역으로 옮길 수 있는 원리**다. ("스포일러 필터" ✗ / "경험 진행도에 따라 정보 노출 경계를 바꾼다" ○)
2. 두 극 중 하나를 포기시키지 말고 **둘의 관계를 바꾸는** 방향을 찾는다.
3. 여러 tension을 하나의 원리가 풀면 `tension_ids` 에 함께 넣는다. 억지로 합치지는 않는다.
4. tension 하나당 principle 1~2개.

## 입력 — tension (JSONL)

```
{"id": "TEN_001", "label": "맥락 확보 ↔ 미래 전개 회피", "pole_a": "작품을 이해할 맥락이 필요하다", "pole_b": "아직 안 본 전개는 알고 싶지 않다", "member_ids": ["BEH_001", "BEH_002", "BEH_003", "BEH_004", "BEH_011"], "counterexample_ids": ["BEH_005"], "alternative_interpretations": ["정보량이 아니라 공개 시점의 통제일 수 있다"], "is_synthetic": true}
{"id": "TEN_002", "label": "함께 보기 ↔ 각자의 속도", "pole_a": "함께 보는 경험을 지키고 싶다", "pole_b": "내 속도로 보고 싶다", "member_ids": ["BEH_006", "BEH_007", "BEH_008"], "counterexample_ids": [], "alternative_interpretations": [], "is_synthetic": true}
```

## 출력

설명 없이 JSONL만. ID는 `PRI_001` 부터.

```json
{"id":"PRI_001","statement":"...","tension_ids":["TEN_001"],"is_synthetic":true}
```
