"""70 윤문 — 시나리오·principle·미래 가정의 문장을 사람 글처럼 다듬는다.

윤문 규칙과 사후 검사는 im-not-ai (MIT, vendor/im-not-ai/ · VENDOR.md) 를 그대로 쓴다.
  - 규칙: vendor/.../references/quick-rules.md 를 프롬프트에 싣는다 (탐지·윤문·자체검증을 한 호출에).
  - 검사: vendor/.../scripts/verify_gates.py — LLM 없이 코드로 변경률·수치 소실·서법(당위·추측) 소실을 판정.

원칙: 원본 레코드는 바꾸지 않는다. 윤문본은 data/polish/polished.jsonl 에 따로 두고 화면에서만 갈아 끼운다.
추적(시나리오 → principle → tension → 행동 → 원문)의 근거는 언제나 원본이다.
"""
import json
import os
import subprocess
import sys
import tempfile

from . import store

VENDOR = os.path.join(store.APP_ROOT, "vendor", "im-not-ai")
RULES_PATH = os.path.join(VENDOR, "skills", "humanize-korean", "references", "quick-rules.md")
GATES = os.path.join(VENDOR, "scripts", "verify_gates.py")
PRESCORE = os.path.join(VENDOR, "scripts", "prepare_monolith_input.py")

# 어떤 레코드의 어떤 필드를 윤문하나 — 사람이 읽는 문장만. ID·점수·참조는 대상이 아니다.
TARGETS = {
    "scenarios": ("SCN_", ["title", "trigger", "experience", "assumptions", "failure_case"]),
    "principles": ("PRI_", ["statement"]),
    "premises": ("PREM_", ["what_if", "changed_assumption", "future_rule"]),
}
# 원본에 없는 필드를 윤문본이 새로 가질 수 있다. takeaway = F-1 로 본문 끝에서 옮긴 해석 문장("핵심").
# 게이트는 이 필드를 본문 바로 뒤에 붙여 비교하므로, 옮긴 문장은 삭제가 아니라 이동으로 계산된다.
EXTRA = {"scenarios": ["takeaway"]}
FLAT_ORDER = {"scenarios": ["title", "trigger", "experience", "takeaway", "assumptions", "failure_case"]}
EXIT = {0: "accepted", 1: "warned", 2: "rejected", 3: "unchecked"}


def rules_text():
    with open(RULES_PATH, encoding="utf-8") as f:
        return f.read()


def prescore(text):
    """im-not-ai 정량 사전 점수 블록(표준 경로의 입력 shim). 실패하면 빈 문자열 — 규칙표만으로 윤문한다."""
    with tempfile.TemporaryDirectory(prefix="faultline-prescore-") as d:
        with open(os.path.join(d, "01_input.txt"), "w", encoding="utf-8") as f:
            f.write(text)
        try:
            subprocess.run([sys.executable, PRESCORE, "--run-dir", d, "--genre", "essay"],
                           capture_output=True, text=True, timeout=60)
            with open(os.path.join(d, "01_input_with_metrics.txt"), encoding="utf-8") as f:
                combined = f.read()
        except (OSError, subprocess.TimeoutExpired):
            return ""
    head = combined.split("[원문 시작]")[0].strip()
    return head if head.startswith("[정량") else ""


def _kind(target_id):
    for key, (prefix, _) in TARGETS.items():
        if str(target_id).startswith(prefix):
            return key
    return None


def _flatten(fields, names):
    """검사용 평문 — 필드 순서대로 한 문단씩. 목록 필드는 항목마다 한 줄."""
    out = []
    for n in names:
        v = fields.get(n)
        if isinstance(v, list):
            out += [str(x) for x in v]
        elif v:
            out.append(str(v))
    return "\n\n".join(out) + "\n"


