"""22 판단 필터 (B) — 20 연결 뒤에 판단 모듈 assign 으로 행동마다 배정을 다시 묻고, 정해 둔 규칙으로 합친다.

config.assign = on 일 때만 자동 실행에 들어간다. 판단은 judge/ 의 claude_cli 백엔드(verbal)로,
파이프라인과 같은 격리 실행기에서 돈다. 정답표(hidden/)는 읽지 않는다 — 후보는 20 연결이 찾은 tension 의 두 극뿐.

합치는 규칙 (2026-09-28, phone-agent-v1 비교 뒤·새 corpus 로 검증하기 전에 고정):
  1. B 가 accept 한 행동 → B 의 답이 이긴다 (다른 tension 의 member · 반례 · 무소속).
  2. B 가 review 로 보낸 행동 → 20 연결의 배정을 그대로 둔다.
  3. 예외: 20 연결이 반례로 둔 행동을 B 가 무소속(NONE)이라 하면 반례로 남긴다.
     반례는 "한쪽 욕구가 없는 행동"이라 B 의 첫 질문(어느 tension 인가)에서 무소속과 헷갈린다 — B 단독 비교에서 반례 보존이 떨어진 자리.
  4. tension 은 버리지 않는다 (20 연결이 찾은 것). member 가 비면 그대로 둔다 — 검증이 경고한다.
  5. (v2 — 채택 안 함, 비교용으로만 남김) B 가 반례라고 해도 20 연결이 member 로 둔 행동이면 연결을 유지.
     사후 계산(본 corpus 라 검증 아님)에서 v2 는 20 연결 단독과 사실상 같았다 — v1 의 이득(침입·반례)도 손해(한 tension
     붕괴)도 모두 이 "member → 반례" 변경에서 나왔다. 기본은 사전 고정한 v1.
  6. (v3, 2026-09-28 10:10 고정 — 다섯 번째 corpus 전) 20 연결이 member 로 둔 행동을 B 가 같은 tension 의 반례라 하면
     옮기지 않고 **뺀다**(member 도 반례도 아님). 연결이 끌어들인 방해물은 빠지고, 진짜 member 를 잃어도 반례로 둔갑하지
     않아 반례 지표가 부풀지 않는다. 다른 tension 으로의 이동·무소속 판정은 v1 과 같다.
20 연결의 원래 출력은 data/linked/tensions_link.jsonl 에 두고, data/linked/tensions.jsonl 을 합친 결과로 바꾼다.
판단 기록은 judge_runs/<실행 ID>/assign.jsonl.
"""
import datetime
import os
from concurrent.futures import ThreadPoolExecutor

from . import config, store

RULE_VERSION = "v1"
RULE = ("B accept 우선 · review 는 20 연결 유지 · 연결 반례를 B 가 무소속이라 하면 반례 유지 · tension 은 버리지 않음 · "
        "(v1)")


