"""결정적 스테이지 — LLM 없이 스크립트로 도는 단계."""
import hashlib
from collections import Counter

from . import qa, store

ROLES = {"member", "distractor", "twin", "false_friend", "counterexample",
         "trap_negation", "trap_no_context", "trap_injection"}
KINDS = {"action", "avoidance", "workaround", "norm", "edge", "opinion", "noise"}


# ---------------------------------------------------------------- 02 split
def check_corpus(rows):
    """생성 결과(라벨 포함) 구조 검사 → (errors, raw, labels). 01 생성 작업의 저장 전 검사와 split 이 같이 쓴다."""
    errors, seen, raw, labels = ([] if rows else ["행 0개"]), set(), [], {}
    for r in rows:
        rid = r.get("id")
        lab = r.get("label") or {}
        if not rid or not str(rid).startswith("RAW_"):
            errors.append("잘못된 id: {}".format(rid))
            continue
        if rid in seen:
            errors.append("중복 id: {}".format(rid))
        seen.add(rid)
        if not r.get("raw_text"):
            errors.append("{}: raw_text 없음".format(rid))
        if lab.get("role") not in ROLES:
            errors.append("{}: role 이상 ({})".format(rid, lab.get("role")))
        if lab.get("expected_kind") not in KINDS:
            errors.append("{}: expected_kind 이상 ({})".format(rid, lab.get("expected_kind")))
        if lab.get("role") == "twin" and not lab.get("twin_of"):
            errors.append("{}: twin 인데 twin_of 없음".format(rid))
        if lab.get("role") == "trap_injection" and not lab.get("injection_token"):
            errors.append("{}: trap_injection 인데 injection_token 없음".format(rid))
        raw.append({"id": rid, "raw_text": r.get("raw_text"),
                    "source_type": r.get("source_type", "synthetic_comment"), "is_synthetic": True})
        labels[rid] = dict(lab, style=r.get("style"))
    for rid, lab in labels.items():
        if lab.get("twin_of") and lab["twin_of"] not in labels:
            errors.append("{}: twin_of {} 없음".format(rid, lab["twin_of"]))
    return errors, raw, labels


def split(root):
    """hidden/corpus_labeled → data/raw (라벨 제거) + hidden/labels. 구조 오류가 있으면 쓰지 않는다."""
    rows = store.read(root, "corpus_labeled", allow_hidden=True)
    if rows is None:
        return {"errors": ["hidden/corpus_labeled.jsonl 없음"], "raw_count": 0, "roles": {}, "qa": None}
    errors, raw, labels = check_corpus(rows)
    roles = Counter(l.get("role") for l in labels.values())
    report = qa.run(root)
    if not errors:
        store.write(root, "raw", raw)
        store.write(root, "labels", labels)
        if report is not None:
            store.write_run_json(root, "qa/corpus_qa.json", report)
    return {"errors": errors, "raw_count": len(raw), "roles": dict(roles), "qa": report}


# ---------------------------------------------------------------- 27 package
RETRIEVAL_VERSION = "retrieval_v01"
PACKAGE_SIZE = 20                       # 한 패키지의 재료 수 (반례 제외)
RATIO = {"relevant": 0.6, "adjacent": 0.2, "distant": 0.2}   # 출발점 가설. 최적값 아님


def _bigrams(s):
    s = store.squash(s)
    return {s[i:i + 2] for i in range(max(0, len(s) - 1))}


def _jaccard(a, b):
    return len(a & b) / len(a | b) if a and b else 0.0


def _stable(seed, key):
    return hashlib.sha1("{}|{}".format(seed, key).encode("utf-8")).hexdigest()


