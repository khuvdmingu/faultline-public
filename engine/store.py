"""파일 저장소. 실험 하나 = 디렉터리 하나(root). 모든 산출물은 키로 접근한다.

root/
  hidden/   평가자 영역 — 정답표·라벨. 파이프라인 스테이지는 읽지 못한다.
  data/     파이프라인 영역 — 엔티티별 JSONL.
  review/   인간 검토 결정.
  runs/     작업 기록·원본 모델 출력·채점 결과.
"""
import datetime
import json
import os
import shutil
import threading

APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXPERIMENT_BASES = ("experiments", "examples")

# 키 → (상대 경로, 영역). 영역이 hidden 인 키는 registry 가 허용한 스테이지만 읽는다.
FILES = {
    "ground_truth":   ("hidden/ground_truth.json", "hidden"),
    "corpus_labeled": ("hidden/corpus_labeled.jsonl", "hidden"),
    "labels":         ("hidden/labels.json", "hidden"),
    "brief":          ("brief.json", "data"),
    "raw":            ("data/raw/raw.jsonl", "data"),
    "baseline":       ("data/baseline/baseline.jsonl", "data"),
    "behaviors":      ("data/extracted/behaviors.jsonl", "data"),
    "tensions":       ("data/linked/tensions.jsonl", "data"),
    "tensions_link":  ("data/linked/tensions_link.jsonl", "data"),   # 22 판단 필터 전 20 연결 원본
    "analogies":      ("data/explore/analogies.jsonl", "data"),
    "packages":       ("data/explore/packages.jsonl", "data"),
    "principles":     ("data/linked/principles.jsonl", "data"),
    "premises":       ("data/explore/premises.jsonl", "data"),
    "scenarios":      ("data/scenarios/scenarios.jsonl", "data"),
    "evaluations":    ("data/evaluate/evaluations.jsonl", "data"),
    "families":       ("data/evaluate/families.jsonl", "data"),
    "polished":       ("data/polish/polished.jsonl", "data"),
    "shortlist":      ("data/shortlist/shortlist.json", "data"),
    "decisions":      ("review/decisions.jsonl", "review"),
}


class BarrierError(PermissionError):
    """정보 차단선 위반 — 파이프라인 스테이지가 hidden/ 을 읽으려 했다."""


def now():
    return datetime.datetime.now().isoformat(timespec="seconds")


def list_roots():
    out = []
    for base in EXPERIMENT_BASES:
        d = os.path.join(APP_ROOT, base)
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            full = os.path.join(d, name)
            if os.path.isdir(os.path.join(full, "hidden")) or os.path.isdir(os.path.join(full, "data")):
                out.append("{}/{}".format(base, name))
    return out


def resolve(rel):
    """실험 상대 경로 → 절대 경로. 등록된 실험만 허용 (경로 탈출 방지)."""
    if os.path.isabs(rel):
        rel = os.path.relpath(rel, APP_ROOT)
    rel = rel.strip("/").replace("\\", "/")
    if rel not in list_roots():
        raise ValueError("알 수 없는 실험: {}".format(rel))
    return os.path.join(APP_ROOT, rel)


def path(root, key):
    return os.path.join(root, FILES[key][0])


def zone(key):
    return FILES[key][1]


def exists(root, key):
    return os.path.exists(path(root, key))


def read(root, key, default=None, allow_hidden=False):
    """hidden/ 키는 기본으로 막는다. 평가자 코드(qa·scoring·split·평가자 모드 화면)만 allow_hidden=True 를 넘긴다."""
    if not allow_hidden and zone(key) == "hidden":
        raise BarrierError("{} 은(는) hidden/ 에 있다 — 이 스테이지는 읽을 수 없다".format(key))
    fp = path(root, key)
    if not os.path.exists(fp):
        return default
    with open(fp, encoding="utf-8") as f:
        if fp.endswith(".jsonl"):
            rows = []
            for n, line in enumerate(f, 1):
                line = line.strip()
                if not line or line.startswith("//"):
                    continue
                try:
                    rows.append(json.loads(line))
                except ValueError as e:
                    raise ValueError("{}:{} JSON 오류: {}".format(FILES[key][0], n, e))
            return rows
        return json.load(f)


def atomic_json(fp, obj, lines=False):
    """임시 파일에 다 쓴 뒤 os.replace — 읽는 쪽이 반쯤 쓴 파일을 보지 않는다(병렬 배치·폴링 경합)."""
    os.makedirs(os.path.dirname(fp), exist_ok=True)
    tmp = "{}.tmp{}-{}".format(fp, os.getpid(), threading.get_ident())
    with open(tmp, "w", encoding="utf-8") as f:
        if lines:
            for r in obj:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        else:
            json.dump(obj, f, ensure_ascii=False, indent=2)
            f.write("\n")
    os.replace(tmp, fp)
    return fp


def write(root, key, obj, keep_prev=True):
    """저장. 기존 파일은 .prev 로 1개 보관한다."""
    fp = path(root, key)
    if keep_prev and os.path.exists(fp):
        shutil.copyfile(fp, fp + ".prev")
    return atomic_json(fp, obj, lines=fp.endswith(".jsonl"))


def append(root, key, row):
    fp = path(root, key)
    os.makedirs(os.path.dirname(fp), exist_ok=True)
    with open(fp, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


def info(root, key):
    fp = path(root, key)
    if not os.path.exists(fp):
        return {"exists": False, "count": 0, "updated": None}
    obj = read(root, key, allow_hidden=True)      # 개수 세기만 — 내용은 밖으로 내보내지 않는다
    if isinstance(obj, list):
        n = len(obj)
    elif isinstance(obj, dict) and "tensions" in obj:
        n = len(obj["tensions"])
    else:
        n = len(obj or {})
    ts = datetime.datetime.fromtimestamp(os.path.getmtime(fp)).isoformat(timespec="minutes")
    return {"exists": True, "count": n, "updated": ts}


def run_dir(root, *parts):
    d = os.path.join(root, "runs", *parts)
    os.makedirs(d, exist_ok=True)
    return d


def write_run_json(root, rel, obj):
    return atomic_json(os.path.join(root, "runs", rel), obj)


def squash(s):
    """공백 차이를 무시한 비교용 문자열."""
    return "".join((s or "").split())
