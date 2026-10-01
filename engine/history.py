"""실행 기록 — 자동 실행 한 번이 끝날 때마다(끝남·멈춤 모두) 요약 한 장을 runs/history/<실행 ID>.json 에 남긴다.

데이터 자체는 여전히 덮어쓴다(직전 1판만 .prev). 여기 남는 건 비교에 필요한 숫자뿐이다:
설정 · 스테이지별 시간과 행 수 · 산출물 개수 · 글 길이 · (이번 실행에서 채점했으면) Phase 0 판정.
그래서 크기·길이·흐름 옵션을 바꿔 가며 돌린 결과를 나란히 놓고 볼 수 있다.

채점 결과는 평가자 정보다. 요약에는 지표 이름·값·판정만 담고 정답 tension 내용은 담지 않는다.
"""
import datetime
import json
import os

from . import config, store

COUNT_KEYS = ["raw", "behaviors", "tensions", "principles", "premises", "scenarios", "families", "shortlist"]
TEXT_KEYS = ["principles", "premises", "scenarios"]      # 글 길이를 재는 층 (brevity 효과 확인용)


def _dir(root):
    return os.path.join(root, "runs", "history")


def _secs(a, b):
    try:
        return int((datetime.datetime.fromisoformat(b) - datetime.datetime.fromisoformat(a)).total_seconds())
    except (TypeError, ValueError):
        return None


def _chars(rec):
    """사람이 읽는 글자 수 — 문자열 필드와 문자열 목록의 합. id·*_ids 참조는 뺀다."""
    n = 0
    for k, v in rec.items():
        if k == "id" or k.endswith("_ids"):
            continue
        if isinstance(v, str):
            n += len(v)
        elif isinstance(v, list):
            n += sum(len(x) for x in v if isinstance(x, str))
        elif isinstance(v, dict):
            n += _chars(v)
    return n


def text_stats(root):
    """레코드당 평균 글자 수."""
    out = {}
    for key in TEXT_KEYS:
        rows = store.read(root, key) or []
        if rows:
            out[key] = round(sum(_chars(r) for r in rows) / len(rows))
    return out


def summarize(root, st):
    steps = []
    for s in st.get("steps", []):
        steps.append({"stage": s["stage"], "status": s.get("status"), "rows": s.get("rows"),
                      "secs": _secs(s.get("started"), s.get("finished")), "note": s.get("note")})
    counts = {}
    for k in COUNT_KEYS:
        obj = store.read(root, k)
        if obj is None:
            continue
        counts[k] = len(obj["picks"]) if k == "shortlist" else len(obj)
    score = None
    ran_score = any(s["stage"] == "score" and s.get("status") == "done" for s in st.get("steps", []))
    fp = os.path.join(root, "runs", "score", "phase0.json")
    if ran_score and os.path.exists(fp):
        with open(fp, encoding="utf-8") as f:
            res = json.load(f)
        vs = [{"metric": v["metric"], "value": v["value"], "verdict": v["verdict"], "n": v.get("n")}
              for v in res["verdicts"]]
        score = {"pass": sum(1 for v in vs if v["verdict"] == "PASS"),
                 "total": sum(1 for v in vs if v["verdict"] != "n/a"), "verdicts": vs}
    c = config.get(root)
    return {"id": st["id"], "status": st.get("status"), "started": st.get("started"), "finished": st.get("finished"),
            "secs": _secs(st.get("started"), st.get("finished")), "error": st.get("error"),
            "config": {k: c[k] for k in config.DEFAULT}, "steps": steps, "counts": counts,
            "text": text_stats(root), "score": score}


def record(root, st):
    rec = summarize(root, st)
    store.write_run_json(root, "history/{}.json".format(st["id"]), rec)
    return rec


def list_runs(root, limit=30):
    d = _dir(root)
    if not os.path.isdir(d):
        return []
    out = []
    for name in sorted(os.listdir(d), reverse=True):
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(d, name), encoding="utf-8") as f:
                out.append(json.load(f))
        except ValueError:
            continue
        if len(out) >= limit:
            break
    return out
