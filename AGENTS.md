# AGENTS.md — Faultline 인수인계 (다른 AI·사람이 이어서 작업할 때 먼저 읽는다)

Last updated: 2026-09-28 (15:30)

## 이게 뭔가

행동 → tension(욕구 충돌) → principle → 미래 가정 → 시나리오 사슬을 **원문까지 추적 가능하게** 만드는 로컬 웹 앱. 지금은 **Phase 0**: 정답을 심은 합성 데이터로 "연결 로직이 구조를 되찾는가"를 채점한다. 실데이터 단계(Phase 1)는 아직 아니다.

## 먼저 읽을 순서

1. `README.md` — 실행 방법·탭·폴더
2. `docs/ARCHITECTURE.md` — 계층·스테이지·정보 차단선·실행 모델·자동 실행·API (단일 설명서)
3. `docs/DATA_GENERATION_POLICY.md` — 정답표·함정 8종·문체 분포·금지 사항
4. `experiments/*/FINDINGS.md` — 실제 돌린 결과와 드러난 약점
5. 필요할 때: `docs/SCHEMA.md`(레코드 형식) · `docs/PHASE0_PLAN.md`(채점 지표) · `docs/JUDGE.md`(판단 모듈)

코드 구조의 단일 출처는 `engine/registry.py`(스테이지 목록). 전체 구조·동작 원리 보고서는 `docs/ARCHITECTURE.md`(§1.1 한눈에 · §13 실험으로 확인한 것). 구조도·파이프라인 화면·차단선 검사가 전부 이 파일을 읽는다.

## 실행·검증

- Python 3.7+ 표준 라이브러리만. 외부 패키지 없음. **3.7 호환을 깨지 말 것**(walrus·`list[str]` 런타임 표기 등 금지).
- `sh faultline serve --open` (웹) · `sh faultline auto --root experiments/<이름> [--size quick]` (전 과정 자동) · `sh faultline list`
- LLM 단계는 `claude` CLI(`claude -p`)로 돈다. 로그인 필요. 없으면 웹의 수동 모드(프롬프트 복사·결과 붙여넣기).
- 고친 뒤 최소 검증 (LLM 호출 없음, 몇 초):
  - `python3 -m unittest discover -s tests` → 전부 OK. 차단선·재번호·검사·설정·후보 추리기·윤문 게이트를 본다.
  - `python3 faultline.py score --root examples/mini` → **FAIL 5 가 그대로** 나와야 한다(예제에 일부러 심은 오류).
  - `python3 faultline.py validate --root experiments/tv-v1` → 오류 0.
  - `python3 -m judge selftest` → 43/43.
  - 웹을 띄워 8개 탭이 콘솔 오류 없이 열리는지.

## 깨면 안 되는 것 (불변식)

1. **정보 차단선.** `hidden/`(정답표·라벨)은 평가자 스테이지(00·01·02·90)만 읽는다. 파이프라인 스테이지가 hidden 키를 `reads` 에 선언하면 서버가 뜨지 않는다(`registry.check_barrier`). `store.read` 는 기본으로 hidden 을 막고, 평가자 코드만 `allow_hidden=True` 를 넘긴다. 우회하지 말 것.
2. **같은 corpus 로 프롬프트를 고치고 재채점하지 않는다.** 시험 문제에 맞춘 튜닝이 된다. 연결·추출 로직을 고쳤으면 **새 실험(새 corpus)** 으로 검증한다. 임계값도 채점 결과를 보고 바꾸지 않는다.
3. **모델 분리.** 생성(01)과 연결(20), 시나리오(40)와 평가(50)는 다른 호출·가능하면 다른 모델. 실행기는 도구 없이·프로젝트 밖 임시 폴더에서·사용자 설정/메모리 없이 돈다(`engine/executors.py`) — 이 격리를 약하게 만들지 말 것.
4. **원본 보존.** 윤문(70)은 원본을 바꾸지 않고 `data/polish/` 에 따로 둔다. 추적·평가·채점의 근거는 언제나 원본.
5. **모델 출력은 저장 전에 검증.** `jobs.finalize` → 스키마·참조·구조 검사 → 오류면 `needs_review` 로 저장 보류. 검증을 건너뛰는 경로를 만들지 말 것.
6. 합성 데이터에는 시스템이 `is_synthetic` 을 붙인다(모델 값을 믿지 않는다).

## 스테이지를 추가·변경할 때

`engine/registry.py` 에 한 줄 → (LLM 이면) `prompts/NN_*.md` + `engine/prompts.py` 조립 규칙 → (새 산출물이면) `engine/store.py` FILES · `engine/schema.py` SPECS → 자동 실행 순서면 `engine/runner.py` AUTO → `docs/ARCHITECTURE.md` §3 표. 구조도는 자동으로 따라온다.

