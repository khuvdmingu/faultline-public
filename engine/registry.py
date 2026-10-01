"""스테이지 등록부 — 시스템 구조의 단일 출처.

웹의 구조도·파이프라인 화면, 프롬프트 조립, 정보 차단선 검사가 모두 이 표를 읽는다.
스테이지를 추가·변경할 때는 여기만 고치면 된다 (docs/ARCHITECTURE.md §3).

필드
  id        스테이지 키 (API·작업 기록에 쓰임)
  num       표시 번호
  lane      evaluator | evidence | explore | evaluate | human
  pos       구조도 좌표 (행, 열)
  kind      human | llm | det(결정적 스크립트)
  reads     입력 키 (engine.store.FILES)
  writes    출력 키 (det 스테이지는 여러 개일 수 있다)
  hidden    True 면 hidden/ 을 읽어도 된다 (생성·분리·채점만)
  model     llm 스테이지 기본 모델 (claude CLI 별칭)
  prompt    prompts/ 템플릿 파일
  batch     (배치 기준 키, 배치 크기) — 입력이 크면 나눠 실행하고 출력 ID 를 재번호한다
  prefix    출력 ID 접두어
  after     구조도 화살표 (주 흐름 선행 스테이지)
  optional  True 면 건너뛰어도 뒤 스테이지가 동작한다
"""

LANES = [
    ("evaluator", "평가자 영역 · hidden/", "정답을 심고, 데이터를 만들고, 채점한다. 파이프라인은 이 영역을 볼 수 없다."),
    ("evidence", "증거 층", "원문에서 행동을 보수적으로 뽑고, 행동 밑의 tension 을 찾는다."),
    ("explore", "탐색 층", "다른 영역의 원리를 끌어와 principle·미래 가정·시나리오로 넓힌다."),
    ("evaluate", "평가·지도화 층", "시나리오를 다차원으로 특성화하고 메커니즘 family 로 묶는다."),
    ("human", "인간 층", "발전·보류·거절을 결정하고 이유를 남긴다."),
]

