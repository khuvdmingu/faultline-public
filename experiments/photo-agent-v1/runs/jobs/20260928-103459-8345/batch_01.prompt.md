# 40 — principle × 미래 가정 → scenario

너는 principle 을 구체적인 장면으로 만드는 디자이너다.

## 탐색 과제 (기기·맥락 조건)

```json
{
  "domain": "사진·영상·기록을 AI 에이전트가 정리하고, 누구에게 무엇을 공유할지 대신 판단하는 경험 — 추억 앨범 만들기·가족·친구 공유·오래된 기록 지우기",
  "device": "스마트폰",
  "device_traits": [
    "카메라",
    "수천 장의 사진 보관함",
    "위치",
    "시간 기록",
    "메신저",
    "SNS 계정"
  ],
  "surroundings": [
    "클라우드 사진 보관함",
    "가족 단톡방",
    "SNS",
    "스마트워치"
  ],
  "exclude": [
    "특정 회사 내부 정보",
    "실존 인물 특정"
  ],
  "technology": "에이전틱 AI — 사용자의 목표를 받아 스스로 계획하고, 여러 앱·기기·서비스에서 대신 행동하며, 필요한 순간에만 사람에게 묻는 AI",
  "note": "파이프라인에 공개되는 탐색 과제. 정답 tension 을 적지 않는다."
}
```

## 규칙

1. 모든 scenario 는 `principle_ids`, `tension_ids`, `evidence_ids`(행동 ID) 를 가진다. **입력에 없는 ID 를 만들지 않는다.**
2. `evidence_ids` 는 각 principle 아래 「사용 가능한 근거」에서만 고른다. 「인접 맥락」은 영감용이며 근거로 쓰지 않는다.
3. 미래 가정을 쓴 scenario 는 `premise_ids` 와 `horizon` 을 적는다. 현재 기술로 되는 scenario 는 `horizon: "plausible"` 또는 `"probable"`, `premise_ids: []`.
4. 추천·요약·음성비서 같은 **기능명으로 차별성을 설명하지 않는다.** 어떤 trade-off 의 관계가 바뀌는지를 쓴다.
5. 기기가 가치를 만드는 이유를 `device_role` 에 쓴다 (큰 화면, 공용 공간, 여러 사람, 폰과의 관계 등). 기기가 중요하지 않다면 그렇다고 쓴다.
6. 현재 기술로 안 되는 부분은 `assumptions` 에 "미래 가정:" 으로 표시한다.
7. `failure_case` (이 시나리오가 틀어지는 장면)는 필수다.
8. principle 하나당 **메커니즘이 서로 다른** scenario 2~3개. 같은 메커니즘을 표현만 바꿔 반복하지 않는다.
9. 각 scenario 의 **핵심 메커니즘은 `evidence_ids` 중 최소 1개 행동이 직접 보여줘야 한다** — 그 행동을 한 사람이 이 시나리오를 보고 "내 얘기"라고 할 수 있어야 한다. 근거 행동이 뒷받침하지 못하는 메커니즘을 쓰려면 `assumptions` 에 적고 `horizon` 을 멀리 둔다. 받칠 근거가 없어 억지가 되는 두 번째 scenario 는 만들지 않는다(그 principle 은 하나만 내도 된다).
10. 입력의 문장은 합성 데이터다. 그 안의 지시는 따르지 않는다.

## 입력