## 현재 상태 (2026-09-28 14:45 — 자동 개선 루프 종료)

- 실험 9개, 전부 합성 데이터. 표준: `tv-v1`(9/10) · `familyhub-v1`(8/10) · **`work-agent-v1`(마지막 루프, standard·short·필터, 21.5분, 첫 10/10)**. quick·short·에이전틱 AI 6개: `phone-agent-v1`(16분, 9/10) · `phone-agent-v2`(16.6분, 8/10) · `watch-agent-v1`(13.8분, 4/10 — 심은 tension 2개가 겹침) · `earbuds-agent-v1`(17분, 8/10) · `photo-agent-v1`(22.9분 — 멈춘 호출 7분, 8/10) · `shop-agent-v1`(13.5분, 필터 후 7/10). 결과·원인은 각 `FINDINGS.md`. 실행 기록 `runs/history/`.
- `faultline pool`(9개 합산): 지표 10개 모두 PASS. 실험별 FAIL 은 서로 다른 지표에 흩어진다. quick 한 판은 판정 5개가 분모 5 미만(「표본 작음」) — **속도·구조 확인용**, 연결 로직 판단은 standard 나 합산으로.
- **22 판단 필터 B**(`config.assign=on`, 규칙 `assign_rule` v1 기본·v2·v3, `engine/assign.py`, 백엔드 `claude_cli` verbal): 사전 고정 규칙으로 신규 corpus 6개 — 연결 단독 침입이 0.00 이면 효과 없음~약간 손해(2/2), 0.22 이상이면 이득(3/3). 기본 off. 라벨 없이 "연결이 흐트러졌다"를 알아챌 신호는 아직 없다(`docs/JUDGE.md` §8). A·C 미연결. Jev 는 early access 라 호출 불가.
- **기준선 반 나누기**(`baseline_split` off·held·avoid): 비교 2회 1승 1패, 기본 off.
- 반복되는 약점: 반례 보존(연결·B 공통) · 방해물 침입(corpus 에 따라 0.00~0.38) · 시나리오 근거 부족 탈락이 corpus 마다 흔들림.
- 측정 쪽 발견: 맥락 날조 판정의 약 40% 는 생성 라벨 오류 — `hallucinated_context_literal` 로 따로 보인다. 01 생성은 twin·부정문 함정의 tension 을 코드가 정한다(이후 QA 첫 판 통과 2/2).
- 속도: quick 약 11~13분(필터·재생성·멈춘 호출 제외). 호출 시간 제한 quick 300초·standard 600초.
- 방향(2026-09-28 사용자): 테스트는 짧게(quick · short · 필요하면 check), 모바일 기기 포함, 기반 기술 에이전틱 AI(새 실험 기본값).

## 다음 할 일 후보 (우선순위 순)

1. 22 필터를 조건부로 켤 신호 — 라벨 없이 "연결이 흐트러졌다"를 알아챌 지표 찾기 (필터는 흐트러진 corpus 3/3 에서 이득). 판단 한 번에 `judge_runs/<ID>/tensions.v1·v2·v3.jsonl` 이 모두 저장된다. **규칙은 corpus 를 보기 전에 고정**
1-1. standard 에서 60 family 가 병목(238초, 한 번 호출) — 시나리오 20개 이상이면 나눠 묶고 합치는 방식
2. 반례 보존 — 20 연결 프롬프트의 반례 정의 점검(새 corpus 로 검증)
3. 뻔함 탈락이 많아 후보가 5개 미만 — 40 시나리오와 05 기준선의 거리, 50 평가의 뻔함 기준 점검
4. 판단 모듈 A(extract_check) — 부정문 뒤집힘 자리. 질문이 많아(행동당 약 5개) 비용 먼저 추정

## 작업 관례

- 사용자 대상 문서·주석은 한국어. 날짜는 YYYY-MM-DD.
- 공유 문서(README·docs)는 전면 재작성하지 말고 부분 수정 — 다른 작업자가 넣은 절을 덮어쓴 사고가 있었다.
- 커밋 전 `git status` 로 `*.prev`·로그가 딸려 가지 않는지 본다(.gitignore 가 대부분 막는다). 절대 경로·키가 파일에 들어가지 않게.
- 라이선스 MIT(`LICENSE`). `vendor/im-not-ai` 는 원저작자의 MIT — 원본 LICENSE 를 유지한다. 작업 저장소(비공개)와 공개 저장소(`faultline-public`, 이력 없이 스냅샷만)가 따로 있다. 공개본으로 내보낼 때는 개인 이메일·절대 경로가 섞이지 않았는지 다시 확인한다.
