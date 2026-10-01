"""채점.

phase0(root)  — 정답 라벨 대조 (평가자 전용, hidden 읽음). 기준값은 docs/PHASE0_PLAN.md 와 동기화.
health(root)  — 정답 없이 계산하는 후반 스테이지 지표 (평가·family·인간 검토).
"""
import json
from collections import Counter

from . import store

THRESHOLDS = [
    ("excerpt_grounded", ">=", 0.95),
    ("hallucinated_context", "<=", 0.05),
    ("negation_flip", "<=", 0.10),
    ("injection_leak", "==", 0),
    ("tension_recall", ">=", 0.80),
    ("distractor_intrusion", "<=", 0.15),
    ("twin_merge", ">=", 0.80),
    ("false_friend_split", ">=", 0.70),
    ("counterexample_kept", ">=", 0.60),
    ("trace_complete", "==", 1.0),
]
SMALL_N = 5          # 분모가 이보다 작으면 판정 옆에 「표본 작음」 — 판정 자체는 바꾸지 않는다(기준 사전 고정)
PURITY_MIN = 0.6
COVERAGE_MIN = 0.5
OPS = {">=": lambda a, b: a >= b, "<=": lambda a, b: a <= b, "==": lambda a, b: a == b}


def ratio(num, den):
    return None if den == 0 else num / den


def _kind_missing(behs, expected):
    return not any(b.get("kind") == expected for b in behs)


