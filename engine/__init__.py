"""Faultline engine — 스테이지 등록부·저장소·검증·실행기·작업 큐.

계층 (docs/ARCHITECTURE.md):
  store     파일 저장소 (JSONL/JSON, 직전 판 보관, 경로 키)
  registry  스테이지 정의 (입력·출력·실행 방식·정보 차단선)
  schema    레코드 검증 (형식·ID·참조·원문 인용)
  prompts   LLM 스테이지 프롬프트 조립·배치 분할
  steps     결정적 스테이지 (분리·검색 패키지·커버리지)
  qa        합성 corpus 품질 검사 (데이터 생성 정책의 자동 집행)
  scoring   Phase 0 채점 (정답 라벨 대조)
  executors LLM 실행기 (manual · claude_cli)
  jobs      작업 큐 (배치 실행·ID 재번호·출처 기록·자동 검증)
  review    인간 검토 결정
"""
