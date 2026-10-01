"""LLM 실행기.

manual      프롬프트를 사람이 복사해 채팅·서브에이전트에서 돌리고 결과를 붙여넣는다. 항상 사용 가능.
claude_cli  `claude -p` 를 백엔드가 직접 호출한다. 구독 로그인(claude.ai)이면 플랜 사용량에서 차감되고
            API 요금은 없다. API 키 환경변수가 있으면 API 과금이 될 수 있으니 health 에서 경고한다.

격리 (docs/ARCHITECTURE.md §5):
  - 도구 없음(--tools "") → 모델이 파일을 읽을 수 없다. 입력은 프롬프트 본문뿐이다.
  - 작업 디렉터리 = 프로젝트 밖 임시 폴더 → 상위 폴더의 CLAUDE.md·메모리가 자동으로 붙지 않는다.
  - 세션 저장 안 함, 슬래시 커맨드·MCP 끔.
  - 기본 시스템 프롬프트를 짧은 작업자 지시로 교체하고, 사용자 설정·자동 메모리를 끈다.
    (2026-09-27 실측: 이것이 없으면 임시 폴더에서도 사용자 메모리 안내가 붙어,
     모델이 데이터 대신 "메모리 확인" 도구 호출문을 출력했다.)
"""
import os
import shutil
import subprocess
import tempfile
import time

MODELS = ["haiku", "sonnet", "opus"]
_HEALTH = {"at": 0, "result": None}
HEALTH_TTL = 300

# 데스크톱 앱 안에서 서버를 띄우면 부모 세션용 변수가 상속돼 자식 CLI 인증이 꼬인다 — 떼어낸다.
_PARENT_VARS_PREFIX = ("CLAUDE_CODE_", "CLAUDE_AGENT_SDK")
_PARENT_VARS = {"CLAUDECODE", "CLAUDE_PID", "CLAUDE_EFFORT", "CLAUDE_PREVIEW_CLASSIFIER_FLOOR"}

WORKER_SYSTEM = ("You are a data-processing worker inside a batch pipeline. No tools, files, memory or "
                 "prior context are available; everything you need is in the user message. "
                 "Follow the user message exactly and output only what it asks for.")


def claude_bin():
    return shutil.which("claude") or os.path.expanduser("~/.local/bin/claude")


def _env():
    env = dict(os.environ)
    inside_app = "CLAUDECODE" in env
    for k in list(env):
        if k in _PARENT_VARS or k.startswith(_PARENT_VARS_PREFIX):
            env.pop(k, None)
    env["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] = "1"
    if inside_app:
        env.pop("ANTHROPIC_BASE_URL", None)
    return env


def run_cli(prompt, model, timeout=900):
    """프롬프트 → 모델 출력 텍스트. 실패하면 RuntimeError."""
    exe = claude_bin()
    if not os.path.exists(exe):
        raise RuntimeError("claude CLI 를 찾지 못했다")
    cmd = [exe, "-p", "--model", model, "--tools", "", "--no-session-persistence",
           "--disable-slash-commands", "--strict-mcp-config", "--output-format", "text",
           "--system-prompt", WORKER_SYSTEM, "--setting-sources", "",
           "--settings", '{"autoMemoryEnabled": false}']
    with tempfile.TemporaryDirectory(prefix="faultline-exec-") as cwd:
        try:
            p = subprocess.run(cmd, input=prompt, cwd=cwd, env=_env(), capture_output=True,
                               text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            raise RuntimeError("시간 초과 ({}초)".format(timeout))
    out = (p.stdout or "").strip()
    if p.returncode != 0 or out.startswith("Failed to authenticate") or "API Error" in out[:200]:
        msg = (out or p.stderr or "").strip().splitlines()
        raise RuntimeError(msg[0] if msg else "종료 코드 {}".format(p.returncode))
    return out


def health(refresh=False):
    """claude_cli 사용 가능 여부. 짧은 haiku 호출로 확인하고 5분 캐시한다."""
    if not refresh and _HEALTH["result"] and time.time() - _HEALTH["at"] < HEALTH_TTL:
        return _HEALTH["result"]
    warn = []
    if os.environ.get("ANTHROPIC_API_KEY"):
        warn.append("ANTHROPIC_API_KEY 가 설정돼 있다 — 구독 대신 API 과금이 될 수 있다")
    try:
        out = run_cli("다른 말 없이 OK 두 글자만 출력해.", "haiku", timeout=90)
        ok = "OK" in out.upper()
        res = {"claude_cli": {"ok": ok, "message": "사용 가능" if ok else "응답 이상: {}".format(out[:60]),
                              "warnings": warn}}
    except RuntimeError as e:
        msg = str(e)
        hint = ""
        if "401" in msg or "authenticate" in msg.lower():
            hint = "터미널에서 `claude` 를 실행해 /login 으로 다시 로그인하면 풀린다"
        res = {"claude_cli": {"ok": False, "message": msg, "hint": hint, "warnings": warn}}
    res["manual"] = {"ok": True, "message": "항상 사용 가능 — 프롬프트 복사 · 결과 붙여넣기"}
    res["checked_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    _HEALTH.update(at=time.time(), result=res)
    return res