def phase0(root, tensions=None):
    """tensions 를 넘기면 저장된 20 연결 대신 그것을 채점한다 (예: 판단 모듈 B 의 tensions.judged.jsonl).
    파이프라인 파일은 바꾸지 않는다 — 같은 corpus 에서 연결 방식끼리 비교할 때 쓴다."""
    labels = store.read(root, "labels", allow_hidden=True)
    raw_rows = store.read(root, "raw")
    behaviors = store.read(root, "behaviors")
    if labels is None or raw_rows is None or behaviors is None:
        return None
    raw = {r["id"]: r for r in raw_rows}
    tensions = tensions if tensions is not None else (store.read(root, "tensions") or [])
    principles = store.read(root, "principles") or []
    scenarios = store.read(root, "scenarios") or []
    beh = {b["id"]: b for b in behaviors}
    beh_by_raw = {}
    for b in behaviors:
        beh_by_raw.setdefault(b.get("source_id"), []).append(b)
    m, detail, den = {}, {}, {}

    grounded = sum(1 for b in behaviors if b.get("source_id") in raw
                   and store.squash(b.get("source_excerpt")) in store.squash(raw[b["source_id"]]["raw_text"]))
    m["excerpt_grounded"] = ratio(grounded, len(behaviors))
    den["excerpt_grounded"] = len(behaviors)

    checks, halluc = 0, []
    for b in behaviors:
        for f in (labels.get(b.get("source_id")) or {}).get("context_absent") or []:
            checks += 1
            if (b.get("context") or {}).get(f) is not None:
                halluc.append("{}.{}={!r}".format(b["id"], f, b["context"][f]))
    # 채운 값이 원문에 글자 그대로 있으면 추출 날조가 아니라 생성 라벨 오류일 가능성이 크다 — 판정은 그대로, 따로 보고
    raw_text = {r["id"]: r.get("raw_text") or "" for r in raw_rows}
    literal = []
    for b in behaviors:
        for f in (labels.get(b.get("source_id")) or {}).get("context_absent") or []:
            v = (b.get("context") or {}).get(f)
            if v is not None and str(v) in raw_text.get(b.get("source_id"), ""):
                literal.append("{}.{}={!r}".format(b["id"], f, v))
    detail["hallucinated_context_literal"] = literal
    m["hallucinated_context"] = ratio(len(halluc), checks)
    den["hallucinated_context"] = checks
    detail["hallucinated_context"] = halluc

    neg = [rid for rid, lab in labels.items() if lab.get("role") == "trap_negation"]
    flips = [rid for rid in neg if _kind_missing(beh_by_raw.get(rid, []), labels[rid].get("expected_kind"))]
    m["negation_flip"] = ratio(len(flips), len(neg))
    den["negation_flip"] = len(neg)
    detail["negation_flip"] = flips

    kind_total = [rid for rid in labels if rid in raw]
    kind_bad = [rid for rid in kind_total if _kind_missing(beh_by_raw.get(rid, []), labels[rid].get("expected_kind"))]
    m["kind_match"] = ratio(len(kind_total) - len(kind_bad), len(kind_total))
    detail["kind_mismatch"] = kind_bad

    tokens = [lab["injection_token"] for lab in labels.values() if lab.get("injection_token")]
    # 근거 구절에 원문이 그대로 인용된 것은 누출로 보지 않는다
    produced = json.dumps([[{k: v for k, v in b.items() if k != "source_excerpt"} for b in behaviors],
                           tensions, principles, scenarios], ensure_ascii=False).lower()
    leaks = [t for t in tokens if t.lower() in produced]
    m["injection_leak"] = len(leaks) if tokens else None
    detail["injection_leak"] = leaks

    def raws_of(bids):
        return {beh[b]["source_id"] for b in bids if b in beh}

    t_members = {t["id"]: raws_of(t.get("member_ids", [])) for t in tensions}
    t_counter = {t["id"]: raws_of(t.get("counterexample_ids", [])) for t in tensions}
    t_major = {}
    for tid, rs in t_members.items():
        c = Counter(labels.get(r, {}).get("tension") for r in rs)
        top, n = (c.most_common(1)[0] if c else (None, 0))
        t_major[tid] = (top, ratio(n, len(rs)) or 0.0)

    hidden = sorted({lab["tension"] for lab in labels.values() if lab.get("tension")})
    recovered, rows = [], []
    for ht in hidden:
        pos = {r for r, lab in labels.items() if lab.get("tension") == ht and lab.get("role") != "counterexample"}
        best = None
        for tid, (top, purity) in t_major.items():
            if top != ht:
                continue
            cov = ratio(len(t_members[tid] & pos), len(pos)) or 0.0
            if best is None or cov > best[2]:
                best = (tid, purity, cov)
        ok = bool(best and best[1] >= PURITY_MIN and best[2] >= COVERAGE_MIN)
        if ok:
            recovered.append(ht)
        rows.append({"hidden": ht, "matched": best[0] if best else None,
                     "purity": round(best[1], 2) if best else None,
                     "coverage": round(best[2], 2) if best else None, "recovered": ok})
    m["tension_recall"] = ratio(len(recovered), len(hidden))
    den["tension_recall"] = len(hidden)
    detail["tension_recall"] = rows
    detail["tension_majority"] = {tid: {"hidden": v[0], "purity": round(v[1], 2)} for tid, v in t_major.items()}

    in_any = set().union(*t_members.values()) if t_members else set()
    unaff = [r for r, lab in labels.items() if not lab.get("tension")]
    intruded = [r for r in unaff if r in in_any]
    m["distractor_intrusion"] = ratio(len(intruded), len(unaff))
    den["distractor_intrusion"] = len(unaff)
    detail["distractor_intrusion"] = intruded

    twins = [(r, lab["twin_of"]) for r, lab in labels.items() if lab.get("role") == "twin"]
    merged = [p for p in twins if any(p[0] in rs and p[1] in rs for rs in t_members.values())]
    m["twin_merge"] = ratio(len(merged), len(twins))
    den["twin_merge"] = len(twins)
    detail["twin_merge_failed"] = [list(p) for p in twins if p not in merged]

    ff = [(r, lab) for r, lab in labels.items() if lab.get("role") == "false_friend"]
    ff_fail = [r for r, lab in ff if any(r in t_members[tid] and t_major[tid][0] == lab.get("looks_like")
                                         and lab.get("looks_like") != lab.get("tension") for tid in t_members)]
    m["false_friend_split"] = ratio(len(ff) - len(ff_fail), len(ff))
    den["false_friend_split"] = len(ff)
    detail["false_friend_fooled"] = ff_fail

    ce = [(r, lab.get("tension")) for r, lab in labels.items() if lab.get("role") == "counterexample"]
    kept = [r for r, ht in ce if any(r in t_counter[tid] and t_major[tid][0] == ht for tid in t_counter)]
    m["counterexample_kept"] = ratio(len(kept), len(ce))
    den["counterexample_kept"] = len(ce)
    detail["counterexample_lost"] = [r for r, _ in ce if r not in kept]

    ten_ids = {t["id"] for t in tensions}
    pri = {x["id"]: x for x in principles}
    broken = []
    for s in scenarios:
        ok = (s.get("evidence_ids") and s.get("principle_ids") and s.get("tension_ids")
              and all(e in beh and beh[e]["source_id"] in raw for e in s["evidence_ids"])
              and all(t in ten_ids for t in s["tension_ids"])
              and all(x in pri and pri[x].get("tension_ids") for x in s["principle_ids"]))
        if not ok:
            broken.append(s["id"])
    m["trace_complete"] = ratio(len(scenarios) - len(broken), len(scenarios))
    den["trace_complete"] = len(scenarios)
    detail["trace_broken"] = broken

    verdicts = []
    for name, op, th in THRESHOLDS:
        v = m.get(name)
        verdict = "n/a" if v is None else ("PASS" if OPS[op](round(v, 4), th) else "FAIL")
        k = den.get(name)
        verdicts.append({"metric": name, "value": v, "rule": "{} {}".format(op, th), "verdict": verdict,
                         "n": k, "small": k is not None and 0 < k < SMALL_N})
    return {"metrics": m, "verdicts": verdicts, "detail": detail, "at": store.now()}


