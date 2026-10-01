"""레코드 검증 — 형식·ID·참조·원문 인용·합성 표시.

SPECS 한 표가 모든 엔티티의 계약이다. docs/SCHEMA.md 와 같은 내용을 코드로 둔다.
"""
from . import store

KINDS = {"action", "avoidance", "workaround", "norm", "edge", "opinion", "noise"}
CONTEXT_KEYS = {"device", "social", "platform", "phase"}
HORIZONS = {"probable", "plausible", "possible", "preferable", "wildcard"}
DECISIONS = {"develop", "hold", "reject"}
SCORE_DIMS = ["behavioral_grounding", "tension_strength", "novelty", "cliche_level",
              "plausibility", "device_fit", "ai_necessity", "agent_fit"]   # agent_fit 은 brief.technology 가 있을 때만

# key: (접두어, 필수 필드, {참조 필드: 대상 키})
SPECS = {
    "raw": ("RAW_", ["raw_text", "is_synthetic"], {}),
    "baseline": ("BAS_", ["title", "experience", "mechanism", "is_synthetic"], {}),
    "behaviors": ("BEH_", ["source_id", "kind", "action", "source_excerpt", "context",
                           "inference_status", "is_synthetic"], {"source_id": "raw"}),
    "tensions": ("TEN_", ["label", "pole_a", "pole_b", "member_ids", "counterexample_ids", "is_synthetic"],
                 {"member_ids": "behaviors", "counterexample_ids": "behaviors"}),
    "analogies": ("ANA_", ["source_domain", "source_pattern", "abstract_mechanism", "target_tension_ids",
                           "mapping", "transfer_limitations", "distance", "is_synthetic"],
                  {"target_tension_ids": "tensions"}),
    "packages": ("PKG_", ["tension_id", "relevant_ids", "adjacent_ids", "distant_analogy_ids",
                          "retrieval_version", "is_synthetic"],
                 {"tension_id": "tensions", "relevant_ids": "behaviors", "adjacent_ids": "behaviors",
                  "distant_analogy_ids": "analogies"}),
    "principles": ("PRI_", ["statement", "tension_ids", "is_synthetic"],
                   {"tension_ids": "tensions", "package_ids": "packages", "analogy_ids": "analogies"}),
    "premises": ("PREM_", ["what_if", "changed_assumption", "future_rule", "horizon", "origin_tension_ids",
                           "principle_ids", "required_changes", "tradeoffs", "is_synthetic"],
                 {"origin_tension_ids": "tensions", "principle_ids": "principles", "analogy_ids": "analogies"}),
    "scenarios": ("SCN_", ["title", "principle_ids", "tension_ids", "evidence_ids", "trigger", "experience",
                           "assumptions", "failure_case", "is_synthetic"],
                  {"principle_ids": "principles", "tension_ids": "tensions", "evidence_ids": "behaviors",
                   "premise_ids": "premises", "analogy_ids": "analogies"}),
    "evaluations": ("EVAL_", ["scenario_id", "rubric_version", "scores", "review_route", "is_synthetic"],
                    {"scenario_id": "scenarios", "similar_baseline_ids": "baseline"}),
    "families": ("FAM_", ["label", "mechanism", "scenario_ids", "is_synthetic"],
                 {"scenario_ids": "scenarios", "principle_ids": "principles"}),
    "polished": ("POL_", ["target_id", "fields", "is_synthetic"], {}),   # 대상 검사는 engine/humanize.gate
    "decisions": ("DEC_", ["scenario_id", "decision", "reason", "at"], {"scenario_id": "scenarios"}),
}
ORDER = ["raw", "baseline", "behaviors", "tensions", "analogies", "packages", "principles", "premises",
         "scenarios", "evaluations", "families", "polished", "decisions"]


def _as_list(v):
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def check_rows(key, rows, ids_by_key):
    """한 엔티티의 레코드 검사. (errors, warnings)"""
    prefix, required, refs = SPECS[key]
    errors, warnings = [], []
    seen = set()
    for r in rows:
        rid = r.get("id", "?")
        tag = "{} {}".format(key, rid)
        for f in required:
            if f not in r:
                errors.append("{}: 필드 {} 없음".format(tag, f))
        if not str(rid).startswith(prefix):
            errors.append("{}: ID 접두어는 {}".format(tag, prefix))
        if rid in seen:
            errors.append("{}: 중복 ID".format(tag))
        seen.add(rid)
        if key != "decisions" and "is_synthetic" in r and not isinstance(r.get("is_synthetic"), bool):
            errors.append("{}: is_synthetic 은 true/false".format(tag))
        for field, target in refs.items():
            for v in _as_list(r.get(field)):
                if target in ids_by_key and v not in ids_by_key[target]:
                    errors.append("{}: {} → 없는 ID {}".format(tag, field, v))
    return errors, warnings


