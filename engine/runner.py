"""자동 실행 — 정답표(없을 때만)부터 후보 추리기·채점까지 스테이지를 순서대로 돈다.

사람 검토(80)는 넣지 않는다. 결과는 75 후보 추리기의 shortlist 로 나오고, 사람 검토는 그 뒤에 원하면 한다.
LLM 스테이지는 jobs 큐(claude_cli)에 넣고 끝날 때까지 기다린다 — 웹·CLI 가 같은 엔진을 쓴다.

멈추는 경우 (고치고 다시 이어 돌리면 된다):
  - 작업이 검증 오류로 needs_review — 저장하지 않고 멈춘다. 파이프라인 탭에서 확인·강제 저장·재실행.
  - 작업 실패 — 한 번 재시도하고, 또 실패하면 멈춘다.
  - 라벨 분리 구조 오류.
합성 corpus 품질 검사가 「재생성 권장」이면 01 생성을 한 번 다시 돈다.

상태는 runs/autorun.json 한 파일. 서버가 재시작되면 돌던 실행은 interrupted 로 표시된다.
"""
import os
import threading
import time

from . import assign, config, history, jobs, registry, scoring, steps, store

AUTO = ["ground_truth", "generate", "split", "baseline", "extract", "link", "assign", "analogy", "package",
        "principle", "premise", "scenario", "judge", "family", "shortlist", "polish", "score"]
# 검증 전용: Phase 0 채점이 실제로 재는 구간(생성 → 추출 → 연결)만. 연결 로직을 고치며 반복할 때.
CHECK = ["ground_truth", "generate", "split", "extract", "link", "assign", "score"]
POLL = 3
_THREADS = {}
_LOCK = threading.Lock()


def _score(root):
    res = scoring.phase0(root)
    if res is None:
        return {"errors": ["채점 불가 — labels·raw·behaviors 가 필요하다"]}
    store.write_run_json(root, "score/phase0.json", res)
    store.write_run_json(root, "score/phase0_{}.json".format(res["at"].replace(":", "")), res)
    return res


DET = {"split": steps.split, "assign": assign.run, "package": steps.package, "shortlist": steps.shortlist,
       "score": _score}


def _has(root, key):
    return os.path.exists(store.path(root, key))


def _done(root, sid):
    st = registry.get(sid)
    if sid == "score":
        return os.path.exists(os.path.join(root, "runs", "score", "phase0.json"))
    return all(_has(root, k) for k in st["writes"])


def plan(root, frm=None, to=None):
    """실행할 스테이지 목록. frm 이 없으면 결과가 비어 있는 첫 스테이지부터 (이어 돌리기)."""
    to = to or AUTO[-1]
    if to not in AUTO:
        raise ValueError("알 수 없는 끝 스테이지: {}".format(to))
    if frm and frm not in AUTO:
        raise ValueError("알 수 없는 시작 스테이지: {}".format(frm))
    if frm is None:
        c0 = config.get(root)
        pool = [s for s in AUTO if (c0["profile"] != "check" or s in CHECK)
                and not (s == "family" and c0["family"] == "off") and not (s == "polish" and c0["polish"] == "off")
                and not (s == "assign" and c0["assign"] == "off")]
        frm = next((s for s in pool if not _done(root, s)), None)
        if frm is None:
            return []
    seq = AUTO[AUTO.index(frm): AUTO.index(to) + 1]
    cfg = config.get(root)
    if cfg["profile"] == "check":
        seq = [s for s in seq if s in CHECK]
    if cfg["assign"] == "off" and "assign" in seq:
        seq.remove("assign")
    if cfg["family"] == "off" and "family" in seq:
        seq.remove("family")
    if cfg["polish"] == "off" and "polish" in seq:
        seq.remove("polish")
    # 정답표가 이미 있으면(사람이 썼든 앞서 생성했든) 00 부터 돌리라고 명시하지 않는 한 덮지 않는다
    if "ground_truth" in seq and _has(root, "ground_truth") and frm != "ground_truth":
        seq.remove("ground_truth")
    if "score" in seq and not _has(root, "ground_truth") and "ground_truth" not in seq:
        seq.remove("score")
    return seq


def status(root):
    st = _read(root)
    if st and st.get("status") == "running" and not running(root):
        st["status"] = "interrupted"
    return st


def _read(root):
    import json
    fp = os.path.join(root, "runs", "autorun.json")
    if not os.path.exists(fp):
        return None
    with open(fp, encoding="utf-8") as f:
        return json.load(f)


def running(root):
    t = _THREADS.get(root)
    return bool(t and t.is_alive())


