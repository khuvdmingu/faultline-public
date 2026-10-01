# hidden/ — 정답 금고

이 폴더의 파일은 **파이프라인(10 추출 · 20 연결 · 30 원리 · 40 시나리오) 세션에 절대 넣지 않는다.** 들어가는 순간 채점이 무의미해진다.

| 파일 | 누가 만드나 | 누가 읽나 |
|---|---|---|
| `ground_truth.json` | 사람 (예시: `ground_truth.example.json`) | 00 생성 모델, `score.py` |
| `corpus_labeled.jsonl` | 00 생성 모델 | `split_corpus.py` |
| `labels.json` | `split_corpus.py` | `score.py` |

실데이터 단계(Phase 1)에서도 이 폴더는 평가자 전용으로 유지한다.
