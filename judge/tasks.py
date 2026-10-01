"""태스크 = (Faultline 레코드 → 상태 텍스트) + (질문 은행) + (답 조합 규칙).

Jev 는 "구조화된 프로그램 상태"를 입력으로 받고, 복잡한 판단을 작은 질문으로 쪼개 코드에서 조합하라고 권한다.
그래서 태스크마다 세 부분만 정의한다:
  items()          판단할 단위와 그 상태 텍스트 (필요한 필드만, 라벨 붙여서)
  questions        질문 은행에서 꺼낸 원자 질문
  run_item()       답을 받아 조합한 결과 — 확정·검토 경로와 이유

태스크는 data/ 만 읽는다. hidden/ 은 읽지 않는다 (정답 대조는 calibrate.py 만 한다).
"""
import hashlib
import os

from . import store
from .policy import decide


def _hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def ask(backend, state, questions):
    """{question_id: (Answer, decision)}"""
    answers = backend.ask(state, questions)
    return {qid: (a, decide(a)) for qid, a in answers.items()}


def pack_answers(judged):
    out = {}
    for qid, (a, d) in judged.items():
        row = a.to_dict()
        row.update(d)
        out[qid] = row
    return out


def reviews_of(judged):
    return sorted(qid for qid, (_, d) in judged.items() if d["decision"] == "review")


def behavior_lines(b, raw_text=None):
    lines = []
    if raw_text is not None:
        lines += ["원문 [{}]:".format(b.get("source_id")), raw_text.strip(), ""]
    lines += ["추출된 행동 [{}]:".format(b["id"]),
              "- kind: {}".format(b.get("kind")),
              "- action: {}".format(b.get("action")),
              "- source_excerpt: {}".format(b.get("source_excerpt"))]
    for k, v in sorted((b.get("context") or {}).items()):
        if v is not None:
            lines.append("- context.{}: {}".format(k, v))
    return lines


class Task:
    name = None
    bank_name = None

    def __init__(self, root, bank_version=None, **opts):
        self.root = root
        self.bank = store.load_bank(self.bank_name, bank_version)
        self.opts = opts

    def items(self):
        raise NotImplementedError

    def run_item(self, backend, item):
        raise NotImplementedError

    def record(self, item, judged, result):
        return {"task": self.name, "bank": self.bank["_tag"], "item_id": item["id"],
                "state_hash": _hash(item["state"]), "state": item["state"],
                "answers": pack_answers(judged), "result": result, "is_synthetic": True}

    def summarize(self, records):
        return {}


# ---------------------------------------------------------------- 10 뒤: 추출 검사

class ExtractCheck(Task):
    name = "extract_check"
    bank_name = "extract_check"

    def items(self):
        raw = {r["id"]: r for r in store.load_data(self.root, "raw")}
        out = []
        for b in store.load_data(self.root, "behaviors"):
            src = raw.get(b.get("source_id"))
            state = "\n".join(behavior_lines(b, src["raw_text"] if src else "(원문 없음)"))
            out.append({"id": b["id"], "state": state, "behavior": b})
        return out

    def questions_for(self, b):
        qs = [store.bank_question(self.bank, "excerpt_supports_action"),
              store.bank_question(self.bank, "polarity")]
        labels = self.bank["context_field_labels"]
        for field, v in sorted((b.get("context") or {}).items()):
            if v is not None:
                qs.append(store.bank_question(self.bank, "context_stated", id_suffix=field,
                                              field_label=labels.get(field, field)))
        qs += [store.bank_question(self.bank, "instruction_in_source"),
               store.bank_question(self.bank, "follows_instruction")]
        return qs

    def run_item(self, backend, item):
        judged = ask(backend, item["state"], self.questions_for(item["behavior"]))
        val = {qid: d["value"] for qid, (_, d) in judged.items()}
        flags = []
        if val.get("excerpt_supports_action") is False:
            flags.append("not_grounded")
        if val.get("polarity") == "FLIPPED" and judged["polarity"][1]["decision"] == "accept":
            flags.append("polarity_flip")
        for qid, v in val.items():
            if qid.startswith("context_stated:") and v is False:
                flags.append("hallucinated_context:" + qid.split(":", 1)[1])
        if val.get("instruction_in_source") and val.get("follows_instruction"):
            flags.append("injection_followed")
        reviews = reviews_of(judged)
        verdict = "flag" if flags else ("review" if reviews else "pass")
        return self.record(item, judged, {"verdict": verdict, "flags": flags, "review": reviews,
                                          "instruction_present": bool(val.get("instruction_in_source"))})

    def summarize(self, records):
        c = {}
        for r in records:
            c[r["result"]["verdict"]] = c.get(r["result"]["verdict"], 0) + 1
            for f in r["result"]["flags"]:
                key = f.split(":")[0]
                c[key] = c.get(key, 0) + 1
        return c


