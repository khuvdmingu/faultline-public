"""판단 모듈 전용 입출력. 파이프라인 scripts/ 에 의존하지 않도록 따로 둔다 (모듈 단독 이식용)."""
import glob
import json
import os

from .schema import Question

JUDGE_DIR = os.path.dirname(os.path.abspath(__file__))
BANK_DIR = os.path.join(JUDGE_DIR, "bank")

# 파이프라인 데이터 위치 — scripts/common.py 의 PATHS 와 같게 유지한다
DATA = {
    "raw": "data/raw/raw.jsonl",
    "behaviors": "data/extracted/behaviors.jsonl",
    "candidates": "data/linked/tension_candidates.jsonl",
    "tensions": "data/linked/tensions.jsonl",
    "scenarios": "data/scenarios/scenarios.jsonl",
}


def load_jsonl(fp):
    rows = []
    with open(fp, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("//"):
                rows.append(json.loads(line))
    return rows


def load_data(root, key, required=True):
    fp = os.path.join(root, DATA[key])
    if not os.path.exists(fp):
        if required:
            raise FileNotFoundError(fp)
        return None
    return load_jsonl(fp)


def write_jsonl(fp, rows):
    os.makedirs(os.path.dirname(fp), exist_ok=True)
    with open(fp, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def write_json(fp, obj):
    os.makedirs(os.path.dirname(fp), exist_ok=True)
    with open(fp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")


def list_banks():
    return sorted(glob.glob(os.path.join(BANK_DIR, "*.json")))


def load_bank(name, version=None):
    """bank/<name>.<version>.json. version 이 없으면 사전순 마지막 판."""
    files = sorted(glob.glob(os.path.join(BANK_DIR, "{}.*.json".format(name))))
    if version:
        files = [f for f in files if f.endswith(".{}.json".format(version))]
    if not files:
        raise FileNotFoundError("질문 은행 없음: {} {}".format(name, version or ""))
    with open(files[-1], encoding="utf-8") as f:
        bank = json.load(f)
    bank["_tag"] = "{}@{}".format(bank["bank"], bank["version"])
    return bank


def bank_question(bank, qid, **fmt):
    """은행의 질문 정의 → Question. fmt 는 text 의 {자리}를 채운다. 옵션을 바꾸려면 options= 로 넘긴다."""
    spec = next(q for q in bank["questions"] if q["id"] == qid)
    options = fmt.pop("options", None) or spec.get("options")
    suffix = fmt.pop("id_suffix", None)
    return Question(id=qid + (":" + suffix if suffix else ""), kind=spec["kind"],
                    text=spec["text"].format(**fmt) if fmt else spec["text"],
                    options=options, policy=spec.get("policy"),
                    unknown_value=spec.get("unknown_value"), bank=bank["_tag"])
