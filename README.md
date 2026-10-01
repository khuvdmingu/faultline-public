# Faultline

> 행동과 행동 사이의 **단층선(tension)** 을 찾아, 거기서 시나리오를 캐내는 시스템.

현실의 행동·회피·우회·관습을 구조화하고, 그 밑의 욕구 충돌(tension)에서 원리·미래 가정·시나리오로 넓힌 뒤, 사람이 발전시킬 것을 고르게 하는 실험 시스템이다. 모든 산출물은 원문까지 추적된다. 원 설계 문서: `~/Documents/Codex/2026-09-27/referenced-chatgpt-conversation-this-is-an/outputs/시나리오_발굴_시스템_상세_정리.md`

**지금 단계: Phase 0** — 실데이터 전에, 정답을 미리 심어둔 AI 생성 데이터로 **데이터 생성과 연결 로직이 제대로 도는지**를 채점한다.

## 실행 — 프로그램처럼

- **더블클릭:** `Faultline.app` — 터미널 창 하나에 서버를 띄우고 브라우저를 연다. 끝내려면 그 창에서 Ctrl+C(또는 창 닫기). 처음 한 번은 macOS 가 "터미널 제어" 허용을 묻는다.
- **터미널:** 어느 폴더에서든 `sh <앱 폴더>/faultline …`

```bash
sh faultline serve --open                                   # 웹 화면
sh faultline new fridge-v1 --device "패밀리허브 냉장고" --domain "주방의 식재료 관리와 가족 소통"
sh faultline auto --root experiments/fridge-v1              # 정답표 → … → 후보 추리기 → 채점, 자동
sh faultline list                                           # 실험별 자동 실행 상태·다음 단계
sh faultline auto --root experiments/fridge-v1 --size quick --brevity short   # 짧은 테스트(≈13분)
sh faultline auto --root experiments/fridge-v1 --assign on  # 20 연결 뒤 판단 필터 B(22) 추가 (≈+3분)
sh faultline history --root experiments/fridge-v1           # 실행 기록 — 설정·시간·글 길이·판정
sh faultline pool                                           # 여러 실험 Phase 0 합산 (quick 한 판은 표본이 작다)
sh faultline score --root … --tensions data/linked/tensions_link.jsonl   # 연결 결과를 바꿔 끼워 비교(저장 안 함)
```

**자동 실행**은 정답표(없을 때만 생성) → 합성 생성 → 라벨 분리 → 기준선 → 추출 → 연결 → 유추 → 패키지 → principle → 미래 가정 → 시나리오 → 평가 → family → 윤문 → **후보 추리기** → 채점까지 한 번에 돈다. 사람 검토는 넣지 않는다 — 결과는 자동 후보 목록(`data/shortlist/shortlist.json`, 웹 「후보·검토」 탭)으로 나오고, 사람 검토는 그 뒤에 원하면 한다. 검증 오류가 나면 저장하지 않고 멈추며, 고친 뒤 「이어서 실행」하면 빈 단계부터 다시 돈다. 합성 데이터 품질 검사가 「재생성 권장」이면 생성을 한 번 다시 돈다. 웹에서는 파이프라인 탭의 「전체 자동 실행」·「새 실험 만들기」가 같은 일을 한다. 자동 실행에는 claude CLI 로그인이 필요하다(구독 사용량에서 차감).

Claude 데스크톱 앱 미리보기에서는 `.claude/launch.json` 의 `faultline` 구성으로 띄운다 (macOS 권한 문제로 `~/.local/bin/python3.11` 사용). Python 3.7+ 표준 라이브러리만 쓴다.

웹 화면이 기본 인터페이스다. 프론트(`web/`)는 백엔드 API 만 호출하고, 작업 생성·배치 실행·검증·저장은 전부 백엔드(`server.py` + `engine/`)가 한다.

| 탭 | 하는 일 |
|---|---|
| 구조도 | 전체 15 스테이지 · 5층 · 정보 차단선. 백엔드 등록부에서 그려지고 산출물 상태가 색으로 보인다 |
| 파이프라인 | 스테이지 실행. LLM 스테이지는 작업을 만들면 **자동(claude CLI)** 또는 **수동(복사·붙여넣기)** 으로 채운다. 검증 오류가 있으면 저장을 보류하고 결정을 묻는다 |
| 추적 탐색 | tension → 검색 패키지 → 유추 → principle → 미래 가정 → 시나리오 → 평가, 그리고 원문 구절까지 |
| 시나리오 지도 | 근거 × 새로움 산점도, family 목록, 표 보기 |
| 후보·검토 | 자동 후보(75) 목록 + (선택) 블라인드 사람 검토 · 이유 필수. 블라인드 중에는 자동 순위를 숨긴다 |
| 커버리지 | 행동 종류 × 감상 단계, tension 별 분포, 공백 |
| 채점·품질 | (평가자 모드) Phase 0 채점 · 합성 데이터 품질 검사 · 후반 지표 |
| 문서 | 아래 문서들 |

