"""확률 → 결정. Jev 식 "퍼지 결정 규칙"을 코드로 조합하는 층.

질문 하나의 결정은 accept(값 확정) 또는 review(사람 검토) 둘뿐이다. 여기서는 아무것도 버리지 않는다 —
버릴지 말지는 태스크(tasks.py)가 여러 답을 합친 뒤에만 정한다 (설계 문서 §17.6: 검사·특성화·지도화, 선별만 하지 않는다).

임계값은 출발점일 뿐 검증된 값이 아니다. 질문 은행(bank/*.json)의 "policy" 로 질문별로 덮어쓴다.
"""

DEFAULT_RULE = {
    "accept_p": 0.70,          # choice: 1위 확률이 이 이상이고
    "min_margin": 0.20,        #         1·2위 차이가 이 이상이면 확정
    "noul_yes": 0.70,          # noul: p(yes) ≥ 이면 True
    "noul_no": 0.30,           #       p(yes) ≤ 이면 False, 사이는 검토
    "score_max_entropy": 0.80, # score: 분포가 이보다 퍼지면 "불안정"으로 검토
    "min_mass": 0.50,          # logprobs·sampling 에서 유효 선택지에 실린 질량이 이보다 낮으면 형식 이탈
}


def rule_for(question):
    r = dict(DEFAULT_RULE)
    r.update(question.policy or {})
    return r


def decide(answer):
    """{"decision": accept|review, "value": 값, "reasons": [...]} 반환."""
    q, r = answer.question, rule_for(answer.question)
    reasons = []
    if answer.error:
        return {"decision": "review", "value": None, "reasons": ["backend_error"]}
    if answer.mass is not None and answer.mass < r["min_mass"]:
        reasons.append("off_format")

    if q.kind == "noul":
        p = answer.p_yes
        value = True if p >= r["noul_yes"] else False if p <= r["noul_no"] else None
        if value is None:
            reasons.append("uncertain")
    elif q.kind == "choice":
        value = answer.top
        if answer.p_top < r["accept_p"] or answer.margin < r["min_margin"]:
            reasons.append("uncertain")
    else:
        value = round(answer.expected, 2)
        if answer.entropy > r["score_max_entropy"]:
            reasons.append("unstable")

    if q.unknown_value is not None and answer.top == q.unknown_value:
        reasons.append("judge_says_unknown")
    return {"decision": "review" if reasons else "accept", "value": value, "reasons": reasons}