def start(root, rel, frm=None, to=None, executor="claude_cli"):
    with _LOCK:
        if running(root):
            raise RuntimeError("이 실험은 이미 자동 실행 중이다")
        seq = plan(root, frm, to)
        if not seq:
            raise ValueError("돌릴 스테이지가 없다 — 모두 끝났다. 처음부터 다시 돌리려면 시작 스테이지를 고른다")
        st = {"id": time.strftime("%Y%m%d-%H%M%S"), "root": rel, "status": "running", "executor": executor,
              "plan": seq, "current": None, "started": store.now(), "finished": None, "error": None,
              "steps": [{"stage": s, "status": "pending"} for s in seq]}
        _save(root, st)
        t = threading.Thread(target=_run, args=(root, rel, st), daemon=True, name="autorun-" + rel)
        _THREADS[root] = t
        t.start()
    return st


def run_sync(root, rel, frm=None, to=None, executor="claude_cli", echo=print):
    """CLI 용 — 같은 실행을 현재 스레드에서 돌리고 진행을 출력한다."""
    seq = plan(root, frm, to)
    if not seq:
        echo("돌릴 스테이지가 없다 — 모두 끝났다")
        return None
    st = {"id": time.strftime("%Y%m%d-%H%M%S"), "root": rel, "status": "running", "executor": executor,
          "plan": seq, "current": None, "started": store.now(), "finished": None, "error": None,
          "steps": [{"stage": s, "status": "pending"} for s in seq]}
    _save(root, st)
    return _run(root, rel, st, echo)


def _save(root, st):
    store.write_run_json(root, "autorun.json", st)
    if st.get("status") in ("done", "stopped"):
        try:
            history.record(root, st)                  # 끝날 때마다 비교용 요약 한 장
        except Exception:                             # noqa: BLE001 — 기록 실패가 실행 결과를 바꾸지 않는다
            pass


def _wait(root, job_id):
    while True:
        time.sleep(POLL)
        j = jobs.load(root, job_id)
        if j["status"] in ("done", "failed", "needs_review"):
            return j


def _llm(root, rel, sid, step, executor, job_id=None):
    if job_id is None:
        job = jobs.create(root, rel, sid, executor)
        step.update(job_id=job["id"], model=job["model"], batches=len(job["batches"]))
        job_id = job["id"]
    job = {"id": job_id}
    j = _wait(root, job["id"])
    if j["status"] == "failed":
        step["note"] = "실패 — 한 번 재시도"
        jobs.retry(root, job["id"])
        j = _wait(root, job["id"])
    res = j.get("result") or {}
    step["rows"] = res.get("rows")
    if j["status"] == "needs_review":
        return False, "검증 오류 {}건 — 저장 보류. 파이프라인 탭에서 작업 {} 확인".format(res.get("error_count"), job["id"])
    if j["status"] == "failed":
        return False, "실패: {}".format(j.get("error") or "원인 불명")
    if res.get("warnings"):
        step["warnings"] = len(res["warnings"])
    return True, None


def _side_times(root, side):
    """나란히 도는 작업의 실제 시작·끝 — 기다린 시점이 아니라 작업이 끝난 시점을 적는다."""
    try:
        j = jobs.load(root, side["job_id"])
    except (ValueError, FileNotFoundError):
        return False
    if j.get("started"):
        side["started"] = j["started"]
    if j["status"] == "done" and j.get("finished"):
        side.update(status="done", finished=j["finished"], rows=(j.get("result") or {}).get("rows"))
        return True
    return False


