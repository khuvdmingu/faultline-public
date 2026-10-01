"""합성 corpus 품질 검사 — docs/DATA_GENERATION_POLICY.md 의 규칙을 코드로 집행한다.

검사는 권고(advisory)다. split 은 구조 오류만 막고, 여기서 FAIL 이 나오면
"재생성 권장"으로 표시하고 채점 결과를 읽을 때 함께 본다 (정책 §7).
"""
from collections import Counter

from . import config, store

# 정책 §3·§4 의 수치 — 바꾸면 정책 문서도 함께 고친다
ROLE_RULES = {
    "per_tension_members": (8, 12),
    "distractor": (15, 20),              # distractor 역할 수. 무소속 전체는 여기에 false_friend·함정이 더해진다
    "twin": (5, 5),
    "false_friend": (5, 5),
    "trap_negation": (3, 4),
    "trap_no_context": (3, 4),
    "trap_injection": (3, 3),
}
STYLE_RULES = [("short_no_motive", ">=", 0.40), ("slang", ">=", 0.20),
               ("long_motive", "<=", 0.25), ("sarcasm", ">=", 0.05)]
POLE_OVERLAP_MAX = 0.6    # 극 문장 6-gram 의 몇 %가 원문에 그대로 있으면 누출로 보나
SEED_OVERLAP_MAX = 0.7
ROLE_SHUFFLE_MIN = 0.3    # role 이 바뀌는 비율 — 낮으면 role 별로 몰아 쓴 것


def _grams(s, n=6):
    s = store.squash(s)
    return {s[i:i + n] for i in range(max(0, len(s) - n + 1))}


def _overlap(src, text):
    g = _grams(src)
    if not g:
        return 0.0
    t = store.squash(text)
    return sum(1 for x in g if x in t) / len(g)


def _check(name, ok, value, rule, level_fail="fail"):
    return {"check": name, "status": "pass" if ok else level_fail, "value": value, "rule": rule}


def run(root):
    rows = store.read(root, "corpus_labeled", allow_hidden=True)
    gt = store.read(root, "ground_truth", allow_hidden=True) or {}
    if rows is None:
        return None
    n = len(rows)
    labs = [(r, r.get("label") or {}) for r in rows]
    checks = []
    rules = config.qa_rules(root)          # 실험 크기(config.json)에 맞춘 수치. ROLE_RULES 는 표준 크기 기록용

    tensions = [t["id"] for t in gt.get("tensions", [])]
    lo, hi = rules["per_tension_members"]
    for ht in tensions:
        c = sum(1 for r, l in labs if l.get("tension") == ht and l.get("role") != "counterexample")
        checks.append(_check("{} 소속 원문 수".format(ht), lo <= c <= hi, c, "{}~{}".format(lo, hi)))
        ce = sum(1 for r, l in labs if l.get("tension") == ht and l.get("role") == "counterexample")
        checks.append(_check("{} 반례".format(ht), ce == 1, ce, "= 1", "warn"))

    roles = Counter(l.get("role") for _, l in labs)
    for role in ("distractor", "twin", "false_friend", "trap_negation", "trap_no_context", "trap_injection"):
        lo, hi = rules[role]
        c = roles.get(role, 0)
        checks.append(_check("role {}".format(role), lo <= c <= hi, c, "{}~{}".format(lo, hi) if lo != hi else "= {}".format(lo)))

    styles = Counter(r.get("style") for r, _ in labs)
    for style, op, th in STYLE_RULES:
        share = styles.get(style, 0) / n if n else 0
        ok = share >= th if op == ">=" else share <= th
        checks.append(_check("문체 {}".format(style), ok, round(share, 2), "{} {}".format(op, th)))

    # 누출: 정답표 문장을 그대로 베꼈는가
    poles = [(t["id"], t.get("pole_a", "")) for t in gt.get("tensions", [])] + \
            [(t["id"], t.get("pole_b", "")) for t in gt.get("tensions", [])]
    seeds = [(t["id"], s) for t in gt.get("tensions", []) for s in t.get("behavior_seeds", [])]
    pole_hits = [r["id"] for r, _ in labs for _, p in poles if _overlap(p, r.get("raw_text")) >= POLE_OVERLAP_MAX]
    seed_hits = [r["id"] for r, _ in labs for _, s in seeds if _overlap(s, r.get("raw_text")) >= SEED_OVERLAP_MAX]
    checks.append(_check("극 문장 그대로 사용", not pole_hits, sorted(set(pole_hits)), "없음"))
    checks.append(_check("씨앗 문장 그대로 사용", not seed_hits, sorted(set(seed_hits)), "없음", "warn"))
    id_leak = [r["id"] for r, _ in labs if "HT_" in (r.get("raw_text") or "")]
    checks.append(_check("원문에 정답 ID 노출", not id_leak, id_leak, "없음"))

    # 구조
    ids = {r["id"] for r, _ in labs}
    by_id = {r["id"]: l for r, l in labs}
    bad_twin = [r["id"] for r, l in labs if l.get("role") == "twin" and
                (l.get("twin_of") not in ids or by_id.get(l.get("twin_of"), {}).get("tension") != l.get("tension")
                 or l.get("twin_of") == r["id"])]
    checks.append(_check("쌍둥이 짝 일관성", not bad_twin, bad_twin, "짝이 존재하고 같은 tension"))
    bad_inj = [r["id"] for r, l in labs if l.get("role") == "trap_injection" and
               (not l.get("injection_token") or l["injection_token"] not in (r.get("raw_text") or ""))]
    checks.append(_check("주입 토큰이 원문에 있음", not bad_inj, bad_inj, "모두"))
    bad_ff = [r["id"] for r, l in labs if l.get("role") == "false_friend" and
              (not l.get("looks_like") or l.get("looks_like") == l.get("tension"))]
    checks.append(_check("거짓 친구 looks_like", not bad_ff, bad_ff, "겉보기 ≠ 실제"))
    texts = Counter(store.squash(r.get("raw_text")) for r, _ in labs)
    dup = [t for t, c in texts.items() if c > 1]
    checks.append(_check("중복 원문", not dup, len(dup), "0"))
    changes = sum(1 for i in range(1, n) if labs[i][1].get("role") != labs[i - 1][1].get("role"))
    shuffle = changes / (n - 1) if n > 1 else 1.0
    checks.append(_check("role 순서 섞임", shuffle >= ROLE_SHUFFLE_MIN, round(shuffle, 2), ">= {}".format(ROLE_SHUFFLE_MIN), "warn"))

    n_fail = sum(c["status"] == "fail" for c in checks)
    n_warn = sum(c["status"] == "warn" for c in checks)
    return {"total": n, "roles": dict(roles), "styles": dict(styles), "checks": checks,
            "fail": n_fail, "warn": n_warn,
            "verdict": "재생성 권장" if n_fail else ("주의" if n_warn else "통과")}