STAGES = [
    dict(id="ground_truth", num="00", name="정답표", lane="evaluator", pos=(0, 0), kind="llm",
         reads=[], writes=["ground_truth"], hidden=True, model="opus", prompt="00_ground_truth.md",
         desc="brief 에서 tension 6개(익숙 3 · 낯섦 3)와 principle 을 심는다. 사람이 직접 써 두면 자동 실행은 이 단계를 건너뛴다."),
    dict(id="generate", num="01", name="합성 생성", lane="evaluator", pos=(0, 1), kind="llm",
         reads=["ground_truth"], writes=["corpus_labeled"], hidden=True, model="sonnet",
         prompt="00_generate_corpus.md", after=["ground_truth"],
         desc="정답표에서 원문을 거꾸로 만든다. 함정 8종을 섞고 문체 분포를 강제한다. 파이프라인과 다른 모델."),
    dict(id="split", num="02", name="라벨 분리 · 품질 검사", lane="evaluator", pos=(0, 2), kind="det",
         reads=["corpus_labeled"], writes=["raw", "labels"], hidden=True, after=["generate"],
         desc="라벨을 떼어 raw 만 파이프라인으로 내려보낸다. 데이터 생성 정책의 자동 검사(QA)를 함께 돈다."),
    dict(id="baseline", num="05", name="기준선 · 뻔함 공간", lane="evaluate", pos=(3, 1), kind="llm",
         reads=["brief"], writes=["baseline"], model="sonnet", prompt="05_baseline.md", prefix="BAS_",
         optional=True,
         desc="corpus 없이 일반 프롬프트로 만든 시나리오. judge 의 cliché 비교 기준이자 A/B/C 실험의 조건 A."),
    dict(id="extract", num="10", name="행동 추출", lane="evidence", pos=(1, 2), kind="llm",
         reads=["raw"], writes=["behaviors"], model="sonnet", prompt="10_extract.md", prefix="BEH_",
         batch=("raw", 30), after=["split"],
         desc="원문 → 행동 단위. 원문에 없는 맥락을 채우지 않고, 근거 구절을 그대로 인용한다."),
    dict(id="link", num="20", name="tension 연결", lane="evidence", pos=(1, 3), kind="llm",
         reads=["behaviors"], writes=["tensions"], model="opus", prompt="20_link.md", prefix="TEN_",
         after=["extract"],
         desc="행동 밑의 두 극 욕구 충돌을 찾는다. 단어가 아니라 욕구로 묶고, 무소속은 억지로 넣지 않는다."),
    dict(id="assign", num="22", name="판단 필터 (B)", lane="evidence", pos=(1, 4), kind="det",
         reads=["raw", "behaviors", "tensions"], writes=["tensions_link", "tensions"], after=["link"], optional=True,
         desc="(선택 · config.assign) 판단 모듈 B 가 행동마다 tension 을 다시 묻는다(무소속 포함). 정해 둔 규칙으로 20 연결과 합친다 — engine/assign.py."),
    dict(id="analogy", num="25", name="먼 영역 유추", lane="explore", pos=(2, 3), kind="llm",
         reads=["tensions", "brief"], writes=["analogies"], model="sonnet", prompt="25_analogy.md",
         prefix="ANA_", batch=("tensions", 2), after=["link"],
         desc="같은 관계 구조를 가진 다른 산업·문화의 메커니즘. 대응 관계와 전이 한계를 함께 쓴다."),
    dict(id="package", num="27", name="검색 패키지", lane="explore", pos=(2, 4), kind="det",
         reads=["tensions", "behaviors", "analogies"], writes=["packages"], prefix="PKG_",
         after=["analogy"],
         desc="tension 별 작업 문맥. relevant 60 · adjacent 20 · distant 20 (retrieval_v01 · 출발점 가설)."),
    dict(id="principle", num="30", name="principle", lane="explore", pos=(2, 5), kind="llm",
         reads=["packages", "tensions", "behaviors", "analogies"], writes=["principles"], model="opus",
         prompt="30_principle.md", prefix="PRI_", batch=("packages", 3), after=["package"],
         desc="tension 을 재구성하는, 다른 기기·영역으로 옮길 수 있는 경험 원리."),
    dict(id="premise", num="35", name="미래 가정 · What-if", lane="explore", pos=(2, 6), kind="llm",
         reads=["principles", "tensions", "analogies"], writes=["premises"], model="opus",
         prompt="35_premise.md", prefix="PREM_", after=["principle"],
         desc="바뀐 가정·미래 규칙·필요 조건·수혜자·트레이드오프. 현재 기능 개선에 머물지 않게 한다."),
    dict(id="scenario", num="40", name="scenario", lane="explore", pos=(2, 7), kind="llm",
         reads=["principles", "premises", "packages", "tensions", "behaviors", "analogies", "brief", "baseline"],
         writes=["scenarios"], model="opus", prompt="40_scenario.md", prefix="SCN_",
         batch=("principles", 3), after=["premise"],
         desc="principle × 미래 가정 × 기기 조건 → 구체 장면. 근거 ID·가정·실패 장면 필수."),
    dict(id="judge", num="50", name="다차원 평가", lane="evaluate", pos=(3, 7), kind="llm",
         reads=["scenarios", "behaviors", "tensions", "premises", "baseline"], writes=["evaluations"],
         model="sonnet", prompt="50_judge.md", prefix="EVAL_", batch=("scenarios", 8),
         after=["scenario", "baseline"],
         desc="근거·tension·새로움·뻔함·현실성·기기 적합·AI 필요성. 총점 없음, 판정 불가는 null. 생성과 다른 모델."),
    dict(id="family", num="60", name="family 지도화", lane="evaluate", pos=(3, 8), kind="llm",
         reads=["scenarios", "principles"], writes=["families"], model="sonnet", prompt="60_family.md",
         prefix="FAM_", after=["judge"],
         desc="제목이 아니라 메커니즘으로 시나리오를 묶는다. 같은 좋은 아이디어의 반복을 가려낸다."),
    dict(id="polish", num="70", name="윤문 · 사람 글로", lane="human", pos=(4, 6), kind="llm",
         reads=["scenarios", "principles", "premises", "shortlist"], writes=["polished"], model="opus",
         prompt="70_polish.md", prefix="POL_", batch=("targets", 8), after=["shortlist"],
         desc="im-not-ai 규칙으로 AI 티를 덜어낸다. 의미·수치·서법은 그대로. 원본은 두고 윤문본만 따로, 코드 게이트가 과윤문을 막는다."),
    dict(id="shortlist", num="75", name="후보 추리기", lane="human", pos=(4, 7), kind="det",
         reads=["scenarios", "evaluations", "families", "behaviors"], writes=["shortlist"], after=["family"],
         desc="평가 점수로 걸러 family 마다 가장 나은 하나씩, 상위 N개를 이유와 함께 고른다. 사람 검토 없이도 결과가 나오게 하는 자동 단계."),
    dict(id="review", num="80", name="인간 검토", lane="human", pos=(4, 8), kind="human",
         reads=["scenarios", "evaluations", "families", "shortlist"], writes=["decisions"], after=["shortlist"],
         desc="(선택) 블라인드로 먼저 읽고 발전·보류·거절. 근거는 두 번째로 본다. 이유를 반드시 남긴다."),
    dict(id="score", num="90", name="Phase 0 채점", lane="evaluator", pos=(0, 8), kind="det",
         reads=["labels", "raw", "behaviors", "tensions", "principles", "scenarios"], writes=[],
         hidden=True, after=["split", "link"],
         desc="정답 라벨과 대조. 추출 4 · 연결 5 · 추적 1 지표. 평가자 전용."),
]

BY_ID = {s["id"]: s for s in STAGES}

HIDDEN_KEYS = {"ground_truth", "corpus_labeled", "labels"}


def check_barrier(stages=None):
    """정보 차단선의 정적 검사 — hidden=False 인 스테이지가 hidden 키를 입력으로 선언하면 오류.
    모듈을 불러올 때 한 번 실행된다. 스테이지를 잘못 추가하면 서버가 뜨지 않는다."""
    bad = [(s["id"], k) for s in (stages or STAGES) if not s.get("hidden")
           for k in s["reads"] if k in HIDDEN_KEYS]
    if bad:
        raise RuntimeError("정보 차단선 위반 선언: {}".format(bad))


check_barrier()


def get(stage_id):
    if stage_id not in BY_ID:
        raise KeyError("알 수 없는 스테이지: {}".format(stage_id))
    return BY_ID[stage_id]


def public():
    """API 용 직렬화."""
    out = []
    for s in STAGES:
        d = {k: v for k, v in s.items()}
        d["pos"] = list(s["pos"])
        d.setdefault("after", [])
        d.setdefault("optional", False)
        d.setdefault("hidden", False)
        out.append(d)
    return {"lanes": [{"id": a, "name": b, "desc": c} for a, b, c in LANES], "stages": out}