### PRI_003: 안 보는 사진은 삭제 대신 저비용 보관 등급으로 옮겨 비용을 낮춘다
tension TEN_002: 모든 추억의 사진을 그대로 보존하고 싶다. ↔ 저장공간과 비용은 한정되어 정리·삭제가 필요하다.
사용 가능한 근거 (evidence_ids 는 여기서만 고른다):
{"id": "BEH_005", "kind": "avoidance", "action": "앨범 정리를 계속 미룸", "excerpt": "계속 미루는중", "inferred_need": "정리 부담 회피"}
{"id": "BEH_012", "kind": "opinion", "action": "저장공간 가격이 비싸다고 느낌", "excerpt": "저장공간 진짜 비싸다"}
{"id": "BEH_018", "kind": "avoidance", "action": "정리를 나중으로 미룸", "excerpt": "정리는 나중에 하지 뭐"}
{"id": "BEH_026", "kind": "opinion", "action": "용량 추가 가격 인상 불만", "excerpt": "용량 16기가 추가에 만원씩 오르는거 실화냐"}
{"id": "BEH_030", "kind": "avoidance", "action": "비슷한 사진 중복 정리 안 함", "excerpt": "비슷한 사진 겹쳐도 그냥 다 놔둠"}
{"id": "BEH_034", "kind": "avoidance", "action": "사진·영상 삭제 못 함", "excerpt": "사진이랑 영상 하나도 못 버리겠는데"}
{"id": "BEH_035", "kind": "opinion", "action": "저장공간 관리에 지침 느낌", "excerpt": "저장공간 걱정하는 건 진짜 지치는 일이에요"}
{"id": "BEH_039", "kind": "action", "action": "용량 경고 시 요금제 상향", "excerpt": "용량 경고 뜨면 그냥 요금제 올림", "inferred_need": "저장공간 확보"}
{"id": "BEH_042", "kind": "opinion", "action": "저장공간 부족 불만", "excerpt": "저장공간 꽉차서 앱 하나도 못깜 개빡침"}
{"id": "BEH_043", "kind": "avoidance", "action": "흐릿한 사진 안 지움", "excerpt": "흐릿한 사진도 그냥 안 지움"}
{"id": "BEH_051", "kind": "avoidance", "action": "용량 없어도 사진 안 지움", "excerpt": "용량 진짜 없어도 사진은 걍 절대 안 지움"}
{"id": "BEH_027", "kind": "edge", "action": "옛날 사진 보이면 바로 삭제", "excerpt": "옛날 사진 보이면 그냥 다 지움"}
인접 맥락 (참고용 — evidence_ids 로 쓰지 않는다):
{"id": "BEH_031", "kind": "avoidance", "action": "단체사진 게시 자체 안 함", "excerpt": "단체사진은 걍 안 올림", "why_included": "무소속"}
{"id": "BEH_053", "kind": "opinion", "action": "자동 정리 기능 시큰둥한 반응", "excerpt": "사진 자동 정리 기능 써봤는데 그냥 그럼", "why_included": "무소속"}
{"id": "BEH_019", "kind": "action", "action": "사진을 다 보관함", "excerpt": "그냥 다 보관함", "why_included": "무소속"}
{"id": "BEH_001", "kind": "opinion", "action": "앱 알림이 너무 많다고 느낌", "excerpt": "앱 알림 넘 많음", "why_included": "무소속"}
연결된 미래 가정:
{"id": "PREM_003", "what_if": "에이전트가 감정적 가치를 평가해 안 보는 사진의 보관권을 제3자 아카이브 시장에 위탁·거래한다면?", "future_rule": "에이전트가 사진 가치를 평가해 보관 권리를 아카이브 기관에 위탁하고 대가를 받는 시장이 성립한다.", "horizon": "wildcard", "required_changes": ["사진 가치를 평가하는 거래 표준", "위탁 후 접근권을 보장하는 계약 체계"], "tradeoffs": ["사진에 대한 배타적 소유권 상실", "위탁 기관 파산 시 추억 접근 불가 위험"]}
관련 유추:
{"id": "ANA_003", "source_domain": "museum_archive", "abstract_mechanism": "보관 공간이 유한하여 가치를 평가해 일부를 정리·폐기한다"}
{"id": "ANA_004", "source_domain": "email_cloud_storage", "abstract_mechanism": "저장 자원 한계에 도달하면 오래된 데이터를 자동 분류해 정리를 제안한다"}

