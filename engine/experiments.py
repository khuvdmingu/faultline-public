"""새 실험 만들기 — experiments/<이름>/ 에 brief.json 과 빈 hidden/·data/ 를 둔다.

brief 는 파이프라인에 공개되는 탐색 과제다. 정답 tension 을 적지 않는다(적으면 채점이 무의미해진다).
정답표는 자동 실행의 00 단계가 brief 에서 만들거나, 사람이 hidden/ground_truth.json 에 직접 쓴다.
"""
import os
import re

from . import config, store

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,39}$")
DEFAULT_EXCLUDE = ["특정 회사 내부 정보", "실존 인물 특정"]
DEFAULT_TECH = "에이전틱 AI — 사용자의 목표를 받아 스스로 계획하고, 여러 앱·기기·서비스에서 대신 행동하며, 필요한 순간에만 사람에게 묻는 AI"


def _lines(v):
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    return [x.strip() for x in re.split(r"[\n,·]", v or "") if x.strip()]


def create(name, domain, device, device_traits=None, surroundings=None, exclude=None, size=None, parallel=None,
           technology=None, brevity=None, profile=None):
    name = (name or "").strip().lower()
    if not NAME_RE.match(name):
        raise ValueError("실험 이름은 영문 소문자·숫자·하이픈 2~40자 (예: fridge-v1)")
    if not (domain or "").strip() or not (device or "").strip():
        raise ValueError("domain(탐색 영역)과 device(기기)는 꼭 적는다")
    rel = "experiments/{}".format(name)
    root = os.path.join(store.APP_ROOT, rel)
    if os.path.exists(root):
        raise ValueError("이미 있는 실험: {}".format(rel))
    for d in ("hidden", "data", "runs", "review"):
        os.makedirs(os.path.join(root, d))
    brief = {"domain": domain.strip(), "device": device.strip(),
             "device_traits": _lines(device_traits), "surroundings": _lines(surroundings),
             "exclude": _lines(exclude) or DEFAULT_EXCLUDE,
             "technology": (technology or "").strip() or DEFAULT_TECH,
             "note": "파이프라인에 공개되는 탐색 과제. 정답 tension 을 적지 않는다."}
    store.write(root, "brief", brief, keep_prev=False)
    cfg = config.set(root, size or config.DEFAULT["size"], parallel, brevity, profile)
    return {"root": rel, "brief": brief, "config": {k: cfg[k] for k in config.DEFAULT}}
