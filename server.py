"""Faultline 백엔드 — 로컬 API + 웹 프론트 서빙.

  python3 server.py [--port 8765]   →  http://127.0.0.1:8765

127.0.0.1 에만 바인딩한다. 프론트(web/)는 이 API 만 호출하고, 파일 쓰기·검증·실행은 전부 여기서 한다.
API 목록은 docs/ARCHITECTURE.md §6.
"""
import argparse
import json
import mimetypes
import os
import re
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from engine import (assign, config, executors, experiments, history, jobs, prompts, registry, review, runner,  # noqa: E402
                    schema, scoring, steps, store)
from engine import qa as corpus_qa  # noqa: E402

WEB = os.path.join(store.APP_ROOT, "web")
DOCS = os.path.join(store.APP_ROOT, "docs")
DATA_KEYS = ["raw", "baseline", "behaviors", "tensions", "analogies", "packages", "principles", "premises",
             "scenarios", "evaluations", "families", "polished", "shortlist", "decisions"]
DET = {"split": steps.split, "assign": assign.run, "package": steps.package, "shortlist": steps.shortlist}


def stage_state(root):
    js = jobs.list_jobs(root, limit=200)
    last = {}
    for j in js:                      # 최신순
        last.setdefault(j["stage"], {"id": j["id"], "status": j["status"], "executor": j["executor"],
                                     "model": j["model"], "created": j["created"]})
    out = []
    for s in registry.STAGES:
        outs = [dict(store.info(root, k), key=k) for k in s["writes"]]
        if s["id"] == "score":
            fp = os.path.join(root, "runs", "score", "phase0.json")
            outs = [{"key": "score", "exists": os.path.exists(fp), "count": 0, "updated": None}]
        out.append({"id": s["id"], "outputs": outs, "done": all(o["exists"] for o in outs) if outs else False,
                    "last_job": last.get(s["id"])})
    return out


def state(root, evaluator):
    data = {k: store.read(root, k) or [] for k in DATA_KEYS}
    raw_synth = any(r.get("is_synthetic") for r in data["raw"])
    res = {"stages": stage_state(root), "data": data, "brief": store.read(root, "brief") or {},
           "synthetic": raw_synth,
           "validate": schema.run(root) if data["raw"] else None,
           "coverage": steps.coverage(root), "health": scoring.health(root),
           "autorun": runner.status(root), "autorun_active": runner.running(root),
           "autorun_plan": runner.plan(root), "autorun_order": runner.AUTO,
           "config": config.get(root), "options": config.public(), "history": history.list_runs(root, 10)}
    if evaluator:
        res["labels"] = store.read(root, "labels", allow_hidden=True) or {}          # 평가자 모드에서만
        res["ground_truth"] = store.read(root, "ground_truth", allow_hidden=True) or {}
        res["score"] = scoring.phase0(root)
        res["qa"] = corpus_qa.run(root)
    return res


def docs_list():
    out = []
    for name in sorted(os.listdir(DOCS)):
        if name.endswith(".md"):
            with open(os.path.join(DOCS, name), encoding="utf-8") as f:
                first = f.readline().lstrip("# ").strip()
            out.append({"name": name, "title": first})
    return out