CLI 도 같은 엔진을 쓴다: `python3 faultline.py stages|split|qa|package|validate|score|coverage|prompt|run|executors|serve|new|auto|shortlist|list`

## 문서

| 문서 | 내용 |
|---|---|
| [AGENTS.md](AGENTS.md) | **이어서 작업할 때 먼저** — 읽을 순서, 검증 명령, 깨면 안 되는 규칙, 현재 상태, 다음 할 일 (다른 AI 공통) |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 전체 구조와 로직 — 계층, 스테이지, 데이터 흐름, 정보 차단선, 실행 모델, API, 확장 지점 |
| [docs/DATA_GENERATION_POLICY.md](docs/DATA_GENERATION_POLICY.md) | 데이터 생성 정책 — 정답표 설계, 함정 8종, 문체 분포, 모델 분리, 검수, 금지, 실데이터 전환 |
| [docs/PHASE0_PLAN.md](docs/PHASE0_PLAN.md) | Phase 0 계획과 사전 고정 통과 기준 |
| [docs/SCHEMA.md](docs/SCHEMA.md) | 엔티티별 데이터 형식 |
| [docs/JUDGE.md](docs/JUDGE.md) · [judge-architecture.html](docs/judge-architecture.html) | 판단 모듈 — 원자 질문 → 선택지별 확률, 백엔드 교체(mock·OpenAI·OpenRouter·로컬·Jev) |

## 폴더

```text
faultline/
├── server.py        백엔드 API + 웹 서빙
├── faultline.py     CLI
├── engine/          registry · store · schema · prompts · jobs · executors · steps · qa · scoring · review
├── judge/           판단 모듈 — Jev 교체형 typed judge (독립 패키지, 파이프라인 미연결) · docs/JUDGE.md
├── web/             프론트 (index.html · styles.css · js/)
├── prompts/         LLM 스테이지 템플릿 (00·05·10·20·25·30·35·40·50·60·70)
├── vendor/im-not-ai/ 한국어 윤문 규칙·게이트 (MIT, 필요한 파일만 · VENDOR.md)
├── docs/            구조 · 정책 · 계획 · 형식
├── experiments/     실험별 루트 — tv-v1 (AI TV, 정답 tension 6개)
├── examples/mini/   동작 확인용 초소형 예제 (일부러 틀린 곳 포함)
└── scripts/         호환용 래퍼 (구버전 명령). build_report.py·report_template.html·common.py 는 삭제 후보
```

실험 하나 = 폴더 하나: `hidden/`(평가자 전용 정답) · `data/`(파이프라인) · `review/`(사람 결정) · `runs/`(작업 기록·원본 출력·채점) · `brief.json`(파이프라인이 보는 탐색 과제).

## 판단 모듈 (judge/)

다른 세션에서 만든 독립 패키지다. 판단을 "상태 + 닫힌 선택지 질문 → 선택지별 확률" 모양으로 쪼개 두어, 지금은 logprobs 를 주는 모델로 돌리고 Jev early access 가 열리면 백엔드만 바꾼다. 붙일 자리는 세 곳이다 — A: 10 추출 뒤 검사 · B: 20 연결을 후보 생성(20a)과 배정(20b)으로 나눈 배정 · C: 40 시나리오 뒤 지도화. 아직 파이프라인에 연결하지 않았다. 붙이는 순서와 방법은 [docs/JUDGE.md](docs/JUDGE.md) §6, 자체 검사는 `python3 -m judge selftest`.

## 지켜야 할 규칙

1. **생성과 해석을 분리한다.** 합성 생성(01)과 tension 연결(20)은 다른 모델, 시나리오(40)와 평가(50)도 다른 모델.
2. **hidden/ 은 파이프라인에 들어가지 않는다.** 코드가 선언·읽기 두 곳에서 막고, CLI 실행기는 도구 없이 워크스페이스 밖에서 돈다. 수동 실행 때는 사람이 지킨다.
3. **합성 데이터는 증거가 아니다.** 모든 파생물은 `is_synthetic: true` 이고, 실데이터 실험과 섞지 않는다.
4. **기준은 실행 전에 고정한다.** 결과를 보고 정답표나 통과 기준을 바꾸지 않는다.

## 예제로 확인하기

`examples/mini` 에는 채점이 오류를 잡는지 보이려고 **일부러 틀린 곳 5개**가 들어 있다. 채점 화면에서 FAIL 5개, 검증에서 오류 1건(끊긴 근거 참조)이 나오는 것이 정상이다.

## 라이선스

MIT — `LICENSE`. 포함된 `vendor/im-not-ai/` 는 원저작자의 MIT 라이선스(`vendor/im-not-ai/LICENSE`)를 따른다.

실험 폴더의 데이터는 전부 LLM 이 만든 **합성 데이터**다(실존 인물·회사 내부 정보 없음). LLM 단계를 자동으로 돌리려면 `claude` CLI 로그인이 필요하고, 없으면 웹의 수동 모드(프롬프트 복사·결과 붙여넣기)로 쓴다. 테스트(`python3 -m unittest discover -s tests`)와 채점·검증·웹 열람은 LLM 없이 돈다.
