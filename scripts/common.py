"""공통 유틸: 경로와 JSONL 입출력. Python 3.7+, 표준 라이브러리만."""
import argparse
import json
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PATHS = {
    "ground_truth": "hidden/ground_truth.json",
    "corpus_labeled": "hidden/corpus_labeled.jsonl",
    "labels": "hidden/labels.json",
    "raw": "data/raw/raw.jsonl",
    "behaviors": "data/extracted/behaviors.jsonl",
    "tensions": "data/linked/tensions.jsonl",
    "principles": "data/linked/principles.jsonl",
    "scenarios": "data/scenarios/scenarios.jsonl",
}


def root_parser(description):
    p = argparse.ArgumentParser(description=description)
    p.add_argument("--root", default=".",
                   help="작업 루트 (기본: 프로젝트 루트). 예: examples/mini")
    return p


def resolve_root(root):
    if os.path.isabs(root):
        return root
    return os.path.normpath(os.path.join(PROJECT_ROOT, root))


def path(root, key):
    return os.path.join(root, PATHS[key])


def load_jsonl(fp, required=True):
    if not os.path.exists(fp):
        if required:
            sys.exit("파일 없음: {}".format(fp))
        return None
    rows = []
    with open(fp, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            line = line.strip()
            if not line or line.startswith("//"):
                continue
            try:
                rows.append(json.loads(line))
            except ValueError as e:
                sys.exit("{}:{} JSON 오류: {}".format(fp, n, e))
    return rows


def write_jsonl(fp, rows):
    os.makedirs(os.path.dirname(fp), exist_ok=True)
    with open(fp, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def load_json(fp, required=True):
    if not os.path.exists(fp):
        if required:
            sys.exit("파일 없음: {}".format(fp))
        return None
    with open(fp, encoding="utf-8") as f:
        return json.load(f)


def write_json(fp, obj):
    os.makedirs(os.path.dirname(fp), exist_ok=True)
    with open(fp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")


def squash(s):
    """공백 차이를 무시한 비교용 문자열."""
    return "".join((s or "").split())