def merge(link_tensions, records, version=RULE_VERSION):
    """20 연결 tension 목록 + assign 기록 → 합친 tension 목록과 바뀐 수."""
    link_role = {}                                        # 행동 → (tension, MEMBER|COUNTER)
    for t in link_tensions:
        for b in t.get("member_ids", []):
            link_role[b] = (t["id"], "MEMBER")
        for b in t.get("counterexample_ids", []):
            link_role[b] = (t["id"], "COUNTER")
    final = dict(link_role)
    changed = {"to_none": 0, "moved": 0, "role": 0, "added": 0, "kept_counter": 0, "kept_member": 0}
    for r in records:
        b, res = r["item_id"], r["result"]
        if res["decision"] != "accept":
            continue                                      # 규칙 2
        old = link_role.get(b)
        if res["tension_id"] is None:
            if old and old[1] == "COUNTER":               # 규칙 3
                changed["kept_counter"] += 1
                continue
            if old:
                changed["to_none"] += 1
                final.pop(b, None)
            continue
        new = (res["tension_id"], "COUNTER" if res.get("role") == "COUNTER" else "MEMBER")
        if version == "v2" and new[1] == "COUNTER" and old and old[1] == "MEMBER":   # 규칙 5 (비교용)
            changed["kept_member"] += 1
            continue
        if version == "v3" and old and old[1] == "MEMBER" and new == (old[0], "COUNTER"):   # 규칙 6
            changed["dropped"] = changed.get("dropped", 0) + 1
            final.pop(b, None)
            continue
        if old is None:
            changed["added"] += 1
        elif old[0] != new[0]:
            changed["moved"] += 1
        elif old[1] != new[1]:
            changed["role"] += 1
        final[b] = new                                    # 규칙 1
    out = []
    for t in link_tensions:                               # 규칙 4 — 순서·필드 유지
        row = dict(t)
        row["member_ids"] = sorted(b for b, (tid, role) in final.items() if tid == t["id"] and role == "MEMBER")
        row["counterexample_ids"] = sorted(b for b, (tid, role) in final.items() if tid == t["id"] and role == "COUNTER")
        out.append(row)
    return out, changed


def run(root, model="sonnet", workers=None, version=None):
    """자동 실행·/api/run 용. 20 연결 원본을 보관하고 합친 결과로 tensions 를 바꾼다."""
    from judge import backends as jb
    from judge import store as jstore
    from judge.tasks import TASKS

    src = store.read(root, "tensions")
    if not src:
        return {"errors": ["20 연결 결과(tensions)가 없다"]}
    if all(t.get("assign_filtered") for t in src):        # 이미 거른 결과면 원본에서 다시
        src = store.read(root, "tensions_link") or src
    src = [{k: v for k, v in t.items() if k != "assign_filtered"} for t in src]
    store.write(root, "tensions_link", src, keep_prev=False)

    task = TASKS["assign"](root, None, candidates=store.path(root, "tensions_link"))
    items = task.items()
    backend = jb.make_backend("claude_cli", model)
    n = workers or config.get(root)["parallel"]
    started = datetime.datetime.now()
    with ThreadPoolExecutor(max(1, n)) as ex:
        records = list(ex.map(lambda it: task.run_item(backend, it), items))
    run_id = started.strftime("%Y%m%d-%H%M%S")
    out_dir = os.path.join(root, "judge_runs", run_id)
    jstore.write_jsonl(os.path.join(out_dir, "assign.jsonl"), records)
    errors = sum(1 for r in records for a in r["answers"].values() if a.get("error"))
    version = version or config.get(root).get("assign_rule") or RULE_VERSION
    merged, changed = merge(src, records, version)
    variants = {v: merge(src, records, v)[0] for v in ("v1", "v2", "v3")}     # 같은 판단으로 규칙별 결과 — 비교용
    for t in merged:
        t["assign_filtered"] = run_id
    summary = task.summarize(records)
    jstore.write_json(os.path.join(out_dir, "manifest.json"), {
        "run_id": run_id, "task": "assign", "bank": task.bank["_tag"], "backend": backend.describe(),
        "started": started.isoformat(timespec="seconds"),
        "finished": datetime.datetime.now().isoformat(timespec="seconds"),
        "items": len(records), "errors": errors, "summary": summary, "rule": RULE, "rule_version": version,
        "changed": changed,
        "source": "pipeline 22"})
    if errors > len(records) // 2:
        return {"errors": ["판단 호출 오류 {}건 / {} — tensions 를 바꾸지 않았다".format(errors, len(records))]}
    for v, rows in variants.items():
        jstore.write_jsonl(os.path.join(out_dir, "tensions.{}.jsonl".format(v)), rows)
    store.write(root, "tensions", merged)
    return {"errors": [], "run_id": run_id, "items": len(records), "summary": summary, "changed": changed,
            "judge_errors": errors}
