# vendor/im-not-ai

- 출처: https://github.com/epoko77-ai/im-not-ai
- 커밋: `2f3d943d08056b612a92e12bfb72ea94dd2acd18` (main, 2026-09-26 push)
- 가져온 날: 2026-09-27 · 라이선스: MIT (`LICENSE` 원문 동봉)
- 방식: 저장소 tarball 에서 아래 파일만 골라 원본 그대로 복사했다. 수정하지 않았다. `install.sh` 는 실행하지 않았다(워크스페이스 밖 `~/.claude` 에 설치하는 스크립트라서).

| 파일 | 쓰는 곳 |
|---|---|
| `skills/humanize-korean/references/quick-rules.md` | `prompts/70_polish.md` 의 `{{RULES}}` — 윤문 규칙표 |
| `scripts/prepare_monolith_input.py` | `engine/humanize.prescore` — 묶음별 정량 사전 점수(표준 경로의 입력 shim)를 `{{METRICS}}` 에 |
| `scripts/verify_gates.py` | `engine/humanize.run_gates` — 윤문 후 코드 게이트(변경률·수치·서법) |
| `scripts/checks.py` · `restore_modality.py` · `console.py` · `verify_change_rate.py` | verify_gates 의존 |
| `skills/humanize-korean/references/metrics.py` · `metrics_v2.py` · `baseline.json` · `baseline_v2.json` | verify_gates 의존 (정량 지표·기준선) |

갱신: 새 커밋의 같은 경로 파일로 덮어쓰고 이 표의 커밋 해시를 바꾼다. 게이트 판정 방식이 바뀌면 `engine/humanize.py` 의 `EXIT` 매핑을 확인한다.
