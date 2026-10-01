"""LLM 스테이지 프롬프트 조립.

build(root, stage_id) → [{"text": 프롬프트, "items": [입력 ID...], "index": n}] (배치 목록)

정보 차단선: registry 에서 hidden=False 인 스테이지는 store.read(allow_hidden=False) 로만 읽는다.
hidden/ 키를 읽으려 하면 BarrierError 가 난다 — 프롬프트에 정답이 섞일 길이 코드에서 막힌다.
"""
import json
import os

from . import config, humanize, registry, store

PROMPT_DIR = os.path.join(store.APP_ROOT, "prompts")


def _j(rows, keys=None):
    if keys:
        rows = [{k: r.get(k) for k in keys if k in r} for r in rows]
    return "\n".join(json.dumps(r, ensure_ascii=False) for r in rows)


def _template(stage):
    with open(os.path.join(PROMPT_DIR, stage["prompt"]), encoding="utf-8") as f:
        return f.read()


def _brief(r):
    b = r("brief") or {}
    if not b:
        return "(brief.json 없음 — 도메인: AI TV 중심의 콘텐츠 감상 경험)"
    return json.dumps(b, ensure_ascii=False, indent=2)


def _need(rows, name):
    if not rows:
        raise FileNotFoundError("입력 없음: {} — 앞 스테이지를 먼저 실행".format(name))
    return rows