def package(root):
    """tension 별 검색 패키지. relevant = 자기 member, adjacent = 다른 tension·무소속 중 맥락이 닿는 행동,
    distant = 자기 유추 + 다른 tension 의 먼 유추(뜻밖의 연결). 선택 이유를 함께 남긴다."""
    tensions = store.read(root, "tensions") or []
    behaviors = store.read(root, "behaviors") or []
    analogies = store.read(root, "analogies") or []
    if not tensions or not behaviors:
        return {"errors": ["tensions·behaviors 가 있어야 한다"], "count": 0}
    beh = {b["id"]: b for b in behaviors}
    text = {b["id"]: _bigrams("{} {}".format(b.get("action", ""), b.get("source_excerpt", ""))) for b in behaviors}
    owner = {}
    for t in tensions:
        for b in t.get("member_ids", []):
            owner.setdefault(b, t["id"])

    n_rel = int(round(PACKAGE_SIZE * RATIO["relevant"]))
    n_adj = int(round(PACKAGE_SIZE * RATIO["adjacent"]))
    n_dis = PACKAGE_SIZE - n_rel - n_adj
    out = []
    for i, t in enumerate(tensions, 1):
        members = [b for b in t.get("member_ids", []) if b in beh]
        relevant = members[:n_rel]
        phases = Counter((beh[b].get("context") or {}).get("phase") for b in members)
        phases.pop(None, None)
        top_phase = phases.most_common(1)[0][0] if phases else None
        centroid = set().union(*[text[b] for b in members]) if members else set()

        cands = []
        for b in behaviors:
            bid = b["id"]
            if bid in members or bid in t.get("counterexample_ids", []) or b.get("kind") == "noise":
                continue
            sim = _jaccard(text[bid], centroid)
            same_phase = top_phase is not None and (b.get("context") or {}).get("phase") == top_phase
            score = sim + (0.15 if same_phase else 0) + (0.05 if bid not in owner else 0)
            why = []
            if same_phase:
                why.append("phase={} 공유".format(top_phase))
            if sim >= 0.08:
                why.append("표현 유사 {:.2f}".format(sim))
            why.append("무소속" if bid not in owner else "{} 소속".format(owner[bid]))
            cands.append((score, bid, " · ".join(why)))
        cands.sort(key=lambda x: (-x[0], x[1]))
        adjacent = cands[:n_adj]

        own = [a for a in analogies if t["id"] in a.get("target_tension_ids", [])]
        foreign = [a for a in analogies if t["id"] not in a.get("target_tension_ids", [])
                   and a.get("distance") == "distant"]
        foreign.sort(key=lambda a: _stable(t["id"], a["id"]))   # 결정적인 뜻밖의 연결
        k_own = min(len(own), max(0, n_dis - 1)) if foreign else min(len(own), n_dis)
        distant = [(a["id"], "자기 유추") for a in own[:k_own]] + \
                  [(a["id"], "다른 tension 의 먼 유추 (뜻밖의 연결)") for a in foreign[:n_dis - k_own]]

        out.append({
            "id": "PKG_{:03d}".format(i), "tension_id": t["id"],
            "relevant_ids": relevant,
            "adjacent_ids": [bid for _, bid, _ in adjacent],
            "distant_analogy_ids": [aid for aid, _ in distant],
            "counterexample_ids": [b for b in t.get("counterexample_ids", []) if b in beh],
            "reasons": dict([(bid, why) for _, bid, why in adjacent] + distant),
            "shortfall": {"relevant": n_rel - len(relevant), "adjacent": n_adj - len(adjacent),
                          "distant": n_dis - len(distant)},
            "retrieval_version": RETRIEVAL_VERSION, "ratio": RATIO, "is_synthetic": True,
        })
    store.write(root, "packages", out)
    return {"errors": [], "count": len(out)}


# ---------------------------------------------------------------- 커버리지
PHASES = ["before", "during", "after", None]