# ---------------------------------------------------------------- 20b: 행동 → tension 배정

class Assign(Task):
    name = "assign"
    bank_name = "assign"

    def candidates(self):
        """20a 출력(tension_candidates.jsonl) 우선. 없으면 기존 tensions.jsonl 의 두 극만 쓴다."""
        path = self.opts.get("candidates")
        if path:
            fp = path if os.path.isabs(path) else os.path.join(self.root, path)
            return store.load_jsonl(fp), fp
        rows = store.load_data(self.root, "candidates", required=False)
        if rows is not None:
            return rows, store.DATA["candidates"]
        return store.load_data(self.root, "tensions"), store.DATA["tensions"] + " (member 무시, 두 극만 사용)"

    def items(self):
        self.cands, self.cand_source = self.candidates()
        self.cand_by_id = {c["id"]: c for c in self.cands}
        raw = {r["id"]: r for r in store.load_data(self.root, "raw")}
        out = []
        for b in store.load_data(self.root, "behaviors"):
            src = raw.get(b.get("source_id"))
            state = "\n".join(behavior_lines(b, src["raw_text"] if src else None))
            out.append({"id": b["id"], "state": state, "behavior": b})
        return out

    def tension_question(self):
        opts = [{"value": c["id"], "desc": "{}: {} ↔ {}".format(c.get("label"), c.get("pole_a"), c.get("pole_b"))}
                for c in self.cands]
        opts.append(self.bank["none_option"])
        return store.bank_question(self.bank, "tension", options=opts)

    def run_item(self, backend, item):
        judged = ask(backend, item["state"], [self.tension_question()])
        a_t, d_t = judged["tension"]
        ranked = a_t.ranked()
        top = a_t.top
        result = {"tension_id": None if top == "NONE" else top, "p": round(a_t.p_top, 4),
                  "margin": round(a_t.margin, 4),
                  "alt": ranked[1][0] if len(ranked) > 1 else None, "role": None}
        if top != "NONE":                                # 두 번째 질문은 첫 답에 따라 만든다
            c = self.cand_by_id[top]
            role_q = store.bank_question(self.bank, "role", label=c.get("label"),
                                         pole_a=c.get("pole_a"), pole_b=c.get("pole_b"))
            judged.update(ask(backend, item["state"], [role_q]))
            result["role"] = judged["role"][1]["value"]
        reviews = reviews_of(judged)
        result["decision"] = "review" if reviews else "accept"
        result["review"] = reviews
        return self.record(item, judged, result)

    def summarize(self, records):
        c = {"accept": 0, "review": 0, "none": 0}
        for r in records:
            c[r["result"]["decision"]] += 1
            if r["result"]["tension_id"] is None:
                c["none"] += 1
        return c

    def emit_tensions(self, records, include_review=False):
        """배정 결과 → tensions.jsonl 과 같은 모양. 파이프라인 파일은 건드리지 않고 판단 실행 폴더에만 쓴다."""
        keep = [r for r in records if include_review or r["result"]["decision"] == "accept"]
        rows, dropped = [], []
        for c in self.cands:
            members = [r["item_id"] for r in keep
                       if r["result"]["tension_id"] == c["id"] and r["result"]["role"] == "MEMBER"]
            counters = [r["item_id"] for r in keep
                        if r["result"]["tension_id"] == c["id"] and r["result"]["role"] == "COUNTER"]
            if len(members) < self.bank.get("min_members", 3):
                dropped.append({"id": c["id"], "members": len(members)})
                continue
            rows.append({"id": c["id"], "label": c.get("label"), "pole_a": c.get("pole_a"),
                         "pole_b": c.get("pole_b"), "member_ids": members, "counterexample_ids": counters,
                         "alternative_interpretations": c.get("alternative_interpretations") or [],
                         "is_synthetic": True})
        return rows, dropped


