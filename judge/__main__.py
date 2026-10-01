"""판단 모듈 CLI. faultline/ 에서 실행한다.

  python3 -m judge banks                                      질문 은행 목록
  python3 -m judge run <task> --root examples/mini --backend mock
  python3 -m judge run assign --backend openrouter --model <모델 id> [--mode logprobs] [--emit-tensions]
  python3 -m judge calibrate <run id> --task assign --root examples/mini   (Phase 0 정답으로 보정 측정)
  python3 -m judge selftest                                   외부 호출 없이 전 경로 검사

task: extract_check · assign · scenario_map_tv
결과: <root>/judge_runs/<run>/<task>.jsonl + manifest.json  (파이프라인 data/ 는 건드리지 않는다)
"""
import argparse
import datetime
import json
import os
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

from . import store
from .backends import BACKENDS, BackendUnavailable, make_backend
from .calibrate import evaluate, phase0_truth
from .tasks import TASKS

PROJECT_ROOT = os.path.dirname(store.JUDGE_DIR)


def resolve(root):
    return root if os.path.isabs(root) else os.path.normpath(os.path.join(PROJECT_ROOT, root))


def shown(p):
    """faultline 안이면 상대 경로, 밖이면 절대 경로."""
    rel = os.path.relpath(p, PROJECT_ROOT)
    return p if rel.startswith("..") else rel


def cmd_banks(_):
    for fp in store.list_banks():
        with open(fp, encoding="utf-8") as f:
            b = json.load(f)
        print("{}@{}  — {}".format(b["bank"], b["version"], b.get("attach", "")))
        for q in b["questions"]:
            n = len(q.get("options") or []) or ("2" if q["kind"] == "noul" else "동적")
            print("    {:<26}{:<7}선택지 {}".format(q["id"], q["kind"], n))


def cmd_run(a):
    root = resolve(a.root)
    try:
        backend = make_backend(a.backend, a.model, a.base_url, a.mode, a.samples, a.timeout, a.adapter_provider)
    except BackendUnavailable as e:
        sys.exit("백엔드를 쓸 수 없다: {}".format(e))
    task = TASKS[a.task](root, a.bank_version, candidates=a.candidates)
    try:
        items = task.items()
    except FileNotFoundError as e:
        sys.exit("입력 파일 없음: {}".format(e))
    if a.limit:
        items = items[:a.limit]
    workers = 1 if a.backend in ("adapter", "jev") else max(1, a.workers)

    started = datetime.datetime.now()
    run = a.run or started.strftime("%Y%m%d-%H%M%S")
    out_dir = os.path.join(root, "judge_runs", run)
    print("{} · {} 항목 · {} · 동시 {}".format(task.name, len(items), backend.describe(), workers))
    with ThreadPoolExecutor(workers) as ex:
        records = list(ex.map(lambda it: task.run_item(backend, it), items))
    store.write_jsonl(os.path.join(out_dir, task.name + ".jsonl"), records)

    answers = [x for r in records for x in r["answers"].values()]
    tokens = Counter()
    for x in answers:
        for k, v in (x.get("usage") or {}).items():
            if isinstance(v, int):
                tokens[k] += v
    lat = [x["latency_ms"] for x in answers if x.get("latency_ms") is not None]
    summary = {"items": len(records), "questions": len(answers),
               "decisions": dict(Counter(x["decision"] for x in answers)),
               "methods": dict(Counter(x["method"] for x in answers)),
               "errors": sum(1 for x in answers if x.get("error")),
               "tokens": dict(tokens), "mean_latency_ms": int(sum(lat) / len(lat)) if lat else None,
               "task": task.summarize(records)}

    extra = {}
    if a.task == "assign":
        extra["candidates_source"] = task.cand_source
        if a.emit_tensions:
            rows, dropped = task.emit_tensions(records, a.include_review)
            store.write_jsonl(os.path.join(out_dir, "tensions.judged.jsonl"), rows)
            extra["emitted_tensions"] = len(rows)
            extra["dropped_tensions"] = dropped

    manifest = {"run_id": run, "task": task.name, "bank": task.bank["_tag"], "root": shown(root),
                "backend": backend.describe(), "limit": a.limit or None,
                "started": started.isoformat(timespec="seconds"),
                "finished": datetime.datetime.now().isoformat(timespec="seconds"),
                "summary": summary}
    manifest.update(extra)
    store.write_json(os.path.join(out_dir, "manifest.json"), manifest)

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if extra:
        print(json.dumps(extra, ensure_ascii=False, indent=2))
    print("저장 →", shown(out_dir))
    if summary["errors"]:
        first = next(x["error"] for x in answers if x.get("error"))
        print("⚠ 오류 {}건. 첫 오류: {}".format(summary["errors"], first))


