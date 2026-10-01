"""회귀 테스트 — LLM 호출 없이 몇 초 안에 끝난다. 고친 뒤 먼저 이것부터:

    python3 -m unittest discover -s tests -v

실험 폴더를 임시 폴더로 복사해서 쓰므로 저장소의 데이터는 바뀌지 않는다.
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

APP = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, APP)

from engine import (assign, config, humanize, jobs, prompts, registry, runner, schema,  # noqa: E402
                    scoring, steps, store)


def copy_exp(rel):
    d = tempfile.mkdtemp(prefix="faultline-test-")
    dst = os.path.join(d, os.path.basename(rel))
    shutil.copytree(os.path.join(APP, rel), dst, ignore=shutil.ignore_patterns("jobs"))
    return d, dst


class Barrier(unittest.TestCase):
    def test_static_declaration(self):
        bad = [dict(registry.get("link"), reads=["behaviors", "ground_truth"])]
        with self.assertRaises(RuntimeError):
            registry.check_barrier(bad)

    def test_read_blocks_hidden(self):
        with self.assertRaises(store.BarrierError):
            store.read(os.path.join(APP, "experiments", "tv-v1"), "ground_truth")

    def test_pipeline_prompts_carry_no_answers(self):
        root = os.path.join(APP, "experiments", "tv-v1")
        gt = store.read(root, "ground_truth", allow_hidden=True)
        poles = [t["pole_a"] for t in gt["tensions"]] + [t["pole_b"] for t in gt["tensions"]]
        for sid in ("extract", "link", "principle", "scenario", "judge"):
            text = "".join(b["text"] for b in prompts.build(root, sid))
            self.assertNotIn("HT_0", text, sid)
            for p in poles:
                self.assertNotIn(p, text, sid)


class Corpus(unittest.TestCase):
    def test_shuffle_renumbers_per_batch(self):
        rows = [{"id": "RAW_001", "raw_text": "a", "_batch": 0, "label": {}},
                {"id": "RAW_002", "raw_text": "b", "_batch": 0, "label": {"twin_of": "RAW_001"}},
                {"id": "RAW_001", "raw_text": "c", "_batch": 1, "label": {}}]
        out = jobs._shuffle_corpus(rows, "seed")
        ids = [r["id"] for r in out]
        self.assertEqual(sorted(ids), ["RAW_001", "RAW_002", "RAW_003"])
        a = next(r for r in out if r["raw_text"] == "a")
        b = next(r for r in out if r["raw_text"] == "b")
        self.assertEqual(b["label"]["twin_of"], a["id"])
        self.assertTrue(all("_batch" not in r for r in out))

    def test_check_corpus_rejects_garbage(self):
        self.assertTrue(steps.check_corpus([{"command": "cat x"}])[0])
        self.assertEqual(steps.check_corpus([])[0], ["행 0개"])

    def test_check_ground_truth(self):
        gt = store.read(os.path.join(APP, "experiments", "tv-v1"), "ground_truth", allow_hidden=True)
        self.assertEqual(steps.check_ground_truth([gt], 6), [])
        self.assertTrue(steps.check_ground_truth([gt], 4))          # 6개인데 quick(4±1) 기준이면 걸린다
        self.assertTrue(steps.check_ground_truth([{"tensions": []}]))

    def test_generate_counts_add_up(self):
        """member 요청 + 배정한 twin·부정문 함정 = 정책의 소속 원문 수 범위."""
        import re as _re
        gt = {"tensions": [{"id": "HT_0{}".format(i)} for i in range(1, 5)]}
        cfg = dict(config.SIZES["quick"], parallel=3)
        bs = prompts._generate_batches("{{GROUND_TRUTH}}{{SCOPE}}{{ID_START}}", gt, cfg)
        text = "".join(b["text"] for b in bs)
        lo, hi = cfg["members"]
        for i in range(1, 5):
            t = "HT_0{}".format(i)
            m = _re.search(t + r" (\d+)(?:~(\d+))?", text.split("| member |")[1 if i <= 2 else 2])
            mlo, mhi = int(m.group(1)), int(m.group(2) or m.group(1))
            tw = sum(int(x) for x in _re.findall(t + r" (\d+)쌍", text))
            ng = sum(int(x) for x in _re.findall(t + r" (\d+)개", text))
            self.assertEqual((mlo + tw + ng, mhi + tw + ng), (lo, hi), t)

    def test_parse_multiline_object(self):
        rows, err = jobs.parse_output('```json\n{\n "a": 1\n}\n```')
        self.assertEqual((rows, err), ([{"a": 1}], []))


class WithCopy(unittest.TestCase):
    def setUp(self):
        self.tmp, self.root = copy_exp("experiments/tv-v1")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_config_roundtrip_and_qa_rules(self):
        c = config.set(self.root, size="quick", brevity="short", profile="check", polish="off", family="off")
        self.assertEqual((c["size"], c["tensions"], c["brevity"], c["profile"]), ("quick", 4, "short", "check"))
        self.assertEqual(config.qa_rules(self.root)["per_tension_members"], (5, 6))
        with self.assertRaises(ValueError):
            config.set(self.root, size="huge")

    def test_check_profile_plan(self):
        config.set(self.root, profile="check")
        self.assertEqual(runner.plan(self.root, "generate"), ["generate", "split", "extract", "link", "score"])
        config.set(self.root, assign="on")
        self.assertEqual(runner.plan(self.root, "link"), ["link", "assign", "score"])
        config.set(self.root, assign="off")
        config.set(self.root, profile="full", family="off", polish="off")
        seq = runner.plan(self.root, "judge")
        self.assertNotIn("family", seq)
        self.assertNotIn("polish", seq)
        self.assertEqual(seq[-1], "score")

    def test_brevity_and_tech_blocks(self):
        config.set(self.root, brevity="short")
        b = store.read(self.root, "brief")
        b["technology"] = "에이전틱 AI"
        store.write(self.root, "brief", b, keep_prev=False)
        text = prompts.build(self.root, "scenario")[0]["text"]
        self.assertIn("길이 규칙", text)
        self.assertIn("agent_actions", text)
        self.assertNotIn("기반 기술 규칙", prompts.build(self.root, "link")[0]["text"])   # 증거 층에는 안 붙는다

    def test_baseline_split_disjoint(self):
        import re as _re
        config.set(self.root, baseline_split="avoid")
        scen = "".join(b["text"] for b in prompts.build(self.root, "scenario"))
        judge = "".join(b["text"] for b in prompts.build(self.root, "judge"))
        shown, held = prompts.baseline_halves(store.read(self.root, "baseline"))
        self.assertIn("뻔한 방향", scen)
        self.assertTrue(all(x["mechanism"] in scen for x in shown))
        self.assertFalse(any(x["mechanism"] in scen for x in held))          # 보관분은 시나리오가 못 본다
        self.assertEqual(set(_re.findall(r"BAS_\d+", judge)), {x["id"] for x in held})
        config.set(self.root, baseline_split="off")
        self.assertNotIn("뻔한 방향", prompts.build(self.root, "scenario")[0]["text"])

    def test_shortlist_diverse_and_polish_scope(self):
        res = steps.shortlist(self.root)
        self.assertEqual(len(res["picks"]), 5)
        self.assertEqual(len({p["tension_id"] for p in res["picks"]}), 5)
        config.set(self.root, polish="shortlist")
        items = [i for b in prompts.build(self.root, "polish") for i in b["items"]]
        self.assertEqual(sorted(items), sorted(p["scenario_id"] for p in res["picks"]))

    def test_polish_gate(self):
        src = store.read(self.root, "scenarios")[0]
        e = src["experience"]
        cut = e.rfind(". ", 0, len(e) - 2)
        ok = {"id": "POL_001", "target_id": src["id"], "is_synthetic": True,
              "fields": {"experience": e[:cut + 1], "takeaway": e[cut + 2:]}}
        bad = {"id": "POL_002", "target_id": "SCN_999", "fields": {}, "is_synthetic": True}
        rows, errors, _ = humanize.gate(self.root, [ok, bad])
        self.assertEqual(len(errors), 1)
        self.assertIn(rows[0]["status"], ("accepted", "warned"))     # 문장 이동은 과윤문이 아니다
        self.assertLess(rows[0]["gate"]["change_rate"], 0.05)

    def test_validate_clean(self):
        self.assertEqual(schema.run(self.root)["errors"], [])


class AssignMerge(unittest.TestCase):
    def test_rules(self):
        link = [{"id": "TEN_001", "member_ids": ["B1", "B2", "B5"], "counterexample_ids": ["B3"]},
                {"id": "TEN_002", "member_ids": ["B4"], "counterexample_ids": []}]
        rec = lambda b, t, role, d="accept": {"item_id": b, "result": {"tension_id": t, "role": role, "decision": d}}
        records = [rec("B1", None, None),               # 방해물 → 무소속
                   rec("B2", "TEN_002", "MEMBER"),      # 다른 tension 으로
                   rec("B3", None, None),               # 연결 반례를 무소속이라 해도 반례 유지 (규칙 3)
                   rec("B4", "TEN_002", "COUNTER"),     # 역할만 바뀜
                   rec("B5", None, None, "review"),     # review → 연결 유지
                   rec("B6", "TEN_001", "MEMBER")]      # 연결이 놓친 것
        out, ch = assign.merge(link, records, version="v1")
        t1, t2 = out
        self.assertEqual(t1["member_ids"], ["B5", "B6"])
        self.assertEqual(t1["counterexample_ids"], ["B3"])
        self.assertEqual(t2["member_ids"], ["B2"])
        self.assertEqual(t2["counterexample_ids"], ["B4"])
        self.assertEqual(ch, {"to_none": 1, "moved": 1, "role": 1, "added": 1, "kept_counter": 1, "kept_member": 0})
        out, ch = assign.merge(link, records, version="v2")      # v2(비교용): 연결 member(B4)를 반례로 바꾸지 않는다
        self.assertEqual(out[1]["member_ids"], ["B2", "B4"])
        self.assertEqual(ch["kept_member"], 1)
        out, ch = assign.merge(link, records, version="v3")      # v3: 같은 tension 에서 member → 반례면 뺀다
        self.assertEqual((out[1]["member_ids"], out[1]["counterexample_ids"]), (["B2"], []))
        self.assertEqual(ch["dropped"], 1)


class Atomic(unittest.TestCase):
    def test_reader_never_sees_half_file(self):
        import threading
        d = tempfile.mkdtemp(prefix="faultline-test-")
        fp = os.path.join(d, "job.json")
        big = {"log": ["x" * 200] * 2000}
        store.atomic_json(fp, big)
        stop, bad = threading.Event(), []

        def reader():
            while not stop.is_set():
                try:
                    with open(fp, encoding="utf-8") as f:
                        json.load(f)
                except ValueError as e:
                    bad.append(e)
        t = threading.Thread(target=reader)
        t.start()
        for _ in range(40):
            store.atomic_json(fp, big)
        stop.set()
        t.join()
        shutil.rmtree(d, ignore_errors=True)
        self.assertEqual(bad, [])


class Pool(unittest.TestCase):
    def test_pool_of_one_equals_phase0(self):
        root = os.path.join(APP, "experiments", "tv-v1")
        one, pooled = scoring.phase0(root), scoring.pool([root, root])
        for a, b in zip(one["verdicts"], pooled["verdicts"]):
            self.assertEqual(a["verdict"], b["verdict"], a["metric"])
            if a.get("n"):
                self.assertEqual(b["n"], 2 * a["n"])
                self.assertAlmostEqual(a["value"], b["value"])


class Mini(unittest.TestCase):
    def test_planted_errors_still_caught(self):
        res = scoring.phase0(os.path.join(APP, "examples", "mini"))
        self.assertEqual(sum(1 for v in res["verdicts"] if v["verdict"] == "FAIL"), 5)


if __name__ == "__main__":
    unittest.main()