def run(root):
    """실험 전체 검사. {"errors", "warnings", "skipped", "counts"}"""
    data = {k: store.read(root, k) for k in ORDER}
    ids = {k: {r.get("id") for r in (rows or [])} for k, rows in data.items() if rows is not None}
    errors, warnings, skipped, counts = [], [], [], {}

    for key in ORDER:
        rows = data[key]
        if rows is None:
            skipped.append(key)
            continue
        counts[key] = len(rows)
        e, w = check_rows(key, rows, ids)
        errors += e
        warnings += w

    raw = {r["id"]: r for r in data["raw"] or []}
    synthetic_root = any(r.get("is_synthetic") for r in raw.values())

    for b in data["behaviors"] or []:
        tag = "behaviors {}".format(b.get("id"))
        src = raw.get(b.get("source_id"))
        if src is not None and store.squash(b.get("source_excerpt")) not in store.squash(src.get("raw_text")):
            errors.append("{}: source_excerpt 가 원문에 없음 ({!r})".format(tag, b.get("source_excerpt")))
        if b.get("kind") not in KINDS:
            errors.append("{}: kind 이상 ({})".format(tag, b.get("kind")))
        ctx = b.get("context")
        if not isinstance(ctx, dict) or set(ctx) - CONTEXT_KEYS:
            errors.append("{}: context 는 {} 키만".format(tag, sorted(CONTEXT_KEYS)))
        if b.get("inference_status") not in ("explicit", "inferred", "none"):
            errors.append("{}: inference_status 이상".format(tag))
    if data["behaviors"] is not None and raw:
        covered = {b.get("source_id") for b in data["behaviors"]}
        missing = [rid for rid in raw if rid not in covered]
        if missing:
            warnings.append("행동이 하나도 없는 원문 {}개: {}".format(len(missing), ", ".join(missing[:10])))

    for t in data["tensions"] or []:
        overlap = set(t.get("member_ids", [])) & set(t.get("counterexample_ids", []))
        if overlap:
            errors.append("tensions {}: member 와 counterexample 에 동시에 있음 {}".format(t.get("id"), sorted(overlap)))
        if len(t.get("member_ids", [])) < 3:
            warnings.append("tensions {}: member 3개 미만".format(t.get("id")))

    for a in data["analogies"] or []:
        if a.get("distance") not in ("adjacent", "distant"):
            errors.append("analogies {}: distance 는 adjacent|distant".format(a.get("id")))
        if not a.get("transfer_limitations"):
            warnings.append("analogies {}: 전이 한계가 비어 있음".format(a.get("id")))

    for p in data["premises"] or []:
        if p.get("horizon") not in HORIZONS:
            errors.append("premises {}: horizon 이상 ({})".format(p.get("id"), p.get("horizon")))

    tension_members = {t["id"]: set(t.get("member_ids", [])) | set(t.get("counterexample_ids", []))
                       for t in data["tensions"] or []}
    for s in data["scenarios"] or []:
        if not s.get("evidence_ids"):
            errors.append("scenarios {}: evidence_ids 가 비어 있음".format(s.get("id")))
        allowed = set().union(*[tension_members.get(t, set()) for t in s.get("tension_ids", [])]) \
            if s.get("tension_ids") else set()
        stray = [e for e in s.get("evidence_ids", []) if allowed and e not in allowed]
        if stray:
            warnings.append("scenarios {}: 연결된 tension 밖의 근거 {}".format(s.get("id"), stray))
        if s.get("horizon") and s["horizon"] not in HORIZONS:
            errors.append("scenarios {}: horizon 이상".format(s.get("id")))

    for ev in data["evaluations"] or []:
        sc = ev.get("scores") or {}
        for d in SCORE_DIMS:
            v = sc.get(d)
            if v is not None and v not in (1, 2, 3, 4, 5):
                errors.append("evaluations {}: {} 는 1~5 또는 null".format(ev.get("id"), d))
    if data["evaluations"] is not None and data["scenarios"]:
        judged = {e.get("scenario_id") for e in data["evaluations"]}
        miss = [s["id"] for s in data["scenarios"] if s["id"] not in judged]
        if miss:
            warnings.append("평가 없는 시나리오 {}개: {}".format(len(miss), ", ".join(miss[:10])))

    if data["families"] is not None and data["scenarios"]:
        assigned = {}
        for f in data["families"]:
            for sid in f.get("scenario_ids", []):
                assigned.setdefault(sid, []).append(f["id"])
        dup = {k: v for k, v in assigned.items() if len(v) > 1}
        if dup:
            errors.append("시나리오가 family 여러 개에 속함: {}".format(dup))
        miss = [s["id"] for s in data["scenarios"] if s["id"] not in assigned]
        if miss:
            warnings.append("family 없는 시나리오 {}개: {}".format(len(miss), ", ".join(miss[:10])))

    for d in data["decisions"] or []:
        if d.get("decision") not in DECISIONS:
            errors.append("decisions {}: decision 은 develop|hold|reject".format(d.get("id")))

    # 합성 실험에서 파생된 레코드는 전부 is_synthetic=true 여야 한다 (승격 금지)
    if synthetic_root:
        for key in ORDER:
            if key in ("raw", "decisions"):
                continue
            for r in data[key] or []:
                if r.get("is_synthetic") is not True:
                    errors.append("{} {}: 합성 실험의 파생물인데 is_synthetic 이 true 가 아님".format(key, r.get("id")))

    return {"errors": errors, "warnings": warnings, "skipped": skipped, "counts": counts}


def check_output(key, rows, root):
    """작업 결과를 저장하기 전 검사 — 같은 실험의 기존 데이터를 참조 대상으로 쓴다."""
    ids = {}
    for k in ORDER:
        if k == key:
            continue
        existing = store.read(root, k)
        if existing is not None:
            ids[k] = {r.get("id") for r in existing}
    ids[key] = {r.get("id") for r in rows}
    return check_rows(key, rows, ids)
