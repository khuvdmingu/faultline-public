"""인간 검토 결정 — review/decisions.jsonl 에 추가만 한다 (수정·삭제 없음, 최신 결정이 유효).

설계 §22.3: 먼저 시나리오 설명만 보고 판단하고(blind), 근거는 두 번째로 본다.
그래서 결정마다 blind 여부와 근거를 봤는지(saw_evidence)를 함께 남긴다.
"""
from . import schema, store


def add(root, payload):
    sid = payload.get("scenario_id")
    decision = payload.get("decision")
    reason = (payload.get("reason") or "").strip()
    scenarios = {s["id"] for s in store.read(root, "scenarios") or []}
    if sid not in scenarios:
        raise ValueError("없는 시나리오: {}".format(sid))
    if decision not in schema.DECISIONS:
        raise ValueError("decision 은 develop|hold|reject")
    if not reason:
        raise ValueError("이유를 적어야 한다 — 버린 이유도 지식이다")
    rows = store.read(root, "decisions") or []
    row = {"id": "DEC_{:03d}".format(len(rows) + 1), "scenario_id": sid, "decision": decision, "reason": reason,
           "blind": bool(payload.get("blind", True)), "saw_evidence": bool(payload.get("saw_evidence", False)),
           "reviewer": payload.get("reviewer") or "user", "at": store.now()}
    store.append(root, "decisions", row)
    return row


def latest(root):
    out = {}
    for d in store.read(root, "decisions") or []:
        out[d["scenario_id"]] = d
    return out