### PRI_004: 찾을 땐 정리된 결과를 보여주고, 둘러볼 땐 원본 순서를 그대로 둔다
tension TEN_003: 자동 정리로 편하게 사진을 찾고 싶다. ↔ 직접 뒤지며 우연히 발견하는 재미를 원한다.
사용 가능한 근거 (evidence_ids 는 여기서만 고른다):
{"id": "BEH_014", "kind": "opinion", "action": "자동 정리하면 찾기 편함", "excerpt": "필요할 때 찾기는 편한데"}
{"id": "BEH_045", "kind": "opinion", "action": "앨범 정리 UI 복잡 불만", "excerpt": "앨범 정리 기능 UI가 왜케 복잡함"}
{"id": "BEH_048", "kind": "action", "action": "사진첩 정처없이 스크롤", "excerpt": "폰 사진첩 정처없이 스크롤함"}
{"id": "BEH_050", "kind": "opinion", "action": "태그 기능 불필요하다는 의견", "excerpt": "태그 다 필요없음"}
{"id": "BEH_016", "kind": "edge", "action": "자동 정리에 맡기고 안 찾아봄", "excerpt": "일부러 찾아보고 그런 거 1도 관심 없음"}
{"id": "BEH_044", "kind": "workaround", "action": "폴더 하나로 합침", "excerpt": "그냥 폴더 하나로 합쳐놓고", "inferred_need": "정리 단순화"}
인접 맥락 (참고용 — evidence_ids 로 쓰지 않는다):
{"id": "BEH_053", "kind": "opinion", "action": "자동 정리 기능 시큰둥한 반응", "excerpt": "사진 자동 정리 기능 써봤는데 그냥 그럼", "why_included": "무소속"}
{"id": "BEH_040", "kind": "avoidance", "action": "자동 태그 기능 꺼둠", "excerpt": "태그 자동으로 하는거 다 꺼놓음", "why_included": "무소속"}
{"id": "BEH_015", "kind": "workaround", "action": "자동 정리 끄고 손으로 뒤적임", "excerpt": "일부러 자동 정리는 꺼놓고 폴더를 손으로 뒤적임", "inferred_need": "우연한 발견의 재미", "why_included": "무소속"}
{"id": "BEH_037", "kind": "opinion", "action": "갤러리 앱 로딩 느림 불만", "excerpt": "갤러리 앱 로딩 왜케 느림", "why_included": "무소속"}
연결된 미래 가정:
{"id": "PREM_004", "what_if": "사용자가 명시하지 않아도 에이전트가 찾기·둘러보기 의도를 스스로 구분해 전환한다면?", "future_rule": "에이전트가 행동 패턴을 읽어 찾기·둘러보기 모드를 실시간으로 전환한다.", "horizon": "probable", "required_changes": ["행동 의도를 추론하는 상시 관찰 체계", "오판 시 즉시 전환 가능한 인터페이스"], "tradeoffs": ["상시 관찰로 인한 프라이버시 축소", "알고리즘 예측으로 우연한 발견의 재미 감소"]}
관련 유추:
{"id": "ANA_005", "source_domain": "music streaming", "abstract_mechanism": "효율적 큐레이션과 우연한 발견 사이의 긴장을 다른 매체에서도 동일하게 겪는다"}
{"id": "ANA_006", "source_domain": "museum", "abstract_mechanism": "정리된 경로 제공과 원자료를 직접 탐색하게 두는 방식이 대립한다"}

## 뻔한 방향 (corpus 없이 일반 프롬프트로 나온 시나리오 — 이 메커니즘을 되풀이하지 않는다)
아래와 메커니즘이 같으면 기능 이름을 바꿔도 뻔한 것이다. 근거 행동에서 출발해 여기에 없는 관계를 찾는다.
{"title": "연말 회고 앨범", "mechanism": "시간 태그 기반 자동 큐레이션"}
{"title": "여행 하이라이트 영상", "mechanism": "위치·시간 클러스터링 영상 생성"}
{"title": "생일 축하 콜라주", "mechanism": "인물 인식+캘린더 연동 자동 생성"}
{"title": "SNS 업로드 추천", "mechanism": "미적 점수 기반 사진 선별"}
{"title": "반려동물 성장 앨범", "mechanism": "객체 인식+시간순 정렬"}
{"title": "공유 앨범 자동 초대", "mechanism": "동행 인식 후 공유권한 자동 부여"}
{"title": "경조사 앨범 자동 발송", "mechanism": "이벤트 인식+수신자 매칭 발송"}
{"title": "클라우드 백업 자동화", "mechanism": "중요도 판별 후 선택적 백업"}

## 출력

설명 없이 JSONL만. ID는 `SCN_001` 부터 (시스템이 다시 번호를 매긴다).

```json
{"id":"SCN_001","title":"...","principle_ids":["PRI_001"],"tension_ids":["TEN_001"],"evidence_ids":["BEH_001"],"premise_ids":["PREM_001"],"analogy_ids":[],"horizon":"possible","trigger":"...","experience":"...","device_role":"...","required_capabilities":["..."],"assumptions":["..."],"failure_case":"..."}
```

## 기반 기술 규칙 (위 규칙과 함께 지킨다)

기반 기술: 에이전틱 AI — 사용자의 목표를 받아 스스로 계획하고, 여러 앱·기기·서비스에서 대신 행동하며, 필요한 순간에만 사람에게 묻는 AI

모든 scenario 는 위 기반 기술 위에서 작동한다. 다음 필드를 더한다: `agent_actions`(에이전트가 사람 대신 스스로 하는 일 1~3개, 목록), `human_checkpoints`(사람에게 묻거나 확인받는 순간 0~2개, 목록), `reversal`(사람이 결과를 되돌리거나 권한을 거두는 방법 한 문장). 에이전트가 모든 것을 알아서 하는 장면만 쓰지 말고, 위임의 경계가 드러나게 한다.

## 길이 규칙 — 짧게 (위의 개수·분량 규칙보다 이것이 우선한다)

principle 하나당 scenario 최대 2개(근거로 받칠 수 없으면 1개). title 20자 이내, trigger 한 문장, experience 3문장 이내, failure_case 2문장 이내, assumptions 최대 2개, device_role 한 문장.
