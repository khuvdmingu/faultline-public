"""Faultline 판단 모듈 — Jev(TypeSafe System One)로 교체 가능한 typed judge.

파이프라인(scripts/)과 연결되지 않은 독립 패키지다. 붙이는 자리와 방법은 docs/JUDGE.md.

    from judge import make_backend, Question, decide
    backend = make_backend("openrouter", model="...")        # 또는 "mock" · "openai" · "custom" · "adapter" · "jev"
    q = Question("has_device", "noul", "원문에 기기가 명시돼 있다.")
    answer = backend.ask(state_text, [q])["has_device"]
    decide(answer)   # {"decision": "accept"|"review", "value": True/False/None, "reasons": [...]}

Python 3.7+, 표준 라이브러리만 (adapter·jev 백엔드는 해당 패키지를 설치했을 때만).
"""
from .backends import BACKENDS, BackendUnavailable, make_backend
from .policy import decide
from .schema import Answer, Question
from .tasks import TASKS

__all__ = ["Answer", "BACKENDS", "BackendUnavailable", "Question", "TASKS", "decide", "make_backend"]