def run_gates(before, after):
    """verify_gates.py 호출 → dict. 실행 불가면 exit_code 3."""
    with tempfile.TemporaryDirectory(prefix="faultline-gate-") as d:
        bp, ap = os.path.join(d, "before.txt"), os.path.join(d, "after.txt")
        with open(bp, "w", encoding="utf-8") as f:
            f.write(before)
        with open(ap, "w", encoding="utf-8") as f:
            f.write(after)
        try:
            p = subprocess.run([sys.executable, GATES, "--before", bp, "--after", ap, "--genre", "essay", "--json"],
                               capture_output=True, text=True, timeout=60)
        except (OSError, subprocess.TimeoutExpired) as e:
            return {"exit_code": 3, "verdict": "검사 실행 실패: {}".format(e)}
    out = p.stdout or ""
    i = out.find("\n{")
    data = {}
    if i >= 0:
        try:
            data = json.loads(out[i + 1:])
        except ValueError:
            data = {}
    code = p.returncode if p.returncode in EXIT else 3
    cr = data.get("change_rate") or {}
    lines = [x for x in out[:i if i >= 0 else len(out)].splitlines() if x.startswith("[P")]
    return {"exit_code": code, "lines": lines,
            "verdict": (data.get("gate") or {}).get("verdict") or (p.stderr or "").strip()[-200:],
            "change_rate": cr.get("rate"),
            "numbers_dropped": data.get("numbers_dropped") or [],
            "modality": (data.get("modality") or {}).get("verdict"),
            "golden": data.get("golden") or []}


def gate(root, rows):
    """모델 출력 검사 + im-not-ai 게이트. (rows, errors, warnings).

    errors  : 형식 오류 (대상 없음·허용 밖 필드·목록 길이 불일치) → 저장 보류
    rejected: 게이트 중단(변경률 50%+) → 레코드는 남기되 status=rejected, 화면은 원문을 보여 준다
    """
    originals = {}
    for key in TARGETS:
        for r in store.read(root, key) or []:
            originals[r["id"]] = r
    errors, warnings = [], []
    seen = set()
    for r in rows:
        tid = r.get("target_id")
        kind = _kind(tid)
        src = originals.get(tid)
        if not kind or not src:
            errors.append("{}: 대상 {} 없음".format(r.get("id"), tid))
            continue
        if tid in seen:
            errors.append("{}: 대상 {} 중복".format(r.get("id"), tid))
        seen.add(tid)
        names = TARGETS[kind][1]
        allowed = names + EXTRA.get(kind, [])
        fields = r.get("fields") or {}
        extra = [k for k in fields if k not in allowed]
        if extra:
            errors.append("{}: 윤문 대상이 아닌 필드 {}".format(r.get("id"), extra))
            continue
        for k, v in fields.items():
            if isinstance(src.get(k), list) and (not isinstance(v, list) or len(v) != len(src[k])):
                errors.append("{}: {} 목록 길이가 원본과 다르다".format(r.get("id"), k))
        # 모델이 빠뜨린 필드는 원문 그대로 — 손대지 않은 것과 같다
        merged = {k: fields.get(k, src.get(k)) for k in names if src.get(k) is not None}
        for k in EXTRA.get(kind, []):
            if isinstance(fields.get(k), str) and fields[k].strip():
                merged[k] = fields[k].strip()
        r["fields"] = merged
        before = {k: src.get(k) for k in names if src.get(k) is not None}
        order = FLAT_ORDER.get(kind, names)
        g = run_gates(_flatten(before, order), _flatten(merged, order))
        r["gate"] = g
        r["status"] = EXIT[g["exit_code"]]
        if r["status"] == "rejected":
            warnings.append("{} ({}): 과윤문 중단 — 원문 유지 · 변경률 {}".format(r["id"], tid, g.get("change_rate")))
        elif r["status"] == "unchecked":
            warnings.append("{} ({}): 게이트 검사 실패 — {}".format(r["id"], tid, g["verdict"]))
    return rows, errors, warnings


def overlay(root):
    """화면용 {target_id: fields} — 게이트를 통과한(accepted·warned) 윤문본만."""
    out = {}
    for r in store.read(root, "polished") or []:
        if r.get("status") in ("accepted", "warned"):
            out[r["target_id"]] = {"fields": r.get("fields") or {}, "status": r["status"],
                                   "change_rate": (r.get("gate") or {}).get("change_rate")}
    return out
