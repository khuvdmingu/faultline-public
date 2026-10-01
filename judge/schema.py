"""판단 질문과 답의 타입. Jev(TypeSafe System One)의 질문 타입과 1:1로 대응한다.

  noul   예/아니오 확률 하나      Jev: Noul(instructions=...)      → NoulAnswer(noul=p)
  choice 닫힌 선택지 중 하나      Jev: Choice(criteria=[...])      → ChoiceAnswer(choice, confidence, probabilities)
  score  순서 있는 등급 중 하나   Jev: Score(criteria=[...])       → ScoreAnswer(score, confidence, probabilities, legend)

Jev 쪽 이름·필드는 공식 어댑터(system-one-adapter-python) 소스에서 확인한 것이다 (2026-09-27).
Choice·Score 생성자가 instructions 를 받는지는 확인하지 못했다 — backends.py 의 to_sdk() 한 곳에만 가정을 둔다.
"""
import math

KINDS = ("noul", "choice", "score")
MAX_OPTIONS = 255          # Jev 공개 제약: 구조화 출력 cardinality ≤ 255
NOUL_OPTIONS = [{"value": "yes", "desc": "예"}, {"value": "no", "desc": "아니오"}]


class QuestionError(ValueError):
    pass


class Question:
    """원자 질문 하나. 상태(state)는 질문 밖에서 따로 넘긴다."""

    def __init__(self, id, kind, text, options=None, policy=None, unknown_value=None, bank=None):
        self.id = id
        self.kind = kind
        self.text = text
        self.options = NOUL_OPTIONS if kind == "noul" else list(options or [])
        self.policy = dict(policy or {})
        self.unknown_value = unknown_value      # "판정 불가" 선택지 값. 고르면 사람 검토로 보낸다
        self.bank = bank                        # "extract_check@v1" 처럼 출처 질문 은행·버전
        self.validate()

    def validate(self):
        if not self.id or not self.text:
            raise QuestionError("id·text 가 비어 있다: {!r}".format(self.id))
        if self.kind not in KINDS:
            raise QuestionError("{}: kind 는 {} 중 하나".format(self.id, KINDS))
        values = [o["value"] for o in self.options]
        if len(values) != len(set(values)):
            raise QuestionError("{}: 선택지 값이 중복된다".format(self.id))
        if not 2 <= len(values) <= MAX_OPTIONS:
            raise QuestionError("{}: 선택지는 2~{}개 (지금 {})".format(self.id, MAX_OPTIONS, len(values)))
        if self.unknown_value is not None and self.unknown_value not in values:
            raise QuestionError("{}: unknown_value 가 선택지에 없다".format(self.id))

    @property
    def values(self):
        return [o["value"] for o in self.options]

    def to_dict(self):
        return {"id": self.id, "kind": self.kind, "text": self.text, "options": self.options,
                "unknown_value": self.unknown_value, "bank": self.bank}


def normalize(raw, values):
    """선택지 밖 값은 버리고 합이 1이 되게 한다. (확률, 선택지에 실린 질량) 반환."""
    probs = {v: max(0.0, float(raw.get(v, 0.0))) for v in values}
    mass = sum(probs.values())
    if mass <= 0:
        return {v: 1.0 / len(values) for v in values}, 0.0
    return {v: p / mass for v, p in probs.items()}, mass


class Answer:
    """질문 하나에 대한 확률 분포와 그 출처."""

    def __init__(self, question, probs, method, backend, model=None, mass=None,
                 usage=None, latency_ms=None, error=None):
        self.question = question
        self.probs = probs              # {선택지 값: 확률}, 합 1
        self.method = method            # logprobs · sampling(k) · verbal · mock · jev
        self.backend = backend
        self.model = model
        self.mass = mass                # logprobs 일 때 유효 선택지에 실린 원래 질량 (낮으면 형식 이탈)
        self.usage = usage or {}
        self.latency_ms = latency_ms
        self.error = error

    def ranked(self):
        return sorted(self.probs.items(), key=lambda kv: -kv[1])

    @property
    def top(self):
        return self.ranked()[0][0]

    @property
    def p_top(self):
        return self.ranked()[0][1]

    @property
    def margin(self):
        r = self.ranked()
        return r[0][1] - (r[1][1] if len(r) > 1 else 0.0)

    @property
    def entropy(self):
        """0(확신) ~ 1(균등). 선택지 수로 정규화."""
        n = len(self.probs)
        h = -sum(p * math.log(p) for p in self.probs.values() if p > 0)
        return h / math.log(n) if n > 1 else 0.0

    @property
    def p_yes(self):
        return self.probs.get("yes") if self.question.kind == "noul" else None

    @property
    def expected(self):
        """score 의 기대 등급 (1부터). 다른 종류는 None."""
        if self.question.kind != "score":
            return None
        return sum((i + 1) * self.probs.get(v, 0.0) for i, v in enumerate(self.question.values))

    def to_dict(self):
        d = {"question_id": self.question.id, "kind": self.question.kind, "bank": self.question.bank,
             "probs": {k: round(v, 4) for k, v in self.probs.items()},
             "top": self.top, "p_top": round(self.p_top, 4), "margin": round(self.margin, 4),
             "entropy": round(self.entropy, 4), "method": self.method, "backend": self.backend,
             "model": self.model}
        if self.expected is not None:
            d["expected"] = round(self.expected, 3)
        if self.mass is not None:
            d["mass"] = round(self.mass, 4)
        if self.usage:
            d["usage"] = self.usage
        if self.latency_ms is not None:
            d["latency_ms"] = self.latency_ms
        if self.error:
            d["error"] = self.error
        return d
