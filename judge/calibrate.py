"""보정(calibration) 측정 — "0.8 이라고 한 판정이 실제로 80% 맞는가".

Jev 는 보정된 확률을 내세운다. 같은 질문을 백엔드별로 돌리고 이 표를 나란히 보면
"Jev 를 쓸 이유가 있는가"(설계 문서 §28.1)에 숫자로 답할 수 있다.

정답(truth)은 {item_id: {question_id: 정답 값}} 모양이다. 모르는 칸은 비워 둔다.
Phase 0 에서는 hidden/labels.json 에서 정답을 만든다 — hidden/ 을 읽는 곳은 이 파일뿐이며 채점 쪽에서만 호출한다.

한계: 원문 100개 안팎이면 구간당 표본이 작아 거친 확인에 그친다. 결과를 임계값 조정 근거로 쓰기 전에 표본 수를 같이 본다.
"""
import json
import os
from collections import Counter


def reliability(pairs, bins=5):
    """pairs = [(확신도, 맞았는가)]. 구간별 표·ECE 반환."""
    table, ece, n = [], 0.0, len(pairs)
    for i in range(bins):
        lo, hi = i / float(bins), (i + 1) / float(bins)
        sel = [(p, ok) for p, ok in pairs if lo <= p < hi or (i == bins - 1 and p == 1.0)]
        if not sel:
            table.append({"bin": "{:.1f}–{:.1f}".format(lo, hi), "n": 0, "conf": None, "acc": None})
            continue
        conf = sum(p for p, _ in sel) / len(sel)
        acc = sum(1 for _, ok in sel if ok) / float(len(sel))
        ece += len(sel) / float(n) * abs(conf - acc)
        table.append({"bin": "{:.1f}–{:.1f}".format(lo, hi), "n": len(sel),
                      "conf": round(conf, 3), "acc": round(acc, 3)})
    return table, (round(ece, 4) if n else None)


def evaluate(records, truth):
    """질문별 정확도·Brier·ECE. 질문 id 의 ':' 뒤(예: context_stated:device)는 한 묶음으로 센다."""
    groups = {}
    for r in records:
        t = truth.get(r["item_id"]) or {}
        for qid, a in r["answers"].items():
            if qid not in t or t[qid] is None:
                continue
            gold = t[qid]
            probs = a["probs"]
            brier = sum((p - (1.0 if v == gold else 0.0)) ** 2 for v, p in probs.items())
            g = groups.setdefault(qid.split(":")[0], {"pairs": [], "brier": [], "methods": Counter()})
            g["pairs"].append((a["p_top"], a["top"] == gold))
            g["brier"].append(brier)
            g["methods"][a.get("method")] += 1
    out = {}
    for qid, g in sorted(groups.items()):
        table, ece = reliability(g["pairs"])
        n = len(g["pairs"])
        out[qid] = {"n": n, "accuracy": round(sum(ok for _, ok in g["pairs"]) / float(n), 3),
                    "brier": round(sum(g["brier"]) / n, 4), "ece": ece, "table": table,
                    "methods": dict(g["methods"])}
    return out


# ---------------------------------------------------------------- Phase 0 정답 만들기 (hidden 사용)

def phase0_truth(root, task, records):
    fp = os.path.join(root, "hidden", "labels.json")
    if not os.path.exists(fp):
        raise FileNotFoundError(fp)
    with open(fp, encoding="utf-8") as f:
        labels = json.load(f)
    beh_fp = os.path.join(root, "data", "extracted", "behaviors.jsonl")
    src_of = {}
    with open(beh_fp, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("//"):
                b = json.loads(line)
                src_of[b["id"]] = b.get("source_id")

    truth = {}
    if task == "extract_check":
        for r in records:
            lab = labels.get(src_of.get(r["item_id"])) or {}
            t = {"instruction_in_source": "yes" if (lab.get("injection_token") or lab.get("role") == "trap_injection")
                 else "no"} if lab else {}
            for f in lab.get("context_absent") or []:
                t["context_stated:" + f] = "no"      # 없는 것만 확실히 안다. 있는 쪽은 라벨이 말하지 않는다
            truth[r["item_id"]] = t
        return truth, "instruction_in_source · context_stated(부재 쪽만)"

    if task == "assign":
        # 후보 → 숨은 tension 대응은 판단이 배정한 행동들의 다수결로 정한다 (score.py 의 방식과 같다).
        # 판단 자신의 답으로 대응을 만들므로 정확도가 다소 부풀 수 있다.
        votes = {}
        for r in records:
            tid = r["result"]["tension_id"]
            ht = (labels.get(src_of.get(r["item_id"])) or {}).get("tension")
            if tid:
                votes.setdefault(tid, Counter())[ht] += 1
        cand_to_ht = {tid: c.most_common(1)[0][0] for tid, c in votes.items()}
        ht_to_cands = {}
        for tid, ht in cand_to_ht.items():
            if ht:
                ht_to_cands.setdefault(ht, []).append(tid)
        for r in records:
            lab = labels.get(src_of.get(r["item_id"])) or {}
            ht = lab.get("tension")
            t = {}
            if not lab:
                pass
            elif ht is None:
                t["tension"] = "NONE"
            elif len(ht_to_cands.get(ht, [])) == 1:
                t["tension"] = ht_to_cands[ht][0]
                if r["result"]["tension_id"] == t["tension"]:
                    t["role"] = "COUNTER" if lab.get("role") == "counterexample" else "MEMBER"
            # 숨은 tension 에 대응하는 후보가 없거나 여럿이면 정답을 정하지 않는다 (후보 생성 문제이지 판단 문제가 아니다)
            truth[r["item_id"]] = t
        return truth, "tension · role (후보↔정답 대응은 다수결)"

    raise ValueError("Phase 0 정답은 extract_check · assign 만 만들 수 있다")