def cmd_calibrate(a):
    root = resolve(a.root)
    # 받는 모양: 경로(절대·faultline 기준) · --root 기준 경로 · run id 만
    tries = [resolve(a.run_dir), os.path.join(root, a.run_dir), os.path.join(root, "judge_runs", a.run_dir)]
    run_dir = next((t for t in tries if os.path.exists(t)), None)
    if run_dir is None:
        sys.exit("실행 결과를 찾지 못함: {}".format(a.run_dir))
    if os.path.isdir(run_dir):
        fp = os.path.join(run_dir, a.task + ".jsonl")
    else:
        fp = run_dir
    records = store.load_jsonl(fp)
    if a.truth:
        with open(resolve(a.truth), encoding="utf-8") as f:
            truth, note = json.load(f), a.truth
    else:
        truth, note = phase0_truth(root, a.task, records)
    res = evaluate(records, truth)
    print("정답: {}\n".format(note))
    for qid, r in res.items():
        print("{:<24} n={:<4} 정확도 {:.2f}  Brier {:.3f}  ECE {}  방식 {}".format(
            qid, r["n"], r["accuracy"], r["brier"], r["ece"], r["methods"]))
        for row in r["table"]:
            if row["n"]:
                print("    확신 {:<8} n={:<4} 평균 확신 {:.2f} → 실제 정답률 {:.2f}".format(
                    row["bin"], row["n"], row["conf"], row["acc"]))
    if not res:
        print("비교할 정답이 없다")
    if a.out:
        store.write_json(resolve(a.out), {"truth": note, "result": res})


def main(argv=None):
    p = argparse.ArgumentParser(prog="python3 -m judge", description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("banks", help="질문 은행 목록")

    r = sub.add_parser("run", help="태스크 실행")
    r.add_argument("task", choices=sorted(TASKS))
    r.add_argument("--root", default=".", help="작업 루트 (faultline 기준). 예: examples/mini")
    r.add_argument("--backend", default="mock", choices=BACKENDS)
    r.add_argument("--model")
    r.add_argument("--base-url", help="custom 백엔드 주소 (…/v1)")
    r.add_argument("--mode", default="logprobs", choices=["logprobs", "sampling", "verbal"])
    r.add_argument("--samples", type=int, default=5, help="sampling 반복 수")
    r.add_argument("--workers", type=int, default=4)
    r.add_argument("--timeout", type=int, default=60)
    r.add_argument("--limit", type=int, default=0, help="앞에서 N개만 (시험 실행용)")
    r.add_argument("--run", help="run id (기본: 날짜-시각)")
    r.add_argument("--bank-version")
    r.add_argument("--candidates", help="assign: tension 후보 파일 (기본: data/linked/tension_candidates.jsonl)")
    r.add_argument("--emit-tensions", action="store_true", help="assign: tensions.jsonl 모양으로도 저장")
    r.add_argument("--include-review", action="store_true", help="emit 할 때 검토 대상도 포함")
    r.add_argument("--adapter-provider", default="openai", help="adapter 백엔드의 provider")

    c = sub.add_parser("calibrate", help="보정 측정")
    c.add_argument("run_dir", help="judge_runs/<run> 폴더 또는 <task>.jsonl")
    c.add_argument("--task", required=True, choices=sorted(TASKS))
    c.add_argument("--root", default=".")
    c.add_argument("--truth", help="정답 JSON {item_id: {question_id: 값}}. 없으면 Phase 0 hidden 라벨 사용")
    c.add_argument("--out")

    sub.add_parser("selftest", help="외부 호출 없이 전 경로 검사")
    a = p.parse_args(argv)
    if a.cmd == "banks":
        cmd_banks(a)
    elif a.cmd == "run":
        cmd_run(a)
    elif a.cmd == "calibrate":
        cmd_calibrate(a)
    elif a.cmd == "selftest":
        from .selftest import main as selftest
        sys.exit(selftest())
    else:
        p.print_help()


if __name__ == "__main__":
    main()
