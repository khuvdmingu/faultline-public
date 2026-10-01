"""작업 큐 — LLM 스테이지 실행의 단위.

작업(job) = 스테이지 1회 실행. 입력이 크면 배치로 나뉜다.
  생성    프롬프트 배치를 만들고 runs/jobs/<id>/ 에 저장한다 (재현·감사용).
  채우기  claude_cli 는 워커 스레드가 순서대로 호출하고, manual 은 사람이 배치별로 붙여넣는다.
  마감    배치 출력을 파싱·병합 → 출력 ID 재번호 → is_synthetic 을 시스템이 부여 → 스키마 검사
          → 통과하면 저장(직전 판 .prev 보관), 실패하면 rejected.jsonl 로만 남기고 사람이 결정.
한 실험(root)에서 동시에 도는 자동 작업은 하나다 (워커가 직렬로 처리 — 사용 한도 보호).
"""
import json
import os
import queue
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

from . import config, executors, humanize, prompts, registry, schema, steps, store

_Q = queue.Queue()
_LOCK = threading.Lock()
_WORKER = {"threads": []}


def _job_dir(root, job_id):
    return store.run_dir(root, "jobs", job_id)


def _save(root, job):
    with _LOCK:
        store.atomic_json(os.path.join(_job_dir(root, job["id"]), "job.json"), job)


def load(root, job_id):
    if not re.match(r"^[0-9]{8}-[0-9]{6}-[a-z0-9]{4}$", job_id or ""):
        raise ValueError("잘못된 작업 ID")
    fp = os.path.join(root, "runs", "jobs", job_id, "job.json")
    if not os.path.exists(fp):
        raise FileNotFoundError(job_id)
    with open(fp, encoding="utf-8") as f:
        return json.load(f)


def list_jobs(root, limit=40):
    d = os.path.join(root, "runs", "jobs")
    if not os.path.isdir(d):
        return []
    out = []
    for name in sorted(os.listdir(d), reverse=True)[:limit]:
        try:
            j = load(root, name)
            j.pop("log", None)
            out.append(j)
        except (ValueError, FileNotFoundError):
            continue
    return out


def parse_output(text):
    """모델 출력 → 레코드. 코드 펜스·설명 줄은 무시하고 JSON 줄(또는 JSON 배열)만 취한다."""
    text = re.sub(r"```[a-zA-Z]*", "", text or "").strip()
    if text.startswith("["):
        try:
            arr = json.loads(text)
            if isinstance(arr, list):
                return [x for x in arr if isinstance(x, dict)], []
        except ValueError:
            pass
    rows, errors = [], []
    for n, line in enumerate(text.splitlines(), 1):
        line = line.strip().rstrip(",")
        if not line.startswith("{"):
            continue
        try:
            rows.append(json.loads(line))
        except ValueError as e:
            errors.append("{}행: {}".format(n, e))
    if not rows and text.startswith("{"):          # 여러 줄로 펼친 JSON 객체 하나 (정답표 등)
        try:
            obj = json.loads(text)
            if isinstance(obj, dict):
                return [obj], []
        except ValueError:
            pass
    if not rows and not errors:
        errors.append("JSON 줄을 찾지 못했다")
    return rows, errors


def create(root, rel_root, stage_id, executor="manual", model=None):
    stage = registry.get(stage_id)
    if stage["kind"] != "llm":
        raise ValueError("{} 은(는) LLM 스테이지가 아니다".format(stage_id))
    if executor not in ("manual", "claude_cli"):
        raise ValueError("알 수 없는 실행기: {}".format(executor))
    model = model or config.model_for(root, stage)
    if model not in executors.MODELS:
        raise ValueError("모델은 {} 중 하나".format(executors.MODELS))
    batches = prompts.build(root, stage_id)
    job_id = "{}-{}".format(time.strftime("%Y%m%d-%H%M%S"), uuid.uuid4().hex[:4])
    d = _job_dir(root, job_id)
    blist = []
    for b in batches:
        pf = "batch_{:02d}.prompt.md".format(b["index"])
        with open(os.path.join(d, pf), "w", encoding="utf-8") as f:
            f.write(b["text"])
        blist.append({"index": b["index"], "items": b["items"], "status": "pending",
                      "prompt_file": pf, "prompt_chars": len(b["text"]), "out_file": None, "error": None})
    job = {"id": job_id, "root": rel_root, "stage": stage_id, "writes": stage["writes"][0],
           "executor": executor, "model": model, "status": "waiting" if executor == "manual" else "queued",
           "created": store.now(), "started": None, "finished": None, "batches": blist,
           "result": None, "error": None, "log": [], "pid": os.getpid() if executor == "claude_cli" else None}
    _save(root, job)
    if executor == "claude_cli":
        _Q.put((root, job_id))
        _ensure_worker()
    return job