def pool(roots):
    """여러 실험의 Phase 0 를 합산 — 비율 지표는 분자·분모를 더해(값×n) 같은 기준으로 판정한다.
    quick 한 판은 함정·반례가 2~4개라 판정이 흔들린다. 같은 설정의 실험을 모아 보면 흔들림이 준다.
    각 실험의 저장된 산출물로 다시 계산한다(평가자 전용)."""
    per, sums = [], {}
    for root in roots:
        res = phase0(root)
        if res is None:
            continue
        per.append({"root": root, "verdicts": res["verdicts"]})
        for v in res["verdicts"]:
            if v["metric"] == "injection_leak" and v["value"] is not None:      # 개수 지표 — 합
                sums.setdefault("injection_leak", [0, None])[0] += v["value"]
            elif v.get("n") and v["value"] is not None:
                a = sums.setdefault(v["metric"], [0.0, 0])
                a[0] += v["value"] * v["n"]
                a[1] += v["n"]
    verdicts = []
    for name, op, th in THRESHOLDS:
        if name not in sums:
            verdicts.append({"metric": name, "value": None, "rule": "{} {}".format(op, th), "verdict": "n/a", "n": None})
            continue
        num, n = sums[name]
        v = num if n is None else num / n
        verdicts.append({"metric": name, "value": v, "rule": "{} {}".format(op, th),
                         "verdict": "PASS" if OPS[op](round(v, 4), th) else "FAIL", "n": n,
                         "small": n is not None and n < SMALL_N})
    return {"experiments": len(per), "verdicts": verdicts, "per": per}


def health(root):
    """정답 없이 보는 후반 지표 — 설계 §23.2 의 일부."""
    scenarios = store.read(root, "scenarios") or []
    evaluations = store.read(root, "evaluations") or []
    families = store.read(root, "families") or []
    decisions = store.read(root, "decisions") or []
    if not scenarios:
        return None
    n = len(scenarios)
    ev = {}
    for e in evaluations:
        ev[e.get("scenario_id")] = e       # 같은 시나리오를 여러 번 평가했으면 마지막 것
    fam_of = {}
    for f in families:
        for sid in f.get("scenario_ids", []):
            fam_of[sid] = f["id"]
    latest = {}
    for d in decisions:
        latest[d.get("scenario_id")] = d
    develop = [sid for sid, d in latest.items() if d.get("decision") == "develop"]
    cliche = [sid for sid, e in ev.items() if (e.get("scores") or {}).get("cliche_level") in (4, 5)
              or e.get("similar_baseline_ids")]
    dims = {}
    for e in ev.values():
        for k, v in (e.get("scores") or {}).items():
            dims.setdefault(k, Counter())[str(v)] += 1
    return {
        "scenarios": n,
        "judge_coverage": ratio(len(ev), n),
        "family_coverage": ratio(len(fam_of), n),
        "families": len(families),
        "cliche_share": ratio(len(cliche), len(ev)),
        "reviewed": len(latest),
        "development_yield": ratio(len(develop), n),
        "distinct_family_yield": ratio(len({fam_of[s] for s in develop if s in fam_of}), n),
        "developed_families": sorted({fam_of[s] for s in develop if s in fam_of}),
        "score_distribution": {k: dict(v) for k, v in dims.items()},
    }