def coverage(root):
    """어떤 행동 공간이 비어 있는가 (설계 §12.4). 정답 라벨 없이 계산한다."""
    behaviors = store.read(root, "behaviors") or []
    tensions = store.read(root, "tensions") or []
    scenarios = store.read(root, "scenarios") or []
    evaluations = store.read(root, "evaluations") or []
    families = store.read(root, "families") or []
    premises = store.read(root, "premises") or []

    kinds = ["action", "avoidance", "workaround", "norm", "edge", "opinion", "noise"]
    grid = {k: {str(p): 0 for p in PHASES} for k in kinds}
    for b in behaviors:
        p = (b.get("context") or {}).get("phase")
        p = p if p in PHASES else None
        if b.get("kind") in grid:
            grid[b["kind"]][str(p)] += 1

    owner = {}
    for t in tensions:
        for bid in t.get("member_ids", []):
            owner[bid] = t["id"]
    per_tension = []
    by_scn = Counter(tid for s in scenarios for tid in s.get("tension_ids", []))
    beh = {b["id"]: b for b in behaviors}
    for t in tensions:
        ks = Counter(beh[b].get("kind") for b in t.get("member_ids", []) if b in beh)
        per_tension.append({"id": t["id"], "label": t.get("label"), "members": len(t.get("member_ids", [])),
                            "counterexamples": len(t.get("counterexample_ids", [])),
                            "kinds": dict(ks), "scenarios": by_scn.get(t["id"], 0)})
    ctx_filled = Counter()
    for b in behaviors:
        for k, v in (b.get("context") or {}).items():
            if v is not None:
                ctx_filled[k] += 1
    gaps = []
    for k in ("workaround", "norm", "edge", "avoidance"):
        if sum(grid[k].values()) == 0:
            gaps.append("{} 행동이 하나도 없다".format(k))
    for p in ("before", "during", "after"):
        if sum(grid[k][p] for k in kinds) == 0:
            gaps.append("{} 단계 행동이 없다".format(p))
    for t in per_tension:
        if t["scenarios"] == 0 and scenarios:
            gaps.append("{} 에서 나온 시나리오가 없다".format(t["id"]))
    horizons = Counter(p.get("horizon") for p in premises)
    if premises and len(horizons) == 1:
        gaps.append("미래 가정이 한 horizon({})에만 몰려 있다".format(next(iter(horizons))))
    fam_sizes = sorted([len(f.get("scenario_ids", [])) for f in families], reverse=True)
    if fam_sizes and scenarios and fam_sizes[0] / len(scenarios) > 0.4:
        gaps.append("가장 큰 family 가 시나리오의 {:.0%}를 차지한다 — 다양성 부족 의심".format(fam_sizes[0] / len(scenarios)))
    return {
        "kind_phase": grid, "kinds": kinds, "phases": [str(p) for p in PHASES],
        "per_tension": per_tension,
        "linked": sum(1 for b in behaviors if b["id"] in owner), "unlinked": sum(1 for b in behaviors if b["id"] not in owner),
        "context_filled": dict(ctx_filled), "behaviors": len(behaviors),
        "horizons": dict(horizons), "family_sizes": fam_sizes,
        "evaluated": len({e.get("scenario_id") for e in evaluations}), "scenarios": len(scenarios),
        "gaps": gaps,
    }


# ---------------------------------------------------------------- 00 정답표 검사
def check_ground_truth(rows, n_expected=6):
    """자동 생성 정답표의 구조 검사 → errors. 저장 전 검사(jobs.finalize)에서 쓴다."""
    if len(rows) != 1 or not isinstance(rows[0], dict):
        return ["JSON 객체 하나여야 한다 (받은 레코드 {}개)".format(len(rows))]
    gt, errors = rows[0], []
    ts = gt.get("tensions") or []
    if not n_expected - 1 <= len(ts) <= n_expected + 1:
        errors.append("tension 수 {} ({}~{})".format(len(ts), n_expected - 1, n_expected + 1))
    ids = [t.get("id") for t in ts]
    if len(set(ids)) != len(ids) or not all(str(i).startswith("HT_") for i in ids):
        errors.append("tension id 는 HT_ 로 시작하고 겹치지 않아야 한다: {}".format(ids))
    for t in ts:
        for k in ("pole_a", "pole_b", "principle"):
            if not t.get(k):
                errors.append("{}: {} 없음".format(t.get("id"), k))
        if t.get("familiarity") not in ("familiar", "unfamiliar"):
            errors.append("{}: familiarity 이상 ({})".format(t.get("id"), t.get("familiarity")))
        if len(t.get("behavior_seeds") or []) < 2:
            errors.append("{}: behavior_seeds 2개 이상".format(t.get("id")))
    axes = [" ".join(str(t.get("axis") or "").split()) for t in ts if t.get("axis")]
    if len(set(axes)) != len(axes):
        errors.append("axis 가 겹친다: {}".format(axes))
    unf = sum(1 for t in ts if t.get("familiarity") == "unfamiliar")
    if ts and unf * 3 < len(ts):
        errors.append("unfamiliar {}개 — 3분의 1 이상이어야 한다".format(unf))
    if len(gt.get("distractor_themes") or []) < 4:
        errors.append("distractor_themes 4개 이상")
    return errors


# ---------------------------------------------------------------- 75 후보 추리기
SHORTLIST_VERSION = "shortlist_v01"
SHORTLIST_N = 5
# 점수에 쓰는 차원 (평균). ai_necessity 는 "AI 가 꼭 필요한가"라는 성격 정보라 좋고 나쁨에 넣지 않는다.
SHORTLIST_DIMS = ["behavioral_grounding", "tension_strength", "novelty", "plausibility", "device_fit", "agent_fit"]
DIM_KO = {"behavioral_grounding": "근거", "tension_strength": "tension", "novelty": "새로움",
          "plausibility": "현실성", "device_fit": "기기 적합", "cliche_level": "뻔함", "agent_fit": "에이전트 적합"}


