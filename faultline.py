"""Faultline CLI — 웹과 같은 엔진을 터미널에서 쓴다.

  python3 faultline.py stages                         스테이지 등록부
  python3 faultline.py split    --root experiments/tv-v1
  python3 faultline.py qa       --root ...            합성 corpus 품질 검사
  python3 faultline.py package  --root ...
  python3 faultline.py validate --root ...
  python3 faultline.py score    --root ...            Phase 0 채점 (평가자 전용)
                       [--tensions judge_runs/<run>/tensions.judged.jsonl]   연결 결과를 바꿔 끼워 비교 (저장 안 함)
  python3 faultline.py coverage --root ...
  python3 faultline.py prompt   --root ... --stage link [--batch 0]   프롬프트 출력
  python3 faultline.py run      --root ... --stage link [--model opus] claude_cli 로 실행 (끝날 때까지 대기)
  python3 faultline.py executors                      실행기 상태

프로그램처럼 쓰기 (같은 폴더의 ./faultline 래퍼나 Faultline.command 로도 된다):
  python3 faultline.py serve [--port 8765] [--open]   웹 화면 띄우기
  python3 faultline.py new fridge-v1 --device "패밀리허브 냉장고" --domain "주방에서의 식재료 관리와 가족 소통"
                       [--traits "큰 터치 화면, 주방에 있음"] [--around "스마트폰, 장보기 앱"]
  python3 faultline.py auto --root experiments/fridge-v1 [--size quick] [--parallel 3] [--from generate] [--to shortlist]
                                                      정답표(없을 때만)→생성→…→윤문→후보 추리기→채점 자동
  python3 faultline.py shortlist --root ...           후보 추리기만 다시
  python3 faultline.py list                           실험 목록과 상태
  python3 faultline.py pool     [--roots a,b,…]       여러 실험 Phase 0 합산 (기본: 정답표 있는 실험 전부)
  python3 faultline.py history  --root ...            자동 실행 기록 (설정·시간·글 길이·판정 비교)
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from engine import (config, executors, experiments, history, jobs, prompts, qa, registry, runner,  # noqa: E402
                    schema, scoring, steps, store)


def _fmt(v):
    return "—" if v is None else ("{:.2f}".format(v) if isinstance(v, float) else str(v))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("cmd", choices=["stages", "split", "qa", "package", "validate", "score", "coverage",
                                   "prompt", "run", "executors", "serve", "new", "auto", "shortlist", "list", "history", "pool"])
    p.add_argument("name", nargs="?", help="new: 실험 이름 (영문 소문자·숫자·하이픈)")
    p.add_argument("--root", default="examples/mini")
    p.add_argument("--stage")
    p.add_argument("--batch", type=int, default=0)
    p.add_argument("--model")
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--open", action="store_true")
    p.add_argument("--device")
    p.add_argument("--domain")
    p.add_argument("--traits")
    p.add_argument("--around")
    p.add_argument("--from", dest="frm")
    p.add_argument("--to")
    p.add_argument("--size", choices=list(config.SIZES), help="quick(빠르게) · standard(표준)")
    p.add_argument("--parallel", type=int, help="한 스테이지 안 동시 배치 수 (1~6, 기본 3)")
    p.add_argument("--brevity", choices=list(config.BREVITY), help="short = 짧게 쓰기")
    p.add_argument("--profile", choices=list(config.PROFILES), help="check = 검증 전용(생성·추출·연결·채점)")
    p.add_argument("--polish", choices=list(config.POLISH))
    p.add_argument("--family", choices=list(config.FAMILY))
    p.add_argument("--assign", choices=list(config.ASSIGN), help="on = 20 연결 뒤 판단 필터 B(22)")
    p.add_argument("--tech", help="new: 기반 기술 (기본: 에이전틱 AI)")
    p.add_argument("--roots", help="pool: 쉼표로 구분한 실험 경로")
    p.add_argument("--tensions", help="score: 20 연결 대신 채점할 tensions jsonl (실험 폴더 기준 경로)")
    a = p.parse_args()

    if a.cmd == "serve":
        import server
        server.main(["--port", str(a.port)] + (["--open"] if a.open else []))
        return
    if a.cmd == "new":
        res = experiments.create(a.name, a.domain, a.device, a.traits, a.around, size=a.size, parallel=a.parallel,
                                 technology=a.tech, brevity=a.brevity, profile=a.profile)
        print("만들었다:", res["root"], "·", ", ".join("{}={}".format(k, v) for k, v in res["config"].items()))
        print("다음:  python3 faultline.py auto --root", res["root"])
        return
    if a.cmd == "list":
        for rel in store.list_roots():
            r = store.resolve(rel)
            st = runner.status(r) or {}
            nxt = runner.plan(r)
            print("{:<26} 자동 실행: {:<11} 다음: {}".format(rel, st.get("status", "—"),
                                                         (nxt[0] + " …") if nxt else "모두 끝남"))
        return

    if a.cmd == "pool":
        rels = a.roots.split(",") if a.roots else [r for r in store.list_roots() if r.startswith("experiments/")]
        res = scoring.pool([store.resolve(r.strip()) for r in rels])
        print("실험 {}개 합산: {}".format(res["experiments"], ", ".join(os.path.basename(p["root"]) for p in res["per"])))
        for v in res["verdicts"]:
            per = " ".join((next((x["verdict"][0] for x in p["verdicts"] if x["metric"] == v["metric"]), "-")) for p in res["per"])
            print("{:<22}{:>7}  {:<8} {:<5} (n={}){}   각 실험: {}".format(v["metric"], _fmt(v["value"]), v["rule"], v["verdict"],
                                                              v["n"], " 표본 작음" if v.get("small") else "", per))
        return
    if a.cmd == "stages":
        for s in registry.STAGES:
            print("{} {:<13}{:<10}{:<6}{:<7} reads={} → {}".format(
                s["num"], s["id"], s["lane"], s["kind"], s.get("model", "-"), s["reads"], s["writes"]))
        return
    if a.cmd == "executors":
        print(json.dumps(executors.health(refresh=True), ensure_ascii=False, indent=2))
        return

    root = store.resolve(a.root)
    if a.cmd == "auto":
        if any(x is not None for x in (a.size, a.parallel, a.brevity, a.profile, a.polish, a.family, a.assign)):
            config.set(root, a.size, a.parallel, a.brevity, a.profile, a.polish, a.family, a.assign)
        c = config.get(root)
        print("설정: 크기 {} · 동시 {} · 길이 {} · 흐름 {} · 윤문 {} · family {} · 판단 필터 {}".format(
            c["size"], c["parallel"], c["brevity"], c["profile"], c["polish"], c["family"], c["assign"]))
        h = executors.health(refresh=True)["claude_cli"]
        if not h["ok"]:
            sys.exit("claude CLI 를 쓸 수 없다: {} {}".format(h["message"], h.get("hint", "")))
        print("계획:", " → ".join(runner.plan(root, a.frm, a.to)) or "(없음)")
        st = runner.run_sync(root, a.root, a.frm, a.to, echo=lambda *x: print(*x, flush=True))
        if st and st["status"] == "done" and os.path.exists(store.path(root, "shortlist")):
            sl = store.read(root, "shortlist")
            scn = {s["id"]: s for s in store.read(root, "scenarios") or []}
            print("\n자동 후보 ({})".format(sl["rule"]))
            for pk in sl["picks"]:
                print("  {}. {} {}  [{}]".format(pk["rank"], pk["scenario_id"], scn.get(pk["scenario_id"], {}).get("title", ""),
                                                ", ".join(pk["why"])))
        sys.exit(0 if st is None or st["status"] == "done" else 1)
    if a.cmd == "history":
        runs = history.list_runs(root)
        if not runs and runner.status(root):              # 기록 기능 이전 실행 — 마지막 실행만 채워 넣는다
            history.record(root, runner.status(root))
            runs = history.list_runs(root)
        print("{:<16} {:<8} {:>6}  {:<30} {:>5} {:>5} {:>5}  {}".format(
            "실행", "상태", "분", "설정(크기·동시·길이·흐름)", "원칙", "가정", "시나리오", "판정"))
        print("  (원칙·가정·시나리오 = 레코드당 평균 글자 수)")
        for r in runs:
            c, t, sc = r["config"], r.get("text", {}), r.get("score")
            print("{:<16} {:<8} {:>6}  {:<30} {:>5} {:>5} {:>5}  {}".format(
                r["id"], r["status"], _fmt(round(r["secs"] / 60, 1) if r.get("secs") else None),
                "{} · {} · {} · {}{}{}".format(c["size"], c["parallel"], c["brevity"], c["profile"],
                                           " · 필터 " + c.get("assign_rule", "v1") if c.get("assign") == "on" else "",
                                           " · 기준선 " + c["baseline_split"] if c.get("baseline_split", "off") != "off" else ""),
                _fmt(t.get("principles")), _fmt(t.get("premises")), _fmt(t.get("scenarios")),
                "{}/{}".format(sc["pass"], sc["total"]) if sc else "—"))
        return
    if a.cmd == "shortlist":
        res = steps.shortlist(root)
        print(json.dumps(res, ensure_ascii=False, indent=2)[:3000])
        return
    if a.cmd == "split":
        res = steps.split(root)
        if res["errors"]:
            print("\n".join(res["errors"]))
            sys.exit(1)
        print("원문 {} · role {}".format(res["raw_count"], res["roles"]))
        if res["qa"]:
            print("QA:", res["qa"]["verdict"], "(FAIL {} · 주의 {})".format(res["qa"]["fail"], res["qa"]["warn"]))
    elif a.cmd == "qa":
        res = qa.run(root)
        if res is None:
            sys.exit("corpus_labeled 없음")
        for c in res["checks"]:
            print("{:<5} {:<28} {}  ({})".format(c["status"].upper(), c["check"], c["value"], c["rule"]))
        print("→", res["verdict"])
    elif a.cmd == "package":
        print(steps.package(root))
    elif a.cmd == "validate":
        res = schema.run(root)
        for w in res["warnings"]:
            print("경고:", w)
        for e in res["errors"]:
            print("오류:", e)
        print("오류 {} · 경고 {} · 미생성 {}".format(len(res["errors"]), len(res["warnings"]), res["skipped"]))
        sys.exit(1 if res["errors"] else 0)
    elif a.cmd == "score":
        alt = None
        if a.tensions:
            fp = a.tensions if os.path.isabs(a.tensions) else os.path.join(root, a.tensions)
            with open(fp, encoding="utf-8") as f:
                alt = [json.loads(x) for x in f if x.strip()]
            print("연결 결과 교체: {} (tension {}개) — 저장하지 않는다".format(os.path.relpath(fp, root), len(alt)))
        res = scoring.phase0(root, alt)
        if res is None:
            sys.exit("labels·raw·behaviors 가 필요하다")
        for v in res["verdicts"]:
            print("{:<22}{:>7}  {:<8} {:<5} {}".format(v["metric"], _fmt(v["value"]), v["rule"], v["verdict"],
                                                       "(n={}{})".format(v["n"], " · 표본 작음" if v.get("small") else "")
                                                       if v.get("n") is not None else ""))
        for r in res["detail"]["tension_recall"]:
            print("  {hidden} → {matched} 순도 {purity} 커버 {coverage} {ok}".format(ok="✓" if r["recovered"] else "✗", **r))
        if alt is None:
            store.write_run_json(root, "score/phase0.json", res)
    elif a.cmd == "coverage":
        print(json.dumps(steps.coverage(root), ensure_ascii=False, indent=2))
    elif a.cmd == "prompt":
        bs = prompts.build(root, a.stage)
        sys.stdout.write(bs[a.batch]["text"])
    elif a.cmd == "run":
        job = jobs.create(root, a.root, a.stage, "claude_cli", a.model)
        print("작업", job["id"], "배치", len(job["batches"]))
        while True:
            time.sleep(3)
            j = jobs.load(root, job["id"])
            if j["status"] in ("done", "failed", "needs_review"):
                print(j["status"], j.get("error") or j.get("result"))
                break


if __name__ == "__main__":
    try:
        main()
    except (ValueError, FileNotFoundError, KeyError) as e:
        sys.exit("오류: {}".format(e))