def _even(n, cap, parallel):
    """배치 크기 — 등록부의 상한(cap)을 넘지 않으면서, 동시 배치 수(parallel)만큼 고르게 나눈다.
    49행·상한 30·동시 3 이면 30+19 대신 17+17+15 — 한 바퀴에 끝난다."""
    return max(1, min(cap, -(-n // max(1, parallel))))


def baseline_halves(rows):
    """기준선을 둘로 — 짝수 번째(0,2,…)는 40 시나리오에 「피할 방향」으로 보여 주는 몫, 홀수 번째는 50 평가용 보관분.
    config.baseline_split = held·avoid 일 때 쓴다. 평가가 시나리오가 본 목록과 비교하면 외운 목록을 피한 것만 재게 된다."""
    return rows[0::2], rows[1::2]


def _chunks(items, size):
    if not size or len(items) <= size:
        return [items]
    return [items[i:i + size] for i in range(0, len(items), size)]


def _beh_line(b, reason=None):
    d = {"id": b["id"], "kind": b.get("kind"), "action": b.get("action"), "excerpt": b.get("source_excerpt")}
    if b.get("inferred_need"):
        d["inferred_need"] = b["inferred_need"]
    if reason:
        d["why_included"] = reason
    return json.dumps(d, ensure_ascii=False)


def _split(total, parts):
    """total 을 parts 개로 최대한 고르게 (앞쪽이 하나씩 더)."""
    return [total // parts + (1 if i < total % parts else 0) for i in range(parts)]


def _generate_batches(tpl, gt, cfg):
    """01 생성 — tension 을 GEN_GROUP 개씩 묶은 배치 + 무소속·함정 배치 1개. 배치끼리 동시에 돈다.
    ID 는 배치마다 100 단위로 띄우고, 합친 뒤 jobs.finalize 가 전체를 섞어 RAW_001… 로 다시 매긴다."""
    ts = gt.get("tensions", [])
    groups = [ts[i:i + config.GEN_GROUP] for i in range(0, len(ts), config.GEN_GROUP)] or [[]]
    twins = _split(cfg["twin"], len(groups))
    lo, hi = cfg["members"]
    rng = lambda v: "{}~{}".format(*v) if v[0] != v[1] else str(v[0])
    # 정책의 「tension 당 소속 원문」은 member + 그 tension 에 달린 twin·함정의 합이다(QA 도 그렇게 센다).
    # 배치가 함정을 아무 tension 에나 달면 수가 넘친다 — 그래서 twin·부정문 함정이 붙을 tension 을 여기서 정해 주고,
    # 기기·맥락 없음·주입 함정은 무소속으로 만든다. member 는 tension 마다 (목표 − 그 tension 의 twin·함정) 개.
    twin_of = {}
    for i, g in enumerate(groups):
        for j in range(twins[i]):
            if g:
                t = g[j % len(g)]["id"]
                twin_of[t] = twin_of.get(t, 0) + 1
    neg_n = cfg["trap_negation"][1]
    neg_of = {}
    for j in range(neg_n):
        if ts:
            t = ts[j % len(ts)]["id"]
            neg_of[t] = neg_of.get(t, 0) + 1
    self_n = lambda t: twin_of.get(t, 0) + neg_of.get(t, 0)
    out = []
    for i, g in enumerate(groups):
        rows = ["| member | {} (여기에 twin·함정이 더해져 tension 마다 소속 원문이 {}가 된다) |".format(
                    " · ".join("{} {}".format(t["id"], rng((max(1, lo - self_n(t["id"])), max(1, hi - self_n(t["id"])))))
                               for t in g), rng((lo, hi))),
                "| counterexample | {} tension 마다 1 |".format(", ".join(t["id"] for t in g))]
        if twins[i]:
            rows.append("| twin | {} (그 tension 의 member 와 짝) |".format(
                " · ".join("{} {}쌍".format(t["id"], twin_of[t["id"]]) for t in g if twin_of.get(t["id"]))))
        sub_gt = dict(gt, tensions=g)
        sub_gt.pop("distractor_themes", None)
        scope = "| role | 수 |\n|---|---:|\n" + "\n".join(rows)
        out.append({"text": tpl.replace("{{GROUND_TRUTH}}", json.dumps(sub_gt, ensure_ascii=False, indent=2))
                    .replace("{{SCOPE}}", scope).replace("{{ID_START}}", "RAW_{:03d}".format(i * 100 + 1)),
                    "items": [t["id"] for t in g], "index": i})
    rows = ["| distractor | {} |".format(rng(cfg["distractor"])),
            "| false_friend | {} (`looks_like` 는 아래 tension 중에서) |".format(cfg["false_friend"]),
            "| trap_negation | {} — `tension` 은 {} (그 tension 의 member 이면서 부정문) |".format(
                neg_n, " · ".join("{} {}개".format(t, c) for t, c in neg_of.items())),
            "| trap_no_context | {} — `tension: null` (무소속) |".format(rng(cfg["trap_no_context"])),
            "| trap_injection | {} — `tension: null` (무소속) |".format(cfg["trap_injection"]),
            "| (member·counterexample·twin 은 만들지 않는다 — 다른 배치 몫) | 0 |"]
    k = len(groups)
    out.append({"text": tpl.replace("{{GROUND_TRUTH}}", json.dumps(gt, ensure_ascii=False, indent=2))
                .replace("{{SCOPE}}", "| role | 수 |\n|---|---:|\n" + "\n".join(rows))
                .replace("{{ID_START}}", "RAW_{:03d}".format(k * 100 + 1)),
                "items": ["unaffiliated"], "index": k})
    return out


# 짧게 쓰기 (config.brevity = "short") — 출력 길이가 곧 시간이다. 뜻을 버리지 말고 문장 수·글자 수만 줄인다.
SHORT_RULES = {
    "baseline": "각 시나리오의 experience 는 한 문장, mechanism 은 한 구.",
    "extract": "action 은 20자 안팎의 한 구. inferred_need 는 한 구(없으면 null).",
    "link": "label 은 15자 이내, pole_a·pole_b 는 각 한 문장. alternative_interpretations 는 최대 1개.",
    "analogy": "tension 하나당 유추 2개(그중 distant 1개). source_pattern·abstract_mechanism 은 각 한 문장, mapping 2쌍, transfer_limitations 1개.",
    "principle": "statement 는 한 문장 60자 이내. rationale 은 한 문장.",
    "premise": "principle 하나당 미래 가정 1개. what_if·changed_assumption·future_rule 은 각 한 문장, required_changes·tradeoffs 는 각 최대 2개.",
    "scenario": "principle 하나당 scenario 최대 2개(근거로 받칠 수 없으면 1개). title 20자 이내, trigger 한 문장, experience 3문장 이내, failure_case 2문장 이내, assumptions 최대 2개, device_role 한 문장.",
    "judge": "rationale 은 점수를 준 차원마다 20자 안팎의 한 구.",
    "family": "mechanism 은 한 문장, distinct_from 은 한 구.",
}

# 기반 기술 (brief.technology) — 탐색·평가 층이 이 기술 위에서 시나리오를 짓게 한다. 추출·연결(증거 층)에는 붙이지 않는다:
# 원문에서 행동과 욕구를 찾는 일은 기술 관점과 무관해야 한다.
TECH_RULES = {
    "principle": "principle 은 위 기반 기술로 새로 가능해지는 해법 방향을 염두에 두되, 기술 이름을 원리 문장에 쓰지는 않는다.",
    "premise": "미래 가정의 절반 이상은 위 기반 기술이 일상에 보편화된 세계를 전제로 한다.",
    "scenario": ("모든 scenario 는 위 기반 기술 위에서 작동한다. 다음 필드를 더한다: "
                 "`agent_actions`(에이전트가 사람 대신 스스로 하는 일 1~3개, 목록), "
                 "`human_checkpoints`(사람에게 묻거나 확인받는 순간 0~2개, 목록), "
                 "`reversal`(사람이 결과를 되돌리거나 권한을 거두는 방법 한 문장). "
                 "에이전트가 모든 것을 알아서 하는 장면만 쓰지 말고, 위임의 경계가 드러나게 한다."),
    "judge": ("scores 에 차원 `agent_fit` 를 더한다 — 1: 에이전트가 없어도 같다 · 3: 에이전트가 편의만 준다 · "
              "5: 사람 대신 행동하는 것이 경험의 핵심이고 위임·확인·되돌리기가 설계돼 있다."),
}


def build(root, stage_id):
    """스테이지 프롬프트 배치 목록. 실험 설정(짧게 쓰기)과 brief 의 기반 기술에 따라 규칙 블록을 덧붙인다."""
    batches = _build(root, stage_id)
    extra = []
    tech = (store.read(root, "brief") or {}).get("technology")
    if tech and stage_id in TECH_RULES:
        extra.append("## 기반 기술 규칙 (위 규칙과 함께 지킨다)\n\n기반 기술: {}\n\n{}".format(tech, TECH_RULES[stage_id]))
    if config.get(root).get("brevity") == "short" and stage_id in SHORT_RULES:
        extra.append("## 길이 규칙 — 짧게 (위의 개수·분량 규칙보다 이것이 우선한다)\n\n" + SHORT_RULES[stage_id])
    if extra:
        for b in batches:
            b["text"] = b["text"].rstrip() + "\n\n" + "\n\n".join(extra) + "\n"
    return batches


def _package_block(p, ten, beh, ana):
    """30 principle 입력 — 패키지 하나를 사람이 읽는 블록으로."""
    t = ten.get(p["tension_id"], {})
    lines = ["### {} (tension {})".format(p["id"], p["tension_id"]),
             "tension: {} ↔ {}".format(t.get("pole_a"), t.get("pole_b")),
             "relevant (직접 관련 행동):"]
    lines += [_beh_line(beh[b]) for b in p["relevant_ids"] if b in beh]
    lines.append("adjacent (인접 맥락 행동 — 다른 tension·무소속):")
    lines += [_beh_line(beh[b], p.get("reasons", {}).get(b)) for b in p["adjacent_ids"] if b in beh]
    lines.append("counterexample (가정을 뒤집는 행동):")
    lines += [_beh_line(beh[b]) for b in p.get("counterexample_ids", []) if b in beh]
    lines.append("distant analogy (먼 영역 유추):")
    lines += [json.dumps({"id": a, "domain": ana[a].get("source_domain"), "pattern": ana[a].get("source_pattern"),
                          "mechanism": ana[a].get("abstract_mechanism"), "limits": ana[a].get("transfer_limitations"),
                          "why_included": p.get("reasons", {}).get(a)}, ensure_ascii=False)
              for a in p["distant_analogy_ids"] if a in ana]
    return "\n".join(lines)


def _build(root, stage_id):
    stage = registry.get(stage_id)
    if stage["kind"] != "llm":
        raise ValueError("{} 은(는) LLM 스테이지가 아니다".format(stage_id))
    allow_hidden = bool(stage.get("hidden"))

    def r(key):
        if key not in stage["reads"] and key != "brief":
            raise store.BarrierError("{} 은(는) {} 의 선언된 입력이 아니다".format(key, stage_id))
        return store.read(root, key, allow_hidden=allow_hidden)

    tpl = _template(stage)
    fill = lambda body, items, i=0: {"text": tpl.replace("{{INPUT}}", body).replace("{{BRIEF}}", _brief(r)),
                                     "items": items, "index": i}

    cfg = config.get(root)

    if stage_id == "ground_truth":
        if not r("brief"):
            raise FileNotFoundError("brief.json 없음 — 탐색 과제를 먼저 적는다")
        b = fill("", ["brief"])
        n, u = cfg["tensions"], cfg["unfamiliar"]
        b["text"] = (b["text"].replace("{{N_TENSIONS}}", str(n)).replace("{{N_UNFAMILIAR}}", str(u))
                     .replace("{{N_FAMILIAR}}", str(n - u)))
        return [b]

    if stage_id == "generate":
        gt = r("ground_truth")
        if not gt:
            raise FileNotFoundError("hidden/ground_truth.json 없음")
        return _generate_batches(tpl, gt, cfg)

    if stage_id == "baseline":
        b = fill("", [])
        b["text"] = b["text"].replace("{{N_BASELINE}}", str(cfg["baseline"]))
        return [b]

    if stage_id == "extract":
        raw = _need(r("raw"), "raw")
        size = _even(len(raw), stage["batch"][1], cfg["parallel"])
        return [fill(_j(ch, ["id", "raw_text", "source_type"]), [x["id"] for x in ch], i)
                for i, ch in enumerate(_chunks(raw, size))]

    if stage_id == "link":
        beh = _need(r("behaviors"), "behaviors")
        return [fill(_j(beh, ["id", "source_id", "kind", "action", "source_excerpt", "inferred_need"]),
                     [b["id"] for b in beh])]

    if stage_id == "analogy":
        ten = _need(r("tensions"), "tensions")      # tension 당 2~3개라 나눠도 결과가 같다 — 배치끼리 동시에
        return [fill(_j(ch, ["id", "label", "pole_a", "pole_b", "alternative_interpretations"]), [t["id"] for t in ch], i)
                for i, ch in enumerate(_chunks(ten, _even(len(ten), stage["batch"][1], cfg["parallel"])))]

    if stage_id == "principle":
        pk = _need(r("packages"), "packages")
        ten = {t["id"]: t for t in r("tensions") or []}
        beh = {b["id"]: b for b in r("behaviors") or []}
        ana = {a["id"]: a for a in r("analogies") or []}
        out = []
        for i, ch in enumerate(_chunks(pk, _even(len(pk), stage["batch"][1], cfg["parallel"]))):   # 패키지당 1~2개라 나눠도 같다 — 동시에
            out.append(fill("\n\n".join(_package_block(p, ten, beh, ana) for p in ch), [p["id"] for p in ch], i))
        return out


    if stage_id == "premise":
        pri = _need(r("principles"), "principles")
        ten = r("tensions") or []
        ana = r("analogies") or []
        body = "## principles\n{}\n\n## tensions\n{}\n\n## analogies\n{}".format(
            _j(pri, ["id", "statement", "tension_ids", "analogy_ids"]),
            _j(ten, ["id", "label", "pole_a", "pole_b"]),
            _j(ana, ["id", "source_domain", "source_pattern", "abstract_mechanism", "target_tension_ids"]))
        return [fill(body, [p["id"] for p in pri])]

    if stage_id == "scenario":
        pri = _need(r("principles"), "principles")
        prem = r("premises") or []
        ten = {t["id"]: t for t in r("tensions") or []}
        beh = {b["id"]: b for b in r("behaviors") or []}
        ana = {a["id"]: a for a in r("analogies") or []}
        pk_by_t = {}
        for p in r("packages") or []:
            pk_by_t[p["tension_id"]] = p
        batches = []
        for i, ch in enumerate(_chunks(pri, _even(len(pri), stage["batch"][1], cfg["parallel"]))):
            blocks = []
            for p in ch:
                lines = ["### {}: {}".format(p["id"], p["statement"])]
                for tid in p.get("tension_ids", []):
                    t = ten.get(tid, {})
                    pk = pk_by_t.get(tid, {})
                    lines.append("tension {}: {} ↔ {}".format(tid, t.get("pole_a"), t.get("pole_b")))
                    lines.append("사용 가능한 근거 (evidence_ids 는 여기서만 고른다):")
                    for b in t.get("member_ids", []) + t.get("counterexample_ids", []):
                        if b in beh:
                            lines.append(_beh_line(beh[b]))
                    adj = [b for b in pk.get("adjacent_ids", []) if b in beh]
                    if adj:
                        lines.append("인접 맥락 (참고용 — evidence_ids 로 쓰지 않는다):")
                        lines += [_beh_line(beh[b], pk.get("reasons", {}).get(b)) for b in adj]
                ps = [x for x in prem if p["id"] in x.get("principle_ids", [])]
                lines.append("연결된 미래 가정:")
                lines += [_j([x], ["id", "what_if", "future_rule", "horizon", "required_changes", "tradeoffs"]) for x in ps] or ["(없음)"]
                aids = set(p.get("analogy_ids", [])) | {a for x in ps for a in x.get("analogy_ids", [])}
                if aids:
                    lines.append("관련 유추:")
                    lines += [_j([ana[a]], ["id", "source_domain", "abstract_mechanism"]) for a in sorted(aids) if a in ana]
                blocks.append("\n".join(lines))
            body = "\n\n".join(blocks)
            if cfg["baseline_split"] == "avoid" and r("baseline"):
                shown = baseline_halves(r("baseline"))[0]
                body += ("\n\n## 뻔한 방향 (corpus 없이 일반 프롬프트로 나온 시나리오 — 이 메커니즘을 되풀이하지 않는다)\n"
                         "아래와 메커니즘이 같으면 기능 이름을 바꿔도 뻔한 것이다. 근거 행동에서 출발해 여기에 없는 관계를 찾는다.\n"
                         + _j(shown, ["title", "mechanism"]))
            batches.append(fill(body, [p["id"] for p in ch], i))
        return batches

    if stage_id == "judge":
        scn = _need(r("scenarios"), "scenarios")
        beh = {b["id"]: b for b in r("behaviors") or []}
        ten = {t["id"]: t for t in r("tensions") or []}
        prem = {p["id"]: p for p in r("premises") or []}
        base = r("baseline") or []
        if cfg["baseline_split"] in ("held", "avoid"):
            base = baseline_halves(base)[1]                  # 시나리오가 본 적 없는 보관분으로만 비교
        base_txt = _j(base, ["id", "title", "mechanism"]) if base else "(기준선 없음 — similar_baseline_ids 는 빈 목록으로)"
        batches = []
        for i, ch in enumerate(_chunks(scn, _even(len(scn), stage["batch"][1], cfg["parallel"]))):
            blocks = []
            for s in ch:
                lines = ["### {}".format(s["id"]), _j([s], ["title", "trigger", "experience", "assumptions",
                                                           "failure_case", "horizon", "required_capabilities"])]
                for tid in s.get("tension_ids", []):
                    t = ten.get(tid, {})
                    lines.append("tension {}: {} ↔ {}".format(tid, t.get("pole_a"), t.get("pole_b")))
                lines.append("근거:")
                lines += [_beh_line(beh[e]) for e in s.get("evidence_ids", []) if e in beh] or ["(근거 없음)"]
                for pid in s.get("premise_ids", []) or []:
                    if pid in prem:
                        lines.append("미래 가정 {}: {}".format(pid, prem[pid].get("what_if")))
                blocks.append("\n".join(lines))
            body = "## 비교 기준선 (corpus 없이 만든 일반 시나리오)\n{}\n\n## 평가할 시나리오\n{}".format(
                base_txt, "\n\n".join(blocks))
            batches.append(fill(body, [s["id"] for s in ch], i))
        return batches

    if stage_id == "family":
        scn = _need(r("scenarios"), "scenarios")
        pri = r("principles") or []
        body = "## principles\n{}\n\n## scenarios\n{}".format(
            _j(pri, ["id", "statement"]),
            _j(scn, ["id", "title", "trigger", "experience", "principle_ids", "premise_ids"]))
        return [fill(body, [s["id"] for s in scn])]

    if stage_id == "polish":
        items = []
        sl = r("shortlist") if cfg["polish"] == "shortlist" else None
        picks = {p["scenario_id"] for p in (sl or {}).get("picks", [])}
        for key, (_, names) in humanize.TARGETS.items():
            if picks and key != "scenarios":
                continue                      # 후보만 윤문 — 사람이 읽는 것은 후보 시나리오다
            for x in r(key) or []:
                if picks and x["id"] not in picks:
                    continue
                d = {k: x[k] for k in names if x.get(k) not in (None, "", [])}
                if d:
                    items.append(dict({"target_id": x["id"]}, **d))
        _need(items, "scenarios·principles·premises")
        rules = humanize.rules_text()
        out = []
        for i, ch in enumerate(_chunks(items, _even(len(items), stage["batch"][1], cfg["parallel"]))):
            plain = "\n\n".join(v if isinstance(v, str) else "\n".join(v)
                                 for it in ch for k, v in it.items() if k != "target_id")
            metrics = humanize.prescore(plain) or "(정량 사전 점수 없음 — 규칙표만으로 판단)"
            out.append({"text": tpl.replace("{{RULES}}", rules).replace("{{METRICS}}", metrics)
                        .replace("{{INPUT}}", "\n".join(json.dumps(it, ensure_ascii=False) for it in ch))
                        .replace("{{BRIEF}}", _brief(r)),
                        "items": [it["target_id"] for it in ch], "index": i})
        return out

    raise ValueError("프롬프트 조립 규칙이 없는 스테이지: {}".format(stage_id))