def shortlist(root, n=SHORTLIST_N):
    """평가 점수로 거르고, family 마다 가장 나은 하나씩 골라 상위 n개. 사람 검토 없이 나오는 자동 후보.
    가중치는 출발점 가설이다 — 사람 검토가 쌓이면 이 규칙과 대조해 고친다."""
    scn = store.read(root, "scenarios") or []
    ev = {e["scenario_id"]: e for e in store.read(root, "evaluations") or []}
    fam = {}
    for f in store.read(root, "families") or []:
        for sid in f.get("scenario_ids", []):
            fam[sid] = f
    beh = {b["id"] for b in store.read(root, "behaviors") or []}
    if not scn or not ev:
        return {"errors": ["scenarios·evaluations 가 필요하다"], "picks": []}
    cands, excluded = [], []
    for s in scn:
        e = ev.get(s["id"])
        if not e:
            excluded.append({"scenario_id": s["id"], "reasons": ["평가 없음"]})
            continue
        sc = e.get("scores") or {}
        why_not = []
        if (sc.get("behavioral_grounding") or 5) < 3:
            why_not.append("근거 부족 ({})".format(sc["behavioral_grounding"]))
        if (sc.get("plausibility") or 5) < 3:
            why_not.append("현실성 부족 ({})".format(sc["plausibility"]))
        if (sc.get("cliche_level") or 1) >= 4:
            why_not.append("뻔함 ({})".format(sc["cliche_level"]))
        if "reject" in str(e.get("review_route") or ""):
            why_not.append("평가 경로 {}".format(e["review_route"]))
        if any(x not in beh for x in s.get("evidence_ids", [])):
            why_not.append("추적 끊김")
        if why_not:
            excluded.append({"scenario_id": s["id"], "reasons": why_not})
            continue
        vals = [sc[d] for d in SHORTLIST_DIMS if isinstance(sc.get(d), (int, float))]
        score = round(sum(vals) / len(vals) - 0.5 * ((sc.get("cliche_level") or 1) - 1), 2) if vals else 0
        f = fam.get(s["id"]) or {}
        cands.append({"scenario_id": s["id"], "score": score, "family_id": f.get("id"),
                      "tension_id": (s.get("tension_ids") or [None])[0],
                      "family_label": f.get("label"), "scores": sc, "review_route": e.get("review_route")})
    cands.sort(key=lambda c: (-c["score"], -(c["scores"].get("novelty") or 0),
                              -(c["scores"].get("behavioral_grounding") or 0), c["scenario_id"]))
    picks, used_t, used_f = [], set(), set()
    chosen = lambda c: any(p["scenario_id"] == c["scenario_id"] for p in picks)
    # family 가 잘 묶이지 않을 때도(tv-v1: 18개→17 family) 한 문제에 몰리지 않게 tension 을 먼저 흩는다.
    for slot, ok in (("tension 대표", lambda c: c["tension_id"] not in used_t and (c["family_id"] or c["scenario_id"]) not in used_f),
                     ("family 대표", lambda c: (c["family_id"] or c["scenario_id"]) not in used_f),
                     ("같은 family 두 번째", lambda c: True)):
        for c in cands:
            if len(picks) >= n:
                break
            if not chosen(c) and ok(c):
                picks.append(dict(c, slot=slot))
                used_t.add(c["tension_id"])
                used_f.add(c["family_id"] or c["scenario_id"])
    for i, p in enumerate(picks, 1):
        sc = p["scores"]
        top = sorted(((sc[d], DIM_KO[d]) for d in SHORTLIST_DIMS if isinstance(sc.get(d), (int, float))),
                     reverse=True)[:2]
        p["rank"] = i
        p["why"] = ["{} {}".format(k, v) for v, k in top] + ["뻔함 {}".format(sc.get("cliche_level", "—")), p["slot"]]
    res = {"version": SHORTLIST_VERSION, "at": store.now(), "n": n,
           "rule": "근거·현실성 3 미만, 뻔함 4 이상, 추적 끊김은 제외 → 점수 = 평균(근거·tension·새로움·현실성·기기 적합·에이전트 적합*) − 0.5×(뻔함−1) → tension 마다 1개(다음 family 마다 1개) → 상위 {}개 (*평가에 있을 때만)".format(n),
           "counts": {"scenarios": len(scn), "eligible": len(cands), "excluded": len(excluded)},
           "picks": picks, "excluded": excluded}
    store.write(root, "shortlist", res)
    return res