# ---------------------------------------------------------------- 40 뒤: 시나리오 지도화 (TV)

QUADRANTS = {
    (True, True): "적극 검토 (근거↑ 새로움↑)",
    (True, False): "개선·실행 후보 (근거↑ 새로움↓)",
    (False, True): "사변적 질문 후보 (근거↓ 새로움↑)",
    (False, False): "낮은 우선순위 (근거↓ 새로움↓)",
}


class ScenarioMapTV(Task):
    name = "scenario_map_tv"
    bank_name = "scenario_map_tv"

    def items(self):
        beh = {b["id"]: b for b in store.load_data(self.root, "behaviors")}
        ten = {t["id"]: t for t in (store.load_data(self.root, "tensions", required=False) or [])}
        out = []
        for s in store.load_data(self.root, "scenarios"):
            lines = ["시나리오 [{}] {}".format(s["id"], s.get("title")),
                     "- trigger: {}".format(s.get("trigger")),
                     "- experience: {}".format(s.get("experience")),
                     "- 가정: {}".format("; ".join(s.get("assumptions") or []) or "(없음)"),
                     "- 실패 사례: {}".format(s.get("failure_case"))]
            for tid in s.get("tension_ids") or []:
                t = ten.get(tid)
                if t:
                    lines.append("- 긴장 {}: {} ↔ {}".format(tid, t.get("pole_a"), t.get("pole_b")))
            lines.append("연결된 근거:")
            for eid in s.get("evidence_ids") or []:
                b = beh.get(eid)
                lines.append("- {} ({}) {} — 구절: \"{}\"".format(eid, b.get("kind"), b.get("action"),
                                                               b.get("source_excerpt")) if b
                             else "- {} (찾을 수 없음)".format(eid))
            out.append({"id": s["id"], "state": "\n".join(lines)})
        return out

    def run_item(self, backend, item):
        qs = [store.bank_question(self.bank, q["id"]) for q in self.bank["questions"]]
        judged = ask(backend, item["state"], qs)
        axes = {qid: d["value"] for qid, (_, d) in judged.items()}
        th = self.bank.get("quadrant_threshold", 3.5)
        g, n = axes.get("grounding"), axes.get("cliche_distance")
        quadrant = QUADRANTS[(g >= th, n >= th)] if g is not None and n is not None else None
        rf = axes.get("requires_future_change")
        result = {"axes": axes, "quadrant": quadrant,
                  "horizon_hint": None if rf is None else ("possible (조건부 미래)" if rf else "plausible 이하"),
                  "contradiction": axes.get("self_contradiction"),
                  "review": reviews_of(judged)}
        return self.record(item, judged, result)

    def summarize(self, records):
        c = {}
        for r in records:
            k = r["result"]["quadrant"] or "미정"
            c[k] = c.get(k, 0) + 1
        return c


TASKS = {t.name: t for t in (ExtractCheck, Assign, ScenarioMapTV)}
