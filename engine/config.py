"""실험 크기·속도 설정 — 실험 폴더의 config.json 한 파일.

size      빠르게(quick) · 표준(standard). 정답 tension 수, 합성 원문 수, 기준선 수, 모델을 함께 정한다.
parallel  한 스테이지 안에서 동시에 돌릴 배치 수(claude CLI 프로세스 수). 1 이면 예전처럼 하나씩.

시간을 좌우하는 것은 (호출 수 ÷ 동시 실행 수) × 호출 길이다. 호출 길이는 출력 행 수와 모델(opus 가 느리다)이 정한다.
quick 은 세 가지를 모두 줄인다. 대신 채점 표본이 작아 지표 하나하나의 흔들림이 커진다 — 판단용 실험은 standard.
config.json 에는 정답이 없다(크기만) — 파이프라인이 봐도 된다.
"""
import json
import os

SIZES = {
    "quick": dict(label="빠르게", desc="tension 4 · 원문 약 45 · 기준선 15 · 전 단계 sonnet",
                  tensions=4, unfamiliar=2, members=(5, 6), distractor=(8, 10), twin=3, false_friend=3,
                  trap_negation=(2, 2), trap_no_context=(2, 2), trap_injection=2, baseline=15,
                  model_map={"opus": "sonnet"}, call_timeout=300),
    "standard": dict(label="표준", desc="tension 6 · 원문 약 100 · 기준선 30 · 연결·원리·시나리오 opus",
                     tensions=6, unfamiliar=3, members=(8, 12), distractor=(15, 20), twin=5, false_friend=5,
                     trap_negation=(3, 4), trap_no_context=(3, 4), trap_injection=3, baseline=30,
                     model_map={}, call_timeout=600),
}
DEFAULT = {"size": "standard", "parallel": 3, "brevity": "normal", "profile": "full",
           "polish": "shortlist", "family": "on", "assign": "off", "assign_rule": "v1", "baseline_split": "off"}
POLISH = {"shortlist": "자동 후보만 윤문 (빠름)", "all": "시나리오·principle·미래 가정 전부", "off": "윤문 안 함"}
FAMILY = {"on": "family 지도화 실행", "off": "건너뜀 — 후보 추리기는 tension 다양성으로 대신한다"}
ASSIGN = {"off": "20 연결 결과를 그대로", "on": "22 판단 필터 — 판단 모듈 B 로 배정을 다시 거른다 (claude CLI, quick 기준 약 4분)"}
ASSIGN_RULE = {"v1": "v1 — B accept 우선 (기본·사전 고정)", "v2": "v2 — 연결 member 유지 (비교용, 채택 안 함)",
               "v3": "v3 — 엇갈리면 빼기 (같은 tension 에서 member→반례)"}
BASELINE_SPLIT = {"off": "그대로 — 기준선 전체로 평가, 시나리오는 기준선을 보지 않음 (예전 방식)",
                  "held": "보관분 평가 — 평가는 기준선의 절반(보관분)으로만, 시나리오는 기준선을 보지 않음 (비교 대조군)",
                  "avoid": "뻔한 방향 피하기 — 시나리오가 나머지 절반을 「뻔한 방향」으로 보고 피한다 · 평가는 보관분으로만"}
BREVITY = {"normal": "보통", "short": "짧게 — 문장 수·글자 수를 줄여 출력과 시간을 줄인다"}
PROFILES = {"full": "전 과정 — 정답표부터 후보 추리기·채점까지",
            "check": "검증 전용 — 정답표·생성·추출·연결·채점만 (연결 로직 반복 실험용)"}
PARALLEL_MAX = 6
GEN_GROUP = 2                     # 01 생성 한 배치가 맡는 tension 수


def get(root):
    c = dict(DEFAULT)
    fp = os.path.join(root, "config.json")
    if os.path.exists(fp):
        with open(fp, encoding="utf-8") as f:
            c.update({k: v for k, v in json.load(f).items() if k in DEFAULT})
    if c["size"] not in SIZES:
        c["size"] = DEFAULT["size"]
    c["parallel"] = max(1, min(PARALLEL_MAX, int(c.get("parallel") or 1)))
    if c["brevity"] not in BREVITY:
        c["brevity"] = DEFAULT["brevity"]
    if c["profile"] not in PROFILES:
        c["profile"] = DEFAULT["profile"]
    if c["polish"] not in POLISH:
        c["polish"] = DEFAULT["polish"]
    if c["family"] not in FAMILY:
        c["family"] = DEFAULT["family"]
    if c["assign"] not in ASSIGN:
        c["assign"] = DEFAULT["assign"]
    if c["baseline_split"] not in BASELINE_SPLIT:
        c["baseline_split"] = DEFAULT["baseline_split"]
    if c["assign_rule"] not in ASSIGN_RULE:
        c["assign_rule"] = DEFAULT["assign_rule"]
    return dict(SIZES[c["size"]], **{k: c[k] for k in DEFAULT})


def set(root, size=None, parallel=None, brevity=None, profile=None, polish=None, family=None,  # noqa: A001
        assign=None, assign_rule=None, baseline_split=None):
    c = {k: get(root)[k] for k in DEFAULT}
    for key, val, allowed in (("polish", polish, POLISH), ("family", family, FAMILY), ("assign", assign, ASSIGN)):
        if val is not None:
            if val not in allowed:
                raise ValueError("{} 는 {} 중 하나".format(key, list(allowed)))
            c[key] = val
    if baseline_split is not None:
        if baseline_split not in BASELINE_SPLIT:
            raise ValueError("baseline_split 은 {} 중 하나".format(list(BASELINE_SPLIT)))
        c["baseline_split"] = baseline_split
    if assign_rule is not None:
        if assign_rule not in ASSIGN_RULE:
            raise ValueError("assign_rule 은 v1·v2·v3 중 하나")
        c["assign_rule"] = assign_rule
    if brevity is not None:
        if brevity not in BREVITY:
            raise ValueError("brevity 는 {} 중 하나".format(list(BREVITY)))
        c["brevity"] = brevity
    if profile is not None:
        if profile not in PROFILES:
            raise ValueError("profile 은 {} 중 하나".format(list(PROFILES)))
        c["profile"] = profile
    if size is not None:
        if size not in SIZES:
            raise ValueError("size 는 {} 중 하나".format(list(SIZES)))
        c["size"] = size
    if parallel is not None:
        c["parallel"] = int(parallel)
    with open(os.path.join(root, "config.json"), "w", encoding="utf-8") as f:
        json.dump(c, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return get(root)


def model_for(root, stage):
    m = stage.get("model") or "sonnet"
    return get(root)["model_map"].get(m, m)


def qa_rules(root):
    c = get(root)
    return {"per_tension_members": c["members"], "distractor": c["distractor"], "twin": (c["twin"], c["twin"]),
            "false_friend": (c["false_friend"], c["false_friend"]), "trap_negation": c["trap_negation"],
            "trap_no_context": c["trap_no_context"], "trap_injection": (c["trap_injection"], c["trap_injection"])}


def public():
    return {"sizes": {k: {"label": v["label"], "desc": v["desc"]} for k, v in SIZES.items()},
            "brevity": BREVITY, "profiles": PROFILES, "polish": POLISH, "family": FAMILY, "assign": ASSIGN,
            "baseline_split": BASELINE_SPLIT, "assign_rule": ASSIGN_RULE}