def prompt_text(root, job_id, index, job=None):
    job = job or load(root, job_id)      # 워커는 메모리의 job 을 넘긴다 — 다른 배치가 쓰는 중인 파일을 다시 읽지 않는다
    b = job["batches"][int(index)]
    with open(os.path.join(_job_dir(root, job_id), b["prompt_file"]), encoding="utf-8") as f:
        return f.read()


def paste(root, job_id, index, text):
    """manual 실행기: 배치 하나의 출력을 받는다. 모든 배치가 차면 자동으로 마감한다."""
    job = load(root, job_id)
    if job["status"] in ("done",):
        raise ValueError("이미 끝난 작업")
    b = job["batches"][int(index)]
    rows, errors = parse_output(text)
    if errors and not rows:
        return {"ok": False, "errors": errors}
    _store_batch(root, job, b, text)
    if all(x["status"] == "done" for x in job["batches"]):
        return finalize(root, job)
    _save(root, job)
    return {"ok": True, "job": job, "parse_warnings": errors}


def _store_batch(root, job, b, text):
    of = "batch_{:02d}.out.txt".format(b["index"])
    with open(os.path.join(_job_dir(root, job["id"]), of), "w", encoding="utf-8") as f:
        f.write(text)
    b.update(status="done", out_file=of, error=None)


def _renumber(rows, prefix):
    if not prefix:
        return rows
    for i, r in enumerate(rows, 1):
        r["id"] = "{}{:03d}".format(prefix, i)
    return rows


def _shuffle_corpus(rows, seed):
    """배치로 나눠 만든 원문을 섞고 RAW_001… 로 다시 번호를 매긴다(twin_of 도 따라 바꾼다).
    배치마다 role 이 몰려 있어 ID 순서가 정답(어느 tension·무소속인가)을 흘리는 것을 막는다."""
    import hashlib
    key = lambda r: (r.get("_batch", 0), r.get("id"))       # 모델이 배치마다 RAW_001 부터 써도 겹치지 않게
    order = sorted(rows, key=lambda r: hashlib.sha1("{}|{}|{}".format(seed, key(r), r.get("raw_text")).encode("utf-8")).hexdigest())
    remap = {key(r): "RAW_{:03d}".format(i) for i, r in enumerate(order, 1)}
    for r in order:
        b = r.pop("_batch", 0)
        r["id"] = remap[(b, r.get("id"))]
        lab = r.get("label") or {}
        if lab.get("twin_of"):
            lab["twin_of"] = remap.get((b, lab["twin_of"]), lab["twin_of"])
    return order