class Handler(BaseHTTPRequestHandler):
    server_version = "Faultline/0.2"

    def log_message(self, fmt, *args):
        if "/api/state" not in (str(args[0]) if args else ""):
            sys.stderr.write("[faultline] " + fmt % args + "\n")

    def send(self, code, body, ctype="application/json; charset=utf-8"):
        raw = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(raw)

    def parts(self):
        u = urlparse(self.path)
        return u.path, {k: v[0] for k, v in parse_qs(u.query).items()}

    def body(self):
        n = int(self.headers.get("Content-Length", 0) or 0)
        return self.rfile.read(n).decode("utf-8") if n else ""

    def root(self, qs):
        rel = qs.get("root") or ""
        return store.resolve(rel), rel

    def static(self, rel):
        fp = os.path.normpath(os.path.join(WEB, rel))
        if not fp.startswith(WEB + os.sep) or not os.path.isfile(fp):
            return self.send(404, {"error": "not found"})
        ctype = mimetypes.guess_type(fp)[0] or "application/octet-stream"
        if fp.endswith(".js"):
            ctype = "text/javascript"
        with open(fp, "rb") as f:
            return self.send(200, f.read(), ctype + ("; charset=utf-8" if ctype.startswith("text") else ""))

    # ------------------------------------------------------------------ GET
    def do_GET(self):
        route, qs = self.parts()
        try:
            if route in ("/", "/index.html"):
                return self.static("index.html")
            if route == "/favicon.ico":                   # 브라우저 자동 요청 — 콘솔에 400 이 남지 않게
                self.send_response(204)
                self.end_headers()
                return None
            if route.startswith("/web/"):
                return self.static(unquote(route[len("/web/"):]))
            if route == "/api/meta":
                return self.send(200, {"registry": registry.public(), "roots": store.list_roots(),
                                       "models": executors.MODELS})
            if route == "/api/executors":
                return self.send(200, executors.health(refresh=qs.get("refresh") == "1"))
            if route == "/api/docs":
                return self.send(200, {"docs": docs_list()})
            m = re.match(r"^/docs/([A-Za-z0-9_.-]+\.html)$", route)
            if m:
                fp = os.path.join(DOCS, m.group(1))
                if not os.path.isfile(fp):
                    return self.send(404, {"error": "not found"})
                with open(fp, "rb") as f:
                    return self.send(200, f.read(), "text/html; charset=utf-8")
            m = re.match(r"^/api/docs/([A-Za-z0-9_.-]+\.md)$", route)
            if m:
                fp = os.path.join(DOCS, m.group(1))
                if not os.path.isfile(fp):
                    return self.send(404, {"error": "not found"})
                with open(fp, encoding="utf-8") as f:
                    return self.send(200, {"name": m.group(1), "text": f.read()})
            root, rel = self.root(qs)
            if route == "/api/autorun":
                return self.send(200, {"status": runner.status(root), "running": runner.running(root),
                                       "next_plan": runner.plan(root), "order": runner.AUTO})
            if route == "/api/state":
                return self.send(200, state(root, qs.get("evaluator") == "1"))
            if route == "/api/jobs":
                return self.send(200, {"jobs": jobs.list_jobs(root)})
            if route == "/api/history":
                return self.send(200, {"runs": history.list_runs(root)})
            m = re.match(r"^/api/jobs/([0-9a-z-]+)$", route)
            if m:
                return self.send(200, jobs.load(root, m.group(1)))
            m = re.match(r"^/api/jobs/([0-9a-z-]+)/prompt$", route)
            if m:
                return self.send(200, {"text": jobs.prompt_text(root, m.group(1), qs.get("batch", 0))})
            if route == "/api/preview":
                bs = prompts.build(root, qs.get("stage"))
                return self.send(200, {"batches": [{"index": b["index"], "items": b["items"], "chars": len(b["text"])} for b in bs],
                                       "first": bs[0]["text"] if bs else ""})
            return self.send(404, {"error": "not found"})
        except store.BarrierError as e:
            return self.send(403, {"error": "정보 차단선: {}".format(e)})
        except (ValueError, KeyError, FileNotFoundError, IndexError) as e:
            return self.send(400, {"error": str(e)})

    # ------------------------------------------------------------------ POST
    def do_POST(self):
        route, qs = self.parts()
        text = self.body()
        try:
            if route == "/api/experiments":
                b = json.loads(text or "{}")
                return self.send(200, experiments.create(b.get("name"), b.get("domain"), b.get("device"),
                                                         b.get("device_traits"), b.get("surroundings"), b.get("exclude"),
                                                         b.get("size"), b.get("parallel"), b.get("technology"),
                                                         b.get("brevity"), b.get("profile")))
            root, rel = self.root(qs)
            if route == "/api/config":
                b = json.loads(text or "{}")
                return self.send(200, config.set(root, b.get("size"), b.get("parallel"), b.get("brevity"),
                                                 b.get("profile"), b.get("polish"), b.get("family"), b.get("assign"),
                                                 b.get("assign_rule"), b.get("baseline_split")))
            if route == "/api/autorun":
                try:
                    st = runner.start(root, rel, qs.get("from") or None, qs.get("to") or None)
                except RuntimeError as e:
                    return self.send(409, {"error": str(e)})
                return self.send(200, st)
            if route == "/api/jobs":
                job = jobs.create(root, rel, qs.get("stage"), qs.get("executor", "manual"), qs.get("model"))
                return self.send(200, job)
            m = re.match(r"^/api/jobs/([0-9a-z-]+)/paste$", route)
            if m:
                res = jobs.paste(root, m.group(1), qs.get("batch", 0), text)
                return self.send(200 if res.get("ok") else 422, res)
            m = re.match(r"^/api/jobs/([0-9a-z-]+)/finalize$", route)
            if m:
                res = jobs.finalize_saved(root, m.group(1), force=qs.get("force") == "1")
                return self.send(200 if res.get("ok") else 422, res)
            m = re.match(r"^/api/jobs/([0-9a-z-]+)/retry$", route)
            if m:
                return self.send(200, jobs.retry(root, m.group(1)))
            if route == "/api/run":
                sid = qs.get("stage")
                if sid not in DET:
                    raise ValueError("스크립트 스테이지가 아니다: {}".format(sid))
                res = DET[sid](root)
                return self.send(422 if res.get("errors") else 200, res)
            if route == "/api/score":
                res = scoring.phase0(root)
                if res is None:
                    raise ValueError("labels·raw·behaviors 가 모두 있어야 채점할 수 있다")
                store.write_run_json(root, "score/phase0.json", res)
                store.write_run_json(root, "score/phase0_{}.json".format(res["at"].replace(":", "")), res)
                return self.send(200, res)
            if route == "/api/review":
                return self.send(200, review.add(root, json.loads(text or "{}")))
            return self.send(404, {"error": "not found"})
        except store.BarrierError as e:
            return self.send(403, {"error": "정보 차단선: {}".format(e)})
        except (ValueError, KeyError, FileNotFoundError, IndexError) as e:
            return self.send(400, {"error": str(e)})


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--port", type=int, default=8765)
    p.add_argument("--open", action="store_true", help="브라우저로 연다")
    args = p.parse_args(argv)
    for rel in store.list_roots():
        jobs.recover(store.resolve(rel))
    url = "http://127.0.0.1:{}".format(args.port)
    try:
        srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    except OSError:
        # 이미 떠 있으면(런처를 두 번 눌렀을 때) 새로 띄우지 않고 열기만 한다
        print("포트 {} 가 이미 쓰이고 있다 — 떠 있는 Faultline 을 연다: {}".format(args.port, url), flush=True)
        if args.open:
            import webbrowser
            webbrowser.open(url)
        return
    print("Faultline → {}  (끝내려면 Ctrl+C)".format(url), flush=True)
    if args.open:
        import webbrowser
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