def _run(root, rel, st, echo=None):
    say = echo or (lambda *a: None)
    regenerated = False
    # 기준선(05)은 brief 만 읽으므로 처음에 따로 띄워 본 사슬과 나란히 돌리고, 평가(50) 직전에 기다린다
    side = None
    bstep = next((s for s in st["steps"] if s["stage"] == "baseline"), None)
    if bstep and registry.get("baseline")["kind"] == "llm":
        try:
            job = jobs.create(root, rel, "baseline", st["executor"])
            bstep.update(status="running", started=store.now(), job_id=job["id"], model=job["model"],
                         batches=len(job["batches"]), note="본 사슬과 나란히")
            side = bstep
            _save(root, st)
        except Exception as e:                        # noqa: BLE001
            bstep["note"] = "나란히 실행 못 함 — 차례에 돈다 ({})".format(e)
    i = 0
    while i < len(st["steps"]):
        step = st["steps"][i]
        sid = step["stage"]
        if step is side:
            i += 1
            continue
        if side is not None and sid in ("judge", "score") or (side is not None and i == len(st["steps"]) - 1):
            ok, err = _llm(root, rel, "baseline", side, st["executor"], side["job_id"])
            side.update(status="done" if ok else "stopped", finished=store.now())
            _side_times(root, side)
            if not ok:
                side["error"] = err
                st.update(status="stopped", error="baseline 에서 멈춤 — {}".format(err), finished=store.now(), current=None)
                _save(root, st)
                say("■ 멈춤: {}".format(st["error"]))
                return st
            side = None
        if side is not None and side.get("status") == "running" and _side_times(root, side):
            say("  05 기준선 (나란히) 끝 · 행 {}".format(side.get("rows")))
        # 60 family 는 시나리오·principle 만 읽는다 — 50 평가와 나란히 띄우고, 자기 차례에 기다린다
        if sid == "judge" and registry.get("family")["kind"] == "llm":
            fstep = next((x for x in st["steps"][i + 1:] if x["stage"] == "family" and x["status"] == "pending"), None)
            if fstep is not None:
                try:
                    fj = jobs.create(root, rel, "family", st["executor"])
                    fstep.update(status="running", started=store.now(), job_id=fj["id"], model=fj["model"],
                                 batches=len(fj["batches"]), note="평가와 나란히", parallel=True)
                except Exception as e:                # noqa: BLE001 — 못 띄우면 차례에 돈다
                    fstep["note"] = "나란히 실행 못 함 — 차례에 돈다 ({})".format(e)
        if step.get("parallel") and step.get("job_id"):
            st["current"] = sid
            _save(root, st)
            say("▶ {} {} (나란히 띄운 작업 기다림)".format(registry.get(sid)["num"], registry.get(sid)["name"]))
            ok, err = _llm(root, rel, sid, step, st["executor"], step["job_id"])
            step.update(status="done" if ok else "stopped", finished=store.now())
            _side_times(root, step)
            if not ok:
                step["error"] = err
                st.update(status="stopped", error="{} 에서 멈춤 — {}".format(sid, err), finished=store.now(), current=None)
                _save(root, st)
                say("■ 멈춤: {}".format(st["error"]))
                return st
            say("  행 {} · {}".format(step.get("rows"), step.get("note")))
            _save(root, st)
            i += 1
            continue
        st["current"] = sid
        step.update(status="running", started=store.now())
        _save(root, st)
        say("▶ {} {}".format(registry.get(sid)["num"], registry.get(sid)["name"]))
        try:
            if registry.get(sid)["kind"] == "llm":
                ok, err = _llm(root, rel, sid, step, st["executor"])
            else:
                res = DET[sid](root)
                errs = res.get("errors") if isinstance(res, dict) else None
                ok, err = (not errs), ("; ".join(errs[:3]) if errs else None)
                if sid == "split" and ok:
                    verdict = (res.get("qa") or {}).get("verdict")
                    step["note"] = "품질 검사: {}".format(verdict)
                    if verdict == "재생성 권장" and not regenerated and "generate" in st["plan"]:
                        regenerated = True
                        step.update(status="redo", finished=store.now())
                        gi = next(k for k, s in enumerate(st["steps"]) if s["stage"] == "generate")
                        st["steps"][gi:i + 1] = [{"stage": "generate", "status": "pending", "note": "품질 재생성"},
                                                 {"stage": "split", "status": "pending"}]
                        i = gi
                        _save(root, st)
                        say("  품질 검사 재생성 권장 → 01 생성을 한 번 다시 돈다")
                        continue
                if sid == "assign" and ok:
                    ch = res["changed"]
                    step["note"] = "판단 {}개 · accept {} · 무소속으로 {} · 이동 {} · 역할 {} · 추가 {} · 반례 유지 {} · member 유지 {}".format(
                        res["items"], res["summary"]["accept"], ch["to_none"], ch["moved"], ch["role"], ch["added"],
                        ch["kept_counter"], ch.get("kept_member", 0))
                if sid == "shortlist" and ok:
                    step["note"] = "후보 {}개 / 적격 {}".format(len(res["picks"]), res["counts"]["eligible"])
                if sid == "score" and ok:
                    p = sum(1 for v in res["verdicts"] if v["verdict"] == "PASS")
                    step["note"] = "PASS {} / {}".format(p, sum(1 for v in res["verdicts"] if v["verdict"] != "n/a"))
        except Exception as e:                        # noqa: BLE001 — 어떤 오류든 기록하고 멈춘다
            ok, err = False, "{}: {}".format(type(e).__name__, e)
        step.update(status="done" if ok else "stopped", finished=store.now())
        if step.get("note") or step.get("rows") is not None:
            say("  {}{}".format("행 {} · ".format(step["rows"]) if step.get("rows") is not None else "",
                                step.get("note") or ""))
        if not ok:
            step["error"] = err
            st.update(status="stopped", error="{} 에서 멈춤 — {}".format(sid, err), finished=store.now(), current=None)
            _save(root, st)
            say("■ 멈춤: {}".format(st["error"]))
            return st
        _save(root, st)
        i += 1
    if side is not None:                              # 계획이 기준선에서 끝난 경우
        ok, err = _llm(root, rel, "baseline", side, st["executor"], side["job_id"])
        side.update(status="done" if ok else "stopped", finished=store.now(), error=err)
        if not ok:
            st.update(status="stopped", error="baseline 에서 멈춤 — {}".format(err), finished=store.now(), current=None)
            _save(root, st)
            return st
    st.update(status="done", finished=store.now(), current=None)
    _save(root, st)
    say("✓ 끝")
    return st