def finalize(root, job, force=False):
    stage = registry.get(job["stage"])
    rows, perr = [], []
    for b in job["batches"]:
        if b["status"] != "done":
            raise ValueError("배치 {} 가 아직 비어 있다".format(b["index"]))
        with open(os.path.join(_job_dir(root, job["id"]), b["out_file"]), encoding="utf-8") as f:
            r, e = parse_output(f.read())
        if job["writes"] == "corpus_labeled":
            for x in r:
                x["_batch"] = b["index"]
        rows += r
        perr += ["배치 {} {}".format(b["index"], x) for x in e]
    rows = _renumber(rows, stage.get("prefix"))
    key = job["writes"]
    if key == "corpus_labeled":
        rows = _shuffle_corpus(rows, job["id"])
    if key not in ("corpus_labeled", "ground_truth"):
        raw = store.read(root, "raw") or []
        synthetic = any(x.get("is_synthetic") for x in raw) or not raw
        for r in rows:
            r["is_synthetic"] = synthetic        # 시스템이 부여 — 모델 출력값을 믿지 않는다
    if key == "ground_truth":
        errors, warnings = steps.check_ground_truth(rows, config.get(root)["tensions"]), []
    elif key == "corpus_labeled":
        errors, warnings = steps.check_corpus(rows)[0], []
    else:
        errors, warnings = schema.check_output(key, rows, root)
    if key == "polished" and not errors:
        rows, e2, w2 = humanize.gate(root, rows)
        errors, warnings = errors + e2, warnings + w2
    job["result"] = {"rows": len(rows), "errors": errors[:50], "error_count": len(errors),
                     "warnings": warnings[:50], "parse_warnings": perr[:20]}
    if errors and not force:
        with open(os.path.join(_job_dir(root, job["id"]), "rejected.jsonl"), "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        job["status"] = "needs_review"
        job["log"].append("{} 검증 오류 {}건 — 저장 보류 (rejected.jsonl)".format(store.now(), len(errors)))
        _save(root, job)
        return {"ok": False, "job": job}
    fp = store.write(root, key, rows[0] if key == "ground_truth" else rows)
    _provenance(root, job, key, len(rows))
    job.update(status="done", finished=store.now())
    job["result"]["file"] = os.path.relpath(fp, store.APP_ROOT)
    job["result"]["forced"] = bool(errors)
    job["log"].append("{} 저장 {}행 → {}".format(store.now(), len(rows), job["result"]["file"]))
    _save(root, job)
    return {"ok": True, "job": job}


def finalize_saved(root, job_id, force=False):
    return finalize(root, load(root, job_id), force=force)


def _provenance(root, job, key, n):
    fp = os.path.join(root, "runs", "provenance.jsonl")
    os.makedirs(os.path.dirname(fp), exist_ok=True)
    with open(fp, "a", encoding="utf-8") as f:
        f.write(json.dumps({"at": store.now(), "key": key, "rows": n, "job": job["id"], "stage": job["stage"],
                            "executor": job["executor"], "model": job["model"]}, ensure_ascii=False) + "\n")


JOB_WORKERS = 2          # 동시에 도는 작업 수 — 자동 실행에서 기준선(05)이 본 사슬과 나란히 돈다


def _ensure_worker():
    alive = [t for t in _WORKER["threads"] if t.is_alive()]
    while len(alive) < JOB_WORKERS:
        t = threading.Thread(target=_work, name="faultline-worker-{}".format(len(alive)), daemon=True)
        t.start()
        alive.append(t)
    _WORKER["threads"] = alive


def _run_batches(root, job):
    """남은 배치를 config.parallel 개씩 동시에. 실패한 배치가 있으면 (index, 오류) 목록."""
    pending = [b for b in job["batches"] if b["status"] != "done"]
    lock, failed = threading.Lock(), []

    def one(b):
        with lock:
            b["status"] = "running"
            _save(root, job)
        text = prompt_text(root, job["id"], b["index"], job)
        t0 = time.time()
        # 멈춘 호출 끊기 — quick 배치는 보통 2분 안에 끝나는데 한 번 475초 동안 응답 없이 붙잡혔다(photo-agent-v1 25 유추)
        limit = config.get(root)["call_timeout"]
        try:
            try:
                out = executors.run_cli(text, job["model"], timeout=limit)
            except RuntimeError as e1:
                # 동시에 여러 프로세스를 돌리면 일시 오류가 난다 — 한 번은 조금 쉬었다 바로 다시
                with lock:
                    job["log"].append("{} 배치 {} 일시 실패, 15초 뒤 재시도: {}".format(store.now(), b["index"], str(e1)[:200]))
                    _save(root, job)
                time.sleep(15)
                out = executors.run_cli(text, job["model"], timeout=limit)
        except RuntimeError as e:
            with lock:
                b.update(status="failed", error=str(e))
                failed.append((b["index"], e))
                job["log"].append("{} 배치 {} 실패: {}".format(store.now(), b["index"], e))
                _save(root, job)
            return
        with lock:
            _store_batch(root, job, b, out)
            job["log"].append("{} 배치 {} 완료 ({:.0f}초, {}자)".format(store.now(), b["index"], time.time() - t0, len(out)))
            _save(root, job)

    workers = max(1, min(config.get(root)["parallel"], len(pending)))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        list(ex.map(one, pending))
    return sorted(failed, key=lambda x: x[0])


def _work():
    while True:
        root, job_id = _Q.get()
        try:
            job = load(root, job_id)
            job.update(status="running", started=store.now(), pid=os.getpid())
            _save(root, job)
            failed = _run_batches(root, job)
            if failed:
                i, e = failed[0]
                job.update(status="failed", error="배치 {}: {}".format(i, e), finished=store.now())
                _save(root, job)
            else:
                finalize(root, job)
        except Exception as e:  # 워커는 죽지 않는다
            try:
                job = load(root, job_id)
                job.update(status="failed", error="{}: {}".format(type(e).__name__, e), finished=store.now())
                _save(root, job)
            except Exception:
                pass
        finally:
            _Q.task_done()


def _alive(pid):
    if not pid or pid == os.getpid():
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def recover(root):
    """서버 재시작 시 — 워커가 잡고 있던 자동 작업은 실패로 표시한다 (재시도 가능).
    다른 살아 있는 프로세스(예: 터미널의 faultline auto)가 돌리는 작업은 건드리지 않는다."""
    for j in list_jobs(root, limit=200):
        if j["executor"] == "claude_cli" and j["status"] in ("queued", "running") and not _alive(j.get("pid")):
            job = load(root, j["id"])
            job.update(status="failed", error="서버가 재시작돼 중단됨 — 재시도 가능", finished=store.now())
            _save(root, job)


def retry(root, job_id):
    job = load(root, job_id)
    if job["executor"] != "claude_cli":
        raise ValueError("manual 작업은 붙여넣기로 채운다")
    for b in job["batches"]:
        if b["status"] in ("failed", "running"):
            if b.get("error"):
                job["log"].append("{} 재시도 — 배치 {} 직전 오류: {}".format(store.now(), b["index"], str(b["error"])[:200]))
            b["status"] = "pending"
    job.update(status="queued", error=None, pid=os.getpid())
    _save(root, job)
    _Q.put((root, job_id))
    _ensure_worker()
    return job
